#!/bin/bash
# Check out the whole basketball-data-science family as sibling repos.
# Run from the directory that should hold them (this repo's parent works):
#   bash basketball-analysis-tools/clone_family.sh
set -euo pipefail
cd "$(dirname "$0")/.."
for r in basketball-data-science jersey-height-study playbyplay-study \
         tracking-study lineup-valuation-study shot-quality-study \
         draft-study basketball-sql-layer nba-scouting-onepagers; do
  [ -d "$r" ] || git clone "https://github.com/ismayc/$r"
done
