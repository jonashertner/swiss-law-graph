// The network (decision 29): every act with a link, in jurisdiction clusters laid out by
// layout/net.mjs — federal law in the centre, treaties above it, the 26 cantons on a ring in the
// direction of their capitals; inside each cluster rings by level (constitution in the middle). Three
// kinds of link, each its own colour: stated bases (Ingress), references in the text of the act
// (footnotes with an SR number), and co-citation by courts. Pointing at an act lights up its links
// across the whole network; a click opens it in the panel.
import { t, cantonName, lang } from "./i18n.js";
import { M, getJSON, idOf, label, labelCt, title } from "./data.js";
import { $, esc, num, sw, href, ICON } from "./util.js";
import { tileLabel } from "./treemap.js";

const LAYERS = ["bases", "legis", "cocite"];
const EDGE = { bases: [58, 65, 80], legis: [213, 94, 0], cocite: [123, 63, 168] };
const LNAME = { bases: "mBasis", legis: "mLaw", cocite: "mCourt" };
let ctx = {}, NET = null, ready = null;
let cv, g, W = 0, H = 0, dpr = 1;
let n = 0, AT, X, Y, RW, CL, D, CLU, KC, order, grid, GS = 24;
let E = {}, adj = [], deg;
let view = { x: 0, y: 0, z: 1 }, fitZ = 1, mx = 90, my = 40, anim = null;
let cache = null, cacheV = null, cacheTimer = 0, raf = 0;
let on = { bases: true, legis: true, cocite: true };
let hot = -1, sel = -1, drag = null, pinch = null;
const COLS = [];

// ---------- data
export function load() {
  if (!ready) ready = Promise.all([getJSON("data/net.json"), getJSON("data/links.json")]).then(([net, links]) => { build(net, links); return NET; });
  return ready;
}
export const has = (i) => !!NET && NET.idx.has(i);
function build(net, links) {
  n = net.ids.length;
  AT = Int32Array.from(net.ids);
  X = new Float32Array(n); Y = new Float32Array(n); RW = new Float32Array(n); CL = new Int8Array(n); D = new Float64Array(n);
  const idx = new Map();
  for (let k = 0; k < n; k++) {
    const i = AT[k];
    idx.set(i, k);
    X[k] = net.xy[2 * k] / net.scale; Y[k] = net.xy[2 * k + 1] / net.scale;
    D[k] = M.D[i]; CL[k] = M.cls[i] >= 0 ? M.cls[i] : 6;
    RW[k] = 2.1 + Math.min(15, Math.sqrt(D[k]) * 0.05);
  }
  KC = new Int16Array(n);
  CLU = Object.entries(net.clusters).map(([key, c]) => ({ key, x: c.c[0] / net.scale, y: c.c[1] / net.scale, r: c.r / net.scale, n: c.n,
    bands: Object.entries(c.bands).map(([l, [a, b]]) => [+l, a / net.scale, b / net.scale]), sectors: Object.entries(c.sectors).map(([s, [a, b]]) => [+s, a, b]) }));
  const ci = new Map(CLU.map((C, j) => [C.key, j]));
  for (let k = 0; k < n; k++) {
    const i = AT[k], key = M.CT[i] ? "ct:" + M.CT[i] : (M.S[i] || "").startsWith("0.") ? "int" : "fed";
    KC[k] = ci.has(key) ? ci.get(key) : 0;
  }
  for (const L of LAYERS) {
    const src = links[L], pairs = [];
    for (const e of src) {
      const a = idx.get(e[0]), b = idx.get(e[1]);
      if (a == null || b == null || a === b) continue;
      pairs.push(a, b);
    }
    E[L] = Int32Array.from(pairs);
  }
  adj = Array.from({ length: n }, () => []);
  LAYERS.forEach((L, li) => { const p = E[L]; for (let j = 0; j < p.length; j += 2) { adj[p[j]].push(p[j + 1], li); adj[p[j + 1]].push(p[j], li); } });
  deg = new Int32Array(n);
  for (let k = 0; k < n; k++) deg[k] = new Set(adj[k].filter((_, j) => j % 2 === 0)).size;
  order = Int32Array.from([...Array(n).keys()].sort((a, b) => RW[a] - RW[b]));
  grid = new Map();
  for (let k = 0; k < n; k++) { const key = Math.floor(X[k] / GS) + ":" + Math.floor(Y[k] / GS); if (!grid.has(key)) grid.set(key, []); grid.get(key).push(k); }
  NET = { idx, unlinked: net.unlinked };
}

