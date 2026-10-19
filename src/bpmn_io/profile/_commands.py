"""Command records, resolution, binding, typing and paste (lot 5).

Implements the per-command checks (a)-(h) of the binding spec section 5:
closed record shape, resolution, context sources, handle checks,
``ui.when``/field authorization, value typing and paste fragment
compilation. Recipe execution (i) stays with the transaction pipeline,
which plans through the lot-3 signatures.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypeGuard

from bpmn_io.profile._c14n import jcs
from bpmn_io.profile._evaluate import ReadContext, evaluate_predicate, make_read_context
from bpmn_io.profile._results import PureSuccess
from bpmn_io.profile._stable_id import allocate_stable_id
from bpmn_io.profile._ui import UiIndex

if TYPE_CHECKING:
    from bpmn_io.profile._compiler import CompiledProfile

__all__ = [
    "FIELD_SOURCES",
    "SURFACE_SUBJECT",
    "CommandError",
    "PreparedCommand",
    "build_stage_index",
    "canonical_preorder",
    "check_field_value",
    "descriptor_facets",
    "evaluate_when",
    "nearest_process_id",
    "prepare_command",
    "recognized_notions",
    "replacement_rows",
    "resolve_field",
    "resolve_reference_candidates",
]

#: Surfaces whose subject is each context member (binding spec section 3.1).
SURFACE_SUBJECT: dict[str, str] = {
    "palette": "owner",
    "paste": "owner",
    "context": "target",
    "replace": "target",
    "delete": "target",
    "direct-edit": "target",
    "append": "source",
    "connect": "source",
}

#: Command context members carrying element handles or the submitted value.
FIELD_SOURCES = frozenset({"owner", "target", "source", "value", "key"})

_MAX_INDEX_NODES = 4000000


class CommandError(Exception):
    """One per-command refusal carrying its closed code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class StageIndex:
    """Bounded ID index over one stage tree with parent links."""

    by_id: dict[str, dict[str, object]] = field(default_factory=dict)
    parent: dict[str, str | None] = field(default_factory=dict)
    prop: dict[str, str | None] = field(default_factory=dict)
    root_id: str | None = None


@dataclass
class PreparedCommand:
    """One validated command ready for lot-3 planning."""

    kind: str
    entry_id: str | None
    surface: str | None
    recipe_id: str
    params: dict[str, object]
    deletion_intent: bool
    subject_id: str


def _utf16(value: str) -> bytes:
    """Encode one string in UTF-16 code units (the deterministic sort order)."""
    return value.encode("utf-16-be")


def _is_element(value: object) -> TypeGuard[dict[str, object]]:
    """Return whether a value is an ID-bearing native element dict."""
    return (
        isinstance(value, dict)
        and isinstance(value.get("$type"), str)
        and isinstance(value.get("id"), str)
    )


def canonical_preorder(tree: object) -> list[tuple[dict[str, object], str | None, str | None]]:
    """Walk one tree in canonical pre-order (explicit stack, bounded).

    An element precedes its descendants; object members sort in UTF-16 key
    order and array items keep their index. Returns ``(element, parent_id,
    property)`` triples.
    """
    found: list[tuple[dict[str, object], str | None, str | None]] = []
    if not isinstance(tree, dict):
        return found
    visited = 0
    stack: list[tuple[dict[str, object], str | None, str | None]] = [(tree, None, None)]
    seen: set[int] = set()
    while stack:
        node, parent_id, prop = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        visited += 1
        if visited > _MAX_INDEX_NODES:
            break
        raw_id = node.get("id")
        node_id = raw_id if isinstance(raw_id, str) else None
        found.append((node, parent_id, prop))
        children: list[tuple[dict[str, object], str | None, str | None]] = []
        for key in sorted(node.keys(), key=_utf16):
            value = node[key]
            if _is_element(value):
                children.append((value, node_id, key))
            elif isinstance(value, list):
                children.extend((entry, node_id, key) for entry in value if _is_element(entry))
        stack.extend(reversed(children))
    return found


