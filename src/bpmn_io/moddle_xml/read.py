# Transposed from bpmn-io/moddle-xml@dc01570 lib/read.js (MIT).
"""XML-to-moddle reader transposed from moddle-xml ``lib/read.js`` (read path only).

The handler stack is a plain list (iterative, no recursion). Upstream promise
rejections surface as synchronous ``ParseError`` raises carrying ``.warnings``.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

from bpmn_io._js import UNDEFINED, UndefinedType
from bpmn_io.moddle import Moddle, coerce_type, is_simple_type, parse_name_ns
from bpmn_io.moddle_xml.common import (
    DEFAULT_NS_MAP,
    get_serialization_type,
    has_lower_case_alias,
)
from bpmn_io.saxen import Parser

if TYPE_CHECKING:
    from collections.abc import Callable

    from bpmn_io.moddle.base import AnyModdleElement, ModdleElement
    from bpmn_io.moddle.descriptor_builder import PropertyDescriptor
    from bpmn_io.moddle.ns import Namespace
    from bpmn_io.moddle.registry import RegisteredPackage

__all__ = [
    "BaseElementHandler",
    "BaseHandler",
    "BodyHandler",
    "ElementHandler",
    "GenericElementHandler",
    "NoopHandler",
    "ParseContext",
    "ParseError",
    "ParseResult",
    "ParseWarning",
    "Reader",
    "ReferenceHandler",
    "ValueHandler",
    "XmlNode",
    "alias_to_name",
    "capitalize",
    "normalize_type_name",
    "prefixed_to_name",
]

#: QName validation, as upstream (`http://www.w3.org/TR/REC-xml/#NT-NameChar`).
_ID_PATTERN = re.compile(r"^([a-z][\w.-]*:)?[a-z_][\w.-]*$", re.IGNORECASE | re.ASCII)

_PREAMBLE_START_PATTERN = re.compile(r"^<\?xml ", re.IGNORECASE)

_ENCODING_PATTERN = re.compile(r' encoding="([^"]+)"', re.IGNORECASE)

_UTF8_PATTERN = re.compile(r"^utf-8$", re.IGNORECASE)


def capitalize(text: str) -> str:
    """Capitalize the first character (helper for `alias_to_name`)."""
    return text[:1].upper() + text[1:]


def alias_to_name(alias_ns: Namespace, pkg: RegisteredPackage) -> str:
    """Resolve a tag alias to its type name (lowerCase-aware)."""
    if not has_lower_case_alias(pkg):
        return alias_ns.name
    return str(alias_ns.prefix) + ":" + capitalize(alias_ns.local_name)


def prefixed_to_name(name_ns: Namespace, pkg: RegisteredPackage | None) -> str:
    """Strip a package type prefix from a type name, keeping the prefix."""
    type_prefix: str | None = None
    if pkg is not None:
        xml = pkg.get("xml")
        if isinstance(xml, dict):
            candidate = xml.get("typePrefix")
            if isinstance(candidate, str):
                type_prefix = candidate
    if type_prefix and name_ns.local_name.startswith(type_prefix):
        return str(name_ns.prefix) + ":" + name_ns.local_name[len(type_prefix) :]
    return name_ns.name


def normalize_type_name(name: str, ns_map: dict[str, str], model: Moddle) -> str:
    """Normalize an `xsi:type` / `xmi:type` value against the node's namespaces."""
    name_ns = parse_name_ns(name, ns_map.get("xmlns"))
    prefix = name_ns.prefix
    mapped = ns_map.get(prefix) if prefix is not None else None
    resolved = mapped or prefix
    # Mirror the JS template coercion of a missing prefix (`undefined:local`).
    qualified = (resolved if resolved is not None else "undefined") + ":" + name_ns.local_name
    qualified_ns = parse_name_ns(qualified)
    pkg = model.get_package(qualified_ns.prefix or "")
    return prefixed_to_name(qualified_ns, pkg)


