// The map: a nested, squarified treemap of every act, drawn on canvas. The node in focus fills the
// stage; below it every act is a tile (area = acts in force, or decisions referring to it; colour =
// who made the rule). Inside an act the tiles are its divisions and articles. Changing the focus
// animates every tile from where it was to where it goes, so the eye can follow.
import { M, kids, KIND, label as nodeLabel, shortLabel, isAct } from "./data.js";
import { t, pick } from "./i18n.js";

const PHI = (1 + Math.sqrt(5)) / 2;
const reduce = matchMedia("(prefers-reduced-motion: reduce)");
let cv, ctx, ov, octx, W = 0, H = 0, dpr = 1;
let mode = "acts";                  // "acts" | "dec"
let focus = 0, sel = null, hot = null, kbd = null, hiCls = -1;
let items = [], byId = new Map(), root = null;
let anim = null, raf = 0;
let OA = null;                      // the act whose articles are open: built by openAct()
const H1 = 26, H2 = 20;             // header bands of groups at depth 1 and below
// with decisions as area, every canton keeps at least this share of its block, so that all 26 stay visible and named
// (VD 145,447 decisions, AI 89: in proportion, AI would be a few pixels); disclosed in the legend and the method
export const CANTON_FLOOR = 0.006;
const isCanton = (id) => !isStr(id) && M.K[id] === KIND.t;
let cb = {};                        // callbacks: select(id), focus(id), hover(id)
let COL = {}, HEAT = [];
let hatch = null;
let TSH = null;                     // the time view: per node the share of it that exists in the year shown (decision 31)

// ---------- the tree the map walks: atlas nodes are numbers, divisions "L<k>", articles "A<j>"
const isStr = (id) => typeof id === "string";
function children(id) {
  if (isStr(id)) return id[0] === "L" && OA ? OA.lk[+id.slice(1)].filter((c) => value(c) > 0) : [];
  if (OA && id === OA.i && !isLeaf(id)) return OA.top.filter((c) => value(c) > 0);
  if (isAct(id)) return [];
  const out = [];
  const V = vals();
  for (const c of kids(id)) if (V[c] > 0) out.push(c);
  return out;
}
export function value(id) {
  if (!isStr(id)) return vals()[id];
  return (mode === "acts" ? OA.va : OA.vd).get(id) || 0;
}
// an act is a tile, except the open act while the map shows its inside
const isLeaf = (id) => (isStr(id) ? id[0] === "A" : isAct(id) && !(OA && OA.i === id && (focus === id || isStr(focus))));
export function parentOf(id) {
  if (!isStr(id)) return id > 0 ? M.P[id] : -1;
  if (!OA) return -1;
  const p = OA.par.get(id);
  return p == null ? OA.i : p;
}
function clsOf(id) { return isStr(id) ? -1 : TSH ? M.hcls[id] : M.cls[id]; }
// the time view's map holds every act that was ever in force: today's and the earlier federal acts (decision 32)
const hist = () => TSH && mode === "acts";
const vals = () => (hist() ? M.val.hist : M.val[mode]);

