"""Text measurement with declared fallback advances (DESIGN R3.3 §9.3).

Line feed splits lines without wrapping; the width of a line sums one
advance per Unicode scalar (``spaceAdvance`` for U+0020, the declared
``defaultAdvance`` otherwise); the height is the line count times
``ascent + descent``. Values are ticks. No normalization, no platform
font measurement.
"""

from __future__ import annotations

import json

from bpmn_io.profile._results import PureRefused, PureResult, PureSuccess

__all__ = ["measure_text"]


def _metrics_record(raw: bytes) -> dict[str, int] | None:
    """Parse one metrics resource (None when malformed)."""
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(document, dict):
        return None
    record: dict[str, int] = {}
    for key in ("defaultAdvance", "spaceAdvance", "ascent", "descent"):
        entry = document.get(key)
        if not isinstance(entry, int) or isinstance(entry, bool) or entry < 0:
            return None
        record[key] = entry
    return record


def measure_text(metrics: bytes, text: str) -> PureResult:
    """Measure one text with a metrics resource."""
    record = _metrics_record(metrics)
    if record is None or not isinstance(text, str):
        return PureRefused(code="operation-error")
    default = record["defaultAdvance"]
    space = record["spaceAdvance"]
    line_height = record["ascent"] + record["descent"]
    lines = text.split("\n")
    widest = 0
    for line in lines:
        width = 0
        for scalar in line:
            width += space if scalar == " " else default
        widest = max(widest, width)
    return PureSuccess(
        payload={"lines": list(lines), "width": widest, "height": len(lines) * line_height}
    )
