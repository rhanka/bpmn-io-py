# Transposed from bpmn-io/bpmn-moddle@f35959a lib/simple.js (MIT).
"""The default six-package BPMN model factory."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import TYPE_CHECKING, Any, Final

from bpmn_io.bpmn_moddle.bpmn_moddle import BpmnModdle
from bpmn_io.descriptors import load_descriptor

if TYPE_CHECKING:
    from bpmn_io.moddle.registry import PackageDef

__all__ = ["DEFAULT_PACKAGES", "create_moddle"]


def _load_color_descriptor() -> PackageDef:
    """Return the vendored ``bpmn-in-color`` descriptor (``DESCRIPTOR_NAMES["color"]``)."""
    text = (
        files("bpmn_io.resources").joinpath("color/bpmn-in-color.json").read_text(encoding="utf-8")
    )
    descriptor: PackageDef = json.loads(text)
    return descriptor


#: The default descriptor packages (upstream ``simple.js:14-21``; ``color`` last).
DEFAULT_PACKAGES: Final[dict[str, PackageDef]] = {
    "bpmn": load_descriptor("bpmn"),
    "bpmndi": load_descriptor("bpmndi"),
    "dc": load_descriptor("dc"),
    "di": load_descriptor("di"),
    "bioc": load_descriptor("bioc"),
    "color": _load_color_descriptor(),
}


def create_moddle(
    additional_packages: dict[str, PackageDef] | None = None,
    config: dict[str, Any] | None = None,
) -> BpmnModdle:
    """Create a ``BpmnModdle`` with the default packages plus ``additional_packages``."""
    return BpmnModdle({**DEFAULT_PACKAGES, **(additional_packages or {})}, config)
