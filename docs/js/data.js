// The model: one tree of every act (docs/data/atlas.json), names per language, and the detail files
// loaded when they are needed. Node indices are positions in depth-first order: a node's children
// follow it, and a parent always comes before its children.
import { lang, cantonName, t } from "./i18n.js";

const cache = new Map();
export function getJSON(url) {
  if (!cache.has(url)) {
    cache.set(url, fetch(url).then((r) => {
      if (!r.ok) throw new Error(`${url}: ${r.status}`);
      return r.json();
    }).catch((e) => { cache.delete(url); throw e; }));
  }
  return cache.get(url);
}

export const KIND = { r: 0, b: 1, c: 2, a: 3, o: 4, t: 5, g: 6, x: 7 };
const KCH = "rbcaotgx";
export const M = { n: 0 };

export function build(atlas) {
  const f = atlas.meta.fields, rows = atlas.nodes, n = rows.length;
  const at = Object.fromEntries(f.map((k, j) => [k, j]));
  Object.assign(M, {
    meta: atlas.meta, n,
    K: new Uint8Array(n), P: new Int32Array(n), S: new Array(n), F: new Int8Array(n).fill(-1),
    D: new Float64Array(n), A: new Int32Array(n), PK: new Int16Array(n).fill(-1), AD: new Array(n), BY: new Array(n),
    U: new Array(n), AB: new Array(n), CT: new Array(n), FB: new Array(n), MM: new Int32Array(n), DD: new Float64Array(n),
    SR: new Array(n), HD: new Uint8Array(n), RP: new Array(n), HG: new Uint8Array(n),
  });
  for (let i = 0; i < n; i++) {
    const r = rows[i], g = (k) => r[at[k]];
    M.K[i] = KIND[r[0]]; M.P[i] = r[1]; M.S[i] = r[2] || "";
    const fl = g("f"); if (fl != null) M.F[i] = fl;
    M.D[i] = g("d") || 0; M.A[i] = g("n") || 0;
    const pk = g("pk"); if (pk != null) M.PK[i] = pk;
    M.AD[i] = g("ad") || ""; M.BY[i] = g("by") || ""; M.U[i] = g("u") || ""; M.AB[i] = g("ab") || "";
    M.CT[i] = g("ct") || ""; M.FB[i] = g("fb") || ""; M.MM[i] = g("m") || 0; M.DD[i] = g("dd") || 0; M.SR[i] = g("sr") || ""; M.HD[i] = g("hd") ? 1 : 0;
    M.RP[i] = g("rp") || ""; M.HG[i] = g("hg") ? 1 : 0;
  }
  // children, as slices of one array
  const cnt = new Int32Array(n);
  for (let i = 1; i < n; i++) cnt[M.P[i]]++;
  M.ko = new Int32Array(n + 1);
  for (let i = 0; i < n; i++) M.ko[i + 1] = M.ko[i] + cnt[i];
  M.kv = new Int32Array(n);
  const fill = M.ko.slice(0, n);
  for (let i = 1; i < n; i++) M.kv[fill[M.P[i]]++] = i;
  // where each subtree ends: the descendants of i are i+1 … end[i]-1
  M.end = new Int32Array(n);
  for (let i = n - 1; i >= 0; i--) { if (M.end[i] < i + 1) M.end[i] = i + 1; if (i) M.end[M.P[i]] = Math.max(M.end[M.P[i]], M.end[i]); }
  // depth, the block a node belongs to, and an index by id
  M.depth = new Uint8Array(n); M.block = new Int32Array(n);
  M.byId = new Map();
  for (let i = 0; i < n; i++) {
    if (i) { M.depth[i] = M.depth[M.P[i]] + 1; M.block[i] = M.K[i] === KIND.b ? i : M.block[M.P[i]]; }
    M.byId.set(idOf(i), i);
    if (M.SR[i]) M.byId.set(M.SR[i], i);
  }
  // values per mode (acts in force; decisions) and the colour classes of what lies below
  // hist: the time view's map, every act that was ever in force (today's and the earlier federal acts), each
  // earlier act in the colour of who made it (hcls) rather than hatched
  M.val = { acts: new Float64Array(n), dec: new Float64Array(n), hist: new Float64Array(n) };
  M.comp = { acts: new Float32Array(n * 7), dec: new Float32Array(n * 7), hist: new Float32Array(n * 7) };
  M.cls = new Int8Array(n).fill(-1); M.hcls = new Int8Array(n).fill(-1);
  for (let i = n - 1; i >= 0; i--) {
    const k = M.K[i];
    if (k === KIND.a || k === KIND.o || k === KIND.x) {
      const c = classOf(i), h = k === KIND.o ? floorClass(M.F[i]) : c; M.cls[i] = c; M.hcls[i] = h;
      const va = k === KIND.a ? 1 : 0, vd = M.D[i], vh = k === KIND.x ? 0 : 1;
      M.val.acts[i] = va; M.val.dec[i] = vd; M.val.hist[i] = vh;
      M.comp.acts[i * 7 + c] += va; M.comp.dec[i * 7 + c] += vd; M.comp.hist[i * 7 + h] += vh;
    }
    if (i) {
      const p = M.P[i];
      M.val.acts[p] += M.val.acts[i]; M.val.dec[p] += M.val.dec[i]; M.val.hist[p] += M.val.hist[i];
      for (let c = 0; c < 7; c++) {
        M.comp.acts[p * 7 + c] += M.comp.acts[i * 7 + c]; M.comp.dec[p * 7 + c] += M.comp.dec[i * 7 + c]; M.comp.hist[p * 7 + c] += M.comp.hist[i * 7 + c];
      }
    }
  }
  M.root = 0;
}

