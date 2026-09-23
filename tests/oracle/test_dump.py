"""Oracle truth tests for the canonical dumper (Lot 1).

These lock the JS-side canonical shapes; later lots compare the Python port against
the same ops. Descriptor packages are read from the vendored resources (the same
bytes the Python port loads).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

ROOT = Path(__file__).parents[2]
RESOURCES = ROOT / "src" / "bpmn_io" / "resources"

DESCRIPTORS = (
    "bpmn/bpmn.json",
    "bpmn/bpmndi.json",
    "bpmn/dc.json",
    "bpmn/di.json",
    "bpmn-io/bioc.json",
)

NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"

pytestmark = pytest.mark.oracle


def _packages() -> list[object]:
    return [json.loads((RESOURCES / rel).read_text(encoding="utf-8")) for rel in DESCRIPTORS]


def test_descriptor_dump_shape(oracle_call: Callable[[dict[str, object]], object]) -> None:
    out = oracle_call({"op": "descriptor-dump", "packages": _packages()})
    assert len(out["types"]) == 161
    assert [entry["name"] for entry in out["skipped"]] == [
        "bioc:ColoredEdge",
        "bioc:ColoredShape",
    ]
    names = [entry["name"] for entry in out["types"]]
    assert names == sorted(names)
    task = {entry["name"]: entry for entry in out["types"]}["bpmn:Task"]
    assert len(task["properties"]) == 24
    assert task["properties"][0]["name"] == "id"
    assert "bpmn:Activity" in task["allTypes"]


def test_descriptor_dump_deterministic(
    oracle_call: Callable[[dict[str, object]], object],
) -> None:
    first = oracle_call({"op": "descriptor-dump", "packages": _packages()})
    second = oracle_call({"op": "descriptor-dump", "packages": _packages()})
    assert first == second


def test_model_dump_small_process(oracle_call: Callable[[dict[str, object]], object]) -> None:
    xml = (
        f'<bpmn:definitions xmlns:bpmn="{NS}" id="D">'
        '<bpmn:process id="P" isExecutable="false">'
        '<bpmn:startEvent id="S" />'
        "</bpmn:process></bpmn:definitions>"
    )
    out = oracle_call({"op": "model-dump", "xml": xml, "type": "bpmn:Definitions"})
    assert out["root"]["$type"] == "bpmn:Definitions"
    assert out["root"]["id"] == "D"
    assert out["root"]["$attrs"] == {"xmlns:bpmn": NS}
    assert set(out["elementsById"]) == {"D", "P", "S"}
    assert out["references"] == []
    assert out["warnings"] == []
    (process,) = out["root"]["rootElements"]
    assert process["$type"] == "bpmn:Process"
    (event,) = process["flowElements"]
    assert event == {"$type": "bpmn:StartEvent", "id": "S", "$attrs": {}}


def test_model_dump_warnings_and_references(
    oracle_call: Callable[[dict[str, object]], object],
) -> None:
    xml = (
        f'<bpmn:definitions xmlns:bpmn="{NS}" id="D" foo="1">'
        '<bpmn:process id="P"><bpmn:startEvent id="S" outgoing="MISSING" />'
        "</bpmn:process></bpmn:definitions>"
    )
    out = oracle_call({"op": "model-dump", "xml": xml, "type": "bpmn:Definitions"})
    assert [warning["message"] for warning in out["warnings"]] == [
        "unknown attribute <foo>",
        "unresolved reference <MISSING>",
    ]
    assert out["references"] == [{"element": "S", "property": "bpmn:outgoing", "id": "MISSING"}]
    element = out["warnings"][1]["element"]
    # `outgoing` stays as the empty collection lazily created by reference
    # resolution (moddle-xml `resolveReferences` via `Properties.get`).
    assert element == {"$type": "bpmn:StartEvent", "id": "S", "outgoing": [], "$attrs": {}}
