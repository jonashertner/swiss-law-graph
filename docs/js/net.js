// The network (decisions 29, 30): every act with a link, in jurisdiction clusters laid out by
// layout/net.mjs — federal law in the centre, treaties above it, the 26 cantons on a ring in the order
// of Art. 1 BV; inside each cluster rings by level (constitution in the middle). Three kinds of link,
// each its own colour: stated bases (Ingress), references in the text of the act (footnotes with an SR
// number), and co-citation by courts.
// Navigation has three steps, each a route: the whole network (#net), one jurisdiction (#net/ZH, fed,
// int) and one act (#net/ZH/700.1). The camera flies between them on the shortest path through scale
// space (van Wijk & Nuij 2003), so the eye keeps its place. An act's links grow out of it; its chain of
// primary bases up to the Constitution is drawn and is also the breadcrumb; moving points run from the
// act that names to the act named. Pointing at a row of the panel or at a crumb shows that act here.
import { t, cantonName } from "./i18n.js";
import { M, KIND, getJSON, idOf, label, labelCt, title } from "./data.js";
import { $, esc, num, sw, href, ICON, store } from "./util.js";
import { tileLabel } from "./treemap.js";
import { fmtArts } from "./dossier.js";
import * as TV from "./time.js";

const LAYERS = ["bases", "legis", "cocite"];
const EDGE = { bases: [58, 65, 80], legis: [213, 94, 0], cocite: [123, 63, 168] };
const LNAME = { bases: "mBasis", legis: "mLaw", cocite: "mCourt" };
const motion = () => !matchMedia("(prefers-reduced-motion: reduce)").matches;
const coarse = () => matchMedia("(pointer: coarse)").matches;
const inout = (u) => (u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2);
const out3 = (u) => 1 - Math.pow(1 - Math.min(1, Math.max(0, u)), 3);
const GROW = 650, FLOW = 14000, DWELL = 140;               // ms: links growing out; points moving; pointing before a preview

let ctx = {}, NET = null, ready = null;
let cv, g, mini, mg, W = 0, H = 0, dpr = 1;
// the network
let n = 0, AT, X, Y, RW, CL, D, KC, order, grid, adj, deg, par, BVk = -1, CLU = [];
const GS = 24, EP = {}, EI = {}, EO = {};
let AL = null;                                           // the time view: 1 if the act exists in the year shown (decision 31)
// the camera, and the pictures it moves while flying
let view = { x: 0, y: 0, z: 1 }, fitZ = 1, mx = 90, my = 40, flight = null, aim = null;   // aim: what the camera frames, until the hand takes over
let base0 = null, base0V = null, cache = null, cacheV = null, cacheTimer = 0, raf = 0, still = 0, wheelT = 0;
// what is shown
let on = { bases: true, legis: true, cocite: true };
let focus = { lvl: 0, c: -1, k: -1 }, ego = null, from = -1, spotC = -1, shown = false, noFly = false;
let panelOff = false, keepPos = false;                    // the act's panel closed by hand: the act stays, the view keeps its place
let hot = null, hotT = 0, prevK = -1, prevEgo = null, chotK = -1, chotC = -1, hint = -1, kbd = null;
let drag = null, pinch = null, miniKey = "";
const COLS = [];

// ---------- values that ease towards a target
const TW = {};
function tw(key, to, dur = 220) {
  const now = performance.now();
  TW[key] = { a: val(key, now), b: to, t0: now, d: motion() ? dur : 0 };
  redraw();
}
function val(key, now) {
  const s = TW[key];
  if (!s) return 0;
  if (!s.d) return s.b;
  return s.a + (s.b - s.a) * out3((now - s.t0) / s.d);
}
const tweening = (now) => Object.values(TW).some((s) => s.d && now - s.t0 < s.d);

// ---------- data
export function load() {
  if (!ready) ready = Promise.all([getJSON("data/net.json"), getJSON("data/links.json")]).then(([net, links]) => { build(net, links); return NET; });
  return ready;
}
export const has = (i) => !!NET && NET.idx.has(i);
function build(net, links) {
  n = net.ids.length;
  AT = Int32Array.from(net.ids);
  X = new Float64Array(n); Y = new Float64Array(n); RW = new Float32Array(n); CL = new Int8Array(n); D = new Float64Array(n);
  const idx = new Map();
  for (let k = 0; k < n; k++) {
    const i = AT[k];
    idx.set(i, k);
    X[k] = net.xy[2 * k] / net.scale; Y[k] = net.xy[2 * k + 1] / net.scale;
    D[k] = M.D[i]; CL[k] = M.cls[i] >= 0 ? M.cls[i] : 6;
    RW[k] = 2.1 + Math.min(15, Math.sqrt(D[k]) * 0.05);
  }
  CLU = Object.entries(net.clusters).map(([key, c]) => ({
    key, id: key.startsWith("ct:") ? key.slice(3) : key, x: c.c[0] / net.scale, y: c.c[1] / net.scale, r: c.r / net.scale, n: c.n,
    bands: Object.entries(c.bands).map(([l, [a, b]]) => [+l, a / net.scale, b / net.scale]), sectors: Object.entries(c.sectors).map(([s, [a, b]]) => [+s, a, b]),
    mem: [], out: [0, 0, 0], to: new Map(), lv: new Map(), ext: null,
  }));
  const ci = new Map(CLU.map((C, j) => [C.key, j]));
  KC = new Int16Array(n);
  for (let k = 0; k < n; k++) {
    const i = AT[k], key = M.CT[i] ? "ct:" + M.CT[i] : (M.S[i] || "").startsWith("0.") ? "int" : "fed";
    KC[k] = ci.has(key) ? ci.get(key) : 0;
    const C = CLU[KC[k]];
    C.mem.push(k); C.lv.set(CL[k], (C.lv.get(CL[k]) || 0) + 1);
  }
  // links: endpoints per layer (the first names the second: the act and its basis; the referring act
  // and the act it refers to), what each says (articles named, provisions, shared decisions), and
  // for every act its links as [partner, layer, link]
  adj = Array.from({ length: n }, () => []);
  par = new Int32Array(n).fill(-1);
  LAYERS.forEach((L, li) => {
    const P = [], I = [], O = [];
    links[L].forEach((e, o) => {
      const a = idx.get(e[0]), b = idx.get(e[1]);
      if (a == null || b == null || a === b) return;
      const j = P.length / 2;
      P.push(a, b); I.push(L === "bases" ? e[3] || [] : e[2]); O.push(o);
      if (L === "bases" && e[2] && par[a] < 0) par[a] = b;          // the act's place in the Stufenbau
      adj[a].push(b, li, j); adj[b].push(a, li, j);
      if (KC[a] !== KC[b]) for (const [p, q] of [[a, b], [b, a]]) { const C = CLU[KC[p]]; C.out[li]++; C.to.set(KC[q], (C.to.get(KC[q]) || 0) + 1); }
    });
    EP[L] = Int32Array.from(P); EI[L] = I; EO[L] = Int32Array.from(O);
  });
  deg = new Int32Array(n);
  for (let k = 0; k < n; k++) { const s = new Set(); for (let q = 0; q < adj[k].length; q += 3) s.add(adj[k][q]); deg[k] = s.size; }
  order = Int32Array.from([...Array(n).keys()].sort((a, b) => RW[a] - RW[b]));
  grid = new Map();
  for (let k = 0; k < n; k++) { const key = Math.floor(X[k] / GS) + ":" + Math.floor(Y[k] / GS); if (!grid.has(key)) grid.set(key, []); grid.get(key).push(k); }
  const bv = M.byId.get("101");
  BVk = bv != null && idx.has(bv) ? idx.get(bv) : -1;
  NET = { idx, unlinked: net.unlinked };
}
// the chain of primary bases from the act up to the top; a cantonal constitution rests on Art. 51 BV
function chainOf(k) {
  const out = [k];
  for (let c = k, guard = 0; par[c] >= 0 && guard < 16; guard++) { c = par[c]; if (out.includes(c) || !live(c)) break; out.push(c); }
  const top = out[out.length - 1];
  if (CL[top] === 0 && M.CT[AT[top]] && BVk >= 0 && live(BVk)) out.push(BVk);
  return out.reverse();                                    // top … k
}

// the year shown: which acts exist, how many decisions refer to them by then, which links are there
const live = (k) => !AL || AL[k] === 1;
function liveLink(li, j) {
  if (!AL) return true;
  const p = EP[LAYERS[li]];
  if (!AL[p[2 * j]] || !AL[p[2 * j + 1]]) return false;
  if (li === 1) return TV.TIME.year >= TV.TIME.y1;           // legislation: today's text only
  if (li === 2) return TV.pairYear(EO.cocite[j]) <= TV.TIME.year;
  return true;
}
function applyTime() {
  const on = TV.TIME.on, y = TV.TIME.year;
  AL = on ? new Uint8Array(n) : null;
  for (let k = 0; k < n; k++) {
    if (on) AL[k] = TV.exists(AT[k], y) ? 1 : 0;
    D[k] = on ? TV.decTo(AT[k], y) : M.D[AT[k]];
    RW[k] = 2.1 + Math.min(15, Math.sqrt(D[k]) * 0.05);
  }
  order = Int32Array.from([...Array(n).keys()].sort((a, b) => RW[a] - RW[b]));
}

