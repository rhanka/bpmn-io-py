# Transposed from bpmn-io/bpmn-auto-layout@1.3.0 lib/ (MIT).
"""Shared layout error and warning types.

Upstream 1.3.0 defines neither: its three ``throw`` sites raise plain ``Error``
(``Grid.js:21-23``, ``Grid.js:65-67``, ``layoutUtil.js:41``) and nothing warns.
Both classes live in this shared leaf so ``grid`` and ``layout_util`` can raise
the single ``LayoutError`` without an import cycle; parse failures keep
propagating as ``ParseError`` and are never wrapped.
"""

from __future__ import annotations

__all__ = ["LayoutError", "LayoutWarning"]


class LayoutError(Exception):
    """Raised for the three upstream layout failures (E1-E3, byte-identical messages)."""


class LayoutWarning(Warning):
    """Forward-compatible warning surface; never emitted by 1.3.0 logic."""
