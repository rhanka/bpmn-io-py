"""Canonical bytes ``profile-c14n/2`` (DESIGN R3.3 §3.1, RFC 8785).

UTF-16 code-unit key ordering, no insignificant whitespace, UTF-8 without
BOM, ECMAScript shortest binary64 number rendering, ``-0`` as ``0``, JSON
escaping, no normalization. Arrays keep order. Rejects NaN, infinities and
lone surrogates.
"""

from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal
from typing import Final

__all__ = ["digest", "digest_bytes", "jcs", "jcs_bytes"]

_Json = dict[str, object] | list[object] | str | int | float | bool | None


def _check_string(value: str) -> None:
    """Reject lone surrogates in one string value."""
    for char in value:
        point = ord(char)
        if 0xD800 <= point <= 0xDFFF:
            msg = "profile-c14n/2 rejects lone surrogates"
            raise ValueError(msg)


def _ecma_number(value: float) -> str:
    """Render one finite binary64 per ECMAScript Number-to-string."""
    if math.isnan(value) or math.isinf(value):
        msg = "profile-c14n/2 rejects non-finite numbers"
        raise ValueError(msg)
    if value == 0:
        return "0"
    negative = value < 0
    magnitude = -value if negative else value
    text = repr(magnitude)
    dec = Decimal(text)
    sign, digits, exponent = dec.as_tuple()
    _ = sign
    if not isinstance(exponent, int):
        msg = "profile-c14n/2 rejects non-finite numbers"
        raise TypeError(msg)
    digit_str = "".join(str(d) for d in digits) if digits else "0"
    original_len = len(digit_str)
    stripped = digit_str.rstrip("0")
    if not stripped:
        return "0"
    cups = stripped
    cups_len = len(cups)
    # n satisfies value = cups * 10^(n - cups_len); trailing-zero strip keeps n.
    n = exponent + original_len
    if cups_len <= n <= 21:
        rendered = cups + "0" * (n - cups_len)
    elif 0 < n <= 21:
        rendered = cups[:n] + "." + cups[n:]
    elif -6 < n <= 0:
        rendered = "0." + "0" * (-n) + cups
    else:
        exp = n - 1
        mantissa = cups if cups_len == 1 else cups[0] + "." + cups[1:]
        sign_str = "+" if exp >= 0 else "-"
        rendered = f"{mantissa}e{sign_str}{abs(exp)}"
    return f"-{rendered}" if negative else rendered


def _escape_key(key: str) -> str:
    """Encode one object key with JSON string escaping."""
    _check_string(key)
    return json.dumps(key, ensure_ascii=False)


def _render(value: object) -> str:  # noqa: PLR0911
    """Render one JSON value to its canonical text."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return _ecma_number(value)
    if isinstance(value, str):
        _check_string(value)
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ",".join(_render(entry) for entry in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value.keys(), key=lambda k: k.encode("utf-16-be"))
        parts = [_escape_key(key) + ":" + _render(value[key]) for key in keys]
        return "{" + ",".join(parts) + "}"
    msg = f"profile-c14n/2 rejects value of type {type(value).__name__}"
    raise TypeError(msg)


def jcs(value: object) -> str:
    """Return the canonical JSON text for ``value``."""
    return _render(value)


def jcs_bytes(value: object) -> bytes:
    """Return the canonical UTF-8 bytes for ``value`` (no BOM, no newline)."""
    return _render(value).encode("utf-8")


def digest(value: object) -> str:
    """Return ``H(x)``: lowercase hex SHA-256 over UTF-8 JCS bytes."""
    return hashlib.sha256(jcs_bytes(value)).hexdigest()


def digest_bytes(data: bytes) -> str:
    """Return ``B(bytes)``: lowercase hex SHA-256 over raw bytes."""
    return hashlib.sha256(data).hexdigest()


#: UTF-16 ordering helper exposed for result sorting (profile-c14n/2 order).
def utf16_key(value: str) -> bytes:
    """Return the UTF-16BE sort key for one string."""
    return value.encode("utf-16-be")


_UTF16_SENTINEL: Final[bytes] = b""