def _with_effective_type(prop: PropertyDescriptor, type_name: str) -> PropertyDescriptor:
    """Copy a property carrying an `xsi:type` / `xmi:type` resolved effective type."""
    clone = copy.copy(prop)
    # An `assign({}, property, { effectiveType })` expando, as upstream.
    clone.__dict__["effective_type"] = type_name
    return clone


def _effective_type_name(prop: PropertyDescriptor) -> str:
    """Return the effective (serial-resolved) or declared type of a property."""
    resolved = getattr(prop, "effective_type", None)
    return resolved if isinstance(resolved, str) else prop.type


@dataclass
class ParseWarning:
    """An import warning (collected, never raised)."""

    message: str
    element: Any = None
    property: str | None = None
    value: Any = None
    error: BaseException | None = None

    def __getitem__(self, key: str) -> object:
        """Read a warning field by name (mapping-style access)."""
        if key == "message":
            return self.message
        if key == "element":
            return self.element
        if key == "property":
            return self.property
        if key == "value":
            return self.value
        if key == "error":
            return self.error
        raise KeyError(key)


@dataclass
class ParseResult:
    """The successful `from_xml` result."""

    root_element: ModdleElement | AnyModdleElement
    elements_by_id: dict[str, ModdleElement | AnyModdleElement]
    references: list[dict[str, Any]]
    warnings: list[ParseWarning]


class ParseError(ValueError):
    """A strict-mode parse failure carrying the warnings collected so far."""

    def __init__(self, message: str, warnings: list[ParseWarning] | None = None) -> None:
        """Create a parse error with its collected warnings."""
        super().__init__(message)
        self.message: str = message
        self.warnings: list[ParseWarning] = warnings if warnings is not None else []


@dataclass
class ParseContext:
    """The mutable parse state shared by every handler of one document."""

    root_handler: ElementHandler
    lax: bool = False
    elements_by_id: dict[str, ModdleElement | AnyModdleElement] = field(default_factory=dict)
    references: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[ParseWarning] = field(default_factory=list)

    def add_reference(self, reference: dict[str, Any]) -> None:
        """Record an unresolved reference."""
        self.references.append(reference)

    def add_element(self, element: ModdleElement | AnyModdleElement | None) -> None:
        """Index an element by id, rejecting missing, illegal and duplicate ids."""
        if element is None:
            msg = "expected element"
            raise ValueError(msg)
        id_property = getattr(element.descriptor_, "id_property", None)
        if id_property is None:
            return
        id_value = element.get(id_property.name)
        if not isinstance(id_value, str) or not id_value:
            return
        if not _ID_PATTERN.match(id_value):
            msg = "illegal ID <" + id_value + ">"
            raise ValueError(msg)
        if id_value in self.elements_by_id:
            msg = "duplicate ID <" + id_value + ">"
            raise ValueError(msg)
        self.elements_by_id[id_value] = element

    def add_warning(self, warning: ParseWarning) -> None:
        """Collect an import warning."""
        self.warnings.append(warning)


@dataclass
class XmlNode:
    """A decoded, namespace-normalized open tag handed to the handlers."""

    name: str
    original_name: str
    attributes: dict[str, str]
    ns: dict[str, str]


class BaseHandler:
    """Default handler: every callback is a no-op pushing no handler."""

    def handle_end(self) -> None:
        """Finish the element (default: nothing)."""

    def handle_text(self, _text: str) -> None:
        """Consume body text (default: nothing)."""

    def handle_node(self, _node: XmlNode) -> BaseHandler | None:
        """Consume a child open tag (default: push nothing)."""
        return None


class NoopHandler(BaseHandler):
    """Lax-mode sink swallowing its whole subtree."""

    def handle_node(self, _node: XmlNode) -> BaseHandler | None:
        """Stay on this sink for the subtree."""
        return self


class BodyHandler(BaseHandler):
    """Handler accumulating body text."""

    def __init__(self) -> None:
        """Create a handler with no body text yet (``undefined`` upstream)."""
        self.body: str | UndefinedType = UNDEFINED

    def handle_text(self, text: str) -> None:
        """Append body text."""
        current = self.body
        self.body = (current if isinstance(current, str) else "") + text


