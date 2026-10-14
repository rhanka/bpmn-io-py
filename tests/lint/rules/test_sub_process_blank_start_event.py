"""Ported RuleTester cases for the ``sub-process-blank-start-event`` rule.

Upstream suite: ``test/rules/sub-process-blank-start-event.mjs``.
"""

from __future__ import annotations

import pytest

from bpmn_io.lint.rules import sub_process_blank_start_event
from tests.lint.rules._case import assert_invalid, assert_valid

VALID = [
    {
        "config": None,
        "fixture": "sub-process-blank-start-event/valid.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "sub-process-blank-start-event/valid-empty.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "sub-process-blank-start-event/valid-intermediate-event.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "sub-process-blank-start-event/valid-event-sub-process.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
]

INVALID = [
    {
        "config": None,
        "fixture": "sub-process-blank-start-event/invalid.bpmn",
        "name": None,
        "report": {
            "id": "StartEvent",
            "message": "Start event must be blank",
            "path": ["eventDefinitions"],
        },
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "sub-process-blank-start-event/invalid-ad-hoc.bpmn",
        "name": None,
        "report": {
            "id": "StartEvent",
            "message": "Start event must be blank",
            "path": ["eventDefinitions"],
        },
        "skipped": False,
    },
]


@pytest.mark.upstream(
    "bpmnlint/test/rules/sub-process-blank-start-event.mjs",
    "rules/sub-process-blank-start-event > should lint valid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/sub-process-blank-start-event.mjs",
    "rules/sub-process-blank-start-event > should lint valid > test case #2",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/sub-process-blank-start-event.mjs",
    "rules/sub-process-blank-start-event > should lint valid > test case #3",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/sub-process-blank-start-event.mjs",
    "rules/sub-process-blank-start-event > should lint valid > test case #4",
)
@pytest.mark.parametrize(
    "case",
    [c for c in VALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_valid(case: dict) -> None:
    assert_valid("sub-process-blank-start-event", sub_process_blank_start_event.factory, case)


@pytest.mark.upstream(
    "bpmnlint/test/rules/sub-process-blank-start-event.mjs",
    "rules/sub-process-blank-start-event > should lint invalid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/sub-process-blank-start-event.mjs",
    "rules/sub-process-blank-start-event > should lint invalid > test case #2",
)
@pytest.mark.parametrize(
    "case",
    [c for c in INVALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_invalid(case: dict) -> None:
    assert_invalid("sub-process-blank-start-event", sub_process_blank_start_event.factory, case)