// ---------- geometry
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const SANS = css("--sans") || "sans-serif";
const sx = (x) => W / 2 + (x - view.x) * view.z, sy = (y) => H / 2 + (y - view.y) * view.z;
const rpx = (k, z = view.z) => Math.min(42, Math.max(0.9, RW[k] * z));
function readCols() { for (let c = 0; c < 7; c++) COLS[c] = css(`--c${c}`); COLS[5] = "#c9c9c6"; }
// A link as a cubic Bézier in world coordinates, from u to w. Inside a cluster straight; between two
// clusters it leaves u's disc at the rim facing w's and enters w's at the rim facing back, so the links
// between the same two clusters run together as one trunk.
const BETA = 0.92;
function curve(u, w, o = new Float64Array(8)) {
  const ax = X[u], ay = Y[u], bx = X[w], by = Y[w];
  o[0] = ax; o[1] = ay; o[6] = bx; o[7] = by;
  if (KC[u] === KC[w]) { o[2] = ax + (bx - ax) / 3; o[3] = ay + (by - ay) / 3; o[4] = ax + (bx - ax) * 2 / 3; o[5] = ay + (by - ay) * 2 / 3; return o; }
  const A = CLU[KC[u]], B = CLU[KC[w]];
  let dx = B.x - A.x, dy = B.y - A.y;
  const d = Math.hypot(dx, dy) || 1; dx /= d; dy /= d;
  const p1x = A.x + dx * A.r * 0.92, p1y = A.y + dy * A.r * 0.92, p2x = B.x - dx * B.r * 0.92, p2y = B.y - dy * B.r * 0.92;
  const q = (s, e, f) => s + (e - s) * f;
  o[2] = q(q(ax, bx, 1 / 3), p1x, BETA); o[3] = q(q(ay, by, 1 / 3), p1y, BETA);
  o[4] = q(q(ax, bx, 2 / 3), p2x, BETA); o[5] = q(q(ay, by, 2 / 3), p2y, BETA);
  return o;
}
function split(c, p, o) {                                 // the part [0, p] of a cubic Bézier (de Casteljau)
  const ax = c[0] + (c[2] - c[0]) * p, ay = c[1] + (c[3] - c[1]) * p, bx = c[2] + (c[4] - c[2]) * p, by = c[3] + (c[5] - c[3]) * p;
  const cx = c[4] + (c[6] - c[4]) * p, cy = c[5] + (c[7] - c[5]) * p, dx = ax + (bx - ax) * p, dy = ay + (by - ay) * p;
  const ex = bx + (cx - bx) * p, ey = by + (cy - by) * p;
  o[0] = c[0]; o[1] = c[1]; o[2] = ax; o[3] = ay; o[4] = dx; o[5] = dy; o[6] = dx + (ex - dx) * p; o[7] = dy + (ey - dy) * p;
  return o;
}
function at(c, s) {
  const u = 1 - s, a = u * u * u, b = 3 * u * u * s, e = 3 * u * s * s, f = s * s * s;
  return [a * c[0] + b * c[2] + e * c[4] + f * c[6], a * c[1] + b * c[3] + e * c[5] + f * c[7]];
}
const SC = new Float64Array(8), SP = new Float64Array(8);
function seg(c, p = 1) {                                  // a link, or its first part, into the current path
  const q = p < 1 ? split(c, Math.max(0, p), SP) : c;
  g.moveTo(sx(q[0]), sy(q[1])); g.bezierCurveTo(sx(q[2]), sy(q[3]), sx(q[4]), sy(q[5]), sx(q[6]), sy(q[7]));
}

// ---------- the picture of the whole network at one view (cached; moved while the camera flies)
function drawBase(c, v) {
  const z = v.z, X0 = (x) => W / 2 + (x - v.x) * z, Y0 = (y) => H / 2 + (y - v.y) * z;
  c.setTransform(dpr, 0, 0, dpr, 0, 0);
  c.fillStyle = "#ffffff"; c.fillRect(0, 0, W, H);
  const zoom = z / fitZ;
  // the clusters: a pale disc, rings between the levels, sectors of federal law and treaties
  for (const C of CLU) {
    const cx = X0(C.x), cy = Y0(C.y), r = C.r * z;
    if (cx + r < -50 || cx - r > W + 50 || cy + r < -50 || cy - r > H + 50) continue;
    c.fillStyle = "#f6f7f8"; c.beginPath(); c.arc(cx, cy, r * 1.04, 0, 2 * Math.PI); c.fill();
    c.strokeStyle = "rgba(14,17,22,.07)"; c.lineWidth = 1;
    for (const [, , b] of C.bands.slice(0, -1)) { c.beginPath(); c.arc(cx, cy, b * z + 0.5 * 0.025 * C.r * z, 0, 2 * Math.PI); c.stroke(); }
    if (C.sectors.length > 1) {
      c.beginPath();
      for (const [, a0] of C.sectors) { c.moveTo(cx + Math.cos(a0) * r * 0.1, cy + Math.sin(a0) * r * 0.1); c.lineTo(cx + Math.cos(a0) * r * 1.04, cy + Math.sin(a0) * r * 1.04); }
      c.stroke();
    }
  }
  // links: within a cluster faint; between clusters along their trunk, a little stronger
  const a = Math.min(0.4, 0.1 * Math.pow(zoom, 0.45)), lw = Math.min(1.2, 0.6 + 0.08 * zoom);
  for (const L of LAYERS) {
    if (!on[L]) continue;
    const p = EP[L], [r, gg, b] = EDGE[L], li = LAYERS.indexOf(L);
    for (const inter of [false, true]) {
      c.strokeStyle = `rgba(${r},${gg},${b},${inter ? a : a * 0.7})`; c.lineWidth = lw;
      c.beginPath();
      for (let j = 0; j < p.length; j += 2) {
        const u = p[j], w = p[j + 1];
        if ((KC[u] !== KC[w]) !== inter || (AL && !liveLink(li, j / 2))) continue;
        const x1 = X0(X[u]), y1 = Y0(Y[u]), x2 = X0(X[w]), y2 = Y0(Y[w]);
        if ((x1 < -40 && x2 < -40) || (x1 > W + 40 && x2 > W + 40) || (y1 < -40 && y2 < -40) || (y1 > H + 40 && y2 > H + 40)) continue;
        if (inter) { curve(u, w, SC); c.moveTo(x1, y1); c.bezierCurveTo(X0(SC[2]), Y0(SC[3]), X0(SC[4]), Y0(SC[5]), x2, y2); }
        else { c.moveTo(x1, y1); c.lineTo(x2, y2); }
      }
      c.stroke();
    }
  }
  // acts: smallest first; an outline once they are large enough to touch
  for (let q = 0; q < n; q++) {
    const k = order[q], x = X0(X[k]), y = Y0(Y[k]);
    if (x < -50 || x > W + 50 || y < -50 || y > H + 50) continue;
    if (AL && !AL[k]) {                                    // not yet there: a trace of its place
      c.fillStyle = "#e4e7eb"; c.fillRect(x - 0.6, y - 0.6, 1.2, 1.2);
      continue;
    }
    const r = rpx(k, z);
    c.fillStyle = COLS[CL[k]];
    c.beginPath(); c.arc(x, y, r, 0, 2 * Math.PI); c.fill();
    if (r > 3) { c.strokeStyle = "#ffffff"; c.lineWidth = 1; c.stroke(); }
  }
}
function picture(v) {
  const c = document.createElement("canvas");
  c.width = Math.round(W * dpr); c.height = Math.round(H * dpr);
  drawBase(c.getContext("2d"), v);
  return c;
}
function renderCache(v = view) { cache = picture(v); cacheV = { ...v }; }
function renderBase0() { base0V = { x: 0, y: 0, z: fitZ }; base0 = picture(base0V); }
function blit(img, v) {                                   // a picture rendered at view v, into the current view
  const s = view.z / v.z;
  g.drawImage(img, W / 2 * (1 - s) + (v.x - view.x) * view.z, H / 2 * (1 - s) + (v.y - view.y) * view.z, W * s, H * s);
}
function redraw() { if (!raf) raf = requestAnimationFrame(frame); }
function settle() {                                       // a sharp picture once the view rests
  clearTimeout(cacheTimer);
  cacheTimer = setTimeout(() => { renderCache(); still = performance.now(); redraw(); }, 140);
}

