"""laygo2_safe — a thin, strict layer over laygo2 for the SKY130 workspace.

laygo2's architecture stays as it is (templates = bricks, grids = stud spacing, Design = the board).
This layer only removes the traps that made LLM-written generators crash or short (baseline
2026-09-30, failure types A and D):

  * every function returns one kind of object; nothing is "a Rect or a list depending on the case"
  * inputs are validated with messages that say what to do instead (rows of unequal length, a pin
    where an instance is expected, a point taken on one grid and routed on another)
  * wire() refuses two points that are not on one track instead of silently filling a rectangle

Stage 1 (this file) is the shell. Stage 2 adds net-aware connect() with a track occupancy table,
stage 3 an abstract connectivity check against the netlist.

Typical use (run from the workspace root, LAYOUT_OUT_DIR set):

    from laygo2_safe import Cell
    c = Cell("inv_2x")
    n0 = c.nmos("MN0", nf=2, tie="S")
    p0 = c.pmos("MP0", nf=2, tie="S")
    c.place_rows([n0], [p0])
    i_w = c.wire("r23", c.pt(n0, "G", "r23"), c.pt(p0, "G", "r23"), vias=(True, True))
    ...
    c.export()
"""
import os
from pathlib import Path

import numpy as np

import laygo2
import laygo2.interface
import laygo2_tech as tech

GRID_NAMES = {"pg": "placement_basic", "r12": "routing_12_cmos", "r23": "routing_23_cmos",
              "r34": "routing_34_basic"}
__all__ = ["Cell", "Point", "SafeError", "GRID_NAMES"]


class SafeError(Exception):
    """A usage error with a message that says what to do instead."""


class Point(np.ndarray):
    """An abstract coordinate [m, n] that remembers the grid it was taken on."""
    def __new__(cls, mn, grid: str):
        obj = np.asarray(mn, dtype=int).view(cls)
        if obj.shape != (2,):
            raise SafeError(f"a Point must be [m, n], got shape {obj.shape}")
        obj.grid = grid
        return obj

    def __array_finalize__(self, obj):
        self.grid = getattr(obj, "grid", None)

    def shifted(self, dm=0, dn=0):
        """The point moved by whole tracks on the same grid."""
        return Point([int(self[0]) + dm, int(self[1]) + dn], self.grid)


def _is_inst(x):
    return isinstance(x, (laygo2.object.physical.Instance, laygo2.object.physical.VirtualInstance))


