"""Block-B mirror J6: predicate/Value refusals keep the original code.

Every predicate or Value evaluation outside recognition propagates the
evaluator's original refusal code; non-match conversion stays only at the
recognition sites. Missing/explicitly empty/absent labels keep their
successful meaning.
"""

from __future__ import annotations

import copy
import json

# A predicate that compiles (its bindings are valid) but refuses at runtime
# on subjects carrying no name: concat needs strings, the read is absent.
_REFUSING_SELF_NAME: dict[str, object] = {
    "op": "present",
    "value": {
        "op": "concat",
        "values": [
            {"op": "literal", "value": "v:"},
            {"op": "read", "binding": "self", "path": "/name"},
        ],
    },
}
# A refusing Value for value positions: concat needs strings, the read is
# absent, so evaluation refuses instead of returning a value.
_REFUSING_VALUE: dict[str, object] = {
    "op": "concat",
    "values": [
        {"op": "literal", "value": "v:"},
        {"op": "read", "binding": "self", "path": "/name"},
    ],
}
# A refusing display: ids is context-restricted, so it loads and compiles
# but refuses profile-value-context once evaluated on a present field.
_REFUSING_DISPLAY: dict[str, object] = {
    "op": "ids",
    "select": {"from": "self", "via": "self", "where": {"op": "true"}, "order": "id"},
}


def _neutral_profile() -> dict:
    """Load the neutral lot-5 profile document."""
    from tests.profile_commands import harness as _harness

    raw = (_harness.EXPECTED / "artifacts/profiles/neutral-lot5.json").read_bytes()
    return json.loads(raw.decode("utf-8"))


def _compile(mutator: object) -> tuple[object, object]:
    """Compile the neutral profile with one document mutation."""
    from bpmn_io.profile import (
        compile_profile,
        create_descriptor_context,
        load_profile,
    )
    from tests.profile_commands import harness as _harness

    profile = _neutral_profile()
    mutator(profile)  # type: ignore[operator]
    raw = json.dumps(profile).encode("utf-8")
    package = dict(_harness.DEFAULT_DESCRIPTOR_PIN)
    package["descriptorBytes"] = _harness.DEFAULT_DESCRIPTOR_BYTES
    context_result = create_descriptor_context([package])
    assert context_result.status == "ok", context_result.to_json()
    pins = [{"id": package["id"], "version": package["version"], "sha256": package["sha256"]}]
    load_result = load_profile(
        raw,
        schema_bytes=_harness.SCHEMA_BYTES,
        base_bytes=_harness.BASE_BYTES,
        descriptor_pins=pins,
        asset_bag=dict(_harness.METRICS_BAG),
    )
    assert load_result.status == "ok", load_result.to_json()
    compile_result = compile_profile(
        load_result.payload,  # type: ignore[union-attr]
        descriptor_context=context_result.payload,  # type: ignore[union-attr]
        base=copy.deepcopy(_harness.BASE_DOCUMENT),
    )
    assert compile_result.status == "ok", compile_result.to_json()
    return context_result.payload, compile_result.payload  # type: ignore[return-value]


def _tree() -> dict:
    """Load the neutral witness document tree (Task_1 left unnamed)."""
    from tests.profile_commands import harness as _harness

    case = json.loads((_harness.EXPECTED / "surface-palette-when.json").read_text(encoding="utf-8"))
    tree = copy.deepcopy(case["input"]["document"]["tree"])
    # Task_1 keeps its type (so notion recognition holds) but carries no
    # name, so a name-reading predicate refuses on it at runtime; Task_2
    # stays named for the successful-meaning controls.
    for root in tree.get("rootElements", []):
        for element in root.get("flowElements", []):
            if element.get("id") == "Task_1":
                element.pop("name", None)
    return tree


