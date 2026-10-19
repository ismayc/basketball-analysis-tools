#!/bin/bash
# Every gate in the family, across all sibling repos: each repo's own
# checks, then the cross-repo layers (SQL reconciliation, scouting
# staleness, glossary staleness, cross-study identity tests).
# Requires sibling checkouts (clone_family.sh). Exits non-zero on the
# first failure.
set -euo pipefail
cd "$(dirname "$0")"
# The shared venv lives in the parent folder that holds the siblings.
export PY=${PY:-$(cd .. && pwd)/.venv/bin/python}
if [ ! -x "$PY" ]; then
  echo "no Python at $PY; create the shared venv (see README) or set PY" >&2
  exit 1
fi

for r in jersey-height-study playbyplay-study tracking-study \
         lineup-valuation-study shot-quality-study draft-study \
         contract-year-study playoff-series-study \
         basketball-sql-layer; do
  echo "=================== $r"
  (cd "../$r" && ./run_checks.sh)
  echo
done

echo "=================== nba-scouting-onepagers"
$PY ../nba-scouting-onepagers/build_onepager.py --check | tail -1
echo

echo "=================== basketball-analysis-tools"
echo "=== family brand: every published page has the family favicon + og ==="
# Full output, not tail -1: the exempt repos' SKIP lines must show.
$PY check_family_brand.py
echo
echo "=== glossary: terms blocks and hover annotations current ==="
$PY glossary.py --check | tail -1
echo
echo "=== numbers: every prose number bound to one committed output cell ==="
$PY verify_numbers.py --check | tail -1
echo
echo "=== cross-study identity tests (pytest) ==="
$PY -m pytest tests/python -q
echo
echo "=== cross-study identity tests (testthat) ==="
Rscript tests/R/run_tests.R

echo
echo "ALL FAMILY CHECKS PASS"
