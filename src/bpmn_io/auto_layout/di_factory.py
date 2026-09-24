# Transposed from bpmn-io/bpmn-auto-layout@1.3.0 lib/di/DiFactory.js (MIT).
"""DI element creation transposed from ``lib/di/DiFactory.js``."""

from __future__ import annotations

from typing import Any, TypeAlias

from bpmn_io import _min_dash

__all__ = ["DiFactory"]

#: A dynamic moddle element; the attribute shape varies by type.
Element: TypeAlias = Any


class DiFactory:
    """Create ``bpmndi``/``dc`` elements on the owning moddle instance."""

    def __init__(self, moddle: Element) -> None:
        """Bind the factory to its owning moddle instance."""
        self.moddle = moddle

    def create(self, type_name: str, attrs: dict[str, Any] | None = None) -> Element:
        """Create an instance of ``type_name`` (``attrs`` defaults to ``{}``)."""
        return self.moddle.create(type_name, attrs or {})

    def create_di_bounds(self, bounds: dict[str, Any] | None = None) -> Element:
        """Create a ``dc:Bounds`` element (empty when ``bounds`` is absent)."""
        return self.create("dc:Bounds", bounds or {})

    def create_di_label(self) -> Element:
        """Create an empty ``bpmndi:BPMNLabel`` element."""
        return self.create("bpmndi:BPMNLabel", {"bounds": self.create_di_bounds()})

    def create_di_shape(
        self, semantic: Element, bounds: dict[str, Any], attrs: dict[str, Any] | None = None
    ) -> Element:
        """Create a ``bpmndi:BPMNShape`` for ``semantic`` with ``bounds``."""
        return self.create(
            "bpmndi:BPMNShape",
            _min_dash.assign(
                {"bpmnElement": semantic, "bounds": self.create_di_bounds(bounds)},
                attrs or {},
            ),
        )

    def create_di_waypoints(self, waypoints: list[dict[str, Any]]) -> list[Element]:
        """Create one ``dc:Point`` per waypoint position."""
        return _min_dash.map(waypoints, self.create_di_waypoint)

    def create_di_waypoint(self, point: dict[str, Any]) -> Element:
        """Create a ``dc:Point`` keeping only ``x``/``y`` (drops ``original``)."""
        return self.create("dc:Point", _min_dash.pick(point, ["x", "y"]))

    def create_di_edge(
        self,
        semantic: Element,
        waypoints: list[dict[str, Any]],
        attrs: dict[str, Any] | None = None,
    ) -> Element:
        """Create a ``bpmndi:BPMNEdge`` for ``semantic`` routed via ``waypoints``."""
        return self.create(
            "bpmndi:BPMNEdge",
            _min_dash.assign(
                {"bpmnElement": semantic, "waypoint": self.create_di_waypoints(waypoints)},
                attrs or {},
            ),
        )

    def create_di_plane(self, attrs: dict[str, Any]) -> Element:
        """Create a ``bpmndi:BPMNPlane`` element."""
        return self.create("bpmndi:BPMNPlane", attrs)

    def create_di_diagram(self, attrs: dict[str, Any]) -> Element:
        """Create a ``bpmndi:BPMNDiagram`` element."""
        return self.create("bpmndi:BPMNDiagram", attrs)
