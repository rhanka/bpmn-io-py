"""Lot-3 import ID-remapping migration (DESIGN §5.2, H B14, H9).

``remap_ids`` applies one approved, closed ``id-remap`` command record to an
envelope and its archived Snapshot/1 diagrams at once: element ids, every
descriptor reference value, binding owner/target ids and the ``bpmnElement``
values naming remapped semantic elements. The total map (command rows plus
identity elsewhere) is built before application and must be injective over
the retained ids. Members attested reference-free are kept byte for byte;
dangling native references and external QName references are kept and
observed, never fetched.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, NamedTuple

from bpmn_io.profile._c14n import digest
from bpmn_io.profile._cn_context import (
    Prefix,
    build_tree_index,
    check_compat,
    check_compiled,
    refuse_result,
    to_wire_envelope,
)
from bpmn_io.profile._cn_plan import _RefusalError, _refuse
from bpmn_io.profile._envelope import (
    check_envelope_integrity,
    check_envelope_shape,
    complete_envelope,
)
from bpmn_io.profile._evaluate import _MAX_ELEMENTS
from bpmn_io.profile._results import (
    Coordinate,
    Report,
    ReportEntry,
    ResultRefused,
    ResultSuccess,
    result_success,
)

if TYPE_CHECKING:
    from bpmn_io.profile._compiler import CompiledProfile

#: Authoring-subset grammar for migration result ids (H C20).
_ID_GRAMMAR = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,255}\Z")

_COMMAND_KEYS = frozenset({"kind", "approved", "approval", "map", "referenceFreeAttestations"})
_MAP_KEYS = frozenset({"sourceId", "resultId", "domain"})
_ATTESTATION_KEYS = frozenset({"property", "referenceFree", "descriptor"})
_DESCRIPTOR_KEYS = frozenset({"id", "version", "sha256"})
_NAMESPACE_KEYS = frozenset({"prefix", "uri"})
_SNAPSHOT_KEYS = frozenset({"descriptorDigest", "diagrams", "sha256"})


class _RemapPlan(NamedTuple):
    """Validated remap state: prefix, total map and migration tables."""

    outcome: Prefix
    total: dict[str, str]
    namespaces: dict[str, str]
    covered: frozenset[tuple[str, str]]
    ref_fields: frozenset[tuple[str, str]]
    own_namespace: str | None
    elements: list[dict[str, Any]]
    ids: list[str]
    diagrams: list[object]
    record_digest: str
    identity: dict[str, Any]
    revision: str


def _check_command(
    command: object,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    """Validate one closed migration command (raises ``operation-error``)."""
    if not isinstance(command, Mapping):
        _refuse("operation-error")
    keys = set(command.keys())
    if (
        keys - _COMMAND_KEYS - {"namespaces"}
        or not {
            "kind",
            "approved",
            "approval",
            "map",
            "referenceFreeAttestations",
        }
        <= keys
    ):
        _refuse("operation-error")
    if command.get("kind") != "id-remap":
        _refuse("operation-error")
    if command.get("approved") is not True:
        _refuse("operation-error")
    approval = command.get("approval")
    if not isinstance(approval, str) or not approval:
        _refuse("operation-error")
    rows = _check_map_shape(command.get("map"))
    attestations = _check_attestation_shape(command.get("referenceFreeAttestations"))
    namespaces = _check_namespace_shape(command.get("namespaces"))
    return rows, attestations, namespaces


def _check_map_shape(rows: object) -> list[dict[str, Any]]:
    """Validate closed migration map rows (raises ``operation-error``)."""
    if not isinstance(rows, list):
        _refuse("operation-error")
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping) or set(row.keys()) != _MAP_KEYS:
            _refuse("operation-error")
        source = row.get("sourceId")
        result = row.get("resultId")
        domain = row.get("domain")
        if not isinstance(source, str) or not isinstance(result, str) or domain != "migration":
            _refuse("operation-error")
        if source in seen:
            _refuse("operation-error")
        seen.add(source)
    return list(rows)


def _check_attestation_shape(attestations: object) -> list[dict[str, Any]]:
    """Validate closed reference-free attestations (raises ``operation-error``)."""
    if not isinstance(attestations, list):
        _refuse("operation-error")
    for record in attestations:
        if not isinstance(record, Mapping) or set(record.keys()) != _ATTESTATION_KEYS:
            _refuse("operation-error")
        descriptor = record.get("descriptor")
        if (
            not isinstance(record.get("property"), str)
            or record.get("referenceFree") is not True
            or not isinstance(descriptor, Mapping)
            or set(descriptor.keys()) != _DESCRIPTOR_KEYS
            or not isinstance(descriptor.get("id"), str)
            or not isinstance(descriptor.get("version"), str)
            or not isinstance(descriptor.get("sha256"), str)
        ):
            _refuse("operation-error")
    return list(attestations)


def _check_namespace_shape(declared: object) -> dict[str, str]:
    """Validate optional captured namespaces (raises ``operation-error``)."""
    namespaces: dict[str, str] = {}
    if declared is None:
        return namespaces
    if not isinstance(declared, list):
        _refuse("operation-error")
    seen_rows: set[tuple[str, str]] = set()
    for record in declared:
        if not isinstance(record, Mapping) or set(record.keys()) != _NAMESPACE_KEYS:
            _refuse("operation-error")
        prefix = record.get("prefix")
        uri = record.get("uri")
        if not isinstance(prefix, str) or not prefix or not isinstance(uri, str) or not uri:
            _refuse("operation-error")
        if (prefix, uri) in seen_rows:
            _refuse("operation-error")
        seen_rows.add((prefix, uri))
        namespaces.setdefault(prefix, uri)
    return namespaces


def _check_imported_di(imported_di: object) -> tuple[str, list[object]]:
    """Validate one closed Snapshot/1 record (raises ``snapshot-schema``)."""
    if not isinstance(imported_di, Mapping) or set(imported_di.keys()) != _SNAPSHOT_KEYS:
        _refuse("snapshot-schema")
    record_digest = imported_di.get("descriptorDigest")
    diagrams = imported_di.get("diagrams")
    sha256 = imported_di.get("sha256")
    if (
        not isinstance(record_digest, str)
        or not isinstance(diagrams, list)
        or not isinstance(sha256, str)
    ):
        _refuse("snapshot-schema")
    if digest({"descriptorDigest": record_digest, "diagrams": diagrams}) != sha256:
        _refuse("snapshot-schema")
    return record_digest, diagrams


def _descriptor_pins(compiled: CompiledProfile) -> list[dict[str, object]]:
    """Return the §9.2 descriptor pins of one compiled identity."""
    identity = compiled.identity
    descriptors = identity.get("descriptors")
    if not isinstance(descriptors, list):
        _refuse("descriptor-mismatch")
    pins: list[dict[str, object]] = []
    for pin in descriptors:
        if (
            not isinstance(pin, Mapping)
            or set(pin.keys()) != _DESCRIPTOR_KEYS
            or not isinstance(pin.get("id"), str)
        ):
            _refuse("descriptor-mismatch")
        pins.append(
            {"id": pin.get("id"), "version": pin.get("version"), "sha256": pin.get("sha256")}
        )
    return pins


def _descriptor_digest(pins: list[dict[str, object]]) -> str:
    """Return the §9.2 digest H(descriptor pins sorted by unique id)."""

    def _key(pin: dict[str, object]) -> bytes:
        value = pin.get("id")
        return str(value).encode("utf-16-be")

    return digest(sorted(pins, key=_key))


def _walk_elements(tree: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect the ``$type`` elements of one tree in pre-order (bounded)."""
    found: list[dict[str, Any]] = []
    stack: list[object] = [tree]
    while stack and len(found) < _MAX_ELEMENTS:
        current = stack.pop()
        if isinstance(current, dict):
            if isinstance(current.get("$type"), str):
                found.append(current)
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return found


