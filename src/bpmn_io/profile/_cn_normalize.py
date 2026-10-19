"""Lot-3 normalization (DESIGN §7 ``normalize`` with §4.6 placements).

``sort_placements`` orders one placement list in §4.6 order. ``normalize``
runs the profile's normalize recipes with ensure semantics (§6.3), the
support-participant check (§5.2 step 8) and the bounded fixed point (§5.6).
It reuses the apply core through a function-local import so this module
never creates an import cycle with :mod:`bpmn_io.profile._cn_apply`
(which imports ``sort_placements`` from here).
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal

from bpmn_io.profile._c14n import jcs
from bpmn_io.profile._cn_context import (
    Authority,
    _utf16,
    context_from_snapshot,
    refuse_result,
    run_prefix,
    to_wire_envelope,
)
from bpmn_io.profile._cn_plan import _plan_recipe_impl, _RefusalError, _Shared
from bpmn_io.profile._envelope import complete_envelope
from bpmn_io.profile._evaluate import _MISSING
from bpmn_io.profile._results import (
    PureRefused,
    Report,
    ReportEntry,
    ResultRefused,
    ResultSuccess,
    result_success,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from bpmn_io.profile._compiler import CompiledProfile

__all__ = ["normalize", "sort_placements"]


def sort_placements(placements: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Sort one placement list in §4.6 order (deep copies).

    Owner process, region, element, anchor (absent first), then the
    related association array lexicographically.
    """
    owned: list[tuple[str, str, str, str | None, list[str]]] = []
    for placement in placements:
        element_id = placement.get("elementId")
        owner_id = placement.get("ownerProcessId")
        region = placement.get("regionKey")
        related = placement.get("relatedAssociationIds")
        anchor = placement.get("anchorAssociationId")
        if not isinstance(related, list):
            msg = "placement record is malformed"
            raise TypeError(msg)
        related_ids: list[str] = []
        for item in related:
            if not isinstance(item, str):
                msg = "placement record is malformed"
                raise TypeError(msg)
            related_ids.append(item)
        if (
            not isinstance(element_id, str)
            or not isinstance(owner_id, str)
            or not isinstance(region, str)
            or (anchor is not None and not isinstance(anchor, str))
            or set(placement.keys())
            - {
                "elementId",
                "ownerProcessId",
                "regionKey",
                "relatedAssociationIds",
                "anchorAssociationId",
            }
        ):
            msg = "placement record is malformed"
            raise TypeError(msg)
        owned.append((element_id, owner_id, region, anchor, related_ids))

    def _key(
        parts: tuple[str, str, str, str | None, list[str]],
    ) -> tuple[Any, ...]:
        element_id, owner_id, region, anchor, related = parts
        return (
            _utf16(owner_id),
            _utf16(region),
            _utf16(element_id),
            (0,) if anchor is None else (1, _utf16(anchor)),
            tuple(_utf16(item) for item in related),
        )

    ordered = sorted(owned, key=_key)
    result: list[dict[str, object]] = []
    for element_id, owner_id, region, anchor, related in ordered:
        record: dict[str, object] = {
            "elementId": element_id,
            "ownerProcessId": owner_id,
            "regionKey": region,
            "relatedAssociationIds": related,
        }
        if anchor is not None:
            record["anchorAssociationId"] = anchor
        result.append(record)
    return result


def _check_intent(intent: object, by_id: Mapping[str, object]) -> str | None:
    """Validate one placement intent (refusal code or None, §5.2 step 6)."""
    if intent is None:
        return None
    if not isinstance(intent, list):
        return "operation-error"
    for entry in intent:
        if not isinstance(entry, dict):
            return "operation-error"
        element_id = entry.get("elementId")
        if not isinstance(element_id, str):
            return "operation-error"
        if element_id not in by_id:
            return "reference-dangling"
    return None


def _assigned_process_refs(writes: list[dict[str, Any]]) -> dict[str, object]:
    """Map each processRef assignRef target id to its assigned value."""
    assigned: dict[str, object] = {}
    for write in writes:
        target = write.get("target")
        if (
            write.get("op") == "assignRef"
            and write.get("property") == "processRef"
            and isinstance(target, dict)
            and isinstance(target.get("id"), str)
        ):
            ids = write.get("ids")
            assigned[target["id"]] = ids[0] if isinstance(ids, list) and ids else None
    return assigned


