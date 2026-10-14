# Transposed from bpmn-io/bpmnlint@de71146 config/recommended.js (MIT).
"""The ``bpmnlint:recommended`` config."""

from __future__ import annotations

__all__ = ["CONFIG"]

CONFIG: dict[str, dict[str, str]] = {
    "rules": {
        "ad-hoc-sub-process": "error",
        "conditional-flows": "error",
        "end-event-required": "error",
        "event-based-gateway": "error",
        "event-sub-process-typed-start-event": "error",
        "fake-join": "warn",
        "global": "warn",
        "label-required": "error",
        "link-event": "error",
        "no-bpmndi": "error",
        "no-complex-gateway": "error",
        "no-disconnected": "error",
        "no-duplicate-sequence-flows": "error",
        "no-gateway-join-fork": "error",
        "no-implicit-split": "error",
        "no-implicit-end": "error",
        "no-implicit-start": "error",
        "no-inclusive-gateway": "warn",
        "no-overlapping-elements": "warn",
        "single-blank-start-event": "error",
        "single-event-definition": "error",
        "start-event-required": "error",
        "sub-process-blank-start-event": "error",
        "superfluous-gateway": "warn",
        "superfluous-label": "warn",
        "superfluous-termination": "warn",
    },
}
