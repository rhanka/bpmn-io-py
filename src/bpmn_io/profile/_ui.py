"""Compiled UI/field index and CR-10 compile rules (lot 5).

Covers the section-6 compile rules for UI entries and notion fields that
``compile_profile`` applies between CR-09 and CR-11, plus the compiled
surface/field/message index attached to ``CompiledProfile`` and the
section-5.1 identity derivation the activation path compares.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bpmn_io.profile._c14n import digest, jcs

if TYPE_CHECKING:
    from bpmn_io.profile._compiler import CompiledProfile

__all__ = [
    "ELEMENT_SOURCES",
    "SURFACES",
    "UiIndex",
    "build_ui_index",
    "check_ui_rules",
    "compiled_identity",
    "localize_message",
    "profile_identity_of",
]

#: The eight schema surfaces a UI entry may name.
SURFACES: tuple[str, ...] = (
    "palette",
    "context",
    "append",
    "connect",
    "replace",
    "paste",
    "delete",
    "direct-edit",
)

#: Command context members carrying element handles.
ELEMENT_SOURCES = frozenset({"owner", "target", "source"})

#: Recipe parameter types a submitted value may feed.
_VALUE_TYPES = frozenset({"string", "number", "boolean"})


@dataclass(frozen=True)
class UiIndex:
    """Immutable compiled surface/field/message index (lot 5)."""

    identity: dict[str, object] = field(default_factory=dict)
    entries: tuple[dict[str, object], ...] = ()
    by_id: dict[str, dict[str, object]] = field(default_factory=dict)
    upstream: dict[str, str] = field(default_factory=dict)
    messages: dict[str, dict[str, str]] = field(default_factory=dict)
    fallback: str = ""
    themes: tuple[str, ...] = ()
    glyphs: tuple[str, ...] = ()
    notion_order: tuple[str, ...] = ()
    notion_fields: dict[str, tuple[dict[str, object], ...]] = field(default_factory=dict)


def profile_identity_of(profile: dict[str, object]) -> dict[str, object]:
    """Return the section-5.1 identity record of one profile document."""
    return {
        "mechanismVersion": profile.get("mechanismVersion"),
        "schemaVersion": profile.get("schemaVersion"),
        "profile": profile.get("profile"),
        "version": profile.get("version"),
        "sha256": digest(profile),
        "base": copy.deepcopy(profile.get("base")),
        "descriptors": copy.deepcopy(profile.get("descriptors")),
    }


def compiled_identity(compiled: CompiledProfile) -> dict[str, object]:
    """Return the compiled section-5.1 identity (lot-3 field or UI index)."""
    direct = getattr(compiled, "identity", None)
    if isinstance(direct, dict) and direct:
        return copy.deepcopy(direct)
    index = getattr(compiled, "ui", None)
    if index is not None and isinstance(index.identity, dict) and index.identity:
        return copy.deepcopy(index.identity)
    message = "compiled profile carries no section-5.1 identity"
    raise ValueError(message)


def _recipe_params(recipe: object) -> dict[str, tuple[str, bool]] | None:
    """Return ``{name: (type, required)}`` of one recipe (None when malformed)."""
    if not isinstance(recipe, dict):
        return None
    params: dict[str, tuple[str, bool]] = {}
    declared = recipe.get("parameters")
    if not isinstance(declared, list):
        return None
    for entry in declared:
        if not isinstance(entry, dict):
            return None
        name = entry.get("name")
        if not isinstance(name, str) or name in params:
            return None
        param_type = entry.get("type")
        params[name] = (
            param_type if isinstance(param_type, str) else "unknown",
            entry.get("required") is True,
        )
    return params


def _source_compatible(source: object, param_type: str) -> bool:
    """Return whether a binding source may feed a recipe parameter type."""
    if source in ELEMENT_SOURCES:
        return param_type == "element"
    if source == "value":
        return param_type in _VALUE_TYPES
    return source == "key" and param_type == "string"


def _check_one_binding(
    binding: object,
    params: dict[str, tuple[str, bool]],
    seen: set[str],
) -> str | None:
    """Check one parameter binding against its recipe (refusal or None)."""
    if not isinstance(binding, dict):
        return "profile-ui-parameters"
    name = binding.get("name")
    source = binding.get("source")
    if not isinstance(name, str) or not isinstance(source, str):
        return "profile-ui-parameters"
    if name in seen:
        return "profile-ui-parameters"
    seen.add(name)
    declared = params.get(name)
    if declared is None:
        return "profile-ui-parameters"
    if not _source_compatible(source, declared[0]):
        return "profile-ui-parameters"
    return None


def _check_parameter_map(
    bindings: object,
    params: dict[str, tuple[str, bool]],
) -> str | None:
    """Check one UI/field parameter map against its recipe (refusal or None)."""
    if not isinstance(bindings, list):
        return "profile-ui-parameters"
    seen: set[str] = set()
    for binding in bindings:
        code = _check_one_binding(binding, params, seen)
        if code is not None:
            return code
    for name, (_, required) in params.items():
        if required and name not in seen:
            return "profile-ui-parameters"
    return None


def _ui_entries(profile: dict[str, object]) -> list[dict[str, object]]:
    """Return the UI entry dicts in profile order."""
    ui_entries = profile.get("ui")
    if not isinstance(ui_entries, list):
        return []
    return [entry for entry in ui_entries if isinstance(entry, dict)]


def _notion_fields(profile: dict[str, object]) -> list[dict[str, object]]:
    """Return the notion field dicts in profile declaration order."""
    found: list[dict[str, object]] = []
    notions = profile.get("notions")
    if not isinstance(notions, list):
        return found
    for notion in notions:
        if not isinstance(notion, dict):
            continue
        fields = notion.get("fields")
        if not isinstance(fields, list):
            continue
        found.extend(entry for entry in fields if isinstance(entry, dict))
    return found


def _check_map_against(
    bindings: object, recipe_name: object, recipes: dict[str, dict[str, object]]
) -> str | None:
    """Check one parameter map against its named recipe (refusal or None)."""
    recipe = recipes.get(str(recipe_name))
    if recipe is None:
        return "profile-symbol"
    params = _recipe_params(recipe)
    if params is None:
        return "profile-ui-parameters"
    return _check_parameter_map(bindings, params)


def _check_item1(
    entries: list[dict[str, object]],
    fields: list[dict[str, object]],
    recipes: dict[str, dict[str, object]],
) -> str | None:
    """Check parameter maps of entries and commanded fields (item 1)."""
    for entry in entries:
        code = _check_map_against(entry.get("parameters"), entry.get("recipe"), recipes)
        if code is not None:
            return code
    for field_entry in fields:
        if field_entry.get("command") is None:
            continue
        code = _check_map_against(
            field_entry.get("parameters"), field_entry.get("command"), recipes
        )
        if code is not None:
            return code
    return None


def _check_item2(fields: list[dict[str, object]]) -> str | None:
    """Check enum choice value uniqueness as JSON (item 2)."""
    for field_entry in fields:
        choices = field_entry.get("choices")
        if not isinstance(choices, list):
            continue
        seen_values: set[str] = set()
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            wire = jcs(choice.get("value"))
            if wire in seen_values:
                return "profile-ui-parameters"
            seen_values.add(wire)
    return None


def _check_item3(entries: list[dict[str, object]]) -> str | None:
    """Check upstream IDs map at most once (item 3)."""
    seen_upstream: set[str] = set()
    for entry in entries:
        upstream = entry.get("upstreamEntries")
        if not isinstance(upstream, list):
            continue
        for name in upstream:
            if not isinstance(name, str):
                continue
            if name in seen_upstream:
                return "profile-symbol"
            seen_upstream.add(name)
    return None


def _check_item4(profile: dict[str, object]) -> str | None:
    """Check every message carries the fallback-locale text (item 4)."""
    policies = profile.get("policies")
    fallback = policies.get("localeFallback") if isinstance(policies, dict) else None
    if not isinstance(fallback, str) or not fallback:
        return None
    messages = profile.get("messages")
    if not isinstance(messages, list):
        return None
    for message in messages:
        if not isinstance(message, dict):
            continue
        texts = message.get("texts")
        names = (
            {
                text.get("name")
                for text in texts
                if isinstance(text, dict) and isinstance(text.get("name"), str)
            }
            if isinstance(texts, list)
            else set()
        )
        if fallback not in names:
            return "profile-symbol"
    return None


def _message_ids(profile: dict[str, object]) -> set[str]:
    """Return the declared message IDs of one profile."""
    messages = profile.get("messages")
    if not isinstance(messages, list):
        return set()
    return {
        str(message.get("id"))
        for message in messages
        if isinstance(message, dict) and isinstance(message.get("id"), str)
    }


def _theme_glyph_ids(profile: dict[str, object]) -> tuple[set[str], set[str]]:
    """Return the theme IDs and glyph IDs of one profile."""
    theme_ids: set[str] = set()
    glyph_ids: set[str] = set()
    themes = profile.get("themes")
    if not isinstance(themes, list):
        return theme_ids, glyph_ids
    for theme in themes:
        if not isinstance(theme, dict):
            continue
        theme_id = theme.get("id")
        if isinstance(theme_id, str):
            theme_ids.add(theme_id)
        glyphs = theme.get("glyphs")
        if isinstance(glyphs, list):
            for glyph in glyphs:
                if isinstance(glyph, dict) and isinstance(glyph.get("id"), str):
                    glyph_ids.add(str(glyph.get("id")))
    return theme_ids, glyph_ids


def _check_entry_symbols(
    entry: dict[str, object],
    message_ids: set[str],
    theme_ids: set[str],
    glyph_ids: set[str],
    recipes: dict[str, dict[str, object]],
) -> str | None:
    """Check one UI entry label, icon and recipe exist (item 5)."""
    if entry.get("label") not in message_ids:
        return "profile-symbol"
    icon = entry.get("icon")
    if not isinstance(icon, dict):
        return "profile-symbol"
    if icon.get("theme") not in theme_ids:
        return "profile-symbol"
    if icon.get("glyph") not in glyph_ids:
        return "profile-symbol"
    if entry.get("recipe") not in recipes:
        return "profile-symbol"
    return None


def _check_field_symbols(
    field_entry: dict[str, object],
    message_ids: set[str],
    recipes: dict[str, dict[str, object]],
) -> str | None:
    """Check one field label, message and command exist (item 5)."""
    if field_entry.get("label") not in message_ids:
        return "profile-symbol"
    if field_entry.get("message") not in message_ids:
        return "profile-symbol"
    command = field_entry.get("command")
    if command is not None and command not in recipes:
        return "profile-symbol"
    return None


def _check_item5(
    entries: list[dict[str, object]],
    fields: list[dict[str, object]],
    symbols: tuple[set[str], set[str], set[str], dict[str, dict[str, object]]],
) -> str | None:
    """Check labels, icons and recipes exist (item 5)."""
    message_ids, theme_ids, glyph_ids, recipes = symbols
    for entry in entries:
        code = _check_entry_symbols(entry, message_ids, theme_ids, glyph_ids, recipes)
        if code is not None:
            return code
    for field_entry in fields:
        code = _check_field_symbols(field_entry, message_ids, recipes)
        if code is not None:
            return code
    return None


def check_ui_rules(
    profile: dict[str, object],
    recipes: dict[str, dict[str, object]],
) -> str | None:
    """Apply the section-6 CR-10 rules in order (refusal code or None)."""
    entries = _ui_entries(profile)
    fields = _notion_fields(profile)
    theme_ids, glyph_ids = _theme_glyph_ids(profile)
    symbols = (_message_ids(profile), theme_ids, glyph_ids, recipes)
    for code in (
        _check_item1(entries, fields, recipes),
        _check_item2(fields),
        _check_item3(entries),
        _check_item4(profile),
        _check_item5(entries, fields, symbols),
    ):
        if code is not None:
            return code
    return None


def _index_messages(profile: dict[str, object]) -> dict[str, dict[str, str]]:
    """Index message texts by ID and locale name."""
    messages: dict[str, dict[str, str]] = {}
    raw_messages = profile.get("messages")
    if not isinstance(raw_messages, list):
        return messages
    for message in raw_messages:
        if not isinstance(message, dict) or not isinstance(message.get("id"), str):
            continue
        texts = message.get("texts")
        table: dict[str, str] = {}
        if isinstance(texts, list):
            for text in texts:
                if (
                    isinstance(text, dict)
                    and isinstance(text.get("name"), str)
                    and isinstance(text.get("value"), str)
                    and text["name"] not in table
                ):
                    table[str(text["name"])] = str(text["value"])
        messages[str(message["id"])] = table
    return messages


def _index_themes(profile: dict[str, object]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Index theme IDs and glyph IDs in profile order."""
    theme_ids: list[str] = []
    glyph_ids: list[str] = []
    raw_themes = profile.get("themes")
    if not isinstance(raw_themes, list):
        return (), ()
    for theme in raw_themes:
        if not isinstance(theme, dict) or not isinstance(theme.get("id"), str):
            continue
        theme_ids.append(str(theme["id"]))
        glyphs = theme.get("glyphs")
        if isinstance(glyphs, list):
            for glyph in glyphs:
                if (
                    isinstance(glyph, dict)
                    and isinstance(glyph.get("id"), str)
                    and glyph["id"] not in glyph_ids
                ):
                    glyph_ids.append(str(glyph["id"]))
    return tuple(theme_ids), tuple(glyph_ids)


