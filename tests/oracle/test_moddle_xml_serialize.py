"""Differential moddle-xml serialization: Python port vs pinned Node (Lot 6).

``op=model-serialize-batch`` (``tests/oracle/dump.mjs``, ``BpmnModdle`` —
always lax) parses each document and serializes it back with ``format``
false/true; the port reads lax through the six vendored descriptor packages
(five + the ``bpmn-in-color`` 6th package, BR01-COLOR resolved in Lot 7)
and serializes with the same options. Outputs must be byte-identical,
failures message-identical.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from test_dump import DESCRIPTORS, RESOURCES

from bpmn_io.moddle import Moddle
from bpmn_io.moddle_xml import Reader, Writer

if TYPE_CHECKING:
    from collections.abc import Callable

pytestmark = pytest.mark.oracle

FIXTURES = Path(__file__).parent.parent / "upstream" / "bpmn-moddle" / "test" / "fixtures" / "bpmn"

#: No exclusions: the 6th descriptor package is vendored (BR01-COLOR resolved
#: in Lot 7).
SKIP_FIXTURES = frozenset()

#: The six default descriptor packages (``DESCRIPTORS`` five + color).
PACKAGES = (*DESCRIPTORS, "color/bpmn-in-color.json")


def _serialize_py(
    xml: str,
    format: bool,  # noqa: A002, FBT001 - option names
) -> dict[str, Any]:
    """Parse lax and serialize back, capturing failures like the batch op."""
    packages = [json.loads((RESOURCES / rel).read_text(encoding="utf-8")) for rel in PACKAGES]
    try:
        root = Reader(Moddle(packages), lax=True).from_xml(xml, "bpmn:Definitions").root_element
        return {"xml": Writer(format=format, preamble=True).to_xml(root)}
    except Exception as exc:  # noqa: BLE001 — messages are the contract here
        return {"error": str(exc)}


def test_serialize_bytes_corpus(oracle_call: Callable[[dict[str, object]], object]) -> None:
    paths = sorted(p for p in FIXTURES.rglob("*.bpmn") if p.name not in SKIP_FIXTURES)
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
