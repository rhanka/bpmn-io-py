# Transposed from bpmn-io/moddle@3124e6a lib/properties.js (MIT).
"""Element property access transposed from moddle ``lib/properties.js``.

Read-only definitions (``writable=False``) are plain instance attributes here: Python has
no per-attribute enumerability, so the upstream getter-based definitions collapse to
``object.__setattr__``. Reference properties are tracked per descriptor instead (see
``EffectiveDescriptor.reference_names``) and skipped by the canonical projection, which
is what upstream enumerability controls.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

from bpmn_io._js import UNDEFINED
from bpmn_io._min_dash import is_string

if TYPE_CHECKING:
    from bpmn_io.moddle.base import ModdleElement
    from bpmn_io.moddle.descriptor_builder import (
        AnyTypeDescriptor,
        EffectiveDescriptor,
        PropertyDescriptor,
    )
    from bpmn_io.moddle.moddle import Moddle

__all__ = ["Properties"]


class Properties:
    """Get, set and define properties of model elements."""

    def __init__(self, model: Moddle) -> None:
        """Bind the helper to its owning model."""
        self.model = model

    def set(self, target: ModdleElement, name: str, value: object) -> None:
        """Set a named property; an ``UNDEFINED`` value unsets it."""
        if not is_string(name) or not name:
            msg = "property name must be a non-empty string"
            raise TypeError(msg)

        if name == "$type":
            # Documented in docs/naming.md: get("$type") also works.
            if value is UNDEFINED:
                vars(target).pop("type_", None)
            else:
                object.__setattr__(target, "type_", value)
            return

        prop = self.get_property(target, name)

        if value is UNDEFINED:
            # unset the property; delete from $attrs (for extensions) or the target
            if prop is not None:
                vars(target).pop(prop.name, None)
            else:
                target.attrs_.pop(_strip_global(name), None)
        elif prop is not None:
            _define_property(target, prop, value)
        else:
            target.attrs_[_strip_global(name)] = value

    def get(self, target: ModdleElement, name: str) -> object:
        """Return the named property value."""
        if name == "$type":
            # Documented in docs/naming.md: get("$type") also works.
            return getattr(target, "type_", UNDEFINED)

        prop = self.get_property(target, name)

        if prop is None:
            return target.attrs_.get(_strip_global(name), UNDEFINED)

        prop_name = prop.name

        # lazily initialize collection properties, but only when the stored value is
        # None or missing: unlike Python, every JavaScript array is truthy, so a
        # truthiness check here would wrongly re-allocate an existing empty list.
        if getattr(target, prop_name, None) is None and prop.is_many:
            _define_property(target, prop, [])

        return getattr(target, prop_name, UNDEFINED)

    def define(
        self,
        target: object,
        name: str,
        *,
        value: object = UNDEFINED,
        writable: bool = False,  # noqa: ARG002
        enumerable: bool = False,  # noqa: ARG002
    ) -> None:
        """Define ``name`` on ``target`` (read-only upstream becomes plain storage)."""
        object.__setattr__(target, name, value)

    def define_descriptor(
        self, target: object, descriptor: EffectiveDescriptor | AnyTypeDescriptor
    ) -> None:
        """Define the descriptor for an element."""
        self.define(target, "descriptor_", value=descriptor)

    def define_model(self, target: object, model: Moddle) -> None:
        """Define the model for an element."""
        self.define(target, "model_", value=model)

    def get_property(self, target: ModdleElement, name: str) -> PropertyDescriptor | None:
        """Return the property with ``name`` on the element, if it is a known one."""
        model = self.model

        prop = model.get_property_descriptor(target, name)

        if prop is not None:
            return prop

        if ":" in name:
            return None

        if model.config.get("strict") is not None:
            msg = f"unknown property <{name}> on <{target.type_}>"
            error = TypeError(msg)

            if model.config.get("strict"):
                raise error

            warnings.warn(str(error), stacklevel=2)

        return None


def _define_property(target: ModdleElement, prop: PropertyDescriptor, value: object) -> None:
    """Store ``value`` for a known property on the target element."""
    object.__setattr__(target, prop.name, value)


def _strip_global(name: str) -> str:
    """Drop one leading ``:`` so ``:xmlns`` and ``xmlns`` share one entry."""
    return name.removeprefix(":")
