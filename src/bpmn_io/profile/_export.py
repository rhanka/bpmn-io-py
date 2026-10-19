"""map_export with export-ir/1 planning, IDs and losses (DESIGN R3.3 §10.2).

Planning runs the export recipes of the selected ``exports[]`` record in
order over their selector results, records every ``outputId`` request,
allocates call-local ids (``counter``/``digest``/``native``) and emits
the IR with capability, loss-action and adapter losses. Refusal returns
the complete report and no artifact; symbol tables never survive a call.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from bpmn_io.profile._c14n import digest
from bpmn_io.profile._evaluate import (
    _is_occurrence_handle,
    evaluate_predicate,
    evaluate_value,
    is_missing,
    make_read_context,
    select,
)
from bpmn_io.profile._export_ir import _REQUIRED_FIELDS, plan_ids
from bpmn_io.profile._layout import _begin_operation, index_tree
from bpmn_io.profile._render import _escape_segment, native_preorder
from bpmn_io.profile._render_digest import check_render_freshness, view_revision
from bpmn_io.profile._results import (
    CAPABILITY_ORDER,
    PureRefused,
    ReportEntry,
    ResultRefused,
    ResultSuccess,
    make_coordinate,
    refused_result,
    report_with_header,
    sort_id_map,
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

#: R occurrence members copied into export-ir/1 records (harmonization B21).
_R_COPY_KEYS: dict[str, tuple[str, ...]] = {
    "page": ("bounds",),
    "node": ("bounds", "style", "label"),
    "edge": ("bounds", "waypoints", "style", "label"),
    "label": ("label",),
}


@dataclass
class _PlanEmit:
    """One planned emit with evaluated fields and self coordinates."""

    recipe_id: str
    kind: str
    fields: list[tuple[str, object]]
    parent: object
    has_parent: bool
    page_id: str | None
    occurrence_key: str | None
    emitted_type: str | None
    semantic_id: str | None
    source: dict[str, Json]


@dataclass
class _PlanLoss:
    """One planned loss action with resolved target coordinates."""

    recipe_id: str
    code: str
    page_id: str | None
    occurrence_key: str | None
    emitted_type: str | None
    source: dict[str, Json]


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
    requests: list[dict[str, object]] = field(default_factory=list)
    actions: list[tuple[str, object, int]] = field(default_factory=list)
    entries: list[ReportEntry] = field(default_factory=list)
    code: str | None = None
    iteration: int = 0


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
    loss: _PlanLoss,
    result: dict[str, Json],
) -> ReportEntry:
    """Build one export loss entry (spec §10.3)."""
    source = loss.source
    return ReportEntry(
        code=f"export-loss/{loss.code}",
        severity="warn",
        classification="loss",
        stage="export",
        rule_id=rule_id,
        message_key=f"export.loss.{loss.code}",
        disposition="mapped",
        source=make_coordinate(
            str(source.get("domain", "none")),
            source.get("pointer") if isinstance(source.get("pointer"), str) else None,
            source.get("targetId") if isinstance(source.get("targetId"), str) else None,
            str(source.get("provenance", "unavailable")),
        ),
        result=make_coordinate(
            str(result.get("domain", "none")),
            result.get("pointer") if isinstance(result.get("pointer"), str) else None,
            result.get("targetId") if isinstance(result.get("targetId"), str) else None,
            str(result.get("provenance", "unavailable")),
        ),
        before_present=False,
        after_present=False,
        page_id=loss.page_id,
        occurrence_key=loss.occurrence_key,
        emitted_type=loss.emitted_type,
        loss_class=loss.code,
    )


_UNAVAILABLE: dict[str, Json] = {
    "domain": "none",
    "pointer": None,
    "targetId": None,
    "provenance": "unavailable",
}


def _iteration_bindings(run: _ExportRun, handle: object) -> dict[str, object]:
    """Build the evaluation bindings of one recipe iteration."""
    bindings: dict[str, object] = {"root": run.tree, "render": run.render, "self": handle}
    if isinstance(handle, dict) and "occurrenceKey" in handle:
        page = run.pages.get(str(handle.get("pageId")))
        if page is not None:
            bindings["page"] = page
        semantic_id = handle.get("semanticId")
        if isinstance(semantic_id, str) and semantic_id in run.by_id:
            bindings["semantic"] = run.by_id[semantic_id]
    elif isinstance(handle, dict) and isinstance(handle.get("pageId"), str):
        bindings["page"] = handle
    return bindings


def _eval_step_value(
    run: _ExportRun, ast: object, bindings: dict[str, object]
) -> tuple[object, str | None]:
    """Evaluate one field value (value, refusal code)."""
    result = evaluate_value(ast, run.context, bindings)
    if isinstance(result, PureRefused):
        return None, "render-stale"
    return result.payload, None


#: Marker for an outputId over an absent binding (the value is MISSING).
_OUTPUT_MISSING: object = object()


def _request_for_output_id(
    run: _ExportRun, node: dict[str, Json], bindings: dict[str, object]
) -> tuple[object, str | None]:
    """Build one outputId request (request, refusal code)."""
    binding = node.get("binding")
    domain = node.get("domain")
    if not isinstance(binding, str) or not isinstance(domain, str):
        return None, "render-stale"
    if binding not in bindings:
        return _OUTPUT_MISSING, None
    handle = bindings[binding]
    if isinstance(handle, _PlanEmit):
        return {
            "pageId": handle.page_id or "",
            "occurrenceKey": handle.occurrence_key or "",
            "domain": domain,
            "semanticId": handle.semantic_id,
        }, None
    if _is_occurrence_handle(handle) or (
        isinstance(handle, dict) and isinstance(handle.get("pageId"), str)
    ):
        semantic = handle.get("semanticId")
        return {
            "pageId": str(handle.get("pageId")),
            "occurrenceKey": str(handle.get("occurrenceKey", "")),
            "domain": domain,
            "semanticId": semantic if isinstance(semantic, str) else None,
        }, None
    if isinstance(handle, dict):
        return _native_request(run, handle, domain, bindings)
    return None, "render-stale"


def _native_request(
    run: _ExportRun, handle: dict[str, Json], domain: str, bindings: dict[str, object]
) -> tuple[object, str | None]:
    """Build one outputId request over a native handle (request, code)."""
    element_id = handle.get("id")
    current = bindings.get("self")
    page_id = current.get("pageId") if isinstance(current, dict) else None
    if not isinstance(element_id, str) or not isinstance(page_id, str):
        return None, "export-occurrence-ambiguous"
    matches = [
        record
        for record in run.render.get("occurrences", [])
        if isinstance(record, dict)
        and record.get("semanticId") == element_id
        and record.get("pageId") == page_id
    ]
    if len(matches) != 1:
        return None, "export-occurrence-ambiguous"
    match = matches[0]
    return {
        "pageId": str(match.get("pageId")),
        "occurrenceKey": str(match.get("occurrenceKey")),
        "domain": domain,
        "semanticId": element_id,
    }, None


def _plan_field_value(
    run: _ExportRun, ast: object, bindings: dict[str, object]
) -> tuple[object, str | None]:
    """Evaluate one emit field value, recording outputId requests."""
    if isinstance(ast, dict) and ast.get("op") == "outputId":
        request, code = _request_for_output_id(run, ast, bindings)
        if code is not None:
            return None, code
        if request is _OUTPUT_MISSING:
            return request, None
        if not isinstance(request, dict):
            return None, "render-stale"
        run.requests.append(request)
        return ("output-id", len(run.requests) - 1), None
    return _eval_step_value(run, ast, bindings)


def _plan_emit_step(
    run: _ExportRun,
    recipe_id: str,
    step: dict[str, Json],
    bindings: dict[str, object],
    handle: object,
) -> str | None:
    """Plan one emit step (refusal code or None)."""
    kind = step.get("kind")
    alias = step.get("as")
    fields = step.get("fields")
    if kind not in _IR_KINDS or not isinstance(alias, str) or not isinstance(fields, list):
        return "render-stale"
    evaluated: list[tuple[str, object]] = []
    for entry in fields:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            return "render-stale"
        value, code = _plan_field_value(run, entry.get("value"), bindings)
        if code is not None:
            return code
        evaluated.append((str(entry.get("name")), value))
    parent: object = None
    has_parent = False
    if step.get("parent") is not None:
        has_parent = True
        parent, code = _plan_field_value(run, step.get("parent"), bindings)
        if code is not None:
            return code
    page_id, occurrence_key, emitted_type, source = _self_coordinates(run, handle)
    if kind in ("node", "edge", "label") and step.get("parent") is None and page_id is None:
        return "render-stale"
    semantic_id = handle.get("semanticId") if isinstance(handle, dict) else None
    record = _PlanEmit(
        recipe_id=recipe_id,
        kind=str(kind),
        fields=evaluated,
        parent=parent,
        has_parent=has_parent,
        page_id=page_id,
        occurrence_key=occurrence_key,
        emitted_type=emitted_type,
        semantic_id=semantic_id if isinstance(semantic_id, str) else None,
        source=source,
    )
    run.actions.append(("emit", record, run.iteration))
    bindings[alias] = record
    return None


def _plan_loss_step(
    run: _ExportRun,
    recipe_id: str,
    step: dict[str, Json],
    bindings: dict[str, object],
    handle: object,
) -> str | None:
    """Plan one loss action (refusal code or None)."""
    code = step.get("code")
    if not isinstance(code, str) or not code:
        return "render-stale"
    target = step.get("target", "self")
    if target is None:
        target = "self"
    if not isinstance(target, str) or target not in bindings:
        return "render-stale"
    resolved = bindings[target]
    page_id, occurrence_key, emitted_type, source = _target_source(run, resolved, handle)
    planned = _PlanLoss(recipe_id, code, page_id, occurrence_key, emitted_type, source)
    run.actions.append(("loss", planned, run.iteration))
    return None


def _plan_iteration(run: _ExportRun, recipe: dict[str, Json], handle: object) -> str | None:
    """Plan one recipe iteration over its steps (refusal code or None)."""
    run.iteration += 1
    bindings = _iteration_bindings(run, handle)
    when = recipe.get("when", {"op": "true"})
    decided = evaluate_predicate(when, run.context, bindings)
    if isinstance(decided, PureRefused):
        return "render-stale"
    if decided.payload is not True:
        return None
    recipe_id = str(recipe.get("id"))
    for step in recipe.get("steps", []):
        code = _plan_step(run, recipe_id, step, bindings, handle)
        if code is not None:
            return code
    return None


def _plan_step(
    run: _ExportRun,
    recipe_id: str,
    step: object,
    bindings: dict[str, object],
    handle: object,
) -> str | None:
    """Plan one recipe step (refusal code or None)."""
    if not isinstance(step, dict):
        return "render-stale"
    op = step.get("op")
    if op == "bind":
        return _resolve_bind(run, step, bindings)
    if op == "emit":
        return _plan_emit_step(run, recipe_id, step, bindings, handle)
    if op == "loss":
        return _plan_loss_step(run, recipe_id, step, bindings, handle)
    if op == "refuse":
        refused = step.get("code")
        return refused if isinstance(refused, str) and refused else "render-stale"
    return "render-stale"


def _plan_recipe(run: _ExportRun, recipe: dict[str, Json]) -> str | None:
    """Plan one export recipe over its selector results."""
    result = select(recipe.get("select"), run.context, {"root": run.tree, "render": run.render})
    if isinstance(result, PureRefused):
        return "render-stale"
    if not isinstance(result.payload, list):
        return "render-stale"
    for item in result.payload:
        code = _plan_iteration(run, recipe, item.element)
        if code is not None:
            return code
    return None


def _resolve_bind(
    run: _ExportRun, step: dict[str, Json], bindings: dict[str, object]
) -> str | None:
    """Run one bind step, storing its alias (refusal code or None)."""
    alias = step.get("as")
    cardinality = step.get("cardinality")
    if not isinstance(alias, str) or cardinality not in ("one", "zeroOrOne", "first"):
        return "render-stale"
    handles, code = _select_bound(run, step, bindings)
    if code is not None or handles is None:
        return code or "render-stale"
    if cardinality == "first":
        handles = handles[:1]
    if len(handles) != 1:
        if cardinality == "zeroOrOne" and not handles:
            bindings.pop(alias, None)
            return None
        return "profile-ambiguous-binding"
    bindings[alias] = handles[0].element
    return None


def _select_bound(
    run: _ExportRun, step: dict[str, Json], bindings: dict[str, object]
) -> tuple[list[Any] | None, str | None]:
    """Select one bind's handles with fallbacks (handles, code)."""
    result = select(step.get("select"), run.context, dict(bindings))
    if isinstance(result, PureRefused) or not isinstance(result.payload, list):
        return None, "render-stale"
    handles = list(result.payload)
    if handles or step.get("cardinality") != "first":
        return handles, None
    fallbacks = step.get("fallbacks")
    if not isinstance(fallbacks, list):
        return handles, None
    for entry in fallbacks:
        fallback = select(entry, run.context, dict(bindings))
        if isinstance(fallback, PureRefused) or not isinstance(fallback.payload, list):
            return None, "render-stale"
        handles = list(fallback.payload)
        if handles:
            break
    return handles, None


