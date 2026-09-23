# Transposed from bpmn-io/moddle-xml@dc01570 lib/write.js (MIT).
"""Moddle-to-XML writer transposed from moddle-xml ``lib/write.js``.

``Writer`` serializes a moddle element tree to XML; the module-level
:func:`to_xml` wraps it and collects unknown-prefix warnings into
:class:`WriteResult`. Tree building and serialization both use explicit
stacks, so deeply nested documents stay flat.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, Self, cast, overload

from bpmn_io._js import UNDEFINED, number_to_string, strict_equal
from bpmn_io.moddle import is_simple_type, parse_name_ns
from bpmn_io.moddle.descriptor_builder import AnyTypeDescriptor
from bpmn_io.moddle_xml.common import (
    DEFAULT_NS_MAP,
    SERIALIZE_PROPERTY,
    get_serialization,
    has_lower_case_alias,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from bpmn_io.moddle.base import AnyModdleElement, ModdleElement
    from bpmn_io.moddle.descriptor_builder import (
        EffectiveDescriptor,
        PropertyDescriptor,
    )
    from bpmn_io.moddle.moddle import Moddle
    from bpmn_io.moddle.registry import RegisteredPackage

__all__ = [
    "XML_PREAMBLE",
    "BodySerializer",
    "ElementSerializer",
    "FormatingWriter",
    "FormattingWriter",
    "Namespaces",
    "ReferenceSerializer",
    "SavingWriter",
    "TypeSerializer",
    "ValueSerializer",
    "WriteResult",
    "Writer",
    "XmlSink",
    "build_tree",
    "escape_attr",
    "escape_body",
    "filter_attributes",
    "filter_contained",
    "get_default_prefix_mappings",
    "get_element_ns",
    "get_ns_attrs",
    "get_property_ns",
    "get_serializable_properties",
    "lower",
    "name_to_alias",
    "ns_name",
    "serialize_tree",
    "to_xml",
]

#: XML preamble prepended unless the writer is created with ``preamble=False``.
XML_PREAMBLE = '<?xml version="1.0" encoding="UTF-8"?>\n'

_ESCAPE_ATTR_CHARS = re.compile('<|>|\'"|"|&|\n\r|\n')
_ESCAPE_CHARS = re.compile("<|>|&")

_ESCAPE_ATTR_MAP = {
    "\n": "#10",
    "\n\r": "#10",
    '"': "#34",
    "'": "#39",
    "<": "#60",
    ">": "#62",
    "&": "#38",
}

_ESCAPE_MAP = {"<": "lt", ">": "gt", "&": "amp"}

#: Generic instance keys skipped as interpreter state (cf. ``base._SPECIAL_NAMES``).
_GENERIC_INTERNAL_KEYS = frozenset({"type_", "attrs_", "parent_", "model_", "descriptor_"})


def _stringify(value: Any) -> str:  # noqa: ANN401 - JS string coercion takes anything
    """Coerce ``value`` as JavaScript string concatenation would."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return number_to_string(value)
    if isinstance(value, str):
        return value
    if value is None:
        return "null"
    if value is UNDEFINED:
        return "undefined"
    return str(value)