// The five colours: who made the rule (legend), plus "not in the collection" and "level not recorded"
function classOf(i) {
  const k = M.K[i];
  if (k === KIND.o || k === KIND.x) return 5;
  return floorClass(M.F[i]);
}
function floorClass(f) {
  if (f === 0 || f === 4) return 0;
  if (f === 1 || f === 5) return 1;
  if (f === 2 || f === 6) return 2;
  if (f === 3 || f === 7) return 3;
  if (f === 8) return 4;
  return 6;
}

export const kids = (i) => M.kv.subarray(M.ko[i], M.ko[i + 1]);
export const kindOf = (i) => KCH[M.K[i]];
export const isAct = (i) => M.K[i] === KIND.a || M.K[i] === KIND.o || M.K[i] === KIND.x;

export function idOf(i) {
  switch (M.K[i]) {
    case KIND.r: return "";
    case KIND.c: return "c" + M.S[i];
    case KIND.a: return M.CT[i] ? `${M.CT[i]}/${M.S[i]}` : M.S[i];
    case KIND.g: return `${M.S[M.P[i]]}/-`;
    case KIND.x: return `${M.CT[i]}/-${M.S[i]}`;
    default: return M.S[i];                        // block (fed/int/kt), earlier act (101@1874), canton (ZH)
  }
}

