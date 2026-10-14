"""Ported RuleTester cases for the ``event-based-gateway`` rule.

Upstream suite: ``test/rules/event-based-gateway.mjs``.
"""

from __future__ import annotations

import pytest

from bpmn_io.lint.rules import event_based_gateway
from tests.lint.rules._case import assert_invalid, assert_valid

VALID = [
    {
        "config": None,
        "fixture": "event-based-gateway/valid.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    }
]

INVALID = [
    {
        "config": None,
        "fixture": "event-based-gateway/invalid-no-outgoing.bpmn",
        "name": None,
        "report": {
            "id": "Gateway_1",
            "message": "An <Event-based Gateway> must have at least 2 outgoing <Sequence Flows>",
        },
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "event-based-gateway/invalid-one-outgoing.bpmn",
        "name": None,
        "report": {
            "id": "Gateway_1",
            "message": "An <Event-based Gateway> must have at least 2 outgoing <Sequence Flows>",
        },
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "event-based-gateway/invalid-conditional-flow.bpmn",
        "name": None,
        "report": {
            "id": "Flow_2",
            "message": "A <Sequence Flow> outgoing from an <Event-based Gateway> must not be "
            "conditional",
        },
        "skipped": False,
    },
]


@pytest.mark.upstream(
    "bpmnlint/test/rules/event-based-gateway.mjs",
    "rules/event-based-gateway > should lint valid > test case #1",
)
@pytest.mark.parametrize(
    "case",
    [c for c in VALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_valid(case: dict) -> None:
    assert_valid("event-based-gateway", event_based_gateway.factory, case)


@pytest.mark.upstream(
    "bpmnlint/test/rules/event-based-gateway.mjs",
    "rules/event-based-gateway > should lint invalid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/event-based-gateway.mjs",
    "rules/event-based-gateway > should lint invalid > test case #2",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/event-based-gateway.mjs",
    "rules/event-based-gateway > should lint invalid > test case #3",
)
@pytest.mark.parametrize(
    "case",
    [c for c in INVALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_invalid(case: dict) -> None:
    assert_invalid("event-based-gateway", event_based_gateway.factory, case)
