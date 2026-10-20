"""Check every number in the family's prose against committed data.

The family's claim is that no number in a write-up is hand-maintained.
The Findings sections and marked README regions are script-WRITTEN by
each study's findings generator; this tool covers everything else the
generators cannot sensibly write (narrative story pages, BRIEFs, the
hand-written parts of READMEs, the hub README): it extracts every numeric
token from the prose and checks that it matches a value in the committed
outputs (or a data-file row count), to the precision the prose displays.

A document with a bindings file (number_bindings/, see number_bindings.py)
is checked exactly: every number in it is tied to one committed cell, and
the cell must display as the prose does, sign included. A number with no
binding fails. `python verify_numbers.py --propose <repo> <file>` drafts
bindings. Labels ("Game 7", "Question 4", "per 100", "95% interval") are
not claims and are not checked.

Documents without a bindings file are pool-matched, and what a pool match
proves is limited; the tool says how limited. A study's
files are matched against that study's git-tracked output CSVs only; the
hub and other non-study READMEs against every study's. A pool of
thousands of values matches many wrong numbers by chance, so each run
measures, per file, how often a nearby wrong number (each token moved by
1 to 9 units of its last displayed digit) would still pass, and prints
it. On 2026-10-18 the old family-wide pool (1,066,841 values, local
untracked files included) passed 400 of 400 random wrong numbers. Exact
per-number cell bindings are the planned replacement.

A token that matches nothing must be listed in an allowlist file with a
reason, or the check fails. Allowlists live in number_allowlists/ (a
private study's in its own number_checks/allowlists/) as
"<repo>__<filename>.txt", one entry per line: the token, two spaces, then
"# reason". "token @ text" scopes an entry to occurrences whose masked
context ends with text.

Run:  python verify_numbers.py            report per file
      python verify_numbers.py --check    gate mode (non-zero on failure)
"""
from __future__ import annotations

import bisect
import json
import math
import random
import re
import subprocess
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
import number_bindings as nb  # noqa: E402

REPO = Path(__file__).resolve().parent
SIBLINGS = REPO.parent
ALLOW_DIR = REPO / "number_allowlists"
BIND_DIR = REPO / "number_bindings"

STUDIES = ["jersey-height-study", "playbyplay-study", "tracking-study",
           "lineup-valuation-study", "shot-quality-study", "draft-study",
           "contract-year-study", "playoff-series-study", "elam-ending-study",
           "draft-potential-by-team"]
# A private study keeps its bindings and allowlists in its own repo, under
# number_checks/{bindings,allowlists}/, so this public repo never holds its
# prose or numbers. Any sibling with that folder is checked too.
STUDIES += sorted(d.parent.name for d in SIBLINGS.glob("*/number_checks")
                  if d.is_dir() and d.parent.name not in STUDIES)


def bind_dir(repo: str) -> Path:
    local = SIBLINGS / repo / "number_checks"
    return local / "bindings" if local.is_dir() else BIND_DIR


def allow_dir(repo: str) -> Path:
    local = SIBLINGS / repo / "number_checks"
    return local / "allowlists" if local.is_dir() else ALLOW_DIR

# files verified, as (repo, relative path)
FILES = ([(s, "docs/story.md") for s in STUDIES]
         + [(s, "BRIEF.md") for s in STUDIES]
         + [(s, "README.md") for s in STUDIES]
         + [("basketball-data-science", "README.md"),
            ("basketball-sql-layer", "README.md"),
            ("nba-scouting-onepagers", "README.md")])

YEAR = re.compile(r"^(19|20)\d{2}$")
SEASON = re.compile(r"^\d{4}-\d{2}$")
# ".44" (no leading zero) is a number too; it once went unchecked. A token
# never starts mid-number, inside a thousands group: "8,200-8,900" once
# yielded "900", which an allowlist entry for an unrelated 900 then covered
# ("0.23,1.20" still yields 1.20). The end of a hyphen range is a token when
# it has thousands commas or a decimal point ("tau 6.7-7.4"); a short whole
# number after a hyphen ("2015-16") stays a season label. A number after "number/" is a token too: ".91/.87" and
# "n=215/207" once checked only their first half.
TOKEN = re.compile(r"(?:(?<![\w./,-])|(?<=,)(?<!\d,)|(?<=\d,)(?!\d{3}(?![\d.]))"
                   r"|(?<=\d-)(?=\d{1,3},\d{3}|\d+\.\d)|(?<=[\d%]/)(?=\.?\d))"
                   r"[+\-−±~≈]{0,2}(\.\d+|\d[\d,]*\.?\d*(?:e-?\d+)?)"
                   r"(%|×|x\b)?")
