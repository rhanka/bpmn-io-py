"""map_export with export-ir/1 planning, IDs and losses (DESIGN R3.3 §10.2).

Planning runs the export recipes of the selected ``exports[]`` record in
order over their selector results, records every ``outputId`` request,
allocates call-local ids (``counter``/``digest``/``native``) and emits
the IR with capability, loss-action and adapter losses. Refusal returns
the complete report and no artifact; symbol tables never survive a call.
"""

from __future__ import annotations

import copy
import dataclasses
import math
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bpmn_io.profile._occurrence import OccurrenceScope

from bpmn_io.profile._c14n import digest, jcs
from bpmn_io.profile._evaluate import (
    _is_occurrence_handle,
    is_missing,
    make_read_context,
    reference_property_names,
)
from bpmn_io.profile._layout import _begin_operation, index_tree
from bpmn_io.profile._render import _escape_segment, native_preorder
from bpmn_io.profile._render_digest import check_render_freshness, view_revision
from bpmn_io.profile._results import (
    CAPABILITY_ORDER,
    ReportEntry,
    ResultRefused,
    ResultSuccess,
    make_coordinate,
    refused_result,
    worst_capability,
)

__all__ = ["ADAPTERS", "map_export"]

Json = Any

#: Registered Python export adapters (format -> adapter record).
ADAPTERS: dict[str, dict[str, object]] = {
    "drawio": {"id": "drawio/1", "drops": frozenset({"metadata"})},
    "sparx": {"id": "sparx/1", "drops": frozenset({"metadata"})},
}

#: Closed export-ir/1 record kinds.
_IR_KINDS = ("page", "node", "edge", "label", "metadata")

#: Parent-compatible record kinds (DESIGN §10.2 emission order).
_PARENT_KINDS = frozenset({"page", "node"})

#: JS ``undefined`` sentinel (lot4-export.ts:217, §2.1). Distinct from None
#: (JSON null) and from MISSING; any IR/entry member holding it refuses
#: ``profile-json`` at finalization, and idMap rows holding it refuse
#: ``operation-error`` at ``sortIdMap`` validation.
_UNDEFINED: Any = object()

#: ID-plan domain order (lot4-export.ts:55).
_DOMAIN_ORDER = ("page", "node", "edge", "label")


def _js_key_string(page_id: object, occurrence_key: object, domain: str) -> str:
    """Build one key string (lot4-export.ts:56-57).

    ``pageId`` formats via JS template (None/undefined becomes "undefined");
    ``occurrenceKey`` uses ``?? ""`` (None becomes "").
    """
    if isinstance(page_id, str):
        page_text = page_id
    elif page_id is None:
        # Missing means JS undefined (null would be "null", but pageId is
        # never null in the corpora; treat None as undefined for keys).
        page_text = "undefined"
    else:
        page_text = str(page_id)
    if isinstance(occurrence_key, str):
        key_text = occurrence_key
    elif occurrence_key is None:
        key_text = ""
    else:
        key_text = str(occurrence_key)
    return f"{page_text} {key_text} {domain}"


def _utf16(text: str) -> bytes:
    """Encode one string in UTF-16 code-unit order (lot4-query.ts:24-26)."""
    return text.encode("utf-16-be")


@dataclass
class _PlanEmit:
    """One interpreted emit with raw field/parent ASTs (lot4-export.ts:425-432).

    Values stay unevaluated until assembly; ``lossAfter`` holds the single
    attached self-loss class of the same iteration, if any.
    """

    recipe_id: str
    kind: str
    fields: list[tuple[str, object]]
    parent_ast: object | None
    has_parent: bool
    self: object
    self_page_id: str
    bound: dict[str, object] = field(default_factory=dict)
    loss_after: str | None = None


@dataclass
class _PlanLoss:
    """One standalone loss emission (lot4-export.ts:402-423)."""

    recipe_id: str
    code: str
    self: object
    self_page_id: str
    target: object


@dataclass
class _ExportRun:
    """Mutable per-call export planning and emission state."""

    operation: str = "mapExport"
    compiled: object = None
    tree: dict[str, Json] = field(default_factory=dict)
    by_id: dict[str, Json] = field(default_factory=dict)
    pointers: dict[str, str] = field(default_factory=dict)
    render: dict[str, Json] = field(default_factory=dict)
    pages: dict[str, dict[str, Json]] = field(default_factory=dict)
    export: dict[str, Json] = field(default_factory=dict)
    adapter: dict[str, object] = field(default_factory=dict)
    context: Any = None
    emissions: list[object] = field(default_factory=list)
    entries: list[ReportEntry] = field(default_factory=list)
    code: str | None = None


def _pointer_map(tree: dict[str, Json]) -> dict[str, str]:
    """Map semantic ids to RFC 6901 tree pointers in native pre-order."""
    return {element_id: pointer for element_id, _, pointer in native_preorder(tree)}


def _child_entries(node: dict[str, Json]) -> list[tuple[bytes, str, Json]]:
    """Collect one node's typed child entries in UTF-16 key order."""
    children: list[tuple[bytes, str, Json]] = []
    for key, value in node.items():
        if isinstance(value, dict) and isinstance(value.get("$type"), str):
            children.append((key.encode("utf-16-be"), key, value))
        elif isinstance(value, list) and all(
            isinstance(entry, dict) and isinstance(entry.get("$type"), str) for entry in value
        ):
            for index, entry in enumerate(value):
                children.append((key.encode("utf-16-be"), f"{key}/{index}", entry))
    children.sort(key=lambda entry: entry[0])
    return children


def _locate_element(
    tree: dict[str, Json], target: dict[str, Json]
) -> tuple[str | None, str | None]:
    """Locate one element by identity (pointer, nearest bearing ancestor)."""
    stack: list[tuple[Json, str, str | None]] = [(tree, "", None)]
    seen = 0
    while stack:
        node, pointer, ancestor = stack.pop()
        seen += 1
        if seen > 100000:
            break
        if node is target:
            return pointer or "", ancestor
        if not isinstance(node, dict):
            continue
        element_id = node.get("id")
        holder = ancestor
        if isinstance(element_id, str) and element_id:
            holder = element_id
        for _, key, child in reversed(_child_entries(node)):
            segments = [_escape_segment(part) for part in key.split("/")]
            stack.append((child, pointer + "/" + "/".join(segments), holder))
    return None, None


def _native_source(run: _ExportRun, element: dict[str, Json]) -> dict[str, Json]:
    """Build source coordinates for one native loss target."""
    element_id = element.get("id")
    if isinstance(element_id, str) and element_id and element_id in run.pointers:
        return {
            "domain": "tree",
            "pointer": run.pointers[element_id],
            "targetId": element_id,
            "provenance": "exact",
        }
    pointer, ancestor = _locate_element(run.tree, element)
    if pointer is None:
        return dict(_UNAVAILABLE)
    return {
        "domain": "tree",
        "pointer": pointer,
        "targetId": ancestor,
        "provenance": "exact",
    }


def _target_source(
    run: _ExportRun, resolved: object, handle: object
) -> tuple[str | None, str | None, str | None, dict[str, Json]]:
    """Split one loss target into page/key/type plus source coordinates."""
    if isinstance(resolved, _PlanEmit) or not isinstance(resolved, dict):
        return _self_coordinates(run, handle)
    if _is_occurrence_handle(resolved):
        return _self_coordinates(run, resolved)
    page_id, occurrence_key, emitted_type, _ = _self_coordinates(run, handle)
    return page_id, occurrence_key, emitted_type, _native_source(run, resolved)


def _self_coordinates(
    run: _ExportRun, handle: object
) -> tuple[str | None, str | None, str | None, dict[str, Json]]:
    """Split one iteration handle into page/key/type plus source."""
    if isinstance(handle, dict) and "occurrenceKey" in handle:
        page_id = str(handle.get("pageId"))
        key = str(handle.get("occurrenceKey"))
        emitted = handle.get("emittedType")
        semantic_id = handle.get("semanticId")
        if isinstance(semantic_id, str) and semantic_id in run.pointers:
            source: dict[str, Json] = {
                "domain": "tree",
                "pointer": run.pointers[semantic_id],
                "targetId": semantic_id,
                "provenance": "exact",
            }
        else:
            source = dict(_UNAVAILABLE)
        return page_id, key, emitted if isinstance(emitted, str) else None, source
    if isinstance(handle, dict) and isinstance(handle.get("pageId"), str):
        return (
            str(handle.get("pageId")),
            None,
            None,
            {
                "domain": "none",
                "pointer": None,
                "targetId": None,
                "provenance": "unavailable",
            },
        )
    if isinstance(handle, dict):
        element_id = handle.get("id")
        pointer = run.pointers.get(element_id) if isinstance(element_id, str) else None
        if isinstance(element_id, str) and pointer is not None:
            return (
                None,
                None,
                None,
                {
                    "domain": "tree",
                    "pointer": pointer,
                    "targetId": element_id,
                    "provenance": "exact",
                },
            )
        if handle.get("$type") == "bpmn:Definitions" or element_id is None:
            own = "" if handle.get("$type") == "bpmn:Definitions" else None
            return (
                None,
                None,
                None,
                {
                    "domain": "tree" if own is not None else "none",
                    "pointer": own,
                    "targetId": element_id if isinstance(element_id, str) else None,
                    "provenance": "exact" if own is not None else "unavailable",
                },
            )
    return (
        None,
        None,
        None,
        {
            "domain": "none",
            "pointer": None,
            "targetId": None,
            "provenance": "unavailable",
        },
    )


