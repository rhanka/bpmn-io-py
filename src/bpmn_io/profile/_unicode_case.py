"""Unicode full default case mappings, version 15.0.0 (DESIGN R3.3 §2.2).

Implements the ``case`` value operator over the pinned full default case
data in :mod:`bpmn_io.profile._unicode15` (generated from the
language-neutral ``unicode-case/1`` contract): unconditional special-casing
entries (multi-code-point results included), no locale behaviour, no
normalization. The single untagged context rule Final_Sigma applies on the
lower path (word-final capital sigma maps to the final form); the 15
language-tagged conditions stay excluded. No platform case data is used:
no ``unicodedata``, no ``str.upper``/``lower``/``casefold``.
"""

from __future__ import annotations

from bisect import bisect_right
from typing import Final

from bpmn_io.profile._unicode15 import (
    CASE_IGNORABLE_RANGES,
    CASED_RANGES,
    FINAL_SIGMA,
    LOWER,
    UNICODE_VERSION,
    UPPER,
)

__all__ = [
    "UNICODE_VERSION_PIN",
    "apply_case",
    "case_version",
    "lower_full",
    "upper_full",
]

#: Pinned Unicode version for the ``case`` operator.
UNICODE_VERSION_PIN: Final[str] = UNICODE_VERSION


def _as_code(value: object) -> int:
    """Narrow a generated descriptor value to a code point."""
    if not isinstance(value, int):
        msg = f"invalid generated Final_Sigma descriptor value {value!r}"
        raise TypeError(msg)
    return value


#: Capital sigma (subject to the Final_Sigma context rule on the lower path).
_CAPITAL_SIGMA: Final[int] = _as_code(FINAL_SIGMA["capital"])


def case_version() -> str:
    """Return the pinned Unicode version backing this module."""
    return UNICODE_VERSION_PIN


def _in_ranges(ranges: tuple[tuple[int, int], ...], code: int) -> bool:
    """Return whether ``code`` falls in the sorted merged ``ranges``."""
    index = bisect_right(ranges, (code, 0x110000))
    return index > 0 and ranges[index - 1][0] <= code <= ranges[index - 1][1]


def _is_final_sigma(text: str, index: int) -> bool:
    """Return whether the sigma at ``index`` is word-final (untagged rule).

    UCD 15.0.0 §3.13 context: a cased character precedes (skipping
    Case_Ignorable characters) and no cased character follows (skipping
    Case_Ignorable characters).
    """
    pos = index - 1
    while pos >= 0 and _in_ranges(CASE_IGNORABLE_RANGES, ord(text[pos])):
        pos -= 1
    if pos < 0 or not _in_ranges(CASED_RANGES, ord(text[pos])):
        return False
    pos = index + 1
    while pos < len(text) and _in_ranges(CASE_IGNORABLE_RANGES, ord(text[pos])):
        pos += 1
    return pos >= len(text) or not _in_ranges(CASED_RANGES, ord(text[pos]))


def upper_full(value: str) -> str:
    """Uppercase ``value`` with the pinned full mappings (no locale)."""
    parts: list[str] = []
    for char in value:
        code = ord(char)
        mapped = UPPER.get(code)
        if mapped is None:
            parts.append(char)
        else:
            parts.append("".join(chr(point) for point in mapped))
    return "".join(parts)


def lower_full(value: str) -> str:
    """Lowercase ``value`` with the pinned full mappings (final sigma kept)."""
    parts: list[str] = []
    for index, char in enumerate(value):
        code = ord(char)
        if code == _CAPITAL_SIGMA and _is_final_sigma(value, index):
            parts.append(chr(_as_code(FINAL_SIGMA["lowerFinal"])))
            continue
        mapped = LOWER.get(code)
        if mapped is None:
            parts.append(char)
        else:
            parts.append("".join(chr(point) for point in mapped))
    return "".join(parts)


def apply_case(value: str, mode: str) -> str:
    """Apply one ``case`` operator mode (``upper`` or ``lower``)."""
    if mode == "upper":
        return upper_full(value)
    if mode == "lower":
        return lower_full(value)
    msg = f"unknown case mode {mode!r}; expected 'upper' or 'lower'"
    raise ValueError(msg)
