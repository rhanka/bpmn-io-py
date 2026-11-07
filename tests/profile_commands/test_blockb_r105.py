"""Block-B R1-05: missing outer binding propagates past recognition."""

from __future__ import annotations


def test_r105_recognizes_missing_binding_refuses() -> None:
    """A recognizes predicate with no outer binding refuses profile-symbol."""
    from bpmn_io.profile import evaluate_predicate
    from bpmn_io.profile._evaluate import make_read_context

    tree = {"$type": "bpmn:Definitions", "id": "D_1"}
    context = make_read_context(
        tree,
        notions={"task": {"recognition": {"op": "true"}}},
    )
    outcome = evaluate_predicate(
        {"op": "recognizes", "binding": "bindingOwner", "notion": "task"},
        context,
        {"root": tree},
    )
    assert outcome.status == "refused"
    assert outcome.code == "profile-symbol"  # type: ignore[union-attr]


def test_r105_inner_refusal_stays_non_match() -> None:
    """A refused inner recognition still evaluates to False."""
    from bpmn_io.profile import evaluate_predicate
    from bpmn_io.profile._evaluate import make_read_context

    tree = {"$type": "bpmn:Definitions", "id": "D_1"}
    element = {"$type": "bpmn:Task", "id": "T_1"}
    context = make_read_context(
        tree,
        notions={"task": {"recognition": {"op": "typeIs", "binding": "self", "type": "x:Nope"}}},
    )
    outcome = evaluate_predicate(
        {"op": "recognizes", "binding": "task", "notion": "task"},
        context,
        {"root": tree, "task": element},
    )
    assert outcome.status == "ok"
    assert outcome.payload is False  # type: ignore[union-attr]
