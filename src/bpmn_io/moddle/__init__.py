# Transposed from bpmn-io/moddle@3124e6a lib/index.js (MIT).
"""Public surface of the moddle meta-model runtime (Lot 4)."""

from bpmn_io.moddle.moddle import Moddle
from bpmn_io.moddle.ns import parse_name as parse_name_ns
from bpmn_io.moddle.types import coerce_type
from bpmn_io.moddle.types import is_built_in as is_built_in_type
from bpmn_io.moddle.types import is_simple as is_simple_type

__all__ = ["Moddle", "coerce_type", "is_built_in_type", "is_simple_type", "parse_name_ns"]
