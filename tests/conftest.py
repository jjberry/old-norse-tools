"""Shared fixtures for the test suite."""

import pytest
from pathlib import Path

from nion.db.schema import get_connection

_DB_PATH = Path(__file__).parent.parent / "data" / "nion.db"


@pytest.fixture(scope="session")
def conn():
    if not _DB_PATH.exists():
        pytest.skip("data/nion.db not found — run `nion-build` first")
    return get_connection(_DB_PATH)
