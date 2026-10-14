"""Ported RuleTester cases for the ``no-gateway-join-fork`` rule.

Upstream suite: ``test/rules/no-gateway-join-fork.mjs``.
"""

from __future__ import annotations

import pytest

from bpmn_io.lint.rules import no_gateway_join_fork
from tests.lint.rules._case import assert_invalid, assert_valid

VALID = [
    {
        "config": None,
        "fixture": "no-gateway-join-fork/valid-fork.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-gateway-join-fork/valid-join.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-gateway-join-fork/valid-fork-join-task.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
]

INVALID = [
    {
        "config": None,
        "fixture": "no-gateway-join-fork/invalid.bpmn",
        "name": None,
        "report": {"id": "Gateway", "message": "Gateway forks and joins"},
        "skipped": False,
    }
]


@pytest.mark.upstream(
    "bpmnlint/test/rules/no-gateway-join-fork.mjs",
    "rules/no-gateway-join-fork > should lint valid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-gateway-join-fork.mjs",
    "rules/no-gateway-join-fork > should lint valid > test case #2",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-gateway-join-fork.mjs",
    "rules/no-gateway-join-fork > should lint valid > test case #3",
)
@pytest.mark.parametrize(
    "case",
    [c for c in VALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_valid(case: dict) -> None:
    assert_valid("no-gateway-join-fork", no_gateway_join_fork.factory, case)


@pytest.mark.upstream(
    "bpmnlint/test/rules/no-gateway-join-fork.mjs",
    "rules/no-gateway-join-fork > should lint invalid > test case #1",
)
@pytest.mark.parametrize(
    "case",
    [c for c in INVALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_invalid(case: dict) -> None:
    assert_invalid("no-gateway-join-fork", no_gateway_join_fork.factory, case)