// colours
function readColours() {
  const cs = getComputedStyle(document.documentElement), v = (n) => cs.getPropertyValue(n).trim();
  COL = { paper: v("--paper"), ink: v("--ink"), ink2: v("--ink-2"), ink3: v("--ink-3"), rule: v("--rule"), accent: v("--accent"), wash: v("--wash") };
  COL.fill = [0, 1, 2, 3, 4, 5, 6].map((c) => v(`--c${c}`));
  COL.on = [0, 1, 2, 3, 4, 5, 6].map((c) => v(`--on-c${c}`));
  const stops = ["#eef4fb", "#cfe0f3", "#78a6dc", "#1f5fae", "#0b2a4a"].map(hex);
  HEAT = [];
  for (let k = 0; k <= 40; k++) {                 // the article ramp: decisions per article, log scale
    const u = k / 40, s = u * (stops.length - 1), a = Math.min(stops.length - 2, Math.floor(s)), f = s - a;
    HEAT.push(`rgb(${[0, 1, 2].map((c) => Math.round(stops[a][c] + (stops[a + 1][c] - stops[a][c]) * f)).join(",")})`);
  }
  const p = document.createElement("canvas"); p.width = p.height = 6;
  const pc = p.getContext("2d");
  pc.fillStyle = COL.fill[5]; pc.fillRect(0, 0, 6, 6);
  pc.strokeStyle = "#cbcbc8"; pc.lineWidth = 1; pc.beginPath(); pc.moveTo(0, 6); pc.lineTo(6, 0); pc.moveTo(-1, 1); pc.lineTo(1, -1); pc.moveTo(5, 7); pc.lineTo(7, 5); pc.stroke();
  hatch = ctx.createPattern(p, "repeat");
}
const hex = (h) => [1, 3, 5].map((k) => parseInt(h.slice(k, k + 2), 16));
export const heatColour = (u) => HEAT[Math.max(0, Math.min(40, Math.round(u * 40)))];
function heatOf(id) {
  const n = OA.n.get(id) || 0;
  return n ? Math.log1p(n) / Math.log1p(OA.max || 1) : 0;
}
function fillOf(id) {
  if (isStr(id)) return heatColour(heatOf(id));
  const c = clsOf(id);
  if (c === 5) return hatch;
  return COL.fill[c >= 0 ? c : 6];
}
function inkOf(id) {
  if (isStr(id)) return heatOf(id) > 0.62 ? "#ffffff" : COL.ink;
  const c = clsOf(id);
  return COL.on[c >= 0 ? c : 6];
}
// the dominant colour class of a group too small to subdivide
function groupFill(id) {
  if (isStr(id)) return heatColour(heatOf(id));
  const comp = hist() ? M.comp.hist : M.comp[mode], o = id * 7;
  let best = 6, bv = -1;
  for (let c = 0; c < 7; c++) if (comp[o + c] > bv) { bv = comp[o + c]; best = c; }
  return best === 5 ? hatch : COL.fill[best];
}

// ---------- labels
export function labelOf(id) {
  if (!isStr(id)) return nodeLabel(id);
  if (id[0] === "A") { const a = OA.arts[+id.slice(1)]; return `${t("art")} ${a[1]}`; }
  const lv = OA.lv[+id.slice(1)];
  return `${pick(lv[2]) || ""} ${pick(lv[3]) || ""}`.replace(/:\s*$/, "").trim();
}
export function crumbLabel(id) {                       // "2 Privatrecht", "Erste Abteilung"
  if (!isStr(id)) return M.K[id] === KIND.c ? `${M.S[id]} ${(M.L[id] || "").split(/\s+[–-]\s+/)[0]}` : nodeLabel(id);
  if (id[0] === "L") { const lv = OA.lv[+id.slice(1)]; return (pick(lv[2]) || pick(lv[3]) || "").replace(/:\s*$/, ""); }
  return labelOf(id);
}
export function tileLabel(id) { return !isStr(id) && isAct(id) ? shortLabel(id) : labelOf(id); }
export function subOf(id) {
  if (!isStr(id)) {
    if (M.K[id] !== KIND.a && M.K[id] !== KIND.o) return "";
    const full = M.T[id] || M.L[id];
    return shortLabel(id) !== full ? full : "";
  }
  if (id[0] === "A") { const a = OA.arts[+id.slice(1)]; return headingOf(a); }
  return "";
}
export function headingOf(a) {                       // the article's marginal heading, else its division's
  if (a[9]) return pick(a[9]) || "";
  return a[3] >= 0 && OA ? pick(OA.lv[a[3]][3]) || "" : "";
}