def build_stage_index(tree: dict[str, object]) -> StageIndex:
    """Index one stage tree by element ID with parent links."""
    index = StageIndex()
    for element, parent_id, prop in canonical_preorder(tree):
        element_id = element.get("id")
        if not isinstance(element_id, str):
            continue
        if element_id not in index.by_id:
            index.by_id[element_id] = element
            index.parent[element_id] = parent_id
            index.prop[element_id] = prop
        if parent_id is None:
            index.root_id = element_id
    return index


def _ui_index(compiled: CompiledProfile) -> UiIndex:
    """Return the compiled UI index (missing index is an invocation error)."""
    index = getattr(compiled, "ui", None)
    if not isinstance(index, UiIndex):
        raise CommandError("operation-error")  # noqa: EM101
    return index


def _recipes(compiled: CompiledProfile) -> dict[str, dict[str, object]]:
    """Return the compiled recipe table."""
    recipes = getattr(compiled, "recipes", {})
    return recipes if isinstance(recipes, dict) else {}


def _notions(compiled: CompiledProfile) -> dict[str, dict[str, object]]:
    """Return the compiled notion recognition table."""
    notions = getattr(compiled, "notions", {})
    return notions if isinstance(notions, dict) else {}


def _read_context_for(tree: dict[str, object], compiled: CompiledProfile) -> ReadContext:
    """Build one read-only evaluation context over a stage tree."""
    recognition = {
        notion_id: info.get("recognition")
        for notion_id, info in _notions(compiled).items()
        if isinstance(info, dict)
    }
    return make_read_context(tree, notions=recognition)


def evaluate_when(
    compiled: CompiledProfile,
    tree: dict[str, object],
    predicate: object,
    subject: dict[str, object],
) -> bool:
    """Evaluate one ``ui.when`` predicate with ``root``/``self`` bindings."""
    context = _read_context_for(tree, compiled)
    outcome = evaluate_predicate(predicate, context, {"root": tree, "self": subject})
    if isinstance(outcome, PureSuccess):
        return outcome.payload is True
    return False


def recognized_notions(
    compiled: CompiledProfile,
    tree: dict[str, object],
    target: dict[str, object],
) -> list[str]:
    """Return the notion IDs recognizing ``target``, in profile order."""
    index = _ui_index(compiled)
    notions = _notions(compiled)
    recognized: list[str] = []
    for notion_id in index.notion_order:
        info = notions.get(notion_id)
        if not isinstance(info, dict):
            continue
        predicate = info.get("recognition")
        if predicate is None:
            continue
        if evaluate_when(compiled, tree, predicate, target):
            recognized.append(notion_id)
    return recognized


def _resolve_surface(
    compiled: CompiledProfile, command: dict[str, object]
) -> tuple[dict[str, object], dict[str, object]]:
    """Resolve a surface/upstream command to ``(entry, recipe)``."""
    index = _ui_index(compiled)
    recipes = _recipes(compiled)
    kind = command.get("command")
    entry: dict[str, object] | None = None
    if kind == "surface":
        name = command.get("entry")
        if not isinstance(name, str):
            raise CommandError("profile-symbol")  # noqa: EM101
        entry = index.by_id.get(name)
        if entry is None:
            raise CommandError("profile-symbol")  # noqa: EM101
    elif kind == "upstream":
        name = command.get("upstream")
        if not isinstance(name, str):
            raise CommandError("transaction-entry-unsupported")  # noqa: EM101
        entry_id = index.upstream.get(name)
        if entry_id is None:
            raise CommandError("transaction-entry-unsupported")  # noqa: EM101
        entry = index.by_id.get(entry_id)
        if entry is None:  # pragma: no cover - compile guarantees the target
            raise CommandError("profile-symbol")  # noqa: EM101
    else:
        message = f"not a surface command: {kind!r}"
        raise ValueError(message)
    recipe = recipes.get(str(entry.get("recipe")))
    if not isinstance(recipe, dict):  # pragma: no cover - compile guarantees it
        raise CommandError("profile-symbol")  # noqa: EM101
    return entry, recipe


