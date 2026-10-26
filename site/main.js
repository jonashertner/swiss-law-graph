// Swiss Law Map, 3D. The official SR hierarchy is the ground plan (circle packing, fixed);
// acts stand on it as orbs sized by the decisions that cite them. Two layers of
// interdependency are routed along the SR tree (hierarchical edge bundling):
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
import { makeShells, makeOrbs, makeDots, makeStems, makeRibbons, setRibbons, makeStars } from "./gl.js";
import { T, CANTON, LANGS } from "./i18n.js";

// ---------- constants ----------
const OPEN_PX = 70;            // a container whose projected radius exceeds this shows its children's links
const ART_PX = 170;            // an act whose projected radius exceeds this shows its articles
const BETA = 0.75;             // bundling strength (Holten 2006): 0 = straight, 1 = fully along the tree
const SAMPLES = 36;            // points per curve
const HUE = {
  1: [0.42, 0.56, 1.0], 2: [0.2, 0.86, 0.74], 3: [1.0, 0.45, 0.33], 4: [0.72, 0.53, 1.0], 5: [0.68, 0.76, 0.32],
  6: [1.0, 0.72, 0.22], 7: [0.32, 0.72, 0.98], 8: [1.0, 0.45, 0.66], 9: [0.4, 0.82, 0.5], k: [0.82, 0.62, 0.42], n: [0.6, 0.66, 0.72],
};
const WIRE = [1.0, 0.62, 0.25];   // legislation: amber, below the plane
const CURRENT = [0.3, 0.82, 1.0]; // case law: cyan, above the plane
const BOTH = [1.0, 0.97, 0.9];    // both layers: white

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const getJSON = (u) => fetch(u).then((r) => { if (!r.ok) throw new Error(u + " " + r.status); return r.json(); });
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

// ---------- state ----------
let lang = pickLang(), t = T[lang], fmt = new Intl.NumberFormat(lang + "-CH");
let core, titles = [], N = 0;
let X, Z, R, P, D, NC, K, HK, PK, kids, ids, idIndex, depthMax = 0;
let jAdj = [], wOut = [], wIn = [];        // judicial adjacency; legislative out/in
let pairKind = new Map();                  // "a|b" -> 1 law, 2 practice, 3 both
let sel = { i: -1, art: null }, hover = { i: -1, art: null };
let period = null, showWire = true, showCurrent = true, edgeYears = null;
const packs = new Map(), packWait = new Map();
const origin = new THREE.Vector3();
let W = innerWidth, H = innerHeight, dpr = Math.min(devicePixelRatio || 1, 2);
const num = (n) => fmt.format(n || 0);

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
renderer.setClearColor(new THREE.Color().setRGB(3 / 255, 6 / 255, 11 / 255, THREE.LinearSRGBColorSpace), 1);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(38, W / H, 0.1, 10000);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.09;
controls.zoomToCursor = true;
controls.screenSpacePanning = false;
controls.maxPolarAngle = Math.PI * 0.47;
controls.minDistance = 1e-4;
controls.maxDistance = 9000;
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
let rings, orbs, wires, current, focusRibbons, dots = null, stems = null, dotsAct = -1, artH = null, artFade = 0;

