# Safety and diagnostic adapter in front of the literal XML reader.
"""F1 XML boundary adapter (contract f1-extensions/1).

Enforces safety and reports native losses without changing the literal
``moddle_xml``/``saxen`` ports:

- input-encoding registry with strict decoding;
- raw and decoded size checks before tokenization;
- ``DOCTYPE``/``ENTITY`` refusal and wire-shape checks before native
  construction (raw scan);
- limit counting through the pinned tokenizer event API (explicit
  stacks, no retained token stream);
- unchanged native construction, then typed diagnostics with RFC 6901
  pointers for every native warning or loss, capped at 1000 warnings
  plus one shared truncation diagnostic.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Final

from bpmn_io._js import UNDEFINED
from bpmn_io.codec._model import (
    CodecResult,
    Diagnostic,
    NativeElement,
    build_model,
    escape_pointer,
    resolve_limits,
    utf16_len,
)
from bpmn_io.codec._scan import ScanEvent, scan_source

if TYPE_CHECKING:
    from bpmn_io.bpmn_moddle.bpmn_moddle import BpmnModdle
    from bpmn_io.moddle.descriptor_builder import PropertyDescriptor
    from bpmn_io.moddle.registry import PackageDef
    from bpmn_io.moddle_xml.read import ParseResult, ParseWarning

__all__ = [
    "ENCODING_NAMES",
    "check_count_limits",
    "classify_native_message",
    "decode_source",
    "element_pointer",
    "map_native_warning",
    "parse_xml",
]

#: Declared encodings accepted by the registry (lowercased lookup).
#: ``utf-8`` means strict UTF-8 decoding; ``latin`` means the direct
#: byte to U+0000..U+00FF mapping (0x80-0x9F land on U+0080..U+009F).
ENCODING_NAMES: Final[dict[str, str]] = {
    "utf-8": "utf-8",
    "utf8": "utf-8",
    "ascii": "utf-8",
    "us-ascii": "utf-8",
    "iso-8859-1": "latin",
    "iso8859-1": "latin",
    "iso88591": "latin",
    "latin1": "latin",
    "latin-1": "latin",
}

#: XML declaration encoding probe (ASCII-only declaration scan).
_DECLARATION_RE: Final = re.compile(r"<\?xml\s[^?]*?encoding\s*=\s*[\"']([^\"']+)[\"']")

#: Byte opener of an XML declaration (the scan starts here, never mid-input).
_DECL_OPEN: Final = b"<?xml"

#: Byte terminator of an XML declaration.
_DECL_CLOSE: Final = b"?>"

#: UTF-8 byte-order mark skipped before the declaration opener.
_UTF8_BOM: Final = b"\xef\xbb\xbf"


def _declared_encoding(source: bytes) -> str | None:
    """Return the encoding declared by ``source``, or None when absent.

    The declaration is analyzed integrally within the input bound (opener at
    the start modulo a BOM, through its terminator) instead of a fixed head
    window, so padding inside ``<?xml ... ?>`` cannot hide an unregistered
    name. Anything unparseable fails open to the default (the native reader
    decides malformed inputs).
    """
    text = source.removeprefix(_UTF8_BOM)
    if not text.startswith(_DECL_OPEN):
        return None
    end = text.find(_DECL_CLOSE, len(_DECL_OPEN))
    if end < 0:
        return None
    match = _DECLARATION_RE.search(text[: end + len(_DECL_CLOSE)].decode("latin1"))
    if match is None:
        return None
    return match.group(1).strip().lower()


#: Native truncation marker (reused MAX_WARNINGS semantics, never edited).
_TRUNCATION_MESSAGE: Final = "too many warnings, further warnings truncated"

#: Detail strings stay bounded even for hostile tag payloads.
_MAX_DETAIL: Final = 4096


class _RefusalError(Exception):
    """Internal limit-trip signal carrying its diagnostic."""

    def __init__(self, diagnostic: Diagnostic) -> None:
        """Bind the refusal to its diagnostic."""
        super().__init__(diagnostic.code)
        self.diagnostic = diagnostic


def _refusal(code: str, detail: str) -> Diagnostic:
    """Build one bounded refusal diagnostic."""
    return Diagnostic(code=code, path=None, target=None, detail=detail[:_MAX_DETAIL])


def _decode_declared(source: bytes, declared: str) -> tuple[str | None, list[Diagnostic]]:
    """Decode ``source`` under one registry encoding name."""
    kind = ENCODING_NAMES.get(declared)
    if kind is None:
        return None, [
            _refusal("unsupported-encoding", f"unsupported declared encoding <{declared}>")
        ]
    if kind == "latin":
        return source.decode("latin1"), []
    try:
        return source.decode("utf-8"), []
    except UnicodeDecodeError as err:
        return None, [_refusal("invalid-encoding", f"bytes are not valid for <{declared}>: {err}")]


def decode_source(source: bytes | str) -> tuple[str | None, list[Diagnostic]]:
    """Decode ``source`` through the input-encoding registry.

    Returns ``(text, [])`` on success or ``(None, [diagnostic])`` carrying
    ``unsupported-encoding``/``invalid-encoding``.
    """
    if isinstance(source, str):
        return source, []
    declared = _declared_encoding(source)
    if declared is None:
        try:
            return source.decode("utf-8"), []
        except UnicodeDecodeError as err:
            return None, [_refusal("invalid-encoding", f"bytes are not valid UTF-8: {err}")]
    return _decode_declared(source, declared)


class _Counter:
    """Explicit-stack counting state for one tokenizer walk."""

    def __init__(self, limits: dict[str, int]) -> None:
        """Bind the walk limits."""
        self.limits = limits
        self.stack: list[str] = []
        self.elements = 0

    def open_tag(
        self,
        name: str,
        raw_attrs: dict[str, str],
        decode: Any,  # noqa: ANN401 - saxen decode callback has no public type
    ) -> None:
        """Count one open tag against depth, total and attribute limits."""
        self.elements += 1
        if self.elements > self.limits["xml-elements"]:
            raise _RefusalError(
                _refusal(
                    "xml-element-count-limit",
                    f"element count exceeds {self.limits['xml-elements']} at <{name}>",
                )
            )
        self.stack.append(name)
        if len(self.stack) > self.limits["xml-depth"]:
            raise _RefusalError(
                _refusal("xml-depth-limit", f"depth exceeds {self.limits['xml-depth']} at <{name}>")
            )
        if len(raw_attrs) > self.limits["xml-attributes-per-element"]:
            limit = self.limits["xml-attributes-per-element"]
            raise _RefusalError(
                _refusal(
                    "xml-attribute-count-limit",
                    f"attribute count exceeds {limit} at <{name}>",
                )
            )
        _check_attr_sizes(name, raw_attrs, decode, self.limits)


def _check_attr_sizes(
    name: str,
    raw_attrs: dict[str, str],
    decode: Any,  # noqa: ANN401 - saxen decode callback has no public type
    limits: dict[str, int],
) -> None:
    """Enforce name/value UTF-16 limits on one tag's attributes."""
    for key, value in raw_attrs.items():
        if utf16_len(str(key)) > limits["xml-attr-name-utf16"]:
            raise _RefusalError(
                _refusal(
                    "xml-attribute-length-limit",
                    f"attribute name exceeds the UTF-16 limit at <{name}>",
                )
            )
        decoded = decode(value) if callable(decode) else value
        if utf16_len(str(decoded)) > limits["xml-attr-value-utf16"]:
            raise _RefusalError(
                _refusal(
                    "xml-attribute-length-limit",
                    f"attribute value exceeds the UTF-16 limit at <{name}>",
                )
            )


