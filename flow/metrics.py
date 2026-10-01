"""flow/metrics.py — layout quality metrics beyond pass/fail, from the flattened CIF.

Per cell: cell bbox area, drawn area per routing layer (li1, met1, met2; union of boxes, so overlaps are
not double counted), contact/via counts (licon, mcon, via), and a wire-length proxy (layer area divided
by the minimum wire width of that layer). Template internals are included, but they are identical for
every layout of the same cell, so differences between layouts come from placement and routing.

Usage:
  uv run python flow/metrics.py --mag-dir runs/lead/nand_2x/logic_ver2 --cell logic_ver2_nand_2x
  uv run python flow/metrics.py --batch results/quality_runs.csv --out results/quality.csv
    (batch CSV columns: label, group, cell, mag_dir, magic_cell)
"""
import argparse
import csv
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_layout import parse_cif, write_cif  # noqa: E402

GRID_UM = 0.005                               # raster resolution (= one laygo2 unit)
WIDTH_UM = {"LI": 0.17, "MET1": 0.14, "MET2": 0.14}   # minimum widths used for the length proxy
LAYERS = ["LI", "MET1", "MET2"]
VIAS = ["CONT", "MCON", "VIA"]


def union_area(boxes):
    """Area of the union of axis-aligned boxes (x, y, w, h in µm) by rasterizing at GRID_UM."""
    if not boxes:
        return 0.0
    x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes); y1 = max(b[1] + b[3] for b in boxes)
    nx = int(round((x1 - x0) / GRID_UM)) + 1; ny = int(round((y1 - y0) / GRID_UM)) + 1
    mask = np.zeros((ny, nx), dtype=bool)
    for x, y, w, h in boxes:
        i0 = int(round((x - x0) / GRID_UM)); i1 = int(round((x + w - x0) / GRID_UM))
        j0 = int(round((y - y0) / GRID_UM)); j1 = int(round((y + h - y0) / GRID_UM))
        mask[j0:j1, i0:i1] = True
    return float(mask.sum()) * GRID_UM * GRID_UM


def metrics(mag_dir, cell):
    with tempfile.TemporaryDirectory() as tmp:
        cif = Path(tmp) / "flat.cif"
        write_cif(Path(mag_dir).resolve(), cell, cif)
        boxes, labels = parse_cif(cif.read_text())
    allb = [b for bs in boxes.values() for b in bs]
    x0 = min(b[0] for b in allb); y0 = min(b[1] for b in allb)
    x1 = max(b[0] + b[2] for b in allb); y1 = max(b[1] + b[3] for b in allb)
    out = {"bbox_w_um": round(x1 - x0, 3), "bbox_h_um": round(y1 - y0, 3), "bbox_area_um2": round((x1 - x0) * (y1 - y0), 3)}
    for L in LAYERS:
        a = union_area(boxes.get(L, []))
        out[f"{L.lower()}_area_um2"] = round(a, 4)
        out[f"{L.lower()}_len_um"] = round(a / WIDTH_UM[L], 2)
    for V in VIAS:
        out[f"n_{V.lower()}"] = len(boxes.get(V, []))
    out["layers_used"] = ",".join(L.lower() for L in LAYERS if boxes.get(L))
    out["n_ports"] = len(labels)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mag-dir"); ap.add_argument("--cell")
    ap.add_argument("--batch", help="CSV with label, group, cell, mag_dir, magic_cell")
    ap.add_argument("--out", help="output CSV for --batch")
    a = ap.parse_args()
    if a.batch:
        rows = list(csv.DictReader(open(a.batch)))
        res = []
        for r in rows:
            try:
                m = metrics(r["mag_dir"], r["magic_cell"])
            except Exception as e:
                m = {"error": str(e)[:120]}
            res.append({**r, **m})
            print(r["label"], r["cell"], m.get("met1_len_um", m.get("error")), flush=True)
        keys = sorted({k for r in res for k in r}, key=lambda k: (k not in rows[0], k))
        with open(a.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(res)
        print(a.out)
    else:
        print(json.dumps(metrics(a.mag_dir, a.cell), indent=2))


if __name__ == "__main__":
    main()
