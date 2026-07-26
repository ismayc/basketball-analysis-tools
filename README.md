# basketball-analysis-tools

Shared tooling for the
[basketball-data-science](https://github.com/ismayc/basketball-data-science)
family of studies. Everything here supports or verifies the family as a
whole; anything specific to one analysis lives in that analysis's repo.

## What's here

| File | What |
|---|---|
| `glossary.py` | Single source of truth for the family's terms of art. Maintains a Terms block at the top of every registered README and wraps each point of use in an `<abbr>` hover tooltip. `--sync` rewrites, `--check` gates staleness. |
| `nba_api_compat.py` | Hard-won compatibility shims for the public NBA data stack: the stats.nba.com User-Agent fingerprint fix and the numpy 2.x `np.in1d` shim for nba-on-court. |
| `clone_family.sh` | Check out every family repo as siblings of this one. |
| `run_all_checks.sh` | The family-wide green light: each sibling repo's own checks, then the cross-repo gates (SQL reconciliation, scouting staleness, glossary staleness, cross-study identity tests). |
| `tests/` | Tests that span repos: e.g. draft-study and shot-quality-study claim the identical hand-rolled IRLS in both languages; the identity is held here, on shared random data, in Python and R. |

## Conventions

The family uses **sibling checkouts**: every repo sits next to the others
in one parent directory, and cross-repo references are `../<repo>` paths.
No submodules, no packaging: `clone_family.sh` sets the world up, and any
repo's `run_checks.sh` works standalone.

## Run

```bash
bash clone_family.sh        # siblings appear next to this repo
uv venv .venv && uv pip install -r requirements.txt --python .venv/bin/python
bash run_all_checks.sh      # every gate in the family
```