def resolve_field(
    compiled: CompiledProfile, notion_id: object, field_id: object
) -> tuple[dict[str, object], dict[str, object]]:
    """Resolve a notion-qualified field to ``(field, recipe)``."""
    index = _ui_index(compiled)
    recipes = _recipes(compiled)
    if not isinstance(notion_id, str) or notion_id not in index.notion_fields:
        raise CommandError("profile-symbol")  # noqa: EM101
    found: dict[str, object] | None = None
    for candidate in index.notion_fields[notion_id]:
        if candidate.get("id") == field_id:
            found = candidate
            break
    if found is None:
        raise CommandError("profile-symbol")  # noqa: EM101
    command_name = found.get("command")
    recipe = recipes.get(str(command_name)) if command_name is not None else None
    if not isinstance(recipe, dict):
        raise CommandError("profile-producer")  # noqa: EM101
    return found, recipe


def _entry_parameter_sources(entry: dict[str, object]) -> dict[str, str]:
    """Return ``{parameter name: source}`` of one UI entry or field."""
    sources: dict[str, str] = {}
    parameters = entry.get("parameters")
    if isinstance(parameters, list):
        for binding in parameters:
            if (
                isinstance(binding, dict)
                and isinstance(binding.get("name"), str)
                and isinstance(binding.get("source"), str)
            ):
                sources[str(binding["name"])] = str(binding["source"])
    return sources


def _recipe_param_types(recipe: dict[str, object]) -> dict[str, str]:
    """Return ``{parameter name: type}`` of one recipe."""
    types: dict[str, str] = {}
    parameters = recipe.get("parameters")
    if isinstance(parameters, list):
        for param in parameters:
            if isinstance(param, dict) and isinstance(param.get("name"), str):
                param_type = param.get("type")
                types[str(param["name"])] = (
                    str(param_type) if isinstance(param_type, str) else "unknown"
                )
    return types


def _check_context_keys(
    context: object,
    subject_key: str,
    bound_sources: dict[str, str],
) -> dict[str, object]:
    """Validate the closed context member set (check (b)/(d))."""
    if not isinstance(context, dict):
        raise CommandError("profile-ui-parameters")  # noqa: EM101
    wanted = {subject_key, *set(bound_sources.values())}
    if set(context) != wanted:
        raise CommandError("profile-ui-parameters")  # noqa: EM101
    return context


def _check_handles(
    context: dict[str, object],
    bound_sources: dict[str, str],
    index: StageIndex,
) -> None:
    """Validate handle members are present ID strings (check (e))."""
    for source in bound_sources.values():
        if source not in ("owner", "target", "source"):
            continue
        handle = context.get(source)
        if not isinstance(handle, str):
            raise CommandError("profile-type")  # noqa: EM101
        if handle not in index.by_id:
            raise CommandError("reference-dangling")  # noqa: EM101


def _check_scalar(value: object, param_type: str) -> None:
    """Validate one submitted value against its recipe type (check (g))."""
    if value is None:
        raise CommandError("profile-type")  # noqa: EM101
    if param_type == "string":
        if not isinstance(value, str):
            raise CommandError("profile-type")  # noqa: EM101
    elif param_type == "number":
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or (isinstance(value, float) and (math.isnan(value) or math.isinf(value)))
        ):
            raise CommandError("profile-type")  # noqa: EM101
    elif param_type == "boolean":
        if not isinstance(value, bool):
            raise CommandError("profile-type")  # noqa: EM101
    else:
        raise CommandError("profile-type")  # noqa: EM101


def nearest_process_id(index: StageIndex, element_id: str) -> str | None:
    """Return the nearest Process ancestor ID above one element."""
    seen: set[str] = set()
    current = index.parent.get(element_id)
    while isinstance(current, str) and current not in seen:
        seen.add(current)
        element = index.by_id.get(current)
        if isinstance(element, dict) and element.get("$type") == "bpmn:Process":
            return current
        current = index.parent.get(current)
    return None


