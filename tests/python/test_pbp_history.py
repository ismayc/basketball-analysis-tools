"""pbp_history: the score-stamp rules (ported from elam-ending-study's
test_import.py, each pinned to the real case that forced it), the season and
file-name conventions, and the finals check."""
from __future__ import annotations

import polars as pl
import pytest

from conftest import REPO, load_script

COLS = ["gameId", "actionNumber", "clock", "period", "teamId", "location",
        "actionType", "subType", "description", "shotResult", "isFieldGoal",
        "scoreHome", "scoreAway"]


@pytest.fixture(scope="module")
def ph():
    return load_script(REPO / "pbp_history.py", "portfolio_pbp_history")


def rows(*events, game="22300001"):
    """events: (actionNumber, clock, actionType, location, scoreHome, scoreAway).
    The game ID is unpadded, as in the archive."""
    return pl.DataFrame(
        [{"gameId": game, "actionNumber": str(n), "clock": c, "period": "4",
          "teamId": "1", "location": loc, "actionType": t, "subType": "",
          "description": "", "shotResult": "", "isFieldGoal": "0",
          "scoreHome": h, "scoreAway": a} for n, c, t, loc, h, a in events],
        schema={k: pl.Utf8 for k in COLS})


def scores(df):
    return list(zip(df["score_h"].to_list(), df["score_a"].to_list()))


def test_instant_replay_stamp_is_ignored(ph):
    # 0022300010: the replay row reads 53-44 after free throws made it 55-44.
    out = ph.prepare(rows(
        (1, "PT04M17.00S", "Free Throw", "h", "55", "44"),
        (2, "PT04M17.00S", "Instant Replay", "", "53", "44"),
        (3, "PT03M59.00S", "Made Shot", "v", "55", "46"),
    ))
    assert scores(out) == [(55, 0), (55, 0), (55, 46)]


def test_stamp_sets_only_the_scoring_team(ph):
    # 0022500527: Camara's (home) free throw is stamped 93-91; away was on 89.
    out = ph.prepare(rows(
        (1, "PT04M43.00S", "Made Shot", "v", "91", "89"),
        (2, "PT04M32.00S", "Free Throw", "h", "93", "91"),
    ))
    assert scores(out) == [(0, 89), (93, 89)]


def test_out_of_order_same_instant_free_throws(ph):
    # 0022300055: a technical free throw stamped 124 sorts after the and-one
    # free throw stamped 126 at the same clock reading; the score stays 126.
    out = ph.prepare(rows(
        (647, "PT03M54.00S", "Free Throw", "h", "126", "103"),
        (655, "PT03M54.00S", "Free Throw", "h", "124", "103"),
        (660, "PT03M34.00S", "Missed Shot", "v", "", ""),
    ))
    assert [h for h, _ in scores(out)] == [126, 126, 126]


def test_clock_order_beats_action_number(ph):
    out = ph.prepare(rows(
        (900, "PT05M05.00S", "Made Shot", "h", "10", "0"),
        (100, "PT04M00.00S", "Made Shot", "h", "12", "0"),
    ))
    assert out["actionNumber"].to_list() == [900, 100]
    assert [h for h, _ in scores(out)] == [10, 12]


def test_padded_labels_are_stripped_and_ids_padded(ph):
    # NBA 1996-97 has "Made Shot" plus trailing spaces.
    out = ph.prepare(rows((1, "PT03M59.00S", "Made Shot" + " " * 31, "h ", "2", "0")))
    assert out["actionType"].to_list() == ["Made Shot"]
    assert out["gameId"].to_list() == ["0022300001"]
    assert scores(out) == [(2, 0)]


def test_missing_columns_are_tolerated(ph):
    # Older archives may lack a column KEEP names (personId here).
    out = ph.prepare(rows((1, "PT03M59.00S", "Made Shot", "h", "2", "0")))
    assert out["personId"].to_list() == [0]


def test_dataset_names(ph):
    assert ph.dataset("nba", "v3", 1996) == "nbastatsv3_1996"
    assert ph.dataset("wnba", "v3", 1997, "po") == "wnba_nbastatsv3_po_1997"
    assert ph.dataset("nba", "pbpstats", 2000) == "pbpstats_2000"


