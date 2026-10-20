"""Full-history PlayByPlayV3 events for the family's play-by-play studies.

Why
---
stats.nba.com and stats.wnba.com stopped answering from the family's machines
in October 2026, but the shufinskiy/nba_data archives on GitHub hold
PlayByPlayV3 for every NBA season from 1996-97 and every WNBA season from
1997, plus pbpstats possession tables (NBA from 2000-01, WNBA from 2009).
Three studies (kills, safe-lead, heliocentrism) read the same events, so the
score-stamp rules that elam-ending-study proved live here once, instead of in
three copies that can drift apart (playbyplay-study's copy needed the same fix
weeks later).

Layout
------
Raw archives and prepared tables go under ``<family>/.pbp-archive/``, outside
every repo, because the rows are NBA.com data and stay local:

    .pbp-archive/raw/<dataset>_<year>.tar.xz   as downloaded (sha256 manifest
                                               in raw/checksums.txt)
    .pbp-archive/events/<league>_<year>_<rs|po>.parquet   prepare() output
    .pbp-archive/events/<league>_<year>_<rs|po>_finals.csv   per-game check

``<year>`` is always the archive's year: the calendar year a season starts
(NBA 1996 is 1996-97; WNBA 1997 is 1997). playoff-series-study's LeagueGameLog
files name NBA seasons by the year they end (``nba_1997_rs.csv`` is 1996-97),
which ``gamelog_path`` converts.

Score stamps
------------
``prepare`` is elam-ending-study's ``01_import.prepare`` without its Elam
columns: stamps only from Made Shot and Free Throw rows, each scoring row sets
only its own side's score, and the running score is a running maximum (see
that file for the three cases that forced each rule). Every game's final is
then checked against LeagueGameLog; a failing game is reported, never
repaired.

Usage
-----
    python pbp_history.py build --league nba --years 1996-2025
    python pbp_history.py build --league wnba --years 1997-2026 --types rs po
    python pbp_history.py status
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
import sys
import tarfile
import urllib.request
from pathlib import Path

import polars as pl

FAMILY = Path(__file__).resolve().parents[1]
HOME = Path(os.environ.get("PBP_ARCHIVE", FAMILY / ".pbp-archive"))
RAW = HOME / "raw"
EVENTS = HOME / "events"
GAMELOG_DIR = FAMILY / "playoff-series-study" / "data" / "raw" / "gamelogs"
URL = "https://raw.githubusercontent.com/shufinskiy/nba_data/main/datasets/{}.tar.xz"

# Archive years each dataset holds (checked against list_data.txt on
# October 19, 2026).
YEARS = {
    ("nba", "v3"): range(1996, 2026), ("wnba", "v3"): range(1997, 2027),
    ("nba", "pbpstats"): range(2000, 2025), ("wnba", "pbpstats"): range(2009, 2026),
}

KEEP = ["gameId", "actionNumber", "clock", "period", "teamId", "personId",
        "playerName", "playerNameI", "location", "actionType", "subType", "description",
        "shotResult", "isFieldGoal", "shotValue", "scoreHome", "scoreAway"]


def dataset(league: str, kind: str, year: int, stype: str = "rs") -> str:
    """Archive dataset name: ("nba", "v3", 1996) -> "nbastatsv3_1996";
    ("wnba", "pbpstats", 2009, "po") -> "wnba_pbpstats_po_2009"."""
    base = {"v3": "nbastatsv3", "pbpstats": "pbpstats"}[kind]
    prefix = "wnba_" if league == "wnba" else ""
    po = "_po" if stype == "po" else ""
    return f"{prefix}{base}{po}_{year}"


def season_label(league: str, year: int) -> str:
    return f"{year}-{(year + 1) % 100:02d}" if league == "nba" else str(year)


def gamelog_path(league: str, year: int, stype: str = "rs") -> Path:
    """LeagueGameLog file for an archive year. NBA files are named by the
    year the season ends, WNBA files by the season's only year."""
    end = year + 1 if league == "nba" else year
    return GAMELOG_DIR / f"{league}_{end}_{stype}.csv"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(name: str) -> Path:
    """Download one archive into raw/ unless it is already there, and record
    its sha256. An existing file whose hash differs from the manifest is an
    error: raw files are never replaced silently."""
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / f"{name}.tar.xz"
    manifest = RAW / "checksums.txt"
    known = {}
    if manifest.exists():
        for line in manifest.read_text().splitlines():
            digest, fname = line.split()
            known[fname] = digest
    if not path.exists():
        tmp = path.with_suffix(".part")
        with urllib.request.urlopen(URL.format(name), timeout=300) as r, open(tmp, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
        tmp.rename(path)
    digest = sha256(path)
    if path.name in known and known[path.name] != digest:
        raise SystemExit(f"{path.name}: sha256 differs from raw/checksums.txt")
    if path.name not in known:
        with open(manifest, "a") as f:
            f.write(f"{digest}  {path.name}\n")
    return path


def read_archive(name: str) -> pl.DataFrame:
    """The archive's one CSV, every column as text, read from the tar.xz
    without extracting to disk."""
    with tarfile.open(fetch(name)) as tar:
        raw = tar.extractfile(tar.getmember(f"{name}.csv")).read()
    return pl.read_csv(io.BytesIO(raw), infer_schema_length=0)


def prepare(df: pl.DataFrame) -> pl.DataFrame:
    """Typed V3 events in game-clock order with running scores.

    Order: period, then clock descending, then actionNumber, because the feed
    inserts late events with a high actionNumber but an early clock. Scores:
    the three rules described in the module docstring. Output columns:
    gameId (10-character text), actionNumber, period, secs_left, teamId,
    personId, playerName, playerNameI, location, actionType, subType, description,
    shotResult, isFieldGoal, shotValue, score_h, score_a, seq."""
    df = df.with_columns(pl.col("gameId").str.zfill(10))
    for c in KEEP:
        if c not in df.columns:
            df = df.with_columns(pl.lit(None, pl.Utf8).alias(c))
    df = df.select(KEEP).with_columns(pl.all().fill_null(""))
    # Right-padded labels ("Made Shot" plus 31 spaces in NBA 1996-97) would
    # slip past every exact match below.
    df = df.with_columns(pl.col("actionType", "subType", "location").str.strip_chars())
    mins = pl.col("clock").str.extract(r"PT(\d+)M", 1).cast(pl.Float64)
    secs = pl.col("clock").str.extract(r"M([\d.]+)S", 1).cast(pl.Float64)
    scoring = pl.col("actionType").is_in(["Made Shot", "Free Throw"])
    df = df.with_columns(
        scoreHome=pl.when(scoring & (pl.col("location") == "h"))
                    .then(pl.col("scoreHome")).otherwise(pl.lit("")),
        scoreAway=pl.when(scoring & (pl.col("location") == "v"))
                    .then(pl.col("scoreAway")).otherwise(pl.lit("")),
    )
    df = df.with_columns(
        period=pl.col("period").cast(pl.Int32),
        actionNumber=pl.col("actionNumber").cast(pl.Int64),
        secs_left=mins * 60 + secs,
        teamId=pl.col("teamId").cast(pl.Int64, strict=False).fill_null(0),
        personId=pl.col("personId").cast(pl.Int64, strict=False).fill_null(0),
        shotValue=pl.col("shotValue").cast(pl.Int32, strict=False).fill_null(0),
        isFieldGoal=pl.col("isFieldGoal").cast(pl.Int32, strict=False).fill_null(0),
        score_h=pl.when(pl.col("scoreHome") == "").then(None)
                  .otherwise(pl.col("scoreHome")).cast(pl.Int32, strict=False),
        score_a=pl.when(pl.col("scoreAway") == "").then(None)
                  .otherwise(pl.col("scoreAway")).cast(pl.Int32, strict=False),
    ).filter(pl.col("secs_left").is_not_null()).sort(
        ["gameId", "period", "secs_left", "actionNumber"],
        descending=[False, False, True, False])
    df = df.with_columns(
        score_h=pl.col("score_h").fill_null(0).cum_max().over("gameId"),
        score_a=pl.col("score_a").fill_null(0).cum_max().over("gameId"),
        seq=pl.int_range(pl.len()).over("gameId").cast(pl.Int32),
    )
    return df.drop("scoreHome", "scoreAway", "clock")


def read_gamelog(league: str, year: int, stype: str = "rs") -> pl.DataFrame:
    """One row per team-game from LeagueGameLog: gameId, team_id, abbr,
    game_date, PTS, AST, FGM. Sides are not read from MATCHUP, because
    neutral-site games ("MIA @ WAS" and "WAS @ MIA" in Mexico City,
    0022400147, and the NBA Cup semifinals in Las Vegas) list both teams with
    "@"; sides come from the event feed's location column instead."""
    gl = pl.read_csv(gamelog_path(league, year, stype), infer_schema_length=0)
    return gl.select(
        gameId=pl.col("GAME_ID").str.zfill(10),
        team_id=pl.col("TEAM_ID").cast(pl.Int64),
        abbr=pl.col("TEAM_ABBREVIATION"),
        game_date=pl.col("GAME_DATE"),
        PTS=pl.col("PTS").cast(pl.Int32),
        AST=pl.col("AST").cast(pl.Int32, strict=False),
        FGM=pl.col("FGM").cast(pl.Int32, strict=False),
    )


def sides(ev: pl.DataFrame) -> pl.DataFrame:
    """Home and away team IDs per game: the team most often on rows the feed
    marks "h" (or "v")."""
    def side(loc: str, name: str) -> pl.DataFrame:
        return (ev.filter((pl.col("location") == loc) & (pl.col("teamId") > 0))
                .group_by("gameId", "teamId").len()
                .sort(["gameId", "len", "teamId"], descending=[False, True, False])
                .group_by("gameId", maintain_order=True).first()
                .select("gameId", pl.col("teamId").alias(name)))
    return side("h", "home_id").join(side("v", "away_id"), on="gameId", how="full", coalesce=True)


def game_table(ev: pl.DataFrame, gl: pl.DataFrame) -> pl.DataFrame:
    """One row per game in the gamelog: date, sides, abbreviations, points,
    assists and field goals made, home and away (gl_h, gl_a, ast_h, ...)."""
    sd = sides(ev)
    g = gl.join(sd, on="gameId", how="left")
    h = g.filter(pl.col("team_id") == pl.col("home_id")).select(
        "gameId", "game_date", "home_id", "away_id", pl.col("abbr").alias("abbr_h"),
        pl.col("PTS").alias("gl_h"), pl.col("AST").alias("ast_h"), pl.col("FGM").alias("fgm_h"))
    a = g.filter(pl.col("team_id") == pl.col("away_id")).select(
        "gameId", pl.col("abbr").alias("abbr_a"), pl.col("PTS").alias("gl_a"),
        pl.col("AST").alias("ast_a"), pl.col("FGM").alias("fgm_a"))
    both = h.join(a, on="gameId", how="inner")
    # Games in the gamelog with no events still need a row (status no_events).
    missing = gl.select("gameId", "game_date").unique("gameId").join(both, on="gameId", how="anti")
    return pl.concat([both, missing], how="diagonal").sort("gameId")


def max_jump(ev: pl.DataFrame) -> pl.DataFrame:
    """Largest one-row rise in either side's running score, per game. No
    scoring row is worth more than 3, so a larger rise means a stamp that is
    wrong or a basket recorded without one. The running maximum hides such a
    stamp from the final whenever it is below the team's final score: in
    0021700025 a home stamp of 114 ninety seconds in froze the home score
    there until the real score passed it, and the final still matched."""
    s = ev.filter(pl.col("actionType").is_in(["Made Shot", "Free Throw"])
                  & pl.col("location").is_in(["h", "v"]))
    s = s.with_columns(sc=pl.when(pl.col("location") == "h").then(pl.col("score_h"))
                       .otherwise(pl.col("score_a")))
    s = s.with_columns(inc=pl.col("sc") - pl.col("sc").shift(1).over("gameId", "location").fill_null(0))
    return s.group_by("gameId").agg(pl.col("inc").max().alias("max_jump"))


def check_finals(ev: pl.DataFrame, gl: pl.DataFrame) -> pl.DataFrame:
    """One row per game in either table: the event feed's final against
    LeagueGameLog's. status is ok, score (both present, finals differ), jump
    (finals agree but a running score rises more than 3 on one row; see
    max_jump), no_events, or no_gamelog. Only ok games are fit for analysis."""
    fin = ev.group_by("gameId").agg(pl.col("score_h").last().alias("ev_h"),
                                    pl.col("score_a").last().alias("ev_a"),
                                    pl.len().alias("n_events"))
    if "actionType" in ev.columns:
        fin = fin.join(max_jump(ev), on="gameId", how="left")
    else:
        fin = fin.with_columns(max_jump=pl.lit(0))
    out = fin.join(gl, on="gameId", how="full", coalesce=True)
    return out.with_columns(status=pl.when(pl.col("n_events").is_null()).then(pl.lit("no_events"))
                            .when(pl.col("gl_h").is_null()).then(pl.lit("no_gamelog"))
                            .when((pl.col("ev_h") != pl.col("gl_h")) | (pl.col("ev_a") != pl.col("gl_a")))
                            .then(pl.lit("score"))
                            .when(pl.col("max_jump").fill_null(0) > 3).then(pl.lit("jump"))
                            .otherwise(pl.lit("ok"))).sort("gameId")


def events_path(league: str, year: int, stype: str = "rs") -> Path:
    return EVENTS / f"{league}_{year}_{stype}.parquet"


# League-seasons whose archive copy is partial, filled from playbyplay-study's
# per-game PlayByPlayV3 cache (harvested from stats.wnba.com before the host
# stopped answering). The archive's WNBA 2026 file was captured July 17, 2026:
# 182 of 330 regular-season games.
CACHE_DIR = FAMILY / "playbyplay-study" / "data" / "raw_pbp"
SUPPLEMENT = {("wnba", 2026, "rs"): "10226"}


def read_v3(league: str, year: int, stype: str = "rs") -> pl.DataFrame:
    df = read_archive(dataset(league, "v3", year, stype)).with_columns(
        pl.col("gameId").str.zfill(10))
    prefix = SUPPLEMENT.get((league, year, stype))
    if prefix:
        have = set(df["gameId"].unique())
        files = [p for p in sorted(CACHE_DIR.glob(f"{prefix}*.parquet")) if p.stem not in have]
        extra = [pl.read_parquet(p).select([c for c in KEEP if c in pl.read_parquet_schema(p)])
                 for p in files]
        if extra:
            df = pl.concat([df, *[e.with_columns(pl.all().cast(pl.Utf8)) for e in extra]],
                           how="diagonal")
    return df


def build(league: str, year: int, stype: str = "rs") -> dict:
    """Prepare one league-season, write events and the finals check, and
    return the check's counts."""
    ev = prepare(read_v3(league, year, stype))
    gl = game_table(ev, read_gamelog(league, year, stype))
    ev = ev.join(gl.select("gameId", "home_id", "away_id"), on="gameId", how="left")
    fin = check_finals(ev, gl)
    EVENTS.mkdir(parents=True, exist_ok=True)
    ev.write_parquet(events_path(league, year, stype))
    fin.write_csv(EVENTS / f"{league}_{year}_{stype}_finals.csv")
    counts = dict(fin.group_by("status").len().iter_rows())
    return {"league": league, "year": year, "season": season_label(league, year),
            "type": stype, "events": ev.height, **counts}


def load_events(league: str, years, stype: str = "rs", columns=None) -> pl.DataFrame:
    """Prepared events for several seasons, with a season label column.
    Builds any season not yet on disk."""
    frames = []
    for y in years:
        p = events_path(league, y, stype)
        if not p.exists():
            build(league, y, stype)
        df = pl.read_parquet(p, columns=columns)
        frames.append(df.with_columns(year=pl.lit(y, pl.Int32),
                                      season=pl.lit(season_label(league, y))))
    return pl.concat(frames, how="diagonal")


def load_finals(league: str, years, stype: str = "rs") -> pl.DataFrame:
    frames = []
    for y in years:
        p = EVENTS / f"{league}_{y}_{stype}_finals.csv"
        if not p.exists():
            build(league, y, stype)
        frames.append(pl.read_csv(p, schema_overrides={"gameId": pl.Utf8})
                      .with_columns(year=pl.lit(y, pl.Int32)))
    return pl.concat(frames, how="diagonal")


def parse_years(spec: str) -> list[int]:
    if "-" in spec:
        a, b = spec.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(y) for y in spec.split(",")]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="fetch and prepare league-seasons")
    b.add_argument("--league", choices=["nba", "wnba"], required=True)
    b.add_argument("--years", required=True, help="e.g. 1996-2025 or 2024,2025")
    b.add_argument("--types", nargs="+", default=["rs"], choices=["rs", "po"])
    b.add_argument("--force", action="store_true", help="rebuild even if present")
    sub.add_parser("status", help="finals-check counts for every built season")
    args = ap.parse_args(argv)
    if args.cmd == "build":
        for y in parse_years(args.years):
            for t in args.types:
                if events_path(args.league, y, t).exists() and not args.force:
                    print(f"{args.league} {y} {t}: present")
                    continue
                print(build(args.league, y, t), flush=True)
        return 0
    rows = []
    for f in sorted(EVENTS.glob("*_finals.csv")):
        league, year, stype = f.stem.split("_")[:3]
        fin = pl.read_csv(f, schema_overrides={"gameId": pl.Utf8})
        rows.append({"league": league, "year": int(year), "type": stype,
                     **dict(fin.group_by("status").len().iter_rows())})
    print(pl.DataFrame(rows).fill_null(0).sort("league", "year", "type"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
