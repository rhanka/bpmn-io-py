"""Shared lot-4 case harness (test-only, mirrors spec §17.2).

Builds compiled profiles from sealed case files. Imports the public
block-A binding plus the lot-4 public names under test.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from bpmn_io.profile._compiler import compile_profile, create_descriptor_context
from bpmn_io.profile._loader import load_profile
from bpmn_io.profile._render_tokens import registry_from_json

ROOT = Path(__file__).resolve().parents[2]
MECHANISM = ROOT / "contracts" / "profile-mechanism" / "1"
RENDER_ARTIFACTS = ROOT / "tests" / "profile_render" / "expected" / "artifacts"
SCHEMA_BYTES = (MECHANISM / "profile-mechanism-1.schema.json").read_bytes()
REGISTRY_DOC = json.loads((MECHANISM / "neutral-registry.json").read_text(encoding="utf-8"))

Json = Any

PACKAGE_FILES = {
    "neutral-descriptors/1": MECHANISM / "neutral-descriptors.json",
    "neutral-base/1": MECHANISM / "neutral-base.json",
    "neutral-render-descriptors/1": RENDER_ARTIFACTS / "render-descriptors.json",
    "neutral-render-base/1": RENDER_ARTIFACTS / "render-base.json",
}


def apply_patch(document: Json, patch: list[dict]) -> Json:
    """Apply RFC 6902 add/remove/replace operations to a deep copy."""
    result = copy.deepcopy(document)
    for operation in patch:
        parts = str(operation["path"]).lstrip("/").split("/")
        holder = result
        for part in parts[:-1]:
            holder = holder[int(part)] if isinstance(holder, list) else holder[part]
        key = parts[-1]
        kind = operation["op"]
        if isinstance(holder, list):
            if kind == "add":
                holder.insert(len(holder) if key == "-" else int(key), operation.get("value"))
            elif kind == "remove":
                del holder[int(key)]
            else:
                holder[int(key)] = copy.deepcopy(operation.get("value"))
        elif kind in ("add", "replace"):
            holder[key] = copy.deepcopy(operation.get("value"))
        else:
            del holder[key]
    return result


def profile_from_ref(ref: dict) -> dict:
    """Materialize one ``{base, patch}`` profile reference."""
    base = json.loads((MECHANISM / str(ref["base"])).read_text(encoding="utf-8"))
    return apply_patch(base, list(ref.get("patch", [])))


def compile_profile_doc(profile: dict, asset_bag: dict[str, bytes] | str | None = "auto") -> tuple:
    """Load and compile one materialized profile document (returns trio).

    ``asset_bag="auto"`` verifies the pinned metrics bytes; ``None``
    loads with no asset bag (``input.assetBag: "absent"``); a dict is
    used verbatim.
    """
    data = json.dumps(profile).encode("utf-8")
    base_bytes = PACKAGE_FILES[profile["base"]["id"]].read_bytes()
    bag: dict[str, bytes] | None = None
    if asset_bag == "auto":
        bag = {}
        for entry in profile.get("resources", []):
            key = entry.get("assetKey") if isinstance(entry, dict) else None
            if key == "neutral-metrics.json" and key not in bag:
                bag[key] = (MECHANISM / key).read_bytes()
    elif isinstance(asset_bag, dict):
        bag = dict(asset_bag)
    validated = load_profile(
        data,
        schema_bytes=SCHEMA_BYTES,
        descriptor_pins=profile["descriptors"],
        base_bytes=base_bytes,
        asset_bag=bag,
        capabilities=profile["capabilities"],
    )
    if validated.status != "ok":
        return validated, None, profile
    registry_result = registry_from_json(REGISTRY_DOC)
    assert registry_result.status == "ok", registry_result.to_json()
    context_result = create_descriptor_context(
        [
            {**pin, "descriptorBytes": PACKAGE_FILES[pin["id"]].read_bytes()}
            for pin in profile["descriptors"]
        ]
    )
    assert context_result.status == "ok", context_result.to_json()
    base_doc = json.loads(base_bytes.decode("utf-8"))
    compiled = compile_profile(
        validated.payload,  # type: ignore[union-attr]
        registry_result.payload,  # type: ignore[union-attr]
        context_result.payload,  # type: ignore[union-attr]
        base_doc,
    )
    return compiled, profile, validated


def compile_case_profile(ref: dict, asset_bag: dict[str, bytes] | str | None = "auto") -> tuple:
    """Load and compile one ``{base, patch}`` case profile per spec §17.2."""
    return compile_profile_doc(profile_from_ref(ref), asset_bag)


def build_case_envelope(
    compiled: object,
    _profile: dict,
    tree: dict,
    bindings: list,
    identity: dict | None = None,
) -> object:
    """Build one case envelope (identity override honored, spec §17.3)."""
    from bpmn_io.profile._envelope import complete_envelope

    use_identity = identity if identity is not None else compiled.identity  # type: ignore[union-attr]
    return complete_envelope(use_identity, tree, bindings or [])


def build_imported_di(identity: dict, diagrams: list) -> dict:
    """Build one Snapshot/1 importedDi record from case diagrams (spec §17.3)."""
    from bpmn_io.profile._c14n import digest as c14n_digest
    from bpmn_io.profile._render_digest import descriptor_digest

    descriptor_hash = descriptor_digest(identity["descriptors"])  # type: ignore[arg-type]
    return {
        "descriptorDigest": descriptor_hash,
        "diagrams": copy.deepcopy(diagrams),
        "sha256": c14n_digest({"descriptorDigest": descriptor_hash, "diagrams": diagrams}),
    }


def resolve_role_value(item: dict, helper: object) -> Json:
    """Resolve one harness role input (inline JSON or pinned vendored bytes)."""
    if "json" in item:
        return copy.deepcopy(item["json"])
    raw = helper.vendored_bytes(item["vendored"])
    if str(item["vendored"]).endswith(".json"):
        return json.loads(raw.decode("utf-8"))
    return raw


def _strip_one(record: Json, pointer: str) -> bool:
    """Remove one pointer from a record (True when it resolved)."""
    parts = str(pointer).lstrip("/").split("/")
    holder = record
    try:
        for part in parts[:-1]:
            holder = holder[int(part)] if isinstance(holder, list) else holder[part]
        key = parts[-1]
        if isinstance(holder, list):
            del holder[int(key)]
        else:
            del holder[key]
    except (KeyError, IndexError, TypeError, ValueError):
        return False
    return True


def strip_unsealed(record: Json, pointers: list | None) -> Json:
    """Remove UNSEALED pointers from an actual record (each must resolve)."""
    record = copy.deepcopy(record)
    for pointer in pointers or []:
        assert _strip_one(record, pointer), f"UNSEALED pointer must resolve: {pointer}"
    return record


def strip_unsealed_expected(record: Json, pointers: list | None) -> Json:
    """Remove UNSEALED pointers still carried by an expectation record."""
    record = copy.deepcopy(record)
    for pointer in pointers or []:
        _strip_one(record, pointer)
    return record


def check_includes(actual_entries: list, includes: list) -> None:
    """Check every includes partial entry matches an actual report entry."""
    for wanted in includes or []:
        members = wanted.get("entry", wanted)
        found = False
        for entry in actual_entries:
            match = True
            for key, value in members.items():
                if key == "targetId":
                    if entry.get("source", {}).get("targetId") != value:
                        match = False
                        break
                elif entry.get(key) != value:
                    match = False
                    break
            if match:
                found = True
                break
        assert found, f"includes entry not matched: {json.dumps(members)[:300]}"


def check_inputs_unchanged(before: dict, after: dict) -> None:
    """Assert the inputsUnchanged members survived the call byte-identically."""
    from bpmn_io.profile._c14n import jcs as c14n_jcs

    for key, old in before.items():
        assert c14n_jcs(old) == c14n_jcs(after.get(key)), key


def compare_case_result(actual: Json, expected: dict, label: str) -> None:
    """Compare one result record with its sealed expectation (spec §17.4)."""
    expected = copy.deepcopy(expected)
    unsealed = expected.pop("unsealed", None)
    includes = expected.pop("includes", None)
    for member in ("trace", "linkRoute", "structural", "inputsUnchanged"):
        expected.pop(member, None)
    if includes:
        entries = actual.get("report", {}).get("entries", []) if isinstance(actual, dict) else []
        check_includes(entries, includes)
    if unsealed:
        actual = strip_unsealed(actual, unsealed)
        expected = strip_unsealed_expected(expected, unsealed)
    assert actual == expected, label
