#!/usr/bin/env bash
# The weekly refresh of the atlas (decision 39), from the root of swiss-law-graph:
#
#   pipeline/atlas.sh fedlex     Fedlex (history, SR numbers, acts, articles, structure, Ingresses, cross-references)
#                                and the OpenCaseLaw snapshot                                        ~1.5–2 h
#   pipeline/atlas.sh cantons    the 26 cantonal collections (pipeline/cantonal/*.py)                ~1.5 h
#   pipeline/atlas.sh build      cantonal_basis, steps 01–08, the layouts, the dates; then the guard  ~40 min
#   pipeline/atlas.sh all        the three in turn
#
# Every fetcher re-reads what changes (refresh.py); a source that fails keeps the copy in data/ (the one committed, or
# the last run's) and the run says so. The run date is SWISSLAW_RUN_DATE (default: today in Zürich): the day the
# sources were read, shown on the site. The guard stops a build whose counts fell by more than 3 % against the live
# site (a source answered partly): nothing is deployed then. Exit: 0 built; 1 a build step or the guard failed.
set -uo pipefail
cd "$(dirname "$0")/.."
export SWISSLAW_REFRESH=${SWISSLAW_REFRESH:-$(date +%s)} PYTHONUNBUFFERED=1
export SWISSLAW_RUN_DATE=${SWISSLAW_RUN_DATE:-$(TZ=Europe/Zurich date +%F)}
export OPENCASELAW=${OPENCASELAW:-../jonashertner/opencaselaw}   # the alias tables (law_codes.json, law_aliases.json): 01, 05
OCL=$OPENCASELAW
SITE=${SITE_URL:-https://jonashertner.github.io/swiss-law-graph/}
failed=()

step() {
  local name=$1 t=$(date +%s) rc
  shift
  echo "::group::$name"
  "$@"; rc=$?
  echo "::endgroup::"
  if (( rc == 0 )); then echo "$name: ok, $(( $(date +%s) - t ))s"
  else echo "::warning::$name failed (exit $rc) after $(( $(date +%s) - t ))s"; failed+=("$name"); fi
  return $rc
}

cited() {                   # the SR numbers courts cite (step 1's act nodes) join the list the Fedlex fetchers read
  python3 - <<'EOF'
import json
from pathlib import Path
p = Path("pipeline/acts_to_validate.txt")
old = {l.strip() for l in open(p) if l.strip()}
new = {v["sr"] for v in json.load(open("build/act_nodes.json")).values()}
key = lambda s: [int(x) if x.isdigit() else x for x in s.replace(".", " . ").split()]
p.write_text("\n".join(sorted(old | new, key=key)) + "\n")
print(f"cited acts: {len(old | new)} ({len(new - old)} new)")
EOF
}

fedlex() {
  step "OpenCaseLaw snapshot"              python3 pipeline/fetch_opencaselaw.py
  [ -d "$OCL/.git" ] || step "OpenCaseLaw alias tables" git clone -q --depth 1 https://github.com/jonashertner/opencaselaw "$OCL"
  step "Fedlex: history"                   python3 pipeline/fetch_fedlex_history.py
  step "Fedlex: SR numbers and tree"       python3 pipeline/fetch_fedlex_srs.py
  step "step 1 (which acts courts cite)"   python3 pipeline/01_resolve.py "$OCL" && cited
  step "Fedlex: acts"                      python3 pipeline/fetch_fedlex_acts.py
  step "Fedlex: articles"                  python3 pipeline/fetch_fedlex_articles.py
  step "Fedlex: structure"                 python3 pipeline/fetch_fedlex_structure.py
  step "step 1 (regimes of the acts)"      python3 pipeline/01_resolve.py "$OCL"
  step "Fedlex: earlier acts' articles"    python3 pipeline/fetch_fedlex_regimes.py
  step "Fedlex: Ingresses"                 python3 pipeline/fetch_fedlex_basis.py
  step "Fedlex: cross-references"          python3 pipeline/fetch_fedlex_xrefs.py
}

cantons() {
  for ct in lexwork zh vd ge ne ju ti sz; do
    step "cantons: $ct"                    python3 "pipeline/cantonal/$ct.py"
  done
}

build() {                   # stops at the first step that fails: nothing after it could be right
  [ -d "$OCL/.git" ] || git clone -q --depth 1 https://github.com/jonashertner/opencaselaw "$OCL"
  for s in "cantonal_basis.py" "01_resolve.py $OCL" "02_validate.py" "03_graph.py" "04_hierarchy.py"; do
    step "build: ${s%% *}" python3 pipeline/$s || return 1
  done
  step "build: layout"   bash -c "cd layout && npm ci --silent && node pack.mjs" || return 1
  for s in 05_site.py 07_tree.py 08_web.py; do step "build: $s" python3 pipeline/$s || return 1; done
  step "Fedlex: dates (time view)" python3 pipeline/fetch_fedlex_dates.py || return 1
  step "build: 08_web.py (dates)" python3 pipeline/08_web.py || return 1
  step "build: network layout" node layout/net.mjs || return 1
  guard
}

guard() {                   # the counts of this build against the site that is live
  python3 - "$SITE" <<'EOF'
import json, sys, urllib.request
site = sys.argv[1]
new = json.load(open("docs/data/atlas.json"))["meta"]
try:
    with urllib.request.urlopen(site + "data/atlas.json", timeout=120) as r:
        old = json.load(r)["meta"]
except Exception as e:                                   # noqa: BLE001 — no live site to compare with: say so, go on
    print(f"::warning::no live atlas to compare with ({e})"); sys.exit(0)
rows, bad = [], []
for k in ("fed_in_force", "int_in_force", "kt_in_force", "history"):
    a, b = old["counts"].get(k, 0), new["counts"].get(k, 0)
    rows.append(f"{k} {a:,} → {b:,}")
    if b < 0.97 * a:
        bad.append(k)
a, b = old.get("decisions", 0), new.get("decisions", 0)
rows.append(f"decisions {a:,} → {b:,}")
if b < 0.97 * a:
    bad.append("decisions")
print(f"run {old.get('run')} → {new.get('run')}: " + "; ".join(rows))
if bad:
    print(f"::error::fell by more than 3 % against the live site: {', '.join(bad)} — not deployed"); sys.exit(1)
EOF
}

case ${1:-all} in
  fedlex)  fedlex ;;
  cantons) cantons ;;
  build)   build || exit 1 ;;
  all)     fedlex; cantons; build || exit 1 ;;
  *)       echo "usage: $0 fedlex|cantons|build|all"; exit 2 ;;
esac
(( ${#failed[@]} )) && echo "::warning::failed: ${failed[*]} — their copies in data/ were used"
exit 0