// ---------- the van Wijk–Nuij camera path (as in d3-interpolate's zoom): out, across, in
const RHO = Math.SQRT2;
function vanWijk(a, b) {
  const w0 = W / a.z, w1 = W / b.z, dx = b.x - a.x, dy = b.y - a.y, d2 = dx * dx + dy * dy;
  if (d2 < 1e-9) {
    const S = Math.log(w1 / w0) / RHO;
    return { S: Math.abs(S), f: (s) => ({ x: a.x + s * dx, y: a.y + s * dy, z: W / (w0 * Math.exp(RHO * s * S)) }) };
  }
  const d1 = Math.sqrt(d2), b0 = (w1 * w1 - w0 * w0 + 4 * d2) / (4 * w0 * d1), b1 = (w1 * w1 - w0 * w0 - 4 * d2) / (4 * w1 * d1);
  const r0 = Math.log(Math.sqrt(b0 * b0 + 1) - b0), r1 = Math.log(Math.sqrt(b1 * b1 + 1) - b1), S = (r1 - r0) / RHO;
  return { S: Math.abs(S), f: (s) => {
    const u = s * S, c0 = Math.cosh(r0), q = (w0 / (2 * d1)) * (c0 * Math.tanh(RHO * u + r0) - Math.sinh(r0));
    return { x: a.x + q * dx, y: a.y + q * dy, z: W / ((w0 * c0) / Math.cosh(RHO * u + r0)) };
  } };
}
function fly(target, frame = null) {
  aim = frame;
  if (!motion()) { flight = null; view = { ...target }; renderCache(); still = performance.now(); redraw(); return; }
  if (!base0) renderBase0();
  const a = { ...view }, P = vanWijk(a, target);
  flight = { a, b: { ...target }, f: P.f, t0: performance.now(), dur: Math.max(420, Math.min(1500, P.S * 780)) };
  renderCache(target);                                    // the destination, sharp on arrival
  redraw();
}
const fitView = () => ({ x: 0, y: 0, z: fitZ });
function frameCluster(c) {
  const C = CLU[c], m = W < 600 ? 22 : 44;
  return { x: C.x, y: C.y, z: Math.min((W - 2 * m) / (2.3 * C.r), (H - 2 * m) / (2.3 * C.r)) };
}
function frameAct(E) {                                    // the act, all it links to and its chain, in view
  let x0 = X[E.k], x1 = x0, y0 = Y[E.k], y1 = y0;
  for (const w of [...E.nodes.keys(), ...E.chain]) { x0 = Math.min(x0, X[w]); x1 = Math.max(x1, X[w]); y0 = Math.min(y0, Y[w]); y1 = Math.max(y1, Y[w]); }
  const bw = Math.max(60, x1 - x0) + 40, bh = Math.max(60, y1 - y0) + 40;
  const z = Math.min(fitZ * 14, Math.max(fitZ, Math.min((W - 2 * mx) / bw, (H - 2 * my) / bh)));
  return { x: (x0 + x1) / 2, y: (y0 + y1) / 2, z };
}

// ---------- one act and everything linked to it
function egoOf(k) {
  const links = [], nodes = new Map(), a = adj[k];
  for (let q = 0; q < a.length; q += 3) {
    const w = a[q], li = a[q + 1], j = a[q + 2], L = LAYERS[li];
    if (!on[L] || !liveLink(li, j)) continue;
    const dir = li === 2 ? 0 : EP[L][2 * j + 1] === w ? 1 : -1;      // 1: this act names the partner
    links.push({ w, li, j, dir, c: curve(k, w) });
    nodes.set(w, (nodes.get(w) || 0) | (1 << li));
  }
  const top = [...nodes.keys()].sort((p, q) => D[q] - D[p] || deg[q] - deg[p]);
  const chain = chainOf(k), up = [];
  for (let s = chain.length - 1; s > 0; s--) {            // from the act upwards
    const lo = chain[s], hi = chain[s - 1];
    up.push({ lo, hi, c: curve(lo, hi), art51: hi === BVk && CL[lo] === 0 && !!M.CT[AT[lo]] });
  }
  // moving points on the strongest links that have a direction: bases first, then by decisions
  const prio = (l) => (l.li === 0 ? 2 : 1) + Math.log1p(D[l.w]) / 30;
  const flow = links.filter((l) => l.dir).sort((p, q) => prio(q) - prio(p)).slice(0, 320).map((l, i) => ({ l, ph: (i * 0.6180339887) % 1 }));
  return { k, links, nodes, top, chain, up, flow, t0: performance.now() };
}
function veil(a) { g.fillStyle = `rgba(255,255,255,${a})`; g.fillRect(0, 0, W, H); }
function dot(w, a = 1, outline = "#fff") {
  const x = sx(X[w]), y = sy(Y[w]), r = Math.max(2.4, rpx(w));
  g.globalAlpha = a;
  g.fillStyle = COLS[CL[w]]; g.beginPath(); g.arc(x, y, r, 0, 2 * Math.PI); g.fill();
  g.strokeStyle = outline; g.lineWidth = outline === "#fff" ? 1 : 1.6; g.stroke();
  g.globalAlpha = 1;
}
const pointed = () => (hint >= 0 ? hint : hot && hot.t === "a" ? hot.i : kbd && kbd.t === "a" ? kbd.i : -1);
function drawEgo(E, now, alpha, full) {
  veil((full ? 0.84 : 0.64) * alpha);
  const grow = full && motion() ? out3((now - E.t0) / GROW) : 1;
  g.lineCap = "round";
  for (let li = 0; li < 3; li++) {
    if (!on[LAYERS[li]]) continue;
    const [r, gg, b] = EDGE[LAYERS[li]];
    g.strokeStyle = `rgba(${r},${gg},${b},${0.72 * alpha})`; g.lineWidth = 1.25;
    g.beginPath();
    for (const l of E.links) if (l.li === li) seg(l.c, grow);
    g.stroke();
  }
  // the link just travelled along, while the camera flies
  if (full && flight && from >= 0) {
    g.strokeStyle = css("--accent"); g.lineWidth = 2.6; g.beginPath();
    for (const l of E.links) if (l.w === from) seg(l.c);
    g.stroke();
  }
  // the chain of bases up to the Constitution: one line, cased in white, growing from the act upwards
  if (full && E.up.length) {
    const m = E.up.length, gc = motion() ? out3((now - E.t0) / (GROW + 250)) : 1;
    E.up.forEach((s, i) => {
      const p = Math.min(1, Math.max(0, gc * m - i));
      if (p <= 0) return;
      g.setLineDash([]); g.strokeStyle = `rgba(255,255,255,${0.95 * alpha})`; g.lineWidth = 5.5; g.beginPath(); seg(s.c, p); g.stroke();
      if (s.art51) g.setLineDash([6, 5]);
      g.strokeStyle = `rgba(14,17,22,${0.86 * alpha})`; g.lineWidth = 2.4; g.beginPath(); seg(s.c, p); g.stroke();
      g.setLineDash([]);
    });
  }
  // the partner pointed at: its links strong
  const em = pointed();
  if (em >= 0 && em !== E.k && E.nodes.has(em)) {
    for (const l of E.links) if (l.w === em) { const [r, gg, b] = EDGE[LAYERS[l.li]]; g.strokeStyle = `rgb(${r},${gg},${b})`; g.lineWidth = 2.8; g.beginPath(); seg(l.c); g.stroke(); }
  }
  // the acts: partners appear as their link reaches them
  const pa = alpha * Math.min(1, Math.max(0, (grow - 0.55) / 0.45));
  if (pa > 0) for (const w of E.nodes.keys()) dot(w, pa);
  if (full) for (const w of E.chain) if (w !== E.k) dot(w, alpha, css("--ink"));
  dot(E.k, alpha);
  // moving points: from the act that names to the act named
  let live = false;
  if (full && grow >= 1 && motion() && E.flow.length) {
    const age = now - E.t0 - GROW;
    if (age < FLOW) {
      live = true;
      const fade = alpha * Math.min(1, age / 400, (FLOW - age) / 1500);
      for (const p of E.flow) {
        const c = p.l.c, Lp = (Math.hypot(sx(c[6]) - sx(c[0]), sy(c[7]) - sy(c[1])) + Math.hypot(sx(c[2]) - sx(c[0]), sy(c[3]) - sy(c[1])) +
          Math.hypot(sx(c[4]) - sx(c[2]), sy(c[5]) - sy(c[3])) + Math.hypot(sx(c[6]) - sx(c[4]), sy(c[7]) - sy(c[5]))) / 2;
        if (Lp < 14) continue;
        let s = (p.ph + (now / 1000) * 70 / Lp) % 1;
        if (p.l.dir < 0) s = 1 - s;
        const [x, y] = at(c, s), [r, gg, b] = EDGE[LAYERS[p.l.li]];
        g.fillStyle = `rgba(${r},${gg},${b},${0.95 * fade})`;
        g.beginPath(); g.arc(sx(x), sy(y), 1.9, 0, 2 * Math.PI); g.fill();
      }
    }
  }
  return live || grow < 1;
}

