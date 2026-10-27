// The page: header, router (#<lang>/<target>), the map with its bar, legend and tooltip, and the
// panel. The hierarchy, the matrix and the method load when first opened.
import { t, setLang, lang, LANGS } from "./i18n.js";
import { M, build, loadNames, getJSON, idOf, isAct, KIND, pathTo, isAncestor } from "./data.js";
import * as TM from "./treemap.js";
import * as DOS from "./dossier.js";
import { initSearch, refreshSearch } from "./search.js";
import * as NET from "./net.js";
import * as TV from "./time.js";
import { $, esc, num, sw, href, ICON, store, date } from "./util.js";

const wide = matchMedia("(min-width: 1181px)"), phone = matchMedia("(max-width: 720px)");
const S = { view: "map", target: "", sel: null, booted: false };
let views = {};                                      // lazily loaded modules: hier, matrix, method

// ---------- language
function pickLang() {
  const h = location.hash.slice(1).split("/")[0].split("@")[0];
  if (LANGS.includes(h)) return h;
  const s = store("atlas-lang");
  if (LANGS.includes(s)) return s;
  for (const l of navigator.languages || [navigator.language || ""]) { const c = (l || "").slice(0, 2).toLowerCase(); if (LANGS.includes(c)) return c; }
  return "de";
}
// the footer: when the data were read (the run of the pipeline), from where, and who made it
function renderFoot() {
  const run = M.meta && M.meta.run;
  $("footdate").textContent = run ? t("dataAsOf", date(run)) : "";
  $("footsrc").textContent = t("footSrc"); $("footsrc").href = href("method");
  const [a, b] = t("made");
  $("footmade").innerHTML = `${esc(a)} <span class="heart" aria-label="♥">♥\uFE0E</span> ${esc(b)} <a href="https://jonashertner.com" rel="author">jonashertner.com</a>`;
}
function staticText() {
  renderFoot();
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
    a.href = href(v === "map" ? mapTarget() : { links: "net", cantons: "cantons", check: "check", new: "new", method: "method" }[v]);
  }
  for (const a of $("subnav").querySelectorAll("a")) {
    a.textContent = t(a.dataset.sub === "hier" ? "hier" : a.dataset.sub);
    a.href = href({ net: "net", hier: "hierarchy", matrix: "matrix" }[a.dataset.sub]);
  }
  $("subnav").setAttribute("aria-label", t("links"));
  $("by").title = t("byline");
  $("q").placeholder = t(S.view === "net" ? "searchNet" : "search"); $("q").setAttribute("aria-label", t("search"));
  $("qbtn").setAttribute("aria-label", t("searchOpen")); $("closeq").setAttribute("aria-label", t("close"));
  $("langs").setAttribute("aria-label", t("language"));
  for (const b of $("langs").querySelectorAll("button")) b.setAttribute("aria-pressed", b.dataset.lang === lang());
  $("langsel").value = lang(); $("langsel").setAttribute("aria-label", t("language"));
  $("tm").setAttribute("aria-label", t("mapLabel"));
  $("loadtxt").textContent = t("loading");
  renderMode();
  TV.texts();
}
async function switchLang(lg) {
  if (lg === lang()) return;
  setLang(lg); store("atlas-lang", lg);
  await loadNames(lg);
  await TV.relabel(lg);
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
  // the year of the time view stands next to the language (#de@1975/net): an id may end in a year itself (101@1874)
  const m = /^([a-z]{2})(?:@(\d{4}))?(?:\/(.*))?$/.exec(h);
  if (m && LANGS.includes(m[1])) {
    let rest = m[3] || "", year = m[2] ? +m[2] : null;
    const old31 = /^(net|matrix|hierarchy|)@(\d{4})$/.exec(rest);        // the first links of the time view: #de/net@1975
    if (old31 && !year) { rest = old31[1]; year = +old31[2]; }
    return { lang: m[1], rest, year };
  }
  return { lang: lang(), rest: h, year: null };
}
function go(target, replace = false) {
  const h = href(target);
  if (location.hash === h) return;
  if (replace) history.replaceState(null, "", h); else history.pushState(null, "", h);
  route();
}
async function route() {
  const { lang: lg, rest, year } = parseHash();
  if (lg !== lang()) await switchLang(lg);
  if (year && (!TV.TIME.on || TV.TIME.year !== year)) await TV.enter(year);
  const first = rest.split("/")[0];
  const view = { net: "net", hierarchy: "hier", matrix: "matrix", method: "method", cantons: "cantons", check: "check", new: "new" }[first] || "map";
  showView(view);
  TV.mount(["map", "net", "matrix"].includes(view) ? view : null);
  if (view === "map") { S.target = rest; TM.setTime(mapShare()); await showMap(rest); }
  else await showOther(view, rest);
  syncHash();
  const top = ["net", "hier", "matrix"].includes(view) ? "links" : view;      // three lenses on the same links
  for (const a of $("views").querySelectorAll("a")) {
    if (a.dataset.view === top) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    if (a.dataset.view === "map") a.href = href(mapTarget());
  }
  const sub = $("subnav");
  sub.hidden = top !== "links";
  if (!sub.hidden) {
    $("v-" + view).prepend(sub);
    for (const a of sub.querySelectorAll("a")) if (a.dataset.sub === view) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  }
}
const mapTarget = () => S.target || "";
function showView(v) {
  S.view = v;
  for (const id of ["map", "net", "hier", "matrix", "method", "cantons", "check", "new"]) $("v-" + id).hidden = id !== v;
  $("q").placeholder = t(v === "net" ? "searchNet" : "search");          // in the network the search finds acts there
  DOS.setLinker(v === "net" ? (j) => (NET.has(j) ? href("net/" + idOf(j)) : href(idOf(j))) : null);
  if (v !== "map") $("tip").hidden = true;
}
async function showOther(view, rest) {
  if (!views[view]) {
    const mod = view === "net" ? NET : await import({ hier: "./hierarchy.js", matrix: "./matrix.js", cantons: "./cantons.js",
      check: "./check.js", new: "./check.js" }[view] || "./method.js");
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
  // an earlier act has no place on today's map (unless courts cite it and the area is decisions): show it in its own time
  const y0 = +(M.AD[i] || "").slice(0, 4);
  if (!TV.TIME.on && M.K[i] === KIND.o && y0 && !(TM.getMode() === "dec" && M.D[i] > 0)) {
    await TV.enter(y0); syncHash(); TM.setTime(mapShare());
  }
  let f, s;
  if (eid !== null && isAct(i) && M.PK[i] >= 0 && (await ensureAct(i))) {
    const oa = TM.openActState(), sid = eid ? oa.byEid.get(eid) : null;
    if (!sid) { f = i; s = i; } else if (sid[0] === "A") { f = contextOf(sid); s = sid; } else { f = sid; s = null; }
  } else if (isAct(i)) {
    const cur = TM.getFocus(), r = TM.itemRect(i);
    f = typeof cur === "number" && cur !== i && !isAct(cur) && isAncestor(cur, i) && r && r.lab ? cur : M.P[i];
    if (TM.isGauge(f)) f = M.P[f];                     // an act inside a bar: its block or canton, the bar marked (no mosaic)
    s = i;
  } else if (TM.isGauge(i)) { f = M.P[i]; s = i; }   // a bar (acts without SR number, codes not in the collection): selected
  else { f = i; s = null; }
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
  if (typeof f === "number" && !isAct(f)) tot = mode === "acts" ? (TV.TIME.on ? t("nActsAt", num(TV.actsUnder(f)), TV.TIME.year) :
    t("nActsInForce", num(M.val.acts[f]))) : M.DD[f] ? t("nDec", num(M.DD[f])) : "";
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
  $("legend").innerHTML = cls.map((c) => `<button class="it" data-cls="${c}">${sw(c)}<span>${esc(t(c === 6 ? "levelUnknown" : "c" + c))}</span></button>`).join("")
    + (TM.getMode() === "dec" ? `<span class="note">${esc(t("cantonFloor", String(TM.CANTON_FLOOR * 100).replace(".", t("dec"))))}. ${esc(t("xgScale"))}</span>` :
      TV.TIME.on ? `<span class="note">${esc(t("noSrScale"))}</span>` : "");
}

// tooltip
function tipHtml(id) {
  const lab = TM.labelOf(id), sub = TM.subOf(id), mode = TM.getMode();
  let meta = "";
  if (typeof id === "string") {
    const oa = TM.openActState(), n = oa.n.get(id) || 0;
    meta = id[0] === "A" ? `${esc(t("nDec", num(n)))}${oa.arts[+id.slice(1)][4] ? " · " + esc(t("repealed")) : ""}` : esc(t("nArts", num(oa.va.get(id) || 0)));
  } else if (isAct(id)) {
    const c = M.cls[id], b = TV.TIME.on ? TV.bornOf(id) : 0;
    meta = `<i style="background:var(--c${c})"></i>${esc(t(c === 6 ? "levelUnknown" : "c" + c))} · ${esc(t("nDec", num(TV.decTo(id))))}` +
      (b ? ` · ${esc(t(TV.exists(id) ? "timeSince" : "timeNotYet", b))}` : "");
  } else if (M.HG[id] && TV.TIME.on) {                // acts without an SR number: the gauge's numbers
    const G = TM.gaugeOf(id);
    meta = `${esc(num(G.n))} ${esc(t("gaugeIn", TV.TIME.year))} · ${esc(num(G.top))} ${esc(t("gaugeTop", G.topY))}`;
  } else if (M.XG[id] && TM.isGauge(id)) {             // a canton's codes not in its collection
    const G = TM.gaugeOf(id), p = Math.round(G.share * 100);
    meta = esc(t("codesIn", num(G.n), p < 1 && G.share > 0 ? "<1" : String(p)));
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

// ---------- the time view (decision 31): on the map, an act not yet there is an empty plot of its size; with
// "decisions" as area, a tile fills as its case law accrues. The year rides on the hash, next to the language (#de@1975/net).
function mapShare() {
  if (!TV.TIME.on) return null;
  const n = M.n, mode = TM.getMode(), y = TV.TIME.year, a = new Float32Array(n), tot = new Float32Array(n), sh = new Float32Array(n).fill(1);
  const V = mode === "acts" ? M.val.hist : M.val.dec;            // with acts as area: every act that was ever in force
  for (let i = n - 1; i >= 1; i--) {                  // children follow their parent: sum upwards from the end
    if (isAct(i)) {
      const v = V[i];
      // with decisions as area: an act that exists but has none yet is faint, not an empty plot
      if (v > 0) { tot[i] = v; a[i] = TV.exists(i, y) ? (mode === "acts" ? v : Math.max(v * 0.001, Math.min(v, TV.decTo(i, y)))) : 0; }
    }
    tot[M.P[i]] += tot[i]; a[M.P[i]] += a[i];
  }
  for (let i = 0; i < n; i++) if (tot[i] > 0) sh[i] = a[i] / tot[i];
  return sh;
}
function syncHash() {
  const { lang: lg, rest } = parseHash(), h = `#${lg}${TV.TIME.on ? "@" + TV.TIME.year : ""}/${rest}`;
  if (h !== location.hash) history.replaceState(null, "", h);
}
let hashT = 0;
let timeWas = false;
TV.subscribe(() => {
  if (S.view === "map") { TM.setTime(mapShare()); renderCrumbs(); if (TV.TIME.on !== timeWas) renderLegend(); }
  timeWas = TV.TIME.on;
  if (!hashT) hashT = setTimeout(() => { hashT = 0; syncHash(); }, 400);   // at most every 400 ms, also while playing
});

// ---------- boot
async function boot() {
  setLang(pickLang());
  staticText();
  const [atlas] = await Promise.all([getJSON("data/atlas.json"), loadNames(lang())]);
  build(atlas);
  renderFoot();
  const sm = store("atlas-mode");
  TM.initTreemap($("tm"), {
    select: (id) => go(targetOf(id), true),
    focus: (id) => go(typeof id === "number" && isAct(id) ? idOf(id) + ":" : targetOf(id)),
    hover: onHover,
    up,
  });
  if (sm === "dec") TM.setMode("dec");
  if (document.fonts) document.fonts.load("600 12px Geist").then(() => TM.refreshLabels()).catch(() => {});
  $("v-map").querySelector(".mapbar").appendChild(TV.toggle());
  $("v-net").querySelector(".vhead").appendChild(TV.toggle());
  $("v-matrix").querySelector(".vhead").appendChild(TV.toggle());
  $("mode").addEventListener("click", (e) => {
    const b = e.target.closest("[data-mode]"); if (!b) return;
    TM.setMode(b.dataset.mode); store("atlas-mode", b.dataset.mode); TM.setTime(mapShare());
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
  // in the network a search result opens there; everything else on the map
  initSearch({
    go: (target) => {
      if (S.view === "net") {                        // in the network a hit opens there: an article or a topic opens its act
        const id = target.split(":")[0], i = M.byId.get(id);
        if (i != null && NET.has(i)) return go("net/" + id);
        if (i != null && M.K[i] === KIND.t) return go("net/" + M.S[i]);
        if (i != null && M.K[i] === KIND.b && (M.S[i] === "fed" || M.S[i] === "int")) return go("net/" + M.S[i]);
      }
      return go(target);                             // everything else (an act without a link) on the map
    },
    ensureAct,
    net: () => (S.view === "net" ? NET.has : null),
  });
  NET.load().then(() => { if (S.view === "map") panelFor(); }).catch(() => {});
  DOS.setExtra((i) => (NET.has(i) ? `<a class="btn" href="${href("net/" + idOf(i))}">${ICON.net} ${esc(t("inNet"))}</a>` : ""));
  $("dossier").addEventListener("click", (e) => {             // "Wie ist das Recht gewachsen?": the time view plays
    const b = e.target.closest("[data-act=time]"); if (!b) return;
    if (S.view !== "map") go(""); TV.enter(TV.TIME.y0, true);
  });
  addEventListener("hashchange", route);
  addEventListener("popstate", route);
  wide.addEventListener("change", () => S.view === "map" && panelFor());
  addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement.tagName !== "INPUT") { e.preventDefault(); $("q").focus(); }
  });
  S.booted = true;
  const entry = !location.hash.slice(1);             // the bare address: the map, then the time view plays (decision 33)
  await route();
  $("loading").hidden = true;
  if (entry && S.view === "map") TV.playIntro().catch(() => {});
}
boot().catch((e) => { console.error(e); $("loadtxt").textContent = "Error: " + e.message; });
export { go };
