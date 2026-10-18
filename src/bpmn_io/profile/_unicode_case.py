"""Unicode full default case mappings, version 15.0.0 (DESIGN R3.3 §2.2).

Implements the ``case`` value operator over the pinned full default case
data: simple uppercase mappings plus unconditional special-casing entries
(multi-code-point results included), no locale behaviour, no normalization.
The single untagged context rule for the capital sigma applies on the lower
path (word-final maps to the final form); language-tagged conditions stay
excluded.
"""

from __future__ import annotations

import unicodedata
from typing import Final

__all__ = [
    "UNICODE_VERSION_PIN",
    "apply_case",
    "case_version",
    "lower_full",
    "upper_full",
]

#: Pinned Unicode version for the ``case`` operator.
UNICODE_VERSION_PIN: Final[str] = "15.0.0"


def case_version() -> str:
    """Return the platform Unicode version backing this module."""
    return unicodedata.unidata_version


def _is_final_sigma(text: str, index: int) -> bool:
    """Return whether the sigma at ``index`` is word-final (untagged rule)."""
    pos = index + 1
    while pos < len(text):
        char = text[pos]
        if unicodedata.category(char) in {"Mn", "Mc", "Me", "Sk", "Sc"}:
            pos += 1
            continue
        break
    if pos < len(text) and text[pos] in {"'", "’", "ʼ", "ʹ"}:  # noqa: RUF001
        pos += 1
        while pos < len(text) and unicodedata.category(text[pos]) in {"Mn", "Mc", "Me"}:
            pos += 1
    following: str | None = text[pos] if pos < len(text) else None
    if following is not None and following.isalpha():
        return False
    return any(char.isalpha() for char in text[: index + 1])


def upper_full(value: str) -> str:
    """Uppercase ``value`` with the full default mappings (no locale)."""
    parts: list[str] = []
    for char in value:
        if char == "ß":
            parts.append("SS")
        elif char == "ﬆ":
            parts.append("ST")
        else:
            parts.append(char.upper())
    return "".join(parts)


def lower_full(value: str) -> str:
    """Lowercase ``value`` with the full default mappings (final sigma kept)."""
    parts: list[str] = []
    for index, char in enumerate(value):
        if char == "Σ":
            parts.append("ς" if _is_final_sigma(value, index) else "σ")  # noqa: RUF001
        elif char == "İ":
            parts.append("İ")
        else:
            parts.append(char.lower())
    return "".join(parts)


def apply_case(value: str, mode: str) -> str:
    """Apply one ``case`` operator mode (``upper`` or ``lower``)."""
    if mode == "upper":
        return upper_full(value)
    if mode == "lower":
        return lower_full(value)
    msg = f"unknown case mode {mode!r}; expected 'upper' or 'lower'"
    raise ValueError(msg)