// ---------- one jurisdiction: the rest steps back; its links to the rest stay
function extOf(c) {
  const C = CLU[c];
  if (!C.ext) {
    const list = [];
    LAYERS.forEach((L, li) => { const p = EP[L]; for (let j = 0; j < p.length; j += 2) if ((KC[p[j]] === c) !== (KC[p[j + 1]] === c)) list.push(li, j / 2); });
    C.ext = Int32Array.from(list);
  }
  return C.ext;
}
function extLinks(c, alpha) {
  const ex = extOf(c);
  g.lineWidth = 1;
  for (let li = 0; li < 3; li++) {
    const L = LAYERS[li];
    if (!on[L]) continue;
    const [r, gg, b] = EDGE[L], p = EP[L];
    g.strokeStyle = `rgba(${r},${gg},${b},${alpha})`;
    g.beginPath();
    for (let q = 0; q < ex.length; q += 2) if (ex[q] === li && liveLink(li, ex[q + 1])) { const j = ex[q + 1]; curve(p[2 * j], p[2 * j + 1], SC); seg(SC); }
    g.stroke();
  }
}
function hole(c, a, k = 1.07) {                           // a veil over everything but one disc
  const C = CLU[c], cx = sx(C.x), cy = sy(C.y), r = C.r * view.z * k;
  g.fillStyle = `rgba(255,255,255,${a})`;
  g.beginPath(); g.rect(0, 0, W, H); g.moveTo(cx + r, cy); g.arc(cx, cy, r, 0, 2 * Math.PI, true); g.fill("evenodd");
}
function rim(c, a, colour = "14,17,22", w = 1.5) {
  const C = CLU[c];
  g.strokeStyle = `rgba(${colour},${a})`; g.lineWidth = w;
  g.beginPath(); g.arc(sx(C.x), sy(C.y), C.r * view.z * 1.06, 0, 2 * Math.PI); g.stroke();
}

// ---------- labels
const boxes = [];
let cboxes = [];                                          // the jurisdictions' names, for the pointer
const free = (x0, y0, x1, y1) => { for (const b of boxes) if (x0 < b[2] && x1 > b[0] && y0 < b[3] && y1 > b[1]) return false; boxes.push([x0, y0, x1, y1]); return true; };
function text(s, x, y, font, colour, align = "left") {
  g.font = font; g.textAlign = align; g.textBaseline = "middle";
  g.lineWidth = 3.5; g.strokeStyle = "rgba(255,255,255,.92)"; g.lineJoin = "round"; g.strokeText(s, x, y);
  g.fillStyle = colour; g.fillText(s, x, y);
}
function place(s, x, y, font, colour, align = "left") {   // a label if it fits; its box
  g.font = font;
  const w = g.measureText(s).width, x0 = align === "center" ? x - w / 2 : align === "right" ? x - w : x;
  if (!free(x0 - 3, y - 8, x0 + w + 3, y + 8)) return null;
  text(s, x, y, font, colour, align);
  return [x0 - 3, y - 9, x0 + w + 3, y + 9];
}
function clusterName(c) {
  const key = CLU[c].key;
  return key === "fed" ? t("fedLaw") : key === "int" ? t("intLaw") : cantonName(key.slice(3));
}
function areaName(d) {
  const i = M.byId.get("c" + d);
  return i != null ? `${d} ${(M.L[i] || "").split(/\s+[–-]\s+/)[0]}` : String(d);
}
function actLabel(w, font, colour) {
  const s = labelCt(AT[w]);
  if (!s || s.length > 40) return false;
  const x = sx(X[w]), y = sy(Y[w]);
  if (x < -20 || x > W + 20 || y < 0 || y > H) return false;
  return !!place(s, x + Math.max(2.4, rpx(w)) + 4, y, font, colour);
}
function labels(now, moving) {
  boxes.length = 0; cboxes = [];
  const ink = css("--ink"), ink2 = css("--ink-2"), ink3 = css("--ink-3"), zoom = view.z / fitZ;
  const la = moving ? 0 : out3((now - still) / 240);
  const E = focus.lvl === 2 ? ego : val("prev", now) > 0.5 ? prevEgo : null;
  // the act in focus, its chain and the partner pointed at come first
  if (E) {
    actLabel(E.k, `680 14px ${SANS}`, ink);
    if (focus.lvl === 2) for (const w of E.chain) if (w !== E.k) actLabel(w, `640 12px ${SANS}`, ink);
    const em = pointed();
    if (em >= 0 && em !== E.k) actLabel(em, `640 12px ${SANS}`, ink);
  } else if (hint >= 0) actLabel(hint, `640 12px ${SANS}`, ink);
  // the jurisdictions, outside their disc
  for (let c = 0; c < CLU.length; c++) {
    const C = CLU[c], cx = sx(C.x), cy = sy(C.y), r = C.r * view.z;
    if (cx + r < 0 || cx - r > W || cy + r < 0 || cy - r > H) continue;
    const strong = c === focus.c || c === chotC, col = focus.lvl === 2 && !strong ? ink2 : ink;
    if (C.key === "fed" || C.key === "int") {
      const y = C.key === "fed" ? cy + r + 18 : cy - r - 16, b = place(clusterName(c), cx, y, `650 ${zoom > 2.5 ? 15 : 13}px ${SANS}`, col, "center");
      if (b) cboxes.push([...b, c]);
      if (C.sectors.length > 1 && (C.key === "fed" ? zoom > 0.9 : zoom > 2.2) && la > 0) {
        g.globalAlpha = la;
        for (const [d, a0, a1] of C.sectors) {           // SR areas round the federal core
          const am = (a0 + a1) / 2, rr = r + 10 + (zoom > 3 ? 4 : 0), x = cx + Math.cos(am) * rr, y2 = cy + Math.sin(am) * rr;
          if ((a1 - a0) * r > 14) place(areaName(C.key === "fed" ? String(d) : `0.${d}`), x, y2, `560 11.5px ${SANS}`, ink2, Math.cos(am) >= 0 ? "left" : "right");
        }
        g.globalAlpha = 1;
      }
      continue;
    }
    const ang = Math.atan2(C.y, C.x), rr = r + 14, x = cx + Math.cos(ang) * rr, y = cy + Math.sin(ang) * rr;
    const f = `620 ${zoom > 2.5 ? 14 : 12.5}px ${SANS}`, al = Math.abs(Math.cos(ang)) < 0.35 ? "center" : Math.cos(ang) > 0 ? "left" : "right";
    for (const s of zoom < 0.75 || (W < 600 && zoom < 1.8) ? [C.id] : [cantonName(C.id), C.id]) {
      const b = place(s, x, y, f, col, al);
      if (b) { cboxes.push([...b, c]); break; }
    }
  }
  if (la <= 0) return;
  g.globalAlpha = la;
  // the levels, on a jurisdiction large enough to read them
  for (let c = 0; c < CLU.length; c++) {
    const C = CLU[c], r = C.r * view.z;
    if (r < 170 || C.key === "int") continue;
    const cx = sx(C.x), cy = sy(C.y);
    if (cx + r < 0 || cx - r > W || cy + r < 0 || cy - r > H) continue;
    g.letterSpacing = "0.07em";
    for (const [l, r0, r1] of C.bands) {
      if (l < 1 || (r1 - r0) * view.z < 16) continue;
      const y = cy - ((r0 + r1) / 2) * view.z;
      if (y > 10 && y < H - 10) place((l === 4 ? t("c5") : t("c" + l)).toUpperCase(), cx, y, `640 10.5px ${SANS}`, ink3, "center");
    }
    g.letterSpacing = "0px";
  }
  // partners of the act in focus, most cited first; otherwise the acts most cited, where there is room
  if (E) {
    const font = `560 11px ${SANS}`, max = focus.lvl === 2 ? 36 : 14;
    let shown = 0;
    for (const w of E.top) { if (shown >= max) break; if (actLabel(w, font, ink2)) shown++; }
  } else if (zoom >= 0.6) {
    const cand = [];
    for (let k = 0; k < n; k++) {
      const x = sx(X[k]), y = sy(Y[k]);
      if (x < 0 || x > W || y < 0 || y > H || (AL && !AL[k])) continue;
      if (rpx(k) >= 2.4 || zoom > 6 || CLU[KC[k]].r * view.z > 260) cand.push(k);
    }
    const mine = (k) => (focus.lvl === 1 && KC[k] === focus.c ? 1 : 0);
    cand.sort((a, b) => mine(b) - mine(a) || D[b] - D[a] || deg[b] - deg[a]);
    const max = Math.min(160, Math.round((W * H) / 6500)), f = `600 11px ${SANS}`;
    let shown = 0;
    for (const k of cand) {
      if (shown >= max) break;
      const s = tileLabel(AT[k]);
      if (!s || s.length > 34) continue;
      if (place(s, sx(X[k]) + rpx(k) + 3, sy(Y[k]), f, ink2)) shown++;
    }
  }
  g.globalAlpha = 1;
}

