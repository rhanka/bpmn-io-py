from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "upstream" / "bpmn-moddle" / "test" / "fixtures"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Root of the vendored upstream bpmn-moddle test fixtures."""
    return FIXTURES


def upstream_dir(package: str) -> Path:
    """Root of the vendored upstream ``lib/`` + ``test/`` trees for ``package``."""
    return Path(__file__).parent / "upstream" / package


def read_fixture(package: str, path: str) -> str:
    """Read a vendored upstream fixture file as UTF-8 text."""
    return (upstream_dir(package) / path).read_text(encoding="utf-8")
