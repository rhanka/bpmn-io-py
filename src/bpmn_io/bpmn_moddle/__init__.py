# Transposed from bpmn-io/bpmn-moddle@f35959a lib/index.js (MIT).
"""Public surface of the BPMN 2.0 model.

Upstream ``lib/index.js`` re-exports the simple-configured factory as ``BpmnModdle``;
both names are kept here: call ``create_moddle()`` (no arguments) for the
``index.js`` equivalent, or use the ``BpmnModdle`` class directly.
"""

from bpmn_io.bpmn_moddle.bpmn_moddle import BpmnModdle, SerializationResult
from bpmn_io.bpmn_moddle.simple import create_moddle

__all__ = ["BpmnModdle", "SerializationResult", "create_moddle"]
