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


def test_labels_are_not_claims(vn):
    text = ("By Game 7 only close series remain; Games 6 and 7 differ. "
            "Question 4 asks about fouls per 100 possessions (95% interval) "
            "and the 95% bootstrap CI, but 35.1% is a claim.")
    assert vn.tokens_of(text) == ["35.1%"]


def test_context_masks_neighboring_numbers(vn):
    a = vn.occurrences("the NBA is −0.03 against Games 2 on and −0.32 against")
    b = vn.occurrences("the NBA is +0.03 against Games 2 on and −0.32 against")
    assert a[-1]["before"] == b[-1]["before"]
    assert (a[0]["sign"], b[0]["sign"]) == ("-", "+")


@pytest.fixture
def bound(tmp_path):
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "s.csv").write_text(
        "LEAGUE,PANEL,MEAN,N\n0,all,-0.000290,630\n10,all,0.0026,170\n")
    return tmp_path


def b(token, sign, where, column, scale=100, absflag=False):
    return {"token": token, "sign": sign, "before": "x", "table": "output/s.csv",
            "where": where, "column": column, "scale": scale, "abs": absflag}


def test_binding_exact_match_and_sign(nbm, bound):
    cache = {}
    assert nbm.check(bound, b("0.03", "-", {"LEAGUE": 0}, "MEAN"), cache) is None
    assert nbm.check(bound, b("0.26", "+", {"LEAGUE": 10}, "MEAN"), cache) is None
    assert nbm.check(bound, b("630", "", {"LEAGUE": 0}, "N", 1), cache) is None
    assert "cell gives" in nbm.check(bound, b("0.04", "-", {"LEAGUE": 0}, "MEAN"), cache)
    assert "cell gives" in nbm.check(bound, b("631", "", {"LEAGUE": 0}, "N", 1), cache)
    # An unsigned prose value for a negative cell needs abs, said out loud.
    assert "set abs" in nbm.check(bound, b("0.03", "", {"LEAGUE": 0}, "MEAN"), cache)
    assert nbm.check(bound, b("0.03", "", {"LEAGUE": 0}, "MEAN", absflag=True), cache) is None


def test_binding_row_and_column_must_exist(nbm, bound):
    cache = {}
    assert "selects 2 rows" in nbm.check(bound, b("1", "", {"PANEL": "all"}, "N", 1), cache)
    assert "no column" in nbm.check(bound, b("1", "", {"LEAGUE": 0}, "SD"), cache)
    assert "missing" in nbm.check(bound, {**b("1", "", {}, "N"), "table": "output/gone.csv"}, cache)


def test_propose_binds_only_unique_cells(nbm, vn, tmp_path):
    (tmp_path / "output").mkdir()
    # -0.03 displays from two cells (MEAN of league 0, LO of league 10).
    (tmp_path / "output" / "s.csv").write_text(
        "LEAGUE,MEAN,LO,N\n0,-0.000290,-0.0010,630\n10,0.0026,-0.00031,170\n")
    occs = [{"token": "630", "sign": "", "before": "a"}, {"token": "0.03", "sign": "-", "before": "b"}]
    got, open_items = nbm.propose(tmp_path, ["output/s.csv"], occs, [], {}, vn.allowed_reason)
    assert [(g["token"], g["column"], g["where"]) for g in got] == [("630", "N", {"LEAGUE": 0})]
    # A single matching cell is a draft, never a verdict.
    assert got[0]["auto"] is True
    assert [o["token"] for o in open_items] == ["0.03"]
    assert len(open_items[0]["candidates"]) == 2


def test_binding_complement(nbm, tmp_path):
    # "20% never played another season" comes from a played-again share.
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "s.csv").write_text("tier,share_played_next\nrole,0.799277\n")
    one = {"token": "20%", "sign": "", "before": "x", "table": "output/s.csv",
           "where": {"tier": "role"}, "column": "share_played_next", "scale": 100,
           "abs": False, "complement": True}
    assert nbm.check(tmp_path, one, {}) is None
    assert "cell gives" in nbm.check(tmp_path, {**one, "token": "25%"}, {})
    assert "cell gives" in nbm.check(tmp_path, {**one, "complement": False}, {})


def test_row_key_prefers_text_columns(nbm):
    import polars as pl
    df = pl.DataFrame({"spec": ["strict", "strict"], "tier": ["role", "star"],
                       "n_cy": [1123, 246], "diff": [0.21, -0.25]})
    assert nbm.row_key(df, 0) == {"tier": "role"}


def test_numbers_glued_to_letters_are_names(vn):
    assert vn.tokens_of("the 1990s and 2000s, 3PA rate, the 12th pick, and 35.1%") == ["35.1%"]


def test_scoped_allowlist_entry(vn):
    occ = vn.occurrences("falls from 99.9% at pick 1. | quintile | 1 | 39 |")
    allowed = {"1 @ at pick": "1 @ at pick  # an illustrative pick number"}
    one = [o for o in occ if o["token"] == "1"]
    assert vn.allowed_reason(one[0], allowed) is not None
    assert vn.allowed_reason(one[1], allowed) is None