def _check_capability(run: _ExportRun) -> tuple[str, str | None]:
    """Evaluate capability records once per occurrence (class, code)."""
    classes: list[str] = []
    occurrences = [
        record for record in run.render.get("occurrences", []) if isinstance(record, dict)
    ]
    for occurrence in occurrences:
        _check_occurrence_capability(run, occurrence, classes)
    if any(outcome not in CAPABILITY_ORDER for outcome in classes):
        return "structural", "render-stale"
    capability = worst_capability([*classes, "structural"])
    if capability == "unsupported":
        return capability, "render-unsupported"
    return capability, None


def _check_occurrence_capability(
    run: _ExportRun, occurrence: dict[str, Json], classes: list[str]
) -> None:
    """Evaluate capability records for one occurrence, collecting losses."""
    bindings = _iteration_bindings(run, occurrence)
    for record in run.export.get("capabilities", []):
        if not isinstance(record, dict):
            continue
        decided = evaluate_predicate(record.get("when"), run.context, bindings)
        if isinstance(decided, PureRefused):
            continue
        if decided.payload is not True:
            continue
        outcome = record.get("class")
        if not isinstance(outcome, str):
            continue
        classes.append(outcome)
        _append_capability_losses(run, occurrence, record)


def _append_capability_losses(
    run: _ExportRun, occurrence: dict[str, Json], record: dict[str, Json]
) -> None:
    """Append one applicable capability record's loss entries."""
    page_id, occurrence_key, emitted_type, source = _self_coordinates(run, occurrence)
    for loss_class in record.get("losses", []):
        if not isinstance(loss_class, str):
            continue
        planned = _PlanLoss(
            str(run.export.get("id")), loss_class, page_id, occurrence_key, emitted_type, source
        )
        run.entries.append(_loss_entry(str(run.export.get("id")), planned, dict(_UNAVAILABLE)))