// ---------- layout
function squarify(ids, vals, x0, y0, x1, y1, out) {
  let i0 = 0, i1 = 0, n = ids.length, value = 0;
  for (const v of vals) value += v;
  while (i0 < n) {
    const dx = x1 - x0, dy = y1 - y0;
    let sum = 0;
    do sum = vals[i1++]; while (!sum && i1 < n);
    let minV = sum, maxV = sum;
    const alpha = Math.max(dy / dx, dx / dy) / (value * PHI);
    let beta = sum * sum * alpha, minRatio = Math.max(maxV / beta, beta / minV);
    for (; i1 < n; ++i1) {
      const v = vals[i1];
      sum += v;
      if (v < minV) minV = v;
      if (v > maxV) maxV = v;
      beta = sum * sum * alpha;
      const r = Math.max(maxV / beta, beta / minV);
      if (r > minRatio) { sum -= v; break; }
      minRatio = r;
    }
    if (dx < dy) {                                   // a row across the top
      const y = value ? y0 + (dy * sum) / value : y1, k = sum ? dx / sum : 0;
      let x = x0;
      for (let j = i0; j < i1; j++) { const w = vals[j] * k; out.push([ids[j], x, y0, w, y - y0]); x += w; }
      y0 = y;
    } else {                                         // a column down the left
      const x = value ? x0 + (dx * sum) / value : x1, k = sum ? dy / sum : 0;
      let y = y0;
      for (let j = i0; j < i1; j++) { const h = vals[j] * k; out.push([ids[j], x0, y, x - x0, h]); y += h; }
      x0 = x;
    }
    value -= sum; i0 = i1;
  }
}
function layout(f) {
  const list = [], map = new Map();
  const top = { id: f, x: 0, y: 0, w: W, h: H, d: 0, hdr: 0, leaf: false, parent: null, lab: 0 };
  map.set(f, top);
  const rec = (it) => {
    const { id, x, y, w, h, d } = it;
    if (d > 0 && isLeaf(id)) { it.leaf = true; return; }
    const ch = children(id);
    if (!ch.length) { it.leaf = true; return; }
    if (d > 0 && (w < 3 || h < 3)) { it.small = true; return; }
    let ix = x, iy = y, iw = w, ih = h;
    if (d > 0) {
      const pad = d === 1 ? 3 : d === 2 ? 2 : isStr(id) ? 0 : 1;      // deep divisions of an act: no frame of their own
      // a part that fills nearly all of its parent repeats it: no header of its own (173 › 173.1 › 173.11 …)
      const hh = isCanton(id) ? (w >= 30 && h >= 34 ? (d === 1 ? H1 : H2) : 0) :   // a canton is always named
        d === 1 ? (w >= 64 && h >= 52 ? H1 : 0) : it.share > 0.8 ? 0 :
        d === 2 ? (w >= 64 && h >= 46 ? H2 : 0) : (w >= 110 && h >= 72 ? H2 : 0);
      it.hdr = hh;
      ix += pad; iw -= 2 * pad; iy += hh || pad; ih -= (hh || pad) + pad;
      if (iw < 1 || ih < 1) { it.small = true; return; }
    }
    // decisions: largest first (squarified layouts need it); acts: parts in the collection's order, then
    // the acts by who made them (constitution first), each in the collection's order
    const order = mode === "dec" ? ch.slice().sort((a, b) => value(b) - value(a)) :
      // (parts first: a lone small tile before a large part would be squeezed into a hairline)
      isStr(id) || (OA && id === OA.i) ? ch : ch.map((c, k) => [isLeaf(c) ? (M.HD[id] && M.S[c] === M.S[id] ? 0 : 1 + clsOf(c)) : -1, k, c])
        .sort((a, b) => a[0] - b[0] || a[1] - b[1]).map((x) => x[2]);
    let vals = order.map(value);
    const rects = [];
    if (mode === "dec" && order.length > 1 && order.every(isCanton)) {
      const tot = vals.reduce((a, b) => a + b, 0);
      vals = vals.map((v) => Math.max(v, tot * CANTON_FLOOR));
    }
    squarify(order, vals, ix, iy, ix + iw, iy + ih, rects);
    for (const [cid, cx, cy, cw, chh] of rects) {
      const c = { id: cid, x: cx, y: cy, w: cw, h: chh, d: d + 1, hdr: 0, leaf: false, parent: it, lab: 0, share: (cw * chh) / (iw * ih) };
      list.push(c); map.set(cid, c);
      rec(c);
    }
  };
  rec(top);
  for (const it of list) it.lab = it.leaf ? leafLabelLevel(it) : 0;
  return { list, map, top };
}
// 0 = no label, 1 = short label, 2 = short label + title
function leafLabelLevel(it) {
  if (it.w < 30 || it.h < 17) return 0;
  return it.w >= 96 && it.h >= 52 ? 2 : 1;
}

