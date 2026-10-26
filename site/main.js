// Swiss Law Map, 3D. Two views of the same acts:
//   Stufenbau (default): federal law in force as the tree its own texts state — the
//     Constitution at the apex, every act under the provision its Ingress names as its
//     basis, on the floor of the authority that enacted it (data/tree.json, step 7);
//   Systematik: the official SR classification as a ground plan (circle packing), acts
//     standing on it as orbs sized by the decisions that cite them.
// In both, two layers of interdependency are routed along the hierarchy (hierarchical
// edge bundling):
//   the courts' current — two acts cited in the same decisions — arcs above the plane;
//   the legislature's wiring — the text of one act refers to another — arcs below it, seen
//   through the glass floor. Arcs rise (or sink) further the further apart the two acts sit
//   in the SR. Pairs linked by both turn white.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { makeShells, makeOrbs, makeDots, makeStems, makeRibbons, setRibbons, makeStars, setTheme, setFog } from "./gl.js";
import { T, CANTON, LANGS } from "./i18n.js";

// ---------- constants ----------
const OPEN_PX = 70;            // a container whose projected radius exceeds this shows its children's links
const ART_PX = 170;            // an act whose projected radius exceeds this shows its articles
const BETA = 0.75;             // bundling strength (Holten 2006): 0 = straight, 1 = fully along the tree
const SAMPLES = 36;            // points per curve
const HUE = {
  1: [0.42, 0.56, 1.0], 2: [0.2, 0.86, 0.74], 3: [1.0, 0.45, 0.33], 4: [0.72, 0.53, 1.0], 5: [0.68, 0.76, 0.32],
  6: [1.0, 0.72, 0.22], 7: [0.32, 0.72, 0.98], 8: [1.0, 0.45, 0.66], 9: [0.4, 0.82, 0.5], k: [0.82, 0.62, 0.42], n: [0.6, 0.66, 0.72],
  bv: [1.0, 0.86, 0.58],
  court: [0.98, 0.42, 0.36],         // decisions: the courts under an act
};
const PLATE = [0.5, 0.58, 0.72];     // the floors of the Stufenbau
const GRAPHITE = [0.56, 0.6, 0.66];  // tree branches on paper: one calm ink; the nodes carry the SR colours
const BASIS2 = [1.0, 0.8, 0.5];     // a further stated basis (not the place in the tree)
const SPAN_PX = 12;                 // tree: a node whose span on screen is narrower merges into its parent's links
const WIRE = [1.0, 0.62, 0.25];   // legislation: amber, below the plane
const CURRENT = [0.3, 0.82, 1.0]; // case law: cyan, above the plane
const BOTH_DARK = [1.0, 0.97, 0.9];   // both layers: white on the night sky …
const BOTH_LIGHT = [0.42, 0.3, 0.56];  // … a deep violet ink on paper
let BOTH = BOTH_LIGHT;
// The two looks (index.html carries the CSS tokens; gl.js the shader side).
const PAPER = [0xf3 / 255, 0xf1 / 255, 0xec / 255], NIGHT_BG = [3 / 255, 6 / 255, 11 / 255];
let theme = pickTheme();
// CSS colour of a hue as the map draws it: ink on paper, light on the night sky.
const ink = (c) => (theme === "light" ? Math.pow(c, 1.6) * 0.8 : c);
const cssHue = (h, pastel) => `rgb(${(HUE[h] || h || HUE.n).map((c) => Math.round(theme === "light" ? 255 * ink(c) : pastel ? 150 + 105 * c : 255 * c)).join(",")})`;

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const getJSON = (u) => fetch(u).then((r) => { if (!r.ok) throw new Error(u + " " + r.status); return r.json(); });
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

// ---------- state ----------
let lang = pickLang(), t = T[lang], fmt = new Intl.NumberFormat(lang + "-CH");
let core, titles = [], N = 0, NCORE = 0, XN = [], tree = null, ingress = null, ingressWait = null;
let X, Z, R, P, NC, K, HK, PK, kids, ids, idIndex;
let CY, SPAN, ROOT = 0, mode = pickMode();   // centre height of each sphere; span width (tree); root of the view
const LAY = {};                              // per view: positions, hierarchy, meshes
let TN = [], TK = [];                        // tree node record / index of a global node
let basisOf = [], dependents = [];           // tree: an act's stated bases; who states a node as basis
let jAdj = [], wOut = [], wIn = [];        // judicial adjacency; legislative out/in
let pairKind = new Map();                  // "a|b" -> 1 law, 2 practice, 3 both
let sel = { i: -1, art: null }, hover = { i: -1, art: null };
let period = null, showWire = true, showCurrent = true, edgeYears = null;
let treeAll = false;      // tree: links of every act, not only the selection's (off: the tree alone reads best)
const packs = new Map(), packWait = new Map();
const origin = new THREE.Vector3();
let W = innerWidth, H = innerHeight, dpr = Math.min(devicePixelRatio || 1, 2);
const num = (n) => fmt.format(n || 0);

function pickTheme() {
  try { const s = localStorage.getItem("slm-theme"); if (s === "light" || s === "dark") return s; } catch (e) { /* storage unavailable */ }
  return "light";
}
function pickMode() {
  try { const s = localStorage.getItem("slm-mode"); if (s === "sr" || s === "tree") return s; } catch (e) { /* storage unavailable */ }
  return "tree";
}
function pickLang() {
  try { const s = localStorage.getItem("slm-lang"); if (LANGS.includes(s)) return s; } catch (e) { /* storage unavailable */ }
  const n = (navigator.language || "de").slice(0, 2);
  return LANGS.includes(n) ? n : "de";
}

// ---------- three.js ----------
const canvas = $("map");
function webgl() { try { const c = document.createElement("canvas"); return !!(c.getContext("webgl2") || c.getContext("webgl")); } catch (e) { return false; } }
if (!webgl()) { $("loading").textContent = "WebGL is not available in this browser."; throw new Error("no WebGL"); }
const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: "high-performance" });
renderer.setPixelRatio(dpr);
renderer.setSize(W, H);
// The shaders write display colours directly; no linear-to-sRGB step at the end.
renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(38, W / H, 0.1, 10000);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.09;
controls.zoomToCursor = true;
controls.screenSpacePanning = false;
controls.maxPolarAngle = Math.PI * 0.47;
controls.minDistance = 1e-4;
controls.maxDistance = 1e5;
controls.mouseButtons = { LEFT: THREE.MOUSE.PAN, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.ROTATE };
controls.touches = { ONE: THREE.TOUCH.PAN, TWO: THREE.TOUCH.DOLLY_ROTATE };
controls.rotateSpeed = 0.6;
controls.addEventListener("end", () => { if (core) $("tilt").textContent = tiltLabel(); });

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const bloom = new UnrealBloomPass(new THREE.Vector2(W / 2, H / 2), 0.65, 0.4, 0.74);
composer.addPass(bloom);
composer.addPass(new OutputPass());

const stars = makeStars();
scene.add(stars);
function applyTheme() {
  const light = theme === "light";
  document.documentElement.dataset.look = theme;      // not data-theme: the host sets that one
  setTheme(light, PAPER);
  renderer.setClearColor(new THREE.Color().setRGB(...(light ? PAPER : NIGHT_BG), THREE.LinearSRGBColorSpace), 1);
  bloom.enabled = !light;           // a glow belongs to the night sky; on paper it only blurs
  stars.visible = !light;
  BOTH = light ? BOTH_LIGHT : BOTH_DARK;
  $("theme").textContent = light ? "☾" : "☀";
  $("theme").setAttribute("aria-label", light ? t.themeDark : t.themeLight);
  $("theme").title = light ? t.themeDark : t.themeLight;
  edgesDirty = true; treeDirty = true;
}
let rings, orbs, wires, current, focusRibbons, treeLines, dots = null, stems = null, dotsAct = -1, artH = null, artFade = 0;

// ---------- data ----------
async function boot() {
  const [c, tt, tr] = await Promise.all([getJSON("data/core.json"), getJSON(`data/titles.${lang}.json`),
    getJSON("data/tree.json").catch(() => null)]);
  core = c; titles = tt; tree = tr;
  const nodes = core.nodes;
  NCORE = nodes.length;
  XN = [];
  // tree nodes that are acts are the map's own nodes; the Constitution's structure is added
  const tmap = tree ? tree.nodes.map((o) => (o.c >= 0 ? o.c : NCORE + XN.push(o) - 1)) : [];
  TMAP = tmap;
  N = NCORE + XN.length;
  NC = new Float64Array(N); PK = new Int32Array(N).fill(-1);
  K = new Array(N); HK = new Array(N); ids = new Array(N);
  idIndex = new Map();
  const sr = layoutArrays();
  for (let i = 0; i < NCORE; i++) {
    const o = nodes[i];
    sr.X[i] = o.x; sr.Z[i] = o.y; sr.R[i] = o.r; sr.P[i] = o.p; K[i] = o.k; NC[i] = o.n || 0; ids[i] = o.i;
    sr.CY[i] = o.k === "act" || o.k === "bucket" ? o.r : 0;      // orbs stand on the plane
    if (o.pk !== undefined) PK[i] = o.pk;
    idIndex.set(o.i, i);
    if (o.p >= 0) sr.kids[o.p].push(i);
  }
  XN.forEach((o, k) => { const i = NCORE + k; K[i] = o.k; ids[i] = o.i; NC[i] = o.dec || 0; idIndex.set(o.i, i); });
  sr.root = 0;
  LAY.sr = sr;
  P = sr.P;
  for (let i = 0; i < NCORE; i++) HK[i] = hueKey(nodes[i], i);
  for (let i = NCORE; i < N; i++) HK[i] = node(i).ct ? "k" : "bv";     // the BV's own nodes gold; cantonal law brown
  if (tree) buildTreeLayout(tmap); else mode = "sr";
  jAdj = Array.from({ length: N }, () => []);
  for (const [a, b, n, l] of core.edges) {
    jAdj[a].push([b, n, l]); jAdj[b].push([a, n, l]);
    pairKind.set(a < b ? a + "|" + b : b + "|" + a, 2);
  }
  for (const a of jAdj) a.sort((p, q) => q[1] * Math.log(q[2]) - p[1] * Math.log(p[2]));
  wOut = Array.from({ length: N }, () => []); wIn = Array.from({ length: N }, () => []);
  for (const [a, b, n] of core.xedges || []) {
    wOut[a].push([b, n]); wIn[b].push([a, n]);
    const key = a < b ? a + "|" + b : b + "|" + a;
    pairKind.set(key, (pairKind.get(key) || 0) | 1);
  }
  for (const a of wOut) a.sort((p, q) => q[1] - p[1]);
  for (const a of wIn) a.sort((p, q) => q[1] - p[1]);

  const want = mode;
  buildScene();
  useLayout(want);
  writeInstances(); refreshStates();
  applyLang();
  buildLegend();
  resize();
  home(false);
  $("loading").hidden = true;
  const h = decodeHash();
  if (h) select(h.i, h.art, true);
  else if (mode === "tree" && tree && !seenOpening()) opening();
  else if (mode !== "tree" && !seenIntro()) $("intro").hidden = false;
  requestAnimationFrame(loop);
}

function layoutArrays() {
  return { X: new Float64Array(N), Z: new Float64Array(N), CY: new Float64Array(N), R: new Float64Array(N),
    SPAN: new Float64Array(N), P: new Int32Array(N).fill(-1), kids: Array.from({ length: N }, () => []), root: 0 };
}
// The Stufenbau: positions from step 7; bases and dependents by global index.
function buildTreeLayout(tmap) {
  const L = layoutArrays();
  TN = new Array(N); TK = new Int32Array(N).fill(-1);
  tree.nodes.forEach((o, k) => {
    const i = tmap[k];
    L.X[i] = o.x; L.Z[i] = o.z; L.CY[i] = o.y; L.R[i] = o.r; L.SPAN[i] = o.w;
    L.P[i] = o.p >= 0 ? tmap[o.p] : -1;
    TN[i] = o; TK[i] = k;
    if (!idIndex.has(o.i)) idIndex.set(o.i, i);      // "K:GE:E 5 10" also finds the cited act "GE LPA"
  });
  for (let i = 0; i < N; i++) if (L.P[i] >= 0) L.kids[L.P[i]].push(i);
  L.root = tmap[tree.root];
  // acts hanging under each node (for the weight of the tree lines)
  L.size = new Float64Array(N);
  const order = [];
  const st = [L.root];
  while (st.length) { const j = st.pop(); order.push(j); for (const c of L.kids[j]) st.push(c); }
  for (let k = order.length - 1; k >= 0; k--) { const j = order[k]; L.size[j] += K[j] === "act" ? 1 : 0; if (L.P[j] >= 0) L.size[L.P[j]] += L.size[j]; }
  LAY.tree = L;
  basisOf = Array.from({ length: N }, () => []); dependents = Array.from({ length: N }, () => []);
  for (const [k, list] of Object.entries(tree.bases)) {
    const i = tmap[+k];
    list.forEach(([tk, eids, clause, how, via, found, prim], k) => {
      const j = tk >= 0 ? tmap[tk] : -1;           // -1: named in the Ingress, not identified
      basisOf[i].push({ j, eids, clause, how, via, found, prim, k });
      if (j < 0) return;
      // a basis in the Constitution names articles: each of them carries the act
      const arts = K[j] === "bvart" || j === L.root ? eids.map((e) => idIndex.get("BV:" + e)).filter((x) => x !== undefined) : [];
      if (arts.length) arts.forEach((a, n) => dependents[a].push({ i, eids, prim: prim && n === 0 }));
      else dependents[j].push({ i, eids, prim });
    });
  }
}
const node = (i) => (i < NCORE ? core.nodes[i] : XN[i - NCORE]);
const inLayout = (i) => i >= 0 && (i === ROOT || P[i] >= 0);
const pickL = (m) => (m ? m[lang] || m.de || m.fr || m.it || "" : "");
function useLayout(m) {
  mode = m;
  const L = LAY[m];
  X = L.X; Z = L.Z; CY = L.CY; R = L.R; P = L.P; kids = L.kids; SPAN = L.SPAN; ROOT = L.root;
  orbIndex = L.orbIndex; ringIndex = L.ringIndex; orbOf = L.orbOf; ringOf = L.ringOf; rings = L.rings; orbs = L.orbs;
  for (const k of Object.keys(LAY)) { LAY[k].rings.visible = k === m; LAY[k].orbs.visible = k === m; }
  if (treeLines) treeLines.visible = m === "tree";
  document.body.dataset.mode = m;
  try { localStorage.setItem("slm-mode", m); } catch (e) { /* storage unavailable */ }
}
// Switch views, keeping the selection where it exists in both.
function setMode(m, refocus = true) {
  if (m === mode || !LAY[m]) return;
  closeArticles();
  useLayout(m);
  writeInstances(); refreshStates(); refreshHover();
  treeDirty = true; edgesDirty = true;
  buildLegend(); applyLang();
  if (!refocus) return;
  if (sel.i >= 0 && inLayout(sel.i)) { sel.art = null; refreshStates(); focusOn(sel.i); refreshPanel(); crumbs(); writeHash(); webFor(sel.i); }
  else { select(-1, null, false); home(); }
}

function hueKey(o, i) {
  if (o.k === "domain") return o.i === "KT" ? "k" : "n";
  if (o.k === "root") return "n";
  if (o.c) return "k";
  const sr = o.sr || "";
  if (sr) return sr.startsWith("0.") ? sr[2] : sr[0];
  return i > 0 && P[i] >= 0 ? HK[P[i]] : "n";
}

// ---------- scene ----------
let ringIndex = [], orbIndex = [], orbOf = null, ringOf = null;
function buildScene() {
  for (const m of Object.keys(LAY)) {
    const L = LAY[m];
    L.orbIndex = []; L.ringIndex = [];
    if (m === "sr") { for (let i = 1; i < NCORE; i++) (K[i] === "act" || K[i] === "bucket" ? L.orbIndex : L.ringIndex).push(i); }
    else for (let i = 0; i < N; i++) if (i === L.root || L.P[i] >= 0) L.orbIndex.push(i);
    L.orbOf = new Int32Array(N).fill(-1); L.ringOf = new Int32Array(N).fill(-1);
    L.orbIndex.forEach((i, j) => (L.orbOf[i] = j));
    L.ringIndex.forEach((i, j) => (L.ringOf[i] = j));
    L.rings = makeShells(m === "tree" ? tree.plates.length : L.ringIndex.length);   // tree: the floors
    L.orbs = makeOrbs(L.orbIndex.length);
    scene.add(L.rings, L.orbs);
  }
  wires = makeRibbons(); current = makeRibbons(); focusRibbons = makeRibbons(); treeLines = makeRibbons();
  scene.add(wires, current, focusRibbons, treeLines);
  for (const m of Object.keys(LAY)) { useLayout(m); writeInstances(); refreshStates(); }
}

// SR view: containers are flat discs on the plane, acts are orbs standing on it.
// Tree view: every node is an orb at its place in the cone; the floors are discs.
function writeInstances() {
  const rc = rings.geometry.attributes.iCenter.array, rr = rings.geometry.attributes.iRadius.array,
    rcol = rings.geometry.attributes.iColor.array;
  if (mode === "tree") tree.plates.forEach(([y, r], j) => {
    rc.set([-origin.x, y - origin.y, -origin.z], j * 3); rr[j] = r; rcol.set(PLATE, j * 3);
  });
  else ringIndex.forEach((i, j) => {
    rc.set([X[i] - origin.x, -origin.y, Z[i] - origin.z], j * 3);
    rr[j] = R[i];
    rcol.set(HUE[HK[i]] || HUE.n, j * 3);
  });
  const oc = orbs.geometry.attributes.iCenter.array, orr = orbs.geometry.attributes.iRadius.array,
    ocol = orbs.geometry.attributes.iColor.array;
  orbIndex.forEach((i, j) => {
    oc.set([X[i] - origin.x, CY[i] - origin.y, Z[i] - origin.z], j * 3);
    orr[j] = R[i];
    const h = HUE[HK[i]] || HUE.n;
    ocol.set(node(i).reg ? h.map((c) => 0.35 * c + 0.3) : h, j * 3);  // earlier act or edition: paler
  });
  treeDirty = true;
  if (courtFor >= 0) writeCourts();
  for (const m of [rings, orbs]) {
    m.geometry.attributes.iCenter.needsUpdate = true;
    m.geometry.attributes.iRadius.needsUpdate = true;
    m.geometry.attributes.iColor.needsUpdate = true;
  }
}

// Per-instance state: visibility, brightness, opened, highlight; dims what is outside the focus.
let related = null;
function refreshStates() {
  related = null;
  if (focusSet && sel.i < 0) related = new Set(focusSet);
  else if (sel.i >= 0) {
    related = new Set([sel.i]);
    let p = P[sel.i];
    while (p >= 0) { related.add(p); p = P[p]; }
    const sub = subtree(sel.i);
    for (const i of sub) related.add(i);
    for (const i of sub) {
      for (const [j] of jAdj[i]) addPath(j);
      for (const [j] of wOut[i]) addPath(j);
      for (const [j] of wIn[i]) addPath(j);
    }
    if (mode === "tree") {             // every stated basis, and every act stating this one
      for (const b of basisOf[sel.i] || []) addPath(b.j);
      for (const d of dependents[sel.i] || []) addPath(d.i);
    }
  }
  function addPath(j) { while (j >= 0 && !related.has(j)) { related.add(j); j = P[j]; } }
  const maxN = Math.log10(NC[0] + 1);
  const rs = rings.geometry.attributes.iState.array;
  if (mode === "tree") tree.plates.forEach((pl, j) => rs.set([related ? 0.3 : 0.55, 1, 0, 0], j * 4));
  else ringIndex.forEach((i, j) => {
    const on = !related || related.has(i);
    const depthA = K[i] === "domain" ? 0.9 : 1.0;
    rs.set([on ? depthA : 0.18, 1, 0, 0], j * 4);
  });
  const os = orbs.geometry.attributes.iState.array;
  orbIndex.forEach((i, j) => {
    const on = !related || related.has(i);
    const o = node(i);
    let b = i >= NCORE && K[i] !== "bvart" ? 0.3 : Math.log10(NC[i] + 1) / maxN;   // the BV's titles and chapters: junctions
    if (period && o.ys) b *= Math.sqrt(share(o));
    os.set([on ? 1 : 0.16, b, 0, i === sel.i && !sel.art ? 0.38 : (i === hover.i ? 0.3 : 0)], j * 4);
  });
  rings.geometry.attributes.iState.needsUpdate = true;
  orbs.geometry.attributes.iState.needsUpdate = true;
  edgesDirty = true; treeDirty = true;
}
function subtree(i) {
  const out = [i], st = [i];
  while (st.length) { const j = st.pop(); for (const c of kids[j]) { out.push(c); st.push(c); } }
  return out;
}
function share(o) {
  if (!period || !o.ys || !o.n) return 1;
  let s = 0;
  for (let y = Math.max(period[0], o.y0); y <= Math.min(period[1], o.y0 + o.ys.length - 1); y++) s += o.ys[y - o.y0];
  return Math.min(1, s / o.n);
}

// ---------- floating origin ----------
function rebase(nx, nz) {
  const dx = nx - origin.x, dz = nz - origin.z;
  if (Math.hypot(dx, dz) < 1e-9) return;
  origin.set(nx, 0, nz);
  camera.position.x -= dx; camera.position.z -= dz;
  controls.target.x -= dx; controls.target.z -= dz;
  if (anim) { anim.shift(dx, dz); }
  writeInstances();
  if (dots) for (const m of [dots, stems]) m.position.set(X[dotsAct] - origin.x, 0, Z[dotsAct] - origin.z);
  edgesDirty = true; treeDirty = true;
}
const worldTarget = () => ({ x: controls.target.x + origin.x, z: controls.target.z + origin.z });

