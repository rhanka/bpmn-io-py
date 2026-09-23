# Transposed from bpmn-io/bpmn-auto-layout@1.3.0 lib/handler/index.js (MIT).
"""Handler registry (order significant: element, incoming, outgoing, attacher)."""

from __future__ import annotations

from typing import Any

from bpmn_io.auto_layout.handlers import (
    attacher_handler,
    element_handler,
    incoming_handler,
    outgoing_handler,
)

__all__ = ["HANDLERS"]

#: Grid/DI operation handlers in upstream import order.
HANDLERS: list[dict[str, Any]] = [
    element_handler.HANDLER,
    incoming_handler.HANDLER,
    outgoing_handler.HANDLER,
    attacher_handler.HANDLER,
]
