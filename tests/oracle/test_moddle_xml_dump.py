"""Differential moddle-xml tests: Python port vs the pinned Node package (Lot 5).

``op=model-dump`` (``tests/oracle/dump.mjs``, ``BpmnModdle`` — always lax)
dumps the canonical model for an XML document; the port reads the same
document lax through the six vendored descriptor packages (five + the
``bpmn-in-color`` 6th package, BR01-COLOR resolved in Lot 7) and must produce
the identical dump (root tree, elements by id, references, warnings). The
corpus is every ``bpmn-moddle`` ``.bpmn`` fixture, including ``error/`` and
``.part.`` fragments (both sides fail those identically — lax warnings).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from test_dump import DESCRIPTORS, RESOURCES

from bpmn_io._js import UNDEFINED
from bpmn_io.moddle import Moddle
from bpmn_io.moddle.base import Base
from bpmn_io.moddle_xml import Reader

if TYPE_CHECKING:
    from collections.abc import Callable

    from bpmn_io.moddle.descriptor_builder import PropertyDescriptor

pytestmark = pytest.mark.oracle

FIXTURES = Path(__file__).parent.parent / "upstream" / "bpmn-moddle" / "test" / "fixtures" / "bpmn"

#: No exclusions: the 6th descriptor package is vendored (BR01-COLOR resolved
#: in Lot 7), so `border-color`/`fill-color` map to properties on both sides.
SKIP_FIXTURES = frozenset()

#: The six default descriptor packages (``DESCRIPTORS`` five + color).
PACKAGES = (*DESCRIPTORS, "color/bpmn-in-color.json")


def _primitive(value: object) -> object:
    """Mirror the ``primitive`` serializer from ``dump.mjs``."""
    if value is None or value is UNDEFINED:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _dump_element(element: Base) -> dict[str, Any]:
    """Mirror ``dumpElement``: ``$type`` + own props in descriptor order + ``$attrs``."""
    out: dict[str, Any] = {"$type": element.type_}
    descriptor = element.descriptor_
    properties = getattr(descriptor, "properties", None) or []
    owned = vars(element)
    for prop in properties:
        if prop.name not in owned:
            continue
        out[prop.name] = _dump_value(element.get(prop.name), prop)
    out["$attrs"] = dict(getattr(element, "attrs_", None) or {})
    return out


def _dump_value(value: object, prop: PropertyDescriptor) -> object:
    if isinstance(value, list):
        return [_dump_item(item, prop) for item in value]
    return _dump_item(value, prop)


def _dump_item(item: object, prop: PropertyDescriptor | None) -> object:
    if isinstance(item, Base):
        if prop is not None and prop.is_reference:
            return item.get("id")
        return _dump_element(item)
    return item


def _dump_py(xml: str) -> dict[str, Any]:
    """Read ``xml`` lax through the port and dump the canonical model."""
    packages = [json.loads((RESOURCES / rel).read_text(encoding="utf-8")) for rel in PACKAGES]
    result = Reader(Moddle(packages), lax=True).from_xml(xml, "bpmn:Definitions")
    return {
        "root": _dump_element(result.root_element),
        "elementsById": {key: _dump_element(el) for key, el in result.elements_by_id.items()},
        "references": [
            {
                "element": _primitive(ref["element"].get("id")),
                "property": ref["property"],
                "id": ref["id"],
            }
            for ref in result.references
        ],
        "warnings": [
            {
                "message": warning.message,
                "element": _dump_element(warning.element) if warning.element is not None else None,
                "property": warning.property,
                "value": _primitive(warning.value),
            }
            for warning in result.warnings
        ],
    }


def _dump_py_safe(xml: str) -> dict[str, Any]:
    """Dump or capture the failure message, mirroring the batch op envelope."""
    from bpmn_io.moddle_xml import ParseError

    try:
        return {"dump": _dump_py(xml)}
    except ParseError as exc:
        return {"error": str(exc)}


def test_model_dump_corpus(oracle_call: Callable[[dict[str, object]], object]) -> None:
    paths = sorted(p for p in FIXTURES.rglob("*.bpmn") if p.name not in SKIP_FIXTURES)
    ids = [str(path.relative_to(FIXTURES)) for path in paths]
    xmls = [path.read_text(encoding="utf-8", errors="replace") for path in paths]
    # One argv per batch: large fixtures exceed the OS argument size limit.
    for start in range(0, len(xmls), 10):
        batch_ids = ids[start : start + 10]
        batch = [{"xml": xml, "type": "bpmn:Definitions"} for xml in xmls[start : start + 10]]
        results = oracle_call({"op": "model-dump-batch", "inputs": batch})
        assert isinstance(results, list)
        assert len(results) == len(batch)
        for fid, xml, expected in zip(batch_ids, xmls[start : start + 10], results, strict=True):
            assert _dump_py_safe(xml) == expected, fid