// names in the current language
export async function loadNames(lg) {
  const nm = await getJSON(`data/names.${lg}.json`);
  const cap = (x) => (x && /^[A-ZÀ-ÖØ-Þ]{3,}\s/.test(x) && /[a-zà-ÿ]/.test(x) ? x.replace(/^([A-ZÀ-ÖØ-Þ])([A-ZÀ-ÖØ-Þ]+)/, (m, a, b) => a + b.toLowerCase()) : x);
  M.L = nm.l.map(cap); M.T = nm.t.map(cap); M.lang = lg;
  shortTab = new Map();
  searchIndex = null;
}
// the names of the repealed acts only the time view shows: their own file, loaded with it (decision 32)
export async function loadHistNames(lg) {
  const h = await getJSON(`data/hnames.${lg}.json`).catch(() => null);      // without them the past keeps its numbers only
  if (!h) return;
  h.i.forEach((i, k) => { M.L[i] = h.l[k]; M.T[i] = h.t[k]; });
  shortTab = new Map();
}
export function label(i) {
  const k = M.K[i];
  if (k === KIND.c) return `${M.S[i]} ${M.L[i]}`;
  if (k === KIND.t) return cantonName(M.S[i]);
  if (k === KIND.x && M.S[i] === "*") return t("pooled");
  return M.L[i] || M.S[i];
}
export const title = (i) => M.T[i] || "";
// A short name for a tile: the abbreviation; without one, the title less its date and less the words
// it shares with at least two siblings ("Verordnung des SBFI über die berufliche Grundbildung …").
const DATES = [/\s+vom\s+\d{1,2}\.\s*[^\s\d]+\s+\d{4}/g, /\s+du\s+\d{1,2}(?:er|\.)?\s+[^\s\d]+\s+\d{4}/gi,
  /\s+del(?:l['’]|\s)?\s*\d{1,2}(?:°|o|\.)?\s+[^\s\d]+\s+\d{4}/gi, /\s+of\s+\d{1,2}\s+[A-Z][a-z]+\s+\d{4}/g];
const undate = (s) => { for (const r of DATES) s = s.replace(r, ""); return s.replace(/\s+([,)])/g, "$1").trim(); };
const TYPE = new RegExp("^(?:(?:Bundes|Einführungs)?(?:gesetz|verordnung|beschluss)|Gesetz|Verordnung|Reglement|Beschluss|Dekret|Vereinbarung|Weisungen?|Richtlinien?|" +
  "Loi(?: fédérale)?|Ordonnance|Règlement|Arrêté|Décret|Convention|Accord|Directive|Legge(?: federale)?|Ordinanza|Regolamento|Decreto(?: legislativo| esecutivo)?|Convenzione|Accordo|Direttiva)" +
  "(?:\\s+(?:des|der|du|de la|de l['’]|del|della|dell['’])\\s+\\S+)?" +
  "\\s+(?:über\\s+(?:den|die|das)|zum|zur|betreffend(?:\\s+(?:den|die|das))?|sur\\s+(?:le|la|les|l['’])|sur|concernant(?:\\s+(?:le|la|les|l['’]))?|relative?\\s+(?:au|aux|à la|à l['’])|" +
  "che\\s+(?:stabilisce|istituisce|disciplina|fissa)|qui\\s+(?:fixe|institue|règle)|sul(?:la|lo|le|l['’])?|sugli|sui|concernente(?:\\s+(?:il|la|lo|i|gli|le|l['’]))?|relativ[oa]\\s+(?:al|alla|ai|alle|all['’]))\\s*", "i");
function untype(s) {
  const r = s.replace(TYPE, "");
  return r !== s && r.length >= 8 && /\s/.test(r.trim()) ? r : r !== s && r.length >= 10 ? r : s;
}
let shortTab = new Map();
// an abbreviation three siblings share ("EFZ" for 190 ordinances on vocational training) names none of them
const ownText = (c, weak) => (M.T[c] && !weak.has(M.L[c]) ? M.L[c] : undate(M.T[c] || M.L[c] || ""));
export function shortLabel(i) {
  if (!isAct(i) || M.K[i] === KIND.x) return label(i);
  const p = M.P[i];
  let tab = shortTab.get(p);
  if (!tab) {
    const n = new Map(), pre = new Map(), suf = new Map(), weak = new Set();
    for (const c of kids(p)) if (isAct(c) && M.T[c]) n.set(M.L[c], (n.get(M.L[c]) || 0) + 1);
    for (const [k, v] of n) if (v >= 3) weak.add(k);
    for (const c of kids(p)) if (isAct(c) && (!M.T[c] || weak.has(M.L[c]))) {
      const w = ownText(c, weak).split(/\s+/);
      for (let k = 3; k <= Math.min(10, w.length - 1); k++) { const key = w.slice(0, k).join(" "); pre.set(key, (pre.get(key) || 0) + 1); }
      for (let k = 2; k <= Math.min(8, w.length - 1); k++) { const key = w.slice(-k).join(" "); suf.set(key, (suf.get(key) || 0) + 1); }
    }
    tab = { pre, suf, weak };
    shortTab.set(p, tab);
  }
  if (M.T[i] && !tab.weak.has(M.L[i])) return label(i);
  const s = ownText(i, tab.weak);
  let w = s.split(/\s+/);
  for (let k = Math.min(10, w.length - 1); k >= 3; k--) {
    if ((tab.pre.get(w.slice(0, k).join(" ")) || 0) >= 3 && w.slice(k).join(" ").length >= 4) { w = w.slice(k); break; }
  }
  for (let k = Math.min(8, w.length - 1); k >= 2; k--) {
    if ((tab.suf.get(w.slice(-k).join(" ")) || 0) >= 3 && w.slice(0, -k).join(" ").length >= 4) { w = w.slice(0, -k); break; }
  }
  const out = untype(w.join(" "));
  return out ? out[0].toUpperCase() + out.slice(1) : s || label(i);
}
export const labelCt = (i) => {
  const l = label(i), ct = M.CT[i];
  return ct && M.K[i] !== KIND.t && !new RegExp(`(^|[\\s/-])${ct}($|[\\s/-])`).test(l) ? `${l} ${ct}` : l;
};
export function longName(i) {                       // title, else label
  const k = M.K[i];
  if (k === KIND.c || k === KIND.t || k === KIND.b || k === KIND.r || k === KIND.g) return label(i);
  return title(i) || label(i);
}
export function srOf(i) {                           // the number the official collection gives the act
  const k = M.K[i];
  if (k === KIND.a || k === KIND.o) return M.S[i].split("@")[0];
  if (k === KIND.c) return M.S[i];
  return "";
}
export function urlOf(i) {
  const u = M.U[i], ct = M.CT[i];
  if (u && /^https?:/.test(u)) return u;
  if (u) return M.meta.fedlex + u;
  if (ct && M.meta.kurl[ct] && M.K[i] === KIND.a) return M.meta.kurl[ct].replace("{}", M.S[i]);
  return "";
}
export const blockKey = (i) => M.S[M.block[i]];     // fed / int / kt
export function pathTo(i) {                         // root … i
  const out = [];
  for (let j = i; j >= 0; j = M.P[j]) out.unshift(j);
  return out;
}
export const isAncestor = (a, b) => { for (let j = b; j >= 0; j = M.P[j]) if (j === a) return true; return false; };

// ---- detail files
export const loadLinks = () => getJSON("data/links.json").then(indexLinks);
let linkIdx = null;
function indexLinks(l) {
  if (linkIdx) return linkIdx;
  const up = new Map(), down = new Map(), co = new Map(), out = new Map(), inn = new Map();
  const push = (m, k, v) => { if (!m.has(k)) m.set(k, []); m.get(k).push(v); };
  for (const [a, b, prim, arts] of l.bases) { push(up, a, { j: b, prim, arts }); push(down, b, { j: a, prim, arts }); }
  for (const [a, b, n, lift] of l.cocite) { push(co, a, { j: b, n, lift }); push(co, b, { j: a, n, lift }); }
  for (const [a, b, w] of l.legis) { push(out, a, { j: b, n: w }); push(inn, b, { j: a, n: w }); }
  linkIdx = { up, down, co, out, inn };
  return linkIdx;
}
export const loadYears = () => getJSON("data/years.json");
export const loadArts = (pk) => getJSON(`data/art/${pk}.json`);
export const loadLaw = (i) => getJSON(`data/law/${M.CT[i] || "F"}.json`);
export const loadHier = () => getJSON("data/hier.json");
export const loadMethod = () => getJSON("data/method.json");

// ---- search: acts by any language's abbreviation, SR number, title words; articles ("Art. 41 OR");
// division headings ("Mietrecht"), loaded with the first query of three letters or more.
let searchIndex = null;
export const fold = (s) => (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[’']/g, "'");
function buildSearch() {
  const ab = [], ti = [], nodes = [];
  for (let i = 0; i < M.n; i++) {
    const k = M.K[i];
    if (k === KIND.r || k === KIND.g || (k === KIND.o && !M.D[i])) continue;     // repealed acts no court cites: the time view only
    nodes.push(i);
    const a = new Set();
    if (M.AB[i]) for (const x of M.AB[i].split("|")) a.add(fold(x));
    if (k === KIND.a || k === KIND.o || k === KIND.x) a.add(fold(M.L[i]));
    if (k === KIND.t) { a.add(fold(M.S[i])); a.add(fold(cantonName(M.S[i]))); }
    ab.push([...a]);
    ti.push(fold(`${M.L[i]} ${M.T[i] || ""} ${k === KIND.c || k === KIND.a || k === KIND.o ? srOf(i) : ""} ${M.SR[i]}`));
  }
  searchIndex = { ab, ti, nodes };
}
const weight = (i) => M.val.dec[i] + 30 * M.val.acts[i];
export function searchActs(q, limit = 12) {
  if (!searchIndex) buildSearch();
  const raw = fold(q).trim();
  if (!raw) return [];
  const ctm = raw.match(/(?:^|\s)([a-z]{2})$|^([a-z]{2})\s/);       // "pbg zh", "zh pbg"
  const cts = new Set(Object.keys(M.meta.kurl).concat(["ge", "gl", "ju", "sz", "ti"]).map((c) => c.toLowerCase()));
  let ct = "", q2 = raw;
  if (ctm) {
    const c = ctm[1] || ctm[2];
    if (cts.has(c) && raw.length > 3) { ct = c.toUpperCase(); q2 = raw.replace(new RegExp(`(^${c}\\s+|\\s+${c}$)`), "").trim(); }
  }
  const words = q2.split(/\s+/).filter(Boolean);
  const { ab, ti, nodes } = searchIndex, hits = [];
  const srq = /^\d+(?:\.\d+)*$/.test(q2.replace(/^(sr|rs)\s*/, "")) ? q2.replace(/^(sr|rs)\s*/, "") : "";
  for (let k = 0; k < nodes.length; k++) {
    const i = nodes[k];
    if (ct && M.CT[i] !== ct && !(M.K[i] === KIND.t && M.S[i] === ct)) continue;
    let s = 0;
    for (const a of ab[k]) {
      if (a === q2) s = Math.max(s, 100);
      else if (a.startsWith(q2) && q2.length >= 2) s = Math.max(s, 60 - Math.min(20, a.length - q2.length));
    }
    if (srq) {
      const sr = M.K[i] === KIND.a || M.K[i] === KIND.o || M.K[i] === KIND.c ? srOf(i) : "";
      if (sr === srq || M.SR[i] === srq) s = Math.max(s, 95);
      else if (sr.startsWith(srq + ".")) s = Math.max(s, 40);
    }
    if (!s && words.length && words.every((w) => ti[k].includes(w))) {
      const starts = words.map((w) => new RegExp(`(^|[\\s(\\-/'’])${w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`).test(ti[k]));
      if (words.every((w, j) => starts[j] || w.length >= 4)) s = 20 + (starts.every(Boolean) ? 10 : 0);
    }
    if (s) hits.push([s, i]);
  }
  hits.sort((x, y) => y[0] - x[0] || (M.K[x[1]] === KIND.o) - (M.K[y[1]] === KIND.o) || weight(y[1]) - weight(x[1]) || x[1] - y[1]);
  return hits.slice(0, limit).map((h) => h[1]);
}
export function exactActs(code) {                     // acts whose abbreviation is exactly this (any language)
  if (!searchIndex) buildSearch();
  const c = fold(code).trim(), out = [];
  searchIndex.nodes.forEach((i, k) => { if (isAct(i) && searchIndex.ab[k].includes(c)) out.push(i); });
  return out.sort((a, b) => (M.K[a] === KIND.o) - (M.K[b] === KIND.o) || M.D[b] - M.D[a]);
}
// "Art. 41 OR", "41 OR", "OR 41", "art 8 cedh"
export function parseArticle(q) {
  const s = q.trim().replace(/\s+/g, " ");
  let m = s.match(/^(?:art(?:\.|icle|ikel|icolo)?\s*)(\d+[a-z]{0,6})(?:\s*(?:abs|al|cpv|para)\.?\s*\d+\w*)?\s+(.+)$/i) ||
    s.match(/^(\d+[a-z]{0,6})\s+(\D.*)$/i);
  if (m) return { num: m[1].toLowerCase(), act: m[2] };
  m = s.match(/^(.+?)\s+(?:art\.?\s*)?(\d+[a-z]{0,6})$/i);
  if (m && !/^\d/.test(m[1])) return { num: m[2].toLowerCase(), act: m[1] };
  return null;
}
export const normNum = (s) => fold(s).replace(/[\s.]/g, "");
let topics = null, topicsLang = "";
// a heading matches when each word starts one of its words or one of its parents' ("Miete Kündigung");
// with nothing found, long words are cut to their first four letters ("Mietrecht" → "miet")
export async function searchTopics(q, limit = 6) {
  const lg = lang();
  if (!topics || topicsLang !== lg) {
    topics = (await getJSON(`data/find.${lg}.json`)).map((r) => [r[0], r[1], r[2], r[3], fold(r[2]).split(/[^a-z0-9]+/).filter(Boolean), r[4]]);
    topicsLang = lg;
  }
  const words = fold(q).split(/[^a-z0-9]+/).filter((w) => w.length >= 3);
  if (!words.length) return [];
  const has = (tp, w) => tp[4].some((tok) => tok.startsWith(w));
  const run = (ws) => {
    const out = [];
    for (const tp of topics) {
      if (tp[0] < 0) continue;
      let own = 0, ok = true;
      for (const w of ws) {
        if (has(tp, w)) { own++; continue; }
        let p = tp[5], found = false;
        while (p >= 0 && !found) { found = has(topics[p], w); p = topics[p][5]; }
        if (!found) { ok = false; break; }
      }
      if (ok && own) out.push({ i: tp[0], eid: tp[1], h: tp[2], n: tp[3], score: own * 30 + Math.log10(tp[3] + 1) * 25 });
    }
    return out;
  };
  let out = run(words);
  if (!out.length) out = run(words.map((w) => (w.length > 5 ? w.slice(0, 4) : w)));
  out.sort((a, b) => b.score - a.score);
  return out.slice(0, limit);
}
