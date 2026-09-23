"""Shared fixtures for oracle (Node differential) tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture(scope="session")
def oracle_call() -> Callable[[dict[str, object]], object]:
    """One JSON call to the Node runner; skips when the oracle is unavailable."""
    from _bridge import available, run

    if not available():
        pytest.skip("oracle needs node and `npm ci` in tests/oracle")
    return run
