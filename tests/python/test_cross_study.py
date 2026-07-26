"""Cross-study identity tests — properties that span sibling repos, so they
live with the family tooling rather than in any one study."""
from __future__ import annotations

import numpy as np


def test_irls_matches_shot_quality_solver(draft, shotq):
    # The two studies claim the identical algorithm; hold them to it.
    rng = np.random.default_rng(3)
    X = np.column_stack([np.ones(300), rng.normal(size=(300, 2))])
    y = (rng.uniform(size=300) < 0.4).astype(float)
    assert np.allclose(draft.logistic_irls(X, y), shotq.logistic_irls(X, y),
                       atol=1e-12)
