// Step 3b — circle packing of build/hierarchy.json with d3-hierarchy (reference implementation).
// Leaf radius = sqrt(value); siblings keep the tree's order (SR order), so the first
// children sit at the centre and the rest spiral outward. Padding scales with each
// parent (PAD x sqrt of its value) so tiny acts are not swamped by fixed gaps.
// Output: build/layout.json {id: [x, y, r, depth]} with the root circle of radius 1000.
import { readFileSync, writeFileSync } from "node:fs";
import { hierarchy, pack } from "d3-hierarchy";

const BUILD = new URL("../build/", import.meta.url);
const PAD = 0.035;
const tree = JSON.parse(readFileSync(new URL("hierarchy.json", BUILD)));
const root = hierarchy(tree).sum((d) => (d.children ? 0 : d.value));
pack().radius((d) => Math.sqrt(d.value)).padding((d) => PAD * Math.sqrt(d.value))(root);
const k = 1000 / root.r;
const out = {};
root.each((d) => {
  out[d.data.id] = [+((d.x - root.x) * k).toFixed(6), +((d.y - root.y) * k).toFixed(6), +(d.r * k).toPrecision(7), d.depth];
});
writeFileSync(new URL("layout.json", BUILD), JSON.stringify(out));
console.log(`${Object.keys(out).length} circles, root r=${root.r.toFixed(1)}`);
