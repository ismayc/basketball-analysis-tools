"""Generate the family's shared social card (og-image.png).

Renders an HTML card with the family tokens (warm off-black surface,
burnt-orange accent, Barlow Condensed display face from family_fonts)
and a shot-arc basketball motif, then screenshots it with headless
Chrome at the standard 1200x630.

Usage: python3 build_og_image.py [output.png]
Default output: ../hub/docs/og-image.png (the hub hosts the one shared card).
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import family_fonts

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "hub" / "docs" / "og-image.png"

WIDTH, HEIGHT = 1200, 630

# Shot-arc motif: a dashed fitted-curve trajectory carrying three
# basketballs (fading in along the flight) into a side-view hoop. The rim
# is drawn about twice the ball's width, matching real rim-to-ball
# proportions (18 in rim vs 9.5 in ball).
BG = "#0f0e0d"
RULE = "#2c2c2a"
MUTED = "#898781"
ACCENT = "#d95926"


def _ball(cx, cy, r, opacity=1.0):
    """Basketball glyph: circle, two diameters, two curved side seams."""
    k = 0.71 * r
    return f"""\
  <g stroke="{ACCENT}" stroke-width="2.5" fill="{BG}" opacity="{opacity}">
    <circle cx="{cx}" cy="{cy}" r="{r}"/>
    <line x1="{cx - r}" y1="{cy}" x2="{cx + r}" y2="{cy}"/>
    <line x1="{cx}" y1="{cy - r}" x2="{cx}" y2="{cy + r}"/>
    <path d="M {cx - k} {cy - k} Q {cx - 0.1 * r} {cy} {cx - k} {cy + k}"
          fill="none"/>
    <path d="M {cx + k} {cy - k} Q {cx + 0.1 * r} {cy} {cx + k} {cy + k}"
          fill="none"/>
  </g>"""


ART_SVG = f"""\
<svg width="1200" height="630" viewBox="0 0 1200 630"
     fill="none" xmlns="http://www.w3.org/2000/svg"
     style="position:absolute; inset:0;">
  <path d="M 780 520 Q 980 55 1112 186" stroke="{MUTED}"
        stroke-width="2.5" stroke-dasharray="9 9"/>
  <line x1="1140" y1="96" x2="1140" y2="212" stroke="{RULE}"
        stroke-width="3.5"/>
  <line x1="1140" y1="190" x2="1084" y2="190" stroke="{ACCENT}"
        stroke-width="4"/>
  <g stroke="{RULE}" stroke-width="1.5">
    <line x1="1086" y1="193" x2="1096" y2="246"/>
    <line x1="1138" y1="193" x2="1128" y2="246"/>
    <line x1="1086" y1="193" x2="1128" y2="246"/>
    <line x1="1138" y1="193" x2="1096" y2="246"/>
    <line x1="1103" y1="192" x2="1120" y2="246"/>
    <line x1="1121" y1="192" x2="1104" y2="246"/>
  </g>
{_ball(838, 394, 16, opacity=0.35)}
{_ball(946, 222, 16, opacity=0.6)}
{_ball(1062, 158, 16)}
</svg>
"""

HTML = f"""\
<!doctype html>
<html><head><meta charset="utf-8">
<style>
{family_fonts.FONT_FACE_CSS}
* {{ margin: 0; box-sizing: border-box; }}
body {{
  width: {WIDTH}px; height: {HEIGHT}px; overflow: hidden;
  background: #0f0e0d; color: #f5f3ec; position: relative;
  font: 17px/1.65 system-ui, -apple-system, "Segoe UI", Helvetica, Arial,
    sans-serif;
}}
.card {{
  position: relative; height: 100%; padding: 64px 84px 62px;
  display: flex; flex-direction: column; border-top: 6px solid #d95926;
}}
.eyebrow {{
  font-family: "Barlow Condensed", sans-serif; font-weight: 500;
  font-size: 30px; letter-spacing: .18em; text-transform: uppercase;
  color: #ea9066;
}}
h1 {{
  font-family: "Barlow Condensed", sans-serif; font-weight: 600;
  font-size: 128px; line-height: 1.02; margin-top: 18px; color: #f5f3ec;
}}
.deck {{
  font-size: 31px; line-height: 1.45; color: #c3c2b7; margin-top: 26px;
  max-width: 560px;
}}
.footer {{
  margin-top: auto; display: flex; align-items: center; gap: 14px;
  font-size: 24px; color: #898781;
}}
.footer .dot {{ color: #d95926; }}
</style></head>
<body>
{ART_SVG}
<div class="card">
  <div class="eyebrow">NBA &middot; WNBA &middot; G League &middot; College</div>
  <h1>Basketball<br>Data Science</h1>
  <div class="deck">Reconciled, validated basketball analytics
    on public data</div>
  <div class="footer">
    <span>ismayc.github.io/basketball-data-science</span>
    <span class="dot">&#9679;</span>
    <span>Chester Ismay</span>
  </div>
</div>
</body></html>
"""


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    with tempfile.TemporaryDirectory() as td:
        page = Path(td) / "og.html"
        page.write_text(HTML)
        subprocess.run(
            [CHROME, "--headless", "--disable-gpu", "--hide-scrollbars",
             f"--screenshot={out}", f"--window-size={WIDTH},{HEIGHT}",
             "--default-background-color=0f0e0dff", str(page)],
            check=True, capture_output=True)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
