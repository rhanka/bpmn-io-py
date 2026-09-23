"""bpmn-io: bpmn.io's bpmn-moddle and bpmn-auto-layout transposed to pure Python.

A literal, attributed transposition of ``moddle``, ``moddle-xml``, ``bpmn-moddle`` and
``bpmn-auto-layout`` (all MIT, (c) camunda Services GmbH) to Python with no runtime dependency.
See ``THIRD_PARTY_NOTICES.md`` and ``UPSTREAM.toml`` for provenance.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from bpmn_io.auto_layout import Layouter, LayoutError, LayoutWarning, layout_process
from bpmn_io.bpmn_moddle import BpmnModdle, SerializationResult, create_moddle
from bpmn_io.check import Report, check
from bpmn_io.descriptors import DESCRIPTOR_NAMES, load_descriptor
from bpmn_io.moddle_xml.read import ParseError, ParseResult
from bpmn_io.upstream import UPSTREAM_VERSIONS

try:
    __version__ = version("bpmn-io")
except PackageNotFoundError:  # pragma: no cover - source checkout without install
    __version__ = "0.0.0+unknown"

__all__ = [
    "DESCRIPTOR_NAMES",
    "UPSTREAM_VERSIONS",
    "BpmnModdle",
    "LayoutError",
    "LayoutWarning",
    "Layouter",
    "ParseError",
    "ParseResult",
    "Report",
    "SerializationResult",
    "__version__",
    "check",
    "create_moddle",
    "layout_process",
    "load_descriptor",
]