// ---------- drawing
const snap = (v) => Math.round(v * dpr) / dpr;
const widthCache = new Map();
function textW(s, font) {
  const k = font + "\u0000" + s;
  let w = widthCache.get(k);
  if (w === undefined) { ctx.font = font; w = ctx.measureText(s).width; if (widthCache.size > 20000) widthCache.clear(); widthCache.set(k, w); }
  return w;
}
function fit(s, font, max) {
  if (max <= 8) return "";
  if (textW(s, font) <= max) return s;
  let lo = 0, hi = s.length;
  while (lo < hi) { const m = (lo + hi + 1) >> 1; if (textW(s.slice(0, m) + "…", font) <= max) lo = m; else hi = m - 1; }
  return lo ? s.slice(0, lo).trimEnd() + "…" : "";
}
function wrap(s, font, max, lines) {
  const words = s.split(/\s+/), out = [];
  let cur = "";
  for (let k = 0; k < words.length; k++) {
    const w = words[k], tryS = cur ? cur + " " + w : w;
    if (textW(tryS, font) <= max) { cur = tryS; continue; }
    if (cur) out.push(cur);
    if (textW(w, font) <= max) cur = w;
    else {                                          // a long compound: break after / or -
      const parts = w.split(/(?<=[/\-])/);
      cur = "";
      for (const q of parts) {
        if (textW(cur + q, font) <= max) { cur += q; continue; }
        if (cur) { out.push(cur); if (out.length === lines - 1) break; }
        cur = textW(q, font) <= max ? q : fit(q, font, max);
      }
    }
    if (out.length >= lines - 1 && k < words.length - 1) { out.push(fit([cur, ...words.slice(k + 1)].join(" "), font, max)); return out.slice(0, lines); }
    if (out.length === lines - 1) { out.push(fit(words.slice(k).join(" "), font, max)); return out; }
  }
  if (cur) out.push(textW(cur, font) <= max ? cur : fit(cur, font, max));
  return out.slice(0, lines);
}
const SANS = getComputedStyle(document.documentElement).getPropertyValue("--sans") || "sans-serif";
const font = (w, px) => `${w} ${px}px ${SANS}`;