def _index_by_id(tree: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index one staged tree by element id (first wins)."""
    by_id: dict[str, dict[str, Any]] = {}
    stack: list[object] = [tree]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            element_id = current.get("id")
            if isinstance(element_id, str) and element_id not in by_id:
                by_id[element_id] = current
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return by_id


def _check_one_participant(
    write: dict[str, Any], assigned: dict[str, object], by_id: dict[str, dict[str, Any]]
) -> str | None:
    """Check one ensured Participant handle (refusal code or None)."""
    handle_id = write.get("id")
    if not isinstance(handle_id, str):
        return "support-binding-conflict"
    target = by_id.get(handle_id)
    if target is None:
        return "support-binding-conflict"
    final = target.get("processRef", _MISSING)
    want = assigned.get(handle_id, _MISSING)
    if want is _MISSING or want is None:
        return "support-binding-conflict" if final is not _MISSING else None
    return None if final == want else "support-binding-conflict"


def _check_participants(writes: list[dict[str, Any]], staged_tree: dict[str, Any]) -> str | None:
    """Check ensured Participant handles end with their processRef (§5.2 step 8)."""
    assigned = _assigned_process_refs(writes)
    by_id = _index_by_id(staged_tree)
    for write in writes:
        if write.get("op") != "ensure" or write.get("type") != "bpmn:Participant":
            continue
        failed = _check_one_participant(write, assigned, by_id)
        if failed is not None:
            return failed
    return None


def _normalize_pass(  # noqa: C901, PLR0911 - one branch per normalize step
    compiled: CompiledProfile,
    wire: object,
    *,
    intent: list[dict[str, Any]] | None,
    activation: Literal["edit", "qualification"],
) -> tuple[dict[str, Any], list[ReportEntry], list[dict[str, object]], str] | str:
    """Run one normalize pass (payload, entries, placements, revision or code)."""
    from bpmn_io.profile._cn_apply import (  # noqa: PLC0415 - cycle: apply imports sort_placements from here
        _apply_core,
    )

    outcome = run_prefix(compiled, wire)
    if isinstance(outcome, str):
        return outcome
    failed = _check_intent(intent, outcome.index.by_id)
    if failed is not None:
        return failed
    context = context_from_snapshot(
        compiled,
        outcome.identity,
        outcome.revision,
        outcome.tree,
        outcome.bindings,
        stage="normalize",
    )
    if isinstance(context, str):
        return context
    authority = Authority(actor="code", activation=activation)
    shared = _Shared()
    writes: list[dict[str, Any]] = []
    for recipe in compiled.recipes.values():
        if not isinstance(recipe, dict) or recipe.get("phase") != "normalize":
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
            phase="normalize",
            staged_tree=outcome.tree,
            staged_bindings=list(outcome.bindings),
            input_tree=copy.deepcopy(outcome.tree),
            emit_entries=True,
        )
    except _RefusalError as exc:
        return exc.code
    failed = _check_participants(writes, report.tree)
    if failed is not None:
        return failed
    placements = sort_placements(report.placements)
    try:
        finished = complete_envelope(outcome.identity, report.tree, report.bindings)
    except (ValueError, TypeError):
        return "profile-schema"
    envelope = finished.to_json()
    entries = list(report.entries)
    payload: dict[str, object] = {"envelope": envelope, "placements": placements, "report": None}
    return payload, entries, placements, finished.semantic_revision


def _check_normalize_fixed(
    compiled: CompiledProfile,
    outcome: tuple[dict[str, Any], list[ReportEntry], list[dict[str, object]], str],
    intent: list[dict[str, Any]] | None,
    activation: Literal["edit", "qualification"],
) -> str | None:
    """Rerun normalize on its output (the fixed-point code or None, §5.6)."""
    payload, _entries, placements, revision = outcome
    rerun = _normalize_pass(compiled, payload["envelope"], intent=intent, activation=activation)
    if isinstance(rerun, str):
        return "normalization-not-fixed"
    payload2, entries2, placements2, revision2 = rerun
    if (
        entries2
        or jcs(payload2["envelope"]) != jcs(payload["envelope"])
        or placements2 != placements
        or revision2 != revision
    ):
        return "normalization-not-fixed"
    return None


def normalize(
    compiled: CompiledProfile,
    envelope: object,
    placement_intent: list[dict[str, object]] | None = None,
    *,
    activation: Literal["edit", "qualification"] = "edit",
) -> ResultSuccess | ResultRefused:
    """Normalize one envelope with the profile's normalize recipes (§5.2)."""
    wire = to_wire_envelope(envelope)
    if activation not in ("edit", "qualification") or (
        placement_intent is not None and not isinstance(placement_intent, list)
    ):
        return refuse_result("normalize", "operation-error", wire)
    base_revision = wire.get("semanticRevision") if isinstance(wire, Mapping) else None
    if not isinstance(base_revision, str):
        return refuse_result("normalize", "operation-error", wire)
    outcome = _normalize_pass(compiled, wire, intent=placement_intent, activation=activation)
    if isinstance(outcome, str):
        return refuse_result("normalize", outcome, wire)
    payload, entries, _placements, revision = outcome
    failed = _check_normalize_fixed(compiled, outcome, placement_intent, activation)
    if failed is not None:
        return refuse_result("normalize", failed, wire)
    output_envelope = payload["envelope"]
    if not isinstance(output_envelope, dict):
        return refuse_result("normalize", "profile-schema", wire)
    identity = output_envelope.get("profileIdentity", {})
    report = Report(
        operation="normalize",
        source_identity=copy.deepcopy(identity),
        target_identity=copy.deepcopy(identity),
        input_revision=base_revision,
        output_revision=revision,
        entries=tuple(entries),
    )
    payload["report"] = report.to_json()
    return result_success(
        operation="normalize",
        profile_identity=copy.deepcopy(identity),
        base_revision=base_revision,
        revision=revision,
        report=report,
        payload=payload,
    )
