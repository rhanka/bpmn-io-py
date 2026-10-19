"""Lot-3 complete operation (DESIGN §7.1, spec §5.1 with §6.1 and §6.2).

Validates the envelope prefix, checks extraction authority, allocates
stable identities, plans every complete recipe on the allocated snapshot,
applies the concatenated plan and proves the fixed point with one silent
second evaluation. Any refusal rolls back the whole operation.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal

from bpmn_io.profile._c14n import jcs
from bpmn_io.profile._cn_apply import _apply_core, _input_parents, _walk_input_pointers
from bpmn_io.profile._cn_context import (
    Authority,
    check_compiled,
    context_from_snapshot,
    refuse_result,
    run_prefix,
    to_wire_envelope,
)
from bpmn_io.profile._cn_identity import Allocation, allocate_tree_ids
from bpmn_io.profile._cn_plan import _plan_recipe_impl, _RefusalError, _Shared
from bpmn_io.profile._compiler import CompiledProfile
from bpmn_io.profile._envelope import complete_envelope
from bpmn_io.profile._results import (
    Coordinate,
    PureRefused,
    Report,
    ReportEntry,
    ResultRefused,
    ResultSuccess,
    result_success,
)

if TYPE_CHECKING:
    from bpmn_io.profile._compiler import CompiledProfile

__all__ = ["complete"]


def _check_extraction(  # noqa: C901 - one branch per member kind
    tree: dict[str, Any], producers: dict[tuple[str, str], frozenset[str]]
) -> str | None:
    """Check the extraction authority (``profile-producer`` or None, §6.1)."""
    stack: list[object] = [tree]
    seen: set[int] = set()
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if id(current) in seen:
                continue
            seen.add(id(current))
            type_name = current.get("$type")
            for key in sorted(current.keys()):
                if key == "$type":
                    continue
                value = current[key]
                if isinstance(value, (dict, list)):
                    if isinstance(value, dict):
                        stack.append(value)
                    else:
                        stack.extend(entry for entry in value if isinstance(entry, dict))
                if not isinstance(type_name, str):
                    return "profile-producer"
                if "ai" not in producers.get((type_name, key), frozenset()):
                    return "profile-producer"
        elif isinstance(current, list):
            stack.extend(current)
    return None


def _allocation_entries(  # noqa: PLR0913, PLR0917 - allocation parts travel together
    allocations: list[Allocation],
    pre_ids: dict[int, str | None],
    pre_parents: dict[int, dict[str, Any]],
    pre_pointers: dict[int, str],
    output_pointers: dict[int, str],
    output_parents: dict[int, dict[str, Any]],
) -> list[ReportEntry]:
    """Build the ``complete/allocate-id`` entries for one allocation run."""
    entries: list[ReportEntry] = []
    for allocation in allocations:
        source_target = _pre_target(allocation.element, pre_ids, pre_parents, pre_pointers)
        pointer = pre_pointers.get(id(allocation.element), "")
        source = Coordinate(
            domain="tree",
            pointer=f"{pointer}/id" if pointer else "/id",
            target_id=source_target,
            provenance="exact",
        )
        out_pointer = output_pointers.get(id(allocation.element), "")
        out_target: str | None = allocation.new_id
        if out_target is None:  # pragma: no cover - defensive
            current: dict[str, Any] | None = output_parents.get(id(allocation.element))
            seen = 0
            while current is not None and seen < 100000:
                seen += 1
                element_id = current.get("id")
                if isinstance(element_id, str):
                    out_target = element_id
                    break
                current = output_parents.get(id(current))
        result = Coordinate(
            domain="tree",
            pointer=f"{out_pointer}/id" if out_pointer else "/id",
            target_id=out_target,
            provenance="generated",
        )
        entries.append(
            ReportEntry(
                rule_id="stable-id/1",
                code="complete/allocate-id",
                message_key="complete.allocate-id",
                severity="info",
                classification="repairable",
                source=source,
                result=result,
                stage="complete",
                disposition="corrected",
                before_present=False,
                after_present=True,
                after=allocation.new_id,
                property="id",
            )
        )
    return entries


def _pre_target(
    element: dict[str, Any],
    pre_ids: dict[int, str | None],
    pre_parents: dict[int, dict[str, Any]],
    pre_pointers: dict[int, str],
) -> str | None:
    """Return the pre-allocation id or nearest ancestor id (else None)."""
    del pre_pointers
    current: dict[str, Any] | None = element
    seen = 0
    while current is not None and seen < 100000:
        seen += 1
        element_id = pre_ids.get(id(current))
        if isinstance(element_id, str):
            return element_id
        current = pre_parents.get(id(current))
    return None


def _snapshot_pre_ids(
    tree: dict[str, Any],
) -> tuple[dict[int, str | None], dict[int, dict[str, Any]]]:
    """Record pre-allocation ids and parents over one tree."""
    pre_ids: dict[int, str | None] = {}
    pre_parents: dict[int, dict[str, Any]] = {}
    stack: list[dict[str, Any]] = [tree]
    seen: set[int] = set()
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        element_id = node.get("id")
        pre_ids[id(node)] = element_id if isinstance(element_id, str) else None
        for value in node.values():
            if isinstance(value, dict):
                pre_parents.setdefault(id(value), node)
                stack.append(value)
            elif isinstance(value, list):
                for entry in value:
                    if isinstance(entry, dict):
                        pre_parents.setdefault(id(entry), node)
                        stack.append(entry)
    return pre_ids, pre_parents


def _complete_pass(  # noqa: C901, PLR0911, PLR0912 - one branch per complete step
    compiled: CompiledProfile,
    envelope: object,
    *,
    mode: Literal["extraction", "retained"],
    activation: Literal["edit", "qualification"],
) -> tuple[dict[str, Any], list[ReportEntry], list[dict[str, Any]], str] | str:
    """Run one complete pass (payload, entries, placements, revision or code)."""
    outcome = run_prefix(compiled, envelope)
    if isinstance(outcome, str):
        return outcome
    if not check_compiled(compiled):
        return "descriptor-mismatch"
    if compiled.types is None or compiled.producers is None:
        return "descriptor-mismatch"
    if mode == "extraction":
        failed = _check_extraction(outcome.tree, compiled.producers)
        if failed is not None:
            return failed
    pre_ids, pre_parents = _snapshot_pre_ids(outcome.tree)
    pre_pointers = dict(outcome.index.pointers)
    try:
        allocations = allocate_tree_ids(outcome.tree, compiled.types, pre_pointers)
    except _RefusalError as exc:
        return exc.code
    context = context_from_snapshot(
        compiled,
        outcome.identity,
        outcome.revision,
        outcome.tree,
        outcome.bindings,
        stage="complete",
    )
    if isinstance(context, str):
        return context
    authority = Authority(actor="code", activation=activation)
    shared = _Shared()
    writes: list[dict[str, Any]] = []
    for recipe in compiled.recipes.values():
        if not isinstance(recipe, dict) or recipe.get("phase") != "complete":
            continue
        planned = _plan_recipe_impl(recipe, context, {}, authority, gates=True, shared=shared)
        if isinstance(planned, PureRefused):
            return planned.code
        payload_writes = planned.payload
        if not isinstance(payload_writes, dict):
            return "profile-type"
        writes.extend(payload_writes["writes"])
    try:
        report = _apply_core(
            writes,
            phase="complete",
            staged_tree=outcome.tree,
            staged_bindings=list(outcome.bindings),
            input_tree=copy.deepcopy(outcome.tree),
            emit_entries=True,
            allocated_ids=frozenset(
                allocation.new_id for allocation in allocations if allocation.new_id is not None
            ),
        )
    except _RefusalError as exc:
        return exc.code
    try:
        finished = complete_envelope(outcome.identity, report.tree, report.bindings)
    except (ValueError, TypeError):
        return "profile-schema"
    payload = finished.to_json()
    output_pointers = _walk_input_pointers(report.tree)
    output_parents = _input_parents(report.tree)
    entries = _allocation_entries(
        allocations, pre_ids, pre_parents, pre_pointers, output_pointers, output_parents
    )
    entries.extend(report.entries)
    return payload, entries, report.placements, finished.semantic_revision


def complete(
    compiled: CompiledProfile,
    envelope: object,
    mode: Literal["extraction", "retained"],
    *,
    activation: Literal["edit", "qualification"] = "edit",
) -> ResultSuccess | ResultRefused:
    """Complete one envelope with the profile's complete recipes (§5.1)."""
    wire = to_wire_envelope(envelope)
    if mode not in ("extraction", "retained") or activation not in ("edit", "qualification"):
        return refuse_result("complete", "operation-error", wire)
    base_revision = wire.get("semanticRevision") if isinstance(wire, Mapping) else None
    if not isinstance(base_revision, str):
        return refuse_result("complete", "operation-error", wire)
    outcome = _complete_pass(compiled, wire, mode=mode, activation=activation)
    if isinstance(outcome, str):
        return refuse_result("complete", outcome, wire)
    payload, entries, placements, revision = outcome
    rerun = _complete_pass(compiled, payload, mode="retained", activation=activation)
    if isinstance(rerun, str):
        return refuse_result("complete", "normalization-not-fixed", wire)
    payload2, entries2, placements2, revision2 = rerun
    if (
        entries2
        or jcs(payload2) != jcs(payload)
        or placements2 != placements
        or revision2 != revision
    ):
        return refuse_result("complete", "normalization-not-fixed", wire)
    identity = payload.get("profileIdentity", {})
    report = Report(
        operation="complete",
        source_identity=copy.deepcopy(identity),
        target_identity=copy.deepcopy(identity),
        input_revision=base_revision,
        output_revision=revision,
        entries=tuple(entries),
    )
    return result_success(
        operation="complete",
        profile_identity=copy.deepcopy(identity),
        base_revision=base_revision,
        revision=revision,
        report=report,
        payload=payload,
    )