class Cell:
    """One layout cell. Wraps a laygo2 Library + Design and the SKY130 templates and grids."""

    def __init__(self, name: str, libname: str = "logic_ver2", out_dir=None):
        self.name, self.libname = name, libname
        self.out_dir = Path(out_dir or os.environ.get("LAYOUT_OUT_DIR", f"runs/golden/{name}")).resolve()
        self.templates = tech.load_templates()
        self._grids = tech.load_grids(templates=self.templates)
        self.lib = laygo2.object.database.Library(name=libname)
        self.dsn = laygo2.object.database.Design(name=name, libname=libname)
        self.lib.append(self.dsn)
        self.instances = {}
        self.ports = {}
        self._placed = False

    # ---- grids -----------------------------------------------------------------------------
    def grid(self, g: str):
        """A laygo2 grid by short name: 'pg', 'r12', 'r23', 'r34' (long names also accepted)."""
        key = GRID_NAMES.get(g, g)
        if key not in self._grids:
            raise SafeError(f"unknown grid {g!r}; use one of {list(GRID_NAMES)}")
        return self._grids[key]

    # ---- instances -------------------------------------------------------------------------
    def nmos(self, name: str, nf: int = 2, tie=None):
        """An nfet_01v8_lvt with nf fingers (W = 0.5 µm per finger). tie: 'S', 'D' or None."""
        return self._mos("nmos", name, nf, tie, transform="R0")

    def pmos(self, name: str, nf: int = 2, tie=None):
        """A pfet_01v8 with nf fingers (W = 1.0 µm per finger), mirrored so its rail is on top."""
        return self._mos("pmos", name, nf, tie, transform="MX")

    def _mos(self, kind, name, nf, tie, transform):
        if name in self.instances:
            raise SafeError(f"instance name {name!r} is already used")
        if not isinstance(nf, int) or nf < 2 or nf % 2:
            raise SafeError(f"nf must be an even integer >= 2, got {nf!r}")
        if tie not in (None, "S", "D"):
            raise SafeError(f"tie must be 'S', 'D' or None, got {tie!r}")
        inst = self.templates[kind].generate(name=name, transform=transform, params={"nf": nf, "tie": tie})
        inst._safe = {"kind": kind, "nf": nf, "tie": tie}
        self.instances[name] = inst
        return inst

    def pins(self, inst) -> list:
        """Pin names an instance actually has ('S' disappears when the source is tied)."""
        self._check_inst(inst)
        return sorted(inst.pins.keys())

    # ---- placement -------------------------------------------------------------------------
    def place_rows(self, nmos_row, pmos_row, mn=(0, 0)):
        """Place the nfets left to right on the bottom row and the pfets left to right directly above.
        The rows may have different lengths. Each element is an instance or None (a gap of one
        instance width is not supported yet: None is simply skipped)."""
        if self._placed:
            raise SafeError("place_rows() was already called for this cell")
        pg = self.grid("pg")
        rows = []
        for label, row in (("nmos_row", nmos_row), ("pmos_row", pmos_row)):
            if _is_inst(row):
                raise SafeError(f"{label} must be a list of instances, got a single instance")
            row = [x for x in row if x is not None]
            for x in row:
                self._check_inst(x)
            rows.append(row)
        nrow, prow = rows
        for inst in nrow:
            if inst._safe["kind"] != "nmos":
                raise SafeError(f"{inst.name} is a pmos but was put in nmos_row")
        for inst in prow:
            if inst._safe["kind"] != "pmos":
                raise SafeError(f"{inst.name} is an nmos but was put in pmos_row")
        cursor = np.array(mn, dtype=int)
        for inst in nrow:
            self.dsn.place(grid=pg, inst=inst, mn=cursor)
            cursor = pg.mn.bottom_right(inst)
        if nrow:
            top = pg.mn.top_left(nrow[0])
        else:
            top = np.array(mn, dtype=int)
        cursor = top
        for inst in prow:
            self.dsn.place(grid=pg, inst=inst, mn=cursor + pg.mn.height_vec(inst))
            cursor = pg.mn.bottom_right(inst)
        self._placed = True

    # ---- coordinates -----------------------------------------------------------------------
    def pt(self, inst, pin: str, g: str, end: str = "left") -> Point:
        """One point of a pin on grid g. Pins G and D are single points; S and RAIL span several
        columns, so choose end='left' or end='right'."""
        self._check_inst(inst)
        if pin not in inst.pins:
            have = ", ".join(sorted(inst.pins))
            hint = " ('S' is tied to the rail, so there is no S pin)" if pin == "S" and inst._safe.get("tie") == "S" else ""
            raise SafeError(f"{inst.name} has no pin {pin!r}{hint}; it has {have}")
        if end not in ("left", "right"):
            raise SafeError("end must be 'left' or 'right'")
        box = self.grid(g).mn(inst.pins[pin])
        return Point(box[0] if end == "left" else box[1], g)

    def span(self, inst, pin: str, g: str):
        """Both ends of a pin on grid g as (left Point, right Point)."""
        return self.pt(inst, pin, g, "left"), self.pt(inst, pin, g, "right")

    # ---- wires -----------------------------------------------------------------------------
    def wire(self, g: str, a: Point, b: Point, vias=(False, False)):
        """A straight wire on grid g between two points that share a row or a column. Returns the
        wire (Rect). vias=(at a, at b) adds vias at the ends. Points on different rows and columns
        are refused: use track() for those."""
        a, b = self._check_pts(g, a, b)
        if a[0] != b[0] and a[1] != b[1]:
            raise SafeError(f"wire() needs two points on one track; {a.tolist()} and {b.tolist()} differ in both "
                            f"m and n (laygo2 would fill the whole rectangle between them). Use track().")
        grid = self.grid(g)
        objs = self.dsn.route(grid=grid, mn=[a, b], via_tag=list(vias))
        if isinstance(objs, list):
            rects = [o for o in objs if isinstance(o, laygo2.object.physical.Rect)]
            return rects[0]
        return objs

    def track(self, g: str, points, track, vias_at_pins=False):
        """Join several points through one shared track on grid g. track=('v', m) is the vertical
        track at column m, ('h', n) the horizontal track at row n. Each point gets a stub to the
        track. Returns the wire on the track. vias_at_pins=True puts a via at each point as well."""
        if len(points) < 2:
            raise SafeError("track() needs at least two points")
        pts = self._check_pts(g, *points)
        if not (isinstance(track, (tuple, list)) and len(track) == 2 and track[0] in ("v", "h")):
            raise SafeError("track must be ('v', column) or ('h', row)")
        kind, idx = track
        if kind == "v":
            for p in pts:
                if p[0] == idx:
                    raise SafeError(f"track ('v', {idx}) runs through the pin at {p.tolist()}; pick a column with no pin")
            t = [int(idx), None]
        else:
            for p in pts:
                if p[1] == idx:
                    raise SafeError(f"track ('h', {idx}) runs through the pin at {p.tolist()}; pick a row with no pin")
            t = [None, int(idx)]
        via_tag = [True, True] if vias_at_pins else [None, True]
        objs = self.dsn.route_via_track(grid=self.grid(g), mn=list(pts), track=t, via_tag=via_tag)
        return objs[-1]

    def via(self, g: str, p: Point):
        """A via at point p connecting the two layers of grid g."""
        (p,) = self._check_pts(g, p)
        return self.dsn.via(grid=self.grid(g), mn=p)

    # ---- ports -----------------------------------------------------------------------------
    def port(self, name: str, g: str, wire):
        """Mark a wire as the cell port `name` (must be the netlist port name, used once)."""
        if name in self.ports:
            raise SafeError(f"port {name!r} was already created")
        if not isinstance(wire, laygo2.object.physical.Rect):
            raise SafeError(f"port() needs the wire object returned by wire()/track(), got {type(wire).__name__}")
        grid = self.grid(g)
        self.ports[name] = self.dsn.pin(name=name, grid=grid, mn=grid.mn.bbox(wire))
        return self.ports[name]

    # ---- export ----------------------------------------------------------------------------
    def export(self):
        """Write <out_dir>/<name>.tcl (and let magic save the .mag under <out_dir>/<libname>/)."""
        if not self._placed:
            raise SafeError("nothing placed: call place_rows() first")
        os.makedirs(self.out_dir / self.libname, exist_ok=True)
        path = self.out_dir / f"{self.name}.tcl"
        laygo2.interface.magic.export(self.lib, filename=str(path), cellname=None, libpath=str(self.out_dir),
                                      scale=0.5, reset_library=False, tech_library="sky130A")
        return path

    # ---- checks ----------------------------------------------------------------------------
    def _check_inst(self, x):
        if not _is_inst(x):
            raise SafeError(f"expected an instance (from nmos()/pmos()), got {type(x).__name__}")
        if not hasattr(x, "_safe"):
            raise SafeError(f"instance {getattr(x, 'name', '?')} was not created through this Cell")

    def _check_pts(self, g, *pts):
        out = []
        for p in pts:
            if not isinstance(p, Point):
                raise SafeError(f"expected a Point from pt()/span()/shifted(), got {type(p).__name__} {p!r}")
            if p.grid != g:
                raise SafeError(f"point {p.tolist()} was taken on grid {p.grid!r} but is used on {g!r}; "
                                f"take it with pt(inst, pin, {g!r})")
            out.append(p)
        return out