def _substitute_ids(value: object, allocated: dict[int, str]) -> object:
    """Replace output-id placeholders with allocated ids (MISSING kept)."""
    if isinstance(value, tuple) and len(value) == 2 and value[0] == "output-id":
        return allocated[value[1]]
    return value


def _reference_check(
    table: dict[str, tuple[str, int]],
    planned: dict[str, str],
    own_id: str,
    value: object,
    allowed: frozenset[str],
) -> str | None:
    """Check one parent/endpoint reference (refusal code or None)."""
    if not isinstance(value, str) or not value:
        return "export-parent-invalid"
    if value == own_id:
        return "export-parent-invalid"
    known = table.get(value)
    if known is not None:
        return None if known[0] in allowed else "export-parent-invalid"
    planned_kind = planned.get(value)
    if planned_kind is None:
        return "export-parent-invalid"
    if planned_kind not in allowed:
        return "export-parent-invalid"
    return "export-parent-order"


@dataclass
class _Emission:
    """Mutable per-call emission state (symbol table and outputs)."""

    allocated: dict[int, str] = field(default_factory=dict)
    planned: dict[str, str] = field(default_factory=dict)
    table: dict[str, tuple[str, int]] = field(default_factory=dict)
    emitted_pages: dict[str, str] = field(default_factory=dict)
    ir: list[dict[str, Json]] = field(default_factory=list)
    id_map: list[dict[str, Json]] = field(default_factory=list)


