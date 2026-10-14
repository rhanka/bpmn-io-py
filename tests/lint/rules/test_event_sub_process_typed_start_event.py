"""Ported RuleTester cases for the ``event-sub-process-typed-start-event`` rule.

Upstream suite: ``test/rules/event-sub-process-typed-start-event.mjs``.
"""

from __future__ import annotations

import pytest

from bpmn_io.lint.rules import event_sub_process_typed_start_event
from tests.lint.rules._case import assert_invalid, assert_valid

VALID = [
    {
        "config": None,
        "fixture": "event-sub-process-typed-start-event/valid.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "event-sub-process-typed-start-event/valid-empty.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "event-sub-process-typed-start-event/valid-empty-sub-process.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "event-sub-process-typed-start-event/valid-intermediate-event.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "event-sub-process-typed-start-event/valid-sub-process.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
]

INVALID = [
    {
        "config": None,
        "fixture": "event-sub-process-typed-start-event/invalid.bpmn",
        "name": None,
        "report": {
            "id": "StartEvent",
            "message": "Start event is missing event definition",
            "path": ["eventDefinitions"],
        },
        "skipped": False,
    }
]


@pytest.mark.upstream(
    "bpmnlint/test/rules/event-sub-process-typed-start-event.mjs",
    "rules/event-sub-process-typed-start-event > should lint valid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/event-sub-process-typed-start-event.mjs",
    "rules/event-sub-process-typed-start-event > should lint valid > test case #2",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/event-sub-process-typed-start-event.mjs",
    "rules/event-sub-process-typed-start-event > should lint valid > test case #3",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/event-sub-process-typed-start-event.mjs",
    "rules/event-sub-process-typed-start-event > should lint valid > test case #4",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/event-sub-process-typed-start-event.mjs",
    "rules/event-sub-process-typed-start-event > should lint valid > test case #5",
)
@pytest.mark.parametrize(
    "case",
    [c for c in VALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_valid(case: dict) -> None:
    assert_valid(
        "event-sub-process-typed-start-event", event_sub_process_typed_start_event.factory, case
    )


@pytest.mark.upstream(
    "bpmnlint/test/rules/event-sub-process-typed-start-event.mjs",
    "rules/event-sub-process-typed-start-event > should lint invalid > test case #1",
)
@pytest.mark.parametrize(
    "case",
    [c for c in INVALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_invalid(case: dict) -> None:
    assert_invalid(
        "event-sub-process-typed-start-event", event_sub_process_typed_start_event.factory, case
    )