def _bridge(context: object, compiled: object) -> object:
    """Return one loaded bridge with an active business profile."""
    from bpmn_io.profile import create_bridge
    from bpmn_io.profile._envelope import complete_envelope
    from bpmn_io.profile._ui import compiled_identity

    session = create_bridge(context)  # type: ignore[arg-type]
    loaded = session.set_definitions(
        complete_envelope(compiled_identity(compiled), _tree(), [])  # type: ignore[arg-type]
    )
    assert getattr(loaded, "status", None) == "ok", getattr(loaded, "to_json", lambda: loaded)()
    activated = session.activate_business_profile(compiled)  # type: ignore[arg-type]
    assert getattr(activated, "status", None) == "ok", getattr(
        activated, "to_json", lambda: activated
    )()
    return session


def _entry_mutator(entry_id: str) -> object:
    def _mutate(profile: dict) -> None:
        for entry in profile.get("ui", []):
            if entry.get("id") == entry_id:
                entry["when"] = copy.deepcopy(_REFUSING_SELF_NAME)

    return _mutate


def _field_mutator(notion_id: str, field_id: str, member: str, ast: object) -> object:
    def _mutate(profile: dict) -> None:
        for notion in profile.get("notions", []):
            if notion.get("id") != notion_id:
                continue
            for field in notion.get("fields", []):
                if field.get("id") == field_id:
                    field[member] = copy.deepcopy(ast)

    return _mutate


def test_j6_list_entries_refusal_propagates() -> None:
    """A refusing entry when refuses list_entries with its code."""
    context, compiled = _compile(_entry_mutator("task-create"))
    session = _bridge(context, compiled)
    revision = session.envelope.semantic_revision  # type: ignore[union-attr]
    out = session.list_entries(  # type: ignore[union-attr]
        base_revision=revision, surface="palette", subject="Process_1", locale="en"
    )
    assert out.status == "refused"
    assert out.code == "profile-type"


def test_j6_surface_command_refusal_propagates() -> None:
    """A refusing entry when refuses the surface command with its code."""
    context, compiled = _compile(_entry_mutator("task-create"))
    session = _bridge(context, compiled)
    envelope = session.envelope  # type: ignore[union-attr]
    view = session._current_view(envelope)  # type: ignore[union-attr]  # noqa: SLF001
    out = session.apply_commands(  # type: ignore[union-attr]
        base_revision=envelope.semantic_revision,
        expected_view_revision=view,
        commands=[
            {
                "command": "surface",
                "entry": "task-create",
                "context": {"owner": "Process_1", "key": "w1", "value": "Witness"},
            }
        ],
        transaction_id="tx-j6-surface",
    )
    assert getattr(out, "status", None) == "refused"
    assert getattr(out, "code", None) == "profile-type"


def test_j6_field_command_visible_refusal_propagates() -> None:
    """A refusing field visible refuses the field command with its code."""
    context, compiled = _compile(_field_mutator("task", "name", "visible", _REFUSING_SELF_NAME))
    session = _bridge(context, compiled)
    envelope = session.envelope  # type: ignore[union-attr]
    view = session._current_view(envelope)  # type: ignore[union-attr]  # noqa: SLF001
    out = session.apply_commands(  # type: ignore[union-attr]
        base_revision=envelope.semantic_revision,
        expected_view_revision=view,
        commands=[
            {
                "command": "field",
                "notion": "task",
                "field": "name",
                "context": {"target": "Task_1", "value": "Witness"},
            }
        ],
        transaction_id="tx-j6-field-visible",
    )
    assert getattr(out, "status", None) == "refused"
    assert getattr(out, "code", None) == "profile-type"


def test_j6_field_command_mutable_refusal_propagates() -> None:
    """A refusing field mutable refuses the field command with its code."""
    context, compiled = _compile(_field_mutator("task", "name", "mutable", _REFUSING_SELF_NAME))
    session = _bridge(context, compiled)
    envelope = session.envelope  # type: ignore[union-attr]
    view = session._current_view(envelope)  # type: ignore[union-attr]  # noqa: SLF001
    out = session.apply_commands(  # type: ignore[union-attr]
        base_revision=envelope.semantic_revision,
        expected_view_revision=view,
        commands=[
            {
                "command": "field",
                "notion": "task",
                "field": "name",
                "context": {"target": "Task_1", "value": "Witness"},
            }
        ],
        transaction_id="tx-j6-field-mutable",
    )
    assert getattr(out, "status", None) == "refused"
    assert getattr(out, "code", None) == "profile-type"