def _loss_entry(
    rule_id: str,
    code: str,
    self_obj: object,
    result: dict[str, Json],
    source: dict[str, Json],
) -> ReportEntry:
    """Build one export loss entry (lot4-export.ts:537-546, spec §10.3)."""
    page_id: str | None = None
    occurrence_key: str | None = None
    emitted_type: str | None = None
    if isinstance(self_obj, dict):
        raw_page = self_obj.get("pageId")
        raw_key = self_obj.get("occurrenceKey")
        raw_type = self_obj.get("emittedType")
        page_id = raw_page if isinstance(raw_page, str) else None
        occurrence_key = raw_key if isinstance(raw_key, str) else None
        emitted_type = raw_type if isinstance(raw_type, str) else None
    # Preserve _UNDEFINED result members for finalization (profile-json).
    result_target = result.get("targetId")
    if result_target is _UNDEFINED:
        kept_target: object = _UNDEFINED
    elif isinstance(result_target, str):
        kept_target = result_target
    else:
        kept_target = None
    result_pointer = result.get("pointer")
    kept_pointer = result_pointer if isinstance(result_pointer, str) else None
    source_target = source.get("targetId")
    kept_source_target = source_target if isinstance(source_target, str) else None
    source_pointer = source.get("pointer")
    kept_source_pointer = source_pointer if isinstance(source_pointer, str) else None
    return ReportEntry(
        code=f"export-loss/{code}",
        severity="warn",
        classification="loss",
        stage="export",
        rule_id=rule_id,
        message_key=f"export.loss.{code}",
        disposition="mapped",
        source=make_coordinate(
            str(source.get("domain", "none")),
            kept_source_pointer,
            kept_source_target,
            str(source.get("provenance", "unavailable")),
        ),
        result=make_coordinate(
            str(result.get("domain", "none")),
            kept_pointer,
            kept_target,  # type: ignore[arg-type]
            str(result.get("provenance", "unavailable")),
        ),
        before_present=False,
        after_present=False,
        page_id=page_id,
        occurrence_key=occurrence_key,
        emitted_type=emitted_type,
        loss_class=code,
    )


def _adapter_loss_entry(
    self_obj: object,
    result_index: int,
    source: dict[str, Json],
) -> ReportEntry:
    """Build one adapter metadata loss (lot4-export.ts:686-693, §2.8).

    Only ``pageId`` is present (no ``occurrenceKey``/``emittedType``);
    source is the ``metadataSelf`` source; result is the artifact pointer
    with null targetId.
    """
    page_id: str | None = None
    if isinstance(self_obj, dict):
        raw_page = self_obj.get("pageId")
        page_id = raw_page if isinstance(raw_page, str) else None
    kept_source_pointer = source.get("pointer") if isinstance(source.get("pointer"), str) else None
    kept_source_target = source.get("targetId") if isinstance(source.get("targetId"), str) else None
    return ReportEntry(
        code="export-loss/metadata",
        severity="warn",
        classification="loss",
        stage="export",
        rule_id="adapter",
        message_key="export.loss.metadata",
        disposition="mapped",
        source=make_coordinate(
            str(source.get("domain", "none")),
            kept_source_pointer,
            kept_source_target,
            str(source.get("provenance", "unavailable")),
        ),
        result=make_coordinate(
            "artifact",
            f"/ir/{result_index}",
            None,
            "exact",
        ),
        before_present=False,
        after_present=False,
        page_id=page_id,
        occurrence_key=None,
        emitted_type=None,
        loss_class="metadata",
    )


_UNAVAILABLE: dict[str, Json] = {
    "domain": "none",
    "pointer": None,
    "targetId": None,
    "provenance": "unavailable",
}


def _occ_scope(run: _ExportRun, bound: dict[str, object]) -> OccurrenceScope:
    """Build the occurrence scope of one export evaluation."""
    from bpmn_io.profile._occurrence import OccurrenceScope  # noqa: PLC0415

    return OccurrenceScope(
        occurrences=[
            occurrence
            for occurrence in run.render.get("occurrences", [])
            if isinstance(occurrence, dict)
        ],
        pages=[page for page in run.render.get("pages", []) if isinstance(page, dict)],
        by_id=run.by_id,
        context=run.context,
        bound=dict(bound),
    )


def _iteration_bindings(handle: object) -> dict[str, object]:
    """Build the evaluation bindings of one recipe iteration (lot4-export.ts:391)."""
    return {"self": handle}


def _eval_step_value(
    run: _ExportRun, ast: object, bindings: dict[str, object]
) -> tuple[object, str | None]:
    """Evaluate one field value in occurrence scope (lot4-export.ts:565)."""
    from bpmn_io.profile._occurrence import evaluate_occurrence_value  # noqa: PLC0415

    try:
        return evaluate_occurrence_value(ast, _occ_scope(run, bindings)), None
    except (ValueError, TypeError) as exc:
        return None, str(exc.args[0]) if exc.args else "operation-error"


def _key_string(page_id: str, occurrence_key: str, domain: str) -> str:
    """One ID-plan key string (lot4-export.ts:56-57)."""
    return _js_key_string(page_id, occurrence_key, domain)


def _collect_add(
    keys: list[tuple[object, object, str]], page_id: object, occurrence_key: object, domain: str
) -> None:
    """Append one key unless its string already occurs (lot4-export.ts:442-443)."""
    key = (page_id, occurrence_key, domain)
    needle = _js_key_string(page_id, occurrence_key, domain)
    for existing in keys:
        if _js_key_string(*existing) == needle:
            return
    keys.append(key)


def _collect_add_item(keys: list[tuple[object, object, str]], item: object, domain: str) -> None:
    """Collect one outputId binding target key (lot4-export.ts:445-451)."""
    from bpmn_io.profile._occurrence import MISSING as _OCC_MISSING  # noqa: PLC0415

    if item is None or not isinstance(item, dict) or item is _OCC_MISSING:
        return
    if is_missing(item):
        return
    page_id = item.get("pageId")
    occurrence_key = item.get("occurrenceKey")
    if not isinstance(page_id, str):
        return
    if occurrence_key is None:
        _collect_add(keys, page_id, "", "page")
    elif isinstance(occurrence_key, str) and isinstance(domain, str) and domain:
        _collect_add(keys, page_id, occurrence_key, domain)


def _collect_keys(  # noqa: C901 - JS key cases transcribed one by one
    run: _ExportRun,
) -> list[tuple[object, object, str]]:
    """Collect the ID-plan keys of interpreted emissions (lot4-export.ts:440-479).

    The emit's own key, edge endpoint keys only for edges, and an explicit
    outputId-parent key; never arbitrary optional-field requests.
    """
    keys: list[tuple[object, object, str]] = []
    for emission in run.emissions:
        if isinstance(emission, _PlanLoss):
            continue
        if not isinstance(emission, _PlanEmit) or emission.kind == "metadata":
            continue
        self_obj = emission.self if isinstance(emission.self, dict) else None
        # JS always adds the own key, whatever the id value (lot4-export.ts:454-457):
        # page -> keyOfPage(self.pageId); other kinds -> keyOfOccurrence
        # (self.pageId, self.occurrenceKey, idDomain). Missing members stay
        # None and format as JS undefined/"" in the key string.
        id_ast = next((value for name, value in emission.fields if name == "id"), None)
        id_domain = emission.kind
        if isinstance(id_ast, dict) and isinstance(id_ast.get("domain"), str):
            id_domain = str(id_ast.get("domain"))
        if emission.kind == "page":
            raw_page = self_obj.get("pageId") if isinstance(self_obj, dict) else None
            # keyOfPage(undefined) -> pageId undefined; keep None for keyString.
            _collect_add(keys, raw_page, "", "page")
        else:
            raw_page = self_obj.get("pageId") if isinstance(self_obj, dict) else None
            raw_key = self_obj.get("occurrenceKey") if isinstance(self_obj, dict) else None
            _collect_add(keys, raw_page, raw_key, id_domain)
        if emission.kind == "edge":
            for endpoint in ("source", "target"):
                field_ast = next(
                    (value for name, value in emission.fields if name == endpoint), None
                )
                if isinstance(field_ast, dict) and field_ast.get("op") == "outputId":
                    binding = field_ast.get("binding")
                    item = (
                        emission.self
                        if binding == "self"
                        else emission.bound.get(binding)
                        if isinstance(binding, str)
                        else None
                    )
                    _collect_add_item(keys, item, "node")
        parent_ast = emission.parent_ast
        if isinstance(parent_ast, dict) and parent_ast.get("op") == "outputId":
            binding = parent_ast.get("binding")
            item = (
                emission.self
                if binding == "self"
                else emission.bound.get(binding)
                if isinstance(binding, str)
                else None
            )
            domain = parent_ast.get("domain")
            if isinstance(domain, str) and domain:
                _collect_add_item(keys, item, domain)
    return keys