// ---------- camera ----------
let anim = null, minFlight = 600;           // tours slow flights down so the eye can follow
const viewDist = () => camera.position.distanceTo(controls.target);
function pxPerUnitAt(dist) { return (H / 2) / Math.tan((camera.fov * Math.PI) / 360) / Math.max(dist, 1e-9); }
let storyTop = 0;                        // top edge of the tour card (px), measured when it is written
function freeRect() {
  const open = !$("panel").hidden;
  if (!open && story && (story.tr || story.descent)) {   // a tour: the card holds the bottom, the subject sits above it
    const y0 = W <= 760 ? 64 : 72, y1 = Math.max(y0 + 160, (storyTop || H - (W <= 760 ? 300 : 280)) - 12);
    return { cx: W / 2, cy: (y0 + y1) / 2, w: W, h: y1 - y0 };
  }
  if (!open) return { cx: W / 2, cy: H / 2, w: W, h: H };
  if (W <= 760) { const sh = Math.min(H * 0.52, 460) + 20; return { cx: W / 2, cy: (H - sh) / 2 + 30, w: W, h: H - sh - 60 }; }
  return { cx: (W - 424) / 2, cy: H / 2, w: W - 424, h: H };
}
function distanceToFit(r) {
  const fr = freeRect();
  const span = Math.min(fr.w, fr.h) * 0.8;
  return (r * 2.2) * ((H / 2) / Math.tan((camera.fov * Math.PI) / 360)) / span;
}
// ty: height of the point looked at (an article dot rises above the floor)
const wrapPi = (a) => a - 2 * Math.PI * Math.floor((a + Math.PI) / (2 * Math.PI));
// Returns the flight's duration (ms), so tours and descents can chain flights.
function flyTo(wx, wz, dist, polar, animate = true, ty = 0, theta = null, minDur = 600) {
  const sph = new THREE.Spherical().setFromVector3(camera.position.clone().sub(controls.target));
  const toPolar = polar ?? sph.phi;
  const toTheta = theta == null ? sph.theta : sph.theta + wrapPi(theta - sph.theta);
  const from = [controls.target.x + origin.x, controls.target.z + origin.z, viewDist()];
  const to = [wx, wz, dist];
  if (!animate || reduceMotion) { setView(to, toPolar, toTheta, ty); return 0; }
  const interp = interpolateZoom(from, to);
  const dur = Math.max(minDur, Math.min(2600, interp.duration * 1.1));
  const t0 = performance.now(), phi0 = sph.phi, th = sph.theta, y0 = controls.target.y;
  anim = {
    step(now) {
      const u = Math.min(1, (now - t0) / dur);
      const e = u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2;
      setView(interp(e), phi0 + (toPolar - phi0) * e, th + (toTheta - th) * e, y0 + (ty - y0) * e);
      if (u >= 1) anim = null;
    },
    shift() { /* positions are absolute, setView applies the origin */ },
  };
  return dur;
}
function recentre() {   // re-apply the panel offset after the panel opened or closed
  const sph = new THREE.Spherical().setFromVector3(camera.position.clone().sub(controls.target));
  const w = worldTarget();
  flyTo(w.x, w.z, viewDist(), sph.phi, true, controls.target.y);
}
function setView([wx, wz, dist], phi, theta, ty = 0) {
  if (Math.hypot(wx - origin.x, wz - origin.z) > Math.max(dist * 4, 1e-6) || dist < 2) rebase(wx, wz);
  controls.target.set(wx - origin.x, ty, wz - origin.z);
  const off = new THREE.Vector3().setFromSpherical(new THREE.Spherical(dist, phi, theta));
  camera.position.copy(controls.target).add(off);
  // keep the object centred in the part of the screen the panel leaves free
  const fr = freeRect();
  camera.setViewOffset(W, H, (W / 2 - fr.cx) , (H / 2 - fr.cy), W, H);
  controls.update();
}
function interpolateZoom(p0, p1) {   // van Wijk & Nuij smooth zoom (d3-interpolate)
  const rho = Math.SQRT2, rho2 = 2, rho4 = 4;
  const [ux0, uy0, w0] = p0, [ux1, uy1, w1] = p1;
  const dx = ux1 - ux0, dy = uy1 - uy0, d2 = dx * dx + dy * dy;
  let i, S;
  if (d2 < 1e-12) { S = Math.log(w1 / w0) / rho; i = (u) => [ux0 + u * dx, uy0 + u * dy, w0 * Math.exp(rho * u * S)]; }
  else {
    const d1 = Math.sqrt(d2);
    const b0 = (w1 * w1 - w0 * w0 + rho4 * d2) / (2 * w0 * rho2 * d1), b1 = (w1 * w1 - w0 * w0 - rho4 * d2) / (2 * w1 * rho2 * d1);
    const r0 = Math.log(Math.sqrt(b0 * b0 + 1) - b0), r1 = Math.log(Math.sqrt(b1 * b1 + 1) - b1);
    S = (r1 - r0) / rho;
    i = (u) => { const s = u * S, c0 = Math.cosh(r0), uu = w0 / (rho2 * d1) * (c0 * Math.tanh(rho * s + r0) - Math.sinh(r0)); return [ux0 + uu * dx, uy0 + uu * dy, w0 * c0 / Math.cosh(rho * s + r0)]; };
  }
  i.duration = Math.abs(S) * 1000;
  return i;
}
// Tree: the camera distance and target height at which every floor, apex to the lowest
// cantonal floor, fits between the search bar and the tools (found numerically).
function fitTree(phi, topPx = null) {
  const pts = [[0, CY[ROOT] + R[ROOT] * 2, 0]];
  for (const [y, r] of tree.plates) for (let a = 0; a < 32; a++) pts.push([r * Math.cos(a * Math.PI / 16), y, r * Math.sin(a * Math.PI / 16)]);
  const theta = new THREE.Spherical().setFromVector3(camera.position.clone().sub(controls.target)).theta;
  const cam = camera.clone(), q = new THREE.Vector3(), tgt = new THREE.Vector3();
  cam.clearViewOffset();
  // the box the tree must fit, in screen px; the view offset puts the camera axis at the free area's centre
  const phone = W <= 760, tour = story && (story.tr || story.descent), fr = freeRect();
  const yTop = topPx ?? (phone ? 120 : 92), yBot = tour ? (storyTop || H - 280) - 14 : H - (phone ? 150 : 70);
  const xL = phone ? W * 0.03 : tour ? 30 : 390, xR = W - (phone ? W * 0.03 : $("panel").hidden ? 250 : 444);   // legend left, floor names right
  const top = (fr.cy - yTop) / (H / 2), bot = (fr.cy - yBot) / (H / 2);
  const left = (xL - fr.cx) / (W / 2), right = (xR - fr.cx) / (W / 2);
  const bounds = (d, ty) => {
    tgt.set(0, ty, 0);
    cam.position.setFromSphericalCoords(d, phi, theta).add(tgt);
    cam.lookAt(tgt); cam.updateMatrixWorld(); cam.updateProjectionMatrix();
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const p of pts) { q.set(p[0], p[1], p[2]).project(cam); x0 = Math.min(x0, q.x); x1 = Math.max(x1, q.x); y0 = Math.min(y0, q.y); y1 = Math.max(y1, q.y); }
    return [x0, x1, y0, y1];
  };
  let ty = (CY[ROOT] + Math.min(...tree.plates.map((p) => p[0]))) / 2, d = 1;
  for (let it = 0; it < 6; it++) {
    let lo = 1e-3, hi = 1e7;
    for (let k = 0; k < 60; k++) {
      const m = Math.sqrt(lo * hi), [x0, x1, y0, y1] = bounds(m, ty);
      if (x1 - x0 <= right - left && y1 - y0 <= top - bot) hi = m; else lo = m;
    }
    d = hi;
    const [, , y0, y1] = bounds(d, ty);
    ty += ((y0 + y1) / 2 - (top + bot) / 2) * d * Math.tan((camera.fov * Math.PI) / 360) / Math.max(Math.sin(phi), 0.2);
  }
  return [d, ty];
}
function home(animate = true) {
  if (mode === "tree") {               // the whole tree, apex to the cantonal floors, seen at an angle
    const phi = W <= 760 ? 0.42 : 0.62;     // near the axis the cone reads as a radial tree; tilt shows the floors
    const [d, ty] = fitTree(phi);
    flyTo(0, 0, d, phi, animate, ty);
    return;
  }
  let x0 = Infinity, z0 = Infinity, x1 = -Infinity, z1 = -Infinity;
  for (const j of kids[0]) { x0 = Math.min(x0, X[j] - R[j]); x1 = Math.max(x1, X[j] + R[j]); z0 = Math.min(z0, Z[j] - R[j]); z1 = Math.max(z1, Z[j] + R[j]); }
  const r = Math.max(x1 - x0, z1 - z0) / 2;
  const polar = W <= 760 ? 0.18 : 0.78;
  flyTo((x0 + x1) / 2, (z0 + z1) / 2 + r * 0.12, distanceToFit(r) * (W <= 760 ? 0.92 : 0.8), polar, animate);
}
function focusOn(i, animate = true) {
  if (mode === "tree") {               // the node with the span of what rests on it, turned to face the viewer
    const span = Math.max(R[i] * 5, (SPAN[i] || 0) * 0.55, tree.method.C * 0.015);
    const a = Math.atan2(Z[i], X[i]), off = Math.hypot(X[i], Z[i]) > tree.method.C * 0.03;
    return flyTo(X[i], Z[i], distanceToFit(span), W <= 760 ? 0.5 : 0.92, animate, CY[i], off ? Math.atan2(Math.cos(a), Math.sin(a)) : null, minFlight);
  }
  // an act is framed with room around it, so its links and partners stay in view;
  // zooming further dissolves it into its articles
  const isAct = K[i] === "act" || K[i] === "bucket";
  const polar = W <= 760 ? 0.3 : (isAct ? 0.82 : 0.72);
  flyTo(X[i], Z[i], distanceToFit(R[i] * (isAct ? 3.2 : 1.0)), polar, animate);
}

// ---------- edges: hierarchical bundling ----------
let edgesDirty = true, lastEdgeBuild = 0, lastEntries = [], hoverLink = -1, buildMs = 0;
const pv = new THREE.Vector3();
function projectedPx(i) {
  const d = camera.position.distanceTo(pv.set(X[i] - origin.x, CY[i] - origin.y, Z[i] - origin.z));
  return R[i] * pxPerUnitAt(d);
}
function spanPx(i) {   // tree: the width on screen of what hangs under a node
  const d = camera.position.distanceTo(pv.set(X[i] - origin.x, CY[i] - origin.y, Z[i] - origin.z));
  return SPAN[i] * pxPerUnitAt(d);
}
function treeFront(i) { let j = i; while (j !== ROOT && P[j] >= 0 && spanPx(j) < SPAN_PX) j = P[j]; return j; }
// Tree: the path through the common basis, lifted (case law) or lowered (legislation).
function controlPointsTree(a, b, lift) {
  const A = ancestorsOf(a), B = ancestorsOf(b);
  const setB = new Map(B.map((n, k) => [n, k]));
  let ia = 0;
  while (ia < A.length && !setB.has(A[ia])) ia++;
  const lca = A[ia] ?? ROOT, ib = setB.get(lca) ?? B.length - 1;
  const nodes = [...A.slice(0, ia + 1), ...B.slice(0, ib).reverse()];
  const off = (lift ? 1 : -1) * tree.method.C * 0.012;
  const pts = nodes.map((n, k) => [X[n] - origin.x, CY[n] - origin.y + (k === 0 || k === nodes.length - 1 ? 0 : off), Z[n] - origin.z]);
  if (pts.length === 2) pts.splice(1, 0, pts[0].map((v, d) => (v + pts[1][d]) / 2 + (d === 1 ? off * 2 : 0)));
  const n = pts.length - 1, p0 = pts[0], pn = pts[n];
  return pts.map((p, k) => k === 0 || k === n ? p : p.map((v, d) => BETA * v + (1 - BETA) * (p0[d] + (k / n) * (pn[d] - p0[d]))));
}
// Tree links (place in the tree): a radial elbow from parent to child, as in a radial
// dendrogram. The Bézier runs in polar coordinates (angle, radius, height), like d3.linkRadial:
// the sideways part follows the ring instead of cutting a chord through the cone.
function radialLink(p, c, samples = 16) {
  const r0 = Math.hypot(X[p], Z[p]), r1 = Math.hypot(X[c], Z[c]), rm = (r0 + r1) / 2;
  const a1 = Math.atan2(Z[c], X[c]);
  let a0 = r0 > 1e-6 ? Math.atan2(Z[p], X[p]) : a1;
  if (a0 - a1 > Math.PI) a0 -= 2 * Math.PI; else if (a1 - a0 > Math.PI) a0 += 2 * Math.PI;
  const q = [[a0, r0, CY[p]], [a0, rm, CY[p]], [a1, rm, CY[c]], [a1, r1, CY[c]]];
  const out = new Float32Array(samples * 3);
  for (let s = 0; s < samples; s++) {
    const u = s / (samples - 1), w = [(1 - u) ** 3, 3 * u * (1 - u) ** 2, 3 * u * u * (1 - u), u ** 3];
    const a = w[0] * q[0][0] + w[1] * q[1][0] + w[2] * q[2][0] + w[3] * q[3][0];
    const r = w[0] * q[0][1] + w[1] * q[1][1] + w[2] * q[2][1] + w[3] * q[3][1];
    out[s * 3] = r * Math.cos(a) - origin.x;
    out[s * 3 + 1] = w[0] * q[0][2] + w[1] * q[1][2] + w[2] * q[2][2] + w[3] * q[3][2] - origin.y;
    out[s * 3 + 2] = r * Math.sin(a) - origin.z;
  }
  return out;
}
// Art. 51 BV → the 26 cantonal constitutions: down the central axis, then out to each canton.
function axisLink(p, c, samples = 18) {
  const C = tree.method.C;
  const q = [[X[p], CY[p], Z[p]], [0, CY[p] - 0.2 * C, 0], [X[c] * 0.2, CY[c] + 0.22 * C, Z[c] * 0.2], [X[c], CY[c], Z[c]]];
  const out = new Float32Array(samples * 3);
  for (let s = 0; s < samples; s++) {
    const u = s / (samples - 1), w = [(1 - u) ** 3, 3 * u * (1 - u) ** 2, 3 * u * u * (1 - u), u ** 3];
    for (let d = 0; d < 3; d++) out[s * 3 + d] = w[0] * q[0][d] + w[1] * q[1][d] + w[2] * q[2][d] + w[3] * q[3][d] - (d === 0 ? origin.x : d === 1 ? origin.y : origin.z);
  }
  return out;
}
const LV = (i) => (TN[i] ? TN[i].l : -1);
let treeDirty = true;
// Tree branches as a radial elbow tree drawn on the cone's surface: from each parent a trunk
// runs outward and down to an arc that spans its children on one floor; from the arc a short
// drop reaches each child. One arc per parent and floor instead of one curve per child, so
// a BV article visibly embraces the acts that rest on it and no branch crosses another.
const polarPt = (a, r, y) => [r * Math.cos(a) - origin.x, y - origin.y, r * Math.sin(a) - origin.z];
const angOf = (i) => Math.atan2(Z[i], X[i]), radOf = (i) => Math.hypot(X[i], Z[i]);
function wrapNear(a, ref) { while (a - ref > Math.PI) a -= 2 * Math.PI; while (ref - a > Math.PI) a += 2 * Math.PI; return a; }
function flat(list) { const out = new Float32Array(list.length * 3); list.forEach((q, k) => out.set(q, k * 3)); return out; }
function arcPts(a0, a1, r, y) {
  const n = Math.max(2, Math.min(180, Math.ceil(Math.abs(a1 - a0) / 0.015) + 1)), out = [];
  for (let k = 0; k < n; k++) out.push(polarPt(a0 + (a1 - a0) * k / (n - 1), r, y));
  return out;
}
function combOf(p, group) {             // geometry shared by a parent's children on one floor
  const rp = radOf(p), yp = CY[p], ap = rp > 1e-6 ? angOf(p) : angOf(group[0]);
  const rc = Math.min(...group.map(radOf)), yc = CY[group[0]];
  return { rp, yp, ap, ra: rp + (rc - rp) * 0.5, ya: yp + (yc - yp) * 0.5 };
}
function branchPath(i) {                // the single path parent → trunk → arc → drop → i
  const p = P[i], g = combOf(p, [i]), a = wrapNear(angOf(i), g.ap);
  return flat([polarPt(g.ap, g.rp, g.yp), polarPt(g.ap, g.ra, g.ya), ...arcPts(g.ap, a, g.ra, g.ya).slice(1), polarPt(a, radOf(i), CY[i])]);
}
function writeTreeLines() {
  treeDirty = false;
  if (mode !== "tree") return;
  const lines = [], chain = new Set();
  if (sel.i >= 0) {                    // what rests on the selection; for the apex (all of it) only the first step
    let j = sel.i; while (j >= 0) { chain.add(j); j = P[j]; }
    const sub = web ? [] : subtree(sel.i);           // with the constellation, what rests on it is shown there
    for (const d of sub.length <= 800 ? sub : kids[sel.i]) chain.add(d);
  }
  const size = LAY.tree.size, top = Math.log10(size[ROOT] + 1), light = theme === "light";
  const groups = new Map();             // parent -> height -> children
  for (const i of orbIndex) {
    const p = P[i];
    if (p < 0) continue;
    if (LV(i) === 4) {                  // constitutional link, not an Ingress: the taproot
      const on = chain.has(i) && chain.has(p), w = Math.log10(size[i] + 1) / top;
      lines.push({ pts: axisLink(p, i), width: on ? 2.6 : 1.1 + 2.6 * w, color: HUE.bv, alpha: on ? 0.95 : related ? 0.05 : 0.22 + 0.4 * w, flow: on ? 0.6 : 0.2 });
      continue;
    }
    if (!groups.has(p)) groups.set(p, new Map());
    const byY = groups.get(p), key = CY[i].toFixed(2);
    if (!byY.has(key)) byY.set(key, []);
    byY.get(key).push(i);
  }
  const dim = related ? 0.18 : 1;
  for (const [p, byY] of groups) for (const group of byY.values()) {
    const g = combOf(p, group), crown = K[group[0]] !== "act";
    const as = group.map((c) => wrapNear(angOf(c), g.ap));
    const amin = Math.min(g.ap, ...as), amax = Math.max(g.ap, ...as);
    const w = Math.log10(group.reduce((s, c) => s + size[c], 0) + 1) / top;
    const lv = LV(group[0]), canton = lv >= 5;
    const kc = TN[p] && TN[p].ct;
    const col = crown ? (kc ? HUE.k : HUE.bv) : light ? GRAPHITE : HUE[HK[p]] || HUE.n;
    const a0 = (canton ? 0.22 : 0.34 + 0.4 * w) * dim;
    lines.push({ pts: flat([polarPt(g.ap, g.rp, g.yp), polarPt(g.ap, g.ra, g.ya)]), width: 0.8 + 3.4 * w, color: col, alpha: a0, flow: related ? 0 : 0.15 });
    if (amax - amin > 1e-4) lines.push({ pts: flat(arcPts(amin, amax, g.ra, g.ya)), width: 0.6 + 2 * w, color: col, alpha: a0 * 0.9, flow: 0 });
    group.forEach((c, k) => {
      lines.push({ pts: flat([polarPt(as[k], g.ra, g.ya), polarPt(as[k], radOf(c), CY[c])]), width: canton ? 0.45 : 0.6,
        color: crown ? (kc ? HUE.k : HUE.bv) : light ? GRAPHITE : HUE[HK[c]] || HUE.n, alpha: (canton ? 0.16 : 0.26) * dim, flow: 0 });
    });
  }
  for (const i of chain) {              // the selection's chain of delegation, and what rests on it
    const p = P[i];
    if (p < 0 || !chain.has(p) || LV(i) === 4) continue;
    const lv = LV(i);
    lines.push({ pts: branchPath(i), width: lv >= 5 ? 1.2 : 2.4, color: K[i] !== "act" ? HUE.bv : HUE[HK[i]] || HUE.n,
      alpha: lv >= 5 ? 0.5 : 0.95, flow: 0.6 });   // pulses run downwards: delegation
  }
  if (sel.i >= 0 && !web) {            // further bases of the selection, and acts naming it as a further basis (the constellation shows them)
    for (const b of basisOf[sel.i] || []) if (!b.prim) lines.push({ pts: radialLink(b.j, sel.i), width: 1.5, color: BASIS2, alpha: 0.8, flow: 0.5 });
    for (const d of dependents[sel.i] || []) if (!d.prim) lines.push({ pts: radialLink(sel.i, d.i), width: 1.2, color: BASIS2, alpha: 0.6, flow: 0.5 });
  }
  setRibbons(treeLines, lines);
}
// The node an act's link attaches to at the current zoom: the first ancestor whose
// children are too small to tell apart (so links merge into readable bundles).
function frontierOf(i, open) {
  const path = [];
  let j = i;
  while (j >= 0) { path.push(j); j = P[j]; }
  for (let k = path.length - 1; k >= 0; k--) { const n = path[k]; if (!open(n)) return n; }
  return i;
}
function ancestorsOf(i) { const a = []; let j = i; while (j >= 0) { a.push(j); j = P[j]; } return a; }
function controlPoints(a, b, lift) {   // lift: above the plane (case law), else below (legislation)
  const A = ancestorsOf(a), B = ancestorsOf(b);
  const setB = new Map(B.map((n, k) => [n, k]));
  let ia = 0;
  while (ia < A.length && !setB.has(A[ia])) ia++;
  const lca = A[ia], ib = setB.get(lca);
  const nodes = [...A.slice(0, ia + 1), ...B.slice(0, ib).reverse()];
  const pts = nodes.map((n, k) => {
    let y;
    if (k === 0 || k === nodes.length - 1) y = lift ? (K[n] === "act" ? 2 * R[n] : R[n] * 0.08) : -R[n] * 0.04;
    else y = lift ? R[n] * 0.5 : -R[n] * 0.38;
    return [X[n] - origin.x, y, Z[n] - origin.z];
  });
  if (pts.length === 2) {   // siblings: one intermediate point above (below) their parent
    const p = P[a];
    const mid = [(pts[0][0] + pts[1][0]) / 2, p >= 0 ? R[p] * (lift ? 0.35 : -0.28) : 0, (pts[0][2] + pts[1][2]) / 2];
    pts.splice(1, 0, mid);
  }
  // Holten's straightening: pull control points toward the straight line by (1 - β)
  const n = pts.length - 1, p0 = pts[0], pn = pts[n];
  return pts.map((p, k) => k === 0 || k === n ? p : p.map((v, d) => BETA * v + (1 - BETA) * (p0[d] + (k / n) * (pn[d] - p0[d]))));
}
function bspline(cp, samples) {
  // uniform cubic B-spline, clamped by repeating the end points
  const P2 = [cp[0], cp[0], ...cp, cp[cp.length - 1], cp[cp.length - 1]];
  const segs = P2.length - 3, out = new Float32Array(samples * 3);
  for (let s = 0; s < samples; s++) {
    const u = (s / (samples - 1)) * segs;
    const k = Math.min(Math.floor(u), segs - 1), f = u - k;
    const b0 = (1 - f) ** 3 / 6, b1 = (3 * f ** 3 - 6 * f ** 2 + 4) / 6, b2 = (-3 * f ** 3 + 3 * f ** 2 + 3 * f + 1) / 6, b3 = f ** 3 / 6;
    for (let d = 0; d < 3; d++) out[s * 3 + d] = b0 * P2[k][d] + b1 * P2[k + 1][d] + b2 * P2[k + 2][d] + b3 * P2[k + 3][d];
  }
  return out;
}
const widthOf = (n) => Math.min(9, 0.7 + 1.25 * Math.log10(n + 1));

