"""Build the family's GitHub Pages sites: one styled analysis page per
study (docs/index.html rendered from its README plus embedded interactive
figures), a card-grid landing page for the hub, and an index for the
scouting one-pagers.

The pages aim at the register of a professional analytics group or a data
journalist's methods page: restrained neutral chrome, one accent, a wide
readable measure, tables that scroll rather than overflow, the family's
glossary tooltips carried through, and the interactive plotly figures
embedded as cards. Light and dark are both first-class; the embedded
figures re-render through a light->dark palette map at view time, so
they follow the reader's color scheme like every other surface.

Run: python report_builder.py --all         every repo's docs/
     python report_builder.py <repo> ...    just those repos
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

import family_brand
import family_fonts
import glossary
import markdown

REPO = Path(__file__).resolve().parent
SIBLINGS = REPO.parent
GH = "https://github.com/ismayc"
PAGES = "https://ismayc.github.io"
OG_IMAGE = family_brand.OG_IMAGE
FAVICON = family_brand.FAVICON

STUDIES = ["jersey-height-study", "playbyplay-study", "tracking-study",
           "lineup-valuation-study", "shot-quality-study", "draft-study"]

# Display face for headings (family identity, shared with the mebounds
# story), inlined as data URIs so it renders identically offline.
FONTS = f"<style>{family_fonts.FONT_FACE_CSS}</style>"

# The family SVG chart engine that replaces plotly in published figures.
FAMPLOT_JS = (REPO / "famplot.js").read_text()

# Resolve the theme before first paint: saved choice, else OS preference.
THEME_BOOT = """<script>
(function () {
  try {
    var t = localStorage.getItem("family:theme");
    if (t === "dark" || t === "light") {
      document.documentElement.dataset.theme = t;
    }
  } catch (e) {}
})();
</script>"""

# Masthead toggle: cycles dark/light, persists, and rebroadcasts the theme
# to every embedded figure iframe (their engines listen for famTheme).
THEME_SCRIPT = """<script>
(function () {
  function current() {
    var t = document.documentElement.dataset.theme;
    if (t === "dark" || t === "light") { return t; }
    return matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark" : "light";
  }
  function broadcast() {
    var t = document.documentElement.dataset.theme || "auto";
    document.querySelectorAll("iframe").forEach(function (f) {
      try { f.contentWindow.postMessage({famTheme: t}, "*"); } catch (e) {}
    });
  }
  var btn = document.querySelector(".themebtn");
  if (btn) {
    btn.addEventListener("click", function () {
      var next = current() === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem("family:theme", next); } catch (e) {}
      broadcast();
    });
  }
  window.addEventListener("load", broadcast);
  document.querySelectorAll("iframe").forEach(function (f) {
    f.addEventListener("load", function () {
      var t = document.documentElement.dataset.theme || "auto";
      try { f.contentWindow.postMessage({famTheme: t}, "*"); } catch (e) {}
    });
  });
})();
</script>"""

# Hub landing-page config: repo -> (kicker, one-line headline)
HUB_CARDS = {
    "jersey-height-study": (
        "46 seasons of rosters",
        "The “players are getting shorter” trend is ~70% a 2019 "
        "measurement-rule change. The jersey numbers really did shrink: "
        "the median nearly halved."),
    "playbyplay-study": (
        "Full 2023-24 play-by-play",
        "The 2-for-1 adds a real possession at no shot-quality cost, "
        "and ~+0.2 net points, indistinguishable from zero."),
    "tracking-study": (
        "7.5M frames of raw SportVU",
        "A 2.5–6s scorer's-table latency fabricates findings if "
        "unhandled; the possession join is validated at 97.6%."),
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

# Newer analyses get their own hub section; the original six stay put.
# Add a repo here and rebuild to grow the section. "href" overrides the
# card's read link; "extra" appends an additional link. A repo listed here
# that also has docs/story.md gets its page built like a study.
NEW_CARDS = {
    "mebounds": {
        "kicker": "2M play-by-play events, WNBA × NBA",
        "headline": (
            "Angel Reese's “mebound” is measurably earned: she recovers "
            "her own misses at 3-4x the league rate, at league-leading "
            "rebound volume no NBA player matches either."),
    },
    "draft-potential-by-team": {
        "kicker": "27 draft classes, priced by slot",
        "headline": (
            "OKC leads at +489 Win Shares above slot, but 27 of 30 "
            "franchise intervals cross zero: provable draft skill is rare. "
            "The era's biggest steal went first overall."),
        "href": f"{PAGES}/draft-potential-by-team/analysis/",
        "extra": (f'<a href="{PAGES}/draft-potential-by-team/">'
                  "interactive viewer</a>"),
    },
}

CSS = """
:root {
  --ink: #161512; --ink-2: #52514e; --ink-3: #898781;
  --surface: #faf9f6; --surface-2: #f2f1ea; --rule: #e1e0d9;
  --accent: #eb6834; --accent-ink: #a83f12; --fig-surface: #fcfcfb;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --ink: #f5f3ec; --ink-2: #c3c2b7; --ink-3: #898781;
    --surface: #0f0e0d; --surface-2: #1a1a19; --rule: #2c2c2a;
    --accent: #d95926; --accent-ink: #ea9066; --fig-surface: #1a1a19;
  }
}
:root[data-theme="dark"] {
  --ink: #f5f3ec; --ink-2: #c3c2b7; --ink-3: #898781;
  --surface: #0f0e0d; --surface-2: #1a1a19; --rule: #2c2c2a;
  --accent: #d95926; --accent-ink: #ea9066; --fig-surface: #1a1a19;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--surface); color: var(--ink);
  font: 17px/1.65 system-ui, -apple-system, "Segoe UI", Helvetica, Arial,
  sans-serif; }
