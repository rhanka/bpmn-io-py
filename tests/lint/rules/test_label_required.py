"""Ported RuleTester cases for the ``label-required`` rule.

Upstream suite: ``test/rules/label-required.mjs``.
"""

from __future__ import annotations

import pytest

from bpmn_io.lint.rules import label_required
from tests.lint.rules._case import assert_invalid, assert_valid

VALID = [
    {
        "config": None,
        "fixture": "label-required/valid-boundary-event.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "label-required/valid-conditional-flow.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "label-required/valid-data-objects.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "label-required/valid-gateways.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "label-required/valid-start-event.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "label-required/valid-participant-lanes.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
]

INVALID = [
    {
        "config": None,
        "fixture": "label-required/invalid-conditional-flow.bpmn",
        "name": None,
        "report": {
            "id": "ConditionalFlow",
            "message": "Element is missing label/name",
            "path": ["name"],
        },
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "label-required/invalid-event.bpmn",
        "name": None,
        "report": {"id": "Element", "message": "Element is missing label/name", "path": ["name"]},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "label-required/invalid-gateway-split.bpmn",
        "name": None,
        "report": {"id": "Element", "message": "Element is missing label/name", "path": ["name"]},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "label-required/invalid-participant.bpmn",
        "name": None,
        "report": {"id": "Element", "message": "Element is missing label/name", "path": ["name"]},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "label-required/invalid-lane.bpmn",
        "name": None,
        "report": {"id": "Element", "message": "Element is missing label/name", "path": ["name"]},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "label-required/invalid-task.bpmn",
        "name": None,
        "report": {"id": "Element", "message": "Element is missing label/name", "path": ["name"]},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "label-required/invalid-boundary-event.bpmn",
        "name": None,
        "report": {"id": "Element", "message": "Element is missing label/name", "path": ["name"]},
        "skipped": False,
    },
]


@pytest.mark.upstream(
    "bpmnlint/test/rules/label-required.mjs",
    "rules/label-required > should lint valid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/label-required.mjs",
    "rules/label-required > should lint valid > test case #2",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/label-required.mjs",
    "rules/label-required > should lint valid > test case #3",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/label-required.mjs",
    "rules/label-required > should lint valid > test case #4",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/label-required.mjs",
    "rules/label-required > should lint valid > test case #5",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/label-required.mjs",
    "rules/label-required > should lint valid > test case #6",
)
@pytest.mark.parametrize(
    "case",
    [c for c in VALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_valid(case: dict) -> None:
    assert_valid("label-required", label_required.factory, case)


@pytest.mark.upstream(
    "bpmnlint/test/rules/label-required.mjs",
    "rules/label-required > should lint invalid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/label-required.mjs",
    "rules/label-required > should lint invalid > test case #2",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/label-required.mjs",
    "rules/label-required > should lint invalid > test case #3",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/label-required.mjs",
    "rules/label-required > should lint invalid > test case #4",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/label-required.mjs",
    "rules/label-required > should lint invalid > test case #5",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/label-required.mjs",
    "rules/label-required > should lint invalid > test case #6",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/label-required.mjs",
    "rules/label-required > should lint invalid > test case #7",
)
@pytest.mark.parametrize(
    "case",
    [c for c in INVALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_invalid(case: dict) -> None:
    assert_invalid("label-required", label_required.factory, case)
