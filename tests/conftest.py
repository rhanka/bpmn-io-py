from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "upstream" / "bpmn-moddle" / "fixtures"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Root of the vendored upstream bpmn-moddle test fixtures."""
    return FIXTURES