// ---------- drawing
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const SANS = css("--sans") || "sans-serif";
const sx = (x) => W / 2 + (x - view.x) * view.z, sy = (y) => H / 2 + (y - view.y) * view.z;
const rpx = (k, z = view.z) => Math.min(42, Math.max(0.9, RW[k] * z));
function readCols() { for (let c = 0; c < 7; c++) COLS[c] = css(`--c${c}`); COLS[5] = "#c9c9c6"; }
function drawBase(c, v) {
  const Wd = W, Hd = H, z = v.z, X0 = (x) => Wd / 2 + (x - v.x) * z, Y0 = (y) => Hd / 2 + (y - v.y) * z;
  c.setTransform(dpr, 0, 0, dpr, 0, 0);
  c.fillStyle = "#ffffff"; c.fillRect(0, 0, Wd, Hd);
  const zoom = z / fitZ;
  // the clusters: a pale disc, rings between the levels, sectors of federal law and treaties
  for (const C of CLU) {
    const cx = X0(C.x), cy = Y0(C.y), r = C.r * z;
    if (cx + r < -50 || cx - r > Wd + 50 || cy + r < -50 || cy - r > Hd + 50) continue;
    c.fillStyle = "#f6f7f8"; c.beginPath(); c.arc(cx, cy, r * 1.04, 0, 2 * Math.PI); c.fill();
    c.strokeStyle = "rgba(14,17,22,.07)"; c.lineWidth = 1;
    for (const [, , b] of C.bands.slice(0, -1)) { c.beginPath(); c.arc(cx, cy, b * z + 0.5 * 0.025 * C.r * z, 0, 2 * Math.PI); c.stroke(); }
    if (C.sectors.length > 1) {
      c.beginPath();
      for (const [, a0] of C.sectors) { c.moveTo(cx + Math.cos(a0) * r * 0.1, cy + Math.sin(a0) * r * 0.1); c.lineTo(cx + Math.cos(a0) * r * 1.04, cy + Math.sin(a0) * r * 1.04); }
      c.stroke();
    }
  }
  // links: within a cluster straight and faint; between clusters a gentle arc, a little stronger
  const a = Math.min(0.4, 0.1 * Math.pow(zoom, 0.45)), lw = Math.min(1.2, 0.6 + 0.08 * zoom);
  const minX = -40, maxX = Wd + 40, minY = -40, maxY = Hd + 40;
  for (const L of LAYERS) {
    if (!on[L]) continue;
    const p = E[L], [r, gg, b] = EDGE[L];
    for (const inter of [false, true]) {
      c.strokeStyle = `rgba(${r},${gg},${b},${inter ? a : a * 0.7})`; c.lineWidth = lw;
      c.beginPath();
      for (let j = 0; j < p.length; j += 2) {
        const u = p[j], w = p[j + 1];
        const x1 = X0(X[u]), y1 = Y0(Y[u]), x2 = X0(X[w]), y2 = Y0(Y[w]);
        if ((x1 < minX && x2 < minX) || (x1 > maxX && x2 > maxX) || (y1 < minY && y2 < minY) || (y1 > maxY && y2 > maxY)) continue;
        const far = KC[u] !== KC[w];
        if (far !== inter) continue;
        if (far) route(c, u, w, X0, Y0, z);
        else { c.moveTo(x1, y1); c.lineTo(x2, y2); }
      }
      c.stroke();
    }
  }
  // acts: smallest first; an outline once they are large enough to touch
  for (let q = 0; q < n; q++) {
    const k = order[q], x = X0(X[k]), y = Y0(Y[k]);
    if (x < -50 || x > Wd + 50 || y < -50 || y > Hd + 50) continue;
    const r = rpx(k, z);
    c.fillStyle = COLS[CL[k]];
    c.beginPath(); c.arc(x, y, r, 0, 2 * Math.PI); c.fill();
    if (r > 3) { c.strokeStyle = "#ffffff"; c.lineWidth = 1; c.stroke(); }
  }
}
function renderCache() {
  if (!cache) cache = document.createElement("canvas");
  cache.width = Math.round(W * dpr); cache.height = Math.round(H * dpr);
  drawBase(cache.getContext("2d"), view);
  cacheV = { ...view };
}
function frame() {
  raf = 0;
  if (anim) {
    const u = Math.min(1, (performance.now() - anim.t0) / anim.dur), e = u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2;
    const lz = Math.log(anim.a.z) + (Math.log(anim.b.z) - Math.log(anim.a.z)) * e;
    view = { x: anim.a.x + (anim.b.x - anim.a.x) * e, y: anim.a.y + (anim.b.y - anim.a.y) * e, z: Math.exp(lz) };
    if (u >= 1) { anim = null; renderCache(); } else raf = requestAnimationFrame(frame);
  }
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.fillStyle = "#ffffff"; g.fillRect(0, 0, W, H);
  if (cache && cacheV) {                                   // the cached picture, moved and scaled to the view
    const s = view.z / cacheV.z;
    const ox = W / 2 - (cacheV.x - view.x) * view.z - (W / 2) * s, oy = H / 2 - (cacheV.y - view.y) * view.z - (H / 2) * s;
    g.drawImage(cache, ox, oy, W * s, H * s);
  }
  if (!anim && !drag && !pinch) labels();
  const focus = hot >= 0 ? hot : sel;
  if (focus >= 0) ego(focus);
  if (sel >= 0) { const x = sx(X[sel]), y = sy(Y[sel]), r = rpx(sel) + 3; g.strokeStyle = css("--accent"); g.lineWidth = 2; g.beginPath(); g.arc(x, y, r, 0, 2 * Math.PI); g.stroke(); }
}
function redraw() { if (!raf) raf = requestAnimationFrame(frame); }
function settle() {                                       // a sharp picture once the view rests
  clearTimeout(cacheTimer);
  cacheTimer = setTimeout(() => { renderCache(); redraw(); }, 140);
}

