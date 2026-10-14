"""Ported RuleTester cases for the ``link-event`` rule.

Upstream suite: ``test/rules/link-event.mjs``.
"""

from __future__ import annotations

import pytest

from bpmn_io.lint.rules import link_event
from tests.lint.rules._case import assert_invalid, assert_valid

VALID = [
    {
        "config": None,
        "fixture": "link-event/valid.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "link-event/valid-collaboration.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
]

INVALID = [
    {
        "config": None,
        "fixture": "link-event/invalid.bpmn",
        "name": None,
        "report": [
            {"id": "CATCH_NO_NAME", "message": "Link event is missing link name"},
            {"id": "THROW_NO_NAME", "message": "Link event is missing link name"},
            {
                "id": "NO_CATCH",
                "message": "Link catch event with link name <NO_CATCH> missing in scope",
            },
            {
                "id": "NO_THROW",
                "message": "Link throw event with link name <NO_THROW> missing in scope",
            },
            {
                "id": "SCOPE_BOUNDARY_THROW",
                "message": "Link catch event with link name <SCOPE_BOUNDARY> missing in scope",
            },
            {
                "id": "DUPLICATE_NAME_CATCH_1",
                "message": "Duplicate link catch event with link name <DUPLICATE_LINK_NAME> in "
                "scope",
            },
            {
                "id": "DUPLICATE_NAME_CATCH_2",
                "message": "Duplicate link catch event with link name <DUPLICATE_LINK_NAME> in "
                "scope",
            },
            {
                "id": "SCOPE_BOUNDARY_CATCH",
                "message": "Link throw event with link name <SCOPE_BOUNDARY> missing in scope",
            },
        ],
        "skipped": False,
    }
]


@pytest.mark.upstream(
    "bpmnlint/test/rules/link-event.mjs",
    "rules/link-event > should lint valid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/link-event.mjs",
    "rules/link-event > should lint valid > test case #2",
)
@pytest.mark.parametrize(
    "case",
    [c for c in VALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_valid(case: dict) -> None:
    assert_valid("link-event", link_event.factory, case)


@pytest.mark.upstream(
    "bpmnlint/test/rules/link-event.mjs",
    "rules/link-event > should lint invalid > test case #1",
)
@pytest.mark.parametrize(
    "case",
    [c for c in INVALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_invalid(case: dict) -> None:
    assert_invalid("link-event", link_event.factory, case)
