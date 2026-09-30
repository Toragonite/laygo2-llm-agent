"""flow/layout3d.py — interactive 3D viewer (HTML) of one or more Magic layout cells.

Each cell is flattened and exported as CIF (same path as flow/plot_layout.py), then every box is
drawn as a 3D slab at its layer's height in the SKY130 stack. The page has a cell selector, layer
toggles, an "explode" slider that pulls the layers apart, hover information and port labels.
Three.js is loaded from cdnjs; everything else is inline, so the file works as a claude.ai artifact.

Usage:
  uv run python flow/layout3d.py --out viewer.html \
      --cell "NAND2 golden=runs/lead/nand_2x/logic_ver2:logic_ver2_nand_2x" \
      --cell "NAND2 GPT-4o=runs/bench/20260930/nand_2x/a3/check_7/logic_ver2:logic_ver2_nand_2x"
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_layout import parse_cif, write_cif  # noqa: E402

# SKY130 stack (approximate heights in µm, enough to show the order and relative thickness):
# layer: (z bottom, z top, colour, opacity, label)
STACK = {
    "NWELL": (-0.40, -0.02, "#9bbf9b", 0.25, "nwell"),
    "DIFF": (0.00, 0.12, "#2e9e4f", 0.9, "diff"),
    "TAP": (0.00, 0.12, "#1b6e36", 0.9, "tap"),
    "POLY": (0.12, 0.30, "#d7263d", 0.95, "poly"),
    "CONT": (0.12, 0.94, "#333333", 1.0, "licon"),
    "LI": (0.94, 1.04, "#3fa7d6", 0.9, "li1"),
    "MCON": (1.04, 1.38, "#5a3d1e", 1.0, "mcon"),
    "MET1": (1.38, 1.74, "#1f4fbf", 0.85, "met1"),
    "VIA": (1.74, 2.00, "#444444", 1.0, "via"),
    "MET2": (2.00, 2.36, "#c02fbf", 0.85, "met2"),
}


def load_cell(mag_dir, cell):
    with tempfile.TemporaryDirectory() as tmp:
        cif = Path(tmp) / "flat.cif"
        write_cif(Path(mag_dir).resolve(), cell, cif)
        boxes, labels = parse_cif(cif.read_text())
    layers = {k: [[round(v, 4) for v in b] for b in boxes[k]] for k in STACK if k in boxes}
    return {"layers": layers, "labels": [[n, round(x, 3), round(y, 3)] for n, x, y in labels]}


PAGE = r"""<title>__TITLE__</title>
<style>
:root { --bg:#f2f4f3; --fg:#1a2220; --muted:#56645f; --line:#d3dbd8; --panel:#ffffff; --accent:#3556b8; --font:"IBM Plex Sans KR","Apple SD Gothic Neo",system-ui,sans-serif; --mono:"IBM Plex Mono",ui-monospace,monospace; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#111615; --fg:#e2e9e6; --muted:#9aaba5; --line:#2c3835; --panel:#182020; --accent:#8ea8f2; color-scheme: dark; } }
:root[data-theme="dark"] { --bg:#111615; --fg:#e2e9e6; --muted:#9aaba5; --line:#2c3835; --panel:#182020; --accent:#8ea8f2; color-scheme: dark; }
* { box-sizing: border-box; }
html, body { height: 100%; }
body { margin: 0; background: var(--bg); color: var(--fg); font-family: var(--font); font-size: 14px; }
.app { display: grid; grid-template-columns: 17rem minmax(0, 1fr); height: 100%; }
.side { padding: 1rem 16px; border-right: 1px solid var(--line); overflow-y: auto; display: flex; flex-direction: column; gap: 0.9rem; background: var(--panel); }
h1 { font-size: 1.1rem; margin: 0; }
.muted { color: var(--muted); font-size: 0.85rem; line-height: 1.4; }
label.row { display: flex; align-items: center; gap: 0.5rem; font-size: 0.9rem; padding: 0.15rem 0; }
.sw { width: 0.9rem; height: 0.9rem; border-radius: 2px; display: inline-block; border: 1px solid rgba(0,0,0,0.15); }
select, input[type=range] { width: 100%; }
select { font: inherit; padding: 0.3rem; background: var(--bg); color: var(--fg); border: 1px solid var(--line); border-radius: 4px; }
.stage { position: relative; min-width: 0; }
canvas { display: block; width: 100%; height: 100%; }
#info { position: absolute; left: 12px; bottom: 12px; background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 0.4rem 0.7rem; font-family: var(--mono); font-size: 0.8rem; color: var(--fg); pointer-events: none; max-width: 90%; }
#hint { position: absolute; right: 12px; top: 12px; color: var(--muted); font-size: 0.8rem; background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 0.3rem 0.6rem; }
.stack { font-family: var(--mono); font-size: 0.72rem; color: var(--muted); display: flex; flex-direction: column-reverse; gap: 2px; }
.stack div { display: flex; justify-content: space-between; }
button { font: inherit; padding: 0.35rem 0.6rem; border: 1px solid var(--line); background: var(--bg); color: var(--fg); border-radius: 4px; cursor: pointer; }
button:focus-visible, select:focus-visible { outline: 2px solid var(--accent); }
@media (max-width: 640px) { .app { grid-template-columns: 1fr; grid-template-rows: auto minmax(0, 1fr); } .side { border-right: none; border-bottom: 1px solid var(--line); max-height: 45%; } }
</style>
<div class="app">
  <aside class="side">
    <h1>__TITLE__</h1>
    <div class="muted">Magic 레이아웃을 평탄화해 층마다 실제 순서와 두께(근사)로 쌓아 그린 3D 뷰. 드래그 = 회전, 휠 = 확대, Shift+드래그 = 이동, 도형 위에 마우스 = 정보.</div>
    <div><div class="muted" style="margin-bottom:0.25rem">셀</div><select id="cell"></select></div>
    <div><div class="muted">층 벌리기 <span id="exv">1.0</span>×</div><input id="explode" type="range" min="1" max="6" step="0.1" value="1"></div>
    <div><div class="muted" style="margin-bottom:0.25rem">층 (아래 → 위)</div><div id="layers"></div></div>
    <label class="row"><input id="labels" type="checkbox" checked> 포트 이름 표시</label>
    <div style="display:flex; gap:0.4rem"><button id="top">위에서 보기</button><button id="iso">비스듬히 보기</button></div>
    <div><div class="muted" style="margin-bottom:0.25rem">스택 높이 (µm, 근사)</div><div class="stack" id="stack"></div></div>
  </aside>
  <div class="stage"><canvas id="c"></canvas><div id="hint">셀 크기 단위: µm</div><div id="info">도형 위에 마우스를 올리면 층과 좌표가 보입니다</div></div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script>
const DATA = __DATA__;
const STACK = __STACK__;
const ORDER = Object.keys(STACK);
const canvas = document.getElementById('c');
const renderer = new THREE.WebGLRenderer({canvas, antialias: true});
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(40, 1, 0.01, 1000);
scene.add(new THREE.AmbientLight(0xffffff, 0.75));
const dl = new THREE.DirectionalLight(0xffffff, 0.7); dl.position.set(3, -4, 8); scene.add(dl);
const dl2 = new THREE.DirectionalLight(0xffffff, 0.3); dl2.position.set(-4, 3, 5); scene.add(dl2);
let group = new THREE.Group(); scene.add(group);
let meshes = [], labelSprites = [], visible = {}, explode = 1, center = new THREE.Vector3(), radius = 3;
ORDER.forEach(k => visible[k] = true);

// --- controls (orbit around `center`) ---
let theta = -0.6, phi = 0.9, dist = 8, pan = new THREE.Vector3();
function place() {
  const x = center.x + pan.x + dist * Math.sin(phi) * Math.sin(theta);
  const y = center.y + pan.y - dist * Math.sin(phi) * Math.cos(theta);
  const z = center.z + pan.z + dist * Math.cos(phi);
  camera.position.set(x, y, z); camera.up.set(0, 0, 1); camera.lookAt(center.clone().add(pan));
}
let drag = null;
canvas.addEventListener('pointerdown', e => { drag = {x: e.clientX, y: e.clientY, shift: e.shiftKey}; canvas.setPointerCapture(e.pointerId); });
canvas.addEventListener('pointerup', () => drag = null);
canvas.addEventListener('pointermove', e => {
  hover(e);
  if (!drag) return;
  const dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag.x = e.clientX; drag.y = e.clientY;
  if (drag.shift) { pan.x -= dx * dist * 0.0015 * Math.cos(theta); pan.y -= dx * dist * 0.0015 * Math.sin(theta); pan.z += dy * dist * 0.0015; }
  else { theta -= dx * 0.008; phi = Math.min(Math.max(phi - dy * 0.008, 0.05), Math.PI / 2 - 0.02); }
  place();
});
canvas.addEventListener('wheel', e => { e.preventDefault(); dist *= Math.exp(e.deltaY * 0.001); dist = Math.min(Math.max(dist, radius * 0.3), radius * 12); place(); }, {passive: false});
document.getElementById('top').onclick = () => { theta = 0; phi = 0.05; place(); };
document.getElementById('iso').onclick = () => { theta = -0.6; phi = 0.9; place(); };

// --- build ---
function zOf(k, ex) { const [z0, z1] = STACK[k]; const gap = (ex - 1) * 0.9 * ORDER.indexOf(k); return [z0 + gap, z1 + gap]; }
function build(name) {
  scene.remove(group); group = new THREE.Group(); scene.add(group); meshes = []; labelSprites = [];
  const d = DATA[name]; let minx = 1e9, miny = 1e9, maxx = -1e9, maxy = -1e9;
  for (const k of ORDER) {
    const boxes = d.layers[k]; if (!boxes) continue;
    const [, , color, opacity] = STACK[k];
    const mat = new THREE.MeshLambertMaterial({color, transparent: opacity < 1, opacity});
    for (const [x, y, w, h] of boxes) {
      const [z0, z1] = zOf(k, explode);
      const geo = new THREE.BoxGeometry(w, h, z1 - z0);
      const m = new THREE.Mesh(geo, mat); m.position.set(x + w / 2, y + h / 2, (z0 + z1) / 2);
      m.userData = {layer: k, x, y, w, h}; m.visible = visible[k]; group.add(m); meshes.push(m);
      const edge = new THREE.LineSegments(new THREE.EdgesGeometry(geo), new THREE.LineBasicMaterial({color: 0x000000, transparent: true, opacity: 0.18}));
      edge.position.copy(m.position); edge.userData = {edgeOf: m}; edge.visible = visible[k]; group.add(edge);
      minx = Math.min(minx, x); miny = Math.min(miny, y); maxx = Math.max(maxx, x + w); maxy = Math.max(maxy, y + h);
    }
  }
  for (const [text, x, y] of d.labels) {
    const s = makeLabel(text); const [, z1] = zOf('MET1', explode); s.position.set(x, y, z1 + 0.25); s.visible = document.getElementById('labels').checked;
    group.add(s); labelSprites.push(s);
  }
  center.set((minx + maxx) / 2, (miny + maxy) / 2, 0.8); radius = Math.max(maxx - minx, maxy - miny); dist = radius * 1.6; pan.set(0, 0, 0); place();
}
function makeLabel(text) {
  const c = document.createElement('canvas'); c.width = 256; c.height = 96; const g = c.getContext('2d');
  g.fillStyle = 'rgba(255,255,255,0.92)'; g.strokeStyle = '#333'; g.lineWidth = 4; roundRect(g, 8, 8, 240, 80, 14); g.fill(); g.stroke();
  g.fillStyle = '#111'; g.font = 'bold 44px sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(text, 128, 50);
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({map: new THREE.CanvasTexture(c), depthTest: false})); sp.scale.set(0.9, 0.34, 1); return sp;
}
function roundRect(g, x, y, w, h, r) { g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r); g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath(); }
function relayer() {
  for (const m of meshes) { const [z0, z1] = zOf(m.userData.layer, explode); m.position.z = (z0 + z1) / 2; }
  for (const o of group.children) if (o.userData.edgeOf) o.position.z = o.userData.edgeOf.position.z;
  const [, z1] = zOf('MET1', explode); for (const s of labelSprites) s.position.z = z1 + 0.25;
}
function applyVisible() { for (const o of group.children) { const m = o.userData.edgeOf || o; if (m.userData.layer) o.visible = visible[m.userData.layer]; } }

