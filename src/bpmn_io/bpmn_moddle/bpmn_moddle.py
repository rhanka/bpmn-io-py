# Transposed from bpmn-io/bpmn-moddle@f35959a lib/bpmn-moddle.js (MIT).
"""A ``Moddle`` model with BPMN 2.0 XML import and export."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from bpmn_io.moddle.moddle import Moddle
from bpmn_io.moddle_xml.read import ParseResult, Reader
from bpmn_io.moddle_xml.write import Writer

if TYPE_CHECKING:
    from bpmn_io.moddle.base import AnyModdleElement, ModdleElement
    from bpmn_io.moddle.registry import PackageDef

__all__ = ["BpmnModdle", "SerializationResult"]


@dataclass(frozen=True)
class SerializationResult:
    """The successful ``to_xml`` result (upstream resolves ``{ xml }``)."""

    xml: str


class BpmnModdle(Moddle):
    """A model that imports and exports BPMN 2.0 XML files."""

    def __init__(
        self,
        packages: list[PackageDef] | dict[str, PackageDef] | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Create a model for ``packages`` (a list or a name-keyed map)."""
        if packages is None:
            from bpmn_io.bpmn_moddle.simple import DEFAULT_PACKAGES  # noqa: PLC0415

            packages = dict(DEFAULT_PACKAGES)
        super().__init__(packages, config)

    def from_xml(
        self,
        xml: str,
        type_name: str | dict[str, Any] | None = "bpmn:Definitions",
        options: dict[str, Any] | None = None,
    ) -> ParseResult:
        """Instantiate a model tree from an XML string (raises ``ParseError``)."""
        if not isinstance(type_name, str):
            options = type_name
            type_name = "bpmn:Definitions"
        reader = Reader({"model": self, "lax": True, **(options or {})})
        root_handler = reader.handler(type_name)
        return reader.from_xml(xml, root_handler)

    def to_xml(
        self,
        element: ModdleElement | AnyModdleElement,
        options: dict[str, Any] | None = None,
    ) -> SerializationResult:
        """Serialize a model tree to XML (writer exceptions propagate as-is)."""
        opts = options or {}
        writer = Writer(
            format=bool(opts.get("format", False)),
            preamble=bool(opts.get("preamble", True)),
        )
        xml = writer.to_xml(element)
        return SerializationResult(xml=xml)
