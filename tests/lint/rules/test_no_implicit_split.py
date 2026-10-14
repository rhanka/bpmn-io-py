"""Ported RuleTester cases for the ``no-implicit-split`` rule.

Upstream suite: ``test/rules/no-implicit-split.mjs``.
"""

from __future__ import annotations

import pytest

from bpmn_io.lint.rules import no_implicit_split
from tests.lint.rules._case import assert_invalid, assert_valid

VALID = [
    {
        "config": None,
        "fixture": "no-implicit-split/valid.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-implicit-split/valid-default-conditional-flow.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
]

INVALID = [
    {
        "config": None,
        "fixture": "no-implicit-split/invalid-event.bpmn",
        "name": None,
        "report": {"id": "Element", "message": "Flow splits implicitly"},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-implicit-split/invalid-task.bpmn",
        "name": None,
        "report": {"id": "Element", "message": "Flow splits implicitly"},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-implicit-split/invalid-call-activity.bpmn",
        "name": None,
        "report": {"id": "Element", "message": "Flow splits implicitly"},
        "skipped": False,
    },
]


@pytest.mark.upstream(
    "bpmnlint/test/rules/no-implicit-split.mjs",
    "rules/no-implicit-split > should lint valid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-implicit-split.mjs",
    "rules/no-implicit-split > should lint valid > test case #2",
)
@pytest.mark.parametrize(
    "case",
    [c for c in VALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_valid(case: dict) -> None:
    assert_valid("no-implicit-split", no_implicit_split.factory, case)


@pytest.mark.upstream(
    "bpmnlint/test/rules/no-implicit-split.mjs",
    "rules/no-implicit-split > should lint invalid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-implicit-split.mjs",
    "rules/no-implicit-split > should lint invalid > test case #2",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-implicit-split.mjs",
    "rules/no-implicit-split > should lint invalid > test case #3",
)
@pytest.mark.parametrize(
    "case",
    [c for c in INVALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_invalid(case: dict) -> None:
    assert_invalid("no-implicit-split", no_implicit_split.factory, case)
