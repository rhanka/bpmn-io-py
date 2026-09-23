"""Differential auto-layout tests: Python port vs the pinned Node package (Lot 8).

``op=layout-process-batch`` (``tests/oracle/dump.mjs``, upstream
``bpmn-auto-layout`` 1.3.0 ``layoutProcess``) lays out each document; the port
``layout_process`` (same algorithm: grid placement, waypoints, DI generation)
must produce byte-identical output, failures message-identical. The corpus is
every ``bpmn-auto-layout`` ``test/fixtures/*.bpmn`` fixture. This is
differential on the algorithm itself, independent of the committed snapshots
pinned by ``tests/auto_layout/test_layout_snapshot.py``; on conflict this
live oracle wins over the vendored snapshot.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from bpmn_io.auto_layout import layout_process

if TYPE_CHECKING:
    from collections.abc import Callable

pytestmark = pytest.mark.oracle

FIXTURES = (
    Path(__file__).resolve().parent.parent / "upstream" / "bpmn-auto-layout" / "test" / "fixtures"
)

#: Sorted fixture names (same enumeration as the snapshot test).
NAMES = sorted(path.name for path in FIXTURES.glob("*.bpmn"))


def _layout_py(xml: str) -> dict[str, Any]:
    """Lay out through the port, capturing failures like the batch op."""
    try:
        return {"xml": layout_process(xml)}
    except Exception as exc:  # noqa: BLE001 — messages are the contract here
        return {"error": str(exc)}


@pytest.mark.parametrize("name", NAMES, ids=lambda name: f"{name}#layout")
def test_auto_layout_oracle_corpus(
    name: str,
    oracle_call: Callable[[dict[str, object]], object],
) -> None:
    xml = (FIXTURES / name).read_text(encoding="utf-8")
    expected = oracle_call({"op": "layout-process-batch", "inputs": [{"xml": xml}]})
    assert isinstance(expected, list)
    assert len(expected) == 1
    assert _layout_py(xml) == expected[0], f"{name}#layout"
