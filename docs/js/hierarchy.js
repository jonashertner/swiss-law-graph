// The hierarchy: every act in force, once, in its block (level × SR area for federal law, level ×
// canton for cantonal law), and one flow from the basis it hangs from (decision 23). A flow is exact
// at its lower end and a share of its source's outflow at its upper end. Acts with no basis in the
// hierarchy stand as stubs on their block, by reason (decision 24).
import { t, pick, cantonName, lang } from "./i18n.js";
import { M, loadHier, idOf, labelCt, title, isAct } from "./data.js";
import { $, esc, num, sw, href } from "./util.js";

let H = null, G = null, ctx = {}, sel = null, hot = null;
const ROWS = ["bv", 1, 2, 3, 4, 5, 6, 7];
const STUBS = ["fed", "unres", "lower", "none", "noing"];
const rowOf = (b) => ROWS.indexOf(H.blocks[b].r);
const sizeOf = (b) => (H.blocks[b].r === "bv" || H.blocks[b].r === 4 ? H.blocks[b].o : H.blocks[b].n);
const part = (b) => (rowOf(b) <= 3 ? "F" : "C");
const cls = (b) => { const r = H.blocks[b].r; return r === "bv" ? (H.blocks[b].k === "int" ? 4 : H.blocks[b].k === "1874" ? 5 : 0) : r === 4 ? 0 : r <= 3 ? r : r - 4; };
const clsRow = (r) => (r === "bv" || r === 4 ? 0 : r <= 3 ? r : r - 4);

export function nameOf(b, short) {
  const { r, k } = H.blocks[b];
  if (r === "bv") {
    if (k === "1874") return t("bv1874");
    if (k === "int") return t("treaties");
    const p = H.bvparts[String(k)];
    if (!p) return t("bvWhole");
    const n = (pick(p.num) || "").replace(/:$/, ""), h = pick(p.h) || "";
    return short ? h || n : `${n} ${h}`.trim();
  }
  if (r >= 1 && r <= 3) {
    const i = M.byId.get("c" + k), l = i != null ? (M.L[i] || "") : "";
    return short ? `${k} ${l.split(/\s+[–-]\s+/)[0]}` : `${k} ${l}`;
  }
  if (r === 4) return short ? k : `${t("row4")} · ${cantonName(k)}`;
  return short ? k : `${cantonName(k)} · ${t("c" + (r - 4))}`;
}
export const rowName = (r) => t(r === "bv" ? "rowBV" : "row" + r);