def _emit_fields(
    emit: _PlanEmit, allocated: dict[int, str]
) -> tuple[dict[str, Json] | None, str | None]:
    """Substitute ids into one emit's fields (fields, refusal code)."""
    fields: dict[str, Json] = {}
    for name, value in emit.fields:
        if value is _OUTPUT_MISSING:
            continue
        resolved = _substitute_ids(value, allocated)
        if is_missing(resolved) or resolved is None:
            if name in _REQUIRED_FIELDS[emit.kind]:
                return None, "export-field-invalid"
            continue
        fields[name] = resolved
    for name in _REQUIRED_FIELDS[emit.kind]:
        if name not in fields:
            return None, "export-field-invalid"
    return fields, None


def _parent_value(emit: _PlanEmit, out: _Emission) -> tuple[object, str | None]:
    """Evaluate one emit's raw parent value (value, refusal code)."""
    if emit.has_parent:
        if emit.parent is _OUTPUT_MISSING:
            value: object = _OUTPUT_MISSING
        else:
            value = _substitute_ids(emit.parent, out.allocated)
        if value is _OUTPUT_MISSING or is_missing(value) or value is None:
            if emit.kind == "metadata":
                return None, None
            return None, "export-field-invalid"
        if not isinstance(value, str):
            return None, "export-parent-invalid"
        return value, None
    if emit.kind in ("node", "edge", "label"):
        return ("implicit-page", emit.page_id or ""), None
    return None, None


