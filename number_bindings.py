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

"before" is the last 30 characters of prose ahead of the number, numbers
masked as #, which is how a binding finds its occurrence again after edits
elsewhere. "abs" is true when the prose states a negative value without its
sign ("smaller by 2.49 points"); "complement" is true when the prose states
1 minus the cell ("20% never played again" from a played-again share).

    python verify_numbers.py --propose <repo> <file>   draft bindings

--propose drafts a binding when exactly one cell in the study's tracked
outputs displays as it does (a Python table and its tracked R twin count
once), marked "auto": true, and writes the rest, with their candidates, to
a .proposals.json file beside it. One matching cell is not proof: on
2026-10-18 the draft-study sample size 567 drafted as one player's OBPM
x 100. The gate fails every "auto" binding until a person confirms it and
deletes the flag.
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


def load_cached(base: Path, table: str, cache: dict, repo: str | None = None) -> pl.DataFrame | None:
    """A table of this repo, or of a sibling repo when a reference names one
    (a story citing another study's result)."""
    root = base.parent / repo if repo else base
    key = (repo, table) if repo else table
    if key not in cache:
        cache[key] = read_table(root, table) if (root / table).exists() else None
    return cache[key]


def one_cell(df: pl.DataFrame, where: dict, column: str) -> float | str:
    """The single cell at where/column, or a reason there is not one."""
    if column not in df.columns:
        return f"has no column {column}"
    vals = cell(df, where, column)
    if len(vals) != 1:
        return f"{where} selects {len(vals)} rows, not 1"
    if vals[0] is None:
        return f"{where} {column} is blank"
    return float(vals[0])


def tables_of(b: dict) -> list[str]:
    """Every table a binding reads."""
    def walk(e):
        if isinstance(e, dict):
            if "op" in e:
                return [t for a in e["args"] for t in walk(a)]
            return [e["table"]]
        return []
    # (an "agg" node names its table like a cell reference does)
    if "expr" in b:
        return walk(b["expr"])
    return [b["table"]] + ([b["minus"]["table"]] if "table" in b.get("minus", {}) else [])


def sources_tracked(b: dict, tracked: set, tracked_in=None) -> bool:
    """Every table read is a tracked output (of its own repo when a
    reference names one), or a local data/ file whose row or column count
    is all that is claimed."""
    refs = [b] if "expr" not in b else []
    def walk(e):
        if isinstance(e, dict):
            if "op" in e:
                for a in e["args"]:
                    walk(a)
            else:
                refs.append(e)
    if "expr" in b:
        walk(b["expr"])
    def tracked_ok(r):
        if r.get("repo"):
            return tracked_in is not None and r["table"] in tracked_in(r["repo"])
        return r["table"] in tracked or local_count(r)
    ok = all(tracked_ok(r) for r in refs)
    return ok and ("table" not in b.get("minus", {}) or b["minus"]["table"] in tracked)


def local_count(b: dict) -> bool:
    """A row or column count of a local data/ file. Such a file may be a
    gitignored download (licensed source data); only its size is claimed."""
    return b["table"].startswith("data/") and b["column"] in ("__rows__", "__columns__")


def eval_expr(e, load) -> float | str:
    """An expression over cells: a number, a cell reference {"table",
    "where", "column"} (column may be __rows__ or __columns__), an
    aggregate {"agg": "median" | "mean", ...}, or {"op": "-" | "/" | "*" | "abs"
    | "1-" | "round", "args": [...]}. "2.3 times the next-largest drop" is
    abs(step) / abs(next drop); "a maximum over ~40,000 frames" is
    round(median frames, -4)."""
    if isinstance(e, (int, float)):
        return float(e)
    if "agg" in e:
        # {"agg": "median" | "mean" | "sum" | "min" | "max" | "wmean" (+ "weight"), "table",
        # "column", "where": {}, "where_not": {}, "range": {col: [lo, hi]}}: "a typical
        # offseason" is a median with rows left out; "201 per second at 31-33s" a mean over
        # a range; "a latency of 2.5-6.0 s" the min and max across games.
        df = load(e["table"], e.get("repo"))
        if df is None:
            return f"{e['table']} missing"
        sub = df
        for k, val in e.get("where", {}).items():
            sub = sub.filter(pl.col(k).cast(pl.Utf8) == str(val))
        for k, val in e.get("where_not", {}).items():
            sub = sub.filter(pl.col(k).cast(pl.Utf8) != str(val))
        for k, (lo, hi) in e.get("range", {}).items():
            sub = sub.filter(pl.col(k).is_between(lo, hi))
        if sub.height == 0 or e["column"] not in sub.columns:
            return f"{e['table']} agg selects nothing"
        col = sub[e["column"]].cast(pl.Float64)
        if e["agg"] == "wmean":
            # weighted by another column: shot-weighted eFG across clock buckets
            w = sub[e["weight"]].cast(pl.Float64)
            return float((col * w).sum() / w.sum())
        return float({"median": col.median, "mean": col.mean, "sum": col.sum,
                      "min": col.min, "max": col.max}[e["agg"]]())
    if "op" not in e:
        df = load(e["table"], e.get("repo"))
        return f"{e['table']} missing" if df is None else raw_value(df, {**e, "where": e.get("where", {})})
    vals = [eval_expr(a, load) for a in e["args"]]
    bad = [x for x in vals if isinstance(x, str)]
    if bad:
        return bad[0]
    op = e["op"]
    if op == "-":
        return vals[0] - vals[1]
    if op == "/":
        return "division by zero" if vals[1] == 0 else vals[0] / vals[1]
    if op == "*":
        return vals[0] * vals[1]
    if op == "round":
        return float(round(vals[0], int(vals[1])))
    if op == "abs":
        return abs(vals[0])
    if op == "1-":
        return 1 - vals[0]
    return f"unknown op {op}"