def test_j6_check_field_refusal_keeps_code() -> None:
    """A refusing mutable reports check_field invalid with its code."""
    context, compiled = _compile(_field_mutator("task", "name", "mutable", _REFUSING_SELF_NAME))
    session = _bridge(context, compiled)
    revision = session.envelope.semantic_revision  # type: ignore[union-attr]
    out = session.check_field(  # type: ignore[union-attr]
        base_revision=revision, target_id="Task_1", field_id="name", value="Witness"
    )
    assert out.status == "ok"
    assert out.payload["valid"] is False
    assert out.payload["code"] == "profile-type"


def test_j6_query_references_refusal_propagates() -> None:
    """A refusing field visible refuses the reference query with its code."""
    context, compiled = _compile(
        _field_mutator("reference", "store", "visible", _REFUSING_SELF_NAME)
    )
    session = _bridge(context, compiled)
    revision = session.envelope.semantic_revision  # type: ignore[union-attr]
    out = session.query_references(  # type: ignore[union-attr]
        base_revision=revision,
        target_id="Ref_1",
        field_id="store",
        query="",
        offset=0,
        limit=10,
    )
    assert out.status == "refused"
    assert out.code == "profile-type"


def test_j6_list_fields_visible_refusal_propagates() -> None:
    """A refusing field visible refuses list_fields with its code."""
    context, compiled = _compile(_field_mutator("task", "name", "visible", _REFUSING_SELF_NAME))
    session = _bridge(context, compiled)
    revision = session.envelope.semantic_revision  # type: ignore[union-attr]
    out = session.list_fields(  # type: ignore[union-attr]
        base_revision=revision, target_id="Task_1", locale="en"
    )
    assert out.status == "refused"
    assert out.code == "profile-type"


def test_j6_list_fields_display_refusal_propagates() -> None:
    """A refusing field display refuses list_fields with its code."""
    context, compiled = _compile(_field_mutator("task", "name", "display", _REFUSING_DISPLAY))
    session = _bridge(context, compiled)
    revision = session.envelope.semantic_revision  # type: ignore[union-attr]
    out = session.list_fields(  # type: ignore[union-attr]
        base_revision=revision, target_id="Task_2", locale="en"
    )
    assert out.status == "refused"
    assert out.code == "profile-value-context"


def test_j6_list_fields_absent_display_stays_successful() -> None:
    """A field without display keeps its successful raw meaning."""
    context, compiled = _compile(lambda _profile: None)
    session = _bridge(context, compiled)
    revision = session.envelope.semantic_revision  # type: ignore[union-attr]
    out = session.list_fields(  # type: ignore[union-attr]
        base_revision=revision, target_id="Task_2", locale="en"
    )
    assert out.status == "ok"
    record = next(f for f in out.payload["fields"] if f["field"] == "name")
    assert record["display"] == "Fixed"
    assert record["value"] == "Fixed"


def _prepare_export_input(
    emit_value: dict | None = None, recipe_when: dict | None = None
) -> tuple[object, object, dict]:
    """Build the export.prepare.success input with an empty-label aid node."""
    from tests.profile_export.test_export_cases import build_imported_di
    from tests.profile_export.test_prepare import _asset_bag, _success_input
    from tests.profile_render._lot4_harness import (
        build_case_envelope,
        compile_profile_doc,
        profile_from_ref,
    )

    case_input = _success_input()
    profile = profile_from_ref(case_input["profile"])
    if emit_value is not None:
        recipe = next(r for r in profile["recipes"] if r["id"] == "export-nodes")
        for step in recipe.get("steps", []):
            for field_entry in step.get("fields", []):
                if field_entry.get("name") == "name":
                    field_entry["value"] = copy.deepcopy(emit_value)
    if recipe_when is not None:
        recipe = next(r for r in profile["recipes"] if r["id"] == "export-nodes")
        recipe["when"] = copy.deepcopy(recipe_when)
    tree = copy.deepcopy(case_input["tree"])
    root = tree["rootElements"][0]
    root["artifacts"] = [{"$type": "bpmn:TextAnnotation", "id": "A_1", "text": "[Aid] "}]
    options = copy.deepcopy(case_input["options"])
    diagrams = options.pop("diagrams", None)
    assert isinstance(diagrams, list)
    assert diagrams
    shapes = diagrams[0]["plane"]["planeElement"]
    shape = copy.deepcopy(shapes[0])
    shape["id"] = "A_1_di"
    shape["bpmnElement"] = "A_1"
    shape["bounds"] = {**shape["bounds"], "y": shape["bounds"]["y"] + 300}
    shapes.append(shape)
    compiled_result, _, _ = compile_profile_doc(copy.deepcopy(profile), _asset_bag(profile))
    assert compiled_result.status == "ok", compiled_result.to_json()
    compiled = compiled_result.payload
    envelope = build_case_envelope(
        compiled,
        profile,
        tree,
        copy.deepcopy(case_input.get("bindings", [])),
        case_input.get("envelopeIdentity"),
    )
    options["importedDi"] = build_imported_di(compiled.identity, diagrams)
    return compiled, envelope, options


