# Transposed from bpmn-io/bpmnlint@de71146 config/correctness.js (MIT).
"""The ``bpmnlint:correctness`` config."""

from __future__ import annotations

__all__ = ["CONFIG"]

CONFIG: dict[str, dict[str, str]] = {
    "rules": {
        "ad-hoc-sub-process": "error",
        "conditional-event": "error",
        "event-based-gateway": "error",
        "event-sub-process-typed-start-event": "error",
        "link-event": "error",
        "no-duplicate-sequence-flows": "warn",
        "sub-process-blank-start-event": "error",
        "single-blank-start-event": "error",
    },
}
