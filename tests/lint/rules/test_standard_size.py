"""Ported RuleTester cases for the ``standard-size`` rule.

Upstream suite: ``test/rules/standard-size.mjs``.
"""

from __future__ import annotations

import pytest

from bpmn_io.lint.rules import standard_size
from tests.lint.rules._case import assert_invalid, assert_valid

VALID = [
    {
        "config": None,
        "fixture": "standard-size/valid-elements.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "standard-size/valid-expanded-subprocess.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "standard-size/valid-collaboration.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "standard-size/valid-empty-pool-horizontal.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "standard-size/valid-empty-pool-vertical.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "standard-size/valid-missing-di.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": {"bpmn:Task": {"height": 80, "width": 120}},
        "fixture": "standard-size/valid-config.bpmn",
        "name": "configured size",
        "report": None,
        "skipped": False,
    },
    {
        "config": {"bpmn:Task": None},
        "fixture": "standard-size/valid-elements.bpmn",
        "name": "ignore malformed config",
        "report": None,
        "skipped": False,
    },
    {
        "config": {"bpmn:Participant": None},
        "fixture": "standard-size/valid-empty-pool-horizontal.bpmn",
        "name": "ignore malformed empty pool config",
        "report": None,
        "skipped": False,
    },
]

INVALID = [
    {
        "config": None,
        "fixture": "standard-size/invalid-elements.bpmn",
        "name": None,
        "report": [
            {"id": "Task_1", "message": "Element has a non-standard size; expected 100x80"},
            {"id": "StartEvent_1", "message": "Element has a non-standard size; expected 36x36"},
            {"id": "Gateway_1", "message": "Element has a non-standard size; expected 50x50"},
        ],
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "standard-size/invalid-collapsed-subprocess.bpmn",
        "name": None,
        "report": {
            "id": "SubProcess_1",
            "message": "Element has a non-standard size; expected 100x80",
        },
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "standard-size/invalid-empty-pool-horizontal.bpmn",
        "name": None,
        "report": {
            "id": "Participant_1",
            "message": "Element has a non-standard height; expected height of 60",
        },
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "standard-size/invalid-empty-pool-vertical.bpmn",
        "name": None,
        "report": {
            "id": "Participant_1",
            "message": "Element has a non-standard width; expected width of 60",
        },
        "skipped": False,
    },
    {
        "config": {"bpmn:Task": {"height": 80, "width": 120}},
        "fixture": "standard-size/valid-elements.bpmn",
        "name": "configured size",
        "report": {"id": "Task_1", "message": "Element has a non-standard size; expected 120x80"},
        "skipped": False,
    },
    {
        "config": {"bpmn:Participant": {"height": 60, "width": 80}},
        "fixture": "standard-size/valid-empty-pool-vertical.bpmn",
        "name": "configured empty pool size",
        "report": {
            "id": "Participant_00h09d6",
            "message": "Element has a non-standard width; expected width of 80",
        },
        "skipped": False,
    },
]


@pytest.mark.upstream(
    "bpmnlint/test/rules/standard-size.mjs",
    "rules/standard-size > should lint valid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/standard-size.mjs",
    "rules/standard-size > should lint valid > test case #2",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/standard-size.mjs",
    "rules/standard-size > should lint valid > test case #3",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/standard-size.mjs",
    "rules/standard-size > should lint valid > test case #4",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/standard-size.mjs",
    "rules/standard-size > should lint valid > test case #5",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/standard-size.mjs",
    "rules/standard-size > should lint valid > test case #6",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/standard-size.mjs",
    "rules/standard-size > should lint valid > test case #7 configured size",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/standard-size.mjs",
    "rules/standard-size > should lint valid > test case #8 ignore malformed config",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/standard-size.mjs",
    "rules/standard-size > should lint valid > test case #9 ignore malformed empty pool config",
)
@pytest.mark.parametrize(
    "case",
    [c for c in VALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_valid(case: dict) -> None:
    assert_valid("standard-size", standard_size.factory, case)


@pytest.mark.upstream(
    "bpmnlint/test/rules/standard-size.mjs",
    "rules/standard-size > should lint invalid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/standard-size.mjs",
    "rules/standard-size > should lint invalid > test case #2",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/standard-size.mjs",
    "rules/standard-size > should lint invalid > test case #3",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/standard-size.mjs",
    "rules/standard-size > should lint invalid > test case #4",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/standard-size.mjs",
    "rules/standard-size > should lint invalid > test case #5 configured size",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/standard-size.mjs",
    "rules/standard-size > should lint invalid > test case #6 configured empty pool size",
)
@pytest.mark.parametrize(
    "case",
    [c for c in INVALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_invalid(case: dict) -> None:
    assert_invalid("standard-size", standard_size.factory, case)
