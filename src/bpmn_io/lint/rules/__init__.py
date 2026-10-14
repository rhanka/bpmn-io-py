"""Built-in bpmnlint rules (upstream ``rules/``), keyed by rule name."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bpmn_io.lint.rules import (
    ad_hoc_sub_process,
    conditional_event,
    conditional_flows,
    end_event_required,
    event_based_gateway,
    event_sub_process_typed_start_event,
    fake_join,
    global_,
    label_required,
    link_event,
    no_bpmndi,
    no_complex_gateway,
    no_disconnected,
    no_duplicate_sequence_flows,
    no_gateway_join_fork,
    no_implicit_end,
    no_implicit_split,
    no_implicit_start,
    no_inclusive_gateway,
    no_overlapping_elements,
    single_blank_start_event,
    single_event_definition,
    standard_size,
    start_event_required,
    sub_process_blank_start_event,
    superfluous_gateway,
    superfluous_label,
    superfluous_termination,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

__all__ = ["RULES"]

#: Rule name -> rule factory (upstream ``rules/<name>.js`` module exports).
RULES: dict[str, Callable[..., dict[str, Any]]] = {
    "ad-hoc-sub-process": ad_hoc_sub_process.factory,
    "conditional-event": conditional_event.factory,
    "conditional-flows": conditional_flows.factory,
    "end-event-required": end_event_required.factory,
    "event-based-gateway": event_based_gateway.factory,
    "event-sub-process-typed-start-event": event_sub_process_typed_start_event.factory,
    "fake-join": fake_join.factory,
    "global": global_.factory,
    "label-required": label_required.factory,
    "link-event": link_event.factory,
    "no-bpmndi": no_bpmndi.factory,
    "no-complex-gateway": no_complex_gateway.factory,
    "no-disconnected": no_disconnected.factory,
    "no-duplicate-sequence-flows": no_duplicate_sequence_flows.factory,
    "no-gateway-join-fork": no_gateway_join_fork.factory,
    "no-implicit-end": no_implicit_end.factory,
    "no-implicit-split": no_implicit_split.factory,
    "no-implicit-start": no_implicit_start.factory,
    "no-inclusive-gateway": no_inclusive_gateway.factory,
    "no-overlapping-elements": no_overlapping_elements.factory,
    "single-blank-start-event": single_blank_start_event.factory,
    "single-event-definition": single_event_definition.factory,
    "standard-size": standard_size.factory,
    "start-event-required": start_event_required.factory,
    "sub-process-blank-start-event": sub_process_blank_start_event.factory,
    "superfluous-gateway": superfluous_gateway.factory,
    "superfluous-label": superfluous_label.factory,
    "superfluous-termination": superfluous_termination.factory,
}