def _interpret_emit_step(  # noqa: PLR0913, PLR0917 - interpret threading matches JS scope
    run: _ExportRun,
    recipe_id: str,
    step: dict[str, Json],
    bindings: dict[str, object],
    handle: object,
    self_page_id: str,
) -> str | None:
    """Interpret one emit step, keeping raw ASTs (lot4-export.ts:425-432).

    No outputId is resolved here; keys are collected after interpretation
    and outputIds resolve at assembly. ``emit.as`` never becomes a binding.
    """
    kind = step.get("kind")
    alias = step.get("as")
    fields = step.get("fields")
    if kind not in _IR_KINDS or not isinstance(alias, str) or not isinstance(fields, list):
        return "render-stale"
    kept: list[tuple[str, object]] = []
    for entry in fields:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            return "render-stale"
        kept.append((str(entry.get("name")), entry.get("value")))
    has_parent = step.get("parent") is not None
    parent_ast = step.get("parent") if has_parent else None
    run.emissions.append(
        _PlanEmit(
            recipe_id=recipe_id,
            kind=str(kind),
            fields=kept,
            parent_ast=parent_ast,
            has_parent=has_parent,
            self=handle,
            self_page_id=self_page_id,
            bound=dict(bindings),
        )
    )
    return None


def _interpret_loss_step(  # noqa: C901, PLR0911, PLR0913, PLR0917 - JS attach cases
    run: _ExportRun,
    recipe_id: str,
    step: dict[str, Json],
    bindings: dict[str, object],
    handle: object,
    self_page_id: str,
    mark: int,
) -> str | None:
    """Interpret one loss step (lot4-export.ts:402-423).

    A self loss in an iteration that already emitted a record for the same
    self attaches to that record's one ``lossAfter`` slot; otherwise it
    stands alone with an unavailable result. Target identity decides.
    """
    from bpmn_io.profile._occurrence import MISSING as _OCC_MISSING  # noqa: PLC0415

    del self_page_id
    code = step.get("code")
    if not isinstance(code, str) or not code:
        return "render-stale"
    raw_target = step.get("target")
    if raw_target == "self":
        target: object = handle
    elif isinstance(raw_target, str):
        target = bindings.get(raw_target)
        if target is None:
            return None
    else:
        return None
    if target is _OCC_MISSING or is_missing(target):
        return None
    if target is handle:
        for index in range(len(run.emissions) - 1, mark - 1, -1):
            prior = run.emissions[index]
            if not isinstance(prior, _PlanEmit):
                if isinstance(prior, _PlanLoss) and prior.self is not handle:
                    break
                continue
            if prior.self is not handle:
                break
            if prior.loss_after is None:
                prior.loss_after = code
                return None
        run.emissions.append(
            _PlanLoss(
                recipe_id=recipe_id,
                code=code,
                self=handle,
                self_page_id=(
                    str(handle.get("pageId"))
                    if isinstance(handle, dict) and isinstance(handle.get("pageId"), str)
                    else ""
                ),
                target=target,
            )
        )
        return None
    run.emissions.append(
        _PlanLoss(
            recipe_id=recipe_id,
            code=code,
            self=handle,
            self_page_id=(
                str(handle.get("pageId"))
                if isinstance(handle, dict) and isinstance(handle.get("pageId"), str)
                else ""
            ),
            target=target,
        )
    )
    return None


def _interpret_iteration(run: _ExportRun, recipe: dict[str, Json], handle: object) -> str | None:
    """Interpret one recipe iteration over its steps (refusal code or None).

    An export recipe ``when`` is never evaluated (``lot4-export.ts:370-394``;
    only capability ``when`` gates); the iteration always runs the steps.
    Output IDs stay unresolved until the ID plan exists. Property access on
    a non-object self throws non-contract ``TypeError`` in JS
    (``:389``); ``mapExport`` turns it into ``operation-error`` (N4).
    """
    # JS: const selfPageId = self.pageId — throws on undefined/null self.
    if not isinstance(handle, dict):
        return "operation-error"
    try:
        raw_page = handle.get("pageId")
    except AttributeError:
        return "operation-error"
    mark = len(run.emissions)
    bindings = _iteration_bindings(handle)
    recipe_id = str(recipe.get("id"))
    self_page_id = raw_page if isinstance(raw_page, str) else ""
    for step in recipe.get("steps", []):
        code = _interpret_step(run, recipe_id, step, bindings, handle, self_page_id, mark)
        if code is not None:
            return code
    return None


def _interpret_step(  # noqa: PLR0913, PLR0917 - interpret threading matches JS scope
    run: _ExportRun,
    recipe_id: str,
    step: object,
    bindings: dict[str, object],
    handle: object,
    self_page_id: str,
    mark: int,
) -> str | None:
    """Interpret one recipe step (refusal code or None)."""
    if not isinstance(step, dict):
        return "render-stale"
    op = step.get("op")
    if op == "bind":
        return _resolve_bind(run, step, bindings)
    if op == "emit":
        return _interpret_emit_step(run, recipe_id, step, bindings, handle, self_page_id)
    if op == "loss":
        return _interpret_loss_step(run, recipe_id, step, bindings, handle, self_page_id, mark)
    if op == "refuse":
        refused = step.get("code")
        return refused if isinstance(refused, str) and refused else "render-stale"
    return "render-stale"


def _page_sort_key(index: dict[object, int], item: object) -> int:
    """Order one page handle by its page position (lot4-export.ts:380-385)."""
    if isinstance(item, dict):
        position = index.get(item.get("pageId"), -1)
        return position if isinstance(position, int) else -1
    return -1


def _occurrence_sort_key(order: dict[object, object], item: object) -> tuple[int, bytes]:
    """Order one occurrence handle by page order then UTF-16 key."""
    if isinstance(item, dict):
        rank = order.get(item.get("pageId"), 0)
        return (
            rank if isinstance(rank, int) else 0,
            str(item.get("occurrenceKey")).encode("utf-16-be"),
        )
    return (0, b"")


def _plan_recipe(run: _ExportRun, recipe: dict[str, Json]) -> str | None:
    """Interpret one export recipe over its occurrence selector results."""
    from bpmn_io.profile._occurrence import run_occurrence_select  # noqa: PLC0415

    try:
        matched = run_occurrence_select(recipe.get("select"), _occ_scope(run, {"self": None}))
    except (ValueError, TypeError) as exc:
        return str(exc.args[0]) if exc.args else "operation-error"
    pages = [page for page in run.render.get("pages", []) if isinstance(page, dict)]
    page_index = {page.get("pageId"): index for index, page in enumerate(pages)}
    page_order = {page.get("pageId"): page.get("order", 0) for page in pages}
    select_node = recipe.get("select")
    if isinstance(select_node, dict) and select_node.get("via") == "pages":
        matched = sorted(matched, key=partial(_page_sort_key, page_index))
    elif all(
        isinstance(item, dict)
        and isinstance(item.get("pageId"), str)
        and isinstance(item.get("occurrenceKey"), str)
        for item in matched
    ):
        matched = sorted(matched, key=partial(_occurrence_sort_key, page_order))
    for item in matched:
        code = _interpret_iteration(run, recipe, item)
        if code is not None:
            return code
    return None


def _resolve_bind(
    run: _ExportRun, step: dict[str, Json], bindings: dict[str, object]
) -> str | None:
    """Run one bind step, storing its alias (refusal code or None)."""
    from bpmn_io.profile._occurrence import MISSING, run_occurrence_select  # noqa: PLC0415

    alias = step.get("as")
    cardinality = step.get("cardinality")
    if not isinstance(alias, str) or cardinality not in ("one", "zeroOrOne", "first"):
        return "render-stale"
    try:
        found = run_occurrence_select(step.get("select"), _occ_scope(run, bindings))
    except (ValueError, TypeError) as exc:
        return str(exc.args[0]) if exc.args else "operation-error"
    if cardinality == "one" and len(found) != 1:
        return "profile-ambiguous-binding"
    if cardinality in ("first", "zeroOrOne") and len(found) > 1:
        return "profile-ambiguous-binding"
    bindings[alias] = found[0] if found else MISSING
    return None


