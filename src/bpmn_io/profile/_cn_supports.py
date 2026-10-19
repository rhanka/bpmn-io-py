"""Lot-3 support binding adapters (DESIGN §5.2 recovery and binding).

``propose_support_bindings`` is the read-only recovery preview: it plans the
profile's ``normalize`` recipes as ``normalize`` with the ``qualification``
activation would, without gates and without applying anything, and reports
the ensures that can reuse an attested element. ``bind_supports`` is the
explicit binding transaction.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from bpmn_io.profile._cn_context import (
    Authority,
    Prefix,
    check_compiled,
    context_from_snapshot,
    refuse_result,
    run_prefix,
    to_wire_envelope,
)
from bpmn_io.profile._cn_plan import _plan_recipe_impl, _RefusalError, _refuse, _Shared
from bpmn_io.profile._envelope import complete_envelope, sort_bindings, validate_bindings
from bpmn_io.profile._results import (
    PureRefused,
    PureSuccess,
    Report,
    ResultRefused,
    ResultSuccess,
    pure_refused,
    pure_success,
    result_success,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from bpmn_io.profile._compiler import CompiledProfile


def propose_support_bindings(
    compiled: CompiledProfile,
    envelope: object,
    *,
    provenance: Sequence[str] = (),
) -> PureSuccess | PureRefused:
    """Propose support bindings for an envelope that lost them (§6.7)."""
    if not isinstance(provenance, (list, tuple)) or not all(
        isinstance(item, str) for item in provenance
    ):
        return pure_refused("operation-error")
    wire = to_wire_envelope(envelope)
    outcome = run_prefix(compiled, wire)
    if isinstance(outcome, str):
        return pure_refused(outcome)
    context = context_from_snapshot(
        compiled,
        outcome.identity,
        outcome.revision,
        outcome.tree,
        outcome.bindings,
        stage="normalize",
    )
    if isinstance(context, str):
        return pure_refused(context)
    authority = Authority(actor="code", activation="qualification")
    shared = _Shared(propose=True, provenance=frozenset(provenance))
    try:
        for recipe in compiled.recipes.values():
            if not isinstance(recipe, dict) or recipe.get("phase") != "normalize":
                continue
            planned = _plan_recipe_impl(recipe, context, {}, authority, gates=False, shared=shared)
            if isinstance(planned, PureRefused):
                return planned
    except _RefusalError as exc:
        return pure_refused(exc.code)
    return pure_success({"proposals": sort_bindings(list(shared.proposals))})


def _bind_prefix(
    compiled: CompiledProfile,
    wire: object,
    bindings: Sequence[Mapping[str, object]],
    activation: str,
) -> Prefix:
    """Run the §5.5 bind prefix (raises the refusal code, §5.0 steps 1-5)."""
    if not check_compiled(compiled):
        _refuse("descriptor-mismatch")
    if activation not in ("edit", "qualification"):
        _refuse("operation-error")
    failed = validate_bindings(bindings)
    if failed is not None:
        _refuse(failed)
    outcome = run_prefix(compiled, wire)
    if isinstance(outcome, str):
        _refuse(outcome)
    if activation == "edit":
        _refuse("profile-open")
    return outcome


def _merged_bindings(
    outcome: Prefix, bindings: Sequence[Mapping[str, object]]
) -> list[dict[str, object]]:
    """Merge supplied records over snapshot bindings (raises on conflict)."""
    owned = [
        {"ownerId": entry["ownerId"], "role": entry["role"], "targetId": entry["targetId"]}
        for entry in bindings
    ]
    taken_roles = {
        (str(record.get("ownerId")), str(record.get("role"))) for record in outcome.bindings
    }
    taken_targets = {str(record.get("targetId")) for record in outcome.bindings}
    known_ids = set(outcome.index.by_id)
    for entry in owned:
        owner_id = str(entry["ownerId"])
        target_id = str(entry["targetId"])
        if (owner_id, str(entry["role"])) in taken_roles:
            _refuse("support-binding-conflict")
        if owner_id not in known_ids or target_id not in known_ids:
            _refuse("support-binding-conflict")
        if target_id in taken_targets:
            _refuse("support-binding-conflict")
        taken_roles.add((owner_id, str(entry["role"])))
        taken_targets.add(target_id)
    return copy.deepcopy(outcome.bindings) + copy.deepcopy(owned)


def bind_supports(
    compiled: CompiledProfile,
    envelope: object,
    bindings: Sequence[Mapping[str, object]],
    *,
    activation: str = "edit",
) -> ResultSuccess | ResultRefused:
    """Bind explicit support records (the recovery transaction, §5.5)."""
    wire = to_wire_envelope(envelope)
    try:
        outcome = _bind_prefix(compiled, wire, bindings, activation)
        merged = _merged_bindings(outcome, bindings)
        finished = complete_envelope(outcome.identity, outcome.tree, merged)
    except _RefusalError as exc:
        return refuse_result("bindSupports", exc.code, wire)
    except (ValueError, TypeError):
        return refuse_result("bindSupports", "profile-schema", wire)
    output = finished.to_json()
    identity = output.get("profileIdentity")
    if not isinstance(identity, dict):
        return refuse_result("bindSupports", "profile-schema", wire)
    base_revision = outcome.revision
    revision = finished.semantic_revision
    report = Report(
        operation="bindSupports",
        source_identity=copy.deepcopy(identity),
        target_identity=copy.deepcopy(identity),
        input_revision=base_revision,
        output_revision=revision,
        entries=(),
    )
    return result_success(
        operation="bindSupports",
        profile_identity=copy.deepcopy(identity),
        base_revision=base_revision,
        revision=revision,
        report=report,
        payload=output,
    )
