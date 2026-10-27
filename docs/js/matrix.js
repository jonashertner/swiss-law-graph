// Dependencies: the hierarchy's blocks as rows and columns, in the order of the Stufenbau (decision 25).
// A cell says how much the row draws on the column: acts naming a basis there, provisions naming an
// act there, or decisions citing both (lift). Shaded fields: the same level.
import { t, cantonName, lang } from "./i18n.js";
import { M, loadHier, getJSON, loadLinks, idOf, labelCt, title } from "./data.js";
import { $, esc, num, sw, href } from "./util.js";
import { nameOf, rowName, ensure } from "./hierarchy.js";
import * as TV from "./time.js";

let H = null, G = null, ctx = {}, layer = "basis", scope = "all", hotCell = null, selCell = null, idx = null, dpr = 1;
let BY = null;                       // in the time view: acts per basis cell in the year shown (decision 31)
const MIN_DEC = 20;
const RAMP = ["#eaf1fa", "#cfe0f3", "#9cc0e8", "#5d8fd0", "#1f5fae", "#0b2a4a"];

function index() {
  if (idx) return idx;
  const m = { basis: new Map(), law: new Map(), court: new Map() };
  for (const [a, b, n, np] of H.basis) m.basis.set(a * 1024 + b, [n, np]);
  for (const [a, b, n, p] of H.law) m.law.set(a * 1024 + b, [n, p]);
  for (const [a, b, n] of H.court) { m.court.set(a * 1024 + b, n); m.court.set(b * 1024 + a, n); }
  m.blockOf = new Map();
  for (const [k, b] of Object.entries(H.nb)) m.blockOf.set(+k, b);
  for (const [k, b] of Object.entries(H.cb || {})) if (!m.blockOf.has(+k)) m.blockOf.set(+k, b);
  return (idx = m);
}
const floorOf = (b) => { const r = H.blocks[b].r; return r === "bv" ? (H.blocks[b].k === "int" ? -0.5 : 0) : r; };
function order(sc) {
  const B = H.blocks, bv = [], fed = { 1: [], 2: [], 3: [] };
  let int = -1;
  B.forEach((b, i) => { if (b.r === "bv") { if (b.k === "int") int = i; else bv.push(i); } else if (b.r >= 1 && b.r <= 3) fed[b.r].push(i); });
  const key = (i) => (B[i].k === 0 ? -1 : B[i].k === "1874" ? 1e9 : +B[i].k);
  bv.sort((a, b) => key(a) - key(b));
  if (layer === "law") bv.splice(0, bv.length, ...bv.filter((i) => B[i].k === 0));     // cross-references name the BV as a whole
  for (const f of [1, 2, 3]) fed[f].sort((a, b) => String(B[a].k).localeCompare(String(B[b].k)));
  const F = [{ key: "bv", name: t("rowBV"), list: bv, same: true }];
  if (int >= 0) F.push({ key: "int", name: t("treaties"), list: [int], same: true });
  for (const f of [1, 2, 3]) F.push({ key: f, name: t("row" + f), list: fed[f], same: true });
  const at = (r, ct) => B.findIndex((b) => b.r === r && b.k === ct);
  const C = H.ct_order.map((ct) => ({ key: "ct", ct, name: ct, list: [4, 5, 6, 7].map((r) => at(r, ct)).filter((i) => i >= 0), module: true }));
  const FR = layer === "basis" ? F.filter((g) => g.key !== "bv" && g.key !== "int") : F;      // the BV and treaties rest on nothing
  if (sc === "fed") return { rows: FR, cols: F };
  if (sc === "cant") return { rows: C, cols: [...F, { key: "own", name: t("mOwn"), list: [4, 5, 6, 7].map((r) => ({ own: r })), own: true }] };
  return { rows: [...FR, ...C], cols: [...F, ...C] };
}
const colOf = (c, a) => (typeof c === "number" ? c : H.blocks.findIndex((b) => b.r === c.own && b.k === H.blocks[a].k));
// the year shown: an act counts in a cell once it and the basis it names exist
async function timeCells() {
  if (!TV.TIME.on) { BY = null; return; }
  const pairs = await getJSON("data/pairs.json"), y = TV.TIME.year, m = new Map(), seen = new Set();
  for (const [ra, rb, i, j] of pairs) {
    if (i < 0 || !TV.exists(i, y) || (j >= 0 && !TV.exists(j, y))) continue;
    const key = ra * 1024 + rb, u = key * 32768 + i;
    if (seen.has(u)) continue;
    seen.add(u); m.set(key, (m.get(key) || 0) + 1);
  }
  BY = m;
}
function value(a, b) {
  if (a < 0 || b < 0) return null;
  const m = index();
  if (layer === "basis" && BY) { const v = BY.get(a * 1024 + b); return v ? { v, n: v, np: null } : null; }
  if (layer === "basis") { const v = m.basis.get(a * 1024 + b); return v ? { v: v[0], n: v[0], np: v[1] } : null; }
  if (layer === "law") { const v = m.law.get(a * 1024 + b); return v ? { v: v[0], n: v[0], p: v[1] } : null; }
  if (a === b) return null;
  const n = m.court.get(a * 1024 + b); if (!n) return null;
  const B = H.blocks, l = (n * H.dec_any) / Math.max(1, (B[a].d || 1) * (B[b].d || 1));
  return { v: n >= MIN_DEC && l > 1 ? l : 0, n, l };
}
function layout() {
  const box = $("mscroll").getBoundingClientRect(), phone = box.width < 760, O = order(scope);
  const flat = (gs) => { const out = []; gs.forEach((g, k) => g.list.forEach((x) => out.push({ x, g: k }))); return out; };
  const rows = flat(O.rows), cols = flat(O.cols), fed = scope === "fed";
  const left = fed ? (phone ? 170 : 250) : (phone ? 96 : 150), top = scope === "all" ? 34 : 150;
  let cw = (box.width - left - 32) / cols.length, ch = (box.height - top - 24) / rows.length;
  if (scope === "cant") ch = Math.min(ch, cw); else cw = ch = Math.min(cw, ch);
  const minS = phone ? 6 : 3;
  cw = Math.max(cw, minS); ch = Math.max(ch, minS);
  const VW = Math.max(box.width - 2, left + cols.length * cw + 24), VH = Math.max(box.height - 4, Math.ceil(top + rows.length * ch + 24));
  return { phone, O, rows, cols, left, top, cw, ch, VW, VH };
}
function canvas(id) {
  const c = $(id), cx = c.getContext("2d");
  c.width = Math.round(G.VW * dpr); c.height = Math.round(G.VH * dpr);
  c.style.width = G.VW + "px"; c.style.height = G.VH + "px";
  cx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return cx;
}
const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const SANS = css("--sans"), MONO = css("--mono");
function shortName(b) {
  const B = H.blocks[b];
  if (B.k === 0 && layer === "law") return t("rowBV");
  if (B.r >= 4) return `${B.k} · ${B.r === 4 ? t("c0") : t("c" + (B.r - 4))}`;
  return nameOf(b, true);
}
function full(b) { const B = H.blocks[b]; return B.r >= 4 ? `${cantonName(B.k)} · ${B.r === 4 ? t("c0") : t("c" + (B.r - 4))}` : B.r === "bv" ? nameOf(b) : `${nameOf(b)} · ${t("c" + B.r)}`; }