class ReferenceHandler(BodyHandler):
    """Handler for a reference-typed child element."""

    def __init__(self, property_desc: PropertyDescriptor, context: ParseContext) -> None:
        """Bind the handler to its property and parse context."""
        super().__init__()
        self.property = property_desc
        self.context = context
        self.element: dict[str, Any] | None = None

    def handle_node(self, _node: XmlNode) -> BaseHandler | None:
        """Create the reference placeholder, rejecting second children."""
        if self.element is not None:
            msg = "expected no sub nodes"
            raise ValueError(msg)
        self.element = self.create_reference()
        return self

    def handle_end(self) -> None:
        """Close the placeholder with the accumulated body as its id."""
        if self.element is not None:
            self.element["id"] = self.body

    def create_reference(self) -> dict[str, Any]:
        """Create the unresolved reference placeholder."""
        return {"property": self.property.ns.name, "id": ""}


class ValueHandler(BodyHandler):
    """Handler for a simple-typed child element."""

    def __init__(
        self, property_desc: PropertyDescriptor, element: ModdleElement | AnyModdleElement
    ) -> None:
        """Bind the handler to its property and owning element."""
        super().__init__()
        self.property_desc = property_desc
        self.element = element

    def handle_end(self) -> None:
        """Coerce the accumulated body and store it on the owner."""
        value = coerce_type(self.property_desc.type, self.body or "")
        if self.property_desc.is_many:
            collection = cast("list[Any]", self.element.get(self.property_desc.name))
            collection.append(value)
        else:
            self.element.set(self.property_desc.name, value)


class BaseElementHandler(BodyHandler):
    """Handler creating its element on the first open tag."""

    def __init__(self, context: ParseContext | None = None) -> None:
        """Create a handler with no element yet."""
        super().__init__()
        self.context = context
        self.element: ModdleElement | AnyModdleElement | None = None

    def require_context(self) -> ParseContext:
        """Return the bound parse context."""
        if self.context is None:
            msg = "expected context"
            raise ValueError(msg)
        return self.context

    def handle_node(self, node: XmlNode) -> BaseHandler | None:
        """Create the element once, then dispatch children."""
        if self.element is None:
            self.element = self.create_element(node)
            self.require_context().add_element(self.element)
            return self
        return self.handle_child(node)

    def create_element(self, _node: XmlNode) -> ModdleElement | AnyModdleElement:
        """Create the element for an open tag."""
        raise NotImplementedError

    def handle_child(self, _node: XmlNode) -> BaseHandler | None:
        """Dispatch a child node and attach the result."""
        raise NotImplementedError