def _check_capability(run: _ExportRun) -> tuple[str, str | None]:
    """Evaluate capability records per occurrence (lot4-export.ts:304-306).

    For each render occurrence in order, evaluate every capability record's
    ``when``; refusals propagate at once. Rank is the max class rank for
    that occurrence; if rank >= 2, refuse ``render-unsupported`` immediately
    before evaluating later occurrences (N6).
    """
    classes: list[str] = []
    occurrences = [
        record for record in run.render.get("occurrences", []) if isinstance(record, dict)
    ]
    for occurrence in occurrences:
        code, rank = _check_occurrence_capability(run, occurrence, classes)
        if code is not None:
            return "structural", code
        if rank >= 2:
            return "unsupported", "render-unsupported"
    if any(outcome not in CAPABILITY_ORDER for outcome in classes):
        return "structural", "render-stale"
    capability = worst_capability([*classes, "structural"])
    if capability == "unsupported":
        return capability, "render-unsupported"
    return capability, None


def _check_occurrence_capability(
    run: _ExportRun, occurrence: dict[str, Json], classes: list[str]
) -> tuple[str | None, int]:
    """Evaluate capability records for one occurrence (rank, code).

    Returns the refusal code (if any) and the max class rank for this
    occurrence (lot4-export.ts:223-232). Losses are collected for matching
    records; unknown classes are kept for the caller's render-stale check.
    """
    from bpmn_io.profile._occurrence import test_occurrence_predicate  # noqa: PLC0415

    rank = 0
    for record in run.export.get("capabilities", []):
        if not isinstance(record, dict):
            continue
        try:
            held = test_occurrence_predicate(
                record.get("when"), _occ_scope(run, {"self": occurrence})
            )
        except (ValueError, TypeError) as exc:
            return str(exc.args[0]) if exc.args else "operation-error", 0
        if held is not True:
            continue
        outcome = record.get("class")
        if not isinstance(outcome, str):
            continue
        classes.append(outcome)
        if outcome in CAPABILITY_ORDER:
            rank = max(rank, CAPABILITY_ORDER.index(outcome))
        # Unknown class: keep for the caller's render-stale check.
        _append_capability_losses(run, occurrence, record)
    return None, rank


def _append_capability_losses(
    run: _ExportRun, occurrence: dict[str, Json], record: dict[str, Json]
) -> None:
    """Append one applicable capability record's loss entries."""
    _, _, _, source = _self_coordinates(run, occurrence)
    for loss_class in record.get("losses", []):
        if not isinstance(loss_class, str):
            continue
        run.entries.append(
            _loss_entry(
                str(run.export.get("id")), loss_class, occurrence, dict(_UNAVAILABLE), source
            )
        )


def _resolve_output_id_target(  # noqa: PLR0911 - JS resolve branches transcribed
    run: _ExportRun,
    ids: dict[str, str],
    value: dict[str, Json],
    self_page_id: str,
    emit: _PlanEmit,
) -> tuple[str | None, str | None]:
    """Resolve one outputId value AST against the ID plan (lot4-export.ts:506-528).

    Returns the allocated id or a refusal code. Mirrors the JS assembly
    position: missing/MISSING bindings refuse ``export-field-invalid``,
    native candidates that are not unique refuse
    ``export-occurrence-ambiguous``, and a planned key without an id refuses
    ``profile-ambiguous-binding``.
    """
    from bpmn_io.profile._occurrence import MISSING as _OCC_MISSING  # noqa: PLC0415

    binding = value.get("binding")
    domain = value.get("domain")
    if not isinstance(binding, str) or not isinstance(domain, str) or not domain:
        return None, "export-field-invalid"
    item = emit.self if binding == "self" else emit.bound.get(binding)
    if item is None or item is _OCC_MISSING or is_missing(item):
        return None, "export-field-invalid"
    if not isinstance(item, dict):
        return None, "export-field-invalid"
    page_id = item.get("pageId")
    occurrence_key = item.get("occurrenceKey")
    element_id = item.get("id")
    if isinstance(page_id, str) and occurrence_key is None:
        key = _key_string(page_id, "", "page")
    elif isinstance(page_id, str) and isinstance(occurrence_key, str):
        key = _key_string(page_id, occurrence_key, domain)
    elif isinstance(element_id, str):
        matches = [
            record
            for record in run.render.get("occurrences", [])
            if isinstance(record, dict)
            and record.get("semanticId") == element_id
            and record.get("pageId") == self_page_id
        ]
        if len(matches) != 1:
            return None, "export-occurrence-ambiguous"
        found = matches[0]
        found_page = found.get("pageId")
        found_key = found.get("occurrenceKey")
        if not isinstance(found_page, str) or not isinstance(found_key, str):
            return None, "export-field-invalid"
        key = _key_string(found_page, found_key, domain)
    else:
        return None, "export-field-invalid"
    resolved = ids.get(key)
    if resolved is None:
        return None, "profile-ambiguous-binding"
    return resolved, None


def _assemble_field_value(  # noqa: PLR0911 - JS field branches transcribed
    run: _ExportRun,
    emit: _PlanEmit,
    ids: dict[str, str],
    name: str,
) -> tuple[object, str | None]:
    """Evaluate one named field at its JS assembly position (value, code).

    Missing fields read as MISSING; outputIds resolve against the ID plan
    at this position, never prematurely.
    """
    from bpmn_io.profile._occurrence import MISSING as _OCC_MISSING  # noqa: PLC0415

    ast: object = _OCC_MISSING
    found = False
    for entry_name, entry_value in emit.fields:
        if entry_name == name:
            ast = entry_value
            found = True
            break
    if not found:
        return _OCC_MISSING, None
    if isinstance(ast, dict) and ast.get("op") == "outputId":
        resolved, code = _resolve_output_id_target(run, ids, ast, emit.self_page_id, emit)
        if code is not None:
            return None, code
        return resolved, None
    if not isinstance(ast, dict) and not isinstance(ast, (str, int, float, bool)):
        return _OCC_MISSING, None
    if isinstance(ast, str):
        return ast, None
    # JS field values evaluate with bound {self, ...aliases} (lot4-export.ts:565).
    value, code = _eval_step_value(run, ast, {"self": emit.self, **emit.bound})
    if code is not None:
        return None, code
    if value is None:
        # JS undefined normalizes to MISSING (lot4-export.ts:566).
        return _OCC_MISSING, None
    return value, None


@dataclass
class _Assembled:
    """Mutable per-call assembly state (symbol table and outputs)."""

    ids: dict[str, str] = field(default_factory=dict)
    planned: set[str] = field(default_factory=set)
    table: dict[str, tuple[str, int]] = field(default_factory=dict)
    ir: list[dict[str, Json]] = field(default_factory=list)
    id_map: list[dict[str, Json]] = field(default_factory=list)


def _assemble_id(  # noqa: PLR0911 - JS id branches transcribed
    run: _ExportRun, emit: _PlanEmit, ids: dict[str, str]
) -> tuple[str | None, str | None]:
    """Resolve one emit's record id in JS order (lot4-export.ts:570-582)."""
    from bpmn_io.profile._occurrence import MISSING as _OCC_MISSING  # noqa: PLC0415

    has_id = any(name == "id" for name, _ in emit.fields)
    if has_id:
        value, code = _assemble_field_value(run, emit, ids, "id")
        if code is not None:
            return None, code
        if value is _OCC_MISSING or not isinstance(value, str):
            return None, "export-field-invalid"
        return value, None
    if emit.kind == "page":
        # JS: ids.get(keyString(keyOfPage(selfPageId))) — selfPageId may be
        # undefined; use the raw self.pageId for key consistency.
        raw_page = emit.self.get("pageId") if isinstance(emit.self, dict) else None
        resolved = ids.get(_js_key_string(raw_page, "", "page"))
        if resolved is None:
            return None, "profile-ambiguous-binding"
        return resolved, None
    if emit.kind in ("node", "edge", "label"):
        raw_page = emit.self.get("pageId") if isinstance(emit.self, dict) else None
        raw_key = emit.self.get("occurrenceKey") if isinstance(emit.self, dict) else None
        resolved = ids.get(_js_key_string(raw_page, raw_key, emit.kind))
        if resolved is None:
            return None, "profile-ambiguous-binding"
        return resolved, None
    return None, None


def _assemble_parent(  # noqa: PLR0911 - JS parent branches transcribed
    run: _ExportRun, emit: _PlanEmit, ids: dict[str, str]
) -> tuple[object, str | None]:
    """Resolve one emit's parent value (lot4-export.ts:591-597, :647-653).

    An explicit outputId resolves over the bound aliases; any other parent
    value evaluates with bound ``{self}`` only (R5-05). Implicit parents
    use the planned page-ID key, not the emitted page id (R6-03).
    """
    from bpmn_io.profile._occurrence import MISSING as _OCC_MISSING  # noqa: PLC0415

    if emit.has_parent:
        ast = emit.parent_ast
        if isinstance(ast, dict) and ast.get("op") == "outputId":
            resolved, code = _resolve_output_id_target(run, ids, ast, emit.self_page_id, emit)
            if code is not None:
                return None, code
            return resolved, None
        value, code = _eval_step_value(run, ast, {"self": emit.self})
        if code is not None:
            return None, code
        if value is _OCC_MISSING or value is None or is_missing(value):
            if emit.kind == "metadata":
                return None, None
            return None, "export-field-invalid"
        if not isinstance(value, str):
            if emit.kind == "metadata":
                return None, None
            return None, "export-parent-invalid"
        return value, None
    if emit.kind in ("node", "edge", "label"):
        raw_page = emit.self.get("pageId") if isinstance(emit.self, dict) else None
        return ids.get(_js_key_string(raw_page, "", "page")), None
    return None, None


