// The page: header, router (#<lang>/<target>), the map with its bar, legend and tooltip, and the
// panel. The hierarchy, the matrix and the method load when first opened.
import { t, setLang, lang, LANGS } from "./i18n.js";
import { M, build, loadNames, getJSON, idOf, isAct, KIND, pathTo, isAncestor } from "./data.js";
import * as TM from "./treemap.js";
import * as DOS from "./dossier.js";
import { initSearch, refreshSearch } from "./search.js";
import { $, esc, num, sw, href, ICON, store } from "./util.js";

const wide = matchMedia("(min-width: 1181px)"), phone = matchMedia("(max-width: 720px)");
const S = { view: "map", target: "", sel: null, booted: false };
let views = {};                                      // lazily loaded modules: hier, matrix, method

// ---------- language
function pickLang() {
  const h = location.hash.slice(1).split("/")[0];
  if (LANGS.includes(h)) return h;
  const s = store("atlas-lang");
  if (LANGS.includes(s)) return s;
  for (const l of navigator.languages || [navigator.language || ""]) { const c = (l || "").slice(0, 2).toLowerCase(); if (LANGS.includes(c)) return c; }
  return "de";
}
function staticText() {
  document.documentElement.lang = lang();
  document.title = t("title");
  document.querySelector('meta[name="description"]').setAttribute("content", t("description"));
  $("brandname").textContent = t("title");
  $("brand").href = href("");
  $("skip").textContent = t("skip");
  $("views").setAttribute("aria-label", t("views"));
  for (const a of $("views").querySelectorAll("a")) {
    const v = a.dataset.view;
    a.textContent = t(v);
    a.href = href(v === "map" ? mapTarget() : { hier: "hierarchy", matrix: "matrix", method: "method" }[v]);
  }
  $("q").placeholder = t("search"); $("q").setAttribute("aria-label", t("search"));
  $("qbtn").setAttribute("aria-label", t("searchOpen")); $("closeq").setAttribute("aria-label", t("close"));
  $("langs").setAttribute("aria-label", t("language"));
  for (const b of $("langs").querySelectorAll("button")) b.setAttribute("aria-pressed", b.dataset.lang === lang());
  $("langsel").value = lang(); $("langsel").setAttribute("aria-label", t("language"));
  $("tm").setAttribute("aria-label", t("mapLabel"));
  $("loadtxt").textContent = t("loading");
  renderMode();
}
async function switchLang(lg) {
  if (lg === lang()) return;
  setLang(lg); store("atlas-lang", lg);
  await loadNames(lg);
  staticText();
  TM.refreshLabels();
  refreshSearch();
  for (const v of Object.values(views)) v.refresh && v.refresh();
}

// ---------- router
function parseHash() {
  let h = decodeURIComponent(location.hash.slice(1));
  const old = /^SR_(.+?)(?:--(.+))?$/.exec(h);              // links of the previous map: #SR_220--art_41
  if (old) return { lang: lang(), rest: old[1] + (old[2] ? ":" + old[2] : "") };
  const parts = h.split("/");
  if (LANGS.includes(parts[0])) return { lang: parts[0], rest: parts.slice(1).join("/") };
  return { lang: lang(), rest: h };
}
function go(target, replace = false) {
  const h = href(target);
  if (location.hash === h) return;
  if (replace) history.replaceState(null, "", h); else history.pushState(null, "", h);
  route();
}
async function route() {
  const { lang: lg, rest } = parseHash();
  if (lg !== lang()) await switchLang(lg);
  const view = rest === "hierarchy" || rest.startsWith("hierarchy/") ? "hier" : rest === "matrix" || rest.startsWith("matrix/") ? "matrix" : rest === "method" ? "method" : "map";
  showView(view);
  if (view === "map") { S.target = rest; await showMap(rest); }
  else await showOther(view, rest);
  for (const a of $("views").querySelectorAll("a")) {
    if (a.dataset.view === view) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    if (a.dataset.view === "map") a.href = href(mapTarget());
  }
}
const mapTarget = () => S.target || "";
function showView(v) {
  S.view = v;
  for (const id of ["map", "hier", "matrix", "method"]) $("v-" + id).hidden = id !== v;
  if (v !== "map") $("tip").hidden = true;
}
async function showOther(view, rest) {
  if (!views[view]) {
    const mod = await import(view === "hier" ? "./hierarchy.js" : view === "matrix" ? "./matrix.js" : "./method.js");
    views[view] = mod;
    await mod.init({ go, panel: DOS });
  }
  await views[view].show(rest);
}

