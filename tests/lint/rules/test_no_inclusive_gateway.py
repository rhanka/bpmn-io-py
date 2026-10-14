"""Ported RuleTester cases for the ``no-inclusive-gateway`` rule.

Upstream suite: ``test/rules/no-inclusive-gateway.mjs``.
"""

from __future__ import annotations

import pytest

from bpmn_io.lint.rules import no_inclusive_gateway
from tests.lint.rules._case import assert_invalid, assert_valid

VALID = [
    {
        "config": None,
        "fixture": "no-inclusive-gateway/valid.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    }
]

INVALID = [
    {
        "config": None,
        "fixture": "no-inclusive-gateway/invalid.bpmn",
        "name": None,
        "report": {
            "id": "Gateway",
            "message": "Element type <bpmn:InclusiveGateway> is discouraged",
        },
        "skipped": False,
    }
]


@pytest.mark.upstream(
    "bpmnlint/test/rules/no-inclusive-gateway.mjs",
    "rules/no-inclusive-gateway > should lint valid > test case #1",
)
@pytest.mark.parametrize(
    "case",
    [c for c in VALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_valid(case: dict) -> None:
    assert_valid("no-inclusive-gateway", no_inclusive_gateway.factory, case)


@pytest.mark.upstream(
    "bpmnlint/test/rules/no-inclusive-gateway.mjs",
    "rules/no-inclusive-gateway > should lint invalid > test case #1",
)
@pytest.mark.parametrize(
    "case",
    [c for c in INVALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_invalid(case: dict) -> None:
    assert_invalid("no-inclusive-gateway", no_inclusive_gateway.factory, case)
