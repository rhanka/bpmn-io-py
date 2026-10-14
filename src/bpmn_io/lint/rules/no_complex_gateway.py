# Transposed from bpmn-io/bpmnlint@de71146 rules/no-complex-gateway.js (MIT).
"""Rule: complex gateways are discouraged."""

from __future__ import annotations

from bpmn_io.lint.rules.helper import check_discouraged_node_type

__all__ = ["factory"]

factory = check_discouraged_node_type("bpmn:ComplexGateway", "no-complex-gateway")
