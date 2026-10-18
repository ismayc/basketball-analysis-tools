0.999  # UNVERIFIED: pending a decision (asked 2026-10-18): a literal in 04_findings.py; stint_validation.csv has on-floor minutes r = 0.99997, which shows as 1.000 at three decimals
1,230  # games in a 30-team, 82-game season (30 x 82 / 2), a schedule fact
1.001  # UNVERIFIED: pending a decision (asked 2026-10-18): the net_100 vs NET_RATING regression slope; no committed output keeps it, so binding needs a new output table
0.07  # UNVERIFIED: pending a decision (asked 2026-10-18): the net_100 vs NET_RATING regression intercept; no committed output keeps it, so binding needs a new output table
15,900  # UNVERIFIED: pending a decision (asked 2026-10-18): 2023-24 lineup rows; lineup_table.csv keeps only the top lineups, so binding needs a new output table
19,500  # UNVERIFIED: pending a decision (asked 2026-10-18): 2025-26 lineup rows; lineup_table.csv keeps only the top lineups, so binding needs a new output table
8,200  # UNVERIFIED: pending a decision (asked 2026-10-18): low end of per-team POSS sums over all lineups; no committed output keeps them, so binding needs a new output table
800  # UNVERIFIED: pending a decision (asked 2026-10-18): high end (8,800) of per-team POSS sums over all lineups; no committed output keeps them, so binding needs a new output table
0.95  # UNVERIFIED: pending a decision (asked 2026-10-18): "lands within Spearman 0.95"; stint_validation.csv gives 0.958, which shows as 0.96 (the story and BRIEF say 0.96)
2  # UNVERIFIED: pending a decision (asked 2026-10-18): "±2-3" brackets the per-season median CI half-widths, 2.5 (2023-24) and 2.6 (2025-26); also a literal in 04_findings.py
1,200  # UNVERIFIED: games covered by an earlier stint build, a historical value no committed output keeps (a literal in 04_findings.py)
2,000  # the LeagueDashLineups row cap, an outside fact about the API
900  # an illustrative lineup size in the weighting explanation, not a result
900×  # an illustrative weight ratio in the weighting explanation, not a result
1  # the 1-possession comparison lineup, the +1/-1 design encoding, and the "not 1" correlation reference, labels
5  # cross-validation folds, the fold rule (row index mod 5), and "Top 5", settings and labels
300  # replacement-pool possession threshold, a setting
500  # bootstrap resamples, a setting
200  # possession filter for the NET_RATING correlation check, a setting
100  # "per 100 possessions" in table headers, a unit label
1.0  # a perfect correlation as the reference point, a label
82  # games in a season, a schedule fact
