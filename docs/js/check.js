// The health check ("Befund") and what is new ("Neu") (decision 35): lists the pipeline computes from the stated
// bases (check.json) and from Fedlex's dates and the collections' adoption dates (news.json). Every row links to the act.
import { t, cantonName } from "./i18n.js";
import { M, idOf, label, labelCt, title, getJSON } from "./data.js";
import { $, esc, num, date, href, sw } from "./util.js";
import { cantonOrder, jurisdiction, normArt } from "./impact.js";

let ctx = null, chk = null, news = null, scope = "all";
const CAP = 12;

export async function init(c) {
  ctx = c;
  [chk, news] = await Promise.all([getJSON("data/check.json"), getJSON("data/news.json")]);
}

const actA = (a) => a >= 0 ? `<a href="${href(idOf(a))}">${sw(M.cls[a] >= 0 ? M.cls[a] : 6)}${esc(labelCt(a))}</a>` : "";
const within = (a) => scope === "all" || jurisdiction(a) === scope || (scope === "fed" && jurisdiction(a) === "int");
const arts = (xs, j) => (xs && xs.length ? `${M.CT[j] && M.meta.ksym && M.meta.ksym[M.CT[j]] === "§" ? "§" : t("art")} ${xs.map(normArt).slice(0, 5).join(", ")}${xs.length > 5 ? " …" : ""}` : "");
const cut = (s, n = 180) => (s && s.length > n ? s.slice(0, n - 1) + "…" : s || "");

function table(rows, cols) {
  if (!rows.length) return `<p class="note">—</p>`;
  return `<div class="tw"><table class="ktab"><thead><tr>${cols.map((c) => `<th${c.r ? ' class="r"' : ""}>${esc(c.h)}</th>`).join("")}</tr></thead><tbody>` +
    rows.map((r, k) => `<tr${k >= CAP ? " hidden" : ""}>${cols.map((c) => `<td${c.r ? ' class="r"' : ""}>${c.f(r)}</td>`).join("")}</tr>`).join("") +
    `</tbody></table></div>${rows.length > CAP ? `<p><button class="moreb" data-more="1">${esc(t("more", num(rows.length - CAP)))}</button></p>` : ""}`;
}
function part(key, desc, rows, cols, n) {
  return `<section class="kpart" id="k-${key}"><h2><span>${esc(t(key))}</span><span class="n num">${esc(num(n ?? rows.length))}</span></h2>` +
    `<p class="note">${esc(desc)}</p>${table(rows, cols)}</section>`;
}
const baseCols = () => [
  { h: t("act"), f: (r) => actA(r[0]) },
  { h: t("kTarget"), f: (r) => (r[1] >= 0 ? actA(r[1]) + (r[2] && r[2].length ? ` <span class="arts">${esc(arts(r[2], r[1]))}</span>` : "") : "") },
  { h: t("kClause"), f: (r) => `<span class="cl">${esc(cut(r[3]))}</span>` },
];

