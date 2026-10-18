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
from typing import Final, Literal

__all__ = ["LexicalError", "LexicalOk", "check_lexical"]

#: Closed lexical refusal codes in source-order precedence handling.
LexicalCode = Literal[
    "profile-json",
    "profile-json-duplicate-key",
    "profile-unicode",
    "profile-number",
]

_SAFE_INTEGER_LIMIT: Final[int] = 9007199254740991

_TOKEN_RE: Final[re.Pattern[str]] = re.compile(
    r'"(?:[^"\\\x00-\x1f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"'
    r"|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?"
    r"|true|false|null"
    r"|[{}[\]:,]"
    r"|\S"
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


class _Parser:
    """Source-order recursive traversal over the token stream."""

    def __init__(self, tokens: list[str]) -> None:
        """Bind the token list with a cursor at the start."""
        self._tokens = tokens
        self._pos = 0

    def parse_value(self) -> Literal["ok", "number"]:
        """Traverse one value, returning ``number`` for a numeric refusal."""
        if self._pos >= len(self._tokens):
            raise _MalformedError
        current = self._tokens[self._pos]
        self._pos += 1
        if current == "{":
            return self._parse_object()
        if current == "[":
            return self._parse_array()
        if current.startswith('"'):
            _decode_string(current)
            return "ok"
        if _NUMBER_RE.match(current) is not None:
            return _check_number(current)
        if current in _TRUE_FALSE_NULL:
            return "ok"
        raise _MalformedError

    def _parse_object(self) -> Literal["ok", "number"]:  # noqa: C901
        """Traverse one object body after its opening brace."""
        if self._pos < len(self._tokens) and self._tokens[self._pos] == "}":
            self._pos += 1
            return "ok"
        seen: set[str] = set()
        while True:
            if self._pos >= len(self._tokens):
                raise _MalformedError
            key_token = self._tokens[self._pos]
            self._pos += 1
            if not key_token.startswith('"'):
                raise _MalformedError
            key = _decode_string(key_token)
            if key in seen:
                raise _DuplicateError
            seen.add(key)
            if self._pos >= len(self._tokens) or self._tokens[self._pos] != ":":
                raise _MalformedError
            self._pos += 1
            outcome = self.parse_value()
            if outcome != "ok":
                return outcome
            if self._pos >= len(self._tokens):
                raise _MalformedError
            if self._tokens[self._pos] != ",":
                break
            self._pos += 1
        if self._pos >= len(self._tokens) or self._tokens[self._pos] != "}":
            raise _MalformedError
        self._pos += 1
        return "ok"

    def _parse_array(self) -> Literal["ok", "number"]:
        """Traverse one array body after its opening bracket."""
        if self._pos < len(self._tokens) and self._tokens[self._pos] == "]":
            self._pos += 1
            return "ok"
        while True:
            outcome = self.parse_value()
            if outcome != "ok":
                return outcome
            if self._pos >= len(self._tokens):
                raise _MalformedError
            if self._tokens[self._pos] != ",":
                break
            self._pos += 1
        if self._pos >= len(self._tokens) or self._tokens[self._pos] != "]":
            raise _MalformedError
        self._pos += 1
        return "ok"


def check_lexical(data: bytes) -> LexicalOk | LexicalError:  # noqa: PLR0911
    """Run the strict lexical pre-parse over raw profile bytes.

    Decodes ``data`` as UTF-8, tokenizes in source order, traverses one root
    value with per-member key decode, Unicode and duplicate checks, then
    rejects trailing data and whole-text grammar failures. Returns
    :class:`LexicalOk` or :class:`LexicalError` with exactly one of the four
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
    except _MalformedError:
        return LexicalError(code="profile-json")
    except IndexError:
        return LexicalError(code="profile-json")
    if outcome == "number":
        return LexicalError(code="profile-number")
    if parser._pos != len(tokens):  # noqa: SLF001 - cursor check is the contract
        return LexicalError(code="profile-json")
    try:
        json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return LexicalError(code="profile-json")
    return LexicalOk()
