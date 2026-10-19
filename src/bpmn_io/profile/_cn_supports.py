"""Lot-3 support binding adapters (DESIGN §5.2 recovery and binding).

``propose_support_bindings`` is the read-only recovery preview: it plans the
profile's ``normalize`` recipes as ``normalize`` with the ``qualification``
activation would, without gates and without applying anything, and reports
the ensures that can reuse an attested element. ``bind_supports`` is the
explicit binding transaction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bpmn_io.profile._cn_context import (
    Authority,
    context_from_snapshot,
    run_prefix,
    to_wire_envelope,
)
from bpmn_io.profile._cn_plan import _plan_recipe_impl, _RefusalError, _Shared
from bpmn_io.profile._envelope import sort_bindings
from bpmn_io.profile._results import PureRefused, PureSuccess, pure_refused, pure_success

if TYPE_CHECKING:
    from collections.abc import Sequence

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