def _check_parent(parent: object, record_id: str | None, out: _Assembled) -> str | None:
    """Apply the JS planned/emitted parent checks (lot4-export.ts:599-605)."""
    if not isinstance(parent, str):
        return "export-field-invalid"
    if record_id is not None and parent == record_id:
        return "export-parent-invalid"
    if parent not in out.planned:
        return "export-parent-invalid"
    if parent not in out.table:
        return "export-parent-order"
    if out.table[parent][0] not in ("page", "node"):
        return "export-parent-invalid"
    return None


def _assemble_edge_endpoints(
    run: _ExportRun, emit: _PlanEmit, ids: dict[str, str]
) -> tuple[object, object, str | None]:
    """Resolve one edge's source/target in JS order (lot4-export.ts:620-630).

    Missing endpoints refuse ``export-field-invalid``; endpoints not yet
    emitted refuse ``export-parent-order`` with no kind or planned checks.
    """
    from bpmn_io.profile._occurrence import MISSING as _OCC_MISSING  # noqa: PLC0415

    source, code = _assemble_field_value(run, emit, ids, "source")
    if code is not None:
        return None, None, code
    target, code = _assemble_field_value(run, emit, ids, "target")
    if code is not None:
        return None, None, code
    if source is _OCC_MISSING or target is _OCC_MISSING:
        return None, None, "export-field-invalid"
    return source, target, None


def _self_member(self_obj: object, name: str) -> object:
    """Return one emission-self member, ``_UNDEFINED`` when absent (lot4-export.ts:587)."""
    if isinstance(self_obj, dict):
        return self_obj.get(name, _UNDEFINED)
    return _UNDEFINED


def _assemble_one_page(
    run: _ExportRun, emit: _PlanEmit, ids: dict[str, str], record_id: str
) -> tuple[dict[str, Json] | None, str | None]:
    """Assemble one page record in JS order (lot4-export.ts:584-587)."""
    from bpmn_io.profile._occurrence import MISSING as _OCC_MISSING  # noqa: PLC0415

    name, code = _assemble_field_value(run, emit, ids, "name")
    if code is not None:
        return None, code
    if name is _OCC_MISSING:
        return None, "export-field-invalid"
    # JS reads members from the emission self, never from the render again (N13).
    record: dict[str, Json] = {
        "kind": "page",
        "id": record_id,
        "name": name,
        "bounds": _self_member(emit.self, "bounds"),
    }
    return record, None


def _assemble_one_node(
    run: _ExportRun, emit: _PlanEmit, ids: dict[str, str], record_id: str, parent: object
) -> tuple[dict[str, Json] | None, str | None]:
    """Assemble one node record in JS order (lot4-export.ts:606-619)."""
    from bpmn_io.profile._occurrence import MISSING as _OCC_MISSING  # noqa: PLC0415

    record: dict[str, Json] = {"kind": "node", "id": record_id}
    name, code = _assemble_field_value(run, emit, ids, "name")
    if code is not None:
        return None, code
    if name is not _OCC_MISSING:
        record["name"] = name
    # JS order: parent, bounds, style from the emission self (N13, §2.7).
    record["parent"] = parent
    record["bounds"] = _self_member(emit.self, "bounds")
    record["style"] = _self_member(emit.self, "style")
    occurrence = emit.self if isinstance(emit.self, dict) else {}
    label = occurrence.get("label") if isinstance(occurrence, dict) else None
    if isinstance(label, dict):
        # N11: node name defaults to the occurrence label text when unset.
        if "name" not in record:
            record["name"] = label.get("text", _UNDEFINED)
        record["label"] = {
            "bounds": label.get("bounds", _UNDEFINED),
            "lines": label.get("lines", _UNDEFINED),
        }
    for field_name, _ in emit.fields:
        if field_name in ("id", "name", "parent"):
            continue
        value, code = _assemble_field_value(run, emit, ids, field_name)
        if code is not None:
            return None, code
        if value is not _OCC_MISSING:
            record[field_name] = value
    return record, None


def _assemble_one_edge(  # noqa: PLR0913, PLR0917 - edge threading matches JS scope
    run: _ExportRun,
    emit: _PlanEmit,
    ids: dict[str, str],
    record_id: str,
    parent: object,
    out: _Assembled,
) -> tuple[dict[str, Json] | None, str | None]:
    """Assemble one edge record in JS order (lot4-export.ts:620-633).

    Endpoints resolve and order-check before any optional field, so an
    endpoint order refusal precedes an optional-field refusal.
    """
    from bpmn_io.profile._occurrence import MISSING as _OCC_MISSING  # noqa: PLC0415

    source, target, code = _assemble_edge_endpoints(run, emit, ids)
    if code is not None:
        return None, code
    if not isinstance(source, str) or not isinstance(target, str):
        return None, "export-field-invalid"
    if source not in out.table or target not in out.table:
        return None, "export-parent-order"
    record: dict[str, Json] = {"kind": "edge", "id": record_id, "source": source, "target": target}
    for field_name, _ in emit.fields:
        if field_name in ("id", "source", "target", "parent"):
            continue
        value, fcode = _assemble_field_value(run, emit, ids, field_name)
        if fcode is not None:
            return None, fcode
        if value is not _OCC_MISSING:
            record[field_name] = value
    # JS order: parent, bounds, waypoints, style from the emission self (N13).
    record["parent"] = parent
    record["bounds"] = _self_member(emit.self, "bounds")
    record["waypoints"] = _self_member(emit.self, "waypoints")
    record["style"] = _self_member(emit.self, "style")
    occurrence = emit.self if isinstance(emit.self, dict) else {}
    label = occurrence.get("label") if isinstance(occurrence, dict) else None
    if isinstance(label, dict):
        record["label"] = {
            "bounds": label.get("bounds", _UNDEFINED),
            "lines": label.get("lines", _UNDEFINED),
        }
    return record, None


def _assemble_one_label(
    run: _ExportRun, emit: _PlanEmit, ids: dict[str, str], record_id: str, parent: object
) -> tuple[dict[str, Json] | None, str | None]:
    """Assemble one label record in JS order (lot4-export.ts:634-642)."""
    from bpmn_io.profile._occurrence import MISSING as _OCC_MISSING  # noqa: PLC0415

    text, code = _assemble_field_value(run, emit, ids, "text")
    if code is not None:
        return None, code
    if text is _OCC_MISSING:
        return None, "export-field-invalid"
    occurrence = emit.self if isinstance(emit.self, dict) else {}
    label = occurrence.get("label") if isinstance(occurrence, dict) else None
    if not isinstance(label, dict):
        return None, "export-field-invalid"
    record: dict[str, Json] = {
        "kind": "label",
        "id": record_id,
        "text": text,
        "parent": parent,
        "bounds": label.get("bounds", _UNDEFINED),
        "lines": label.get("lines", _UNDEFINED),
    }
    return record, None


def _assemble_one_metadata(
    run: _ExportRun, emit: _PlanEmit, ids: dict[str, str]
) -> tuple[dict[str, Json] | None, str | None]:
    """Assemble one metadata record in JS order (lot4-export.ts:643-654)."""
    from bpmn_io.profile._occurrence import MISSING as _OCC_MISSING  # noqa: PLC0415

    name, code = _assemble_field_value(run, emit, ids, "name")
    if code is not None:
        return None, code
    value, code = _assemble_field_value(run, emit, ids, "value")
    if code is not None:
        return None, code
    if name is _OCC_MISSING or value is _OCC_MISSING:
        return None, "export-field-invalid"
    record: dict[str, Json] = {"kind": "metadata", "name": name, "value": value}
    if emit.has_parent and emit.parent_ast is not None:
        ast = emit.parent_ast
        if isinstance(ast, dict) and ast.get("op") == "outputId":
            out_parent, pcode = _resolve_output_id_target(run, ids, ast, emit.self_page_id, emit)
            if pcode is not None:
                return None, pcode
            if isinstance(out_parent, str):
                record["parent"] = out_parent
        else:
            eval_parent, pcode = _eval_step_value(run, ast, {"self": emit.self})
            if pcode is not None:
                return None, pcode
            if isinstance(eval_parent, str):
                record["parent"] = eval_parent
    return record, None


