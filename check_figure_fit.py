"""Check that built study pages and their figures fit the screen.

Renders each page in headless Chrome (throwaway profile) inside a wrapper
iframe at phone width (390) and desktop width (1280), then fails when:

- the page scrolls sideways (anything wider than the viewport, such as an
  unscaled README image: 1800px PNGs did this on October 20, 2026),
- a figure scrolls sideways inside its frame, or its chart is wider than
  the frame,
- a figure's content is taller than its frame (a clipped chart, or a
  scrollbar inside the frame).

Usage: python3 check_figure_fit.py [page.html ...]
With no arguments it checks every sibling repo's docs/index.html that
embeds a figure. Exit status 1 on any failure. Needs Google Chrome; about
5 seconds per page per width.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import tempfile

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
WIDTHS = (390, 1280)
SIBLINGS = pathlib.Path(__file__).resolve().parent.parent

PROBE = r"""
<script>
function probe(){
  const f = document.getElementById('p');
  const d = f.contentDocument, w = f.contentWindow;
  const out = {innerWidth: w.innerWidth,
               scrollWidth: d.documentElement.scrollWidth, figs: []};
  for (const fr of d.querySelectorAll('iframe')) {
    const r = fr.getBoundingClientRect();
    const rec = {src: fr.getAttribute('src'), frameW: Math.round(r.width),
                 frameH: Math.round(r.height)};
    try {
      const fd = fr.contentDocument, de = fd.documentElement;
      rec.scrollW = de.scrollWidth; rec.clientW = de.clientWidth;
      rec.scrollH = de.scrollHeight; rec.clientH = de.clientHeight;
      const svgs = [...fd.querySelectorAll('svg')]
        .map(s => Math.round(s.getBoundingClientRect().width));
      rec.svgW = svgs.length ? Math.max(...svgs) : 0;
    } catch (e) { rec.err = String(e); }
    out.figs.push(rec);
  }
  document.getElementById('out').textContent = JSON.stringify(out);
}
window.addEventListener('load', () => setTimeout(probe, 4000));
</script>
"""


def measure(page: pathlib.Path, width: int, work: pathlib.Path) -> dict:
    wrap = work / "wrap.html"
    wrap.write_text(
        '<!doctype html><html><body style="margin:0">'
        f'<iframe id="p" src="{page.as_uri()}" '
        f'style="width:{width}px;height:3000px;border:0"></iframe>'
        f'<pre id="out"></pre>{PROBE}</body></html>')
    cmd = ["perl", "-e", "alarm 90; exec @ARGV", CHROME, "--headless=new",
           f"--user-data-dir={work / 'profile'}",
           "--allow-file-access-from-files", "--disable-gpu",
           "--virtual-time-budget=15000", "--window-size=1400,3000",
           "--dump-dom", wrap.as_uri()]
    dom = subprocess.run(cmd, capture_output=True, text=True).stdout
    m = re.search(r'<pre id="out">(.*?)</pre>', dom, re.S)
    if not m or not m.group(1).strip():
        return {}
    txt = (m.group(1).replace("&quot;", '"').replace("&lt;", "<")
           .replace("&gt;", ">").replace("&amp;", "&"))
    return json.loads(txt)


def problems(d: dict) -> list[str]:
    if not d:
        return ["page did not report (render failed or timed out)"]
    out = []
    if d["scrollWidth"] > d["innerWidth"] + 1:
        out.append(f"page scrolls sideways: {d['scrollWidth']}px in "
                   f"{d['innerWidth']}px")
    for g in d["figs"]:
        if "err" in g:
            out.append(f"{g['src']}: unreadable ({g['err']})")
            continue
        if g["scrollW"] > g["clientW"] + 1:
            out.append(f"{g['src']}: scrolls sideways in its frame")
        if g["svgW"] > g["frameW"] + 1:
            out.append(f"{g['src']}: chart {g['svgW']}px wider than frame "
                       f"{g['frameW']}px")
        if g["scrollH"] > g["clientH"] + 2:
            out.append(f"{g['src']}: content {g['scrollH']}px taller than "
                       f"frame {g['clientH']}px")
    return out


def default_pages() -> list[pathlib.Path]:
    return sorted(p for p in SIBLINGS.glob("*/docs/index.html")
                  if "<iframe" in p.read_text())


def main(argv: list[str]) -> int:
    pages = [pathlib.Path(a).resolve() for a in argv] or default_pages()
    if not pages:
        # a check that finds nothing must not read as a pass
        print("no pages with figures found")
        return 1
    work = pathlib.Path(tempfile.mkdtemp())
    failed = checked = 0
    for page in pages:
        for w in WIDTHS:
            d = measure(page, w, work)
            checked += 1
            figs = len(d.get("figs", []))
            bad = problems(d)
            name = f"{page.parent.parent.name} @{w}px ({figs} figures)"
            print(("FAIL " if bad else "ok   ") + name)
            for b in bad:
                print("     " + b)
            failed += bool(bad)
    print(f"{checked - failed} of {checked} page renders fit")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