def _classified_members(
    types: dict[str, dict[str, Any]],
    type_name: str,
    ref_fields: frozenset[tuple[str, str]],
) -> set[str] | None:
    """Return the descriptor-classified members of one type (None when unknown).

    The compiled ``ref_fields`` (id-valued scalars such as ``calledElement``)
    classify alongside the descriptor sections.
    """
    spec = types.get(type_name)
    if spec is None:
        return None
    members = {"$type", "id"}
    scalars = spec.get("scalars")
    if isinstance(scalars, (list, tuple)):
        members.update(str(item) for item in scalars)
    for key in ("references", "containment"):
        fields = spec.get(key)
        if isinstance(fields, dict):
            members.update(str(item) for item in fields)
    members.update(member for (owner, member) in ref_fields if owner == type_name)
    return members


def _element_ids(elements: list[dict[str, Any]]) -> list[str]:
    """Collect element ids in walk order (raises on repetition)."""
    ids: list[str] = []
    seen: set[str] = set()
    for element in elements:
        element_id = element.get("id")
        if not isinstance(element_id, str):
            continue
        if element_id in seen:
            _refuse("id-collision")
        seen.add(element_id)
        ids.append(element_id)
    return ids


def _check_map_rows(rows: list[dict[str, Any]], known: set[str]) -> list[tuple[str, str]]:
    """Check map rows in UTF-16 source order (raises on dangling/grammar)."""
    ordered = sorted(rows, key=lambda row: str(row.get("sourceId")).encode("utf-16-be"))
    checked: list[tuple[str, str]] = []
    for row in ordered:
        source = row.get("sourceId")
        result = row.get("resultId")
        if source not in known:
            _refuse("reference-dangling")
        if not isinstance(result, str) or _ID_GRAMMAR.fullmatch(result) is None:
            _refuse("profile-schema")
        checked.append((str(source), str(result)))
    return checked


