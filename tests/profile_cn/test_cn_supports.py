"""Recovery-proposal unit behaviour (lot 3, §6.7)."""

from __future__ import annotations

import pytest

from bpmn_io.profile._cn_context import ReadContext
from bpmn_io.profile._cn_plan import _Planner, _propose_ensure, _RefusalError, _Shared


def _planner(shared: _Shared) -> tuple[_Planner, dict[str, object], dict[str, object]]:
    lane: dict[str, object] = {"$type": "bpmn:Lane", "id": "g_lane"}
    parent: dict[str, object] = {"$type": "bpmn:LaneSet", "id": "g_set", "lanes": [lane]}
    root: dict[str, object] = {"$type": "bpmn:Definitions", "id": "Defs", "rootElements": [parent]}
    context = ReadContext(
        root=root,
        envelope={"bindings": []},
        by_id={"g_lane": lane},
        parents={id(lane): parent},
        revision="r",
    )
    planner = _Planner(
        context=context,
        recipe_id="r",
        phase="normalize",
        actor="code",
        activation="qualification",
        gates=False,
        shared=shared,
    )
    return planner, parent, lane


def _ensure(
    planner: _Planner,
    parent: dict[str, object],
    owner_id: str,
    role: str,
) -> bool:
    bindings: dict[str, object] = {}
    return _propose_ensure(
        planner,
        "g_lane",
        "bpmn:Lane",
        parent,  # type: ignore[arg-type]
        "lanes",
        owner_id,
        role,
        ("owner", role),
        (owner_id, role),
        bindings,
        "alias",
    )


def test_qualified_occupant_is_proposed() -> None:
    """An attested, unbound, well-placed occupant yields one proposal."""
    shared = _Shared(propose=True, provenance=frozenset({"g_lane"}))
    planner, parent, _lane = _planner(shared)
    assert _ensure(planner, parent, "Process_A", "external-lane") is True
    assert shared.proposals == [
        {"ownerId": "Process_A", "role": "external-lane", "targetId": "g_lane"}
    ]


def test_identical_proposal_coalesces() -> None:
    """The same proposal twice is recorded once."""
    shared = _Shared(propose=True, provenance=frozenset({"g_lane"}))
    planner, parent, _lane = _planner(shared)
    assert _ensure(planner, parent, "Process_A", "external-lane") is True
    assert _ensure(planner, parent, "Process_A", "external-lane") is True
    assert len(shared.proposals) == 1


def test_two_proposals_for_one_target_conflict() -> None:
    """Two roles proposed for one target refuse support-binding-conflict."""
    shared = _Shared(propose=True, provenance=frozenset({"g_lane"}))
    planner, parent, _lane = _planner(shared)
    assert _ensure(planner, parent, "Process_A", "external-lane") is True
    with pytest.raises(_RefusalError) as caught:
        _ensure(planner, parent, "Process_A", "other-role")
    assert caught.value.code == "support-binding-conflict"


def test_unattested_occupant_gives_no_proposal() -> None:
    """An occupied id outside provenance binds the alias with no proposal."""
    shared = _Shared(propose=True, provenance=frozenset())
    planner, parent, _lane = _planner(shared)
    assert _ensure(planner, parent, "Process_A", "external-lane") is True
    assert shared.proposals == []
