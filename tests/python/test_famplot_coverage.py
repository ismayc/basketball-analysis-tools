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
# Axis types it has a scale for. A missing type means linear.
SUPPORTED_AXIS_TYPES = {None, "linear", "log", "category"}
# Scatter modes it understands (split on "+").
SUPPORTED_MODES = {"lines", "markers"}
# Per-trace keys famplot reads and honors.
SUPPORTED_TRACE_KEYS = {
    "type", "mode", "name", "x", "y", "customdata", "marker", "line",
    "fill", "fillcolor", "orientation", "visible", "showlegend",
    "hoverinfo", "hovertemplate", "hovertext", "error_x", "error_y",
    "opacity", "width", "xbins", "nbinsx", "histnorm", "cliponaxis",
    "legendgroup", "offsetgroup", "text", "textposition", "textfont",
}
# Keys famplot drops. Dropping them costs a label or a legend entry, never
# a misplaced mark, so they are allowed through.
IGNORED_TRACE_KEYS = {
    "texttemplate", "textangle", "insidetextanchor", "cliponaxis",
    "meta", "uid",
}


def figures() -> list[Path]:
    return sorted(p for repo in SIBLINGS.iterdir()
                  for p in (repo / "docs" / "figures").rglob("*.html")
                  if (repo / "docs" / "figures").is_dir())


# Figures this gate cannot read statically, with the reason. These are
# hand-authored interactive pages that build their traces from JS variables
# and call Plotly.react, not plotly write_html exports with a literal spec.
# famplot still renders them, so an engine change can still break them; they
# just have to be checked by eye. Listed explicitly because a gate that
# quietly drops a target reads exactly like a gate that checked it.
UNPARSEABLE = {
    "jersey-height-study/docs/figures/fig6_number_histogram.html",
}


def specs():
    out, skipped = [], []
    for path in figures():
        m = NEWPLOT.search(path.read_text())
        if not m:
            skipped.append(path)
            continue
        try:
            data = json.loads(m.group(1))
            layout = json.loads(m.group(2))
        except json.JSONDecodeError:
            skipped.append(path)
            continue
        out.append((path, data, layout))
    return out, skipped


ALL, SKIPPED = specs()


def test_every_figure_is_read_or_declared_unreadable():
    """A new figure shape the regex cannot parse would drop out of every
    assertion below without a word. Fail here instead, so the choice to
    exempt it is deliberate and written down."""
    undeclared = [str(p.relative_to(SIBLINGS)) for p in SKIPPED
                  if str(p.relative_to(SIBLINGS)) not in UNPARSEABLE]
    assert not undeclared, (
        "figures the gate cannot parse and that are not in UNPARSEABLE: "
        + ", ".join(undeclared))
    gone = UNPARSEABLE - {str(p.relative_to(SIBLINGS)) for p in SKIPPED}
    assert not gone, f"UNPARSEABLE lists figures that now parse: {sorted(gone)}"


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
def test_axis_scales_are_implemented(spec):
    """famplot picks a scale per axis from `type`. An unimplemented one is
    not an error: the axis silently draws linear, which reads as a real
    chart with the wrong geometry. That shipped as a cross-validation curve
    labeled "log scale" whose log-spaced penalties bunched at the left."""
    path, _, layout = spec
    for axis in ("xaxis", "yaxis"):
        kind = (layout.get(axis) or {}).get("type")
        assert kind in SUPPORTED_AXIS_TYPES, f"{path.name} {axis}: {kind}"


@pytest.mark.parametrize("spec", ALL, ids=label)
def test_log_axes_carry_only_positive_scatter_data(spec):
    """famplot's log branch scales scatter and line coordinates. Bars anchor
    to zero, which has no position on a log axis, and a non-positive value
    has none either; both come out NaN."""
    path, data, layout = spec
    for axis, key in (("xaxis", "x"), ("yaxis", "y")):
        if (layout.get(axis) or {}).get("type") != "log":
            continue
        for i, tr in enumerate(data):
            assert tr.get("type", "scatter") == "scatter", \
                f"{path.name} trace {i}: {tr.get('type')} on a log {axis}"
            bad = [v for v in (tr.get(key) or [])
                   if isinstance(v, (int, float)) and v <= 0]
            assert not bad, f"{path.name} trace {i}: {key}<=0 on a log axis"


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


# Hovertemplate fields famplot's hover() resolves. An unknown one is not an
# error there either: it substitutes "" and the tooltip loses that piece.
# Four figures shipped with "%{text}" leading their template and every
# tooltip missing the player's name before this was caught.
HOVER_PATHS = {"x", "y", "text", "hovertext", "fullData.name"}
HOVER_FIELD = re.compile(r"%\{([^}:]+)(?::[^}]*)?\}")


@pytest.mark.parametrize("spec", ALL, ids=label)
def test_hovertemplate_fields_are_resolvable(spec):
    path, data, _ = spec
    for i, tr in enumerate(data):
        for field in HOVER_FIELD.findall(tr.get("hovertemplate") or ""):
            ok = field in HOVER_PATHS or field.startswith("customdata[")
            assert ok, f"{path.name} trace {i}: %{{{field}}} unresolvable"


@pytest.mark.parametrize("spec", ALL, ids=label)
def test_drawn_text_labels_are_only_on_bars(spec):
    """famplot draws `text` for bars. On a scatter, `text` is the hover
    payload; plotly only draws it when the mode says "text", which famplot
    has no branch for and which would stamp a label on every point."""
    path, data, _ = spec
    for i, tr in enumerate(data):
        if tr.get("text") is None:
            continue
        kind = tr.get("type", "scatter")
        if kind == "scatter":
            assert "text" not in (tr.get("mode") or "lines"), \
                f"{path.name} trace {i}: scatter asks for drawn text"