// A link between two clusters leaves its cluster at the edge facing the other and enters the other at
// the edge facing back: links between the same two clusters run together, as one trunk.
const BETA = 0.92;
function route(c, u, w, X0, Y0, z) {
  const A = CLU[KC[u]], B = CLU[KC[w]];
  const ax = X[u], ay = Y[u], bx = X[w], by = Y[w];
  let dx = B.x - A.x, dy = B.y - A.y;
  const d = Math.hypot(dx, dy) || 1; dx /= d; dy /= d;
  const p1x = A.x + dx * A.r * 0.92, p1y = A.y + dy * A.r * 0.92, p2x = B.x - dx * B.r * 0.92, p2y = B.y - dy * B.r * 0.92;
  const q = (s, t, k) => s + (t - s) * k;
  const c1x = q(q(ax, bx, 1 / 3), p1x, BETA), c1y = q(q(ay, by, 1 / 3), p1y, BETA);
  const c2x = q(q(ax, bx, 2 / 3), p2x, BETA), c2y = q(q(ay, by, 2 / 3), p2y, BETA);
  c.moveTo(X0(ax), Y0(ay));
  c.bezierCurveTo(X0(c1x), Y0(c1y), X0(c2x), Y0(c2y), X0(bx), Y0(by));
}

// labels: the jurisdictions, then the acts most cited, where there is room
const boxes = [];
const free = (x0, y0, x1, y1) => { for (const b of boxes) if (x0 < b[2] && x1 > b[0] && y0 < b[3] && y1 > b[1]) return false; boxes.push([x0, y0, x1, y1]); return true; };
function text(s, x, y, font, colour, align = "left", halo = true) {
  g.font = font; g.textAlign = align; g.textBaseline = "middle";
  if (halo) { g.lineWidth = 3.5; g.strokeStyle = "rgba(255,255,255,.92)"; g.lineJoin = "round"; g.strokeText(s, x, y); }
  g.fillStyle = colour; g.fillText(s, x, y);
}
function clusterName(key) {
  if (key === "fed") return t("fedLaw");
  if (key === "int") return t("intLaw");
  return cantonName(key.slice(3));
}
function areaName(d) {
  const i = M.byId.get("c" + d);
  return i != null ? `${d} ${(M.L[i] || "").split(/\s+[–-]\s+/)[0]}` : String(d);
}
function labels() {
  boxes.length = 0;
  const zoom = view.z / fitZ, ink = css("--ink"), ink2 = css("--ink-2"), ink3 = css("--ink-3");
  for (const C of CLU) {                                  // names of the clusters, outside their disc
    const cx = sx(C.x), cy = sy(C.y), r = C.r * view.z;
    if (cx + r < 0 || cx - r > W || cy + r < 0 || cy - r > H) continue;
    if (C.key === "fed" || C.key === "int") {
      const y = C.key === "fed" ? cy + r + 18 : cy - r - 16;
      const s = clusterName(C.key), f = `650 ${zoom > 2.5 ? 15 : 13}px ${SANS}`;
      g.font = f; const w = g.measureText(s).width;
      if (free(cx - w / 2 - 4, y - 9, cx + w / 2 + 4, y + 9)) text(s, cx, y, f, ink, "center");
      if (C.sectors.length > 1 && (C.key === "fed" ? zoom > 0.9 : zoom > 2.2)) {
        for (const [d, a0, a1] of C.sectors) {           // SR areas round the federal core
          const am = (a0 + a1) / 2, rr = r + 10 + (zoom > 3 ? 4 : 0), x = cx + Math.cos(am) * rr, y2 = cy + Math.sin(am) * rr;
          const s2 = C.key === "fed" ? areaName(d) : `0.${d}`, f2 = `560 11.5px ${SANS}`;
          g.font = f2; const w2 = g.measureText(s2).width, right = Math.cos(am) >= 0, x0 = right ? x : x - w2;
          if ((a1 - a0) * r > 14 && free(x0 - 2, y2 - 7, x0 + w2 + 2, y2 + 7)) text(s2, x, y2, f2, ink2, right ? "left" : "right");
        }
      }
      continue;
    }
    const ang = Math.atan2(C.y, C.x), rr = r + 14, x = cx + Math.cos(ang) * rr, y = cy + Math.sin(ang) * rr;
    const f = `620 ${zoom > 2.5 ? 14 : 12.5}px ${SANS}`, al = Math.abs(Math.cos(ang)) < 0.35 ? "center" : Math.cos(ang) > 0 ? "left" : "right";
    for (const s of zoom < 0.75 || (W < 600 && zoom < 1.8) ? [C.key.slice(3)] : [cantonName(C.key.slice(3)), C.key.slice(3)]) {
      g.font = f; const w = g.measureText(s).width, x0 = al === "center" ? x - w / 2 : al === "left" ? x : x - w;
      if (free(x0 - 3, y - 8, x0 + w + 3, y + 8)) { text(s, x, y, f, ink, al); break; }
    }
  }
  if (zoom < 0.6) return;
  // acts: by decisions, as many as fit without touching
  const cand = [];
  for (let k = 0; k < n; k++) {
    const x = sx(X[k]), y = sy(Y[k]);
    if (x < 0 || x > W || y < 0 || y > H) continue;
    if (rpx(k) >= 2.4 || zoom > 6) cand.push(k);
  }
  cand.sort((a, b) => D[b] - D[a] || deg[b] - deg[a]);
  const max = Math.min(140, Math.round((W * H) / 7000)), f = `600 11px ${SANS}`;
  g.font = f;
  let shown = 0;
  for (const k of cand) {
    if (shown >= max) break;
    const s = tileLabel(AT[k]);
    if (!s || s.length > 34) continue;
    const x = sx(X[k]) + rpx(k) + 3, y = sy(Y[k]), w = g.measureText(s).width;
    if (!free(x - 2, y - 7, x + w + 2, y + 7)) continue;
    text(s, x, y, f, ink2);
    shown++;
  }
}
// one act and everything linked to it, over a veil
function ego(k) {
  g.fillStyle = "rgba(255,255,255,.8)"; g.fillRect(0, 0, W, H);
  const nb = adj[k], seen = new Map();
  g.lineWidth = 1.2;
  for (let li = 0; li < 3; li++) {
    const L = LAYERS[li];
    if (!on[L]) continue;
    const [r, gg, b] = EDGE[L];
    g.strokeStyle = `rgba(${r},${gg},${b},.78)`;
    g.beginPath();
    const x1 = sx(X[k]), y1 = sy(Y[k]);
    for (let j = 0; j < nb.length; j += 2) {
      if (nb[j + 1] !== li) continue;
      const w = nb[j], x2 = sx(X[w]), y2 = sy(Y[w]);
      seen.set(w, (seen.get(w) || 0) | (1 << li));
      g.moveTo(x1, y1);
      if (KC[k] !== KC[w]) route(g, k, w, sx, sy, view.z);
      else g.lineTo(x2, y2);
    }
    g.stroke();
  }
  for (const w of [...seen.keys(), k]) {
    const x = sx(X[w]), y = sy(Y[w]), r = Math.max(2.2, rpx(w));
    g.fillStyle = COLS[CL[w]]; g.beginPath(); g.arc(x, y, r, 0, 2 * Math.PI); g.fill();
    g.strokeStyle = "#fff"; g.lineWidth = 1; g.stroke();
  }
  boxes.length = 0;
  const top = [...seen.keys()].sort((a, b) => D[b] - D[a]).slice(0, 28);
  const ink = css("--ink"), ink2 = css("--ink-2");
  const s0 = labelCt(AT[k]), x0 = sx(X[k]) + rpx(k) + 5, y0 = sy(Y[k]);
  g.font = `680 14px ${SANS}`; const w0 = g.measureText(s0).width;
  free(x0 - 2, y0 - 9, x0 + w0 + 2, y0 + 9); text(s0, x0, y0, `680 14px ${SANS}`, ink);
  g.font = `560 11px ${SANS}`;
  for (const w of top) {
    const s = labelCt(AT[w]);
    if (s.length > 34) continue;
    const x = sx(X[w]) + Math.max(2.2, rpx(w)) + 3, y = sy(Y[w]), tw = g.measureText(s).width;
    if (x < 0 || x > W || y < 0 || y > H) continue;
    if (free(x - 2, y - 7, x + tw + 2, y + 7)) text(s, x, y, `560 11px ${SANS}`, ink2);
  }
}

