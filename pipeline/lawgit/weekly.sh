#!/usr/bin/env bash
# The twice-weekly run of the law repository (decision 39), from the root of swiss-law-graph:
#
#   pipeline/lawgit/weekly.sh <checkout of jonashertner/swisslaw-git on main>
#
# 1. fetch: every fetcher re-reads what changes (lists, headers, texts in force: refresh.py) and keeps what does not
#    (the document of a version); 2. convert what is new; 3. build_repo.py --append: late versions, the window, README,
#    future rebuilt, checked against a replay of every known version. A source that fails is reported and its acts stay
#    as they are. DEADLINE (minutes, default 300): a cold start (empty caches, ~4–5 h) stops fetching in time so the
#    workflow can still save the caches; the next run goes on from there and appends once everything is in.
# Exit: 0 appended; 1 the append stopped (a guard or the replay check: see its message); 3 fetching not finished.
set -uo pipefail
REPO=$(cd "$1" && pwd)
cd "$(dirname "$0")/../.."
export SWISSLAW_REFRESH=${SWISSLAW_REFRESH:-$(date +%s)} PYTHONUNBUFFERED=1
T0=$(date +%s)
DEADLINE=$(( ${DEADLINE:-300} * 60 ))
failed=()

step() {                    # step <name> <command …>: time-boxed to what is left of the deadline
  local name=$1 left=$(( DEADLINE - ($(date +%s) - T0) )) t=$(date +%s) rc
  shift
  if (( left < 120 )); then echo "::warning::$name: skipped, deadline reached"; failed+=("$name (deadline)"); return 1; fi
  echo "::group::$name"
  timeout --kill-after=60 "$left" "$@"; rc=$?
  echo "::endgroup::"
  if (( rc == 0 )); then echo "$name: ok, $(( $(date +%s) - t ))s"
  elif (( rc == 124 || rc == 137 )); then echo "::warning::$name: stopped at the deadline"; failed+=("$name (deadline)")
  else echo "::warning::$name failed (exit $rc) after $(( $(date +%s) - t ))s"; failed+=("$name"); fi
  return $rc
}

# 1. sources (each independent: one failing leaves the others)
step "Fedlex: history"              python3 pipeline/fetch_fedlex_history.py
step "Fedlex: versions"             python3 pipeline/lawgit/fedlex_versions.py
step "Fedlex: XML of new versions"  python3 pipeline/lawgit/fedlex_fetch.py
step "Fedlex: AS, BBl, consultations" python3 pipeline/lawgit/fedlex_pending.py
step "LexWork: 19 cantons"          python3 pipeline/lawgit/lexwork_fetch.py
step "Vaud"                         python3 pipeline/lawgit/vd_fetch.py
step "Zürich: list"                 python3 pipeline/cantonal/zh.py && \
step "Zürich: versions"             python3 pipeline/lawgit/zh_fetch.py
step "Geneva"                       python3 pipeline/cantonal/ge.py
step "Neuchâtel"                    python3 pipeline/cantonal/ne.py
step "Jura"                         python3 pipeline/cantonal/ju.py
# 2. convert what is new (LexWork versions without structured text: their PDFs, then convert again)
step "convert"                      python3 pipeline/lawgit/convert.py ch kt vd sil pend pdfcur zh
step "LexWork: PDFs"                python3 pipeline/lawgit/lexwork_pdf_fetch.py && \
step "convert: LexWork PDFs"        python3 pipeline/lawgit/convert.py kt

for f in "${failed[@]}"; do
  case $f in *deadline*) echo "::warning::fetching not finished within ${DEADLINE}s; caches saved, the next run goes on"; exit 3;; esac
done
(( ${#failed[@]} )) && echo "::warning::failed: ${failed[*]} — their acts stay as main shows them"

# 3. append
python3 pipeline/lawgit/build_repo.py --append "$REPO" || exit 1
echo "done in $(( ($(date +%s) - T0) / 60 )) min$( (( ${#failed[@]} )) && echo "; failed: ${failed[*]}")"