def _index_notions(
    profile: dict[str, object],
) -> tuple[tuple[str, ...], dict[str, tuple[dict[str, object], ...]]]:
    """Index notion order and field records in declaration order."""
    notion_order: list[str] = []
    notion_fields: dict[str, tuple[dict[str, object], ...]] = {}
    raw_notions = profile.get("notions")
    if not isinstance(raw_notions, list):
        return (), {}
    for notion in raw_notions:
        if not isinstance(notion, dict) or not isinstance(notion.get("id"), str):
            continue
        notion_id = str(notion["id"])
        notion_order.append(notion_id)
        raw_fields = notion.get("fields")
        notion_fields[notion_id] = (
            tuple(copy.deepcopy(entry) for entry in raw_fields if isinstance(entry, dict))
            if isinstance(raw_fields, list)
            else ()
        )
    return tuple(notion_order), notion_fields


def build_ui_index(profile: dict[str, object]) -> UiIndex:
    """Build the immutable surface/field/message index of one profile."""
    raw_ui = profile.get("ui", [])
    entries = (
        tuple(copy.deepcopy(entry) for entry in raw_ui if isinstance(entry, dict))
        if isinstance(raw_ui, list)
        else ()
    )
    by_id = {str(entry.get("id")): entry for entry in entries}
    upstream: dict[str, str] = {}
    for entry in entries:
        names = entry.get("upstreamEntries")
        if isinstance(names, list):
            for name in names:
                if isinstance(name, str) and name not in upstream:
                    upstream[name] = str(entry.get("id"))
    policies = profile.get("policies")
    fallback = ""
    if isinstance(policies, dict) and isinstance(policies.get("localeFallback"), str):
        fallback = str(policies["localeFallback"])
    themes, glyphs = _index_themes(profile)
    notion_order, notion_fields = _index_notions(profile)
    return UiIndex(
        identity=profile_identity_of(profile),
        entries=entries,
        by_id=by_id,
        upstream=upstream,
        messages=_index_messages(profile),
        fallback=fallback,
        themes=themes,
        glyphs=glyphs,
        notion_order=notion_order,
        notion_fields=notion_fields,
    )


def localize_message(
    index: UiIndex,
    key: str,
    locale: str,
) -> tuple[str, str]:
    """Resolve one message key for a locale to ``(text, source)``."""
    table = index.messages.get(key)
    if table is None:
        return key, "key"
    if locale in table:
        return table[locale], "exact"
    if index.fallback and index.fallback in table:
        return table[index.fallback], "fallback"
    return key, "key"