class Namespaces:
    """A scope of known namespace declarations, chained to its parent."""

    def __init__(self, parent: Namespaces | None = None) -> None:
        """Create a scope inheriting ``parent``'s default prefix map."""
        self.prefix_map: dict[str, str] = {}
        self.uri_map: dict[str, dict[str, Any]] = {}
        self.used: dict[str, dict[str, Any] | None] = {}
        self.wellknown: list[dict[str, Any]] = []
        self.custom: list[dict[str, Any]] = []
        self.parent = parent
        self.default_prefix_map: dict[str, str] = (
            parent.default_prefix_map if parent is not None else {}
        )

    def map_default_prefixes(self, default_prefix_map: dict[str, str]) -> None:
        """Replace the default prefix-to-uri map."""
        self.default_prefix_map = default_prefix_map

    def default_uri_by_prefix(self, prefix: str | None) -> str | None:
        """Return the default uri for ``prefix``, if mapped."""
        return self.default_prefix_map.get(prefix) if prefix is not None else None

    def resolve(self, fn: Callable[[Namespaces], object]) -> object:
        """Return the first truthy ``fn(scope)`` walking up the ancestors."""
        scope: Namespaces | None = self
        while scope is not None:
            resolved = fn(scope)
            if resolved:
                return resolved
            scope = scope.parent
        return None

    def each_scope(self, fn: Callable[[Namespaces], None]) -> None:
        """Call ``fn(scope)`` for this scope and each ancestor."""
        scope: Namespaces | None = self
        while scope is not None:
            fn(scope)
            scope = scope.parent

    def by_uri(self, uri: str | None) -> dict[str, Any] | None:
        """Return the namespace registered for ``uri``, if any."""
        return cast(
            "dict[str, Any] | None",
            self.resolve(lambda scope: scope.uri_map.get(uri) if uri is not None else None),
        )

    def add(self, ns: dict[str, Any], is_wellknown: bool = False) -> None:  # noqa: FBT001, FBT002
        """Register ``ns`` by uri, tracking it as wellknown or custom."""
        self.uri_map[cast("str", ns.get("uri"))] = ns
        if is_wellknown:
            self.wellknown.append(ns)
        else:
            self.custom.append(ns)
        self.map_prefix(ns.get("prefix"), ns.get("uri"))

    def uri_by_prefix(self, prefix: str | None) -> str | None:
        """Return the uri mapped for ``prefix`` (bare ``xmlns`` when unset)."""
        key = prefix or "xmlns"
        return cast("str | None", self.resolve(lambda scope: scope.prefix_map.get(key)))

    def map_prefix(self, prefix: str | None, uri: str | None) -> None:
        """Map ``prefix`` (bare ``xmlns`` when unset) to ``uri``."""
        self.prefix_map[prefix or "xmlns"] = cast("str", uri)

    def get_ns_key(self, ns: dict[str, Any]) -> str:
        """Return the usage key of ``ns`` (``uri|prefix`` when prefixed)."""
        prefix = ns.get("prefix")
        uri = ns.get("uri")
        if prefix is not None:
            return str(uri) + "|" + str(prefix)
        return str(uri)

    def log_used(self, ns: dict[str, Any]) -> None:
        """Mark ``ns`` used in this scope and every ancestor."""
        ns_key = self.get_ns_key(ns)
        resolved = self.by_uri(ns.get("uri"))
        self.each_scope(lambda scope: scope.used.__setitem__(ns_key, resolved))

    def get_used(self) -> list[dict[str, Any]]:
        """Return the registered namespaces logged as used, in order."""
        all_ns = [*self.wellknown, *self.custom]
        return [ns for ns in all_ns if self.used.get(self.get_ns_key(ns))]


def lower(text: str) -> str:
    """Lowercase the first character (``tagAlias: lowerCase`` writes)."""
    return text[:1].lower() + text[1:]


def name_to_alias(name: str, pkg: RegisteredPackage | None) -> str:
    """Return the tag alias for ``name`` (lowercased for lowerCase packages)."""
    if pkg is not None and has_lower_case_alias(pkg):
        return lower(name)
    return name


def ns_name(ns: str | dict[str, Any]) -> str:
    """Render a namespace reference (strings pass through untouched)."""
    if isinstance(ns, str):
        return ns
    prefix = ns.get("prefix")
    local_name = ns.get("localName")
    return ((prefix + ":") if prefix else "") + str(local_name)


def get_ns_attrs(namespaces: Namespaces) -> list[dict[str, Any]]:
    """Project used namespaces to ``xmlns`` declarations (never ``xml``)."""
    return [
        {
            "name": "xmlns" + ((":" + str(ns["prefix"])) if ns.get("prefix") else ""),
            "value": ns.get("uri"),
        }
        for ns in namespaces.get_used()
        if ns.get("prefix") != "xml"
    ]


def get_element_ns(
    ns: dict[str, Any], descriptor: EffectiveDescriptor | AnyTypeDescriptor
) -> dict[str, Any]:
    """Merge the tag local name (alias-aware) over the effective namespace."""
    if isinstance(descriptor, AnyTypeDescriptor):
        local_name = descriptor.ns_local_name
    else:
        local_name = name_to_alias(descriptor.ns.local_name, descriptor.pkg)
    return {"localName": local_name, **ns}


def get_property_ns(ns: dict[str, Any], descriptor: PropertyDescriptor) -> dict[str, Any]:
    """Merge the property local name (always raw) over the namespace."""
    return {"localName": descriptor.ns.local_name, **ns}


def get_serializable_properties(element: ModdleElement) -> list[PropertyDescriptor]:
    """Return the set properties of a typed element, in descriptor order."""
    descriptor = element.descriptor_
    owned = vars(element)
    result: list[PropertyDescriptor] = []
    for prop in descriptor.properties:
        if prop.is_virtual:
            continue
        # Own-dict membership: class-level defaults are visible but not set.
        if prop.name not in owned:
            continue
        value = element.get(prop.name)
        # Strict equality: ``True`` never equals ``1``, as upstream ``===``.
        if strict_equal(value, prop.default):
            continue
        if value is None:
            continue
        if prop.is_many and len(cast("list[Any]", value)) == 0:
            continue
        result.append(prop)
    return result


