"""check_hub_cards.py must pass the built hub and fail each way a card can go wrong."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import check_hub_cards as chc  # noqa: E402
import verify_numbers as vn  # noqa: E402


@pytest.fixture(scope="module")
def page():
    path = vn.repo_base("basketball-data-science") / "docs" / "index.html"
    if not path.exists():
        pytest.skip("no hub checkout")
    return path.read_text()


@pytest.fixture(scope="module")
def entries():
    return json.loads(chc.BINDINGS.read_text())["entries"]


def test_number_pattern_reads_ranges_units_and_signs():
    got = [(n["sign"], n["token"]) for n in chc.numbers_of(
        "recovers 18-23%, 3.6-4.5x, 7.5M frames, 2.5–6s, (−0.25), +489, r ≈ .9, 218,701, and 2-for-1")]
    assert got == [("", "18"), ("", "23"), ("", "3.6"), ("", "4.5"), ("", "7.5"), ("", "2.5"),
                   ("", "6"), ("-", "0.25"), ("+", "489"), ("", ".9"), ("", "218,701"),
                   ("", "2"), ("", "1")]


def test_built_hub_passes(page, entries):
    problems, counts, _ = chc.check_page(page, entries)
    assert problems == []
    assert counts["cards"] == 17
    assert counts["numbers"] == counts["bound"] + counts["allowed"] == len(entries)


@pytest.mark.parametrize("right,wrong", [
    ("4,866 games", "4,860 games"),
    ("recovers 18-23%", "recovers 18-24%"),
    ("5.8% of the time", "5.9% of the time"),
    ("from 31.5%", "from 31.6%"),
    ("(+0.21", "(+0.22"),
    ("+489", "+490"),
    ("exactly 0.0", "exactly 0.1"),
])
def test_wrong_number_fails(page, entries, right, wrong):
    assert right in page
    problems, _, _ = chc.check_page(page.replace(right, wrong), entries)
    assert problems


def test_a_new_number_with_no_entry_fails(page, entries):
    problems, _, _ = chc.check_page(page.replace("Game 1 three-point", "Game 1 (41) three-point"), entries)
    assert any("no entry" in p and "41" in p for p in problems)


def test_a_stale_entry_fails(page, entries):
    extra = entries + [{"card": "mebounds", "token": "99", "reason": "stale"}]
    problems, _, _ = chc.check_page(page, extra)
    assert any("not on the page" in p for p in problems)


def test_a_page_with_no_cards_fails(entries):
    problems, _, _ = chc.check_page("<html></html>", entries)
    assert problems


def test_a_missing_card_fails(page, entries):
    problems, _, _ = chc.check_page(page.replace("elam ending study", "elam study"), entries)
    assert any("elam-ending-study: no card" in p for p in problems)


def test_an_untracked_source_fails(page, entries):
    changed = [dict(e) for e in entries]
    target = next(e for e in changed if e["token"] == "489")
    target["expr"] = {**target["expr"], "table": "output/not_in_git.csv"}
    problems, _, _ = chc.check_page(page, changed)
    assert any("not tracked" in p for p in problems)
