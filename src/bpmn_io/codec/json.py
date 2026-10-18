# Lossless JSON projection (F1) of the native moddle tree.
"""Project native trees to JSON and hydrate JSON back to native trees.

Generic ``$any`` dispatch precedes every registered-type guard in both
directions. Parents and typed-reference identity are rebuilt on
hydration; inputs are never mutated; descriptors resolve through the
per-call model only. Key order on the wire is UTF-16 code-unit order.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Final, TypeGuard, cast

from bpmn_io._js import UNDEFINED
from bpmn_io.codec._model import (
    CodecResult,
    Diagnostic,
    JsonObject,
    JsonValue,
    NativeElement,
    build_model,
    c14n_bytes,
    escape_pointer,
    is_valid_qname,
    resolve_limits,
    utf16_key,
    utf16_len,
)
from bpmn_io.codec.xml_boundary import cap_diagnostics, element_target

if TYPE_CHECKING:
    from bpmn_io.bpmn_moddle.bpmn_moddle import BpmnModdle
    from bpmn_io.moddle.base import AnyModdleElement, ModdleElement
    from bpmn_io.moddle.descriptor_builder import PropertyDescriptor
    from bpmn_io.moddle.registry import PackageDef

__all__ = ["hydrate", "project"]

#: Internal instance slots never projected (parents are rebuilt on hydration).
_INTERNAL_KEYS: Final = frozenset({"type_", "attrs_", "parent_", "model_", "descriptor_"})

#: Detail strings stay bounded even for hostile payloads.
_MAX_DETAIL: Final = 4096


class _AbortError(Exception):
    """Internal refusal signal carrying its diagnostic."""

    def __init__(self, diagnostic: Diagnostic) -> None:
        """Bind the abort to its diagnostic."""
        super().__init__(diagnostic.code)
        self.diagnostic = diagnostic


def _is_native_element(value: object) -> TypeGuard[NativeElement]:
    """Return whether ``value`` is a native moddle element (no dynamic lookup)."""
    return hasattr(value, "type_") and hasattr(value, "descriptor_") and hasattr(value, "parent_")


def _is_generic(element: NativeElement) -> TypeGuard[AnyModdleElement]:
    """Return whether ``element`` is a generic (``$any``) element."""
    return bool(getattr(getattr(element, "descriptor_", None), "is_generic", False))


class _Projector:
    """State of one projection (explicit stack, bounded traversal)."""

    def __init__(self, limits: dict[str, int]) -> None:
        """Create a projector for ``limits``."""
        self.limits = limits
        self.diagnostics: list[Diagnostic] = []
        self.nodes = 0
        self.seen: set[int] = set()

    def _enter(self, path: str) -> None:
        """Count one node, refusing beyond depth or total limits."""
        self.nodes += 1
        if self.nodes > self.limits["xml-elements"]:
            raise _AbortError(
                Diagnostic(
                    code="xml-element-count-limit",
                    path=path or None,
                    target=None,
                    detail=f"node count exceeds {self.limits['xml-elements']}",
                )
            )
        depth = path.count("/") + 1 if path else 1
        if depth > self.limits["xml-depth"]:
            raise _AbortError(
                Diagnostic(
                    code="xml-depth-limit",
                    path=path or None,
                    target=None,
                    detail=f"depth exceeds {self.limits['xml-depth']}",
                )
            )

    def _check_string(self, text: str, what: str, path: str | None) -> None:
        """Enforce the UTF-16 string limit on one projected string."""
        if utf16_len(text) > self.limits["xml-attr-value-utf16"]:
            raise _AbortError(
                Diagnostic(
                    code="xml-attribute-length-limit",
                    path=path,
                    target=None,
                    detail=f"{what} exceeds the UTF-16 string limit",
                )
            )

    def run(self, root: NativeElement) -> JsonObject:
        """Project ``root`` to JSON-compatible data (explicit stack)."""
        if not _is_native_element(root):
            raise _AbortError(
                Diagnostic(
                    code="invalid-any",
                    path=None,
                    target=None,
                    detail="project root is not a native element",
                )
            )
        # Iterative post-order: (element, path, visited-children?).
        results: dict[int, JsonObject] = {}
        stack: list[tuple[Any, str, bool]] = [(root, "", False)]
        while stack:
            element, path, expanded = stack.pop()
            if expanded:
                results[id(element)] = self._assemble(element, path, results)
                continue
            if id(element) in self.seen:
                raise _AbortError(
                    Diagnostic(
                        code="descriptor-mismatch",
                        path=path or None,
                        target=element_target(element),
                        detail="shared child visited twice",
                    )
                )
            self.seen.add(id(element))
            self._enter(path)
            stack.append((element, path, True))
            for child, child_path in self._child_paths(element, path):
                stack.append((child, child_path, False))
        return results[id(root)]

    def _child_paths(self, element: NativeElement, path: str) -> list[tuple[NativeElement, str]]:
        """List ``(child, path)`` pairs under ``element`` in visit order."""
        prefix = path + "/" if path else "/"
        if _is_generic(element):
            return self._generic_child_paths(element, prefix)
        return self._typed_child_paths(element, prefix)

    def _generic_child_paths(
        self, element: AnyModdleElement, prefix: str
    ) -> list[tuple[NativeElement, str]]:
        """List generic ``$children`` pairs in visit order."""
        found: list[tuple[NativeElement, str]] = []
        children = vars(element).get("$children")
        if isinstance(children, list):
            for index, item in enumerate(children):
                if _is_native_element(item):
                    found.append((item, prefix + "$children/" + str(index)))
        return found

    def _typed_child_paths(
        self, element: NativeElement, prefix: str
    ) -> list[tuple[NativeElement, str]]:
        """List contained-child pairs of one typed element in visit order."""
        found: list[tuple[NativeElement, str]] = []
        descriptor = getattr(element, "descriptor_", None)
        for prop in getattr(descriptor, "properties", ()):
            if prop.is_reference:
                continue
            value = vars(element).get(prop.name, UNDEFINED)
            if value is UNDEFINED or value is None:
                continue
            if _is_native_element(value):
                found.append((value, prefix + escape_pointer(prop.name)))
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    if _is_native_element(item):
                        found.append((item, prefix + escape_pointer(prop.name) + "/" + str(index)))
        return found

    def _assemble(
        self, element: NativeElement, path: str, results: dict[int, JsonObject]
    ) -> JsonObject:
        """Build the JSON node of one element from projected children."""
        if _is_generic(element):
            return self._assemble_generic(element, path, results)
        return self._assemble_typed(element, path, results)

    def _generic_attrs(self, element: AnyModdleElement, path: str) -> dict[str, str]:
        """Collect one generic element's string attributes (bounded)."""
        raw = vars(element)
        attrs: dict[str, str] = {}
        for key, value in raw.items():
            if key in _INTERNAL_KEYS or key in ("$body", "$children"):
                continue
            if key.startswith("$"):
                raise _AbortError(
                    Diagnostic(
                        code="invalid-any",
                        path=path or None,
                        target=None,
                        detail=f"generic member <{key}> is not representable"[:_MAX_DETAIL],
                    )
                )
            if not isinstance(value, str):
                raise _AbortError(
                    Diagnostic(
                        code="invalid-any",
                        path=path or None,
                        target=None,
                        detail=f"generic attribute <{key}> is not a string"[:_MAX_DETAIL],
                    )
                )
            self._check_string(key, "generic attribute name", path or None)
            self._check_string(value, "generic attribute value", path or None)
            attrs[key] = value
        if raw.get("attrs_"):
            raise _AbortError(
                Diagnostic(
                    code="invalid-any",
                    path=path or None,
                    target=None,
                    detail="generic extension storage is not representable",
                )
            )
        return attrs

    def _assemble_generic(
        self, element: AnyModdleElement, path: str, results: dict[int, JsonObject]
    ) -> JsonObject:
        """Build the ``$any`` node of one generic element."""
        raw = vars(element)
        node: dict[str, Any] = {"$type": "$any"}
        name = element.type_
        uri = element.descriptor_.ns_uri
        self._check_string(name, "generic qname", path or None)
        self._check_string(uri, "generic namespace URI", path or None)
        node["$name"] = {"qname": name, "uri": uri}
        node["$attrs"] = self._generic_attrs(element, path)
        if "$body" in raw:
            node["$body"] = self._generic_body(raw["$body"], path)
        if "$children" in raw:
            node["$children"] = self._generic_children(raw["$children"], path, results)
            if "$body" in raw:
                self.diagnostics.append(
                    Diagnostic(
                        code="moddle-content-normalized",
                        path=path or None,
                        target=None,
                        detail="mixed text/child interleaving is not reconstructed",
                    )
                )
        return {key: node[key] for key in sorted(node.keys(), key=utf16_key)}

    def _generic_body(self, body: object, path: str) -> str:
        """Validate one generic ``$body`` payload (must be a string)."""
        if not isinstance(body, str):
            raise _AbortError(
                Diagnostic(
                    code="invalid-any",
                    path=path or None,
                    target=None,
                    detail="generic $body is not a string",
                )
            )
        self._check_string(body, "generic body", path or None)
        return body

    def _generic_children(
        self, children: object, path: str, results: dict[int, JsonObject]
    ) -> list[JsonObject]:
        """Project one generic ``$children`` array (must hold elements)."""
        if not isinstance(children, list):
            raise _AbortError(
                Diagnostic(
                    code="invalid-any",
                    path=path or None,
                    target=None,
                    detail="generic $children is not an array",
                )
            )
        return [results[id(item)] for item in children]

    def _assemble_typed(
        self, element: NativeElement, path: str, results: dict[int, JsonObject]
    ) -> JsonObject:
        """Build the JSON node of one registered-type element."""
        typed = cast("ModdleElement", element)
        node: dict[str, Any] = {"$type": typed.type_}
        descriptor = typed.descriptor_
        reference_names = set(descriptor.reference_names)
        known = set(descriptor.properties_by_name)
        for key in vars(element):
            if key in _INTERNAL_KEYS or key in known:
                continue
            self.diagnostics.append(
                Diagnostic(
                    code="moddle-content-dropped",
                    path=(path + "/" + escape_pointer(key)) if path else "/" + key,
                    target=element_target(element),
                    detail=f"instance member <{key}> has no descriptor slot"[:_MAX_DETAIL],
                )
            )
        for prop in descriptor.properties:
            value = vars(element).get(prop.name, UNDEFINED)
            if value is UNDEFINED:
                continue
            if prop.name in reference_names:
                node[prop.name] = self._project_reference(value, path, prop.name)
                continue
            where = (path + "/" + escape_pointer(prop.name)) if path else "/" + prop.name
            node[prop.name] = self._project_value(value, where, results)
        attrs = dict(vars(element).get("attrs_", {}))
        for key, value in attrs.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise _AbortError(
                    Diagnostic(
                        code="invalid-any",
                        path=path or None,
                        target=element_target(element),
                        detail="typed foreign attribute is not a string pair",
                    )
                )
            self._check_string(key, "foreign attribute name", path or None)
            self._check_string(value, "foreign attribute value", path or None)
        node["$attrs"] = attrs
        return {key: node[key] for key in sorted(node.keys(), key=utf16_key)}

    def _project_reference(self, value: object, path: str, prop: str) -> JsonValue:
        """Project one reference property to ``{"$ref": id}`` entries."""
        if isinstance(value, list):
            return [self._project_reference(item, path, prop) for item in value]
        if not _is_native_element(value):
            raise _AbortError(
                Diagnostic(
                    code="descriptor-mismatch",
                    path=(path + "/" + escape_pointer(prop)) if path else "/" + prop,
                    target=None,
                    detail="reference slot holds a non-element",
                )
            )
        target = element_target(value)
        if target is None:
            raise _AbortError(
                Diagnostic(
                    code="descriptor-mismatch",
                    path=(path + "/" + escape_pointer(prop)) if path else "/" + prop,
                    target=None,
                    detail="reference target carries no id",
                )
            )
        ref: JsonObject = {"$ref": target}
        return ref

    def _project_value(
        self, value: object, where: str, results: dict[int, JsonObject]
    ) -> JsonValue:
        """Project one non-reference property value to JSON data."""
        if value is None or isinstance(value, (bool, str)):
            if isinstance(value, str):
                self._check_string(value, "property value", where)
            return value
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            if not math.isfinite(value):
                raise _AbortError(
                    Diagnostic(
                        code="invalid-any",
                        path=where,
                        target=None,
                        detail="non-finite number is not representable",
                    )
                )
            return value
        if isinstance(value, list):
            return [
                self._project_value(item, where + "/" + str(i), results)
                for i, item in enumerate(value)
            ]
        if _is_native_element(value):
            return results[id(value)]
        raise _AbortError(
            Diagnostic(
                code="invalid-any",
                path=where,
                target=None,
                detail="property value is not representable",
            )
        )


