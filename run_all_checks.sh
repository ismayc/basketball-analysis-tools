#!/bin/bash
# Every gate in the family, across all sibling repos: each repo's own
# checks, then the cross-repo layers (SQL reconciliation, scouting
# staleness, glossary staleness, cross-study identity tests).
# Requires sibling checkouts (clone_family.sh). Exits non-zero on the
# first failure.
set -euo pipefail
cd "$(dirname "$0")"
export PY=${PY:-$(pwd)/.venv/bin/python}

for r in jersey-height-study playbyplay-study tracking-study \
         lineup-valuation-study shot-quality-study draft-study \
         basketball-sql-layer; do
  echo "=================== $r"
  (cd "../$r" && ./run_checks.sh)
  echo
done

echo "=================== nba-scouting-onepagers"
$PY ../nba-scouting-onepagers/build_onepager.py --check | tail -1
echo

echo "=================== basketball-analysis-tools"
echo "=== glossary: terms blocks and hover annotations current ==="
$PY glossary.py --check | tail -1
echo
echo "=== numbers: every prose number verified against committed outputs ==="
$PY verify_numbers.py --check | tail -1
echo
echo "=== cross-study identity tests (pytest) ==="
$PY -m pytest tests/python -q
echo
echo "=== cross-study identity tests (testthat) ==="
Rscript tests/R/run_tests.R

echo
echo "ALL FAMILY CHECKS PASS"