def test_j6_export_value_refusal_propagates() -> None:
    """A refusing export field value refuses profile-type (lot4-query)."""
    from bpmn_io.profile._prepare import prepare_export

    refusing = {
        "op": "concat",
        "values": [
            {"op": "literal", "value": "v:"},
            {"op": "read", "binding": "self", "path": "/label/text"},
        ],
    }
    compiled, envelope, options = _prepare_export_input(emit_value=refusing)
    out = prepare_export(compiled, envelope, options)
    assert getattr(out, "status", None) == "refused", getattr(out, "to_json", lambda: out)()
    assert getattr(out, "code", None) == "profile-type"


def test_j6_export_recipe_when_ignored() -> None:
    """An export recipe when is never evaluated (lot4-export)."""
    from bpmn_io.profile._prepare import prepare_export

    refusing_label = {
        "op": "concat",
        "values": [
            {"op": "literal", "value": "v:"},
            {"op": "read", "binding": "self", "path": "/label/text"},
        ],
    }
    for when in ({"op": "false"}, {"op": "present", "value": refusing_label}):
        compiled, envelope, options = _prepare_export_input(recipe_when=when)
        out = prepare_export(compiled, envelope, options)
        message = out.to_json() if callable(getattr(out, "to_json", None)) else out
        assert getattr(out, "status", None) == "ok", message
        payload = getattr(out, "payload", None) or {}
        sources = {row.get("sourceId") for row in payload.get("idMap", [])}
        assert {"A_1", "Task_A", "Task_B"} <= sources, payload.get("idMap")


def test_j6_export_select_refusal_propagates() -> None:
    """A refusing export select keeps its code instead of render-stale."""
    from bpmn_io.profile import (
        compile_profile,
        create_descriptor_context,
        load_profile,
    )
    from tests.profile_commands import harness as _harness

    profile = _neutral_profile()
    for recipe in profile.get("recipes", []):
        if recipe.get("id") == "export-nodes":
            recipe["select"] = {
                "from": "render",
                "via": "reference",
                "property": "name",
                "where": {"op": "true"},
                "order": "id",
            }
    raw = json.dumps(profile).encode("utf-8")
    package = dict(_harness.DEFAULT_DESCRIPTOR_PIN)
    package["descriptorBytes"] = _harness.DEFAULT_DESCRIPTOR_BYTES
    context_result = create_descriptor_context([package])
    assert context_result.status == "ok", context_result.to_json()
    pins = [{"id": package["id"], "version": package["version"], "sha256": package["sha256"]}]
    load_result = load_profile(
        raw,
        schema_bytes=_harness.SCHEMA_BYTES,
        base_bytes=_harness.BASE_BYTES,
        descriptor_pins=pins,
        asset_bag=dict(_harness.METRICS_BAG),
    )
    assert load_result.status == "ok", load_result.to_json()
    compile_result = compile_profile(
        load_result.payload,  # type: ignore[union-attr]
        descriptor_context=context_result.payload,  # type: ignore[union-attr]
        base=copy.deepcopy(_harness.BASE_DOCUMENT),
    )
    assert compile_result.status == "refused"
    assert compile_result.code == "profile-selector-property"  # type: ignore[union-attr]