def _ownership_ok(index: StageIndex, target_id: str, candidate_id: str) -> bool:
    """Apply effective reference ownership of one candidate for a target."""
    parent = index.parent.get(candidate_id)
    if parent is not None and parent == index.root_id:
        return True
    candidate_process = nearest_process_id(index, candidate_id)
    target_process = nearest_process_id(index, target_id)
    if candidate_process is None or target_process is None:
        return False
    return candidate_process == target_process


def descriptor_facets(
    types: dict[str, dict[str, object]], type_name: str
) -> dict[str, dict[str, tuple[str, ...]]]:
    """Return the containment/reference facets of one descriptor type."""
    record = types.get(type_name)
    facets: dict[str, dict[str, tuple[str, ...]]] = {"containment": {}, "references": {}}
    if not isinstance(record, dict):
        return facets
    for facet in ("containment", "references"):
        raw = record.get(facet)
        if isinstance(raw, dict):
            table: dict[str, tuple[str, ...]] = {}
            for prop, admitted in raw.items():
                if isinstance(prop, str) and isinstance(admitted, (list, tuple)):
                    table[prop] = tuple(str(name) for name in admitted if isinstance(name, str))
            facets[facet] = table
    return facets


def resolve_reference_candidates(
    tree: dict[str, object],
    index: StageIndex,
    target_id: str,
    target_types: list[str],
    query: str,
) -> list[dict[str, object]]:
    """List matching reference candidates in UTF-16 ID order (section 4.6)."""
    matches: list[dict[str, object]] = []
    for element, _, _ in canonical_preorder(tree):
        element_id = element.get("id")
        if not isinstance(element_id, str):
            continue
        if element.get("$type") not in target_types:
            continue
        if not _ownership_ok(index, target_id, element_id):
            continue
        name = element.get("name")
        label = name if isinstance(name, str) else ""
        if query not in label:
            continue
        matches.append({"id": element_id, "type": element.get("$type"), "label": label})
    matches.sort(key=lambda entry: _utf16(str(entry["id"])))
    return matches


def _check_enum_value(field_entry: dict[str, object], value: object) -> None:
    """Validate one submitted value against enum choices (check (g))."""
    choices = field_entry.get("choices")
    accepted = (
        {jcs(choice.get("value")) for choice in choices if isinstance(choice, dict)}
        if isinstance(choices, list)
        else set()
    )
    if jcs(value) not in accepted:
        raise CommandError("profile-type")  # noqa: EM101


def _check_reference_value(
    index: StageIndex,
    field_entry: dict[str, object],
    target_id: str,
    value: object,
) -> None:
    """Validate one submitted reference ID (check (g))."""
    if not isinstance(value, str):
        raise CommandError("profile-type")  # noqa: EM101
    candidate = index.by_id.get(value)
    if candidate is None:
        raise CommandError("reference-dangling")  # noqa: EM101
    wanted = _string_list(field_entry.get("targetTypes"))
    if candidate.get("$type") not in wanted:
        raise CommandError("profile-type")  # noqa: EM101
    if not _ownership_ok(index, target_id, value):
        raise CommandError("profile-type")  # noqa: EM101


def _string_list(value: object) -> list[str]:
    """Return the string members of one list value."""
    if isinstance(value, list):
        return [str(name) for name in value if isinstance(name, str)]
    return []


def check_field_value(
    index: StageIndex,
    field_entry: dict[str, object],
    recipe: dict[str, object],
    target_id: str,
    value: object,
) -> None:
    """Validate one submitted field value, widget rules included (check (g))."""
    bound = _entry_parameter_sources(field_entry)
    recipe_params = _recipe_param_types(recipe)
    for name, source in bound.items():
        if source == "value":
            _check_scalar(value, recipe_params.get(name, "unknown"))
    widget = field_entry.get("widget")
    if widget == "enum":
        _check_enum_value(field_entry, value)
    elif widget == "reference":
        _check_reference_value(index, field_entry, target_id, value)