def _emit_parent(emit: _PlanEmit, out: _Emission, record_id: object) -> tuple[object, str | None]:
    """Resolve one emit's parent with order checks (parent, code)."""
    parent, code = _parent_value(emit, out)
    if code is not None:
        return None, code
    if isinstance(parent, tuple) and parent[0] == "implicit-page":
        page_id = out.emitted_pages.get(parent[1])
        if page_id is None:
            return None, "export-parent-order"
        parent = page_id
    if isinstance(parent, str):
        own = record_id if isinstance(record_id, str) else ""
        code = _reference_check(out.table, out.planned, own, parent, _PARENT_KINDS)
        if code is not None:
            return None, code
    return parent, None


def _check_endpoints(
    emit: _PlanEmit, out: _Emission, fields: dict[str, Json], record_id: str
) -> str | None:
    """Check one edge's source/target endpoints (refusal code or None)."""
    if emit.kind != "edge":
        return None
    for endpoint in ("source", "target"):
        code = _reference_check(
            out.table, out.planned, record_id, fields.get(endpoint), frozenset({"node"})
        )
        if code is not None:
            return code
    return None


def _emit_record(run: _ExportRun, emit: _PlanEmit, out: _Emission) -> str | None:
    """Emit one planned record with R copies (refusal code or None)."""
    fields, code = _emit_fields(emit, out.allocated)
    if code is not None or fields is None:
        return code or "export-field-invalid"
    record_id = fields.get("id")
    if emit.kind != "metadata" and (not isinstance(record_id, str) or not record_id):
        return "export-field-invalid"
    if isinstance(record_id, str) and record_id in out.table:
        return "export-parent-invalid"
    parent, code = _emit_parent(emit, out, record_id)
    if code is not None:
        return code
    if isinstance(record_id, str):
        code = _check_endpoints(emit, out, fields, record_id)
        if code is not None:
            return code
    record: dict[str, Json] = {"kind": emit.kind}
    record.update(fields)
    if parent is not None:
        record["parent"] = parent
    record.update(_render_copies(run, emit))
    if isinstance(record_id, str):
        out.table[record_id] = (emit.kind, len(out.ir))
    if emit.kind == "page" and isinstance(record_id, str) and emit.page_id is not None:
        out.emitted_pages[emit.page_id] = record_id
    index = len(out.ir)
    out.ir.append(record)
    _append_id_map(out, emit, record_id)
    _append_adapter_loss(run, emit, index)
    return None


