# Transposed from bpmn-io/bpmnlint@de71146 lib/testers/helper.js (MIT).
"""Moddle creation helpers for lint tests, transposed from ``lib/testers/helper.js``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bpmn_io.bpmn_moddle.simple import create_moddle as _create_model

__all__ = ["create_moddle", "read_moddle"]


def create_moddle(
    xml: str,
    element_type: str | dict[str, Any] = "bpmn:Definitions",
    moddle_extensions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a moddle root from ``xml`` (upstream ``createModdle``, sync per D4.1)."""
    if not isinstance(element_type, str):
        moddle_extensions = element_type
        element_type = "bpmn:Definitions"

    moddle = _create_model(moddle_extensions) if moddle_extensions else _create_model()

    result = moddle.from_xml(xml, element_type)
    root = result.root_element
    warnings = result.warnings

    return {
        "root": root,
        "moddle": moddle,
        "context": {
            "warnings": warnings,
        },
        "warnings": warnings,
    }


def read_moddle(
    file_path: str | Path,
    element_type: str | dict[str, Any] = "bpmn:Definitions",
    moddle_extensions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Read a moddle root from ``file_path`` (upstream ``readModdle``)."""
    contents = Path(file_path).read_text(encoding="utf-8")

    return create_moddle(contents, element_type, moddle_extensions)
