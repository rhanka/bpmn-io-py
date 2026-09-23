"""Port-robustness: dunders are never intercepted (Lot 4 plan requirement).

Upstream has no ``__getattr__`` equivalent — properties are plain instance
attributes and dynamic classes rebuild through the owning model. These pin
that ``copy``, ``pickle`` and ``hasattr`` keep working on elements; they carry
no upstream marker (no JS counterpart exists).
"""

from __future__ import annotations

import copy
import json
import pickle
from pathlib import Path

import pytest

from bpmn_io.moddle import Moddle

FIXTURES = (
    Path(__file__).resolve().parent.parent / "upstream" / "moddle" / "test" / "fixtures" / "model"
)
RESOURCES = Path(__file__).resolve().parent.parent.parent / "src" / "bpmn_io" / "resources"


def _model() -> Moddle:
    """Build the model the upstream ``properties`` suite runs against."""
    package = json.loads((FIXTURES / "properties.json").read_text(encoding="utf-8"))
    return Moddle([package])


def test_copy_preserves_type_and_values() -> None:
    element = _model().create("props:Complex", {"id": "a", "name": "n"})
    clone = copy.copy(element)
    assert clone is not element
    assert clone.get("id") == "a"
    assert clone.type_ == element.type_


def test_deepcopy_duplicates_values() -> None:
    element = _model().create("props:Complex", {"id": "a"})
    clone = copy.deepcopy(element)
    assert clone is not element
    assert clone.get("id") == "a"
    clone.set("id", "b")
    assert element.get("id") == "a"


def test_pickle_roundtrip() -> None:
    element = _model().create("props:Complex", {"id": "a", "name": "n"})
    clone = pickle.loads(pickle.dumps(element))  # noqa: S301 - roundtrip of a self-created element
    assert clone.type_ == "props:Complex"
    assert clone.get("id") == "a"
    assert clone.get("name") == "n"


def test_keyword_properties_via_get_set_kwargs() -> None:
    """Python-keyword properties (`from`, `import`, `type`) work via get/set/kwargs."""
    bpmn = json.loads((RESOURCES / "bpmn" / "bpmn.json").read_text(encoding="utf-8"))
    model = Moddle([bpmn])
    assert model.create("bpmn:Assignment", {"from": "x"}).get("from") == "x"
    item = model.create("bpmn:ItemDefinition")
    item.set("import", "y")
    assert item.get("import") == "y"
    for type_name in (
        "bpmn:Relationship",
        "bpmn:ExtensionAttributeDefinition",
        "bpmn:CorrelationProperty",
        "bpmn:ResourceParameter",
    ):
        element = model.create(type_name)
        element.set("type", "t1")
        assert element.get("type") == "t1"


def test_dunders_not_intercepted() -> None:
    element = _model().create("props:Complex")
    assert hasattr(element, "__class__")
    assert isinstance(element.__dict__, dict)
    assert not hasattr(element, "missing-property")
    with pytest.raises(AttributeError):
        _ = element.missing_property
