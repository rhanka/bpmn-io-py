"""Ported RuleTester cases for the ``start-event-required`` rule.

Upstream suite: ``test/rules/start-event-required.mjs``.
"""

from __future__ import annotations

import pytest

from bpmn_io.lint.rules import start_event_required
from tests.lint.rules._case import assert_invalid, assert_valid

VALID = [
    {
        "config": None,
        "fixture": "start-event-required/valid.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "start-event-required/valid-sub-process.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "start-event-required/valid-sub-process-sub-types.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
]

INVALID = [
    {
        "config": None,
        "fixture": "start-event-required/invalid.bpmn",
        "name": None,
        "report": {"id": "Process", "message": "Process is missing start event"},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "start-event-required/invalid-sub-process.bpmn",
        "name": None,
        "report": {"id": "SubProcess", "message": "Sub process is missing start event"},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "start-event-required/invalid-sub-process-sub-types.bpmn",
        "name": None,
        "report": [
            {"id": "TRANSACTION", "message": "Sub process is missing start event"},
            {"id": "EVENT_SUBPROCESS", "message": "Sub process is missing start event"},
        ],
        "skipped": False,
    },
]


@pytest.mark.upstream(
    "bpmnlint/test/rules/start-event-required.mjs",
    "rules/start-event-required > should lint valid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/start-event-required.mjs",
    "rules/start-event-required > should lint valid > test case #2",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/start-event-required.mjs",
    "rules/start-event-required > should lint valid > test case #3",
)
@pytest.mark.parametrize(
    "case",
    [c for c in VALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_valid(case: dict) -> None:
    assert_valid("start-event-required", start_event_required.factory, case)


@pytest.mark.upstream(
    "bpmnlint/test/rules/start-event-required.mjs",
    "rules/start-event-required > should lint invalid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/start-event-required.mjs",
    "rules/start-event-required > should lint invalid > test case #2",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/start-event-required.mjs",
    "rules/start-event-required > should lint invalid > test case #3",
)
@pytest.mark.parametrize(
    "case",
    [c for c in INVALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_invalid(case: dict) -> None:
    assert_invalid("start-event-required", start_event_required.factory, case)