// ---------- data ----------
async function boot() {
  const [c, tt] = await Promise.all([getJSON("data/core.json"), getJSON(`data/titles.${lang}.json`)]);
  core = c; titles = tt;
  const nodes = core.nodes;
  N = nodes.length;
  X = new Float64Array(N); Z = new Float64Array(N); R = new Float64Array(N);
  P = new Int32Array(N); D = new Int32Array(N); NC = new Float64Array(N); PK = new Int32Array(N).fill(-1);
  K = new Array(N); HK = new Array(N); ids = new Array(N); kids = Array.from({ length: N }, () => []);
  idIndex = new Map();
  for (let i = 0; i < N; i++) {
    const o = nodes[i];
    X[i] = o.x; Z[i] = o.y; R[i] = o.r; P[i] = o.p; K[i] = o.k; NC[i] = o.n || 0; ids[i] = o.i;
    if (o.pk !== undefined) PK[i] = o.pk;
    idIndex.set(o.i, i);
    if (o.p >= 0) { kids[o.p].push(i); D[i] = D[o.p] + 1; depthMax = Math.max(depthMax, D[i]); }
    HK[i] = hueKey(o, i);
  }
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

  buildScene();
  applyLang();
  buildLegend();
  resize();
  home(false);
  $("loading").hidden = true;
  const h = decodeHash();
  if (h) select(h.i, h.art, true);
  else if (!seenIntro()) $("intro").hidden = false;
  requestAnimationFrame(loop);
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
  ringIndex = []; orbIndex = [];
  for (let i = 1; i < N; i++) (K[i] === "act" || K[i] === "bucket" ? orbIndex : ringIndex).push(i);
  orbOf = new Int32Array(N).fill(-1); ringOf = new Int32Array(N).fill(-1);
  orbIndex.forEach((i, j) => (orbOf[i] = j));
  ringIndex.forEach((i, j) => (ringOf[i] = j));
  rings = makeShells(ringIndex.length);
  orbs = makeOrbs(orbIndex.length);
  wires = makeRibbons(); current = makeRibbons(); focusRibbons = makeRibbons();
  scene.add(rings, orbs, wires, current, focusRibbons);
  writeInstances();
  refreshStates();
}

// Containers are flat discs on the plane; acts are orbs standing on it.
function writeInstances() {
  const rc = rings.geometry.attributes.iCenter.array, rr = rings.geometry.attributes.iRadius.array,
    rcol = rings.geometry.attributes.iColor.array;
  ringIndex.forEach((i, j) => {
    rc.set([X[i] - origin.x, -origin.y, Z[i] - origin.z], j * 3);
    rr[j] = R[i];
    rcol.set(HUE[HK[i]] || HUE.n, j * 3);
  });
  const oc = orbs.geometry.attributes.iCenter.array, orr = orbs.geometry.attributes.iRadius.array,
    ocol = orbs.geometry.attributes.iColor.array;
  orbIndex.forEach((i, j) => {
    oc.set([X[i] - origin.x, R[i] - origin.y, Z[i] - origin.z], j * 3);   // orbs stand on the plane
    orr[j] = R[i];
    const h = HUE[HK[i]] || HUE.n;
    ocol.set(core.nodes[i].reg ? h.map((c) => 0.35 * c + 0.3) : h, j * 3);  // earlier act or edition: paler
  });
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
  if (sel.i >= 0) {
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
  }
  function addPath(j) { while (j >= 0 && !related.has(j)) { related.add(j); j = P[j]; } }
  const maxN = Math.log10(NC[0] + 1);
  const rs = rings.geometry.attributes.iState.array;
  ringIndex.forEach((i, j) => {
    const on = !related || related.has(i);
    const depthA = K[i] === "domain" ? 0.9 : 1.0;
    rs.set([on ? depthA : 0.18, 1, 0, 0], j * 4);
  });
  const os = orbs.geometry.attributes.iState.array;
  orbIndex.forEach((i, j) => {
    const on = !related || related.has(i);
    const o = core.nodes[i];
    let b = Math.log10(NC[i] + 1) / maxN;
    if (period && o.ys) b *= Math.sqrt(share(o));
    os.set([on ? 1 : 0.16, b, 0, i === sel.i && !sel.art ? 0.38 : (i === hover.i ? 0.3 : 0)], j * 4);
  });
  rings.geometry.attributes.iState.needsUpdate = true;
  orbs.geometry.attributes.iState.needsUpdate = true;
  edgesDirty = true;
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
  edgesDirty = true;
}
const worldTarget = () => ({ x: controls.target.x + origin.x, z: controls.target.z + origin.z });