def _check_opaque(
    elements: list[dict[str, Any]],
    types: dict[str, dict[str, Any]],
    ref_fields: frozenset[tuple[str, str]],
    covered: frozenset[tuple[str, str]],
) -> None:
    """Refuse unclassified, unattested members (``migration-reference-opaque``)."""
    for element in elements:
        type_name = element.get("$type")
        if not isinstance(type_name, str):
            continue
        allowed = _classified_members(types, type_name, ref_fields)
        for member in element:
            if member in ("$type", "id"):
                continue
            if allowed is not None and member in allowed:
                continue
            if (type_name, member) in covered:
                continue
            _refuse("migration-reference-opaque")


def _covered_members(
    attestations: list[dict[str, Any]],
    pins: list[dict[str, object]],
) -> frozenset[tuple[str, str]]:
    """Return the attested reference-free ``(type, member)`` pairs."""
    covered: set[tuple[str, str]] = set()
    for record in attestations:
        prop = record.get("property")
        descriptor = record.get("descriptor")
        if not isinstance(prop, str) or not isinstance(descriptor, Mapping):
            continue
        pair = prop.rsplit(".", 1)
        if len(pair) != 2:
            continue
        candidate = {
            "id": descriptor.get("id"),
            "version": descriptor.get("version"),
            "sha256": descriptor.get("sha256"),
        }
        if any(
            pin.get("id") == candidate["id"]
            and pin.get("version") == candidate["version"]
            and pin.get("sha256") == candidate["sha256"]
            for pin in pins
        ):
            covered.add((pair[0], pair[1]))
    return frozenset(covered)


def _escape_segment(segment: str) -> str:
    """Escape one RFC 6901 pointer segment."""
    return segment.replace("~", "~0").replace("/", "~1")


def _reference_members(
    types: dict[str, dict[str, Any]],
    type_name: str,
    ref_fields: frozenset[tuple[str, str]],
) -> set[str]:
    """Return the reference properties of one type (descriptor plus idRefs)."""
    found: set[str] = set()
    spec = types.get(type_name)
    if spec is not None:
        fields = spec.get("references")
        if isinstance(fields, dict):
            found.update(str(key) for key in fields)
    found.update(member for (owner, member) in ref_fields if owner == type_name)
    return found


