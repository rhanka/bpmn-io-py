"""Ported RuleTester cases for the ``no-implicit-start`` rule.

Upstream suite: ``test/rules/no-implicit-start.mjs``.
"""

from __future__ import annotations

import pytest

from bpmn_io.lint.rules import no_implicit_start
from tests.lint.rules._case import assert_invalid, assert_valid

VALID = [
    {
        "config": None,
        "fixture": "no-implicit-start/valid.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-implicit-start/valid-collaboration.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
]

INVALID = [
    {
        "config": None,
        "fixture": "no-implicit-start/invalid.bpmn",
        "name": None,
        "report": [
            {"id": "END_EVENT", "message": "Element is an implicit start"},
            {"id": "INTERMEDIATE_THROW_EVENT", "message": "Element is an implicit start"},
            {"id": "TASK", "message": "Element is an implicit start"},
            {"id": "GATEWAY", "message": "Element is an implicit start"},
            {"id": "LINK_THROW", "message": "Element is an implicit start"},
            {"id": "INTERMEDIATE_CATCH_EVENT", "message": "Element is an implicit start"},
        ],
        "skipped": False,
    }
]


@pytest.mark.upstream(
    "bpmnlint/test/rules/no-implicit-start.mjs",
    "rules/no-implicit-start > should lint valid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-implicit-start.mjs",
    "rules/no-implicit-start > should lint valid > test case #2",
)
@pytest.mark.parametrize(
    "case",
    [c for c in VALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_valid(case: dict) -> None:
    assert_valid("no-implicit-start", no_implicit_start.factory, case)


@pytest.mark.upstream(
    "bpmnlint/test/rules/no-implicit-start.mjs",
    "rules/no-implicit-start > should lint invalid > test case #1",
)
@pytest.mark.parametrize(
    "case",
    [c for c in INVALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_invalid(case: dict) -> None:
    assert_invalid("no-implicit-start", no_implicit_start.factory, case)
