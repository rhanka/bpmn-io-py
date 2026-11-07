"""Block-B mirror G4: shared recognition non-match boundary (neutral data)."""

from __future__ import annotations


def _context() -> tuple[object, object]:
    from bpmn_io.profile._evaluate import make_read_context

    tree = {
        "$type": "bpmn:Definitions",
        "id": "D_1",
        "rootElements": [
            {
                "$type": "bpmn:Process",
                "id": "P_1",
                "flowElements": [{"$type": "bpmn:Task", "id": "T_1"}],
            }
        ],
    }
    target = tree["rootElements"][0]["flowElements"][0]  # type: ignore[index]
    # Recognition body refuses once evaluated: concat needs strings, the
    # read operand is absent, so evaluation refuses instead of matching.
    refusing_body = {
        "op": "present",
        "value": {
            "op": "concat",
            "values": [
                {"op": "literal", "value": "v:"},
                {"op": "read", "binding": "self", "path": "/name"},
            ],
        },
    }
    notions = {"probe": {"recognition": refusing_body}}
    context = make_read_context(tree, notions=notions)
    return context, target


def test_g4_refused_recognition_is_non_match() -> None:
    """A refused notion recognition is a non-match (shared boundary)."""
    from bpmn_io.profile import evaluate_predicate

    context, target = _context()
    outcome = evaluate_predicate(
        {"op": "recognizes", "binding": "self", "notion": "probe"},
        context,
        {"root": context.root, "self": target},
    )
    assert outcome.status == "ok"
    assert outcome.payload is False  # type: ignore[union-attr]


def test_g4_error_outside_recognition_propagates() -> None:
    """An error outside recognition keeps its original refusal code."""
    from bpmn_io.profile import evaluate_predicate

    context, target = _context()
    outcome = evaluate_predicate(
        {
            "op": "present",
            "value": {
                "op": "concat",
                "values": [
                    {"op": "literal", "value": "v:"},
                    {"op": "read", "binding": "self", "path": "/name"},
                ],
            },
        },
        context,
        {"root": context.root, "self": target},
    )
    assert outcome.status == "refused"
    assert outcome.code == "profile-type"  # type: ignore[union-attr]
