// Compare the cantons (decision 35): for a federal act, the cantonal acts whose Ingress names it as a basis,
// canton by canton in the order of Art. 1 BV — with their level and the articles they name.
import { t, cantonName } from "./i18n.js";
import { M, KIND, idOf, label, labelCt, title, loadLinks, fold } from "./data.js";
import { $, esc, num, href, sw } from "./util.js";
import { cantonalOf, cantonOrder, normArt } from "./impact.js";

let ctx = null, L = null, rank = null, cur = null, q = "";

export async function init(c) { ctx = c; L = await loadLinks(); }

// every federal act with at least one cantonal act resting on it: cantons, acts
function ranking() {
  if (rank) return rank;
  rank = [];
  for (const [i] of L.down) {
    if (M.K[i] !== KIND.a || M.CT[i]) continue;
    const by = cantonalOf(L, i);
    if (!by.size) continue;
    let n = 0; for (const xs of by.values()) n += xs.length;
    rank.push({ i, k: by.size, n, by });
  }
  rank.sort((a, b) => b.k - a.k || b.n - a.n || a.i - b.i);
  return rank;
}
const cell = (n) => `<i class="${n ? (n >= 4 ? "c3" : n >= 2 ? "c2" : "c1") : ""}"></i>`;
function strip(by) {
  return `<span class="strip" aria-hidden="true">${cantonOrder().map((ct) => cell((by.get(ct) || []).length)).join("")}</span>`;
}
const eidOf = (a) => (/^art_/.test(a) ? a : "art_" + String(a).replace(/\s+/g, "_"));
const artLabel = (a) => normArt(a).replace(/^(\d+)([a-z]+)$/, "$1$2");

function indexHTML() {
  const f = fold(q);
  const list = ranking().filter((r) => !f || fold(label(r.i)).includes(f) || fold(title(r.i)).includes(f) || M.S[r.i].startsWith(q.trim()));
  const head = `<div class="cthead" aria-hidden="true"><span></span><span class="strip">${cantonOrder().map((ct) => `<b title="${esc(cantonName(ct))}">${esc(ct)}</b>`).join("")}</span><span></span></div>`;
  return `<h2>${esc(t("cTop"))}</h2>${head}<ul class="ctlist">${list.slice(0, 80).map((r) =>
    `<li><a href="${href("cantons/" + idOf(r.i))}"><span class="a">${sw(M.cls[r.i] >= 0 ? M.cls[r.i] : 6)}<b>${esc(label(r.i))}</b> <span class="b">${esc(title(r.i) !== label(r.i) ? title(r.i) : "")}</span></span>` +
    `${strip(r.by)}<span class="v">${esc(t("cRow", num(r.k), num(r.n)))}</span></a></li>`).join("")}</ul>`;
}

function actHTML(i) {
  const by = cantonalOf(L, i);
  let n = 0; for (const xs of by.values()) n += xs.length;
  const rows = cantonOrder().map((ct) => {
    const xs = (by.get(ct) || []).slice().sort((p, q) => (M.F[p.j] - M.F[q.j]) || (M.D[q.j] - M.D[p.j]) || p.j - q.j);
    const acts = xs.map((x) => {
      const arts = (x.arts || []).map(artLabel).filter(Boolean);
      return `<li><a href="${href(idOf(x.j))}">${sw(M.cls[x.j] >= 0 ? M.cls[x.j] : 6)}<b>${esc(label(x.j))}</b>${title(x.j) && title(x.j) !== label(x.j) ? ` <span class="b">${esc(title(x.j))}</span>` : ""}` +
        `${arts.length ? ` <span class="arts">${esc(t("art"))} ${esc(arts.slice(0, 6).join(", "))}${arts.length > 6 ? " …" : ""}</span>` : ""}</a></li>`;
    });
    return `<tr${xs.length ? "" : ' class="none"'}><th scope="row"><span class="ct">${esc(ct)}</span> ${esc(cantonName(ct))}</th><td class="r">${xs.length ? esc(num(xs.length)) : ""}</td>` +
      `<td>${xs.length ? `<ul class="cacts">${acts.slice(0, 4).join("")}${acts.length > 4 ? `${acts.slice(4).map((a) => a.replace("<li>", "<li hidden>")).join("")}<li><button class="moreb" data-more="1">+ ${esc(t("more", num(acts.length - 4)))}</button></li>` : ""}</ul>` :
        `<span class="none">${esc(t("cNone"))}</span>`}</td></tr>`;
  }).join("");
  // the articles of the federal act the cantons name, by the number of cantons naming each
  const arts = new Map();
  for (const [ct, xs] of by) for (const x of xs) for (const a of x.arts || []) {
    const k = normArt(a); if (!k) continue;
    if (!arts.has(k)) arts.set(k, { a, cts: new Set() });
    arts.get(k).cts.add(ct);
  }
  const top = [...arts.values()].sort((p, q) => q.cts.size - p.cts.size || String(p.a).localeCompare(String(q.a), "de", { numeric: true })).slice(0, 16);
  const artList = top.length ? `<h2>${esc(t("cArts"))}</h2><ul class="cartlist">${top.map((x) =>
    `<li><a href="${href(idOf(i) + ":" + eidOf(x.a))}"><b>${esc(t("art"))} ${esc(artLabel(x.a))}</b><span class="t"><i style="width:${(100 * x.cts.size / 26).toFixed(1)}%"></i></span>` +
    `<span class="v">${esc(t("cArtRow", num(x.cts.size)))}</span></a></li>`).join("")}</ul>` : "";
  return `<p class="crumb"><a href="${href("cantons")}">← ${esc(t("cBack"))}</a></p>` +
    `<h2 class="acth">${sw(M.cls[i] >= 0 ? M.cls[i] : 6)}${esc(labelCt(i))}</h2>${title(i) && title(i) !== label(i) ? `<p class="lead">${esc(title(i))}</p>` : ""}` +
    `<p class="stat1">${esc(t("cStat", num(n), num(by.size)))} <a href="${href(idOf(i))}">${esc(t("cOpen"))}</a></p>` +
    `<div class="tw"><table class="ctab"><tbody>${rows}</tbody></table></div>${artList}<p class="note">${esc(t("cNote"))}</p>`;
}

function render() {
  const d = $("cdoc");
  const pick = cur != null;
  d.innerHTML = `<h1>${esc(t("impCompare"))}</h1><p class="lead">${esc(t("cLede"))}</p>` +
    (pick ? "" : `<div class="csearch"><input id="cq" type="search" placeholder="${esc(t("cSearch"))}" aria-label="${esc(t("cSearch"))}" value="${esc(q)}"></div>`) +
    `<div id="cbody">${pick ? actHTML(cur) : indexHTML()}</div>`;
  const inp = $("cq");
  if (inp) inp.oninput = () => { q = inp.value; $("cbody").innerHTML = indexHTML(); };
  d.querySelectorAll("[data-more]").forEach((b) => (b.onclick = () => {
    b.closest("ul").querySelectorAll("li[hidden]").forEach((li) => (li.hidden = false)); b.parentElement.remove();
  }));
}

export async function show(rest) {
  ctx.panel.hide();
  const id = rest.split("/").slice(1).join("/");
  const i = id ? M.byId.get(id) : null;
  cur = i != null && M.K[i] === KIND.a && !M.CT[i] ? i : null;
  render();
  $("v-cantons").scrollTop = 0;
}
export function refresh() { if (!$("v-cantons").hidden) render(); }
