1,230  # games in a 30-team, 82-game season (30 x 82 / 2), a schedule fact
2  # UNVERIFIED: "±2-3" is a stated rough bracket of the per-season median CI half-widths, 2.5 (2023-24) and 2.6 (2025-26); kept as a range by decision (2026-10-18); also a literal in 04_findings.py
1,200  # UNVERIFIED: games covered by an earlier stint build, a historical value no committed output keeps (a literal in 04_findings.py)
2,000  # the LeagueDashLineups row cap, an outside fact about the API
900  # an illustrative lineup size in the weighting explanation, not a result
900×  # an illustrative weight ratio in the weighting explanation, not a result
1  # the 1-possession comparison lineup, the +1/-1 design encoding, and the "not 1" correlation reference, labels
5  # cross-validation folds, the fold rule (row index mod 5), and "Top 5", settings and labels
300  # replacement-pool possession threshold, a setting
500  # bootstrap resamples, a setting
200  # possession filter for the NET_RATING correlation check and the regression, a setting
100  # "per 100 possessions" in table headers, a unit label
1.0  # a perfect correlation as the reference point, a label
82  # games in a season, a schedule fact
19 @ **Correction, October  # a date (the stint correction, October 19, 2026)
19 @ of the same lineups (October  # a date (the pbpstats check, October 19, 2026)
19 @ One more gate, added October  # a date (the pbpstats check, October 19, 2026)
19 @ the possession gap (October  # a date (the pbpstats check, October 19, 2026)
50  # possession floor for the POSS identity check and the small-lineup bin in 11_poss_gap.py, a setting
0 @ used exactly once carry  # a bin label ("0 or 1 extra possession"), a literal in 04_findings.py