function layout() {
  const box = $("hscroll").getBoundingClientRect();
  const phone = box.width < 760;
  const VW = Math.max(phone ? 1080 : 980, Math.floor(box.width) - 24), VH = Math.max(phone ? 820 : 640, Math.floor(box.height) - 4);
  const gut = 172;                                        // row names left of the rows (a phone scrolls sideways)
  const x0 = gut + 34, x1 = VW - 24, y0 = phone ? 96 : 92, y1 = VH - 30;
  const rowH = 18;
  const unit = (y1 - y0 - ROWS.length * rowH) / 7.8;
  const Y = []; let y = y0;
  ROWS.forEach((r, q) => { Y.push(y); y += rowH + (q === 3 ? unit * 1.8 : unit); });
  const B = H.blocks, nB = B.length;
  const flows = H.flows.map(([s, d, m], q) => ({ q, s, d, n: m.length, m }));
  const trunk = flows.filter((f) => B[f.s].r === "bv" && B[f.d].r === 4);
  const isSkip = (f) => rowOf(f.d) - rowOf(f.s) > 1 && part(f.s) === part(f.d);
  const cols = { F: ["1", "2", "3", "4", "5", "6", "7", "8", "9"], C: H.ct_order };
  const colOf = (b) => (B[b].r === "bv" ? null : B[b].k);
  const wmax = {}, lane = {};
  for (let b = 0; b < nB; b++) { const c = colOf(b); if (c != null && sizeOf(b)) wmax[c] = Math.max(wmax[c] || 0, sizeOf(b)); }
  for (const f of flows) if (isSkip(f)) lane[colOf(f.d)] = (lane[colOf(f.d)] || 0) + f.n;
  const g = { phone, gut, VW, VH, x0, x1, y0, y1, rowH, Y, unit, k: {}, blocks: [], flows, trunk, lanes: {} };
  for (const P of ["F", "C"]) {
    const gap = P === "F" ? 12 : 4, list = cols[P].filter((c) => wmax[c]);
    const units = list.reduce((s, c) => s + wmax[c] + (lane[c] || 0), 0);
    const k = (x1 - x0 - gap * (list.length - 1) - list.filter((c) => lane[c]).length * 3) / units;
    g.k[P] = k;
    let x = x0;
    for (const c of list) {
      g.lanes[c] = { x: x + wmax[c] * k + 2, used: 0 };
      g[c] = { x, w: wmax[c] * k };
      x += wmax[c] * k + (lane[c] ? lane[c] * k + 3 : 0) + gap;
    }
  }
  for (let b = 0; b < nB; b++) {
    const c = colOf(b), w = sizeOf(b) * g.k[part(b)];
    if (c == null || !w) continue;
    g.blocks[b] = { x: g[c].x + (g[c].w - w) / 2, y: Y[rowOf(b)], w, h: rowH };
  }
  // the Constitution's row, on its own scale: each part near the mean position of what rests on it
  const bvList = []; for (let b = 0; b < nB; b++) if (B[b].r === "bv" && B[b].o) bvList.push(b);
  g.k.BV = (x1 - x0 - 6 * (bvList.length - 1)) / Math.max(1, bvList.reduce((s, b) => s + B[b].o, 0));
  const bvs = [];
  for (const b of bvList) {
    let sx = 0, sn = 0;
    for (const f of flows) if (f.s === b && g.blocks[f.d] && B[f.d].r !== 4) { sx += (g.blocks[f.d].x + g.blocks[f.d].w / 2) * f.n; sn += f.n; }
    bvs.push([b, sn ? sx / sn : x0, B[b].o * g.k.BV]);
  }
  bvs.sort((a, b) => a[1] - b[1] || a[0] - b[0]);
  let right = x0 - 6;
  for (const [b, c, w] of bvs) { const x = Math.max(c - w / 2, right + 6); g.blocks[b] = { x, y: Y[0], w, h: rowH }; right = x + w; }
  if (right > x1) { const sh = right - x1; for (const [b] of bvs) g.blocks[b].x = Math.max(x0, g.blocks[b].x - sh); }
  for (let q = 1; q < bvs.length; q++) { const a = g.blocks[bvs[q - 1][0]], z = g.blocks[bvs[q][0]]; if (z.x < a.x + a.w + 4) z.x = a.x + a.w + 4; }
  const cx = (b) => g.blocks[b].x + g.blocks[b].w / 2;
  const ins = {}, outs = {};
  for (const f of flows) { (outs[f.s] = outs[f.s] || []).push(f); (ins[f.d] = ins[f.d] || []).push(f); }
  const stubs = H.stubs.map(([d, kind, m], q) => ({ q, d, g: kind, n: m.length, m }));
  for (const s of stubs) (ins[s.d] = ins[s.d] || []).push(s);
  for (const f of flows) if (isSkip(f)) {
    const L = g.lanes[colOf(f.d)], w = f.n * g.k[part(f.d)];
    f.lane = [L.x + L.used, L.x + L.used + w]; L.used += w;
  }
  for (const [b, list] of Object.entries(outs)) {
    const gb = g.blocks[b]; if (!gb) continue;
    const tot = list.reduce((s, f) => s + f.n, 0);
    list.sort((p, q) => (p.lane ? p.lane[0] : B[p.d].r === 4 ? -1e9 : g.blocks[p.d] ? cx(p.d) : 0) - (q.lane ? q.lane[0] : B[q.d].r === 4 ? -1e9 : g.blocks[q.d] ? cx(q.d) : 0) || p.q - q.q);
    let x = gb.x;
    for (const f of list) { const w = (f.n / tot) * gb.w; f.sa = x; f.sb = x + w; x += w; }
  }
  for (const [b, list] of Object.entries(ins)) {
    const gb = g.blocks[b]; if (!gb) continue;
    const k = g.k[part(+b)];
    const key = (f) => (f.g ? -2e9 + STUBS.indexOf(f.g) : f.lane ? 1e9 + f.lane[0] : B[f.s].r === "bv" && B[+b].r === 4 ? -1.5e9 : g.blocks[f.s] ? cx(f.s) : 0);
    list.sort((p, q) => key(p) - key(q) || (p.q ?? 0) - (q.q ?? 0));
    let x = gb.x;
    for (const f of list) { const w = f.n * k; f.ta = x; f.tb = x + w; x += w; }
  }
  g.stubs = stubs;
  return g;
}
const f1 = (v) => v.toFixed(1);
function ribbon(f) {
  const s = G.blocks[f.s], d = G.blocks[f.d];
  const ys = s.y + s.h, yt = d.y;
  if (f.lane) {
    const [la, lb] = f.lane, y1 = ys + G.unit * 0.42, y2 = yt - G.unit * 0.42, m1 = (ys + y1) / 2, m2 = (y2 + yt) / 2;
    return `M${f1(f.sa)},${f1(ys)}C${f1(f.sa)},${f1(m1)} ${f1(la)},${f1(m1)} ${f1(la)},${f1(y1)}L${f1(la)},${f1(y2)}C${f1(la)},${f1(m2)} ${f1(f.ta)},${f1(m2)} ${f1(f.ta)},${f1(yt)}` +
      `L${f1(f.tb)},${f1(yt)}C${f1(f.tb)},${f1(m2)} ${f1(lb)},${f1(m2)} ${f1(lb)},${f1(y2)}L${f1(lb)},${f1(y1)}C${f1(lb)},${f1(m1)} ${f1(f.sb)},${f1(m1)} ${f1(f.sb)},${f1(ys)}Z`;
  }
  const ym = (ys + yt) / 2;
  return `M${f1(f.sa)},${f1(ys)}C${f1(f.sa)},${f1(ym)} ${f1(f.ta)},${f1(ym)} ${f1(f.ta)},${f1(yt)}L${f1(f.tb)},${f1(yt)}C${f1(f.tb)},${f1(ym)} ${f1(f.sb)},${f1(ym)} ${f1(f.sb)},${f1(ys)}Z`;
}
const STUBFILL = { fed: "var(--c1)", unres: "var(--c4)", lower: "var(--c4)", none: "var(--rule-2)", noing: "url(#hatch)" };