function drawFill(it, r, alpha) {
  const x0 = snap(r.x), y0 = snap(r.y), x1 = snap(r.x + r.w), y1 = snap(r.y + r.h);
  const w = x1 - x0, h = y1 - y0;
  if (w <= 0 || h <= 0 || !(it.leaf || it.small)) return;
  const id = it.id, g = w > 3 && h > 3 ? 1 : 0, s = shareOf(id);
  ctx.globalAlpha = alpha * (hiCls >= 0 && !isStr(id) && (!it.leaf || clsOf(id) !== hiCls) ? 0.16 : 1);
  if (s === 0) {                                     // not yet there: an empty plot of its size
    ctx.fillStyle = COL.wash; ctx.fillRect(x0, y0, Math.max(0.5, w - g), Math.max(0.5, h - g));
    return;
  }
  ctx.globalAlpha *= it.leaf ? (mode === "dec" ? 0.25 + 0.75 * s : 1) : 0.18 + 0.82 * s;
  ctx.fillStyle = it.leaf ? fillOf(id) : groupFill(id);
  ctx.fillRect(x0, y0, Math.max(0.5, w - g), Math.max(0.5, h - g));
}
const shareOf = (id) => (!TSH ? 1 : isStr(id) ? (OA ? TSH[OA.i] : 1) : TSH[id]);
export function setTime(share) {
  const was = hist();
  TSH = share;
  if (hist() !== was) relayout(true, "resize"); else redraw();     // the past makes room on the map, and gives it back
}
function drawLabel(it, alpha, r = it) {
  const x0 = snap(r.x), y0 = snap(r.y), x1 = snap(r.x + r.w), y1 = snap(r.y + r.h);
  const w = x1 - x0, h = y1 - y0;
  ctx.globalAlpha = alpha * (hiCls >= 0 && it.leaf && !isStr(it.id) && clsOf(it.id) !== hiCls ? 0.25 : 1) * (it.leaf && shareOf(it.id) === 0 ? 0.4 : 1);
  if (it.leaf) { if (it.lab) drawLeafLabel(it, x0, y0, w - 1, h - 1); return; }
  if (isCanton(it.id)) { drawCantonLabel(it, x0, y0, w, h); return; }
  if (!it.hdr) return;
  const big = it.d === 1, f = font(big ? 620 : 600, big ? 13 : 11.5);
  ctx.fillStyle = big ? COL.ink : COL.ink2;
  ctx.font = f; ctx.textBaseline = "alphabetic";
  const s = fit(labelOf(it.id), f, w - 10);
  if (s) ctx.fillText(s, x0 + 4, y0 + (big ? 17.5 : 14));
}
// a canton: its name in the header band, its code where the name does not fit; a tile too small for a band gets the
// code on a paper chip over its acts
function drawCantonLabel(it, x0, y0, w, h) {
  const big = it.d === 1, name = labelOf(it.id), code = M.S[it.id];
  if (it.hdr) {
    const f = font(big ? 620 : 600, big ? 13 : 11.5);
    ctx.fillStyle = big ? COL.ink : COL.ink2; ctx.font = f; ctx.textBaseline = "alphabetic";
    const s = textW(name, f) <= w - 10 ? name : textW(code, f) <= w - 6 ? code : "";
    if (s) ctx.fillText(s, x0 + (s === code && w < 40 ? 3 : 4), y0 + (big ? 17.5 : 14));
    return;
  }
  const f = font(640, w >= 26 && h >= 16 ? 11 : 9.5), tw = textW(code, f);
  if (w < tw + 4 || h < 11) return;
  const cw = tw + 6, ch = h >= 16 ? 15 : 12;
  ctx.fillStyle = COL.paper; ctx.globalAlpha *= 0.92;
  ctx.fillRect(x0 + 1, y0 + 1, Math.min(cw, w - 2), Math.min(ch, h - 2));
  ctx.globalAlpha /= 0.92;
  ctx.fillStyle = COL.ink; ctx.font = f; ctx.textBaseline = "alphabetic";
  ctx.fillText(code, x0 + 4, y0 + (ch === 15 ? 12 : 10));
}
function drawLeafLabel(it, x, y, w, h) {
  const id = it.id;
  let px = w < 110 ? 11 : 12, tp = 11.5;
  if (w > 420 && h > 260) { px = 26; tp = 15; } else if (w > 240 && h > 140) { px = 18; tp = 13; } else if (w > 150 && h > 84) { px = 15; tp = 12; }
  const lab = tileLabel(id), sub = subOf(id), f = font(640, px), room = w - 10;
  ctx.save(); ctx.beginPath(); ctx.rect(x, y, w, h); ctx.clip();
  drawLeafText(it, x, y, w, h, px, tp, lab, sub, f, room);
  ctx.restore();
}
function drawLeafText(it, x, y, w, h, px, tp, lab, sub, f, room) {
  const id = it.id;
  ctx.fillStyle = shareOf(id) === 0 ? COL.ink3 : inkOf(id); ctx.textBaseline = "alphabetic";
  let used = 0;
  if (textW(lab, f) <= room) {
    ctx.font = f; ctx.fillText(lab, x + 5, y + px + 3); used = px + 3;
  } else {                                          // too long for one line: wrap it, smaller, if the tile is tall enough
    const p2 = Math.min(px, 12), f2 = font(620, p2), lh = Math.round(p2 * 1.22), lines = Math.floor((h - 7) / lh);
    if (lines >= 2 && w >= 56) {
      const ls = wrap(lab, f2, room, Math.min(lines, 6));
      if (!ls.length || ls[0].length < 4) return;
      ctx.font = f2;
      ls.forEach((ln, k) => ctx.fillText(ln, x + 5, y + p2 + 3 + lh * k));
      used = p2 + 3 + lh * (ls.length - 1);
      if (ls.join(" ").length < lab.length) return;
    } else {
      const s = fit(lab, f, room);
      if (s.length < 9) return;                     // a stub of a word says nothing: leave the tile bare
      ctx.font = f; ctx.fillText(s, x + 5, y + px + 3);
      return;
    }
  }
  if (it.lab === 2 && sub && sub !== lab) {
    const tf = font(420, tp), lh = tp * 1.28, n = Math.floor((h - used - 10) / lh);
    if (n < 1) return;
    ctx.font = tf;
    const a0 = ctx.globalAlpha;
    ctx.globalAlpha = a0 * 0.86;
    wrap(sub, tf, room, Math.min(n, 5)).forEach((ln, k) => ctx.fillText(ln, x + 5, y + used + 5 + lh * (k + 1)));
    ctx.globalAlpha = a0;
  }
}
const ease = (u) => (u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2);
function frame(now) {
  raf = 0;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);
  let e = 1, done = true;
  if (anim) {
    const u = Math.min(1, (now - anim.t0) / anim.dur);
    e = ease(u); done = u >= 1;
  }
  const lerp = (a, b) => ({ x: a.x + (b.x - a.x) * e, y: a.y + (b.y - a.y) * e, w: a.w + (b.w - a.w) * e, h: a.h + (b.h - a.h) * e });
  if (anim && !done) {
    for (const x of anim.exit) drawFill(x.it, lerp(x.it, x.to), 1 - e);
    for (const it of items) {
      const from = anim.from.get(it.id);
      drawFill(it, from ? lerp(from, it) : it, from || !anim.fade ? 1 : e);
    }
    const la = e > 0.7 ? (e - 0.7) / 0.3 : 0;
    if (la > 0) for (const it of items) if ((it.leaf && it.lab) || it.hdr || isCanton(it.id)) { const from = anim.from.get(it.id); drawLabel(it, la, from ? lerp(from, it) : it); }
    ctx.globalAlpha = 1;
    raf = requestAnimationFrame(frame);
  } else {
    anim = null;
    for (const it of items) drawFill(it, it, 1);
    for (const it of items) if ((it.leaf && it.lab) || it.hdr || isCanton(it.id)) drawLabel(it, 1);
    ctx.globalAlpha = 1;
  }
  drawOverlay();
}
function redraw() { if (!raf) raf = requestAnimationFrame(frame); }

