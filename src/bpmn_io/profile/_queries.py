"""Read-only headless queries: entries, fields, references, copy (lot 5).

Implements the section-8.3 query surface over a committed envelope: surface
listings with the shared ``ui.when`` authorization, field records with
display/value resolution, on-change validation, reference picking in
UTF-16 order, canonical copy fragments and message localization.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from bpmn_io.profile._commands import (
    CommandError,
    StageIndex,
    _field_editable,
    _string_list,
    build_stage_index,
    canonical_preorder,
    check_field_value,
    evaluate_when,
    recognized_notions,
    resolve_reference_candidates,
)
from bpmn_io.profile._evaluate import _eval_value, make_read_context
from bpmn_io.profile._results import PureResult, pure_refused, pure_success
from bpmn_io.profile._ui import SURFACES, UiIndex, localize_message

if TYPE_CHECKING:
    from bpmn_io.profile._compiler import CompiledProfile

__all__ = [
    "check_field",
    "copy_fragment",
    "list_entries",
    "list_fields",
    "localize",
    "query_references",
]

_MAX_SAFE_INTEGER = 9007199254740991


def _ui_index(compiled: CompiledProfile) -> UiIndex:
    """Return the compiled UI index (missing index refuses the call)."""
    index = getattr(compiled, "ui", None)
    if not isinstance(index, UiIndex):
        raise CommandError("operation-error")  # noqa: EM101
    return index


def _utf16(value: str) -> bytes:
    """Encode one string in UTF-16 code units (the deterministic sort order)."""
    return value.encode("utf-16-be")


def list_entries(
    compiled: CompiledProfile,
    tree: dict[str, object],
    surface: object,
    subject_id: object,
    locale: object,
) -> PureResult:
    """List the authorized entries of one surface for a subject element."""
    if not isinstance(surface, str) or surface not in SURFACES:
        return pure_refused("profile-type")
    if not isinstance(subject_id, str):
        return pure_refused("profile-type")
    if not isinstance(locale, str):
        return pure_refused("operation-error")
    index = build_stage_index(tree)
    subject = index.by_id.get(subject_id)
    if subject is None:
        return pure_refused("reference-dangling")
    try:
        ui = _ui_index(compiled)
    except CommandError as exc:
        return pure_refused(exc.code)
    groups: dict[str, list[dict[str, object]]] = {}
    for entry in ui.entries:
        if entry.get("surface") != surface:
            continue
        if not evaluate_when(compiled, tree, entry.get("when", {"op": "true"}), subject):
            continue
        label_key = entry.get("label")
        key = label_key if isinstance(label_key, str) else ""
        text, _ = localize_message(ui, key, locale)
        icon = entry.get("icon")
        upstream_entries = entry.get("upstreamEntries")
        record = {
            "id": entry.get("id"),
            "label": {"key": key, "text": text},
            "icon": {
                "theme": icon.get("theme") if isinstance(icon, dict) else None,
                "glyph": icon.get("glyph") if isinstance(icon, dict) else None,
            },
            "order": entry.get("order"),
            "upstreamEntries": list(upstream_entries) if isinstance(upstream_entries, list) else [],
        }
        group = entry.get("group")
        groups.setdefault(group if isinstance(group, str) else "", []).append(record)
    payload_groups = []
    for group, records in groups.items():
        records.sort(key=_entry_order)
        payload_groups.append({"group": group, "entries": records})
    return pure_success({"surface": surface, "groups": payload_groups})


def _entry_order(item: dict[str, object]) -> tuple[int, bytes]:
    """Order listing entries by numeric order, then UTF-16 ID."""
    order = item.get("order")
    return (order if isinstance(order, int) else 0, _utf16(str(item.get("id"))))


def _read_field_state(  # noqa: PLR0913, PLR0917 - field record inputs are fixed
    compiled: CompiledProfile,
    tree: dict[str, object],
    ui: UiIndex,
    target: dict[str, object],
    notion_id: str,
    field_entry: dict[str, object],
    locale: str,
) -> dict[str, object] | None:
    """Build one field record, or None when the field is hidden."""
    if not evaluate_when(compiled, tree, field_entry.get("visible", {"op": "true"}), target):
        return None
    mutable = evaluate_when(compiled, tree, field_entry.get("mutable", {"op": "true"}), target)
    path = field_entry.get("path")
    present = False
    stored: object = None
    if isinstance(path, str) and path.startswith("/"):
        node: object = target
        for raw in path[1:].split("/"):
            part = raw.replace("~1", "/").replace("~0", "~")
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                break
        else:
            present = True
            stored = node
    label_key = field_entry.get("label")
    message_key = field_entry.get("message")
    label_text, _ = localize_message(ui, label_key if isinstance(label_key, str) else "", locale)
    message_text, _ = localize_message(
        ui, message_key if isinstance(message_key, str) else "", locale
    )
    record: dict[str, object] = {
        "notion": notion_id,
        "field": field_entry.get("id"),
        "widget": field_entry.get("widget"),
        "path": path,
        "label": {"key": label_key, "text": label_text},
        "message": {"key": message_key, "text": message_text},
        "present": present,
        "mutable": bool(mutable)
        and field_entry.get("command") is not None
        and field_entry.get("widget") != "readonly",
        "choices": copy.deepcopy(field_entry.get("choices") or []),
        "targetTypes": copy.deepcopy(field_entry.get("targetTypes") or []),
    }
    if present:
        record["display"] = _display_value(tree, target, field_entry.get("display"), stored)
        record["value"] = copy.deepcopy(stored)
    return record


def _display_value(
    tree: dict[str, object],
    target: dict[str, object],
    display_ast: object,
    stored: object,
) -> object:
    """Evaluate one field display value, falling back to storage."""
    if display_ast is None:
        return stored
    try:
        context = make_read_context(tree)
        return _eval_value(display_ast, context, {"root": tree, "self": target, "params": {}})
    except Exception:  # noqa: BLE001 - display falls back to storage
        return stored


def list_fields(
    compiled: CompiledProfile,
    tree: dict[str, object],
    target_id: object,
    locale: object,
) -> PureResult:
    """List the visible fields of the notions recognizing a target."""
    if not isinstance(target_id, str):
        return pure_refused("profile-type")
    if not isinstance(locale, str):
        return pure_refused("operation-error")
    index = build_stage_index(tree)
    target = index.by_id.get(target_id)
    if target is None:
        return pure_refused("reference-dangling")
    try:
        ui = _ui_index(compiled)
    except CommandError as exc:
        return pure_refused(exc.code)
    fields: list[dict[str, object]] = []
    for notion_id in recognized_notions(compiled, tree, target):
        records = (
            _read_field_state(compiled, tree, ui, target, notion_id, field_entry, locale)
            for field_entry in ui.notion_fields.get(notion_id, ())
        )
        fields.extend(record for record in records if record is not None)
    return pure_success({"targetId": target_id, "fields": fields})


def _resolve_check_field(
    compiled: CompiledProfile,
    tree: dict[str, object],
    index: StageIndex,
    target_id: str,
    field_id: str,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """Resolve one reference-query field to ``(target, field, recipe)``."""
    ui = _ui_index(compiled)
    target = index.by_id.get(target_id)
    if target is None:
        raise CommandError("reference-dangling")  # noqa: EM101
    holders: list[tuple[str, dict[str, object]]] = []
    for notion_id in recognized_notions(compiled, tree, target):
        holders.extend(
            (notion_id, field_entry)
            for field_entry in ui.notion_fields.get(notion_id, ())
            if field_entry.get("id") == field_id
        )
    if not holders:
        raise CommandError("profile-symbol")  # noqa: EM101
    if len({notion_id for notion_id, _ in holders}) > 1:
        raise CommandError("profile-ambiguous-notion")  # noqa: EM101
    _, field_entry = holders[0]
    recipes = getattr(compiled, "recipes", {})
    command_name = field_entry.get("command")
    recipe = recipes.get(str(command_name)) if isinstance(recipes, dict) else None
    if not isinstance(recipe, dict):
        raise CommandError("profile-producer")  # noqa: EM101
    return target, field_entry, recipe


def _invalid_outcome(field_entry: dict[str, object], code: str) -> PureResult:
    """Build one ``valid: false`` outcome with the field message key."""
    message = field_entry.get("message")
    return pure_success(
        {
            "valid": False,
            "code": code,
            "messageKey": message if isinstance(message, str) else "invalid",
        }
    )


def check_field(
    compiled: CompiledProfile,
    tree: dict[str, object],
    target_id: object,
    field_id: object,
    value: object,
) -> PureResult:
    """Validate one submitted field value without committing."""
    if not isinstance(target_id, str) or not isinstance(field_id, str):
        return pure_refused("operation-error")
    index = build_stage_index(tree)
    try:
        _ui_index(compiled)
        target, field_entry, recipe = _resolve_check_field(
            compiled, tree, index, target_id, field_id
        )
    except CommandError as exc:
        return pure_refused(exc.code)
    if not _field_editable(compiled, tree, target, field_entry):
        return _invalid_outcome(field_entry, "profile-producer")
    try:
        check_field_value(index, field_entry, recipe, target_id, value)
    except CommandError as exc:
        return _invalid_outcome(field_entry, exc.code)
    return pure_success({"valid": True})


def _check_reference_page(  # noqa: PLR0913, PLR0917 - page inputs are fixed
    target_id: object,
    field_id: object,
    query: object,
    offset: object,
    limit: object,
    base_revision: object,
    current_revision: str,
) -> tuple[str, str, str, int, int]:
    """Validate reference query arguments in section-5 order (raises refusals)."""
    if (
        not isinstance(target_id, str)
        or not isinstance(field_id, str)
        or not isinstance(query, str)
    ):
        raise CommandError("operation-error")  # noqa: EM101
    if not _safe_count(offset) or not _safe_count(limit):
        raise CommandError("profile-bounds")  # noqa: EM101
    if not isinstance(base_revision, str) or base_revision != current_revision:
        raise CommandError("operation-error")  # noqa: EM101
    if not isinstance(offset, int) or not isinstance(limit, int):
        raise CommandError("operation-error")  # noqa: EM101
    return target_id, field_id, query, offset, limit


def query_references(  # noqa: PLR0913, PLR0917 - reference query inputs are fixed
    compiled: CompiledProfile,
    tree: dict[str, object],
    current_revision: str,
    target_id: object,
    field_id: object,
    query: object,
    offset: object,
    limit: object,
    base_revision: object,
) -> PureResult:
    """List reference candidates of one field with paging."""
    try:
        target_str, field_str, query_str, offset_int, limit_int = _check_reference_page(
            target_id, field_id, query, offset, limit, base_revision, current_revision
        )
    except CommandError as exc:
        return pure_refused(exc.code)
    index = build_stage_index(tree)
    try:
        _ui_index(compiled)
        target, field_entry, _recipe = _resolve_check_field(
            compiled, tree, index, target_str, field_str
        )
    except CommandError as exc:
        return pure_refused(exc.code)
    if field_entry.get("widget") != "reference":
        return pure_refused("profile-type")
    if not _field_editable(compiled, tree, target, field_entry):
        return pure_success({"candidates": []})
    wanted = _string_list(field_entry.get("targetTypes"))
    candidates = resolve_reference_candidates(tree, index, target_str, wanted, query_str)
    return pure_success({"candidates": candidates[offset_int : offset_int + limit_int]})


def _safe_count(value: object) -> bool:
    """Return whether a paging bound is a safe nonnegative integer."""
    return (
        isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= _MAX_SAFE_INTEGER
    )


def _collect_copy_ids(element_ids: object, index: StageIndex) -> list[str]:
    """Collect requested copy IDs, dropping duplicates (raises refusals)."""
    if not isinstance(element_ids, list):
        raise CommandError("operation-error")  # noqa: EM101
    wanted: list[str] = []
    for name in element_ids:
        if not isinstance(name, str):
            raise CommandError("profile-type")  # noqa: EM101
        if name not in index.by_id:
            raise CommandError("reference-dangling")  # noqa: EM101
        if name == index.root_id:
            raise CommandError("profile-type")  # noqa: EM101
        if name not in wanted:
            wanted.append(name)
    return wanted


def _drop_contained(wanted: list[str], index: StageIndex) -> list[str]:
    """Drop requested IDs contained in another requested element."""
    drop: set[str] = set()
    for name in wanted:
        ancestor = index.parent.get(name)
        while isinstance(ancestor, str):
            if ancestor in wanted:
                drop.add(name)
                break
            ancestor = index.parent.get(ancestor)
    return [name for name in wanted if name not in drop]


def copy_fragment(
    compiled: CompiledProfile | None,
    tree: dict[str, object],
    revision: str,
    element_ids: object,
) -> PureResult:
    """Copy requested elements into a canonical pre-order fragment."""
    _ = compiled
    index = build_stage_index(tree)
    try:
        wanted = _collect_copy_ids(element_ids, index)
    except CommandError as exc:
        return pure_refused(exc.code)
    keep = _drop_contained(wanted, index)
    elements = []
    for element, _, _ in canonical_preorder(tree):
        element_id = element.get("id")
        if not isinstance(element_id, str) or element_id not in keep:
            continue
        elements.append({"property": index.prop.get(element_id), "element": copy.deepcopy(element)})
    return pure_success({"fragmentVersion": "1", "sourceRevision": revision, "elements": elements})


def localize(compiled: CompiledProfile, key: object, locale: object) -> PureResult:
    """Resolve one profile message key for a locale."""
    try:
        ui = _ui_index(compiled)
    except CommandError as exc:
        return pure_refused(exc.code)
    if not isinstance(key, str) or not isinstance(locale, str):
        return pure_refused("operation-error")
    text, source = localize_message(ui, key, locale)
    return pure_success({"key": key, "text": text, "source": source})
