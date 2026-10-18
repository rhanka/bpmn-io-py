"""Strict lexical pre-parse for profile text (DESIGN R3.3 §2.1.1).

Implements the four diagnostic codes and first-failure reporting order
derived from ``parseStrict``. Applies at every nesting depth, before schema
validation or compilation.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Final, Literal, cast

__all__ = ["LexicalError", "LexicalOk", "check_lexical"]

#: Closed lexical refusal codes in source-order precedence handling.
#: ``resource-limit`` is the DESIGN §2.5 host traversal bound, reported when
#: nesting exceeds the explicit depth cap instead of recursing.
LexicalCode = Literal[
    "profile-json",
    "profile-json-duplicate-key",
    "profile-unicode",
    "profile-number",
    "resource-limit",
]

_SAFE_INTEGER_LIMIT: Final[int] = 9007199254740991

#: Maximum nesting depth of the lexical traversal. Deeper inputs refuse with
#: ``resource-limit`` instead of recursing (DESIGN R3.3 §2.5 host limits).
_MAX_LEXICAL_DEPTH: Final[int] = 256

#: ECMAScript WhiteSpace + LineTerminator (the exact pre-scan skip set of
#: DESIGN R3.3 §2.1.1 step 1): U+0009-U+000D, U+0020, U+00A0, U+1680,
#: U+2000-U+200A, U+2028, U+2029, U+202F, U+205F, U+3000, U+FEFF.
#: Notably absent: U+0085 (NEL) and U+200B. Python ``\\S`` must not be used:
#: it treats U+0085 as whitespace and would skip it.
_ES_WHITESPACE: Final[str] = (
    "	\n\x0b\x0c\r \xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007"
    "\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
)

_TOKEN_RE: Final[re.Pattern[str]] = re.compile(
    r'"(?:[^"\\\x00-\x1f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"'
    r"|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?"
    r"|true|false|null"
    r"|[{}[\]:,]"
    r"|[^	\n\x0b\x0c\r \xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]"
)

_NUMBER_RE: Final[re.Pattern[str]] = re.compile(r"^-?[0-9]")

_TRUE_FALSE_NULL: Final[frozenset[str]] = frozenset({"true", "false", "null"})


@dataclass(frozen=True)
class LexicalOk:
    """Successful lexical pre-parse marker."""

    status: Literal["ok"] = "ok"


@dataclass(frozen=True)
class LexicalError:
    """One lexical refusal with its closed code."""

    status: Literal["refused"] = "refused"
    code: LexicalCode = "profile-json"


class _DuplicateError(Exception):
    """Decoded duplicate key in one object."""


class _UnicodeError(Exception):
    """Lone surrogate in a decoded string."""


class _MalformedError(Exception):
    """Generic JSON grammar failure."""


def _decode_string(token: str) -> str:
    """Decode one string token, checking Unicode scalars."""
    try:
        value = json.loads(token)
    except (json.JSONDecodeError, ValueError) as exc:
        raise _MalformedError from exc
    if not isinstance(value, str):
        raise _MalformedError
    for char in value:
        point = ord(char)
        if 0xD800 <= point <= 0xDFFF:
            raise _UnicodeError
    return value


def _check_number(token: str) -> Literal["ok", "number"]:
    """Apply the §2.1.1 binary64 safe-integer rule to one number token."""
    try:
        number = float(token)
    except ValueError:
        return "ok"
    if not math.isfinite(number):
        return "number"
    try:
        as_int = int(number)
    except (OverflowError, ValueError):
        return "number"
    if float(number).is_integer() and abs(as_int) > _SAFE_INTEGER_LIMIT:
        return "number"
    return "ok"


class _DepthError(Exception):
    """Nesting deeper than the explicit host traversal bound."""


class _Parser:
    """Source-order iterative traversal over the token stream.

    An explicit stack replaces recursion so hostile nesting refuses with a
    typed ``resource-limit`` instead of raising ``RecursionError``. Check
    order mirrors the former recursive walk exactly: per object member the
    key decodes, then Unicode scalars, then duplicates, then the colon, then
    the value; a numeric refusal propagates immediately without examining
    later siblings or delimiters.
    """

    def __init__(self, tokens: list[str]) -> None:
        """Bind the token list with a cursor at the start."""
        self._tokens = tokens
        self._pos = 0

    def _take(self) -> str:
        """Consume one token, refusing truncated input as malformed."""
        if self._pos >= len(self._tokens):
            raise _MalformedError
        current = self._tokens[self._pos]
        self._pos += 1
        return current

    def _peek(self) -> str | None:
        """Return the next token without consuming it."""
        if self._pos >= len(self._tokens):
            return None
        return self._tokens[self._pos]

    def _scalar_value(self, current: str) -> Literal["ok", "number"]:
        """Apply one scalar token in value position."""
        if current.startswith('"'):
            _decode_string(current)
            return "ok"
        if _NUMBER_RE.match(current) is not None:
            return _check_number(current)
        if current in _TRUE_FALSE_NULL:
            return "ok"
        raise _MalformedError

    def _push(self, stack: list[list[object]], current: str) -> None:
        """Open one container frame, refusing beyond the host depth bound."""
        if len(stack) >= _MAX_LEXICAL_DEPTH:
            raise _DepthError
        stack.append([current, set() if current == "{" else None, "head"])

    @staticmethod
    def _close(stack: list[list[object]]) -> None:
        """Close the top frame; a completed child resumes its parent at ``comma``."""
        stack.pop()
        if stack:
            stack[-1][2] = "comma"

    def _step_value(self, stack: list[list[object]], frame: list[object]) -> bool:
        """Consume one nested value; True keeps traversing, False stops on number."""
        current = self._take()
        if current not in ("{", "["):
            if self._scalar_value(current) != "ok":
                return False
            frame[2] = "comma"
            return True
        self._push(stack, current)
        return True

    def _step_object(self, stack: list[list[object]], frame: list[object]) -> None:
        """Advance one object frame by a single stage transition."""
        stage = frame[2]
        if stage in ("head", "key"):
            if stage == "head" and self._peek() == "}":
                self._pos += 1
                self._close(stack)
                return
            key_token = self._take()
            if not key_token.startswith('"'):
                raise _MalformedError
            key = _decode_string(key_token)
            seen = cast("set[str]", frame[1])
            if key in seen:
                raise _DuplicateError
            seen.add(key)
            frame[2] = "colon"
        elif stage == "colon":
            if self._take() != ":":
                raise _MalformedError
            frame[2] = "value"
        elif stage == "value":
            frame[2] = "comma" if self._step_value(stack, frame) else "number"
        else:  # stage == "comma"
            delimiter = self._take()
            if delimiter == ",":
                frame[2] = "key"
            elif delimiter != "}":
                raise _MalformedError
            else:
                self._close(stack)

    def _step_array(self, stack: list[list[object]], frame: list[object]) -> None:
        """Advance one array frame by a single stage transition."""
        stage = frame[2]
        if stage == "head":
            if self._peek() == "]":
                self._pos += 1
                self._close(stack)
            else:
                frame[2] = "value"
        elif stage == "value":
            frame[2] = "comma" if self._step_value(stack, frame) else "number"
        else:  # stage == "comma"
            delimiter = self._take()
            if delimiter == ",":
                frame[2] = "value"
            elif delimiter != "]":
                raise _MalformedError
            else:
                self._close(stack)

    def parse_value(self) -> Literal["ok", "number"]:
        """Traverse one value, returning ``number`` for a numeric refusal."""
        current = self._take()
        if current not in ("{", "["):
            return self._scalar_value(current)
        # Each frame is [kind, seen-keys-or-None, stage] with stage one of
        # "head" (first member/element or immediate close), "key" (object
        # key expected), "colon", "value" (nested value expected), "comma"
        # (`,` or the closing delimiter expected) and "number" (a numeric
        # refusal was reached; unwind without further checks).
        stack: list[list[object]] = []
        self._push(stack, current)
        while stack:
            frame = stack[-1]
            if frame[2] == "number":
                return "number"
            if frame[0] == "{":
                self._step_object(stack, frame)
            else:
                self._step_array(stack, frame)
        return "ok"


def _finish_traversal(text: str, tokens: list[str], parser: _Parser) -> LexicalOk | LexicalError:
    """Reject trailing data and whole-text grammar failures after traversal."""
    if parser._pos != len(tokens):  # noqa: SLF001 - cursor check is the contract
        return LexicalError(code="profile-json")
    try:
        json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return LexicalError(code="profile-json")
    except RecursionError:
        # Unreachable for traversal-accepted depths (the explicit cap sits
        # far below the interpreter recursion limit), kept as a typed bound.
        return LexicalError(code="resource-limit")
    return LexicalOk()


def check_lexical(data: bytes) -> LexicalOk | LexicalError:  # noqa: PLR0911
    """Run the strict lexical pre-parse over raw profile bytes.

    Decodes ``data`` as UTF-8, tokenizes in source order, traverses one root
    value with per-member key decode, Unicode and duplicate checks, then
    rejects trailing data and whole-text grammar failures. Returns
    :class:`LexicalOk` or :class:`LexicalError` with exactly one of the five
    closed codes.
    """
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return LexicalError(code="profile-json")
    tokens = _TOKEN_RE.findall(text)
    parser = _Parser(tokens)
    try:
        outcome = parser.parse_value()
    except _UnicodeError:
        return LexicalError(code="profile-unicode")
    except _DuplicateError:
        return LexicalError(code="profile-json-duplicate-key")
    except _DepthError:
        return LexicalError(code="resource-limit")
    except _MalformedError:
        return LexicalError(code="profile-json")
    except IndexError:
        return LexicalError(code="profile-json")
    if outcome == "number":
        return LexicalError(code="profile-number")
    return _finish_traversal(text, tokens, parser)
