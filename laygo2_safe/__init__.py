"""laygo2_safe — a thin, strict, net-aware layer over laygo2 for the SKY130 workspace.

laygo2's architecture stays as it is (templates = bricks, grids = stud spacing, Design = the board).
This layer removes the traps that made LLM-written generators crash or short (baseline 2026-09-30):

  stage 1  every function returns one kind of object; inputs are validated with messages that say
           what to do instead; wire() refuses two points that are not on one track
  stage 2  the cell keeps an occupancy table of every pin, wire and via as physical rectangles per
           layer, tagged with a net. connect(net, pins) draws a direct wire when it is free and
           otherwise searches nearby tracks, refusing any geometry that would touch (short) or come
           closer than the layer's spacing rule to another net
  stage 3  check(netlist) compares the nets the pins were connected to with the reference netlist,
           before any EDA tool runs

Typical use (run from the workspace root, LAYOUT_OUT_DIR set):

    from laygo2_safe import Cell
    c = Cell("inv_2x")
    n0 = c.nmos("MN0", nf=2, tie="S", ref="XM1")
    p0 = c.pmos("MP0", nf=2, tie="S", ref="XM2")
    c.place_rows([n0], [p0])
    w_i = c.connect("I", [(n0, "G"), (p0, "G")], "r23")
    w_o = c.connect("O", [(n0, "D"), (p0, "D")], "r23")
    w_vss = c.connect("VSS", [(n0, "RAIL"), (n0, "RAIL", "right")], "r12")
    ...
    c.port("I", "r23", w_i); ...
    print(c.check("ref/netlist/inv.spice"))   # [] when consistent
    c.export()
"""
import os
import re
from pathlib import Path

import numpy as np

import laygo2
import laygo2.interface
import laygo2_tech as tech

GRID_NAMES = {"pg": "placement_basic", "r12": "routing_12_cmos", "r23": "routing_23_cmos",
              "r34": "routing_34_basic"}
UNIT_UM = 0.005                                    # one laygo2 unit is 5 nm in this workspace
# Minimum same-layer spacing (SKY130: li.3 = 0.17 µm, m1.2 = 0.14 µm, m2.2 = 0.14 µm), in units.
LAYER_SPACING = {"locali": 34, "metal1": 28, "metal2": 28}
# Half-widths used for zero-width pins and vias (pins and via cells are stored as centrelines).
PIN_HALF = {"locali": 17, "metal1": 26, "metal2": 26}   # via pads stay inside the wire end (measured)
SEARCH_RADIUS = 6                                  # tracks tried on each side in connect()
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


def _flat(objs):
    for o in objs if isinstance(objs, list) else [objs]:
        if isinstance(o, list):
            yield from _flat(o)
        elif o is not None:
            yield o


class _Occ:
    """One occupied rectangle: layer name, expanded box [[x0, y0], [x1, y1]], net (None = not yet
    assigned) and a human-readable owner such as 'MN0.G' or 'net A wire'."""
    __slots__ = ("layer", "box", "net", "owner")

    def __init__(self, layer, box, net, owner):
        self.layer, self.box, self.net, self.owner = layer, np.asarray(box, dtype=int), net, owner

    def gap(self, other):
        """Distance between two boxes (0 when they touch or overlap)."""
        dx = max(other.box[0][0] - self.box[1][0], self.box[0][0] - other.box[1][0], 0)
        dy = max(other.box[0][1] - self.box[1][1], self.box[0][1] - other.box[1][1], 0)
        return max(dx, dy) if (dx == 0 or dy == 0) else float(np.hypot(dx, dy))


