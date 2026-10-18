"""Parity tests for the closed schema subset against this package."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CORPUS = ROOT / "contracts" / "profile-parity-corpus" / "1"
MANIFEST = CORPUS / "manifest.json"
LOCK = json.loads((ROOT / "CONTRACTS.lock").read_text(encoding="utf-8"))

Json = dict[str, "Json"] | list["Json"] | str | int | float | bool | None

CLOSED_29 = (
    "$schema",
    "$id",
    "$comment",
    "title",
    "$defs",
    "$ref",
    "type",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "minItems",
    "maxItems",
    "uniqueItems",
    "minLength",
    "pattern",
    "enum",
    "const",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "allOf",
    "anyOf",
    "oneOf",
    "not",
    "if",
    "then",
    "else",
)


def _cases() -> list[tuple[str, Json]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return [
        (rel, json.loads((ROOT / "contracts" / rel).read_text(encoding="utf-8")))
        for rel in sorted(manifest["files"])
    ]


def _artifact_path(entry: Json) -> Path:
    assert isinstance(entry, dict)
    path = ROOT / "contracts" / str(entry["path"])
    assert path.is_file()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == entry["sha256"]
    return path


def _by_role(entries: list[Json], role: str) -> Json:
    matches = [e for e in entries if isinstance(e, dict) and e.get("role") == role]
    assert len(matches) == 1, f"expected exactly one {role!r} artifact"
    return matches[0]


def _roles(inputs: list[Json]) -> set[str]:
    return {str(e["role"]) for e in inputs if isinstance(e, dict) and "role" in e}


def test_schema_mutation_cases() -> None:
    """Full-profile mutation cases validate through this package."""
    from bpmn_io.profile import validate
    from bpmn_io.profile._schema import SchemaRefusal

    schema = json.loads(
        _artifact_path(
            {
                "path": "profile-mechanism/1/profile-mechanism-1.schema.json",
                "sha256": LOCK["files"][
                    "contracts/profile-mechanism/1/profile-mechanism-1.schema.json"
                ],
            }
        ).read_text()
    )
    for rel, case in _cases():
        assert isinstance(case, dict)
        if not str(case["caseId"]).startswith("schema-"):
            continue
        inputs = case["inputArtifacts"]
        assert isinstance(inputs, list)
        if "mutation" not in _roles(inputs):
            continue
        mutation = _by_role(inputs, "mutation")
        assert isinstance(mutation, dict)
        spec = mutation["json"]
        assert isinstance(spec, dict)
        profile = json.loads(_artifact_path(case["profileArtifact"]).read_text())
        pointer = str(spec["pointer"]).split("/")[1:]
        target = profile
        for part in pointer[:-1]:
            target = target[int(part) if part.isdigit() else part]
        target[pointer[-1]] = spec["value"]
        try:
            ok = validate(schema, profile, {})
        except SchemaRefusal:
            ok = False
        if case["expectedStatus"] == "ok":
            assert ok is True, rel
        else:
            assert ok is False, rel


def test_schema_fragment_cases() -> None:
    """Fragment cases validate through this package with fullmatch patterns."""
    from bpmn_io.profile import validate

    for rel, case in _cases():
        assert isinstance(case, dict)
        if not str(case["caseId"]).startswith("schema-"):
            continue
        if str(case["caseId"]) == "schema-keyword-subset":
            continue
        inputs = case["inputArtifacts"]
        assert isinstance(inputs, list)
        if "fragmentSchema" not in _roles(inputs):
            continue
        frag_schema = _by_role(inputs, "fragmentSchema")
        assert isinstance(frag_schema, dict)
        data = _by_role(inputs, "fragmentData")
        assert isinstance(data, dict)
        ok = validate(frag_schema["json"], data["json"], {})
        if case["expectedStatus"] == "ok":
            assert ok is True, rel
        else:
            assert ok is False, rel


def test_schema_registry_cases() -> None:
    """Pinned external references resolve; unknown pins refuse."""
    import pytest

    from bpmn_io.profile import validate
    from bpmn_io.profile._schema import SchemaRefusal

    for rel, case in _cases():
        assert isinstance(case, dict)
        if case["caseId"] not in (
            "schema-external-ref-pinned",
            "schema-external-ref-unknown",
        ):
            continue
        inputs = case["inputArtifacts"]
        assert isinstance(inputs, list)
        schema = json.loads(_artifact_path(_by_role(inputs, "schema")).read_text())
        if case["caseId"] == "schema-external-ref-pinned":
            registry_entry = _by_role(inputs, "registry")
            assert isinstance(registry_entry, dict)
            registry_doc = json.loads(_artifact_path(registry_entry).read_text())
            pinned_id = str(registry_doc.get("$id", ""))
            assert pinned_id != ""
            data = _by_role(inputs, "fragmentData")
            assert isinstance(data, dict)
            assert validate(schema, data["json"], {pinned_id: registry_doc}) is True, rel
            assert case["expectedStatus"] == "ok", rel
        else:
            with pytest.raises(SchemaRefusal) as exc_info:
                validate(schema, {}, {})
            assert exc_info.value.code == "profile-schema-ref", rel
            assert case["expectedStatus"] == "refused:profile-schema-ref", rel


def test_schema_keyword_subset_case() -> None:
    """The closed-subset witness names a keyword outside the 29."""
    import pytest

    from bpmn_io.profile import validate
    from bpmn_io.profile._schema import SchemaRefusal

    for rel, case in _cases():
        assert isinstance(case, dict)
        if str(case["caseId"]) != "schema-keyword-subset":
            continue
        inputs = case["inputArtifacts"]
        assert isinstance(inputs, list)
        frag_schema = _by_role(inputs, "fragmentSchema")
        assert isinstance(frag_schema, dict)
        assert isinstance(frag_schema["json"], dict)
        with pytest.raises(SchemaRefusal) as exc_info:
            validate(frag_schema["json"], "x", {})
        assert exc_info.value.code == "profile-schema-keyword", rel
        verdict = _by_role(case["expectedArtifacts"], "verdict")
        assert isinstance(verdict, dict)
        payload = verdict["json"]
        assert isinstance(payload, dict)
        closed = payload["closedSubset"]
        assert isinstance(closed, dict)
        assert closed["known"] is False, rel
        assert closed["keyword"] not in CLOSED_29, rel
        assert case["expectedStatus"] == "refused:profile-schema-keyword", rel
