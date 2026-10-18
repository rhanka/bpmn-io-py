"""Evaluator behaviour over the native tree (read-only, bounded)."""

from __future__ import annotations

_SIMPLE_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
    'id="Defs_1" targetNamespace="http://example.com">'
    '<bpmn:process id="Process_1" name="P">'
    '<bpmn:task id="Task_1" name="T" />'
    "</bpmn:process>"
    "</bpmn:definitions>"
)


def _native_root() -> object:
    from bpmn_io import create_moddle

    moddle = create_moddle()
    result = moddle.from_xml(_SIMPLE_XML)
    assert result.root_element is not None
    return result.root_element


def test_predicate_true_false_and_logic() -> None:
    """Basic Boolean operators evaluate without touching storage."""
    from bpmn_io.profile import evaluate_predicate
    from bpmn_io.profile._evaluate import make_read_context

    context = make_read_context(_native_root())
    bindings: dict[str, object] = {}
    first = evaluate_predicate({"op": "true"}, context, bindings)
    assert first.status == "ok"
    assert first.payload is True  # type: ignore[union-attr]
    second = evaluate_predicate({"op": "false"}, context, bindings)
    assert second.payload is False  # type: ignore[union-attr]


def test_case_operator_matches_pinned_witnesses() -> None:
    """Upper and lower mappings follow the pinned full default data."""
    from bpmn_io.profile import apply_case

    assert apply_case("ß", "upper") == "SS"
    assert apply_case("SS", "lower") == "ss"
    assert apply_case("Task", "upper") == "TASK"
    assert apply_case("TASK", "lower") == "task"


def test_malicious_ast_refuses_with_closed_code() -> None:
    """Unknown operators refuse instead of evaluating partially."""
    from bpmn_io.profile import evaluate_predicate
    from bpmn_io.profile._evaluate import make_read_context

    context = make_read_context(_native_root())
    result = evaluate_predicate({"op": "frobnicate"}, context, {})
    assert result.status == "refused"
    assert result.code == "profile-symbol"  # type: ignore[union-attr]


def test_selector_self_orders_by_id() -> None:
    """Self selection returns the bound element with a stable pointer."""
    from bpmn_io.profile import select
    from bpmn_io.profile._evaluate import make_read_context

    root = _native_root()
    context = make_read_context(root)
    result = select({"from": "root", "via": "self", "order": "id"}, context, {})
    assert result.status == "ok"
    assert result.payload is not None  # type: ignore[union-attr]