// ---------- the map
async function ensureAct(i) {
  const oa = TM.openActState();
  if (oa && oa.i === i) return oa;
  const shard = await getJSON(`data/art/${M.PK[i]}.json`);
  const data = shard.acts[String(i)];
  if (!data || !data.arts) return null;
  return TM.openAct(i, data);
}
function contextOf(aid) {                             // a division around the article with enough articles to read it in
  const oa = TM.openActState();
  let p = TM.parentOf(aid);
  while (typeof p === "string" && (oa.va.get(p) || 0) < 30) p = TM.parentOf(p);
  return p;
}
async function showMap(target) {
  const ci = target.indexOf(":");
  const nid = ci >= 0 ? target.slice(0, ci) : target, eid = ci >= 0 ? target.slice(ci + 1) : null;
  let i = nid === "" ? 0 : M.byId.get(nid);
  if (i == null) i = 0;
  let f, s;
  if (eid !== null && isAct(i) && M.PK[i] >= 0 && (await ensureAct(i))) {
    const oa = TM.openActState(), sid = eid ? oa.byEid.get(eid) : null;
    if (!sid) { f = i; s = i; } else if (sid[0] === "A") { f = contextOf(sid); s = sid; } else { f = sid; s = null; }
  } else if (isAct(i)) {
    const cur = TM.getFocus(), r = TM.itemRect(i);
    f = typeof cur === "number" && cur !== i && !isAct(cur) && isAncestor(cur, i) && r && r.lab ? cur : M.P[i];
    s = i;
  } else { f = i; s = null; }
  TM.setFocus(f);
  S.sel = s;
  TM.setSelection(s);
  renderCrumbs(); renderMode(); renderLegend();
  panelFor();
}
function panelFor() {
  const f = TM.getFocus(), oa = TM.openActState();
  if (S.sel != null) {
    if (typeof S.sel === "string") DOS.article(oa, S.sel, { go, close: clearSel });
    else DOS.node(S.sel, { go, close: clearSel, closable: true });
    return;
  }
  const fn = typeof f === "string" ? oa.i : f;
  if (wide.matches || typeof f === "string" || isAct(fn)) DOS.node(fn, { go, close: clearSel, closable: !wide.matches });
  else DOS.hide();
}
function clearSel() {
  const f = TM.getFocus(), oa = TM.openActState();
  if (typeof f === "string") { go(`${idOf(oa.i)}:${oa.lv[+f.slice(1)][0]}`, true); return; }
  if (S.sel != null && !wide.matches) { S.sel = null; TM.setSelection(null); DOS.hide(); go(idOf(f), true); return; }
  go(idOf(f), true);
}
function targetOf(id) {
  if (typeof id !== "string") return idOf(id);
  const oa = TM.openActState(), k = +id.slice(1);
  return `${idOf(oa.i)}:${id[0] === "A" ? oa.arts[k][0] : oa.lv[k][0]}`;
}
function up() {
  const f = TM.getFocus();
  if (f === 0) return;
  const p = TM.parentOf(f);
  if (typeof p === "string") go(targetOf(p));
  else if (typeof f === "string" && isAct(p)) go(idOf(p) + ":");
  else go(idOf(p));
}
function renderCrumbs() {
  const f = TM.getFocus(), oa = TM.openActState(), out = [];
  const chain = [];
  if (typeof f === "string") {
    for (let p = f; typeof p === "string"; p = TM.parentOf(p)) chain.unshift(p);
    chain.unshift(...pathTo(oa.i));
  } else chain.push(...pathTo(f));
  if (f !== 0) out.push(`<button class="upbtn" id="upbtn" title="${esc(t("up"))}" aria-label="${esc(t("up"))}">${ICON.up}</button>`);
  const from = phone.matches ? Math.max(0, chain.length - 2) : 0;
  chain.forEach((id, k) => {
    if (k < from) return;
    const last = k === chain.length - 1, lab = id === 0 ? t("root") : last ? TM.labelOf(id) : TM.crumbLabel(id);
    const tgt = typeof id === "string" ? targetOf(id) : isAct(id) && (typeof f === "string" || f === id) ? idOf(id) + ":" : idOf(id);
    if (k > from) out.push(`<span class="sep" aria-hidden="true">/</span>`);
    out.push(last ? `<span aria-current="location" title="${esc(lab)}">${esc(lab)}</span>` : `<a href="${href(tgt)}" title="${esc(lab)}">${esc(lab)}</a>`);
  });
  const mode = TM.getMode();
  let tot = "";
  if (typeof f === "number" && !isAct(f)) tot = mode === "acts" ? t("nActsInForce", num(M.val.acts[f])) : M.DD[f] ? t("nDec", num(M.DD[f])) : "";
  else if (oa) tot = mode === "acts" ? t("nArts", num(oa.va.get(typeof f === "string" ? f : null) ?? oa.arts.filter((a) => !a[4]).length)) : "";
  if (tot) out.push(`<span class="tot">${esc(tot)}</span>`);
  $("crumbs").setAttribute("aria-label", t("root"));
  $("crumbs").innerHTML = out.join("");
  const ub = $("upbtn"); if (ub) ub.onclick = up;
}
function renderMode() {
  const inside = TM.openActState() && (typeof TM.getFocus() === "string" || TM.getFocus() === TM.openActState().i);
  const m = TM.getMode();
  $("mode").setAttribute("aria-label", t("area"));
  $("mode").innerHTML = `<span class="seglabel">${esc(t("area"))}</span>` +
    [["acts", inside ? t("articles") : t("acts")], ["dec", t("decisions")]].map(([k, l]) => `<button data-mode="${k}" aria-pressed="${m === k}">${esc(l)}</button>`).join("");
}
function renderLegend() {
  const oa = TM.openActState(), f = TM.getFocus();
  const inside = oa && (typeof f === "string" || f === oa.i);
  if (inside) {
    $("legend").innerHTML = `<span class="ramp"><span>${esc(t("perArticle"))}</span><span class="num">0</span><i style="background:linear-gradient(90deg,${[0, .25, .5, .75, 1].map((u) => TM.heatColour(u)).join(",")})"></i><span class="num">${esc(num(oa.max))}</span></span>`;
    return;
  }
  const vis = TM.visibleClasses();
  const cls = [0, 1, 2, 3, 4, 5, 6].filter((c) => c <= 4 ? true : vis.has(c));
  $("legend").innerHTML = cls.map((c) => `<button class="it" data-cls="${c}">${sw(c)}<span>${esc(t(c === 6 ? "levelUnknown" : "c" + c))}</span></button>`).join("");
}

