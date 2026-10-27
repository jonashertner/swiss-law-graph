// The method: every count, exclusion and choice behind the views, from the pipeline's own records.
import { t, lang } from "./i18n.js";
import { M, loadMethod } from "./data.js";
import { methodHTML } from "./methodtext.js";
import { $, esc, num } from "./util.js";

let ctx = {}, data = null;
const REPO = "https://github.com/jonashertner/swiss-law-graph";
const foot = {
  de: (d) => `Quellen: OpenCaseLaw (CC0, Stand ${d}), Fedlex, die Gesetzessammlungen der 26 Kantone. Programm und Daten: <a href="${REPO}">${REPO.replace("https://", "")}</a>.`,
  fr: (d) => `Sources : OpenCaseLaw (CC0, état au ${d}), Fedlex, les recueils de lois des 26 cantons. Programme et données : <a href="${REPO}">${REPO.replace("https://", "")}</a>.`,
  it: (d) => `Fonti: OpenCaseLaw (CC0, stato al ${d}), Fedlex, le raccolte di leggi dei 26 Cantoni. Programma e dati: <a href="${REPO}">${REPO.replace("https://", "")}</a>.`,
  en: (d) => `Sources: OpenCaseLaw (CC0, as of ${d}), Fedlex, the statute collections of the 26 cantons. Code and data: <a href="${REPO}">${REPO.replace("https://", "")}</a>.`,
};
function render() {
  const shim = { method: t("method"), decisions: t("decisions"), lv1: t("row1"), lv2: t("row2"), lv3: t("row3") };
  let body = methodHTML({ ...data.core, inforce: data.inforce }, lang(), shim, num, esc, data.tree);
  body = body.replace(/^\s*<button[^>]*id="mclose"[^>]*>.*?<\/button>\s*<h2[^>]*>.*?<\/h2>\s*<p>.*?<\/p>/s, "");
  $("mdoc").innerHTML = `<h1>${esc(t("method"))}</h1><p class="lead">${esc(t("methodLead"))}</p>` +
    `<p class="note">${esc(t("nActsInForce", num(M.meta.counts.fed_in_force + M.meta.counts.int_in_force + M.meta.counts.kt_in_force)))} · ${esc(t("nDec", num(M.meta.decisions)))} · ${esc(t("asOf"))} ${esc(M.meta.run || "")}</p>` +
    body.replace(/<h3>/g, "<h2>").replace(/<\/h3>/g, "</h2>") +
    `<p class="foot">${foot[lang()](esc(data.core.snapshot || M.meta.run || ""))}</p>`;
}
export async function init(c) { ctx = c; data = await loadMethod(); }
export async function show() { ctx.panel.hide(); render(); $("v-method").scrollTop = 0; }
export function refresh() { if (!$("v-method").hidden) render(); }
