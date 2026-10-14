"""Ported RuleTester cases for the ``superfluous-gateway`` rule.

Upstream suite: ``test/rules/superfluous-gateway.mjs``.
"""

from __future__ import annotations

import pytest

from bpmn_io.lint.rules import superfluous_gateway
from tests.lint.rules._case import assert_invalid, assert_valid

VALID = [
    {
        "config": None,
        "fixture": "superfluous-gateway/valid.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "superfluous-gateway/valid-none-gateway.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
]

INVALID = [
    {
        "config": None,
        "fixture": "superfluous-gateway/invalid.bpmn",
        "name": None,
        "report": {
            "id": "Gateway_1",
            "message": "Gateway is superfluous. It only has one source and target.",
        },
        "skipped": False,
    }
]


@pytest.mark.upstream(
    "bpmnlint/test/rules/superfluous-gateway.mjs",
    "rules/superfluous-gateway > should lint valid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/superfluous-gateway.mjs",
    "rules/superfluous-gateway > should lint valid > test case #2",
)
@pytest.mark.parametrize(
    "case",
    [c for c in VALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_valid(case: dict) -> None:
    assert_valid("superfluous-gateway", superfluous_gateway.factory, case)


@pytest.mark.upstream(
    "bpmnlint/test/rules/superfluous-gateway.mjs",
    "rules/superfluous-gateway > should lint invalid > test case #1",
)
@pytest.mark.parametrize(
    "case",
    [c for c in INVALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_invalid(case: dict) -> None:
    assert_invalid("superfluous-gateway", superfluous_gateway.factory, case)
