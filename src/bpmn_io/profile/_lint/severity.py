# DESIGN R3.3 §6.3: numeric severities and the info-through-warn transport.
"""Severity normalization and adapter transport for the lint bridge.

Profile and upstream settings resolve numeric severities ``0=off``,
``1=warn``, ``2=error``, ``3=info`` alongside the case-insensitive words.
Both runtimes deliberately transport effective ``info`` as ``warn`` and the
adapter restores ``info`` in the unified entries; the raw upstream category
stays ``warn`` (``rawStandardFindings`` preserves it verbatim).
"""

from __future__ import annotations

from typing import Any

from bpmn_io.profile._lint.errors import ProfileDataError

__all__ = [
    "CLASSIFICATIONS",
    "SEVERITIES",
    "normalize_severity",
    "transport_severity",
]

#: Effective severities (DESIGN R3.3 §6.3 numeric mapping included).
SEVERITIES = ("off", "warn", "error", "info")

#: Unified classifications authored per setting (DESIGN R3.3 §10.1).
CLASSIFICATIONS = ("integrity", "readiness", "repairable", "advisory")

_NUMERIC_SEVERITIES = ("off", "warn", "error", "info")

#: ASCII-only case fold for severity words (severity words are ASCII,
#: DESIGN R3.3 §6.3; non-ASCII input never folds and refuses below).
_ASCII_FOLD = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


def normalize_severity(value: Any) -> str:  # noqa: ANN401 - JSON-dynamic input
    """Resolve a severity word or number to its effective severity word.

    Words match case-insensitively; integral numbers (including integral
    floats such as ``1.0``) map ``0/1/2/3`` to ``off/warn/error/info``.
    Booleans, non-integral numbers and unknown words refuse: severity
    authoring is closed profile data, never a truthiness test.
    """
    if isinstance(value, bool):
        msg = f"invalid severity: {value!r}"
        raise ProfileDataError(msg)
    if isinstance(value, float):
        if not value.is_integer():
            msg = f"invalid severity: {value!r}"
            raise ProfileDataError(msg)
        value = int(value)
    if isinstance(value, int):
        if 0 <= value <= 3:
            return _NUMERIC_SEVERITIES[value]
        msg = f"invalid severity: {value!r}"
        raise ProfileDataError(msg)
    if isinstance(value, str):
        word = value.translate(_ASCII_FOLD)
        if word in SEVERITIES:
            return word
        msg = f"invalid severity: {value!r}"
        raise ProfileDataError(msg)
    msg = f"invalid severity: {value!r}"
    raise ProfileDataError(msg)


def transport_severity(severity: str) -> str:
    """Map an effective severity to its upstream transport category.

    Effective ``info`` travels as ``warn``; every other severity travels
    unchanged. The adapter restores ``info`` from the effective policy row.
    """
    if severity == "info":
        return "warn"
    return severity
