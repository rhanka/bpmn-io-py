"""Upstream report path resolution (DESIGN R3.3 §6.4)."""

from __future__ import annotations

import pytest

from bpmn_io.profile._lint.index import build_id_index, resolve_pointer, walk_tree
from tests.profile_lint.helpers import NAMED_TASK_DOC, parse


def _index() -> dict[str, str]:
    """Index the named-task fixture (Task_A first flow element)."""
    return build_id_index(parse(NAMED_TASK_DOC))


#: Task fixture with one ID-less documentation child under Task_A.
_IDLESS_DOC = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
    id="D1" targetNamespace="http://example.com/n">
  <bpmn:process id="P1" isExecutable="false">
    <bpmn:task id="Task_A">
      <bpmn:documentation>hello</bpmn:documentation>
    </bpmn:task>
    <bpmn:task id="Task_B" name="Ready" />
  </bpmn:process>
</bpmn:definitions>
"""


def _child_index() -> tuple[dict[str, str], set[str]]:
    """Index the ID-less fixture with its full walk-pointer set."""
    root = parse(_IDLESS_DOC)
    return build_id_index(root), {pointer for _, pointer in walk_tree(root)}


def test_property_segment_appends_to_indexed_base() -> None:
    """An upstream property path resolves against the reported ID's pointer."""
    index = _index()
    base = index["Task_A"]
    pointer, provenance = resolve_pointer(index, "Task_A", "name")
    assert pointer == f"{base}/name"
    assert provenance == "exact"


def test_unknown_id_absolute_pointer_refused() -> None:
    """A verbatim pointer for an unknown ID is refused, never exact."""
    index = _index()
    pointer, provenance = resolve_pointer(index, "ghost", "/invented~2")
    assert pointer is None
    assert provenance == "unavailable"


def test_absent_id_absolute_pointer_passes_through() -> None:
    """A generic absolute pointer without a reported ID stays exact."""
    index, known = _child_index()
    pointer, provenance = resolve_pointer(index, None, "/rootElements/0/flowElements/1", known)
    assert pointer == "/rootElements/0/flowElements/1"
    assert provenance == "exact"


def test_unknown_id_property_path_refused() -> None:
    """A property path for an unknown ID stays unavailable."""
    index = _index()
    pointer, provenance = resolve_pointer(index, "ghost", "name")
    assert pointer is None
    assert provenance == "unavailable"


def test_empty_segments_point_at_node() -> None:
    """An empty segment array points at the reported node itself."""
    index = _index()
    pointer, provenance = resolve_pointer(index, "Task_A", [])
    assert pointer == index["Task_A"]
    assert provenance == "exact"


def test_unsupported_forms_refused() -> None:
    """Non-string/non-list paths and bad segments stay unavailable."""
    index = _index()
    for bad in ({"path": "name"}, [-1], [True], ""):
        pointer, provenance = resolve_pointer(index, "Task_A", bad)
        assert pointer is None
        assert provenance == "unavailable"


def test_slash_in_property_name_escapes() -> None:
    """A property name carrying a slash appends as one escaped segment."""
    index = _index()
    pointer, provenance = resolve_pointer(index, "Task_A", "relative/pointer")
    assert pointer == f"{index['Task_A']}/relative~1pointer"
    assert provenance == "exact"


def test_generic_invented_escape_refused() -> None:
    """A generic pointer with a bad ``~`` escape stays unavailable (syntax)."""
    index, known = _child_index()
    pointer, provenance = resolve_pointer(index, "Task_A", "/invented~2", known)
    assert pointer is None
    assert provenance == "unavailable"


def test_generic_trailing_escape_refused() -> None:
    """A generic pointer ending in ``~`` stays unavailable (syntax)."""
    index, known = _child_index()
    pointer, provenance = resolve_pointer(index, "Task_A", f"{index['Task_A']}/foo~", known)
    assert pointer is None
    assert provenance == "unavailable"


def test_generic_missing_child_refused() -> None:
    """A well-formed but absent child pointer stays unavailable (existence)."""
    index, known = _child_index()
    missing = f"{index['Task_A']}/documentation/99"
    assert missing not in known
    pointer, provenance = resolve_pointer(index, "Task_A", missing, known)
    assert pointer is None
    assert provenance == "unavailable"


def test_generic_pointer_under_other_id_refused() -> None:
    """A pointer that exists under another id stays unavailable (scope)."""
    index, known = _child_index()
    pointer, provenance = resolve_pointer(index, "Task_A", index["Task_B"], known)
    assert pointer is None
    assert provenance == "unavailable"


def test_generic_idless_child_accepted() -> None:
    """A valid ID-less child of the reported id stays exact."""
    index, known = _child_index()
    child = f"{index['Task_A']}/documentation/0"
    assert child in known
    assert child not in index.values()
    pointer, provenance = resolve_pointer(index, "Task_A", child, known)
    assert pointer == child
    assert provenance == "exact"


@pytest.mark.parametrize(
    ("reported_id", "path", "exists"),
    [
        ("Task_A", "/rootElements/0/flowElements/0/documentation/99", False),
        ("Task_A", "/rootElements/0/flowElements/0/documentation/0", True),
        ("Task_A", "/rootElements/0/flowElements/0", True),
        (None, "/rootElements/0/flowElements/0", True),
        ("D1", "", True),
        (None, "", True),
    ],
)
def test_generic_pointer_without_known_pointers_refused(
    reported_id: str | None, path: str, *, exists: bool
) -> None:
    """DESIGN R3.3 §6.4: no generic pointer is exact without the verified walk set."""
    index, known = _child_index()
    assert (path in known) is exists
    pointer, provenance = resolve_pointer(index, reported_id, path)
    assert pointer is None
    assert provenance == "unavailable"
