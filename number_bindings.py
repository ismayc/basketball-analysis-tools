"""Per-number bindings: each number in a write-up tied to one committed cell.

verify_numbers.py's pool matching accepts a number if any value nearby
exists, which for tables of thousands of values is most numbers. A binding
names the one cell a number came from, and the check re-formats that cell
at the number's displayed precision and requires an exact match, sign
included. A document with a bindings file is strict: every number in it
must be bound or allowlisted.

Bindings live in number_bindings/<repo>__<file>.json:

    {"bindings": [
      {"token": "40.1%", "sign": "", "before": "...By 2025-26 it was",
       "table": "output/game1_season.csv", "where": {"LEAGUE": 0, "SEASON": 2026},
       "column": "G1_RATE", "scale": 100, "abs": false}
    ]}

"before" is the last 30 characters of prose ahead of the number, which is
how a binding finds its occurrence again after edits elsewhere. "abs" is
true when the prose states a negative value without its sign ("smaller by
2.49 points").

    python verify_numbers.py --propose <repo> <file>   draft bindings

--propose binds a number when exactly one cell in the study's tracked
outputs displays as it does (a Python table and its tracked R twin count
once) and writes the rest, with their candidates, to a .proposals.json
file beside it for a person to resolve.
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import polars as pl

KEY_PRIORITY = ["LEAGUE", "SEASON", "PANEL", "METRIC", "STAGE", "BIN", "GAME_NO",
                "DECADE", "season", "league", "panel", "metric", "model", "term"]


def path_for(bind_dir: Path, repo: str, rel: str) -> Path:
    return bind_dir / f"{repo}__{rel.replace('/', '_')}.json"


def load(path: Path) -> list[dict]:
    return json.loads(path.read_text())["bindings"] if path.exists() else []


def save(path: Path, bindings: list[dict]) -> None:
    path.write_text(json.dumps({"bindings": bindings}, indent=1, ensure_ascii=False) + "\n")


def decimals(token: str) -> int:
    t = token.rstrip("%×x").replace(",", "")
    return len(t.split(".")[1]) if "." in t else 0


def shown(token: str, sign: str) -> str:
    """The number as displayed, sign included, in plain digits."""
    t = token.rstrip("%×x").replace(",", "")
    return f"{-float(t) if sign == '-' else float(t):.{decimals(token)}f}"


def fmt(value: float, dec: int) -> str:
    out = f"{value:.{dec}f}"
    return out[1:] if out.startswith("-") and float(out) == 0 else out


def read_table(base: Path, table: str) -> pl.DataFrame:
    return pl.read_csv(base / table, infer_schema_length=None)


def cell(df: pl.DataFrame, where: dict, column: str) -> list:
    sub = df
    for k, v in where.items():
        sub = sub.filter(pl.col(k).cast(pl.Utf8) == str(v))
    return sub[column].to_list()


def check(base: Path, b: dict, cache: dict) -> str | None:
    """None when the bound cell displays exactly as the prose does, else why not."""
    key = b["table"]
    if key not in cache:
        cache[key] = read_table(base, key) if (base / key).exists() else None
    df = cache[key]
    if df is None:
        return f"{key} missing"
    if b["column"] not in df.columns:
        return f"{key} has no column {b['column']}"
    vals = cell(df, b["where"], b["column"])
    if len(vals) != 1:
        return f"{key} {b['where']} selects {len(vals)} rows, not 1"
    if vals[0] is None:
        return f"{key} {b['where']} {b['column']} is blank"
    v = float(vals[0]) * b.get("scale", 1)
    if b.get("abs"):
        v = abs(v)
    want = shown(b["token"], b["sign"])
    got = fmt(v, decimals(b["token"]))
    if b["sign"] == "" and not b.get("abs") and v < 0 and float(got) != 0:
        return f"prose shows {b['token']} unsigned but the cell is {got}; set abs if intended"
    return None if got == fmt(float(want), decimals(b["token"])) else f"cell gives {got}, prose shows {want}"


def find(bindings: list[dict], occ: dict) -> dict | None:
    for b in bindings:
        if b["token"] == occ["token"] and b["sign"] == occ["sign"] and b["before"] == occ["before"]:
            return b
    return None


def find_by_context(bindings: list[dict], occ: dict) -> dict | None:
    """The binding at the same spot when the number itself was edited."""
    hits = [b for b in bindings if b["before"] == occ["before"]]
    return hits[0] if len(hits) == 1 else None


def expected(base: Path, b: dict, cache: dict) -> str:
    """The bound cell as the prose should show it."""
    if b["table"] not in cache:
        cache[b["table"]] = read_table(base, b["table"]) if (base / b["table"]).exists() else None
    df = cache[b["table"]]
    vals = cell(df, b["where"], b["column"]) if df is not None and b["column"] in df.columns else []
    if len(vals) != 1 or vals[0] is None:
        return "no single cell"
    v = float(vals[0]) * b.get("scale", 1)
    v = abs(v) if b.get("abs") else v
    out = fmt(v, decimals(b["token"]))
    return ("+" + out if b["sign"] == "+" and v >= 0 else out) + ("%" if b["token"].endswith("%") else "")


def row_key(df: pl.DataFrame, i: int) -> dict:
    """The fewest non-float columns that pick out row i alone."""
    cols = [c for c in df.columns if not df[c].dtype.is_float()]
    cols.sort(key=lambda c: (KEY_PRIORITY.index(c) if c in KEY_PRIORITY else len(KEY_PRIORITY),
                             df.columns.index(c)))
    row = df.row(i, named=True)
    for size in range(1, 4):
        for combo in itertools.combinations(cols, size):
            where = {c: row[c] for c in combo}
            if len(cell(df, where, df.columns[0])) == 1:
                return where
    return {"__row__": i}


def candidates(base: Path, tables: list[str], occ: dict, limit: int = 12) -> list[dict]:
    """Every cell in the tables that displays as the occurrence does."""
    dec = decimals(occ["token"])
    want = fmt(float(shown(occ["token"], occ["sign"])), dec)
    out, seen_twins = [], set()
    for t in tables:
        twin_of = t.replace("_r.csv", ".csv").replace("/r/", "/")
        try:
            df = read_table(base, t)
        except Exception:  # noqa: BLE001 - an unreadable table offers no candidates
            continue
        for c in df.columns:
            if not df[c].dtype.is_numeric():
                continue
            vals = df[c].cast(pl.Float64).to_list()
            for scale in (1, 100):
                for absflag in (False, True):
                    for i, v in enumerate(vals):
                        if v is None:
                            continue
                        x = abs(v * scale) if absflag else v * scale
                        if fmt(x, dec) != want:
                            continue
                        if not absflag and occ["sign"] == "" and x < 0:
                            continue
                        if absflag and v * scale >= 0:
                            continue
                        sig = (twin_of, c, i, scale, absflag)
                        if sig in seen_twins:
                            continue
                        seen_twins.add(sig)
                        out.append({"table": t, "row": i, "column": c, "scale": scale,
                                    "abs": absflag, "value": v})
                        if len(out) > limit:
                            return out
    return out


def propose(base: Path, tables: list[str], occs: list[dict], existing: list[dict],
            allowed: dict) -> tuple[list[dict], list[dict]]:
    """Keep existing bindings that still find their occurrence; bind the
    rest when exactly one cell fits; return (bindings, open items)."""
    bound, open_items = [], []
    tables = sorted(tables, key=lambda t: ("_r.csv" in t or "/r/" in t, t))
    for occ in occs:
        if occ["token"] in allowed:
            continue
        b = find(existing, occ)
        if b:
            bound.append(b)
            continue
        cands = candidates(base, tables, occ)
        if len(cands) == 1:
            c = cands[0]
            df = read_table(base, c["table"])
            bound.append({**occ, "table": c["table"], "where": row_key(df, c["row"]),
                          "column": c["column"], "scale": c["scale"], "abs": c["abs"]})
        else:
            open_items.append({**occ, "candidates": [
                {**c, "where": row_key(read_table(base, c["table"]), c["row"])} for c in cands]})
    return bound, open_items
