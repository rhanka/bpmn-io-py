"""Lenient SAX parser transposed from saxen ``lib/parser.js`` (Lot 3, MIT).

Same event model (``openTag``/``closeTag``/``text``/``cdata``/``comment``/``question``/
``attention``/``error``/``warn``), same error and warning texts, same ``{data, line,
column}`` positions, same namespace normalization (configured prefixes, anonymous
``ns<N>`` allocation with per-run counter, prototype-safe matrices), same streaming
remainder buffering, and same attribute leniency. Python ``None`` is JS ``null``;
programmer errors raise ``TypeError``/``ValueError``/``RuntimeError`` with the upstream
messages, while parse-time failures travel through ``onError`` (default: raise) and
are returned by ``parse``/``end``.

Deviations from upstream (all outside the exercised paths): the proxy element is a
live view with the same lazy ``attrs``/``ns`` semantics, cloned via ``dict(element)``
(``Object.assign`` equivalent); handler ``getContext`` is a bound method reading the
live cursors, identical when called synchronously as upstream callers do; ``for .. in``
iteration order over plain data is insertion order on both sides.
"""

from __future__ import annotations

import inspect
import math
import re
from typing import TYPE_CHECKING, Any

from bpmn_io.saxen.decode import decode_entities

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

__all__ = ["ParseError", "Parser"]

_NON_WHITESPACE_OUTSIDE_ROOT_NODE = "non-whitespace outside of root node"

_SPLITS_RE = re.compile(r"(\r\n|\r|\n)")


class _AbortError(Exception):
    """Internal control flow: abort the parse run, optionally with a remainder."""

    def __init__(self, remainder: str | None = None) -> None:
        super().__init__(remainder)
        self.remainder = remainder


class ParseError(Exception):
    """Parse-time failure (upstream ``Error``); via ``onError`` or ``parse``/``end``."""


def _char_code(text: str, index: int) -> float:
    """Return the char code at ``index``, ``NaN`` past the end (``charCodeAt``)."""
    return ord(text[index]) if index < len(text) else math.nan


def _is_space(code: float) -> bool:
    r"""Return true for the upstream whitespace set (space + ``\t\n\v\f\r``)."""
    return code == 32 or 8 < code < 14


def _substring(text: str, start: int, end: int) -> str:
    """Emulate ``String.substring`` (swapped, clamped arguments)."""
    low, high = (start, end) if start <= end else (end, start)
    return text[max(low, 0) : max(high, 0)]


#: Characters stripped by ``String.prototype.trim`` (WhiteSpace + LineTerminator,
#: notably U+FEFF which Python's ``str.strip`` keeps).
_JS_TRIM_CHARS = (
    "\t\n\x0b\x0c\r "
    "\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007"
    "\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
)


def _js_trim(text: str) -> str:
    """Emulate ``String.prototype.trim`` for root-level blank checks."""
    return text.strip(_JS_TRIM_CHARS)


def _set_ns_entry(
    ns_matrix: dict[str, str], changes: dict[str, str | None], key: str, value: str
) -> None:
    """Set a namespace matrix entry, recording the previous value for restoration."""
    if key not in changes:
        changes[key] = ns_matrix.get(key)
    ns_matrix[key] = value


def _restore_ns_matrix(ns_matrix: dict[str, str], changes: dict[str, str | None]) -> None:
    """Restore a namespace matrix from a change log (tolerant delete, as upstream)."""
    for key, value in changes.items():
        if value is None:
            ns_matrix.pop(key, None)
        else:
            ns_matrix[key] = value


def _uri_prefix(prefix: str) -> str:
    """Return the matrix key holding a prefix namespace URI."""
    return prefix + "$uri"


def _throw(err: Exception, _context: object) -> None:
    """Default error handler: raise the parse error."""
    raise err


_POSITIONAL_KINDS = frozenset(
    {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD},
)