// tooltip
function tipHtml(id) {
  const lab = TM.labelOf(id), sub = TM.subOf(id), mode = TM.getMode();
  let meta = "";
  if (typeof id === "string") {
    const oa = TM.openActState(), n = oa.n.get(id) || 0;
    meta = id[0] === "A" ? `${esc(t("nDec", num(n)))}${oa.arts[+id.slice(1)][4] ? " · " + esc(t("repealed")) : ""}` : esc(t("nArts", num(oa.va.get(id) || 0)));
  } else if (isAct(id)) {
    const c = M.cls[id];
    meta = `<i style="background:var(--c${c})"></i>${esc(t(c === 6 ? "levelUnknown" : "c" + c))} · ${esc(t("nDec", num(M.D[id])))}`;
  } else {
    meta = esc(t("nActsInForce", num(M.val.acts[id])));
    if (M.DD[id]) meta += " · " + esc(t("nDec", num(M.DD[id])));
  }
  return `<b>${esc(lab)}</b>${sub && sub !== lab ? `<span class="t2">${esc(sub.length > 160 ? sub.slice(0, 158) + "…" : sub)}</span>` : ""}<span class="t3">${meta}</span>`;
}
function onHover(id, e, it) {
  const tip = $("tip");
  if (id == null || id === TM.getFocus()) { tip.hidden = true; return; }
  tip.innerHTML = tipHtml(id);
  tip.hidden = false;
  let x, y;
  if (e) { x = e.clientX; y = e.clientY; }
  else if (it) { const r = TM.canvasEl().getBoundingClientRect(); x = r.left + it.x + Math.min(it.w, 40); y = r.top + it.y + Math.min(it.h, 24); }
  else return;
  const tw = tip.offsetWidth, th = tip.offsetHeight;
  let tx = x + 14, ty = y + 16;
  if (tx + tw > innerWidth - 8) tx = x - tw - 12;
  if (ty + th > innerHeight - 8) ty = y - th - 12;
  tip.style.left = Math.max(8, tx) + "px"; tip.style.top = Math.max(8, ty) + "px";
}

