"""Declarative rule evaluation through the full profile evaluator."""

from __future__ import annotations

import pytest

from bpmn_io.profile._lint.evaluate import EvaluationError, evaluate_rule
from tests.profile_lint.helpers import CLEAN_DOC, NAMED_TASK_DOC, Json, contract, parse


def _rule(rule_id: str, phase: str) -> dict[str, Json]:
    profile = contract("neutral-profile.json")
    assert isinstance(profile, dict)
    rules = profile["rules"]
    assert isinstance(rules, list)
    for rule in rules:
        assert isinstance(rule, dict)
        if rule.get("id") == rule_id and rule.get("phase") == phase:
            return rule
    msg = f"unknown fixture rule: {rule_id}/{phase}"
    raise AssertionError(msg)


def _text_prefix_rule() -> dict[str, Json]:
    """A valid textPrefix rule over task names (reviewer probe for #4)."""
    return {
        "id": "task-prefixed",
        "phase": "post-normalize",
        "select": {
            "from": "root",
            "via": "all",
            "where": {
                "op": "typeIs",
                "binding": "self",
                "type": "bpmn:Task",
                "mode": "exact",
            },
            "order": "id",
        },
        "assert": {
            "op": "textPrefix",
            "value": {"op": "read", "binding": "self", "path": "/name"},
            "prefix": "R",
            "trim": "none",
        },
        "code": "task-prefix-missing",
        "message": "invalid",
        "classification": "readiness",
    }


def test_task_named_fires_only_for_unnamed() -> None:
    """The neutral task-named rule flags empty and missing names, not set ones."""
    rule = _rule("task-named", "post-normalize")
    findings = evaluate_rule(rule, parse(NAMED_TASK_DOC), phase="post-normalize")
    assert [(finding.target_id, finding.code) for finding in findings] == [
        ("Task_A", "task-name-missing")
    ]
    assert findings[0].profile_rule_id == "profile:task-named"
    assert findings[0].message_key == "invalid"
    assert findings[0].source_pointer == "/rootElements/0/flowElements/0"


def test_text_prefix_rule_evaluates() -> None:
    """A valid textPrefix rule evaluates instead of refusing lint-rule-error."""
    findings = evaluate_rule(_text_prefix_rule(), parse(NAMED_TASK_DOC), phase="post-normalize")
    assert [(finding.target_id, finding.code) for finding in findings] == [
        ("Task_A", "task-prefix-missing")
    ]
    assert findings[0].source_pointer == "/rootElements/0/flowElements/0"


def test_unknown_operator_refuses() -> None:
    """An unknown predicate operator stays unavailable, never false."""
    rule = _rule("task-named", "post-normalize")
    broken = {**rule, "assert": {"op": "frobnicate"}}
    with pytest.raises(EvaluationError):
        evaluate_rule(broken, parse(NAMED_TASK_DOC), phase="post-normalize")


def test_rule_shape_violations_refuse() -> None:
    """Rules missing their id, assert or selector refuse evaluation."""
    rule = _rule("task-named", "post-normalize")
    root = parse(NAMED_TASK_DOC)
    for broken in (
        {key: value for key, value in rule.items() if key != "id"},
        {key: value for key, value in rule.items() if key != "assert"},
        {
            **rule,
            "select": {
                "from": "root",
                "via": "all",
                "where": {"op": "frobnicate"},
                "order": "id",
            },
        },
    ):
        with pytest.raises(EvaluationError):
            evaluate_rule(broken, root, phase="post-normalize")


def test_supported_binding_traversal_evaluates() -> None:
    """Declared bindings evaluate on the stage snapshot with cardinality."""
    base = _rule("task-named", "post-normalize")
    rule = {
        **base,
        "id": "process-task-bound",
        "select": {
            "from": "root",
            "via": "all",
            "where": {
                "op": "typeIs",
                "binding": "self",
                "type": "bpmn:Process",
                "mode": "exact",
            },
            "order": "id",
        },
        "bindings": [
            {
                "op": "bind",
                "as": "task",
                "select": {
                    "from": "self",
                    "via": "children",
                    "where": {
                        "op": "typeIs",
                        "binding": "self",
                        "type": "bpmn:Task",
                        "mode": "exact",
                    },
                    "order": "id",
                },
                "cardinality": "one",
            }
        ],
        "assert": {
            "op": "present",
            "value": {"op": "read", "binding": "task", "path": "/name"},
        },
    }
    findings = evaluate_rule(rule, parse(CLEAN_DOC), phase="post-normalize")
    assert findings == []


def test_binding_cardinality_violation_refuses() -> None:
    """A binding matching twice for cardinality one is unavailable, not false."""
    base = _rule("task-named", "post-normalize")
    rule = {
        **base,
        "id": "process-task-bound",
        "select": {
            "from": "root",
            "via": "all",
            "where": {
                "op": "typeIs",
                "binding": "self",
                "type": "bpmn:Process",
                "mode": "exact",
            },
            "order": "id",
        },
        "bindings": [
            {
                "op": "bind",
                "as": "task",
                "select": {
                    "from": "self",
                    "via": "children",
                    "where": {
                        "op": "typeIs",
                        "binding": "self",
                        "type": "bpmn:Task",
                        "mode": "exact",
                    },
                    "order": "id",
                },
                "cardinality": "one",
            }
        ],
        "assert": {"op": "true"},
    }
    with pytest.raises(EvaluationError):
        evaluate_rule(rule, parse(NAMED_TASK_DOC), phase="post-normalize")


def test_assignable_uses_descriptor_inheritance() -> None:
    """A Task is not assignable to Process (reviewer probe for core #3)."""
    rule = _rule("task-named", "post-normalize")
    probing = {
        **rule,
        "assert": {
            "op": "typeIs",
            "binding": "self",
            "type": "bpmn:Process",
            "mode": "assignable",
        },
    }
    findings = evaluate_rule(probing, parse(NAMED_TASK_DOC), phase="post-normalize")
    assert {finding.target_id for finding in findings} == {"Task_A", "Task_B"}


def test_reference_traversal_resolves_targets() -> None:
    """A reference selector yields the referenced targets, not the source.

    ``CLEAN_DOC`` Flow_1 targets Task_1 (passes the Task filter) while
    Flow_2 targets End_1 (fails it), so exactly Flow_2 is reported.
    """
    base = _rule("task-named", "post-normalize")
    rule = {
        **base,
        "id": "flow-target-named",
        "select": {
            "from": "root",
            "via": "all",
            "where": {
                "op": "typeIs",
                "binding": "self",
                "type": "bpmn:SequenceFlow",
                "mode": "exact",
            },
            "order": "id",
        },
        "assert": {
            "op": "count",
            "select": {
                "from": "self",
                "via": "reference",
                "property": "targetRef",
                "where": {
                    "op": "typeIs",
                    "binding": "self",
                    "type": "bpmn:Task",
                    "mode": "exact",
                },
                "order": "id",
            },
            "min": 1,
        },
    }
    findings = evaluate_rule(rule, parse(CLEAN_DOC), phase="post-normalize")
    assert [(finding.target_id, finding.code) for finding in findings] == [
        ("Flow_2", "task-name-missing")
    ]
    assert findings[0].source_pointer == "/rootElements/0/flowElements/4"
