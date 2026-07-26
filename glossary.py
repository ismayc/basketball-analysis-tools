"""Single source of truth for the portfolio's terms of art.

Every analysis document gets (1) a Terms block at the top defining every
glossary term the document actually uses, and (2) hover tooltips at each
point of use. The terms are wrapped in <abbr title="..."> tags, which
GitHub renders as a dotted underline with the definition on hover. The
scouting one-pagers reuse the same definitions through their own renderer.

The block and the annotations are maintained by this tool, never by hand:

    python tools/glossary.py --sync     rewrite Terms blocks + annotations
                                        in every registered doc, and
                                        regenerate docs/glossary.md
    python tools/glossary.py --check    fail if any committed doc differs
                                        from what --sync would write
                                        (wired into the family check runner)

Detection is automatic: a doc's Terms block lists exactly the glossary
terms whose aliases appear in its prose (code spans, fenced blocks, and
headings are ignored). Re-running the findings generators strips a README
body back to plain text, so run --sync afterwards; --check exists so
forgetting cannot survive the gates.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
SIBLINGS = REPO.parent          # the family's repos, checked out next door
GLOSSARY_MD = SIBLINGS / "basketball-data-science" / "docs" / "glossary.md"
HUB_GLOSSARY_URL = ("https://github.com/ismayc/basketball-data-science/"
                    "blob/main/docs/glossary.md")
OPEN, CLOSE = "<!-- terms -->", "<!-- /terms -->"

# term -> (definition, [aliases matched case-sensitively, longest wins]).
# Definitions go inside title="..." attributes: no double quotes, no < > &.
TERMS: dict[str, tuple[str, list[str]]] = {
    "PPS": (
        "Points per shot: total points on field-goal attempts divided by "
        "attempts. Free throws excluded.",
        ["PPS"]),
    "xPPS": (
        "Expected points per shot - the model's fair price of a shot diet: "
        "what an average shooter would score on the same attempts, judged "
        "from location and shot type alone, before knowing what went in.",
        ["xPPS"]),
    "xPTS": (
        "Expected points: the modeled make probability times the shot's "
        "point value, summed over attempts.",
        ["xPTS", "xPts"]),
    "xMake": (
        "The model's probability that a given shot goes in, estimated from "
        "location and shot type; the per-shot building block behind xPPS "
        "and xPTS.",
        ["xMake"]),
    "shot-making": (
        "Actual minus expected points per 100 shots: conversion above or "
        "below what the shot diet itself explains. Positive means making "
        "shots the model prices as hard.",
        ["making/100", "making_100", "Making /100", "Making/100",
         "shot-making", "Shot-making", "shot making", "shot-maker"]),
    "EB making": (
        "A player's shot-making after empirical-Bayes shrinkage: the "
        "observed number pulled toward the league mean in proportion to "
        "its sampling noise. The number to trust for projection.",
        ["EB making"]),
    "FGA": (
        "Field-goal attempts.",
        ["FGA"]),
    "eFG%": (
        "Effective field-goal percentage: field-goal percentage with made "
        "threes counted 1.5x, putting twos and threes on one points scale.",
        ["eFG%", "eFG"]),
    "RAPM": (
        "Regularized adjusted plus-minus: a ridge regression crediting "
        "each player with net points per 100 possessions while adjusting "
        "for the other nine players on the floor.",
        ["RAPM"]),
    "stint": (
        "A stretch of game time with no substitution at either end - the "
        "unit of observation for the stint-level RAPM model.",
        ["stint", "stints"]),
    "net_100": (
        "Net points per 100 possessions: 100 x plus-minus / possessions; "
        "sits on the same scale as the NBA's published net rating.",
        ["net_100", "Net/100", "net/100", "net rating", "NET_RATING"]),
    "POSS": (
        "Possession count in NBA lineup data - specifically offensive "
        "possessions for the lineup in question.",
        ["POSS"]),
    "plus-minus": (
        "Points scored minus points allowed while a player or lineup is "
        "on the floor.",
        ["plus-minus"]),
    "2-for-1": (
        "Shooting early with 25-36 seconds left in a period so your team "
        "gets two possessions to the opponent's one before the buzzer.",
        ["2-for-1s", "2-for-1", "two-for-one"]),
    "rush": (
        "Shots in the final four seconds of a period - the desperation "
        "window where both shot selection and execution collapse.",
        ["(rush)"]),
    "decile calibration": (
        "Split shots into ten bins by predicted make probability and "
        "compare predicted vs actual rates per bin; the reported number "
        "is the worst bin's gap.",
        ["decile calibration", "decile"]),
    "IRLS": (
        "Iteratively reweighted least squares - the standard algorithm "
        "for fitting a logistic regression.",
        ["IRLS"]),
    "ridge": (
        "Ridge regression: least squares with an L2 penalty that keeps "
        "many-parameter models stable at the cost of a little bias.",
        ["ridge"]),
    "empirical Bayes": (
        "Estimate the spread of true skill across the league from the "
        "data, then pull each individual's noisy estimate toward the "
        "league mean in proportion to its noise.",
        ["empirical-Bayes", "empirical Bayes", "Empirical-Bayes",
         "Empirical Bayes", "EB"]),
    "shrinkage weight": (
        "The fraction of an observed number that survives empirical-Bayes "
        "regression: 1 means fully trusted, 0 means replaced by the "
        "league mean.",
        ["shrinkage weight", "shrinkage weights", "shrinkage"]),
    "tau": (
        "The estimated spread of true, noise-free skill across players "
        "(per 100 shots here); the knob that sets how hard empirical "
        "Bayes shrinks.",
        ["tau"]),
    "MAE": (
        "Mean absolute error.",
        ["MAE"]),
    "RMSE": (
        "Root mean squared error.",
        ["RMSE"]),
    "AUC": (
        "Area under the ROC curve: the probability the model ranks a "
        "random positive case above a random negative one. 0.5 is a coin "
        "flip.",
        ["AUC"]),
    "log loss": (
        "Negative average log-likelihood of the outcomes under the "
        "predicted probabilities; punishes confident wrong predictions.",
        ["log loss", "logloss"]),
    "CI": (
        "Confidence interval.",
        ["CI"]),
    "Spearman": (
        "Rank correlation: correlation of the orderings rather than the "
        "raw values.",
        ["Spearman"]),
    "corner three": (
        "A three-pointer from the corner, where the NBA line is roughly "
        "3 ft closer than the arc - the geometry discount that makes it "
        "the cheapest three.",
        ["corner threes", "corner three", "corner-three", "corner 3"]),
    "SportVU": (
        "The NBA's 2013-16 optical tracking system: x,y for all ten "
        "players (plus z for the ball) at 25 frames per second.",
        ["SportVU"]),
    "window function": (
        "SQL construct computing a value over a set of rows related to "
        "the current row (a rank, running total, or centered average) "
        "without collapsing them.",
        ["window-function", "window functions", "window function"]),
    "DuckDB": (
        "An in-process analytical SQL engine that queries CSV and parquet "
        "files directly, with no server or load step.",
        ["DuckDB"]),
    "HCA": (
        "Home-court advantage, expressed here as net points per 100 "
        "possessions.",
        ["HCA"]),
}

# Documents maintained by --sync: sibling-relative path -> the link each
# doc's Terms block uses for the full glossary (the hub links locally; the
# standalone repos link to the hub on GitHub).
DOCS: dict[str, str] = {
    "basketball-data-science/README.md": "docs/glossary.md",
    "jersey-height-study/README.md": HUB_GLOSSARY_URL,
    "playbyplay-study/README.md": HUB_GLOSSARY_URL,
    "tracking-study/README.md": HUB_GLOSSARY_URL,
    "lineup-valuation-study/README.md": HUB_GLOSSARY_URL,
    "shot-quality-study/README.md": HUB_GLOSSARY_URL,
    "draft-study/README.md": HUB_GLOSSARY_URL,
    "basketball-sql-layer/README.md": HUB_GLOSSARY_URL,
    "nba-scouting-onepagers/README.md": HUB_GLOSSARY_URL,
}

_ALIAS_TO_TERM = {a: t for t, (_, aliases) in TERMS.items() for a in aliases}
_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])("
    + "|".join(re.escape(a) for a in
               sorted(_ALIAS_TO_TERM, key=len, reverse=True))
    + r")(?![A-Za-z0-9_])")
_ABBR = re.compile(r'<abbr title="[^"]*">([^<]*)</abbr>')
_CODE_SPAN = re.compile(r"(`+[^`]*`+)")


def strip_abbr(text: str) -> str:
    return _ABBR.sub(r"\1", text)


def _wrap(match: re.Match) -> str:
    alias = match.group(1)
    definition = TERMS[_ALIAS_TO_TERM[alias]][0]
    return f'<abbr title="{definition}">{alias}</abbr>'


def annotate(text: str) -> str:
    """Wrap term occurrences in <abbr> hover tips. Skips fenced code
    blocks, inline code spans, headings, and table separator rows; the
    input must already be abbr-free (see strip_abbr)."""
    out, in_fence = [], False
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            out.append(line)
        elif in_fence or stripped.startswith("#"):
            out.append(line)
        else:
            parts = _CODE_SPAN.split(line)
            out.append("".join(
                p if i % 2 else _PATTERN.sub(_wrap, p)
                for i, p in enumerate(parts)))
    return "".join(out)


def wrap_terms(text: str) -> str:
    """Wrap every term alias in a plain fragment (no code/heading
    protection), for renderers that manage their own protected zones."""
    return _PATTERN.sub(_wrap, text)


def terms_for(text: str) -> list[str]:
    """Glossary terms whose aliases appear in the prose (code and
    headings excluded), in glossary order."""
    prose, in_fence = [], False
    for line in strip_abbr(text).splitlines():
        s = line.lstrip()
        if s.startswith("```"):
            in_fence = not in_fence
        elif not in_fence and not s.startswith("#"):
            prose.append("".join(p for i, p in
                                 enumerate(_CODE_SPAN.split(line))
                                 if i % 2 == 0))
    found = {_ALIAS_TO_TERM[m.group(1)]
             for m in _PATTERN.finditer("\n".join(prose))}
    return [t for t in TERMS if t in found]


def terms_block(keys: list[str], glossary_rel: str) -> str:
    if not keys:
        items = "> *(no specialized metric terms in this document)*"
    else:
        items = "\n".join(f"> - **{k}**: {TERMS[k][0]}" for k in keys)
    return (f"{OPEN}\n"
            "> **Terms used in this analysis.** Dotted-underlined terms "
            "anywhere below repeat these definitions on hover "
            f"([full glossary]({glossary_rel})).\n>\n{items}\n{CLOSE}\n")


def sync_text(text: str, glossary_rel: str) -> str:
    """The canonical form of a registered document: clean prose, a fresh
    Terms block, hover annotations everywhere else. Idempotent."""
    plain = strip_abbr(text)
    if OPEN in plain:
        head, rest = plain.split(OPEN, 1)
        old_block, tail = rest.split(CLOSE, 1)
        tail = tail.lstrip("\n")
    else:                       # first run: insert before the first section
        cut = plain.find("\n## ")
        cut = len(plain) if cut == -1 else cut + 1
        head, tail = plain[:cut], plain[cut:]
        if not head.endswith("\n\n"):
            head = head.rstrip("\n") + "\n\n"
    keys = terms_for(head + tail)
    return (annotate(head) + terms_block(keys, glossary_rel) + "\n"
            + annotate(tail))


def full_glossary() -> str:
    rows = "\n".join(f"| **{k}** | {d} |" for k, (d, _) in TERMS.items())
    return f"""# Glossary