def _resolve_with_label(label: dict) -> object:
    """Resolve the neutral profile with one task render label (JS-verified)."""
    from bpmn_io.profile import (
        compile_profile,
        complete_envelope,
        create_descriptor_context,
        load_profile,
    )
    from bpmn_io.profile._render import resolve_theme
    from tests.profile_commands import harness as _harness

    raw = (_harness.EXPECTED / "artifacts/profiles/neutral-lot5.json").read_bytes()
    profile = json.loads(raw.decode("utf-8"))
    task = next(n for n in profile.get("notions", []) if n.get("id") == "task")
    binding = next(b for b in task.get("renderBindings", []) if b.get("theme") == "plain")
    binding["label"] = copy.deepcopy(label)
    package = dict(_harness.DEFAULT_DESCRIPTOR_PIN)
    package["descriptorBytes"] = _harness.DEFAULT_DESCRIPTOR_BYTES
    pins = [{"id": package["id"], "version": package["version"], "sha256": package["sha256"]}]
    load_result = load_profile(
        json.dumps(profile).encode("utf-8"),
        schema_bytes=_harness.SCHEMA_BYTES,
        base_bytes=_harness.BASE_BYTES,
        descriptor_pins=pins,
        asset_bag=dict(_harness.METRICS_BAG),
    )
    assert load_result.status == "ok", load_result.to_json()
    context_result = create_descriptor_context([package])
    assert context_result.status == "ok", context_result.to_json()
    compile_result = compile_profile(
        load_result.payload,  # type: ignore[arg-type]
        descriptor_context=context_result.payload,  # type: ignore[arg-type]
        base=copy.deepcopy(_harness.BASE_DOCUMENT),
    )
    assert compile_result.status == "ok", compile_result.to_json()
    compiled = compile_result.payload
    from bpmn_io.profile._ui import compiled_identity

    identity = compiled_identity(compiled)  # type: ignore[arg-type]
    tree = {
        "$type": "bpmn:Definitions",
        "id": "D_1",
        "targetNamespace": "urn:x",
        "rootElements": [
            {
                "$type": "bpmn:Process",
                "id": "P_1",
                "flowElements": [
                    {"$type": "bpmn:Task", "id": "Task_1"},
                    {"$type": "bpmn:Task", "id": "Task_2", "name": "Fixed"},
                ],
            },
        ],
        "diagrams": [
            {
                "$type": "bpmndi:BPMNDiagram",
                "id": "d1",
                "plane": {
                    "$type": "bpmndi:BPMNPlane",
                    "bpmnElement": "P_1",
                    "planeElement": [
                        {
                            "$type": "bpmndi:BPMNShape",
                            "id": "s1",
                            "bpmnElement": "Task_1",
                            "bounds": {"x": 10, "y": 20, "width": 100, "height": 80},
                        },
                        {
                            "$type": "bpmndi:BPMNShape",
                            "id": "s2",
                            "bpmnElement": "Task_2",
                            "bounds": {"x": 150, "y": 20, "width": 100, "height": 80},
                        },
                    ],
                },
            }
        ],
    }
    from bpmn_io.profile._envelope import make_imported_di
    from bpmn_io.profile._layout import compute_layout
    from bpmn_io.profile._render_digest import descriptor_digest

    envelope = complete_envelope(identity, copy.deepcopy(tree), [])
    imported = make_imported_di(tree, descriptor_digest(identity.get("descriptors")))  # type: ignore[arg-type]
    staged = compute_layout(compiled, envelope, [], imported, theme_id="plain")
    assert getattr(staged, "status", None) == "ok", getattr(staged, "to_json", lambda: staged)()
    return resolve_theme(
        compiled,
        envelope,
        staged.payload,  # type: ignore[union-attr]
        "plain",
        {"semantic": [], "occurrence": []},
        {"native": [], "bioc": []},
    )


