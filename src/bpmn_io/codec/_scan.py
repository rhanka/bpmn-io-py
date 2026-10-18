# Bounded raw XML source scan (F1 boundary adapter, first stage).
"""Bounded raw scan of XML source text before native model construction.

Detects refusal-class constructs without building any model node:

- ``DOCTYPE`` and ``ENTITY`` declarations (refused outright);
- named character references outside the natively decoded set;
- colliding foreign attribute names (closed reserved-name list);
- duplicate expanded attributes and duplicate namespace declarations;
- malformed QNames.

The scan retains nothing: no token stream, no text payload, no
reconstruction metadata. It tracks line/column coordinates for
diagnostics and a namespace scope stack for prefix resolution. Tags the
scanner cannot parse are skipped (fail-open); the native reader decides
them. Counting limits (elements, depth, attribute sizes) are enforced by
the pinned tokenizer walk in :mod:`bpmn_io.codec.xml_boundary`, not here.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from typing import Final

from bpmn_io.codec._model import (
    Diagnostic,
    escape_pointer,
    is_valid_qname,
)

__all__ = ["RawScan", "ScanEvent", "scan_source"]

#: Case-insensitive DOCTYPE opener (XML keywords are uppercase; variants refuse alike).
_DOCTYPE_RE: Final = re.compile(r"<!DOCTYPE\b", re.IGNORECASE)

#: ENTITY declarations, inside or outside a DOCTYPE (standalone isolates the code).
_ENTITY_DECL_RE: Final = re.compile(r"<!ENTITY\b", re.IGNORECASE)

#: One ``&...;`` reference in markup or data.
_ENTITY_REF_RE: Final = re.compile(r"&#([0-9]+);|&#[xX]([0-9a-fA-F]+);|&([A-Za-z0-9_]+);")

#: References decoded natively (five predefined plus five uppercase variants).
_KNOWN_ENTITIES: Final = frozenset(
    {"amp", "apos", "gt", "lt", "quot", "AMP", "APOS", "GT", "LT", "QUOT"}
)

#: XML namespace of the reserved ``xml`` prefix.
_XML_URI: Final = "http://www.w3.org/XML/1998/namespace"

#: Failsafe numeric-reference digit bound when the interpreter disables its
#: own ``int`` string-conversion ceiling (``get_int_max_str_digits() == 0``):
#: the default ceiling, so overlong references still refuse before allocation.
_FAILSAFE_REF_DIGITS: Final = 4300

#: Detail prefix cap for overlong references (details never carry megabytes).
_MAX_REF_DETAIL: Final = 64


def _digit_cap() -> int:
    """Return the exact digit-run bound the native ``int()`` enforces here."""
    cap = sys.get_int_max_str_digits()
    return cap if cap > 0 else _FAILSAFE_REF_DIGITS


#: Reserved names refused as full foreign attribute names (closed union).
_RESERVED: Final = frozenset(
    {
        "$attrs",
        "$body",
        "$children",
        "$descriptor",
        "$model",
        "$parent",
        "$type",
        "__class__",
        "__contains__",
        "__delattr__",
        "__dict__",
        "__dir__",
        "__doc__",
        "__eq__",
        "__format__",
        "__ge__",
        "__getattribute__",
        "__getitem__",
        "__gt__",
        "__hash__",
        "__init__",
        "__init_subclass__",
        "__le__",
        "__lt__",
        "__module__",
        "__ne__",
        "__new__",
        "__proto__",
        "__reduce__",
        "__reduce_ex__",
        "__repr__",
        "__setattr__",
        "__setitem__",
        "__sizeof__",
        "__str__",
        "__subclasshook__",
        "__weakref__",
        "attrs_",
        "constructor",
        "descriptor_",
        "get",
        "hasOwnProperty",
        "has_type",
        "instance_of",
        "isPrototypeOf",
        "model_",
        "parent_",
        "propertyIsEnumerable",
        "prototype",
        "set",
        "toJSON",
        "toLocaleString",
        "toString",
        "to_canonical_dict",
        "type_",
        "valueOf",
    }
)


@dataclass
class ScanEvent:
    """One dropped or normalized source span (comment, PI, CDATA, truncation)."""

    kind: str
    line: int
    col: int
    detail: str


@dataclass
class RawScan:
    """The raw scan outcome: refusal diagnostics plus loss observations."""

    diagnostics: list[Diagnostic] = field(default_factory=list)
    events: list[ScanEvent] = field(default_factory=list)


def _coord(detail: str, line: int, col: int, kind: str) -> str:
    """Format an ``f1-xml-source/1`` coordinate detail string."""
    return f"{detail} (f1-xml-source/1@{line}:{col}:{kind})"


def _check_entity_refs(
    chunk: str, line: int, col: int, out: list[Diagnostic], events: list[ScanEvent]
) -> None:
    """Refuse unknown named references; record truncating numeric ones.

    Digit runs beyond the bounded conversion refuse with
    ``xml-entity-reference-unsupported`` before native construction: the
    literal reader port would raise ``ValueError`` on them, so letting them
    through would trade a typed refusal for an uncontracted exception.
    """
    for match in _ENTITY_REF_RE.finditer(chunk):
        decimal, hex_digits, named = match.group(1, 2, 3)
        if named is not None:
            if named in _KNOWN_ENTITIES:
                continue
            out.append(
                Diagnostic(
                    code="xml-entity-reference-unsupported",
                    path=None,
                    target=None,
                    detail=_coord(f"undeclared named reference <&{named};>", line, col, "entity"),
                )
            )
            return
        digits = decimal if decimal is not None else hex_digits
        assert digits is not None  # noqa: S101 - the pattern always binds one group
        if len(digits) > _digit_cap():
            shown = match.group(0)[:_MAX_REF_DETAIL]
            out.append(
                Diagnostic(
                    code="xml-entity-reference-unsupported",
                    path=None,
                    target=None,
                    detail=_coord(
                        f"overlong numeric reference <{shown}...> exceeds the bounded conversion",
                        line,
                        col,
                        "entity",
                    ),
                )
            )
            return
        code = int(decimal) if decimal is not None else int(hex_digits, 16)
        if code > 0xFFFF:
            events.append(
                ScanEvent(
                    kind="numeric-truncation",
                    line=line,
                    col=col,
                    detail=f"numeric reference <{match.group(0)}> truncates modulo 0x10000",
                )
            )


def _split_qname(name: str) -> tuple[str | None, str] | None:
    """Split ``prefix:local`` (None prefix when unprefixed); None when malformed."""
    if not is_valid_qname(name):
        return None
    if ":" in name:
        prefix, _, local = name.partition(":")
        return prefix, local
    return None, name


def _skip_ws(text: str, i: int, end: int) -> int:
    """Skip XML whitespace at ``i`` (bounded caller-side scan helper)."""
    while i < end and text[i] in " \t\r\n":
        i += 1
    return i


def _parse_attr_value(text: str, i: int, end: int) -> tuple[str, int] | None:
    """Parse one quoted attribute value at ``i`` (past the ``=``)."""
    i = _skip_ws(text, i, end)
    if i >= end or text[i] not in "\"'":
        return None
    quote = text[i]
    close = text.find(quote, i + 1)
    if close < 0:
        return None
    return text[i + 1 : close], close + 1


def _parse_attr(text: str, i: int, end: int) -> tuple[str, str, int] | None:
    """Parse one ``name[=value]`` attribute at ``i`` (bare names take ``""``)."""
    attr_start = i
    while i < end and text[i] not in " \t\r\n=/>":
        i += 1
    attr = text[attr_start:i]
    if not attr:
        return None
    i = _skip_ws(text, i, end)
    value = ""
    if i < end and text[i] == "=":
        outcome = _parse_attr_value(text, i + 1, end)
        if outcome is None:
            return None
        value, i = outcome
    return attr, value, i


def _parse_tag_attrs(
    text: str, name: str, i: int, end: int
) -> tuple[str, list[tuple[str, str]], bool, int] | None:
    """Parse the attribute run of one open tag (quote-aware, fail-open)."""
    attrs: list[tuple[str, str]] = []
    while i < end:
        i = _skip_ws(text, i, end)
        if i >= end:
            return None
        char = text[i]
        if char == ">":
            return name, attrs, False, i + 1
        if char == "/" and i + 1 < end and text[i + 1] == ">":
            return name, attrs, True, i + 2
        if char in "/>":
            return None
        parsed = _parse_attr(text, i, end)
        if parsed is None:
            return None
        attr, value, i = parsed
        attrs.append((attr, value))
    return None


def _parse_tag(text: str, start: int) -> tuple[str, list[tuple[str, str]], bool, int] | None:
    """Parse ``<name attrs>`` at ``start``; None when the tag is not parseable.

    Returns ``(name, [(attr, value)], self_closing, end_index)``. Quote-aware:
    ``>`` inside quoted values never ends the tag. Bare attribute names take
    the empty value. Anything else abandons the tag (fail-open).
    """
    end = len(text)
    i = _skip_ws(text, start + 1, end)
    name_start = i
    while i < end and text[i] not in " \t\r\n/>":
        i += 1
    name = text[name_start:i]
    if not name or name.startswith(("!", "?")):
        return None
    return _parse_tag_attrs(text, name, i, end)


class _Scanner:
    """Bounded single-pass scan state (no retained token stream or payload)."""

    def __init__(self, text: str) -> None:
        """Bind the scanner to its decoded source text."""
        self.text = text
        self.out: list[Diagnostic] = []
        self.events: list[ScanEvent] = []
        self.scopes: list[dict[str, str]] = [{}]
        self.line = 1
        self.line_start = 0
        self.tag_line = 0
        self.tag_col = 0

    def run(self) -> RawScan:
        """Walk the source once, collecting refusals and loss observations."""
        if self._refused_marker():
            return RawScan(diagnostics=self.out, events=self.events)
        i = 0
        end = len(self.text)
        while i < end and not self.out:
            stepped = self._step(i, end)
            if stepped is None:
                break
            i = stepped
        return RawScan(diagnostics=self.out, events=self.events)

    def _at(self, index: int) -> tuple[int, int]:
        """Compute the 1-based (line, column) of ``index``."""
        return self.line, index - self.line_start + 1

    def _coord_of(self, index: int) -> tuple[int, int]:
        """Compute the 1-based (line, column) of ``index`` from scratch."""
        line = self.text.count("\n", 0, index) + 1
        col = index - (self.text.rfind("\n", 0, index) + 1) + 1
        return line, col

    def _refuse(self, code: str, detail: str, line: int, col: int, kind: str) -> None:
        """Record one refusal diagnostic with its source coordinate."""
        self.out.append(
            Diagnostic(
                code=code,
                path=None,
                target=None,
                detail=_coord(detail, line, col, kind),
            )
        )

    def _refused_marker(self) -> bool:
        """Refuse DOCTYPE/ENTITY markers before any model node exists."""
        match = _DOCTYPE_RE.search(self.text)
        if match is not None:
            line, col = self._coord_of(match.start())
            self._refuse(
                "xml-doctype-forbidden", "DOCTYPE declaration refused", line, col, "doctype"
            )
            return True
        match = _ENTITY_DECL_RE.search(self.text)
        if match is not None:
            line, col = self._coord_of(match.start())
            self._refuse(
                "xml-entity-declaration-forbidden",
                "ENTITY declaration refused",
                line,
                col,
                "entity",
            )
            return True
        return False

    def _advance(self, start: int, next_i: int) -> int:
        """Account newlines over one consumed span, then continue past it."""
        skipped = self.text[start:next_i]
        self.line += skipped.count("\n")
        if "\n" in skipped:
            self.line_start = start + skipped.rfind("\n") + 1
        return next_i

    def _step(self, i: int, end: int) -> int | None:
        """Advance one span (newline, text or markup); None stops the walk."""
        char = self.text[i]
        if char == "\n":
            self.line += 1
            self.line_start = i + 1
            return i + 1
        if char != "<":
            return self._text(i, end)
        return self._markup(i)

    def _markup(self, i: int) -> int | None:
        """Advance one ``<``-led span; None stops the walk (fail-open)."""
        if self.text.startswith("<!--", i):
            return self._comment(i)
        if self.text.startswith("<?", i):
            return self._instruction(i)
        if self.text.startswith("<![CDATA[", i):
            return self._cdata(i)
        if self.text.startswith("</", i):
            return self._close_tag(i)
        return self._open_tag(i)

    def _text(self, i: int, end: int) -> int:
        """Consume one text run, refusing unknown named references."""
        seg_end = self.text.find("<", i)
        if seg_end < 0:
            seg_end = end
        chunk = self.text[i:seg_end]
        if chunk.strip():
            line, col = self._at(i)
            _check_entity_refs(chunk, line, col, self.out, self.events)
        newlines = chunk.count("\n")
        if newlines:
            self.line += newlines
            self.line_start = i + chunk.rfind("\n") + 1
        return seg_end

    def _comment(self, i: int) -> int | None:
        """Record one dropped comment; None when unterminated (fail-open)."""
        close = self.text.find("-->", i + 4)
        if close < 0:
            return None
        line, col = self._at(i)
        self.events.append(ScanEvent(kind="comment", line=line, col=col, detail="comment dropped"))
        return self._advance(i, close + 3)

    def _instruction(self, i: int) -> int | None:
        """Record one dropped processing instruction (never the declaration)."""
        close = self.text.find("?>", i + 2)
        if close < 0:
            return None
        if not self.text.startswith("<?xml ", i) and not self.text.startswith("<?XML ", i):
            line, col = self._at(i)
            self.events.append(
                ScanEvent(kind="pi", line=line, col=col, detail="processing instruction dropped")
            )
        return self._advance(i, close + 2)

    def _cdata(self, i: int) -> int | None:
        """Record one erased CDATA boundary; None when unterminated."""
        close = self.text.find("]]>", i + 9)
        if close < 0:
            return None
        line, col = self._at(i)
        self.events.append(
            ScanEvent(kind="cdata-boundary", line=line, col=col, detail="CDATA boundary erased")
        )
        return self._advance(i, close + 3)

    def _close_tag(self, i: int) -> int | None:
        """Pop one namespace scope; None when unterminated (fail-open)."""
        close = self.text.find(">", i + 2)
        if close < 0:
            return None
        if len(self.scopes) > 1:
            self.scopes.pop()
        return self._advance(i, close + 1)

    def _refuse_here(self, code: str, detail: str) -> None:
        """Record one refusal diagnostic at the current tag coordinate."""
        self._refuse(code, detail, self.tag_line, self.tag_col, "declaration")

    def _open_tag(self, i: int) -> int | None:
        """Check one open tag; unparseable tags advance one char (fail-open)."""
        parsed = _parse_tag(self.text, i)
        if parsed is None:
            return i + 1
        name, attrs, self_closing, next_i = parsed
        self.tag_line, self.tag_col = self._at(i)
        advanced = self._advance(i, next_i)
        split = _split_qname(name)
        if split is None:
            self._refuse_here("malformed-qname", f"malformed element name <{name}>")
            return None
        scope = self._extend_scope(attrs)
        if scope is None or not self._check_attrs(name, attrs, scope):
            return None
        prefix, _local = split
        if prefix is not None and prefix not in ("xml", "xmlns") and prefix not in scope:
            self._refuse_here("unbound-prefix", f"unbound element prefix <{prefix}> on <{name}>")
            return None
        if not self_closing:
            self.scopes.append(scope)
        return advanced

    def _extend_scope(self, attrs: list[tuple[str, str]]) -> dict[str, str] | None:
        """Copy the scope with this tag's declarations; None on refusal."""
        scope = dict(self.scopes[-1])
        for attr, value in attrs:
            if attr == "xmlns":
                scope[""] = value
            elif attr.startswith("xmlns:"):
                declared = attr[len("xmlns:") :]
                if not is_valid_qname("p:" + declared):
                    self._refuse_here("malformed-qname", f"malformed declaration <{attr}>")
                    return None
                scope[declared] = value
        return scope

    def _check_attrs(self, name: str, attrs: list[tuple[str, str]], scope: dict[str, str]) -> bool:
        """Run per-attribute checks in document order; False on refusal."""
        seen: set[tuple[str, str]] = set()
        seen_decls: set[str] = set()
        for attr, value in attrs:
            _check_entity_refs(value, self.tag_line, self.tag_col, self.out, self.events)
            if self.out:
                return False
            if attr == "xmlns" or attr.startswith("xmlns:"):
                if not self._check_decl(attr, value, seen_decls):
                    return False
                continue
            if not self._check_attr(name, attr, scope, seen):
                return False
        return True

    def _check_decl(self, attr: str, value: str, seen_decls: set[str]) -> bool:
        """Check one namespace declaration; False on refusal."""
        key = "" if attr == "xmlns" else attr[len("xmlns:") :]
        if key in seen_decls:
            self._refuse_here("duplicate-namespace", f"duplicate declaration <{attr}>")
            return False
        seen_decls.add(key)
        if key == "xml" and value != _XML_URI:
            self._refuse_here("invalid-namespace", "invalid xml prefix binding")
            return False
        return True

    def _check_attr(
        self, name: str, attr: str, scope: dict[str, str], seen: set[tuple[str, str]]
    ) -> bool:
        """Check one foreign attribute; False on refusal."""
        if attr in _RESERVED:
            self.out.append(
                Diagnostic(
                    code="reserved-name",
                    path="/" + escape_pointer(name),
                    target=None,
                    detail=_coord(
                        f"reserved attribute <{attr}> on <{name}>",
                        self.tag_line,
                        self.tag_col,
                        "declaration",
                    ),
                )
            )
            return False
        attr_split = _split_qname(attr)
        if attr_split is None:
            self._refuse_here("malformed-qname", f"malformed attribute name <{attr}>")
            return False
        prefix, local = attr_split
        if prefix is not None and prefix not in ("xml", "xmlns") and prefix not in scope:
            self._refuse_here("unbound-prefix", f"unbound prefix <{prefix}> on <{attr}>")
            return False
        if prefix == "xml":
            uri = _XML_URI
        elif prefix is not None:
            uri = scope.get(prefix, "")
        else:
            uri = ""
        if (uri, local) in seen:
            code = "duplicate-namespace" if prefix == "xmlns" else "duplicate-attribute"
            self._refuse_here(code, f"duplicate attribute <{attr}>")
            return False
        seen.add((uri, local))
        return True


def scan_source(text: str) -> RawScan:
    """Run the bounded raw scan over decoded XML ``text``.

    Returns refusal diagnostics in document order plus loss observations
    (comments, processing instructions, CDATA spans, truncating numeric
    references). The scan never raises on adversarial input;
    untokenizable spans are left to the native reader.
    """
    return _Scanner(text).run()