class _Rewriter:
    """Atomic total-map rewrite over one owned tree copy (DESIGN §5.2)."""

    def __init__(self, plan: _RemapPlan, types: dict[str, dict[str, Any]]) -> None:
        self.total = plan.total
        self.namespaces = plan.namespaces
        self.own_namespace = plan.own_namespace
        self.covered = plan.covered
        self.types = types
        self.ref_fields = plan.ref_fields
        self.entries: list[ReportEntry] = []

    def _observe(  # noqa: PLR0913, PLR0917 - one observed-value fact set per call
        self,
        code: str,
        value: str,
        pointer: str,
        target_id: str | None,
        prop: str,
        domain: Literal["tree", "artifact"] = "tree",
    ) -> None:
        """Record one kept-but-reported reference value (§6.6)."""
        coordinate = Coordinate(
            domain=domain,
            pointer=pointer,
            target_id=target_id,
            provenance="exact",
        )
        self.entries.append(
            ReportEntry(
                code=code,
                severity="error",
                classification="integrity",
                stage="import",
                rule_id="remap-ids",
                message_key=code,
                disposition="observed",
                source=coordinate,
                result=coordinate,
                before_present=True,
                after_present=True,
                before=value,
                after=value,
                property=prop,
            )
        )

    def rewrite_reference(self, value: str, element_id: str | None, pointer: str, prop: str) -> str:
        """Rewrite one reference value (kept values are observed)."""
        if not value:
            return value
        if value in self.total:
            return self.total[value]
        prefix, separator, local = value.partition(":")
        if separator and prefix in self.namespaces:
            if self.namespaces[prefix] == self.own_namespace and self.own_namespace is not None:
                if local in self.total:
                    return f"{prefix}:{self.total[local]}"
            else:
                self._observe("unsupported-namespace", value, pointer, element_id, prop)
                return value
        self._observe("reference-dangling", value, pointer, element_id, prop)
        return value

    def rewrite_tree(self, tree: dict[str, Any]) -> None:
        """Rewrite one owned tree in place (ids, references, no fetches)."""
        stack: list[tuple[dict[str, Any], str]] = [(tree, "")]
        while stack:
            node, pointer = stack.pop()
            self._rewrite_object(node, pointer)
            for key, item in node.items():
                child = f"{pointer}/{_escape_segment(key)}"
                if isinstance(item, dict):
                    stack.append((item, child))
                elif isinstance(item, list):
                    for position, entry in enumerate(item):
                        if isinstance(entry, dict):
                            stack.append((entry, f"{child}/{position}"))

    def _rewrite_object(self, node: dict[str, Any], pointer: str) -> None:
        """Rewrite one owned object (ids and reference members)."""
        type_name = node.get("$type")
        if not isinstance(type_name, str):
            return
        element_id = node.get("id")
        if isinstance(element_id, str):
            node["id"] = self.total.get(element_id, element_id)
        references = _reference_members(self.types, type_name, self.ref_fields)
        for key in list(node.keys()):
            if key in ("$type", "id") or (type_name, key) in self.covered:
                continue
            if key in references:
                child = f"{pointer}/{_escape_segment(key)}"
                node[key] = self._rewrite_member(node[key], node.get("id"), child, key)

    def _rewrite_member(self, item: object, element_id: object, pointer: str, prop: str) -> object:
        """Rewrite one reference member value (strings and array items)."""
        target = element_id if isinstance(element_id, str) else None
        if isinstance(item, str):
            return self.rewrite_reference(item, target, pointer, prop)
        if isinstance(item, list):
            return [
                self.rewrite_reference(entry, target, pointer, prop)
                if isinstance(entry, str)
                else entry
                for entry in item
            ]
        return item

    def rewrite_diagrams(self, diagrams: list[object]) -> list[object]:
        """Rewrite owned diagrams (``bpmnElement`` only, DI ids kept)."""
        stack: list[tuple[object, str]] = [(diagrams, "/importedDi/diagrams")]
        while stack:
            current, pointer = stack.pop()
            if isinstance(current, dict):
                value = current.get("bpmnElement")
                if isinstance(value, str):
                    if value in self.total:
                        current["bpmnElement"] = self.total[value]
                    else:
                        holder = current.get("id")
                        self._observe(
                            "reference-dangling",
                            value,
                            f"{pointer}/bpmnElement",
                            holder if isinstance(holder, str) else None,
                            "bpmnElement",
                            domain="artifact",
                        )
                for key, item in current.items():
                    if key in ("id", "bpmnElement"):
                        continue
                    self._push_diagram(item, f"{pointer}/{_escape_segment(key)}", stack)
            elif isinstance(current, list):
                for position, entry in enumerate(current):
                    self._push_diagram(entry, f"{pointer}/{position}", stack)
        return diagrams

    def _push_diagram(self, item: object, pointer: str, stack: list[tuple[object, str]]) -> None:
        """Queue one diagram slot for the owned rewrite walk."""
        if isinstance(item, (dict, list)):
            stack.append((item, pointer))


def _check_envelope_steps(
    compiled: CompiledProfile, wire: object
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], str]:
    """Run the §5.0 steps 2-4 envelope checks (raises the refusal code)."""
    if not isinstance(wire, dict):
        _refuse("profile-schema")
    failed = check_envelope_shape(wire)
    if failed is not None:
        _refuse(failed)
    failed = check_compat(compiled, wire)
    if failed is not None:
        _refuse(failed)
    failed = check_envelope_integrity(wire)
    if failed is not None:
        _refuse(failed)
    tree = wire.get("tree")
    bindings = wire.get("bindings")
    identity = wire.get("profileIdentity")
    revision = wire.get("semanticRevision")
    if (
        not isinstance(tree, dict)
        or not isinstance(bindings, list)
        or not isinstance(identity, dict)
        or not isinstance(revision, str)
    ):
        _refuse("profile-schema")
    records: list[dict[str, Any]] = []
    for record in bindings:
        if not isinstance(record, dict):
            _refuse("profile-schema")
        records.append(record)
    return tree, records, identity, revision