.display, h1, h2, .masthead .family, .card h3 {
  font-family: "Barlow Condensed", system-ui, sans-serif; }
.masthead { border-bottom: 1px solid var(--rule); }
.masthead .inner { width: min(1200px, 94vw); margin: 0 auto; padding: .8rem 0;
  display: flex; gap: 1rem; align-items: baseline; flex-wrap: wrap; }
.masthead a { color: var(--ink-2); text-decoration: none; font-size: .88rem; }
.masthead a:hover { color: var(--accent-ink); }
.masthead .family { font-weight: 600; font-size: 1.05rem;
  text-transform: uppercase; letter-spacing: .08em; color: var(--ink); }
.masthead .spacer { flex: 1; }
.themebtn { background: none; border: 1px solid var(--rule);
  border-radius: 999px; width: 30px; height: 30px; cursor: pointer;
  color: var(--ink-2); font-size: .95rem; line-height: 1;
  align-self: center; }
.themebtn:hover { border-color: var(--accent); color: var(--ink); }
.eyebrow { font-family: "Barlow Condensed", system-ui, sans-serif;
  font-weight: 500; font-size: 1rem; letter-spacing: .14em;
  text-transform: uppercase; color: var(--ink-3); margin-top: 1.6rem; }
.eyebrow + h1 { margin-top: .3rem; }
.eyebrow.beat { margin: 2.4rem 0 0; padding-top: 1.2rem;
  border-top: 1px solid var(--rule); color: var(--accent-ink); }
.eyebrow.beat + h2 { border-top: none; padding-top: 0; margin-top: .2rem; }
.tiles { display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: .9rem; margin: 1.8rem 0; }
.tile { background: var(--surface-2); border: 1px solid var(--rule);
  border-radius: 8px; padding: 1rem 1.1rem .9rem; }
.tile .label { font-size: .78rem; letter-spacing: .06em;
  text-transform: uppercase; color: var(--ink-3); }
.tile .value { font-family: "Barlow Condensed", system-ui, sans-serif;
  font-weight: 600; font-size: 2.7rem; line-height: 1.05; margin-top: .2rem;
  color: var(--ink); }