def _append_id_map(out: _Emission, emit: _PlanEmit, record_id: object) -> None:
    """Append one emit's idMap row when it carries a source identity."""
    if emit.kind == "page" and isinstance(record_id, str):
        out.id_map.append(
            {
                "sourceId": emit.page_id,
                "resultId": record_id,
                "domain": "export",
                "pageId": emit.page_id,
            }
        )
    elif emit.semantic_id is not None and isinstance(record_id, str):
        out.id_map.append(
            {
                "sourceId": emit.semantic_id,
                "resultId": record_id,
                "domain": "export",
                "pageId": emit.page_id,
                "occurrenceKey": emit.occurrence_key,
            }
        )


def _append_adapter_loss(run: _ExportRun, emit: _PlanEmit, index: int) -> None:
    """Append one adapter loss for an undropped emitted record kind."""
    drops = run.adapter.get("drops")
    if not isinstance(drops, frozenset) or emit.kind not in drops:
        return
    planned = _PlanLoss(
        "adapter",
        emit.kind,
        emit.page_id,
        emit.occurrence_key,
        emit.emitted_type,
        emit.source,
    )
    run.entries.append(
        _loss_entry(
            "adapter",
            planned,
            {
                "domain": "artifact",
                "pointer": f"/ir/{index}",
                "targetId": None,
                "provenance": "exact",
            },
        )
    )


def _render_copies(run: _ExportRun, emit: _PlanEmit) -> dict[str, Json]:
    """Copy R geometry, style and label lines into one IR record."""
    copies: dict[str, Json] = {}
    if emit.kind == "page":
        page = run.pages.get(emit.page_id or "")
        if page is not None and isinstance(page.get("bounds"), dict):
            copies["bounds"] = copy.deepcopy(page.get("bounds"))
        return copies
    occurrence = None
    for record in run.render.get("occurrences", []):
        if (
            isinstance(record, dict)
            and record.get("pageId") == emit.page_id
            and record.get("occurrenceKey") == emit.occurrence_key
        ):
            occurrence = record
            break
    if occurrence is None:
        return copies
    for key in _R_COPY_KEYS.get(emit.kind, ()):
        if key == "label":
            _copy_label(occurrence, copies, flat=emit.kind == "label")
        elif occurrence.get(key) is not None:
            copies[key] = copy.deepcopy(occurrence.get(key))
    return copies


