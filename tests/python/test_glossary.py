"""Unit tests for tools/glossary.py — the terms-block + hover-tip layer.

The staleness gate (--check) runs in run_all_checks.sh; these pin the
wrapping rules that would fail silently: alias boundaries, protected
zones, and idempotency.
"""
from __future__ import annotations


def test_pps_never_wrapped_inside_xpps(gloss):
    out = gloss.annotate("xPPS and PPS differ.\n")
    assert out.count("<abbr") == 2
    assert ">xPPS</abbr>" in out and ">PPS</abbr>" in out
    assert "x<abbr" not in out


def test_code_and_headings_are_protected(gloss):
    md = ("## PPS heading\n\n"
          "Inline `PPS` code and real PPS prose.\n\n"
          "```\nPPS in a fence\n```\n")
    out = gloss.annotate(md)
    assert out.count("<abbr") == 1
    assert "`PPS`" in out and "PPS in a fence" in out
    assert "## PPS heading" in out


def test_sync_is_idempotent_and_strip_roundtrips(gloss):
    doc = "# T\n\nPPS and RAPM here.\n\n## Body\n\nMore RAPM.\n"
    once = gloss.sync_text(doc, "docs/glossary.md")
    assert gloss.sync_text(once, "docs/glossary.md") == once
    assert gloss.OPEN in once and gloss.CLOSE in once
    assert gloss.strip_abbr(gloss.annotate("PPS.\n")) == "PPS.\n"


def test_terms_for_detects_prose_only(gloss):
    md = "# T\n\nReal RAPM here, `PPS` only in code.\n\n## AUC heading\n"
    keys = gloss.terms_for(md)
    assert "RAPM" in keys
    assert "PPS" not in keys      # code span
    assert "AUC" not in keys      # heading


def test_every_definition_is_title_attribute_safe(gloss):
    for term, (definition, aliases) in gloss.TERMS.items():
        assert not set('"<>&') & set(definition), term
        assert aliases, term