.tile .value small { font-size: 1.4rem; color: var(--ink-2);
  font-weight: 500; }
.tile .sub { font-size: .84rem; color: var(--ink-2); margin-top: .15rem; }
main { width: min(1200px, 94vw); margin: 0 auto; padding: 1.5rem 0 4rem; }
h1 { font-weight: 600; font-size: 2.7rem; line-height: 1.02;
  text-transform: uppercase; letter-spacing: .01em; text-wrap: balance;
  margin: 1.2rem 0 .6rem; }
h2 { font-weight: 600; font-size: 1.75rem; line-height: 1.08;
  text-transform: uppercase; letter-spacing: .02em; margin: 2.2rem 0 .6rem;
  padding-top: 1rem; border-top: 1px solid var(--rule); }
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
abbr[data-tip] { text-decoration: underline dotted var(--accent);
  text-underline-offset: 2px; cursor: help; position: relative; }
abbr[data-tip]:hover::after { content: attr(data-tip); position: absolute;
  left: 0; top: 1.5em; z-index: 40; background: var(--ink);
  color: var(--surface); padding: .5rem .75rem; border-radius: 7px;
  width: max-content; max-width: min(340px, 80vw); font-size: .82rem;
  line-height: 1.45; font-weight: 400; white-space: normal;
  box-shadow: 0 4px 16px rgba(0,0,0,.28); pointer-events: none; }
hr { border: none; border-top: 1px solid var(--rule); margin: 2rem 0; }
.figure-card { background: var(--fig-surface); border: 1px solid var(--rule);
  border-radius: 10px; margin: 1.4rem 0; overflow: hidden; }
.figure-card iframe { display: block; width: 100%; height: 560px;
  border: none; padding: .75rem 1rem 0 1.1rem;
  background: var(--fig-surface); }
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
  letter-spacing: .09em; color: var(--accent-ink); font-weight: 600; }
.card h3 { margin: 0; font-weight: 600; font-size: 1.35rem;
  text-transform: uppercase; letter-spacing: .02em; line-height: 1.05; }
