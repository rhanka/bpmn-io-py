"""Compiler review regressions (finding #2).

Each probe builds a profile that must refuse with its closed code: unknown
bindings, unknown descriptor types, cyclic recognition and an empty operator
registry refuse before any success. Descriptor and producer checks run
against the pinned neutral descriptors and base (independent contract
artifacts), never against implementation output.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from bpmn_io.profile._compiler import DescriptorContext
from bpmn_io.profile._loader import ValidatedProfile

ROOT = Path(__file__).resolve().parent.parent.parent
MECHANISM = ROOT / "contracts" / "profile-mechanism" / "1"


def _read(name: str) -> bytes:
    return (MECHANISM / name).read_bytes()


def _neutral_profile() -> dict[str, Any]:
    profile = json.loads(_read("neutral-profile.json").decode("utf-8"))
    assert isinstance(profile, dict)
    return profile


def _load(profile: dict[str, Any]) -> ValidatedProfile:
    from bpmn_io.profile import load_profile

    loaded = load_profile(
        json.dumps(profile).encode("utf-8"),
        schema_bytes=_read("profile-mechanism-1.schema.json"),
    )
    assert loaded.status == "ok", loaded
    assert isinstance(loaded.payload, ValidatedProfile)
    return loaded.payload


def _context() -> DescriptorContext:
    from bpmn_io.profile import create_descriptor_context

    profile = _neutral_profile()
    descriptors = profile["descriptors"]
    assert isinstance(descriptors, list)
    raw = _read("neutral-descriptors.json")
    packages = [{**entry, "descriptorBytes": raw} for entry in descriptors]
    result = create_descriptor_context(packages)  # type: ignore[arg-type]
    assert result.status == "ok", result
    assert isinstance(result.payload, DescriptorContext)
    return result.payload


def _base() -> dict[str, Any]:
    base = json.loads(_read("neutral-base.json").decode("utf-8"))
    assert isinstance(base, dict)
    return base


def test_descriptor_context_populates_type_index() -> None:
    """The pinned descriptors build a non-empty type index with references."""
    context = _context()
    assert context.types
    assert "bpmn:Task" in context.types
    assert "bpmn:Process" in context.types
    assert "sourceRef" in context.types["bpmn:Association"]["references"]


def test_ghost_binding_refuses_symbol() -> None:
    """A predicate naming an undeclared binding refuses with profile-symbol."""
    from bpmn_io.profile import compile_profile

    profile = _neutral_profile()
    rules = profile["rules"]
    assert isinstance(rules, list)
    first = copy.deepcopy(rules[0])
    assert isinstance(first, dict)
    first["assert"] = {"op": "typeIs", "binding": "ghost", "type": "bpmn:Task", "mode": "exact"}
    profile["rules"] = [first]
    compiled = compile_profile(_load(profile))
    assert compiled.status == "refused"
    assert compiled.code == "profile-symbol"  # type: ignore[union-attr]


def test_ghost_selector_source_refuses_symbol() -> None:
    """A selector from an undeclared binding refuses with profile-symbol."""
    from bpmn_io.profile import compile_profile

    profile = _neutral_profile()
    rules = profile["rules"]
    assert isinstance(rules, list)
    first = copy.deepcopy(rules[0])
    assert isinstance(first, dict)
    first["select"] = {"from": "ghost", "via": "self", "where": {"op": "true"}, "order": "id"}
    profile["rules"] = [first]
    compiled = compile_profile(_load(profile))
    assert compiled.status == "refused"
    assert compiled.code == "profile-symbol"  # type: ignore[union-attr]


def test_unknown_descriptor_type_refuses() -> None:
    """A typeIs naming a type outside the descriptor index refuses."""
    from bpmn_io.profile import compile_profile

    profile = _neutral_profile()
    rules = profile["rules"]
    assert isinstance(rules, list)
    first = copy.deepcopy(rules[0])
    assert isinstance(first, dict)
    first["assert"] = {"op": "typeIs", "binding": "self", "type": "bpmn:Ghost", "mode": "exact"}
    profile["rules"] = [first]
    compiled = compile_profile(_load(profile), descriptor_context=_context())
    assert compiled.status == "refused"
    assert compiled.code == "profile-type"  # type: ignore[union-attr]


def test_cyclic_recognition_refuses_cycle() -> None:
    """Mutually recognizing notions refuse with profile-cycle."""
    from bpmn_io.profile import compile_profile

    profile = _neutral_profile()
    notions = profile["notions"]
    assert isinstance(notions, list)
    assert len(notions) >= 2
    first = copy.deepcopy(notions[0])
    second = copy.deepcopy(notions[1])
    assert isinstance(first, dict)
    assert isinstance(second, dict)
    first["recognition"] = {"op": "recognizes", "binding": "self", "notion": second["id"]}
    second["recognition"] = {"op": "recognizes", "binding": "self", "notion": first["id"]}
    profile["notions"] = [first, second]
    compiled = compile_profile(_load(profile))
    assert compiled.status == "refused"
    assert compiled.code == "profile-cycle"  # type: ignore[union-attr]


def test_empty_registry_refuses_capability() -> None:
    """An empty operator registry refuses used operators with profile-capability."""
    from bpmn_io.profile import RegistrySet, compile_profile

    payload = _load(_neutral_profile())
    assert isinstance(payload, ValidatedProfile)
    empty = RegistrySet(capabilities=(), signatures={})
    compiled = compile_profile(payload, registry_set=empty)
    assert compiled.status == "refused"
    assert compiled.code == "profile-capability"  # type: ignore[union-attr]


def test_neutral_compiles_with_context_and_base() -> None:
    """The neutral profile compiles cleanly against its pinned context."""
    from bpmn_io.profile import compile_profile

    compiled = compile_profile(
        _load(_neutral_profile()), descriptor_context=_context(), base=_base()
    )
    assert compiled.status == "ok", compiled


def test_editor_only_completion_write_refuses_producer() -> None:
    """A complete-phase write to an editor-only field refuses profile-producer."""
    from bpmn_io.profile import compile_profile

    base = _base()
    fields = base["fields"]
    assert isinstance(fields, list)
    for field in fields:
        assert isinstance(field, dict)
        if field.get("type") == "bpmn:Process" and field.get("field") == "isExecutable":
            field["producers"] = ["editor"]
    compiled = compile_profile(_load(_neutral_profile()), descriptor_context=_context(), base=base)
    assert compiled.status == "refused"
    assert compiled.code == "profile-producer"  # type: ignore[union-attr]


def test_write_set_mismatch_refuses() -> None:
    """Declared writes must equal the actions' required writes exactly."""
    from bpmn_io.profile import compile_profile

    profile = _neutral_profile()
    recipes = profile["recipes"]
    assert isinstance(recipes, list)
    first = copy.deepcopy(recipes[0])
    assert isinstance(first, dict)
    assert isinstance(first["writes"], list)
    assert first["writes"]
    first["writes"] = first["writes"][1:]
    profile["recipes"] = [first, *recipes[1:]]
    compiled = compile_profile(_load(profile))
    assert compiled.status == "refused"
    assert compiled.code == "profile-write-set"  # type: ignore[union-attr]


