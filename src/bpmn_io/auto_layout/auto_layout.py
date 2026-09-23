# Transposed from bpmn-io/bpmn-auto-layout@1.3.0 lib/index.js (MIT).
"""Module-level layout entry point (mirrors ``lib/index.js``)."""

from __future__ import annotations

from bpmn_io.auto_layout.errors import LayoutError, LayoutWarning
from bpmn_io.auto_layout.layouter import Layouter

__all__ = ["LayoutError", "LayoutWarning", "layout_process"]


def layout_process(xml: str) -> str:
    """Lay out the first root process of ``xml`` and return the DI XML."""
    return Layouter().layout_process(xml)
