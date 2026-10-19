"""Headless transaction pipeline and report composition (lot 5).

Runs section 4.8 over a detached stage: per-command validation and lot-3
planning, one ``complete`` pass, the pre-normalize draft lint, one
``normalize`` pass and the post-normalize draft lint. Reports compose per
section 4.9 with lint entries mapped to the bare-rule coordinates. Lot-3
entry points resolve late so this module imports without lot 3; when they
are absent the batch refuses ``operation-error`` and the integration run
supplies them.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from bpmn_io._js import UNDEFINED
from bpmn_io.bpmn_moddle.simple import create_moddle
from bpmn_io.moddle.base import ModdleElement
from bpmn_io.profile._c14n import jcs
from bpmn_io.profile._commands import (
    CommandError,
    PreparedCommand,
    build_stage_index,
    prepare_command,
    replacement_rows,
)
from bpmn_io.profile._envelope import complete_envelope
from bpmn_io.profile._lint import lint as lint_bridge
from bpmn_io.profile._results import sort_id_map

if TYPE_CHECKING:
    from collections.abc import Callable

    from bpmn_io.moddle.moddle import Moddle
    from bpmn_io.profile._compiler import CompiledProfile

__all__ = [
    "ApplyError",
    "StagedResult",
    "lot5_entry_order_key",
    "run_apply",
    "sort_lot5_entries",
]

_LOT3_NAMES = (
    "Authority",
    "apply_plan",
    "complete",
    "create_read_context",
    "normalize",
    "plan_recipe",
)

_TRANSPORT_RULE_ID = "profile-mechanism/profile"

_STAGE_RANK = {
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
}


class ApplyError(Exception):
    """One refused batch carrying its closed code and partial report parts."""

    def __init__(
        self,
        code: str,
        entries: list[dict[str, object]] | None = None,
        raw: list[object] | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.entries = list(entries or [])
        self.raw = list(raw or [])


@dataclass
class StagedResult:
    """One staged batch: normalized tree/bindings and composed report parts."""

    tree: dict[str, object]
    bindings: list[dict[str, object]]
    revision: str
    entries: list[dict[str, object]]
    raw: list[object]
    id_map: list[dict[str, object]]
    changed: bool


def _lot3() -> dict[str, Any]:
    """Resolve the lot-3 entry points (raises ApplyError when absent)."""
    import bpmn_io.profile as package  # noqa: PLC0415 - late binding, lot 3 merges later

    funcs = {name: getattr(package, name, None) for name in _LOT3_NAMES}
    if any(func is None for func in funcs.values()):
        raise ApplyError("operation-error")  # noqa: EM101
    return funcs


def _u16(value: object) -> bytes:
    """Encode one value in UTF-16 code units (the deterministic sort order)."""
    return str(value).encode("utf-16-be")


def _nullable(value: object) -> tuple[int, bytes]:
    """Encode one nullable coordinate with null before present."""
    return (0, b"") if value is None else (1, _u16(value))


def _optional(entry: dict[str, object], key: str) -> tuple[int, bytes]:
    """Encode one optional entry member with absent before present."""
    if key not in entry:
        return (0, b"")
    value = entry[key]
    return (1, _u16(value if isinstance(value, str) else jcs(value)))


def _present(entry: dict[str, object], flag: str, key: str) -> tuple[int, bytes]:
    """Encode one presence-gated before/after value."""
    return (1, _u16(jcs(entry[key]))) if entry.get(flag) else (0, b"")


def lot5_entry_order_key(entry: dict[str, object]) -> tuple[object, ...]:
    """Return the section-4.9 profile-report/2 sort key of one wire entry."""
    source = entry.get("source")
    result = entry.get("result")
    source_map = source if isinstance(source, dict) else {}
    result_map = result if isinstance(result, dict) else {}
    stage = entry.get("stage")
    rank = _STAGE_RANK.get(stage if isinstance(stage, str) else "", len(_STAGE_RANK))
    return (
        rank,
        _u16(entry.get("ruleId")),
        _u16(source_map.get("domain")),
        _nullable(source_map.get("pointer")),
        _nullable(source_map.get("targetId")),
        _u16(entry.get("code")),
        _optional(entry, "pageId"),
        _optional(entry, "occurrenceKey"),
        _present(entry, "beforePresent", "before"),
        _present(entry, "afterPresent", "after"),
        _u16(result_map.get("domain")),
        _nullable(result_map.get("pointer")),
        _nullable(result_map.get("targetId")),
        _optional(entry, "property"),
    )


def sort_lot5_entries(
    entries: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Sort wire entries per section 4.9, coalescing exact duplicates."""
    ranked = sorted(entries, key=lot5_entry_order_key)
    coalesced: list[dict[str, object]] = []
    previous_wire: str | None = None
    previous_key: tuple[object, ...] | None = None
    for entry in ranked:
        key = lot5_entry_order_key(entry)
        wire = jcs(entry)
        if previous_key is not None and key == previous_key and wire == previous_wire:
            continue
        previous_key = key
        previous_wire = wire
        coalesced.append(entry)
    return coalesced


