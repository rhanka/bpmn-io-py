"""Ported RuleTester cases for the ``superfluous-label`` rule.

Upstream suite: ``test/rules/superfluous-label.mjs``.
"""

from __future__ import annotations

import pytest

from bpmn_io.lint.rules import superfluous_label
from tests.lint.rules._case import assert_invalid, assert_valid

VALID = [
    {
        "config": None,
        "fixture": "superfluous-label/valid.bpmn",
        "name": "unlabeled flow, labeled XOR/OR fork, conditional and default flows",
        "report": None,
        "skipped": False,
    }
]

INVALID = [
    {
        "config": None,
        "fixture": "superfluous-label/invalid.bpmn",
        "name": "labeled unconditional flows",
        "report": [
            {
                "id": "Flow_Labeled_StartEvent",
                "message": "Sequence flow has superfluous label",
                "path": ["name"],
            },
            {
                "id": "Flow_Labeled_Task",
                "message": "Sequence flow has superfluous label",
                "path": ["name"],
            },
            {
                "id": "Flow_Labeled_Gateway",
                "message": "Sequence flow has superfluous label",
                "path": ["name"],
            },
            {
                "id": "Flow_Labeled_Passthrough",
                "message": "Sequence flow has superfluous label",
                "path": ["name"],
            },
        ],
        "skipped": False,
    }
]


@pytest.mark.upstream(
    "bpmnlint/test/rules/superfluous-label.mjs",
    "rules/superfluous-label > should lint valid > "
    "test case #1 unlabeled flow, labeled XOR/OR fork, conditional and default flows",
)
@pytest.mark.parametrize(
    "case",
    [c for c in VALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_valid(case: dict) -> None:
    assert_valid("superfluous-label", superfluous_label.factory, case)


@pytest.mark.upstream(
    "bpmnlint/test/rules/superfluous-label.mjs",
    "rules/superfluous-label > should lint invalid > test case #1 labeled unconditional flows",
)
@pytest.mark.parametrize(
    "case",
    [c for c in INVALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_invalid(case: dict) -> None:
    assert_invalid("superfluous-label", superfluous_label.factory, case)
