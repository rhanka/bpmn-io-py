# Transposed from bpmn-io/moddle@3124e6a lib/factory.js (MIT).
"""Model element factory transposed from moddle ``lib/factory.js``.

Each type gets a fresh class (per-type ``__dict__`` isolation comes for free, where
upstream builds a fresh prototype). Single-valued properties with a default become class
attributes, mirroring upstream prototype defaults: they are visible but not serialized
until set on the instance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bpmn_io._js import UNDEFINED
from bpmn_io._min_dash import for_each
from bpmn_io.moddle.base import ModdleElement

if TYPE_CHECKING:
    from bpmn_io.moddle.descriptor_builder import EffectiveDescriptor, PropertyDescriptor
    from bpmn_io.moddle.moddle import Moddle
    from bpmn_io.moddle.properties import Properties

__all__ = ["Factory"]


class Factory:
    """A model element factory."""

    def __init__(self, model: Moddle, properties: Properties) -> None:
        """Bind the factory to its model and property helper."""
        self.model = model
        self.properties = properties

    def create_type(self, descriptor: EffectiveDescriptor) -> type[ModdleElement]:
        """Build the element class for an effective descriptor."""
        model = self.model
        props = self.properties

        namespace: dict[str, Any] = {}

        def _set_default(prop: PropertyDescriptor, _key: object) -> None:
            """Carry one prototype default into the class namespace."""
            if not prop.is_many and prop.default is not UNDEFINED:
                namespace[prop.name] = prop.default

        # initialize default values
        for_each(descriptor.properties, _set_default)

        name = descriptor.ns.name

        def _element_init(self: ModdleElement, attrs: dict[str, Any] | None = None) -> None:
            """Create an element, initializing it from ``attrs``."""
            props.define(self, "type_", value=name, enumerable=True)
            props.define(self, "attrs_", value={})
            props.define(self, "parent_", writable=True)

            def _apply(value: object, key: str) -> None:
                """Set one constructor attribute."""
                self.set(key, value)

            for_each(attrs, _apply)

        def _has_type(element: object, type: object = None) -> bool:  # noqa: A002
            """Check type membership (the per-model ``hasType`` static)."""
            if type is None:
                return element in descriptor.all_types_by_name
            return model.has_type(element, type)

        namespace["__init__"] = _element_init
        namespace["has_type"] = staticmethod(_has_type)
        namespace["model_"] = model
        namespace["descriptor_"] = descriptor

        return type("ModdleElement", (ModdleElement,), namespace)