def prepare_command(
    compiled: CompiledProfile,
    tree: dict[str, object],
    index: StageIndex,
    command: object,
    types: dict[str, dict[str, object]] | None = None,
) -> PreparedCommand:
    """Validate one command record through check (h) (checks (a)-(h)).

    Returns the recipe, bound parameters and deletion intent for lot-3
    planning. Paste fragments are compiled onto the stage tree in place;
    ``types`` is the descriptor type index used for paste admission.
    """
    # Check (a): closed command kinds only.
    if not isinstance(command, dict):
        raise CommandError("transaction-entry-unsupported")  # noqa: EM101
    kind = command.get("command")
    if kind == "field":
        return _prepare_field(compiled, tree, index, command)
    if kind in ("surface", "upstream"):
        return _prepare_surface(compiled, tree, index, command, types or {})
    raise CommandError("transaction-entry-unsupported")  # noqa: EM101


def _surface_shape(command: dict[str, object]) -> str:
    """Validate the closed surface/upstream member set (check (b))."""
    kind = str(command.get("command"))
    for key in command:
        if key not in {"command", "entry", "upstream", "context", "fragment"}:
            raise CommandError("profile-ui-parameters")  # noqa: EM101
    if kind == "surface" and ("entry" not in command or "context" not in command):
        raise CommandError("profile-ui-parameters")  # noqa: EM101
    if kind == "upstream" and ("upstream" not in command or "context" not in command):
        raise CommandError("profile-ui-parameters")  # noqa: EM101
    return kind


def _surface_subject(
    index: StageIndex,
    context: dict[str, object],
    subject_key: str,
) -> dict[str, object]:
    """Return the subject element of one surface command (check (e))."""
    subject_id = context.get(subject_key)
    if not isinstance(subject_id, str):
        raise CommandError("profile-type")  # noqa: EM101
    subject = index.by_id.get(subject_id)
    if subject is None:
        raise CommandError("reference-dangling")  # noqa: EM101
    return subject


def _surface_values(
    bound: dict[str, str],
    recipe_params: dict[str, str],
    context: dict[str, object],
) -> None:
    """Validate submitted values and keys of one surface command (check (g))."""
    for name, source in bound.items():
        if source == "value":
            _check_scalar(context.get("value"), recipe_params.get(name, "unknown"))
        elif source == "key" and not isinstance(context.get("key"), str):
            raise CommandError("profile-type")  # noqa: EM101


def _prepare_surface(
    compiled: CompiledProfile,
    tree: dict[str, object],
    index: StageIndex,
    command: dict[str, object],
    types: dict[str, dict[str, object]],
) -> PreparedCommand:
    """Validate one surface/upstream command through check (h)."""
    kind = _surface_shape(command)
    entry, recipe = _resolve_surface(compiled, command)
    surface = str(entry.get("surface"))
    bound = _entry_parameter_sources(entry)
    subject_key = SURFACE_SUBJECT.get(surface, "target")
    context = _check_context_keys(command.get("context"), subject_key, bound)
    fragment = command.get("fragment")
    if (fragment is not None) != (surface == "paste"):
        raise CommandError("profile-ui-parameters")  # noqa: EM101
    _check_handles(context, bound, index)
    subject = _surface_subject(index, context, subject_key)
    subject_id = context.get(subject_key)
    if not isinstance(subject_id, str):  # pragma: no cover - checked above
        raise CommandError("profile-type")  # noqa: EM101
    if not evaluate_when(compiled, tree, entry.get("when", {"op": "true"}), subject):
        raise CommandError("profile-producer")  # noqa: EM101
    _surface_values(bound, _recipe_param_types(recipe), context)
    if surface == "paste":
        if not isinstance(fragment, dict):  # pragma: no cover - checked above
            raise CommandError("profile-ui-parameters")  # noqa: EM101
        _apply_paste(index, types, subject_id, str(context.get("key")), fragment)
    return PreparedCommand(
        kind=kind,
        entry_id=str(entry.get("id")),
        surface=surface,
        recipe_id=str(entry.get("recipe")),
        params=_bind_params(bound, context),
        deletion_intent=surface in ("delete", "replace"),
        subject_id=subject_id,
    )