def project(
    root: NativeElement,
    *,
    descriptors: dict[str, PackageDef] | None = None,
    limits: dict[str, int] | None = None,
) -> CodecResult:
    """Project a native tree to JSON-compatible data (generic-first).

    Returns ``ok=True`` with the projected dict, plus loss diagnostics if
    any; limit and shape violations return ``ok=False``. The input tree
    is only read, never mutated.
    """
    resolved = resolve_limits(limits)
    model, model_diagnostic = build_model(descriptors)
    if model is None:
        return CodecResult(
            ok=False,
            value=None,
            diagnostics=(model_diagnostic,),  # type: ignore[arg-type]
        )
    projector = _Projector(resolved)
    try:
        value = projector.run(root)
    except _AbortError as abort:
        return CodecResult(ok=False, value=None, diagnostics=(abort.diagnostic,))
    size = len(c14n_bytes(value))
    if size > resolved["json-object-bytes"]:
        return CodecResult(
            ok=False,
            value=None,
            diagnostics=(
                Diagnostic(
                    code="xml-input-size-limit",
                    path=None,
                    target=None,
                    detail=f"projected object size {size} exceeds {resolved['json-object-bytes']}",
                ),
            ),
        )
    return CodecResult(ok=True, value=value, diagnostics=tuple(projector.diagnostics))