def _map_lint_entry(entry: object) -> dict[str, object]:
    """Map one lint bridge entry to the section-4.9 coordinates."""
    record = copy.deepcopy(entry) if isinstance(entry, dict) else {}
    rule_id = record.get("ruleId")
    if isinstance(rule_id, str) and rule_id.startswith("profile:"):
        record["ruleId"] = rule_id[len("profile:") :]
    record["result"] = {
        "domain": "none",
        "pointer": None,
        "targetId": None,
        "provenance": "unavailable",
    }
    return record


def _raw_standard_findings(raw: object) -> list[object]:
    """Project raw upstream findings, excluding the transport rule."""
    if isinstance(raw, dict):
        projected: list[object] = []
        for name, findings in sorted(raw.items(), key=lambda pair: _u16(pair[0])):
            if name == _TRANSPORT_RULE_ID or str(name).startswith("profile:"):
                continue
            projected.append({"rule": name, "findings": findings})
        return projected
    return []


def _moddle_of_tree(tree: dict[str, object]) -> ModdleElement:
    """Build one typed moddle Definitions root from a stage tree."""
    model = create_moddle()
    return _build_element(model, tree, {})


def _set_child(  # noqa: PLR0913, PLR0917 - conversion inputs are fixed
    model: Moddle,
    element: ModdleElement,
    key: str,
    value: object,
    index: dict[str, ModdleElement],
    pending: list[tuple[str, object]],
) -> None:
    """Set one converted property: containment now, references later."""
    try:
        properties = {prop.name: prop for prop in element.descriptor_.properties}
    except AttributeError:
        properties = {}
    prop = properties.get(key)
    if prop is not None and not prop.is_attr and not prop.is_reference:
        if isinstance(value, dict) and isinstance(value.get("$type"), str):
            child = _build_element(model, value, index)
            element.set(key, child)
        elif isinstance(value, list):
            element.set(
                key,
                [
                    _build_element(model, entry, index)
                    if isinstance(entry, dict) and isinstance(entry.get("$type"), str)
                    else entry
                    for entry in value
                ],
            )
        else:
            element.set(key, value)
    elif prop is not None and prop.is_reference:
        pending.append((key, value))
    else:
        element.set(key, value)


def _build_element(
    model: Moddle, node: dict[str, object], index: dict[str, ModdleElement]
) -> ModdleElement:
    """Recursively build one moddle element, linking references by ID."""
    type_name = node.get("$type")
    if not isinstance(type_name, str):
        message = f"lint conversion failed for {type_name!r}"
        raise TypeError(message)
    try:
        element = model.create(type_name)
    except Exception as exc:
        message = f"lint conversion failed for {type_name!r}"
        raise ValueError(message) from exc
    node_id = node.get("id")
    if isinstance(node_id, str):
        index[node_id] = element
    pending: list[tuple[str, object]] = []
    for key, value in node.items():
        if key == "$type":
            continue
        _set_child(model, element, key, value, index, pending)
    for key, value in pending:
        if isinstance(value, str):
            element.set(key, index.get(value, value))
        elif isinstance(value, list):
            element.set(
                key,
                [index.get(entry, entry) if isinstance(entry, str) else entry for entry in value],
            )
        else:
            element.set(key, value)
    return element


