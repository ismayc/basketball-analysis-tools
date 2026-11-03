"""Check every number on the built hub page's cards against a committed source.

The card text in report_builder.py is typed by hand, and verify_numbers.py does
not read it. On November 3, 2026 the Elam card said 4,860 games while the study's
games table had 4,866 rows.

This reads the built page, not the source strings, so it checks what is
published. Its number pattern is stricter than verify_numbers.py's: it also
catches the end of a range ("18-23%") and a number with a unit ("7.5M", "6s").
It has no skip rules. Each number on a card must have one entry in
number_bindings/hub_cards.json:

  - a binding: the same cell format as number_bindings.py, plus "card" and
    "token", or a "json" source: {"repo", "json", "key": [...]}, for a value in
    a tracked JSON file;
  - an allowance: {"card", "token", "reason"} for a label, a year, or an outside
    fact. A reason that starts with UNVERIFIED has no committed source, and the
    check lists it.

An entry that matches no number on the page is a failure too, so a reworded card
cannot leave a stale entry behind.

    python check_hub_cards.py
"""
from __future__ import annotations

import html as html_lib
import json
import re
import subprocess
import sys
from pathlib import Path

import number_bindings as nb
import report_builder as rb
import verify_numbers as vn

BINDINGS = vn.BIND_DIR / "hub_cards.json"
CARD = re.compile(r'<div class="card">(.*?)<span class="links">', re.S)
TITLE = re.compile(r"<h3>(.*?)</h3>", re.S)
TAG = re.compile(r"<[^>]+>")
# A sign counts only when no word or number touches it: the hyphens in "18-23%"
# and "2-for-1" join things, and the one in "(-0.25)" is a minus.
NUMBER = re.compile(r"(?P<sign>(?<![\w%])[+\-−])?(?P<num>\d+(?:,\d{3})*(?:\.\d+)?|\.\d+)")


def cards_of(page: str) -> dict[str, str]:
    """Card title to visible text (kicker and headline) from a built page."""
    out = {}
    for block in CARD.findall(page):
        title = TITLE.search(block)
        if title is None:
            continue
        name = " ".join(TAG.sub(" ", title[1]).split())
        out[name] = " ".join(html_lib.unescape(TAG.sub(" ", TITLE.sub(" ", block))).split())
    return out


def numbers_of(text: str) -> list[dict]:
    return [{"token": m["num"], "sign": {"+": "+", "-": "-", "−": "-"}.get(m["sign"] or "", "")}
            for m in NUMBER.finditer(text)]


def json_value(entry: dict) -> float | str:
    path = vn.repo_base(entry["repo"]) / entry["json"]
    if not path.exists():
        return f"{entry['json']} missing"
    value = json.loads(path.read_text())
    for key in entry["key"]:
        if key not in value:
            return f"{entry['json']} has no {key}"
        value = value[key]
    return float(str(value).rstrip("%").replace(",", ""))


def is_tracked(repo: str, rel: str) -> bool:
    base = vn.repo_base(repo)
    done = subprocess.run(["git", "-C", str(base), "ls-files", "--error-unmatch", rel],
                          capture_output=True)
    return done.returncode == 0


def sources_of(entry: dict) -> list[tuple[str, str]]:
    if "json" in entry:
        return [(entry["repo"], entry["json"])]
    found = []

    def walk(e):
        if isinstance(e, dict):
            if "op" in e:
                for arg in e["args"]:
                    walk(arg)
            elif "table" in e:
                found.append((e.get("repo", ""), e["table"]))
    walk(entry["expr"])
    return found


def check_entry(entry: dict, base: Path, cache: dict) -> str | None:
    untracked = [t for r, t in sources_of(entry) if not r or not is_tracked(r, t)]
    if untracked:
        return f"source not tracked by git, or names no repo: {untracked}"
    if "json" in entry:
        raw = json_value(entry)
        if isinstance(raw, str):
            return raw
        return nb.compare(raw * entry.get("scale", 1), entry)
    return nb.check(base, entry, cache)


def check_page(page: str, entries: list[dict]) -> tuple[list[str], dict[str, int], list[str]]:
    """Problems, counts, and the numbers that have no committed source."""
    cards = cards_of(page)
    problems: list[str] = []
    if not cards:
        return ["no cards found on the page; this check would have read nothing"], {}, []
    missing = sorted(set(rb.HUB_CARDS) | set(rb.NEW_CARDS))
    for repo in missing:
        if repo.replace("-", " ") not in cards:
            problems.append(f"{repo}: no card on the page")

    base = vn.repo_base("basketball-data-science")
    cache: dict = {}
    unused = list(entries)
    counts = {"cards": len(cards), "numbers": 0, "bound": 0, "allowed": 0}
    unverified: list[str] = []
    for name, text in cards.items():
        for n in numbers_of(text):
            counts["numbers"] += 1
            hit = next((e for e in unused if e["card"] == name and e["token"] == n["token"]
                        and e.get("sign", n["sign"]) == n["sign"]), None)
            label = f"{name}: {n['sign']}{n['token']}"
            if hit is None:
                problems.append(f"{label} has no entry in {BINDINGS.name}")
                continue
            unused.remove(hit)
            if "reason" in hit:
                counts["allowed"] += 1
                if hit["reason"].startswith("UNVERIFIED"):
                    unverified.append(label)
                continue
            why = check_entry({**hit, "sign": n["sign"]}, base, cache)
            if why:
                problems.append(f"{label}: {why}")
            else:
                counts["bound"] += 1
    problems.extend(f"{e['card']}: {e['token']} is in {BINDINGS.name} but not on the page"
                    for e in unused)
    return problems, counts, unverified


def main() -> int:
    repo_dir = vn.repo_base("basketball-data-science")
    page = (repo_dir / "docs" / "index.html").read_text()
    entries = json.loads(BINDINGS.read_text())["entries"]
    problems, counts, unverified = check_page(page, entries)
    for p in problems:
        print(f"HUB CARD FAIL {p}")
    if problems:
        print(f"HUB CARD CHECK FAILED ({len(problems)} problem(s))")
        return 1
    if unverified:
        print(f"{len(unverified)} number(s) have no committed source: " + "; ".join(unverified))
    print(f"HUB CARD CHECK PASSED ({counts['numbers']} numbers on {counts['cards']} cards: "
          f"{counts['bound']} bound to a committed source, {counts['allowed']} allowed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