// the overlay: selection, hover, keyboard cursor
function drawOverlay() {
  octx.setTransform(dpr, 0, 0, dpr, 0, 0);
  octx.clearRect(0, 0, W, H);
  if (anim) return;
  const box = (id, colour, lw, inner) => {
    const it = byId.get(id);
    if (!it) return;
    const x = snap(it.x), y = snap(it.y), w = snap(it.x + it.w) - x - (it.leaf ? 1 : 0), h = snap(it.y + it.h) - y - (it.leaf ? 1 : 0);
    if (inner) { octx.strokeStyle = "#fff"; octx.lineWidth = 1; octx.strokeRect(x + lw + 0.5, y + lw + 0.5, w - 2 * lw - 1, h - 2 * lw - 1); }
    octx.strokeStyle = colour; octx.lineWidth = lw;
    octx.strokeRect(x + lw / 2, y + lw / 2, Math.max(1, w - lw), Math.max(1, h - lw));
  };
  if (hot != null && hot !== sel) box(hot, COL.ink, 1.5, false);
  if (kbd != null && kbd !== sel) box(kbd, COL.accent, 2, false);
  if (sel != null && sel !== focus) {
    if (byId.has(sel)) box(sel, COL.accent, 2, true);
    else {                                           // selected but too small to draw: mark the tile it hides in
      for (let p = parentOf(sel); p != null && p >= 0 || isStr(p); p = parentOf(p)) if (byId.has(p) && p !== focus) { box(p, COL.accent, 2, true); break; }
    }
  }
}