def _safe_element_get(element: ModdleElement, name: str) -> object:
    """Read one moddle property, mapping failures to UNDEFINED."""
    try:
        return element.get(name)
    except Exception:  # noqa: BLE001 - conversion stays total
        return UNDEFINED


def _fix_parents(element: ModdleElement) -> None:
    """Repair containment parent links top-down (references keep none)."""
    try:
        properties = {prop.name: prop for prop in element.descriptor_.properties}
    except AttributeError:
        return
    for name, prop in properties.items():
        if prop.is_attr or prop.is_reference:
            continue
        value = _safe_element_get(element, name)
        if value is UNDEFINED or value is None:
            continue
        if isinstance(value, list):
            for child in value:
                if isinstance(child, ModdleElement):
                    child.parent_ = element
                    _fix_parents(child)
        elif isinstance(value, ModdleElement):
            value.parent_ = element
            _fix_parents(value)


def _lint_stage(
    compiled: CompiledProfile,
    tree: dict[str, object],
    bindings: list[dict[str, object]],
    phase: str,
) -> tuple[list[dict[str, object]], list[object]]:
    """Run one draft lint stage; returns mapped entries and raw findings."""
    try:
        root = _moddle_of_tree(tree)
        _fix_parents(root)
        outcome = lint_bridge(
            root,
            compiled,
            phase=phase,
            readiness_policy="draft",
            bindings=copy.deepcopy(bindings),
        )
    except ApplyError:
        raise
    except Exception as exc:
        raise ApplyError("operation-error") from exc  # noqa: EM101
    if not isinstance(outcome, dict) or outcome.get("status") != "ok":
        raise ApplyError("operation-error")  # noqa: EM101
    report = outcome.get("report")
    raw_entries = report.get("entries") if isinstance(report, dict) else []
    entries = [
        _map_lint_entry(entry) for entry in (raw_entries if isinstance(raw_entries, list) else [])
    ]
    raw = _raw_standard_findings(
        report.get("rawStandardFindings") if isinstance(report, dict) else None
    )
    return entries, raw


def _report_wire(report: object) -> dict[str, object]:
    """Return the wire mapping of one lot-3 result report."""
    if isinstance(report, dict):
        return report
    to_json = getattr(report, "to_json", None)
    if callable(to_json):
        converted = to_json()
        if isinstance(converted, dict):
            return converted
    return {}


def _change_field(change: object, key: str) -> object:
    """Read one ChangeReport field from a mapping or an attribute object."""
    if isinstance(change, dict):
        return change.get(key)
    return getattr(change, key, None)


def _change_ids(change: object, key: str) -> list[str]:
    """Read one ChangeReport ID list as UTF-8 strings."""
    value = _change_field(change, key)
    if not isinstance(value, list):
        return []
    return [str(name) for name in value if isinstance(name, str)]


def _wire_entries(report: dict[str, object]) -> list[dict[str, object]]:
    """Return deep copies of the wire entries of one report mapping."""
    raw_entries = report.get("entries", [])
    if not isinstance(raw_entries, list):
        return []
    return [dict(entry) for entry in raw_entries if isinstance(entry, dict)]


def _blocking_code(entries: list[dict[str, object]], *, post: bool) -> str | None:
    """Return the code of the first unresolved blocking error, if any."""
    for entry in sort_lot5_entries(entries):
        if entry.get("severity") != "error" or entry.get("disposition") != "observed":
            continue
        if not post and entry.get("classification") == "repairable":
            continue
        code = entry.get("code")
        if isinstance(code, str):
            return code
    return None


def _poll(signal: Callable[[], bool] | None, is_disposed: Callable[[], bool]) -> None:
    """Poll one cancellation signal (refusals raise ApplyError)."""
    if signal is not None and signal():
        if is_disposed():
            raise ApplyError("canvas-disposed")  # noqa: EM101
        raise ApplyError("operation-cancelled")  # noqa: EM101
    if is_disposed():
        raise ApplyError("canvas-disposed")  # noqa: EM101


