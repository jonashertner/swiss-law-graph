// The panel beside the map: what an act, an article or a part of the collection is, what it rests
// on, what rests on it, and how courts use it. Every number is the data's; every row is a link.
import { t, cantonName, pick, lang } from "./i18n.js";
import { M, KIND, kindOf, isAct, idOf, label, labelCt, title, srOf, urlOf, getJSON, loadLinks, loadYears, loadLaw } from "./data.js";
import { $, esc, num, date, sw, href, decUrl, ICON } from "./util.js";
import { headingOf } from "./treemap.js";

const el = () => $("dossier");
let token = 0, opts = {}, linker = null, extra = () => "";
export function setLinker(f) { linker = f; }
export function setExtra(f) { extra = f; }
const linkTo = (j) => (linker ? linker(j) : href(idOf(j)));
const LIST = 10;

export function hide() { el().hidden = true; el().innerHTML = ""; document.body.classList.remove("sheet"); }
function open(html, o) {
  opts = o || {};
  const d = el();
  const was = !d.hidden;
  d.hidden = false;
  document.body.classList.add("sheet");
  d.innerHTML = `<div class="grab" id="grab"></div>${o && o.closable !== false ? `<button class="x" id="dx" aria-label="${esc(t("close"))}" title="${esc(t("close"))}">${ICON.x}</button>` : ""}${html}`;
  if (!was || o.scrollTop !== false) d.scrollTop = 0;
  const x = $("dx"); if (x) x.onclick = () => (opts.close ? opts.close() : hide());
  const g = $("grab"); if (g) g.onclick = () => d.classList.toggle("full");
  wire(d);
}
function wire(d) {
  d.querySelectorAll("[data-more]").forEach((b) => {
    b.onclick = () => { const ul = b.closest("ul"); ul.querySelectorAll("li[hidden]").forEach((li) => (li.hidden = false)); b.parentElement.remove(); };
  });
}
export function custom({ kicker = "", h1 = "", lede = "", html = "" }, o = {}) {
  open(`${kicker ? `<div class="k">${kicker}</div>` : ""}<h1${h1.length > 42 ? ' class="long"' : ""}>${esc(h1)}</h1>${lede ? `<p class="lede">${esc(lede)}</p>` : ""}${html}`, o);
}

