"""Smoke tests for the Node oracle runner bridge (Lot 1)."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from _bridge import OracleError

if TYPE_CHECKING:
    from collections.abc import Callable

ROOT = Path(__file__).parents[2]

pytestmark = pytest.mark.oracle


def _pins() -> dict[str, str]:
    pins = tomllib.loads((ROOT / "UPSTREAM.toml").read_text())["upstream"]
    return {name: spec["version"] for name, spec in pins.items()}


def test_ping_reports_node_and_pinned_versions(
    oracle_call: Callable[[dict[str, object]], object],
) -> None:
    result = oracle_call({"op": "ping"})
    assert result["node"].startswith("v")
    assert result["packages"] == _pins()


def test_generic_call_dispatches_to_package_function(
    oracle_call: Callable[[dict[str, object]], object],
) -> None:
    assert (
        oracle_call(
            {"op": "call", "package": "min-dash", "path": "flatten", "args": [[[1], [2]]]},
        )
        == [1, 2]
    )


def test_call_unknown_path_raises(
    oracle_call: Callable[[dict[str, object]], object],
) -> None:
    with pytest.raises(OracleError):
        oracle_call({"op": "call", "package": "min-dash", "path": "nope", "args": []})


def test_unknown_op_raises(oracle_call: Callable[[dict[str, object]], object]) -> None:
    with pytest.raises(OracleError):
        oracle_call({"op": "nope"})