def _prepare_field(
    compiled: CompiledProfile,
    tree: dict[str, object],
    index: StageIndex,
    command: dict[str, object],
) -> PreparedCommand:
    """Validate one field command through check (h)."""
    # Check (b): closed members.
    if set(command) != {"command", "notion", "field", "context"}:
        raise CommandError("profile-ui-parameters")  # noqa: EM101
    # Check (c): notion-qualified field resolution.
    field_entry, recipe = resolve_field(compiled, command.get("notion"), command.get("field"))
    # Check (d): exactly target plus bound sources.
    bound = _entry_parameter_sources(field_entry)
    context = _check_context_keys(command.get("context"), "target", bound)
    # Check (e): target handle, then notion recognition.
    target_id = context.get("target")
    if not isinstance(target_id, str):
        raise CommandError("profile-type")  # noqa: EM101
    target = index.by_id.get(target_id)
    if target is None:
        raise CommandError("reference-dangling")  # noqa: EM101
    notion_id = str(command.get("notion"))
    if notion_id not in recognized_notions(compiled, tree, target):
        raise CommandError("profile-type")  # noqa: EM101
    # Check (f): visible, mutable, commanded, writable widget.
    if not _field_editable(compiled, tree, target, field_entry):
        raise CommandError("profile-producer")  # noqa: EM101
    # Check (g): value typing and widget rules, revalidated at commit.
    if "value" not in context:
        raise CommandError("profile-ui-parameters")  # noqa: EM101
    check_field_value(index, field_entry, recipe, target_id, context.get("value"))
    return PreparedCommand(
        kind="field",
        entry_id=None,
        surface=None,
        recipe_id=str(field_entry.get("command")),
        params=_bind_params(bound, context),
        deletion_intent=False,
        subject_id=target_id,
    )


def _field_editable(
    compiled: CompiledProfile,
    tree: dict[str, object],
    target: dict[str, object],
    field_entry: dict[str, object],
) -> bool:
    """Return whether one field accepts an edit on a target right now."""
    if field_entry.get("command") is None:
        return False
    if field_entry.get("widget") == "readonly":
        return False
    if not evaluate_when(compiled, tree, field_entry.get("visible", {"op": "true"}), target):
        return False
    return evaluate_when(compiled, tree, field_entry.get("mutable", {"op": "true"}), target)


def _bind_params(bound: dict[str, str], context: dict[str, object]) -> dict[str, object]:
    """Feed recipe parameters from command context members."""
    return {name: copy.deepcopy(context[source]) for name, source in bound.items()}


def replacement_rows(
    recipe_phase: str,
    removed: list[str],
    created: list[str],
) -> list[dict[str, object]]:
    """Return the section-4.5 replacement-map rows of one convert execution."""
    if recipe_phase != "convert":
        return []
    if len(removed) != 1 or len(created) != 1:
        return []
    if removed[0] == created[0]:
        return []
    return [{"sourceId": removed[0], "resultId": created[0], "domain": "migration"}]


def _prepare_paste_root(  # noqa: PLR0913, PLR0917 - paste root inputs are fixed
    index: StageIndex,
    types: dict[str, dict[str, object]],
    owner_id: str,
    owner_facets: dict[str, dict[str, tuple[str, ...]]],
    key: str,
    root: object,
    remap: dict[str, str],
) -> tuple[str, dict[str, object]]:
    """Allocate IDs of one fragment root and validate its placement."""
    if not isinstance(root, dict):
        raise CommandError("profile-type")  # noqa: EM101
    prop = root.get("property")
    element = root.get("element")
    if not isinstance(prop, str) or not _is_element(element):
        raise CommandError("profile-type")  # noqa: EM101
    admitted = owner_facets["containment"].get(prop)
    if admitted is None or element.get("$type") not in admitted:
        raise CommandError("profile-type")  # noqa: EM101
    fresh = copy.deepcopy(element)
    for node, _, _ in canonical_preorder(fresh):
        node_id = node.get("id")
        if not isinstance(node_id, str):
            raise CommandError("profile-type")  # noqa: EM101
        new_id = allocate_stable_id(owner_id, "paste", jcs([key, node_id]))
        if new_id in index.by_id or new_id in remap.values():
            raise CommandError("id-collision")  # noqa: EM101
        remap[node_id] = new_id
    _rewrite_refs(types, fresh, remap, index)
    _assign_remapped_ids(fresh, remap)
    return prop, fresh