def _slot_kind(model: BpmnModdle, prop: PropertyDescriptor) -> str:
    """Classify one property slot as reference, containment or scalar.

    Enumeration-typed properties (``literalValues`` declarations, never
    registered as element types) hold plain strings and classify as
    scalar, exactly as the native reader and writer treat them.
    """
    if prop.is_reference:
        return "reference"
    if prop.type == "Element":
        return "containment"
    try:
        known = model.registry.type_map.get(prop.type) is not None
    except Exception:  # noqa: BLE001 - unknown descriptors fail closed to scalar
        known = False
    if known:
        return "containment"
    return "scalar"


class _Validator:
    """Input validation walk before native construction (no model nodes built)."""

    def __init__(self, model: BpmnModdle, limits: dict[str, int]) -> None:
        """Bind the validator to its per-call model and limits."""
        self.model = model
        self.limits = limits
        self.nodes = 0
        self.seen: set[int] = set()

    def _check_string(self, text: str, what: str, path: str | None) -> None:
        """Enforce the UTF-16 string limit on one input string."""
        if utf16_len(text) > self.limits["xml-attr-value-utf16"]:
            raise _AbortError(
                Diagnostic(
                    code="xml-attribute-length-limit",
                    path=path,
                    target=None,
                    detail=f"{what} exceeds the UTF-16 string limit",
                )
            )

    def run(self, data: JsonValue) -> None:
        """Validate the whole input (shapes, reserved names, string limits)."""
        if not isinstance(data, dict):
            raise _AbortError(
                Diagnostic(
                    code="invalid-any",
                    path=None,
                    target=None,
                    detail="hydrate root is not an object",
                )
            )
        stack: list[tuple[Any, str, int]] = [(data, "", 1)]
        while stack:
            node, path, depth = stack.pop()
            if not isinstance(node, dict):
                raise _AbortError(
                    Diagnostic(
                        code="invalid-any",
                        path=path or None,
                        target=None,
                        detail="element node is not an object",
                    )
                )
            if id(node) in self.seen:
                raise _AbortError(
                    Diagnostic(
                        code="descriptor-mismatch",
                        path=path or None,
                        target=None,
                        detail="shared child used twice",
                    )
                )
            self.seen.add(id(node))
            if depth > self.limits["xml-depth"]:
                raise _AbortError(
                    Diagnostic(
                        code="xml-depth-limit",
                        path=path or None,
                        target=None,
                        detail=f"depth exceeds {self.limits['xml-depth']}",
                    )
                )
            self.nodes += 1
            if self.nodes > self.limits["xml-elements"]:
                raise _AbortError(
                    Diagnostic(
                        code="xml-element-count-limit",
                        path=path or None,
                        target=None,
                        detail=f"node count exceeds {self.limits['xml-elements']}",
                    )
                )
            type_name = node.get("$type")
            if not isinstance(type_name, str):
                raise _AbortError(
                    Diagnostic(
                        code="invalid-any",
                        path=path or None,
                        target=None,
                        detail="$type is not a string",
                    )
                )
            self._check_string(type_name, "$type", path or None)
            if type_name == "$any":
                self._validate_generic(node, path, depth, stack)
            else:
                self._validate_typed(node, path, depth, stack, type_name)

    def _push_child(self, value: JsonValue, path: str, depth: int, stack: list[Any]) -> None:
        """Queue one contained child node for validation."""
        stack.append((value, path, depth + 1))

    def _validate_generic(
        self, node: dict[str, Any], path: str, depth: int, stack: list[Any]
    ) -> None:
        """Validate one ``$any`` node (reserved names refused first)."""
        for key in node:
            if key in ("$type", "$name", "$attrs", "$body", "$children"):
                continue
            raise _AbortError(
                Diagnostic(
                    code="invalid-any",
                    path=path or None,
                    target=None,
                    detail=f"generic member <{key}> is not allowed"[:_MAX_DETAIL],
                )
            )
        self._validate_generic_name(node, path)
        self._validate_generic_payload(node, path, depth, stack)

    def _validate_generic_name(self, node: dict[str, Any], path: str) -> None:
        """Validate one ``$any`` node's ``$name`` shape and namespace."""
        name = node.get("$name")
        if (
            not isinstance(name, dict)
            or not isinstance(name.get("qname"), str)
            or not isinstance(name.get("uri"), str)
            or set(name.keys()) != {"qname", "uri"}
        ):
            raise _AbortError(
                Diagnostic(
                    code="invalid-any",
                    path=path or None,
                    target=None,
                    detail="$name is not {qname, uri} strings",
                )
            )
        qname = name["qname"]
        uri = name["uri"]
        self._check_string(qname, "$name.qname", path or None)
        self._check_string(uri, "$name.uri", path or None)
        if not is_valid_qname(qname):
            raise _AbortError(
                Diagnostic(
                    code="malformed-qname",
                    path=path or None,
                    target=None,
                    detail=f"generic name <{qname}> is malformed"[:_MAX_DETAIL],
                )
            )
        if ":" in qname and not uri:
            raise _AbortError(
                Diagnostic(
                    code="invalid-namespace",
                    path=path or None,
                    target=None,
                    detail=f"prefixed name <{qname}> has an empty URI",
                )
            )

    def _validate_generic_payload(
        self, node: dict[str, Any], path: str, depth: int, stack: list[Any]
    ) -> None:
        """Validate one ``$any`` node's attributes, body and children."""
        prefix = path + "/" if path else "/"
        attrs = node.get("$attrs")
        if not isinstance(attrs, dict):
            raise _AbortError(
                Diagnostic(
                    code="invalid-any",
                    path=path or None,
                    target=None,
                    detail="$attrs is not a string map",
                )
            )
        self._check_attrs(attrs, path)
        body = node.get("$body")
        if "$body" in node:
            if not isinstance(body, str):
                raise _AbortError(
                    Diagnostic(
                        code="invalid-any",
                        path=path or None,
                        target=None,
                        detail="$body is not a string",
                    )
                )
            self._check_string(body, "$body", path or None)
        children = node.get("$children")
        if "$children" in node:
            if not isinstance(children, list):
                raise _AbortError(
                    Diagnostic(
                        code="invalid-any",
                        path=path or None,
                        target=None,
                        detail="$children is not an array",
                    )
                )
            for index, item in enumerate(children):
                self._push_child(item, prefix + "$children/" + str(index), depth, stack)

    def _check_attrs(self, attrs: dict[Any, Any], path: str) -> None:
        """Refuse reserved names and non-string pairs in one attribute map."""
        from bpmn_io.codec._model import RESERVED_NAMES  # noqa: PLC0415

        count = len(attrs)
        if count > self.limits["xml-attributes-per-element"]:
            raise _AbortError(
                Diagnostic(
                    code="xml-attribute-count-limit",
                    path=path or None,
                    target=None,
                    detail=(f"attribute count exceeds {self.limits['xml-attributes-per-element']}"),
                )
            )
        for key in attrs:
            if key in RESERVED_NAMES:
                where = (
                    (path + "/$attrs/" + escape_pointer(key))
                    if path
                    else ("/$attrs/" + escape_pointer(key))
                )
                raise _AbortError(
                    Diagnostic(
                        code="reserved-name",
                        path=where,
                        target=None,
                        detail=f"reserved attribute <{key}>"[:_MAX_DETAIL],
                    )
                )
        for key, value in attrs.items():
            if path and isinstance(key, str):
                key_path = path + "/$attrs/" + escape_pointer(key)
            elif not path:
                key_path = "/$attrs"
            else:
                key_path = path + "/$attrs"
            if not isinstance(key, str) or not isinstance(value, str):
                raise _AbortError(
                    Diagnostic(
                        code="invalid-any",
                        path=key_path,
                        target=None,
                        detail="$attrs holds a non-string pair",
                    )
                )
            self._check_string(key, "attribute name", key_path)
            self._check_string(value, "attribute value", key_path)

    def _validate_typed(
        self, node: dict[str, Any], path: str, depth: int, stack: list[Any], type_name: str
    ) -> None:
        """Validate one registered-type node against its effective descriptor."""
        prefix = path + "/" if path else "/"
        try:
            descriptor = self.model.registry.get_effective_descriptor(type_name)
        except Exception:  # noqa: BLE001 - unknown names refuse, whatever the cause
            raise _AbortError(
                Diagnostic(
                    code="descriptor-mismatch",
                    path=path or None,
                    target=None,
                    detail=f"unknown type <{type_name}>"[:_MAX_DETAIL],
                )
            ) from None
        known = descriptor.properties_by_name
        for key, value in node.items():
            if key in ("$type", "$attrs"):
                continue
            if key in known:
                self._validate_slot(value, known[key], prefix + escape_pointer(key), depth, stack)
                continue
            self._validate_foreign(key, value, prefix, path)
        attrs = node.get("$attrs", {})
        if not isinstance(attrs, dict):
            raise _AbortError(
                Diagnostic(
                    code="invalid-any",
                    path=path or None,
                    target=None,
                    detail="$attrs is not a string map",
                )
            )
        self._check_attrs(attrs, path)

    def _validate_foreign(self, key: str, value: JsonValue, prefix: str, path: str) -> None:
        """Validate one foreign member of a typed node (reserved names refuse)."""
        from bpmn_io.codec._model import RESERVED_NAMES  # noqa: PLC0415

        if key in RESERVED_NAMES:
            raise _AbortError(
                Diagnostic(
                    code="reserved-name",
                    path=prefix + escape_pointer(key),
                    target=None,
                    detail=f"reserved member <{key}>"[:_MAX_DETAIL],
                )
            )
        if not isinstance(value, str):
            raise _AbortError(
                Diagnostic(
                    code="invalid-any",
                    path=prefix + escape_pointer(key),
                    target=None,
                    detail=f"foreign attribute <{key}> is not a string"[:_MAX_DETAIL],
                )
            )
        self._check_string(key, "foreign attribute name", path or None)
        self._check_string(value, "foreign attribute value", path or None)

    def _validate_slot(
        self,
        value: JsonValue,
        prop: PropertyDescriptor,
        path: str,
        depth: int,
        stack: list[Any],
    ) -> None:
        """Validate one property value against its descriptor slot."""
        items = value if isinstance(value, list) else [value]
        if isinstance(value, list) and not prop.is_many:
            raise _AbortError(
                Diagnostic(
                    code="descriptor-mismatch",
                    path=path,
                    target=None,
                    detail=f"single slot <{prop.name}> holds an array",
                )
            )
        kind = _slot_kind(self.model, prop)
        for index, item in enumerate(items):
            where = path if not isinstance(value, list) else path + "/" + str(index)
            if kind == "reference":
                self._validate_reference(item, prop, where)
                continue
            if isinstance(item, dict):
                if kind != "containment" or "$ref" in item:
                    raise _AbortError(
                        Diagnostic(
                            code="descriptor-mismatch",
                            path=where,
                            target=None,
                            detail=f"slot <{prop.name}> holds an incompatible node",
                        )
                    )
                self._push_child(item, where, depth, stack)
                continue
            if item is None or isinstance(item, (str, bool, int, float)):
                if kind == "containment":
                    raise _AbortError(
                        Diagnostic(
                            code="descriptor-mismatch",
                            path=where,
                            target=None,
                            detail=f"containment slot <{prop.name}> holds a scalar",
                        )
                    )
                if isinstance(item, str):
                    self._check_string(item, "property value", where)
                continue
            raise _AbortError(
                Diagnostic(
                    code="descriptor-mismatch",
                    path=where,
                    target=None,
                    detail=f"slot <{prop.name}> holds an unsupported value",
                )
            )

    def _validate_reference(self, item: JsonValue, prop: PropertyDescriptor, where: str) -> None:
        """Validate one reference entry (exactly ``{"$ref": id}``)."""
        if (
            not isinstance(item, dict)
            or set(item.keys()) != {"$ref"}
            or not isinstance(item.get("$ref"), str)
        ):
            raise _AbortError(
                Diagnostic(
                    code="descriptor-mismatch",
                    path=where,
                    target=None,
                    detail=f"reference slot <{prop.name}> holds a non-reference",
                )
            )
        ref = item.get("$ref")
        assert isinstance(ref, str)  # noqa: S101 - narrowed by the shape check above
        self._check_string(ref, "reference id", where)


