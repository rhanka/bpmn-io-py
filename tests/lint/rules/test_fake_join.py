"""Ported RuleTester cases for the ``fake-join`` rule.

Upstream suite: ``test/rules/fake-join.mjs``.
"""

from __future__ import annotations

import pytest

from bpmn_io.lint.rules import fake_join
from tests.lint.rules._case import assert_invalid, assert_valid

VALID = [
    {
        "config": None,
        "fixture": "fake-join/valid.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "fake-join/valid-gateway.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
]

INVALID = [
    {
        "config": None,
        "fixture": "fake-join/invalid-task.bpmn",
        "name": None,
        "report": {"id": "Element", "message": "Incoming flows do not join"},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "fake-join/invalid-callActivity.bpmn",
        "name": None,
        "report": {"id": "Element", "message": "Incoming flows do not join"},
        "skipped": False,
    },
]


@pytest.mark.upstream(
    "bpmnlint/test/rules/fake-join.mjs",
    "rules/fake-join > should lint valid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/fake-join.mjs",
    "rules/fake-join > should lint valid > test case #2",
)
@pytest.mark.parametrize(
    "case",
    [c for c in VALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_valid(case: dict) -> None:
    assert_valid("fake-join", fake_join.factory, case)


@pytest.mark.upstream(
    "bpmnlint/test/rules/fake-join.mjs",
    "rules/fake-join > should lint invalid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/fake-join.mjs",
    "rules/fake-join > should lint invalid > test case #2",
)
@pytest.mark.parametrize(
    "case",
    [c for c in INVALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_invalid(case: dict) -> None:
    assert_invalid("fake-join", fake_join.factory, case)