def _apply_paste(
    index: StageIndex,
    types: dict[str, dict[str, object]],
    owner_id: str,
    key: str,
    fragment: dict[str, object],
) -> None:
    """Compile one paste fragment onto the stage tree (check (h))."""
    if not isinstance(key, str):
        raise CommandError("profile-type")  # noqa: EM101
    if fragment.get("fragmentVersion") != "1":
        raise CommandError("profile-type")  # noqa: EM101
    roots = fragment.get("elements")
    if not isinstance(roots, list):
        raise CommandError("profile-type")  # noqa: EM101
    owner = index.by_id.get(owner_id)
    if owner is None:  # pragma: no cover - checked at (e)
        raise CommandError("reference-dangling")  # noqa: EM101
    owner_type = owner.get("$type")
    if not isinstance(owner_type, str):
        raise CommandError("profile-type")  # noqa: EM101
    owner_facets = descriptor_facets(types, owner_type)
    remap: dict[str, str] = {}
    staged = [
        _prepare_paste_root(index, types, owner_id, owner_facets, key, root, remap)
        for root in roots
    ]
    for prop, fresh in staged:
        container = owner.get(prop)
        if not isinstance(container, list):
            raise CommandError("profile-type")  # noqa: EM101
        container.append(fresh)
        for element, parent_id, element_prop in canonical_preorder(fresh):
            element_id = element.get("id")
            if not isinstance(element_id, str):  # pragma: no cover - remapped
                raise CommandError("profile-type")  # noqa: EM101
            index.by_id[element_id] = element
            index.parent[element_id] = parent_id if parent_id is not None else owner_id
            index.prop[element_id] = element_prop if parent_id is not None else prop


def _assign_remapped_ids(fresh: dict[str, object], remap: dict[str, str]) -> None:
    """Assign reallocated IDs throughout one pasted subtree."""
    stack: list[object] = [fresh]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            node_id = node.get("id")
            if isinstance(node_id, str) and node_id in remap:
                node["id"] = remap[node_id]
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)


def _rewrite_member(  # noqa: PLR0913, PLR0917 - rewrite inputs are fixed
    references: dict[str, tuple[str, ...]],
    node: dict[str, object],
    key: str,
    value: object,
    remap: dict[str, str],
    index: StageIndex,
    stack: list[object],
) -> None:
    """Rewrite one fragment member: references remap, elements descend."""
    if isinstance(value, dict):
        stack.append(value)
    elif isinstance(value, list):
        if key in references and all(isinstance(entry, str) for entry in value):
            node[key] = [_remap_or_keep(references[key], entry, remap, index) for entry in value]
        else:
            stack.extend(value)
    elif isinstance(value, str) and key in references:
        node[key] = _remap_or_keep(references[key], value, remap, index)


def _rewrite_refs(
    types: dict[str, dict[str, object]],
    fresh: dict[str, object],
    remap: dict[str, str],
    index: StageIndex,
) -> None:
    """Rewrite fragment-internal references; validate external ones."""
    stack: list[object] = [fresh]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(node)
            continue
        if not isinstance(node, dict):
            continue
        type_name = node.get("$type")
        references: dict[str, tuple[str, ...]] = {}
        if isinstance(type_name, str):
            references = descriptor_facets(types, type_name)["references"]
        for key, value in list(node.items()):
            if key in ("$type", "id"):
                continue
            _rewrite_member(references, node, key, value, remap, index, stack)


def _remap_or_keep(
    admitted: tuple[str, ...],
    value: str,
    remap: dict[str, str],
    index: StageIndex,
) -> str:
    """Reallocate one fragment reference or validate its external target."""
    if value in remap:
        return remap[value]
    target = index.by_id.get(value)
    if target is None:
        raise CommandError("reference-dangling")  # noqa: EM101
    if target.get("$type") not in admitted:
        raise CommandError("profile-type")  # noqa: EM101
    return value
