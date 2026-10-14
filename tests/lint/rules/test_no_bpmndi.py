"""Ported RuleTester cases for the ``no-bpmndi`` rule.

Upstream suite: ``test/rules/no-bpmndi.mjs``.
"""

from __future__ import annotations

import pytest

from bpmn_io.lint import Linter
from bpmn_io.lint.resolver import NodeResolver
from bpmn_io.lint.rules import no_bpmndi
from bpmn_io.lint.testers.helper import read_moddle
from tests.conftest import upstream_dir
from tests.lint.rules._case import assert_invalid, assert_valid

VALID = [
    {
        "config": None,
        "fixture": "no-bpmndi/valid.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-bpmndi/valid-sub-processes.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-bpmndi/valid-data-object.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-bpmndi/valid-error.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-bpmndi/valid-extension-elements.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-bpmndi/valid-signavio.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-bpmndi/valid-complex.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-bpmndi/valid-group.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-bpmndi/valid-nested-boundary.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-bpmndi/valid-lanes.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-bpmndi/valid-multiple-nested-levels.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-bpmndi/valid-empty.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-bpmndi/valid-no-lanes.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-bpmndi/valid-message-flow.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-bpmndi/ignore-edge-without-bpmn-element.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    },
]

INVALID = [
    {
        "config": None,
        "fixture": "no-bpmndi/invalid-catch-event.bpmn",
        "name": None,
        "report": {"id": "boundaryEvent", "message": "Element is missing bpmndi"},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-bpmndi/invalid-sub-processes.bpmn",
        "name": None,
        "report": {"id": "boundaryEvent_1", "message": "Element is missing bpmndi"},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-bpmndi/invalid-multiple-sub-processes.bpmn",
        "name": None,
        "report": {"id": "boundaryEvent", "message": "Element is missing bpmndi"},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-bpmndi/invalid-sequence-flow.bpmn",
        "name": None,
        "report": {"id": "sequenceFlow", "message": "Element is missing bpmndi"},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-bpmndi/invalid-participant.bpmn",
        "name": None,
        "report": {"id": "Participant_1", "message": "Element is missing bpmndi"},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-bpmndi/invalid-group.bpmn",
        "name": None,
        "report": {"id": "Group_1", "message": "Element is missing bpmndi"},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-bpmndi/invalid-lane.bpmn",
        "name": None,
        "report": {"id": "lane2", "message": "Element is missing bpmndi"},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-bpmndi/invalid-collapsed-pool.bpmn",
        "name": None,
        "report": {"id": "participant1", "message": "Element is missing bpmndi"},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-bpmndi/invalid-nested-boundary.bpmn",
        "name": None,
        "report": {"id": "boundaryEvent", "message": "Element is missing bpmndi"},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-bpmndi/invalid-multiple-nested-levels.bpmn",
        "name": None,
        "report": {"id": "task1", "message": "Element is missing bpmndi"},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-bpmndi/invalid-nested-lanes.bpmn",
        "name": None,
        "report": {"id": "task1", "message": "Element is missing bpmndi"},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-bpmndi/invalid-missing-nested-lane.bpmn",
        "name": None,
        "report": {"id": "lane_1", "message": "Element is missing bpmndi"},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-bpmndi/invalid-missing-nested-lane-deep.bpmn",
        "name": None,
        "report": {"id": "lane7", "message": "Element is missing bpmndi"},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-bpmndi/invalid-message-flow.bpmn",
        "name": None,
        "report": {"id": "danglingMessageFlow", "message": "Element is missing bpmndi"},
        "skipped": False,
    },
    {
        "config": None,
        "fixture": "no-bpmndi/invalid-no-bpmn-diagram.bpmn",
        "name": None,
        "report": {"id": "StartEvent_1", "message": "Element is missing bpmndi"},
        "skipped": False,
    },
]


@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint valid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint valid > test case #2",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint valid > test case #3",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint valid > test case #4",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint valid > test case #5",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint valid > test case #6",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint valid > test case #7",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint valid > test case #8",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint valid > test case #9",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint valid > test case #10",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint valid > test case #11",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint valid > test case #12",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint valid > test case #13",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint valid > test case #14",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint valid > test case #15",
)
@pytest.mark.parametrize(
    "case",
    [c for c in VALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_valid(case: dict) -> None:
    assert_valid("no-bpmndi", no_bpmndi.factory, case)


@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint invalid > test case #1",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint invalid > test case #2",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint invalid > test case #3",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint invalid > test case #4",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint invalid > test case #5",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint invalid > test case #6",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint invalid > test case #7",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint invalid > test case #8",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint invalid > test case #9",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint invalid > test case #10",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint invalid > test case #11",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint invalid > test case #12",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint invalid > test case #13",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint invalid > test case #14",
)
@pytest.mark.upstream(
    "bpmnlint/test/rules/no-bpmndi.mjs",
    "rules/no-bpmndi > should lint invalid > test case #15",
)
@pytest.mark.parametrize(
    "case",
    [c for c in INVALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_invalid(case: dict) -> None:
    assert_invalid("no-bpmndi", no_bpmndi.factory, case)


def test_rule_error_on_empty_definitions() -> None:
    fixture = (
        upstream_dir("bpmn-auto-layout") / "test" / "fixtures" / "scenario.empty-definitions.bpmn"
    )
    root = read_moddle(fixture)["root"]
    results = Linter(resolver=NodeResolver()).lint(root, {"rules": {"no-bpmndi": "error"}})
    assert results == {
        "no-bpmndi": [
            {
                "message": "Cannot read properties of undefined (reading 'map')",
                "category": "rule-error",
            },
        ],
    }