// ---------- shared pieces
const clsName = (c) => t(c === 6 ? "levelUnknown" : "c" + c);
const artNum = (s) => String(s).replace(/^art_/, "").replace(/_/g, "");
function rowsHTML(items, render, cap = LIST) {
  if (!items.length) return "";
  return `<ul class="rows">${items.map((x, k) => `<li${k >= cap ? " hidden" : ""}>${render(x)}</li>`).join("")}${items.length > cap ?
    `<li><button class="moreb" data-more="1">+ ${esc(t("more", num(items.length - cap)))}</button></li>` : ""}</ul>`;
}
function actRow(j, value, sub) {
  const s = sub ?? title(j);
  return `<a class="r" href="${linkTo(j)}"><span class="a">${sw(M.cls[j] >= 0 ? M.cls[j] : 6)}${esc(labelCt(j))}</span>${value != null ? `<span class="v">${esc(value)}</span>` : ""}${s && s !== label(j) ? `<span class="b">${esc(s)}</span>` : ""}</a>`;
}
function section(h, body, n) {
  return body ? `<section><h2><span>${esc(h)}</span>${n != null ? `<span class="n">${esc(num(n))}</span>` : ""}</h2>${body}</section>` : "";
}
function yearsChart(y0, ys) {
  if (!ys || !ys.length) return "";
  const n = ys.length, max = Math.max(...ys), W = 360, H = 76, bw = W / n, km = ys.indexOf(max);
  const bars = ys.map((v, k) => v ? `<rect class="bar" data-y="${y0 + k}" data-v="${v}" x="${(k * bw + (bw > 3 ? 0.5 : 0)).toFixed(2)}" y="${(H - (H * v) / max).toFixed(2)}" width="${Math.max(0.6, bw - (bw > 3 ? 1 : 0)).toFixed(2)}" height="${((H * v) / max).toFixed(2)}"/>` : "").join("");
  return `<div class="chart" data-chart="1"><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="${esc(t("perYear"))}: ${y0}–${y0 + n - 1}">${bars}</svg>` +
    `<span class="top" style="left:${(100 * (km + 0.5) / n).toFixed(1)}%">${esc(num(max))} · ${y0 + km}</span>` +
    `<div class="cap"><span>${y0}</span><span>${y0 + n - 1}</span></div></div>`;
}
function wireCharts(d) {
  d.querySelectorAll("[data-chart]").forEach((c) => {
    let peek = null;
    c.addEventListener("pointermove", (e) => {
      const r = e.target.closest("rect"); if (!r) return;
      if (!peek) { peek = document.createElement("div"); peek.className = "peek"; c.appendChild(peek); }
      c.querySelectorAll(".on").forEach((x) => x.classList.remove("on")); r.classList.add("on");
      peek.textContent = `${r.dataset.y} · ${num(+r.dataset.v)}`;
      const cr = c.getBoundingClientRect(), rr = r.getBoundingClientRect();
      peek.style.left = Math.min(cr.width - 40, Math.max(40, rr.left - cr.left + rr.width / 2)) + "px";
    });
    c.addEventListener("pointerleave", () => { if (peek) peek.remove(); peek = null; c.querySelectorAll(".on").forEach((x) => x.classList.remove("on")); });
  });
}
function decRows(ids, dec) {
  const items = (ids || []).filter((d) => dec[d]);
  return rowsHTML(items, (d) => {
    const x = dec[d];
    return `<a class="r" href="${decUrl(d)}" target="_blank" rel="noopener" title="${esc(t("openDec"))}"><span class="a">${esc(x[0])}</span><span class="v">${x[2] ? esc(t("citedBy", num(x[2]))) : ""}</span><span class="b">${esc(date(x[1]))}</span></a>`;
  }, 6);
}
const later = (id, html) => `<div id="${id}"><p class="spin">${esc(t("loading"))}</p></div>`;
function fill(id, html, my) {
  if (my !== token) return;
  const x = $(id);
  if (!x) return;
  if (!html) { x.remove(); return; }
  x.outerHTML = html;
  wire(el()); wireCharts(el());
}

// ---------- a part of the collection (block, SR area, canton) or the whole
function topActsBelow(i, cap = 12) {
  const out = [];
  for (let j = i + 1; j < M.end[i]; j++) if (isAct(j) && M.D[j] > 0) out.push(j);
  out.sort((a, b) => M.D[b] - M.D[a] || a - b);
  return out.slice(0, cap);
}
function groupHTML(i) {
  const k = M.K[i], comp = M.comp.acts, o = i * 7, acts = M.val.acts[i];
  const kick = k === KIND.c ? `<span>SR ${esc(M.S[i])}</span>` : k === KIND.t ? `<span>${esc(M.S[i])}</span>` : "";
  const h1 = i === 0 ? t("title") : k === KIND.c ? M.L[i] : label(i);
  const parts = [0, 1, 2, 3, 4, 6].filter((c) => comp[o + c] > 0);
  const stack = acts ? `<div class="stack" aria-hidden="true">${parts.map((c) => `<i style="flex:${comp[o + c]};background:var(--c${c})"></i>`).join("")}</div>` +
    `<div class="stackkey">${parts.map((c) => `<span>${sw(c)}${esc(clsName(c))}</span><span class="num">${esc(num(comp[o + c]))}</span>`).join("")}</div>` : "";
  const top = topActsBelow(i);
  return `${kick ? `<div class="k">${kick}</div>` : ""}<h1${h1.length > 42 ? ' class="long"' : ""}>${esc(h1)}</h1>` +
    (i === 0 ? `<p class="lede">${esc(t("description"))}</p>` : k === KIND.g ? `<p class="lede">${esc(t("codeNote"))}</p>` : "") +
    `<div class="stat2">${acts ? `<div class="stat"><b>${esc(num(acts))}</b><span>${esc(t("inForceActs"))}</span></div>` : ""}` +
    `${M.DD[i] ? `<div class="stat"><b>${esc(num(M.DD[i]))}</b><span>${esc(t("referring"))}</span></div>` : ""}</div>` + stack +
    section(t("topActs"), rowsHTML(top, (j) => actRow(j, num(M.D[j])), 12));
}