// ---------- changing what is shown
function relayout(animate, kind) {
  const old = byId, oldItems = items, oldFocus = root ? root.id : null;
  const L = layout(focus);
  items = L.list; byId = L.map; root = L.top;
  if (!animate || reduce.matches || !oldItems.length) { anim = null; redraw(); updateList(); return; }
  // where each tile comes from; tiles that leave go where the camera takes them
  const from = new Map(), exit = [];
  let A = null, B = null;                            // reference: rect in the old layout, rect in the new
  if (kind === "in" && old.has(focus)) { A = old.get(focus); B = { x: 0, y: 0, w: W, h: H }; }
  else if (kind === "out" && byId.has(oldFocus)) { A = { x: 0, y: 0, w: W, h: H }; B = byId.get(oldFocus); }
  else if (kind === "resize") { A = { x: 0, y: 0, w: W, h: H }; B = A; }
  const map = (r, a, b) => ({ x: b.x + ((r.x - a.x) * b.w) / (a.w || 1), y: b.y + ((r.y - a.y) * b.h) / (a.h || 1), w: (r.w * b.w) / (a.w || 1), h: (r.h * b.h) / (a.h || 1) });
  for (const it of items) {
    const o = old.get(it.id);
    if (o) { from.set(it.id, o); continue; }
    let p = it.parent;
    while (p && !old.has(p.id)) p = p.parent;
    if (p && p.d > 0) { from.set(it.id, map(it, p, old.get(p.id))); continue; }
    if (A) from.set(it.id, map(it, B, A));
  }
  if (A) for (const o of oldItems) if (!byId.has(o.id)) exit.push({ it: o, to: map(o, A, B) });
  anim = { t0: performance.now(), dur: kind === "resize" ? 320 : 620, from, exit, fade: !A };
  redraw(); updateList();
}
export function setFocus(id, animate = true) {
  const prev = focus;
  if (id === prev && items.length) { redraw(); return; }
  focus = id;
  const kind = isDesc(prev, id) ? "in" : isDesc(id, prev) ? "out" : "jump";
  kbd = null;
  relayout(animate, kind);
}
function isDesc(a, b) {                               // is b inside a?
  for (let p = b; p != null && (isStr(p) || p >= 0); p = parentOf(p)) if (p === a) return true;
  return false;
}
export const getFocus = () => focus;
export function setSelection(id) { sel = id; drawOverlay(); }
export function setMode(m) { if (m === mode) return; mode = m; relayout(true, "resize"); }
export const getMode = () => mode;
export function highlightClass(c) { hiCls = c; redraw(); }
export function resize() {
  const r = cv.parentElement.getBoundingClientRect();
  const w = Math.max(1, Math.floor(r.width)), h = Math.max(1, Math.floor(r.height));
  dpr = Math.min(2, window.devicePixelRatio || 1);
  for (const c of [cv, ov]) { c.width = Math.round(w * dpr); c.height = Math.round(h * dpr); }
  const ow = W, oh = H;
  W = w; H = h;
  if (!ow || !items.length) { relayout(false); return; }
  if (ow === w && oh === h) { redraw(); return; }
  // scale the old tiles to the new stage, then move them to their new places
  const sx = w / ow, sy = h / oh;
  for (const it of items) { it.x *= sx; it.y *= sy; it.w *= sx; it.h *= sy; }
  relayout(true, "same");
}
export function refreshLabels() { widthCache.clear(); relayout(false); }
export function visibleClasses() {                    // colour classes in view, for the legend
  const s = new Set();
  for (const it of items) if (it.leaf && !isStr(it.id)) s.add(clsOf(it.id));
  return s;
}

// ---------- the open act: its divisions and articles
export function openAct(i, data) {
  const lv = data.lv || [], arts = data.arts || [];
  const lk = lv.map(() => []), top = [], par = new Map();
  const first = new Float64Array(lv.length).fill(Infinity);
  arts.forEach((a, j) => { for (let k = a[3]; k >= 0; k = lv[k][1]) if (j < first[k]) first[k] = j; });
  const keyed = (list) => list.sort((p, q) => p[0] - q[0]).map((x) => x[1]);
  const kidsOf = lv.map(() => []), topK = [];
  lv.forEach((l, k) => { if (first[k] === Infinity) return; (l[1] >= 0 ? kidsOf[l[1]] : topK).push([first[k] - 0.5, "L" + k]); if (l[1] >= 0) par.set("L" + k, "L" + l[1]); });
  arts.forEach((a, j) => { (a[3] >= 0 ? kidsOf[a[3]] : topK).push([j, "A" + j]); if (a[3] >= 0) par.set("A" + j, "L" + a[3]); });
  kidsOf.forEach((x, k) => { lk[k] = keyed(x); });
  top.push(...keyed(topK));
  const va = new Map(), vd = new Map(), n = new Map();
  let max = 0;
  arts.forEach((a, j) => {
    const id = "A" + j;
    va.set(id, a[4] ? 0 : 1); vd.set(id, a[2] || 0); n.set(id, a[2] || 0);
    if (a[2] > max) max = a[2];
    for (let k = a[3]; k >= 0; k = lv[k][1]) {
      const L = "L" + k;
      va.set(L, (va.get(L) || 0) + (a[4] ? 0 : 1)); vd.set(L, (vd.get(L) || 0) + (a[2] || 0)); n.set(L, (n.get(L) || 0) + (a[2] || 0));
    }
  });
  const byEid = new Map(arts.map((a, j) => [a[0], "A" + j]));
  lv.forEach((l, k) => byEid.set(l[0], "L" + k));
  OA = { i, lv, arts, lk, top, par, va, vd, n, max, byEid, data };
  return OA;
}
export const openActState = () => OA;
export function closeAct() { OA = null; }

