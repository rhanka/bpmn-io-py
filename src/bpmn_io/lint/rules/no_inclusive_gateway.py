# Transposed from bpmn-io/bpmnlint@de71146 rules/no-inclusive-gateway.js (MIT).
"""Rule: inclusive gateways are discouraged."""

from __future__ import annotations

from bpmn_io.lint.rules.helper import check_discouraged_node_type

__all__ = ["factory"]

factory = check_discouraged_node_type("bpmn:InclusiveGateway", "no-inclusive-gateway")
