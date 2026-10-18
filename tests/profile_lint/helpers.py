"""Shared fixtures for the profile lint bridge tests (lot 1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from bpmn_io.bpmn_moddle.simple import create_moddle
from bpmn_io.profile._lint.transform import flatten_policy, select_record

if TYPE_CHECKING:
    from bpmn_io.moddle.base import ModdleElement

ROOT = Path(__file__).resolve().parent.parent.parent
CONTRACTS = ROOT / "contracts" / "profile-mechanism" / "1"
CORPUS = ROOT / "contracts" / "profile-parity-corpus" / "1" / "cases"

Json = dict[str, "Json"] | list["Json"] | str | int | float | bool | None


def contract(name: str) -> Json:
    """Load a vendored profile-mechanism contract artifact."""
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def corpus_case(case_id: str) -> dict[str, Json]:
    """Load one parity-corpus case by its ``caseId``."""
    for path in sorted(CORPUS.glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        if case["caseId"] == case_id:
            return case
    msg = f"unknown corpus case: {case_id}"
    raise AssertionError(msg)


def by_role(case: dict[str, Json], role: str) -> Json:
    """Return the single artifact with ``role`` of a corpus case."""
    matches = [entry for entry in case["inputArtifacts"] if entry.get("role") == role]
    assert len(matches) == 1, f"expected exactly one {role!r} artifact"
    return matches[0]["json"]


def expected_role(case: dict[str, Json], role: str) -> Json:
    """Return the single expected artifact with ``role`` of a corpus case."""
    matches = [entry for entry in case["expectedArtifacts"] if entry.get("role") == role]
    assert len(matches) == 1, f"expected exactly one {role!r} artifact"
    return matches[0]["json"]


def parse(xml: str) -> ModdleElement:
    """Parse BPMN XML to its Definitions root (fails loudly when invalid)."""
    result = create_moddle().from_xml(xml)
    assert not result.warnings
    return result.root_element


def make_compiled(
    profile: dict[str, Json],
    *,
    phase: str,
    readiness_policy: str,
    registry: dict[str, Json] | None = None,
    profile_digest: str = "0" * 64,
) -> dict[str, Json]:
    """Build the ``compiled`` argument of ``lint`` from profile JSON data."""
    record = select_record(profile["validation"], phase=phase, readiness_policy=readiness_policy)
    flattened = flatten_policy(record, registry)
    return {
        "compiledOptions": {
            "mechanismVersion": "1",
            "profileDigest": profile_digest,
            "phase": phase,
            "readinessPolicy": readiness_policy,
            "compiledRules": profile["rules"],
            "bindings": [],
            "severityPolicyDigest": flattened.severity_policy_digest,
        },
        "validation": profile["validation"],
        "registry": registry or {},
    }


NAMED_TASK_DOC = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
    id="Definitions_1" targetNamespace="http://example.com/neutral">
  <bpmn:process id="Process_1" isExecutable="false">
    <bpmn:task id="Task_A" />
    <bpmn:task id="Task_B" name="Ready" />
  </bpmn:process>
</bpmn:definitions>
"""

CLEAN_DOC = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
    id="Definitions_1" targetNamespace="http://example.com/neutral">
  <bpmn:process id="Process_1" isExecutable="false">
    <bpmn:startEvent id="Start_1" name="Begin">
      <bpmn:outgoing>Flow_1</bpmn:outgoing>
    </bpmn:startEvent>
    <bpmn:task id="Task_1" name="Do">
      <bpmn:incoming>Flow_1</bpmn:incoming>
      <bpmn:outgoing>Flow_2</bpmn:outgoing>
    </bpmn:task>
    <bpmn:endEvent id="End_1" name="Done">
      <bpmn:incoming>Flow_2</bpmn:incoming>
    </bpmn:endEvent>
    <bpmn:sequenceFlow id="Flow_1" sourceRef="Start_1" targetRef="Task_1" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="Task_1" targetRef="End_1" />
  </bpmn:process>
</bpmn:definitions>
"""