// ---------- marks on top: what is pointed at, chosen by key, shown from the panel
function ringAt(x, y, r, colour, w, dash) {
  g.strokeStyle = colour; g.lineWidth = w; if (dash) g.setLineDash(dash);
  g.beginPath(); g.arc(x, y, r, 0, 2 * Math.PI); g.stroke(); g.setLineDash([]);
}
function marks(now) {
  const accent = css("--accent"), ink = css("--ink");
  let busy = false;
  if (focus.lvl === 2) {
    const k = focus.k, x = sx(X[k]), y = sy(Y[k]), r = Math.max(2.4, rpx(k));
    ringAt(x, y, r + 3.5, accent, 2);
    if (motion() && ego && now - ego.t0 < GROW + 1600) {   // one ripple as the links arrive
      const u = (now - ego.t0) / (GROW + 1600);
      g.globalAlpha = Math.max(0, 1 - u); ringAt(x, y, r + 4 + 34 * out3(u), accent, 1.5); g.globalAlpha = 1;
      busy = true;
    }
  }
  if (hot && hot.t === "a" && hot.i !== focus.k) { const k = hot.i; ringAt(sx(X[k]), sy(Y[k]), Math.max(2.4, rpx(k)) + 2.5, ink, 1.5); }
  if (kbd) {
    if (kbd.t === "a") ringAt(sx(X[kbd.i]), sy(Y[kbd.i]), Math.max(2.4, rpx(kbd.i)) + 4, accent, 2, [3, 3]);
    else rim(kbd.i, 1, "226,0,26", 2);
  }
  if (hint >= 0) {
    const x = sx(X[hint]), y = sy(Y[hint]), r = Math.max(2.4, rpx(hint));
    ringAt(x, y, r + 3, ink, 2);
    if (motion()) { const u = (now % 1300) / 1300; g.globalAlpha = 1 - u; ringAt(x, y, r + 4 + 16 * u, ink, 1.5); g.globalAlpha = 1; busy = true; }
  }
  return busy;
}

// ---------- the overview map in the corner, once the view is closer than the whole
function drawMini() {
  const show = view.z > fitZ * 1.8;
  if (mini.hidden !== !show) mini.hidden = !show;
  if (!show) return;
  const key = `${view.x.toFixed(1)}|${view.y.toFixed(1)}|${view.z.toFixed(4)}|${W}|${H}|${focus.c}`;
  if (key === miniKey) return;
  miniKey = key;
  const S = mini.clientWidth || 112;
  if (mini.width !== Math.round(S * dpr)) { mini.width = Math.round(S * dpr); mini.height = Math.round(S * dpr); }
  const s = S / 2160, o = S / 2;
  mg.setTransform(dpr, 0, 0, dpr, 0, 0);
  mg.clearRect(0, 0, S, S);
  for (let c = 0; c < CLU.length; c++) {
    const C = CLU[c];
    mg.fillStyle = c === focus.c ? "#c9ced6" : "#e6e9ed";
    mg.beginPath(); mg.arc(o + C.x * s, o + C.y * s, Math.max(1.5, C.r * s), 0, 2 * Math.PI); mg.fill();
  }
  const vw = (W / view.z) * s, vh = (H / view.z) * s, vx = o + (view.x * s) - vw / 2, vy = o + (view.y * s) - vh / 2;
  mg.strokeStyle = css("--accent"); mg.lineWidth = 1.5;
  mg.strokeRect(Math.max(1, vx), Math.max(1, vy), Math.min(S - 2, vw), Math.min(S - 2, vh));
}

// ---------- the frame
function frame(now) {
  raf = 0;
  now = now || performance.now();
  let busy = false;
  if (flight) {
    const u = Math.min(1, (now - flight.t0) / flight.dur);
    view = u < 1 ? flight.f(inout(u)) : { ...flight.b };
    if (u >= 1) { flight = null; still = now; } else busy = true;
  }
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  const same = cacheV && cacheV.x === view.x && cacheV.y === view.y && cacheV.z === view.z;
  if (!same) { g.fillStyle = "#ffffff"; g.fillRect(0, 0, W, H); if (base0) blit(base0, base0V); }
  if (cache) blit(cache, cacheV);
  const moving = !!flight || !!(drag && drag.moved) || !!pinch || now - wheelT < 160;
  // a jurisdiction open: the rest steps back, its links to the rest stay
  const sp = val("spot", now);
  if (sp > 0.002 && spotC >= 0) { hole(spotC, 0.6 * sp); extLinks(spotC, 0.3 * sp); }
  // a jurisdiction pointed at
  const ch = val("chot", now);
  if (ch > 0.002 && chotC >= 0) {
    if (focus.lvl === 0) { hole(chotC, 0.5 * ch); extLinks(chotC, 0.42 * ch); }
    if (chotC !== focus.c) rim(chotC, 0.6 * ch);
  }
  // an act: in focus, or previewed while pointed at
  const sv = val("sel", now);
  if (ego && sv > 0.002) busy = drawEgo(ego, now, sv, focus.lvl === 2) || busy;
  else if (ego && focus.lvl !== 2) ego = null;
  const pv = val("prev", now);
  if (focus.lvl !== 2 && prevEgo && pv > 0.002) drawEgo(prevEgo, now, pv, false);
  labels(now, moving);
  busy = marks(now) || busy;
  if (!moving || flight) drawMini();
  busy = busy || dwell(now) || tweening(now) || (!moving && now - still < 260) || moving;
  if (busy) redraw();
}
// a preview once the pointer has rested on an act or a jurisdiction for a moment
function dwell(now) {
  if (!hot) return false;
  if (now - hotT < DWELL) return true;
  if (hot.t === "a" && focus.lvl < 2 && prevK !== hot.i && !drag) { prevK = hot.i; prevEgo = egoOf(hot.i); tw("prev", 1, 180); }
  if (hot.t === "c" && chotK !== hot.i) { chotK = chotC = hot.i; tw("chot", 1, 200); }
  return false;
}

