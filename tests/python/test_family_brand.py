"""Unit tests for tools/check_family_brand.py.

These pin the exemption rules so a skip can never pass silently: an
exempt repo is reported with its reason, a non-exempt repo missing the
brand still fails, and a scan that finds no pages fails.
"""
from __future__ import annotations


def _repo(root, name, html):
    (root / name / ".git").mkdir(parents=True)
    (root / name / "docs").mkdir()
    (root / name / "docs" / "index.html").write_text(html)


def _branded(brand):
    import family_brand
    return (f'<link rel="icon" href="data:image/svg+xml,'
            f'{brand.FAVICON_CORE}">'
            f'<meta property="og:image" content="{family_brand.OG_IMAGE}">'
            f'<meta property="og:title" content="x">')


def test_exempt_repo_is_skipped_and_named(brand, tmp_path, capsys):
    exempt = next(iter(brand.EXEMPT))
    _repo(tmp_path, exempt, "<html>own brand</html>")
    _repo(tmp_path, "some-study", _branded(brand))
    assert brand.main(tmp_path) == 0
    out = capsys.readouterr().out
    assert f"BRAND SKIP {exempt} (1 pages): {brand.EXEMPT[exempt]}" in out
    assert "1 pages checked, 1 skipped as exempt, 0 failures" in out


def test_unbranded_non_exempt_repo_still_fails(brand, tmp_path, capsys):
    _repo(tmp_path, "new-study", "<html>no brand</html>")
    assert brand.main(tmp_path) == 1
    out = capsys.readouterr().out
    assert "new-study/docs/index.html: missing family favicon" in out
    assert "new-study/docs/index.html: missing family og:image" in out
    assert "new-study/docs/index.html: missing og:title" in out


def test_only_exempt_pages_found_fails(brand, tmp_path, capsys):
    exempt = next(iter(brand.EXEMPT))
    _repo(tmp_path, exempt, "<html>own brand</html>")
    assert brand.main(tmp_path) == 1
    assert "no published pages found" in capsys.readouterr().out


def test_every_exemption_has_a_reason(brand):
    assert brand.EXEMPT
    assert all(reason.strip() for reason in brand.EXEMPT.values())