def _escape(
    value: Any,  # noqa: ANN401 - JS escape coerces anything via string concat
    pattern: re.Pattern[str],
    replace_map: dict[str, str],
) -> str:
    """Escape ``value`` (stringified first, as upstream)."""
    text = value if isinstance(value, str) else _stringify(value)
    return pattern.sub(lambda match: "&" + replace_map[match.group(0)] + ";", text)


def escape_attr(value: Any) -> str:  # noqa: ANN401 - JS escapeAttr coerces anything
    """Escape an attribute value (line breaks, quotes, ``<>&``)."""
    return _escape(value, _ESCAPE_ATTR_CHARS, _ESCAPE_ATTR_MAP)


def escape_body(value: Any) -> str:  # noqa: ANN401 - JS escapeBody coerces anything
    """Escape body text (``<>&``)."""
    return _escape(value, _ESCAPE_CHARS, _ESCAPE_MAP)


def filter_attributes(props: list[PropertyDescriptor]) -> list[PropertyDescriptor]:
    """Split the attribute properties out of ``props``."""
    return [prop for prop in props if prop.is_attr]


def filter_contained(props: list[PropertyDescriptor]) -> list[PropertyDescriptor]:
    """Split the contained (non-attribute) properties out of ``props``."""
    return [prop for prop in props if not prop.is_attr]


def _descriptor_ns(descriptor: EffectiveDescriptor | AnyTypeDescriptor) -> dict[str, Any]:
    """Project a descriptor namespace to a writer ``ns`` reference."""
    if isinstance(descriptor, AnyTypeDescriptor):
        return {
            "prefix": descriptor.ns_prefix,
            "uri": descriptor.ns_uri,
            "localName": descriptor.ns_local_name,
        }
    return {
        "prefix": descriptor.ns.prefix,
        "uri": None,
        "localName": descriptor.ns.local_name,
    }


def _property_ns(prop: PropertyDescriptor) -> dict[str, Any]:
    """Project a property namespace to a writer ``ns`` reference."""
    return {"prefix": prop.ns.prefix, "uri": None, "localName": prop.ns.local_name}


class ReferenceSerializer:
    """A serializer for reference properties (``<tag>id</tag>`` lines)."""

    def __init__(self, tag_name: str) -> None:
        """Bind the serializer to its tag name."""
        self.tag_name = tag_name
        self.element: ModdleElement | AnyModdleElement | None = None

    def build(self, element: ModdleElement | AnyModdleElement) -> Self:
        """Bind the referenced element."""
        self.element = element
        return self

    def serialize_to(self, writer: FormattingWriter) -> None:
        """Write the indented ``<tag>id</tag>`` line."""
        element_id = _stringify(getattr(self.element, "id", UNDEFINED))
        writer.append_indent().append(
            "<" + self.tag_name + ">" + element_id + "</" + self.tag_name + ">"
        ).append_new_line()


class BodySerializer:
    """A serializer for body text (escaped only for ``String`` properties)."""

    def __init__(self) -> None:
        """Create an unbound body serializer."""
        self.value: Any = None
        self.escape = False

    def build(
        self,
        prop: PropertyDescriptor | dict[str, Any],
        value: Any,  # noqa: ANN401 - body values are dynamically typed
    ) -> Self:
        """Bind the body value, flagging ``String`` values needing escape."""
        self.value = value
        prop_type = prop["type"] if isinstance(prop, dict) else prop.type
        if (
            prop_type == "String"
            and isinstance(value, str)
            and _ESCAPE_CHARS.search(value) is not None
        ):
            self.escape = True
        return self

    def serialize_value(self, writer: FormattingWriter) -> None:
        """Append the (maybe escaped) value."""
        writer.append(escape_body(self.value) if self.escape else _stringify(self.value))

    def serialize_to(self, writer: FormattingWriter) -> None:
        """Append the (maybe escaped) value."""
        self.serialize_value(writer)


class ValueSerializer(BodySerializer):
    """A serializer for simple-typed containment (``<tag>value</tag>`` lines)."""

    def __init__(self, tag_name: str) -> None:
        """Bind the serializer to its tag name."""
        super().__init__()
        self.tag_name = tag_name

    def serialize_to(self, writer: FormattingWriter) -> None:
        """Write the indented ``<tag>value</tag>`` line."""
        writer.append_indent().append("<" + self.tag_name + ">")
        self.serialize_value(writer)
        writer.append("</" + self.tag_name + ">").append_new_line()