def run_apply(  # noqa: PLR0913 - pipeline inputs are fixed
    *,
    compiled: CompiledProfile,
    identity: dict[str, object],
    tree: dict[str, object],
    bindings: list[dict[str, object]],
    base_revision: object,
    expected_view_revision: object,
    current_revision: str,
    current_view: str,
    commands: object,
    transaction_id: object,
    signal: Callable[[], bool] | None,
    descriptor_types: dict[str, dict[str, object]],
    is_disposed: Callable[[], bool],
) -> StagedResult | None:
    """Run section-4.8 steps 2-10 over a detached stage.

    Returns ``None`` for the empty-batch no-op; otherwise the staged
    normalized tree, bindings and composed report parts. Refusals raise
    :class:`ApplyError` with the report parts executed so far.
    """
    _ = transaction_id
    # Step 2: first signal poll with the guard held.
    _poll(signal, is_disposed)
    # Step 3: revision guards.
    if base_revision != current_revision or expected_view_revision != current_view:
        raise ApplyError("operation-error")  # noqa: EM101
    # Step 4: the empty batch runs no C, N or lint stage.
    if isinstance(commands, list) and not commands:
        return None
    if not isinstance(commands, list):  # pragma: no cover - bridge guards types
        raise ApplyError("operation-error")  # noqa: EM101
    # Step 5: validate and apply the commands in order on a detached stage.
    lot3 = _lot3()
    stage_tree = copy.deepcopy(tree)
    stage_bindings = copy.deepcopy(bindings)
    id_map: list[dict[str, object]] = []
    for command in commands:
        index = build_stage_index(stage_tree)
        try:
            prepared = prepare_command(compiled, stage_tree, index, command, descriptor_types)
        except CommandError as exc:
            raise ApplyError(exc.code) from exc
        except Exception as exc:
            raise ApplyError("operation-error") from exc  # noqa: EM101
        _plan_and_apply(lot3, compiled, identity, prepared, stage_tree, stage_bindings, id_map)
        # Poll P2 after each command.
        _poll(signal, is_disposed)
    # Step 6: complete once over the staged batch.
    staged_envelope = complete_envelope(identity, stage_tree, stage_bindings)
    completed = lot3["complete"](compiled, staged_envelope, "retained", activation="edit")
    if getattr(completed, "status", None) != "ok":
        raise ApplyError(str(getattr(completed, "code", "operation-error")))
    c_payload = getattr(completed, "payload", {})
    c_envelope = c_payload.get("envelope") if isinstance(c_payload, dict) else None
    c_entries = _wire_entries(_report_wire(getattr(completed, "report", None)))
    if not isinstance(c_envelope, dict):
        raise ApplyError("operation-error")  # noqa: EM101
    return _run_normalize(lot3, compiled, c_envelope, c_entries, signal, is_disposed, id_map)