# A year-shaped number followed by one of these is a count ("2000 series"),
# not a year, and is checked like any other number.
COUNT_NOUN = re.compile(
    r"\s+(series|games?|players?|teams?|shots?|possessions?|"
    r"attempts?|rows?|lineups?|picks?|contracts?|minutes|points|"
    r"team-seasons?|player-seasons?|stints?)\b", re.I)
# Numbers that name things rather than claim them: "Game 1", "Games 6 and
# 7", "Question 4", "#1", "per 100 possessions", and an interval's
# confidence level ("95% interval"). They have no cell to come from.
LABEL_BEFORE = re.compile(
    r"\b(Games?|Questions?|Amendments?|Figures?|Fig\.|Steps?|Parts?|Options?|"
    r"Tables?|Sections?|Findings?|Limitations?|Models?)\s+(\d+\s*(,|and|or|to|through|&)\s*)*$"
    r"|\bper\s+$|#$", re.I)
# A markdown list or heading number: "1. ", "### 2) " at the start of a line.
LIST_PREFIX = re.compile(r"[#>*\s-]*")
LEVEL_AFTER = re.compile(r"%?\s+(bootstrap\s+|percentile\s+)?(interval|CI|confidence|credible)", re.I)
PERTURB_PER_TOKEN = 5


class Pool:
    """Sorted numeric values with nearest-value lookups."""

    def __init__(self, values: set[float]):
        self.values = sorted(values)

    def __len__(self) -> int:
        return len(self.values)

    def near(self, x: float, tol: float) -> bool:
        i = bisect.bisect_left(self.values, x - tol)
        return i < len(self.values) and self.values[i] <= x + tol

    def any_between(self, lo: float, hi: float) -> bool:
        return self.near((lo + hi) / 2, (hi - lo) / 2)


def git_tracked(base: Path, sub: str) -> list[Path]:
    """Files under base/sub that git tracks. Fails loudly outside a repo."""
    r = subprocess.run(["git", "-C", str(base), "ls-files", "-z", sub],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"git ls-files failed in {base}: {r.stderr.strip()}")
    return sorted(base / p for p in r.stdout.split("\0") if p)


def csv_values(files: list[Path], unreadable: list[str]) -> set[float]:
    vals: set[float] = set()
    for f in files:
        try:
            df = pl.read_csv(f, infer_schema_length=500, ignore_errors=True)
        except Exception as e:  # noqa: BLE001 - reported, never skipped quietly
            unreadable.append(f"{f.relative_to(SIBLINGS)} ({type(e).__name__})")
            continue
        vals.update({float(df.height), float(df.height + 1),
                     float(df.height - 1)})
        for col in df.columns:
            ser = df[col]
            if ser.dtype.is_numeric():
                vals.update(float(v) for v in ser.drop_nulls()
                            if math.isfinite(float(v)))
    return vals


def raw_study_values(study: str, unreadable: list[str]) -> set[float]:
    """The study's git-tracked output CSVs, plus data-file row counts for
    corpus-size claims (data/ is often gitignored; only counts are used)."""
    base = SIBLINGS / study
    tracked = [f for f in git_tracked(base, "output") if f.suffix == ".csv"]
    vals = csv_values(tracked, unreadable)
    # Row counts of the built tables directly in data/ and of every tracked
    # data file. Raw downloads in data/raw/ are left out; a capped recursive
    # listing once sorted data/stints_2023.parquet behind 120 raw files and
    # dropped it.
    data = {f for f in (base / "data").glob("*") if f.suffix in (".csv", ".parquet")}
    data |= {f for f in git_tracked(base, "data") if f.suffix in (".csv", ".parquet")}
    for f in sorted(data):
        try:
            if f.suffix == ".csv":
                n = sum(1 for _ in open(f, "rb"))
                vals.update({float(n), float(n - 1)})
            else:
                vals.add(float(pl.scan_parquet(f).select(pl.len()).collect()[0, 0]))
        except Exception as e:  # noqa: BLE001 - reported, never skipped quietly
            unreadable.append(f"{f.relative_to(SIBLINGS)} (row count, {type(e).__name__})")
    return vals


def with_scaled(vals: set[float]) -> Pool:
    # Prose drops a number's sign (TOKEN keeps only the digits), so every
    # variant is added at both signs: -0.0655 must match "6.55".
    scaled = set()
    for v in vals:
        scaled.update({v * 100, -v * 100, -v})
        if abs(v) >= 1e5:
            scaled.update({v / 1e6, -v / 1e6})
    return Pool(vals | scaled)