class ElementSerializer:
    """A serializer for one element (namespaces, tag, attributes, children)."""

    def __init__(
        self,
        parent: ElementSerializer | None = None,
        property_descriptor: PropertyDescriptor | None = None,
    ) -> None:
        """Nest under ``parent`` for ``property_descriptor`` (sharing warnings)."""
        self.body: list[Any] = []
        self.attrs: list[dict[str, Any]] = []
        self.parent = parent
        self.property_descriptor = property_descriptor
        self.element: ModdleElement | AnyModdleElement | None = None
        self.ns: dict[str, Any] = {}
        self.tag_name = ""
        self.other_attrs: list[dict[str, Any]] = []
        self.namespaces: Namespaces | None = None
        self.parent_namespaces: Namespaces | Any | None = UNDEFINED
        self.warnings: list[str] = parent.warnings if parent is not None else []

    def build(self, element: ModdleElement | AnyModdleElement) -> Self:
        """Build the serializer tree for ``element`` (iterative)."""
        build_tree(self, element)
        return self

    def enter(self, element: ModdleElement | AnyModdleElement) -> list[dict[str, Any]]:
        """Register namespaces, tag and attributes; return deferred child work."""
        self.element = element
        descriptor = element.descriptor_
        property_descriptor = self.property_descriptor
        is_generic = isinstance(descriptor, AnyTypeDescriptor)
        if is_generic:
            self.other_attrs = self.parse_generic_ns_attributes(cast("AnyModdleElement", element))
        else:
            self.other_attrs = self.parse_ns_attributes(cast("ModdleElement", element))
        if property_descriptor is not None:
            self.ns = self.ns_property_tag_name(property_descriptor)
        else:
            self.ns = self.ns_tag_name(descriptor)
        self.tag_name = self.add_tag_name(self.ns)
        if is_generic:
            return self.collect_generic_containments(cast("AnyModdleElement", element))
        properties = get_serializable_properties(cast("ModdleElement", element))
        self.parse_attributes(filter_attributes(properties))
        return self.collect_containments(filter_contained(properties))

    def exit(self) -> None:
        """Attach generic attributes after children (document order)."""
        if self.element is not None:
            self.parse_generic_attributes(self.element, self.other_attrs)

    def ns_tag_name(self, descriptor: EffectiveDescriptor | AnyTypeDescriptor) -> dict[str, Any]:
        """Resolve the element tag namespace (alias-aware)."""
        effective_ns = self.log_namespace_used(_descriptor_ns(descriptor))
        return get_element_ns(effective_ns, descriptor)

    def ns_property_tag_name(self, descriptor: PropertyDescriptor) -> dict[str, Any]:
        """Resolve the property tag namespace (raw local name)."""
        effective_ns = self.log_namespace_used(_property_ns(descriptor))
        return get_property_ns(effective_ns, descriptor)

    def is_local_ns(self, ns: dict[str, Any]) -> bool:
        """Return whether ``ns`` matches this element's namespace."""
        return ns.get("uri") == self.ns.get("uri")

    def ns_attribute_name(self, target: str | PropertyDescriptor) -> dict[str, Any]:
        """Resolve the attribute name, stripping the prefix when local."""
        if isinstance(target, str):
            parsed = parse_name_ns(target)
            ns = {
                "prefix": parsed.prefix,
                "uri": None,
                "localName": parsed.local_name,
            }
            inherited = False
        else:
            ns = _property_ns(target)
            inherited = target.inherited
        if inherited:
            return {"localName": ns["localName"]}
        effective_ns = self.log_namespace_used(ns)
        self.get_namespaces().log_used(effective_ns)
        if self.is_local_ns(effective_ns):
            return {"localName": ns["localName"]}
        return {"localName": ns["localName"], **effective_ns}

    def parse_generic_ns_attributes(self, element: AnyModdleElement) -> list[dict[str, Any]]:
        """Consume generic ``xmlns`` declarations; return leftover attributes."""
        leftovers: list[dict[str, Any]] = []
        for key, value in vars(element).items():
            if key.startswith("$") or key in _GENERIC_INTERNAL_KEYS:
                continue
            leftover = self.parse_ns_attribute(element, key, value)
            if leftover is not None:
                leftovers.append(leftover)
        return leftovers

    def collect_generic_containments(self, element: AnyModdleElement) -> list[dict[str, Any]]:
        """Defer ``$body``/``$children`` serializers for a generic element."""
        children: list[dict[str, Any]] = []
        body_text = element.get("$body")
        if body_text:

            def _create_body(text: object = body_text) -> BodySerializer:
                """Build the generic body serializer."""
                return BodySerializer().build({"type": "String"}, text)

            children.append({"create": _create_body})
        generic_children = element.get("$children")
        if generic_children:
            for child in cast("list[Any]", generic_children):

                def _create_child(
                    _self: ElementSerializer = self,
                ) -> ElementSerializer:
                    """Build the child element serializer."""
                    return ElementSerializer(_self)

                children.append({"create": _create_child, "element": child})
        return children

    def parse_ns_attribute(
        self,
        element: ModdleElement | AnyModdleElement,
        name: str,
        value: Any,  # noqa: ANN401 - attribute values are dynamically typed
    ) -> dict[str, Any] | None:
        """Consume one ``xmlns`` declaration; return other attributes as-is."""
        model = getattr(element, "model_", None)
        name_ns = parse_name_ns(name)
        ns: dict[str, Any] | None = None
        if name_ns.prefix == "xmlns":
            ns = {"prefix": name_ns.local_name, "uri": value}
        if name_ns.prefix is None and name_ns.local_name == "xmlns":
            ns = {"uri": value}
        if ns is None:
            return {"name": name, "value": value}
        if model is not None and model.get_package(value) is not None:
            self.log_namespace(ns, wellknown=True, local=True)
        else:
            actual_ns = self.log_namespace_used(ns, local=True)
            self.get_namespaces().log_used(actual_ns)
        return None

    def parse_ns_attributes(self, element: ModdleElement) -> list[dict[str, Any]]:
        """Consume ``$attrs`` namespaces first; return leftover attributes."""
        attributes: list[dict[str, Any]] = []
        for name, value in element.attrs_.items():
            leftover = self.parse_ns_attribute(element, name, value)
            if leftover is not None:
                attributes.append(leftover)
        return attributes

    def parse_generic_attributes(
        self,
        element: ModdleElement | AnyModdleElement,
        attributes: list[dict[str, Any]],
    ) -> None:
        """Attach leftover attributes, warning on missing namespace info."""
        for attr in attributes:
            try:
                self.add_attribute(self.ns_attribute_name(attr["name"]), attr["value"])
            except Exception as err:  # noqa: BLE001 - unknown prefixes warn, upstream
                self.warnings.append(
                    "missing namespace information for <"
                    + str(attr["name"])
                    + "="
                    + _stringify(attr["value"])
                    + "> on "
                    + repr(element)
                    + ": "
                    + str(err)
                )

    def collect_containments(self, properties: list[PropertyDescriptor]) -> list[dict[str, Any]]:
        """Defer child serializers for body, simple, reference and containment."""
        element = cast("ModdleElement", self.element)
        children: list[dict[str, Any]] = []
        for prop in properties:
            raw = element.get(prop.name)
            values: list[Any] = cast("list[Any]", raw) if prop.is_many else [raw]
            if prop.is_body:
                children.append(self._body_child(prop, values[0]))
            elif is_simple_type(prop.type):
                children.extend(self._simple_children(prop, values))
            elif prop.is_reference:
                children.extend(self._reference_children(prop, values))
            else:
                children.extend(self._contained_children(prop, values, get_serialization(prop)))
        return children

    def _body_child(self, prop: PropertyDescriptor, value: object) -> dict[str, Any]:
        """Defer the body serializer for one body property."""

        def _create_body(
            _prop: PropertyDescriptor = prop,
            _value: object = value,
        ) -> BodySerializer:
            """Build the body serializer."""
            return BodySerializer().build(_prop, _value)

        return {"create": _create_body}

    def _simple_children(self, prop: PropertyDescriptor, values: list[Any]) -> list[dict[str, Any]]:
        """Defer one value serializer per simple-typed value."""
        children: list[dict[str, Any]] = []
        for item in values:

            def _create_value(
                _self: ElementSerializer = self,
                _prop: PropertyDescriptor = prop,
                _item: object = item,
            ) -> ValueSerializer:
                """Build the simple-value serializer (namespaces in order)."""
                tag = _self.add_tag_name(_self.ns_property_tag_name(_prop))
                return ValueSerializer(tag).build(_prop, _item)

            children.append({"create": _create_value})
        return children

    def _reference_children(
        self, prop: PropertyDescriptor, values: list[Any]
    ) -> list[dict[str, Any]]:
        """Defer one reference serializer per referenced element."""
        children: list[dict[str, Any]] = []
        for item in values:

            def _create_reference(
                _self: ElementSerializer = self,
                _prop: PropertyDescriptor = prop,
                _item: ModdleElement | AnyModdleElement = item,
            ) -> ReferenceSerializer:
                """Build the reference serializer (namespaces in order)."""
                tag = _self.add_tag_name(_self.ns_property_tag_name(_prop))
                return ReferenceSerializer(tag).build(_item)

            children.append({"create": _create_reference})
        return children

    def _contained_children(
        self, prop: PropertyDescriptor, values: list[Any], serialization: object
    ) -> list[dict[str, Any]]:
        """Defer one element serializer per contained element."""
        children: list[dict[str, Any]] = []
        for item in values:

            def _create_contained(
                _self: ElementSerializer = self,
                _prop: PropertyDescriptor = prop,
                _item: ModdleElement | AnyModdleElement = item,
                _serialization: object = serialization,
            ) -> ElementSerializer:
                """Build the contained serializer (namespaces in order)."""
                if _serialization:
                    if _serialization == SERIALIZE_PROPERTY:
                        return ElementSerializer(_self, _prop)
                    return TypeSerializer(_self, _prop, cast("str", _serialization))
                return ElementSerializer(_self)

            children.append({"create": _create_contained, "element": item})
        return children

    def get_namespaces(
        self,
        local: bool = False,  # noqa: FBT001, FBT002 - upstream flag shape
    ) -> Namespaces:
        """Return the owned scope (creating it) or the ancestor scope."""
        namespaces = self.namespaces
        if namespaces is None:
            parent_namespaces = self.get_parent_namespaces()
            if local or parent_namespaces is None:
                self.namespaces = namespaces = Namespaces(parent_namespaces)
            else:
                namespaces = parent_namespaces
        return namespaces

    def get_parent_namespaces(self) -> Namespaces | None:
        """Resolve and memoize the closest ancestor scope (``None`` = none)."""
        memoized = self.parent_namespaces
        if memoized is not UNDEFINED:
            return cast("Namespaces | None", memoized)
        scope: Namespaces | None = None
        ancestor = self.parent
        while ancestor is not None:
            if ancestor.namespaces is not None:
                scope = ancestor.namespaces
                break
            if ancestor.parent_namespaces is not UNDEFINED:
                scope = cast("Namespaces | None", ancestor.parent_namespaces)
                break
            ancestor = ancestor.parent
        self.parent_namespaces = scope
        return scope

    def log_namespace(
        self,
        ns: dict[str, Any],
        wellknown: bool = False,  # noqa: FBT001, FBT002 - upstream flag shape
        local: bool = False,  # noqa: FBT001, FBT002 - upstream flag shape
    ) -> dict[str, Any]:
        """Add ``ns`` to the scope (mapping its prefix), returning it."""
        namespaces = self.get_namespaces(local=local)
        if namespaces.by_uri(ns.get("uri")) is None or local:
            namespaces.add(ns, is_wellknown=wellknown)
        namespaces.map_prefix(ns.get("prefix"), ns.get("uri"))
        return ns

    def log_namespace_used(
        self,
        ns: dict[str, Any],
        local: bool = False,  # noqa: FBT001, FBT002 - upstream flag shape
    ) -> dict[str, Any]:
        """Resolve ``ns`` to its canonical scope entry (registering it)."""
        namespaces = self.get_namespaces(local=local)
        prefix = ns.get("prefix")
        uri = ns.get("uri")
        if not prefix and not uri:
            # Anonymous namespace (elementForm=unqualified), cf. #23.
            return {"localName": ns.get("localName")}
        wellknown_uri = namespaces.default_uri_by_prefix(prefix)
        uri = uri or wellknown_uri or namespaces.uri_by_prefix(prefix)
        if not uri:
            msg = "no namespace uri given for prefix <" + str(prefix) + ">"
            raise ValueError(msg)
        resolved = namespaces.by_uri(uri)
        if resolved is None:
            resolved = self._ensure_namespace(namespaces, prefix, uri, wellknown_uri)
        if prefix:
            namespaces.map_prefix(prefix, uri)
        return resolved

    def _ensure_namespace(
        self,
        namespaces: Namespaces,
        prefix: str | None,
        uri: str,
        wellknown_uri: str | None,
    ) -> dict[str, Any]:
        """Register a default or deconflicted prefixed namespace for ``uri``."""
        if not prefix:
            return self.log_namespace({"uri": uri}, wellknown=(wellknown_uri == uri), local=True)
        new_prefix: str | None = prefix
        idx = 1
        while namespaces.uri_by_prefix(new_prefix):
            new_prefix = str(prefix) + "_" + str(idx)
            idx += 1
        return self.log_namespace(
            {"prefix": new_prefix, "uri": uri}, wellknown=(wellknown_uri == uri)
        )

    def parse_attributes(self, properties: list[PropertyDescriptor]) -> None:
        """Serialize attribute properties (references via their ids)."""
        element = cast("ModdleElement", self.element)
        for prop in properties:
            value = element.get(prop.name)
            if prop.is_reference:
                if not prop.is_many:
                    value = getattr(value, "id", UNDEFINED)
                else:
                    parts: list[str] = []
                    for item in cast("list[Any]", value):
                        item_id = getattr(item, "id", UNDEFINED)
                        if item_id is None or item_id is UNDEFINED:
                            parts.append("")
                        else:
                            parts.append(_stringify(item_id))
                    value = " ".join(parts)
            self.add_attribute(self.ns_attribute_name(prop), value)

    def add_tag_name(self, ns_tag_name: dict[str, Any]) -> str:
        """Log the tag namespace as used, returning the qualified tag name."""
        actual_ns = self.log_namespace_used(ns_tag_name)
        self.get_namespaces().log_used(actual_ns)
        return ns_name(ns_tag_name)

    def add_attribute(
        self,
        name: dict[str, Any],
        value: Any,  # noqa: ANN401 - attribute values are dynamically typed
    ) -> None:
        """Add an attribute, escaping strings and de-duplicating (issue #66)."""
        attrs = self.attrs
        text = escape_attr(value) if isinstance(value, str) else _stringify(value)
        idx = -1
        for pos, attr in enumerate(attrs):
            existing = attr["name"]
            if (
                existing.get("localName") == name.get("localName")
                and existing.get("uri") == name.get("uri")
                and existing.get("prefix") == name.get("prefix")
            ):
                idx = pos
                break
        attr = {"name": name, "value": text}
        if idx != -1:
            attrs[idx] = attr
        else:
            attrs.append(attr)

    def serialize_attributes(self, writer: FormattingWriter) -> None:
        """Write hoisted namespace declarations first, then attributes."""
        attrs = list(self.attrs)
        if self.namespaces is not None:
            attrs = get_ns_attrs(self.namespaces) + attrs
        for attr in attrs:
            writer.append(" ").append(ns_name(attr["name"])).append('="').append(
                attr["value"]
            ).append('"')

    def serialize_to(self, writer: FormattingWriter) -> None:
        """Serialize this element's tree to ``writer``."""
        serialize_tree(self, writer)


