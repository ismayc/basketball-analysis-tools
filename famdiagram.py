"""Explainer diagrams for the family's study pages, as theme-aware SVG.

A study's figure script draws a diagram with `Diagram`, saving it to
`figures/<ref>.svg`, and its story places it with `{{svg:<ref>|caption}}`.
report_builder.py inlines the SVG into the page (no iframe), so the
diagram follows the page's light and dark theme: every color is a class
here, styled from the page tokens by report_builder's CSS (`.dg-*`).
Never write a hex color into a diagram.

Phones: an inline SVG scales with the column, so its text shrinks with it.
A diagram whose wide layout would put text under MIN_PX on a phone also
saves a narrow layout, `figures/<ref>_narrow.svg`, drawn for a 360-unit
width; the page shows the wide one above 640px and the narrow one below.
`save()` refuses a layout whose smallest text would read under MIN_PX at
the narrowest width it is shown at.

Numbers in a diagram must come from committed outputs read by the figure
script, never typed into the script, the same as the Plotly figures.

Classes (fill or stroke): ink, ink2, ink3, rule, surface, surface2, accent,
nba, wnba, c3 (green), c4 (amber), c8 (red). Use `fill="nba"` and the
like; `stroke=` the same names.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

COLORS = ("ink", "ink2", "ink3", "rule", "surface", "surface2", "accent",
          "nba", "wnba", "c3", "c4", "c8", "none")
MIN_PX = 11.0
# Narrowest content width each layout is shown at (report_builder CSS):
# the wide layout from 640px viewports (main is 94vw), the narrow one down
# to a 360px phone.
WIDE_MIN_SHOWN = 600.0
NARROW_MIN_SHOWN = 330.0


def _cls(fill: str | None, stroke: str | None, extra: str = "") -> str:
    parts = []
    for kind, c in (("f", fill), ("s", stroke)):
        if c is None:
            continue
        if c not in COLORS:
            raise ValueError(f"unknown diagram color {c!r}; use one of {COLORS}")
        parts.append(f"dg-{kind}-{c}")
    if extra:
        parts.append(extra)
    return " ".join(parts)


class Diagram:
    """An SVG canvas in viewBox units. Coordinates are user units; the
    rendered size scales to the page column."""

    def __init__(self, width: float, height: float, title: str):
        self.w, self.h, self.title = width, height, title
        self.parts: list[str] = []
        self.font_sizes: list[float] = []

    # shapes -------------------------------------------------------------
    def rect(self, x, y, w, h, fill="surface2", stroke=None, rx=0,
             opacity=None, dash=None, sw=1.5):
        a = f' rx="{rx}"' if rx else ""
        a += f' opacity="{opacity}"' if opacity is not None else ""
        a += f' stroke-dasharray="{dash}"' if dash else ""
        a += f' stroke-width="{sw}"' if stroke else ""
        self.parts.append(f'<rect x="{x:g}" y="{y:g}" width="{w:g}" '
                          f'height="{h:g}" class="{_cls(fill, stroke)}"{a}/>')

    def circle(self, cx, cy, r, fill="accent", stroke=None, opacity=None,
               sw=1.5):
        a = f' opacity="{opacity}"' if opacity is not None else ""
        a += f' stroke-width="{sw}"' if stroke else ""
        self.parts.append(f'<circle cx="{cx:g}" cy="{cy:g}" r="{r:g}" '
                          f'class="{_cls(fill, stroke)}"{a}/>')

    def line(self, x1, y1, x2, y2, stroke="ink3", sw=1.5, dash=None,
             arrow=False, opacity=None):
        a = f' stroke-dasharray="{dash}"' if dash else ""
        a += f' opacity="{opacity}"' if opacity is not None else ""
        a += ' marker-end="url(#dg-arrow)"' if arrow else ""
        self.parts.append(f'<line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" '
                          f'y2="{y2:g}" stroke-width="{sw}" '
                          f'class="{_cls(None, stroke, "dg-arrowed" if arrow else "")}"{a}/>')

    def path(self, d, fill="none", stroke="ink2", sw=1.5, dash=None,
             opacity=None, arrow=False):
        a = f' stroke-dasharray="{dash}"' if dash else ""
        a += f' opacity="{opacity}"' if opacity is not None else ""
        a += ' marker-end="url(#dg-arrow)"' if arrow else ""
        self.parts.append(f'<path d="{d}" stroke-width="{sw}" '
                          f'class="{_cls(fill, stroke)}"{a}/>')

    def polyline(self, pts, stroke="ink2", sw=1.5, dash=None, opacity=None,
                 fill="none"):
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        self.path(d, fill=fill, stroke=stroke, sw=sw, dash=dash,
                  opacity=opacity)

    def text(self, x, y, s, size=15, fill="ink", anchor="start",
             weight=None, display=False, italic=False):
        """`display=True` uses the family's Barlow Condensed face."""
        self.font_sizes.append(size)
        a = f' text-anchor="{anchor}"' if anchor != "start" else ""
        a += f' font-weight="{weight}"' if weight else ""
        a += ' font-style="italic"' if italic else ""
        cls = _cls(fill, None, "dg-display" if display else "dg-text")
        self.parts.append(f'<text x="{x:g}" y="{y:g}" font-size="{size:g}" '
                          f'class="{cls}"{a}>{html.escape(str(s))}</text>')

    def group(self, svg_fragment: str):
        """Raw fragment, for rare cases; it must use dg- classes only."""
        if re.search(r"#[0-9a-fA-F]{3,6}\b", svg_fragment):
            raise ValueError("hex color in a diagram fragment; use a dg- class")
        self.parts.append(svg_fragment)

    # output -------------------------------------------------------------
    def svg(self) -> str:
        defs = ('<defs><marker id="dg-arrow" viewBox="0 0 10 10" refX="9" '
                'refY="5" markerWidth="7" markerHeight="7" '
                'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" '
                'class="dg-f-ink3"/></marker></defs>')
        return (f'<svg xmlns="http://www.w3.org/2000/svg" class="dg" '
                f'viewBox="0 0 {self.w:g} {self.h:g}" role="img" '
                f'aria-label="{html.escape(self.title)}">'
                f'<title>{html.escape(self.title)}</title>{defs}'
                + "".join(self.parts) + "</svg>\n")

    def min_px(self, shown_width: float) -> float:
        if not self.font_sizes:
            return float("inf")
        return min(self.font_sizes) * shown_width / self.w


def save(fig_dir: Path, ref: str, wide: Diagram,
         narrow: Diagram | None = None) -> list[Path]:
    """Write figures/<ref>.svg (and <ref>_narrow.svg). Refuses a layout
    whose smallest text would render under MIN_PX where it is shown."""
    fig_dir = Path(fig_dir)
    fig_dir.mkdir(parents=True, exist_ok=True)
    shown = WIDE_MIN_SHOWN if narrow is not None else NARROW_MIN_SHOWN
    checks = [(wide, shown, f"{ref}.svg")]
    if narrow is not None:
        checks.append((narrow, NARROW_MIN_SHOWN, f"{ref}_narrow.svg"))
    for d, w, name in checks:
        px = d.min_px(w)
        if px < MIN_PX:
            raise ValueError(
                f"{name}: smallest text renders at {px:.1f}px at {w:g}px "
                f"wide (minimum {MIN_PX}); enlarge the text"
                + ("" if narrow else " or add a narrow layout"))
    out = []
    for d, _, name in checks:
        p = fig_dir / name
        p.write_text(d.svg())
        out.append(p)
    stale = fig_dir / f"{ref}_narrow.svg"
    if narrow is None and stale.exists():
        stale.unlink()
    return out