def check_count_limits(text: str, limits: dict[str, int]) -> list[Diagnostic]:
    """Count elements, depth and attribute sizes via the pinned tokenizer.

    Uses only the event API with an explicit stack; retains no token
    stream. Returns limit diagnostics in document order (at most one:
    the first violation wins).
    """
    from bpmn_io.saxen import Parser  # noqa: PLC0415

    counter = _Counter(limits)

    def _on_open(
        obj: Any,  # noqa: ANN401 - saxen proxy element has no public type
        decode_str: Any,  # noqa: ANN401 - saxen decode callback has no public type
        _self_closing: bool,  # noqa: FBT001 - parser-fixed callback arity
        _get_context: Any,  # noqa: ANN401 - saxen context callback has no public type
    ) -> None:
        """Count one open tag."""
        counter.open_tag(str(obj.name), dict(obj.attrs or {}), decode_str)

    def _on_close(*_args: Any) -> None:  # noqa: ANN401 - parser-fixed callback arity
        """Pop one nesting level."""
        if counter.stack:
            counter.stack.pop()

    parser = Parser({"proxy": True})
    parser.on("openTag", _on_open).on("closeTag", _on_close)
    try:
        parser.parse(text)
    except _RefusalError as refusal:
        return [refusal.diagnostic]
    except Exception:  # noqa: BLE001 - malformed input is the native reader's call
        return []
    return []