// ---------- an act
export async function node(i, o = {}) {
  const my = ++token;
  if (!isAct(i)) { open(groupHTML(i), o); return; }
  const k = M.K[i], ct = M.CT[i], sr = srOf(i), u = urlOf(i);
  const pooled = k === KIND.x && M.S[i] === "*";
  const status = k === KIND.a ? `<span class="badge on">${esc(t("inForce"))}</span>` : k === KIND.o ? `<span class="badge">${esc(t("earlier"))}</span>` :
    `<span class="badge">${esc(pooled ? t("pooled") : t("notInCollection"))}</span>`;
  const kick = `${sr && k !== KIND.x ? `<span>${ct ? esc(ct) + " " : "SR "}${esc(sr)}</span>` : ct ? `<span>${esc(cantonName(ct))}</span>` : ""}${M.SR[i] ? `<span>SR ${esc(M.SR[i])}</span>` : ""}${status}`;
  const h1 = labelCt(i), lede = title(i);
  const facts = [];
  const c = M.cls[i];
  // the level; where no issuer is stated, the level comes from the title (or is not known)
  const how = M.BY[i] === "Titel" || M.FB[i] === "Titel" ? ` (${t("fromTitle")})` : M.FB[i] === "unbekannt" ? ` (${t("notStated")})` : "";
  if (k === KIND.a) facts.push([t("level"), `${sw(c)}${esc(clsName(c) + how)}`]);
  const BY = { Bundesversammlung: "byFA", Bundesrat: "byFC", Gericht: "byCourt", "Departement, Amt oder andere Behörde": "byDept" };
  if (BY[M.BY[i]]) facts.push([t("enactedBy"), esc(t(BY[M.BY[i]]))]);
  if (M.AD[i]) facts.push([t("adopted"), esc(date(M.AD[i]))]);
  if (M.A[i]) facts.push([t("articles"), `<span class="num">${esc(num(M.A[i]))}</span>`]);
  if (k === KIND.o) { const today = M.byId.get(M.S[i].split("@")[0]); if (today != null) facts.push([t("today"), `<a href="${href(idOf(today))}">${esc(label(today))}</a>`]); }
  const head = `<div class="k">${kick}</div><h1${h1.length > 42 ? ' class="long"' : ""}>${esc(h1)}</h1>` +
    (lede && lede !== h1 ? `<p class="lede">${esc(lede)}</p>` : "") +
    (pooled ? `<p class="lede">${esc(t("pooledNote", num(M.MM[i])))}</p>` : k === KIND.x ? `<p class="lede">${esc(t("codeNote"))}</p>` : "") +
    (u ? `<a class="src" href="${esc(u)}" target="_blank" rel="noopener">${esc(ct && !u.includes("fedlex") ? t("cantonText") : t("fedlex"))} ${ICON.ext}</a>` : "") +
    (!linker && extra(i) ? `<div class="btnrow">${extra(i)}</div>` : "") +
    (facts.length ? `<dl class="facts">${facts.map(([a, b]) => `<dt>${esc(a)}</dt><dd>${b}</dd>`).join("")}</dl>` : "") +
    (M.D[i] ? `<div class="stat"><b>${esc(num(M.D[i]))}</b><span>${esc(t("referring"))}</span></div>` : "");
  const hasArts = M.PK[i] >= 0;
  open(head + later("d-years") + (hasArts ? later("d-arts") : "") + later("d-basis") + later("d-down") + later("d-co") + later("d-legis") +
    (hasArts ? later("d-dec") : "") + later("d-ing"), o);
  // decisions per year
  loadYears().then((y) => fill("d-years", y[i] ? section(t("perYear"), yearsChart(y[i][0], y[i][1])) : "", my)).catch(() => fill("d-years", "", my));
  // articles and decisions
  if (hasArts) {
    getJSON(`data/art/${M.PK[i]}.json`).then((sh) => {
      const a = sh.acts[String(i)];
      if (!a) { fill("d-arts", "", my); fill("d-dec", "", my); return; }
      const arts = (a.arts || []).filter((x) => x[2] > 0).sort((p, q) => q[2] - p[2]).slice(0, 8);
      const max = arts.length ? arts[0][2] : 1;
      const lvh = (x) => x[9] ? pick(x[9]) : x[3] >= 0 && a.lv[x[3]] ? pick(a.lv[x[3]][3]) : "";
      const bars = arts.length ? `<ul class="bars">${arts.map((x) => `<li><button data-go="${esc(idOf(i) + ":" + x[0])}"><span class="a">${esc(t("art"))} ${esc(x[1])}</span>` +
        `<span class="t"><i style="width:${(100 * x[2] / max).toFixed(1)}%"></i><span>${esc(lvh(x) || "")}</span></span><span class="v">${esc(num(x[2]))}</span></button></li>`).join("")}</ul>` : "";
      const btn = a.arts && a.arts.length ? `<div class="btnrow"><a class="btn" href="${href(idOf(i) + ":")}">${ICON.zoom} ${esc(t("allArts"))}</a></div>` : "";
      fill("d-arts", bars || btn ? section(t("topArts"), bars + btn) : "", my);
      fill("d-dec", section(t("topDec"), decRows(a.top, sh.dec)), my);
      el().querySelectorAll("[data-go]").forEach((b) => (b.onclick = () => o.go && o.go(b.dataset.go)));
    }).catch(() => { fill("d-arts", "", my); fill("d-dec", "", my); });
  }
  // what it rests on, what rests on it, partners
  const L = await loadLinks().catch(() => null);
  if (my !== token) return;
  if (L) {
    const down = (L.down.get(i) || []).slice().sort((p, q) => M.D[q.j] - M.D[p.j] || p.j - q.j);
    fill("d-down", section(t("restingOn"), rowsHTML(down, (x) => actRow(x.j, x.arts && x.arts.length ? fmtArts(x.arts, i) : null)), down.length), my);
    const co = (L.co.get(i) || []).slice().sort((p, q) => q.n * Math.log(q.lift) - p.n * Math.log(p.lift));
    fill("d-co", section(t("cocited"), rowsHTML(co, (x) => actRow(x.j, t("together", num(x.n))), 8), co.length), my);
    const out = (L.out.get(i) || []).slice().sort((p, q) => q.n - p.n), inn = (L.inn.get(i) || []).slice().sort((p, q) => q.n - p.n);
    fill("d-legis", (out.length ? section(t("refersTo"), rowsHTML(out, (x) => actRow(x.j, t("provisions", num(x.n))), 6), out.length) : "") +
      (inn.length ? section(t("referredBy"), rowsHTML(inn, (x) => actRow(x.j, t("provisions", num(x.n))), 6), inn.length) : ""), my);
  } else { fill("d-down", "", my); fill("d-co", "", my); fill("d-legis", "", my); }
  // Ingress and the bases it states, with the clause verbatim
  if (k !== KIND.a) { fill("d-basis", "", my); fill("d-ing", "", my); return; }
  loadLaw(i).then((law) => {
    const rec = law[String(i)];
    if (!rec) {
      const up = L ? (L.up.get(i) || []) : [];
      fill("d-basis", up.length ? section(t("restsOn"), rowsHTML(up, (x) => actRow(x.j, fmtArts(x.arts, x.j)))) : "", my);
      fill("d-ing", ct ? section(t("ingress"), `<p class="note">${esc(t("noIngress"))}</p>`) : "", my);
      return;
    }
    const [issuer, ing, bases] = rec;
    const bs = bases.slice().sort((p, q) => q[4] - p[4]);
    const basisRow = (b) => {
      const [j, arts, clause, via, prim] = b;
      const note = via === "old" ? t("viaOld") : via === "note" ? t("viaNote") : via === "aBV→BV" ? t("viaABV") : "";
      if (j >= 0) {
        return `<a class="r wrap" href="${linkTo(j)}"><span class="a">${sw(M.cls[j] >= 0 ? M.cls[j] : 6)}${esc(labelCt(j))}${prim ? "" : ""}</span>` +
          `<span class="v">${esc(fmtArts(arts, j))}</span><span class="b">${esc(clause || title(j))}${note ? ` · ${esc(note)}` : ""}${prim && bs.length > 1 ? ` · ${esc(t("primary"))}` : ""}</span></a>`;
      }
      const why = { absent: t("viaAbsent"), earlier: t("viaEarlier"), fedany: t("basisFederal"), other: t("basisOther"), unresolved: t("basisUnknown") }[via] || t("basisUnknown");
      return `<div class="r wrap"><span class="a" style="color:var(--ink-2)">${esc(why)}</span><span class="b">${esc(clause)}</span></div>`;
    };
    fill("d-basis", section(t("restsOn"), bs.length ? rowsHTML(bs, basisRow, 8) : `<p class="note">${esc(ing ? t("noBasis") : t("noIngress"))}</p>`), my);
    fill("d-ing", ing ? section(t("ingress"), `<details class="more"><summary>${esc(t("showText"))}</summary><p class="ing">${esc(ing)}</p></details>`) :
      section(t("ingress"), `<p class="note">${esc(t("noIngress"))}</p>`), my);
  }).catch(() => { fill("d-basis", "", my); fill("d-ing", "", my); });
}
export function fmtArts(arts, j) {                           // "Art. 41, 42" — or "§ 3" where the canton writes §
  if (!arts || !arts.length) return "";
  const nums = arts.map(artNum).filter(Boolean);
  if (!nums.length) return "";
  const sym = M.CT[j] && M.meta.ksym && M.meta.ksym[M.CT[j]] === "§" ? "§" : t("art");
  return `${sym} ${nums.slice(0, 4).join(", ")}${nums.length > 4 ? " …" : ""}`;
}

