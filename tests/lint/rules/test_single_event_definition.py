"""Ported RuleTester cases for the ``single-event-definition`` rule.

Upstream suite: ``test/rules/single-event-definition.mjs``.
"""

from __future__ import annotations

import pytest

from bpmn_io.lint.rules import single_event_definition
from tests.lint.rules._case import assert_invalid, assert_valid

VALID = [
    {
        "config": None,
        "fixture": "single-event-definition/valid.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "single-event-definition/valid-blank.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
]

INVALID = [
    {
        "config": None,
        "fixture": "single-event-definition/invalid.bpmn",
        "name": None,
        "report": {
            "id": "Event",
            "message": "Event has multiple event definitions",
            "path": ["eventDefinitions"],
        },
        "skipped": False,
    }
]


@pytest.mark.upstream(
    "bpmnlint/test/rules/single-event-definition.mjs",
    "rules/single-event-definition > should lint valid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/single-event-definition.mjs",
    "rules/single-event-definition > should lint valid > test case #2",
)
@pytest.mark.parametrize(
    "case",
    [c for c in VALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_valid(case: dict) -> None:
    assert_valid("single-event-definition", single_event_definition.factory, case)


@pytest.mark.upstream(
    "bpmnlint/test/rules/single-event-definition.mjs",
    "rules/single-event-definition > should lint invalid > test case #1",
)
@pytest.mark.parametrize(
    "case",
    [c for c in INVALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_invalid(case: dict) -> None:
    assert_invalid("single-event-definition", single_event_definition.factory, case)
