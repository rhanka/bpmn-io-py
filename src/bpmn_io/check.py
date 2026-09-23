"""L0 integrity checks over BPMN XML strings and model trees (plan Lot 7 L0 item)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeGuard, overload

from bpmn_io._js import UNDEFINED
from bpmn_io.bpmn_moddle.simple import create_moddle
from bpmn_io.moddle.base import AnyModdleElement, Base, ModdleElement
from bpmn_io.moddle.ns import parse_name
from bpmn_io.moddle_xml.read import ParseError, ParseWarning

__all__ = ["Report", "check"]


@dataclass(frozen=True)
class Report:
    """The outcome of :func:`check` (frozen, mirroring ``ParseResult``/``WriteResult``)."""

    #: True when no errors were found (warnings alone keep ``ok`` True).
    ok: bool
    #: Fatal findings: unresolved references, unknown attributes, parse messages.
    errors: list[str]
    #: Collected warnings (plus one synthetic warning per error for element input).
    warnings: list[ParseWarning]
    #: Elements indexed by id (empty when the input is unparseable).
    elements_by_id: dict[str, ModdleElement | AnyModdleElement]


@overload
def check(
    xml_or_element: str, type_name: str = ..., options: dict[str, Any] | None = ...
) -> Report: ...
@overload
def check(xml_or_element: ModdleElement | AnyModdleElement) -> Report: ...
def check(
    xml_or_element: object,
    type_name: str = "bpmn:Definitions",
    options: dict[str, Any] | None = None,
) -> Report:
    """Check a BPMN XML string or a model tree, returning a frozen ``Report``."""
    if isinstance(xml_or_element, str):
        return _check_xml(xml_or_element, type_name, options)
    if _is_element(xml_or_element):
        return _check_element(xml_or_element)
    msg = "check() requires an XML string or a model element, got " + type(xml_or_element).__name__
    raise TypeError(msg)


def _is_element(value: object) -> TypeGuard[ModdleElement | AnyModdleElement]:
    """Return whether ``value`` is a model element (typed or generic)."""
    return isinstance(value, Base)


def _check_xml(xml: str, type_name: str, options: dict[str, Any] | None) -> Report:
    """Parse ``xml`` with the default model, mapping ``ParseError`` to a ``Report``."""
    model = create_moddle()
    try:
        result = model.from_xml(xml, type_name, options)
    except ParseError as err:
        return Report(
            ok=False,
            errors=[err.message],
            warnings=list(err.warnings),
            elements_by_id={},
        )
    return Report(
        ok=True,
        errors=[],
        warnings=list(result.warnings),
        elements_by_id=dict(result.elements_by_id),
    )


def _check_element(element: ModdleElement | AnyModdleElement) -> Report:
    """Walk ``element``, reporting unresolved references and unknown attributes."""
    errors: list[str] = []
    warnings: list[ParseWarning] = []
    elements_by_id: dict[str, ModdleElement | AnyModdleElement] = {}
    ordered = _collect_elements(element, elements_by_id)
    for candidate in ordered:
        _check_unknown_attributes(candidate, errors, warnings)
        _check_references(candidate, elements_by_id, errors, warnings)
    return Report(ok=not errors, errors=errors, warnings=warnings, elements_by_id=elements_by_id)


def _collect_elements(
    root: ModdleElement | AnyModdleElement,
    elements_by_id: dict[str, ModdleElement | AnyModdleElement],
) -> list[ModdleElement | AnyModdleElement]:
    """Walk the containment tree, indexing elements by their ``id``."""
    ordered: list[ModdleElement | AnyModdleElement] = []
    seen: set[int] = set()
    stack: list[ModdleElement | AnyModdleElement] = [root]
    while stack:
        current = stack.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        ordered.append(current)
        _index_by_id(current, elements_by_id)
        stack.extend(_child_elements(current))
    return ordered


def _index_by_id(
    element: ModdleElement | AnyModdleElement,
    elements_by_id: dict[str, ModdleElement | AnyModdleElement],
) -> None:
    """Record ``element`` under its string ``id``, when it has one."""
    if isinstance(element, AnyModdleElement):
        raw_id: object = element.get("id")
    else:
        id_property = element.descriptor_.id_property
        if id_property is None:
            return
        raw_id = element.get(id_property.name)
    if isinstance(raw_id, str):
        elements_by_id[raw_id] = element


def _child_elements(
    element: ModdleElement | AnyModdleElement,
) -> list[ModdleElement | AnyModdleElement]:
    """Return the directly contained child elements of ``element``."""
    if isinstance(element, AnyModdleElement):
        return _generic_children(element)
    children: list[ModdleElement | AnyModdleElement] = []
    owned = vars(element)
    for prop in element.descriptor_.properties:
        if prop.is_attr or prop.is_reference or prop.is_virtual:
            continue
        raw = owned.get(prop.name, UNDEFINED)
        if raw is UNDEFINED or raw is None:
            continue
        if prop.is_many:
            if isinstance(raw, list):
                children.extend(item for item in raw if _is_element(item))
        elif _is_element(raw):
            children.append(raw)
    return children


def _generic_children(
    element: AnyModdleElement,
) -> list[ModdleElement | AnyModdleElement]:
    """Return the child elements of a generic element."""
    children: list[ModdleElement | AnyModdleElement] = []
    raw_children = element.get("$children")
    if isinstance(raw_children, list):
        children.extend(item for item in raw_children if _is_element(item))
    for key, value in vars(element).items():
        if key in ("type_", "parent_", "descriptor_", "model_", "$children"):
            continue
        if _is_element(value):
            children.append(value)
        elif isinstance(value, list):
            children.extend(item for item in value if _is_element(item))
    return children


def _check_unknown_attributes(
    element: ModdleElement | AnyModdleElement,
    errors: list[str],
    warnings: list[ParseWarning],
) -> None:
    """Report leftover ``attrs_`` entries as unknown attributes (generic nodes skipped).

    Only entries the reader would have warned about are reported: a bare ``xmlns``
    slot and XML-machinery prefixes (``xmlns:*``, ``xsi:*``) are accepted silently,
    exactly like the reader's warning condition in ``read.py:create_element``.
    """
    if isinstance(element, AnyModdleElement):
        return
    for name, value in element.attrs_.items():
        if name == "xmlns":
            continue
        prefix = parse_name(name, element.descriptor_.ns.prefix).prefix
        if element.model_.get_package(prefix or "") is None:
            continue
        message = f"unknown attribute <{name}>"
        errors.append(message)
        warnings.append(ParseWarning(message=message, element=element, property=name, value=value))


def _check_references(
    element: ModdleElement | AnyModdleElement,
    elements_by_id: dict[str, ModdleElement | AnyModdleElement],
    errors: list[str],
    warnings: list[ParseWarning],
) -> None:
    """Report reference properties holding ids absent from the collected index."""
    if isinstance(element, AnyModdleElement):
        return
    owned = vars(element)
    for prop in element.descriptor_.properties:
        if not prop.is_reference or prop.name not in owned:
            continue
        raw = owned[prop.name]
        targets: list[object] = list(raw) if prop.is_many and isinstance(raw, list) else [raw]
        for target in targets:
            if isinstance(target, str) and target not in elements_by_id:
                message = f"unresolved reference <{target}>"
                errors.append(message)
                warnings.append(
                    ParseWarning(message=message, element=element, property=prop.name, value=target)
                )