Every term of art used across the portfolio's analyses, defined once.
Maintained by `tools/glossary.py`, which also stamps a per-document Terms
block at the top of each analysis and wraps each use in a hover tooltip
(`--sync` to update, `--check` gates staleness in the family runner).

| Term | Definition |
|---|---|
{rows}
"""


def main(argv: list[str]) -> int:
    check = "--check" in argv
    stale = []
    for rel, glossary_rel in DOCS.items():
        path = SIBLINGS / rel
        current = path.read_text()
        wanted = sync_text(current, glossary_rel)
        if current != wanted:
            stale.append(rel)
            if not check:
                path.write_text(wanted)
    wanted_glossary = full_glossary()
    glossary_current = (GLOSSARY_MD.read_text()
                        if GLOSSARY_MD.exists() else "")
    if glossary_current != wanted_glossary:
        stale.append("docs/glossary.md")
        if not check:
            GLOSSARY_MD.write_text(wanted_glossary)

    if check:
        if stale:
            print(f"GLOSSARY CHECK FAILED: stale terms/annotations in "
                  f"{', '.join(stale)}. Fix: python tools/glossary.py "
                  "--sync")
            return 1
        print("GLOSSARY CHECK PASSED (terms blocks and hover annotations "
              "current in all registered docs)")
        return 0
    print(f"synced {len(stale)} of {len(DOCS) + 1} docs"
          if stale else "all docs already in sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