function buildEdges() {
  edgesDirty = false;
  lastEdgeBuild = performance.now();
  const t0 = lastEdgeBuild;
  const cache = new Map();
  const open = (n) => {
    if (cache.has(n)) return cache.get(n);
    const v = K[n] !== "act" && K[n] !== "bucket" && (n === 0 || projectedPx(n) > OPEN_PX);
    cache.set(n, v);
    return v;
  };
  lastSig = openSignature();
  const focus = sel.i < 0 ? null : mode === "tree" ? new Set(K[sel.i] === "act" ? [sel.i] : []) : new Set(subtree(sel.i));
  const agg = new Map();    // "fa|fb|layer" -> weight
  const fcache = new Map(), isTree = mode === "tree";
  const front = (a) => { let f = fcache.get(a); if (f === undefined) { f = isTree ? treeFront(a) : frontierOf(a, open); fcache.set(a, f); } return f; };
  const add = (a, b, w, layer) => {
    if (isTree && (!inLayout(a) || !inLayout(b))) return;      // an act outside today's federal tree
    const fa = focus && focus.has(a) ? a : front(a), fb = focus && focus.has(b) ? b : front(b);
    if (fa === fb) return;
    const key = layer === 1 ? fa + "|" + fb + "|1" : (fa < fb ? fa + "|" + fb : fb + "|" + fa) + "|2";
    agg.set(key, (agg.get(key) || 0) + w);
  };
  const quiet = isTree && !focus && !treeAll;                 // tree overview: the delegation tree alone
  const inFocus = (a, b) => !quiet && !sel.art && (!focus || focus.has(a) || focus.has(b));   // an article: only its own links
  const hj = web ? (web.hot >= 0 ? web.hot : hoverLink) : -1;
  const shown = web ? (a, b) => hj >= 0 && ((a === sel.i && b === hj) || (b === sel.i && a === hj)) : inFocus;   // the constellation draws the rest
  if (showCurrent) core.edges.forEach(([a, b, n], k) => {
    if (!shown(a, b)) return;
    let w = n;
    const ey = period && edgeYears ? edgeYears[k] : null;
    if (period && edgeYears) {
      w = 0;
      if (ey) { const [y0, ys] = ey; for (let y = Math.max(period[0], y0); y <= Math.min(period[1], y0 + ys.length - 1); y++) w += ys[y - y0]; }
    }
    if (w > 0) add(a, b, w, 2);
  });
  if (showWire) for (const [a, b, n] of core.xedges || []) if (shown(a, b)) add(a, b, n, 1);
  const lines = { wire: [], current: [] };
  let maxW = { 1: 1, 2: 1 };
  for (const [key, w] of agg) { const layer = +key.split("|")[2]; maxW[layer] = Math.max(maxW[layer], w); }
  const entries = [...agg].sort((p, q) => q[1] - p[1]).slice(0, focus ? 700 : 1100);
  const hl = hoverLink >= 0 ? new Set(ancestorsOf(hoverLink)) : null;   // a link pointed at in the panel
  lastEntries = entries;
  for (const [key, w] of entries) {
    const [fa, fb, layer] = key.split("|").map(Number);
    const both = pairKind.get(fa < fb ? fa + "|" + fb : fb + "|" + fa) === 3;
    // weight relative to the strongest link on screen: additive glow piles up, so the
    // overview stays faint and lets the strongest bundles carry the picture
    const strong = Math.log10(w + 1) / Math.log10(maxW[layer] + 1), s3 = strong ** 3;
    let alpha = focus ? 0.22 + 0.4 * strong : 0.07 + 0.4 * s3;
    let width = focus ? 1 + 3.2 * strong ** 2 : 0.9 + 4.8 * s3;
    if (isTree) { alpha *= focus ? 0.6 : 0.55; width *= 0.8; }      // the tree lines carry the picture
    if (focus && layer === 1) { alpha = 0.5 + 0.35 * strong; width = 1.6 + 2.2 * strong; }   // legislative weights are mostly 1
    if (hl) { if (hl.has(fa) || hl.has(fb)) { alpha = 0.95; width += 2; } else alpha *= 0.2; }
    const cpf = isTree ? controlPointsTree : controlPoints;
    if (layer === 2) {
      lines.current.push({ pts: bspline(cpf(fa, fb, true), SAMPLES), width, color: both ? BOTH : CURRENT, alpha, flow: 0.25 });
    } else {
      lines.wire.push({ pts: bspline(cpf(fa, fb, false), SAMPLES), width: width * 1.1, color: both ? BOTH : WIRE, alpha, flow: 1, taper: true });
    }
  }
  setRibbons(current, lines.current);
  setRibbons(wires, lines.wire);
  // links of the selected article
  const fl = [];
  if (sel.art) {
    const a = artPos(sel.i, sel.art);
    const rec = actRec(sel.i), q = rec && dotsAct === sel.i ? rec.arts.indexOf(a) : -1, ay = q >= 0 ? artY(q) : 0;
    if (a && a[6] && a[6].e) for (const e of a[6].e) {
      const ax = a[2] - origin.x, az = a[3] - origin.z, bx = e[2] - origin.x, bz = e[3] - origin.z;
      const d = Math.hypot(bx - ax, bz - az);
      const cp = [[ax, ay, az], [ax + (bx - ax) * 0.25, ay + d * 0.35, az + (bz - az) * 0.25], [ax + (bx - ax) * 0.75, d * 0.35, az + (bz - az) * 0.75], [bx, 0, bz]];
      fl.push({ pts: bspline(cp, 28), width: widthOf(e[4]) * 0.9, color: CURRENT, alpha: 0.8, flow: 0.4 });
    }
    if (a && a[6] && a[6].x && showWire) for (const j of a[6].x) {
      const ax = a[2] - origin.x, az = a[3] - origin.z, bx = X[j] - origin.x, bz = Z[j] - origin.z;
      const cp = [[ax, ay, az], ...controlPoints(sel.i, j, false).slice(1, -1), [bx, 0, bz]];
      fl.push({ pts: bspline(cp, 40), width: 2.6, color: WIRE, alpha: 0.95, flow: 1, taper: true });
    }
  }
  setRibbons(focusRibbons, fl);
  buildMs = performance.now() - t0;
}

// The bundles only change when a container crosses the OPEN_PX threshold (or the
// origin moves): rebuilding is skipped while the set of open containers is the same.
let lastSig = "";
function openSignature() {
  const out = [origin.x.toPrecision(8), origin.z.toPrecision(8)], st = [ROOT];
  if (mode === "tree") {
    while (st.length) { const n = st.pop(); if (n !== ROOT && spanPx(n) < SPAN_PX) continue; out.push(n); for (const k of kids[n]) st.push(k); }
    return out.join(",");
  }
  while (st.length) {
    const n = st.pop();
    if (K[n] === "act" || K[n] === "bucket" || (n !== 0 && projectedPx(n) <= OPEN_PX)) continue;
    out.push(n);
    for (const k of kids[n]) st.push(k);
  }
  return out.join(",");
}
function frontierChanged() { return openSignature() !== lastSig; }

// ---------- articles ----------
function ensurePack(pk) {
  if (pk < 0) return null;
  if (packs.has(pk)) return Promise.resolve(packs.get(pk));
  if (packWait.has(pk)) return packWait.get(pk);
  const pr = getJSON(`data/p/${pk}.json`).then((d) => { packs.set(pk, d); packWait.delete(pk); refreshPanel(); return d; })
    .catch(() => { packWait.delete(pk); });
  packWait.set(pk, pr);
  return pr;
}
const actRec = (i) => { const p = packs.get(PK[i]); return p ? p.acts[ids[i]] : null; };
const decInfo = (i, did) => { const p = packs.get(PK[i]); return p ? p.dec[did] : null; };
function artPos(i, key) { const r = actRec(i); return r && r.arts ? r.arts.find((a) => a[0] === key) || null : null; }

function openArticles(i) {
  if (dotsAct === i) return;
  closeArticles();
  const rec = actRec(i);
  if (!rec || !rec.arts) return;
  const n = rec.arts.length;
  const pos = new Float32Array(n * 3), rad = new Float32Array(n), col = new Float32Array(n * 3), st = new Float32Array(n * 4);
  const maxN = Math.max(1, ...rec.arts.map((a) => a[5]));
  const hue = HUE[HK[i]] || HUE.n;
  // skyline: an article rises by the decisions citing it (square root, tallest = 0.55 r of the act)
  artH = new Float32Array(n);
  rec.arts.forEach((a, k) => {
    artH[k] = a[5] ? R[i] * 0.55 * Math.sqrt(a[5] / maxN) : 0;
    pos.set([a[2] - X[i], artH[k] + 0.0004 * R[i], a[3] - Z[i]], k * 3);
    rad[k] = a[4];
    col.set(hue, k * 3);
    st.set([a[5] ? Math.sqrt(a[5] / maxN) : 0, a[6] && a[6].rep ? 1 : 0, 0, 1], k * 4);
  });
  dots = makeDots(pos, rad, col, st);
  stems = makeStems(pos, col);
  for (const m of [dots, stems]) { m.position.set(X[i] - origin.x, 0, Z[i] - origin.z); scene.add(m); }
  dotsAct = i;
}
function closeArticles() {
  if (!dots) return;
  for (const m of [dots, stems]) { scene.remove(m); m.geometry.dispose(); m.material.dispose(); }
  dots = null; stems = null; dotsAct = -1; artH = null;
}
const artY = (k) => (artH ? artH[k] * artFade : 0);
function updateArticleState() {
  if (!dots) return;
  const rec = actRec(dotsAct), st = dots.geometry.attributes.iState.array;
  rec.arts.forEach((a, k) => {
    st[k * 4 + 2] = a[0] === sel.art ? 1 : (a[0] === hover.art && hover.i === dotsAct ? 0.5 : 0);
    st[k * 4 + 3] = 1;
  });
  if (sel.art && sel.i === dotsAct) {
    const linked = new Set(((artPos(sel.i, sel.art) || [])[6]?.e || []).filter((e) => e[0] === ids[sel.i]).map((e) => e[1]));
    rec.arts.forEach((a, k) => { if (a[0] !== sel.art && !linked.has(a[0])) st[k * 4 + 3] = 0.5; });
  }
  dots.geometry.attributes.iState.needsUpdate = true;
}

// ---------- picking ----------
const ray = new THREE.Raycaster();
function pick(px, py) {
  if (!core) return { i: -1, art: null };
  const v = new THREE.Vector2((px / W) * 2 - 1, -(py / H) * 2 + 1);
  ray.setFromCamera(v, camera);
  const o = ray.ray.origin, d = ray.ray.direction;
  if (mode === "tree") {               // the node under the pointer, nearest the eye; small ones get 6 px
    let best = -1, key = Infinity;
    for (const i of orbIndex) {
      const [sx, sy, sz] = toScreen(X[i], CY[i], Z[i]);
      if (sz > 1) continue;
      const rpx = projectedPx(i), dd = Math.hypot(sx - px, sy - py);
      const k = dd <= rpx ? sz : dd <= 6 ? 2 + dd : Infinity;
      if (k < key) { key = k; best = i; }
    }
    return { i: best, art: null };
  }
  // 1. orbs (acts): nearest sphere hit among visible ones
  let best = -1, bestT = Infinity;
  const c = new THREE.Vector3();
  const st = [0];
  while (st.length) {
    const i = st.pop();
    const isOrb = K[i] === "act" || K[i] === "bucket";
    c.set(X[i] - origin.x, isOrb ? R[i] : 0, Z[i] - origin.z);
    // bounding test: containers are spheres on the plane holding their orbs (height ≤ 2r)
    const rr = isOrb ? R[i] : R[i] * 1.5;
    const oc = c.clone().sub(o), b = oc.dot(d), disc = b * b - (oc.lengthSq() - rr * rr);
    if (disc < 0 && i !== 0) continue;
    if (isOrb) {
      if (projectedPx(i) < 1.5) continue;
      const tHit = b - Math.sqrt(disc);
      if (tHit > 0 && tHit < bestT) { bestT = tHit; best = i; }
      continue;
    }
    if (i === 0 || projectedPx(i) > 3) for (const k of kids[i]) st.push(k);
  }
  // 2. the plane: deepest container holding the point
  let ground = -1, gx = 0, gz = 0;
  if (Math.abs(d.y) > 1e-9) {
    const tp = -o.y / d.y;
    if (tp > 0) {
      gx = o.x + d.x * tp + origin.x; gz = o.z + d.z * tp + origin.z;
      let i = 0;
      for (;;) {
        let next = -1;
        for (const k of kids[i]) {
          if (K[k] === "act" || K[k] === "bucket") continue;
          if ((gx - X[k]) ** 2 + (gz - Z[k]) ** 2 <= R[k] * R[k] && projectedPx(k) > 3) { next = k; break; }
        }
        if (next < 0) break;
        i = next; ground = i;
      }
      // articles of the opened act: nearest risen dot on screen
      if (dots && artFade > 0.3) {
        const rec = actRec(dotsAct), cell = Math.max(10, Math.min(28, rec.p * pxPerUnitAt(viewDist()) * 0.6));
        let bd = cell * cell, ba = null;
        rec.arts.forEach((a, q) => {
          const [sx, sy, sz] = toScreen(a[2], artY(q), a[3]);
          if (sz > 1) return;
          const dd = (sx - px) ** 2 + (sy - py) ** 2;
          if (dd < bd) { bd = dd; ba = a; }
        });
        if (ba) return { i: dotsAct, art: ba[0] };
      }
    }
  }
  if (best >= 0 && !(dots && best === dotsAct)) return { i: best, art: null };
  if (best >= 0 && dots && best === dotsAct) return { i: best, art: null };
  return { i: ground, art: null };
}

// ---------- labels (HTML, kept in step with the camera) ----------
const labelLayer = $("labels");
const pool = [];
function labelEl(k) {
  while (pool.length <= k) {
    const el = document.createElement("div");
    el.className = "lab";
    labelLayer.appendChild(el);
    pool.push(el);
  }
  return pool[k];
}
labelLayer.addEventListener("click", (e) => { const b = e.target.closest(".edge[data-sel]"); if (b) select(+b.dataset.sel); });
const v3 = new THREE.Vector3();
function toScreen(x, y, z) {
  v3.set(x - origin.x, y, z - origin.z).project(camera);
  return [((v3.x + 1) / 2) * W, ((1 - v3.y) / 2) * H, v3.z];
}
function updateLabels() {
  const cand = [];
  const st = mode === "tree" ? [] : [0];
  const camD = (i) => projectedPx(i);
  if (mode === "tree") for (const i of orbIndex) {
    const px = camD(i), k = K[i];
    if (k === "act") { if (px > 3.5) cand.push([i, px]); }
    else if (k === "bvart" || k === "kvart") { if (px > 3 && spanPx(i) > 22) cand.push([i, px * 0.8]); }
    else if (k === "tgroup" && ids[i].startsWith("KG:")) { if (spanPx(i) > 320) cand.push([i, 20]); }   // a canton's groups: close up only
    else if (k === "title" || k === "chapter" || k === "section") { const sp = spanPx(i); if (sp > (k === "title" ? 90 : 160)) cand.push([i, sp * 0.1]); }
    else if (spanPx(i) > 50) cand.push([i, 25]);
  }
  while (st.length) {
    const i = st.pop();
    const isOrb = K[i] === "act" || K[i] === "bucket";
    const px = camD(i);
    if (px < 2) continue;
    if (i > 0) {
      if (isOrb && px > 9) cand.push([i, px]);
      else if (!isOrb && px > 46 && !(K[i] === "group" && px > 400)) cand.push([i, px]);
    }
    if (!isOrb && (i === 0 || px > 14)) for (const k of kids[i]) st.push(k);
  }
  if (sel.i >= 0) {   // the focus and its partners always get a name (the constellation names them itself)
    const extra = web ? [] : [...jAdj[sel.i].slice(0, 8).map((e) => e[0]), ...wOut[sel.i].slice(0, 6).map((e) => e[0]), ...wIn[sel.i].slice(0, 4).map((e) => e[0])];
    for (const j of [sel.i, ...(hoverLink >= 0 ? [hoverLink] : []), ...extra]) cand.push([j, 1e6 - cand.length]);
  } else if (focusSet && focusSet.size <= 40) {   // a tour stop naming a few acts: they get their names
    for (const j of focusSet) if (K[j] === "act") cand.push([j, 1e6 - cand.length]);
  }
  cand.sort((a, b) => b[1] - a[1]);
  const boxes = [], used = new Set();
  let k = 0;
  const fits = (b) => { for (const o of boxes) if (b[0] < o[2] && b[2] > o[0] && b[1] < o[3] && b[3] > o[1]) return false; boxes.push(b); return true; };
  for (const [i, px] of cand) {
    if (k >= 90 || used.has(i)) continue;
    if (web && i !== sel.i) continue;                // the constellation names the partners
    const isOrb = mode === "tree" || K[i] === "act" || K[i] === "bucket";
    if (mode === "tree" && !inLayout(i)) continue;
    if (related && !related.has(i) && px < 1e5) continue;
    const [sx, sy, sz] = isOrb ? toScreen(X[i], CY[i] + R[i], Z[i]) : toScreen(X[i], 0, Z[i] - R[i] * 0.93);
    if (sz > 1) continue;
    const text = isOrb ? label(i) : areaLabel(i);
    const size = K[i] === "title" ? 13 : K[i] === "chapter" || K[i] === "section" ? 11.5 : K[i] === "bvart" ? 11 :
      isOrb ? Math.max(11, Math.min(22, Math.sqrt(px) * 2.2)) : (K[i] === "domain" ? 19 : Math.max(11, Math.min(16, Math.sqrt(px) * 1.2)));
    const w = Math.min(Math.min(text.length, 46) * size * 0.56, 300), h = size * 1.3;
    if (sx - w / 2 < 4 || sx + w / 2 > W - 4 || sy - h < 4 || sy > H - 4) continue;
    const box = [sx - w / 2, sy - h - 4, sx + w / 2, sy];
    if (!fits(box)) continue;
    used.add(i);
    const el = labelEl(k++);
    el.textContent = text.length > 46 ? text.slice(0, 45) + "…" : text;
    el.style.transform = `translate(${sx.toFixed(1)}px, ${(sy - 4).toFixed(1)}px) translate(-50%, -100%)`;
    el.style.fontSize = size.toFixed(1) + "px";
    el.dataset.kind = isOrb && K[i] === "act" ? "act" : K[i];
    el.style.setProperty("--hue", cssHue(HK[i], true));
    el.classList.toggle("on", i === sel.i);
    el.classList.remove("edge");
    el.hidden = false;
  }
  // tree: the name of each floor beside its rim, at the floor's outline on the screen's left
  // (like the storeys of a building section); on its near rim when that edge is off screen
  if (mode === "tree" && !web) {
    const ca = Math.atan2(camera.position.z + origin.z, camera.position.x + origin.x);
    let lastY = -1e9;                              // floors close together on screen: keep their names apart
    for (const [y, r, key] of tree.plates) {
      const a = toScreen(r * Math.cos(ca + Math.PI / 2), y, r * Math.sin(ca + Math.PI / 2));
      const b = toScreen(r * Math.cos(ca - Math.PI / 2), y, r * Math.sin(ca - Math.PI / 2));
      const right = $("panel").hidden;               // the panel covers the right edge when open
      const [lx, ly, lz] = (a[0] > b[0]) === right ? a : b;
      const nn = key === "lvBV" ? null : tree.method.by_level[key.slice(2)];
      const el = labelEl(k++);
      const [head, sub] = t[key].split(" · ");
      el.innerHTML = `<b>${esc(sub || head)}</b><span>${esc(sub ? head : "")}${nn ? (sub ? " · " : "") + num(nn) : ""}</span>`;
      el.style.fontSize = "";
      el.dataset.kind = "plate";
      el.classList.remove("on", "edge");
      if (lz <= 1 && (right ? lx < W - 200 : lx > 240) && ly > 70 && ly < H - 30) {
        const yy = Math.max(ly, lastY + 34);
        lastY = yy;
        const wEst = Math.max((sub || head).length * 7.6, ((sub ? head : "").length + 8) * 7.3);   // keep it on screen
        const xx = right ? Math.min(lx + 16 + (yy - ly) * 0.25, W - 10 - wEst) : lx - 16;
        fits(right ? [xx, yy - 17, xx + wEst, yy + 17] : [xx - wEst, yy - 17, xx, yy + 17]);   // canton names keep clear
        el.style.transform = right ? `translate(${xx.toFixed(1)}px, ${yy.toFixed(1)}px) translate(0, -50%)`
          : `translate(${(lx - 16).toFixed(1)}px, ${yy.toFixed(1)}px) translate(-100%, -50%)`;
        el.style.textAlign = right ? "left" : "right";
        el.hidden = false;
        continue;
      }
      el.style.textAlign = "center";
      // a phone, or a selection (its panel or card names the floor): names over the tree would hide it
      if (W <= 760 || sel.i >= 0) { el.hidden = true; continue; }
      const [sx, sy, sz] = toScreen(r * Math.cos(ca), y, r * Math.sin(ca));
      const wc = Math.max((sub || head).length * 7.6, 120);
      if (sz > 1 || sx < 60 || sx > W - 60 || sy < 70 || sy > H - 30 || !fits([sx - wc / 2, sy + 6, sx + wc / 2, sy + 40])) { el.hidden = true; continue; }
      el.style.transform = `translate(${sx.toFixed(1)}px, ${(sy + 6).toFixed(1)}px) translate(-50%, 0)`;
      el.hidden = false;
    }
  }
  // tree: each canton's name at the outer rim of its sector (its code where the sector is narrow)
  if (mode === "tree" && W > 760 && !web) {
    const rim = tree.plates[tree.plates.length - 1];
    for (const i of orbIndex) {
      if (!TN[i] || TN[i].l !== 4) continue;
      const a = Math.atan2(Z[i], X[i]), [sx, sy, sz] = toScreen(rim[1] * 1.04 * Math.cos(a), rim[0], rim[1] * 1.04 * Math.sin(a));
      if (sz > 1 || sx < 30 || sx > W - 30 || sy < 70 || sy > H - 20) continue;
      const wide = spanPx(i) > 150, text = wide ? cantonName(TN[i].ct) : TN[i].ct;
      const w = text.length * 7.5 + 6, box = [sx - w / 2, sy - 9, sx + w / 2, sy + 9];
      if (!fits(box)) continue;
      const el = labelEl(k++);
      el.textContent = text;
      el.style.transform = `translate(${sx.toFixed(1)}px, ${sy.toFixed(1)}px) translate(-50%, -50%)`;
      el.style.fontSize = "";
      el.dataset.kind = "kt";
      el.classList.remove("on", "edge");
      el.hidden = false;
    }
  }
  // tree: the decisions hanging under the selected act
  for (const [did, d, pos] of courtList) {
    if (!pos || k >= 200) continue;
    const [sx, sy, sz] = toScreen(pos[0], pos[1], pos[2]);
    if (sz > 1 || sx < 10 || sx > W - 10 || sy < 60 || sy > H - 10) continue;
    const rp = pos[3] * pxPerUnitAt(camera.position.distanceTo(pv.set(pos[0] - origin.x, pos[1] - origin.y, pos[2] - origin.z)));
    const w = d[0].length * 6.6 + 8, box = [sx - w / 2, sy + rp + 1, sx + w / 2, sy + rp + 17];   // below its sphere
    if (!fits(box)) continue;
    const el = labelEl(k++);
    el.textContent = d[0];
    el.style.transform = `translate(${sx.toFixed(1)}px, ${(sy + rp + 2).toFixed(1)}px) translate(-50%, 0)`;
    el.style.fontSize = "";
    el.dataset.kind = "dec";
    el.classList.remove("on", "edge");
    el.hidden = false;
  }
  // scale: acts in view, federal and cantonal
  {
    let vf = 0, vk = 0;
    for (const i of orbIndex) {
      if (K[i] !== "act") continue;
      if ((related && !related.has(i)) || (TN[i] && TN[i].cited)) continue;   // acts in force only
      const [sx, sy, sz] = toScreen(X[i], CY[i], Z[i]);
      if (sz > 1 || sx < 0 || sx > W || sy < 0 || sy > H) continue;
      if (isCant(i) || node(i).c) vk++; else vf++;
    }
    updateHud(vf, vk);
  }
  // article numbers when the floor plan is close enough to read
  if (dots) {
    const rec = actRec(dotsAct), pxu = pxPerUnitAt(viewDist());
    const cell = rec.p * pxu;
    if (cell > 26) {
      for (let q = 0; q < rec.arts.length; q++) {
        const a = rec.arts[q];
        if (k >= 260) break;
        const [sx, sy, sz] = toScreen(a[2], artY(q), a[3]);
        if (sz > 1 || sx < -20 || sx > W + 20 || sy < -20 || sy > H + 20) continue;
        const el = labelEl(k++);
        if (a[0] === sel.art) {   // the selected article: full name, above its dot
          const lift = a[4] * pxPerUnitAt(camera.position.distanceTo(v3.set(a[2] - origin.x, artY(q), a[3] - origin.z))) * 1.9 + 6;
          el.textContent = `${t.art} ${a[1]} ${label(dotsAct)}`;
          el.style.transform = `translate(${sx.toFixed(1)}px, ${(sy - lift).toFixed(1)}px) translate(-50%, -100%)`;
          el.style.fontSize = "16px";
        } else {
          el.textContent = cell > 70 ? `${t.art} ${a[1]}` : a[1];
          el.style.transform = `translate(${sx.toFixed(1)}px, ${sy.toFixed(1)}px) translate(-50%, -50%)`;
          el.style.fontSize = Math.min(13, cell * 0.24).toFixed(1) + "px";
        }
        el.dataset.kind = "art";
        el.classList.toggle("on", a[0] === sel.art);
        el.classList.remove("edge");
        el.hidden = false;
      }
    }
  }
  // partners outside the view: a chip on the edge of the free area, pointing to them
  if (sel.i >= 0 && !sel.art && !web) {
    const fr = freeRect(), x0 = fr.cx - fr.w / 2 + 24, x1 = fr.cx + fr.w / 2 - 24, y0 = 96, y1 = fr.cy + fr.h / 2 - 70;
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    const list = [...new Set([hoverLink, ...jAdj[sel.i].slice(0, 5).map((e) => e[0]), ...wOut[sel.i].slice(0, 3).map((e) => e[0])])]
      .filter((j) => j >= 0 && j !== sel.i);
    const placed = [];
    for (const j of list) {
      if (!inLayout(j)) continue;
      const [sx, sy, sz] = toScreen(X[j], CY[j], Z[j]);
      if (sz < 1 && sx > x0 && sx < x1 && sy > y0 && sy < y1) continue;
      let dx = sx - cx, dy = sy - cy;
      if (sz > 1) { dx = -dx; dy = -dy; }
      const f = Math.min((x1 - cx) / Math.max(Math.abs(dx), 1e-6), (y1 - cy) / Math.max(Math.abs(dy), 1e-6));
      let ex = cx + dx * f, ey = cy + dy * f;
      const tb = $("tools").getBoundingClientRect();     // keep clear of the legend and tools
      if (ex < tb.right + 60 && ey > tb.top - 16) ey = tb.top - 16;
      const step = ey > cy ? -24 : 24;        // one direction: stepping toward the centre would oscillate around it
      const hw = label(j).length * 3.6 + 22;  // half width of the chip; it keeps clear of names already placed
      const hit = (y) => placed.some(([px, py]) => Math.abs(px - ex) < 120 && Math.abs(py - y) < 22) ||
        boxes.some((o) => ex + hw > o[0] && ex - hw < o[2] && y + 11 > o[1] && y - 11 < o[3]);
      for (let g = 0; g < 40 && hit(ey); g++) ey += step;
      placed.push([ex, ey]);
      const el = labelEl(k++);
      const kind = pairKind.get(sel.i < j ? sel.i + "|" + j : j + "|" + sel.i) || 2;
      el.innerHTML = `<i style="transform: rotate(${Math.atan2(dy, dx).toFixed(3)}rad)">➜</i>${esc(label(j))}`;
      el.style.transform = `translate(${ex.toFixed(1)}px, ${ey.toFixed(1)}px) translate(-50%, -50%)`;
      el.style.fontSize = "12.5px";
      el.dataset.kind = "act";
      el.dataset.sel = j;
      el.dataset.link = kind === 3 ? "both" : kind === 1 ? "wire" : "current";
      el.classList.add("edge");
      el.classList.toggle("on", j === hoverLink);
      el.hidden = false;
    }
  }
  for (let j = k; j < pool.length; j++) pool[j].hidden = true;
}
function label(i) {
  const o = node(i);
  if (o.k === "kvart") return `${ksym(o.ct)} ${o.n} ${kvShort(o.ct)}`;
  if (o.k === "tgroup" && o.i.startsWith("KG:")) return `${t["kg_" + o.i.split(":")[2]]} · ${o.ct}`;
  if (TN[i] && TN[i].l === 4 && i >= NCORE) return kvShort(TN[i].ct);
  if (o.k === "act" && o.ct && i >= NCORE) {     // a cantonal act read from its collection
    const ab = o.ab ? o.ab.split(/\s*,\s*/).pop() : "";
    if (ab && ab.length <= 16) return ab;
    const tt = o.t || "";
    return tt.length > 42 ? tt.slice(0, 40).replace(/\s+\S*$/, "") + " …" : tt || `${o.ct} ${o.ksr}`;
  }
  if (o.k === "bvart") return `${t.art} ${o.n}`;
  if (o.k === "title" || o.k === "chapter" || o.k === "section") return `${pickL(o.num).replace(/:$/, "")} ${pickL(o.h)}`.trim();
  if (o.k === "abv") return t.abv;
  if (o.k === "tgroup") return o.i === "TREE:int" ? t.tgIntl : t.tgNone;
  if (o.k === "root") return t.root;
  if (o.k === "domain") return t[o.i];
  if (o.k === "canton") return CANTON[o.c] ? CANTON[o.c][LANGS.indexOf(lang)] : o.c;
  if (o.k === "bucket") return `${t.bucket} (${o.codes})`;
  if (o.k === "act") {
    const a = o.a ? (o.a[lang] || o.a.de || o.a.fr || o.a.it) : null;
    if (a) return o.reg && o.reg !== "a" ? `${a} ${o.reg}` : (o.reg === "a" ? `a${a}` : a);
    return o.sr ? `SR ${o.sr}${o.reg ? "@" + o.reg : ""}` : o.i;
  }
  return title(i) || o.sr || o.i;
}
function areaLabel(i) {
  const o = node(i);
  if (o.k === "group") return o.sr;                     // the act inside carries the name
  return (o.k === "area" && o.sr ? o.sr + "  " : "") + label(i);
}
function title(i) {
  if (TN[i] && TN[i].t) return TN[i].t;          // cantonal acts: the official title from the canton's collection
  const v = titles[i]; return v == null ? "" : typeof v === "string" ? v : v[0];
}
const cantonName = (ct) => (CANTON[ct] ? CANTON[ct][LANGS.indexOf(lang)] : ct);
const kvShort = (ct) => `${t.kvShort} ${ct}`;
const ksym = (ct) => (tree && tree.method.ksym && tree.method.ksym[ct]) || t.art;
const ctLang = (ct) => (["FR", "GE", "VD", "NE", "JU", "VS"].includes(ct) ? "fr" : ct === "TI" ? "it" : "de");
function kUrl(i) {                               // the act on the canton's own portal
  const o = TN[i];
  if (!o) return "";
  if (o.u) return o.u;
  const tpl = tree.method.kurl && tree.method.kurl[o.ct];
  return tpl && o.ksr ? tpl.replace("{}", o.ksr) : "";
}
function titleLang(i) { const v = titles[i]; return v && typeof v !== "string" ? v[1] : null; }

