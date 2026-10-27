// The network view's layout (decision 29). Every act with at least one link — a stated basis, a
// statutory reference or a co-citation (docs/data/links.json) — in two levels:
//   1. one cluster per jurisdiction: federal law, treaties, each canton. Inside a cluster, ForceAtlas2
//      (LinLog, Barnes-Hut) on the links within it; the cluster is scaled to a disc whose area is
//      proportional to its acts. A canton's disc is turned so that its acts linked to federal law
//      face the centre.
//   2. the clusters at fixed places: federal law in the centre (the Constitution at its middle),
//      treaties above it, the 26 cantons on a ring in the order of Art. 1 BV, clockwise from the top,
//      each with as much of the ring as its disc needs.
// The links between clusters are what the view then shows: delegation from cantonal to federal law,
// case law across jurisdictions.
// Run after pipeline/08_web.py:  node layout/net.mjs   (~40 s) → docs/data/net.json
import fs from "node:fs";
import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";

const ROOT = new URL("..", import.meta.url).pathname;
const D = (f) => JSON.parse(fs.readFileSync(ROOT + "docs/data/" + f, "utf8"));
const atlas = D("atlas.json"), links = D("links.json");
const F = atlas.meta.fields, col = Object.fromEntries(F.map((k, j) => [k, j]));
const rows = atlas.nodes, get = (i, k) => rows[i][col[k]];
const UNIT = 10;                                          // a cluster of n acts gets radius UNIT·√n

// ---- nodes with a link, and their clusters
const isAct = (i) => ["a", "o", "x"].includes(rows[i][0]);
const linked = new Set();
for (const name of ["bases", "legis", "cocite"]) for (const e of links[name]) { linked.add(e[0]); linked.add(e[1]); }
const ids = [...linked].filter(isAct).sort((a, b) => a - b);
const clusterOf = (i) => (get(i, "ct") ? "ct:" + get(i, "ct") : (rows[i][2] || "").startsWith("0.") ? "int" : "fed");
const BV = ids.find((i) => rows[i][0] === "a" && rows[i][2] === "101" && !get(i, "ct"));
const members = new Map();
for (const i of ids) { const c = clusterOf(i); if (!members.has(c)) members.set(c, []); members.get(c).push(i); }
const kvOf = new Map();                                   // each canton's constitution: its cluster's middle
for (const i of ids) if (get(i, "ct") && get(i, "f") === 4) kvOf.set(get(i, "ct"), i);

// ---- edges, merged per pair
const W = new Map(), key = (a, b) => (a < b ? a + "|" + b : b + "|" + a);
const add = (a, b, w) => { if (a !== b && linked.has(a) && linked.has(b)) W.set(key(a, b), (W.get(key(a, b)) || 0) + w); };
for (const [a, b, prim] of links.bases) add(a, b, prim ? 2 : 1);
for (const [a, b, w] of links.legis) add(a, b, Math.min(3, 0.6 + 0.4 * Math.log1p(w)));
for (const [a, b, , lift] of links.cocite) add(a, b, 0.5 + 0.3 * Math.log(Math.max(1, lift)));

let seed = 7;
const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);

