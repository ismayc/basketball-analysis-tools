"""Build the family's GitHub Pages sites: one styled analysis page per
study (docs/index.html rendered from its README plus embedded interactive
figures), a card-grid landing page for the hub, and an index for the
scouting one-pagers.

The pages aim at the register of a professional analytics group or a data
journalist's methods page: restrained neutral chrome, one accent, a wide
readable measure, tables that scroll rather than overflow, the family's
glossary tooltips carried through, and the interactive plotly figures
embedded as cards. Light and dark are both first-class; figures stay on
white cards in both (they are rendered on a white template).

Run: python report_builder.py --all         every repo's docs/
     python report_builder.py <repo> ...    just those repos
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

import glossary
import markdown

REPO = Path(__file__).resolve().parent
SIBLINGS = REPO.parent
GH = "https://github.com/ismayc"
PAGES = "https://ismayc.github.io"

STUDIES = ["jersey-height-study", "playbyplay-study", "tracking-study",
           "lineup-valuation-study", "shot-quality-study", "draft-study"]

# Hub landing-page config: repo -> (kicker, one-line headline)
HUB_CARDS = {
    "jersey-height-study": (
        "45 seasons of rosters",
        "The “players are getting shorter” trend is ~70% a 2019 "
        "measurement-rule change."),
    "playbyplay-study": (
        "Full 2023-24 play-by-play",
        "The 2-for-1 adds a real possession at no shot-quality cost, "
        "and ~+0.2 net points, indistinguishable from zero."),
    "tracking-study": (
        "7.5M frames of raw SportVU",
        "A 2.5–6s scorer's-table latency fabricates findings if "
        "unhandled; the possession join is validated at 97.5%."),
    "lineup-valuation-study": (
        "Every five-man lineup, two seasons",
        "RAPM-family player and lineup value with exact team-total "
        "reconstruction and honest error bars."),
    "shot-quality-study": (
        "218,701 shots (+ G League, + WNBA)",
        "Shot selection repeats (r ≈ .9); shot-making half-repeats "
        "(r ≈ .6). The EB projection built on that beats naive "
        "carry-forward by ~10%."),
    "draft-study": (
        "56,781 college player-seasons",
        "On held-out drafts, college box scores add nothing beyond the "
        "pick: the scouts already priced them in."),
}

CSS = """
:root {
  --ink: #1a1d24; --ink-2: #4a4f5c; --ink-3: #767b88;
  --surface: #ffffff; --surface-2: #f5f6f8; --rule: #e3e5ea;
  --accent: #1452cc; --accent-ink: #1452cc;
}
@media (prefers-color-scheme: dark) {
  :root {
    --ink: #e8eaf0; --ink-2: #b5bac6; --ink-3: #878d9c;
    --surface: #14161c; --surface-2: #1d2029; --rule: #2c303c;
    --accent: #6f9bff; --accent-ink: #8db0ff;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--surface); color: var(--ink);
  font: 17px/1.65 -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; }
.masthead { border-bottom: 1px solid var(--rule); }
.masthead .inner { width: min(1200px, 94vw); margin: 0 auto; padding: .8rem 0;
  display: flex; gap: 1rem; align-items: baseline; flex-wrap: wrap; }
.masthead a { color: var(--ink-2); text-decoration: none; font-size: .88rem; }
.masthead a:hover { color: var(--accent-ink); }
.masthead .family { font-weight: 700; letter-spacing: .02em; color: var(--ink); }
.masthead .spacer { flex: 1; }
main { width: min(1200px, 94vw); margin: 0 auto; padding: 1.5rem 0 4rem; }
h1 { font-size: 2rem; line-height: 1.2; letter-spacing: -.01em;
  margin: 1.2rem 0 .6rem; }
h2 { font-size: 1.35rem; margin: 2.2rem 0 .6rem; padding-top: 1rem;
  border-top: 1px solid var(--rule); }
h3 { font-size: 1.08rem; margin: 1.6rem 0 .4rem; }
a { color: var(--accent-ink); text-decoration-thickness: 1px;
  text-underline-offset: 2px; }
p, li { color: var(--ink); }
code { background: var(--surface-2); border: 1px solid var(--rule);
  border-radius: 4px; padding: .08em .35em; font-size: .86em; }
pre { background: var(--surface-2); border: 1px solid var(--rule);
  border-radius: 8px; padding: .8rem 1rem; overflow-x: auto; }
pre code { background: none; border: none; padding: 0; }
blockquote { margin: 1.2rem 0; padding: .8rem 1.1rem;
  background: var(--surface-2); border-left: 3px solid var(--accent);
  border-radius: 0 8px 8px 0; font-size: .92rem; }
blockquote p { margin: .3rem 0; }
.tablewrap { overflow-x: auto; margin: 1rem 0; }
table { border-collapse: collapse; width: 100%; font-size: .9rem;
  font-variant-numeric: tabular-nums; }
th { text-align: left; color: var(--ink-2); font-weight: 600;
  border-bottom: 2px solid var(--rule); padding: .4rem .6rem; }
td { border-bottom: 1px solid var(--rule); padding: .4rem .6rem;
  vertical-align: top; }
abbr[title] { text-decoration: underline dotted var(--accent);
  text-underline-offset: 2px; cursor: help; }
hr { border: none; border-top: 1px solid var(--rule); margin: 2rem 0; }
.figure-card { background: #fff; border: 1px solid var(--rule);
  border-radius: 10px; margin: 1.4rem 0; overflow: hidden; }
.figure-card iframe { display: block; width: 100%; height: 560px;
  border: none; }
.figure-card figcaption { padding: .55rem .9rem; font-size: .85rem;
  color: var(--ink-3); border-top: 1px solid var(--rule);
  background: var(--surface); }
footer { border-top: 1px solid var(--rule); margin-top: 3rem;
  padding: 1rem 1.25rem; font-size: .85rem; color: var(--ink-3);
  text-align: center; }
footer a { color: var(--ink-2); }
details.terms { margin: 1rem 0; border: 1px solid var(--rule);
  border-radius: 8px; background: var(--surface-2); font-size: .9rem; }
details.terms summary { padding: .55rem .9rem; cursor: pointer;
  color: var(--ink-2); font-weight: 600; }
details.terms ul { margin: 0; padding: .2rem 1.4rem .8rem; }
details.terms li { margin: .3rem 0; color: var(--ink-2); }
/* hub cards */
.cards { display: grid; grid-template-columns:
  repeat(auto-fit, minmax(290px, 1fr)); gap: 1rem; margin: 1.5rem 0; }
.card { border: 1px solid var(--rule); border-radius: 10px;
  padding: 1rem 1.1rem; background: var(--surface-2);
  display: flex; flex-direction: column; gap: .45rem; }
.card .kicker { font-size: .78rem; text-transform: uppercase;
  letter-spacing: .06em; color: var(--ink-3); }
.card h3 { margin: 0; font-size: 1.05rem; }
.card p { margin: 0; font-size: .92rem; color: var(--ink-2); flex: 1; }
.card .links { font-size: .88rem; }
.hero { padding: 2.2rem 0 .6rem; }
.hero p.deck { font-size: 1.12rem; color: var(--ink-2); }
"""


def page(title: str, body: str, deck: str = "") -> str:
    desc = f'<meta name="description" content="{deck}">' if deck else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
{desc}
<style>{CSS}</style>
</head>
<body>
<header class="masthead"><div class="inner">
  <a class="family" href="{PAGES}/basketball-data-science/">Basketball Data Science</a>
  <span class="spacer"></span>
  <a href="{PAGES}/nba-scouting-onepagers/">Scouting one-pagers</a>
  <a href="{GH}/basketball-data-science">GitHub</a>
</div></header>
<main>
{body}
</main>
<footer>Public data · dual-implementation reconciled · every gate scripted ·
<a href="{GH}/basketball-data-science">the family on GitHub</a></footer>
</body>
</html>
"""


def absolutize_links(html: str, repo: str) -> str:
    """Relative README links (files in the repo) -> GitHub blob URLs."""
    def fix(m: re.Match) -> str:
        href = m.group(1)
        if href.startswith(("http", "#", "mailto:")):
            return m.group(0)
        return f'href="{GH}/{repo}/blob/main/{href}"'
    return re.sub(r'href="([^"]+)"', fix, html)


def wrap_tables(html: str) -> str:
    return (html.replace("<table>", '<div class="tablewrap"><table>')
            .replace("</table>", "</table></div>"))


def caption_from(stem: str) -> str:
    s = re.sub(r"^fig\d+_", "", stem)
    s = re.sub(r"_(py|r)$", "", s)
    return s.replace("_", " ").capitalize()


RESPONSIVE_SNIPPET = """<script>
window.addEventListener("load", function () {
  var gs = document.querySelectorAll(".plotly-graph-div");
  function fit() { gs.forEach(function (g) {
    Plotly.relayout(g, {autosize: true, width: null, height: null}); }); }
  fit(); window.addEventListener("resize", fit);
});
</script>"""


def make_figure_responsive(text: str) -> str:
    """The studies' write_html output pins the outer div to the figure's
    layout size (e.g. 900x620). Let the embedded copy fill its iframe and
    follow resizes instead; the committed originals stay untouched."""
    text = re.sub(r'style="height:\d+px; width:\d+px;"',
                  'style="height:100%; width:100%;"', text, count=1)
    text = text.replace("<head>",
                        "<head><style>html,body{margin:0;height:100%}</style>",
                        1)
    if "</body>" in text:
        text = text.replace("</body>", RESPONSIVE_SNIPPET + "</body>", 1)
    else:
        text += RESPONSIVE_SNIPPET
    return text


def figures_section(repo_dir: Path, docs: Path) -> str:
    """Copy each interactive figure into docs/figures and embed it."""
    figs = sorted(p for p in (repo_dir / "figures").rglob("*.html")
                  if not p.stem.endswith("_r"))
    if not figs:
        return ""
    out = ["<h2>Interactive figures</h2>",
           "<p>Rendered by the Python implementation; hover for values. "
           "Static R twins live in the repo.</p>"]
    for f in figs:
        rel = f.relative_to(repo_dir / "figures")
        dest = docs / "figures" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(make_figure_responsive(f.read_text()))
        season = f" ({rel.parts[0]})" if len(rel.parts) > 1 else ""
        out.append(
            f'<figure class="figure-card">'
            f'<iframe src="figures/{rel.as_posix()}" loading="lazy" '
            f'title="{caption_from(f.stem)}"></iframe>'
            f'<figcaption>{caption_from(f.stem)}{season}</figcaption>'
            f'</figure>')
    return "\n".join(out)


def tipify_html(body: str) -> str:
    """Glossary hover tooltips on rendered HTML, outside tags and outside
    any <details> terms panel."""
    out, skip = [], 0
    for part in re.split(r"(<details[\s\S]*?</details>|<[^>]+>)", body):
        if part.startswith("<details"):
            out.append(part)
        elif part.startswith("<"):
            out.append(part)
        else:
            out.append(glossary.wrap_terms(part))
    return "".join(out)


def figure_card(repo_dir: Path, docs: Path, ref: str, caption: str) -> str:
    src = repo_dir / "figures" / f"{ref}.html"
    rel = Path(ref + ".html")
    dest = docs / "figures" / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(make_figure_responsive(src.read_text()))
    return (f'<figure class="figure-card">'
            f'<iframe src="figures/{rel.as_posix()}" loading="lazy" '
            f'title="{caption_from(Path(ref).stem)}"></iframe>'
            f'<figcaption>{caption}</figcaption></figure>')


def terms_panel(md_text: str) -> str:
    keys = glossary.terms_for(md_text)
    if not keys:
        return ""
    items = "".join(f"<li><strong>{k}</strong>: {glossary.TERMS[k][0]}</li>"
                    for k in keys)
    return ("<details class=\"terms\"><summary>Terms used in this "
            "analysis</summary><ul>" + items + "</ul></details>")


def build_study(repo: str) -> None:
    repo_dir = SIBLINGS / repo
    docs = repo_dir / "docs"
    docs.mkdir(exist_ok=True)
    story = repo_dir / "docs" / "story.md"
    if story.exists():
        md_text = story.read_text()
        used = re.findall(r"\{\{fig:([^|}]+)\|([^}]*)\}\}", md_text)
        placeholders = {}
        for i, (ref, cap) in enumerate(used):
            key = f"FIGPLACEHOLDER{i}ENDFIG"
            md_text = md_text.replace("{{fig:%s|%s}}" % (ref, cap), key, 1)
            placeholders[key] = figure_card(repo_dir, docs, ref.strip(),
                                            cap.strip())
        html = markdown.markdown(md_text,
                                 extensions=["tables", "fenced_code"])
        html = wrap_tables(absolutize_links(html, repo))
        for key, card in placeholders.items():
            html = html.replace(f"<p>{key}</p>", card).replace(key, card)
        # terms panel right after the lede paragraph
        panel = terms_panel(story.read_text())
        if panel:
            html = html.replace("</p>", "</p>\n" + panel, 1)
        html = tipify_html(html)
        referenced = {r.strip() for r, _ in used}
        leftovers = [f for f in sorted((repo_dir / "figures").rglob("*.html"))
                     if not f.stem.endswith("_r")
                     and f.relative_to(repo_dir / "figures"
                                       ).with_suffix("").as_posix()
                     not in referenced]
        if leftovers:
            html += "\n<h2>Additional figures</h2>"
            for f in leftovers:
                ref = f.relative_to(repo_dir / "figures"
                                    ).with_suffix("").as_posix()
                season = (f" ({ref.split('/')[0]})" if "/" in ref else "")
                html += "\n" + figure_card(
                    repo_dir, docs, ref, caption_from(f.stem) + season)
        html += (f'\n<h2>Method, code, and verification</h2>'
                 f'<p>The full technical write-up (data provenance, model '
                 f'specification, validation gates, and stated limitations) '
                 f'is the <a href="{GH}/{repo}#readme">README</a>. The '
                 f'analysis is implemented independently in R and Python and '
                 f'reconciled to numeric tolerance; <code>run_checks.sh</code> '
                 f'replays every gate.</p>')
    else:
        md_text = (repo_dir / "README.md").read_text()
        html = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
        html = wrap_tables(absolutize_links(html, repo))
        html += "\n" + figures_section(repo_dir, docs)
    title = re.search(r"<h1>(.*?)</h1>", html, re.DOTALL)
    title_text = re.sub(r"<[^>]+>", "", title.group(1)) if title else repo
    (docs / "index.html").write_text(page(title_text, html))
    print(f"built {repo}/docs/index.html")


def build_hub() -> None:
    repo_dir = SIBLINGS / "basketball-data-science"
    docs = repo_dir / "docs"
    docs.mkdir(exist_ok=True)
    cards = []
    for r in STUDIES:
        kicker, headline = HUB_CARDS[r]
        cards.append(f"""<div class="card">
  <span class="kicker">{kicker}</span>
  <h3>{r.replace("-", " ")}</h3>
  <p>{headline}</p>
  <span class="links"><a href="{PAGES}/{r}/">Read the analysis →</a> ·
  <a href="{GH}/{r}">code</a></span>
</div>""")
    layers = f"""<div class="card">
  <span class="kicker">SQL layer</span>
  <h3>basketball sql layer</h3>
  <p>The headline tables re-expressed as DuckDB window-function SQL,
  reconciled to exactly 0.0 against the polars outputs.</p>
  <span class="links"><a href="{GH}/basketball-sql-layer">code</a></span>
</div>
<div class="card">
  <span class="kicker">Scouting</span>
  <h3>nba scouting onepagers</h3>
  <p>Auto-generated opponent one-pagers for all 30 teams, full 2025-26
  season, gated byte-for-byte against the data.</p>
  <span class="links"><a href="{PAGES}/nba-scouting-onepagers/">Browse
  the reports →</a> · <a href="{GH}/nba-scouting-onepagers">code</a></span>
</div>
<div class="card">
  <span class="kicker">Tooling</span>
  <h3>basketball analysis tools</h3>
  <p>The glossary/tooltip engine, nba_api shims, cross-study identity
  tests, and the family-wide check orchestrator.</p>
  <span class="links"><a href="{GH}/basketball-analysis-tools">code</a></span>
</div>"""
    body = f"""<div class="hero">
<h1>Basketball data science</h1>
<p class="deck">Six studies and three working layers on public NBA, WNBA,
G League, and college data, written as narratives, run as pipelines, and
gated like production code.</p>
</div>
<p>The studies build on each other deliberately. The first asks the
smallest question (did NBA players really get shorter?) and finds the
famous decline is mostly a measurement-rule change, a rehearsal for every
"the metric moved" conversation that matters. From there the family works
up the stack: a full season of play-by-play turns the 2-for-1 debate into
a measured trade-off; seven million frames of raw tracking expose a
scorer's-table clock latency that quietly fabricates findings when
ignored; regularized lineup models put honest error bars on player value
and then rebuild it from an independent unit of observation to prove the
ordering isn't plumbing; a shot-pricing model splits shooting into the
skill that repeats and the skill that doesn't, and turns that split into a
projection rule that beats naive carry-forward out of sample; and the
draft study reports the most useful kind of result (that public college
stats add <em>nothing</em> beyond the pick) because knowing the ceiling
of public information is itself an edge.</p>
<p>One discipline runs through all of it. Every analysis is implemented
twice, in R and in Python, and the two must reconcile to numeric tolerance
before any finding is written. That gate is not ceremony. It caught a
text-versus-numeric sort that corrupted every scoreboard number in the
play-by-play study, and a dplyr masking bug that silently degraded a
standard-error column while every sum still matched. Results are validated
against independent external data before being believed, every number on
every page is generated by a script, and each study states plainly what it
cannot claim.</p>
<p>Each card below opens the study as a narrative (the question, the
evidence, and the specific figures that carry it), with the full technical
write-up one link deeper.</p>
<h2>The studies</h2>
<div class="cards">
{"".join(cards)}
</div>
<h2>The layers on top</h2>
<div class="cards">
{layers}
</div>
<h2>Also live</h2>
<p>Six seasons of the NBA over/under tracker
(<a href="{PAGES}/2026-nba-over-under.html">2025-26</a> ·
<a href="{PAGES}/2021-nba-over-under.html">2020-21</a> and the years
between), the <a href="{PAGES}/nba-player-finder/">NBA Player Finder</a>,
<a href="{PAGES}/nba-schedule/">NBA</a> /
<a href="{PAGES}/wnba-schedule/">WNBA</a> schedule viewers, and the rest of
<a href="https://chester.rbind.io/portfolio">chester.rbind.io/portfolio</a>.</p>
<h2>Standards &amp; references</h2>
<p><a href="{GH}/basketball-data-science/blob/main/docs/glossary.md">Glossary</a> ·
<a href="{GH}/basketball-data-science/blob/main/docs/analysis-audit.md">Analysis
audit</a> ·
<a href="{GH}/basketball-data-science/blob/main/docs/public-data-availability.md">Public-data
survey</a></p>"""
    (docs / "index.html").write_text(page(
        "Basketball Data Science: studies, tools, and standards", body,
        "Reconciled, validated basketball analytics on public data."))
    print("built basketball-data-science/docs/index.html")


def build_scouting_index() -> None:
    repo_dir = SIBLINGS / "nba-scouting-onepagers"
    docs = repo_dir / "docs"
    cards = []
    for md_file in sorted(docs.glob("*.md")):
        abbr = md_file.stem
        h1 = md_file.read_text().splitlines()[0]
        team = h1.replace("# Scouting one-pager: ", "").split(" (")[0]
        cards.append(f'<div class="card"><h3>{team}</h3>'
                     f'<span class="links"><a href="{abbr}.html">'
                     f'one-pager →</a></span></div>')
    body = f"""<div class="hero">
<h1>Opponent scouting one-pagers</h1>
<p class="deck">One page per team for the full 2025-26 season: the daily
deliverable of a coaching-analytics seat, generated end-to-end from public
data.</p>
</div>
<p>Each report reads the way a staff consumes it: the keys up top, then
the evidence beneath them. The shot profile prices where a team shoots
from using a model whose season-to-season transfer was validated by
backtest; personnel is split into shot <em>diet</em> (the part that
repeats year over year) and shot <em>making</em> (the part that is half
noise), and the making numbers are shrunk by empirical Bayes before any
bullet is allowed to call someone a shot-maker, so a hot month cannot
drive a game plan. Lineups come from the per-team files, player impact
from the opponent-adjusted RAPM model, and every claim in the keys traces
to a number in a table below it.</p>
<p>The reports cannot silently drift: the pipeline regenerates the Phoenix
report in memory on every family check run and fails unless the committed
copy matches byte-for-byte.</p>
<div class="cards">
{"".join(cards)}
</div>
<p><a href="{GH}/nba-scouting-onepagers">How they're built →</a></p>"""
    (docs / "index.html").write_text(page(
        "NBA opponent scouting one-pagers, 2025-26", body,
        "Auto-generated scouting reports for all 30 NBA teams."))
    print("built nba-scouting-onepagers/docs/index.html")


def main(argv: list[str]) -> int:
    targets = STUDIES if (not argv or argv[0] == "--all") else argv
    for r in targets:
        if r in STUDIES:
            build_study(r)
    if not argv or argv[0] == "--all":
        build_hub()
        build_scouting_index()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