def raw_value(df: pl.DataFrame, b: dict, load=None) -> float | str:
    """The bound number before scaling: a cell, the table's row or column
    count ("__rows__", "__columns__"), or that minus another cell or count
    ("minus": {"where": ..., "column": ..., "table": optional}), an AUC
    gain or a feature count, for example."""
    if b["column"] == "__rows__":
        v = float(df.height)
    elif b["column"] == "__columns__":
        v = float(df.width)
    else:
        v = one_cell(df, b["where"], b["column"])
    if isinstance(v, str) or "minus" not in b:
        return v
    m_spec = b["minus"]
    other = df if "table" not in m_spec else (load(m_spec["table"]) if load else None)
    if other is None:
        return f"minus table {m_spec.get('table')} missing"
    m = raw_value(other, {"column": m_spec["column"], "where": m_spec.get("where", {})})
    return m if isinstance(m, str) else v - m


def value_of(raw: float, b: dict) -> float:
    """The cell as the prose states it: 1 minus the cell when "complement"
    ("20% never played again" from a played-again share), then scaled,
    then unsigned when "abs"."""
    v = (1 - raw) if b.get("complement") else raw
    v *= b.get("scale", 1)
    return abs(v) if b.get("abs") else v


def check(base: Path, b: dict, cache: dict) -> str | None:
    """None when the bound cell displays exactly as the prose does, else why not."""
    if "expr" in b:
        raw = eval_expr(b["expr"], lambda tb, repo=None: load_cached(base, tb, cache, repo))
        if isinstance(raw, str):
            return raw
        return compare(value_of(raw, b), b)
    key = b["table"]
    if key not in cache:
        cache[key] = read_table(base, key) if (base / key).exists() else None
    df = cache[key]
    if df is None:
        return f"{key} missing"
    raw = raw_value(df, b, lambda tb, repo=None: load_cached(base, tb, cache, repo))
    if isinstance(raw, str):
        return f"{key} {raw}"
    return compare(value_of(raw, b), b)


def compare(v: float, b: dict) -> str | None:
    want = shown(b["token"], b["sign"])
    got = fmt(v, decimals(b["token"]))
    if b["sign"] == "" and not b.get("abs") and v < 0 and float(got) != 0:
        return f"prose shows {b['token']} unsigned but the cell is {got}; set abs if intended"
    return None if got == fmt(float(want), decimals(b["token"])) else f"cell gives {got}, prose shows {want}"


def find(bindings: list[dict], occ: dict) -> dict | None:
    for b in bindings:
        if (b["token"] == occ["token"] and b["sign"] == occ["sign"] and b["before"] == occ["before"]
                and b.get("nth", 0) == occ.get("nth", 0)):
            return b
    return None


def find_by_context(bindings: list[dict], occ: dict) -> dict | None:
    """The binding at the same spot when the number itself was edited."""
    hits = [b for b in bindings if b["before"] == occ["before"] and b.get("nth", 0) == occ.get("nth", 0)]
    return hits[0] if len(hits) == 1 else None


def expected(base: Path, b: dict, cache: dict) -> str:
    """The bound cell as the prose should show it."""
    if "expr" in b:
        raw = eval_expr(b["expr"], lambda tb, repo=None: load_cached(base, tb, cache, repo))
        if isinstance(raw, str):
            return "no single value"
        v = value_of(raw, b)
        out = fmt(v, decimals(b["token"]))
        return ("+" + out if b["sign"] == "+" and v >= 0 else out) + ("%" if b["token"].endswith("%") else "")
    if b["table"] not in cache:
        cache[b["table"]] = read_table(base, b["table"]) if (base / b["table"]).exists() else None
    df = cache[b["table"]]
    raw = raw_value(df, b, lambda tb, repo=None: load_cached(base, tb, cache, repo)) if df is not None else "missing"
    if isinstance(raw, str):
        return "no single cell"
    v = value_of(raw, b)
    out = fmt(v, decimals(b["token"]))
    return ("+" + out if b["sign"] == "+" and v >= 0 else out) + ("%" if b["token"].endswith("%") else "")


def row_key(df: pl.DataFrame, i: int) -> dict:
    """The fewest columns that pick out row i alone: text columns first
    (spec, era, tier), integer columns only when text cannot. An integer
    such as a sample size makes a brittle key, since it moves with the data."""
    def rank(c: str) -> tuple:
        return (KEY_PRIORITY.index(c) if c in KEY_PRIORITY else len(KEY_PRIORITY), df.columns.index(c))
    text = sorted((c for c in df.columns if df[c].dtype == pl.Utf8), key=rank)
    ints = sorted((c for c in df.columns if df[c].dtype.is_integer()), key=rank)
    row = df.row(i, named=True)
    for pool in (text, text + ints):
        for size in range(1, min(4, len(pool)) + 1):
            for combo in itertools.combinations(pool, size):
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
            allowed: dict, allowed_reason) -> tuple[list[dict], list[dict]]:
    """Keep existing bindings that still find their occurrence; bind the
    rest when exactly one cell fits; return (bindings, open items)."""
    bound, open_items = [], []
    tables = sorted(tables, key=lambda t: ("_r.csv" in t or "/r/" in t, t))
    for occ in occs:
        if allowed_reason(occ, allowed) is not None:
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
                          "column": c["column"], "scale": c["scale"], "abs": c["abs"],
                          "auto": True})
        else:
            open_items.append({**occ, "candidates": [
                {**c, "where": row_key(read_table(base, c["table"]), c["row"])} for c in cands]})
    return bound, open_items