// ---------- pointer and keyboard
function hitAt(x, y) {
  for (let k = items.length - 1; k >= 0; k--) {
    const it = items[k];
    if (x >= it.x && x < it.x + it.w && y >= it.y && y < it.y + it.h) return it;
  }
  return null;
}
function activate(it) {
  if (!it) return;
  const id = it.id;
  if (it.leaf) {
    const pid = parentOf(id);
    if (it.lab || pid === focus) {
      if (sel === id && !isStr(id) && M.PK[id] >= 0 && M.A[id] > 0) cb.focus(id);        // a second click opens its articles
      else cb.select(id);
    } else cb.focus(pid);
    return;
  }
  cb.focus(id);
}
function updateList() {
  const ul = document.getElementById("tmlist");
  if (!ul) return;
  const top = items.filter((it) => it.d === 1).slice(0, 400);
  ul.innerHTML = top.map((it, k) => `<li><button data-k="${k}">${esc(labelOf(it.id))}</button></li>`).join("");
  ul.onclick = (e) => { const b = e.target.closest("button"); if (b) activate(top[+b.dataset.k]); };
}
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
function moveKbd(dx, dy) {
  const top = items.filter((it) => it.d === 1);
  if (!top.length) return;
  const cur = byId.get(kbd) && byId.get(kbd).d === 1 ? byId.get(kbd) : null;
  if (!cur) { kbd = top[0].id; return; }
  const cx = cur.x + cur.w / 2, cy = cur.y + cur.h / 2;
  let best = null, bd = Infinity;
  for (const it of top) {
    if (it === cur) continue;
    const ix = it.x + it.w / 2, iy = it.y + it.h / 2, ddx = ix - cx, ddy = iy - cy;
    if (dx && Math.sign(ddx) !== dx) continue;
    if (dy && Math.sign(ddy) !== dy) continue;
    const d = dx ? Math.abs(ddx) + 2 * Math.abs(ddy) : Math.abs(ddy) + 2 * Math.abs(ddx);
    if (d < bd) { bd = d; best = it; }
  }
  if (best) kbd = best.id;
}

export function initTreemap(canvas, callbacks) {
  cv = canvas; cb = callbacks;
  ctx = cv.getContext("2d");
  ov = document.createElement("canvas");
  ov.style.cssText = "position:absolute;inset:0;width:100%;height:100%;pointer-events:none";
  cv.parentElement.appendChild(ov);
  octx = ov.getContext("2d");
  readColours();
  const pos = (e) => { const r = cv.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
  cv.addEventListener("pointermove", (e) => {
    if (e.pointerType === "touch") return;
    const [x, y] = pos(e), it = hitAt(x, y), id = it ? it.id : null;
    if (id !== hot) { hot = id; drawOverlay(); }
    cb.hover(id, e);
  });
  cv.addEventListener("pointerleave", () => { hot = null; drawOverlay(); cb.hover(null); });
  cv.addEventListener("click", (e) => { const [x, y] = pos(e); activate(hitAt(x, y)); });
  cv.addEventListener("keydown", (e) => {
    const d = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
    if (d) { e.preventDefault(); moveKbd(...d); drawOverlay(); const it = byId.get(kbd); if (it) cb.hover(it.id, null, it); return; }
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); if (kbd != null) activate(byId.get(kbd)); return; }
    if (e.key === "Escape" || e.key === "Backspace") { e.preventDefault(); cb.up(); }
  });
  cv.addEventListener("blur", () => { kbd = null; drawOverlay(); cb.hover(null); });
  new ResizeObserver(() => resize()).observe(cv.parentElement);
  resize();
}
export const itemRect = (id) => byId.get(id) || null;
export const canvasEl = () => cv;