def _copy_label(occurrence: dict[str, Json], copies: dict[str, Json], *, flat: bool) -> None:
    """Copy one occurrence label into an IR record (flat for labels)."""
    label = occurrence.get("label")
    if not isinstance(label, dict):
        return
    if flat:
        if isinstance(label.get("bounds"), dict):
            copies["bounds"] = copy.deepcopy(label.get("bounds"))
        if isinstance(label.get("lines"), list):
            copies["lines"] = copy.deepcopy(label.get("lines"))
        return
    nested: dict[str, Json] = {}
    if isinstance(label.get("bounds"), dict):
        nested["bounds"] = copy.deepcopy(label.get("bounds"))
    if isinstance(label.get("lines"), list):
        nested["lines"] = copy.deepcopy(label.get("lines"))
    if nested:
        copies["label"] = nested


def _plan_static_metadata(run: _ExportRun) -> str | None:
    """Plan artifact-global metadata of the exports[] record (code or None)."""
    metadata = run.export.get("metadata", [])
    if not isinstance(metadata, list):
        return "render-stale"
    for entry in metadata:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("name"), str)
            or not isinstance(entry.get("value"), str)
        ):
            return "render-stale"
        run.actions.append(
            (
                "emit",
                _PlanEmit(
                    recipe_id=str(run.export.get("id")),
                    kind="metadata",
                    fields=[("name", entry["name"]), ("value", entry["value"])],
                    parent=None,
                    has_parent=False,
                    page_id=None,
                    occurrence_key=None,
                    emitted_type=None,
                    semantic_id=None,
                    source=dict(_UNAVAILABLE),
                ),
                run.iteration,
            )
        )
    return None


def _run_emission(
    run: _ExportRun, allocated: dict[int, str]
) -> tuple[list[dict[str, Json]], list[dict[str, Json]], str | None]:
    """Emit every planned action with symbol checks (ir, idMap, code)."""
    out = _Emission(allocated=allocated)
    for action, item, _ in run.actions:
        if action != "emit" or not isinstance(item, _PlanEmit):
            continue
        for name, value in item.fields:
            if name == "id" and isinstance(value, tuple) and value[0] == "output-id":
                out.planned[allocated[value[1]]] = item.kind
    last_emit: dict[int, int] = {}
    for action, item, iteration in run.actions:
        if action == "emit" and isinstance(item, _PlanEmit):
            before = len(out.ir)
            code = _emit_record(run, item, out)
            if code is not None:
                return [], [], code
            if len(out.ir) > before:
                last_emit[iteration] = len(out.ir) - 1
        elif action == "loss" and isinstance(item, _PlanLoss):
            _run_loss_action(run, out, item, last_emit.get(iteration))
        else:
            return [], [], "render-stale"
    return out.ir, out.id_map, None


def _run_loss_action(run: _ExportRun, out: _Emission, item: _PlanLoss, last: int | None) -> None:
    """Append one loss action with iteration-local result coordinates."""
    if last is None:
        result: dict[str, Json] = dict(_UNAVAILABLE)
    else:
        record_id = out.ir[last].get("id")
        result = {
            "domain": "artifact",
            "pointer": f"/ir/{last}",
            "targetId": record_id if isinstance(record_id, str) else None,
            "provenance": "exact",
        }
    run.entries.append(_loss_entry(item.recipe_id, item, result))


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
    run, capability, code = _map_planned(compiled, tree, candidate, export, format)
    if code is not None or run is None or capability is None:
        return refused_result("mapExport", code or "render-stale", echo_identity, echo_revision)
    return _map_finished(run, candidate, format, capability, (echo_identity, echo_revision))