function fitC(c, s, max) {
  if (c.measureText(s).width <= max) return s;
  let lo = 0, hi = s.length;
  while (lo < hi) { const m = (lo + hi + 1) >> 1; if (c.measureText(s.slice(0, m) + "…").width <= max) lo = m; else hi = m - 1; }
  return lo ? s.slice(0, lo).trimEnd() + "…" : "";
}
function render() {
  if (!H) return;
  dpr = Math.min(2, devicePixelRatio || 1);
  G = layout();
  $("mwrap").style.width = G.VW + "px"; $("mwrap").style.height = G.VH + "px";
  const c = canvas("mc"); canvas("mx");
  const { rows, cols, left, top, cw, ch } = G;
  c.clearRect(0, 0, G.VW, G.VH);
  let vmax = 1;
  if (BY && layer === "basis") {                       // the time view keeps today's scale: cells darken as the years pass
    const keep = BY; BY = null;
    for (const r of rows) for (const cc of cols) { const v = value(r.x, colOf(cc.x, r.x)); if (v && v.v > vmax) vmax = v.v; }
    BY = keep;
  }
  const val = rows.map((r) => cols.map((cc) => { const v = value(r.x, colOf(cc.x, r.x)); if (v && v.v > vmax) vmax = v.v; return v; }));
  if (layer === "court") {
    const ls = val.flat().filter((v) => v && v.v).map((v) => v.v).sort((a, b) => a - b);
    if (ls.length) vmax = Math.max(2, ls[Math.floor(0.98 * (ls.length - 1))]);
    G.capped = ls.length && ls[ls.length - 1] > vmax;
  }
  G.vmax = vmax; G.val = val;
  const X = (j) => left + j * cw, Y = (i) => top + i * ch;
  const span = (gs) => { const out = []; let k = 0; gs.forEach((g) => { out.push([k, k + g.list.length, g]); k += g.list.length; }); return out; };
  const RS = span(G.O.rows), CS = span(G.O.cols);
  G.RS = RS; G.CS = CS;
  c.fillStyle = css("--wash-2");
  const colIdx = new Map(cols.map((cc, j) => [typeof cc.x === "number" ? cc.x : "own" + cc.x.own, j]));
  for (const [a, b, g] of RS) {
    if (g.same) { const cg = CS.find((x) => x[2].key === g.key); if (cg) c.fillRect(X(cg[0]), Y(a), (cg[1] - cg[0]) * cw, (b - a) * ch); }
    if (g.module) for (let k = a; k < b; k++) {
      const j = scope === "cant" ? colIdx.get("own" + H.blocks[rows[k].x].r) : colIdx.get(rows[k].x);
      if (j != null) c.fillRect(X(j), Y(k), cw, ch);
    }
  }
  const gap = Math.min(cw, ch) >= 7 ? 1 : 0, lv = Math.log1p(vmax);
  val.forEach((row, i) => row.forEach((v, j) => {
    if (!v || !v.v) return;
    const u = layer === "court" ? Math.min(1, Math.log(v.v) / Math.log(Math.max(2, vmax))) : Math.log1p(v.v) / lv;
    c.fillStyle = RAMP[Math.min(RAMP.length - 1, Math.round(u * (RAMP.length - 1)))];
    c.fillRect(X(j), Y(i), cw - gap, ch - gap);
  }));
  const Wd = cols.length * cw, Hd = rows.length * ch;
  c.strokeStyle = css("--rule-2"); c.lineWidth = 1;
  c.beginPath();
  for (const [a] of RS.slice(1)) { c.moveTo(left - 4, Y(a) + 0.5); c.lineTo(left + Wd, Y(a) + 0.5); }
  for (const [a] of CS.slice(1)) { c.moveTo(X(a) + 0.5, top - 4); c.lineTo(X(a) + 0.5, top + Hd); }
  c.stroke();
  c.strokeStyle = css("--ink"); c.strokeRect(left + 0.5, top + 0.5, Wd, Hd);
  const fedN = (gs) => gs.filter((g) => g.key !== "ct" && g.key !== "own").reduce((s, g) => s + g.list.length, 0);
  if (scope === "all") {
    c.lineWidth = 1.5; c.beginPath();
    c.moveTo(left - 8, Y(fedN(G.O.rows))); c.lineTo(left + Wd, Y(fedN(G.O.rows)));
    c.moveTo(X(fedN(G.O.cols)), top - 8); c.lineTo(X(fedN(G.O.cols)), top + Hd); c.stroke(); c.lineWidth = 1;
  }
  // labels
  c.textBaseline = "middle";
  const ink = css("--ink"), ink2 = css("--ink-2"), ink3 = css("--ink-3");
  const rowLabels = scope === "fed" || ch >= 11;
  for (const [a, b, g] of RS) {
    if (g.key === "ct") {
      c.font = `600 ${Math.min(11, Math.max(8, (Y(b) - Y(a)) * 0.6))}px ${MONO}`; c.textAlign = "right"; c.fillStyle = ink;
      if (Y(b) - Y(a) >= 9) c.fillText(g.name, left - (rowLabels ? 96 : 8), (Y(a) + Y(b)) / 2);
    } else if (!rowLabels) {
      c.font = `600 11px ${SANS}`; c.textAlign = "right"; c.fillStyle = ink2;
      c.fillText(fitC(c, g.name, left - 16), left - 8, (Y(a) + Y(b)) / 2);
    }
  }
  if (rowLabels) {
    c.font = `500 ${Math.min(11.5, ch * 0.8)}px ${SANS}`; c.textAlign = "right"; c.fillStyle = ink2;
    rows.forEach((r, i) => { if (H.blocks[r.x].r < 4 || H.blocks[r.x].r === "bv") c.fillText(fitC(c, shortName(r.x), left - 34), left - 8, Y(i) + ch / 2); else c.fillText(fitC(c, t(H.blocks[r.x].r === 4 ? "c0" : "c" + (H.blocks[r.x].r - 4)), 88), left - 8, Y(i) + ch / 2); });
    c.font = `600 10.5px ${SANS}`; c.fillStyle = ink3;
    for (const [a, b, g] of RS) {                           // the groups of rows: a band with the name
      if (g.key === "ct" || Y(b) - Y(a) < 40) continue;
      c.save(); c.translate(10, (Y(a) + Y(b)) / 2); c.rotate(-Math.PI / 2); c.textAlign = "center";
      c.fillText(fitC(c, g.name, Y(b) - Y(a) - 6), 0, 0); c.restore(); c.textAlign = "right";
    }
  }
  c.textAlign = "center";
  for (const [a, b, g] of CS) {
    const x0 = X(a), x1 = X(b), w = x1 - x0;
    if (g.key === "ct") { c.font = `600 ${Math.min(11, Math.max(7.5, w * 0.42))}px ${MONO}`; c.fillStyle = ink; if (w >= 11) c.fillText(g.name, (x0 + x1) / 2, top - 12); }
    else if (scope !== "all") { c.font = `600 10.5px ${SANS}`; c.fillStyle = ink2; if (w >= c.measureText(g.name).width * 0.8) c.fillText(fitC(c, g.name, Math.max(20, w - 4)), (x0 + x1) / 2, top - 140); }
  }
  if (scope === "all") { const k = fedN(G.O.cols); c.font = `600 11px ${SANS}`; c.fillStyle = ink2; c.fillText(t("mFed"), left + (k * cw) / 2, top - 12, k * cw - 6); }
  if (scope !== "all" && cw >= 8) {
    c.font = `500 ${Math.min(11, cw * 0.8)}px ${SANS}`; c.fillStyle = ink2; c.textAlign = "left";
    cols.forEach((cc, j) => {
      const txt = typeof cc.x === "number" ? shortName(cc.x) : t(cc.x.own === 4 ? "c0" : "c" + (cc.x.own - 4));
      const steep = cw < 15;
      c.save(); c.translate(X(j) + cw * (steep ? 0.5 : 0.62), top - 6); c.rotate(steep ? -Math.PI / 2 : -Math.PI / 3);
      c.textBaseline = steep ? "middle" : "alphabetic"; c.fillText(fitC(c, txt, 110), 0, 0); c.restore();
    });
  }
  foot();
  drawHot();
}
function foot() {
  const unit = layer === "basis" ? t("acts") : layer === "law" ? t("mProvisions") : t("mLift");
  const ticks = (layer === "court" ? [2, 10, 100] : [1, 10, 100, 1000]).filter((v) => v <= G.vmax * 0.8);
  const grad = `linear-gradient(90deg,${RAMP.join(",")})`;
  let html = `<span class="mramp"><span>${esc(unit)}</span><span class="num">${layer === "court" ? "1" : "1"}</span><i style="background:${grad}"></i><span class="num">${esc((G.capped ? "≥ " : "") + num(Math.round(G.vmax)))}</span></span>` +
    `<span class="mkey"><span><i class="sw" style="background:var(--wash-2)"></i>${esc(t("mSame"))}</span></span>`;
  if (TV.TIME.on && layer !== "basis") html += `<span class="mkey"><span>${esc(t("timeToday"))}</span></span>`;
  if (layer === "basis" && H.rank && !TV.TIME.on) {
    const r = H.rank, tot = r.higher + r.same + r.lower, pc = (x) => (100 * x) / tot;
    html += `<span class="mkey"><span class="mshare" aria-hidden="true"><i style="flex:${r.higher};background:var(--c1)"></i><i style="flex:${r.same};background:var(--c2)"></i><i style="flex:${Math.max(r.lower, tot / 400)};background:var(--accent)"></i></span>` +
      `<span>${esc(t("mHigher"))} ${Math.round(pc(r.higher))} %</span><span>${esc(t("mSame"))} ${Math.round(pc(r.same))} %</span>` +
      `<button class="lowbtn" data-low="1">${esc(t("mLower"))}: ${esc(num(r.lower))}</button></span>`;
  }
  $("mfoot").innerHTML = html;
  const b = $("mfoot").querySelector("[data-low]"); if (b) b.onclick = lowPanel;
}
function drawHot() {
  if (!G) return;
  const c = $("mx").getContext("2d");
  c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, G.VW, G.VH);
  const draw = (cell, strong) => {
    if (!cell) return;
    const [i, j] = cell, x = G.left + j * G.cw, y = G.top + i * G.ch;
    if (strong) { c.fillStyle = "rgba(14,17,22,.05)"; c.fillRect(G.left, y, G.cols.length * G.cw, G.ch); c.fillRect(x, G.top, G.cw, G.rows.length * G.ch); }
    c.strokeStyle = strong ? css("--ink") : css("--accent"); c.lineWidth = 2;
    c.strokeRect(x - 1, y - 1, G.cw + 2, G.ch + 2);
  };
  draw(selCell, false); draw(hotCell, true);
}
function cellAt(e) {
  const r = $("mx").getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
  const j = Math.floor((x - G.left) / G.cw), i = Math.floor((y - G.top) / G.ch);
  return i >= 0 && j >= 0 && i < G.rows.length && j < G.cols.length ? [i, j] : null;
}
const fx = (v) => v.toFixed(1).replace(".", lang() === "en" ? "." : ",");
function tipHtml([i, j]) {
  const a = G.rows[i].x, b = colOf(G.cols[j].x, a), v = G.val[i][j];
  let s;
  if (layer === "basis") s = v ? (v.np == null ? t("mBasisCellY", t("nActs", num(v.n))) : t("mBasisCell", t("nActs", num(v.n)), num(v.np))) : t("mNone");
  else if (layer === "law") s = v ? t("mLawCell", num(v.n), num(v.p)) : t("mNone");
  else s = a === b ? t("mDiag") : !v ? t("mNone") : v.n < MIN_DEC || v.l <= 1 ? `${t("mFew")} (${num(v.n)})` : t("mCourtCell", num(v.n), fx(v.l));
  const rel = floorOf(b) < floorOf(a) ? t("mHigher") : floorOf(b) === floorOf(a) ? t("mSame") : t("mLower");
  return `<b>${esc(full(a))}</b><span class="t2">→ ${esc(full(b))}</span><span class="t3">${esc(s)}${layer === "basis" && v ? " · " + esc(rel) : ""}</span>`;
}
function sec(h, body, n) { return body ? `<section><h2><span>${esc(h)}</span>${n != null ? `<span class="n">${esc(num(n))}</span>` : ""}</h2>${body}</section>` : ""; }
function rows(items, render, cap = 12) {
  if (!items.length) return "";
  return `<ul class="rows">${items.map((x, k) => `<li${k >= cap ? " hidden" : ""}>${render(x)}</li>`).join("")}${items.length > cap ? `<li><button class="moreb" data-more="1">+ ${esc(t("more", num(items.length - cap)))}</button></li>` : ""}</ul>`;
}
const actA = (i, v, b) => `<a class="r" href="${href(idOf(i))}"><span class="a">${sw(M.cls[i] >= 0 ? M.cls[i] : 6)}${esc(labelCt(i))}</span>${v ? `<span class="v">${esc(v)}</span>` : ""}${b ? `<span class="b">${esc(b)}</span>` : ""}</a>`;
async function cellPanel(a, b) {
  const v = value(a, b);
  selCell = cellOf(a, b); drawHot();
  let html = "";
  if (layer === "basis") {
    const pairs = await getJSON("data/pairs.json");
    const by = new Map();
    for (const [ra, rb, i, j, art] of pairs) {
      if (ra !== a || rb !== b || i < 0 || !TV.exists(i) || (j >= 0 && !TV.exists(j))) continue;
      if (!by.has(i)) by.set(i, []);
      by.get(i).push([j, art]);
    }
    const items = [...by.entries()].sort((p, q) => M.D[q[0]] - M.D[p[0]] || p[0] - q[0]);
    html = `<div class="stat"><b>${esc(num(items.length))}</b><span>${esc(t("acts"))}</span></div><p class="note">${esc(v ? (v.np == null ? t("mBasisCellY", t("nActs", num(v.n))) : t("mBasisCell", t("nActs", num(v.n)), num(v.np))) : t("mNone"))}</p>` +
      sec(t("restsOn"), rows(items, ([i, js]) => actA(i, "", "→ " + js.map(([j, art]) => (art ? `${M.CT[j] && M.meta.ksym[M.CT[j]] === "§" ? "§" : t("art")} ${art} ` : "") + (j >= 0 ? labelCt(j) : "?")).join("; "))));
  } else {
    const L = await loadLinks(), m = index(), pairs = [];
    const src = layer === "law" ? L.out : L.co;
    for (const [i, list] of src) {
      if (m.blockOf.get(i) !== a) continue;
      for (const x of list) if (m.blockOf.get(x.j) === b) pairs.push([i, x.j, x.n]);
    }
    pairs.sort((p, q) => q[2] - p[2] || p[0] - q[0]);
    const unit = layer === "law" ? (n) => t("provisions", num(n)) : (n) => t("together", num(n));
    html = `<div class="stat"><b>${esc(num(v ? v.n : 0))}</b><span>${esc(layer === "law" ? t("mProvisions") : t("decisions"))}</span></div>` +
      (layer === "court" && v ? `<p class="note">${esc(t("mCourtCell", num(v.n), fx(v.l)))}</p>` : "") +
      sec(layer === "law" ? t("refersTo") : t("cocited"), rows(pairs, ([i, j, n]) => actA(i, unit(n), (layer === "law" ? "→ " : "↔ ") + labelCt(j))));
  }
  ctx.panel.custom({ kicker: `<span>${esc(t(layer === "basis" ? "mBasis" : layer === "law" ? "mLaw" : "mCourt"))}</span>`, h1: full(a), lede: "→ " + full(b), html }, { close: () => { selCell = null; drawHot(); sidePanel(); } });
  wire();
}
function cellOf(a, b) {
  const i = G.rows.findIndex((r) => r.x === a), j = G.cols.findIndex((c) => colOf(c.x, a) === b);
  return i >= 0 && j >= 0 ? [i, j] : null;
}
function wire() {
  const d = $("dossier");
  d.querySelectorAll("[data-more]").forEach((b) => { b.onclick = () => { const ul = b.closest("ul"); ul.querySelectorAll("li[hidden]").forEach((li) => (li.hidden = false)); b.parentElement.remove(); }; });
  d.querySelectorAll("[data-cell]").forEach((b) => (b.onclick = () => { const [a, c] = b.dataset.cell.split(",").map(Number); cellPanel(a, c); }));
  d.querySelectorAll("[data-cell]").forEach((b) => (b.onpointerenter = () => { const [a, c] = b.dataset.cell.split(",").map(Number); hotCell = cellOf(a, c); drawHot(); }));
}
// with nothing chosen: the strongest cells
function sidePanel() {
  if (!G || matchMedia("(max-width: 1180px)").matches) { ctx.panel.hide(); return; }
  const cells = [], seen = new Set();
  G.val.forEach((row, i) => row.forEach((v, j) => {
    if (!v || !v.v) return;
    const a = G.rows[i].x, b = colOf(G.cols[j].x, a);
    if (layer === "court") { const k = Math.min(a, b) * 1024 + Math.max(a, b); if (seen.has(k)) return; seen.add(k); }
    cells.push([a, b, v]);
  }));
  const score = (v) => (layer === "court" ? v.n * Math.log(v.l) : v.v);
  cells.sort((p, q) => score(q[2]) - score(p[2]));
  const sideName = (b) => (H.blocks[b].r >= 1 && H.blocks[b].r <= 3 ? `${shortName(b)} · ${t("c" + H.blocks[b].r)}` : shortName(b));
  const fmtV = (v) => (layer === "basis" ? t("nActs", num(v.n)) : layer === "law" ? t("provisions", num(v.n)) : `${fx(v.l)}×`);
  const title_ = layer === "basis" ? t("mTitleBasis") : layer === "law" ? t("mTitleLaw") : t("mTitleCourt");
  ctx.panel.custom({ kicker: `<span>${esc(t(layer === "basis" ? "mBasis" : layer === "law" ? "mLaw" : "mCourt"))}</span>`, h1: t("mTop"), lede: title_,
    html: `<ul class="rows">${cells.slice(0, 16).map(([a, b, v]) => `<li><button class="r wrap" data-cell="${a},${b}"><span class="a">${esc(sideName(a))} ${layer === "court" ? "↔" : "→"} ${esc(sideName(b))}</span><span class="v">${esc(fmtV(v))}</span></button></li>`).join("")}</ul>` }, { closable: false });
  wire();
}
// bases on a lower level than the act naming them: each read by hand (decision 26)
async function lowPanel() {
  const low = H.low;
  const html = [`<div class="stat"><b>${esc(num(low.items.length))}</b><span>${esc(t("mLowList"))}</span></div>`];
  low.cats.forEach((c, k) => {
    const by = new Map();
    for (const [i, j, ck] of low.items) if (ck === k && i >= 0) { if (!by.has(i)) by.set(i, []); by.get(i).push(j); }
    if (!by.size) return;
    const n = [...by.values()].reduce((s, x) => s + x.length, 0);
    const acts = [...by.entries()].sort((p, q) => M.D[q[0]] - M.D[p[0]] || p[0] - q[0]);
    html.push(sec(t("low_" + c), rows(acts, ([i, js]) => actA(i, "", "→ " + js.map((j) => (j >= 0 ? labelCt(j) : "?")).join("; ")), 6), n));
  });
  ctx.panel.custom({ kicker: `<span>${esc(t("mBasis"))}</span>`, h1: t("mLower"), html: html.join("") }, { close: sidePanel });
  wire();
}
function controls() {
  $("mtitle").textContent = layer === "basis" ? t("mTitleBasis") : layer === "law" ? t("mTitleLaw") : t("mTitleCourt");
  $("mlayer").innerHTML = [["basis", t("mBasis")], ["law", t("mLaw")], ["court", t("mCourt")]].map(([k, l]) => `<button data-layer="${k}" aria-pressed="${layer === k}">${esc(l)}</button>`).join("");
  $("mscope").innerHTML = [["all", t("mAll")], ["fed", t("mFed")], ["cant", t("mCant")]].map(([k, l]) => `<button data-scope="${k}" aria-pressed="${scope === k}">${esc(l)}</button>`).join("");
  $("mx").setAttribute("aria-label", $("mtitle").textContent);
}
export async function init(c) {
  ctx = c;
  H = await ensure();
  $("mlayer").addEventListener("click", (e) => { const b = e.target.closest("[data-layer]"); if (!b) return; layer = b.dataset.layer; selCell = null; controls(); render(); sidePanel(); });
  $("mscope").addEventListener("click", (e) => { const b = e.target.closest("[data-scope]"); if (!b) return; scope = b.dataset.scope; selCell = null; controls(); render(); sidePanel(); });
  const mx = $("mx"), tip = $("tip");
  mx.addEventListener("pointermove", (e) => {
    const cell = cellAt(e), key = cell ? cell.join(":") : "";
    if (key !== (hotCell ? hotCell.join(":") : "")) { hotCell = cell; drawHot(); }
    if (!cell) { tip.hidden = true; return; }
    tip.innerHTML = tipHtml(cell); tip.hidden = false;
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    let x = e.clientX + 14, y = e.clientY + 16;
    if (x + tw > innerWidth - 8) x = e.clientX - tw - 12;
    if (y + th > innerHeight - 8) y = e.clientY - th - 12;
    tip.style.left = x + "px"; tip.style.top = y + "px";
  });
  mx.addEventListener("pointerleave", () => { hotCell = null; drawHot(); tip.hidden = true; });
  mx.addEventListener("click", (e) => {
    const cell = cellAt(e); if (!cell) return;
    const a = G.rows[cell[0]].x, b = colOf(G.cols[cell[1]].x, a);
    if (!value(a, b)) return;
    tip.hidden = true; cellPanel(a, b);
  });
  mx.addEventListener("keydown", (e) => {
    const d = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] }[e.key];
    if (d) {
      e.preventDefault();
      const [i, j] = hotCell || [0, 0];
      hotCell = [Math.max(0, Math.min(G.rows.length - 1, i + d[0])), Math.max(0, Math.min(G.cols.length - 1, j + d[1]))];
      drawHot();
      const r = mx.getBoundingClientRect();
      tip.innerHTML = tipHtml(hotCell); tip.hidden = false;
      tip.style.left = r.left + G.left + (hotCell[1] + 1) * G.cw + 8 + "px"; tip.style.top = r.top + G.top + (hotCell[0] + 1) * G.ch + 8 + "px";
    } else if (e.key === "Enter" && hotCell) {
      const a = G.rows[hotCell[0]].x, b = colOf(G.cols[hotCell[1]].x, a);
      if (value(a, b)) cellPanel(a, b);
    }
  });
  new ResizeObserver(() => { if (!$("v-matrix").hidden) render(); }).observe($("mscroll"));
  TV.subscribe(async () => {
    if ($("v-matrix").hidden) return;
    await timeCells(); render();
    if (!selCell && !TV.playing()) sidePanel();
  });
}
export async function show() { controls(); await timeCells(); render(); if (!selCell) sidePanel(); }
export function refresh() { if (!$("v-matrix").hidden) { idx = null; show(); } }