def test_unknown_recipe_reference_refuses_symbol() -> None:
    """A notion createRecipe naming no recipe refuses with profile-symbol."""
    from bpmn_io.profile import compile_profile

    profile = _neutral_profile()
    notions = profile["notions"]
    assert isinstance(notions, list)
    assert notions
    first = copy.deepcopy(notions[0])
    assert isinstance(first, dict)
    first["createRecipe"] = "ghost-recipe"
    profile["notions"] = [first, *notions[1:]]
    compiled = compile_profile(_load(profile))
    assert compiled.status == "refused"
    assert compiled.code == "profile-symbol"  # type: ignore[union-attr]


def test_unknown_param_refuses_symbol() -> None:
    """A value naming an undeclared recipe parameter refuses."""
    from bpmn_io.profile import compile_profile

    profile = _neutral_profile()
    recipes = profile["recipes"]
    assert isinstance(recipes, list)
    first = copy.deepcopy(recipes[0])
    assert isinstance(first, dict)
    steps = first["steps"]
    assert isinstance(steps, list)
    assert steps
    create = copy.deepcopy(steps[0])
    assert isinstance(create, dict)
    create["key"] = {"op": "param", "name": "ghostparam"}
    first["steps"] = [create, *steps[1:]]
    profile["recipes"] = [first, *recipes[1:]]
    compiled = compile_profile(_load(profile))
    assert compiled.status == "refused"
    assert compiled.code == "profile-symbol"  # type: ignore[union-attr]
