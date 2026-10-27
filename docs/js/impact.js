// What depends on an act or an article (decision 35): every act in force whose Ingress names it as a basis, and
// whatever rests on those, down the whole chain of delegation. Read from links.json (the stated bases, all of them).
import { M, KIND, kids } from "./data.js";

export const normArt = (s) => String(s).replace(/^art_/, "").replace(/_/g, "").toLowerCase();

// j -> depth (1 = names it directly); art: only first steps that name this article
export function dependents(L, i, art = null) {
  const depth = new Map();
  let front = [];
  for (const x of L.down.get(i) || []) {
    if (x.j === i || M.K[x.j] !== KIND.a) continue;
    if (art && !(x.arts || []).some((a) => normArt(a) === art)) continue;
    if (!depth.has(x.j)) { depth.set(x.j, 1); front.push(x.j); }
  }
  for (let d = 2; front.length; d++) {
    const next = [];
    for (const j of front) for (const x of L.down.get(j) || []) {
      if (x.j !== i && M.K[x.j] === KIND.a && !depth.has(x.j)) { depth.set(x.j, d); next.push(x.j); }
    }
    front = next;
  }
  return depth;
}

// "fed", "int" or the canton
export const jurisdiction = (j) => M.CT[j] || (M.S[j].startsWith("0.") ? "int" : "fed");

// the 26 cantons in the order of Art. 1 BV, as the atlas holds them
let order = null;
export function cantonOrder() {
  if (order) return order;
  const kt = kids(0).find((b) => M.S[b] === "kt");
  order = kt == null ? [] : [...kids(kt)].filter((c) => M.K[c] === KIND.t).map((c) => M.S[c]);
  return order;
}

// per federal act: the cantonal acts resting on it directly, by canton
export function cantonalOf(L, i) {
  const by = new Map();
  for (const x of L.down.get(i) || []) {
    const j = x.j, ct = M.CT[j];
    if (!ct || M.K[j] !== KIND.a) continue;
    if (!by.has(ct)) by.set(ct, []);
    by.get(ct).push(x);
  }
  return by;
}