// ---------- the view and the hand
function fit(animate = true) {
  const target = { x: 0, y: 0, z: fitZ };
  go(target, animate);
}
function go(target, animate = true) {
  if (!animate || matchMedia("(prefers-reduced-motion: reduce)").matches) { view = target; renderCache(); redraw(); return; }
  anim = { a: { ...view }, b: target, t0: performance.now(), dur: 700 };
  redraw();
}
function flyTo(k) {                                       // the act and all it links to, in view
  let x0 = X[k], x1 = X[k], y0 = Y[k], y1 = Y[k];
  for (let j = 0; j < adj[k].length; j += 2) {
    if (!on[LAYERS[adj[k][j + 1]]]) continue;
    const w = adj[k][j];
    x0 = Math.min(x0, X[w]); x1 = Math.max(x1, X[w]); y0 = Math.min(y0, Y[w]); y1 = Math.max(y1, Y[w]);
  }
  const pad = 40, bw = Math.max(60, x1 - x0) + pad, bh = Math.max(60, y1 - y0) + pad;
  const z = Math.min(fitZ * 14, Math.max(fitZ, Math.min((W - 2 * mx) / bw, (H - 2 * my) / bh)));
  go({ x: (x0 + x1) / 2, y: (y0 + y1) / 2, z });
}
function resize() {
  const r = cv.parentElement.getBoundingClientRect();
  const w = Math.max(1, Math.floor(r.width)), h = Math.max(1, Math.floor(r.height));
  dpr = Math.min(2, devicePixelRatio || 1);
  cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
  const first = !W;
  W = w; H = h;
  const oldFit = fitZ;
  mx = W < 600 ? 38 : 90; my = W < 600 ? 30 : 40;         // room for the cantons' names round the ring
  fitZ = Math.min((W - 2 * mx) / 2000, (H - 2 * my) / 2000);
  if (first) view = { x: 0, y: 0, z: fitZ };
  else { const s = fitZ / oldFit; view.z *= s; if (anim) { anim.a.z *= s; anim.b.z *= s; } }   // the sheet opened mid-flight
  renderCache(); redraw();
}
function pick(px, py) {
  const wx = view.x + (px - W / 2) / view.z, wy = view.y + (py - H / 2) / view.z;
  const rad = Math.max(10 / view.z, 4), gx = Math.floor(wx / GS), gy = Math.floor(wy / GS), span = Math.ceil(rad / GS);
  let best = -1, bd = Infinity;
  for (let a = gx - span; a <= gx + span; a++) for (let b = gy - span; b <= gy + span; b++) {
    const cell = grid.get(a + ":" + b); if (!cell) continue;
    for (const k of cell) {
      const d = Math.hypot(X[k] - wx, Y[k] - wy), lim = Math.max(rad, RW[k] + 2 / view.z);
      if (d < lim && d < bd) { bd = d; best = k; }
    }
  }
  return best;
}
function tip(k, e) {
  const el = $("tip");
  if (k < 0 || !e) { el.hidden = true; return; }
  const i = AT[k], counts = [0, 0, 0];
  for (let j = 1; j < adj[k].length; j += 2) counts[adj[k][j]]++;
  el.innerHTML = `<b>${esc(labelCt(i))}</b>${title(i) && title(i) !== label(i) ? `<span class="t2">${esc(title(i).length > 150 ? title(i).slice(0, 148) + "…" : title(i))}</span>` : ""}` +
    `<span class="t3"><i style="background:${COLS[CL[k]]}"></i>${esc(t(CL[k] === 6 ? "levelUnknown" : "c" + CL[k]))} · ${esc(t("nLinks", num(deg[k])))}</span>`;
  el.hidden = false;
  const tw = el.offsetWidth, th = el.offsetHeight;
  let x = e.clientX + 14, y = e.clientY + 16;
  if (x + tw > innerWidth - 8) x = e.clientX - tw - 12;
  if (y + th > innerHeight - 8) y = e.clientY - th - 12;
  el.style.left = x + "px"; el.style.top = y + "px";
}
function select(k, fly) {
  sel = k;
  if (k < 0) { summary(); redraw(); return; }
  ctx.panel.node(AT[k], { go: ctx.go, close: () => ctx.go("net", true), closable: true });
  if (fly) flyTo(k);
  redraw();
}
function wire() {
  const pts = new Map();
  cv.addEventListener("pointerdown", (e) => {
    cv.setPointerCapture(e.pointerId);
    pts.set(e.pointerId, [e.clientX, e.clientY]);
    if (pts.size === 2) { const [a, b] = [...pts.values()]; pinch = { d: Math.hypot(a[0] - b[0], a[1] - b[1]), z: view.z }; drag = null; }
    else drag = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, moved: false };
    anim = null;
  });
  cv.addEventListener("pointermove", (e) => {
    if (pts.has(e.pointerId)) pts.set(e.pointerId, [e.clientX, e.clientY]);
    if (pinch && pts.size === 2) {
      const [a, b] = [...pts.values()], d = Math.hypot(a[0] - b[0], a[1] - b[1]);
      view.z = Math.min(fitZ * 60, Math.max(fitZ * 0.6, pinch.z * (d / pinch.d)));
      redraw(); settle(); return;
    }
    if (drag) {
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 4) drag.moved = true;
      if (drag.moved) { view.x = drag.vx - dx / view.z; view.y = drag.vy - dy / view.z; $("tip").hidden = true; redraw(); settle(); return; }
    }
    if (e.pointerType === "touch") return;
    const r = cv.getBoundingClientRect(), k = pick(e.clientX - r.left, e.clientY - r.top);
    if (k !== hot) { hot = k; redraw(); }
    tip(k, e);
    cv.style.cursor = k >= 0 ? "pointer" : drag ? "grabbing" : "grab";
  });
  const up = (e) => {
    pts.delete(e.pointerId);
    if (pinch && pts.size < 2) { pinch = null; settle(); }
    if (drag && !drag.moved && e.type === "pointerup") {
      const r = cv.getBoundingClientRect(), k = pick(e.clientX - r.left, e.clientY - r.top);
      if (k >= 0) ctx.go("net/" + idOf(AT[k]), true); else if (sel >= 0) ctx.go("net", true);
    }
    drag = null; redraw();
  };
  cv.addEventListener("pointerup", up); cv.addEventListener("pointercancel", up);
  cv.addEventListener("pointerleave", () => { if (hot >= 0) { hot = -1; redraw(); } $("tip").hidden = true; });
  cv.addEventListener("wheel", (e) => {
    e.preventDefault();
    const r = cv.getBoundingClientRect(), px = e.clientX - r.left, py = e.clientY - r.top;
    const wx = view.x + (px - W / 2) / view.z, wy = view.y + (py - H / 2) / view.z;
    const z = Math.min(fitZ * 60, Math.max(fitZ * 0.6, view.z * Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0018))));
    view = { x: wx - (px - W / 2) / z, y: wy - (py - H / 2) / z, z };
    anim = null; $("tip").hidden = true; redraw(); settle();
  }, { passive: false });
  cv.addEventListener("dblclick", (e) => {
    const r = cv.getBoundingClientRect(), px = e.clientX - r.left, py = e.clientY - r.top;
    go({ x: view.x + (px - W / 2) / view.z, y: view.y + (py - H / 2) / view.z, z: Math.min(fitZ * 60, view.z * 2.5) });
  });
  cv.addEventListener("keydown", (e) => {
    const step = 80 / view.z;
    const m = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
    if (m) { e.preventDefault(); view.x += m[0]; view.y += m[1]; redraw(); settle(); }
    else if (e.key === "+" || e.key === "=") go({ ...view, z: Math.min(fitZ * 60, view.z * 1.6) });
    else if (e.key === "-") go({ ...view, z: Math.max(fitZ * 0.6, view.z / 1.6) });
    else if (e.key === "0") fit();
    else if (e.key === "Escape" && sel >= 0) ctx.go("net", true);
  });
  new ResizeObserver(() => { if (!$("v-net").hidden) resize(); }).observe(cv.parentElement);
}