#: Ordered (fragment, code) rules mapping native messages to closed codes.
#: Earlier rules win, implementing the intra-node priority over the
#: ``unparsable content`` wrapper. Fragments match the nested error when
#: one is present.
_NATIVE_RULES: Final = (
    ("missing namespace for prefix", "unbound-prefix"),
    ("already defined", "duplicate-attribute"),
    ("unknown type", "invalid-xsi-type"),
    ("unknown attribute", "moddle-warning"),
    ("unresolved reference", "moddle-warning"),
    ("unsupported document encoding", "moddle-warning"),
    ("missing namespace information", "moddle-warning"),
    ("unexpected element", "moddle-content-dropped"),
    ("unrecognized element", "moddle-content-dropped"),
    ("unexpected body text", "moddle-content-dropped"),
    ("expected no sub nodes", "moddle-content-dropped"),
    ("illegal ID", "moddle-content-dropped"),
    ("duplicate ID", "moddle-content-dropped"),
)


def classify_native_message(message: str) -> str:
    """Map one native warning/error message to its closed diagnostic code.

    Follows ``contracts/f1-extensions/1/diagnostics.json`` nativeMappings:
    the nested error wins over the ``unparsable content`` wrapper by
    intra-node priority; anything unrecognized fails closed to
    ``moddle-unmapped-diagnostic``.
    """
    inner = message
    if "nested error:" in message:
        inner = message.split("nested error:", 1)[1]
    for fragment, code in _NATIVE_RULES:
        if fragment not in inner:
            continue
        if fragment == "already defined" and ("<xmlns" in inner or "xmlns:" in inner):
            return "duplicate-namespace"
        return code
    if "failed to parse document" in message:
        return "xml-invalid"
    if _TRUNCATION_MESSAGE in message:
        return "moddle-warning-truncated"
    if message.startswith("unparsable content"):
        return "moddle-content-dropped"
    return "moddle-unmapped-diagnostic"


def element_target(element: NativeElement) -> str | None:
    """Return the id target of ``element`` (typed ids only, else None)."""
    descriptor = getattr(element, "descriptor_", None)
    id_property = getattr(descriptor, "id_property", None)
    if id_property is None:
        return None
    value = vars(element).get(id_property.name)
    return value if isinstance(value, str) and value else None


def element_pointer(element: NativeElement, prop_name: str | None = None) -> str | None:
    """Build the RFC 6901 pointer of ``element`` through parent links.

    Segments follow containment identity (typed property names with
    many-indexes, generic ``$children`` indexes). Unattached or
    unresolvable ancestry yields None instead of a fabricated path.
    """
    segments: list[str] = []
    if prop_name is not None:
        segments.append(prop_name)
    current = element
    seen: set[int] = set()
    while True:
        if id(current) in seen:
            return None
        seen.add(id(current))
        parent = getattr(current, "parent_", None)
        if parent is None or parent is UNDEFINED or not hasattr(parent, "__dict__"):
            segments.reverse()
            return "/" + "/".join(segments) if segments else ""
        segment = _child_segment(parent, current)
        if segment is None:
            return None
        segments.append(segment)
        current = parent


def _child_segment(parent: NativeElement, child: NativeElement) -> str | None:
    """Return the pointer segment locating ``child`` under ``parent``."""
    raw = vars(parent)
    children = raw.get("$children")
    if isinstance(children, list):
        for index, item in enumerate(children):
            if item is child:
                return "$children/" + str(index)
    descriptor = getattr(parent, "descriptor_", None)
    properties = getattr(descriptor, "properties", None)
    if properties is None:
        return None
    for prop in properties:
        segment = _slot_segment(raw, prop, child)
        if segment is not None:
            return segment
    return None


def _slot_segment(
    raw: dict[str, Any], prop: PropertyDescriptor, child: NativeElement
) -> str | None:
    """Return the pointer segment locating ``child`` in one property slot."""
    value = raw.get(prop.name, UNDEFINED)
    if value is UNDEFINED:
        return None
    if value is child:
        return escape_pointer(prop.name)
    if isinstance(value, list):
        for index, item in enumerate(value):
            if item is child:
                return escape_pointer(prop.name) + "/" + str(index)
    return None


def map_native_warning(warning: ParseWarning) -> Diagnostic | None:
    """Map one native warning to its typed diagnostic (None: truncation marker)."""
    message = str(warning.message)
    if _TRUNCATION_MESSAGE in message:
        return None
    code = classify_native_message(message)
    element = warning.element
    path: str | None = None
    target: str | None = None
    if element is not None and hasattr(element, "parent_"):
        target = element_target(element)
        prop = warning.property
        prop_name = prop if isinstance(prop, str) and prop else None
        path = element_pointer(element, prop_name)
    return Diagnostic(
        code=code,
        path=path,
        target=target,
        detail=message[:_MAX_DETAIL],
    )