def test_season_labels_and_gamelog_years(ph):
    # Archive years are start years; NBA gamelog files use the end year.
    assert ph.season_label("nba", 1999) == "1999-00"
    assert ph.season_label("wnba", 2009) == "2009"
    assert ph.gamelog_path("nba", 1996).name == "nba_1997_rs.csv"
    assert ph.gamelog_path("wnba", 1997, "po").name == "wnba_1997_po.csv"


def test_check_finals_statuses(ph):
    ev = pl.DataFrame({"gameId": ["a", "a", "b", "c"], "score_h": [0, 90, 80, 70],
                       "score_a": [2, 88, 79, 71]})
    gl = pl.DataFrame({"gameId": ["a", "b", "d"], "gl_h": [90, 81, 60], "gl_a": [88, 79, 50]})
    out = ph.check_finals(ev, gl)
    assert dict(zip(out["gameId"], out["status"])) == {
        "a": "ok", "b": "score", "c": "no_gamelog", "d": "no_events"}


def test_neutral_site_sides_come_from_the_feed(ph):
    # 0022400147 (Mexico City): LeagueGameLog lists both teams with "@", so
    # sides must come from the event feed's location column.
    ev = pl.DataFrame({"gameId": ["g"] * 4, "teamId": [7, 7, 9, 0],
                       "location": ["h", "h", "v", ""],
                       "score_h": [2, 4, 4, 4], "score_a": [0, 0, 3, 3]})
    gl = pl.DataFrame({"gameId": ["g", "g"], "team_id": [9, 7], "abbr": ["WAS", "MIA"],
                       "game_date": ["2024-11-02"] * 2, "PTS": [3, 4], "AST": [1, 2],
                       "FGM": [1, 2]})
    gt = ph.game_table(ev, gl)
    assert gt.select("home_id", "away_id", "abbr_h", "gl_h", "gl_a").row(0) == (7, 9, "MIA", 4, 3)
    assert ph.check_finals(ev, gt)["status"].to_list() == ["ok"]


def test_gamelog_game_without_events_is_reported(ph):
    ev = pl.DataFrame({"gameId": ["g", "g"], "teamId": [7, 9], "location": ["h", "v"],
                       "score_h": [2, 2], "score_a": [0, 3]})
    gl = pl.DataFrame({"gameId": ["g", "g", "x", "x"], "team_id": [7, 9, 7, 9],
                       "abbr": ["A", "B", "A", "B"], "game_date": ["d"] * 4,
                       "PTS": [2, 3, 1, 1], "AST": [0] * 4, "FGM": [1] * 4})
    out = ph.check_finals(ev, ph.game_table(ev, gl))
    assert dict(zip(out["gameId"], out["status"])) == {"g": "ok", "x": "no_events"}


def test_stamp_jump_is_flagged_even_when_the_final_matches(ph):
    # 0021700025: a home stamp of 114 ninety seconds in; the running maximum
    # held 114 until the real score passed it, so the final still matched.
    ev = ph.prepare(rows(
        (1, "PT10M30.00S", "Made Shot", "h", "114", "0"),
        (2, "PT10M00.00S", "Made Shot", "v", "114", "2"),
        (3, "PT01M00.00S", "Made Shot", "h", "116", "2"),
    ))
    assert ph.max_jump(ev)["max_jump"].to_list() == [114]
    gl = pl.DataFrame({"gameId": ["0022300001"], "gl_h": [116], "gl_a": [2]})
    assert ph.check_finals(ev, gl)["status"].to_list() == ["jump"]
    ok = ph.prepare(rows((1, "PT10M30.00S", "Made Shot", "h", "3", "0"),
                         (2, "PT10M00.00S", "Free Throw", "h", "4", "0")))
    gl = pl.DataFrame({"gameId": ["0022300001"], "gl_h": [4], "gl_a": [0]})
    assert ph.check_finals(ok, gl)["status"].to_list() == ["ok"]
