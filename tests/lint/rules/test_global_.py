"""Ported RuleTester cases for the ``global`` rule.

Upstream suite: ``test/rules/global.mjs``.
"""

from __future__ import annotations

import pytest

from bpmn_io.lint.rules import global_
from tests.lint.rules._case import assert_invalid, assert_valid

VALID = [
    {
        "config": None,
        "fixture": "global/valid-error.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "global/valid-escalation.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "global/valid-message.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "global/valid-no-ref.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
]

INVALID = [
    {
        "config": None,
        "fixture": "global/invalid-error-missing-name.bpmn",
        "name": None,
        "report": {"id": "Error", "message": "Element is missing name"},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "global/invalid-escalation-missing-name.bpmn",
        "name": None,
        "report": {"id": "Escalation", "message": "Element is missing name"},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "global/invalid-message-missing-name.bpmn",
        "name": None,
        "report": {"id": "Message", "message": "Element is missing name"},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "global/invalid-signal-missing-name.bpmn",
        "name": None,
        "report": {"id": "Signal", "message": "Element is missing name"},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "global/invalid-error-missing-reference.bpmn",
        "name": None,
        "report": {"id": "Error", "message": "Element is unused"},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "global/invalid-escalation-missing-reference.bpmn",
        "name": None,
        "report": {"id": "Escalation", "message": "Element is unused"},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "global/invalid-message-missing-reference.bpmn",
        "name": None,
        "report": {"id": "Message", "message": "Element is unused"},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "global/invalid-signal-missing-reference.bpmn",
        "name": None,
        "report": {"id": "Signal", "message": "Element is unused"},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "global/invalid-error-duplicate-name.bpmn",
        "name": None,
        "report": [
            {"id": "Error_1", "message": "Element name is not unique"},
            {"id": "Error_2", "message": "Element name is not unique"},
        ],
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "global/invalid-escalation-duplicate-name.bpmn",
        "name": None,
        "report": [
            {"id": "Escalation_1", "message": "Element name is not unique"},
            {"id": "Escalation_2", "message": "Element name is not unique"},
        ],
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "global/invalid-message-duplicate-name.bpmn",
        "name": None,
        "report": [
            {"id": "Message_1", "message": "Element name is not unique"},
            {"id": "Message_2", "message": "Element name is not unique"},
        ],
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "global/invalid-signal-duplicate-name.bpmn",
        "name": None,
        "report": [
            {"id": "Signal_1", "message": "Element name is not unique"},
            {"id": "Signal_2", "message": "Element name is not unique"},
        ],
        "skipped": False,
    },
]


@pytest.mark.upstream(
    "bpmnlint/test/rules/global.mjs",
    "rules/global > should lint valid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/global.mjs",
    "rules/global > should lint valid > test case #2",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/global.mjs",
    "rules/global > should lint valid > test case #3",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/global.mjs",
    "rules/global > should lint valid > test case #4",
)
@pytest.mark.parametrize(
    "case",
    [c for c in VALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_valid(case: dict) -> None:
    assert_valid("global", global_.factory, case)


@pytest.mark.upstream(
    "bpmnlint/test/rules/global.mjs",
    "rules/global > should lint invalid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/global.mjs",
    "rules/global > should lint invalid > test case #2",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/global.mjs",
    "rules/global > should lint invalid > test case #3",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/global.mjs",
    "rules/global > should lint invalid > test case #4",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/global.mjs",
    "rules/global > should lint invalid > test case #5",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/global.mjs",
    "rules/global > should lint invalid > test case #6",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/global.mjs",
    "rules/global > should lint invalid > test case #7",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/global.mjs",
    "rules/global > should lint invalid > test case #8",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/global.mjs",
    "rules/global > should lint invalid > test case #9",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/global.mjs",
    "rules/global > should lint invalid > test case #10",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/global.mjs",
    "rules/global > should lint invalid > test case #11",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/global.mjs",
    "rules/global > should lint invalid > test case #12",
)
@pytest.mark.parametrize(
    "case",
    [c for c in INVALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_invalid(case: dict) -> None:
    assert_invalid("global", global_.factory, case)
