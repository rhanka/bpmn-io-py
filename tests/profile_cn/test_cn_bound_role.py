"""``boundRole`` with the notion-scope ``bindingOwner`` (lot 3, trig seal)."""

from __future__ import annotations

from bpmn_io.profile import evaluate_predicate
from bpmn_io.profile._evaluate import ReadContext


def _context() -> ReadContext:
    lane = {"$type": "bpmn:Lane", "id": "Lane_1"}
    other = {"$type": "bpmn:Lane", "id": "Lane_2"}
    stranger = {"$type": "bpmn:Lane", "id": "Lane_9"}
    return ReadContext(
        root={"$type": "bpmn:Definitions", "id": "Defs"},
        elements=(lane, other, stranger),
        by_id={"Lane_1": lane, "Lane_2": other, "Lane_9": stranger},
        bindings=(
            {"ownerId": "Process_A", "role": "external-lane", "targetId": "Lane_1"},
            {"ownerId": "Process_A", "role": "other-role", "targetId": "Lane_2"},
        ),
    )


def _predicate() -> dict[str, object]:
    return {"op": "boundRole", "binding": "self", "owner": "bindingOwner", "role": "external-lane"}


def test_binding_owner_matches_bound_role() -> None:
    """A lane bound under the tested role is recognized whatever the owner."""
    context = _context()
    lane = context.by_id["Lane_1"]
    outcome = evaluate_predicate(_predicate(), context, {"self": lane})
    assert outcome.status == "ok"
    assert outcome.payload is True  # type: ignore[union-attr]


def test_binding_owner_enforces_role() -> None:
    """A lane bound under another role only is not recognized."""
    context = _context()
    other = context.by_id["Lane_2"]
    outcome = evaluate_predicate(_predicate(), context, {"self": other})
    assert outcome.status == "ok"
    assert outcome.payload is False  # type: ignore[union-attr]


def test_binding_owner_rejects_unbound() -> None:
    """A lane with no binding record is not recognized."""
    context = _context()
    stranger = context.by_id["Lane_9"]
    outcome = evaluate_predicate(_predicate(), context, {"self": stranger})
    assert outcome.status == "ok"
    assert outcome.payload is False  # type: ignore[union-attr]