class ElementHandler(BaseElementHandler):
    """Handler for a typed model element."""

    def __init__(self, model: Moddle, type_name: str, context: ParseContext | None = None) -> None:
        """Resolve the element class for a type name."""
        super().__init__(context)
        self.model = model
        self.type = model.get_type(type_name)

    def add_reference(self, reference: dict[str, Any]) -> None:
        """Record an unresolved reference on the parse context."""
        self.require_context().add_reference(reference)

    def handle_text(self, text: str) -> None:
        """Accumulate body text, rejecting it without a body property."""
        element = cast("ModdleElement", self.element)
        body_property = element.descriptor_.body_property
        if body_property is None:
            msg = "unexpected body text <" + text + ">"
            raise ValueError(msg)
        super().handle_text(text)

    def handle_end(self) -> None:
        """Coerce accumulated body text into the body property."""
        element = cast("ModdleElement", self.element)
        body_property = element.descriptor_.body_property
        if body_property is not None and self.body is not UNDEFINED:
            element.set(body_property.name, coerce_type(body_property.type, self.body))

    def create_element(self, node: XmlNode) -> ModdleElement:
        """Build the element, wiring attributes and attribute references."""
        context = self.require_context()
        descriptor = self.type.descriptor_
        constructor = cast("Callable[[dict[str, Any] | None], ModdleElement]", self.type)
        instance = constructor({})
        for attr_name, attr_value in node.attributes.items():
            prop = descriptor.properties_by_name.get(attr_name)
            if prop is not None and prop.is_reference:
                if not prop.is_many:
                    context.add_reference(
                        {"element": instance, "property": prop.ns.name, "id": attr_value}
                    )
                else:
                    # IDREFS: whitespace-separated reference list, kept literal.
                    for part in attr_value.split(" "):
                        context.add_reference(
                            {"element": instance, "property": prop.ns.name, "id": part}
                        )
            elif prop is not None:
                instance.set(attr_name, coerce_type(prop.type, attr_value))
            elif attr_name == "xmlns":
                instance.set(":xmlns", attr_value)
            else:
                prop_name_ns = parse_name_ns(attr_name, descriptor.ns.prefix)
                if self.model.get_package(prop_name_ns.prefix or "") is not None:
                    context.add_warning(
                        ParseWarning(
                            message="unknown attribute <" + attr_name + ">",
                            element=instance,
                            property=attr_name,
                            value=attr_value,
                        )
                    )
                instance.set(attr_name, attr_value)
        return instance

    def get_property_for_node(self, node: XmlNode) -> PropertyDescriptor:
        """Resolve the property receiving a child node (`xsi:type` aware)."""
        name_ns = parse_name_ns(node.name)
        descriptor = self.type.descriptor_
        prop = descriptor.properties_by_name.get(name_ns.name)
        if prop is not None and not prop.is_attr:
            serialization_type = get_serialization_type(prop)
            if serialization_type is not None:
                type_name = node.attributes.get(serialization_type)
                if type_name:
                    normalized = normalize_type_name(type_name, node.ns, self.model)
                    element_type = self.model.get_type(normalized)
                    return _with_effective_type(prop, element_type.descriptor_.name)
            return prop
        pkg = self.model.get_package(name_ns.prefix or "")
        if pkg is not None:
            element_type_name = alias_to_name(name_ns, pkg)
            element_type = self.model.get_type(element_type_name)
            for candidate in descriptor.properties:
                # Upstream tests `!p.isAttribute` (not `isAttr`), a field moddle
                # descriptors never define, so it is always true here.
                if (
                    not candidate.is_virtual
                    and not candidate.is_reference
                    and candidate.type in element_type.descriptor_.all_types_by_name
                ):
                    return _with_effective_type(candidate, element_type.descriptor_.name)
        else:
            for candidate in descriptor.properties:
                if not candidate.is_reference and candidate.type == "Element":
                    return candidate
        msg = "unrecognized element <" + name_ns.name + ">"
        raise ValueError(msg)

    def __repr__(self) -> str:
        """Describe the handler by its element type."""
        return "ElementDescriptor[" + self.type.descriptor_.name + "]"

    def value_handler(
        self, property_desc: PropertyDescriptor, element: ModdleElement | AnyModdleElement
    ) -> ValueHandler:
        """Create the simple-value handler for a property."""
        return ValueHandler(property_desc, element)

    def reference_handler(self, property_desc: PropertyDescriptor) -> ReferenceHandler:
        """Create the reference handler for a property."""
        return ReferenceHandler(property_desc, self.require_context())

    def handler(self, type_name: str) -> BaseElementHandler:
        """Create the child handler for a type (generic for `Element`)."""
        if type_name == "Element":
            return GenericElementHandler(self.model, type_name, self.require_context())
        return ElementHandler(self.model, type_name, self.require_context())

    def handle_child(self, node: XmlNode) -> BaseHandler | None:
        """Dispatch a child node to its property handler and attach the result."""
        prop = self.get_property_for_node(node)
        element = cast("ModdleElement | AnyModdleElement", self.element)
        type_name = _effective_type_name(prop)
        if is_simple_type(type_name):
            return self.value_handler(prop, element)
        if prop.is_reference:
            child_handler: BaseHandler | None = self.reference_handler(prop).handle_node(node)
        else:
            child_handler = self.handler(type_name).handle_node(node)
        new_element: Any = None
        if child_handler is not None:
            new_element = getattr(child_handler, "element", None)
        if new_element is not None:
            if prop.is_many:
                collection = cast("list[Any]", element.get(prop.name))
                collection.append(new_element)
            else:
                element.set(prop.name, new_element)
            if prop.is_reference:
                new_element["element"] = element
                self.require_context().add_reference(new_element)
            else:
                new_element.parent_ = element
        return child_handler


