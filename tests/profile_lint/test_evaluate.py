"""Declarative rule evaluation (lot-1 recognition subset)."""

from __future__ import annotations

import pytest

from bpmn_io.profile._lint.evaluate import EvaluationError, _predicate, evaluate_rule
from bpmn_io.profile._lint.index import walk_tree
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


def _lit(value: object) -> dict[str, object]:
    return {"op": "literal", "value": value}


def test_task_named_fires_only_for_unnamed() -> None:
    """The neutral task-named rule flags empty and missing names, not set ones."""
    rule = _rule("task-named", "post-normalize")
    findings = evaluate_rule(rule, parse(NAMED_TASK_DOC))
    assert [(finding.target_id, finding.code) for finding in findings] == [
        ("Task_A", "task-name-missing")
    ]
    assert findings[0].profile_rule_id == "profile:task-named"
    assert findings[0].message_key == "invalid"
    assert findings[0].source_pointer == "/rootElements/0/flowElements/0"


def test_type_is_modes() -> None:
    """Exact matches the type name; assignable follows the descriptor closure."""
    root = parse(NAMED_TASK_DOC)
    task = next(node for node, _ in walk_tree(root) if node.get("id") == "Task_A")
    bindings: dict[str, object] = {"root": root, "self": task}
    assert (
        _predicate(
            {"op": "typeIs", "binding": "self", "type": "bpmn:Task", "mode": "exact"},
            bindings,
        )
        is True
    )
    assert (
        _predicate(
            {"op": "typeIs", "binding": "self", "type": "Task", "mode": "exact"},
            bindings,
        )
        is True
    )
    assert (
        _predicate(
            {"op": "typeIs", "binding": "self", "type": "bpmn:FlowNode", "mode": "exact"},
            bindings,
        )
        is False
    )
    assert (
        _predicate(
            {"op": "typeIs", "binding": "self", "type": "bpmn:FlowNode", "mode": "assignable"},
            bindings,
        )
        is True
    )


def test_present_equal_booleans() -> None:
    """Empty string is present; equal needs same type and value, no coercion."""
    bindings: dict[str, object] = {"root": None, "self": None}
    assert _predicate({"op": "present", "value": _lit("")}, bindings) is True
    assert _predicate({"op": "present", "value": _lit(0)}, bindings) is True
    assert _predicate({"op": "equal", "left": _lit(1), "right": _lit(1)}, bindings) is True
    assert (
        _predicate({"op": "equal", "left": _lit(1), "right": _lit(value=True)}, bindings) is False
    )
    assert _predicate({"op": "equal", "left": _lit(1), "right": _lit("1")}, bindings) is False
    assert _predicate({"op": "all", "args": [{"op": "true"}, {"op": "false"}]}, bindings) is False
    assert _predicate({"op": "any", "args": [{"op": "true"}, {"op": "false"}]}, bindings) is True
    assert _predicate({"op": "not", "arg": {"op": "true"}}, bindings) is False


def test_unsupported_operators_refuse() -> None:
    """Operators outside the lot-1 subset are unavailable, never false."""
    for predicate in (
        {"op": "reachable"},
        {"op": "textPrefix", "value": _lit("a"), "prefix": "a"},
        {"op": "recognizes", "binding": "self", "notion": "x"},
    ):
        with pytest.raises(EvaluationError, match="unsupported"):
            _predicate(predicate, {"root": None, "self": None})
    with pytest.raises(EvaluationError, match="root binding"):
        _predicate(
            {
                "op": "count",
                "selector": {
                    "from": "root",
                    "via": "all",
                    "where": {"op": "true"},
                    "order": "id",
                },
                "min": 0,
            },
            {"root": None, "self": None},
        )


def test_selector_shape_refuses() -> None:
    """Non-root traversals and non-id orders refuse evaluation."""
    root = parse(NAMED_TASK_DOC)
    base = _rule("task-named", "post-normalize")
    select = base["select"]
    assert isinstance(select, dict)
    for variant in (
        {**select, "via": "descendants"},
        {**select, "order": "page-occurrence"},
        {**select, "from": "self"},
    ):
        with pytest.raises(EvaluationError, match="unsupported"):
            evaluate_rule({**base, "select": variant}, root)


def test_read_edge_cases() -> None:
    """Array indexing refuses; missing properties read MISSING (present=false)."""
    root = parse(CLEAN_DOC)
    task = next(node for node, _ in walk_tree(root) if node.get("id") == "Task_1")
    bindings: dict[str, object] = {"root": root, "self": task}
    assert (
        _predicate(
            {"op": "present", "value": {"op": "read", "binding": "self", "path": "/name"}},
            bindings,
        )
        is True
    )
    assert (
        _predicate(
            {"op": "present", "value": {"op": "read", "binding": "self", "path": "/nope"}},
            bindings,
        )
        is False
    )
    with pytest.raises(EvaluationError, match="array indexing"):
        _predicate(
            {
                "op": "present",
                "value": {"op": "read", "binding": "self", "path": "/incoming/0"},
            },
            bindings,
        )