def serialize_tree(root: ElementSerializer, writer: FormattingWriter) -> None:
    """Serialize a built serializer tree iteratively (deep-nesting safe)."""
    stack: list[dict[str, Any]] = [
        {"serializer": root, "index": 0, "opened": False, "indent": False}
    ]
    while stack:
        frame = stack[-1]
        serializer = cast("ElementSerializer", frame["serializer"])
        if not frame["opened"]:
            first_body = serializer.body[0] if serializer.body else None
            frame["indent"] = first_body is not None and type(first_body) is not BodySerializer
            writer.append_indent().append("<" + serializer.tag_name)
            serializer.serialize_attributes(writer)
            writer.append(">" if first_body is not None else " />")
            frame["opened"] = True
            if first_body is None:
                writer.append_new_line()
                stack.pop()
                continue
            if frame["indent"]:
                writer.append_new_line().indent()
        if frame["index"] < len(serializer.body):
            child = serializer.body[frame["index"]]
            frame["index"] = frame["index"] + 1
            if isinstance(child, ElementSerializer):
                stack.append({"serializer": child, "index": 0, "opened": False, "indent": False})
            else:
                child.serialize_to(writer)
            continue
        if frame["indent"]:
            writer.unindent().append_indent()
        writer.append("</" + serializer.tag_name + ">").append_new_line()
        stack.pop()