.card p { margin: 0; font-size: .92rem; color: var(--ink-2); flex: 1; }
.card .links { font-size: .88rem; }
.hero { padding: 2.2rem 0 .6rem; }
.hero h1 { font-size: clamp(3rem, 7vw, 4.6rem); margin: .4rem 0 .5rem; }
.hero p.deck { font-size: 1.15rem; color: var(--ink-2); max-width: 50rem; }
"""


def page(title: str, body: str, deck: str = "", repo: str = "") -> str:
    fallback = ("Reconciled, validated basketball analytics on public data: "
                "part of the basketball-data-science family.")
    description = deck or fallback
    og_url = f"{PAGES}/{repo or 'basketball-data-science'}/"
    gh_link = (f'<a href="{GH}/{repo}">Code on GitHub</a>' if repo
               else f'<a href="{GH}/basketball-data-science">GitHub</a>')
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
{FAVICON}
<meta property="og:type" content="website">
<meta property="og:site_name" content="Basketball Data Science">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{og_url}">
<meta property="og:image" content="{OG_IMAGE}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{OG_IMAGE}">
{FONTS}
{THEME_BOOT}
<style>{CSS}</style>
</head>
<body>
<header class="masthead"><div class="inner">
  <a class="family" href="{PAGES}/basketball-data-science/">Basketball Data Science</a>
  <span class="spacer"></span>
  <a href="{PAGES}/basketball-data-science/">All studies</a>
  <a href="{PAGES}/nba-scouting-onepagers/">Scouting one-pagers</a>
  {gh_link}
  <button class="themebtn" type="button" aria-label="Toggle color theme">◐</button>
</div></header>
<main>
{body}
</main>
<footer>Public data · dual-implementation reconciled · every gate scripted ·
<a href="{GH}/basketball-data-science">the family on GitHub</a></footer>
{THEME_SCRIPT}
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
(function () {
  // Figures are authored on the light family palette; on a dark scheme the
  // same spec is re-rendered through this light->dark map (chrome and series
  // steps from the family palette). Each plot's light spec is remembered so
  // theme flips are lossless in both directions.
  var MAP = {"white": "#1a1a19", "#fff": "#1a1a19", "#fcfcfb": "#1a1a19",
    "#ffffff": "#1a1a19",
    "#f2f1ea": "#21201e", "#eceae2": "#262624", "#e1e0d9": "#2c2c2a",
    "#c3c2b7": "#383835", "#52514e": "#c3c2b7", "#2a3f5f": "#c3c2b7",
    "#0b0b0b": "#f5f3ec", "#161512": "#f5f3ec", "#2a78d6": "#3987e5",
    "#eb6834": "#d95926", "#1baf7a": "#199e70"};
  var mq = window.matchMedia("(prefers-color-scheme: dark)");
  // The parent page's manual theme toggle overrides the OS preference; it
  // arrives as a postMessage from the embedding page.
  var override = null;
  var themeFn = null;
  function isDark() {
    return override ? override === "dark" : mq.matches;
  }
  function stampBody() {
    document.body.classList.toggle("fam-dark", override === "dark");
    document.body.classList.toggle("fam-light", override === "light");
  }
  window.addEventListener("message", function (e) {
    if (!e.data || !e.data.famTheme) { return; }
    var t = e.data.famTheme;
    override = (t === "dark" || t === "light") ? t : null;
    stampBody();
    if (themeFn) { themeFn(); }
  });
  function darken(o) {
    if (typeof o === "string") { return MAP[o.toLowerCase()] || o; }
    if (Array.isArray(o)) { return o.map(darken); }
    if (o && typeof o === "object") {
      var r = {}; for (var k in o) { r[k] = darken(o[k]); } return r;
    }
    return o;
  }
  function copy(o) { return JSON.parse(JSON.stringify(o)); }
  // Hand-built figure pages (e.g. animated histograms) often omit chrome
  // colors and inherit plotly's defaults; pin those to the family's light
  // values so the dark map has something to map.
  function withDefaults(layout) {
    var L = layout ? copy(layout) : {};
    L.paper_bgcolor = L.paper_bgcolor || "#fcfcfb";
    L.plot_bgcolor = L.plot_bgcolor || "#fcfcfb";
    L.font = L.font || {}; L.font.color = L.font.color || "#52514e";
    ["xaxis", "yaxis"].forEach(function (a) {
      L[a] = L[a] || {};
      L[a].gridcolor = L[a].gridcolor || "#e1e0d9";
      if (L[a].zeroline !== false) {
        L[a].zerolinecolor = L[a].zerolinecolor || "#e1e0d9";
      }
    });
    return L;
  }
  // Route every author-side render through the theme: remember the light
  // spec, darken it when the scheme is dark.
  var origReact = null;
  function installWrapper() {
    if (origReact || !window.Plotly) { return; }
    origReact = Plotly.react;
    Plotly.react = function (gd, data, layout, config) {
      var el = typeof gd === "string" ? document.getElementById(gd) : gd;
      var L = withDefaults(layout), D = copy(data || []);
      if (el) { el._lightSpec = {data: copy(D), layout: copy(L),
                                 config: config}; }
      if (isDark()) { D = darken(D); L = darken(L); }
      return origReact.call(Plotly, el || gd, D, L, config);
    };
  }
  installWrapper();
  window.addEventListener("load", function () {
    installWrapper();
    var gs = Array.prototype.slice.call(
      document.querySelectorAll(".plotly-graph-div, .js-plotly-plot"));
    // Plots rendered before the wrapper installed (write_html pages, or a
    // hand-built page that drew during parse): their current spec is the
    // light spec.
    gs.forEach(function (g) {
      if (!g._lightSpec) {
        g._lightSpec = {data: copy(g.data),
                        layout: withDefaults(g.layout)};
      }
    });
    // Re-render each plot from its light spec, darkened when the scheme is
    // dark. Sizing is plotly's own job: the layouts get autosize and every
    // figure ships config {responsive: true}, which react() preserves.
    function theme() {
      gs.forEach(function (g) {
        var src = g._lightSpec;
        var D = copy(src.data), L = copy(src.layout);
        delete L.width; L.autosize = true;
        if (isDark()) { D = darken(D); L = darken(L); }
        origReact.call(Plotly, g, D, L, src.config);
      });
    }
    themeFn = theme;
    stampBody();
    theme();
    if (mq.addEventListener) { mq.addEventListener("change", theme); }
  });
})();
</script>"""