// ---------- camera ----------
let anim = null;
const viewDist = () => camera.position.distanceTo(controls.target);
function pxPerUnitAt(dist) { return (H / 2) / Math.tan((camera.fov * Math.PI) / 360) / Math.max(dist, 1e-9); }
function freeRect() {
  const open = !$("panel").hidden;
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
function flyTo(wx, wz, dist, polar, animate = true, ty = 0) {
  const sph = new THREE.Spherical().setFromVector3(camera.position.clone().sub(controls.target));
  const toPolar = polar ?? sph.phi;
  const from = [controls.target.x + origin.x, controls.target.z + origin.z, viewDist()];
  const to = [wx, wz, dist];
  if (!animate || reduceMotion) { setView(to, toPolar, sph.theta, ty); return; }
  const interp = interpolateZoom(from, to);
  const dur = Math.max(600, Math.min(2400, interp.duration * 1.1));
  const t0 = performance.now(), phi0 = sph.phi, th = sph.theta, y0 = controls.target.y;
  anim = {
    step(now) {
      const u = Math.min(1, (now - t0) / dur);
      const e = u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2;
      setView(interp(e), phi0 + (toPolar - phi0) * e, th, y0 + (ty - y0) * e);
      if (u >= 1) anim = null;
    },
    shift() { /* positions are absolute, setView applies the origin */ },
  };
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
function home(animate = true) {
  let x0 = Infinity, z0 = Infinity, x1 = -Infinity, z1 = -Infinity;
  for (const j of kids[0]) { x0 = Math.min(x0, X[j] - R[j]); x1 = Math.max(x1, X[j] + R[j]); z0 = Math.min(z0, Z[j] - R[j]); z1 = Math.max(z1, Z[j] + R[j]); }
  const r = Math.max(x1 - x0, z1 - z0) / 2;
  const polar = W <= 760 ? 0.18 : 0.78;
  flyTo((x0 + x1) / 2, (z0 + z1) / 2 + r * 0.12, distanceToFit(r) * (W <= 760 ? 0.92 : 0.8), polar, animate);
}
function focusOn(i, animate = true) {
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
  const d = camera.position.distanceTo(pv.set(X[i] - origin.x, K[i] === "act" ? R[i] - origin.y : 0, Z[i] - origin.z));
  return R[i] * pxPerUnitAt(d);
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
  const focus = sel.i >= 0 ? new Set(subtree(sel.i)) : null;
  const agg = new Map();    // "fa|fb|layer" -> weight
  const fcache = new Map();
  const front = (a) => { let f = fcache.get(a); if (f === undefined) { f = frontierOf(a, open); fcache.set(a, f); } return f; };
  const add = (a, b, w, layer) => {
    const fa = focus && focus.has(a) ? a : front(a), fb = focus && focus.has(b) ? b : front(b);
    if (fa === fb) return;
    const key = layer === 1 ? fa + "|" + fb + "|1" : (fa < fb ? fa + "|" + fb : fb + "|" + fa) + "|2";
    agg.set(key, (agg.get(key) || 0) + w);
  };
  const inFocus = (a, b) => !focus || focus.has(a) || focus.has(b);
  if (showCurrent) core.edges.forEach(([a, b, n], k) => {
    if (!inFocus(a, b)) return;
    let w = n;
    const ey = period && edgeYears ? edgeYears[k] : null;
    if (period && edgeYears) {
      w = 0;
      if (ey) { const [y0, ys] = ey; for (let y = Math.max(period[0], y0); y <= Math.min(period[1], y0 + ys.length - 1); y++) w += ys[y - y0]; }
    }
    if (w > 0) add(a, b, w, 2);
  });
  if (showWire) for (const [a, b, n] of core.xedges || []) if (inFocus(a, b)) add(a, b, n, 1);
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
    if (focus && layer === 1) { alpha = 0.5 + 0.35 * strong; width = 1.6 + 2.2 * strong; }   // legislative weights are mostly 1
    if (hl) { if (hl.has(fa) || hl.has(fb)) { alpha = 0.95; width += 2; } else alpha *= 0.2; }
    if (layer === 2) {
      lines.current.push({ pts: bspline(controlPoints(fa, fb, true), SAMPLES), width, color: both ? BOTH : CURRENT, alpha, flow: 0.25 });
    } else {
      lines.wire.push({ pts: bspline(controlPoints(fa, fb, false), SAMPLES), width: width * 1.1, color: both ? BOTH : WIRE, alpha, flow: 1, taper: true });
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
  const out = [origin.x.toPrecision(8), origin.z.toPrecision(8)], st = [0];
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
  const st = [0];
  const camD = (i) => projectedPx(i);
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
  if (sel.i >= 0) {   // the focus and its partners always get a name
    const extra = [...jAdj[sel.i].slice(0, 8).map((e) => e[0]), ...wOut[sel.i].slice(0, 6).map((e) => e[0]), ...wIn[sel.i].slice(0, 4).map((e) => e[0])];
    for (const j of [sel.i, ...(hoverLink >= 0 ? [hoverLink] : []), ...extra]) cand.push([j, 1e6 - cand.length]);
  }
  cand.sort((a, b) => b[1] - a[1]);
  const boxes = [], used = new Set();
  let k = 0;
  const fits = (b) => { for (const o of boxes) if (b[0] < o[2] && b[2] > o[0] && b[1] < o[3] && b[3] > o[1]) return false; boxes.push(b); return true; };
  for (const [i, px] of cand) {
    if (k >= 90 || used.has(i)) continue;
    const isOrb = K[i] === "act" || K[i] === "bucket";
    if (related && !related.has(i) && px < 1e5) continue;
    const [sx, sy, sz] = isOrb ? toScreen(X[i], 2 * R[i], Z[i]) : toScreen(X[i], 0, Z[i] - R[i] * 0.93);
    if (sz > 1) continue;
    const text = isOrb ? label(i) : areaLabel(i);
    const size = isOrb ? Math.max(11, Math.min(22, Math.sqrt(px) * 2.2)) : (K[i] === "domain" ? 19 : Math.max(11, Math.min(16, Math.sqrt(px) * 1.2)));
    const w = Math.min(Math.min(text.length, 46) * size * 0.56, 300), h = size * 1.3;
    if (sx - w / 2 < 4 || sx + w / 2 > W - 4 || sy - h < 4 || sy > H - 4) continue;
    const box = [sx - w / 2, sy - h - 4, sx + w / 2, sy];
    if (!fits(box)) continue;
    used.add(i);
    const el = labelEl(k++);
    el.textContent = text.length > 46 ? text.slice(0, 45) + "…" : text;
    el.style.transform = `translate(${sx.toFixed(1)}px, ${(sy - 4).toFixed(1)}px) translate(-50%, -100%)`;
    el.style.fontSize = size.toFixed(1) + "px";
    el.dataset.kind = isOrb ? "act" : K[i];
    el.style.setProperty("--hue", `rgb(${(HUE[HK[i]] || HUE.n).map((c) => Math.round(150 + 105 * c)).join(",")})`);
    el.classList.toggle("on", i === sel.i);
    el.classList.remove("edge");
    el.hidden = false;
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
  if (sel.i >= 0 && !sel.art) {
    const fr = freeRect(), x0 = fr.cx - fr.w / 2 + 24, x1 = fr.cx + fr.w / 2 - 24, y0 = 96, y1 = fr.cy + fr.h / 2 - 70;
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    const list = [...new Set([hoverLink, ...jAdj[sel.i].slice(0, 5).map((e) => e[0]), ...wOut[sel.i].slice(0, 3).map((e) => e[0])])]
      .filter((j) => j >= 0 && j !== sel.i);
    const placed = [];
    for (const j of list) {
      const [sx, sy, sz] = toScreen(X[j], K[j] === "act" ? R[j] : 0, Z[j]);
      if (sz < 1 && sx > x0 && sx < x1 && sy > y0 && sy < y1) continue;
      let dx = sx - cx, dy = sy - cy;
      if (sz > 1) { dx = -dx; dy = -dy; }
      const f = Math.min((x1 - cx) / Math.max(Math.abs(dx), 1e-6), (y1 - cy) / Math.max(Math.abs(dy), 1e-6));
      let ex = cx + dx * f, ey = cy + dy * f;
      const tb = $("tools").getBoundingClientRect();     // keep clear of the legend and tools
      if (ex < tb.right + 60 && ey > tb.top - 16) ey = tb.top - 16;
      while (placed.some(([px, py]) => Math.abs(px - ex) < 120 && Math.abs(py - ey) < 22)) ey += ey > cy ? -24 : 24;
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
  const o = core.nodes[i];
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
  const o = core.nodes[i];
  if (o.k === "group") return o.sr;                     // the act inside carries the name
  return (o.k === "area" && o.sr ? o.sr + "  " : "") + label(i);
}
function title(i) { const v = titles[i]; return v == null ? "" : typeof v === "string" ? v : v[0]; }
function titleLang(i) { const v = titles[i]; return v && typeof v !== "string" ? v[1] : null; }

// ---------- loop ----------
let lastT = performance.now(), lastLabels = 0, moving = false, lastCam = "";
function loop(now) {
  requestAnimationFrame(loop);
  if (!core) return;
  const dt = Math.min(0.05, (now - lastT) / 1000);
  lastT = now;
  if (anim) anim.step(now);
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
  for (const m of [rings, orbs]) { m.material.uniforms.uPixelScale.value = pxScale; }
  for (const m of [wires, current, focusRibbons]) {
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
  composer.render(dt);
}
function updateOpenAct() {
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
    const o = core.nodes[h.i];
    head = K[h.i] === "act" ? label(h.i) + (title(h.i) ? " · " + title(h.i) : "") : areaLabel(h.i);
    line = t.decN(num(NC[h.i]));
    const nl = wOut[h.i].length + wIn[h.i].length, nc = jAdj[h.i].length;
    if (o.k === "act" && (nl || nc)) line += ` · ${t.lawWiring} ${nl} · ${t.practice} ${nc}`;
  }
  tip.innerHTML = `<b>${esc(head.length > 140 ? head.slice(0, 139) + "…" : head)}</b><span>${esc(line)}</span>`;
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
}
addEventListener("keydown", (e) => {
  if (e.target.matches("input, select, textarea")) return;
  if (e.key === "/") { e.preventDefault(); $("search").focus(); }
  else if (e.key === "Escape") {
    if (!$("method").hidden) closeMethod();
    else if (!$("intro").hidden) closeIntro();
    else if (sel.i >= 0) { const p = P[sel.i]; sel.art ? select(sel.i) : (p > 0 ? select(p) : goHome()); }
  }
});

// ---------- selection ----------
function select(i, art = null, animate = true) {
  if (i < 0) {
    const was = !$("panel").hidden;
    sel = { i: -1, art: null }; $("panel").hidden = true; $("tools").classList.remove("raised");
    refreshStates(); refreshHover(); writeHash(); crumbs();
    if (was && animate) recentre();
    return;
  }
  sel = { i, art };
  hoverLink = -1;
  $("panel").hidden = false;
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
    focusOn(i, animate);
    refreshPanel();
  }
  writeHash(); crumbs();
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
    const o = core.nodes[j];
    b.textContent = o.k === "area" || o.k === "group" ? o.sr : label(j);
    b.title = label(j);
    b.onclick = () => (j === 0 ? goHome() : select(j));
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
  const col = `rgb(${(HUE[hue] || HUE.n).map((c) => Math.round(255 * c)).join(",")})`;
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
    html += `<section><h3><i class="sw wire"></i>${esc(t.lawWiring)}</h3><p class="note">${esc(t.lawWiringNote)}</p>`;
    if (wOut[i].length) html += `<p class="note">${esc(t.refersTo)}</p><ul class="list">${wOut[i].slice(0, 12).map(([j, n]) => linkRow(j, t.refsN(num(n)), title(j), kindOf(j))).join("")}</ul>`;
    if (wIn[i].length) html += `<p class="note">${esc(t.referredBy)}</p><ul class="list">${wIn[i].slice(0, 12).map(([j, n]) => linkRow(j, t.refsN(num(n)), title(j), kindOf(j))).join("")}</ul>`;
    html += "</section>";
  }
  if (jAdj[i].length) {
    html += `<section><h3><i class="sw current"></i>${esc(t.practice)}</h3><p class="note">${esc(t.practiceNote)}</p><ul class="list">${jAdj[i].slice(0, 12).map(([j, n, l]) =>
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
function refreshPanel() {
  if (sel.i < 0 || $("panel").hidden) return;
  const i = sel.i, o = core.nodes[i], hue = HK[i];
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
    eyebrow = o.c ? `${t.cantonalAct} · ${CANTON[o.c] ? CANTON[o.c][LANGS.indexOf(lang)] : o.c}` : `${t.sr} ${o.sr}${o.reg ? (o.reg === "a" ? " · " + t.edition : " · " + t.earlier) : ""}`;
    h2 = label(i);
    sub = tt + (tl ? ` [${tl.toUpperCase()}]` : "");
    html += countBlock(o.n, t.citeAct, o, null);
    if (o.c && !tt) html += `<p class="note">${esc(t.cantonalNoTitle)}</p>`;
    if (o.from || o.to) html += `<dl class="facts"><dt>${esc(t.inForce)}</dt><dd class="mono">${esc(o.from || "")} – ${esc(o.to || "")}</dd></dl>`;
    if (o.reg && o.reg !== "a") {
      const j = idIndex.get("SR " + o.sr);
      if (j !== undefined) html += `<p class="note">${esc(t.successor)}: <button class="link" data-sel="${j}">${esc(label(j))}</button></p>`;
    }
    if (o.ys) html += `<section><h3>${esc(t.perYear)}</h3>${spark(o.y0, o.ys, hue)}</section>`;
    html += interdependencies(i);
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
    if (o.e) html += `<section><a class="link" href="${esc(o.e + (o.c ? "" : "/" + lang))}" target="_blank" rel="noopener">${esc(o.c ? t.cantonal : t.official)} ↗</a></section>`;
  } else if (o.k === "bucket") {
    const p = core.nodes[P[i]];
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
      const oj = core.nodes[j];
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
    h = ids[sel.i].replace(/ /g, "_").replace(/@/g, "~").replace(/\*/g, "x");
    if (sel.art) h += "--" + sel.art.replace(/\//g, "~");
  }
  try { history.replaceState(null, "", h ? "#" + h : location.pathname + location.search); } catch (e) { /* sandboxed */ }
}
function decodeHash() {
  const h = decodeURIComponent((location.hash || "").slice(1));
  if (!h) return null;
  const [node, art] = h.split("--");
  const i = idIndex.get(node.replace(/_/g, " ").replace(/~/g, "@").replace(/ x$/, " *"));
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
  const ali = core.alias[nq];
  if (ali !== undefined) out.push({ i: ali, score: 900 });
  for (let i = 1; i < N; i++) {
    const o = core.nodes[i];
    if (o.k === "bucket") continue;
    let s = 0;
    if (o.sr && (o.sr === q || (q.length >= 2 && /^[\d.]+$/.test(q) && o.sr.startsWith(q)))) s = o.sr === q ? 800 : 300 - o.sr.length;
    if (o.a) for (const v of Object.values(o.a)) { const nv = norm(v); if (nv === nq) s = Math.max(s, 850); else if (nq.length >= 2 && nv.startsWith(nq)) s = Math.max(s, 400); }
    if (!s && words.length) {
      const tt = (title(i) || "").toLowerCase();
      if (tt && words.every((w) => tt.includes(w))) s = 200 - Math.min(tt.length / 4, 60);
      else if (o.k === "canton" && label(i).toLowerCase().startsWith(lq)) s = 600;
    }
    if (s) out.push({ i, score: s + Math.log10(NC[i] + 1) * 12 });
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
    const o = core.nodes[r.i];
    const head = r.topic || (r.artNum ? `${t.art} ${r.artNum} ${label(r.i)}` : (o.k === "area" ? `${o.sr} ${label(r.i)}` : label(r.i)));
    const subl = r.topic ? `${label(r.i)} · ${title(r.i)}`
      : o.k === "act" ? [o.sr ? `${t.sr} ${o.sr}` : (o.c || ""), title(r.i)].filter(Boolean).join(" · ") : (o.k === "area" || o.k === "group" ? t.area : "");
    return `<button role="option" aria-selected="${n === 0}" data-n="${n}"><span class="t">${esc(head)}</span><span class="s">${esc(subl)}</span><span class="n">${r.artNum ? "" : num(r.topic ? r.n : NC[r.i])}</span></button>`;
  }).join("");
}
function choose(n) {
  const r = results[n];
  if (!r) return;
  $("results").hidden = true;
  $("search").blur();
  if (r.art) { select(r.i, r.art); return; }
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
$("lwire").onclick = () => { showWire = !showWire; $("lwire").setAttribute("aria-pressed", showWire); edgesDirty = true; };
$("lcurrent").onclick = () => { showCurrent = !showCurrent; $("lcurrent").setAttribute("aria-pressed", showCurrent); edgesDirty = true; };
$("periodbtn").onclick = () => {
  const box = $("period"), on = box.hidden;
  box.hidden = !on;
  $("periodbtn").setAttribute("aria-pressed", on);
  if (on) setPeriod(); else { period = null; refreshStates(); refreshPanel(); }
};
for (const id of ["y0", "y1"]) $(id).addEventListener("input", setPeriod);
function setPeriod() {
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
  let y = 1880, last = 0;
  const step = (now) => {
    if (now - last > 140) {
      last = now;
      $("y0").value = Math.max(1875, y - 9); $("y1").value = y;
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
  $("tilt").textContent = core ? tiltLabel() : t.view3d; $("play").textContent = playing ? t.pause : t.play;
  $("l-from").textContent = t.from; $("l-to").textContent = t.to; $("periodnote").textContent = t.periodNote;
  $("introtext").textContent = t.intro; $("introok").textContent = t.introOk; $("introtitle").textContent = t.name;
  $("ik1").textContent = t.lawWiring; $("ik2").textContent = t.practice; $("ik3").textContent = t.bothShort;
  $("layershead").textContent = t.layers;
  $("lwiren").textContent = core.xedges && core.xedges.length ? num(core.xedges.length) : "";
  $("lcurrentn").textContent = num(core.edges.length);
  $("lwire").querySelector("span").textContent = t.lawWiring;
  $("lcurrent").querySelector("span").textContent = t.practice;
  $("lwire").title = t.lawWiringNote; $("lcurrent").title = t.practiceNote;
  $("lboth").textContent = t.both;
}
function buildLegend() {
  const el = $("legend");
  const ch = idIndex.get("CH");
  const items = kids[ch].map((j) => [j, HK[j], label(j)]);
  items.push([idIndex.get("KT"), "k", t.KT]);
  el.innerHTML = items.map(([j, h, l]) => `<button data-sel="${j}" title="${esc(l)}"><i style="background: rgb(${(HUE[h] || HUE.n).map((c) => Math.round(255 * c)).join(",")})"></i><span>${esc(core.nodes[j].sr ? core.nodes[j].sr + " " : "")}${esc(l)}</span></button>`).join("");
  el.onclick = (e) => { const b = e.target.closest("[data-sel]"); if (b) select(+b.dataset.sel); };
}

// ---------- intro ----------
function seenIntro() { try { return localStorage.getItem("slm-intro") === "1"; } catch (e) { return false; } }
function closeIntro() { $("intro").hidden = true; try { localStorage.setItem("slm-intro", "1"); } catch (e) { /* storage unavailable */ } }
$("introok").onclick = closeIntro;

// ---------- method ----------
async function openMethod() {
  const { methodHTML } = await import("./method.js");
  $("mbox").innerHTML = methodHTML(core.method, lang, t, num, esc);
  $("method").hidden = false;
  $("mclose").onclick = closeMethod;
  $("mclose").focus();
}
function closeMethod() { $("method").hidden = true; $("methodbtn").focus(); }
$("methodbtn").onclick = openMethod;
$("method").addEventListener("click", (e) => { if (e.target.id === "method") closeMethod(); });

window.__slm = { select, pick, home, updateLabels, rebuild: () => { buildEdges(); return buildMs; }, idx: (id) => idIndex.get(id), get dbg() { return { buildMs, lines: lastEntries.length, dotsAct, p: dots ? actRec(dotsAct).p : null, pxu: pxPerUnitAt(viewDist()), R: R[sel.i], pool: pool.length, fade: artFade, W, H }; }, get state() { return { sel, origin: origin.toArray(), dist: viewDist() }; }, get entries() { return lastEntries.map(([k, w]) => { const [a, b, l] = k.split("|").map(Number); return [ids[a], ids[b], l, w, Math.round(projectedPx(a)), Math.round(projectedPx(b))]; }); }, get meshes() { return { wires, current, focusRibbons, orbs, rings, camera, controls }; } };
boot().catch((e) => { $("loading").textContent = "Error: " + e.message; console.error(e); });
