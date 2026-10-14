"""Ported RuleTester cases for the ``no-overlapping-elements`` rule.

Upstream suite: ``test/rules/no-overlapping-elements.mjs``.
"""

from __future__ import annotations

import pytest

from bpmn_io.lint.rules import no_overlapping_elements
from tests.lint.rules._case import assert_invalid, assert_valid

VALID = [
    {
        "config": None,
        "fixture": "no-overlapping-elements/valid-boundary-event.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-overlapping-elements/valid-collaboration.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-overlapping-elements/valid-process.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-overlapping-elements/valid-subprocess.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-overlapping-elements/valid-subprocess-collapsed.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-overlapping-elements/valid-data-objects.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-overlapping-elements/ignore-missing-di.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-overlapping-elements/ignore-missing-bounds.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
]

INVALID = [
    {
        "config": None,
        "fixture": "no-overlapping-elements/invalid-boundary-event.bpmn",
        "name": None,
        "report": [
            {"id": "TASK", "message": "Element overlaps with other element"},
            {"id": "LOOKS_LIKE_BOUNDARY", "message": "Element overlaps with other element"},
        ],
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-overlapping-elements/invalid-collaboration.bpmn",
        "name": None,
        "report": [
            {"id": "Participant_1af2hnr", "message": "Element overlaps with other element"},
            {"id": "Participant_06xnivi", "message": "Element overlaps with other element"},
        ],
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-overlapping-elements/invalid-process.bpmn",
        "name": None,
        "report": [
            {"id": "TASK_1", "message": "Element overlaps with other element"},
            {"id": "TASK_2", "message": "Element overlaps with other element"},
        ],
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-overlapping-elements/invalid-subprocess.bpmn",
        "name": None,
        "report": [{"id": "TASK", "message": "Element is outside of parent boundary"}],
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-overlapping-elements/invalid-subprocess-collapsed.bpmn",
        "name": None,
        "report": [
            {"id": "TASK", "message": "Element overlaps with other element"},
            {"id": "END_EVENT", "message": "Element overlaps with other element"},
        ],
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-overlapping-elements/invalid-wide-element.bpmn",
        "name": None,
        "report": [
            {"id": "TASK_FAR", "message": "Element overlaps with other element"},
            {"id": "WIDE_TASK", "message": "Element overlaps with other element"},
        ],
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-overlapping-elements/invalid-touching-elements.bpmn",
        "name": None,
        "report": [
            {"id": "TASK_LEFT", "message": "Element overlaps with other element"},
            {"id": "TASK_RIGHT", "message": "Element overlaps with other element"},
            {"id": "TASK_TOP", "message": "Element overlaps with other element"},
            {"id": "TASK_BOTTOM", "message": "Element overlaps with other element"},
        ],
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-overlapping-elements/invalid-report-order.bpmn",
        "name": "report in element order",
        "report": [
            {"id": "TASK_A", "message": "Element overlaps with other element"},
            {"id": "TASK_B", "message": "Element overlaps with other element"},
            {"id": "TASK_C", "message": "Element overlaps with other element"},
            {"id": "TASK_D", "message": "Element overlaps with other element"},
        ],
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-overlapping-elements/invalid-nan-bounds.bpmn",
        "name": None,
        "report": [
            {"id": "TASK_LEFT", "message": "Element overlaps with other element"},
            {"id": "TASK_RIGHT", "message": "Element overlaps with other element"},
        ],
        "skipped": False,
    },
]


@pytest.mark.upstream(
    "bpmnlint/test/rules/no-overlapping-elements.mjs",
    "rules/no-overlapping-elements > should lint valid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-overlapping-elements.mjs",
    "rules/no-overlapping-elements > should lint valid > test case #2",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-overlapping-elements.mjs",
    "rules/no-overlapping-elements > should lint valid > test case #3",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-overlapping-elements.mjs",
    "rules/no-overlapping-elements > should lint valid > test case #4",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-overlapping-elements.mjs",
    "rules/no-overlapping-elements > should lint valid > test case #5",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-overlapping-elements.mjs",
    "rules/no-overlapping-elements > should lint valid > test case #6",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-overlapping-elements.mjs",
    "rules/no-overlapping-elements > should lint valid > test case #7",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-overlapping-elements.mjs",
    "rules/no-overlapping-elements > should lint valid > test case #8",
)
@pytest.mark.parametrize(
    "case",
    [c for c in VALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_valid(case: dict) -> None:
    assert_valid("no-overlapping-elements", no_overlapping_elements.factory, case)


@pytest.mark.upstream(
    "bpmnlint/test/rules/no-overlapping-elements.mjs",
    "rules/no-overlapping-elements > should lint invalid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-overlapping-elements.mjs",
    "rules/no-overlapping-elements > should lint invalid > test case #2",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-overlapping-elements.mjs",
    "rules/no-overlapping-elements > should lint invalid > test case #3",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-overlapping-elements.mjs",
    "rules/no-overlapping-elements > should lint invalid > test case #4",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-overlapping-elements.mjs",
    "rules/no-overlapping-elements > should lint invalid > test case #5",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-overlapping-elements.mjs",
    "rules/no-overlapping-elements > should lint invalid > test case #6",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-overlapping-elements.mjs",
    "rules/no-overlapping-elements > should lint invalid > test case #7",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-overlapping-elements.mjs",
    "rules/no-overlapping-elements > should lint invalid > test case #8 report in element order",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-overlapping-elements.mjs",
    "rules/no-overlapping-elements > should lint invalid > test case #9",
)
@pytest.mark.parametrize(
    "case",
    [c for c in INVALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_invalid(case: dict) -> None:
    assert_invalid("no-overlapping-elements", no_overlapping_elements.factory, case)
