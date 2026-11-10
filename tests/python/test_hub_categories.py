"""The hub groups studies by category, so a study left out of the grouping
would disappear from the page. These tests fail on that, and prove the build
check catches it rather than passing with no effect."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import report_builder as rb  # noqa: E402


def test_each_study_card_is_in_exactly_one_category():
    placed = [r for _, _, repos in rb.HUB_CATEGORIES for r in repos]
    assert sorted(placed) == sorted(set(rb.HUB_CARDS) | set(rb.NEW_CARDS))


def test_check_stops_on_a_study_with_no_category(monkeypatch):
    monkeypatch.setitem(rb.NEW_CARDS, "new-study",
                        {"kicker": "k", "headline": "h"})
    with pytest.raises(ValueError, match="new-study"):
        rb.check_hub_categories()


def test_check_stops_on_a_repeated_study(monkeypatch):
    first = rb.HUB_CATEGORIES[0]
    doubled = [first, (first[0], first[1], first[2][:1])] + rb.HUB_CATEGORIES[1:]
    monkeypatch.setattr(rb, "HUB_CATEGORIES", doubled)
    with pytest.raises(ValueError, match=first[2][0]):
        rb.check_hub_categories()


def test_built_hub_has_every_category_card_and_nav_link(tmp_path, monkeypatch):
    (tmp_path / "hub" / "docs").mkdir(parents=True)
    monkeypatch.setattr(rb, "SIBLINGS", tmp_path)
    rb.build_hub()
    html = (tmp_path / "hub" / "docs" / "index.html").read_text()
    assert 'class="sectionnav"' in html
    for title, _, repos in rb.HUB_CATEGORIES:
        sid = rb.slug(title)
        assert f'<h2 id="{sid}">{title}</h2>' in html
        assert f'href="#{sid}"' in html
        for r in repos:
            assert f'{r.replace("-", " ")}</a></h3>' in html
    assert "New analyses" not in html
    assert "Six studies" not in html
    # No masthead has the "All studies" or "Scouting one-pagers" links
    # (dropped from the hub November 3, 2026, and from every other page
    # November 10). The family name links to the hub, which lists the
    # scouting reports.
    masthead = html.split('class="masthead"')[1].split("</header>")[0]
    assert "All studies" not in masthead
    assert "Scouting one-pagers" not in masthead
    assert "nba-scouting-onepagers/" in html.split("</header>")[1]
    other = rb.page("t", "<h1>t</h1>", repo="some-study")
    other_mast = other.split('class="masthead"')[1].split("</header>")[0]
    assert "All studies" not in other_mast
    assert "Scouting one-pagers" not in other_mast
    assert f'href="{rb.PAGES}/basketball-data-science/">Basketball Data Science' in other_mast
    # Every h2 has a short nav label, so the nav stays on one desktop row.
    nav = html.split('class="sectionnav"')[1].split("</nav>")[0]
    assert nav.count("<a ") == len(rb.HUB_NAV_LABELS)
    for full, short in rb.HUB_NAV_LABELS.items():
        assert f">{short}</a>" in nav
        if full != short:
            assert f">{full}</a>" not in nav
