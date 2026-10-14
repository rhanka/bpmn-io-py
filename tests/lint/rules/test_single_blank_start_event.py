"""Ported RuleTester cases for the ``single-blank-start-event`` rule.

Upstream suite: ``test/rules/single-blank-start-event.mjs``.
"""

from __future__ import annotations

import pytest

from bpmn_io.lint.rules import single_blank_start_event
from tests.lint.rules._case import assert_invalid, assert_valid

VALID = [
    {
        "config": None,
        "fixture": "single-blank-start-event/valid.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "single-blank-start-event/valid-empty.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "single-blank-start-event/valid-end-event.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "single-blank-start-event/valid-sub-process.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "single-blank-start-event/valid-typed.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "single-blank-start-event/valid-typed-sub-process.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "single-blank-start-event/valid-scopes.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
]

INVALID = [
    {
        "config": None,
        "fixture": "single-blank-start-event/invalid.bpmn",
        "name": None,
        "report": {"id": "Process", "message": "Process has multiple blank start events"},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "single-blank-start-event/invalid-sub-process.bpmn",
        "name": None,
        "report": {"id": "SubProcess", "message": "Sub process has multiple blank start events"},
        "skipped": False,
    },
]


@pytest.mark.upstream(
    "bpmnlint/test/rules/single-blank-start-event.mjs",
    "rules/single-blank-start-event > should lint valid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/single-blank-start-event.mjs",
    "rules/single-blank-start-event > should lint valid > test case #2",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/single-blank-start-event.mjs",
    "rules/single-blank-start-event > should lint valid > test case #3",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/single-blank-start-event.mjs",
    "rules/single-blank-start-event > should lint valid > test case #4",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/single-blank-start-event.mjs",
    "rules/single-blank-start-event > should lint valid > test case #5",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/single-blank-start-event.mjs",
    "rules/single-blank-start-event > should lint valid > test case #6",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/single-blank-start-event.mjs",
    "rules/single-blank-start-event > should lint valid > test case #7",
)
@pytest.mark.parametrize(
    "case",
    [c for c in VALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_valid(case: dict) -> None:
    assert_valid("single-blank-start-event", single_blank_start_event.factory, case)


@pytest.mark.upstream(
    "bpmnlint/test/rules/single-blank-start-event.mjs",
    "rules/single-blank-start-event > should lint invalid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/single-blank-start-event.mjs",
    "rules/single-blank-start-event > should lint invalid > test case #2",
)
@pytest.mark.parametrize(
    "case",
    [c for c in INVALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_invalid(case: dict) -> None:
    assert_invalid("single-blank-start-event", single_blank_start_event.factory, case)