// ---------- loop ----------
let lastT = performance.now(), lastLabels = 0, moving = false, lastCam = "";
function loop(now) {
  requestAnimationFrame(loop);
  if (!core) return;
  const dt = Math.min(0.05, (now - lastT) / 1000);
  lastT = now;
  if (anim) anim.step(now);
  const idle = mode === "tree" && sel.i < 0 && !anim && !story && now - lastInput > 25000 && !reduceMotion;
  if (idle !== controls.autoRotate) { controls.autoRotate = idle; controls.autoRotateSpeed = 0.35; }
  controls.update();
  const dist = viewDist();
  camera.near = Math.max(dist * 0.002, 1e-7);
  camera.far = dist * 80 + 4000;
  camera.updateProjectionMatrix();
  // re-centre the floating origin when the view has travelled far from it
  if (!anim && Math.hypot(controls.target.x, controls.target.z) > Math.max(dist * 3, 5)) {
    const w = worldTarget(); rebase(w.x, w.z);
  }
  const pxScale = (H / 2) / Math.tan((camera.fov * Math.PI) / 360);
  for (const m of [rings, orbs, courtOrbs]) if (m) m.material.uniforms.uPixelScale.value = pxScale;
  orbs.material.uniforms.uMinPx.value = mode === "tree" ? 2.4 : 1.1;     // every act stays a visible dot
  if (courtOrbs) courtOrbs.material.uniforms.uMinPx.value = 2.4;
  {                                    // depth fade around the point looked at: the far side recedes
    const d = camera.position.distanceTo(controls.target);
    if (mode === "tree") setFog(d * 0.92, d * 1.75, 0.8); else setFog(d * 1.2, d * 3.5, 0.45);
  }
  if (treeDirty) writeTreeLines();
  for (const m of [wires, current, focusRibbons, treeLines, courtLines]) {
    if (!m) continue;
    m.material.uniforms.uTime.value = now / 1000;
    m.material.uniforms.uViewport.value.set(W / 2, H / 2);
  }
  stars.material.uniforms.uScale.value = dpr;
  // articles of the act in view
  const camKey = [camera.position.x, camera.position.y, camera.position.z, controls.target.x, controls.target.z].map((v) => v.toPrecision(6)).join();
  moving = camKey !== lastCam;
  lastCam = camKey;
  updateOpenAct();
  if (dots) {
    dots.material.uniforms.uPixelScale.value = pxScale;
    const px = projectedPx(dotsAct);
    artFade = Math.max(0, Math.min(1, (px - ART_PX * 0.8) / (ART_PX * 0.6)));
    dots.material.uniforms.uFade.value = artFade;
    stems.material.uniforms.uFade.value = artFade;
    const j = orbOf[dotsAct];
    if (j >= 0) {
      const os = orbs.geometry.attributes.iState.array;
      os[j * 4 + 2] = Math.max(0, Math.min(1, (px - ART_PX * 0.7) / (ART_PX * 0.5)));
      orbs.geometry.attributes.iState.needsUpdate = true;
    }
  }
  if (edgesDirty || (moving && now - lastEdgeBuild > 220 && frontierChanged())) buildEdges();
  if (moving || now - lastLabels > 200) { updateLabels(); lastLabels = now; }
  renderWeb(now);
  composer.render(dt);
}
function updateOpenAct() {
  if (mode === "tree") return;         // the skyline lives on the SR map
  // the largest act on screen whose articles are worth showing
  let best = -1, bestPx = ART_PX * 0.75;
  const cand = sel.i >= 0 && K[sel.i] === "act" ? [sel.i] : [];
  const tw = worldTarget();
  const st = [0];
  while (st.length && cand.length < 1) {
    const i = st.pop();
    if (K[i] === "act") { if ((tw.x - X[i]) ** 2 + (tw.z - Z[i]) ** 2 < R[i] * R[i] * 1.2) cand.push(i); continue; }
    if ((tw.x - X[i]) ** 2 + (tw.z - Z[i]) ** 2 < R[i] * R[i]) for (const k of kids[i]) st.push(k);
  }
  for (const i of cand) { const px = projectedPx(i); if (PK[i] >= 0 && px > bestPx) { best = i; bestPx = px; } }
  if (best < 0) {
    if (dots && projectedPx(dotsAct) < ART_PX * 0.6) {
      const j = orbOf[dotsAct];
      if (j >= 0) { orbs.geometry.attributes.iState.array[j * 4 + 2] = 0; orbs.geometry.attributes.iState.needsUpdate = true; }
      closeArticles();
    }
    return;
  }
  if (best !== dotsAct) {
    if (actRec(best)) { openArticles(best); updateArticleState(); }
    else ensurePack(PK[best])?.then(() => { if (projectedPx(best) > ART_PX * 0.75) { openArticles(best); updateArticleState(); } });
  }
}

// ---------- input ----------
let downAt = null, lastTap = 0;
canvas.addEventListener("pointerdown", (e) => { downAt = { x: e.clientX, y: e.clientY, t: performance.now() }; anim = null; $("results").hidden = true; });
canvas.addEventListener("pointerup", (e) => {
  if (!downAt) return;
  const moved = Math.hypot(e.clientX - downAt.x, e.clientY - downAt.y);
  downAt = null;
  if (moved > 5 || e.button === 2) return;
  const h = pick(e.clientX, e.clientY);
  if (h.i > 0) select(h.i, h.art);
  else if (sel.i >= 0) { const p = P[sel.i]; p > 0 ? select(p) : goHome(); }
});
canvas.addEventListener("pointermove", (e) => {
  if (e.pointerType !== "mouse" || downAt) return;
  const h = pick(e.clientX, e.clientY);
  if (h.i !== hover.i || h.art !== hover.art) {
    hover = h;
    if (orbOf && !sel.art) refreshHover();
    updateArticleState();
  }
  showTip(e.clientX, e.clientY, h);
});
canvas.addEventListener("pointerleave", () => { $("tip").hidden = true; });
canvas.addEventListener("contextmenu", (e) => e.preventDefault());
function refreshHover() {
  const os = orbs.geometry.attributes.iState.array;
  orbIndex.forEach((i, j) => { os[j * 4 + 3] = i === sel.i && !sel.art ? 0.38 : (i === hover.i ? 0.3 : 0); });
  orbs.geometry.attributes.iState.needsUpdate = true;
  canvas.style.cursor = hover.i > 0 ? "pointer" : "grab";
}
function showTip(px, py, h) {
  const tip = $("tip");
  if (h.i <= 0) { tip.hidden = true; return; }
  let head, line;
  if (h.art) {
    const a = artPos(h.i, h.art);
    if (!a) { tip.hidden = true; return; }
    const hh = a[6] && a[6].h ? (a[6].h[lang] || a[6].h.de || "") : "";
    head = `${t.art} ${a[1]} ${label(h.i)}${hh ? " · " + hh : ""}`;
    line = t.decN(num(a[5]));
  } else {
    const o = node(h.i);
    head = K[h.i] === "act" ? label(h.i) + (title(h.i) ? " · " + title(h.i) : "") :
      K[h.i] === "bvart" ? `${label(h.i)} ${t.bv}${pickL(o.h) ? " · " + pickL(o.h) : ""}` : areaLabel(h.i);
    line = t.decN(num(NC[h.i]));
    if (mode === "tree" && dependents[h.i] && dependents[h.i].length) line += ` · ${t.restN(num(dependents[h.i].length))}`;
    const nl = wOut[h.i].length + wIn[h.i].length, nc = jAdj[h.i].length;
    if (o.k === "act" && (nl || nc)) line += ` · ${t.lawWiring} ${nl} · ${t.practice} ${nc}`;
  }
  const hint = webOn && !h.art && h.i !== sel.i && (K[h.i] === "act" || K[h.i] === "bvart" || K[h.i] === "kvart") ? t.webClick : "";
  tip.innerHTML = `<b>${esc(head.length > 140 ? head.slice(0, 139) + "…" : head)}</b><span>${esc(line)}</span>${hint ? `<span class="hint">${esc(hint)}</span>` : ""}`;
  tip.hidden = false;
  tip.style.left = Math.min(px + 14, W - tip.offsetWidth - 8) + "px";
  tip.style.top = Math.min(py + 16, H - tip.offsetHeight - 8) + "px";
}
addEventListener("resize", resize);
function resize() {
  W = innerWidth; H = innerHeight;
  renderer.setSize(W, H);
  composer.setSize(W, H);
  bloom.resolution.set(W / 2, H / 2);
  camera.aspect = W / H;
  camera.updateProjectionMatrix();
  edgesDirty = true;
  if (!$("story").hidden) storyTop = $("story").getBoundingClientRect().top;
  relayoutWeb();
}
addEventListener("keydown", (e) => {
  if (e.target.matches("input, select, textarea")) return;
  if (e.key === "/") { e.preventDefault(); $("search").focus(); }
  else if (story && story.tr && (e.key === "ArrowRight" || e.key === "ArrowLeft")) { e.preventDefault(); stepTour(e.key === "ArrowRight" ? 1 : -1); }
  else if (e.key === "f" && !e.metaKey && !e.ctrlKey) $("focusbtn").click();
  else if (e.key === "c" && !e.metaKey && !e.ctrlKey) $("webbtn").click();
  else if (e.key === "Escape") {
    if (story && story.opening) skipOpening();
    else if (story && (story.tr || story.descent)) { story.descent = false; endTour(false); }
    else if (!$("method").hidden) closeMethod();
    else if (!$("intro").hidden) closeIntro();
    else if (sel.i >= 0) { const p = P[sel.i]; sel.art ? select(sel.i) : (p > 0 ? select(p) : goHome()); }
  }
});

// ---------- selection ----------
function select(i, art = null, animate = true, quiet = false) {
  if (i >= 0 && (art || !inLayout(i))) {      // an article, or an act outside the tree: the SR map shows it
    if (mode === "tree" && LAY.sr && i < NCORE) setMode("sr", false);
  }
  if (i >= NCORE && mode !== "tree") setMode("tree", false);
  if (i < 0) {
    const was = !$("panel").hidden;
    sel = { i: -1, art: null }; $("panel").hidden = true; $("tools").classList.remove("raised");
    hideCourts(); webFor(-1);
    refreshStates(); refreshHover(); writeHash(); crumbs(); renderSpine();
    if (was && animate) recentre();
    return;
  }
  sel = { i, art };
  hoverLink = -1;
  $("panel").hidden = quiet;
  $("tools").classList.toggle("raised", W <= 760);
  closeIntro();
  if (PK[i] >= 0) ensurePack(PK[i]);
  refreshStates(); refreshHover();
  if (art) {
    const go = () => {
      const a = artPos(i, art), rec = actRec(i);
      if (a && rec) {
        const fr = freeRect();
        const dist = (rec.p * 9) * ((H / 2) / Math.tan((camera.fov * Math.PI) / 360)) / Math.min(fr.w, fr.h);
        const maxN = Math.max(1, ...rec.arts.map((x) => x[5]));
        const ty = a[5] ? R[i] * 0.55 * Math.sqrt(a[5] / maxN) : 0;
        flyTo(a[2], a[3], Math.max(dist, distanceToFit(R[i]) * 0.22), 0.55, animate, ty);
      } else focusOn(i, animate);
      updateArticleState(); refreshPanel();
    };
    if (actRec(i)) go(); else { refreshPanel(); ensurePack(PK[i])?.then(go); }
  } else {
    if (!(story && story.descent)) focusOn(i, animate);
    refreshPanel();
  }
  hideCourts();                                  // a tour or descent shows the courts at their own stop
  if (mode === "tree" && K[i] === "act" && PK[i] >= 0 && !webOn && !(story && (story.tr || story.descent))) courtsFor(i);
  writeHash(); crumbs(); renderSpine();
  webFor(i);                                     // its connections, brought next to it
}
function goHome() { select(-1, null, false); home(); }

function crumbs() {
  const el = $("crumbs");
  el.innerHTML = "";
  let i = sel.i;
  if (i < 0) return;
  const path = [];
  while (i >= 0) { path.unshift(i); i = P[i]; }
  path.forEach((j, n) => {
    if (n) el.append(Object.assign(document.createElement("span"), { textContent: "›" }));
    const b = document.createElement("button");
    const o = node(j);
    b.textContent = o.k === "area" || o.k === "group" ? o.sr : o.k === "title" || o.k === "chapter" || o.k === "section" ? pickL(o.num).replace(/:$/, "") : label(j);
    b.title = label(j);
    b.onclick = () => (j === 0 && mode === "sr" ? goHome() : select(j));
    el.append(b);
  });
  if (sel.art) {
    const a = artPos(sel.i, sel.art);
    el.append(Object.assign(document.createElement("span"), { textContent: "›" }));
    el.append(Object.assign(document.createElement("button"), { textContent: `${t.art} ${a ? a[1] : ""}` }));
  }
}

