"""Differential moddle tests: Python port vs the pinned Node package (Lot 4).

``op=descriptor-dump`` (``tests/oracle/dump.mjs``) dumps the effective
descriptor of every registered type — effective properties in order with
their flags — for the five vendored descriptor packages; the port builds the
same model and must produce the identical dump, including the skipped
(trait-only) types and their error messages.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from test_dump import DESCRIPTORS, RESOURCES

from bpmn_io._js import UNDEFINED
from bpmn_io.moddle import Moddle

if TYPE_CHECKING:
    from collections.abc import Callable

    from bpmn_io.moddle.descriptor_builder import EffectiveDescriptor

pytestmark = pytest.mark.oracle


def _dump_descriptor(descriptor: EffectiveDescriptor) -> dict[str, Any]:
    """Mirror the ``descriptorDump`` per-type shape from ``dump.mjs``."""
    properties = []
    for prop in descriptor.properties:
        entry: dict[str, Any] = {
            "name": prop.name,
            "ns": prop.ns.name if prop.ns is not None else None,
            "type": prop.type,
            "isAttr": bool(prop.is_attr),
            "isMany": bool(prop.is_many),
            "isReference": bool(prop.is_reference),
            "isId": bool(prop.is_id),
            "isBody": bool(prop.is_body),
            "inherited": bool(prop.inherited),
        }
        if prop.default is not UNDEFINED:
            entry["default"] = prop.default
        properties.append(entry)
    return {
        "name": descriptor.name,
        "allTypes": [t["name"] for t in descriptor.all_types],
        "idProperty": descriptor.id_property.name if descriptor.id_property is not None else None,
        "bodyProperty": (
            descriptor.body_property.name if descriptor.body_property is not None else None
        ),
        "properties": properties,
    }


def _dump_py(packages: list[Any]) -> dict[str, Any]:
    """Build the port model and dump every effective descriptor."""
    moddle = Moddle(packages, {"strict": True})
    types = []
    skipped = []
    for name in sorted(moddle.registry.type_map):
        try:
            descriptor = moddle.registry.get_effective_descriptor(name)
        except Exception as exc:  # noqa: BLE001 — messages are the contract here
            skipped.append({"name": name, "error": str(exc)})
            continue
        types.append(_dump_descriptor(descriptor))
    return {"types": types, "skipped": skipped}


def test_descriptor_dump_corpus(oracle_call: Callable[[dict[str, object]], object]) -> None:
    import json

    packages = [json.loads((RESOURCES / rel).read_text(encoding="utf-8")) for rel in DESCRIPTORS]
    expected = oracle_call({"op": "descriptor-dump", "packages": packages})
    assert _dump_py(packages) == expected
