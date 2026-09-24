"""Differential bpmn-moddle serialization: Python port vs pinned Node (Lot 7).

``op=model-serialize-batch`` (``tests/oracle/dump.mjs``, upstream
``BpmnModdle`` with its six default descriptor packages) parses each document
and serializes it back with ``format`` false/true; the port ``BpmnModdle``
(same six packages, ``bpmn-in-color-moddle`` 0.2.0 vendored) must produce
byte-identical output, failures message-identical. The corpus is every
``bpmn-moddle`` ``.bpmn`` fixture, ``bpmn-in-color.bpmn`` included.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from bpmn_io.bpmn_moddle import BpmnModdle

if TYPE_CHECKING:
    from collections.abc import Callable

pytestmark = pytest.mark.oracle

FIXTURES = Path(__file__).parent.parent / "upstream" / "bpmn-moddle" / "test" / "fixtures" / "bpmn"


def _serialize_py(
    xml: str,
    format: bool,  # noqa: A002, FBT001 - option names
) -> dict[str, Any]:
    """Parse lax and serialize back, capturing failures like the batch op."""
    try:
        root = BpmnModdle().from_xml(xml).root_element
        return {"xml": BpmnModdle().to_xml(root, {"format": format, "preamble": True}).xml}
    except Exception as exc:  # noqa: BLE001 — messages are the contract here
        return {"error": str(exc)}


def test_bpmn_serialize_bytes_corpus(
    oracle_call: Callable[[dict[str, object]], object],
) -> None:
    paths = sorted(FIXTURES.rglob("*.bpmn"))
    ids = [str(path.relative_to(FIXTURES)) for path in paths]
    xmls = [path.read_text(encoding="utf-8", errors="replace") for path in paths]
    inputs: list[dict[str, Any]] = []
    for xml in xmls:
        inputs.append({"xml": xml, "format": False, "preamble": True})
        inputs.append({"xml": xml, "format": True, "preamble": True})
    # One argv per batch: large fixtures exceed the OS argument size limit.
    per_batch = 6
    for start in range(0, len(inputs), per_batch):
        batch = inputs[start : start + per_batch]
        results = oracle_call({"op": "model-serialize-batch", "inputs": batch})
        assert isinstance(results, list)
        assert len(results) == len(batch)
        for offset, expected in enumerate(results):
            index = start + offset
            fid = f"{ids[index // 2]}#format={bool(index % 2)}"
            assert _serialize_py(xmls[index // 2], bool(index % 2)) == expected, fid