// ---------- an article
export async function article(oa, aid, o = {}) {
  const my = ++token;
  const i = oa.i, a = oa.arts[+aid.slice(1)];
  const [eid, n, nd, , rep, y0, ys, top, e] = a;
  const path = [];
  for (let k = a[3]; k >= 0; k = oa.lv[k][1]) path.unshift(`${pick(oa.lv[k][2]) || ""} ${pick(oa.lv[k][3]) || ""}`.replace(/:\s*$/, "").trim());
  const u = urlOf(i);
  const head = `<div class="k"><a href="${href(idOf(i))}" style="text-decoration:none"><span>${esc(srOf(i) ? "SR " + srOf(i) : "")}</span> <span>${esc(label(i))}</span></a>${rep ? `<span class="badge">${esc(t("repealed"))}</span>` : ""}</div>` +
    `<h1>${esc(t("art"))} ${esc(n)} ${esc(label(i))}</h1>` +
    (headingOf(a) ? `<p class="lede">${esc(headingOf(a))}</p>` : "") +
    (path.length ? `<p class="path">${path.map((p) => `<span>${esc(p)}</span>`).join("")}</p>` : "") +
    (u ? `<a class="src" href="${esc(u)}#${esc(eid)}" target="_blank" rel="noopener">${esc(t("fedlex"))} ${ICON.ext}</a>` : "") +
    `<div class="stat"><b>${esc(num(nd))}</b><span>${esc(t("referring"))}</span></div>`;
  open(head + section(t("perYear"), yearsChart(y0, ys)) + later("a-dec") + later("a-co"), o);
  wireCharts(el());
  const sh = await getJSON(`data/art/${M.PK[i]}.json`).catch(() => null);
  if (my !== token) return;
  fill("a-dec", sh ? section(t("topDec"), decRows(top, sh.dec)) : "", my);
  const co = (e || []).filter((x) => x[0] >= 0).sort((p, q) => q[2] * Math.log(q[3]) - p[2] * Math.log(p[3]));
  fill("a-co", section(t("cocitedArts"), rowsHTML(co, (x) => {
    const [j, ej, nn] = x;
    return `<a class="r" href="${href(idOf(j) + ":" + ej)}"><span class="a">${sw(M.cls[j] >= 0 ? M.cls[j] : 6)}${esc(t("art"))} ${esc(artNum(ej))} ${esc(labelCt(j))}</span><span class="v">${esc(t("together", num(nn)))}</span></a>`;
  }, 8), co.length), my);
}