def _assemble_one_emit(  # noqa: C901, PLR0911, PLR0912 - JS per-kind order transcribed
    run: _ExportRun, emit: _PlanEmit, ids: dict[str, str], out: _Assembled
) -> tuple[dict[str, Json] | None, object, str | None]:
    """Assemble one emit in JS per-kind order (record, record_id, code)."""
    record_id, code = _assemble_id(run, emit, ids)
    if code is not None:
        return None, None, code
    if isinstance(record_id, str) and record_id in out.table:
        return None, None, "export-parent-invalid"
    if emit.kind == "page":
        if not isinstance(record_id, str):
            return None, None, "export-field-invalid"
        record, code = _assemble_one_page(run, emit, ids, record_id)
        if code is not None or record is None:
            return None, None, code or "export-field-invalid"
        return record, record_id, None
    if emit.kind in ("node", "edge", "label"):
        if not isinstance(record_id, str):
            return None, None, "export-field-invalid"
        parent, code = _assemble_parent(run, emit, ids)
        if code is not None:
            return None, None, code
        pcode = _check_parent(parent, record_id, out)
        if pcode is not None:
            return None, None, pcode
        if emit.kind == "node":
            record, code = _assemble_one_node(run, emit, ids, record_id, parent)
        elif emit.kind == "edge":
            # Endpoints resolve after the parent checks, before optional fields.
            record, code = _assemble_one_edge(run, emit, ids, record_id, parent, out)
            if code is None and record is not None:
                src = record.get("source")
                tgt = record.get("target")
                if not isinstance(src, str) or not isinstance(tgt, str):
                    return None, None, "export-field-invalid"
                if src not in out.table or tgt not in out.table:
                    return None, None, "export-parent-order"
        else:
            record, code = _assemble_one_label(run, emit, ids, record_id, parent)
        if code is not None or record is None:
            return None, None, code or "export-field-invalid"
        return record, record_id, None
    record, code = _assemble_one_metadata(run, emit, ids)
    if code is not None or record is None:
        return None, None, code or "export-field-invalid"
    # Metadata has no id; JS keeps resultId undefined for the idMap row (R6-09).
    return record, _UNDEFINED, None


def _append_id_map(out: _Assembled, emit: _PlanEmit, record_id: object) -> None:
    """Append one emit's idMap row (lot4-export.ts:662-669, R6-09).

    Page rows always; other kinds when the self carries a defined
    ``semanticId`` (``!== undefined``) — including metadata, whose id is
    undefined and whose row fails ``sortIdMap`` validation with
    ``operation-error`` by transcription.
    """
    raw_page = emit.self.get("pageId") if isinstance(emit.self, dict) else None
    # JS undefined for missing members; None stands for undefined here
    # (render JSON has no undefined literal).
    if emit.kind == "page":
        out.id_map.append(
            {
                "sourceId": raw_page,
                "resultId": record_id,
                "domain": "export",
                "pageId": raw_page,
            }
        )
        return
    self_obj = emit.self if isinstance(emit.self, dict) else {}
    if isinstance(self_obj, dict) and "semanticId" in self_obj:
        semantic_id = self_obj.get("semanticId")
        raw_key = self_obj.get("occurrenceKey") if isinstance(self_obj, dict) else None
        out.id_map.append(
            {
                "sourceId": semantic_id,
                "resultId": record_id,
                "domain": "export",
                "pageId": raw_page,
                "occurrenceKey": raw_key,
            }
        )


def _append_adapter_loss(run: _ExportRun, emit: _PlanEmit, index: int) -> None:
    """Append one adapter metadata loss (lot4-export.ts:678-694, §2.8).

    Every metadata record gets the entry (the ``writtenMetadata`` set holds
    objects, so membership never holds); only ``pageId`` is present.
    """
    if emit.kind != "metadata":
        return
    run.entries.append(_adapter_loss_entry(emit.self, index, _metadata_self_source(run, emit)))


def _metadata_self_source(run: _ExportRun, emit: _PlanEmit) -> dict[str, Json]:
    """Build the adapter-loss source of one emitted record (lot4-export.ts:698-708)."""
    self_obj = emit.self
    if isinstance(self_obj, dict) and self_obj.get("$type") == "bpmn:Definitions":
        element_id = self_obj.get("id")
        return {
            "domain": "tree",
            "pointer": "",
            "targetId": element_id if isinstance(element_id, str) else None,
            "provenance": "exact",
        }
    if isinstance(self_obj, dict) and isinstance(self_obj.get("pageId"), str):
        if self_obj.get("occurrenceKey") is None:
            return dict(_UNAVAILABLE)
        _, _, _, source = _self_coordinates(run, self_obj)
        return source
    if isinstance(self_obj, dict):
        return _native_source(run, self_obj)
    return dict(_UNAVAILABLE)


def _standalone_loss_source(run: _ExportRun, item: _PlanLoss) -> dict[str, Json]:
    """Build the source of one standalone loss (lot4-export.ts:549-557)."""
    target = item.target
    if isinstance(target, dict) and isinstance(target.get("$type"), str):
        return _native_source(run, target)
    _, _, _, source = _self_coordinates(run, item.self)
    return source


def _run_emission(
    run: _ExportRun, ids: dict[str, str]
) -> tuple[list[dict[str, Json]], list[dict[str, Json]], str | None]:
    """Assemble interpreted emissions in JS order (ir, idMap, code).

    Standalone losses keep an unavailable result; attached self losses use
    the record's one ``lossAfter`` slot with artifact coordinates
    (lot4-export.ts:402-423, :549-661).
    """
    out = _Assembled(ids=dict(ids), planned=set(ids.values()))
    for emission in run.emissions:
        if isinstance(emission, _PlanLoss):
            source = _standalone_loss_source(run, emission)
            run.entries.append(
                _loss_entry(
                    emission.recipe_id, emission.code, emission.self, dict(_UNAVAILABLE), source
                )
            )
            continue
        if not isinstance(emission, _PlanEmit):
            return [], [], "render-stale"
        record, record_id, code = _assemble_one_emit(run, emission, ids, out)
        if code is not None or record is None:
            return [], [], code or "export-field-invalid"
        if isinstance(record_id, str):
            out.table[record_id] = (emission.kind, len(out.ir))
        index = len(out.ir)
        out.ir.append(record)
        _append_id_map(out, emission, record_id)
        _append_adapter_loss(run, emission, index)
        if emission.loss_after is not None:
            _, _, _, attached_source = _self_coordinates(run, emission.self)
            run.entries.append(
                _loss_entry(
                    emission.recipe_id,
                    emission.loss_after,
                    emission.self,
                    {
                        "domain": "artifact",
                        "pointer": f"/ir/{index}",
                        "targetId": record_id if isinstance(record_id, str) else _UNDEFINED,
                        "provenance": "exact",
                    },
                    attached_source,
                )
            )
    return out.ir, out.id_map, None


def _select_export(
    compiled: object,
    format: object,  # noqa: A002 - format is the exports[] member name
) -> tuple[dict[str, Json] | None, str | None]:
    """Find the unique exports[] record with a registered adapter."""
    if not isinstance(format, str):
        return None, "export-format-unsupported"
    profile = getattr(compiled, "profile", None)
    records = profile.get("exports", []) if isinstance(profile, dict) else []
    match = None
    for record in records:
        if isinstance(record, dict) and record.get("format") == format:
            match = record
            break
    if match is None or format not in ADAPTERS:
        return None, "export-format-unsupported"
    return match, None


def map_export(
    compiled: object,
    envelope: object,
    layout: object,
    r: object,
    format: object,  # noqa: A002 - spec binding signature names the format member
) -> ResultSuccess | ResultRefused:
    """Map one fresh RenderData/1 to a PreparedArtifact (DESIGN §10.2)."""
    wire, echo_identity, echo_revision, refused = _begin_operation("mapExport", compiled, envelope)
    if refused is not None:
        return refused
    checked, code = _map_checked(compiled, wire, layout, r, format)
    if code is not None or checked is None:
        return refused_result("mapExport", code or "render-stale", echo_identity, echo_revision)
    export, tree, candidate = checked
    for entry in candidate.get("coverage", []):
        if isinstance(entry, dict) and entry.get("disposition") == "unsupported":
            return refused_result("mapExport", "render-unsupported", echo_identity, echo_revision)
    wire_bindings = wire.get("bindings") if isinstance(wire, dict) else None
    run, capability, code = _map_planned(compiled, tree, candidate, export, format, wire_bindings)
    if code is not None or run is None or capability is None:
        return refused_result("mapExport", code or "render-stale", echo_identity, echo_revision)
    return _map_finished(run, candidate, format, capability, (echo_identity, echo_revision))


