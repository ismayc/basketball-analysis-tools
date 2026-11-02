"""A study's own terms: hover tips where a term is used, and a list at the page end."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import report_builder as rb  # noqa: E402

TERMS = [
    {"term": "Wilson interval", "definition": 'A range for a "rate".',
     "aliases": ["95% Wilson interval", "Wilson interval"]},
    {"term": "sigma", "definition": "Volatility.", "aliases": ["sigma"]},
]


def test_longest_alias_wins_and_the_definition_is_escaped():
    out = rb.tipify_local("<p>A 95% Wilson interval.</p>", TERMS)
    assert out.count("<abbr") == 1
    assert '>95% Wilson interval</abbr>' in out
    assert "&quot;rate&quot;" in out
    assert 'tabindex="0"' in out


def test_headings_links_code_and_tag_attributes_stay_plain():
    body = ('<h2>Why sigma moved</h2><a href="#x">sigma</a><code>sigma</code>'
            '<iframe title="sigma"></iframe><p>sigma</p>')
    out = rb.tipify_local(body, TERMS)
    assert out.count("<abbr") == 1
    assert out.endswith('>sigma</abbr></p>')
    assert '<h2>Why sigma moved</h2>' in out
    assert 'title="sigma"></iframe>' in out


def test_a_term_inside_a_longer_word_is_left_alone():
    assert "<abbr" not in rb.tipify_local("<p>sigmas and multi-sigma</p>", TERMS)


def test_no_terms_file_means_no_change(tmp_path):
    assert rb.local_terms(tmp_path) == []
    body = "<p>sigma</p>"
    assert rb.tipify_local(body, []) == body
    assert rb.key_terms_section([]) == ""


def test_key_terms_section_lists_every_term_and_joins_the_nav():
    sec = rb.key_terms_section(TERMS)
    assert sec.count("<dt>") == len(TERMS)
    body, nav = rb.section_nav(
        f'<div class="eyebrow beat">One</div><h2>Plain</h2><div class="eyebrow beat">Two</div>'
        f"<h2>{rb.METHOD_H2}</h2>{sec}")
    assert 'href="#key-terms"' in nav
    assert '<h2 id="key-terms">' in body
    assert "<h2>Plain</h2>" in body