def _map_finished(
    run: _ExportRun,
    candidate: dict[str, Json],
    format: object,  # noqa: A002 - format is the exports[] member name
    capability: str,
    echo: tuple[dict[str, object] | None, str | None],
) -> ResultSuccess | ResultRefused:
    """Allocate, emit and assemble one planned run (DESIGN §10.1 steps 7-9)."""
    echo_identity, echo_revision = echo
    request_ids, code = _map_allocated(run)
    if code is not None or request_ids is None:
        return refused_result(
            "mapExport", code or "export-id-ambiguous", echo_identity, echo_revision
        )
    ir, id_map, code = _run_emission(run, request_ids)
    if code is not None:
        return refused_result("mapExport", code, echo_identity, echo_revision)
    binding = copy.deepcopy(candidate.get("binding"))
    if not isinstance(binding, dict):
        return refused_result("mapExport", "render-stale", echo_identity, echo_revision)
    view = view_revision(binding)
    identity = copy.deepcopy(echo_identity) if echo_identity is not None else {}
    revision = echo_revision or ""
    sorted_map = sort_id_map(id_map)
    artifacts: list[dict[str, Json]] = [
        {
            "format": str(format),
            "capability": capability,
            "digest": digest(ir),
            "entryIndexes": list(range(len(run.entries))),
        }
    ]
    report = report_with_header(
        "mapExport", identity, revision, entries=run.entries, id_map=sorted_map, artifacts=artifacts
    )
    payload: dict[str, Json] = {
        "format": str(format),
        "profileIdentity": identity,
        "semanticRevision": revision,
        "viewRevision": view,
        "ir": ir,
        "renderBinding": binding,
        "report": report.to_json(),
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


def _map_planned(
    compiled: object,
    tree: dict[str, Json],
    candidate: dict[str, Json],
    export: dict[str, Json],
    format: object,  # noqa: A002 - format is the exports[] member name
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
    run.context = make_read_context(tree, notions=notions if isinstance(notions, dict) else {})
    capability, code = _check_capability(run)
    if code is not None:
        return None, None, code
    recipes = getattr(compiled, "recipes", {})
    for recipe_id in export.get("recipes", []):
        recipe = recipes.get(recipe_id) if isinstance(recipes, dict) else None
        if not isinstance(recipe, dict):
            return None, None, "render-stale"
        code = _plan_recipe(run, recipe)
        if code is not None:
            return None, None, code
    code = _plan_static_metadata(run)
    if code is not None:
        return None, None, code
    return run, capability, None


def _map_allocated(run: _ExportRun) -> tuple[dict[int, str] | None, str | None]:
    """Allocate one run's call-local ids (request ids, refusal code)."""
    policy = run.export.get("idPolicy")
    origin = run.export.get("counterOrigin")
    if policy not in ("counter", "digest", "native") or type(origin) is not int:
        return None, "render-stale"
    plan = plan_ids(
        {
            "policy": policy,
            "counterOrigin": origin,
            "pages": [
                {
                    "pageId": page_id,
                    "order": page.get("order") if type(page.get("order")) is int else 0,
                }
                for page_id, page in run.pages.items()
            ],
            "requests": run.requests,
        }
    )
    if isinstance(plan, PureRefused):
        return None, plan.code
    if not isinstance(plan.payload, dict):
        return None, "render-stale"
    request_ids = _map_request_ids(run.requests, plan.payload.get("ids"))
    if request_ids is None:
        return None, "export-id-ambiguous"
    return request_ids, None


def _map_request_ids(requests: list[dict[str, object]], ids: object) -> dict[int, str] | None:
    """Map every request index to its allocated id (None when missing)."""
    if not isinstance(ids, list):
        return None
    by_key: dict[tuple[str, str, str], str] = {}
    for row in ids:
        if not isinstance(row, dict):
            return None
        key = (
            str(row.get("pageId")),
            str(row.get("occurrenceKey")),
            str(row.get("domain")),
        )
        by_key.setdefault(key, str(row.get("id")))
    allocated: dict[int, str] = {}
    for index, request in enumerate(requests):
        lookup = (
            str(request.get("pageId")),
            str(request.get("occurrenceKey")),
            str(request.get("domain")),
        )
        if lookup not in by_key:
            return None
        allocated[index] = by_key[lookup]
    return allocated
