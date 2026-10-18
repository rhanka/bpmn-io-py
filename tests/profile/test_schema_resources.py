"""Schema review regressions (finding #9).

Expectations come from Ajv 8.17.1 behavior (independent reference under
``tests/oracle/``) and DESIGN R3.3 §2.1/SPEC §1: a ``$ref`` into an external
resource re-anchors nested local references to that resource, and only the
eight pinned patterns form the closed inventory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
MECHANISM = ROOT / "contracts" / "profile-mechanism" / "1"


def _lint_schema() -> object:
    return json.loads((MECHANISM / "compiled-lint-options.schema.json").read_bytes())


def _profile_schema() -> dict[str, object]:
    schema = json.loads((MECHANISM / "profile-mechanism-1.schema.json").read_bytes())
    assert isinstance(schema, dict)
    return schema


def test_external_ref_reanchors_nested_local_refs() -> None:
    """Local refs inside an external resource resolve against that resource."""
    from bpmn_io.profile import validate

    external = {
        "$id": "urn:review:extern/1",
        "$defs": {"thing": {"type": "string"}},
        "type": "object",
        "properties": {"a": {"$ref": "#/$defs/thing"}},
    }
    schema = {"$ref": "urn:review:extern/1#/properties/a"}
    assert validate(schema, "hello", {"urn:review:extern/1": external}) is True


def test_external_ref_still_refuses_unknown_nested_pointer() -> None:
    """A dangling nested pointer inside the external resource still refuses."""
    from bpmn_io.profile import validate
    from bpmn_io.profile._schema import SchemaRefusal

    external = {
        "$id": "urn:review:extern/1",
        "type": "object",
        "properties": {"a": {"$ref": "#/$defs/missing"}},
    }
    schema = {"$ref": "urn:review:extern/1#/properties/a"}
    with pytest.raises(SchemaRefusal) as exc_info:
        validate(schema, "hello", {"urn:review:extern/1": external})
    assert exc_info.value.code == "profile-schema-ref"


def test_compiled_options_with_real_rule_validates() -> None:
    """Options carrying a neutral rule validate against the pinned registry."""
    from bpmn_io.profile import validate

    profile = json.loads((MECHANISM / "neutral-profile.json").read_bytes())
    assert isinstance(profile, dict)
    rules = profile["rules"]
    assert isinstance(rules, list)
    assert rules
    value = {
        "mechanismVersion": "1",
        "profileDigest": "0" * 64,
        "phase": "post-normalize",
        "readinessPolicy": "accept",
        "compiledRules": rules,
        "bindings": [],
        "severityPolicyDigest": "1" * 64,
    }
    registry = {"urn:profile-mechanism:1:profile": _profile_schema()}
    assert validate(_lint_schema(), value, registry) is True


def test_wildcard_pattern_refuses_outside_inventory() -> None:
    """``^.*$`` is not in the closed pattern inventory."""
    from bpmn_io.profile import validate
    from bpmn_io.profile._schema import SchemaRefusal

    with pytest.raises(SchemaRefusal) as exc_info:
        validate({"type": "string", "pattern": "^.*$"}, "anything", {})
    assert exc_info.value.code == "profile-schema-pattern"


def test_inventory_patterns_still_accepted() -> None:
    """Every pinned inventory pattern keeps validating data."""
    from bpmn_io.profile import validate

    vectors = [
        ("^[A-Za-z_][A-Za-z0-9_.:/-]*$", "bpmn:Task", True),
        ("^[A-Za-z_][A-Za-z0-9_.:/-]*$", "9lives", False),
        ("^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$", "1.0.0", True),
        ("^[a-z]{2}(?:-[A-Z]{2})?$", "en", True),
        ("^[0-9a-f]{64}$", "0" * 64, True),
        ("^[A-Za-z_][A-Za-z0-9_]*$", "plain", True),
        ("^(?:/(?:[^~/]|~[01])*)*$", "/a~0b", True),
        (
            "^(?:bpmnlint:recommended|plugin:[A-Za-z_][A-Za-z0-9_.-]*/[A-Za-z_][A-Za-z0-9_.-]*)$",
            "bpmnlint:recommended",
            True,
        ),
        ("^[A-Za-z_][A-Za-z0-9_.:/-]*/[1-9][0-9]*$", "predicates/1", True),
    ]
    for pattern, data, wanted in vectors:
        assert validate({"type": "string", "pattern": pattern}, data, {}) is wanted
