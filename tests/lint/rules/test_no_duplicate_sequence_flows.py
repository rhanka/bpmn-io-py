"""Ported RuleTester cases for the ``no-duplicate-sequence-flows`` rule.

Upstream suite: ``test/rules/no-duplicate-sequence-flows.mjs``.
"""

from __future__ import annotations

import pytest

from bpmn_io.lint.rules import no_duplicate_sequence_flows
from tests.lint.rules._case import assert_invalid, assert_valid

VALID = [
    {
        "config": None,
        "fixture": "no-duplicate-sequence-flows/valid.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    }
]

INVALID = [
    {
        "config": None,
        "fixture": "no-duplicate-sequence-flows/invalid-no-condition.bpmn",
        "name": None,
        "report": [
            {"id": "SequenceFlow_2", "message": "SequenceFlow is a duplicate"},
            {"id": "StartEvent_1", "message": "Duplicate outgoing sequence flows"},
            {"id": "Task_2", "message": "Duplicate incoming sequence flows"},
        ],
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-duplicate-sequence-flows/invalid-condition.bpmn",
        "name": None,
        "report": [
            {"id": "SequenceFlow_1", "message": "SequenceFlow is a duplicate"},
            {"id": "Task_1", "message": "Duplicate outgoing sequence flows"},
            {"id": "Task_2", "message": "Duplicate incoming sequence flows"},
        ],
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-duplicate-sequence-flows/invalid-multiple.bpmn",
        "name": None,
        "report": [
            {"id": "SequenceFlow_2", "message": "SequenceFlow is a duplicate"},
            {"id": "Task_1", "message": "Duplicate outgoing sequence flows"},
            {"id": "Task_2", "message": "Duplicate incoming sequence flows"},
            {"id": "SequenceFlow_3", "message": "SequenceFlow is a duplicate"},
        ],
        "skipped": False,
    },
]


@pytest.mark.upstream(
    "bpmnlint/test/rules/no-duplicate-sequence-flows.mjs",
    "rules/no-duplicate-sequence-flows > should lint valid > test case #1",
)
@pytest.mark.parametrize(
    "case",
    [c for c in VALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_valid(case: dict) -> None:
    assert_valid("no-duplicate-sequence-flows", no_duplicate_sequence_flows.factory, case)


@pytest.mark.upstream(
    "bpmnlint/test/rules/no-duplicate-sequence-flows.mjs",
    "rules/no-duplicate-sequence-flows > should lint invalid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-duplicate-sequence-flows.mjs",
    "rules/no-duplicate-sequence-flows > should lint invalid > test case #2",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-duplicate-sequence-flows.mjs",
    "rules/no-duplicate-sequence-flows > should lint invalid > test case #3",
)
@pytest.mark.parametrize(
    "case",
    [c for c in INVALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_invalid(case: dict) -> None:
    assert_invalid("no-duplicate-sequence-flows", no_duplicate_sequence_flows.factory, case)