// ---------- panel ----------
function spark(y0, ys, hue) {
  if (!ys || !ys.length) return "";
  const max = Math.max(...ys), n = ys.length, w = 360, h = 64, pad = 14, bw = w / Math.max(n, 1);
  const col = cssHue(hue);
  let bars = "";
  ys.forEach((v, j) => {
    if (!v) return;
    const bh = (h - pad - 4) * v / max;
    const inP = !period || (y0 + j >= period[0] && y0 + j <= period[1]);
    bars += `<rect x="${(j * bw).toFixed(2)}" y="${(h - pad - bh).toFixed(2)}" width="${Math.max(bw - 0.6, 0.6).toFixed(2)}" height="${bh.toFixed(2)}" fill="${col}" fill-opacity="${inP ? 0.9 : 0.25}"/>`;
  });
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="${esc(t.perYear)}">
    <line x1="0" x2="${w}" y1="${h - pad}" y2="${h - pad}" stroke="var(--line)" stroke-width="1"/>${bars}
    <text x="0" y="${h - 2}" font-size="10" fill="var(--muted)" font-family="IBM Plex Mono, monospace">${y0}</text>
    <text x="${w}" y="${h - 2}" font-size="10" fill="var(--muted)" text-anchor="end" font-family="IBM Plex Mono, monospace">${y0 + n - 1} · max ${num(max)}</text></svg>`;
}
const decUrl = (did) => "https://mcp.opencaselaw.ch/entscheid/" + encodeURIComponent(did);
function decList(i, list) {
  return `<ul class="list">${list.map((did) => {
    const d = decInfo(i, did);
    if (!d) return "";
    return `<li><a class="k link" href="${decUrl(did)}" target="_blank" rel="noopener" title="${esc(t.openDec)}">${esc(d[0])}</a><span class="v">${esc(t.citedBy(num(d[2])))}</span><span class="d">${d[1] ? esc(d[1]) : ""}</span></li>`;
  }).join("")}</ul>`;
}
function countBlock(n, what, o, rec) {
  let s = `<section><div class="big"><b>${num(n)}</b><span>${esc(what)}</span></div>`;
  if (period && (o || rec)) {
    const src = rec || o;
    let sh = 0;
    if (src.ys) for (let y = Math.max(period[0], src.y0); y <= Math.min(period[1], src.y0 + src.ys.length - 1); y++) sh += src.ys[y - src.y0];
    s += `<p class="note">${esc(t.inPeriod(period[0], period[1]))}: <span class="mono">${num(sh)}</span></p>`;
  }
  if (o && o.f != null && n) s += `<p class="note">${esc(t.federalShare)}: <span class="mono">${num(o.f)}</span> (${Math.round(100 * o.f / n)} %)</p>`;
  return s + "</section>";
}
function linkRow(j, value, sub, kind) {
  const sw = kind === 3 ? "both" : kind === 1 ? "wire" : "current";
  return `<li><button class="k link" data-sel="${j}"><i class="sw ${sw}"></i>${esc(label(j))}</button><span class="v">${esc(value)}</span>${sub ? `<span class="d">${esc(sub)}</span>` : ""}</li>`;
}
function interdependencies(i) {
  let html = "";
  const kindOf = (j) => pairKind.get(i < j ? i + "|" + j : j + "|" + i) || 0;
  if (wOut[i].length || wIn[i].length) {
    html += `<section data-sec="law"><h3><i class="sw wire"></i>${esc(t.lawWiring)}</h3><p class="note">${esc(t.lawWiringNote)}</p>`;
    if (wOut[i].length) html += `<p class="note">${esc(t.refersTo)}</p><ul class="list">${wOut[i].slice(0, 12).map(([j, n]) => linkRow(j, t.refsN(num(n)), title(j), kindOf(j))).join("")}</ul>`;
    if (wIn[i].length) html += `<p class="note">${esc(t.referredBy)}</p><ul class="list">${wIn[i].slice(0, 12).map(([j, n]) => linkRow(j, t.refsN(num(n)), title(j), kindOf(j))).join("")}</ul>`;
    html += "</section>";
  }
  if (jAdj[i].length) {
    html += `<section data-sec="court"><h3><i class="sw current"></i>${esc(t.practice)}</h3><p class="note">${esc(t.practiceNote)}</p><ul class="list">${jAdj[i].slice(0, 12).map(([j, n, l]) =>
      linkRow(j, t.together(num(n), l.toFixed(1)), title(j), kindOf(j))).join("")}</ul></section>`;
  }
  if (core.xedges && (wOut[i].length || wIn[i].length || jAdj[i].length)) {
    const law = new Set([...wOut[i], ...wIn[i]].map((e) => e[0]));
    const prac = jAdj[i].map((e) => e[0]);
    const onlyPrac = prac.filter((j) => !law.has(j)).slice(0, 6);
    const pracSet = new Set(prac);
    const onlyLaw = [...law].filter((j) => !pracSet.has(j) && K[j] === "act").sort((a, b) => NC[b] - NC[a]).slice(0, 6);
    if (onlyPrac.length) html += `<section><h3>${esc(t.practiceOnly)}</h3><ul class="list">${onlyPrac.map((j) => linkRow(j, "", title(j), 2)).join("")}</ul></section>`;
    if (onlyLaw.length) html += `<section><h3>${esc(t.lawOnly)}</h3><ul class="list">${onlyLaw.map((j) => linkRow(j, "", title(j), 1)).join("")}</ul></section>`;
  }
  return html;
}
// The legal basis of an act, as its Ingress states it, and the acts resting on it.
const LEVEL = (i) => (TN[i] ? TN[i].l : -1);
function ensureIngress() {
  if (ingress || ingressWait || !tree) return;
  ingressWait = getJSON("data/ingress.json").then((d) => { ingress = d; ingressWait = null; refreshPanel(); }).catch(() => { ingressWait = null; });
}
let ingressK = null, ingressKWait = null;     // cantonal Ingresses and the clauses of their bases (7 MB: on demand)
function ensureIngressK() {
  if (ingressK || ingressKWait || !tree) return;
  ingressKWait = getJSON("data/ingress_k.json").then((d) => { ingressK = d; ingressKWait = null; refreshPanel(); }).catch(() => { ingressKWait = null; });
}
const listRow = (c, v, d) => `<li><button class="k link" data-sel="${c}">${esc(label(c))}</button><span class="v">${v ?? ""}</span>${d ? `<span class="d">${esc(d)}</span>` : ""}</li>`;
// A cantonal constitution: Art. 51 BV above it, below it the articles other acts rest on and the groups.
function kvSections(i) {
  const ct = TN[i].ct, art51 = idIndex.get("BV:art_51"), L = LAY.tree;
  const ch = L.kids[i] || [], arts = ch.filter((c) => K[c] === "kvart"), groups = ch.filter((c) => K[c] === "tgroup");
  const under = (c) => subtree(c).filter((j) => K[j] === "act" && j !== c).length;
  const byFloor = [5, 6, 7].map((l) => [l, subtree(i).filter((j) => LV(j) === l && !TN[j].cited).length]);
  let html = `<section><h3><i class="sw tree"></i>${esc(t.basisHead)}</h3><ul class="list"><li><button class="k link" data-sel="${art51}"><i class="sw tree"></i>${esc(t.art)} 51 ${esc(t.bv)}</button><span class="d">${esc(t.kvBasis)}</span></li></ul><p class="note">${esc(t.kvBasisNote)}</p></section>`;
  html += `<section><h3>${esc(t.kvFloors)}</h3><dl class="facts">${byFloor.map(([l, n]) => `<dt>${esc(t["lv" + l].split(" · ")[1] || t["lv" + l])}</dt><dd class="mono">${num(n)}</dd>`).join("")}</dl></section>`;
  if (arts.length) html += `<section><h3><i class="sw tree"></i>${esc(t.kvArts)} · ${num(arts.length)}</h3><ul class="list">${arts.slice().sort((a, b) => under(b) - under(a)).slice(0, 40).map((c) =>
    listRow(c, num(under(c)), pickL(node(c).h))).join("")}</ul>${arts.length > 40 ? `<p class="note">+ ${num(arts.length - 40)}</p>` : ""}</section>`;
  html += `<section><ul class="list">${groups.map((c) => listRow(c, num((L.kids[c] || []).length), t["kg_" + ids[c].split(":")[2] + "Note"])).join("")}</ul></section>`;
  const e = TN[i].e;
  if (e) html += `<section><a class="link" href="${esc(e + "/" + lang)}" target="_blank" rel="noopener">${esc(t.official)} ↗</a></section>`;
  if (kUrl(i)) html += `<section><a class="link" href="${esc(kUrl(i))}" target="_blank" rel="noopener">${esc(t.cantonalColl(cantonName(ct)))} ↗</a></section>`;
  return html;
}
// A cantonal act: who enacted it, on what it rests (verbatim clauses), what rests on it.
function kActSections(i) {
  ensureIngressK();
  const o = TN[i], bs = basisOf[i] || [], deps = dependents[i] || [];
  const rec = ingressK ? ingressK[TK[i]] : null;
  let html = `<section><h3><i class="sw tree"></i>${esc(t.basisHead)}</h3>`;
  const facts = [];
  if (rec && rec[0]) facts.push([t.enactedBy, rec[0]]);
  facts.push([t.floor, (t["lv" + o.l] || "").split(" · ")[1] || ""]);
  if (o.ad) facts.push([t.adopted, o.ad.split("-").reverse().join(".")]);
  html += `<dl class="facts">${facts.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>`;
  if (o.fb === "Titel" || o.fb === "unbekannt") html += `<p class="note">${esc(o.fb === "Titel" ? t.floorByTitle : t.floorUnknown)}</p>`;
  if (bs.length) {
    html += `<ul class="list">${bs.map((b) => {
      const clause = rec && rec[2] ? rec[2][b.k] || "" : "";
      const tags = [b.prim ? t.basisPlace : "", b.via === "old" ? t.basisOld : "", b.via === "earlier" ? t.basisEarlier : "",
        b.via === "absent" ? t.basisAbsent : "", b.j >= 0 && !b.found ? t.basisNotFound : ""].filter(Boolean).join(" · ");
      if (b.j < 0) return `<li><span class="k"><i class="sw tree2"></i>${esc(b.via === "unresolved" ? t.basisUnresolved : b.via === "earlier" ? t.basisEarlierShort : t.basisAbsentShort)}</span><span class="v">${esc(tags)}</span>${clause ? `<span class="d">«${esc(clause)}»</span>` : ""}</li>`;
      const isBV = K[b.j] === "bvart" || b.j === LAY.tree.root;
      const names = artNames(b.eids);
      const head = K[b.j] === "kvart" ? label(b.j) + (names.length > 1 ? ` (${names.join(", ")})` : "")
        : isBV ? (names.length ? `${t.art} ${names.join(", ")} ${t.bv}` : t.bvFull)
          : `${names.length ? (/§/.test(clause) ? "§" : t.art) + " " + names.slice(0, 6).join(", ") + (names.length > 6 ? " …" : "") + " " : ""}${label(b.j)}`;
      const target = isBV && names.length ? idIndex.get("BV:" + b.eids[0]) ?? b.j : b.j;
      return `<li><button class="k link" data-sel="${target}"><i class="sw ${b.prim ? "tree" : "tree2"}"></i>${esc(head)}</button><span class="v">${esc(tags)}</span>${clause ? `<span class="d">«${esc(clause)}»</span>` : ""}</li>`;
    }).join("")}</ul>`;
    if (P[i] >= 0 && K[P[i]] === "tgroup") html += `<p class="note">${esc(t.kgFedPlace)}</p>`;
  } else html += `<p class="note">${esc(!rec && ingressKWait ? t.loading : rec && rec[1] ? t.kNoBasis : t.kNoIngress)}</p>`;
  if (rec && rec[1]) html += `<details class="ingress"><summary>${esc(t.ingressK)}</summary><blockquote lang="${ctLang(o.ct)}">${esc(rec[1])}</blockquote></details>`;
  html += "</section>";
  if (deps.length) html += dependentsSection(deps, t.restHead);
  const u = kUrl(i);
  if (u) html += `<section><a class="link" href="${esc(u)}" target="_blank" rel="noopener">${esc(t.cantonalColl(cantonName(o.ct)))} ↗</a></section>`;
  return html;
}
function artNames(eids) { return [...new Set(eids.map((e) => (e.startsWith("disp_") ? t.finalProv + " " : "") + e.replace(/^.*art_/, "").replace(/_/g, "")))]; }
// a label that stands on its own in running text: "Art. 82 BV", "SG BE"
function fullLabel(j) {
  const o = node(j), l = label(j);
  if (o.k === "bvart") return `${l} ${ROOT >= 0 ? label(ROOT) : "BV"}`;
  const ct = TN[j] && TN[j].ct;
  if (ct && TN[j].l >= 5 && !l.includes(ct)) return `${l} ${ct}`;
  return l;
}
function basisSections(i) {
  if (!tree || !TN[i]) return "";
  if (TN[i].l === 4) return kvSections(i);        // a cantonal constitution
  if (TN[i].cited) {                               // cited in decisions, no act in force under that code
    return `<section><h3><i class="sw tree"></i>${esc(t.basisHead)}</h3><p class="note">${esc(t.kg_citedNote)}</p></section>`;
  }
  if (TN[i].ct) return kActSections(i);            // a cantonal act read from its collection
  ensureIngress();
  const bs = basisOf[i] || [], deps = dependents[i] || [];
  const ing = ingress ? ingress[TK[i]] : null;
  let html = `<section><h3><i class="sw tree"></i>${esc(t.basisHead)}</h3>`;
  if (TN[i].by) html += `<p class="note">${esc(t.enactedBy)}: ${esc(ing && ing[0] ? ing[0] : t["by_" + TN[i].by] || TN[i].by)}</p>`;
  if (bs.length) {
    html += `<ul class="list">${bs.map((b) => {
      const isBV = K[b.j] === "bvart" || b.j === LAY.tree.root || K[b.j] === "abv";
      const names = artNames(b.eids);
      let head;
      if (K[b.j] === "abv") head = t.abv;
      else if (isBV) head = names.length ? `${t.art} ${names.join(", ")} ${t.bv}` : t.bvFull;
      else head = `${names.length ? t.art + " " + names.join(", ") + " " : ""}${label(b.j)}`;
      const tags = [b.prim ? t.basisPlace : "", b.how === "exec" ? t.basisExec : "", b.via === "aBV→BV" ? t.basisAbv : "",
        b.found ? "" : t.basisNotFound].filter(Boolean).join(" · ");
      const target = isBV && names.length ? idIndex.get("BV:" + b.eids[0]) ?? b.j : b.j;
      return `<li><button class="k link" data-sel="${target}"><i class="sw ${b.prim ? "tree" : "tree2"}"></i>${esc(head)}</button><span class="v">${esc(tags)}</span>${b.clause ? `<span class="d">«${esc(b.clause)}»</span>` : ""}</li>`;
    }).join("")}</ul>`;
  } else html += `<p class="note">${esc(t.noBasis)}</p>`;
  if (ing && ing[1]) html += `<details class="ingress"><summary>${esc(t.ingress)}</summary><blockquote lang="de">${esc(ing[1])}</blockquote></details>`;
  html += "</section>";
  if (deps.length) html += delegationNorms(i, deps) + dependentsSection(deps, t.restHead);
  return html;
}
// The provisions of this act that other acts name as their basis (in effect its delegation norms).
function artKey(e) {
  const m = e.match(/(disp_[^/]+\/)?art_(\d+)(?:_([a-z]))?(?:_([a-z]+))?/);
  return m ? (m[1] ? 1e7 : 0) + +m[2] * 1000 + (m[3] ? (m[3].charCodeAt(0) - 96) * 30 : 0) + (m[4] ? m[4].length : 0) : 1e9;
}
function delegationNorms(i, deps) {
  const by = new Map();
  for (const d of deps) for (const e of d.eids || []) { if (!by.has(e)) by.set(e, new Set()); by.get(e).add(d.i); }
  if (!by.size) return "";
  const keys = [...by.keys()].sort((a, b) => artKey(a) - artKey(b));
  return `<section><h3><i class="sw tree"></i>${esc(t.delegHead)} · ${num(keys.length)}</h3><ul class="list">${keys.slice(0, 60).map((e) => {
    const name = (e.startsWith("disp_") ? "SchlT/ÜB " : "") + e.replace(/^.*art_/, "").replace(/_/g, "");
    const acts = [...by.get(e)].sort((a, b) => NC[b] - NC[a]);
    return `<li><button class="k link" data-sel="${i}" data-art="${esc(e)}">${esc(t.art)} ${esc(name)}</button><span class="v">${num(acts.length)}</span><span class="d">${acts.slice(0, 8).map((j) => `<button class="link" data-sel="${j}">${esc(label(j))}</button>`).join(", ")}${acts.length > 8 ? " …" : ""}</span></li>`;
  }).join("")}</ul>${keys.length > 60 ? `<p class="note">+ ${num(keys.length - 60)}</p>` : ""}</section>`;
}
function dependentsSection(deps, head) {
  const by = new Map();
  for (const d of deps) { const l = LEVEL(d.i); if (!by.has(l)) by.set(l, []); by.get(l).push(d); }
  let html = `<section data-sec="deps"><h3><i class="sw tree"></i>${esc(head)} · ${num(deps.length)}</h3>`;
  for (const l of [...by.keys()].sort()) {
    const list = by.get(l).sort((a, b) => NC[b.i] - NC[a.i]);
    html += `<p class="note">${esc(t["lv" + l] || "")}</p><ul class="list">${list.slice(0, 40).map((d) => {
      const names = artNames(d.eids || []);
      return `<li><button class="k link" data-sel="${d.i}"><i class="sw ${d.prim ? "tree" : "tree2"}"></i>${esc(label(d.i))}</button><span class="v">${names.length ? esc(t.art + " " + names.slice(0, 4).join(", ") + (names.length > 4 ? " …" : "")) : ""}</span><span class="d">${esc(title(d.i))}</span></li>`;
    }).join("")}</ul>${list.length > 40 ? `<p class="note">+ ${num(list.length - 40)}</p>` : ""}`;
  }
  return html + "</section>";
}
function treePanel(i) {                // the Constitution's own nodes, the sectors, and cantonal law
  const o = node(i);
  let eyebrow = t.bvFull, h2 = label(i), sub = "", html = "";
  if (o.ct) {
    const ctn = cantonName(o.ct);
    if (o.k === "kvart") {
      const kv = LAY.tree.P[i];
      eyebrow = `${t.cantonalAct} · ${ctn}`; sub = pickL(o.h);
      html += dependentsSection(dependents[i] || [], t.restHeadArt);
      const e = TN[kv] && TN[kv].e;
      if (e) html += `<section><a class="link" href="${esc(e + "/" + lang + "#" + o.i.split(":")[2])}" target="_blank" rel="noopener">${esc(t.official)} ↗</a></section>`;
    } else if (o.k === "tgroup") {
      eyebrow = `${t.cantonalAct} · ${ctn}`;
      const g = o.i.split(":")[2], ch = (LAY.tree.kids[i] || []).slice().sort((a, b) => NC[b] - NC[a] || label(a).localeCompare(label(b)));
      html += `<p class="note">${esc(t["kg_" + g + "Note"])}</p><section><div class="big"><b>${num(ch.length)}</b><span>${esc(t.acts)}</span></div><ul class="list">${ch.slice(0, 80).map((c) =>
        listRow(c, NC[c] ? num(NC[c]) : "", title(c))).join("")}</ul>${ch.length > 80 ? `<p class="note">+ ${num(ch.length - 80)}</p>` : ""}</section>`;
    } else {                           // an act of the canton's collection, or its constitution
      eyebrow = `${t.cantonalAct} · ${ctn}${o.ksr ? " · " + o.ksr : ""}`;
      sub = o.k === "act" && o.l !== 4 ? o.t || "" : "";
      html += o.l === 4 ? kvSections(i) : kActSections(i);
    }
    return { eyebrow, h2, sub, html };
  }
  const chain = [];
  let j = P[i];
  while (j >= 0 && j !== ROOT) { chain.unshift(pickL(node(j).num).replace(/:$/, "")); j = P[j]; }
  if (chain.length) eyebrow += " · " + chain.join(" · ");
  if (o.k === "bvart") {
    h2 = `${t.art} ${o.n} ${t.bv}`;
    sub = pickL(o.h);
    html += countBlock(o.dec || 0, t.citeArt, null, null);
    if (o.rep) html += `<p class="note"><span class="pill">${esc(t.repealed)}</span></p>`;
    const deps = dependents[i] || [];
    const kvs = kids[i].filter((c) => LV(c) === 4);
    if (kvs.length) html += `<section><h3><i class="sw tree"></i>${esc(t.lv4)} · ${num(kvs.length)}</h3><p class="note">${esc(t.kvBasisNote)}</p><ul class="list">${kvs.map((c) =>
      `<li><button class="k link" data-sel="${c}">${esc(label(c))}</button><span class="v">${num(NC[c])}</span><span class="d">${esc(title(c))}</span></li>`).join("")}</ul></section>`;
    html += deps.length ? dependentsSection(deps, t.restHeadArt) : kvs.length ? "" : `<p class="note">${esc(t.noRest)}</p>`;
    const bv = LAY.tree.root, ob = node(bv);
    html += `<section><button class="link" data-sel="${bv}" data-art="${esc(o.i.slice(3))}">${esc(t.toSkyline)}</button></section>`;
    if (ob.e) html += `<section><a class="link" href="${esc(ob.e + "/" + lang + "#" + o.i.slice(3))}" target="_blank" rel="noopener">${esc(t.official)} ↗</a></section>`;
  } else if (o.k === "abv" || o.k === "tgroup") {
    eyebrow = t.viewTree;
    html += `<p class="note">${esc(o.k === "abv" ? t.abvNote : o.i === "TREE:int" ? t.tgIntlNote : t.tgNoneNote)}</p>`;
    const ch = kids[i].slice().sort((a, b) => NC[b] - NC[a]);
    if (o.k === "abv") html += dependentsSection(dependents[i] || [], t.restHead);
    else html += `<section><ul class="list">${ch.slice(0, 60).map((c) => `<li><button class="k link" data-sel="${c}">${esc(label(c))}</button><span class="v">${num(NC[c])}</span><span class="d">${esc(title(c))}</span></li>`).join("")}</ul>${ch.length > 60 ? `<p class="note">+ ${num(ch.length - 60)}</p>` : ""}</section>`;
  } else {                             // title, chapter, section of the Constitution
    const arts = subtree(i).filter((a) => K[a] === "bvart");
    const rest = arts.reduce((s, a) => s + (dependents[a] || []).length, 0);
    html += `<section><div class="big"><b>${num(arts.length)}</b><span>${esc(t.bvArticles)}</span></div><p class="note">${esc(t.restInside(num(rest)))}</p></section>`;
    html += `<section><ul class="list">${kids[i].map((c) => `<li><button class="k link" data-sel="${c}">${esc(K[c] === "bvart" ? `${label(c)} · ${pickL(node(c).h)}` : label(c))}</button><span class="v">${K[c] === "bvart" ? num((dependents[c] || []).length) : ""}</span></li>`).join("")}</ul></section>`;
  }
  return { eyebrow, h2, sub, html };
}
function refreshPanel() {
  if (sel.i < 0 || $("panel").hidden) return;
  const i = sel.i, o = node(i), hue = HK[i];
  if (i >= NCORE) {
    const p = treePanel(i);
    $("phead").innerHTML = `<p class="eyebrow">${esc(p.eyebrow)}</p><h2>${esc(p.h2)}</h2>${p.sub ? `<p class="sub">${esc(p.sub)}</p>` : ""}`;
    $("pbody").innerHTML = p.html; $("pbody").scrollTop = 0; crumbs();
    return;
  }
  const head = $("phead"), body = $("pbody");
  let eyebrow = "", h2 = "", sub = "", html = "";
  const tt = title(i), tl = titleLang(i), rec = actRec(i);
  if (sel.art) {
    const a = artPos(i, sel.art);
    const actName = label(i);
    eyebrow = o.sr ? `${t.sr} ${o.sr}` : actName;
    if (!a) { head.innerHTML = `<p class="eyebrow">${esc(eyebrow)}</p><h2>${esc(t.loading)}</h2>`; body.innerHTML = ""; return; }
    const ex = a[6] || {};
    h2 = `${t.art} ${a[1]} ${actName}`;
    sub = ex.h ? (ex.h[lang] || ex.h.de || ex.h.fr || ex.h.it) : "";
    const levels = rec.levels || [], chain = [];
    let li = ex.l;
    while (li !== undefined && li >= 0 && levels[li]) { chain.unshift(levels[li]); li = levels[li][1]; }
    const path = chain.map((lv) => [lv[2][lang] || lv[2].de || "", lv[3][lang] || lv[3].de || lv[3].fr || ""].join(" ").trim()).filter(Boolean);
    html += countBlock(a[5], t.citeArt, null, { ys: ex.ys, y0: ex.y0 });
    if (ex.rep) html += `<p class="note"><span class="pill">${esc(t.repealed)}</span></p>`;
    if (path.length) html += `<section><h3>${esc(t.path)}</h3><ul class="list">${path.map((p) => `<li><span class="k">${esc(p)}</span></li>`).join("")}</ul></section>`;
    if (ex.ys) html += `<section><h3>${esc(t.perYear)}</h3>${spark(ex.y0, ex.ys, hue)}</section>`;
    if (ex.top && ex.top.length) html += `<section><h3>${esc(t.topDecArt)}</h3>${decList(i, ex.top)}</section>`;
    if (ex.e && ex.e.length) {
      html += `<section><h3><i class="sw current"></i>${esc(t.coArts)}</h3><ul class="list">${ex.e.map((e) => {
        const j = idIndex.get(e[0]);
        const lab = j !== undefined ? label(j) : e[0];
        const an = e[1].replace(/^.*art_/, "").replace(/_/g, "");
        return `<li><button class="k link" data-sel="${j}" data-art="${esc(e[1])}">${esc(t.art)} ${esc(an)} ${esc(lab)}</button><span class="v">${esc(t.together(num(e[4]), e[5]))}</span></li>`;
      }).join("")}</ul><p class="note">${esc(t.coNote)}</p></section>`;
    }
    if (ex.x && ex.x.length) {
      html += `<section><h3><i class="sw wire"></i>${esc(t.artRefersTo)}</h3><ul class="list">${ex.x.slice().sort((p, q) => NC[q] - NC[p]).map((j) =>
        `<li><button class="k link" data-sel="${j}">${esc(label(j))}</button><span class="d">${esc(title(j))}</span></li>`).join("")}</ul></section>`;
    }
    if (o.e) {
      const anchor = /^(art_|disp_)/.test(sel.art) && !o.reg ? `/${lang}#${sel.art.replace(/\//g, "_")}` : "";
      html += `<section><a class="link" href="${esc(o.e + anchor)}" target="_blank" rel="noopener">${esc(t.official)} ↗</a></section>`;
    }
  } else if (o.k === "act") {
    eyebrow = o.c ? `${t.cantonalAct} · ${cantonName(o.c)}${TN[i] && TN[i].ksr ? " · " + TN[i].ksr : ""}` : `${t.sr} ${o.sr}${o.reg ? (o.reg === "a" ? " · " + t.edition : " · " + t.earlier) : ""}`;
    h2 = label(i);
    sub = tt + (tl ? ` [${tl.toUpperCase()}]` : "");
    const tn = TN[i] && TN[i].dn ? TN[i] : null;     // a cantonal act cited under two codes (CPJA = VRG)
    html += countBlock(tn ? tn.dn : o.n, t.citeAct, tn ? null : o, null);
    if (tn) html += `<p class="note">${esc(t.alsoCited(label(i), num(o.n), TN[i].al.map(([c, n]) => `${c} (${num(n)})`).join(", ")))}</p>`;
    if (o.c && !tt) html += `<p class="note">${esc(TN[i] && TN[i].cited ? t.kg_citedNote : t.cantonalNoTitle)}</p>`;
    if (o.from || o.to) html += `<dl class="facts"><dt>${esc(t.inForce)}</dt><dd class="mono">${esc(o.from || "")} – ${esc(o.to || "")}</dd></dl>`;
    if (o.reg && o.reg !== "a") {
      const j = idIndex.get("SR " + o.sr);
      if (j !== undefined) html += `<p class="note">${esc(t.successor)}: <button class="link" data-sel="${j}">${esc(label(j))}</button></p>`;
    }
    if (mode === "tree") html += basisSections(i);
    if (o.ys) html += `<section><h3>${esc(t.perYear)}</h3>${spark(o.y0, o.ys, hue)}</section>`;
    html += interdependencies(i);
    if (mode !== "tree") html += basisSections(i);
    if (rec && rec.arts) {
      const top = rec.arts.filter((a) => a[5]).sort((a, b) => b[5] - a[5]).slice(0, 10);
      const max = top.length ? top[0][5] : 1;
      html += `<section><h3>${esc(t.topArts)}</h3><p class="note">${esc(t.articlesIn(num(rec.arts.length)))}</p><ul class="list">${top.map((a) => {
        const h = a[6] && a[6].h ? (a[6].h[lang] || a[6].h.de || "") : "";
        return `<li><button class="k link" data-sel="${i}" data-art="${esc(a[0])}">${esc(t.art)} ${esc(a[1])}${h ? " · " + esc(h) : ""}</button><span class="v">${num(a[5])}</span><span class="bar"><i style="width:${(100 * a[5] / max).toFixed(1)}%"></i></span></li>`;
      }).join("")}</ul></section>`;
    } else if (PK[i] >= 0 && !rec) html += `<p class="note">${esc(t.loading)}</p>`;
    else if (!o.c) html += `<p class="note">${esc(t.noArticles)}</p>`;
    if (rec && rec.top && rec.top.length) html += `<section><h3>${esc(t.topDec)}</h3>${decList(i, rec.top)}</section>`;
    if (o.nf) {
      html += `<section><h3>${esc(t.notFound)}</h3><p class="note">${esc(t.nfNote(num(o.nf), num(o.nfd)))}</p>`;
      if (rec && rec.nf && rec.nf.length) html += `<p class="note mono">${rec.nf.slice(0, 20).map(([a, n]) => `${esc(t.art)} ${esc(a)} (${num(n)})`).join(" · ")}</p>`;
      html += "</section>";
    }
    if (o.nt) html += `<p class="note">${esc(t.noText(num(o.nt)))}</p>`;
    if (o.c && TN[i] && kUrl(i)) html += `<section><a class="link" href="${esc(kUrl(i))}" target="_blank" rel="noopener">${esc(t.cantonalColl(cantonName(o.c)))} ↗</a></section>`;
    else if (o.e) html += `<section><a class="link" href="${esc(o.e + (o.c ? "" : "/" + lang))}" target="_blank" rel="noopener">${esc(o.c ? t.cantonal : t.official)} ↗</a></section>`;
  } else if (o.k === "bucket") {
    const p = node(P[i]);
    eyebrow = t.cantonalAct; h2 = t.bucket;
    html += countBlock(o.n, t.citeAct, null, null);
    html += `<p class="note">${esc(t.bucketNote(num(o.codes), CANTON[p.c] ? CANTON[p.c][LANGS.indexOf(lang)] : p.c))}</p>`;
  } else {
    eyebrow = o.k === "area" ? `${t.sr} ${o.sr}` : o.k === "group" ? `${t.sr} ${o.sr} · ${t.group}` : o.k === "canton" ? t.KT : t.root;
    h2 = label(i);
    sub = tl ? `[${tl.toUpperCase()}]` : "";
    html += countBlock(o.n, t.citeArea, null, null);
    const ch = kids[i].slice().sort((a, b) => NC[b] - NC[a]).slice(0, 14);
    const max = ch.length ? Math.max(NC[ch[0]], 1) : 1;
    html += `<section><h3>${esc(t.children)}</h3><ul class="list">${ch.map((j) => {
      const oj = node(j);
      const name = oj.k === "act" ? `${label(j)}${title(j) ? " · " + title(j) : ""}` : (oj.sr ? oj.sr + " " : "") + label(j);
      return `<li><button class="k link" data-sel="${j}">${esc(name)}</button><span class="v">${num(NC[j])}</span><span class="bar"><i style="width:${(100 * NC[j] / max).toFixed(1)}%"></i></span></li>`;
    }).join("")}</ul></section>`;
  }
  head.innerHTML = `<p class="eyebrow">${esc(eyebrow)}</p><h2>${esc(h2)}</h2>${sub ? `<p class="sub">${esc(sub)}</p>` : ""}`;
  body.innerHTML = html;
  body.scrollTop = 0;
  crumbs();
}
// pointing at an act in the panel lights its link in the scene
$("pbody").addEventListener("pointerover", (e) => {
  const b = e.target.closest("[data-sel]");
  const j = b && !b.dataset.art ? +b.dataset.sel : -1;
  if (j === hoverLink || j === sel.i) return;
  hoverLink = j; hover = { i: j, art: null };
  edgesDirty = true; refreshHover();
});
$("pbody").addEventListener("pointerleave", () => {
  if (hoverLink < 0) return;
  hoverLink = -1; hover = { i: -1, art: null };
  edgesDirty = true; refreshHover();
});
$("pbody").addEventListener("click", (e) => {
  const b = e.target.closest("[data-sel]");
  if (!b) return;
  const j = +b.dataset.sel;
  if (Number.isFinite(j) && j >= 0) select(j, b.dataset.art || null);
});
$("close").onclick = () => select(-1);

