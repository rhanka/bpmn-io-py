"""Synthetic CR-10 unit tests (no lot-3 dependency).

The sealed neutral-based compile cases cannot reach CR-10 until the lot-3
B-fixes land (``count`` reads ``selector`` instead of ``select``), so each
section-6 rule is verified here against small profiles that need no lot-3
behaviour. These stay green after the merge.
"""

from __future__ import annotations

from bpmn_io.profile._ui import build_ui_index, check_ui_rules, localize_message


def _recipe(
    rid: str,
    params: list[tuple[str, str, bool]] | None = None,
) -> dict[str, object]:
    return {
        "id": rid,
        "phase": "create",
        "parameters": [
            {"name": name, "type": ptype, "required": required}
            for name, ptype, required in (params or [])
        ],
        "select": {"from": "owner", "via": "self", "order": "id"},
        "when": {"op": "true"},
        "steps": [{"op": "bind", "as": "x"}],
        "writes": [],
    }


def _profile(
    ui: list[dict[str, object]] | None = None,
    notions: list[dict[str, object]] | None = None,
    messages: list[dict[str, object]] | None = None,
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    recipes = {
        "make-task": _recipe(
            "make-task",
            [("owner", "element", True), ("key", "string", True), ("name", "string", True)],
        ),
        "rename": _recipe("rename", [("target", "element", True), ("name", "string", True)]),
    }
    profile = {
        "mechanismVersion": "1",
        "schemaVersion": "1.0.0",
        "profile": "synthetic/1",
        "version": "0.0.1",
        "base": {"id": "b", "version": "v", "sha256": "0" * 64},
        "descriptors": [],
        "policies": {"localeFallback": "en"},
        "messages": messages
        if messages is not None
        else [
            {"id": "label", "texts": [{"name": "en", "value": "Task"}]},
            {"id": "invalid", "texts": [{"name": "en", "value": "Bad."}]},
        ],
        "themes": [
            {"id": "plain", "glyphs": [{"id": "task", "kind": "native"}]},
        ],
        "ui": ui
        if ui is not None
        else [
            {
                "id": "task-create",
                "surface": "palette",
                "label": "label",
                "when": {"op": "true"},
                "recipe": "make-task",
                "group": "basic",
                "order": 0,
                "upstreamEntries": ["create.task"],
                "parameters": [
                    {"name": "owner", "source": "owner"},
                    {"name": "key", "source": "key"},
                    {"name": "name", "source": "value"},
                ],
                "icon": {"theme": "plain", "glyph": "task"},
            }
        ],
        "notions": notions
        if notions is not None
        else [
            {
                "id": "task",
                "nativeTypes": ["bpmn:Task"],
                "recognition": {"op": "true"},
                "fields": [
                    {
                        "id": "name",
                        "path": "/name",
                        "widget": "text",
                        "label": "label",
                        "message": "invalid",
                        "visible": {"op": "true"},
                        "mutable": {"op": "true"},
                        "command": "rename",
                        "parameters": [
                            {"name": "target", "source": "target"},
                            {"name": "name", "source": "value"},
                        ],
                        "choices": [],
                        "targetTypes": [],
                    }
                ],
            }
        ],
    }
    return profile, recipes


def test_ok_profile_passes() -> None:
    """A clean profile passes every CR-10 item."""
    profile, recipes = _profile()
    assert check_ui_rules(profile, recipes) is None
    index = build_ui_index(profile)
    assert index.by_id["task-create"]["recipe"] == "make-task"
    assert index.upstream == {"create.task": "task-create"}
    assert index.notion_order == ("task",)
    assert localize_message(index, "label", "fr") == ("Task", "fallback")


def test_duplicate_parameter_name() -> None:
    """One entry map binding a parameter twice refuses."""
    profile, recipes = _profile()
    ui = profile["ui"]
    assert isinstance(ui, list)
    first = ui[0]
    assert isinstance(first, dict)
    first["parameters"] = [
        {"name": "owner", "source": "owner"},
        {"name": "owner", "source": "target"},
        {"name": "key", "source": "key"},
        {"name": "name", "source": "value"},
    ]
    assert check_ui_rules(profile, recipes) == "profile-ui-parameters"


def test_unknown_parameter_name() -> None:
    """A binding naming an undeclared parameter refuses."""
    profile, recipes = _profile()
    ui = profile["ui"]
    assert isinstance(ui, list)
    first = ui[0]
    assert isinstance(first, dict)
    params = first["parameters"]
    assert isinstance(params, list)
    params.append({"name": "ghost", "source": "value"})
    assert check_ui_rules(profile, recipes) == "profile-ui-parameters"


def test_missing_required_parameter() -> None:
    """Omitting a required recipe parameter refuses."""
    profile, recipes = _profile()
    ui = profile["ui"]
    assert isinstance(ui, list)
    first = ui[0]
    assert isinstance(first, dict)
    first["parameters"] = [
        {"name": "owner", "source": "owner"},
        {"name": "key", "source": "key"},
    ]
    assert check_ui_rules(profile, recipes) == "profile-ui-parameters"


def test_source_type_mismatch() -> None:
    """An element parameter bound from a value source is ill-typed (CR-10)."""
    profile, recipes = _profile()
    ui = profile["ui"]
    assert isinstance(ui, list)
    first = ui[0]
    assert isinstance(first, dict)
    first["parameters"] = [
        {"name": "owner", "source": "value"},
        {"name": "key", "source": "key"},
        {"name": "name", "source": "value"},
    ]
    assert check_ui_rules(profile, recipes) == "profile-type"


def test_field_parameter_gap() -> None:
    """A field map missing a required parameter refuses."""
    profile, recipes = _profile()
    notions = profile["notions"]
    assert isinstance(notions, list)
    notion = notions[0]
    assert isinstance(notion, dict)
    fields = notion["fields"]
    assert isinstance(fields, list)
    field_entry = fields[0]
    assert isinstance(field_entry, dict)
    field_entry["parameters"] = [{"name": "target", "source": "target"}]
    assert check_ui_rules(profile, recipes) == "profile-ui-parameters"


def test_enum_duplicate_values() -> None:
    """Two enum choices sharing a JSON value are ill-typed, names aside (CR-10)."""
    profile, recipes = _profile()
    notions = profile["notions"]
    assert isinstance(notions, list)
    notion = notions[0]
    assert isinstance(notion, dict)
    notion["fields"] = [
        {
            "id": "direction",
            "path": "/associationDirection",
            "widget": "enum",
            "label": "label",
            "message": "invalid",
            "visible": {"op": "true"},
            "mutable": {"op": "true"},
            "command": "rename",
            "parameters": [
                {"name": "target", "source": "target"},
                {"name": "name", "source": "value"},
            ],
            "choices": [
                {"name": "one", "value": "One"},
                {"name": "uno", "value": "One"},
            ],
            "targetTypes": [],
        }
    ]
    assert check_ui_rules(profile, recipes) == "profile-type"


def test_upstream_duplicate_across_entries() -> None:
    """One upstream ID mapped by two entries refuses."""
    profile, recipes = _profile()
    ui = profile["ui"]
    assert isinstance(ui, list)
    twin = dict(ui[0])
    assert isinstance(twin, dict)
    twin["id"] = "task-create-2"
    ui.append(twin)
    assert check_ui_rules(profile, recipes) == "profile-symbol"


def test_upstream_duplicate_within_entry() -> None:
    """One upstream ID listed twice by one entry refuses."""
    profile, recipes = _profile()
    ui = profile["ui"]
    assert isinstance(ui, list)
    first = ui[0]
    assert isinstance(first, dict)
    first["upstreamEntries"] = ["create.task", "create.task"]
    assert check_ui_rules(profile, recipes) == "profile-symbol"


def test_message_missing_fallback() -> None:
    """A message without the fallback-locale text refuses."""
    profile, recipes = _profile()
    messages = profile["messages"]
    assert isinstance(messages, list)
    messages.append({"id": "label.extra", "texts": [{"name": "fr", "value": "Extra"}]})
    assert check_ui_rules(profile, recipes) == "profile-symbol"


def test_ui_label_unknown_message() -> None:
    """A UI label naming no message refuses."""
    profile, recipes = _profile()
    ui = profile["ui"]
    assert isinstance(ui, list)
    first = ui[0]
    assert isinstance(first, dict)
    first["label"] = "label.unknown"
    assert check_ui_rules(profile, recipes) == "profile-symbol"


def test_ui_icon_unknown_glyph() -> None:
    """A UI icon naming no theme glyph refuses."""
    profile, recipes = _profile()
    ui = profile["ui"]
    assert isinstance(ui, list)
    first = ui[0]
    assert isinstance(first, dict)
    icon = first["icon"]
    assert isinstance(icon, dict)
    icon["glyph"] = "missing-glyph"
    assert check_ui_rules(profile, recipes) == "profile-symbol"


def test_ui_icon_unknown_theme() -> None:
    """A UI icon naming no theme refuses."""
    profile, recipes = _profile()
    ui = profile["ui"]
    assert isinstance(ui, list)
    first = ui[0]
    assert isinstance(first, dict)
    icon = first["icon"]
    assert isinstance(icon, dict)
    icon["theme"] = "nocturne"
    assert check_ui_rules(profile, recipes) == "profile-symbol"


def test_ui_recipe_unknown() -> None:
    """A UI entry naming no recipe refuses."""
    profile, recipes = _profile()
    ui = profile["ui"]
    assert isinstance(ui, list)
    first = ui[0]
    assert isinstance(first, dict)
    first["recipe"] = "no-such-recipe"
    first["parameters"] = []
    assert check_ui_rules(profile, recipes) == "profile-symbol"


def test_source_type_yields_to_missing_key() -> None:
    """A source-type defect plus a missing required parameter refuses ui-parameters."""
    profile, recipes = _profile()
    ui = profile["ui"]
    assert isinstance(ui, list)
    first = ui[0]
    assert isinstance(first, dict)
    first["parameters"] = [
        {"name": "owner", "source": "value"},
        {"name": "name", "source": "value"},
    ]
    assert check_ui_rules(profile, recipes) == "profile-ui-parameters"


def test_source_type_yields_to_duplicate_owner() -> None:
    """A source-type defect plus a duplicated parameter refuses ui-parameters."""
    profile, recipes = _profile()
    ui = profile["ui"]
    assert isinstance(ui, list)
    first = ui[0]
    assert isinstance(first, dict)
    first["parameters"] = [
        {"name": "owner", "source": "value"},
        {"name": "owner", "source": "target"},
        {"name": "key", "source": "key"},
        {"name": "name", "source": "value"},
    ]
    assert check_ui_rules(profile, recipes) == "profile-ui-parameters"


def test_source_type_yields_to_undeclared_ghost() -> None:
    """A source-type defect plus an undeclared parameter refuses ui-parameters."""
    profile, recipes = _profile()
    ui = profile["ui"]
    assert isinstance(ui, list)
    first = ui[0]
    assert isinstance(first, dict)
    first["parameters"] = [
        {"name": "owner", "source": "value"},
        {"name": "key", "source": "key"},
        {"name": "name", "source": "value"},
        {"name": "ghost", "source": "value"},
    ]
    assert check_ui_rules(profile, recipes) == "profile-ui-parameters"


def test_enum_duplicate_beats_missing_field_target() -> None:
    """Duplicate enum values plus a missing field binding refuse profile-type."""
    profile, recipes = _profile()
    notions = profile["notions"]
    assert isinstance(notions, list)
    notion = notions[0]
    assert isinstance(notion, dict)
    notion["fields"] = [
        {
            "id": "direction",
            "path": "/associationDirection",
            "widget": "enum",
            "label": "label",
            "message": "invalid",
            "visible": {"op": "true"},
            "mutable": {"op": "true"},
            "command": "rename",
            "parameters": [{"name": "name", "source": "value"}],
            "choices": [
                {"name": "one", "value": "One"},
                {"name": "uno", "value": "One"},
            ],
            "targetTypes": [],
        }
    ]
    assert check_ui_rules(profile, recipes) == "profile-type"


def test_duplicate_choices_ignored_off_enum_widget() -> None:
    """Choice values of a non-enum field are not checked (JS gates on the enum widget)."""
    profile, recipes = _profile()
    notions = profile["notions"]
    assert isinstance(notions, list)
    notion = notions[0]
    assert isinstance(notion, dict)
    fields = notion["fields"]
    assert isinstance(fields, list)
    field_entry = fields[0]
    assert isinstance(field_entry, dict)
    assert field_entry["widget"] == "text"
    field_entry["choices"] = [
        {"name": "one", "value": "One"},
        {"name": "uno", "value": "One"},
    ]
    assert check_ui_rules(profile, recipes) is None


def test_field_enum_duplicate_beats_ui_missing_key() -> None:
    """A field enum defect plus a UI missing key refuse profile-type (fields first)."""
    profile, recipes = _profile()
    ui = profile["ui"]
    assert isinstance(ui, list)
    first = ui[0]
    assert isinstance(first, dict)
    first["parameters"] = [
        {"name": "owner", "source": "owner"},
        {"name": "name", "source": "value"},
    ]
    notions = profile["notions"]
    assert isinstance(notions, list)
    notion = notions[0]
    assert isinstance(notion, dict)
    notion["fields"] = [
        {
            "id": "direction",
            "path": "/associationDirection",
            "widget": "enum",
            "label": "label",
            "message": "invalid",
            "visible": {"op": "true"},
            "mutable": {"op": "true"},
            "command": "rename",
            "parameters": [
                {"name": "target", "source": "target"},
                {"name": "name", "source": "value"},
            ],
            "choices": [
                {"name": "one", "value": "One"},
                {"name": "uno", "value": "One"},
            ],
            "targetTypes": [],
        }
    ]
    assert check_ui_rules(profile, recipes) == "profile-type"
