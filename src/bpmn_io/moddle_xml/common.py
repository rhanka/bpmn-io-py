# Transposed from bpmn-io/moddle-xml@dc01570 lib/common.js (MIT).
"""Namespace helpers transposed from moddle-xml ``lib/common.js``."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bpmn_io.moddle.descriptor_builder import PropertyDescriptor
    from bpmn_io.moddle.registry import RegisteredPackage

__all__ = [
    "DEFAULT_NS_MAP",
    "SERIALIZE_PROPERTY",
    "get_serialization",
    "get_serialization_type",
    "has_lower_case_alias",
]

#: Default namespace uris by prefix (inverted when building the uri map).
DEFAULT_NS_MAP: dict[str, str] = {
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
    "xml": "http://www.w3.org/XML/1998/namespace",
}

#: Serialization marker opting out of `xsi:type` / `xmi:type` resolution.
SERIALIZE_PROPERTY = "property"


def has_lower_case_alias(pkg: RegisteredPackage) -> bool:
    """Return whether a package lowerCases its tag names."""
    xml = pkg.get("xml")
    return isinstance(xml, dict) and xml.get("tagAlias") == "lowerCase"


def get_serialization(element: PropertyDescriptor) -> object:
    """Return the `xml.serialize` marker of a property descriptor, if mapping-shaped."""
    xml = element.xml
    if isinstance(xml, dict):
        return xml.get("serialize")
    return None


def get_serialization_type(element: PropertyDescriptor) -> str | None:
    """Return the attribute carrying a property's effective type, if any."""
    serialize = get_serialization(element)
    if isinstance(serialize, str) and serialize != SERIALIZE_PROPERTY:
        return serialize
    return None
