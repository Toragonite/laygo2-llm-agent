"""flow/plot_layout.py — draw a Magic layout cell as a PNG (no display needed).

Magic's own plot commands need a graphics window, so this runs one batch magic process that flattens
the cell and writes CIF text, then draws the CIF boxes with matplotlib.

Usage:
  uv run python flow/plot_layout.py --mag-dir runs/nand_2x/logic_ver2 --cell logic_ver2_nand_2x \
      --out nand.png [--title "NAND2 golden"]
"""
import argparse
import re
import subprocess
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
# CIF layer -> (face colour, alpha, hatch, z-order, legend name). Implant layers are left out.
STYLE = {
    "NWELL": ("#9bbf9b", 0.18, None, 0, "nwell"),
    "DIFF": ("#2e9e4f", 0.55, None, 1, "diff"),
    "TAP": ("#1b6e36", 0.55, None, 1, "tap"),
    "POLY": ("#d7263d", 0.65, None, 2, "poly"),
    "CONT": ("#222222", 0.9, None, 3, "licon"),
    "LI": ("#3fa7d6", 0.45, None, 4, "li1"),
    "MCON": ("#5a3d1e", 0.9, None, 5, "mcon"),
    "MET1": ("#1f4fbf", 0.30, "//", 6, "met1"),
    "VIA": ("#444444", 0.9, None, 7, "via"),
    "MET2": ("#c02fbf", 0.30, "\\\\", 8, "met2"),
}


def write_cif(mag_dir: Path, cell: str, cif: Path):
    tcl = cif.with_suffix(".tcl")
    tcl.write_text(f"""addpath {mag_dir}
load {cell}
select top cell
flatten __plot_flat__
load __plot_flat__
cif write {cif.with_suffix('')}
quit -noprompt
""")
    subprocess.run(["magic", "-dnull", "-noconsole", "-rcfile", str(REPO / "flow" / "maginit.tcl"), str(tcl)],
                   cwd=cif.parent, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=180)
    if not cif.exists():
        raise RuntimeError(f"magic did not write {cif}")


def parse_cif(text: str):
    """Return ({layer: [(x0, y0, w, h), ...]}, [(label, x, y)]) in microns for a flattened CIF file."""
    scale = 1.0
    m = re.search(r"DS\s+\d+\s+(\d+)\s+(\d+);", text)
    if m:
        scale = int(m.group(1)) / int(m.group(2))
    um = scale / 100.0  # CIF units are centimicrons
    boxes, labels, layer = {}, [], None
    for raw in text.splitlines():
        ln = raw.strip().rstrip(";")
        if ln.startswith("L "):
            layer = ln.split()[1]
        elif ln.startswith("B ") and layer:
            w, h, cx, cy = (int(v) for v in ln.split()[1:5])
            boxes.setdefault(layer, []).append(((cx - w / 2) * um, (cy - h / 2) * um, w * um, h * um))
        elif ln.startswith("94 "):
            parts = ln.split()
            if len(parts) >= 5 and parts[4] == "MET1TXT":  # port labels only
                labels.append((parts[1], int(parts[2]) * um, int(parts[3]) * um))
    return boxes, labels


def draw(boxes, labels, out: Path, title: str):
    fig, ax = plt.subplots(figsize=(4.2, 5.2), dpi=150)
    used = []
    for layer, (color, alpha, hatch, z, name) in STYLE.items():
        for x, y, w, h in boxes.get(layer, []):
            ax.add_patch(Rectangle((x, y), w, h, facecolor=color, alpha=alpha, hatch=hatch,
                                   edgecolor=color if hatch else "none", linewidth=0.6, zorder=z))
        if boxes.get(layer):
            used.append((color, alpha, hatch, name))
    for name, x, y in labels:
        ax.text(x, y, name, fontsize=8, fontweight="bold", ha="center", va="center", zorder=10,
                bbox=dict(boxstyle="round,pad=0.15", facecolor="white", edgecolor="#333333", linewidth=0.5))
    allb = [b for bs in boxes.values() for b in bs]
    x0 = min(b[0] for b in allb); y0 = min(b[1] for b in allb)
    x1 = max(b[0] + b[2] for b in allb); y1 = max(b[1] + b[3] for b in allb)
    ax.set_xlim(x0 - 0.2, x1 + 0.2); ax.set_ylim(y0 - 0.2, y1 + 0.2)
    ax.set_aspect("equal"); ax.set_xlabel("µm", fontsize=8); ax.tick_params(labelsize=7)
    if title:
        ax.set_title(title, fontsize=10)
    handles = [Rectangle((0, 0), 1, 1, facecolor=c, alpha=a, hatch=h, edgecolor=c if h else "none") for c, a, h, _ in used]
    ax.legend(handles, [n for *_, n in used], fontsize=6, loc="upper center", bbox_to_anchor=(0.5, -0.1),
              ncol=5, frameon=False)
    fig.tight_layout()
    fig.savefig(out, facecolor="white")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mag-dir", required=True, help="directory holding <cell>.mag")
    ap.add_argument("--cell", required=True, help="magic cell name, e.g. logic_ver2_nand_2x")
    ap.add_argument("--out", required=True, help="output PNG")
    ap.add_argument("--title", default="")
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        cif = Path(tmp) / "flat.cif"
        write_cif(Path(a.mag_dir).resolve(), a.cell, cif)
        boxes, labels = parse_cif(cif.read_text())
    draw(boxes, labels, Path(a.out), a.title)
    print(a.out)


if __name__ == "__main__":
    main()
