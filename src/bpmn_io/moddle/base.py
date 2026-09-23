# Transposed from bpmn-io/moddle@3124e6a lib/base.js (MIT).
"""Moddle base element transposed from moddle ``lib/base.js``.

Model properties live in the instance ``__dict__`` under their local names, exactly
like JavaScript own-properties. There are no ``__getattr__``/``__setattr__`` overrides,
so dunders are never intercepted and ``copy``, ``pickle``, ``hasattr`` and debugger
introspection behave normally. Keyword-named properties (``from``, ``import``, ``type``)
are stored normally and reached via ``get``/``set`` and ``getattr``.
"""

from __future__ import annotations

import copyreg
from typing import TYPE_CHECKING, Any, cast

from bpmn_io._js import UNDEFINED, UndefinedType
from bpmn_io._min_dash import set as _set_path
from bpmn_io.moddle.descriptor_builder import AnyTypeDescriptor
from bpmn_io.moddle.ns import parse_name

if TYPE_CHECKING:
    from collections.abc import Callable

    from bpmn_io.moddle.descriptor_builder import EffectiveDescriptor
    from bpmn_io.moddle.moddle import Moddle


def _reduce_undefined(_value: UndefinedType) -> str:
    """Pickle the ``UNDEFINED`` singleton by name (preserving identity)."""
    return "UNDEFINED"


# Dynamic element classes have no import path, so instances rebuild through the model;
# the singleton keeps its identity across copies and pickles through this registration.
copyreg.pickle(UndefinedType, _reduce_undefined)

__all__ = ["AnyModdleElement", "Base", "ModdleElement"]

#: Instance members excluded from the canonical projection (non-enumerable upstream).
_SPECIAL_NAMES: tuple[str, ...] = ("attrs_", "parent_", "model_", "descriptor_")


class Base:
    """Moddle base element."""

    if TYPE_CHECKING:
        #: Owning model (bound per element class by the factory).
        model_: Moddle

    def get(self, name: str) -> object:
        """Return the named property value."""
        return self.model_.properties.get(cast("ModdleElement", self), name)

    def set(self, name: str, value: object) -> None:
        """Set the named property value."""
        self.model_.properties.set(cast("ModdleElement", self), name, value)

    def to_canonical_dict(self) -> dict[str, Any]:
        """Project the element to plain JSON-like data (the ``json_equal`` protocol).

        Mirrors what upstream ``JSON.stringify`` sees: the ``$type`` under its ``$``-key,
        defined non-reference properties in insertion order, and none of the internal
        members (``$attrs``/``$parent``/``$model``/``$descriptor``) or reference
        properties (non-enumerable upstream). Nested elements resolve through this same
        protocol in the caller.
        """
        raw = vars(self)
        descriptor = getattr(self, "descriptor_", None)
        references: frozenset[str] = getattr(descriptor, "reference_names", frozenset())
        result: dict[str, Any] = {}
        for key, value in raw.items():
            if key == "type_":
                result["$type"] = value
            elif key in _SPECIAL_NAMES or key in references:
                continue
            else:
                result[key] = value
        return result


class ModdleElement(Base):
    """A typed model element instance (shape built by the factory)."""

    #: Qualified type name (the only enumerable special, as upstream).
    type_: str
    #: Extension attributes (unknown properties land here, keyed without leading ``:``).
    attrs_: dict[str, Any]
    #: Containing element, if any.
    parent_: ModdleElement | AnyModdleElement | None
    #: Effective descriptor of the element type.
    descriptor_: EffectiveDescriptor

    def instance_of(self, type: str) -> bool:  # noqa: A002
        """Return whether this element is of the given type."""
        return self.model_.has_type(self, type)

    def __reduce__(
        self,
    ) -> tuple[Callable[..., ModdleElement], tuple[Moddle, str], dict[str, Any]]:
        """Rebuild through the owning model (dynamic classes have no import path)."""
        return (_rebuild_element, (self.model_, self.type_), dict(vars(self)))


class AnyModdleElement(Base):
    """A generic (untyped) element, as created by ``Moddle.create_any``.

    Behaves like a plain JavaScript object: properties are readable both as attributes
    and as items. The ``get``/``set``/``instance_of`` accessors live on the class (they
    are non-enumerable upstream), so they never leak into the instance mapping.
    """

    #: Qualified type name, exactly as passed to ``create_any``.
    type_: str
    #: Containing element, if any.
    parent_: ModdleElement | AnyModdleElement | None
    #: Generic ``{name, isGeneric, ns}`` descriptor.
    descriptor_: AnyTypeDescriptor

    def __init__(self, name: str, ns_uri: str, model: Moddle) -> None:
        """Create a generic element of ``name`` in the ``ns_uri`` namespace."""
        name_ns = parse_name(name)
        props = model.properties
        props.define(self, "type_", value=name)
        props.define_descriptor(
            self,
            AnyTypeDescriptor(
                name=name,
                ns_prefix=name_ns.prefix,
                ns_local_name=name_ns.local_name,
                ns_uri=ns_uri,
            ),
        )
        props.define_model(self, model)
        props.define(self, "parent_", writable=True)

    def get(self, name: str) -> object:
        """Return the stored value under ``name`` (``UNDEFINED`` when absent)."""
        return getattr(self, name, UNDEFINED)

    def set(self, name: str, value: object) -> None:
        """Set the stored value under ``name`` (guarded, as upstream)."""
        _set_path(self, [name], value)

    def instance_of(self, type: str) -> bool:  # noqa: A002
        """Return whether ``type`` strictly equals this element type."""
        return type == self.type_

    def __getitem__(self, key: str) -> object:
        """Read one stored value (item access mirrors attribute access)."""
        return self.get(key)

    def __setitem__(self, key: str, value: object) -> None:
        """Write one stored value (item access mirrors attribute access)."""
        self.set(key, value)

    def __contains__(self, key: object) -> bool:
        """Return whether one stored value exists under ``key``."""
        return isinstance(key, str) and hasattr(self, key)


def _rebuild_element(model: Moddle, type_name: str) -> ModdleElement:
    """Create a blank element for unpickling (state is applied by the caller)."""
    return model.create(type_name)
