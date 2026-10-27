// Search: acts in any language ("OR", "CO", "SR 220", "Planungs- und Baugesetz ZH"), articles
// ("Art. 41 OR", "8 EMRK"), and the headings of divisions ("Mietrecht").
import { t, cantonName, lang } from "./i18n.js";
import { M, KIND, idOf, label, labelCt, title, srOf, isAct, searchActs, exactActs, parseArticle, searchTopics, normNum, getJSON, fold, loadHistNames } from "./data.js";
import { $, esc, sw } from "./util.js";

let ctx = {}, items = [], cur = -1, seq = 0;
const input = () => $("q"), box = () => $("results");

function metaOf(i) {
  const k = M.K[i];
  if (k === KIND.c) return `SR ${M.S[i]}`;
  if (k === KIND.t) return M.S[i];
  if (k === KIND.b) return "";
  if (M.CT[i]) return M.CT[i];
  const per = k === KIND.o && M.AD[i] && (M.RP[i] || M.LE[i]) ? `${M.AD[i].slice(0, 4)}–${(M.RP[i] || M.LE[i]).slice(0, 4)}` : "";
  return [srOf(i) ? `SR ${srOf(i)}` : "", per].filter(Boolean).join(" · ");   // an earlier act: when it applied
}
let hist = null;                                     // the names of the repealed acts, fetched with the first search
function withHistory() {
  if (M.histLang === lang() || (hist && hist.lg === lang())) return;
  hist = { lg: lang(), p: loadHistNames(lang()).then(() => { if (!box().hidden && input().value.trim()) run(input().value); }) };
}
function render(groups) {
  items = [];
  const out = [];
  for (const [name, list] of groups) {
    if (!list.length) continue;
    out.push(`<div class="grp" role="presentation">${esc(name)}</div>`);
    for (const it of list) {
      const k = items.length;
      items.push(it);
      out.push(`<button role="option" id="opt${k}" data-k="${k}" aria-selected="false"${it.off ? ' class="off"' : ""}>${it.sw != null ? sw(it.sw) : "<span></span>"}` +
        `<span style="min-width:0;display:flex;gap:8px;align-items:baseline;overflow:hidden"><span class="lab">${esc(it.lab)}</span><span class="sub">${esc(it.sub || "")}</span></span>` +
        `<span class="meta">${esc(it.meta || "")}</span></button>`);
    }
  }
  const b = box();
  b.innerHTML = out.length ? out.join("") : `<div class="empty">${esc(t("none"))}</div>`;
  b.hidden = false;
  input().setAttribute("aria-expanded", "true");
  cur = items.length ? 0 : -1;
  mark();
}
function mark() {
  box().querySelectorAll("[role=option]").forEach((b) => b.setAttribute("aria-selected", +b.dataset.k === cur));
  if (cur >= 0) { const o = $("opt" + cur); if (o) { o.scrollIntoView({ block: "nearest" }); input().setAttribute("aria-activedescendant", o.id); } }
}
function close() {
  box().hidden = true; input().setAttribute("aria-expanded", "false"); input().removeAttribute("aria-activedescendant");
}
function choose(k) {
  const it = items[k];
  if (!it) return;
  close();
  input().blur();
  $("search").classList.remove("open");
  ctx.go(it.target);
}
const nodeItem = (i) => ({ lab: labelCt(i), sub: M.K[i] === KIND.c ? M.L[i] : isAct(i) ? title(i) : M.K[i] === KIND.t ? cantonName(M.S[i]) : "", meta: metaOf(i), sw: isAct(i) ? (M.cls[i] >= 0 ? M.cls[i] : 6) : null, target: idOf(i) });

async function run(q) {
  const my = ++seq;
  withHistory();
  const inNet = ctx.net && ctx.net();                // the network is open: acts in it first, the others marked
  let acts = searchActs(q, inNet ? 24 : 10).filter((i) => !(M.K[i] === KIND.c && M.val.acts[i] === 0 && M.val.dec[i] === 0));
  if (inNet) acts = acts.filter((i) => M.K[i] !== KIND.c).sort((a, b) => !inNet(a) - !inNet(b)).slice(0, 10);
  const item = (i) => {
    const it = nodeItem(i);
    if (inNet && isAct(i) && !inNet(i)) { it.meta = [it.meta, t("notInNet")].filter(Boolean).join(" · "); it.off = true; }
    return it;
  };
  const groups = [[t("acts"), acts.map(item)]];
  render(groups);
  // an article: "Art. 41 OR"
  const pa = parseArticle(q);
  if (pa) {
    let cand = exactActs(pa.act).filter((i) => M.PK[i] >= 0);
    if (!cand.length) cand = searchActs(pa.act, 4).filter((i) => isAct(i) && M.PK[i] >= 0);
    const arts = [];
    for (const i of cand.slice(0, 3)) {
      const sh = await getJSON(`data/art/${M.PK[i]}.json`).catch(() => null);
      const a = sh && sh.acts[String(i)];
      if (!a || !a.arts) continue;
      const want = normNum(pa.num);
      for (const x of a.arts) if (normNum(x[1]) === want) arts.push({ lab: `${t("art")} ${x[1]} ${labelCt(i)}`, sub: x[9] ? x[9][M.lang] || x[9].de || "" : "", meta: srOf(i) ? `SR ${srOf(i)}` : "", sw: M.cls[i], target: `${idOf(i)}:${x[0]}` });
    }
    if (my !== seq) return;
    if (arts.length) { groups.splice(0, groups.length, [t("articles"), arts.slice(0, 4)], [t("acts"), acts.filter((i) => cand.includes(i)).map(item)]); render(groups); }
  }
  // headings of divisions
  if (fold(q).replace(/[^a-z]/g, "").length >= 4 && !pa) {
    const tp = await searchTopics(q, 6).catch(() => []);
    if (my !== seq) return;
    if (tp.length) {
      groups.push([t("topics"), tp.map((r) => ({ lab: r.h, sub: "", meta: labelCt(r.i), sw: M.cls[r.i], target: `${idOf(r.i)}:${r.eid}` }))]);
      render(groups);
    }
  }
}
export function refreshSearch() { if (!box().hidden && input().value.trim()) run(input().value); }
export function initSearch(c) {
  ctx = c;
  let timer = 0;
  input().addEventListener("input", () => {
    clearTimeout(timer);
    const q = input().value;
    if (!q.trim()) { close(); return; }
    timer = setTimeout(() => run(q), 70);
  });
  input().addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); if (items.length) { cur = (cur + 1) % items.length; mark(); } }
    else if (e.key === "ArrowUp") { e.preventDefault(); if (items.length) { cur = (cur - 1 + items.length) % items.length; mark(); } }
    else if (e.key === "Enter") { e.preventDefault(); if (cur >= 0) choose(cur); }
    else if (e.key === "Escape") { close(); input().blur(); $("search").classList.remove("open"); }
  });
  input().addEventListener("focus", () => { if (input().value.trim()) run(input().value); });
  box().addEventListener("pointerdown", (e) => { const b = e.target.closest("[data-k]"); if (b) { e.preventDefault(); choose(+b.dataset.k); } });
  document.addEventListener("pointerdown", (e) => { if (!e.target.closest("#search")) close(); });
  $("qbtn").addEventListener("click", () => { $("search").classList.add("open"); input().focus(); });
  $("closeq").addEventListener("click", () => { close(); $("search").classList.remove("open"); });
}