class _Builder:
    """Native construction from validated input (references resolved last)."""

    def __init__(self, model: BpmnModdle) -> None:
        """Bind the builder to its per-call model."""
        self.model = model
        self.diagnostics: list[Diagnostic] = []
        self.pending: list[tuple[ModdleElement, PropertyDescriptor, str, str]] = []
        self.index: dict[str, NativeElement] = {}

    def run(self, data: JsonValue) -> NativeElement:
        """Build the tree, index typed ids, then resolve references."""
        if not isinstance(data, dict):
            raise _AbortError(
                Diagnostic(
                    code="invalid-any",
                    path=None,
                    target=None,
                    detail="hydrate root is not an object",
                )
            )
        root = self._build(data, "")
        self._index_ids(root)
        self._resolve()
        return root

    def _index_ids(self, root: NativeElement) -> None:
        """Index typed elements by id; generic ids never enter the index."""
        stack: list[tuple[Any, str]] = [(root, "")]
        seen: set[int] = set()
        while stack:
            element, path = stack.pop()
            if id(element) in seen:
                continue
            seen.add(id(element))
            if not _is_generic(element):
                target = element_target(element)
                if target is not None:
                    if target in self.index:
                        raise _AbortError(
                            Diagnostic(
                                code="xml-invalid",
                                path=path or None,
                                target=target,
                                detail=f"duplicate ID <{target}>"[:_MAX_DETAIL],
                            )
                        )
                    self.index[target] = element
            self._enqueue_contained(stack, element, path)

    def _enqueue_contained(self, stack: list[tuple[Any, str]], element: object, path: str) -> None:
        """Queue contained children of one built element for id indexing."""
        raw = vars(element)
        children = raw.get("$children")
        if isinstance(children, list):
            for index, item in enumerate(children):
                stack.append((item, path + "/$children/" + str(index)))
        descriptor = getattr(element, "descriptor_", None)
        properties = getattr(descriptor, "properties", None)
        if properties is None:
            return
        for prop in properties:
            self._enqueue_slot(stack, raw, prop, path)

    def _enqueue_slot(
        self, stack: list[tuple[Any, str]], raw: dict[str, Any], prop: PropertyDescriptor, path: str
    ) -> None:
        """Queue one property slot's contained children for id indexing."""
        if prop.is_reference:
            return
        value = raw.get(prop.name, UNDEFINED)
        if value is UNDEFINED or value is None:
            return
        slot = path + "/" + escape_pointer(prop.name)
        if _is_native_element(value):
            stack.append((value, slot))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if _is_native_element(item):
                    stack.append((item, slot + "/" + str(index)))

    def _index_target(self, ref_id: str) -> NativeElement | None:
        """Return the typed target of ``ref_id`` (generic ids never indexed)."""
        candidate = self.index.get(ref_id)
        if candidate is not None and not _is_generic(candidate):
            return candidate
        return None

    def _resolve(self) -> None:
        """Resolve pending references; misses warn and unset (native parity)."""
        for element, prop, ref_id, path in self.pending:
            target = self._index_target(ref_id)
            if target is None:
                self.diagnostics.append(
                    Diagnostic(
                        code="moddle-warning",
                        path=path or None,
                        target=None,
                        detail=f"unresolved reference <{ref_id}>"[:_MAX_DETAIL],
                    )
                )
                continue
            if prop.is_many:
                collection = element.get(prop.name)
                if isinstance(collection, list):
                    collection.append(target)
            else:
                element.set(prop.name, target)

    def _build(self, node: dict[str, Any], path: str) -> NativeElement:
        """Build one element with parent links (input already validated)."""
        type_name = node["$type"]
        if type_name == "$any":
            return self._build_generic(node, path)
        try:
            element = self.model.create(type_name)
        except Exception:  # noqa: BLE001 - factory raises per violated invariant
            raise _AbortError(
                Diagnostic(
                    code="descriptor-mismatch",
                    path=path or None,
                    target=None,
                    detail=f"unknown type <{type_name}>"[:_MAX_DETAIL],
                )
            ) from None
        self._fill_typed(element, node, path)
        return element

    def _fill_typed(self, element: ModdleElement, node: dict[str, Any], path: str) -> None:
        """Fill one typed element's slots and foreign attributes."""
        known = element.descriptor_.properties_by_name
        prefix = path + "/" if path else "/"
        for key, value in node.items():
            if key in ("$type", "$attrs"):
                continue
            if key in known:
                self._fill_slot(element, known[key], value, prefix + escape_pointer(key))
                continue
            element.set(key, value)
        for key, value in node.get("$attrs", {}).items():
            element.set(key, value)

    def _fill_slot(
        self, element: ModdleElement, prop: PropertyDescriptor, value: JsonValue, base_path: str
    ) -> None:
        """Fill one property slot by its reference/scalar/containment kind."""
        kind = _slot_kind(self.model, prop)
        if kind == "reference":
            self._fill_reference(element, prop, value, base_path)
        elif kind == "scalar":
            self._fill_scalar(element, prop, value, base_path)
        else:
            self._fill_containment(element, prop, value, base_path)

    def _fill_reference(
        self, element: ModdleElement, prop: PropertyDescriptor, value: JsonValue, base_path: str
    ) -> None:
        """Queue one reference slot's targets (resolved after indexing)."""
        items = value if isinstance(value, list) else [value]
        if prop.is_many:
            element.set(prop.name, [])
        else:
            element.set(prop.name, UNDEFINED)
        for index, item in enumerate(items):
            suffix = "/" + str(index) if isinstance(value, list) else ""
            child_path = base_path + suffix
            ref = item.get("$ref") if isinstance(item, dict) else None
            if not isinstance(ref, str):
                raise _AbortError(
                    Diagnostic(
                        code="descriptor-mismatch",
                        path=child_path,
                        target=None,
                        detail=f"reference slot <{prop.name}> holds a non-reference",
                    )
                )
            self.pending.append((element, prop, ref, child_path))

    def _fill_scalar(
        self, element: ModdleElement, prop: PropertyDescriptor, value: JsonValue, base_path: str
    ) -> None:
        """Fill one scalar slot, coercing simple-typed values natively."""
        items = value if isinstance(value, list) else [value]
        if prop.is_many:
            collection = element.get(prop.name)
            if not isinstance(collection, list):
                raise _AbortError(
                    Diagnostic(
                        code="descriptor-mismatch",
                        path=base_path,
                        target=None,
                        detail=f"slot <{prop.name}> holds no collection",
                    )
                )
            for item in items:
                collection.append(_coerce_simple(prop, item, base_path))
        else:
            element.set(prop.name, _coerce_simple(prop, items[0], base_path))

    def _fill_containment(
        self, element: ModdleElement, prop: PropertyDescriptor, value: JsonValue, base_path: str
    ) -> None:
        """Build one containment slot's children with parent links."""
        items = value if isinstance(value, list) else [value]
        for index, item in enumerate(items):
            suffix = "/" + str(index) if isinstance(value, list) else ""
            child_path = base_path + suffix
            if not isinstance(item, dict):
                raise _AbortError(
                    Diagnostic(
                        code="descriptor-mismatch",
                        path=child_path,
                        target=None,
                        detail=f"containment slot <{prop.name}> holds a scalar",
                    )
                )
            child = self._build(item, child_path)
            if prop.is_many:
                collection = element.get(prop.name)
                if not isinstance(collection, list):
                    raise _AbortError(
                        Diagnostic(
                            code="descriptor-mismatch",
                            path=child_path,
                            target=None,
                            detail=f"slot <{prop.name}> holds no collection",
                        )
                    )
                collection.append(child)
            else:
                element.set(prop.name, child)
            child.parent_ = element

    def _build_generic(self, node: dict[str, Any], path: str) -> AnyModdleElement:
        """Build one generic element (identity, attributes, body, children)."""
        name = node["$name"]
        element = self.model.create_any(name["qname"], name["uri"])
        for key, value in node["$attrs"].items():
            element[key] = value
        if "$body" in node:
            element["$body"] = node["$body"]
        if "$children" in node:
            prefix = path + "/" if path else "/"
            children: list[NativeElement] = []
            element["$children"] = children
            for index, item in enumerate(node["$children"]):
                child = self._build(item, prefix + "$children/" + str(index))
                children.append(child)
                child.parent_ = element
        return element