// ---------- the pointer
function nearest(wx, wy, rad) {
  const gx = Math.floor(wx / GS), gy = Math.floor(wy / GS), span = Math.ceil(rad / GS) + 1;
  let best = -1, bd = Infinity;
  for (let a = gx - span; a <= gx + span; a++) for (let b = gy - span; b <= gy + span; b++) {
    const cell = grid.get(a + ":" + b); if (!cell) continue;
    for (const k of cell) {
      if (AL && !AL[k]) continue;
      const d = Math.hypot(X[k] - wx, Y[k] - wy), lim = Math.max(rad, RW[k] + 2 / view.z);
      if (d < lim && d < bd) { bd = d; best = k; }
    }
  }
  return best;
}
// acts can be pointed at once they can be told apart: large ones always, the rest inside a
// jurisdiction shown large enough; before that the pointer finds the jurisdiction
const pickable = (k) => rpx(k) >= 3.4 || CLU[KC[k]].r * view.z >= 130;
function hit(px, py, touch) {
  const wx = view.x + (px - W / 2) / view.z, wy = view.y + (py - H / 2) / view.z;
  if (focus.lvl === 2 && ego) {                           // the act in focus, its partners and its chain first
    let best = -1, bd = touch ? 22 : 12;
    const test = (w) => { const d = Math.hypot(sx(X[w]) - px, sy(Y[w]) - py) - Math.max(0, rpx(w) - 3); if (d < bd) { bd = d; best = w; } };
    test(ego.k); for (const w of ego.nodes.keys()) test(w); for (const w of ego.chain) test(w);
    if (best >= 0) return { t: "a", i: best };
  }
  const k = nearest(wx, wy, (touch ? 16 : 10) / view.z);
  if (k >= 0 && pickable(k)) return { t: "a", i: k };
  for (const b of cboxes) if (px >= b[0] && px <= b[2] && py >= b[1] && py <= b[3]) return { t: "c", i: b[4] };
  let bc = -1, bd = Infinity;
  for (let c = 0; c < CLU.length; c++) { const C = CLU[c], d = Math.hypot(wx - C.x, wy - C.y) / C.r; if (d < 1.08 && d < bd) { bd = d; bc = c; } }
  return bc >= 0 ? { t: "c", i: bc } : null;
}
const sameItem = (a, b) => (!a && !b) || (a && b && a.t === b.t && a.i === b.i);
function setHot(it, e) {
  if (!sameItem(it, hot)) {
    hot = it; hotT = performance.now();
    if (!it || it.t !== "a") { prevK = -1; if (hint < 0) tw("prev", 0, 160); }
    if (!it || it.t !== "c") { chotK = -1; tw("chot", 0, 160); }
    redraw();
  }
  tip(it, e && e.clientX, e && e.clientY);
  cv.style.cursor = it ? "pointer" : "grab";
}
// what links the act pointed at with the act in focus, in words
function relations(k, w) {
  const out = [], K = labelCt(AT[k]);
  if (!ego) return out;
  for (const l of ego.links) {
    if (l.w !== w) continue;
    if (l.li === 0) out.push(l.dir > 0 ? t("relOn", K, fmtArts(EI.bases[l.j], AT[w])) : t("relUnder", K, fmtArts(EI.bases[l.j], AT[k])));
    else if (l.li === 1) out.push(l.dir > 0 ? t("relRefTo", K, num(EI.legis[l.j])) : t("relRefBy", K, num(EI.legis[l.j])));
    else out.push(t("relCo", K, num(EI.cocite[l.j])));
  }
  if (!out.length && ego.chain.includes(w)) out.push(t("relChain", K));
  return out;
}
function tip(it, cx, cy) {
  const el = $("tip");
  if (!it || cx == null || coarse()) { el.hidden = true; return; }
  let html;
  if (it.t === "c") {
    const C = CLU[it.i];
    html = `<b>${esc(clusterName(it.i))}</b><span class="t2">${esc(t("netCTip", num(C.mem.length), num(C.out[0] + C.out[1] + C.out[2])))}</span>` +
      (!(focus.lvl === 1 && focus.c === it.i) ? `<span class="t3">${esc(t("netOpen"))}</span>` : "");
  } else {
    const k = it.i, i = AT[k], rel = focus.lvl === 2 && k !== focus.k ? relations(focus.k, k) : [];
    const act = k === focus.k ? "" : focus.lvl === 2 && (ego.nodes.has(k) || ego.chain.includes(k)) ? t("netFollow") : focus.lvl === 2 ? t("netSwitch") : "";
    html = `<b>${esc(labelCt(i))}</b>${title(i) && title(i) !== label(i) ? `<span class="t2">${esc(title(i).length > 150 ? title(i).slice(0, 148) + "…" : title(i))}</span>` : ""}` +
      rel.map((r) => `<span class="t4">${esc(r)}</span>`).join("") +
      `<span class="t3"><i style="background:${COLS[CL[k]]}"></i>${esc(t(CL[k] === 6 ? "levelUnknown" : "c" + CL[k]))} · ${esc(t("nLinks", num(deg[k])))}` +
      `${TV.TIME.on && TV.bornOf(i) ? " · " + esc(t(live(k) ? "timeSince" : "timeNotYet", TV.bornOf(i))) : ""}</span>` +
      (act ? `<span class="t3">${esc(act)}</span>` : "");
  }
  el.innerHTML = html;
  el.hidden = false;
  const tw2 = el.offsetWidth, th = el.offsetHeight;
  let x = cx + 14, y = cy + 16;
  if (x + tw2 > innerWidth - 8) x = cx - tw2 - 12;
  if (y + th > innerHeight - 8) y = cy - th - 12;
  el.style.left = x + "px"; el.style.top = y + "px";
}
// what a click does: an act opens with its links; a jurisdiction opens; elsewhere one step back
function learnt(l) { const s = +(store("slm-net-learnt") || 0); if (!(s & (1 << l))) store("slm-net-learnt", String(s | (1 << l))); }
function activate(it) {
  if (!it) { if (focus.lvl > 0) up(false); return; }
  learnt(focus.lvl);
  if (it.t === "a") {
    if (!(focus.lvl === 2 && it.i === focus.k)) ctx.go("net/" + idOf(AT[it.i]));
    else if (panelOff) openPanel();                      // the chosen act again: its panel comes back, the view stays
  }
  else if (!(focus.lvl === 1 && focus.c === it.i)) ctx.go("net/" + CLU[it.i].id);
}
function closePanel() {                                   // × on the act's panel: the panel goes, the act stays chosen
  panelOff = true; holdPos();
  ctx.panel.hide();
  hints(); redraw();
}
function openPanel() {
  panelOff = false; holdPos();
  ctx.panel.node(AT[focus.k], { go: ctx.go, close: closePanel, closable: true });
  redraw();
}
let holdT = 0;
function holdPos() {                                      // the stage resizes when the panel goes or comes: keep the view
  keepPos = true; clearTimeout(holdT);
  holdT = setTimeout(() => { keepPos = false; }, 600);   // no resize followed (phone sheet): nothing to keep
}
function up(flyUp = true) {
  if (focus.lvl === 2) { noFly = !flyUp; ctx.go("net/" + CLU[focus.c].id); }
  else if (focus.lvl === 1) ctx.go("net");
  else if (Math.abs(view.z / fitZ - 1) > 0.02 || Math.hypot(view.x, view.y) > 1) fly(fitView(), fitView);
}

// ---------- the keyboard: arrows move to the nearest item that way, Enter opens, Escape goes up
function items() {
  if (focus.lvl === 0) return CLU.map((_, c) => ({ t: "c", i: c }));
  if (focus.lvl === 1) return CLU[focus.c].mem.map((k) => ({ t: "a", i: k }));
  return [...new Set([focus.k, ...ego.nodes.keys(), ...ego.chain])].map((k) => ({ t: "a", i: k }));
}
const posOf = (it) => (it.t === "a" ? { x: X[it.i], y: Y[it.i] } : { x: CLU[it.i].x, y: CLU[it.i].y });
function move(dx, dy) {
  const cur = kbd ? posOf(kbd) : focus.lvl === 2 ? posOf({ t: "a", i: focus.k }) : focus.lvl === 1 ? posOf({ t: "c", i: focus.c }) : { x: view.x, y: view.y };
  let best = null, bs = Infinity;
  for (const it of items()) {
    if (kbd && sameItem(it, kbd)) continue;
    const p = posOf(it), vx = p.x - cur.x, vy = p.y - cur.y, along = vx * dx + vy * dy;
    if (along <= 1e-6) continue;
    const s = along + 2.2 * Math.abs(vx * dy - vy * dx);
    if (s < bs) { bs = s; best = it; }
  }
  if (!best) return;
  kbd = best;
  const p = posOf(best);
  if (sx(p.x) < 50 || sx(p.x) > W - 50 || sy(p.y) < 50 || sy(p.y) > H - 50) fly({ x: p.x, y: p.y, z: view.z });
  if (best.t === "a" && focus.lvl < 2) { prevK = best.i; prevEgo = egoOf(best.i); tw("prev", 1, 180); }
  if (best.t === "c") { chotK = chotC = best.i; tw("chot", 1, 200); }
  const r = cv.getBoundingClientRect();
  tip(best, r.left + sx(p.x), r.top + sy(p.y));
  const rel = best.t === "a" && focus.lvl === 2 && best.i !== focus.k ? relations(focus.k, best.i) : [];
  $("nlive").textContent = (best.t === "c" ? clusterName(best.i) : labelCt(AT[best.i])) + (rel.length ? ". " + rel.join(". ") : "");
  redraw();
}

