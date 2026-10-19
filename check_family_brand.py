"""Family brand gate: every published page carries the family favicon and
the family og image.

Discovers sibling repos automatically, so a NEW family member that ships
pages without the brand fails this check with no configuration. A repo is
in scope when it has a .git directory and publishes any of:

- docs/*.html          (Pages sites: hub, studies, scouting, mebounds)
- story/index.html     (the mebounds story mirror)
- index.html + vite.config.js  (app shells whose head ships to dist/)

Skipped: figure iframes under docs/figures/ (chrome-less embeds), raw
data caches, repos with no published pages, and the repos in EXEMPT. Each
exempt repo is printed with its reason on every run, so a skip is never
silent.

Run: python check_family_brand.py            report + exit non-zero on fail
"""
from __future__ import annotations

from pathlib import Path

import family_brand

SIBLINGS = Path(__file__).resolve().parent.parent

# The favicon appears entity-encoded in some shells; match on the stable
# core of the data URI instead of the exact wrapper.
FAVICON_CORE = "font-size=%2290%22>🏀</text></svg>"

# Repos that publish pages under their own brand on purpose. Add a repo
# here only with the reason it is not a family page.
EXEMPT = {
    "nba-shot-charts": "own favicon and og image; private, password-protected "
                       "Netlify site, not linked from the hub",
    "wnba-shot-charts": "own favicon and og image; private, password-protected "
                        "Netlify site, not linked from the hub",
}


def pages_for(repo: Path) -> list[Path]:
    pages: list[Path] = []
    docs = repo / "docs"
    if docs.is_dir():
        pages += sorted(docs.glob("*.html"))
    story = repo / "story" / "index.html"
    if story.exists():
        pages.append(story)
    if (repo / "vite.config.js").exists() and (repo / "index.html").exists():
        pages.append(repo / "index.html")
    return pages


def main(siblings: Path = SIBLINGS) -> int:
    failures: list[str] = []
    checked = 0
    skipped = 0
    for repo in sorted(siblings.iterdir()):
        if not (repo / ".git").is_dir():
            continue
        if repo.name in EXEMPT:
            n = len(pages_for(repo))
            skipped += n
            print(f"BRAND SKIP {repo.name} ({n} pages): {EXEMPT[repo.name]}")
            continue
        for page in pages_for(repo):
            rel = page.relative_to(siblings)
            text = page.read_text(errors="replace")
            checked += 1
            if FAVICON_CORE not in text:
                failures.append(f"{rel}: missing family favicon")
            if f'content="{family_brand.OG_IMAGE}"' not in text:
                failures.append(f"{rel}: missing family og:image")
            if 'property="og:title"' not in text:
                failures.append(f"{rel}: missing og:title")
    if not checked:
        failures.append("no published pages found; check sibling checkouts")
    for f in failures:
        print(f"BRAND FAIL {f}")
    print(f"family brand check: {checked} pages checked, "
          f"{skipped} skipped as exempt, {len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