def _validate_id_map(
    rows: list[dict[str, Json]],
) -> tuple[list[dict[str, Json]] | None, str | None]:
    """Validate and sort one idMap (report.ts:72-80, §2.9 step 2).

    Every row must have ``sourceId``, ``resultId``, ``domain``, optional
    ``pageId``/``occurrenceKey``; every present member among those four must
    be a non-empty string, else ``operation-error`` (failContract without a
    code). Order is domain, pageId, occurrenceKey, sourceId, resultId with
    absent first in UTF-16.
    """
    for row in rows:
        allowed = ("sourceId", "resultId", "domain", "pageId", "occurrenceKey")
        if (
            "sourceId" not in row
            or "resultId" not in row
            or "domain" not in row
            or any(k not in allowed for k in row)
        ):
            return None, "operation-error"
        if row.get("domain") not in ("migration", "export"):
            return None, "operation-error"
        for key in ("sourceId", "resultId", "pageId", "occurrenceKey"):
            if key in row:
                value = row[key]
                if not isinstance(value, str) or value == "":
                    return None, "operation-error"

    def _opt(value: object) -> tuple[bytes, bytes]:
        if value is None:
            return (b"\x00", b"")
        return (b"\x01", str(value).encode("utf-16-be"))

    def _key(row: dict[str, Json]) -> tuple[bytes, ...]:
        return (
            str(row.get("domain")).encode("utf-16-be"),
            *_opt(row.get("pageId")),
            *_opt(row.get("occurrenceKey")),
            str(row.get("sourceId")).encode("utf-16-be"),
            str(row.get("resultId")).encode("utf-16-be"),
        )

    return sorted(rows, key=_key), None


def _digest_ir(ir: list[dict[str, Json]]) -> tuple[str | None, str | None]:
    """Digest one IR (canonical.ts:36, §2.9 step 3).

    An ``_UNDEFINED`` member anywhere refuses ``profile-json``; lone
    surrogates refuse ``profile-unicode``; non-finite numbers refuse
    ``profile-number``.
    """
    try:
        return digest(ir), None
    except ValueError as exc:
        message = str(exc)
        if "lone surrogates" in message:
            return None, "profile-unicode"
        if "non-finite" in message:
            return None, "profile-number"
        return None, "profile-json"
    except Exception:  # noqa: BLE001 - canonicalization failure -> profile-json
        return None, "profile-json"


def _map_entry_sort_key(
    entry: ReportEntry,
) -> tuple[object, ...]:
    """Return the lot4-result.ts:36-56 sort key for one entry (§2.9 step 5)."""

    def _opt(value: object) -> tuple[bytes, bytes]:
        if value is None:
            return (b"\x00", b"")
        return (b"\x01", str(value).encode("utf-16-be"))

    if entry.before_present:
        before = (b"\x01", jcs(entry.before).encode("utf-8"))
    else:
        before = (b"\x00", b"")
    if entry.after_present:  # noqa: SIM108
        after = (b"\x01", jcs(entry.after).encode("utf-8"))
    else:
        after = (b"\x00", b"")
    stage_rank = {
        "load": 0,
        "import": 1,
        "complete": 2,
        "pre-normalize": 3,
        "normalize": 4,
        "post-normalize": 5,
        "layout": 6,
        "post-layout": 7,
        "release": 8,
        "render": 9,
        "export": 10,
    }.get(entry.stage, 99)
    return (
        stage_rank,
        _utf16(entry.rule_id),
        _utf16(entry.source.domain),
        _opt(entry.source.pointer),
        _opt(entry.source.target_id),
        _utf16(entry.code),
        _opt(entry.page_id),
        _opt(entry.occurrence_key),
        before,
        after,
        _opt(entry.result.domain),
        _opt(entry.result.pointer),
        _opt(entry.result.target_id),
        _opt(entry.property),
    )


def _short_entry_sort_key(
    entry: ReportEntry,
) -> tuple[object, ...]:
    """Return the report.ts:64-70 sort key (buildReport stable order)."""

    def _opt(value: object) -> tuple[bytes, bytes]:
        if value is None:
            return (b"\x00", b"")
        return (b"\x01", str(value).encode("utf-16-be"))

    if entry.before_present:
        before = (b"\x01", jcs(entry.before).encode("utf-8"))
    else:
        before = (b"\x00", b"")
    if entry.after_present:  # noqa: SIM108
        after = (b"\x01", jcs(entry.after).encode("utf-8"))
    else:
        after = (b"\x00", b"")
    stage_rank = {
        "load": 0,
        "import": 1,
        "complete": 2,
        "pre-normalize": 3,
        "normalize": 4,
        "post-normalize": 5,
        "layout": 6,
        "post-layout": 7,
        "release": 8,
        "render": 9,
        "export": 10,
    }.get(entry.stage, 99)
    return (
        stage_rank,
        _utf16(entry.rule_id),
        _utf16(entry.source.domain),
        _opt(entry.source.pointer),
        _opt(entry.source.target_id),
        _utf16(entry.code),
        _opt(entry.page_id),
        _opt(entry.occurrence_key),
        before,
        after,
    )


def _validate_and_sort_entries(  # noqa: C901, PLR0911
    entries: list[ReportEntry],
) -> tuple[list[ReportEntry] | None, str | None]:
    """Validate and order map entries (§2.9 steps 4-5, N12).

    Canonical form first (``_UNDEFINED`` → ``profile-json``), then the
    empty-string coordinate rule (→ ``operation-error``). Order is the
    lot4-result full key, then the stable ``compareEntries`` order, with
    canonical-duplicate removal (first kept).
    """
    for entry in entries:
        wire = entry.to_json()
        try:
            jcs(wire)
        except ValueError as exc:
            message = str(exc)
            if "lone surrogates" in message:
                return None, "profile-unicode"
            if "non-finite" in message:
                return None, "profile-number"
            return None, "profile-json"
        except Exception:  # noqa: BLE001 - _UNDEFINED or shape -> profile-json
            return None, "profile-json"
        # Empty-string members refuse operation-error (boundary text()).
        for coord in (wire.get("source"), wire.get("result")):
            if isinstance(coord, dict) and coord.get("targetId") == "":
                return None, "operation-error"
        for key in (
            "code",
            "ruleId",
            "messageKey",
            "pageId",
            "occurrenceKey",
            "emittedType",
            "property",
        ):
            if key in wire and wire[key] == "":
                return None, "operation-error"
    # Full-key sort, then stable short-key sort (both stable in Python).
    by_full = sorted(entries, key=_map_entry_sort_key)
    by_short = sorted(by_full, key=_short_entry_sort_key)
    seen: set[str] = set()
    merged: list[ReportEntry] = []
    for entry in by_short:
        try:
            text = jcs(entry.to_json())
        except Exception:  # noqa: BLE001 - already validated; keep profile-json
            return None, "profile-json"
        if text in seen:
            continue
        seen.add(text)
        merged.append(entry)
    return merged, None


def _map_finished(  # noqa: PLR0911
    run: _ExportRun,
    candidate: dict[str, Json],
    format: object,  # noqa: A002 - format is the exports[] member name
    capability: str,
    echo: tuple[dict[str, object] | None, str | None],
) -> ResultSuccess | ResultRefused:
    """Allocate, emit, assemble and finalize one planned run (§2.9)."""
    echo_identity, echo_revision = echo
    allocated, code = _map_allocated(run)
    if code is not None or allocated is None:
        return refused_result(
            "mapExport", code or "export-id-ambiguous", echo_identity, echo_revision
        )
    ir, id_map, code = _run_emission(run, allocated)
    if code is not None:
        return refused_result("mapExport", code, echo_identity, echo_revision)
    binding = copy.deepcopy(candidate.get("binding"))
    if not isinstance(binding, dict):
        return refused_result("mapExport", "render-stale", echo_identity, echo_revision)
    view = view_revision(binding)
    identity = copy.deepcopy(echo_identity) if echo_identity is not None else {}
    revision = echo_revision or ""
    sorted_map, code = _validate_id_map(id_map)
    if code is not None or sorted_map is None:
        return refused_result("mapExport", code or "operation-error", echo_identity, echo_revision)
    ir_digest, code = _digest_ir(ir)
    if code is not None or ir_digest is None:
        return refused_result("mapExport", code or "profile-json", echo_identity, echo_revision)
    merged, code = _validate_and_sort_entries(list(run.entries))
    if code is not None or merged is None:
        return refused_result("mapExport", code or "operation-error", echo_identity, echo_revision)
    artifacts: list[dict[str, Json]] = [
        {
            "format": str(format),
            "capability": capability,
            "digest": ir_digest,
            "entryIndexes": list(range(len(merged))),
        }
    ]
    # Build the report without re-sorting (entries already in final order).
    # report_with_header sorts via shared keys; construct directly to keep
    # the transcribed map order, then validate through to_json order?
    # Use report_with_header but with pre-sorted entries; Report.to_json
    # re-sorts with the shared key, so build the payload manually to keep
    # the map order while reusing the header validation.
    from bpmn_io.profile._results import Report  # noqa: PLC0415

    report = Report(
        operation="mapExport",
        entries=tuple(merged),
        raw_standard_findings=(),
        id_map=tuple(sorted_map),
        artifacts=tuple(artifacts),
        source_identity=copy.deepcopy(identity),
        target_identity=copy.deepcopy(identity),
        input_revision=revision,
        output_revision=revision,
    )
    payload: dict[str, Json] = {
        "format": str(format),
        "profileIdentity": identity,
        "semanticRevision": revision,
        "viewRevision": view,
        "ir": ir,
        "renderBinding": binding,
        "report": {
            "reportVersion": "2",
            "operation": "mapExport",
            "entries": [e.to_json() for e in merged],
            "rawStandardFindings": [],
            "idMap": sorted_map,
            "artifacts": artifacts,
            "sourceIdentity": copy.deepcopy(identity),
            "targetIdentity": copy.deepcopy(identity),
            "inputRevision": revision,
            "outputRevision": revision,
        },
        "capability": capability,
        "idMap": sorted_map,
    }
    return ResultSuccess(
        operation="mapExport",
        profile_identity=identity,
        base_revision=revision,
        revision=revision,
        payload=payload,
        report=report,
    )


