"""Fixtures for the tools repo: its own modules plus sibling study code
for the cross-study identity tests."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SIBLINGS = REPO.parent


def load_script(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def gloss():
    return load_script(REPO / "glossary.py", "portfolio_glossary")


@pytest.fixture(scope="session")
def shotq():
    return load_script(SIBLINGS / "shot-quality-study/python/02_model.py",
                       "shotq_model")


@pytest.fixture(scope="session")
def draft():
    return load_script(SIBLINGS / "draft-study/python/02_model.py",
                       "draft_model")
