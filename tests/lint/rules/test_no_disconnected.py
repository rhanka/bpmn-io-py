"""Ported RuleTester cases for the ``no-disconnected`` rule.

Upstream suite: ``test/rules/no-disconnected.mjs``.
"""

from __future__ import annotations

import pytest

from bpmn_io.lint.rules import no_disconnected
from tests.lint.rules._case import assert_invalid, assert_valid

VALID = [
    {
        "config": None,
        "fixture": "no-disconnected/valid.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-disconnected/valid-text-annotation.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-disconnected/valid-event-subprocess.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-disconnected/valid-adhoc-subprocess.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-disconnected/valid-compensation.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
]

INVALID = [
    {
        "config": None,
        "fixture": "no-disconnected/invalid.bpmn",
        "name": None,
        "report": {"id": "Element", "message": "Element is not connected"},
        "skipped": False,
    }
]


@pytest.mark.upstream(
    "bpmnlint/test/rules/no-disconnected.mjs",
    "rules/no-disconnected > should lint valid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-disconnected.mjs",
    "rules/no-disconnected > should lint valid > test case #2",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-disconnected.mjs",
    "rules/no-disconnected > should lint valid > test case #3",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-disconnected.mjs",
    "rules/no-disconnected > should lint valid > test case #4",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-disconnected.mjs",
    "rules/no-disconnected > should lint valid > test case #5",
)
@pytest.mark.parametrize(
    "case",
    [c for c in VALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_valid(case: dict) -> None:
    assert_valid("no-disconnected", no_disconnected.factory, case)


@pytest.mark.upstream(
    "bpmnlint/test/rules/no-disconnected.mjs",
    "rules/no-disconnected > should lint invalid > test case #1",
)
@pytest.mark.parametrize(
    "case",
    [c for c in INVALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_invalid(case: dict) -> None:
    assert_invalid("no-disconnected", no_disconnected.factory, case)
