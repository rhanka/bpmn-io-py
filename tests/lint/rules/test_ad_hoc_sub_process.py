"""Ported RuleTester cases for the ``ad-hoc-sub-process`` rule.

Upstream suite: ``test/rules/ad-hoc-sub-process.mjs``.
"""

from __future__ import annotations

import pytest

from bpmn_io.lint.rules import ad_hoc_sub_process
from tests.lint.rules._case import assert_invalid, assert_valid

VALID = [
    {
        "config": None,
        "fixture": "ad-hoc-sub-process/valid.bpmn",
        "name": None,
        "report": None,
        "skipped": False,
    }
]

INVALID = [
    {
        "config": None,
        "fixture": "ad-hoc-sub-process/invalid-start-end.bpmn",
        "name": None,
        "report": [
            {
                "id": "StartEvent",
                "message": "A <Start Event> is not allowed in <Ad Hoc Sub Process>",
            },
            {"id": "EndEvent", "message": "An <End Event> is not allowed in <Ad Hoc Sub Process>"},
        ],
        "skipped": False,
    }
]


@pytest.mark.upstream(
    "bpmnlint/test/rules/ad-hoc-sub-process.mjs",
    "rules/ad-hoc-sub-process > should lint valid > test case #1",
)
@pytest.mark.parametrize(
    "case",
    [c for c in VALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_valid(case: dict) -> None:
    assert_valid("ad-hoc-sub-process", ad_hoc_sub_process.factory, case)


@pytest.mark.upstream(
    "bpmnlint/test/rules/ad-hoc-sub-process.mjs",
    "rules/ad-hoc-sub-process > should lint invalid > test case #1",
)
@pytest.mark.parametrize(
    "case",
    [c for c in INVALID if not c["skipped"]],
    ids=lambda c: c["fixture"],
)
def test_invalid(case: dict) -> None:
    assert_invalid("ad-hoc-sub-process", ad_hoc_sub_process.factory, case)