class Cell:
    """One layout cell. Wraps a laygo2 Library + Design, the SKY130 templates and grids, and an
    occupancy table used by connect() and check()."""

    def __init__(self, name: str, libname: str = "logic_ver2", out_dir=None, rails=("VSS", "VDD"), netlist=None):
        self.name, self.libname = name, libname
        self.rails = {"nmos": rails[0], "pmos": rails[1]}
        # With the reference netlist known up front, ref='XMn' lets nmos()/pmos() and connect() reject a
        # wrong tie or a pin on the wrong net immediately, at the line that is wrong.
        self.netlist_path = netlist
        self._nl_ports, self._nl_devices = (None, None)
        if netlist:
            ports, devs = _parse_netlist(Path(netlist).read_text())
            self._nl_ports, self._nl_devices = ports, {d["name"]: d for d in devs}
        self.out_dir = Path(out_dir or os.environ.get("LAYOUT_OUT_DIR", f"runs/golden/{name}")).resolve()
        self.templates = tech.load_templates()
        self._grids = tech.load_grids(templates=self.templates)
        self.lib = laygo2.object.database.Library(name=libname)
        self.dsn = laygo2.object.database.Design(name=name, libname=libname)
        self.lib.append(self.dsn)
        self.instances = {}
        self.ports = {}
        self._placed = False
        self._occ = []                 # list of _Occ
        self._pin_occ = {}             # (inst name, pin) -> _Occ
        self._pin_extra = {}           # (inst name, pin) -> further _Occ pieces of the same pin
        self._wire_net = {}            # id(Rect) -> net

    # ---- grids -----------------------------------------------------------------------------
    def grid(self, g: str):
        """A laygo2 grid by short name: 'pg', 'r12', 'r23', 'r34' (long names also accepted)."""
        key = GRID_NAMES.get(g, g)
        if key not in self._grids:
            raise SafeError(f"unknown grid {g!r}; use one of {list(GRID_NAMES)}")
        return self._grids[key]

    # ---- instances -------------------------------------------------------------------------
    def nmos(self, name: str, nf: int = 2, tie=None, ref: str = None):
        """An nfet_01v8_lvt with nf fingers (W = 0.5 µm per finger). tie: 'S', 'D' or None.
        ref: the device's name in the reference netlist (e.g. 'XM1'), used by check()."""
        return self._mos("nmos", name, nf, tie, "R0", ref)

    def pmos(self, name: str, nf: int = 2, tie=None, ref: str = None):
        """A pfet_01v8 with nf fingers (W = 1.0 µm per finger), mirrored so its rail is on top."""
        return self._mos("pmos", name, nf, tie, "MX", ref)

    def _mos(self, kind, name, nf, tie, transform, ref):
        if name in self.instances:
            raise SafeError(f"instance name {name!r} is already used")
        if not isinstance(nf, int) or nf < 2 or nf % 2:
            raise SafeError(f"nf must be an even integer >= 2, got {nf!r}")
        if tie not in (None, "S", "D"):
            raise SafeError(f"tie must be 'S', 'D' or None, got {tie!r}")
        if ref and self._nl_devices is not None:
            dev = self._nl_devices.get(ref)
            if dev is None:
                raise SafeError(f"ref {ref!r} is not a device of the netlist; devices are {sorted(self._nl_devices)}")
            want_kind = "nmos" if "nfet" in dev["model"] else "pmos"
            if want_kind != kind:
                raise SafeError(f"{ref} is a {want_kind} in the netlist; use c.{want_kind}() for {name}")
            if dev["m"] != nf:
                raise SafeError(f"{ref} has m={dev['m']} in the netlist, so use nf={dev['m']} for {name}")
            rail = self.rails[kind]
            for term in ("S", "D"):
                on_rail = dev[term] == rail
                if tie == term and not on_rail:
                    raise SafeError(f"{name} ({ref}): tie={term!r} but the netlist puts its {term} on {dev[term]!r}, "
                                    f"not on {rail}; use tie=None and connect it")
                if on_rail and tie != term:
                    raise SafeError(f"{name} ({ref}): its {term} is on {rail} in the netlist; use tie={term!r}")
        inst = self.templates[kind].generate(name=name, transform=transform, params={"nf": nf, "tie": tie})
        inst._safe = {"kind": kind, "nf": nf, "tie": tie, "ref": ref, "transform": transform}
        self.instances[name] = inst
        return inst

    def pins(self, inst) -> list:
        """Pin names an instance actually has ('S' disappears when the source is tied)."""
        self._check_inst(inst)
        return sorted(inst.pins.keys())

    # ---- placement -------------------------------------------------------------------------
    def place_rows(self, nmos_row, pmos_row, mn=(0, 0)):
        """Place the nfets left to right on the bottom row and the pfets left to right directly above.
        The rows may have different lengths; None entries are skipped."""
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
        cursor = pg.mn.top_left(nrow[0]) if nrow else np.array(mn, dtype=int)
        for inst in prow:
            self.dsn.place(grid=pg, inst=inst, mn=cursor + pg.mn.height_vec(inst))
            cursor = pg.mn.bottom_right(inst)
        self._placed = True
        self._register_pins(nrow + prow)

    def _register_pins(self, insts):
        """Record every pin's physical footprint. Pins are centrelines, so the footprints come from
        the drawn template (measured on the golden cells): drain and source contacts are li1 strips
        ~0.24 µm wide running between the source row and the drain row; the gate strap is ~0.4 µm
        wide; the rail is 0.26 µm of metal1."""
        for inst in insts:
            rail_net = self.rails[inst._safe["kind"]]
            shadow = self.templates[inst._safe["kind"]].generate(
                name=inst.name + "__shadow", transform=inst._safe["transform"],
                params={"nf": inst._safe["nf"], "tie": None})
            shadow.xy = inst.xy
            y_d, y_s = int(shadow.pins["D"].bbox[0][1]), int(shadow.pins["S"].bbox[0][1])
            sgn = 1 if y_s > y_d else -1        # direction from the drain row toward the source row
            # measured on the golden cells: the drain strip reaches 105 units toward the source row,
            # the source strips 113 units toward the drain row; the pin stubs are 17 units tall
            d_box_y = sorted([y_d - sgn * 17, y_d + sgn * 105])
            s_box_y = sorted([y_s + sgn * 17, y_s - sgn * 113])
            y_rail = int(inst.pins["RAIL"].bbox[0][1])
            for pn, pin in inst.pins.items():
                layer, b = self._layer_of(pin), np.array(pin.bbox, dtype=int)
                extra = []
                if pn == "D":
                    box = [[b[0][0] - 34, d_box_y[0]], [b[1][0] + 34, d_box_y[1]]]
                elif pn == "S":
                    # a li1 bar along the pin row, 0.225 µm past both contacts, plus the two contact strips
                    box = [[b[0][0] - 45, y_s - 17], [b[1][0] + 45, y_s + 17]]
                    for x in sorted({int(b[0][0]), int(b[1][0])}):
                        extra.append([[x - 24, s_box_y[0]], [x + 24, s_box_y[1]]])
                elif pn == "G":
                    box = [[b[0][0] - 40, b[0][1] - 17], [b[1][0] + 40, b[1][1] + 17]]
                else:  # RAIL
                    box = [[b[0][0], b[0][1] - 26], [b[1][0], b[1][1] + 26]]
                occ = _Occ(layer, box, rail_net if pn == "RAIL" else None, f"{inst.name}.{pn}")
                self._occ.append(occ)
                self._pin_occ[(inst.name, pn)] = occ
                self._pin_extra[(inst.name, pn)] = [_Occ(layer, e, None, f"{inst.name}.{pn}") for e in extra]
                self._occ.extend(self._pin_extra[(inst.name, pn)])
            tie = inst._safe["tie"]
            if tie in ("S", "D"):
                # the tied terminal has no pin, but its contact strips and the li1 straps down to the
                # rail are drawn and sit on the rail net
                b = np.array(shadow.pins[tie].bbox, dtype=int)
                box_y = s_box_y if tie == "S" else d_box_y
                y_pin = y_s if tie == "S" else y_d
                strap_y = sorted([y_rail + (17 if y_rail < y_pin else -17), y_pin + (17 if y_rail < y_pin else -17)])
                for x in sorted({int(b[0][0]), int(b[1][0])}):
                    self._occ.append(_Occ("locali", [[x - 24, box_y[0]], [x + 24, box_y[1]]], rail_net,
                                          f"{inst.name}.{tie} (tied to {rail_net})"))
                    self._occ.append(_Occ("locali", [[x - 26, strap_y[0]], [x + 26, strap_y[1]]], rail_net,
                                          f"{inst.name}.{tie} strap (tied to {rail_net})"))

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

    # ---- manual wires (stage 1 API; also recorded in the occupancy table) --------------------
    def wire(self, g: str, a: Point, b: Point, vias=(False, False), net=None):
        """A straight wire on grid g between two points that share a row or a column. Returns the
        wire (Rect). vias=(at a, at b) adds vias at the ends. Points on different rows and columns
        are refused: use track() or connect()."""
        a, b = self._check_pts(g, a, b)
        if a[0] != b[0] and a[1] != b[1]:
            raise SafeError(f"wire() needs two points on one track; {a.tolist()} and {b.tolist()} differ in both "
                            f"m and n (laygo2 would fill the whole rectangle between them). Use track() or connect().")
        objs = list(_flat(self.grid(g).route(mn=[a, b], via_tag=list(vias))))
        return self._commit(g, objs, net, f"net {net} wire" if net else "wire (no net)")

    def track(self, g: str, points, track, vias_at_pins=False, net=None):
        """Join several points through one shared track on grid g. track=('v', m) is the vertical
        track at column m, ('h', n) the horizontal track at row n. Returns the wire on the track."""
        if len(points) < 2:
            raise SafeError("track() needs at least two points")
        pts = self._check_pts(g, *points)
        t = self._track_arg(track, pts)
        via_tag = [True, True] if vias_at_pins else [None, True]
        objs = list(_flat(self.grid(g).route_via_track(mn=list(pts), track=t, via_tag=via_tag)))
        return self._commit(g, objs, net, f"net {net} track" if net else "track (no net)")

    def via(self, g: str, p: Point, net=None):
        """A via at point p connecting the two layers of grid g."""
        (p,) = self._check_pts(g, p)
        objs = [self.grid(g).via(mn=p)]
        self._commit(g, objs, net, f"net {net} via" if net else "via (no net)", want_rect=False)
        return objs[0]

    # ---- stage 2: net-aware connect ---------------------------------------------------------
    def connect(self, net: str, items, g: str, prefer: str = None):
        """Connect the given pins as net `net` on grid g and return the main wire (for port()).

        items: a list of (inst, pin) or (inst, pin, 'left'|'right') for pins, or Points.
        If all points share a row or a column and the straight wire is free, it is drawn directly.
        Otherwise nearby vertical and horizontal tracks are tried (prefer='v' or 'h' to choose the
        first family) and the first one whose stubs and track touch no other net and keep the layer
        spacing is used. Every pin is assigned to `net`; a pin already on another net is refused."""
        if not self._placed:
            raise SafeError("connect() needs placed instances: call place_rows() first")
        grid = self.grid(g)
        pts, pin_occs = [], []
        for it in items:
            if isinstance(it, Point):
                pts.append(it)
            elif isinstance(it, (tuple, list)) and len(it) in (2, 3) and _is_inst(it[0]):
                inst, pn = it[0], it[1]
                end = it[2] if len(it) == 3 else "left"
                pts.append(self.pt(inst, pn, g, end))
                occ = self._pin_occ[(inst.name, pn)]
                if occ.net not in (None, net):
                    raise SafeError(f"{inst.name}.{pn} is already on net {occ.net!r}; it cannot also be on {net!r} "
                                    f"(check the netlist)")
                ref = inst._safe.get("ref")
                if ref and self._nl_devices is not None and pn in ("D", "G", "S"):
                    want = self._nl_devices[ref][pn]
                    if want != net:
                        raise SafeError(f"{inst.name}.{pn} ({ref}.{pn}) is on net {want!r} in the netlist, not {net!r}")
                if pn == "RAIL" and net != occ.net:
                    raise SafeError(f"{inst.name}.RAIL is the {occ.net} rail; it cannot be connected as {net!r}")
                pin_occs.append(occ)
            else:
                raise SafeError(f"connect() items must be (inst, pin[, end]) or Points, got {it!r}")
        if len(pts) == 1 and len(items) == 1 and isinstance(items[0], (tuple, list)) and len(items[0]) == 2:
            inst, pn = items[0][0], items[0][1]
            left, right = self.span(inst, pn, g)
            if np.array_equal(left, right):
                # a single-point pin (a gate that is a port by itself): a short stub so that a port fits on it
                for occ in pin_occs:
                    occ.net = net
                a = left
                for dm, dn in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                    b = a.shifted(dm, dn)
                    m_lo, m_hi, n_lo, n_hi = self._extent(grid)
                    if not (m_lo <= b[0] <= m_hi and n_lo <= b[1] <= n_hi):
                        continue
                    objs = self._path_objs(grid, [a, b], pin_occs, pin_occs)
                    if not self._conflicts(net, self._rects(g, objs)):
                        return self._commit(g, objs, net, f"net {net} stub")
                raise SafeError(f"connect({net!r}): no free stub next to {inst.name}.{pn}")
            pts = [left, right]
        if len(pts) < 2:
            raise SafeError("connect() needs at least two pins")
        pts = self._check_pts(g, *pts)
        for occ in pin_occs:
            occ.net = net
        for it in items:
            if isinstance(it, (tuple, list)) and _is_inst(it[0]):
                for e in self._pin_extra.get((it[0].name, it[1]), []):
                    e.net = net

        tried = []
        # 1. straight wire when every point shares a row or a column
        same_m, same_n = len({int(p[0]) for p in pts}) == 1, len({int(p[1]) for p in pts}) == 1
        if same_m or same_n:
            order = sorted(pts, key=lambda p: (int(p[1]) if same_m else int(p[0])))
            a, b = order[0], order[-1]
            via_a = self._pin_layer(pin_occs, a) != self._wire_layer(grid, a, b, same_m)
            objs = list(_flat(grid.route(mn=[a, b], via_tag=[via_a, via_a])))
            bad = self._conflicts(net, self._rects(g, objs))
            if not bad:
                return self._commit(g, objs, net, f"net {net} wire")
            tried.append(("straight wire", bad))
        # 2. shared track nearby
        ms = sorted({int(p[0]) for p in pts}); ns = sorted({int(p[1]) for p in pts})
        m_lo, m_hi, n_lo, n_hi = self._extent(grid)
        # tracks between the pins first (shortest stubs, least in the way), then outward
        between_m = [m for m in range(min(ms) + 1, max(ms)) if m not in ms]
        between_n = [n for n in range(min(ns) + 1, max(ns)) if n not in ns]
        outside_m = [m for m in self._spread(ms, SEARCH_RADIUS) if m_lo <= m <= m_hi and m not in ms and m not in between_m]
        outside_n = [n for n in self._spread(ns, SEARCH_RADIUS) if n_lo <= n <= n_hi and n not in ns and n not in between_n]

        def try_tracks(cand_v, cand_h):
            families = [("v", cand_v), ("h", cand_h)]
            if prefer == "h" or (prefer is None and same_n):
                families.reverse()
            for kind, cands in families:
                for idx in cands:
                    t = [idx, None] if kind == "v" else [None, idx]
                    stub_layer = self._stub_layer(grid, kind, pts)
                    via_pins = any(self._pin_layer(pin_occs, p) != stub_layer for p in pts)
                    objs = list(_flat(grid.route_via_track(mn=list(pts), track=t, via_tag=[True if via_pins else None, True])))
                    bad = self._conflicts(net, self._rects(g, objs))
                    if not bad:
                        return self._commit(g, objs, net, f"net {net} track {kind}{idx}")
                    tried.append((f"track {kind}={idx}", bad))
            return None

        # 2. shared track between the pins (short stubs)
        w = try_tracks([m for m in between_m], [n for n in between_n])
        if w is not None:
            return w
        # 3. L- and Z-shaped paths for two pins (short detours), then tracks outside the pins
        if len(pts) == 2:
            a, b = pts
            first_bad = None
            for path in self._zpaths(grid, a, b, SEARCH_RADIUS):
                objs = self._path_objs(grid, path, pin_occs, pin_occs)
                bad = self._conflicts(net, self._rects(g, objs))
                if not bad:
                    return self._commit(g, objs, net, f"net {net} path")
                if first_bad is None:
                    first_bad = f"{[p.tolist() for p in path]}: {bad[0]}"
            tried.append(("L/Z paths", [first_bad or "no candidates"]))
        w = try_tracks(outside_m, outside_n)
        if w is not None:
            return w
        if len(pts) == 2:
            a, b = pts
            # 4. escape on metal2 (grid r34 shares r23's columns): up on metal1, across on metal2, down
            if g == "r23":
                for pairs in self._escape_paths(a, b):
                    rects_all = [r for gg, o in pairs for r in self._rects(gg, [o])]
                    if not self._conflicts(net, rects_all):
                        return self._commit(None, pairs, net, f"net {net} metal2 path")
                tried.append(("metal2 escape paths", ["all candidates blocked"]))
        elif len(pts) > 2:
            # more pins: join the first pin to each other pin, one path at a time
            wires, first = [], pts[0]
            for other in pts[1:]:
                w = self.connect(net, [first, other], g, prefer)
                wires.append(w)
            return wires[-1]
        lines = [f"connect({net!r}) found no free path on {g} for {[p.tolist() for p in pts]}:"]
        for what, bad in tried[:6]:
            lines.append(f"  {what}: {bad[0]}")
        lines.append("  try another grid, a different end of the pin, or move the instances apart")
        raise SafeError("\n".join(lines))

    # ---- ports -----------------------------------------------------------------------------
    def port(self, name: str, g: str, wire):
        """Mark a wire as the cell port `name` (must be the netlist port name, used once)."""
        if name in self.ports:
            raise SafeError(f"port {name!r} was already created")
        if not isinstance(wire, laygo2.object.physical.Rect):
            raise SafeError(f"port() needs the wire object returned by wire()/track()/connect(), got {type(wire).__name__}")
        wnet = self._wire_net.get(id(wire))
        if wnet is not None and wnet != name:
            raise SafeError(f"port {name!r} is being put on a wire of net {wnet!r}")
        grid = self.grid(g)
        self.ports[name] = self.dsn.pin(name=name, grid=grid, mn=grid.mn.bbox(wire))
        return self.ports[name]

    # ---- stage 3: connectivity check against the reference netlist --------------------------
    def check(self, netlist_path=None) -> list:
        """Compare the nets the pins were connected to with the reference netlist. Returns a list
        of problems (empty = consistent). Instances need ref='XMn' to be matched."""
        netlist_path = netlist_path or self.netlist_path
        if not netlist_path:
            raise SafeError("check() needs a netlist: Cell(..., netlist=path) or check(path)")
        ports, devices = _parse_netlist(Path(netlist_path).read_text())
        problems = []
        by_ref = {inst._safe["ref"]: inst for inst in self.instances.values() if inst._safe["ref"]}
        for inst in self.instances.values():
            if not inst._safe["ref"]:
                problems.append(f"{inst.name}: no ref= given, cannot be matched to the netlist")
        for dev in devices:
            inst = by_ref.get(dev["name"])
            if inst is None:
                problems.append(f"netlist device {dev['name']} ({dev['model']}) has no instance with ref={dev['name']!r}")
                continue
            kind = "nmos" if "nfet" in dev["model"] else "pmos"
            if inst._safe["kind"] != kind:
                problems.append(f"{inst.name}: is {inst._safe['kind']} but {dev['name']} is {kind}")
            if inst._safe["nf"] != dev["m"]:
                problems.append(f"{inst.name}: nf={inst._safe['nf']} but {dev['name']} has m={dev['m']}")
            rail = self.rails[kind]
            for term in ("D", "G", "S"):
                want = dev[term]
                tie = inst._safe["tie"]
                if term == tie:
                    if want != rail:
                        problems.append(f"{inst.name}.{term} is tied to {rail} but the netlist puts it on {want}")
                    continue
                if term == "S" and tie == "D":
                    pass
                occ = self._pin_occ.get((inst.name, term))
                if occ is None:
                    problems.append(f"{inst.name}.{term}: pin missing")
                elif occ.net is None:
                    problems.append(f"{inst.name}.{term} is not connected (netlist: {want})")
                elif occ.net != want:
                    problems.append(f"{inst.name}.{term} is on {occ.net} but the netlist puts it on {want}")
                if want == rail and tie != term and term != "G":
                    problems.append(f"{inst.name}.{term} is on {rail} in the netlist: use tie={term!r}")
        for p in ports:
            if p not in self.ports:
                problems.append(f"port {p} not created")
        for p in self.ports:
            if p not in ports:
                problems.append(f"port {p} is not a netlist port")
        return problems

    # ---- export ----------------------------------------------------------------------------
    def export(self):
        """Write <out_dir>/<name>.tcl (magic saves the .mag under <out_dir>/<libname>/)."""
        if not self._placed:
            raise SafeError("nothing placed: call place_rows() first")
        os.makedirs(self.out_dir / self.libname, exist_ok=True)
        path = self.out_dir / f"{self.name}.tcl"
        laygo2.interface.magic.export(self.lib, filename=str(path), cellname=None, libpath=str(self.out_dir),
                                      scale=0.5, reset_library=False, tech_library="sky130A")
        return path

    def occupancy(self):
        """The occupancy table as plain dicts (for viewers and debugging)."""
        return [{"layer": o.layer, "box": o.box.tolist(), "net": o.net, "owner": o.owner} for o in self._occ]

    # ---- internals -------------------------------------------------------------------------
    def _commit(self, g, objs, net, owner, want_rect=True):
        """Add objects made on grid g (or a list of (grid, obj) pairs when g is None) to the design."""
        pairs = objs if g is None else [(g, o) for o in objs]
        rects_all = [r for gg, o in pairs for r in self._rects(gg, [o])]
        bad = self._conflicts(net, rects_all) if net is not None else []
        if bad:
            raise SafeError(f"{owner} would conflict: " + "; ".join(bad[:3]))
        objs = [o for _, o in pairs]
        for o in objs:
            self.dsn.append(o)
        for layer, box in rects_all:
            self._occ.append(_Occ(layer, box, net, owner))
        rects = [o for o in objs if isinstance(o, laygo2.object.physical.Rect)]
        if not want_rect:
            return None
        main = rects[-1]
        for r in rects:
            self._wire_net[id(r)] = net
        return main

    def _rects(self, g, objs):
        """Physical (layer, expanded box) for wires and vias produced on grid g."""
        grid = self.grid(g)
        out = []
        for o in objs:
            if isinstance(o, laygo2.object.physical.Rect):
                box = np.array(o.bbox, dtype=int)
                box[0] -= [o.hextension or 0, o.vextension or 0]
                box[1] += [o.hextension or 0, o.vextension or 0]
                out.append((self._layer_of(o), box))
            elif _is_inst(o):   # via cell: mark both layers of the grid at its position
                xy = np.array(o.xy, dtype=int)
                mn = grid.mn(xy)
                for layer in (str(grid.vlayer[int(mn[0])][0]), str(grid.hlayer[int(mn[1])][0])):
                    h = PIN_HALF.get(layer, 17)
                    out.append((layer, np.array([xy - h, xy + h])))
        return out

    def _conflicts(self, net, rects):
        msgs = []
        for layer, box in rects:
            cand = _Occ(layer, box, net, "new")
            for o in self._occ:
                if o.layer != layer or o.net == net:
                    continue
                gap = cand.gap(o)
                if gap == 0:
                    who = f"{o.owner} (net {o.net})" if o.net else f"{o.owner} (not connected yet)"
                    msgs.append(f"touches {who} on {layer} at x={box[0][0]*UNIT_UM:.2f}..{box[1][0]*UNIT_UM:.2f} µm")
                elif gap < LAYER_SPACING.get(layer, 0):
                    who = f"{o.owner} (net {o.net})" if o.net else o.owner
                    msgs.append(f"only {gap*UNIT_UM:.3f} µm from {who} on {layer} (min {LAYER_SPACING[layer]*UNIT_UM:.2f})")
        return msgs

    @staticmethod
    def _layer_of(obj):
        return str(np.asarray(obj.layer)[0])

    @staticmethod
    def _expand(box, layer):
        h = PIN_HALF.get(layer, 17)
        b = np.array(box, dtype=int)
        return np.array([b[0] - h, b[1] + h])

    @staticmethod
    def _wire_layer(grid, a, b, vertical):
        return str(grid.vlayer[int(a[0])][0]) if vertical else str(grid.hlayer[int(a[1])][0])

    @staticmethod
    def _stub_layer(grid, kind, pts):
        # stubs of a vertical track run horizontally on the row layer of each point (and vice versa)
        p = pts[0]
        return str(grid.hlayer[int(p[1])][0]) if kind == "v" else str(grid.vlayer[int(p[0])][0])

    def _zpaths(self, grid, a, b, radius):
        """Candidate 3-segment paths a -> (m1, na) -> (m1, nt) -> (m2, nt) -> (m2, nb) -> b, nearest first:
        the middle run is on a free row nt (or, mirrored, a free column). Duplicate points are dropped."""
        m_lo, m_hi, n_lo, n_hi = self._extent(grid)
        ma, na, mb, nb = int(a[0]), int(a[1]), int(b[0]), int(b[1])
        rows = [n for n in self._spread(sorted({na, nb}), radius) if n_lo <= n <= n_hi]
        # L-shaped paths first (the middle run on one of the pin rows), then rows between, then outward
        rows = [na, nb] + [n for n in range(min(na, nb) + 1, max(na, nb))] + rows
        cols_a = [ma] + [m for m in self._spread([ma], 2) if m_lo <= m <= m_hi]
        cols_b = [mb] + [m for m in self._spread([mb], 2) if m_lo <= m <= m_hi]
        seen = set()
        for nt in rows:
            for m1 in cols_a:
                for m2 in cols_b:
                    pts = [(ma, na), (m1, na), (m1, nt), (m2, nt), (m2, nb), (mb, nb)]
                    dedup = [pts[0]] + [q for i, q in enumerate(pts[1:], 1) if q != pts[i - 1]]
                    key = tuple(dedup)
                    if key in seen or len(dedup) < 2:
                        continue
                    seen.add(key)
                    yield [Point(q, a.grid) for q in dedup]
        # mirrored: middle run on a free column mt
        cols = [ma, mb] + [m for m in range(min(ma, mb) + 1, max(ma, mb))] + [m for m in self._spread(sorted({ma, mb}), radius) if m_lo <= m <= m_hi]
        rows_a = [na] + [n for n in self._spread([na], 2) if n_lo <= n <= n_hi]
        rows_b = [nb] + [n for n in self._spread([nb], 2) if n_lo <= n <= n_hi]
        for mt in cols:
            for n1 in rows_a:
                for n2 in rows_b:
                    pts = [(ma, na), (ma, n1), (mt, n1), (mt, n2), (mb, n2), (mb, nb)]
                    dedup = [pts[0]] + [q for i, q in enumerate(pts[1:], 1) if q != pts[i - 1]]
                    key = tuple(dedup)
                    if key in seen or len(dedup) < 2:
                        continue
                    seen.add(key)
                    yield [Point(q, a.grid) for q in dedup]

    def _escape_paths(self, a, b):
        """Candidate paths a -> up on metal1 -> across on metal2 (r34 row nt) -> down on metal1 -> b, as
        lists of (grid name, laygo2 object). Vias: li-metal1 at the pins (r23), metal1-metal2 at the corners
        (r34). When the descent column differs from b's column, a short li stub on b's row finishes it."""
        r23, r34 = self.grid("r23"), self.grid("r34")
        a34, b34 = r34.mn(r23.xy(a)), r34.mn(r23.xy(b))
        ma, mb, na34, nb34 = int(a34[0]), int(b34[0]), int(a34[1]), int(b34[1])
        n_lo, n_hi = int(r34.mn(np.array(self._extent_xy()[0]))[1]), int(r34.mn(np.array(self._extent_xy()[1]))[1])
        rows = [n for n in range(min(na34, nb34) + 1, max(na34, nb34))]
        rows += [n for n in self._spread(sorted({na34, nb34}), SEARCH_RADIUS) if n_lo <= n <= n_hi and n not in rows]
        m_lo, m_hi = int(r34.mn(np.array(self._extent_xy()[0]))[0]), int(r34.mn(np.array(self._extent_xy()[1]))[0])
        cols_a = [ma] + [m for m in self._spread([ma], 2) if m_lo <= m <= m_hi]
        cols_b = [mb] + [m for m in self._spread([mb], 2) if m_lo <= m <= m_hi]
        for nt in rows:
            if nt in (na34, nb34):
                continue
            for m1, m2 in ((m1, m2) for m1 in cols_a for m2 in cols_b):
                pairs = []
                if m1 == ma:
                    pairs.append(("r23", r23.via(mn=a)))
                else:   # step sideways on li first, then a via up to metal1
                    p1 = Point([m1, int(a[1])], "r23")
                    pairs += [("r23", o) for o in _flat(r23.route(mn=[a, p1], via_tag=[False, False]))]
                    pairs.append(("r23", r23.via(mn=p1)))
                path = [[m1, na34], [m1, nt], [m2, nt], [m2, nb34]]
                objs = list(_flat(r34.route(mn=path, via_tag=[False, True, True, False])))
                pairs += [("r34", o) for o in objs]
                if m2 == mb:
                    pairs.append(("r23", r23.via(mn=b)))
                else:
                    p2 = Point([m2, int(b[1])], "r23")
                    pairs.append(("r23", r23.via(mn=p2)))
                    pairs += [("r23", o) for o in _flat(r23.route(mn=[p2, b], via_tag=[False, False]))]
                yield pairs

    def _extent_xy(self):
        xs = [i.bbox for i in self.instances.values()]
        return np.min([b[0] for b in xs], axis=0), np.max([b[1] for b in xs], axis=0)

    def _path_objs(self, grid, path, occ_a, occ_b):
        """laygo2 objects for a multi-point path: consecutive points share a row or a column. Vias go
        at every corner and at an end whose pin layer differs from the wire layer there."""
        def seg_layer(p, q):
            vertical = int(p[0]) == int(q[0])
            return str(grid.vlayer[int(p[0])][0]) if vertical else str(grid.hlayer[int(p[1])][0])
        n = len(path)
        via_tag = [False] * n
        pin_layer = occ_a[0].layer if occ_a else "locali"
        via_tag[0] = seg_layer(path[0], path[1]) != pin_layer
        via_tag[-1] = seg_layer(path[-2], path[-1]) != pin_layer
        for i in range(1, n - 1):
            via_tag[i] = seg_layer(path[i - 1], path[i]) != seg_layer(path[i], path[i + 1])
        return list(_flat(grid.route(mn=list(path), via_tag=via_tag)))

    def _pin_layer(self, pin_occs, p):
        return pin_occs[0].layer if pin_occs else "locali"

    def _extent(self, grid):
        xs = [i.bbox for i in self.instances.values()]
        lo = np.min([b[0] for b in xs], axis=0); hi = np.max([b[1] for b in xs], axis=0)
        mlo, mhi = grid.mn(np.array(lo)), grid.mn(np.array(hi))
        return int(mlo[0]), int(mhi[0]), int(mlo[1]), int(mhi[1])

    @staticmethod
    def _spread(values, radius):
        """Track indices around the given ones, nearest first: v-1, v+1, v-2, v+2, ..."""
        seen, out = set(values), []
        for d in range(1, radius + 1):
            for v in values:
                for cand in (v - d, v + d):
                    if cand not in seen:
                        seen.add(cand); out.append(cand)
        return out

    def _track_arg(self, track, pts):
        if not (isinstance(track, (tuple, list)) and len(track) == 2 and track[0] in ("v", "h")):
            raise SafeError("track must be ('v', column) or ('h', row)")
        kind, idx = track
        for p in pts:
            if (kind == "v" and p[0] == idx) or (kind == "h" and p[1] == idx):
                raise SafeError(f"track ({kind!r}, {idx}) runs through the pin at {p.tolist()}; pick a column/row with no pin")
        return [int(idx), None] if kind == "v" else [None, int(idx)]

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


def _parse_netlist(text):
    """Ports and devices of the first .subckt in a flat SPICE netlist (comments ignored)."""
    ports, devices = [], []
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith("*"):
            continue
        if s.lower().startswith(".subckt"):
            ports = s.split()[2:]
        elif s[0] in "XxMm":
            f = s.split()
            m = 1
            for tok in f[6:]:
                mm = re.match(r"m=(\d+)", tok, re.I)
                if mm:
                    m = int(mm.group(1))
            # devices are renamed XM1, XM2, ... in file order, exactly as llm/generate.py shows them to the LLM
            devices.append({"name": f"XM{len(devices) + 1}", "orig": f[0], "D": f[1], "G": f[2], "S": f[3], "B": f[4],
                            "model": f[5], "m": m})
    return ports, devices