def _run_normalize(  # noqa: PLR0913, PLR0917 - normalize inputs are fixed
    lot3: dict[str, Any],
    compiled: CompiledProfile,
    c_envelope: dict[str, object],
    c_entries: list[dict[str, object]],
    signal: Callable[[], bool] | None,
    is_disposed: Callable[[], bool],
    id_map: list[dict[str, object]],
) -> StagedResult:
    """Run section-4.8 steps 7-10: draft lints around one normalize pass."""
    c_tree = c_envelope.get("tree")
    c_bindings = c_envelope.get("bindings")
    if not isinstance(c_tree, dict) or not isinstance(c_bindings, list):
        raise ApplyError("operation-error")  # noqa: EM101
    # Step 7: pre-normalize draft lint; non-repairable errors block.
    pre_entries, pre_raw = _lint_stage(compiled, c_tree, c_bindings, "pre-normalize")
    code = _blocking_code(pre_entries, post=False)
    if code is not None:
        raise ApplyError(code, pre_entries, pre_raw)
    # Step 8: normalize once.
    normalized = lot3["normalize"](compiled, c_envelope, None, activation="edit")
    if getattr(normalized, "status", None) != "ok":
        raise ApplyError(str(getattr(normalized, "code", "operation-error")), pre_entries, pre_raw)
    n_payload = getattr(normalized, "payload", {})
    n_envelope = n_payload.get("envelope") if isinstance(n_payload, dict) else None
    n_report = _report_wire(n_payload.get("report")) if isinstance(n_payload, dict) else {}
    if not isinstance(n_envelope, dict):
        raise ApplyError("operation-error", pre_entries, pre_raw)  # noqa: EM101
    n_entries = _wire_entries(n_report)
    # Step 9: post-normalize draft lint; any unresolved error blocks.
    n_tree = n_envelope.get("tree")
    n_bindings = n_envelope.get("bindings")
    if not isinstance(n_tree, dict) or not isinstance(n_bindings, list):
        raise ApplyError("operation-error", pre_entries, pre_raw)  # noqa: EM101
    post_entries, post_raw = _lint_stage(compiled, n_tree, n_bindings, "post-normalize")
    combined = pre_entries + post_entries
    code = _blocking_code(post_entries, post=True)
    if code is not None:
        raise ApplyError(code, combined, pre_raw + post_raw)
    # Step 10: final signal poll.
    _poll(signal, is_disposed)
    entries = sort_lot5_entries(c_entries + pre_entries + n_entries + post_entries)
    final_revision = n_envelope.get("semanticRevision")
    if not isinstance(final_revision, str):
        raise ApplyError("operation-error", combined, pre_raw + post_raw)  # noqa: EM101
    return StagedResult(
        tree=n_tree,
        bindings=n_bindings,
        revision=final_revision,
        entries=entries,
        raw=pre_raw + post_raw,
        id_map=sort_id_map(id_map),
        changed=True,
    )


def _plan_and_apply(  # noqa: PLR0913, PLR0917 - staging inputs are fixed
    lot3: dict[str, Any],
    compiled: CompiledProfile,
    identity: dict[str, object],
    prepared: PreparedCommand,
    stage_tree: dict[str, object],
    stage_bindings: list[dict[str, object]],
    id_map: list[dict[str, object]],
) -> None:
    """Plan and apply one prepared command on the stage (check (i))."""
    authority_cls = lot3["Authority"]
    try:
        authority = authority_cls(
            actor="editor", activation="edit", deletion_intent=prepared.deletion_intent
        )
    except Exception as exc:
        raise ApplyError("operation-error") from exc  # noqa: EM101
    recipes = getattr(compiled, "recipes", {})
    recipe = recipes.get(prepared.recipe_id) if isinstance(recipes, dict) else None
    if not isinstance(recipe, dict):
        raise ApplyError("profile-symbol")  # noqa: EM101
    staged_envelope = complete_envelope(identity, stage_tree, stage_bindings)
    try:
        read_context = lot3["create_read_context"](compiled, staged_envelope, stage="load")
    except Exception as exc:
        raise ApplyError("operation-error") from exc  # noqa: EM101
    if getattr(read_context, "status", None) != "ok":
        raise ApplyError(str(getattr(read_context, "code", "operation-error")))
    plan = lot3["plan_recipe"](
        recipe, getattr(read_context, "payload", None), prepared.params, authority
    )
    if getattr(plan, "status", None) != "ok":
        raise ApplyError(str(getattr(plan, "code", "operation-error")))
    report = lot3["apply_plan"](getattr(plan, "payload", None), stage_tree, staged_envelope)
    if getattr(report, "status", None) != "ok":
        raise ApplyError(str(getattr(report, "code", "operation-error")))
    change = getattr(report, "payload", {})
    new_tree = _change_field(change, "tree")
    new_bindings = _change_field(change, "bindings")
    if isinstance(new_tree, dict):
        stage_tree.clear()
        stage_tree.update(copy.deepcopy(new_tree))
    if isinstance(new_bindings, list):
        stage_bindings.clear()
        stage_bindings.extend(copy.deepcopy(new_bindings))
    created = _change_ids(change, "created")
    removed = _change_ids(change, "removed")
    phase = recipe.get("phase") if isinstance(recipe, dict) else None
    id_map.extend(replacement_rows(phase if isinstance(phase, str) else "", removed, created))