// ---------- controls and the panel without a selection
function controls() {
  $("ntitle").textContent = t("netTitle");
  const cnt = (L) => E[L].length / 2;
  $("nlayers").innerHTML = LAYERS.map((L) => `<button class="chip" data-layer="${L}" aria-pressed="${on[L]}"><i style="background:rgb(${EDGE[L].join(",")})"></i>${esc(t(LNAME[L]))} <span class="num">${esc(num(cnt(L)))}</span></button>`).join("") +
    `<button class="chip fit" id="nfit" title="${esc(t("netFit"))}" aria-label="${esc(t("netFit"))}">${ICON.fit}</button>`;
  $("nfoot").innerHTML = [0, 1, 2, 3, 4, 5].map((c) => `<span class="it">${sw(c)}<span>${esc(t("c" + c))}</span></span>`).join("") +
    `<span class="it num">${esc(t("netCount", num(n), num(NET.unlinked)))}</span>`;
  cv.setAttribute("aria-label", t("netTitle"));
}
function summary() {
  if (matchMedia("(max-width: 1180px)").matches) { ctx.panel.hide(); return; }
  const most = [...Array(n).keys()].sort((a, b) => deg[b] - deg[a] || D[b] - D[a]).slice(0, 12);
  // federal acts most cantons rest on: stated bases from cantonal acts
  const by = new Map(), acts = new Map(), p = E.bases;
  for (let j = 0; j < p.length; j += 2) {
    const a = AT[p[j]], b = AT[p[j + 1]];
    if (M.CT[a] && !M.CT[b] && !(M.S[b] || "").startsWith("0.")) { if (!by.has(b)) by.set(b, new Set()); by.get(b).add(M.CT[a]); acts.set(b, (acts.get(b) || 0) + 1); }
  }
  // the Constitution aside (every canton rests on it): most cantons first, then most cantonal acts
  const bridges = [...by.entries()].filter(([b]) => M.S[b] !== "101").sort((x, y) => y[1].size - x[1].size || acts.get(y[0]) - acts.get(x[0])).slice(0, 12);
  const row = (i, v) => `<a class="r" href="${href("net/" + idOf(i))}"><span class="a">${sw(M.cls[i] >= 0 ? M.cls[i] : 6)}${esc(labelCt(i))}</span><span class="v">${esc(v)}</span>${title(i) && title(i) !== label(i) ? `<span class="b">${esc(title(i))}</span>` : ""}</a>`;
  const layers = LAYERS.map((L) => `<span><i class="sw" style="background:rgb(${EDGE[L].join(",")})"></i>${esc(t(LNAME[L]))}</span><span class="num">${esc(num(E[L].length / 2))}</span>`).join("");
  ctx.panel.custom({ kicker: `<span>${esc(t("net"))}</span>`, h1: t("netTitle"), lede: t("netLede"),
    html: `<div class="stat2"><div class="stat"><b>${esc(num(n))}</b><span>${esc(t("netLinked"))}</span></div><div class="stat"><b>${esc(num(LAYERS.reduce((s, L) => s + E[L].length / 2, 0)))}</b><span>${esc(t("netEdges"))}</span></div></div>` +
      `<div class="stackkey" style="margin-top:14px">${layers}</div>` +
      `<section><h2><span>${esc(t("netBridges"))}</span></h2><ul class="rows">${bridges.map(([i, s]) => `<li>${row(i, t("nCantons", num(s.size)))}</li>`).join("")}</ul></section>` +
      `<section><h2><span>${esc(t("netMost"))}</span></h2><ul class="rows">${most.map((k) => `<li>${row(AT[k], t("nLinks", num(deg[k])))}</li>`).join("")}</ul></section>` },
    { closable: false });
}
export async function init(c) {
  ctx = c;
  cv = $("nc"); g = cv.getContext("2d");
  readCols();
  await load();
  wire();
  $("nlayers").addEventListener("click", (e) => {
    if (e.target.closest("#nfit")) { fit(); return; }
    const b = e.target.closest("[data-layer]"); if (!b) return;
    on[b.dataset.layer] = !on[b.dataset.layer];
    if (!LAYERS.some((L) => on[L])) on[b.dataset.layer] = true;
    controls(); renderCache(); redraw();
  });
  if (document.fonts) document.fonts.ready.then(() => redraw());
}
export async function show(rest) {
  controls();
  resize();
  const id = rest.startsWith("net/") ? rest.slice(4) : "";
  const i = id ? M.byId.get(id) : null, k = i != null && NET.idx.has(i) ? NET.idx.get(i) : -1;
  if (k >= 0) select(k, k !== sel || view.z < fitZ * 2);
  else { sel = -1; summary(); redraw(); }
}
export function refresh() { if (!$("v-net").hidden) { controls(); if (sel >= 0) select(sel, false); else summary(); redraw(); } }