def test_j6_label_missing_empty_absent_stay_successful() -> None:
    """Missing and empty labels resolve ok; a refusing label refuses (JS)."""
    from bpmn_io.profile import (
        compile_profile,
        complete_envelope,
        create_descriptor_context,
        load_profile,
    )
    from bpmn_io.profile._envelope import make_imported_di
    from bpmn_io.profile._layout import compute_layout
    from bpmn_io.profile._render_digest import descriptor_digest
    from bpmn_io.profile._ui import compiled_identity
    from tests.profile_commands import harness as _harness

    def _compiled(label: dict) -> tuple[object, object, object]:
        raw = (_harness.EXPECTED / "artifacts/profiles/neutral-lot5.json").read_bytes()
        profile = json.loads(raw.decode("utf-8"))
        task = next(n for n in profile.get("notions", []) if n.get("id") == "task")
        binding = next(b for b in task.get("renderBindings", []) if b.get("theme") == "plain")
        binding["label"] = copy.deepcopy(label)
        package = dict(_harness.DEFAULT_DESCRIPTOR_PIN)
        package["descriptorBytes"] = _harness.DEFAULT_DESCRIPTOR_BYTES
        pins = [{"id": package["id"], "version": package["version"], "sha256": package["sha256"]}]
        load_result = load_profile(
            json.dumps(profile).encode("utf-8"),
            schema_bytes=_harness.SCHEMA_BYTES,
            base_bytes=_harness.BASE_BYTES,
            descriptor_pins=pins,
            asset_bag=dict(_harness.METRICS_BAG),
        )
        assert load_result.status == "ok", load_result.to_json()
        context_result = create_descriptor_context([package])
        assert context_result.status == "ok", context_result.to_json()
        compile_result = compile_profile(
            load_result.payload,  # type: ignore[arg-type]
            descriptor_context=context_result.payload,  # type: ignore[arg-type]
            base=copy.deepcopy(_harness.BASE_DOCUMENT),
        )
        assert compile_result.status == "ok", compile_result.to_json()
        compiled = compile_result.payload
        identity = compiled_identity(compiled)  # type: ignore[arg-type]
        tree = {
            "$type": "bpmn:Definitions",
            "id": "D_1",
            "targetNamespace": "urn:x",
            "rootElements": [
                {
                    "$type": "bpmn:Process",
                    "id": "P_1",
                    "flowElements": [
                        {"$type": "bpmn:Task", "id": "Task_1"},
                        {"$type": "bpmn:Task", "id": "Task_2", "name": "Fixed"},
                    ],
                },
            ],
            "diagrams": [
                {
                    "$type": "bpmndi:BPMNDiagram",
                    "id": "d1",
                    "plane": {
                        "$type": "bpmndi:BPMNPlane",
                        "bpmnElement": "P_1",
                        "planeElement": [
                            {
                                "$type": "bpmndi:BPMNShape",
                                "id": "s1",
                                "bpmnElement": "Task_1",
                                "bounds": {"x": 10, "y": 20, "width": 100, "height": 80},
                            },
                            {
                                "$type": "bpmndi:BPMNShape",
                                "id": "s2",
                                "bpmnElement": "Task_2",
                                "bounds": {"x": 150, "y": 20, "width": 100, "height": 80},
                            },
                        ],
                    },
                }
            ],
        }
        envelope = complete_envelope(identity, copy.deepcopy(tree), [])
        imported = make_imported_di(tree, descriptor_digest(identity.get("descriptors")))  # type: ignore[arg-type]
        return compiled, envelope, imported

    missing = {"op": "read", "binding": "self", "path": "/name"}
    out = _resolve_with_label(missing)
    assert getattr(out, "status", None) == "ok", getattr(out, "to_json", lambda: out)()
    out = _resolve_with_label({"op": "literal", "value": ""})
    assert getattr(out, "status", None) == "ok", getattr(out, "to_json", lambda: out)()
    compiled, envelope, imported = _compiled(copy.deepcopy(_REFUSING_VALUE))
    refused = compute_layout(compiled, envelope, [], imported, theme_id="plain")
    assert getattr(refused, "status", None) == "refused", getattr(
        refused, "to_json", lambda: refused
    )()
    assert getattr(refused, "code", None) == "profile-type"