class TypeSerializer(ElementSerializer):
    """A serializer adding an ``xsi:type``/``xmi:type`` marker attribute."""

    def __init__(
        self,
        parent: ElementSerializer | None,
        property_descriptor: PropertyDescriptor,
        serialization: str,
    ) -> None:
        """Bind the containment parent, property and type carrier attribute."""
        super().__init__(parent, property_descriptor)
        self.serialization = serialization
        self.type_ns: dict[str, Any] | None = None

    def parse_ns_attributes(self, element: ModdleElement) -> list[dict[str, Any]]:
        """Strip the serialization carrier; add the effective-type marker."""
        attributes = [
            attr
            for attr in super().parse_ns_attributes(element)
            if attr["name"] != self.serialization
        ]
        descriptor = element.descriptor_
        prop = cast("PropertyDescriptor", self.property_descriptor)
        # Same name as the property type: no ``xsi:type`` needed.
        if descriptor.name == prop.type:
            return attributes
        self.type_ns = self.ns_tag_name(descriptor)
        self.get_namespaces().log_used(self.type_ns)
        model = element.model_
        pkg = model.get_package(str(self.type_ns.get("uri")))
        xml_conf = pkg.get("xml") if isinstance(pkg, dict) else None
        type_prefix = (xml_conf.get("typePrefix") if isinstance(xml_conf, dict) else None) or ""
        prefix = self.type_ns.get("prefix")
        self.add_attribute(
            self.ns_attribute_name(self.serialization),
            ((prefix + ":") if prefix else "") + type_prefix + descriptor.ns.local_name,
        )
        return attributes

    def is_local_ns(self, ns: dict[str, Any]) -> bool:
        """Match against the effective-type namespace, once resolved."""
        base = self.type_ns if self.type_ns is not None else self.ns
        return ns.get("uri") == base.get("uri")