// ---- 1. each cluster on its own
const local = new Map();                                  // id → [x, y] inside its disc (centre 0, radius r)
const geo = {};                                           // per cluster: rings and sectors, for the view
const radius = {};
for (const [c, list] of members) {
  const g = new Graph({ type: "undirected" });
  const centre = c === "fed" ? BV : c.startsWith("ct:") ? kvOf.get(c.slice(3)) : null;
  for (const i of list) {
    const a = rnd() * 2 * Math.PI, d = Math.sqrt(rnd()) * 100;
    if (i === centre) g.addNode(String(i), { x: 0, y: 0, fixed: true, size: 1 });
    else if (c === "fed") {                               // federal law: start each SR area in its own sector
      const s = +(rows[i][2] || "1")[0] || 1, sa = ((s - 1) / 9) * 2 * Math.PI + (rnd() - 0.5) * 0.6;
      g.addNode(String(i), { x: Math.sin(sa) * (40 + d), y: -Math.cos(sa) * (40 + d), size: 1 });
    } else g.addNode(String(i), { x: Math.cos(a) * d, y: Math.sin(a) * d, size: 1 });
  }
  for (const [k, w] of W) {
    const [a, b] = k.split("|");
    if (g.hasNode(a) && g.hasNode(b)) g.addEdge(a, b, { weight: w });
  }
  forceAtlas2.assign(g, { iterations: list.length > 1500 ? 700 : 500,
    settings: { linLogMode: true, barnesHutOptimize: list.length > 300, barnesHutTheta: 0.6, gravity: 1.2, scalingRatio: 4,
                slowDown: 2, edgeWeightInfluence: 1, outboundAttractionDistribution: true, adjustSizes: false } });
  const pts = list.map((i) => { const a = g.getNodeAttributes(String(i)); return [i, a.x, a.y]; });
  let cx = 0, cy = 0;
  if (centre == null) { for (const [, x, y] of pts) { cx += x; cy += y; } cx /= pts.length; cy /= pts.length; }
  const r = UNIT * Math.sqrt(list.length);
  radius[c] = r;
  radialise(c, pts.map(([i, x, y]) => [i, Math.atan2(y - cy, x - cx)]), centre, r);
  console.log(`${c.padEnd(6)} ${String(list.length).padStart(5)} acts`);
}

// The disc of a cluster in rings by level — constitution in the middle, then parliament, government,
// administration, then what is not in the collection in force — each ring as large as its acts; federal
// law and treaties also in sectors by SR area. Inside a ring (and sector) the acts keep the angular
// order ForceAtlas2 gave them, spread evenly (Halton points), so related acts stay side by side.
function levelOf(i) {
  const k = rows[i][0], f = get(i, "f");
  if (k !== "a") return 4;
  if (f === 0 || f === 4) return 0;
  if (f === 1 || f === 5) return 1;
  if (f === 2 || f === 6) return 2;
  if (f === 3 || f === 7) return 3;
  return f === 8 ? 1 : 4;
}
function halton(j, b) { let f = 1, r = 0; while (j > 0) { f /= b; r += f * (j % b); j = Math.floor(j / b); } return r; }
function radialise(c, nodes, centre, R) {
  const sectorOf = (i) => (c === "fed" ? +(rows[i][2] || "1")[0] || 1 : c === "int" ? +(rows[i][2] || "0.1")[2] || 1 : 0);
  const rest = nodes.filter(([i]) => i !== centre);
  if (centre != null) local.set(centre, [0, 0]);
  const N = rest.length, levels = [0, 1, 2, 3, 4];
  const cnt = levels.map((l) => rest.filter(([i]) => levelOf(i) === l).length);
  const inner = centre != null ? 0.12 : 0, gap = 0.025;
  let cum = 0;
  const band = {};
  for (const l of levels) {
    if (!cnt[l]) continue;
    const r0 = R * Math.sqrt(inner * inner + (1 - inner * inner) * (cum / N)) + (cum ? gap * R : 0);
    cum += cnt[l];
    band[l] = [r0, R * Math.sqrt(inner * inner + (1 - inner * inner) * (cum / N))];
  }
  geo[c] = { band, sector: {} };
  // sectors: as wide as their acts, in SR order, a small gap between them
  const secs = [...new Set(rest.map(([i]) => sectorOf(i)))].sort((a, b) => a - b);
  const sc = Object.fromEntries(secs.map((x) => [x, rest.filter(([i]) => sectorOf(i) === x).length]));
  const sgap = secs.length > 1 ? 0.025 : 0, span = 2 * Math.PI - sgap * secs.length;
  const sector = {};
  let a0 = -Math.PI / 2;
  for (const x of secs) { const w = (span * sc[x]) / N; sector[x] = [a0, a0 + w]; a0 += w + sgap; }
  if (secs.length > 1) geo[c].sector = sector;
  for (const l of levels) for (const x of secs) {
    const cell = rest.filter(([i]) => levelOf(i) === l && sectorOf(i) === x);
    if (!cell.length) continue;
    const [r0, r1] = band[l], [s0, s1] = sector[x];
    const base = secs.length > 1 ? (sector[x][0] + Math.PI / 2) : 0;          // the FA2 angle, read from the sector's start
    cell.sort((p, q) => ((p[1] - base + 6 * Math.PI) % (2 * Math.PI)) - ((q[1] - base + 6 * Math.PI) % (2 * Math.PI)));
    const pts = cell.map((_, j) => {
      const u = halton(j + 1, 2), v = halton(j + 1, 3);
      return [Math.sqrt(r0 * r0 + u * (r1 * r1 - r0 * r0)), s0 + v * (s1 - s0)];
    }).sort((p, q) => p[1] - q[1]);
    cell.forEach(([i], j) => { const [rr, aa] = pts[j]; local.set(i, [rr * Math.cos(aa), rr * Math.sin(aa)]); });
  }
}

