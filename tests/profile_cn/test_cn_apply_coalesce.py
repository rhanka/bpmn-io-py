"""Single-cardinality assignRef coalescing (lot 3, DESIGN §2.4)."""

from __future__ import annotations

import pytest

from bpmn_io.profile._cn_apply import _coalesce_writes
from bpmn_io.profile._cn_plan import _RefusalError


def _append_unique(target_id: str, ids: list[str]) -> dict[str, object]:
    return {
        "op": "assignRef",
        "recipeId": "r",
        "target": {"id": target_id},
        "property": "flowNodeRef",
        "mode": "appendUnique",
        "ids": list(ids),
        "cardinality": "single",
    }


def test_identical_single_append_unique_coalesces_to_one() -> None:
    """Two identical single appendUnique writes survive as one appendUnique."""
    first = _append_unique("Lane_1", ["Task_1"])
    second = _append_unique("Lane_1", ["Task_1"])
    merged, _alias = _coalesce_writes([first, second])
    assert len(merged) == 1
    assert merged[0][1]["mode"] == "appendUnique"
    assert merged[0][1]["ids"] == ["Task_1"]


def test_different_single_append_unique_unions() -> None:
    """Two appendUnique writes for one single slot union into one write."""
    first = _append_unique("Lane_1", ["Task_2"])
    second = _append_unique("Lane_1", ["Task_1"])
    merged, _alias = _coalesce_writes([first, second])
    assert len(merged) == 1
    assert merged[0][1]["mode"] == "appendUnique"
    assert merged[0][1]["ids"] == ["Task_1", "Task_2"]


def test_mixed_single_modes_conflict() -> None:
    """Mixed appendUnique/remove for one single (target, property) conflict."""
    first = _append_unique("Lane_1", ["Task_1"])
    second = dict(_append_unique("Lane_1", ["Task_1"]))
    second["mode"] = "remove"
    with pytest.raises(_RefusalError) as caught:
        _coalesce_writes([first, second])
    assert caught.value.code == "profile-write-conflict"