class SavingWriter:
    """An in-memory sink collecting the serialized document."""

    def __init__(self) -> None:
        """Create an empty sink."""
        self.value = ""

    def write(self, text: str) -> None:
        """Append ``text`` to the collected document."""
        self.value += text


class XmlSink(Protocol):
    """An external XML sink (anything with ``write(str)``)."""

    def write(self, text: str) -> object:
        """Append ``text`` to the sink."""
        ...


class FormattingWriter:
    """An indenting writer facade (newlines and indent gated on ``format``)."""

    def __init__(
        self,
        out: XmlSink,
        format: bool,  # noqa: A002, FBT001 - upstream option name
    ) -> None:
        """Wrap ``out``, enabling pretty-printing when ``format`` is set."""
        self._out = out
        self._format = format
        self._indent = [""]

    def append(self, text: str) -> FormattingWriter:
        """Write ``text`` verbatim."""
        self._out.write(text)
        return self

    def append_new_line(self) -> FormattingWriter:
        """Write a newline when formatting."""
        if self._format:
            self._out.write("\n")
        return self

    def append_indent(self) -> FormattingWriter:
        """Write the current indent when formatting."""
        if self._format:
            self._out.write("  ".join(self._indent))
        return self

    def indent(self) -> FormattingWriter:
        """Increase the indent level."""
        self._indent.append("")
        return self

    def unindent(self) -> FormattingWriter:
        """Decrease the indent level."""
        self._indent.pop()
        return self