class RootElementHandler(ElementHandler):
    """Root handler validating the document element against its type."""

    def create_element(self, node: XmlNode) -> ModdleElement:
        """Validate the root tag, then build the element as usual."""
        name_ns = parse_name_ns(node.name)
        pkg = self.model.get_package(name_ns.prefix or "")
        type_name = alias_to_name(name_ns, pkg) if pkg is not None else node.name
        if type_name not in self.type.descriptor_.all_types_by_name:
            msg = "unexpected element <" + node.original_name + ">"
            raise ValueError(msg)
        return super().create_element(node)


class GenericElementHandler(BaseElementHandler):
    """Handler for untyped extension elements."""

    def __init__(
        self,
        model: Moddle,
        type_name: str,  # noqa: ARG002 - upstream signature parity (`Element`)
        context: ParseContext | None = None,
    ) -> None:
        """Create a handler bound to a model (the type name is always `Element`)."""
        super().__init__(context)
        self.model = model

    def create_element(self, node: XmlNode) -> AnyModdleElement:
        """Create a generic element with raw attributes and its namespace uri."""
        name_ns = parse_name_ns(node.name)
        uri = node.ns.get((name_ns.prefix or "") + "$uri", "")
        return self.model.create_any(node.name, uri, node.attributes)

    def handle_child(self, node: XmlNode) -> BaseHandler | None:
        """Nest every child as a generic element under `$children`."""
        child = GenericElementHandler(self.model, "Element", self.require_context())
        nested = child.handle_node(node)
        element = cast("AnyModdleElement", self.element)
        new_element = child.element
        if new_element is not None:
            children = element.get("$children")
            if children is UNDEFINED or children is None:
                children = []
                element.set("$children", children)
            cast("list[Any]", children).append(new_element)
            new_element.parent_ = element
        return nested

    def handle_end(self) -> None:
        """Store accumulated body text as `$body` (only when non-empty)."""
        element = cast("AnyModdleElement", self.element)
        if self.body:
            element.set("$body", self.body)


class Reader:
    """A reader for a meta-model."""

    def __init__(
        self,
        model_or_options: Moddle | dict[str, Any],
        lax: bool = False,  # noqa: FBT001, FBT002 - upstream `{model, lax}` options shape
    ) -> None:
        """Create a reader for a model (or `{model, lax}` options)."""
        if isinstance(model_or_options, Moddle):
            self.model = model_or_options
            self.lax = lax
        else:
            model = model_or_options.get("model")
            if not isinstance(model, Moddle):
                msg = "Reader requires a Moddle model"
                raise TypeError(msg)
            self.model = model
            self.lax = bool(model_or_options.get("lax", lax))

    def handler(self, name: str) -> RootElementHandler:
        """Create the root handler for a type name."""
        return RootElementHandler(self.model, name)

    def _prepare_handler(
        self,
        root_handler_or_name: ElementHandler | str | dict[str, Any],
        options: dict[str, Any] | None,
    ) -> tuple[ElementHandler, dict[str, Any]]:
        """Resolve the root handler and effective call options."""
        opts: dict[str, Any] = dict(options) if options is not None else {}
        if isinstance(root_handler_or_name, ElementHandler):
            return root_handler_or_name, opts
        if isinstance(root_handler_or_name, str):
            return self.handler(root_handler_or_name), opts
        if isinstance(root_handler_or_name, dict):
            nested = root_handler_or_name.get("rootHandler")
            merged = {**root_handler_or_name, **opts}
            if isinstance(nested, ElementHandler):
                return nested, merged
            if isinstance(nested, str):
                return self.handler(nested), merged
        msg = "expected root handler or type name"
        raise TypeError(msg)

    def from_xml(
        self,
        xml: str,
        root_handler_or_name: ElementHandler | str | dict[str, Any],
        options: dict[str, Any] | None = None,
    ) -> ParseResult:
        """Parse XML into a moddle tree (sync; raises `ParseError` in strict mode)."""
        root_handler, opts = self._prepare_handler(root_handler_or_name, options)
        lax = bool(opts.get("lax", self.lax))
        context = ParseContext(root_handler=root_handler, lax=lax)
        root_handler.context = context
        parser = Parser({"proxy": True})
        parser.ns(_build_uri_map(self.model))
        stack: list[Any] = [root_handler]
        _wire_parser(parser, stack, context, lax)
        try:
            parser.parse(xml)
            _resolve_references(context)
        except ParseError:
            raise
        except Exception as err:
            msg = str(err)
            raise ParseError(msg, context.warnings) from err
        root_element = root_handler.element
        if root_element is None:
            msg = "failed to parse document as <" + root_handler.type.descriptor_.name + ">"
            raise ParseError(msg, context.warnings)
        return ParseResult(
            root_element=root_element,
            elements_by_id=context.elements_by_id,
            references=context.references,
            warnings=context.warnings,
        )


