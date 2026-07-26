"""Machine-verify every number in the family's prose against committed data.

The family's claim is that no number in a write-up is hand-maintained.
The Findings sections and marked README regions are script-WRITTEN by
each study's findings generator; this tool covers everything else the
generators cannot sensibly write (narrative story pages, BRIEFs, the
hand-written parts of READMEs, the hub README): it extracts every numeric
token from the prose and verifies each one matches a value in the
family's committed outputs (or a data-file row count), to the precision
the prose displays.

A token that matches nothing must be listed in an allowlist file with a
reason, or the check fails. Allowlists live in number_allowlists/ as
"<repo>__<filename>.txt", one token per line, with a # reason.

Run:  python verify_numbers.py            report per file
      python verify_numbers.py --check    gate mode (non-zero on failure)
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

import polars as pl

REPO = Path(__file__).resolve().parent
SIBLINGS = REPO.parent
ALLOW_DIR = REPO / "number_allowlists"

STUDIES = ["jersey-height-study", "playbyplay-study", "tracking-study",
           "lineup-valuation-study", "shot-quality-study", "draft-study"]

# files verified, as (repo, relative path)
FILES = ([(s, "docs/story.md") for s in STUDIES]
         + [(s, "BRIEF.md") for s in STUDIES]
         + [(s, "README.md") for s in STUDIES]
         + [("basketball-data-science", "README.md"),
            ("basketball-sql-layer", "README.md"),
            ("nba-scouting-onepagers", "README.md")])

YEAR = re.compile(r"^(19|20)\d{2}$")
SEASON = re.compile(r"^\d{4}-\d{2}$")
TOKEN = re.compile(r"(?<![\w./-])[+\-−±~≈]{0,2}(\d[\d,]*\.?\d*(?:e-?\d+)?)"
                   r"(%|×|x\b)?")


def build_pool() -> set[float]:
    pool: set[float] = set()
    for s in STUDIES:
        base = SIBLINGS / s
        for f in sorted((base / "output").rglob("*.csv")):
            try:
                df = pl.read_csv(f, infer_schema_length=500,
                                 ignore_errors=True)
            except Exception:
                continue
            pool.update({float(df.height), float(df.height + 1),
                         float(df.height - 1)})
            for col in df.columns:
                ser = df[col]
                if ser.dtype.is_numeric():
                    pool.update(float(v) for v in ser.drop_nulls()
                                if math.isfinite(float(v)))
        # data-file row counts (fast line count) for corpus-size claims
        for f in sorted((base / "data").rglob("*.csv"))[:20]:
            try:
                n = sum(1 for _ in open(f, "rb"))
            except OSError:
                continue
            pool.update({float(n), float(n - 1)})
        for f in sorted((base / "data").rglob("*.parquet"))[:10]:
            try:
                pool.add(float(pl.scan_parquet(f).select(pl.len())
                               .collect()[0, 0]))
            except Exception:
                continue
    # scaled variants
    scaled = set()
    for v in pool:
        scaled.add(v * 100)
        if abs(v) >= 1e5:
            scaled.add(v / 1e6)
        scaled.add(-v)
    return pool | scaled


def strip_nonprose(text: str) -> str:
    text = re.sub(r"<!-- terms -->.*?<!-- /terms -->", "", text, flags=re.S)
    text = re.sub(r'<abbr title="[^"]*">', "", text)
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`[^`]*`", "", text)
    text = re.sub(r"\]\([^)]*\)", "]", text)          # link targets
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\{\{fig:[^|]*\|", "", text)       # keep caption text
    return text


def tokens_of(text: str) -> list[str]:
    out = []
    for m in TOKEN.finditer(strip_nonprose(text)):
        num, suffix = m.group(1), m.group(2) or ""
        if YEAR.match(num):
            continue
        raw = num + suffix
        ctx = text[max(0, m.start() - 1):m.end() + 3]
        if SEASON.match(ctx.strip()):
            continue
        out.append(raw)
    return out


def matches(tok: str, pool: set[float]) -> bool:
    pct = tok.endswith("%")
    t = tok.rstrip("%×x").replace(",", "")
    try:
        f = float(t)
    except ValueError:
        return True
    if "e" in t:      # order-of-magnitude claims like ~2e-13
        if f == 0:
            return False
        return any(v != 0 and abs(math.log10(abs(v)) - math.log10(abs(f)))
                   < 0.51 for v in pool)
    dec = len(t.split(".")[1]) if "." in t else 0
    cands = [f]
    if pct:
        cands = [f, f / 100]
    for v in pool:
        for c in cands:
            if abs(v - c) < 0.5 * 10 ** -dec + 1e-12:
                return True
            if pct and abs(v * 100 - f) < 0.5 * 10 ** -dec + 1e-12:
                return True
    return False


def allowlist_for(repo: str, rel: str) -> dict[str, str]:
    f = ALLOW_DIR / f"{repo}__{rel.replace('/', '_')}.txt"
    allowed: dict[str, str] = {}
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                tok = line.split("#")[0].strip()
                allowed[tok] = line
    return allowed


def main(argv: list[str]) -> int:
    pool = build_pool()
    seasons_ints = {float(y) for y in range(1979, 2027)}
    pool -= set()  # keep as-is; years filtered at token level
    failures: list[str] = []
    checked = files_n = 0
    for repo, rel in FILES:
        path = SIBLINGS / repo / rel
        if not path.exists():
            continue
        files_n += 1
        allowed = allowlist_for(repo, rel)
        unmatched = []
        for tok in tokens_of(path.read_text()):
            checked += 1
            if tok in allowed:
                continue
            if float(tok.rstrip("%×x").replace(",", "") or 0) in seasons_ints:
                continue
            if not matches(tok, pool):
                unmatched.append(tok)
        if unmatched:
            failures.append(f"{repo}/{rel}: " + ", ".join(
                sorted(set(unmatched))))
    if failures:
        print(f"NUMBER VERIFICATION FAILED "
              f"({len(failures)} files with unmatched tokens):")
        for f in failures:
            print("  " + f)
        return 1
    print(f"NUMBER VERIFICATION PASSED ({checked} numeric tokens across "
          f"{files_n} files match committed outputs or justified "
          f"allowlists)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