def _coerce_simple(prop: PropertyDescriptor, item: JsonValue, path: str) -> object:
    """Coerce one simple-typed value through the native converter."""
    from bpmn_io.moddle import coerce_type  # noqa: PLC0415

    if prop.type == "String" or not isinstance(item, str):
        return item
    try:
        return coerce_type(prop.type, item)
    except Exception:  # noqa: BLE001 - converters raise per malformed input
        raise _AbortError(
            Diagnostic(
                code="descriptor-mismatch",
                path=path,
                target=None,
                detail=f"value of <{prop.name}> does not coerce to <{prop.type}>"[:_MAX_DETAIL],
            )
        ) from None


def hydrate(
    data: JsonValue,
    *,
    descriptors: dict[str, PackageDef] | None = None,
    limits: dict[str, int] | None = None,
) -> CodecResult:
    """Hydrate JSON data to a native tree (generic-first, parents rebuilt).

    Reserved names refuse BEFORE native construction; shapes, limits and
    descriptor slots validate next; references resolve last with
    native-parity misses (warn and unset). The input is only read.
    """
    resolved = resolve_limits(limits)
    model, model_diagnostic = build_model(descriptors)
    if model is None:
        return CodecResult(
            ok=False,
            value=None,
            diagnostics=(model_diagnostic,),  # type: ignore[arg-type]
        )
    try:
        input_size = len(c14n_bytes(data))
    except Exception:  # noqa: BLE001 - untrusted input may not canonicalize
        input_size = 0
    if input_size > resolved["json-object-bytes"]:
        return CodecResult(
            ok=False,
            value=None,
            diagnostics=(
                Diagnostic(
                    code="xml-input-size-limit",
                    path=None,
                    target=None,
                    detail=(
                        f"input object size {input_size} exceeds {resolved['json-object-bytes']}"
                    ),
                ),
            ),
        )
    validator = _Validator(model, resolved)
    try:
        validator.run(data)
        builder = _Builder(model)
        value = builder.run(data)
    except _AbortError as abort:
        return CodecResult(ok=False, value=None, diagnostics=(abort.diagnostic,))
    return CodecResult(
        ok=True,
        value=value,
        diagnostics=tuple(cap_diagnostics(builder.diagnostics, truncated=False)),
    )