function wire() {
  const pts = new Map();
  const local = (e) => { const r = cv.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
  cv.addEventListener("pointerdown", (e) => {
    cv.setPointerCapture(e.pointerId);
    $("nhint").classList.add("gone");
    pts.set(e.pointerId, [e.clientX, e.clientY]);
    if (pts.size === 2) { const [a, b] = [...pts.values()]; pinch = { d: Math.hypot(a[0] - b[0], a[1] - b[1]), z: view.z }; drag = null; }
    else drag = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, moved: false };
    if (flight) { flight = null; renderCache(); }
    aim = null;
  });
  cv.addEventListener("pointermove", (e) => {
    if (pts.has(e.pointerId)) pts.set(e.pointerId, [e.clientX, e.clientY]);
    if (pinch && pts.size === 2) {
      const [a, b] = [...pts.values()], d = Math.hypot(a[0] - b[0], a[1] - b[1]);
      view = { ...view, z: Math.min(fitZ * 60, Math.max(fitZ * 0.6, pinch.z * (d / pinch.d))) };
      redraw(); settle(); return;
    }
    if (drag) {
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 4) drag.moved = true;
      if (drag.moved) { view = { ...view, x: drag.vx - dx / view.z, y: drag.vy - dy / view.z }; setHot(null); cv.style.cursor = "grabbing"; redraw(); settle(); return; }
    }
    if (e.pointerType === "touch") return;
    const [px, py] = local(e);
    setHot(hit(px, py, false), e);
  });
  const end = (e) => {
    pts.delete(e.pointerId);
    if (pinch && pts.size < 2) { pinch = null; settle(); }
    if (drag && !drag.moved && e.type === "pointerup") { const [px, py] = local(e); kbd = null; activate(hit(px, py, e.pointerType === "touch")); }
    drag = null; redraw();
  };
  cv.addEventListener("pointerup", end); cv.addEventListener("pointercancel", end);
  cv.addEventListener("pointerleave", () => setHot(null));
  cv.addEventListener("wheel", (e) => {
    e.preventDefault();
    const [px, py] = local(e);
    const wx = view.x + (px - W / 2) / view.z, wy = view.y + (py - H / 2) / view.z;
    const z = Math.min(fitZ * 60, Math.max(fitZ * 0.6, view.z * Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0018))));
    flight = null; aim = null;
    view = { x: wx - (px - W / 2) / z, y: wy - (py - H / 2) / z, z };
    wheelT = performance.now(); setHot(null); redraw(); settle();
  }, { passive: false });
  cv.addEventListener("dblclick", (e) => {
    const [px, py] = local(e);
    fly({ x: view.x + (px - W / 2) / view.z, y: view.y + (py - H / 2) / view.z, z: Math.min(fitZ * 60, view.z * 2.5) });
  });
  cv.addEventListener("keydown", (e) => {
    const d = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
    if (d && e.shiftKey) { e.preventDefault(); view = { ...view, x: view.x + d[0] * 80 / view.z, y: view.y + d[1] * 80 / view.z }; redraw(); settle(); }
    else if (d) { e.preventDefault(); move(d[0], d[1]); }
    else if (e.key === "Enter" || e.key === " ") { if (kbd) { e.preventDefault(); const it = kbd; kbd = null; activate(it); } }
    else if (e.key === "Escape") { e.preventDefault(); kbd = null; $("tip").hidden = true; up(true); }
    else if (e.key === "+" || e.key === "=") fly({ ...view, z: Math.min(fitZ * 60, view.z * 1.6) });
    else if (e.key === "-") fly({ ...view, z: Math.max(fitZ * 0.6, view.z / 1.6) });
    else if (e.key === "0") fly(fitView(), fitView);
  });
  cv.addEventListener("blur", () => { if (kbd) { kbd = null; $("tip").hidden = true; redraw(); } });
  mini.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    const r = mini.getBoundingClientRect(), S = r.width, s = S / 2160;
    fly({ x: (e.clientX - r.left - S / 2) / s, y: (e.clientY - r.top - S / 2) / s, z: view.z });
  });
  new ResizeObserver(() => { if (!$("v-net").hidden) resize(); }).observe(cv.parentElement);
  // the panel and the crumbs point at acts and jurisdictions here
  const hintOf = (a) => {
    const m = a && /#[a-z]{2}\/net\/(.+)$/.exec(a.getAttribute("href") || "");
    if (!m) return null;
    const id = decodeURIComponent(m[1]), i = M.byId.get(id);
    if (i != null && NET.idx.has(i)) return { t: "a", i: NET.idx.get(i) };
    const c = CLU.findIndex((C) => C.id === id);
    return c >= 0 ? { t: "c", i: c } : null;
  };
  for (const root of [$("dossier"), $("ntitle")]) {
    const over = (e) => { if (!$("v-net").hidden) setHint(hintOf(e.target.closest("a[href]"))); };
    const out = (e) => { const a = e.target.closest("a[href]"); if (a && !(e.relatedTarget && a.contains(e.relatedTarget))) setHint(null); };
    root.addEventListener("pointerover", over); root.addEventListener("focusin", over);
    root.addEventListener("pointerout", out); root.addEventListener("focusout", out);
  }
}
function setHint(it) {
  const k = it && it.t === "a" ? it.i : -1, c = it && it.t === "c" ? it.i : -1;
  if (k !== hint) {
    hint = k;
    if (focus.lvl < 2) { if (k >= 0) { prevK = k; prevEgo = egoOf(k); tw("prev", 1, 180); } else { prevK = -1; tw("prev", 0, 160); } }
  }
  if (c !== chotK) { chotK = c; if (c >= 0) { chotC = c; tw("chot", 1, 200); } else tw("chot", 0, 160); }
  redraw();
}
function resize() {
  const r = cv.parentElement.getBoundingClientRect();
  const w = Math.max(1, Math.floor(r.width)), h = Math.max(1, Math.floor(r.height));
  if (w === W && h === H && cache) return;
  dpr = Math.min(2, devicePixelRatio || 1);
  cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
  const first = !W, oldFit = fitZ, oldW = W, oldH = H;
  W = w; H = h;
  mx = W < 600 ? 38 : 90; my = W < 600 ? 30 : 40;         // room for the cantons' names round the ring
  fitZ = Math.min((W - 2 * mx) / 2000, (H - 2 * my) / 2000);
  if (first) view = fitView();
  else if (keepPos) {                                     // the panel closed: what is on screen stays where it is
    keepPos = false; aim = null;
    view = { ...view, x: view.x + (W - oldW) / (2 * view.z), y: view.y + (H - oldH) / (2 * view.z) };
  } else if (aim) {                                         // the panel opened: frame the same thing in the new stage
    const b = aim();
    if (flight) { const a = { ...view }, left = Math.max(260, flight.dur - (performance.now() - flight.t0)); flight = { a, b, f: vanWijk(a, b).f, t0: performance.now(), dur: left }; }
    else view = b;
  } else view = { ...view, z: view.z * (fitZ / oldFit) };
  renderBase0();
  renderCache(flight ? flight.b : view);
  miniKey = ""; redraw();
}