// ---- 2. the clusters in place
// the order of Art. 1 BV, clockwise from the top, as everywhere on the site
const ART1 = ["ZH", "BE", "LU", "UR", "SZ", "OW", "NW", "GL", "ZG", "FR", "SO", "BS", "BL", "SH", "AR", "AI", "SG", "GR", "AG", "TG", "TI", "VD", "VS", "NE", "GE", "JU"];
const cts = ART1.filter((c) => members.has("ct:" + c));
const GAP = 1.18;
const need = cts.reduce((s, c) => s + 2 * radius["ct:" + c] * GAP, 0);
const rF = radius.fed, rI = radius.int || 0;
const R = Math.max(need / (2 * Math.PI), rF + 2 * rI + Math.max(...cts.map((c) => radius["ct:" + c])) + 120);
const centres = { fed: [0, 0] };
if (rI) centres.int = [0, -(rF + rI + 60)];
let ang = -(radius["ct:" + cts[0]] * GAP) / R;
for (const c of cts) {
  const w = (2 * radius["ct:" + c] * GAP) / R, mid = ang + w / 2;
  centres["ct:" + c] = [R * Math.sin(mid), -R * Math.cos(mid)];
  ang += w;
}
// turn each canton so that its acts linked to federal law face the centre
const fedSide = new Map();
for (const [k] of W) {
  const [a, b] = k.split("|").map(Number);
  for (const [p, q] of [[a, b], [b, a]]) if (clusterOf(p).startsWith("ct:") && clusterOf(q) === "fed") {
    const c = clusterOf(p), [x, y] = local.get(p), s = fedSide.get(c) || [0, 0];
    fedSide.set(c, [s[0] + x, s[1] + y]);
  }
}
const pos = new Map(), rotOf = {};
for (const [c, list] of members) {
  const [cx, cy] = centres[c];
  let rot = 0;
  if (fedSide.has(c)) {
    const [sx, sy] = fedSide.get(c), want = Math.atan2(-cy, -cx), have = Math.atan2(sy, sx);
    rot = want - have;
  }
  rotOf[c] = rot;
  const cs = Math.cos(rot), sn = Math.sin(rot);
  for (const i of list) { const [x, y] = local.get(i); pos.set(i, [cx + x * cs - y * sn, cy + x * sn + y * cs]); }
}
// ---- out: ±1000 across, integers at a tenth
let ext = 0;
for (const [x, y] of pos.values()) ext = Math.max(ext, Math.abs(x), Math.abs(y));
const k = 1000 / ext, q = (v) => Math.round(v * k * 10);
const xy = [];
for (const i of ids) { const [x, y] = pos.get(i); xy.push(q(x), q(y)); }
const clusters = {};
const r4 = (v) => Math.round(v * 1e4) / 1e4;
for (const [c, list] of members) {
  const G = geo[c];
  clusters[c] = { c: [q(centres[c][0]), q(centres[c][1])], r: q(radius[c]), n: list.length,
    bands: Object.fromEntries(Object.entries(G.band).map(([l, [a, b]]) => [l, [q(a), q(b)]])),
    sectors: Object.fromEntries(Object.entries(G.sector).map(([x, [a, b]]) => [x, [r4(a + rotOf[c]), r4(b + rotOf[c])]])) };
}
const unlinked = rows.filter((r, i) => r[0] === "a" && !linked.has(i)).length;
fs.writeFileSync(ROOT + "docs/data/net.json", JSON.stringify({ ids, xy, clusters, scale: 10, unlinked }));
console.log(`net.json ${(fs.statSync(ROOT + "docs/data/net.json").size / 1e6).toFixed(2)} MB; ${ids.length} acts, ${unlinked} acts in force without a link; ring ${R.toFixed(0)}`);