def _wire_parser(
    parser: Parser,
    stack: list[Any],
    context: ParseContext,
    lax: bool,  # noqa: FBT001 - threaded parse flag, as upstream
) -> None:
    """Register the reader callbacks on a namespace-configured parser."""

    def _on_open_tag(
        obj: Any,  # noqa: ANN401 - saxen proxy element has no public type
        decode_str: Callable[[str], str],
        _self_closing: bool,  # noqa: FBT001 - parser-fixed callback arity
        get_context: Callable[[], dict[str, Any]],
    ) -> None:
        """Decode an open tag into a node and dispatch it."""
        raw_attrs: Any = obj.attrs or {}
        node = XmlNode(
            name=obj.name,
            original_name=obj.originalName,
            attributes={key: decode_str(value) for key, value in raw_attrs.items()},
            ns=obj.ns,
        )
        _handle_open(node, get_context, stack, context, lax)

    def _on_question(question: str, _get_context: Callable[[], dict[str, Any]]) -> None:
        """Inspect an XML preamble for unsupported encodings."""
        _handle_question(question, context)

    def _on_close() -> None:
        """Pop the stack and finish the element."""
        _handle_close(stack)

    def _on_cdata(text: str, get_context: Callable[[], dict[str, Any]]) -> None:
        """Feed raw CDATA to the top handler, warning on failure."""
        _handle_cdata(text, get_context, stack, context)

    def _on_text(
        text: str,
        decode_entities_fn: Callable[[str], str],
        get_context: Callable[[], dict[str, Any]],
    ) -> None:
        """Feed decoded, non-blank text to the top handler."""
        _handle_text(decode_entities_fn(text), get_context, stack, context)

    def _on_error(err: BaseException, get_context: Callable[[], dict[str, Any]]) -> None:
        """Raise a strict-mode failure as `ParseError`."""
        _handle_error(err, get_context, context, lax=False)

    def _on_warning(err: BaseException, get_context: Callable[[], dict[str, Any]]) -> None:
        """Collect a failure as a warning."""
        _handle_warning(err, get_context, context)

    parser.on("openTag", _on_open_tag).on("question", _on_question).on("closeTag", _on_close).on(
        "cdata", _on_cdata
    ).on("text", _on_text).on("error", _on_error).on("warn", _on_warning)


def _handle_error(
    err: BaseException,
    get_context: Callable[[], dict[str, Any]],
    context: ParseContext,
    lax: bool,  # noqa: FBT001
) -> bool:
    """Format a parse failure; warn in lax mode, raise `ParseError` otherwise."""
    info = get_context()
    data = info["data"]
    if data.startswith("<") and " " in data:
        data = data[: data.index(" ")] + ">"
    message = (
        "unparsable content "
        + (data + " " if data else "")
        + "detected\n\tline: "
        + str(info["line"])
        + "\n\tcolumn: "
        + str(info["column"])
        + "\n\tnested error: "
        + str(err)
    )
    if lax:
        context.add_warning(ParseWarning(message=message, error=err))
        return True
    raise ParseError(message, context.warnings)


