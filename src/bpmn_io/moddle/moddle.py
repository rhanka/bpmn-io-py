# Transposed from bpmn-io/moddle@3124e6a lib/moddle.js (MIT).
"""The moddle model transposed from moddle ``lib/moddle.js``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from bpmn_io._js import UNDEFINED
from bpmn_io._min_dash import for_each, is_object
from bpmn_io.moddle.base import AnyModdleElement
from bpmn_io.moddle.factory import Factory
from bpmn_io.moddle.properties import Properties
from bpmn_io.moddle.registry import PackageDef, Registry

if TYPE_CHECKING:
    from collections.abc import Callable

    from bpmn_io.moddle.base import ModdleElement
    from bpmn_io.moddle.descriptor_builder import EffectiveDescriptor, PropertyDescriptor
    from bpmn_io.moddle.registry import RegisteredPackage, RegisteredTypeDef

__all__ = ["Moddle"]


class Moddle:
    """A model that creates elements of the registered package types."""

    def __init__(
        self,
        packages: list[PackageDef] | dict[str, PackageDef],
        config: dict[str, Any] | None = None,
    ) -> None:
        """Create a model for ``packages`` (a list or a name-keyed map)."""
        self.properties = Properties(self)
        self.factory = Factory(self, self.properties)
        self.registry = Registry(packages, self.properties)
        self.type_cache: dict[str, type[ModdleElement]] = {}
        self.config: dict[str, Any] = config if config is not None else {}

    def __getstate__(self) -> dict[str, Any]:
        """Exclude the element-class cache (rebuilt lazily after unpickling)."""
        state = dict(self.__dict__)
        state["type_cache"] = {}
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        """Restore unpickled state."""
        self.__dict__.update(state)

    def create(
        self, descriptor: str | EffectiveDescriptor, attrs: dict[str, Any] | None = None
    ) -> ModdleElement:
        """Create an instance of the type called ``descriptor``."""
        element_type = self.get_type(descriptor)

        if not element_type:
            msg = f"unknown type <{descriptor}>"
            raise ValueError(msg)

        # The factory installs an ``(attrs)`` constructor the base type cannot see.
        constructor = cast("Callable[[dict[str, Any] | None], ModdleElement]", element_type)
        return constructor(attrs)

    def get_type(self, descriptor: str | EffectiveDescriptor) -> type[ModdleElement]:
        """Return the element class for ``descriptor`` (cached by qualified name)."""
        name = descriptor if isinstance(descriptor, str) else descriptor.ns.name

        element_type = self.type_cache.get(name)

        if element_type is None:
            effective = self.registry.get_effective_descriptor(name)
            element_type = self.type_cache[name] = self.factory.create_type(effective)

        return element_type

    def create_any(
        self, name: str, ns_uri: str, properties: dict[str, Any] | None = None
    ) -> AnyModdleElement:
        """Create a generic element outside the meta-model (identity ``instance_of``)."""
        element = AnyModdleElement(name, ns_uri, self)

        def _apply(prop: object, key: str) -> None:
            """Initialize one generic property."""
            if is_object(prop):
                prop_map = cast("dict[str, Any]", prop)
                if prop_map.get("value") is not UNDEFINED:
                    element[prop_map["name"]] = prop_map["value"]
                    return
            element[key] = prop

        for_each(properties, _apply)

        return element

    def get_package(self, uri_or_prefix: str) -> RegisteredPackage | None:
        """Return a registered package by uri or prefix."""
        return self.registry.get_package(uri_or_prefix)

    def get_packages(self) -> list[RegisteredPackage]:
        """Return a snapshot of all known packages."""
        return self.registry.get_packages()

    def get_element_descriptor(
        self, element: ModdleElement | type[ModdleElement]
    ) -> EffectiveDescriptor:
        """Return the descriptor for an element (or element class)."""
        return element.descriptor_

    def has_type(self, element: object, type: object = None) -> bool:  # noqa: A002
        """Return whether ``element`` represents ``type`` (single arg means the model)."""
        if type is None:
            checked = element
            element = self
        else:
            checked = type

        owner = cast("ModdleElement", element)
        descriptor = owner.model_.get_element_descriptor(owner)

        return checked in descriptor.all_types_by_name

    def get_property_descriptor(
        self,
        element: ModdleElement | type[ModdleElement],
        property: str,  # noqa: A002
    ) -> PropertyDescriptor | None:
        """Return the descriptor of an element's named property, if known."""
        return self.get_element_descriptor(element).properties_by_name.get(property)

    def get_type_descriptor(self, type: str) -> RegisteredTypeDef | None:  # noqa: A002
        """Return the registered type definition for ``type``, if known."""
        return self.registry.type_map.get(type)