# Dark styling for the figure page itself and for any hand-rolled HTML
# controls a figure embeds (e.g. the jersey study's season buttons). The
# media query covers the OS preference; the fam-dark/fam-light classes are
# stamped by the runtime when the parent page's manual toggle overrides it.
FIGURE_DARK_CSS = """<style>html,body{margin:0;height:100%}
@media (prefers-color-scheme: dark){
  body:not(.fam-light){background:#1a1a19;color:#c3c2b7}
  body:not(.fam-light) .controls button{background:#1a1a19;color:#c3c2b7;border-color:#383835}
  body:not(.fam-light) .controls button.on{background:#3987e5;color:#0f0e0d;border-color:#3987e5}
  body:not(.fam-light) .seasonlab{color:#f5f3ec}
}
body.fam-dark{background:#1a1a19;color:#c3c2b7}
body.fam-dark .controls button{background:#1a1a19;color:#c3c2b7;border-color:#383835}
body.fam-dark .controls button.on{background:#3987e5;color:#0f0e0d;border-color:#3987e5}
body.fam-dark .seasonlab{color:#f5f3ec}</style>"""


# Bring embedded figures onto the family palette at publish time (the
# committed pipeline outputs stay untouched). Maps the legacy navy/steel
# series colors and plotly's default-template inks and grids to the family
# equivalents; hexes chosen so no figure ends up with two identical series.
FIGURE_COLOR_MAP = {
    "#1E3A5F": "#2a78d6",   # legacy navy marks/buttons -> family blue
    "#9AAFC9": "#9ec5f4",   # legacy steel pair -> family blue, light step
    "#2a3f5f": "#52514e",   # plotly template ink -> family ink-2
    "#C8D4E3": "#e1e0d9",   # plotly template axis lines -> family rule
    "#EBF0F8": "#eceae2",   # plotly template grid -> warm hairline
    "#E5ECF6": "#f2f1ea",   # plotly template plot bg -> family surface-2
    '"paper_bgcolor":"white"': '"paper_bgcolor":"#fcfcfb"',
    '"plot_bgcolor":"white"': '"plot_bgcolor":"#fcfcfb"',
}


def make_figure_responsive(text: str) -> str:
    """Publish-time rewrite of a study figure: swap the plotly CDN engine
    for the family SVG engine (famplot), map any legacy colors onto the
    family palette, let the copy fill its iframe and follow resizes, and
    adapt it to the viewer's color scheme. The committed plotly originals
    stay untouched and remain reproducible from each study's code."""
    text = re.sub(
        r'<script[^>]*src="https://cdn\.plot\.ly/[^"]*"[^>]*></script>',
        lambda m: "<script>" + FAMPLOT_JS + "</script>", text, count=1)
    for old, new in FIGURE_COLOR_MAP.items():
        if old.startswith("#"):
            text = re.sub(re.escape(old), new, text, flags=re.IGNORECASE)
        else:
            text = text.replace(old, new)
    text = re.sub(r'style="height:\d+px; width:\d+px;"',
                  'style="height:100%; width:100%;"', text, count=1)
    text = text.replace("<head>", "<head>" + FIGURE_DARK_CSS, 1)
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
           "<p>Drawn in the family chart style; hover for values. "
           "Interactive plotly versions of every figure are available by "
           "running the study's figure code on GitHub "
           "(<code>python/</code> → <code>figures/</code>), and static R "
           "twins live in the repo.</p>"]
    for f in figs:
        rel = f.relative_to(repo_dir / "figures")
        dest = docs / "figures" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        text = f.read_text()
        dest.write_text(make_figure_responsive(text))
        # Size each embed to its figure's authored height so compact charts
        # don't float in a fixed-height frame and tall ones don't clip.
        hm = re.search(r'"height":\s*(\d+)', text)
        h = int(hm.group(1)) if hm else 500
        season = f" ({rel.parts[0]})" if len(rel.parts) > 1 else ""
        out.append(
            f'<figure class="figure-card">'
            f'<iframe src="figures/{rel.as_posix()}" loading="lazy" '
            f'style="height:{h + 16}px" '
            f'title="{caption_from(f.stem)}"></iframe>'
            f'<figcaption>{caption_from(f.stem)}{season}</figcaption>'
            f'</figure>')
    return "\n".join(out)