def _handle_warning(
    err: BaseException, get_context: Callable[[], dict[str, Any]], context: ParseContext
) -> bool:
    """Collect a failure as a warning (lax-style error handling)."""
    return _handle_error(err, get_context, context, lax=True)


def _resolve_references(context: ParseContext) -> None:
    """Replace reference placeholders with their targets, warning on misses."""
    for ref in context.references:
        element = ref["element"]
        target = context.elements_by_id.get(ref["id"])
        prop = element.descriptor_.properties_by_name[ref["property"]]
        if target is None:
            context.add_warning(
                ParseWarning(
                    message="unresolved reference <" + str(ref["id"]) + ">",
                    element=element,
                    property=str(ref["property"]),
                    value=ref["id"],
                )
            )
        if prop.is_many:
            _resolve_many(element, prop.name, ref, target)
        else:
            # Unresolved single references unset the property (upstream sets
            # ``undefined``); only UNDEFINED unsets, None would store null.
            element.set(prop.name, target if target is not None else UNDEFINED)


def _resolve_many(
    element: ModdleElement | AnyModdleElement,
    name: str,
    ref: dict[str, Any],
    target: ModdleElement | AnyModdleElement | None,
) -> None:
    """Splice out or replace one collection placeholder (identity-matched)."""
    collection = cast("list[Any]", element.get(name))
    idx = len(collection)
    for pos, item in enumerate(collection):
        if item is ref:
            idx = pos
            break
    if target is None:
        if idx < len(collection):
            del collection[idx]
    elif idx < len(collection):
        collection[idx] = target
    else:
        collection.append(target)


def _handle_close(stack: list[Any]) -> None:
    """Pop the stack and finish the element."""
    stack.pop().handle_end()


def _handle_question(question: str, context: ParseContext) -> None:
    """Warn on non-UTF-8 XML preambles."""
    if not _PREAMBLE_START_PATTERN.match(question):
        return
    match = _ENCODING_PATTERN.search(question)
    encoding = match.group(1) if match else None
    if not encoding or _UTF8_PATTERN.match(encoding):
        return
    context.add_warning(
        ParseWarning(
            message="unsupported document encoding <" + encoding + ">, falling back to UTF-8"
        )
    )


def _handle_open(
    node: XmlNode,
    get_context: Callable[[], dict[str, Any]],
    stack: list[Any],
    context: ParseContext,
    lax: bool,  # noqa: FBT001
) -> None:
    """Push the child handler for a node, degrading to a sink in lax mode."""
    try:
        stack.append(stack[-1].handle_node(node))
    except Exception as err:  # noqa: BLE001 - every node failure funnels here, as upstream
        if _handle_error(err, get_context, context, lax):
            stack.append(NoopHandler())


def _handle_cdata(
    text: str,
    get_context: Callable[[], dict[str, Any]],
    stack: list[Any],
    context: ParseContext,
) -> None:
    """Feed raw CDATA to the top handler, warning on failure."""
    try:
        stack[-1].handle_text(text)
    except Exception as err:  # noqa: BLE001 - text failures are warnings, as upstream
        _handle_warning(err, get_context, context)


def _handle_text(
    text: str,
    get_context: Callable[[], dict[str, Any]],
    stack: list[Any],
    context: ParseContext,
) -> None:
    """Feed decoded, non-blank text to the top handler."""
    if not text.strip():
        return
    _handle_cdata(text, get_context, stack, context)


def _build_uri_map(model: Moddle) -> dict[str, str]:
    """Map namespace uris to prefixes (config, then `xsi`/`xml` defaults, then packages)."""
    configured: dict[str, str] = dict(model.config.get("nsMap") or {})
    defaults = {uri: prefix for prefix, uri in DEFAULT_NS_MAP.items()}
    packaged: dict[str, str] = {pkg["uri"]: pkg["prefix"] for pkg in model.get_packages()}
    return {**configured, **defaults, **packaged}