def cap_diagnostics(diagnostics: list[Diagnostic], *, truncated: bool) -> list[Diagnostic]:
    """Cap diagnostics at 1000 warnings plus one truncation diagnostic."""
    if len(diagnostics) <= 1000 and not truncated:
        return diagnostics
    kept = diagnostics[:1000]
    omitted = diagnostics[1000] if len(diagnostics) > 1000 else None
    kept.append(
        Diagnostic(
            code="moddle-warning-truncated",
            path=omitted.path if omitted is not None else None,
            target=None,
            detail="further warnings truncated at the 1000-warning cap",
        )
    )
    return kept


def _fail(diagnostic: Diagnostic) -> CodecResult:
    """Wrap one refusal diagnostic in a failed result."""
    return CodecResult(ok=False, value=None, diagnostics=(diagnostic,))


def _check_input_sizes(
    source: bytes | str, text: str, resolved: dict[str, int]
) -> Diagnostic | None:
    """Enforce raw and decoded size bounds before tokenization."""
    raw_size = len(source) if isinstance(source, bytes) else len(source.encode("utf-8"))
    if raw_size > resolved["xml-input-bytes"]:
        return _refusal(
            "xml-input-size-limit",
            f"raw input size {raw_size} exceeds {resolved['xml-input-bytes']}",
        )
    decoded_size = len(text.encode("utf-8"))
    if decoded_size > resolved["xml-decoded-bytes"]:
        return _refusal(
            "xml-input-size-limit",
            f"decoded size {decoded_size} exceeds {resolved['xml-decoded-bytes']}",
        )
    return None


def _construct(model: BpmnModdle, text: str) -> tuple[ParseResult | None, CodecResult | None]:
    """Run unchanged native construction, mapping fatal errors."""
    from bpmn_io.moddle_xml.read import ParseError  # noqa: PLC0415

    try:
        return model.from_xml(text), None
    except ParseError as err:
        failure = _fail(
            Diagnostic(
                code=classify_native_message(str(err.message)),
                path=None,
                target=None,
                detail=str(err.message)[:_MAX_DETAIL],
            )
        )
        return None, failure


def _decode_and_size(
    source: bytes | str, resolved: dict[str, int]
) -> tuple[str | None, CodecResult | None]:
    """Decode ``source`` and enforce size bounds (early refusal or text)."""
    text, decode_diagnostics = decode_source(source)
    if text is None:
        return None, CodecResult(ok=False, value=None, diagnostics=tuple(decode_diagnostics))
    text = text.removeprefix("\ufeff")
    size_refusal = _check_input_sizes(source, text, resolved)
    if size_refusal is not None:
        return None, _fail(size_refusal)
    return text, None


def parse_xml(
    source: bytes | str,
    *,
    descriptors: dict[str, PackageDef] | None = None,
    limits: dict[str, int] | None = None,
) -> CodecResult:
    """Parse XML into a native tree through the safety boundary.

    Refusals (encoding, size, raw wire-shape, count limits, descriptor
    identity, fatal native errors) return ``ok=False``; native warnings
    and losses return ``ok=True`` with typed diagnostics.
    """
    resolved = resolve_limits(limits)
    text, early = _decode_and_size(source, resolved)
    if early is not None:
        return early
    assert text is not None  # noqa: S101 - early refusal covers the None case
    scan = scan_source(text)
    if scan.diagnostics:
        return CodecResult(ok=False, value=None, diagnostics=tuple(scan.diagnostics))
    count_diagnostics = check_count_limits(text, resolved)
    if count_diagnostics:
        return CodecResult(ok=False, value=None, diagnostics=tuple(count_diagnostics))
    model, model_diagnostic = build_model(descriptors)
    if model is None:
        return CodecResult(
            ok=False,
            value=None,
            diagnostics=(model_diagnostic,),  # type: ignore[arg-type]
        )
    result, failure = _construct(model, text)
    if failure is not None:
        return failure
    assert result is not None  # noqa: S101 - construction either returns or fails
    mapped: list[Diagnostic] = [_event_diagnostic(event) for event in scan.events]
    truncated = False
    for warning in result.warnings:
        diagnostic = map_native_warning(warning)
        if diagnostic is None:
            truncated = True
            continue
        mapped.append(diagnostic)
    return CodecResult(
        ok=True,
        value=result.root_element,
        diagnostics=tuple(cap_diagnostics(mapped, truncated=truncated)),
    )


def _event_diagnostic(event: ScanEvent) -> Diagnostic:
    """Map one raw-scan loss observation to its typed diagnostic.

    Scan observations precede native warnings deterministically: input
    order first, native collection order second.
    """
    kind = event.kind
    detail = f"{event.detail} (f1-xml-source/1@{event.line}:{event.col}:{kind})"
    if kind in ("comment", "pi"):
        return Diagnostic(code="moddle-content-dropped", path=None, target=None, detail=detail)
    return Diagnostic(code="moddle-content-normalized", path=None, target=None, detail=detail)
