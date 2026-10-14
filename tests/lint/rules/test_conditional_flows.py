"""Ported RuleTester cases for the ``conditional-flows`` rule.

Upstream suite: ``test/rules/conditional-flows.mjs``.
"""

from __future__ import annotations

import pytest

from bpmn_io.lint.rules import conditional_flows
from tests.lint.rules._case import assert_invalid, assert_valid

VALID = [
    {
        "config": None,
        "fixture": "conditional-flows/valid-split.bpmn",
        "name": "split",
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "conditional-flows/valid-split-after-task.bpmn",
        "name": "split after task",
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "conditional-flows/valid-conditional-fork.bpmn",
        "name": "conditional fork",
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "conditional-flows/valid-no-condition-after-merge.bpmn",
        "name": "no condition after merge",
        "report": None,
        "skipped": False,
    },
]

INVALID = [
    {
        "config": None,
        "fixture": "conditional-flows/invalid-fork-after-exclusive-gateway.bpmn",
        "name": "fork after exclusive gateway",
        "report": {
            "id": "Flow_2",
            "message": "Sequence flow is missing condition",
            "path": ["conditionExpression"],
        },
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "conditional-flows/invalid-fork-after-exclusive-gateway-default.bpmn",
        "name": "fork after exclusive gateway default",
        "report": {
            "id": "Flow_1",
            "message": "Sequence flow is missing condition",
            "path": ["conditionExpression"],
        },
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "conditional-flows/invalid-fork-after-task.bpmn",
        "name": "fork after task",
        "report": {
            "id": "Flow_1",
            "message": "Sequence flow is missing condition",
            "path": ["conditionExpression"],
        },
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "conditional-flows/invalid-fork-after-task-default.bpmn",
        "name": "fork after task default",
        "report": {
            "id": "Flow_1",
            "message": "Sequence flow is missing condition",
            "path": ["conditionExpression"],
        },
        "skipped": False,
    },
]


@pytest.mark.upstream(
    "bpmnlint/test/rules/conditional-flows.mjs",
    "rules/conditional-flows > should lint valid > test case #1 split",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/conditional-flows.mjs",
    "rules/conditional-flows > should lint valid > test case #2 split after task",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/conditional-flows.mjs",
    "rules/conditional-flows > should lint valid > test case #3 conditional fork",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/conditional-flows.mjs",
    "rules/conditional-flows > should lint valid > test case #4 no condition after merge",
)
@pytest.mark.parametrize(
    "case",
    [c for c in VALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_valid(case: dict) -> None:
    assert_valid("conditional-flows", conditional_flows.factory, case)


@pytest.mark.upstream(
    "bpmnlint/test/rules/conditional-flows.mjs",
    "rules/conditional-flows > should lint invalid > test case #1 fork after exclusive gateway",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/conditional-flows.mjs",
    "rules/conditional-flows > should lint invalid > "
    "test case #2 fork after exclusive gateway default",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/conditional-flows.mjs",
    "rules/conditional-flows > should lint invalid > test case #3 fork after task",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/conditional-flows.mjs",
    "rules/conditional-flows > should lint invalid > test case #4 fork after task default",
)
@pytest.mark.parametrize(
    "case",
    [c for c in INVALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_invalid(case: dict) -> None:
    assert_invalid("conditional-flows", conditional_flows.factory, case)