function checkHTML() {
  const sel = `<label class="kscope">${esc(t("kScope"))} <select id="kscope">${[["all", t("kAll")], ["fed", t("impFed")], ...cantonOrder().map((c) => [c, cantonName(c)])]
    .map(([v, l]) => `<option value="${v}"${v === scope ? " selected" : ""}>${esc(l)}</option>`).join("")}</select></label>`;
  const f = (xs) => xs.filter((r) => within(r[0]));
  const nk = chk.nobasis_kt;
  const ktRows = Object.entries(nk).filter(([ct]) => scope === "all" || scope === ct)
    .map(([ct, [a, b]]) => [ct, a, b]).sort((p, q) => q[1] / q[2] - p[1] / p[2]);
  const unchanged = chk.unchanged.filter((r) => within(r[0]));
  return `<h1>${esc(t("check"))}</h1><p class="lead">${esc(t("kLede"))}</p>${sel}` +
    `<nav class="ktoc">${["kDangling", "kRepealed", "kBV1874", "kOld", "kNote", "kNoBasis", "kNoBasisKt", "kUnchanged", "kLower", "kFedlex"]
      .map((k) => `<a href="#" data-jump="k-${k}">${esc(t(k))}</a>`).join("")}</nav>` +
    part("kDangling", t("kDanglingD"), f(chk.dangling), [baseCols()[0],
      { h: t("kTarget"), f: (r) => actA(r[1]) + ["rep", "absent"].map((k) => {
        const xs = r[2].filter((x) => x[1] === k).map((x) => x[0]);
        return xs.length ? ` <span class="arts miss">${esc(t(k === "rep" ? "kRep" : "kMissing"))}: ${esc(arts(xs, r[1]))}</span>` : "";
      }).join("") }, baseCols()[2]]) +
    part("kRepealed", t("kRepealedD"), f(chk.repealed), baseCols()) +
    part("kBV1874", t("kBV1874D"), f(chk.bv1874), baseCols()) +
    part("kOld", t("kOldD"), f(chk.olddate), baseCols()) +
    part("kNote", t("kNoteD"), f(chk.note), baseCols()) +
    (scope === "all" || scope === "fed" ? part("kNoBasis", t("kNoBasisD"), chk.nobasis.map((a) => [a]),
      [{ h: t("act"), f: (r) => actA(r[0]) }, { h: "", f: (r) => `<span class="cl">${esc(title(r[0]) !== label(r[0]) ? title(r[0]) : "")}</span>` },
        { h: t("decisions"), r: 1, f: (r) => (M.D[r[0]] ? esc(num(M.D[r[0]])) : "") }]) : "") +
    (scope !== "fed" ? part("kNoBasisKt", t("kNoBasisKtD"), ktRows, [{ h: t("kScope"), f: (r) => `<span class="ct">${esc(r[0])}</span> ${esc(cantonName(r[0]))}` },
      { h: t("kShare"), f: (r) => `<span class="t"><i style="width:${(100 * r[1] / r[2]).toFixed(1)}%"></i></span>` },
      { h: "", r: 1, f: (r) => `${esc(num(r[1]))} / ${esc(num(r[2]))}` }], ktRows.reduce((s, r) => s + r[1], 0)) : "") +
    (scope === "all" || scope === "fed" ? part("kUnchanged", t("kUnchangedD"), unchanged, [{ h: t("act"), f: (r) => actA(r[0]) },
      { h: "", f: (r) => `<span class="cl">${esc(cut(title(r[0]) !== label(r[0]) ? title(r[0]) : "", 120))}</span>` },
      { h: t("kVersion"), r: 1, f: (r) => esc(date(r[1])) }, { h: t("decisions"), r: 1, f: (r) => (M.D[r[0]] ? esc(num(M.D[r[0]])) : "0") }]) : "") +
    `<section class="kpart" id="k-kLower"><h2><span>${esc(t("kLower"))}</span><span class="n num">${esc(num(chk.lower))}</span></h2><p class="note">${esc(t("kLowerD", num(chk.lower)))}</p>` +
    `<p><a class="btn" href="${href("matrix")}">${esc(t("kSee"))}</a></p></section>` +
    `<section class="kpart" id="k-kFedlex"><h2><span>${esc(t("kFedlex"))}</span></h2><p class="note">${esc(t("kFedlexD", num(chk.fedlex.dates), num(chk.fedlex.ended)))}</p></section>`;
}

function newsHTML() {
  const rows = (xs) => xs;
  return `<h1>${esc(t("new"))}</h1><p class="lead">${esc(t("nLede", date(news.since), date(news.run)))}</p>` +
    `<p><a class="btn" href="feed.${M.lang || "de"}.xml">${esc(t("nFeed"))}</a></p>` +
    part("nIn", "", rows(news.in_force), [{ h: t("act"), f: (r) => actA(r[0]) }, { h: "", f: (r) => `<span class="cl">${esc(cut(title(r[0]) !== label(r[0]) ? title(r[0]) : "", 140))}</span>` },
      { h: t("inForce"), r: 1, f: (r) => esc(date(r[1])) }]) +
    part("nKt", "", rows(news.cantonal), [{ h: t("act"), f: (r) => actA(r[0]) }, { h: "", f: (r) => `<span class="cl">${esc(cut(title(r[0]) !== label(r[0]) ? title(r[0]) : "", 140))}</span>` },
      { h: t("adopted"), r: 1, f: (r) => esc(date(r[1])) }]) +
    part("nEnded", "", rows(news.ended), [{ h: t("act"), f: (r) => actA(r[0]) }, { h: "", f: (r) => `<span class="cl">${esc(cut(title(r[0]) !== label(r[0]) ? title(r[0]) : "", 140))}</span>` },
      { h: t("repealedOn"), r: 1, f: (r) => esc(date(r[1])) }]);
}

let page = "check";
function render() {
  const d = $(page === "check" ? "kdoc" : "ndoc");
  d.innerHTML = page === "check" ? checkHTML() : newsHTML();
  d.querySelectorAll("[data-more]").forEach((b) => (b.onclick = () => {
    b.closest("section").querySelectorAll("tr[hidden]").forEach((r) => (r.hidden = false)); b.parentElement.remove();
  }));
  d.querySelectorAll("[data-jump]").forEach((a) => (a.onclick = (e) => { e.preventDefault(); const x = $(a.dataset.jump); if (x) x.scrollIntoView({ behavior: "smooth" }); }));
  const s = $("kscope"); if (s) s.onchange = () => { scope = s.value; render(); };
}
export async function show(rest) {
  ctx.panel.hide();
  page = rest.split("/")[0] === "new" ? "new" : "check";
  render();
  $(page === "check" ? "v-check" : "v-new").scrollTop = 0;
}
export function refresh() { if (!$("v-check").hidden || !$("v-new").hidden) render(); }
