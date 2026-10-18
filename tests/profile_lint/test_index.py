"""Upstream report path resolution (DESIGN R3.3 §6.4)."""

from __future__ import annotations

from bpmn_io.profile._lint.index import build_id_index, resolve_pointer
from tests.profile_lint.helpers import NAMED_TASK_DOC, parse


def _index() -> dict[str, str]:
    """Index the named-task fixture (Task_A first flow element)."""
    return build_id_index(parse(NAMED_TASK_DOC))


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
    index = _index()
    pointer, provenance = resolve_pointer(index, None, "/rootElements/0/flowElements/1")
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