// ---------- hash ----------
function writeHash() {
  let h = "";
  if (sel.i >= 0) {
    const id = ids[sel.i], km = id.match(/^(K|KV|KG):(.*)$/);
    // cantonal ids keep every character: "_" escapes ("K:GL:VIII B/21/5/1" -> "K.GL_cVIII_sB_l21_l5_l1")
    h = km ? km[1] + "." + km[2].replace(/_/g, "_u").replace(/ /g, "_s").replace(/\//g, "_l").replace(/:/g, "_c").replace(/[^A-Za-z0-9._~-]/g, (c) => "_x" + c.charCodeAt(0).toString(16) + "_")
      : id.replace(/ /g, "_").replace(/@/g, "~").replace(/\*/g, "x").replace(/^(BV|TREE):/, "$1.").replace(/\//g, "~~");
    if (sel.art) h += "--" + sel.art.replace(/\//g, "~");
  }
  try { history.replaceState(null, "", h ? "#" + h : location.pathname + location.search); } catch (e) { /* sandboxed */ }
}
function decodeHash() {
  const h = decodeURIComponent((location.hash || "").slice(1));
  if (!h) return null;
  const [nd, art] = h.split("--");
  const km = nd.match(/^(K|KV|KG)\.(.*)$/);
  const id = km ? km[1] + ":" + km[2].replace(/_x([0-9a-f]+)_/g, (m, c) => String.fromCharCode(parseInt(c, 16))).replace(/_c/g, ":").replace(/_l/g, "/").replace(/_s/g, " ").replace(/_u/g, "_")
    : /^(BV|TREE)\./.test(nd) ? nd.replace(/^(BV|TREE)\./, "$1:").replace(/~~/g, "/") : nd.replace(/_/g, " ").replace(/~/g, "@").replace(/ x$/, " *");
  const i = idIndex.get(id);
  return i === undefined ? null : { i, art: art ? art.replace(/~/g, "/") : null };
}

// ---------- search ----------
const DIACRITICS = new RegExp("[" + String.fromCharCode(0x300) + "-" + String.fromCharCode(0x36f) + "]", "g");
const norm = (s) => s.normalize("NFD").replace(DIACRITICS, "").replace(/[.\s\-_/]+/g, "").toUpperCase();
const fold = (s) => s.normalize("NFD").replace(DIACRITICS, "").toLowerCase();
let results = [], cursor = 0;
let topics = null, topicsLang = null, topicsLoading = null;
function ensureTopics() {
  if ((topics && topicsLang === lang) || topicsLoading) return;
  const l = lang;
  topicsLoading = getJSON(`data/topics.${l}.json`).then((d) => {
    topics = d.map(([i, art, text, n, parent]) => [i, art, text, n, fold(text).split(/[^a-z0-9]+/).filter(Boolean), parent]);
    topicsLang = l; topicsLoading = null;
    if ($("search").value.trim()) showResults();
  }).catch(() => { topicsLoading = null; });
}
function topicMatches(q) {
  if (!topics || topicsLang !== lang) return [];
  const words = fold(q).split(/[^a-z0-9]+/).filter((w) => w.length >= 3);
  if (!words.length) return [];
  const hasWord = (tp, w) => tp[4].some((tok) => tok.startsWith(w));
  const run = (ws) => {
    const out = [];
    for (const tp of topics) {
      let own = 0, ok = true;
      for (const w of ws) {
        if (hasWord(tp, w)) { own++; continue; }
        let p = tp[5], found = false;
        while (p >= 0 && !found) { found = hasWord(topics[p], w); p = topics[p][5]; }
        if (!found) { ok = false; break; }
      }
      if (ok && own) out.push({ i: tp[0], art: tp[1], topic: tp[2], n: tp[3], score: 120 + own * 30 + Math.log10(tp[3] + 1) * 25 });
    }
    return out;
  };
  let out = run(words);
  if (!out.length) out = run(words.map((w) => (w.length > 5 ? w.slice(0, 4) : w)));
  out.sort((a, b) => b.score - a.score);
  return out.slice(0, 8);
}
function search(q) {
  q = q.trim();
  const out = [];
  if (!q) return out;
  const m = q.match(/^(?:art(?:\.|icle|ikel|icolo)?\s*)?(\d+\s*[a-z]{0,9})\s+(?:al\.?\s*\d+\s*|abs\.?\s*\d+\s*|cpv\.?\s*\d+\s*)?([\p{L}][\p{L}\d.\s/-]*)$/iu)
    || q.match(/^([\p{L}][\p{L}\d./-]*)\s+(?:art\.?\s*)?(\d+\s*[a-z]{0,9})$/iu);
  if (m) {
    let artNum = m[1], code = m[2];
    if (/^\d/.test(m[2])) { artNum = m[2]; code = m[1]; }
    const j = core.alias[norm(code)];
    if (j !== undefined) out.push({ i: j, artNum: artNum.replace(/\s+/g, "").toLowerCase(), score: 1000 });
  }
  const nq = norm(q), lq = q.toLowerCase();
  const words = lq.split(/\s+/).filter((w) => w.length > 1);
  // "ZH PBG" / "PBG ZH": an abbreviation inside one canton
  const cq = q.match(/^([A-Za-z]{2})\s+(.+)$/) || q.match(/^(.+?)\s+([A-Za-z]{2})$/);
  const qct = cq ? (CANTON[cq[1].toUpperCase()] ? cq[1].toUpperCase() : CANTON[cq[2].toUpperCase()] ? cq[2].toUpperCase() : null) : null;
  const rest = qct ? norm(cq[1].toUpperCase() === qct ? cq[2] : cq[1]) : nq;
  const restWords = qct ? (cq[1].toUpperCase() === qct ? cq[2] : cq[1]).toLowerCase().split(/\s+/).filter((w) => w.length > 1) : words;
  const ali = core.alias[nq];
  if (ali !== undefined) out.push({ i: ali, score: 900 });
  for (let i = 1; i < NCORE; i++) {
    const o = core.nodes[i];
    if (o.k === "bucket") continue;
    let s = 0;
    if (o.sr && (o.sr === q || (q.length >= 2 && /^[\d.]+$/.test(q) && o.sr.startsWith(q)))) s = o.sr === q ? 800 : 300 - o.sr.length;
    if (o.a) for (const v of Object.values(o.a)) {
      const nv = norm(v);
      if (nv === nq || (qct && o.c === qct && nv === rest)) s = Math.max(s, 850); else if (nq.length >= 2 && nv.startsWith(nq)) s = Math.max(s, 400);
    }
    if (!s && words.length) {
      const tt = (title(i) || "").toLowerCase();
      if (tt && words.every((w) => tt.includes(w))) s = 200 - Math.min(tt.length / 4, 60);
      else if (o.k === "canton" && label(i).toLowerCase().startsWith(lq)) s = 600;
    }
    if (s) out.push({ i, score: s + Math.log10(NC[i] + 1) * 12 });
  }
  // cantonal acts of the official collections: abbreviation ("PBG", "ZH PBG", "PBG ZH"), number, title words
  if (tree && (rest.length >= 2 || restWords.length)) for (let i = NCORE; i < N; i++) {
    const o = XN[i - NCORE];
    if (!o.ct || (o.k !== "act" && o.k !== "kvart") || (qct && o.ct !== qct)) continue;
    let s = 0;
    if (o.ab) for (const a of o.ab.split(/\s*,\s*/)) { const na = norm(a); if (na === rest) s = Math.max(s, qct ? 820 : 640); }
    if (!s && o.ksr && (o.ksr === q || norm(o.ksr) === rest)) s = 600;
    if (!s && restWords.length && o.t) { const tt = fold(o.t); if (restWords.every((w) => tt.includes(fold(w)))) s = 180 - Math.min(o.t.length / 4, 60) + (qct ? 120 : 0); }
    if (s) out.push({ i, score: s - LV(i) });
  }
  ensureTopics();
  if (!m) out.push(...topicMatches(q));
  out.sort((a, b) => b.score - a.score);
  const seen = new Set();
  return out.filter((r) => { const key = r.i + "|" + (r.artNum || r.art || ""); if (seen.has(key)) return false; seen.add(key); return true; }).slice(0, 12);
}
function showResults() {
  const box = $("results"), q = $("search").value;
  results = search(q);
  cursor = 0;
  if (!q.trim()) { box.hidden = true; return; }
  box.hidden = false;
  if (!results.length) { box.innerHTML = `<div class="empty">${esc(t.none)}</div>`; return; }
  box.innerHTML = results.map((r, n) => {
    const o = node(r.i);
    const head = r.topic || (r.artNum ? `${t.art} ${r.artNum} ${label(r.i)}` : (o.k === "area" ? `${o.sr} ${label(r.i)}` : label(r.i)));
    const subl = r.topic ? `${label(r.i)} · ${title(r.i)}`
      : o.k === "act" ? [o.sr ? `${t.sr} ${o.sr}` : o.ct ? `${o.ct} ${o.ksr || ""}`.trim() : (o.c || ""), title(r.i)].filter(Boolean).join(" · ") : (o.k === "area" || o.k === "group" ? t.area : "");
    return `<button role="option" aria-selected="${n === 0}" data-n="${n}"><span class="t">${esc(head)}</span><span class="s">${esc(subl)}</span><span class="n">${r.artNum ? "" : num(r.topic ? r.n : NC[r.i])}</span></button>`;
  }).join("");
}
function choose(n) {
  const r = results[n];
  if (!r) return;
  $("results").hidden = true;
  $("search").blur();
  if (r.art) { select(r.i, r.art); return; }
  if (r.artNum && mode === "tree" && LAY.tree && r.i === LAY.tree.root) {      // "Art. 122 BV": the article in the tree
    const m = r.artNum.match(/^(\d+)([a-z]?)(bis|ter|quater|quinquies|sexies|septies|octies|novies|decies)?$/);
    const j = m ? idIndex.get("BV:art_" + [m[1], m[2], m[3]].filter(Boolean).join("_")) : undefined;
    if (j !== undefined) { select(j); return; }
  }
  if (r.artNum && PK[r.i] >= 0) {
    ensurePack(PK[r.i])?.then(() => {
      const rec = actRec(r.i);
      const a = rec && rec.arts && (rec.arts.find((x) => x[1] === r.artNum) || rec.arts.find((x) => x[1].split("–")[0] === r.artNum) || rec.arts.find((x) => x[0] === "art_" + r.artNum));
      select(r.i, a ? a[0] : null);
    });
  } else select(r.i);
}
$("search").addEventListener("input", showResults);
$("search").addEventListener("keydown", (e) => {
  const opts = [...$("results").querySelectorAll("button")];
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    if (!opts.length) return;
    cursor = (cursor + (e.key === "ArrowDown" ? 1 : -1) + opts.length) % opts.length;
    opts.forEach((b, n) => b.setAttribute("aria-selected", n === cursor));
    opts[cursor].scrollIntoView({ block: "nearest" });
  } else if (e.key === "Enter") { e.preventDefault(); choose(cursor); }
  else if (e.key === "Escape") { $("results").hidden = true; $("search").blur(); }
});
$("results").addEventListener("click", (e) => { const b = e.target.closest("button[data-n]"); if (b) choose(+b.dataset.n); });

// ---------- tools, layers, period, language ----------
$("zin").onclick = () => zoomBy(0.55);
$("zout").onclick = () => zoomBy(1.8);
function zoomBy(f) { const w = worldTarget(); const sph = new THREE.Spherical().setFromVector3(camera.position.clone().sub(controls.target)); flyTo(w.x, w.z, viewDist() * f, sph.phi); }
$("home").onclick = goHome;
// views: from above (the SR as a map) → tilted → from the side (case law above, legislation below)
const VIEWS = [0.02, 0.85, 1.36];
function nextView(phi) { const k = VIEWS.findIndex((v) => phi < v + 0.2); return VIEWS[(k < 0 ? 0 : k + 1) % VIEWS.length]; }
function tiltLabel() {
  const phi = new THREE.Spherical().setFromVector3(camera.position.clone().sub(controls.target)).phi;
  const n = nextView(phi);
  return n === VIEWS[0] ? t.viewTop : n === VIEWS[1] ? t.view3d : t.viewSide;
}
$("tilt").onclick = () => {
  const sph = new THREE.Spherical().setFromVector3(camera.position.clone().sub(controls.target));
  const w = worldTarget();
  flyTo(w.x, w.z, viewDist(), nextView(sph.phi), true, controls.target.y);
  setTimeout(() => { $("tilt").textContent = tiltLabel(); }, 2500);
};
$("theme").onclick = () => {
  theme = theme === "light" ? "dark" : "light";
  try { localStorage.setItem("slm-theme", theme); } catch (e) { /* storage unavailable */ }
  applyTheme(); buildLegend(); refreshPanel(); updateLabels(); relayoutWeb();
};
$("mtree").onclick = () => setMode("tree");
$("msr").onclick = () => setMode("sr");
$("lwire").onclick = () => { showWire = !showWire; $("lwire").setAttribute("aria-pressed", showWire); edgesDirty = true; };
$("lall").onclick = () => { treeAll = !treeAll; $("lall").setAttribute("aria-pressed", treeAll); edgesDirty = true; };
$("lcurrent").onclick = () => { showCurrent = !showCurrent; $("lcurrent").setAttribute("aria-pressed", showCurrent); edgesDirty = true; };
$("periodbtn").onclick = () => {
  const box = $("period"), on = box.hidden;
  box.hidden = !on;
  $("periodbtn").setAttribute("aria-pressed", on);
  $("y1").min = mode === "tree" ? 1800 : 1875;
  setGrowthUI();
  if (on && mode === "tree") { select(-1, null, false); home(); }   // the growth reads from the whole tree
  if (on) setPeriod(); else { period = null; growthYear = null; if (mode === "tree") setFocus(null); refreshStates(); refreshPanel(); }
};
for (const id of ["y0", "y1"]) $(id).addEventListener("input", setPeriod);
function setPeriod() {
  if (mode === "tree") { const y = +$("y1").value; $("o1").value = y; setGrowth(y); return; }
  if (!edgeYears) getJSON("data/ey.json").then((d) => { edgeYears = d; edgesDirty = true; }).catch(() => {});
  let a = +$("y0").value, b = +$("y1").value;
  if (a > b) [a, b] = [b, a];
  $("o0").value = a; $("o1").value = b;
  period = [a, b];
  refreshStates(); refreshPanel();
}
let playing = null;
$("play").onclick = () => {
  if (playing) { cancelAnimationFrame(playing); playing = null; $("play").textContent = t.play; return; }
  if ($("period").hidden) $("periodbtn").click();
  $("play").textContent = t.pause;
  let y = mode === "tree" ? 1848 : 1880, last = 0;
  const step = (now) => {
    if (now - last > (mode === "tree" ? 110 : 140)) {
      last = now;
      if (mode !== "tree") $("y0").value = Math.max(1875, y - 9);
      $("y1").value = y;
      setPeriod();
      y++;
      if (y > 2026) { playing = null; $("play").textContent = t.play; return; }
    }
    playing = requestAnimationFrame(step);
  };
  playing = requestAnimationFrame(step);
};
$("lang").addEventListener("change", async (e) => {
  lang = e.target.value; t = T[lang]; fmt = new Intl.NumberFormat(lang + "-CH");
  try { localStorage.setItem("slm-lang", lang); } catch (err) { /* storage unavailable */ }
  titles = await getJSON(`data/titles.${lang}.json`);
  topics = null;
  applyLang(); buildLegend(); refreshPanel(); crumbs(); updateLabels();
  if ($("search").value) showResults();
});
function applyLang() {
  document.documentElement.lang = lang;
  $("lang").value = lang;
  $("brandname").textContent = t.name;
  $("search").placeholder = t.search;
  $("home").textContent = t.home; $("periodbtn").textContent = t.time; $("methodbtn").textContent = t.method;
  $("webbtn").textContent = t.webBtn; $("webbtn").title = t.webHint; $("webbtn").setAttribute("aria-pressed", webOn);
  if (web) { web.G = webGroups(web.i, !(story && story.tr)); relayoutWeb(); }
  $("tilt").textContent = core ? tiltLabel() : t.view3d; $("play").textContent = playing ? t.pause : t.play;
  $("l-from").textContent = t.from; $("l-to").textContent = t.to; $("periodnote").textContent = t.periodNote;
  $("introtext").textContent = mode === "tree" ? t.introTree : t.intro; $("introok").textContent = t.introOk; $("introtitle").textContent = t.name;
  $("mtree").textContent = t.viewTree; $("msr").textContent = t.viewSR;
  $("tourbtn").textContent = t.tours; $("tourbtn").hidden = !LAY.tree;
  $("focusbtn").title = t.focusMode; $("focusbtn").setAttribute("aria-label", t.focusMode);
  $("opening").querySelector(".op-skip").textContent = t.opSkip;
  if (core) { setGrowthUI(); renderSpine(); }
  $("mtree").setAttribute("aria-pressed", mode === "tree"); $("msr").setAttribute("aria-pressed", mode === "sr");
  $("mtree").hidden = $("msr").hidden = !LAY.tree;
  $("ltree").hidden = mode !== "tree";
  $("lall").hidden = mode !== "tree"; $("lalltext").textContent = t.treeAll;
  $("ltreetext").textContent = t.basisLink;
  $("ik1").textContent = t.lawWiring; $("ik2").textContent = t.practice; $("ik3").textContent = t.bothShort;
  $("layershead").textContent = t.layers;
  $("lwiren").textContent = core.xedges && core.xedges.length ? num(core.xedges.length) : "";
  $("lcurrentn").textContent = num(core.edges.length);
  $("lwire").querySelector("span").textContent = t.lawWiring;
  $("lcurrent").querySelector("span").textContent = t.practice;
  $("lwire").title = t.lawWiringNote; $("lcurrent").title = t.practiceNote;
  $("lboth").textContent = t.both;
}
function buildLegend() {               // colour = SR area in both views; in the tree the areas are not places
  const el = $("legend");
  const ch = idIndex.get("CH"), srk = LAY.sr.kids;
  const items = srk[ch].map((j) => [j, HK[j], label(j)]);
  items.push([idIndex.get("KT"), "k", t.KT]);
  if (mode === "tree") items.unshift([-1, "bv", t.bvFull]);
  el.innerHTML = items.map(([j, h, l]) => `<button data-sel="${j}" data-hue="${h}" title="${esc(mode === "tree" ? t.lensHint : l)}" aria-pressed="${lens === h}"${mode === "tree" && h === "bv" ? " disabled" : ""}><i style="background: ${cssHue(h)}"></i><span>${esc(j >= 0 && core.nodes[j].sr ? core.nodes[j].sr + " " : "")}${esc(l)}</span></button>`).join("");
  el.onclick = (e) => {
    const b = e.target.closest("[data-sel]");
    if (!b) return;
    if (mode === "sr") select(+b.dataset.sel);
    else if (b.dataset.hue !== "bv") { select(-1, null, false); setLens(b.dataset.hue); }   // a lens: that area across all floors
  };
}

// ---------- intro ----------
function seenIntro() { try { return localStorage.getItem("slm-intro") === "1"; } catch (e) { return false; } }
function closeIntro() { $("intro").hidden = true; try { localStorage.setItem("slm-intro", "1"); } catch (e) { /* storage unavailable */ } }
$("introok").onclick = closeIntro;

// ---------- method ----------
async function openMethod() {
  const { methodHTML } = await import("./method.js");
  $("mbox").innerHTML = methodHTML(core.method, lang, t, num, esc, tree ? tree.method : null);
  $("method").hidden = false;
  $("mclose").onclick = closeMethod;
  $("mclose").focus();
}
function closeMethod() { $("method").hidden = true; $("methodbtn").focus(); }
$("methodbtn").onclick = openMethod;
$("method").addEventListener("click", (e) => { if (e.target.id === "method") closeMethod(); });

window.__slm = { select, pick, home, setMode, get mode() { return mode; }, updateLabels, rebuild: () => { buildEdges(); return buildMs; }, idx: (id) => idIndex.get(id), get dbg() { return { buildMs, lines: lastEntries.length, dotsAct, p: dots ? actRec(dotsAct).p : null, pxu: pxPerUnitAt(viewDist()), R: R[sel.i], pool: pool.length, fade: artFade, W, H }; }, get state() { return { sel, origin: origin.toArray(), dist: viewDist() }; }, get entries() { return lastEntries.map(([k, w]) => { const [a, b, l] = k.split("|").map(Number); return [ids[a], ids[b], l, w, Math.round(projectedPx(a)), Math.round(projectedPx(b))]; }); }, get meshes() { return { wires, current, focusRibbons, orbs, rings, camera, controls, scene, treeLines, courtOrbs, courtLines }; } };
// ---------- immersion: opening, tours, descent, spine, scale, lenses, growth, courts ----------
// Martini glass (Segel & Heer 2010): a short authored opening and guided tours, then free
// exploration. Every number a tour or the opening shows is computed here from the data.
let TMAP = [], focusSet = null, story = null, lens = null, growthYear = null, lastInput = performance.now();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const gi = (k) => TMAP[k];                                  // tree index -> global index
const setFocus = (s) => { focusSet = s; refreshStates(); treeDirty = true; };
const floorNodes = (pred) => { const s = new Set(); for (const i of orbIndex) if (pred(LV(i), i)) s.add(i); return s; };
const isCant = (i) => !!(TN[i] && TN[i].ct);
function facts() {                                          // the numbers the opening and tours show
  if (facts.v) return facts.v;
  const L = LAY.tree, by = tree.method.by_level, arts = orbIndex.filter((i) => K[i] === "bvart");
  const par = (l) => { const c = { bv: 0, l1: 0, l2: 0, none: 0, other: 0 };   // where the acts of a floor hang
    for (const i of orbIndex) if (LV(i) === l && !/^SR 0\./.test(ids[i] || "")) {   // treaties stand on floor 1 only as bases
      const p = L.P[i];
      if (K[p] === "bvart" || p === L.root) c.bv++; else if (/^SR 0\./.test(ids[p] || "")) c.other++;
      else if (LV(p) === 1) c.l1++; else if (LV(p) === 2) c.l2++;
      else if (ids[p] === "TREE:none") c.none++; else c.other++;            // treaties, BV 1874, same floor
    }
    return c; };
  facts.v = { fed: tree.method.acts, kant: tree.method.cantonal_acts, dec: core.nodes[0].n, arts: arts.length,
    artsBasis: arts.filter((i) => (dependents[i] || []).length).length, artsRest: arts.reduce((s, i) => s + (dependents[i] || []).length, 0),
    l1: by["1"], l2: by["2"], l3: by["3"], p1: par(1), p2: par(2), p3: par(3) };
  return facts.v;
}

// --- the narration card
function card(eyebrow, head, body, nav) {
  const el = $("story");
  el.innerHTML = `<p class="eyebrow">${esc(eyebrow)}</p><h3>${esc(head)}</h3><p class="body">${body}</p>${nav || ""}`;
  el.hidden = false;
  storyTop = el.getBoundingClientRect().top;
  relayoutWeb();
}
function navHtml(k, n) {
  const dots = Array.from({ length: n }, (_, j) => `<i class="${j === k ? "on" : ""}"></i>`).join("");
  return `<div class="nav"><span class="dots" aria-hidden="true">${dots}</span>
    <button class="chip" data-story="prev"${k ? "" : " disabled"}>← ${esc(t.back)}</button>
    <button class="chip strong" data-story="${k < n - 1 ? "next" : "end"}">${esc(k < n - 1 ? t.next : t.end)} ${k < n - 1 ? "→" : ""}</button>
    <button class="chip" data-story="close" aria-label="${esc(t.closeTour)}">×</button></div>`;
}
$("story").addEventListener("click", (e) => {
  const b = e.target.closest("[data-story]");
  if (b) { const a = b.dataset.story; if (a === "next") stepTour(1); else if (a === "prev") stepTour(-1); else endTour(a === "end"); return; }
  const s = e.target.closest("[data-sel]");
  if (s) { const j = +s.dataset.sel; endTour(false); select(j); }
});
const linkTo = (j, text) => `<button class="link" data-sel="${j}">${esc(text ?? label(j))}</button>`;

// --- tours
function startTour(id) {
  closeIntro(); $("opening").hidden = true; $("tourmenu").hidden = true;
  if (mode !== "tree") setMode("tree", false);
  lens = null; growthYear = null; setGrowthUI();
  story = { tr: tree.tours.find((x) => x.id === id), k: 0 };
  document.body.classList.add("touring");
  minFlight = 1700;
  showStop();
}
function stepTour(d) { if (!story || !story.tr) return; story.k = Math.max(0, Math.min(story.tr.stops.length - 1, story.k + d)); showStop(); }
function endTour(toExplore) {
  story = null; minFlight = 600; $("story").hidden = true; setFocus(null); hideCourts();
  document.body.classList.remove("touring"); storyTop = 0;
  if (toExplore && sel.i >= 0) select(sel.i);
}
function roleOf(i) {
  if (K[i] === "bvart") return t.role_bvart;
  const l = LV(i);
  return t["role" + (l === 4.5 ? 4 : l)] || "";
}
function nodeFacts(i) {
  const bits = [];
  const o = TN[i];
  if (K[i] === "bvart") {
    const h = pickL(node(i).h);
    bits.push(`<b>${esc(fullLabel(i))}${h ? " · " + esc(h) : ""}</b>`);
  } else {
    bits.push(`<b>${esc(fullLabel(i))}</b>${title(i) && title(i) !== label(i) ? " · " + esc(title(i)) : ""}`);
    const who = (t["lv" + o.l] || "").split(" · ")[1] || "";           // the floor = the enacting authority
    // federal: the Ingress names the issuer (o.by); cantonal: only the floor is in the tree (issuer or title)
    if (who) bits.push(o.ct ? `${esc(t.fFloor(who))} (${esc(cantonName(o.ct))})` : esc(o.by ? t.fBy(who) : t.fFloor(who)));
    const b = (basisOf[i] || []).find((x) => x.prim) || (basisOf[i] || []).find((x) => x.j >= 0);
    if (b && b.j >= 0) {
      const names = artNames(b.eids);
      bits.push(esc(t.fBasisPre) + " " + linkTo(b.j, (names.length && K[b.j] !== "bvart" && K[b.j] !== "kvart" ? `${t.art} ${names.slice(0, 4).join(", ")}${names.length > 4 ? " …" : ""} ` : "") + fullLabel(b.j)));
    }
    const nd = (o && o.dn) || NC[i];
    if (nd) bits.push(esc(t.fDec(num(nd))));
  }
  const nr = (dependents[i] || []).length;      // the apex: everything rests on it, the count would mislead
  if (nr && i !== ROOT) bits.push(esc(t.fRest(num(nr))));
  return bits.join(" · ");
}
async function showStop() {
  const { tr, k } = story, s = tr.stops[k], n = tr.stops.length, f = facts(), C = tree.method.C;
  const eyebrow = `${t.tour} · ${t["tour_" + tr.id]} · ${k + 1}/${n}`;
  hideCourts();
  if (s.k === "overview") {
    select(-1, null, false); setFocus(null);
    card(eyebrow, t.st_overviewH, esc(t.st_overview(num(f.fed), num(f.kant), num(f.dec))), navHtml(k, n));
    home();
  } else if (s.k === "apex") {
    select(-1, null, false);
    setFocus(floorNodes((l, i) => i === ROOT || ["title", "chapter", "section", "bvart"].includes(K[i])));
    const pl = tree.plates[0];
    card(eyebrow, t.st_apexH, esc(t.st_apex(num(f.arts), num(f.artsBasis), num(f.artsRest))), navHtml(k, n));
    flyTo(0, 0, distanceToFit(pl[1] * 1.15), 0.7, true, pl[0], null, minFlight);   // the article ring, from above
  } else if (s.k === "floor") {
    select(-1, null, false);
    setFocus(floorNodes((l) => l === s.l));
    const pl = tree.plates[s.l];
    const p = f["p" + s.l];
    const body = s.l === 1 ? t.st_floor1(num(f.l1), num(p.bv), num(p.none)) : s.l === 2 ? t.st_floor2(num(f.l2), num(p.l1), num(p.bv)) : t.st_floor3(num(f.l3), num(p.l2), num(p.l1));
    card(eyebrow, t["role" + s.l], esc(body), navHtml(k, n));
    flyTo(0, 0, distanceToFit(pl[1] * 1.08), 0.9, true, pl[0], null, minFlight);
  } else if (s.k === "cantons") {
    select(-1, null, false);
    setFocus(floorNodes((l) => l >= 4));
    const pl = tree.plates[tree.plates.length - 1];
    card(eyebrow, t.st_cantonsH, esc(t.st_cantons(num(f.kant), (f.kant / f.fed).toFixed(1).replace(".", lang === "en" ? "." : ","))), navHtml(k, n));
    flyTo(0, 0, distanceToFit(pl[1] * 1.02), 0.78, true, tree.plates[5][0], null, minFlight);
  } else if (s.k === "courts" && s.top) {
    select(-1, null, false);
    const top = s.top.map(gi);
    setFocus(new Set(top));
    const list = top.map((j) => `${linkTo(j)} (${num(NC[j])})`).join(", ");
    card(eyebrow, t.role_courts, esc(t.st_courts(num(f.dec))) + " " + list + ".", navHtml(k, n));
    home();
  } else {                                     // a node of a thread, or the courts under one
    const i = gi(s.i);
    setFocus(null);
    select(i, null, true, true);
    if (s.k === "courts") {
      card(eyebrow, t.role_courts, esc(t.st_courtsAct(label(i), num((TN[i] && TN[i].dn) || NC[i]))) + ` <span class="muted">${esc(t.loading)}</span>`, navHtml(k, n));
      const rec = await courtsFor(i);
      if (!story || story.tr !== tr || story.k !== k) return;
      const top = rec && rec.top ? rec.top.slice(0, 3).map((did) => decInfo(i, did)).filter(Boolean) : [];
      card(eyebrow, t.role_courts, esc(t.st_courtsAct(label(i), num((TN[i] && TN[i].dn) || NC[i]))) +
        (top.length ? " " + esc(t.st_courtsTop) + " " + top.map((d) => `<b>${esc(d[0])}</b>`).join(", ") + "." : ""), navHtml(k, n));
    } else card(eyebrow, roleOf(i), nodeFacts(i), navHtml(k, n));
  }
}

// --- the opening: the floors light up one after the other while the numbers build up
async function opening() {
  if (!tree || mode !== "tree") return;
  const f = facts(), ov = $("opening"), C = tree.method.C;
  story = { opening: true };
  ov.hidden = false;
  const beats = [
    [t.op0, "", "", new Set()],
    [t.op1(num(f.arts)), t.op1s, "", floorNodes((l, i) => i === ROOT || ["title", "chapter", "section", "bvart"].includes(K[i]))],
    [t.op2(num(f.fed)), t.op2s, "", floorNodes((l, i) => (l >= 1 && l <= 3) || i === ROOT || K[i] === "bvart")],
    [t.op3, t.op3s, "", floorNodes((l, i) => l === 4 || l <= 3)],
    [t.op4(num(f.kant)), t.op4s, "", null],
    [t.op5(num(f.dec)), t.op5s, "", null],
  ];
  const [d0, ty0] = fitTree(W <= 760 ? 0.42 : 0.62, H * (W <= 760 ? 0.36 : 0.33));   // the top third holds the words
  flyTo(0, 0, d0 * 2.4, 0.25, false, ty0, 0.4);
  for (let b = 0; b < beats.length && story && story.opening; b++) {
    const [h, sub, , set] = beats[b];
    $("opening").querySelector(".op-num").textContent = h;
    $("opening").querySelector(".op-text").textContent = sub;
    $("opening").classList.remove("beat"); void ov.offsetWidth; $("opening").classList.add("beat");
    setFocus(set);
    if (b === 0) flyTo(0, 0, d0 * 1.45, 0.42, true, ty0, 0.9, 5200);
    if (b === 3) flyTo(0, 0, d0 * 1.1, 0.55, true, ty0, 1.6, 5200);
    await sleep(b === 0 ? 1800 : 3000);
  }
  if (!story || !story.opening) return;
  setFocus(null);
  flyTo(0, 0, d0, W <= 760 ? 0.42 : 0.62, true, ty0, null, 1800);
  $("opening").querySelector(".op-num").textContent = t.opAsk;
  $("opening").querySelector(".op-text").textContent = "";
  $("opening").querySelector(".op-actions").innerHTML = tree.tours.map((tr) => `<button class="chip strong" data-tour="${tr.id}">${esc(t["tour_" + tr.id])}</button>`).join("") +
    `<button class="chip" data-op="explore">${esc(t.opExplore)}</button>`;
  story = null;
}
function skipOpening() {
  if (story && story.opening) story = null;
  $("opening").hidden = true;
  $("opening").querySelector(".op-actions").innerHTML = "";
  setFocus(null);
  try { localStorage.setItem("slm-opening", "1"); } catch (e) { /* storage unavailable */ }
}
$("opening").addEventListener("click", (e) => {
  const b = e.target.closest("[data-tour]");
  if (b) { skipOpening(); startTour(b.dataset.tour); return; }
  if (e.target.closest("[data-op='explore'], .op-skip")) { skipOpening(); home(); }
});
function seenOpening() { try { return localStorage.getItem("slm-opening") === "1"; } catch (e) { return false; } }

// --- tour menu
$("tourbtn").onclick = () => {
  const m = $("tourmenu");
  m.innerHTML = `<p class="eyebrow">${esc(t.tours)}</p>` + tree.tours.map((tr) => `<button data-tour="${tr.id}"><b>${esc(t["tour_" + tr.id])}</b><span>${esc(t["tourSub_" + tr.id])}</span></button>`).join("") +
    `<button data-op="replay"><b>${esc(t.replay)}</b><span>${esc(t.replaySub)}</span></button>`;
  m.hidden = !m.hidden;
};
$("tourmenu").addEventListener("click", (e) => {
  const b = e.target.closest("[data-tour], [data-op]");
  if (!b) return;
  $("tourmenu").hidden = true;
  if (b.dataset.tour) startTour(b.dataset.tour);
  else { endTour(false); select(-1, null, false); if (mode !== "tree") setMode("tree", false); opening(); }
});

// --- descent: from the Constitution down the chain of delegation to the act
async function descend(i) {
  const chain = ancestorsOf(i).reverse().filter((j) => !["title", "chapter", "section"].includes(K[j]));
  story = { descent: true };
  minFlight = 1500;
  document.body.classList.add("touring");
  for (const j of chain) {
    if (!story || !story.descent) break;
    select(j, null, true, true);
    card(t.descend, roleOf(j) || t.lvBV, nodeFacts(j),
      `<div class="nav"><span class="dots"></span><button class="chip" data-story="close" aria-label="${esc(t.closeTour)}">×</button></div>`);
    await sleep(focusOn(j, true) + 1100);
  }
  const was = story && story.descent;
  story = null; minFlight = 600; $("story").hidden = true;
  document.body.classList.remove("touring"); storyTop = 0;
  if (was) select(i);
}

// --- spine: the chain of delegation of the selection, floor by floor (left, tree view)
function renderSpine() {
  const el = $("spine");
  if (mode !== "tree" || sel.i < 0 || W <= 760 || story) { el.hidden = true; return; }
  const chain = ancestorsOf(sel.i).reverse();
  const rows = [];
  let crown = [];
  for (const j of chain) {
    if (["title", "chapter", "section"].includes(K[j])) { crown.push(pickL(node(j).num).replace(/:$/, "")); continue; }
    const hue = K[j] === "act" || K[j] === "bvart" ? cssHue(HK[j]) : "var(--muted)";
    const sub = K[j] === "bvart" ? (crown.join(" › ") + (pickL(node(j).h) ? " · " + pickL(node(j).h) : "")) : roleOf(j);
    rows.push(`<button data-sel="${j}" class="${j === sel.i ? "on" : ""}"><i style="background:${hue}"></i><b>${esc(label(j))}</b><span>${esc(sub)}</span></button>`);
    crown = [];
  }
  el.innerHTML = `<p class="eyebrow">${esc(t.spineHead)}</p>${rows.join("")}<button class="chip" data-descend="${sel.i}">▼ ${esc(t.descend)}</button>`;
  el.hidden = false;
}
$("spine").addEventListener("click", (e) => {
  const d = e.target.closest("[data-descend]");
  if (d) { descend(+d.dataset.descend); return; }
  const b = e.target.closest("[data-sel]");
  if (b) select(+b.dataset.sel);
});

// --- scale: what is in view right now
function updateHud(visFed, visKant) {
  const el = $("hud");
  if (!core || (story && story.opening)) { el.hidden = true; return; }
  const f = tree ? facts() : null;
  let s = `<b>${esc(t.hudView)}</b> ${esc(t.hudFed(num(visFed)))} · ${esc(t.hudKant(num(visKant)))}`;
  if (growthYear) s += ` · <b>${esc(t.hudYear(growthYear))}</b>`;
  else if (f && visFed >= f.fed * 0.9 && visKant >= f.kant * 0.9) s += ` · ${esc(t.hudDec(num(f.dec)))}`;
  el.innerHTML = s;
  el.hidden = false;
}

// --- lenses: an SR area (legend) across the whole tree
function setLens(key) {
  lens = lens === key ? null : key;
  if (!lens) { setFocus(null); buildLegend(); return; }
  setFocus(floorNodes((l, i) => (lens === "k" ? isCant(i) : !isCant(i) && HK[i] === lens && K[i] === "act")));
  buildLegend();
  home();                                      // an area across all floors: seen from the overview
}

// --- growth: today's law by year of adoption (repealed acts are not in the data)
function setGrowthUI() {
  const on = mode === "tree" && !$("period").hidden;
  $("y0").closest("label").hidden = mode === "tree";
  $("periodnote").textContent = mode === "tree" ? t.growthNote : t.periodNote;
  if (!on) growthYear = null;
}
function setGrowth(y) {
  growthYear = y;
  const yy = String(y);
  setFocus(floorNodes((l, i) => {
    if (K[i] !== "act") return i === ROOT || ["title", "chapter", "section", "bvart", "kvart", "tgroup"].includes(K[i]);
    const ad = TN[i] && TN[i].ad;               // undated acts (133) appear with today's law only
    return ad ? ad.slice(0, 4) <= yy : y >= +$("y1").max;
  }));
}

// --- courts: the most-cited decisions referring to the selected act hang below it
let courtOrbs = null, courtLines = null, courtFor = -1, courtList = [];
async function courtsFor(i) {
  if (PK[i] < 0) return null;
  if (!actRec(i)) await ensurePack(PK[i]);
  const rec = actRec(i);
  if (!rec || !rec.top || sel.i !== i || mode !== "tree") return rec;
  courtFor = i; courtList = rec.top.slice(0, 10).map((did) => [did, decInfo(i, did)]).filter((x) => x[1]);
  writeCourts();
  return rec;
}
function hideCourts() { courtFor = -1; courtList = []; if (courtOrbs) { courtOrbs.geometry.instanceCount = 0; setRibbons(courtLines, []); } }
function writeCourts() {
  if (!courtOrbs) {
    courtOrbs = makeOrbs(12); courtLines = makeRibbons();
    scene.add(courtOrbs, courtLines);
  }
  const i = courtFor, n = courtList.length;
  if (i < 0 || !n) { hideCourts(); return; }
  // they hang within the act's own framing (focusOn), so act and decisions fit in one view
  const span = Math.max(R[i] * 5, (SPAN[i] || 0) * 0.55, tree.method.C * 0.015), drop = R[i] + span * 0.3, ring = Math.max(R[i] * 1.8, span * 0.2);
  const g = courtOrbs.geometry, cc = g.attributes.iCenter.array, rr = g.attributes.iRadius.array, col = g.attributes.iColor.array, st = g.attributes.iState.array;
  const maxC = Math.max(1, ...courtList.map((x) => x[1][2] || 0)), lines = [];
  courtList.forEach(([did, d], k) => {
    const a = (k / n) * Math.PI * 2;
    const x = X[i] + ring * Math.cos(a), z = Z[i] + ring * Math.sin(a), y = CY[i] - drop - (k % 2) * ring * 0.25;
    cc.set([x - origin.x, y - origin.y, z - origin.z], k * 3);
    rr[k] = Math.max(R[i] * 0.22, span * 0.012) * (0.7 + 1.1 * Math.sqrt((d[2] || 0) / maxC));
    col.set(HUE.court, k * 3);
    st.set([1, 0.35 + 0.65 * Math.sqrt((d[2] || 0) / maxC), 0, 0], k * 4);
    courtList[k][2] = [x, y, z, rr[k]];
    lines.push({ pts: flat([[X[i] - origin.x, CY[i] - origin.y, Z[i] - origin.z], [x - origin.x, y - origin.y, z - origin.z]]), width: 1.1, color: HUE.court, alpha: 0.55, flow: 0.5 });
  });
  g.instanceCount = n;
  for (const a of ["iCenter", "iRadius", "iColor", "iState"]) g.attributes[a].needsUpdate = true;
  setRibbons(courtLines, lines);
}

// ---------- the constellation: an act's connections, brought next to it ----------
// In the cone an act's partners sit far apart (other floors, other cantons, other SR areas): lines
// to them run off-screen to dots a few pixels wide. So they are brought to it ("bring & go",
// Moscovich et al., CHI 2009), in groups that keep the directions of the law: above, what it
// rests on; below, what rests on it; left, the acts its text names or that name it; right, the
// acts the courts cite with it and its most-cited decisions. Each partner flies in from where it
// really is; pointing at one shows that place, a click goes there.
let webOn = (() => { try { return localStorage.getItem("slm-web") !== "0"; } catch (e) { return true; } })();
let web = null, webReq = 0, bvArts = null;
const decOf = (j) => (TN[j] && TN[j].dn) || NC[j] || 0;
const WREL = { up: "basis", down: "basis", law: "wire", court: "current", dec: "court" };
const isBV = (i) => ids[i] === "SR 101";
const artList = (names) => (names.length ? `${t.art} ${names.slice(0, 3).join(", ")}${names.length > 3 ? " …" : ""}` : "");

function webGroups(i, withDec) {
  const g = { up: [], down: [], law: [], court: [], dec: [] }, n = {};
  const seen = new Set();
  for (const b of basisOf[i] || []) {                 // the bases its Ingress states; the first is its place
    if (b.j < 0 || seen.has(b.j)) continue;
    seen.add(b.j);
    g.up.push({ j: b.j, w: K[b.j] === "bvart" || K[b.j] === "kvart" ? "" : artList(artNames(b.eids || [])), dash: !b.prim, s: 1 });
  }
  n.up = g.up.length; n.upUnk = (basisOf[i] || []).filter((b) => b.j < 0).length;
  if (isBV(i) || (TN[i] && TN[i].l === 4)) {          // a constitution: the articles most acts rest on
    if (!bvArts) { bvArts = []; for (let k = NCORE; k < N; k++) if (K[k] === "bvart") bvArts.push(k); }
    const arts = isBV(i) ? bvArts : LAY.tree.kids[i].filter((k) => K[k] === "kvart");
    const list = arts.map((k) => [k, (dependents[k] || []).length]).filter((x) => x[1] > 0).sort((a, b) => b[1] - a[1] || a[0] - b[0]);
    g.down = list.map(([k, c]) => ({ j: k, w: t.webActs(num(c)), s: c }));
    n.down = list.length; n.apex = true;
  } else {
    const dd = new Map();
    for (const d of dependents[i] || []) if (!dd.has(d.i)) dd.set(d.i, d);
    const own = K[i] !== "bvart" && K[i] !== "kvart";   // an act: which of its articles they name
    g.down = [...dd.values()].sort((a, b) => decOf(b.i) - decOf(a.i) || a.i - b.i)
      .map((d) => ({ j: d.i, w: own ? artList(artNames(d.eids || [])) : "", dash: !d.prim, s: decOf(d.i) }));
    n.down = dd.size;
  }
  const lm = new Map();                               // legislation: provisions naming the other act
  for (const [j, c] of wOut[i]) lm.set(j, { j, o: c, n: 0 });
  for (const [j, c] of wIn[i]) { const x = lm.get(j) || { j, o: 0, n: 0 }; x.n = c; lm.set(j, x); }
  g.law = [...lm.values()].sort((a, b) => b.o + b.n - (a.o + a.n) || decOf(b.j) - decOf(a.j) || a.j - b.j)
    .map((x) => ({ j: x.j, w: [x.o ? "→ " + num(x.o) : "", x.n ? "← " + num(x.n) : ""].filter(Boolean).join("   "), s: x.o + x.n }));
  n.law = lm.size;
  g.court = jAdj[i].map(([j, c]) => ({ j, w: t.decN(num(c)), s: c }));
  n.court = jAdj[i].length;
  const rec = actRec(i);
  if (withDec && rec && rec.top) {
    g.dec = rec.top.map((did) => [did, decInfo(i, did)]).filter((x) => x[1]).map(([did, d]) => ({ j: -1, did, lab: d[0], w: t.citedBy(num(d[2])), s: d[2] }));
  }
  n.dec = g.dec.length;
  return { g, n, i };
}

// Where the act will stand (the centre of the free area) and the room around it.
function webBox() {
  const fr = freeRect(), phone = W <= 760;
  const x0 = Math.max(fr.cx - fr.w / 2 + (phone ? 8 : 26), 8), x1 = Math.min(fr.cx + fr.w / 2 - (phone ? 8 : 26), W - 8);
  const y0 = phone ? 64 : 80, y1 = fr.cy + fr.h / 2 - (phone ? 6 : story ? 10 : 72);
  return { x0, x1, y0, y1, w: x1 - x0, h: y1 - y0, cx: fr.cx, cy: fr.cy, phone };
}
// Slots as offsets from the act, so the constellation stays with it when the view moves.
function webLayout(G) {
  const B = webBox(), ph = B.phone, LW = ph ? 84 : 150, SP = ph ? 25 : 30, items = [], heads = [];
  const { g, n } = G;
  const cy = B.cy;
  const capRow = Math.max(2, Math.floor((B.w - 16) / (LW + 16)));
  const row = (list, y, total, grp) => {
    const more = total - list.length, k = list.length + (more > 0 ? 1 : 0);
    const step = Math.min(LW + 22, (B.w - 16) / Math.max(k, 1));
    const x = (q) => B.cx + (q - (k - 1) / 2) * step - LW * 0.32;
    list.forEach((it, q) => items.push({ ...it, g: grp, x: x(q), y, side: "r", mw: step - 30 }));
    if (more > 0) items.push({ j: -1, more, g: grp, x: x(k - 1), y, side: "r", mw: step - 30 });
  };
  // above: what it rests on (below the chain to the Constitution, when it is shown)
  const chainH = mode === "tree" && P[G.i] >= 0 && !ph ? 22 : 0;
  const yUp = B.y0 + chainH + (ph ? 40 : 58);
  if (g.up.length) {
    row(g.up.slice(0, capRow - (g.up.length > capRow ? 1 : 0)), yUp, n.up, "up");
    heads.push({ g: "up", x: B.cx, y: B.y0 + chainH + (ph ? 14 : 28), text: t.webUp, count: n.up, extra: n.upUnk ? t.webUnk(num(n.upUnk)) : "" });
  }
  // below: what rests on it, the most-cited first, in one or two rows
  const rows = ph || n.down <= capRow ? 1 : 2, capD = rows * capRow;
  const yD2 = B.y1 - (ph ? 24 : 34), yD1 = rows === 2 ? yD2 - (ph ? 0 : 46) : yD2;
  if (g.down.length) {
    const shown = g.down.slice(0, n.down > capD ? capD - 1 : capD);
    if (rows === 2) { row(shown.slice(0, capRow), yD1, capRow, "down"); row(shown.slice(capRow), yD2, n.down - capRow, "down"); }
    else row(shown, yD2, n.down, "down");
    heads.push({ g: "down", x: B.cx, y: yD2 + (ph ? 18 : 30), text: n.apex ? t.webDownApex : t.webDown, count: n.down, shown: shown.length,
      extra: !n.apex && shown.length < n.down ? t.webDownKey : "" });
  }
  // the sides: legislation (left), case law and decisions (right)
  const top = (g.up.length ? yUp + (ph ? 30 : 40) : B.y0 + 10), bot = (g.down.length ? yD1 - (ph ? 26 : 36) : B.y1 - 10);
  const capCol = Math.max(0, Math.min(ph ? 6 : 9, Math.floor((bot - top) / SP) - 1));   // a column stays short enough to read
  const xs = B.w / 2 - LW - (ph ? 6 : 16);
  const col = (list, total, grp, x, y0, side) => {
    const more = total - list.length;
    const mw = ph ? LW - 4 : LW + 18;
    list.forEach((it, q) => items.push({ ...it, g: grp, x, y: y0 + q * SP, side, mw, w: ph && grp === "court" ? num(it.s) : it.w }));
    if (more > 0) items.push({ j: -1, more, g: grp, x, y: y0 + list.length * SP, side, mw });
    return list.length + (more > 0 ? 1 : 0);
  };
  if (g.law.length && capCol > 0) {
    const m = Math.min(g.law.length, n.law > capCol ? capCol - 1 : capCol), k = m + (n.law > m ? 1 : 0);
    const y0 = Math.max(top + SP * (ph ? 1 : 1.6), cy - ((k - 1) / 2) * SP);
    heads.push({ g: "law", x: ph ? B.x0 : B.cx - xs, y: y0 - SP * (ph ? 1.1 : 1.6), text: t.webLaw, count: n.law, shown: m, key: t.webLawKey(fullLabel(G.i)), side: ph ? "r" : "l" });
    col(g.law.slice(0, m), n.law, "law", B.cx - xs, y0, "l");
  }
  const capR = ph || !g.dec.length ? capCol : capCol + 4;   // with the decisions the right column holds two groups
  const md = ph ? 0 : Math.min(g.dec.length, 4, Math.max(0, capR - 3));
  const mc = Math.min(g.court.length, Math.max(0, capR - (md ? md + 1 : 0) - 1));
  const k = mc + (mc ? 1 : 0) + md + (md ? 1 : 0);
  let yr = Math.max(top + SP, cy - ((k - 2) / 2) * SP);
  if (mc) {
    heads.push({ g: "court", x: ph ? B.x1 : B.cx + xs, y: yr - SP * (ph ? 1.1 : 1.35), text: t.webCourt, count: n.court, shown: mc, key: t.webCourtKey, side: ph ? "l" : "r" });
    yr += col(g.court.slice(0, mc), mc, "court", B.cx + xs, yr, "r") * SP + SP * 1.15;
  }
  if (md) {
    heads.push({ g: "dec", x: B.cx + xs, y: yr - SP * 0.95, text: t.webDec, side: "r" });
    col(g.dec.slice(0, md), md, "dec", B.cx + xs, yr, "r");
  }
  // offsets from where the act will stand
  for (const it of items) { it.dx = it.x - B.cx; it.dy = it.y - cy; }
  for (const h of heads) {                          // a heading stays inside the free area
    h.dx = h.x - B.cx; h.dy = h.y - cy;
    h.maxW = ph && (h.g === "law" || h.g === "court") ? B.w * 0.46 : h.side === "l" ? h.x - B.x0 + 8 : h.side === "r" ? B.x1 - h.x + 8 : B.w;
  }
  return { items, heads, B };
}

function webAllowed(i) {
  if (!webOn || i < 0 || sel.art || W < 330) return false;
  if (story && (story.descent || story.opening)) return false;
  if (story && story.tr && story.tr.stops[story.k] && story.tr.stops[story.k].k === "courts") return false;
  return K[i] === "act" || K[i] === "bvart" || K[i] === "kvart" || (TN[i] && TN[i].l === 4);
}
async function webFor(i) {
  const req = ++webReq;
  clearWeb();
  if (!webAllowed(i)) return;
  if (PK[i] >= 0 && !actRec(i)) { try { await ensurePack(PK[i]); } catch (e) { /* the decisions stay out */ } }
  if (req !== webReq || sel.i !== i) return;
  const G = webGroups(i, !(story && story.tr));
  if (!G.g.up.length && !G.g.down.length && !G.g.law.length && !G.g.court.length && !G.g.dec.length) return;
  web = { i, G, t0: performance.now() + 120, hot: -1, done: false, ...webLayout(G) };
  buildWebDom();
  document.body.classList.add("webbing");
  edgesDirty = true; treeDirty = true;
}
function clearWeb() {
  if (!web) return;
  web = null;
  $("web").innerHTML = ""; $("wedges").innerHTML = "";
  document.body.classList.remove("webbing");
  edgesDirty = true; treeDirty = true;
}
function relayoutWeb() { if (web) { Object.assign(web, webLayout(web.G)); buildWebDom(); web.done = false; } }

function buildWebDom() {
  const el = $("web"), svg = $("wedges"), max = {};
  el.setAttribute("aria-label", `${t.webBtn}: ${fullLabel(web.i)}`);
  for (const it of web.items) max[it.g] = Math.max(max[it.g] || 1, it.s || 1);
  const ns = "http://www.w3.org/2000/svg";
  el.innerHTML = ""; svg.innerHTML = "";
  const thread = document.createElementNS(ns, "path");
  thread.setAttribute("class", "w-thread"); svg.append(thread); web.thread = thread;
  web.items.forEach((it, k) => {
    it.k = k;
    const rel = WREL[it.g];
    const strength = Math.sqrt((it.s || 1) / max[it.g]);
    const sz = it.more ? 9 : it.g === "dec" ? 7 : Math.round(7 + 9 * Math.sqrt(Math.min(1, decOf(it.j) / Math.max(1, NC[0] * 0.04))));
    const b = document.createElement(it.did ? "a" : "button");
    b.className = `wn ${it.side === "l" ? "l" : ""} ${it.more ? "more" : ""} ${it.did ? "dec" : ""}`;
    if (it.mw) b.style.setProperty("--mw", Math.max(60, it.mw).toFixed(0) + "px");
    b.style.setProperty("--r", `var(--${rel})`);
    b.style.setProperty("--c", it.more ? "var(--bg)" : it.g === "dec" ? "var(--court)" : cssHue(HK[it.j]));
    const name = it.more ? t.webMore(num(it.more)) : it.did ? it.lab : fullLabel(it.j);
    b.innerHTML = `<i style="width:${sz}px;height:${sz}px"></i><span><b>${esc(name)}</b>${it.w ? `<em>${esc(it.w)}</em>` : ""}</span>`;
    if (it.did) { b.href = decUrl(it.did); b.target = "_blank"; b.rel = "noopener"; b.title = t.openDec; }
    else if (!it.more) b.dataset.j = it.j;
    else b.dataset.more = it.g;
    const gname = { up: t.webUp, down: web.G.n.apex ? t.webDownApex : t.webDown, law: t.webLaw, court: t.webCourt, dec: t.webDec }[it.g];
    b.setAttribute("aria-label", `${gname}: ${name}${it.w ? ", " + it.w : ""}`);    // the relation is read out, not only seen
    it.r = sz / 2;
    it.el = b; el.append(b);
    if (!it.more) {
      const p = document.createElementNS(ns, "path");
      p.setAttribute("class", `w-e w-${rel}${it.dash ? " dash" : ""}`);
      p.setAttribute("stroke-width", (1 + 2.4 * strength).toFixed(2));
      it.path = p; svg.append(p);
    }
  });
  for (const h of web.heads) {
    const d = document.createElement("div");
    d.className = `wh ${h.side === "l" ? "l" : h.side === "r" ? "r" : ""}`;
    d.style.maxWidth = Math.max(120, h.maxW).toFixed(0) + "px";
    d.style.setProperty("--r", `var(--${WREL[h.g]})`);
    const cnt = h.count == null ? "" : h.shown != null && h.shown < h.count && !web.B.phone ? t.webOf(num(h.shown), num(h.count)) : num(h.count);
    d.innerHTML = `<i></i>${esc(h.text)}${cnt ? ` · ${esc(cnt)}` : ""}${h.extra ? ` <small>${esc(h.extra)}</small>` : ""}${h.key ? `<small>${esc(h.key)}</small>` : ""}`;
    h.el = d; el.append(d);
  }
  if (mode === "tree" && P[web.i] >= 0 && !web.B.phone) {      // the chain up to the Constitution
    const chain = ancestorsOf(web.i).reverse().filter((j) => !["title", "chapter", "section"].includes(K[j]) && j !== web.i);
    if (chain.length) {
      const c = document.createElement("nav");
      c.className = "wc"; c.setAttribute("aria-label", t.spineHead);
      c.innerHTML = chain.map((j) => `<button data-j="${j}">${esc(fullLabel(j))}</button>`).join("<span>›</span>") +
        `<span>›</span><b>${esc(fullLabel(web.i))}</b><button class="chip" data-descend="${web.i}">▼ ${esc(t.descend)}</button>`;
      web.chain = c; el.append(c);
    }
  }
  web.done = false;
}

const easeOut = (u) => 1 - Math.pow(1 - u, 3);
function renderWeb(now) {
  if (!web) return;
  const i = web.i;
  if (!inLayout(i)) { clearWeb(); return; }
  const [ax, ay, az] = toScreen(X[i], CY[i], Z[i]);
  const animating = now < web.t0 + 700 + web.items.length * 26;
  if (!animating && web.done && !moving && !web.dirty) return;
  web.dirty = false;
  const off = az > 1 || ax < -W * 0.5 || ax > W * 1.5 || ay < -H * 0.5 || ay > H * 1.5;
  $("web").style.visibility = $("wedges").style.visibility = off ? "hidden" : "";
  if (off) return;
  const ra = Math.min(projectedPx(i), 110) + 3;
  const hot = web.hot >= 0 ? web.hot : hoverLink;
  const veil = $("wveil").style;                     // the scene recedes, the act stays lit
  veil.setProperty("--ax", ax.toFixed(0) + "px"); veil.setProperty("--ay", ay.toFixed(0) + "px"); veil.setProperty("--ar", (ra + 26).toFixed(0) + "px");
  for (const it of web.items) {
    const sx = ax + it.dx, sy = ay + it.dy;
    const u = Math.max(0, Math.min(1, (now - web.t0 - it.k * 26) / 620)), e = easeOut(u);
    let fx = ax, fy = ay;
    if (it.j >= 0 && inLayout(it.j)) {
      const [rx, ry, rz] = toScreen(X[it.j], CY[it.j], Z[it.j]);
      if (rz <= 1) { fx = rx; fy = ry; }
      it.real = rz <= 1 ? [rx, ry] : null;
    } else it.real = null;
    const px = fx + (sx - fx) * e, py = fy + (sy - fy) * e;
    it.px = px; it.py = py;
    const pad = 4 + it.r;
    it.el.style.transform = it.side === "l" ? `translate(${(px + pad).toFixed(1)}px, ${py.toFixed(1)}px) translate(-100%, -50%)`
      : `translate(${(px - pad).toFixed(1)}px, ${py.toFixed(1)}px) translate(0, -50%)`;
    it.el.style.opacity = Math.min(1, u * 2.5).toFixed(2);
    it.el.style.setProperty("--lab", Math.max(0, (u - 0.45) / 0.55).toFixed(2));
    it.el.classList.toggle("hot", it.j >= 0 && it.j === hot);
    if (it.path) {
      const vert = it.g === "up" || it.g === "down";
      const c1x = vert ? ax : ax + (px - ax) * 0.55, c1y = vert ? ay + (py - ay) * 0.55 : ay;
      const c2x = vert ? px : ax + (px - ax) * 0.45, c2y = vert ? ay + (py - ay) * 0.45 : py;
      const dl = Math.hypot(c1x - ax, c1y - ay) || 1;
      const x0 = ax + ((c1x - ax) / dl) * ra, y0 = ay + ((c1y - ay) / dl) * ra;
      it.path.setAttribute("d", `M${x0.toFixed(1)},${y0.toFixed(1)}C${c1x.toFixed(1)},${c1y.toFixed(1)} ${c2x.toFixed(1)},${c2y.toFixed(1)} ${px.toFixed(1)},${py.toFixed(1)}`);
      it.path.style.opacity = (Math.min(1, u * 1.6) * (hot >= 0 && it.j !== hot ? 0.35 : 1)).toFixed(2);
      it.path.classList.toggle("hot", it.j === hot);
    }
  }
  const hi = hot >= 0 ? web.items.find((x) => x.j === hot && x.real) : null;   // where it really is (or towards it)
  let td = "";
  if (hi) {
    let [rx, ry] = hi.real;
    const m = 10, dx = rx - hi.px, dy = ry - hi.py;
    let f = 1;                                       // off screen: stop at the edge, pointing at it
    if (rx < m) f = Math.min(f, (m - hi.px) / dx); if (rx > W - m) f = Math.min(f, (W - m - hi.px) / dx);
    if (ry < m) f = Math.min(f, (m - hi.py) / dy); if (ry > H - m) f = Math.min(f, (H - m - hi.py) / dy);
    rx = hi.px + dx * f; ry = hi.py + dy * f;
    td = `M${hi.px.toFixed(1)},${hi.py.toFixed(1)}L${rx.toFixed(1)},${ry.toFixed(1)}M${(rx + 4.5).toFixed(1)},${ry.toFixed(1)}a4.5,4.5 0 1,0 -9,0a4.5,4.5 0 1,0 9,0`;
  }
  web.thread.setAttribute("d", td);
  const lab = Math.max(0, Math.min(1, (now - web.t0 - 300) / 500)).toFixed(2);
  for (const h of web.heads) {
    h.el.style.transform = `translate(${(ax + h.dx).toFixed(1)}px, ${(ay + h.dy).toFixed(1)}px) translate(${h.side === "l" ? "-100%" : h.side === "r" ? "0" : "-50%"}, -50%)`;
    h.el.style.opacity = lab;
  }
  if (web.chain) { web.chain.style.transform = `translate(${(ax).toFixed(1)}px, ${(web.B.y0 + 2).toFixed(1)}px) translate(-50%, 0)`; web.chain.style.opacity = lab; }
  if (!animating) web.done = true;
}
function setWebHot(j) {
  if (!web || web.hot === j) return;
  web.hot = j; web.dirty = true; edgesDirty = true;
  hover = { i: j, art: null }; refreshHover();
}
$("web").addEventListener("pointerover", (e) => {
  const b = e.target.closest("[data-j]");
  if (!b || b.closest(".wc")) { if (!e.target.closest(".wn")) setWebHot(-1); return; }
  const j = +b.dataset.j;
  setWebHot(j);
  const r = b.getBoundingClientRect();
  showTip(r.right, r.bottom - 6, { i: j, art: null });
});
$("web").addEventListener("pointerout", (e) => {
  if (e.relatedTarget && e.relatedTarget.closest && e.relatedTarget.closest(".wn")) return;
  setWebHot(-1); $("tip").hidden = true;
});
$("web").addEventListener("click", (e) => {
  const d = e.target.closest("[data-descend]");
  if (d) { clearWeb(); descend(+d.dataset.descend); return; }
  const m = e.target.closest("[data-more]");
  if (m) {                                   // the full list is in the panel
    if ($("panel").hidden) { $("panel").hidden = false; recentre(); relayoutWeb(); }
    const sec = $("pbody").querySelector(m.dataset.more === "down" ? "[data-sec=deps]" : m.dataset.more === "law" ? "[data-sec=law]" : "[data-sec=court]");
    if (sec) sec.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
    return;
  }
  const b = e.target.closest("[data-j]");
  if (!b) return;
  const j = +b.dataset.j;
  $("tip").hidden = true;
  if (story && story.tr) endTour(false);
  select(j);
});
$("webbtn").onclick = () => {
  webOn = !webOn;
  try { localStorage.setItem("slm-web", webOn ? "1" : "0"); } catch (e) { /* storage unavailable */ }
  $("webbtn").setAttribute("aria-pressed", webOn);
  if (webOn && sel.i >= 0) webFor(sel.i); else clearWeb();
  if (!webOn && sel.i >= 0 && mode === "tree" && K[sel.i] === "act" && !story) courtsFor(sel.i);
  else hideCourts();
};

// --- focus mode, idle orbit
$("focusbtn").onclick = () => {
  const on = !document.body.classList.contains("immersive");
  document.body.classList.toggle("immersive", on);
  $("focusbtn").setAttribute("aria-pressed", on);
  try { if (on && document.documentElement.requestFullscreen) document.documentElement.requestFullscreen().catch(() => {}); else if (!on && document.fullscreenElement) document.exitFullscreen().catch(() => {}); } catch (e) { /* not allowed here */ }
};
for (const ev of ["pointerdown", "wheel", "keydown", "touchstart"]) addEventListener(ev, () => { lastInput = performance.now(); }, { passive: true });

applyTheme();
boot().catch((e) => { $("loading").textContent = "Error: " + e.message; console.error(e); });
