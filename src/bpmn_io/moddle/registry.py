# Transposed from bpmn-io/moddle@3124e6a lib/registry.js (MIT).
"""Package and type registry transposed from moddle ``lib/registry.js``.

Traversal is iterative: ``map_types`` uses an explicit stack reproducing the exact
upstream visit order (superclasses depth-first in order, then self, then traits in
order). Registered packages and types stay plain dicts, as upstream plain objects;
``dict`` lookups miss safely for ``constructor``/``__proto__``-style names.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bpmn_io._min_dash import for_each
from bpmn_io.moddle.descriptor_builder import DescriptorBuilder, EffectiveDescriptor
from bpmn_io.moddle.ns import Namespace, parse_name
from bpmn_io.moddle.types import is_built_in

if TYPE_CHECKING:
    from collections.abc import Callable

    from bpmn_io.moddle.properties import Properties

__all__ = [
    "PackageDef",
    "RegisteredPackage",
    "RegisteredTypeDef",
    "Registry",
]

#: A package definition, as declared in a descriptor file.
PackageDef = dict[str, Any]

#: A registered package (a shallow copy of its definition).
RegisteredPackage = dict[str, Any]

#: A registered type (copied, namespaced, and linked to its package).
RegisteredTypeDef = dict[str, Any]


class Registry:
    """A registry of moddle packages."""

    def __init__(
        self, packages: list[PackageDef] | dict[str, PackageDef], properties: Properties
    ) -> None:
        """Register ``packages`` (a list or a name-keyed map)."""
        self.package_map: dict[str, RegisteredPackage] = {}
        self.type_map: dict[str, RegisteredTypeDef] = {}
        self.packages: list[RegisteredPackage] = []
        self.properties = properties

        for_each(packages, self.register_package)

    def get_package(self, uri_or_prefix: str) -> RegisteredPackage | None:
        """Return the registered package for a namespace uri or prefix."""
        return self.package_map.get(uri_or_prefix)

    def get_packages(self) -> list[RegisteredPackage]:
        """Return all registered packages."""
        return self.packages

    def register_package(self, pkg: PackageDef, _key: object = None) -> None:
        """Register one package and all of its types."""
        # copy package
        pkg = dict(pkg)

        _ensure_available(self.package_map, pkg, "prefix")
        _ensure_available(self.package_map, pkg, "uri")

        # register types
        for descriptor in pkg.get("types") or []:
            self.register_type(descriptor, pkg)

        self.package_map[pkg["uri"]] = pkg
        self.package_map[pkg["prefix"]] = pkg
        self.packages.append(pkg)

    def register_type(self, type_def: PackageDef, pkg: RegisteredPackage) -> None:
        """Register one type of ``pkg`` (properties are namespaced in place)."""
        type_def = {
            **type_def,
            "superClass": list(type_def.get("superClass") or []),
            "extends": list(type_def.get("extends") or []),
            "properties": list(type_def.get("properties") or []),
            "meta": dict(type_def.get("meta") or {}),
        }

        ns = parse_name(type_def["name"], pkg.get("prefix"))
        name = ns.name
        properties_by_name: dict[str, Any] = {}

        # parse properties
        for prop in type_def["properties"]:
            # namespace property names
            property_ns = parse_name(prop["name"], ns.prefix)
            property_name = property_ns.name

            # namespace property types
            if not is_built_in(prop["type"]):
                prop["type"] = parse_name(prop["type"], property_ns.prefix).name

            prop["ns"] = property_ns
            prop["name"] = property_name

            properties_by_name[property_name] = prop

        # update ns + name
        type_def["ns"] = ns
        type_def["name"] = name
        type_def["propertiesByName"] = properties_by_name

        for extends_name in type_def["extends"]:
            extends_name_ns = parse_name(extends_name, ns.prefix)

            extended = self.type_map[extends_name_ns.name]

            traits = extended.get("traits")
            if traits is None:
                traits = extended["traits"] = []
            traits.append(name)

        # link to package
        self.define_package(type_def, pkg)

        # register
        self.type_map[name] = type_def

    def map_types(
        self,
        ns_name: Namespace,
        iterator: Callable[[RegisteredTypeDef, bool], None],
        trait: bool = False,  # noqa: FBT001, FBT002
    ) -> None:
        """Walk the hierarchy bottom-up, calling ``iterator(type, inherited)``.

        Superclasses come first (depth-first, in order, staying traits under a trait),
        then the type itself with ``inherited = not trait``, then traits in order.
        """
        # Each frame is [ns_name, trait, phase, resolved type, pending children].
        stack: list[list[Any]] = [[ns_name, trait, 0, None, None]]
        while stack:
            frame = stack[-1]
            phase = frame[2]
            if phase == 0:
                current_ns = frame[0]
                current_trait = frame[1]
                if is_built_in(current_ns.name):
                    resolved: RegisteredTypeDef = {"name": current_ns.name}
                else:
                    found = self.type_map.get(current_ns.name)
                    if found is None:
                        msg = "unknown type <" + current_ns.name + ">"
                        raise ValueError(msg)
                    resolved = found
                supers = [
                    parse_name(cls, "" if is_built_in(cls) else current_ns.prefix)
                    for cls in resolved.get("superClass") or []
                ]
                frame[3] = resolved
                frame[4] = current_trait
                frame[2] = 1
                stack.extend(
                    [child_ns, current_trait, 0, None, None] for child_ns in reversed(supers)
                )
            elif phase == 1:
                resolved = frame[3]
                current_trait = frame[4]
                current_ns = frame[0]
                iterator(resolved, not current_trait)
                traits = [
                    parse_name(cls, "" if is_built_in(cls) else current_ns.prefix)
                    for cls in resolved.get("traits") or []
                ]
                frame[2] = 2
                stack.extend([child_ns, True, 0, None, None] for child_ns in reversed(traits))
            else:
                stack.pop()

    def get_effective_descriptor(self, name: str) -> EffectiveDescriptor:
        """Return the effective descriptor for the type called ``name``."""
        ns_name = parse_name(name)

        builder = DescriptorBuilder(ns_name)

        def _collect(
            type_def: RegisteredTypeDef,
            inherited: bool,  # noqa: FBT001
        ) -> None:
            """Fold one visited type into the builder."""
            builder.add_trait(type_def, inherited)

        self.map_types(ns_name, _collect)

        descriptor = builder.build()

        # define package link
        last_type = descriptor.all_types[-1]
        self.define_package(descriptor, last_type["$pkg"])

        return descriptor

    def define_package(self, target: EffectiveDescriptor | RegisteredTypeDef, pkg: object) -> None:
        """Link ``target`` to its package (``$pkg``, non-enumerable upstream)."""
        if isinstance(target, dict):
            target["$pkg"] = pkg
        else:
            self.properties.define(target, "pkg", value=pkg)


def _ensure_available(
    package_map: dict[str, RegisteredPackage], pkg: PackageDef, identifier_key: str
) -> None:
    """Reject packages whose ``identifier_key`` is already registered."""
    value = pkg.get(identifier_key)

    if value in package_map:
        msg = "package with " + identifier_key + " <" + str(value) + ">"
        raise ValueError(msg)