#: Upstream spelling alias (``FormatingWriter`` in ``lib/write.js``).
FormatingWriter = FormattingWriter


class Writer:
    """A writer for meta-model backed document trees (behavioral port)."""

    def __init__(
        self,
        format: bool = False,  # noqa: A002, FBT001, FBT002 - upstream option names
        preamble: bool = True,  # noqa: FBT001, FBT002 - upstream option names
    ) -> None:
        """Store the output options (``format``/``preamble``, as upstream)."""
        self.format = format
        self.preamble = preamble
        self.warnings: list[str] = []

    @overload
    def to_xml(self, tree: ModdleElement | AnyModdleElement, writer: None = None) -> str: ...

    @overload
    def to_xml(self, tree: ModdleElement | AnyModdleElement, writer: XmlSink) -> None: ...

    def to_xml(
        self, tree: ModdleElement | AnyModdleElement, writer: XmlSink | None = None
    ) -> str | None:
        """Serialize ``tree`` (string return, or stream into ``writer``)."""
        self.warnings = []
        internal: XmlSink = writer if writer is not None else SavingWriter()
        formatting = FormattingWriter(internal, format=self.format)
        if self.preamble:
            formatting.append(XML_PREAMBLE)
        serializer = ElementSerializer()
        serializer.warnings = self.warnings
        model = cast(
            "Moddle",
            getattr(tree, "model_"),  # noqa: B009 - $model is undeclared, upstream
        )
        serializer.get_namespaces().map_default_prefixes(get_default_prefix_mappings(model))
        serializer.build(tree).serialize_to(formatting)
        if writer is None:
            return cast("SavingWriter", internal).value
        return None


@dataclass(frozen=True)
class WriteResult:
    """The successful ``to_xml`` result (mirroring ``ParseResult``)."""

    xml: str
    warnings: list[str]


def build_tree(
    root_serializer: ElementSerializer,
    root_element: ModdleElement | AnyModdleElement,
) -> None:
    """Build the serializer tree iteratively (deep-nesting safe)."""
    stack: list[dict[str, Any]] = [
        {
            "serializer": root_serializer,
            "children": root_serializer.enter(root_element),
            "index": 0,
        }
    ]
    while stack:
        frame = stack[-1]
        serializer = cast("ElementSerializer", frame["serializer"])
        children = cast("list[dict[str, Any]]", frame["children"])
        index = cast("int", frame["index"])
        if index >= len(children):
            serializer.exit()
            stack.pop()
            continue
        frame["index"] = index + 1
        child = children[index]
        child_serializer = child["create"]()
        serializer.body.append(child_serializer)
        if child.get("element") is not None:
            stack.append(
                {
                    "serializer": child_serializer,
                    "children": child_serializer.enter(child["element"]),
                    "index": 0,
                }
            )


def get_default_prefix_mappings(model: Moddle) -> dict[str, str]:
    """Map default prefixes to uris (defaults, ``nsMap`` config, packages)."""
    configured: dict[str, str] = dict(model.config.get("nsMap") or {})
    prefix_map: dict[str, str] = {
        **DEFAULT_NS_MAP,
        **{prefix: uri for uri, prefix in configured.items()},
    }
    for pkg in model.get_packages():
        prefix_map[pkg["prefix"]] = pkg["uri"]
    return prefix_map


def to_xml(
    element: ModdleElement | AnyModdleElement,
    format: bool = False,  # noqa: A002, FBT001, FBT002 - upstream option names
    preamble: bool = True,  # noqa: FBT001, FBT002 - upstream option names
) -> WriteResult:
    """Serialize ``element``, collecting unknown-prefix warnings."""
    writer = Writer(format=format, preamble=preamble)
    return WriteResult(xml=writer.to_xml(element), warnings=writer.warnings)