def _adapt_arity(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``fn`` dropping trailing args beyond its arity (JS call tolerance).

    Upstream listeners declare any parameter prefix (``function(el)``); extra
    positional arguments are dropped, mirroring JavaScript's calling convention.
    """
    try:
        params = list(inspect.signature(fn).parameters.values())
    except (TypeError, ValueError):
        return fn
    if any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in params):
        return fn
    positional = [p for p in params if p.kind in _POSITIONAL_KINDS]
    count = len(positional)

    def call(*args: object) -> object:
        """Invoke ``fn`` with exactly ``count`` positional arguments.

        Extra arguments are dropped and missing ones arrive as ``None``,
        mirroring JavaScript's calling convention (extras ignored, missing
        parameters ``undefined``).
        """
        if len(args) > count:
            args = args[:count]
        elif len(args) < count:
            args = args + (None,) * (count - len(args))
        return fn(*args)

    return call


def _build_ns_matrix(ns_uri_to_prefix: dict[str, str]) -> dict[str, str]:
    """Build the initial namespace matrix from a ``{uri: prefix}`` map."""
    ns_matrix: dict[str, str] = {}
    for uri, prefix in ns_uri_to_prefix.items():
        ns_matrix[prefix] = prefix
        ns_matrix[_uri_prefix(prefix)] = uri
    return ns_matrix


class _ProxyElement:
    """Lazy element view passed to handlers in proxy mode (one per parse run)."""

    _KEYS = ("name", "originalName", "attrs", "ns")

    def __init__(self, parser: Parser) -> None:
        self._parser = parser

    @property
    def name(self) -> str:
        """Return the normalized element name."""
        return self._parser.element_name

    @property
    def originalName(self) -> str:  # noqa: N802 - upstream member name
        """Return the raw element name."""
        return self._parser.raw_element_name

    @property
    def attrs(self) -> dict[str, str]:
        """Return the lazily parsed attributes."""
        return self._parser.get_attrs()

    @property
    def ns(self) -> dict[str, str]:
        """Return the cached namespace snapshot."""
        return self._parser.ns_snapshot()

    def keys(self) -> list[str]:
        """Return the clonable member names (``dict(element)`` support)."""
        return list(self._KEYS)

    def __getitem__(self, key: str) -> object:
        """Read one member by name (``dict(element)`` support)."""
        if key == "name":
            return self.name
        if key == "originalName":
            return self.originalName
        if key == "attrs":
            return self.attrs
        if key == "ns":
            return self.ns
        raise KeyError(key)


_EVENT_SLOTS = {
    "openTag": "_on_open_tag",
    "text": "_on_text",
    "closeTag": "_on_close_tag",
    "error": "_on_error",
    "warn": "_on_warning",
    "cdata": "_on_cdata",
    "attention": "_on_attention",
    "question": "_on_question",
    "comment": "_on_comment",
}


class Parser:
    """SAX parser with streaming support (transposed ``saxen`` constructor)."""

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        """Create a parser (``proxy`` option enables the element view)."""
        proxy: Any = options.get("proxy") if options else False
        self._proxy = bool(proxy)
        self._on_text: Callable[..., Any] | None = None
        self._on_open_tag: Callable[..., Any] | None = None
        self._on_close_tag: Callable[..., Any] | None = None
        self._on_cdata: Callable[..., Any] | None = None
        self._on_error: Callable[..., Any] = _throw
        self._on_warning: Callable[..., Any] | None = None
        self._on_comment: Callable[..., Any] | None = None
        self._on_question: Callable[..., Any] | None = None
        self._on_attention: Callable[..., Any] | None = None
        self._is_namespace = False
        self._ns_uri_to_prefix: dict[str, str] = {}
        self._maybe_ns = False
        self._xml = ""
        self._i = 0
        self._j = 0
        self._streaming = False
        self._el_name_cache: dict[str, str] | None = None
        self._ns_changes: dict[str, str | None] | None = None
        self._ns_snapshot: dict[str, str] | None = None
        self._anonymous_count = 0
        self._attrs_string = ""
        self._attrs_start = 0
        self._cached_attrs: dict[str, str] | None = None
        self._element_name = ""
        self._raw_element_name = ""
        self._ga_default_alias: str | None = None
        self._element_proxy: _ProxyElement | None = None
        self.reset_state()

    def _reset_run(self) -> None:
        """Reset the per-parse-run state (mirrors the upstream ``parse`` locals)."""
        self._el_name_cache = None
        self._ns_changes = None
        self._ns_snapshot = None
        self._anonymous_count = 0
        self._attrs_string = ""
        self._attrs_start = 0
        self._cached_attrs = None
        self._element_name = ""
        self._raw_element_name = ""
        self._ga_default_alias = None
        self._element_proxy = _ProxyElement(self) if self._proxy else None

    def reset_state(self) -> None:
        """Reset the parser state before a (streamed) parse run."""
        self._ns_changes_stack: list[dict[str, str | None] | None] | None = (
            [] if self._is_namespace else None
        )
        self._ns_matrix: dict[str, str] | None = (
            _build_ns_matrix(self._ns_uri_to_prefix) if self._is_namespace else None
        )
        self._node_stack: list[str] = []
        self._parse_stop = False
        self._return_error: Exception | None = None
        self._root_found = False
        self._leftover = ""

    def on(self, name: str, cb: object) -> Parser:
        """Register a parse listener; chainable (``openTag``/``text``/...)."""
        if not callable(cb):
            msg = "required args <name, cb>"
            raise TypeError(msg)
        try:
            slot = _EVENT_SLOTS[name]
        except KeyError:
            msg = f"unsupported event: {name}"
            raise ValueError(msg) from None
        setattr(self, slot, _adapt_arity(cb))
        return self

    def ns(self, ns_map: Mapping[str, str] | None = None) -> Parser:
        """Set the namespace to prefix mapping; chainable."""
        if ns_map is None:
            ns_map = {}
        if not isinstance(ns_map, dict):
            msg = "required args <nsMap={}>"
            raise TypeError(msg)
        self._is_namespace = True
        self._ns_uri_to_prefix = dict(ns_map)
        return self

    def stop(self) -> None:
        """Stop parsing (honored after the running handler returns)."""
        self._parse_stop = True

    def parse(self, xml: object) -> Exception | None:
        """Parse a complete XML string; return the error, if not thrown."""
        if not isinstance(xml, str):
            msg = "required args <xml=string>"
            raise TypeError(msg)
        if self._streaming:
            msg = "parse during stream; call end() first"
            raise RuntimeError(msg)
        self.reset_state()
        self._parse(xml, streaming=False)
        self._parse_stop = False
        return self._return_error

    def write(self, xml: object) -> Parser:
        """Write the next chunk of a streamed XML string; chainable."""
        if not isinstance(xml, str):
            msg = "required args <xml=string>"
            raise TypeError(msg)
        if not self._streaming:
            self.reset_state()
            self._streaming = True
        if self._return_error is None:
            self._leftover = self._parse(self._leftover + xml, streaming=True) or ""
        return self

    def end(self) -> Exception | None:
        """Finish a streamed parse; return the error, if not thrown."""
        if not self._streaming:
            self.reset_state()
        self._streaming = False
        if self._return_error is None:
            self._parse(self._leftover)
        self._leftover = ""
        self._parse_stop = False
        return self._return_error

    def _check_stop(self) -> None:
        """Abort the parse run when ``stop()`` was called from a handler."""
        if self._parse_stop:
            raise _AbortError

    def _handle_error(self, err: object) -> None:
        """Record a parse error and notify ``onError`` (default: raise)."""
        if not isinstance(err, Exception):
            err = ParseError(err)
        self._return_error = err
        self._on_error(err, self._get_context)

    def _handle_warning(self, message: str) -> None:
        """Record a parse warning and notify ``onWarning``, if registered."""
        if self._on_warning is None:
            return
        self._on_warning(Exception(message), self._get_context)

    def _get_context(self) -> dict[str, Any]:
        """Return the ``{data, line, column}`` context at the live cursors."""
        xml, i, j = self._xml, self._i, self._j
        line = 0
        column = 0
        start_of_line = 0
        end_of_line = j
        while i >= start_of_line:
            match = _SPLITS_RE.search(xml, start_of_line)
            if match is None:
                break
            end_of_line = len(match.group(1)) + match.start()
            if end_of_line > i:
                break
            line += 1
            start_of_line = end_of_line
        if i == -1:
            column = end_of_line
            data = xml[j:] if j >= 0 else xml
        elif j == 0:
            column = 0
            data = _substring(xml, j, i)
        else:
            column = i - start_of_line
            data = xml[i:] if j == -1 else _substring(xml, i, j + 1)
        return {"data": data, "line": line, "column": column}

    @property
    def element_name(self) -> str:
        """Return the normalized name of the tag being dispatched."""
        return self._element_name

    @property
    def raw_element_name(self) -> str:
        """Return the raw name of the tag being dispatched."""
        return self._raw_element_name

    def ns_snapshot(self) -> dict[str, str]:
        """Return the cached namespace snapshot (invalidated on matrix change)."""
        if self._ns_snapshot is None:
            self._ns_snapshot = dict(self._ns_matrix or {})
        return self._ns_snapshot

    def get_attrs(self) -> dict[str, str]:
        """Parse and return the attributes of the tag being dispatched."""
        if self._cached_attrs is not None:
            return self._cached_attrs
        s = self._attrs_string
        n = len(s)
        self._ga_seen: set[str] = set()
        self._ga_attrs: dict[str, str] = {}
        self._ga_attr_list: list[str] = []
        self._ga_default_alias = None
        if self._is_namespace:
            self._ga_default_alias = (self._ns_matrix or {}).get("xmlns")
        value: str | None = None
        i = self._attrs_start
        while i < n:
            w = _char_code(s, i)
            if _is_space(w):
                i += 1
                continue
            if (w < 65 or w > 122 or 90 < w < 97) and w not in {95, 58}:
                self._handle_warning("illegal first char attribute name")
                skip = True
            else:
                skip = False
            name, value, skip, i = self._read_attr(s, i, n, value, skip=skip)
            if name is None:
                i += 1
                continue
            i, skip = self._finish_attr(s, i, n, name, value, skip=skip)
            i += 1
        for k in range(0, len(self._ga_attr_list), 2):
            name = self._normalize_attr_name(self._ga_attr_list[k], self._ga_default_alias)
            if name is None:
                continue
            self._ga_attrs[name] = self._ga_attr_list[k + 1]
        self._cached_attrs = self._ga_attrs
        return self._ga_attrs

    def _read_attr(
        self, s: str, i: int, n: int, value: str | None, *, skip: bool
    ) -> tuple[str | None, str | None, bool, int]:
        """Scan one attribute name and value.

        Return ``(name, value, skip, i)`` where ``i`` is the value-end position;
        callers account the outer loop increment explicitly, mirroring the upstream
        ``for`` loop. A ``None`` name abandons the attribute (no record).
        """
        name, skip, j = self._scan_attr_name(s, i, n, skip=skip)
        if name is None:
            return None, value, skip, j
        value, skip, j = self._scan_attr_value(s, j, n, value, skip=skip)
        if name == "xmlns:xml" and value != "http://www.w3.org/XML/1998/namespace":
            self._handle_error("illegal value of xmlns:xml")
        return name, value, skip, j

    def _scan_attr_name(
        self, s: str, i: int, n: int, *, skip: bool
    ) -> tuple[str | None, bool, int]:
        """Scan one attribute name; return ``(name_or_None, skip, j)``."""
        j = i + 1
        while j < n:
            w = _char_code(s, j)
            if 96 < w < 123 or 64 < w < 91 or 47 < w < 59 or w in {46, 45, 95}:
                j += 1
                continue
            if _is_space(w):
                self._handle_warning("missing attribute value")
                return None, skip, j
            if w == 61:
                break
            self._handle_warning("illegal attribute name char")
            skip = True
            j += 1
        name = s[i:j]
        if name == "xmlns:xmlns":
            self._handle_warning("illegal declaration of xmlns")
            skip = True
        return name, skip, j

    def _find_close_quote(self, s: str, i: int, quote: str, other: str) -> tuple[int, bool]:
        """Find a value closing quote, warning on quote mismatch."""
        j = s.find(quote, i)
        if j != -1:
            return j, False
        j = s.find(other, i)
        if j != -1:
            self._handle_warning("attribute value quote missmatch")
            return j, True
        return -1, False

    def _scan_attr_value(
        self, s: str, j: int, n: int, value: str | None, *, skip: bool
    ) -> tuple[str | None, bool, int]:
        """Scan one attribute value; return ``(value_or_None, skip, j)``."""
        w = _char_code(s, j + 1)
        if w in {34, 39}:
            quote, other = ('"', "'") if w == 34 else ("'", '"')
            i = j + 2
            j, mismatch = self._find_close_quote(s, i, quote, other)
            if j == -1:
                self._handle_warning("missing closing quotes")
                return None, True, n
            if mismatch:
                return value, True, j
            return s[i:j], skip, j
        self._handle_warning("missing attribute value quotes")
        j += 1
        while j < n and not _is_space(_char_code(s, j + 1)):
            j += 1
        return None, True, j

    def _finish_attr(  # noqa: PLR0913 - upstream attr pipeline carries (s, j, n, name, value) + skip
        self, s: str, j: int, n: int, name: str, value: str | None, *, skip: bool = False
    ) -> tuple[int, bool]:
        """Consume trailing space, dedupe and record one attribute.

        Return ``(i, skip)`` where ``i`` is the pre-increment cursor (callers
        add the outer loop step, mirroring the upstream ``for`` loop). The
        trailing scan always runs — even for dropped attributes, as upstream —
        and a first illegal character drops the attribute (``skip``), exactly
        like the upstream ``skipAttr`` flag.
        """
        anchor = j
        while j + 1 < n:
            w = _char_code(s, j + 1)
            if _is_space(w):
                break
            if j == anchor:
                self._handle_warning("illegal character after attribute end")
                skip = True
            j += 1
        i = j + 1
        if skip:
            return i, skip
        if name in self._ga_seen:
            self._handle_warning(f"attribute <{name}> already defined")
            return i, skip
        self._ga_seen.add(name)
        if not self._is_namespace:
            self._ga_attrs[name] = value or ""
            return i, skip
        if self._maybe_ns:
            self._declare_ns(name, value or "")
            return i, skip
        normalized = self._normalize_attr_name(name, self._ga_default_alias)
        if normalized is None:
            return i, skip
        self._ga_attrs[normalized] = value or ""
        return i, skip

    def _declare_ns(self, name: str, value: str) -> None:
        """Handle one attribute in eager namespace mode (declaration or deferral)."""
        ns_matrix = self._ns_matrix
        newalias: str | None = None
        if name == "xmlns":
            newalias = "xmlns"
            ns_uri = decode_entities(value)
        elif name.startswith("xmlns:"):
            newalias = name[6:]
            ns_uri = decode_entities(value)
        if newalias is not None and ns_matrix is not None:
            alias = self._ns_uri_to_prefix.get(ns_uri)
            if alias is None:
                if newalias == "xmlns" or (
                    _uri_prefix(newalias) in ns_matrix
                    and ns_matrix[_uri_prefix(newalias)] != ns_uri
                ):
                    alias = self._alloc_anonymous(ns_matrix)
                else:
                    alias = newalias
                self._ns_uri_to_prefix[ns_uri] = alias
            if ns_matrix.get(newalias) != alias:
                if self._ns_changes is None:
                    self._ns_changes = {}
                _set_ns_entry(ns_matrix, self._ns_changes, newalias, alias)
                if newalias == "xmlns":
                    self._ga_default_alias = alias
                    _set_ns_entry(ns_matrix, self._ns_changes, _uri_prefix(alias), ns_uri)
                _set_ns_entry(ns_matrix, self._ns_changes, _uri_prefix(newalias), ns_uri)
                self._el_name_cache = None
                self._ns_snapshot = None
            # expose xmlns(:alias)="..." in attributes, as upstream
            self._ga_attrs[name] = value
        else:
            self._ga_attr_list.append(name)
            self._ga_attr_list.append(value)

    def _alloc_anonymous(self, ns_matrix: dict[str, str]) -> str:
        """Allocate the next free ``ns<N>`` prefix."""
        while True:
            alias = f"ns{self._anonymous_count}"
            self._anonymous_count += 1
            if alias not in ns_matrix:
                return alias

    def _normalize_attr_name(self, name: str, default_alias: str | None) -> str | None:
        """Normalize one attribute name, warning on missing namespace prefixes."""
        w = name.find(":")
        if w == -1:
            return name
        ns_name = (self._ns_matrix or {}).get(name[:w])
        if not ns_name:
            self._handle_warning(f"missing namespace for prefix <{name[:w]}>")
            return None
        if default_alias == ns_name:
            return name[w + 1 :]
        return ns_name + name[w:]

    def _normalize_element_name(self, raw: str) -> str:
        """Normalize one element name, aborting on missing namespace prefixes."""
        w = raw.find(":")
        if w == -1:
            xmlns = (self._ns_matrix or {}).get("xmlns")
            if xmlns is None:
                return raw
            return xmlns + ":" + raw
        ns_name = (self._ns_matrix or {}).get(raw[:w])
        if not ns_name:
            self._handle_error(f"missing namespace on <{raw}>")
            raise _AbortError
        return ns_name + raw[w:]

    def _apply_ns(self, raw: str) -> None:
        """Normalize the tag name through the memoized namespace matrix."""
        if self._el_name_cache is None:
            self._el_name_cache = {}
        cached = self._el_name_cache.get(raw)
        if cached is not None:
            self._element_name = cached
            return
        self._element_name = self._normalize_element_name(raw)
        self._el_name_cache[raw] = self._element_name

    def _parse(self, xml: str, *, streaming: bool = False) -> str | None:
        """Run the main scan loop; return the streaming remainder, if any."""
        self._xml = xml
        self._reset_run()
        self._i = 0
        self._j = 0
        try:
            while self._j != -1:
                self._parse_step(streaming=streaming)
        except _AbortError as abort:
            return abort.remainder
        return None

    def _parse_step(self, *, streaming: bool) -> None:
        """Parse the next text segment and tag starting at the cursor."""
        xml = self._xml
        j = self._j
        i = j if _char_code(xml, j) == 60 else xml.find("<", j)
        if i == -1:
            self._parse_eof(streaming=streaming)
            return
        self._i = i
        if not self._root_found:
            self._root_found = True
        if j != i:
            self._parse_text(j, i)
        w = _char_code(xml, i + 1)
        if w == 33:
            if self._parse_bang(i, streaming=streaming):
                return
        elif w == 63:
            self._parse_question(i, streaming=streaming)
            return
        end = self._scan_tag_end(i)
        if end is None:
            if streaming:
                raise _AbortError(xml[i:])
            self._j = -1
            self._handle_error("unclosed tag")
            raise _AbortError
        self._j = end
        self._dispatch_tag(i)
        self._j += 1

    def _parse_eof(self, *, streaming: bool) -> None:
        """Handle the end of input; always aborts the parse run."""
        xml = self._xml
        j = self._j
        if streaming:
            raise _AbortError(xml[j:])
        if self._node_stack:
            self._i = -1
            self._handle_error("unexpected end of file")
            raise _AbortError
        if not self._root_found:
            self._i = -1
            self._handle_error("missing start tag")
            raise _AbortError
        if self._root_found and j < len(xml) and _js_trim(xml[j:]):
            self._i = -1
            self._handle_warning(_NON_WHITESPACE_OUTSIDE_ROOT_NODE)
        raise _AbortError

    def _parse_text(self, j: int, i: int) -> None:
        """Handle the text segment between the cursor and the next tag."""
        xml = self._xml
        if not self._node_stack:
            if _js_trim(xml[j:i]):
                self._handle_warning(_NON_WHITESPACE_OUTSIDE_ROOT_NODE)
                self._check_stop()
            return
        if self._on_text is not None:
            self._on_text(xml[j:i], decode_entities, self._get_context)
            self._check_stop()

    def _parse_bang(self, i: int, *, streaming: bool) -> bool:
        """Handle a ``<!`` section; return True when consumed, else tag-scan."""
        xml = self._xml
        if _char_code(xml, i + 2) == 91 and xml[i + 3 : i + 9] == "CDATA[":
            self._parse_cdata(i, streaming=streaming)
            return True
        if xml[i + 2 : i + 4] == "--":
            self._parse_comment(i, streaming=streaming)
            return True
        return False

    def _parse_cdata(self, i: int, *, streaming: bool) -> None:
        """Handle a CDATA section."""
        xml = self._xml
        j = xml.find("]]>", i)
        if j == -1:
            if streaming:
                raise _AbortError(xml[i:])
            self._j = j
            self._handle_error("unclosed cdata")
            raise _AbortError
        self._j = j
        if self._on_cdata is not None:
            self._on_cdata(xml[i + 9 : j], self._get_context)
            self._check_stop()
        self._j = j + 3

    def _parse_comment(self, i: int, *, streaming: bool) -> None:
        """Handle a comment section."""
        xml = self._xml
        j = xml.find("-->", i)
        if j == -1:
            if streaming:
                raise _AbortError(xml[i:])
            self._j = j
            self._handle_error("unclosed comment")
            raise _AbortError
        self._j = j
        if self._on_comment is not None:
            self._on_comment(xml[i + 4 : j], decode_entities, self._get_context)
            self._check_stop()
        self._j = j + 3

    def _parse_question(self, i: int, *, streaming: bool) -> None:
        """Handle a question section."""
        xml = self._xml
        j = xml.find("?>", i)
        if j == -1:
            if streaming:
                raise _AbortError(xml[i:])
            self._j = j
            self._handle_error("unclosed question")
            raise _AbortError
        self._j = j
        if self._on_question is not None:
            self._on_question(xml[i : j + 2], self._get_context)
            self._check_stop()
        self._j = j + 2

    def _scan_tag_end(self, i: int) -> int | None:
        """Scan a tag end, skipping quoted strings; None when incomplete."""
        xml = self._xml
        x = i + 1
        while True:
            v = _char_code(xml, x)
            if math.isnan(v):
                return None
            if v == 34:
                q = xml.find('"', x + 1)
                x = q if q != -1 else x
            elif v == 39:
                q = xml.find("'", x + 1)
                x = q if q != -1 else x
            elif v == 62:
                return x
            x += 1

    def _dispatch_tag(self, i: int) -> None:
        """Dispatch one scanned tag (attention, close, or open)."""
        xml = self._xml
        j = self._j
        self._cached_attrs = {}
        if _char_code(xml, i + 1) == 33:
            if self._on_attention is not None:
                self._on_attention(xml[i : j + 1], decode_entities, self._get_context)
                self._check_stop()
            return
        if _char_code(xml, i + 1) == 47:
            self._close_tag(i, j)
            return
        self._open_tag(i, j)

    def _close_tag(self, i: int, j: int) -> None:
        """Validate and dispatch one closing tag."""
        xml = self._xml
        stack = self._node_stack
        if not stack:
            self._handle_error("missing open tag")
            raise _AbortError
        raw = stack.pop()
        q = i + 2 + len(raw)
        if xml[i + 2 : q] != raw:
            self._handle_error("closing tag mismatch")
            raise _AbortError
        while q < j:
            if not _is_space(_char_code(xml, q)):
                self._handle_error("close tag")
                raise _AbortError
            q += 1
        self._raw_element_name = raw
        if self._is_namespace:
            self._apply_ns(raw)
        else:
            self._element_name = raw
        self._emit_close(tag_start=False)

    def _read_open_name(self, i: int, j: int) -> tuple[str, bool, int, str]:
        """Read an opening tag head; return ``(raw, tag_end, q, x)``."""
        xml = self._xml
        if xml[j - 1] == "/":
            x = xml[i + 1 : j - 1]
            tag_end = True
        else:
            x = xml[i + 1 : j]
            tag_end = False
        w = _char_code(x, 0)
        if not (96 < w < 123 or 64 < w < 91 or w in {95, 58}):
            self._handle_error("illegal first char nodeName")
            raise _AbortError
        q = 1
        y = len(x)
        raw: str | None = None
        while q < y:
            w = _char_code(x, q)
            if 96 < w < 123 or 64 < w < 91 or 47 < w < 59 or w in (45, 95, 46):
                q += 1
                continue
            if _is_space(w):
                raw = x[:q]
                self._cached_attrs = None
                break
            self._handle_error("invalid nodeName")
            raise _AbortError
        if raw is None:
            raw = x
        return raw, tag_end, q, x

    def _open_tag(self, i: int, j: int) -> None:
        """Validate, namespace and dispatch one opening tag."""
        raw, tag_end, q, x = self._read_open_name(i, j)
        if not tag_end:
            self._node_stack.append(raw)
        self._raw_element_name = raw
        if self._is_namespace:
            self._ns_changes = None
            if self._cached_attrs is None and "xmlns" in x[q:]:
                self._maybe_ns = True
                self._attrs_start = q
                self._attrs_string = x
                self.get_attrs()
                self._maybe_ns = False
            if not tag_end and self._ns_changes_stack is not None:
                self._ns_changes_stack.append(self._ns_changes)
            self._apply_ns(raw)
        else:
            self._element_name = raw
        self._emit_open(q, x, tag_end=tag_end)
        if tag_end:
            self._emit_close(tag_start=True)

    def _emit_open(self, q: int, x: str, *, tag_end: bool) -> None:
        """Dispatch the open-tag event."""
        self._attrs_start = q
        self._attrs_string = x
        if self._on_open_tag is not None:
            if self._proxy:
                self._on_open_tag(self._element_proxy, decode_entities, tag_end, self._get_context)
            else:
                self._on_open_tag(
                    self._element_name,
                    self.get_attrs,
                    decode_entities,
                    tag_end,
                    self._get_context,
                )
            self._check_stop()

    def _emit_close(self, *, tag_start: bool) -> None:
        """Dispatch the close-tag event and restore the namespace matrix."""
        if self._on_close_tag is not None:
            target = self._element_proxy if self._proxy else self._element_name
            self._on_close_tag(target, decode_entities, tag_start, self._get_context)
            self._check_stop()
        if self._is_namespace:
            if not tag_start:
                stack = self._ns_changes_stack
                changes = stack.pop() if stack else None
            else:
                changes = self._ns_changes
            if changes and self._ns_matrix is not None:
                _restore_ns_matrix(self._ns_matrix, changes)
                self._ns_changes = None
                self._el_name_cache = None
                self._ns_snapshot = None
