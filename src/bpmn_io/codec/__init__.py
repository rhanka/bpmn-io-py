# Published generic extension-preserving codec (F1 lane, contract f1-extensions/1).
"""Parse, project, hydrate and serialize BPMN trees with preserved extensions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bpmn_io.codec._model import CodecResult, Diagnostic
from bpmn_io.codec.json import hydrate as hydrate
from bpmn_io.codec.json import project as project
from bpmn_io.codec.serialize import serialize_xml as serialize_xml
from bpmn_io.codec.xml_boundary import parse_xml as parse_xml

if TYPE_CHECKING:
    from types import ModuleType

__all__ = [
    "CodecResult",
    "Diagnostic",
    "hydrate",
    "parse_xml",
    "project",
    "serialize_xml",
]


def __getattr__(name: str) -> ModuleType:
    """Lazily re-export submodule helpers without circular imports."""
    if name in {"json", "serialize", "xml_boundary"}:
        import importlib  # noqa: PLC0415

        return importlib.import_module(f"bpmn_io.codec.{name}")
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