STUDY_MENTIONS = {
    "shot-quality study": "shot-quality-study",
    "shot quality study": "shot-quality-study",
    "play-by-play study": "playbyplay-study",
    "playbyplay study": "playbyplay-study",
    "tracking study": "tracking-study",
    "lineup-valuation study": "lineup-valuation-study",
    "lineup valuation study": "lineup-valuation-study",
    "draft study": "draft-study",
    "jersey study": "jersey-height-study",
    "jersey-height study": "jersey-height-study",
}


def link_study_mentions(html: str, self_repo: str = "") -> str:
    """Auto-link prose mentions of sibling studies to their Pages sites,
    the same way glossary terms get tooltips. Skips text already inside
    an anchor, and never links a page's mentions of itself."""
    phrases = {k: v for k, v in STUDY_MENTIONS.items() if v != self_repo}
    if not phrases:
        return html
    pat = re.compile("(" + "|".join(re.escape(k) for k in
                                    sorted(phrases, key=len, reverse=True))
                     + ")", re.IGNORECASE)

    def sub(m: re.Match) -> str:
        target = phrases[m.group(1).lower()]
        return f'<a href="{PAGES}/{target}/">{m.group(1)}</a>'

    out, depth = [], 0
    for seg in re.split(r"(<[^>]+>)", html):
        if seg.startswith("<"):
            low = seg.lower()
            if low.startswith("<a ") or low == "<a>":
                depth += 1
            elif low.startswith("</a"):
                depth = max(0, depth - 1)
            out.append(seg)
        else:
            out.append(seg if depth else pat.sub(sub, seg))
    return "".join(out)


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
    text = src.read_text()
    dest.write_text(make_figure_responsive(text))
    # Size the embed to the figure's authored height so compact charts
    # don't float in a fixed-height frame and tall ones don't clip.
    hm = re.search(r'"height":\s*(\d+)', text)
    h = int(hm.group(1)) if hm else 500
    return (f'<figure class="figure-card">'
            f'<iframe src="figures/{rel.as_posix()}" loading="lazy" '
            f'style="height:{h + 16}px" '
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
    html = link_study_mentions(html, self_repo=repo)
    # instant styled tooltips on the published page; README keeps title=
    # for GitHub's native rendering
    html = html.replace('<abbr title="', '<abbr data-tip="')
    kicker = (HUB_CARDS.get(repo, ("", ""))[0]
              or NEW_CARDS.get(repo, {}).get("kicker", ""))
    if kicker:
        html = html.replace(
            "<h1>", f'<div class="eyebrow">{kicker}</div>\n<h1>', 1)
    (docs / "index.html").write_text(page(title_text, html, repo=repo))
    print(f"built {repo}/docs/index.html")


def build_hub() -> None:
    # The hub repo is cloned as "basketball-data-science" by clone_family.sh
    # but lives as "hub" in this checkout; write wherever it actually is.
    repo_dir = SIBLINGS / "basketball-data-science"
    if not (repo_dir / "docs").exists() and (SIBLINGS / "hub" / "docs").exists():
        repo_dir = SIBLINGS / "hub"
    docs = repo_dir / "docs"
    docs.mkdir(exist_ok=True)
    def card(r, kicker, headline, href=None, extra=None):
        links = f'<a href="{href or f"{PAGES}/{r}/"}">Read the analysis →</a>'
        if extra:
            links += f" ·\n  {extra}"
        links += f' ·\n  <a href="{GH}/{r}">code</a>'
        return f"""<div class="card">
  <span class="kicker">{kicker}</span>
  <h3>{r.replace("-", " ")}</h3>
  <p>{headline}</p>
  <span class="links">{links}</span>
</div>"""

    cards = [card(r, *HUB_CARDS[r]) for r in STUDIES]
    new_cards = [card(r, c["kicker"], c["headline"], c.get("href"),
                      c.get("extra")) for r, c in NEW_CARDS.items()]
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
<div class="eyebrow">Six studies &middot; three layers &middot; one discipline</div>
<h1>Basketball data science</h1>
<p class="deck">Six studies and three working layers on public NBA, WNBA,
G League, and college data, written as narratives, run as pipelines, and
gated like production code.</p>
</div>
<p>The studies build on each other deliberately. The first asks the
smallest question: did NBA players really get shorter? The famous decline
turns out to be mostly a measurement-rule change, a rehearsal for every
"the metric moved" conversation that matters. From there the family works
up the stack. A full season of play-by-play turns the 2-for-1 debate into
a measured trade-off. Seven million frames of raw tracking expose a
scorer's-table clock latency that quietly fabricates findings when
ignored. Regularized lineup models put honest error bars on player value,
then rebuild it from an independent unit of observation to prove the
ordering isn't plumbing. A shot-pricing model splits shooting into the
skill that repeats and the skill that doesn't, and turns that split into
a projection rule that beats naive carry-forward out of sample. And the
draft study reports the most useful kind of result, that public college
stats add <em>nothing</em> beyond the pick, because knowing the ceiling
of public information is itself an edge.</p>
<p>One discipline runs through all of it. Every analysis is implemented
twice, in R and in Python, and the two must reconcile to numeric tolerance
before any finding is written. That gate is not ceremony. It caught a
text-versus-numeric sort that corrupted every scoreboard number in the
play-by-play study, and a dplyr masking bug that silently degraded a
standard-error column while every sum still matched. Results are validated
against independent external data before being believed, every number on
no analysis number in any README is typed by hand (findings scripts
write them from committed outputs, with drift gates), every number in
the narrative pages is machine-verified against those outputs on every
check run, and each study states plainly what it cannot claim.</p>
<p>Each card below opens the study as a narrative (the question, the
evidence, and the specific figures that carry it), with the full technical
write-up one link deeper.</p>
<h2>The studies</h2>
<div class="cards">
{"".join(cards)}
</div>
<h2>New analyses</h2>
<div class="cards">
{"".join(new_cards)}
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
<a href="{GH}/basketball-data-science/blob/main/docs/data-provenance.md">Data
provenance (sources and seasons)</a> ·
<a href="{GH}/basketball-data-science/blob/main/docs/public-data-availability.md">Public-data
survey</a></p>"""
    body = link_study_mentions(body)
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
<div class="eyebrow">The scouting layer &middot; 30 teams &middot; 2025-26</div>
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
        "Auto-generated scouting reports for all 30 NBA teams.",
        repo="nba-scouting-onepagers"))
    print("built nba-scouting-onepagers/docs/index.html")


def main(argv: list[str]) -> int:
    storied_new = [r for r in NEW_CARDS
                   if (SIBLINGS / r / "docs" / "story.md").exists()]
    targets = (STUDIES + storied_new
               if (not argv or argv[0] == "--all") else argv)
    for r in targets:
        if r in STUDIES or r in storied_new:
            build_study(r)
    if not argv or argv[0] == "--all":
        build_hub()
        build_scouting_index()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
