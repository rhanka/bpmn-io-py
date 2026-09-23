# Transposed from bpmn-io/moddle@3124e6a lib/descriptor-builder.js (MIT).
"""Element descriptor building transposed from moddle ``lib/descriptor-builder.js``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

from bpmn_io._js import UNDEFINED
from bpmn_io.moddle.ns import Namespace, parse_name

if TYPE_CHECKING:
    from bpmn_io.moddle.registry import RegisteredPackage, RegisteredTypeDef

__all__ = [
    "AnyTypeDescriptor",
    "DescriptorBuilder",
    "EffectiveDescriptor",
    "PropertyDescriptor",
]


@dataclass
class PropertyDescriptor:
    """A registered property plus its effective (local) name and origin."""

    #: Local name after trait cloning (qualified while registered in the type map).
    name: str
    ns: Namespace
    type: str
    local_name: str
    inherited: bool = False
    defined_by: RegisteredTypeDef | None = field(default=None, compare=False)
    is_attr: bool = False
    is_many: bool = False
    is_reference: bool = False
    is_id: bool = False
    is_body: bool = False
    #: Prototype default gate: only ``UNDEFINED`` means "no default" (``None``/``False``/``0``
    #: are real defaults, as upstream which tests ``p.default !== undefined``).
    default: Any = UNDEFINED
    replaces: str | None = None
    redefines: str | None = None
    is_virtual: bool = False
    is_read_only: bool = False
    is_unique: bool = False
    subsetted_property: str | None = None
    #: Pass-through serialization hints (e.g. ``{"serialize": ...}``), read downstream.
    xml: Any = None


@dataclass
class EffectiveDescriptor:
    """The materialized descriptor of one element type."""

    ns: Namespace
    name: str
    all_types: list[RegisteredTypeDef]
    all_types_by_name: dict[str, RegisteredTypeDef]
    properties: list[PropertyDescriptor]
    properties_by_name: dict[str, PropertyDescriptor]
    body_property: PropertyDescriptor | None = None
    id_property: PropertyDescriptor | None = None
    #: Owning package (``$pkg``, non-enumerable upstream).
    pkg: RegisteredPackage | None = None

    @property
    def reference_names(self) -> frozenset[str]:
        """Return the names of reference properties (non-enumerable upstream)."""
        return frozenset(p.name for p in self.properties if p.is_reference)


@dataclass(frozen=True)
class AnyTypeDescriptor:
    """The generic ``{name, isGeneric, ns}`` descriptor of ``createAny`` elements."""

    name: str
    ns_prefix: str | None
    ns_local_name: str
    ns_uri: str
    is_generic: bool = True


class DescriptorBuilder:
    """A utility to build element descriptors."""

    def __init__(self, name_ns: Namespace) -> None:
        """Create a builder for the type called ``name_ns``."""
        self.ns = name_ns
        self.name = name_ns.name
        self.all_types: list[RegisteredTypeDef] = []
        self.all_types_by_name: dict[str, RegisteredTypeDef] = {}
        self.properties: list[PropertyDescriptor] = []
        self.properties_by_name: dict[str, PropertyDescriptor] = {}
        self.body_property: PropertyDescriptor | None = None
        self.id_property: PropertyDescriptor | None = None

    def build(self) -> EffectiveDescriptor:
        """Return the effective descriptor built so far."""
        return EffectiveDescriptor(
            ns=self.ns,
            name=self.name,
            all_types=self.all_types,
            all_types_by_name=self.all_types_by_name,
            properties=self.properties,
            properties_by_name=self.properties_by_name,
            body_property=self.body_property,
            id_property=self.id_property,
        )

    def add_property(
        self,
        prop: PropertyDescriptor,
        idx: int | bool | None = None,  # noqa: FBT001
        validate: bool = True,  # noqa: FBT001, FBT002
    ) -> None:
        """Add a property at ``idx`` (a boolean ``idx`` means ``validate``)."""
        if isinstance(idx, bool):
            validate = idx
            idx = None

        self.add_named_property(prop, validate)

        if idx is not None:
            self.properties.insert(idx, prop)
        else:
            self.properties.append(prop)

    def replace_property(
        self,
        old_property: PropertyDescriptor,
        new_property: PropertyDescriptor,
        replace: str | None,
    ) -> None:
        """Refine ``old_property`` with ``new_property`` (replaces appends, redefines keep)."""
        old_name_ns = old_property.ns

        rename = old_property.name != new_property.name

        if old_property.is_id:
            if not new_property.is_id:
                msg = (
                    "property <"
                    + new_property.ns.name
                    + "> must be id property "
                    + "to refine <"
                    + old_property.ns.name
                    + ">"
                )
                raise ValueError(msg)

            self.set_id_property(new_property, validate=False)

        if old_property.is_body:
            if not new_property.is_body:
                msg = (
                    "property <"
                    + new_property.ns.name
                    + "> must be body property "
                    + "to refine <"
                    + old_property.ns.name
                    + ">"
                )
                raise ValueError(msg)

            # TODO: Check compatibility
            self.set_body_property(new_property, validate=False)

        # validate existence and get location of old property
        idx = -1
        for pos, candidate in enumerate(self.properties):
            if candidate is old_property:
                idx = pos
                break
        if idx == -1:
            msg = "property <" + old_name_ns.name + "> not found in property list"
            raise ValueError(msg)

        # remove old property
        del self.properties[idx]

        # replacing the named property is intentional
        #
        #  * validate only if this is a "rename" operation
        #  * add at specific index unless we "replace"
        #
        self.add_property(new_property, None if replace else idx, rename)

        # make new property available under old name
        self.properties_by_name[old_name_ns.name] = new_property
        self.properties_by_name[old_name_ns.local_name] = new_property

    def redefine_property(
        self, prop: PropertyDescriptor, target_property_name: str, replace: str | None
    ) -> None:
        """Refine the ``Target#attr`` property named by ``replaces``/``redefines``."""
        ns_prefix = prop.ns.prefix
        parts = target_property_name.split("#")

        name = parse_name(parts[0], ns_prefix)
        attr_name = parse_name(parts[1], name.prefix).name

        redefined_property = self.properties_by_name.get(attr_name)
        if redefined_property is None:
            msg = "refined property <" + attr_name + "> not found"
            raise ValueError(msg)

        self.replace_property(redefined_property, prop, replace)

        prop.redefines = None

    def add_named_property(
        self,
        prop: PropertyDescriptor,
        validate: bool,  # noqa: FBT001
    ) -> None:
        """Register a property under both its qualified and local names."""
        ns = prop.ns

        if validate:
            self.assert_not_defined(prop, ns.name)
            self.assert_not_defined(prop, ns.local_name)

        self.properties_by_name[ns.name] = prop
        self.properties_by_name[ns.local_name] = prop

    def remove_named_property(self, prop: PropertyDescriptor) -> None:
        """Unregister a property (uncalled upstream; kept for surface parity)."""
        ns = prop.ns

        self.properties_by_name.pop(ns.name, None)
        self.properties_by_name.pop(ns.local_name, None)

    def set_body_property(
        self,
        prop: PropertyDescriptor,
        validate: bool = True,  # noqa: FBT001, FBT002
    ) -> None:
        """Set the body property, optionally guarding against duplicates."""
        if validate and self.body_property is not None:
            msg = (
                "body property defined multiple times "
                "(<" + self.body_property.ns.name + ">, <" + prop.ns.name + ">)"
            )
            raise ValueError(msg)

        self.body_property = prop

    def set_id_property(
        self,
        prop: PropertyDescriptor,
        validate: bool = True,  # noqa: FBT001, FBT002
    ) -> None:
        """Set the id property, optionally guarding against duplicates."""
        if validate and self.id_property is not None:
            msg = (
                "id property defined multiple times "
                "(<" + self.id_property.ns.name + ">, <" + prop.ns.name + ">)"
            )
            raise ValueError(msg)

        self.id_property = prop

    def assert_not_trait(self, type_descriptor: RegisteredTypeDef) -> None:
        """Reject direct materialization of a trait type."""
        extends = type_descriptor.get("extends") or []

        if extends:
            msg = f"cannot create <{type_descriptor['name']}> extending <{','.join(extends)}>"
            raise ValueError(msg)

    def assert_not_defined(self, prop: PropertyDescriptor, name: str) -> None:  # noqa: ARG002
        """Reject redefinition of a property without ``redefines``."""
        defined_property = self.properties_by_name.get(prop.name)

        if defined_property is not None:
            before = cast("RegisteredTypeDef", defined_property.defined_by)
            after = cast("RegisteredTypeDef", prop.defined_by)
            msg = (
                "property <"
                + prop.name
                + "> already defined; "
                + "override of <"
                + before["ns"].name
                + "#"
                + defined_property.ns.name
                + "> by "
                + "<"
                + after["ns"].name
                + "#"
                + prop.ns.name
                + "> not allowed without redefines"
            )
            raise ValueError(msg)

    def has_property(self, name: str) -> PropertyDescriptor | None:
        """Return the property registered under ``name``, if any."""
        return self.properties_by_name.get(name)

    def add_trait(
        self,
        trait: RegisteredTypeDef,
        inherited: bool,  # noqa: FBT001
    ) -> None:
        """Fold one type of the hierarchy into this descriptor."""
        if inherited:
            self.assert_not_trait(trait)

        type_name = cast("str", trait.get("name"))

        if type_name in self.all_types_by_name:
            return

        for raw in trait.get("properties") or []:
            raw_ns = raw.get("ns")
            prop = PropertyDescriptor(
                name=raw_ns.local_name,
                ns=raw_ns,
                type=raw.get("type"),
                local_name=raw_ns.local_name,
                inherited=inherited,
                defined_by=trait,
                is_attr=bool(raw.get("isAttr", False)),
                is_many=bool(raw.get("isMany", False)),
                is_reference=bool(raw.get("isReference", False)),
                is_id=bool(raw.get("isId", False)),
                is_body=bool(raw.get("isBody", False)),
                default=raw.get("default", UNDEFINED),
                replaces=raw.get("replaces"),
                redefines=raw.get("redefines"),
                is_virtual=bool(raw.get("isVirtual", False)),
                is_read_only=bool(raw.get("isReadOnly", False)),
                is_unique=bool(raw.get("isUnique", False)),
                subsetted_property=raw.get("subsettedProperty"),
                xml=raw.get("xml"),
            )

            replaces = prop.replaces
            redefines = prop.redefines

            # add replace/redefine support
            if replaces or redefines:
                self.redefine_property(prop, replaces or redefines or "", replaces)
            else:
                if prop.is_body:
                    self.set_body_property(prop)
                if prop.is_id:
                    self.set_id_property(prop)
                self.add_property(prop)

        self.all_types.append(trait)
        self.all_types_by_name[type_name] = trait