// ---------- the bar above, the hint, the legend, the panel
function crumbs() {
  const el = $("ntitle");
  if (focus.lvl === 0) { el.innerHTML = `<h1>${esc(t("netTitle"))}</h1>`; return; }
  const sep = `<span class="sep" aria-hidden="true">›</span>`;
  const a = (target, s) => `<a href="${href(target)}">${esc(s)}</a>`;
  const parts = [a("net", t("net"))];
  if (focus.lvl === 1) parts.push(`<span aria-current="page">${esc(clusterName(focus.c))}</span>`);
  else {
    // the act's chain of bases is its place in the law: Constitution › … › the act
    const ch = ego ? ego.chain : chainOf(focus.k), top = ch[0];
    if (top !== BVk && CL[top] !== 0) parts.push(a("net/" + CLU[KC[top]].id, clusterName(KC[top])));
    for (const j of ch.slice(0, -1)) parts.push(a("net/" + idOf(AT[j]), labelCt(AT[j])));
    parts.push(`<span aria-current="page">${esc(labelCt(AT[focus.k]))}</span>`);
  }
  el.innerHTML = `<nav class="crumbs" aria-label="${esc(t("netPath"))}"><button class="upbtn" id="nup" title="${esc(t("up"))}" aria-label="${esc(t("up"))}">${ICON.up}</button>${parts.join(sep)}</nav>`;
  $("nup").onclick = () => up(true);
}
let hintT = 0;
function hints() {
  const el = $("nhint"), seen = +(store("slm-net-learnt") || 0);
  clearTimeout(hintT);
  if (seen & (1 << focus.lvl)) { el.hidden = true; return; }
  el.textContent = t(`netHint${focus.lvl}${coarse() ? "t" : ""}`);
  el.hidden = false; el.classList.remove("gone");
  hintT = setTimeout(() => el.classList.add("gone"), 8000);   // it steps aside after a while, or at the first touch
}
function legend() {
  const lv = [0, 1, 2, 3, 4, 5].map((c) => `<span class="it">${sw(c)}<span>${esc(t("c" + c))}</span></span>`).join("");
  let end = `<span class="it num end">${esc(t("netCount", num(n), num(NET.unlinked)))}</span>`;
  if (focus.lvl === 2 && ego) {
    end = (ego.up.length ? `<span class="it end"><i class="ln" aria-hidden="true"></i>${esc(t("netChainKey"))}</span>` : "") +
      (motion() && ego.flow.length ? `<span class="it${ego.up.length ? "" : " end"}"><i class="pt" aria-hidden="true"></i>${esc(t("netFlowKey"))}</span>` : "");
  }
  $("nfoot").innerHTML = lv + end;
}
function controls() {
  const cnt = (L) => EP[L].length / 2;
  const past = TV.TIME.on && TV.TIME.year < TV.TIME.y1;
  $("nlayers").innerHTML = LAYERS.map((L) => `<button class="chip${past && L === "legis" ? " past" : ""}" data-layer="${L}" aria-pressed="${on[L]}"${past && L === "legis" ? ` title="${esc(t("timeToday"))}"` : ""}><i style="background:rgb(${EDGE[L].join(",")})"></i>${esc(t(LNAME[L]))} <span class="num">${esc(past && L === "legis" ? t("timeToday") : num(cnt(L)))}</span></button>`).join("") +
    `<button class="chip fit" id="nfit" title="${esc(t("netFit"))}" aria-label="${esc(t("netFit"))}">${ICON.fit}</button>`;
  cv.setAttribute("aria-label", t("netKeys"));
  mini.setAttribute("aria-label", t("netMini"));
}
const wide = () => !matchMedia("(max-width: 1180px)").matches;
const row = (i, v) => `<a class="r" href="${href("net/" + idOf(i))}"><span class="a">${sw(M.cls[i] >= 0 ? M.cls[i] : 6)}${esc(labelCt(i))}</span><span class="v">${esc(v)}</span>${title(i) && title(i) !== label(i) ? `<span class="b">${esc(title(i))}</span>` : ""}</a>`;
const layerKey = (cnt) => `<div class="stackkey" style="margin-top:14px">${LAYERS.map((L, li) => `<span><i class="sw" style="background:rgb(${EDGE[L].join(",")})"></i>${esc(t(LNAME[L]))}</span><span class="num">${esc(num(cnt(L, li)))}</span>`).join("")}</div>`;
function summary() {
  if (!wide()) { ctx.panel.hide(); return; }
  const most = [...Array(n).keys()].sort((a, b) => deg[b] - deg[a] || D[b] - D[a]).slice(0, 12);
  // federal acts most cantons rest on: stated bases from cantonal acts; the Constitution aside
  const by = new Map(), acts = new Map(), p = EP.bases;
  for (let j = 0; j < p.length; j += 2) {
    const a = AT[p[j]], b = AT[p[j + 1]];
    if (M.CT[a] && !M.CT[b] && !(M.S[b] || "").startsWith("0.")) { if (!by.has(b)) by.set(b, new Set()); by.get(b).add(M.CT[a]); acts.set(b, (acts.get(b) || 0) + 1); }
  }
  const bridges = [...by.entries()].filter(([b]) => M.S[b] !== "101").sort((x, y) => y[1].size - x[1].size || acts.get(y[0]) - acts.get(x[0])).slice(0, 12);
  ctx.panel.custom({ kicker: `<span>${esc(t("net"))}</span>`, h1: t("netTitle"), lede: t("netLede"),
    html: `<div class="stat2"><div class="stat"><b>${esc(num(n))}</b><span>${esc(t("netLinked"))}</span></div><div class="stat"><b>${esc(num(LAYERS.reduce((s, L) => s + EP[L].length / 2, 0)))}</b><span>${esc(t("netEdges"))}</span></div></div>` +
      layerKey((L) => EP[L].length / 2) +
      `<section><h2><span>${esc(t("netBridges"))}</span></h2><ul class="rows">${bridges.map(([i, s]) => `<li>${row(i, t("nCantons", num(s.size)))}</li>`).join("")}</ul></section>` +
      `<section><h2><span>${esc(t("netMost"))}</span></h2><ul class="rows">${most.map((k) => `<li>${row(AT[k], t("nLinks", num(deg[k])))}</li>`).join("")}</ul></section>` },
    { closable: false });
}
function clusterCard(c) {
  if (!wide()) { ctx.panel.hide(); return; }
  const C = CLU[c];
  const mine = (i) => (C.key.startsWith("ct:") ? M.CT[i] === C.id : !M.CT[i] && (M.S[i] || "").startsWith("0.") === (C.key === "int"));
  let total = 0;
  for (let i = 0; i < M.n; i++) if (M.K[i] === KIND.a && mine(i)) total++;
  const linked = C.mem.filter((k) => M.K[AT[k]] === KIND.a).length;
  const lv = [...C.lv.entries()].sort((a, b) => a[0] - b[0]);
  const levels = `<section><h2><span>${esc(t("netByLevel"))}</span></h2><ul class="rows">${lv.map(([cl, m]) =>
    `<li><div class="r"><span class="a">${sw(cl)}${esc(t(cl === 6 ? "levelUnknown" : "c" + cl))}</span><span class="v">${esc(num(m))}</span></div></li>`).join("")}</ul></section>`;
  const partners = [...C.to.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8);
  const withRows = partners.map(([q, m]) => `<li><a class="r" href="${href("net/" + CLU[q].id)}"><span class="a">${esc(clusterName(q))}</span><span class="v">${esc(t("nLinks", num(m)))}</span></a></li>`).join("");
  // for a canton: the federal acts its acts rest on most
  let fed = "";
  if (C.key.startsWith("ct:")) {
    const cnt = new Map(), p = EP.bases;
    for (let j = 0; j < p.length; j += 2) if (KC[p[j]] === c && CLU[KC[p[j + 1]]].key === "fed" && p[j + 1] !== BVk) cnt.set(p[j + 1], (cnt.get(p[j + 1]) || 0) + 1);
    const top = [...cnt.entries()].sort((a, b) => b[1] - a[1] || D[b[0]] - D[a[0]]).slice(0, 8);
    if (top.length) fed = `<section><h2><span>${esc(t("netFedBases"))}</span></h2><ul class="rows">${top.map(([k, m]) => `<li>${row(AT[k], t("nActs", num(m)))}</li>`).join("")}</ul></section>`;
  }
  const most = C.mem.slice().sort((a, b) => deg[b] - deg[a] || D[b] - D[a]).slice(0, 10);
  ctx.panel.custom({ kicker: `<span>${esc(t("net"))}</span>`, h1: clusterName(c), lede: t("netCLede", num(linked), num(total)),
    html: `<section><h2><span>${esc(t("netOut"))}</span></h2>${layerKey((L, li) => C.out[li]).replace(' style="margin-top:14px"', "")}</section>` +
      levels + (withRows ? `<section><h2><span>${esc(t("netWith"))}</span></h2><ul class="rows">${withRows}</ul></section>` : "") + fed +
      `<section><h2><span>${esc(t("netMost"))}</span></h2><ul class="rows">${most.map((k) => `<li>${row(AT[k], t("nLinks", num(deg[k])))}</li>`).join("")}</ul></section>` },
    { closable: true, close: () => ctx.go("net") });
}

export async function init(c) {
  ctx = c;
  cv = $("nc"); g = cv.getContext("2d");
  mini = $("nmini"); mg = mini.getContext("2d");
  readCols();
  await load();
  wire();
  $("nlayers").addEventListener("click", (e) => {
    if (e.target.closest("#nfit")) { fly(fitView(), fitView); return; }
    const b = e.target.closest("[data-layer]"); if (!b) return;
    on[b.dataset.layer] = !on[b.dataset.layer];
    if (!LAYERS.some((L) => on[L])) on[b.dataset.layer] = true;
    if (ego) { const t0 = ego.t0; ego = egoOf(ego.k); ego.t0 = t0 - FLOW; }
    if (prevEgo) prevEgo = egoOf(prevEgo.k);
    controls(); legend(); renderBase0(); renderCache(); redraw();
  });
  if (document.fonts) document.fonts.ready.then(() => redraw());
  let lastPast = null;
  TV.subscribe(() => {
    if ($("v-net").hidden) return;
    applyTime();
    if (ego) { const t0 = ego.t0; ego = egoOf(ego.k); ego.t0 = Math.min(t0, performance.now() - GROW - FLOW); }
    if (prevEgo) prevEgo = egoOf(prevEgo.k);
    const past = TV.TIME.on && TV.TIME.year < TV.TIME.y1;
    if (past !== lastPast) { lastPast = past; controls(); }
    if (TV.playing()) base0 = null; else renderBase0();      // the whole picture only once the years rest
    renderCache(); redraw();
    drawnFor = TV.TIME.on ? TV.TIME.year : 0;
  });
}
let drawnFor = null;                                       // the year the pictures were drawn for
export async function show(rest) {
  controls();
  applyTime();
  resize();
  const tk = TV.TIME.on ? TV.TIME.year : 0;
  if (drawnFor !== null && tk !== drawnFor) { renderBase0(); renderCache(); }
  drawnFor = tk;
  const id = rest.startsWith("net/") ? rest.slice(4) : "";
  let nf = { lvl: 0, c: -1, k: -1 };
  if (id) {
    const i = M.byId.get(id);
    if (i != null && NET.idx.has(i)) { const k = NET.idx.get(i); nf = { lvl: 2, c: KC[k], k }; }
    else { const c = CLU.findIndex((C) => C.id === id); if (c >= 0) nf = { lvl: 1, c, k: -1 }; }
  }
  const pf = focus, flyTo = !noFly;
  noFly = false;
  focus = nf; kbd = null; hint = -1; prevK = -1; chotK = -1;
  tw("prev", 0, 120); tw("chot", 0, 120);
  if (nf.lvl === 1) spotC = nf.c;
  tw("spot", nf.lvl === 1 ? 1 : 0, 280);
  if (nf.lvl === 2) {
    if (pf.lvl !== 2 || pf.k !== nf.k || !ego) {
      const prevAct = pf.lvl === 2 ? pf.k : -1;
      ego = egoOf(nf.k);
      from = prevAct >= 0 && ego.nodes.has(prevAct) ? prevAct : -1;   // the link travelled along, if there is one
      tw("sel", 1, 260);
      if (flyTo) fly(frameAct(ego), () => frameAct(ego));
      ego.t0 = flight ? flight.t0 + flight.dur : performance.now();
    }
    panelOff = false;
    ctx.panel.node(AT[nf.k], { go: ctx.go, close: closePanel, closable: true });
  } else {
    tw("sel", 0, 220); from = -1;
    if (nf.lvl === 1) {
      if (flyTo && (pf.lvl !== 1 || pf.c !== nf.c || !shown)) fly(frameCluster(nf.c), () => frameCluster(focus.c));
      clusterCard(nf.c);
    } else {
      if ((pf.lvl !== 0 || !shown) && flyTo) fly(fitView(), fitView);
      summary();
    }
  }
  shown = true;
  crumbs(); hints(); legend();
  $("tip").hidden = true;
  redraw();
}
export function refresh() {
  if ($("v-net").hidden) return;
  controls(); crumbs(); hints(); legend();
  if (focus.lvl === 2) { if (!panelOff) ctx.panel.node(AT[focus.k], { go: ctx.go, close: closePanel, closable: true }); }
  else if (focus.lvl === 1) clusterCard(focus.c); else summary();
  redraw();
}
