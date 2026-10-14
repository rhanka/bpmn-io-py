"""Ported RuleTester cases for the ``conditional-event`` rule.

Upstream suite: ``test/rules/conditional-event.mjs``.
"""

from __future__ import annotations

import pytest

from bpmn_io.lint.rules import conditional_event
from tests.lint.rules._case import assert_invalid, assert_valid

VALID = [
    {
        "config": None,
        "fixture": "conditional-event/valid.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "conditional-event/not-executable.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
]

INVALID = [
    {
        "config": None,
        "fixture": "conditional-event/missing-condition.bpmn",
        "name": None,
        "report": [
            {
                "id": "Event_1",
                "message": "Conditional event is missing a condition",
                "path": ["condition"],
            }
        ],
        "skipped": False,
    }
]


@pytest.mark.upstream(
    "bpmnlint/test/rules/conditional-event.mjs",
    "rules/conditional-event > should lint valid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/conditional-event.mjs",
    "rules/conditional-event > should lint valid > test case #2",
)
@pytest.mark.parametrize(
    "case",
    [c for c in VALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_valid(case: dict) -> None:
    assert_valid("conditional-event", conditional_event.factory, case)


@pytest.mark.upstream(
    "bpmnlint/test/rules/conditional-event.mjs",
    "rules/conditional-event > should lint invalid > test case #1",
)
@pytest.mark.parametrize(
    "case",
    [c for c in INVALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_invalid(case: dict) -> None:
    assert_invalid("conditional-event", conditional_event.factory, case)
