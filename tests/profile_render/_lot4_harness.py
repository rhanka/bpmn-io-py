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


def compile_profile_doc(profile: dict, asset_bag: dict[str, bytes] | None = None) -> tuple:
    """Load and compile one materialized profile document (returns trio)."""
    data = json.dumps(profile).encode("utf-8")
    base_bytes = PACKAGE_FILES[profile["base"]["id"]].read_bytes()
    bag = dict(asset_bag) if asset_bag is not None else {}
    for entry in profile.get("resources", []):
        key = entry.get("assetKey") if isinstance(entry, dict) else None
        if key == "neutral-metrics.json" and key not in bag:
            bag[key] = (MECHANISM / key).read_bytes()
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


def compile_case_profile(ref: dict, asset_bag: dict[str, bytes] | None = None) -> tuple:
    """Load and compile one ``{base, patch}`` case profile per spec §17.2."""
    return compile_profile_doc(profile_from_ref(ref), asset_bag)