// --- hover ---
const ray = new THREE.Raycaster(), mouse = new THREE.Vector2(); const info = document.getElementById('info');
function hover(e) {
  const r = canvas.getBoundingClientRect(); mouse.x = ((e.clientX - r.left) / r.width) * 2 - 1; mouse.y = -((e.clientY - r.top) / r.height) * 2 + 1;
  ray.setFromCamera(mouse, camera); const hit = ray.intersectObjects(meshes.filter(m => m.visible))[0];
  if (!hit) return; const u = hit.object.userData; const [z0, z1] = STACK[u.layer];
  info.textContent = `${STACK[u.layer][4]}  x ${u.x.toFixed(3)}–${(u.x + u.w).toFixed(3)}  y ${u.y.toFixed(3)}–${(u.y + u.h).toFixed(3)}  (w ${u.w.toFixed(3)}, h ${u.h.toFixed(3)} µm)  z ${z0}–${z1}`;
}

// --- UI ---
const sel = document.getElementById('cell'); for (const n of Object.keys(DATA)) { const o = document.createElement('option'); o.value = n; o.textContent = n; sel.appendChild(o); }
sel.onchange = () => build(sel.value);
const lay = document.getElementById('layers');
for (const k of [...ORDER].reverse()) {
  const l = document.createElement('label'); l.className = 'row';
  const cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = true; cb.id = 'layer-' + k; cb.onchange = () => { visible[k] = cb.checked; applyVisible(); };
  const sw = document.createElement('span'); sw.className = 'sw'; sw.style.background = STACK[k][2];
  l.append(cb, sw, document.createTextNode(STACK[k][4])); lay.appendChild(l);
}
document.getElementById('labels').onchange = e => { for (const s of labelSprites) s.visible = e.target.checked; };
const ex = document.getElementById('explode'); ex.oninput = () => { explode = parseFloat(ex.value); document.getElementById('exv').textContent = explode.toFixed(1); relayer(); };
const st = document.getElementById('stack'); for (const k of ORDER) { const d = document.createElement('div'); d.innerHTML = `<span>${STACK[k][4]}</span><span>${STACK[k][0]} … ${STACK[k][1]}</span>`; st.appendChild(d); }
function resize() { const r = canvas.parentElement.getBoundingClientRect(); renderer.setSize(r.width, r.height, false); camera.aspect = r.width / r.height; camera.updateProjectionMatrix(); }
window.addEventListener('resize', resize);
scene.background = null; renderer.setClearColor(0x000000, 0);
resize(); build(sel.value || Object.keys(DATA)[0]);
(function loop() { renderer.render(scene, camera); requestAnimationFrame(loop); })();
</script>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cell", action="append", required=True, help='"<name>=<mag dir>:<magic cell>" (repeatable)')
    ap.add_argument("--out", required=True, help="output HTML")
    ap.add_argument("--title", default="Layout 3D")
    a = ap.parse_args()
    data = {}
    for spec in a.cell:
        name, rest = spec.split("=", 1)
        mag_dir, cell = rest.rsplit(":", 1)
        data[name] = load_cell(mag_dir, cell)
        print(f"{name}: {sum(len(v) for v in data[name]['layers'].values())} boxes")
    html = PAGE.replace("__TITLE__", a.title).replace("__DATA__", json.dumps(data)).replace("__STACK__", json.dumps(STACK))
    Path(a.out).write_text(html)
    print(a.out)


if __name__ == "__main__":
    main()