def test_repeated_context_gets_nth(vn):
    row = "a long table caption that fills the context | 38 |\n"
    occ = vn.occurrences(row + row)
    assert [o["nth"] for o in occ] == [0, 1]


def test_rows_and_cross_table_minus(nbm, tmp_path):
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "m1.csv").write_text("term,coef\n" + "".join(f"t{i},0.1\n" for i in range(17)))
    (tmp_path / "output" / "m0.csv").write_text("term,coef\nintercept,1\nlog_pick,2\n")
    feat = {"token": "15", "sign": "+", "before": "x", "table": "output/m1.csv", "where": {},
            "column": "__rows__", "scale": 1, "abs": False,
            "minus": {"table": "output/m0.csv", "column": "__rows__"}}
    assert nbm.check(tmp_path, feat, {}) is None
    assert "cell gives" in nbm.check(tmp_path, {**feat, "token": "16"}, {})


def test_list_markers_and_section_references_are_labels(vn):
    text = "## Models\n\n1. Height trend.\n2) Regime model.\n### 3. Bootstrap\n\nSee Finding 1 and limitation 5; 35.1% is a claim.\n"
    assert vn.tokens_of(text) == ["35.1%"]


def test_leading_dot_decimal_is_a_number(vn):
    assert vn.tokens_of("correlation .44 → .12") == [".44", ".12"]


def test_template_literal_needs_matching_context(vn, tmp_path):
    gen = tmp_path / "gen.py"
    gen.write_text('def build():\n    return f"""## Findings\n\nThe sample is 567 players; count {n} then 1.\n"""\n')
    lits = vn.template_literals(gen)
    assert ("567", "## Findings The sample is") in lits
    assert not any(tok == "1" and "count" not in ctx for tok, ctx in lits)


def test_expression_binding(nbm, tmp_path):
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "h.csv").write_text("season,h\n2016,79.2804\n2017,79.0220\n2018,79.0221\n2019,78.4157\n")
    ref = lambda y: {"table": "output/h.csv", "where": {"season": y}, "column": "h"}
    step = {"op": "-", "args": [ref(2019), ref(2018)]}
    prev = {"op": "-", "args": [ref(2017), ref(2016)]}
    ratio = {"token": "2.3", "sign": "", "before": "x", "scale": 1, "abs": False,
             "expr": {"op": "/", "args": [{"op": "abs", "args": [step]}, {"op": "abs", "args": [prev]}]}}
    assert nbm.check(tmp_path, ratio, {}) is None
    assert "cell gives" in nbm.check(tmp_path, {**ratio, "token": "1.8"}, {})


def test_template_percent_format_keeps_its_sign(vn, tmp_path):
    gen = tmp_path / "gen.py"
    gen.write_text('def build():\n    return f"""falls from {p1:.1%} at pick 1 and on."""\n')
    assert any(tok == "1" and ctx.endswith("#% at pick") for tok, ctx in vn.template_literals(gen))


def test_cross_repo_reference_and_range_mean(nbm, tmp_path):
    here, sib = tmp_path / "a", tmp_path / "b"
    (here / "output").mkdir(parents=True); (sib / "output").mkdir(parents=True)
    (sib / "output" / "c.csv").write_text("bucket,xpps\nwin,1.0893\nbase,1.0970\n")
    (here / "output" / "t.csv").write_text("bucket,n\n30,1\n31,200\n32,201\n33,202\n34,9\n")
    ref = lambda b: {"repo": "b", "table": "output/c.csv", "where": {"bucket": b}, "column": "xpps"}
    cross = {"token": "0.8", "sign": "-", "before": "x", "scale": 100, "abs": False,
             "expr": {"op": "-", "args": [ref("win"), ref("base")]}}
    assert nbm.check(here, cross, {}) is None
    band = {"token": "201", "sign": "", "before": "x", "scale": 1, "abs": False,
            "expr": {"agg": "mean", "table": "output/t.csv", "column": "n", "range": {"bucket": [31, 33]}}}
    assert nbm.check(here, band, {}) is None


def test_cross_repo_row_count_of_a_data_file_is_allowed(nbm):
    none = lambda repo: set()
    count = {"expr": {"repo": "b", "table": "data/raw.csv", "where": {}, "column": "__rows__"}}
    cell = {"expr": {"repo": "b", "table": "data/raw.csv", "where": {}, "column": "pts"}}
    assert nbm.sources_tracked(count, set(), none)
    assert not nbm.sources_tracked(cell, set(), none)


