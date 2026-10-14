"""Ported RuleTester cases for the ``superfluous-termination`` rule.

Upstream suite: ``test/rules/superfluous-termination.mjs``.
"""

from __future__ import annotations

import pytest

from bpmn_io.lint.rules import superfluous_termination
from tests.lint.rules._case import assert_invalid, assert_valid

VALID = [
    {
        "config": None,
        "fixture": "superfluous-termination/valid.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "superfluous-termination/valid-implicit-end.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "superfluous-termination/valid-boundary-non-interrupting.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "superfluous-termination/valid-event-sub-process-non-interrupting.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
]

INVALID = [
    {
        "config": None,
        "fixture": "superfluous-termination/invalid.bpmn",
        "name": None,
        "report": {"id": "TERMINATE_EVENT", "message": "Termination is superfluous."},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "superfluous-termination/invalid-boundary-interrupting.bpmn",
        "name": None,
        "report": {"id": "TERMINATE_EVENT", "message": "Termination is superfluous."},
        "skipped": True,
    },
    {
        "config": None,
        "fixture": "superfluous-termination/invalid-event-sub-process-interrupting.bpmn",
        "name": None,
        "report": {"id": "TERMINATE_EVENT", "message": "Termination is superfluous."},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "superfluous-termination/invalid-exclusive-paths.bpmn",
        "name": None,
        "report": {"id": "TERMINATE_EVENT", "message": "Termination is superfluous."},
        "skipped": True,
    },
    {
        "config": None,
        "fixture": "superfluous-termination/invalid-sub-process.bpmn",
        "name": None,
        "report": {"id": "TERMINATE_EVENT", "message": "Termination is superfluous."},
        "skipped": False,
    },
]


@pytest.mark.upstream(
    "bpmnlint/test/rules/superfluous-termination.mjs",
    "rules/superfluous-termination > should lint valid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/superfluous-termination.mjs",
    "rules/superfluous-termination > should lint valid > test case #2",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/superfluous-termination.mjs",
    "rules/superfluous-termination > should lint valid > test case #3",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/superfluous-termination.mjs",
    "rules/superfluous-termination > should lint valid > test case #4",
)
@pytest.mark.parametrize(
    "case",
    [c for c in VALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_valid(case: dict) -> None:
    assert_valid("superfluous-termination", superfluous_termination.factory, case)


@pytest.mark.upstream(
    "bpmnlint/test/rules/superfluous-termination.mjs",
    "rules/superfluous-termination > should lint invalid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/superfluous-termination.mjs",
    "rules/superfluous-termination > should lint invalid > test case #3",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/superfluous-termination.mjs",
    "rules/superfluous-termination > should lint invalid > test case #5",
)
@pytest.mark.parametrize(
    "case",
    [c for c in INVALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_invalid(case: dict) -> None:
    assert_invalid("superfluous-termination", superfluous_termination.factory, case)
