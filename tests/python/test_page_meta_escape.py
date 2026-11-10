"""Page titles and descriptions are escaped inside meta attributes.

A raw double quote in the kills study's title ended its og:title attribute,
so link previews showed only "Is a" (November 10, 2026).
"""
import html
import re

import report_builder as rb


def meta(page: str, prop: str) -> str:
    m = re.search(rf'<meta (?:property|name)="{prop}" content="([^"]*)">', page)
    assert m, prop
    return html.unescape(m[1])


def test_quotes_in_title_survive_attributes():
    title = 'Is a "kill" anything more than a good stop rate?'
    page = rb.page(title, "<h1>t</h1>", deck='A "deck" & more', repo="some-study")
    assert meta(page, "og:title") == title
    assert meta(page, "og:description") == 'A "deck" & more'
    assert meta(page, "description") == 'A "deck" & more'
    assert f"<title>{html.escape(title, quote=True)}</title>" in page


def test_existing_entities_not_double_escaped():
    page = rb.page("Rock &amp; roll", "<h1>t</h1>", repo="some-study")
    assert meta(page, "og:title") == "Rock & roll"
    assert "&amp;amp;" not in page
