# Transposed from bpmn-io/bpmnlint@de71146 config/all.js (MIT).
"""The ``bpmnlint:all`` config: every built-in rule at ``error``."""

from __future__ import annotations

__all__ = ["CONFIG"]

_ALL_RULES = [
    "ad-hoc-sub-process",
    "conditional-event",
    "conditional-flows",
    "end-event-required",
    "event-based-gateway",
    "event-sub-process-typed-start-event",
    "fake-join",
    "global",
    "label-required",
    "link-event",
    "no-bpmndi",
    "no-complex-gateway",
    "no-disconnected",
    "no-duplicate-sequence-flows",
    "no-gateway-join-fork",
    "no-implicit-end",
    "no-implicit-split",
    "no-implicit-start",
    "no-inclusive-gateway",
    "no-overlapping-elements",
    "single-blank-start-event",
    "single-event-definition",
    "standard-size",
    "start-event-required",
    "sub-process-blank-start-event",
    "superfluous-gateway",
    "superfluous-label",
    "superfluous-termination",
]

CONFIG: dict[str, dict[str, str]] = {
    "rules": dict.fromkeys(_ALL_RULES, "error"),
}