function render() {
  if (!H) return;
  G = layout();
  const svg = $("hsvg"), B = H.blocks, out = [];
  svg.setAttribute("viewBox", `0 0 ${G.VW} ${G.VH}`);
  svg.setAttribute("width", G.VW); svg.setAttribute("height", G.VH);
  svg.setAttribute("aria-label", t("hierTitle"));
  out.push(`<defs><pattern id="hatch" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="4" height="4" fill="#fff"/><line x1="0" y1="0" x2="0" y2="4" stroke="var(--rule-2)" stroke-width="2"/></pattern></defs>`);
  // rows: names and their counts
  const rowTot = {};
  for (let b = 0; b < B.length; b++) rowTot[B[b].r] = (rowTot[B[b].r] || 0) + (B[b].r === "bv" ? 0 : B[b].n);
  ROWS.forEach((r, q) => {
    if (G.gut) {
      const y = G.Y[q] + G.rowH / 2 + 4;
      out.push(`<text class="row" x="0" y="${f1(y - 7)}">${esc(rowName(r))}</text>`);
      if (r !== "bv") out.push(`<text class="rown" x="0" y="${f1(y + 8)}">${esc(t("nActs", num(rowTot[r] || 0)))}</text>`);
    } else out.push(`<text class="row" x="${G.x0}" y="${f1(G.Y[q] - (q === 0 ? 46 : 8))}">${esc(rowName(r))}${r !== "bv" ? `<tspan class="rown" dx="8">${esc(num(rowTot[r] || 0))}</tspan>` : ""}</text>`);
  });
  const yDiv = G.Y[3] + G.rowH + G.unit * 0.9;
  out.push(`<line class="divider" x1="0" x2="${G.x1}" y1="${f1(yDiv)}" y2="${f1(yDiv)}"/>`);
  out.push(`<text class="divt" x="${G.x1}" y="${f1(yDiv + 15)}" text-anchor="end">${esc(t("prevails"))}</text>`);
  // flows
  out.push(`<g id="hflows">`);
  for (const f of G.flows) {
    if (!G.blocks[f.s] || !G.blocks[f.d] || f.sa == null) continue;
    if (B[f.s].r === "bv" && B[f.d].r === 4) continue;
    out.push(`<path class="flow${cls(f.d) === 1 ? " f0" : ""}" data-f="${f.q}" d="${ribbon(f)}"/>`);
  }
  out.push(`</g>`);
  for (const s of G.stubs) {
    const gb = G.blocks[s.d]; if (!gb || s.ta == null) continue;
    const h = Math.min(G.unit * 0.5, 26);
    out.push(`<rect class="stub" data-s="${s.q}" x="${f1(s.ta)}" y="${f1(gb.y - h)}" width="${f1(Math.max(0.6, s.tb - s.ta))}" height="${f1(h)}" fill="${STUBFILL[s.g]}"/>`);
  }
  if (G.trunk.length) {                                   // Art. 51 BV: down the left into the 26 constitutions
    const src = G.blocks[G.trunk[0].s], sa = Math.min(...G.trunk.map((f) => f.sa)), sb = Math.max(...G.trunk.map((f) => f.sb));
    const xt = G.x0 - 22, yb = G.Y[4] - G.unit * 0.4, ys = src.y + src.h;
    out.push(`<path class="trunk" d="M${f1((sa + sb) / 2)},${f1(ys)}C${f1((sa + sb) / 2)},${f1(ys + G.unit * 0.5)} ${f1(xt)},${f1(ys + G.unit * 0.3)} ${f1(xt)},${f1(ys + G.unit)}L${f1(xt)},${f1(yb)}L${f1(Math.max(...G.trunk.map((f) => G.blocks[f.d].x)))},${f1(yb)}"/>`);
    for (const f of G.trunk) { const d = G.blocks[f.d]; out.push(`<path class="trunk" style="stroke-width:1" d="M${f1(d.x + 1)},${f1(yb)}L${f1(d.x + 1)},${f1(d.y)}"/>`); }
    out.push(`<text class="trunkt" x="${f1(xt + 6)}" y="${f1(yb - 6)}">${esc(t("art51"))}</text>`);
  }
  // canton codes below the lowest row
  const yFoot = G.Y[7] + G.rowH + 14;
  for (const ct of H.ct_order) if (G[ct]) out.push(`<text class="colt" x="${f1(G[ct].x + G[ct].w / 2)}" y="${f1(yFoot)}" text-anchor="middle">${esc(ct)}</text>`);
  // blocks
  let bvLast = -1e9;
  const order = [...B.keys()].filter((b) => G.blocks[b]).sort((p, q) => G.blocks[p].x - G.blocks[q].x);
  for (const b of order) {
    const g = G.blocks[b], c = cls(b), n = sizeOf(b);
    const name = nameOf(b, true), fits = (s) => s.length * 6.1 + 8 < g.w;
    const txt = B[b].r === "bv" ? (fits(num(n)) ? num(n) : "") : fits(`${name} · ${num(n)}`) ? `${name} · ${num(n)}` : fits(name) ? name : fits(String(B[b].k)) ? String(B[b].k) : "";
    if (B[b].r === "bv" && n >= 3 && g.x - bvLast >= 28) {
      const nm = name.length > 28 ? name.slice(0, 27) + "…" : name;
      bvLast = g.x;
      out.push(`<text class="bvt" transform="translate(${f1(g.x + 2)},${f1(g.y - 5)}) rotate(-32)">${esc(nm)}</text>`);
    }
    out.push(`<g class="blk" data-b="${b}" tabindex="0" role="button" aria-label="${esc(rowName(B[b].r) + ": " + nameOf(b) + ", " + t("nActs", num(n)))}">` +
      `<rect x="${f1(g.x)}" y="${f1(g.y)}" width="${f1(Math.max(1, g.w))}" height="${g.h}" fill="var(--c${c})"${c === 5 ? ' fill-opacity=".9"' : ""}/>` +
      (txt ? `<text x="${f1(g.x + 4)}" y="${f1(g.y + g.h / 2 + 3.8)}" fill="var(--on-c${c})">${esc(txt)}</text>` : "") + `</g>`);
  }
  svg.innerHTML = out.join("");
  // the key: stubs, and the three scales
  const tot = (kind) => H.stubs.reduce((a, [, k, m]) => a + (k === kind ? m.length : 0), 0);
  $("hkey").innerHTML = `<span>${esc(t("noParent"))}</span>` + STUBS.map((k) => `<button data-stub="${k}"><i class="sw s-${k}"></i>${esc(t("stub_" + k))} <b class="num">${esc(num(tot(k)))}</b></button>`).join("");
  const sc = (k) => { const n = [5, 10, 20, 50, 100, 200, 500, 1000].filter((v) => v * k <= 90).pop() || 5; return [n, n * k]; };
  $("hfoot").innerHTML = `<span>${esc(t("scale"))}</span>` + [[t("rowBV"), G.k.BV], [t("mFed"), G.k.F], [t("mCant"), G.k.C]].map(([l, k]) => { const [n, w] = sc(k);
    return `<span class="scl"><i style="width:${w.toFixed(1)}px"></i>${esc(l)}: ${esc(t("nActs", num(n)))}</span>`; }).join("");
  if (sel) light(sel[0], sel[1], true);
}