def _remap_prefix(
    compiled: CompiledProfile,
    wire: object,
    imported_di: object,
    command: object,
    activation: str,
) -> _RemapPlan:
    """Run the §5.5 remap prefix (raises the refusal code)."""
    if not check_compiled(compiled):
        _refuse("descriptor-mismatch")
    if activation not in ("edit", "qualification"):
        _refuse("operation-error")
    rows, attestations, namespaces = _check_command(command)
    record_digest, diagrams = _check_imported_di(imported_di)
    tree, bindings, identity, revision = _check_envelope_steps(compiled, wire)
    pins = _descriptor_pins(compiled)
    if _descriptor_digest(pins) != record_digest:
        _refuse("descriptor-mismatch")
    if activation == "edit":
        _refuse("profile-open")
    owned_tree = copy.deepcopy(tree)
    owned_bindings = copy.deepcopy(bindings)
    owned_diagrams = copy.deepcopy(diagrams)
    types = compiled.types or {}
    elements = _walk_elements(owned_tree)
    ids = _element_ids(elements)
    seen = set(ids)
    ordered = _check_map_rows(rows, seen)
    total = {element_id: element_id for element_id in ids} | dict(ordered)
    if len({total[element_id] for element_id in ids}) != len(ids):
        _refuse("id-collision")
    covered = _covered_members(attestations, pins)
    ref_fields = compiled.ref_fields or frozenset()
    _check_opaque(elements, types, ref_fields, covered)
    own_namespace = owned_tree.get("targetNamespace")
    return _RemapPlan(
        outcome=Prefix(
            identity=copy.deepcopy(identity),
            revision=revision,
            tree=owned_tree,
            bindings=owned_bindings,
            index=build_tree_index(owned_tree),
        ),
        total=total,
        namespaces=namespaces,
        covered=covered,
        ref_fields=ref_fields,
        own_namespace=own_namespace if isinstance(own_namespace, str) else None,
        elements=elements,
        ids=ids,
        diagrams=owned_diagrams,
        record_digest=record_digest,
        identity=copy.deepcopy(identity),
        revision=revision,
    )


def remap_ids(
    compiled: CompiledProfile,
    envelope: object,
    imported_di: object,
    command: object,
    *,
    activation: str = "edit",
) -> ResultSuccess | ResultRefused:
    """Apply one approved id-remap migration (DESIGN §5.2, §5.5)."""
    wire = to_wire_envelope(envelope)
    try:
        plan = _remap_prefix(compiled, wire, imported_di, command, activation)
    except _RefusalError as exc:
        return refuse_result("remapIds", exc.code, wire)
    rewriter = _Rewriter(plan, compiled.types or {})
    try:
        rewriter.rewrite_tree(plan.outcome.tree)
        new_bindings = [
            {
                "ownerId": plan.total.get(str(record.get("ownerId")), str(record.get("ownerId"))),
                "role": record.get("role"),
                "targetId": plan.total.get(
                    str(record.get("targetId")), str(record.get("targetId"))
                ),
            }
            for record in plan.outcome.bindings
        ]
        new_diagrams = rewriter.rewrite_diagrams(plan.diagrams)
        finished = complete_envelope(plan.identity, plan.outcome.tree, new_bindings)
    except (ValueError, TypeError):
        return refuse_result("remapIds", "profile-schema", wire)
    output = finished.to_json()
    identity = output.get("profileIdentity")
    if not isinstance(identity, dict):
        return refuse_result("remapIds", "profile-schema", wire)
    revision = finished.semantic_revision
    snapshot = {
        "descriptorDigest": plan.record_digest,
        "diagrams": new_diagrams,
        "sha256": digest({"descriptorDigest": plan.record_digest, "diagrams": new_diagrams}),
    }
    report = Report(
        operation="remapIds",
        source_identity=copy.deepcopy(identity),
        target_identity=copy.deepcopy(identity),
        input_revision=plan.revision,
        output_revision=revision,
        entries=tuple(rewriter.entries),
        id_map=tuple(
            {
                "sourceId": element_id,
                "resultId": plan.total[element_id],
                "domain": "migration",
            }
            for element_id in sorted(plan.ids, key=lambda value: value.encode("utf-16-be"))
        ),
    )
    return result_success(
        operation="remapIds",
        profile_identity=copy.deepcopy(identity),
        base_revision=plan.revision,
        revision=revision,
        report=report,
        payload={"envelope": output, "importedDi": snapshot},
    )