def _map_checked(
    compiled: object,
    wire: dict[str, Json] | None,
    layout: object,
    r: object,
    format: object,  # noqa: A002 - format is the exports[] member name
) -> tuple[tuple[dict[str, Json], dict[str, Json], dict[str, Json]] | None, str | None]:
    """Check compatibility, format and freshness (checked triple, code)."""
    if wire is None:
        return None, "render-stale"
    export, code = _select_export(compiled, format)
    if export is None or code is not None:
        return None, code or "export-format-unsupported"
    candidate = copy.deepcopy(r) if isinstance(r, dict) else r
    source_layout = copy.deepcopy(layout) if isinstance(layout, dict) else layout
    tree = wire.get("tree")
    bindings = wire.get("bindings")
    theme_echoes = candidate.get("binding", {}) if isinstance(candidate, dict) else {}
    theme_id = theme_echoes.get("themeId") if isinstance(theme_echoes, dict) else None
    code = check_render_freshness(compiled, tree, bindings, source_layout, candidate, theme_id)
    if code is not None:
        return None, code
    if (
        not isinstance(candidate, dict)
        or not isinstance(tree, dict)
        or not isinstance(bindings, list)
    ):
        return None, "render-stale"
    return (export, tree, candidate), None


def _map_planned(  # noqa: PLR0913, PLR0917 - support threading matches map_export
    compiled: object,
    tree: dict[str, Json],
    candidate: dict[str, Json],
    export: dict[str, Json],
    format: object,  # noqa: A002 - format is the exports[] member name
    support: object = None,
) -> tuple[_ExportRun | None, str | None, str | None]:
    """Build one export run through capability and planning (run, class, code)."""
    run = _ExportRun()
    run.compiled = compiled
    run.tree = tree
    by_id, _, _ = index_tree(tree)
    run.by_id = by_id
    run.pointers = _pointer_map(tree)
    run.render = candidate
    run.pages = {
        str(page.get("pageId")): page
        for page in candidate.get("pages", [])
        if isinstance(page, dict) and isinstance(page.get("pageId"), str)
    }
    run.export = export
    adapter = ADAPTERS.get(str(format))
    if not isinstance(adapter, dict):
        return None, None, "export-format-unsupported"
    run.adapter = adapter
    notions = getattr(compiled, "notions", None)
    _types = getattr(compiled, "types", None)
    _refs = getattr(compiled, "ref_fields", None)
    run.context = make_read_context(
        tree,
        notions=notions if isinstance(notions, dict) else {},
        reference_properties=reference_property_names(_types, _refs),
        types=_types if isinstance(_types, dict) else None,
        ref_fields=_refs,
    )
    # Support bindings drive boundRole recognition (e.g. the band notion);
    # attach the wire bindings like the render read context does.
    support_entries = support if isinstance(support, list) else []
    run.context = dataclasses.replace(
        run.context,
        bindings=tuple(entry for entry in support_entries if isinstance(entry, dict)),
    )
    capability, code = _check_capability(run)
    if code is not None:
        return None, None, code
    recipes = getattr(compiled, "recipes", {})
    for recipe_id in export.get("recipes", []):
        recipe = recipes.get(recipe_id) if isinstance(recipes, dict) else None
        if not isinstance(recipe, dict):
            return None, None, "export-format-unsupported"
        code = _plan_recipe(run, recipe)
        if code is not None:
            return None, None, code
    # N7: exports[].metadata is inert in JS (no static metadata records).
    return run, capability, None


def _is_safe_integer(value: object) -> bool:
    """Return whether one value is a JS safe integer (lot4-export.ts:477)."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return -(2**53 - 1) <= value <= 2**53 - 1
    if isinstance(value, float):
        return value.is_integer() and -(2**53 - 1) <= value <= 2**53 - 1
    return False


def _plan_counter_ids(  # noqa: C901
    keys: list[tuple[object, object, str]],
    pages: list[dict[str, object]],
    origin: object,
) -> tuple[dict[str, str] | None, str | None]:
    """Plan counter ids (lot4-export.ts:476-484, §2.5).

    Deduplicated keys stably sorted by domain, numeric page order, UTF-16
    occurrenceKey. Numeric page order uses first-match render order.
    """
    if not _is_safe_integer(origin):
        return None, "export-id-ambiguous"
    origin_int = int(origin)  # type: ignore[call-overload]
    unique: list[tuple[object, object, str]] = []
    seen: set[str] = set()
    for key in keys:
        text = _js_key_string(*key)
        if text not in seen:
            seen.add(text)
            unique.append(key)
    order_list = [(p.get("pageId"), p.get("order")) for p in pages if isinstance(p, dict)]

    def _order_of(page_id: object) -> float:
        for pid, order in order_list:
            if pid == page_id:
                if isinstance(order, bool):
                    return 0.0
                if isinstance(order, (int, float)):
                    try:
                        number = float(order)
                    except (ValueError, OverflowError):
                        return 0.0
                    if math.isnan(number):
                        return 0.0
                    return number
                return 0.0
        return 0.0

    decorated = list(enumerate(unique))
    decorated.sort(
        key=lambda pair: (
            _DOMAIN_ORDER.index(pair[1][2]),
            _order_of(pair[1][0]),
            _utf16(pair[1][1] if isinstance(pair[1][1], str) else ""),
            pair[0],
        )
    )
    ids: dict[str, str] = {}
    for index, (_, key) in enumerate(decorated):
        ids[_js_key_string(*key)] = f"e_{origin_int + index}"
    return ids, None


def _plan_digest_ids(
    keys: list[tuple[object, object, str]],
) -> tuple[dict[str, str] | None, str | None]:
    """Plan digest ids (lot4-export.ts:312, §2.5).

    An undefined member makes canonicalization throw ``profile-json`` (N5).
    """
    ids: dict[str, str] = {}
    for key in keys:
        page_id, occurrence_key, domain = key
        # JS H([pageId, occurrenceKey, domain]) with undefined members throws.
        if page_id is None or occurrence_key is None:
            return None, "profile-json"
        # JSON null would hash, but keys never carry null (None = undefined).
        try:
            allocated = f"e_{digest([page_id, occurrence_key, domain])}"
        except Exception:  # noqa: BLE001 - canonicalization failure -> profile-json
            return None, "profile-json"
        ids[_js_key_string(page_id, occurrence_key, domain)] = allocated
    return ids, None


def _plan_native_ids(
    keys: list[tuple[object, object, str]],
    occurrences: list[object],
) -> tuple[dict[str, str] | None, str | None]:
    """Plan native ids (lot4-export.ts:486-503, §2.5)."""
    ids: dict[str, str] = {}
    used: dict[str, str] = {}
    for key in keys:
        text = _js_key_string(*key)
        if text in ids:
            continue
        page_id, occurrence_key, domain = key
        if domain == "page":
            # JS keeps undefined pageId as undefined (no refusal here);
            # a later lookup or validation refuses with its own code.
            allocated: object = page_id
        else:
            found = None
            for record in occurrences:
                if (
                    isinstance(record, dict)
                    and record.get("pageId") == page_id
                    and record.get("occurrenceKey") == occurrence_key
                ):
                    found = record
                    break
            if not isinstance(found, dict):
                return None, "export-id-ambiguous"
            semantic_id = found.get("semanticId")
            if not isinstance(semantic_id, str):
                return None, "export-id-ambiguous"
            allocated = semantic_id
        if allocated in used and used[allocated] != text:
            return None, "export-id-ambiguous"
        used[allocated] = text  # type: ignore[index]
        ids[text] = allocated  # type: ignore[assignment]
    return ids, None


def _map_allocated(
    run: _ExportRun,
) -> tuple[dict[str, str] | None, str | None]:
    """Allocate one run's call-local ids (lot4-export.ts:309-317, §2.5).

    The map planners are transcribed separately from the ``exportIdPlan``
    seam; an unknown ``idPolicy`` falls through to native (JS else branch).
    """
    keys = _collect_keys(run)
    policy = run.export.get("idPolicy")
    pages = [p for p in run.render.get("pages", []) if isinstance(p, dict)]
    if policy == "counter":
        return _plan_counter_ids(keys, pages, run.export.get("counterOrigin"))
    if policy == "digest":
        return _plan_digest_ids(keys)
    occurrences = [o for o in run.render.get("occurrences", []) if isinstance(o, dict)]
    return _plan_native_ids(keys, occurrences)  # type: ignore[arg-type]