// ---------- boot
async function boot() {
  setLang(pickLang());
  staticText();
  const [atlas] = await Promise.all([getJSON("data/atlas.json"), loadNames(lang())]);
  build(atlas);
  const sm = store("atlas-mode");
  TM.initTreemap($("tm"), {
    select: (id) => go(targetOf(id), true),
    focus: (id) => go(typeof id === "number" && isAct(id) ? idOf(id) + ":" : targetOf(id)),
    hover: onHover,
    up,
  });
  if (sm === "dec") TM.setMode("dec");
  if (document.fonts) document.fonts.load("600 12px Geist").then(() => TM.refreshLabels()).catch(() => {});
  $("mode").addEventListener("click", (e) => {
    const b = e.target.closest("[data-mode]"); if (!b) return;
    TM.setMode(b.dataset.mode); store("atlas-mode", b.dataset.mode);
    renderMode(); renderCrumbs(); setTimeout(renderLegend, 700);
  });
  $("legend").addEventListener("pointerover", (e) => { const b = e.target.closest("[data-cls]"); TM.highlightClass(b ? +b.dataset.cls : -1); });
  $("legend").addEventListener("pointerleave", () => TM.highlightClass(-1));
  $("legend").addEventListener("click", (e) => {                     // touch: a tap toggles the highlight
    const b = e.target.closest("[data-cls]"); if (!b) return;
    const on = b.getAttribute("aria-pressed") !== "true";
    for (const x of $("legend").querySelectorAll("[data-cls]")) x.setAttribute("aria-pressed", "false");
    b.setAttribute("aria-pressed", on); TM.highlightClass(on ? +b.dataset.cls : -1);
  });
  const toLang = (lg) => { const { rest } = parseHash(); history.pushState(null, "", `#${lg}/${rest}`); route(); };
  $("langs").addEventListener("click", (e) => { const b = e.target.closest("[data-lang]"); if (b) toLang(b.dataset.lang); });
  $("langsel").addEventListener("change", () => toLang($("langsel").value));
  initSearch({ go, ensureAct });
  addEventListener("hashchange", route);
  addEventListener("popstate", route);
  wide.addEventListener("change", () => S.view === "map" && panelFor());
  addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement.tagName !== "INPUT") { e.preventDefault(); $("q").focus(); }
  });
  S.booted = true;
  await route();
  $("loading").hidden = true;
}
boot().catch((e) => { console.error(e); $("loadtxt").textContent = "Error: " + e.message; });
export { go };
