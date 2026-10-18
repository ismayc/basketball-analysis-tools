"""Unit tests for tools/verify_numbers.py.

The gate shipped matching against a 1,066,841-value family pool, so every
wrong number passed (400 of 400 random tokens, 2026-10-18). These pin the
pieces that made that silent: the matching rule, the sign handling, the
year skip, generator regions, the measured pass rate, and the loud
failure outside a git checkout.
"""
from __future__ import annotations

import subprocess

import pytest


def test_match_is_to_display_precision(vn):
    pool = vn.Pool({0.401})
    assert vn.matches("40.1%", vn.with_scaled({0.401}))
    assert vn.matches("0.40", pool)
    assert not vn.matches("0.41", pool)
    # The 2026-10-18 case: a wrong share must fail against a small pool.
    assert not vn.matches("40.7%", vn.with_scaled({0.401}))


def test_negative_proportion_matches_unsigned_percentage(vn):
    # Prose "−6.55 points" reaches the matcher as "6.55"; the stored value is
    # -0.0655. The old scaling never made -v * 100, so this matched only by
    # chance in a big pool.
    assert vn.matches("6.55", vn.with_scaled({-0.0655}))


def test_year_skipped_but_counts_checked(vn):
    assert vn.tokens_of("In 2010, the rule changed.") == []
    assert vn.tokens_of("From 1998 to 2026.") == []
    assert vn.tokens_of("We kept 2000 series and 1985 games.") == ["2000", "1985"]
    assert vn.tokens_of("A cut of 1,350.") == ["1,350"]


def test_generator_regions_left_to_the_generator(vn):
    text = ("Typed 3.5 here.\n<!-- gen:headline -->\n| 1.25 | 7.50 |\n"
            "<!-- /gen:headline -->\nAnd 4.2.\n")
    assert vn.tokens_of(text) == ["3.5", "4.2"]
    assert vn.generator_owned(text) == 2


def test_wrong_pass_rate_measures_the_pool(vn):
    exact = vn.with_scaled({0.351})
    assert vn.wrong_pass_rate(["35.1%"], exact, "seed") == 0.0
    dense = vn.Pool({round(i * 0.01, 2) for i in range(0, 10001)})
    assert vn.wrong_pass_rate(["35.1"], dense, "seed") == 1.0
    assert vn.wrong_pass_rate(["2e-13"], exact, "seed") is None


def test_pool_near_bounds(vn):
    p = vn.Pool({1.0, 2.0})
    assert p.near(1.04, 0.05) and not p.near(1.06, 0.05)
    assert not p.near(3.0, 0.5) and p.any_between(1.5, 2.0)


def test_git_tracked_fails_loudly_outside_a_repo(vn, tmp_path):
    with pytest.raises(SystemExit, match="git ls-files failed"):
        vn.git_tracked(tmp_path, "output")


def test_git_tracked_lists_only_tracked_files(vn, tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "kept.csv").write_text("a\n1\n")
    (tmp_path / "output" / "local.csv").write_text("a\n2\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "output/kept.csv"], check=True)
    assert [p.name for p in vn.git_tracked(tmp_path, "output")] == ["kept.csv"]