def build_pools(studies: list[str]) -> tuple[dict[str, Pool], Pool, list[str]]:
    """One pool per study, the union for non-study files, and any CSV that
    could not be read (printed by main, never dropped silently)."""
    unreadable: list[str] = []
    raw = {s: raw_study_values(s, unreadable) for s in studies
           if (SIBLINGS / s).exists()}
    union: set[float] = set().union(*raw.values()) if raw else set()
    return ({s: with_scaled(v) for s, v in raw.items()}, with_scaled(union),
            unreadable)


GEN_REGION = re.compile(r"<!-- gen:([\w-]+) -->.*?<!-- /gen:\1 -->", re.S)


def generator_owned(text: str) -> int:
    """Tokens inside <!-- gen:NAME --> regions. Each study's findings
    generator writes those and its --check (run by run_checks.sh under
    pipefail) is their exact gate, so they are not matched here."""
    return sum(len(tokens_of_prose(m.group(0))) for m in GEN_REGION.finditer(text))


def strip_nonprose(text: str) -> str:
    text = GEN_REGION.sub("", text)
    text = re.sub(r"<!-- terms -->.*?<!-- /terms -->", "", text, flags=re.S)
    text = re.sub(r'<abbr title="[^"]*">', "", text)
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`[^`]*`", "", text)
    text = re.sub(r"\]\([^)]*\)", "]", text)          # link targets
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\{\{fig:[^|]*\|", "", text)       # keep caption text
    text = re.sub(r"\{\{svg:[^|]*\|", "", text)       # diagrams, same
    return text


def tokens_of(text: str) -> list[str]:
    """Numeric tokens in the prose a person typed (generator regions out)."""
    return tokens_of_prose(strip_nonprose(text))


def tokens_of_prose(prose: str) -> list[str]:
    return [o["token"] for o in occurrences_of_prose(prose)]


def occurrences(text: str) -> list[dict]:
    """Each checked number with its displayed sign, the prose before it, and
    (internal, "_pos") its offset in the stripped prose."""
    return occurrences_of_prose(strip_nonprose(text))


def occurrences_of_prose(prose: str) -> list[dict]:
    out = []
    for m in TOKEN.finditer(prose):
        # "In 2010, ..." and "1,350." end in sentence punctuation, not digits.
        num, suffix = m.group(1).rstrip(",."), m.group(2) or ""
        if YEAR.match(num) and not suffix and not COUNT_NOUN.match(prose, m.end()):
            continue
        # "2-for-1" names a strategy; its 2 is not a count.
        if prose[m.end():m.end() + 5] == "-for-":
            continue
        # A number glued to letters ("3PA", "12th") is part of a name. Checked
        # here, not in TOKEN: a regex lookahead backtracks "1990s" to "199".
        if not suffix and prose[m.end():m.end() + 1].isalpha():
            continue
        raw = num + suffix
        ctx = prose[max(0, m.start() - 1):m.end() + 3]
        if SEASON.match(ctx.strip()):
            continue
        lead = prose[m.start():m.start(1)]
        line = prose[prose.rfind("\n", 0, m.start()) + 1:m.start()]
        if (not lead and m.group(1).endswith(".") and LIST_PREFIX.fullmatch(line)
                and prose[m.end():m.end() + 1] in (" ", "")) or (
                not lead and LIST_PREFIX.fullmatch(line) and prose[m.end():m.end() + 2] == ") "):
            continue
        if not lead and (LABEL_BEFORE.search(prose[max(0, m.start() - 40):m.start()])
                         or (suffix == "%" and LEVEL_AFTER.match(prose, m.end()))):
            continue
        sign = "-" if ("−" in lead or "-" in lead) else "+" if "+" in lead else ""
        out.append({"token": raw, "sign": sign, "before": context(prose[max(0, m.start() - 80):m.start()]),
                    "_pos": m.start()})
    # Table cells can share token and masked context ("38" in three rows);
    # nth numbers the repeats in reading order so each gets its own binding.
    seen: dict = {}
    for o in out:
        k = (o["token"], o["sign"], o["before"])
        o["nth"] = seen.get(k, 0)
        seen[k] = o["nth"] + 1
    return out


FINDINGS_MARKER = "## Findings"
GATE_LINE = re.compile(r"python/(\S*findings\S*\.py) --check")


def gated_generator(base: Path) -> Path | None:
    """The findings generator whose --check run_checks.sh runs, if any. Its
    README section from "## Findings" on is written from outputs and gated
    exactly, except numbers typed into its template."""
    rc = base / "run_checks.sh"
    m = GATE_LINE.search(rc.read_text()) if rc.exists() else None
    return base / "python" / m.group(1) if m else None


# Stands in for each {...} of a template so contexts mask as the README's do.
PLACEHOLDER = "9.87654321"


def template_literals(generator: Path) -> set[tuple[str, str]]:
    """(token, masked context) of numbers typed into a generator's
    triple-quoted templates outside {...}: a --check passes them whether or
    not they are true. Context is part of the key, so a typed list marker
    "1." does not cover a computed count that happens to be 1."""
    lits: set[tuple[str, str]] = set()
    for m in re.finditer(r'f?"""(.*?)"""', generator.read_text(), re.S):
        # A percent format ("{p1:.1%}") prints its own "%"; keep it so the
        # context reads "#% at pick" as the README does.
        body = strip_nonprose(re.sub(r"\{[^{}]*\}", lambda b: PLACEHOLDER + ("%" if b.group(0).endswith("%}") else ""),
                                     m.group(1)))
        lits |= {(o["token"], o["before"]) for o in occurrences_of_prose(body)
                 if o["token"] != PLACEHOLDER}
    return lits


def checked_occurrences(base: Path, rel: str, text: str) -> tuple[list[dict], int]:
    """The occurrences this gate must check, and how many it leaves to a
    gated generator. In a README whose Findings section a generator --check
    covers, computed Findings numbers are left to it; template literals and
    everything before the section stay here."""
    occ = occurrences(text)
    skipped = 0
    gen = gated_generator(base) if rel == "README.md" else None
    if gen is not None and gen.exists():
        cut = strip_nonprose(text).find(FINDINGS_MARKER)
        if cut >= 0:
            lits = template_literals(gen)
            kept = [o for o in occ if o["_pos"] < cut or (o["token"], o["before"]) in lits]
            skipped = len(occ) - len(kept)
            occ = kept
    return [{k: v for k, v in o.items() if k != "_pos"} for o in occ], skipped


def context(before: str) -> str:
    """The last 30 characters ahead of a number, numbers masked as #, so
    editing one number does not orphan the binding of the next."""
    masked = re.sub(r"[+\-−]?\d[\d,.]*", "#", " ".join(before.split()))
    return masked[-30:]


def matches(tok: str, pool: Pool) -> bool:
    pct = tok.endswith("%")
    t = tok.rstrip("%×x").replace(",", "")
    try:
        f = float(t)
    except ValueError:
        return True
    if "e" in t:      # order-of-magnitude claims like ~2e-13
        if f == 0:
            return False
        lo, hi = abs(f) / 10 ** 0.51, abs(f) * 10 ** 0.51
        return pool.any_between(lo, hi) or pool.any_between(-hi, -lo)
    dec = len(t.split(".")[1]) if "." in t else 0
    tol = 0.5 * 10 ** -dec + 1e-12
    if pool.near(f, tol):
        return True
    # A percentage may be stored as a proportion.
    return pct and pool.near(f / 100, tol / 100)


def perturbed(tok: str, rng: random.Random) -> list[str]:
    """Nearby wrong versions of tok: same format, moved 1 to 9 units of the
    last displayed digit. Empty for tokens that cannot be perturbed."""
    pct = tok.endswith("%")
    t = tok.rstrip("%×x").replace(",", "")
    if "e" in t:
        return []
    try:
        f = float(t)
    except ValueError:
        return []
    dec = len(t.split(".")[1]) if "." in t else 0
    out = []
    for _ in range(PERTURB_PER_TOKEN):
        k = rng.choice([-1, 1]) * rng.randint(1, 9)
        out.append(f"{f + k * 10 ** -dec:.{dec}f}" + ("%" if pct else ""))
    return out


def wrong_pass_rate(tokens: list[str], pool: Pool, seed: str) -> float | None:
    """Share of nearby wrong numbers the pool would still accept."""
    rng = random.Random(seed)
    trials = [p for tok in tokens for p in perturbed(tok, rng)]
    if not trials:
        return None
    return sum(matches(p, pool) for p in trials) / len(trials)


def allowed_reason(occ: dict, allowed: dict) -> str | None:
    """The allowlist line covering this occurrence: a plain "token" entry, or
    a scoped "token @ text" entry whose text ends the occurrence's masked
    context, right before the number ("1 @ at pick" covers "at pick 1" and
    not quintile 1)."""
    if occ["token"] in allowed:
        return allowed[occ["token"]]
    for key, line in allowed.items():
        tok, _, scope = key.partition(" @ ")
        if scope and tok == occ["token"] and occ["before"].rstrip().endswith(scope):
            return line
    return None


def allowlist_for(repo: str, rel: str) -> dict[str, str]:
    f = allow_dir(repo) / f"{repo}__{rel.replace('/', '_')}.txt"
    allowed: dict[str, str] = {}
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                # Two spaces end the token: a scoped entry's masked context
                # contains "#" itself ("12 @ between pick # and pick  # why").
                tok = line.split("  #")[0].strip()
                allowed[tok] = line
    return allowed


def repo_base(repo: str) -> Path:
    # The hub is cloned as "basketball-data-science" but checked out as
    # "hub" in the development tree; resolve to whichever exists, the way
    # report_builder.build_hub() and glossary.py do. Without this the hub
    # README silently fell out of the gate and its numbers went unchecked.
    base = SIBLINGS / repo
    if repo == "basketball-data-science" and not base.exists():
        base = SIBLINGS / "hub"
    return base


def tracked_tables(base: Path) -> list[str]:
    return [str(p.relative_to(base)) for p in git_tracked(base, "output") if p.suffix == ".csv"]


def check_bound(repo: str, rel: str, text: str, allowed: dict,
                unverified: list[str]) -> tuple[int, list[str]]:
    """Strict check of a document with a bindings file: every number is
    allowlisted or bound to a tracked cell that displays exactly as it does."""
    base = repo_base(repo)
    bindings = nb.load(nb.path_for(bind_dir(repo), repo, rel))
    tracked = set(tracked_tables(base))
    cache: dict = {}
    problems, bound = [], 0
    occs, _ = checked_occurrences(base, rel, text)
    for occ in occs:
        reason = allowed_reason(occ, allowed)
        if reason is not None:
            if "UNVERIFIED" in reason:
                unverified.append(f"{repo}/{rel}: {occ['token']}")
            continue
        b = nb.find(bindings, occ)
        where = f"{occ['sign']}{occ['token']} after \"{occ['before']}\""
        if b is None:
            was = nb.find_by_context(bindings, occ)
            if was is not None:
                problems.append(f"{where}: changed; the cell bound here gives "
                                f"{nb.expected(base, was, cache)} (prose had {was['sign']}{was['token']})")
            else:
                problems.append(f"unbound {where}")
        elif b.get("auto"):
            problems.append(f"{where}: drafted by --propose and not yet reviewed; confirm "
                            f"{b['table']} {b['where']} {b['column']} and delete \"auto\"")
        elif not nb.sources_tracked(b, tracked, lambda r: set(tracked_tables(SIBLINGS / r))):
            problems.append(f"{where}: {nb.tables_of(b)} not all tracked outputs")
        elif (why := nb.check(base, b, cache)) is not None:
            problems.append(f"{where}: {why}")
        else:
            bound += 1
    return bound, problems


def propose_cli(repo: str, rel: str) -> int:
    base = repo_base(repo)
    path = nb.path_for(bind_dir(repo), repo, rel)
    occs, _ = checked_occurrences(base, rel, (base / rel).read_text())
    bound, open_items = nb.propose(base, tracked_tables(base), occs, nb.load(path),
                                   allowlist_for(repo, rel), allowed_reason)
    path.parent.mkdir(parents=True, exist_ok=True)
    nb.save(path, bound)
    prop = path.with_suffix(".proposals.json")
    if open_items:
        prop.write_text(json.dumps(open_items, indent=1, ensure_ascii=False) + "\n")
    elif prop.exists():
        prop.unlink()
    print(f"{repo}/{rel}: {len(bound)} bound, {len(open_items)} open"
          f"{f' (see {prop.name})' if open_items else ''}")
    return 0


def unused_entries() -> list[str]:
    """Allowlist entries and bindings that no checked number uses."""
    out = []
    for repo, rel in FILES:
        base = repo_base(repo)
        if not (base / rel).exists():
            continue
        occs, _ = checked_occurrences(base, rel, (base / rel).read_text())
        for key, line in allowlist_for(repo, rel).items():
            if not any(allowed_reason(o, {key: line}) for o in occs):
                out.append(f"{repo}/{rel} allowlist {key}")
        for b in nb.load(nb.path_for(bind_dir(repo), repo, rel)):
            if not any(nb.find([b], o) for o in occs):
                out.append(f"{repo}/{rel} binding {b['sign']}{b['token']}")
    return out


def main(argv: list[str]) -> int:
    if argv[:1] == ["--propose"]:
        if len(argv) != 3:
            raise SystemExit("usage: verify_numbers.py --propose <repo> <file>")
        return propose_cli(argv[1], argv[2])
    pools, union, unreadable = build_pools(STUDIES)
    failures: list[str] = []
    skipped: list[str] = []
    rates: list[tuple[float, str]] = []
    unverified: list[str] = []
    checked = files_n = strict_n = bound_n = 0
    for repo, rel in FILES:
        base = repo_base(repo)
        path = base / rel
        if not path.exists():
            skipped.append(f"{repo}/{rel}")
            continue
        files_n += 1
        allowed = allowlist_for(repo, rel)
        name = f"{repo}/{rel}"
        if nb.path_for(bind_dir(repo), repo, rel).exists():
            text = path.read_text()
            n, problems = check_bound(repo, rel, text, allowed, unverified)
            checked += len(checked_occurrences(base, rel, text)[0])
            strict_n += 1
            bound_n += n
            print(f"  {name}: {n} bound, exact check")
            if problems:
                problems.append(f"to rebind after an intended edit: python verify_numbers.py "
                                f"--propose {repo} {rel}, then settle number_bindings/"
                                f"{nb.path_for(bind_dir(repo), repo, rel).with_suffix('.proposals.json').name}")
                failures.append(f"{name}:\n      " + "\n      ".join(problems))
            continue
        pool = pools.get(repo, union)
        occs, gen_skipped = checked_occurrences(base, rel, path.read_text())
        toks = [o["token"] for o in occs]
        unmatched = []
        for tok in toks:
            checked += 1
            if tok in allowed:
                if "UNVERIFIED" in allowed[tok]:
                    unverified.append(f"{repo}/{rel}: {tok}")
                continue
            if not matches(tok, pool):
                unmatched.append(tok)
        rate = wrong_pass_rate([t for t in toks if t not in allowed], pool,
                               f"{repo}/{rel}")
        if rate is not None:
            rates.append((rate, name))
        gen = generator_owned(path.read_text()) + gen_skipped
        print(f"  {name}: {len(toks)} tokens"
              f"{f' (+{gen} in generator regions, gated by the generator)' if gen else ''}, "
              f"pool {len(pool):,} values, "
              f"wrong-number pass rate "
              f"{'n/a' if rate is None else f'{rate:.0%}'}")
        if unmatched:
            failures.append(f"{name}: " + ", ".join(sorted(set(unmatched))))
    if skipped:
        # Say so out loud. A gate that quietly drops a target reads exactly
        # like a gate that checked it.
        print(f"skipped {len(skipped)} declared file(s) not in this "
              f"checkout: {', '.join(skipped)}")
    if unreadable:
        print(f"could not read {len(unreadable)} tracked output file(s); "
              f"their values are not in the pool: {', '.join(unreadable)}")
    stale = unused_entries()
    if stale:
        # Not a failure: an entry that covers nothing hides nothing, but it
        # misstates what the allowlist or bindings vouch for.
        print(f"{len(stale)} allowlist or binding entr(ies) match no number any more: "
              f"{'; '.join(stale)}")
    if unverified:
        # Allowlisted with an UNVERIFIED reason: passed, but checked by nobody.
        print(f"{len(unverified)} allowlisted token(s) are marked UNVERIFIED "
              f"(no committed source): {'; '.join(unverified)}")
    if failures:
        print(f"NUMBER VERIFICATION FAILED "
              f"({len(failures)} files with unmatched tokens):")
        for f in failures:
            print("  " + f)
        return 1
    rates.sort()
    median = rates[len(rates) // 2][0] if rates else float("nan")
    worst = rates[-1] if rates else (float("nan"), "none")
    pool_note = (f" The other {files_n - strict_n} files are pool-matched, "
                 f"weak evidence: a nearby wrong number would pass {median:.0%} of "
                 f"the time (median file), {worst[0]:.0%} in {worst[1]}."
                 if rates else " No file is pool-matched.")
    print(f"NUMBER CHECK PASSED ({checked} numeric tokens across {files_n} "
          f"files; {strict_n} files bound exactly ({bound_n} numbers tied to "
          f"one committed cell each); {len(unverified)} tokens allowlisted as "
          f"UNVERIFIED).{pool_note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
