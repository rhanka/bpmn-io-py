"""Ported RuleTester cases for the ``no-implicit-end`` rule.

Upstream suite: ``test/rules/no-implicit-end.mjs``.
"""

from __future__ import annotations

import pytest

from bpmn_io.lint.rules import no_implicit_end
from tests.lint.rules._case import assert_invalid, assert_valid

VALID = [
    {
        "config": None,
        "fixture": "no-implicit-end/valid.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-implicit-end/valid-compensation.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-implicit-end/valid-collaboration.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
]

INVALID = [
    {
        "config": None,
        "fixture": "no-implicit-end/invalid.bpmn",
        "name": None,
        "report": [
            {"id": "INTERMEDIATE_THROW_EVENT", "message": "Element is an implicit end"},
            {"id": "TASK", "message": "Element is an implicit end"},
            {"id": "GATEWAY", "message": "Element is an implicit end"},
            {"id": "START_EVENT", "message": "Element is an implicit end"},
            {"id": "SUB_PROCESS", "message": "Element is an implicit end"},
            {"id": "BOUNDARY", "message": "Element is an implicit end"},
            {"id": "INTERMEDIATE_CATCH_EVENT", "message": "Element is an implicit end"},
            {"id": "LINK_CATCH_EVENT", "message": "Element is an implicit end"},
        ],
        "skipped": False,
    }
]


@pytest.mark.upstream(
    "bpmnlint/test/rules/no-implicit-end.mjs",
    "rules/no-implicit-end > should lint valid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-implicit-end.mjs",
    "rules/no-implicit-end > should lint valid > test case #2",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-implicit-end.mjs",
    "rules/no-implicit-end > should lint valid > test case #3",
)
@pytest.mark.parametrize(
    "case",
    [c for c in VALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_valid(case: dict) -> None:
    assert_valid("no-implicit-end", no_implicit_end.factory, case)


@pytest.mark.upstream(
    "bpmnlint/test/rules/no-implicit-end.mjs",
    "rules/no-implicit-end > should lint invalid > test case #1",
)
@pytest.mark.parametrize(
    "case",
    [c for c in INVALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_invalid(case: dict) -> None:
    assert_invalid("no-implicit-end", no_implicit_end.factory, case)
