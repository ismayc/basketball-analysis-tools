"""famdiagram.py and its report_builder embed."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import famdiagram  # noqa: E402
import report_builder  # noqa: E402


def small(width=600, size=16):
    d = famdiagram.Diagram(width, 200, "A test diagram")
    d.rect(10, 10, 100, 50, fill="surface2", stroke="rule", rx=6)
    d.line(10, 100, 200, 100, stroke="nba", arrow=True)
    d.text(20, 40, "Stops & kills <3", size=size, fill="ink")
    return d


def test_colors_are_classes_never_hex():
    svg = small().svg()
    assert not re.search(r"#[0-9a-fA-F]{6}", svg)
    assert 'class="dg-f-surface2 dg-s-rule"' in svg
    assert "Stops &amp; kills &lt;3" in svg          # text is escaped
    with pytest.raises(ValueError):
        famdiagram.Diagram(10, 10, "x").rect(0, 0, 1, 1, fill="#ff0000")
    with pytest.raises(ValueError):
        famdiagram.Diagram(10, 10, "x").group('<rect fill="#abc"/>')


def test_save_refuses_text_too_small_for_phones(tmp_path):
    # 16 units in a 900-wide layout shown at 330px is 5.9px: refused
    with pytest.raises(ValueError, match="narrow layout"):
        famdiagram.save(tmp_path, "d", small(width=900))
    # with a narrow layout, the wide one is judged at 600px (10.7px): refused
    with pytest.raises(ValueError):
        famdiagram.save(tmp_path, "d", small(width=900), small(width=360))
    # 20 units at 900 shown at 600 is 13.3px, narrow 16 at 360 -> 14.7px
    paths = famdiagram.save(tmp_path, "d", small(width=900, size=20),
                            small(width=360))
    assert [p.name for p in paths] == ["d.svg", "d_narrow.svg"]
    # dropping the narrow layout later removes the stale file
    famdiagram.save(tmp_path, "d", small(width=480))
    assert not (tmp_path / "d_narrow.svg").exists()


def test_diagram_card_inlines_both_layouts(tmp_path):
    figs = tmp_path / "figures"
    famdiagram.save(figs, "d", small(width=900, size=20), small(width=360))
    card = report_builder.diagram_card(tmp_path, "d", "Caption text")
    assert card.count("<svg") == 2
    assert 'class="dg-has-narrow"' in card and "<iframe" not in card
    assert card.endswith("<figcaption>Caption text</figcaption></figure>")
    famdiagram.save(figs, "e", small(width=480))
    assert report_builder.diagram_card(tmp_path, "e", "c").count("<svg") == 1


def test_css_defines_every_diagram_class():
    for c in famdiagram.COLORS:
        for kind in ("f", "s"):
            assert f".dg-{kind}-{c} " in report_builder.CSS, (kind, c)


def test_arrow_markers_are_unique_per_layout():
    # One shared id resolved to the hidden wide copy on phones, so the
    # narrow layout's arrows drew without heads (October 20, 2026).
    wide, narrow = small(width=900, size=20), small(width=360)
    assert wide.arrow_id != narrow.arrow_id
    assert f'id="{wide.arrow_id}"' in wide.svg()
    assert f'url(#{wide.arrow_id})' in wide.svg()
    assert wide.arrow_id == small(width=900, size=20).arrow_id   # deterministic