def test_ranges_never_split_a_number(vn):
    toks = lambda s: [o["token"] for o in vn.occurrences(s)]
    assert toks("sums land at 8,200-8,900, matching") == ["8,200", "8,900"]
    assert toks("the 2015-16 season") == []
    assert toks("CI [0.23,1.20] here") == ["0.23", "1.20"]
    assert toks("rows (~16,000–19,500 lineups") == ["16,000", "19,500"]
    assert toks("selection r .91/.87, n=215/207 at") == [".91", ".87", "215", "207"]
    assert toks("by 11.4%/10.0% MAE") == ["11.4%", "10.0%"]
    assert toks("worth 2.2 pts/100 here") == ["2.2"]
    assert toks("tau ≈ 6.7-7.4/100") == ["6.7", "7.4", "100"]


def test_min_max_aggregates_and_product_round_ops(nbm, tmp_path):
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "g.csv").write_text("game,lead,frames\na,6.0,38000\nb,2.5,41466\nc,4.0,52000\n")
    agg = lambda a, c: {"agg": a, "table": "output/g.csv", "column": c}
    b = lambda tok, expr: {"token": tok, "sign": "", "before": "x", "scale": 1, "abs": False, "expr": expr}
    assert nbm.check(tmp_path, b("2.5", agg("min", "lead")), {}) is None
    assert nbm.check(tmp_path, b("6.0", agg("max", "lead")), {}) is None
    assert "cell gives" in nbm.check(tmp_path, b("6.5", agg("max", "lead")), {})
    rounded = {"op": "round", "args": [agg("median", "frames"), -4]}
    assert nbm.check(tmp_path, b("40,000", rounded), {}) is None
    assert "cell gives" in nbm.check(tmp_path, b("41,466", rounded), {})
    assert nbm.check(tmp_path, b("12.0", {"op": "*", "args": [agg("max", "lead"), 2]}), {}) is None


def test_floor_op_rounds_an_at_least_claim_down(nbm, tmp_path):
    # kills-study: a 0.9985903 minimum is "at least 99.85%", never 99.86%
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "v.csv").write_text("cap\n0.9985903\n0.9991\n0.995\n")
    b = lambda tok, expr: {"token": tok, "sign": "", "before": "x", "scale": 100, "abs": False, "expr": expr}
    lo = {"agg": "min", "table": "output/v.csv", "column": "cap", "where": {}}
    worst = {"agg": "min", "table": "output/v.csv", "column": "cap", "range": {"cap": [0.998, 1]}}
    assert nbm.check(tmp_path, b("99.85%", {"op": "floor", "args": [worst, 4]}), {}) is None
    assert "cell gives" in nbm.check(tmp_path, b("99.86%", {"op": "floor", "args": [worst, 4]}), {})
    # an exact 0.995 stays 0.995 despite float noise in 0.995 * 1000
    assert nbm.check(tmp_path, b("99.5%", {"op": "floor", "args": [lo, 3]}), {}) is None


def test_row_difference_median_and_argmin(nbm, tmp_path):
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "v.csv").write_text("lo,hi\n1.0,6.0\n2.0,7.2\n0.0,4.0\n")
    (tmp_path / "output" / "cv.csv").write_text("lam,cv_wmse\n1600.0,1895.9\n3200.0,1893.9\n6400.0,1895.9\n")
    b = lambda tok, expr: {"token": tok, "sign": "", "before": "x", "scale": 1, "abs": False, "expr": expr}
    width = {"agg": "median", "table": "output/v.csv", "column": "hi", "minus_column": "lo"}
    assert nbm.check(tmp_path, b("2.5", {"op": "/", "args": [width, 2]}), {}) is None
    chosen = {"agg": "argmin", "table": "output/cv.csv", "column": "lam", "by": "cv_wmse"}
    assert nbm.check(tmp_path, b("3200", chosen), {}) is None
    assert "cell gives" in nbm.check(tmp_path, b("1600", chosen), {})
    lo = lambda t: {"table": t, "where": {}, "column": "lam"}
    (tmp_path / "output" / "cv2.csv").write_text("lam\n800.0\n")
    first = {"agg": "min", "table": "output/cv.csv", "column": "lam"}
    assert nbm.check(tmp_path, b("800", {"op": "min", "args": [first, lo("output/cv2.csv")]}), {}) is None
    assert nbm.check(tmp_path, b("1600", {"op": "max", "args": [first, lo("output/cv2.csv")]}), {}) is None


def test_private_study_checks_live_in_its_own_repo(vn, tmp_path, monkeypatch):
    # A study with number_checks/ keeps its bindings and allowlists there,
    # so the public tools repo never holds a private study's prose.
    monkeypatch.setattr(vn, "SIBLINGS", tmp_path)
    (tmp_path / "priv" / "number_checks").mkdir(parents=True)
    assert vn.bind_dir("priv") == tmp_path / "priv" / "number_checks" / "bindings"
    assert vn.allow_dir("priv") == tmp_path / "priv" / "number_checks" / "allowlists"
    assert vn.bind_dir("pub") == vn.BIND_DIR and vn.allow_dir("pub") == vn.ALLOW_DIR