// ---------- highlight and panels
function light(kind, id, keep) {
  const svg = $("hsvg");
  svg.querySelectorAll(".hot").forEach((e) => e.classList.remove("hot"));
  if (kind == null) { svg.classList.remove("dim"); return; }
  svg.classList.add("dim");
  const B = new Set();
  if (kind === "b") {
    B.add(id);
    for (const f of G.flows) if (f.s === id || f.d === id) { const p = svg.querySelector(`[data-f="${f.q}"]`); if (p) p.classList.add("hot"); B.add(f.s); B.add(f.d); }
    for (const s of G.stubs) if (s.d === id) { const p = svg.querySelector(`[data-s="${s.q}"]`); if (p) p.classList.add("hot"); }
  } else if (kind === "f") {
    const f = G.flows[id]; const p = svg.querySelector(`[data-f="${id}"]`); if (p) p.classList.add("hot"); B.add(f.s); B.add(f.d);
  } else if (kind === "s") {
    const s = G.stubs[id]; const p = svg.querySelector(`[data-s="${id}"]`); if (p) p.classList.add("hot"); B.add(s.d);
  } else if (kind === "k") {
    for (const s of G.stubs) if (s.g === id) { const p = svg.querySelector(`[data-s="${s.q}"]`); if (p) p.classList.add("hot"); B.add(s.d); }
  }
  for (const b of B) { const e = svg.querySelector(`[data-b="${b}"]`); if (e) e.classList.add("hot"); }
}
const byDec = (a, b) => M.D[b] - M.D[a] || a - b;
function actList(m, cap = 60) {
  const list = m.filter((i) => i >= 0).slice().sort(byDec);
  if (!list.length) return "";
  return `<ul class="rows">${list.map((i, k) => `<li${k >= 12 ? " hidden" : ""}><a class="r" href="${href(idOf(i))}"><span class="a">${sw(M.cls[i] >= 0 ? M.cls[i] : 6)}${esc(labelCt(i))}</span>` +
    `<span class="v">${M.D[i] ? esc(t("nDec", num(M.D[i]))) : ""}</span>${title(i) ? `<span class="b">${esc(title(i))}</span>` : ""}</a></li>`).slice(0, cap).join("")}` +
    `${list.length > 12 ? `<li><button class="moreb" data-more="1">+ ${esc(t("more", num(Math.min(cap, list.length) - 12)))}</button></li>` : ""}</ul>`;
}
function sec(h, body, n) { return body ? `<section><h2><span>${esc(h)}</span>${n != null ? `<span class="n">${esc(num(n))}</span>` : ""}</h2>${body}</section>` : ""; }
function blockRows(items) {
  return `<ul class="rows">${items.map(([b, n, q], k) => `<li${k >= 8 ? " hidden" : ""}><button class="r" data-hb="${b}"${q != null ? ` data-hf="${q}"` : ""}><span class="a">${sw(cls(b))}${esc(nameOf(b))}</span><span class="v">${esc(num(n))}</span><span class="b">${esc(rowName(H.blocks[b].r))}</span></button></li>`).join("")}` +
    `${items.length > 8 ? `<li><button class="moreb" data-more="1">+ ${esc(t("more", num(items.length - 8)))}</button></li>` : ""}</ul>`;
}
function blockPanel(b) {
  const B = H.blocks[b], n = sizeOf(b);
  const inn = G.flows.filter((f) => f.d === b).map((f) => [f.s, f.n, f.q]).sort((p, q) => q[1] - p[1]);
  const out = G.flows.filter((f) => f.s === b).map((f) => [f.d, f.n, f.q]).sort((p, q) => q[1] - p[1]);
  const st = G.stubs.filter((s) => s.d === b);
  const stubs = st.length ? `<div class="stackkey">${st.map((s) => `<span><i class="sw s-${s.g}"></i>${esc(t("stub_" + s.g))}</span><span class="num">${esc(num(s.n))}</span>`).join("")}</div>` : "";
  ctx.panel.custom({ kicker: `<span>${esc(rowName(B.r))}</span>`, h1: nameOf(b),
    html: `<div class="stat"><b>${esc(num(B.r === "bv" ? B.o : B.n))}</b><span>${esc(B.r === "bv" ? t("restOnBlock") : t("inForceActs"))}</span></div>` +
      sec(t("restFrom"), blockRows(inn)) + (stubs ? sec(t("noParent"), stubs) : "") + sec(t("restOnBlock"), blockRows(out)) +
      (B.r !== "bv" ? sec(t("actsHere"), actList(H.members[b] || []), (H.members[b] || []).length) : "") }, { close: clearSel });
  wirePanel();
}
function flowPanel(q) {
  const f = G.flows[q];
  ctx.panel.custom({ kicker: `<span>${esc(rowName(H.blocks[f.d].r))}</span>`, h1: `${nameOf(f.d)} → ${nameOf(f.s)}`,
    html: `<div class="stat"><b>${esc(num(f.n))}</b><span>${esc(t("flowFrom"))} ${esc(nameOf(f.s))}</span></div>` + sec(t("actsHere"), actList(f.m)) }, { close: clearSel });
  wirePanel();
}
function stubPanel(q) {
  const s = G.stubs[q];
  ctx.panel.custom({ kicker: `<span>${esc(t("noParent"))}</span>`, h1: `${nameOf(s.d)} · ${t("stub_" + s.g)}`,
    html: `<div class="stat"><b>${esc(num(s.n))}</b><span>${esc(t("actsHere"))}</span></div>` + sec(t("actsHere"), actList(s.m)) }, { close: clearSel });
  wirePanel();
}
function kindPanel(kind) {
  const by = G.stubs.filter((s) => s.g === kind), all = by.flatMap((s) => s.m);
  ctx.panel.custom({ kicker: `<span>${esc(t("noParent"))}</span>`, h1: t("stub_" + kind),
    html: `<div class="stat"><b>${esc(num(all.length))}</b><span>${esc(t("actsHere"))}</span></div>` +
      sec(t("hier"), blockRows(by.map((s) => [s.d, s.n]).sort((p, q) => q[1] - p[1]))) + sec(t("actsHere"), actList(all, 120)) }, { close: clearSel });
  wirePanel();
}
function wirePanel() {
  const d = $("dossier");
  d.querySelectorAll("[data-hb]").forEach((b) => (b.onclick = () => (b.dataset.hf != null ? pick2("f", +b.dataset.hf) : pick2("b", +b.dataset.hb))));
  d.querySelectorAll("[data-more]").forEach((b) => { b.onclick = () => { const ul = b.closest("ul"); ul.querySelectorAll("li[hidden]").forEach((li) => (li.hidden = false)); b.parentElement.remove(); }; });
}
function pick2(kind, id) {
  sel = [kind, id];
  light(kind, id);
  if (kind === "b") blockPanel(id); else if (kind === "f") flowPanel(id); else if (kind === "s") stubPanel(id); else kindPanel(id);
  const r = $("hsvg").querySelector(`.sel`); if (r) r.classList.remove("sel");
  if (kind === "b") { const e = $("hsvg").querySelector(`[data-b="${id}"]`); if (e) e.classList.add("sel"); }
}
function clearSel() { sel = null; light(null); ctx.panel.hide(); const r = $("hsvg").querySelector(".sel"); if (r) r.classList.remove("sel"); }
function tipFor(kind, id) {
  if (kind === "b") { const B = H.blocks[id]; return `<b>${esc(nameOf(id))}</b><span class="t2">${esc(rowName(B.r))}</span><span class="t3">${esc(B.r === "bv" ? t("nActs", num(B.o)) + " · " + t("restOnBlock") : t("nActs", num(B.n)))}</span>`; }
  if (kind === "f") { const f = G.flows[id]; return `<b>${esc(nameOf(f.d))}</b><span class="t2">${esc(t("flowFrom"))} ${esc(nameOf(f.s))}</span><span class="t3">${esc(t("nActs", num(f.n)))}</span>`; }
  const s = G.stubs[id];
  return `<b>${esc(nameOf(s.d))}</b><span class="t2">${esc(t("stub_" + s.g))}</span><span class="t3">${esc(t("nActs", num(s.n)))}</span>`;
}
function targetOf(e) {
  const b = e.target.closest("[data-b]"); if (b) return ["b", +b.dataset.b];
  const f = e.target.closest("[data-f]"); if (f) return ["f", +f.dataset.f];
  const s = e.target.closest("[data-s]"); if (s) return ["s", +s.dataset.s];
  return null;
}
export async function ensure() { if (!H) H = await loadHier(); return H; }
export async function init(c) {
  ctx = c;
  $("htitle").textContent = t("hierTitle");
  const svg = $("hsvg"), tip = $("tip");
  svg.addEventListener("pointermove", (e) => {
    const tg = targetOf(e);
    const key = tg ? tg.join(":") : "";
    if (key !== hot) { hot = key; if (!sel) light(tg ? tg[0] : null, tg ? tg[1] : null); }
    if (!tg) { tip.hidden = true; return; }
    tip.innerHTML = tipFor(tg[0], tg[1]); tip.hidden = false;
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    let x = e.clientX + 14, y = e.clientY + 16;
    if (x + tw > innerWidth - 8) x = e.clientX - tw - 12;
    if (y + th > innerHeight - 8) y = e.clientY - th - 12;
    tip.style.left = x + "px"; tip.style.top = y + "px";
  });
  svg.addEventListener("pointerleave", () => { tip.hidden = true; hot = null; if (!sel) light(null); else light(sel[0], sel[1]); });
  svg.addEventListener("click", (e) => { const tg = targetOf(e); if (tg) pick2(tg[0], tg[1]); else clearSel(); tip.hidden = true; });
  svg.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { const tg = targetOf(e); if (tg) { e.preventDefault(); pick2(tg[0], tg[1]); } } });
  $("hkey").addEventListener("click", (e) => { const b = e.target.closest("[data-stub]"); if (b) pick2("k", b.dataset.stub); });
  await ensure();
  new ResizeObserver(() => { if (!$("v-hier").hidden) render(); }).observe($("hscroll"));
}
export async function show() {
  $("htitle").textContent = t("hierTitle");
  if (!sel) ctx.panel.hide();
  render();
  if (sel) pick2(sel[0], sel[1]);
}
export function refresh() { if (!$("v-hier").hidden) show(); }
export { H as hierData, cls as blockClass, sizeOf };
