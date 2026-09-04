"""Every published figure is drawn by famplot, not by plotly.

The studies author figures with plotly and `report_builder` swaps the CDN
engine for famplot at publish time. famplot implements only the subset of
the plotly spec the family actually uses, and an unimplemented feature does
not raise: it produces NaN geometry, which SVG silently resolves to 0. That
failure mode shipped once already, with a dot plot's markers stacked at the
top of the page instead of on the plotting surface (lineup-valuation-study
fig1, both seasons).

So this gate reads what the committed figures ask for and fails when a study
starts using a spec feature famplot has no branch for. A new feature here is
a prompt to teach famplot, not to widen the allowlist on sight.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SIBLINGS = REPO.parent

NEWPLOT = re.compile(
    r'Plotly\.newPlot\(\s*"[^"]+",\s*(\[.*\]),\s*(\{.*\}),\s*\{.*?\}\s*\)',
    re.S)

# Trace types famplot has a rendering branch for.
SUPPORTED_TYPES = {"scatter", "bar", "histogram"}
# Scatter modes it understands (split on "+").
SUPPORTED_MODES = {"lines", "markers"}
# Per-trace keys famplot reads and honors.
SUPPORTED_TRACE_KEYS = {
    "type", "mode", "name", "x", "y", "customdata", "marker", "line",
    "fill", "fillcolor", "orientation", "visible", "showlegend",
    "hoverinfo", "hovertemplate", "hovertext", "error_x", "error_y",
    "opacity", "width", "xbins", "nbinsx", "histnorm", "cliponaxis",
    "legendgroup", "offsetgroup",
}
# Keys famplot drops. Dropping them costs a label or a legend entry, never
# a misplaced mark, so they are allowed through. In-bar value labels
# (`text` on a bar trace) are the one live gap: tracking-study fig3 asks
# for them and the published chart has none.
IGNORED_TRACE_KEYS = {
    "text", "textfont", "textposition", "texttemplate", "textangle",
    "insidetextanchor", "cliponaxis", "meta", "uid",
}


def figures() -> list[Path]:
    return sorted(p for repo in SIBLINGS.iterdir()
                  for p in (repo / "docs" / "figures").rglob("*.html")
                  if (repo / "docs" / "figures").is_dir())


def specs():
    out = []
    for path in figures():
        m = NEWPLOT.search(path.read_text())
        if not m:
            continue
        try:
            data = json.loads(m.group(1))
            layout = json.loads(m.group(2))
        except json.JSONDecodeError:
            continue
        out.append((path, data, layout))
    return out


ALL = specs()


def label(item) -> str:
    return str(item[0].relative_to(SIBLINGS))


def test_some_figures_were_found():
    # A silent zero-figure sweep would make every check below vacuous.
    assert len(ALL) >= 15


@pytest.mark.parametrize("spec", ALL, ids=label)
def test_trace_types_and_modes_are_implemented(spec):
    path, data, _ = spec
    for i, tr in enumerate(data):
        kind = tr.get("type", "scatter")
        assert kind in SUPPORTED_TYPES, f"{path.name} trace {i}: {kind}"
        if kind == "scatter":
            for mode in (tr.get("mode") or "lines").split("+"):
                assert mode in SUPPORTED_MODES, f"{path.name} trace {i}: {mode}"


@pytest.mark.parametrize("spec", ALL, ids=label)
def test_no_unhandled_trace_keys(spec):
    path, data, _ = spec
    for i, tr in enumerate(data):
        extra = set(tr) - SUPPORTED_TRACE_KEYS - IGNORED_TRACE_KEYS
        assert not extra, f"{path.name} trace {i} uses {sorted(extra)}"


@pytest.mark.parametrize("spec", ALL, ids=label)
def test_binary_arrays_are_only_where_famplot_decodes_them(spec):
    """plotly packs numpy arrays as {dtype, bdata}. famplot decodes x, y,
    customdata, marker.color, marker.size and the error arrays; a packed
    array anywhere else reaches the renderer as an object and arithmetic on
    it yields NaN."""
    path, data, _ = spec

    def packed(v) -> bool:
        return isinstance(v, dict) and "bdata" in v

    for i, tr in enumerate(data):
        for key, val in tr.items():
            if key in ("x", "y", "customdata"):
                continue
            if key == "marker":
                for mk, mv in val.items():
                    if mk in ("color", "size"):
                        continue
                    assert not packed(mv), \
                        f"{path.name} trace {i}: marker.{mk} is packed"
                continue
            if key in ("error_x", "error_y"):
                for ek, ev in val.items():
                    if ek in ("array", "arrayminus"):
                        continue
                    assert not packed(ev), \
                        f"{path.name} trace {i}: {key}.{ek} is packed"
                continue
            assert not packed(val), f"{path.name} trace {i}: {key} is packed"


@pytest.mark.parametrize("spec", ALL, ids=label)
def test_every_string_coordinate_lands_in_a_band(spec):
    """famplot bands string coordinates instead of scaling them, but only
    the bar and scatter-markers branches collect the category list. A line
    trace can ride along on categories some other trace established; a
    string that never reaches the list scales as a number, and every such
    mark stacks at 0 outside the plotting surface.

    This mirrors famplot's own collection rules, so it fails the moment a
    study's figure asks for a band famplot would not build.
    """
    path, data, layout = spec
    cat_x = (layout.get("xaxis") or {}).get("type") == "category"
    cat_y = (layout.get("yaxis") or {}).get("type") == "category"

    def vals(v):
        return v if isinstance(v, list) else []

    x_cats, y_cats, banders = set(), set(), 0
    for tr in data:
        kind = tr.get("type", "scatter")
        mode = tr.get("mode") or "lines"
        horiz_bar = kind == "bar" and tr.get("orientation") == "h"
        if horiz_bar:
            y_cats |= set(vals(tr.get("y")))
            banders += 1
        elif kind == "bar" or (kind == "scatter" and "markers" in mode):
            banders += 1
            for xv in vals(tr.get("x")):
                if cat_x or isinstance(xv, str):
                    x_cats.add(xv)
            if kind == "scatter":
                for yv in vals(tr.get("y")):
                    if cat_y or isinstance(yv, str):
                        y_cats.add(yv)

    for i, tr in enumerate(data):
        loose_x = {v for v in vals(tr.get("x")) if isinstance(v, str)}
        loose_y = {v for v in vals(tr.get("y")) if isinstance(v, str)}
        if loose_x:
            # famplot only switches the x axis to bands when a bar or a
            # markers trace is present to anchor them.
            assert banders, f"{path.name} trace {i}: string x, nothing bands it"
        assert not (loose_x - x_cats), \
            f"{path.name} trace {i}: unbanded x {sorted(loose_x - x_cats)}"
        assert not (loose_y - y_cats), \
            f"{path.name} trace {i}: unbanded y {sorted(loose_y - y_cats)}"
