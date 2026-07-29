"""The family's shared brand: one favicon, one og image.

Single source of truth consumed by every page generator (report_builder,
build_onepager, the mebounds story build, the draft-potential app shell)
and enforced across all published pages by check_family_brand.py. A new
family member that ships pages without these fails the family checks.
"""

# Emoji-SVG favicon, inlined as a data URI so every page carries the same
# icon with no asset to host.
FAVICON = ('<link rel="icon" href="data:image/svg+xml,'
           '<svg xmlns=%22http://www.w3.org/2000/svg%22 '
           'viewBox=%220 0 100 100%22>'
           '<text y=%22.9em%22 font-size=%2290%22>🏀</text></svg>">')

# The shared social-card image, hosted once on the hub's Pages site.
OG_IMAGE = "https://ismayc.github.io/basketball-data-science/og-image.png"

OG_SITE_NAME = "Basketball Data Science"
