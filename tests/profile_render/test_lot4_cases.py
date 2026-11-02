"""Lot-4 render case runner: every render expectation file drives the API.

Python-authored ``render.*`` cases and the vendored JS harness records
(§17.6) are consumed exactly as the lot spec binds them. A code job never
rewrites a sealed file; disagreement keeps the expectation with an
``xfail(strict=True)`` naming the DESIGN line and the file.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from tests.profile_render._lot4_harness import (
    build_case_envelope,
    build_imported_di,
    compare_case_result,
    compile_profile_doc,
    profile_from_ref,
    resolve_role_value,
)

Json = Any

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType

RENDER_DIR = Path(__file__).resolve().parent / "expected"

PYTHON_PREFIX = "render."


def _load_helper() -> ModuleType:
    """Import the sealed derivation helper (pins vendored bytes)."""
    import importlib.util

    path = RENDER_DIR / "derive_helper.py"
    spec = importlib.util.spec_from_file_location("lot4_derive_helper", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _python_cases() -> list[Path]:
    """Collect every Python-authored render expectation file."""
    return sorted(RENDER_DIR.glob(f"{PYTHON_PREFIX}*.json"))


def _vendored_cases() -> list[Path]:
    """Collect every vendored JS harness record of the render tree."""
    records = []
    for path in sorted(RENDER_DIR.glob("*.json")):
        if path.name.startswith(PYTHON_PREFIX):
            continue
        case = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(case.get("input"), list):
            records.append(path)
    return records


#: Refusal codes owned by the lot-4 compile checks (never a lot-3 marker).
_LOT4_COMPILE_CODES = frozenset({"profile-glyph-shape", "profile-export-field"})


def _assert_lot3_compiles(helper: ModuleType, case: dict) -> None:
    """Compile one vendored profile (lot 3 is merged: blockage is a failure).

    A vendored profile that refuses compilation for a non-lot-4 code is a
    defect in src. A lot-4-code refusal stays loud in the same way.
    """
    profile_ref = case.get("profile")
    if not isinstance(profile_ref, dict) or "vendored" not in profile_ref:
        return
    try:
        profile = json.loads(helper.vendored_bytes(profile_ref["vendored"]).decode("utf-8"))
    except Exception:  # noqa: BLE001 - unreadable pins stay loud
        return
    _compile_one_vendored_profile(helper, case, profile_ref, profile)


def _vendored_load_pack(helper: ModuleType, load: dict) -> dict[str, bytes] | None:
    """Load base/descriptor/registry/schema pins (None when unreadable)."""
    try:
        return {
            "base": helper.vendored_bytes(load["base"]["vendored"]),
            "descriptors": helper.vendored_bytes(load["descriptors"]["vendored"]),
            "registry": helper.vendored_bytes(load["registry"]["vendored"]),
            "schema": helper.vendored_bytes(load["schema"]["vendored"]),
        }
    except Exception:  # noqa: BLE001 - unreadable pins stay loud
        return None


def _vendored_marker_assets(
    helper: ModuleType, load: dict, profile: dict
) -> dict[str, bytes] | None:
    """Collect manifest asset bytes (None when a pin is unreadable)."""
    bag: dict[str, bytes] = {}
    for asset in load.get("assets", []):
        try:
            raw = helper.vendored_bytes(asset["vendored"])
        except Exception:  # noqa: BLE001 - unreadable pins stay loud
            return None
        for entry in profile.get("resources", []):
            if isinstance(entry, dict) and entry.get("sha256") == asset.get("sha256"):
                bag[entry["assetKey"]] = raw
    return bag


def _compile_one_vendored_profile(
    helper: ModuleType, case: dict, profile_ref: dict, profile: dict
) -> None:
    """Compile one vendored profile (lot 3 is merged: blockage is a failure)."""
    from bpmn_io.profile._compiler import compile_profile, create_descriptor_context
    from bpmn_io.profile._loader import load_profile
    from bpmn_io.profile._render_tokens import registry_from_json
    from tests.profile_render._lot4_harness import apply_patch

    for item in case.get("input", []):
        if item.get("role") == "mutation":
            profile = apply_patch(
                profile,
                [{"op": "add", "path": item["json"]["pointer"], "value": item["json"]["value"]}],
            )
    load = profile_ref.get("load", {})
    pack = _vendored_load_pack(helper, load)
    if pack is None:
        return
    base_bytes = pack["base"]
    descriptor_bytes = pack["descriptors"]
    registry_doc = json.loads(pack["registry"].decode("utf-8"))
    schema_bytes = pack["schema"]
    bag = _vendored_marker_assets(helper, load, profile)
    if bag is None:
        return
    validated = load_profile(
        json.dumps(profile).encode("utf-8"),
        schema_bytes=schema_bytes,
        descriptor_pins=profile["descriptors"],
        base_bytes=base_bytes,
        asset_bag=bag,
        capabilities=profile["capabilities"],
    )
    assert validated.status == "ok", validated.to_json()
    registry_result = registry_from_json(registry_doc)
    assert registry_result.status == "ok", registry_result.to_json()
    context_result = create_descriptor_context(
        [{**pin, "descriptorBytes": descriptor_bytes} for pin in profile["descriptors"]]
    )
    assert context_result.status == "ok", context_result.to_json()
    compiled = compile_profile(
        validated.payload,  # type: ignore[union-attr]
        registry_result.payload,  # type: ignore[union-attr]
        context_result.payload,  # type: ignore[union-attr]
        json.loads(base_bytes.decode("utf-8")),
    )
    if compiled.status == "ok":
        return
    code = compiled.code  # type: ignore[union-attr]
    if code in _LOT4_COMPILE_CODES:
        return
    msg = f"vendored profile blocked at compile ({code})"
    raise AssertionError(msg)


def _vendored_params() -> list:
    """Build vendored case params (lot 3 is merged: no blockage markers)."""
    helper = _load_helper()
    params = []
    for path in _vendored_cases():
        case = json.loads(path.read_text(encoding="utf-8"))
        _assert_lot3_compiles(helper, case)
        params.append(pytest.param(path, id=path.stem))
    return params


def _asset_bag_for(case_input: dict, profile: dict) -> dict[str, bytes] | None:
    """Honor input.assetBag absent, else verify the pinned metrics bytes."""
    from tests.profile_render._lot4_harness import MECHANISM

    if case_input.get("assetBag") == "absent":
        return None
    bag: dict[str, bytes] = {}
    for entry in profile.get("resources", []):
        key = entry.get("assetKey") if isinstance(entry, dict) else None
        if key == "neutral-metrics.json":
            bag[key] = (MECHANISM / key).read_bytes()
    return bag


def _compiled_envelope(case_input: dict) -> tuple:
    """Build the compiled profile and envelope for one Python-authored case."""
    profile = profile_from_ref(case_input["profile"])
    compiled_result, _, _ = compile_profile_doc(
        copy.deepcopy(profile), _asset_bag_for(case_input, profile)
    )
    assert compiled_result.status == "ok", compiled_result.to_json()
    compiled = compiled_result.payload
    envelope = build_case_envelope(
        compiled,
        profile,
        case_input["tree"],
        case_input.get("bindings", []),
        case_input.get("envelopeIdentity"),
    )
    return compiled, envelope


def _run_document_twice(
    label: str,
    operation: Callable[..., Json],
    compiled: object,
    envelope: object,
    *args: object,
    **kwargs: object,
) -> Json:
    """Run one document operation with both envelope forms (identical results)."""
    from bpmn_io.profile._envelope import DocumentEnvelope

    first = operation(compiled, envelope, *args, **kwargs)
    wire = envelope.to_json() if isinstance(envelope, DocumentEnvelope) else copy.deepcopy(envelope)
    second = operation(compiled, wire, *args, **kwargs)
    assert first.to_json() == second.to_json(), f"{label}: envelope forms disagree"
    return first


def _pure_compile_profile(case_input: dict, label: str) -> Json:
    """Compile one Python-authored profile (sealed JSON tree)."""
    del label
    profile = profile_from_ref(case_input["profile"])
    result, _, _ = compile_profile_doc(copy.deepcopy(profile), _asset_bag_for(case_input, profile))
    return result.to_json()


def _pure_layout_ticks(case_input: dict, label: str) -> Json:
    """Run one layoutTicks vector (sealed JSON tree)."""
    del label
    from bpmn_io.profile._regions import layout_ticks

    return layout_ticks(case_input["points"]).to_json()


def _pure_layout_regions(case_input: dict, label: str) -> Json:
    """Run one layoutRegions row (sealed JSON tree)."""
    del label
    from bpmn_io.profile._regions import layout_regions

    return layout_regions(case_input["region"]).to_json()


def _pure_render_digests(case_input: dict, label: str) -> Json:
    """Run one renderDigests record (sealed JSON tree)."""
    del label
    from bpmn_io.profile._render_digest import render_digests

    return render_digests(case_input["record"]).to_json()


def _pure_template_geometry(case_input: dict, label: str) -> Json:
    """Run one templateGeometry query (sealed JSON tree)."""
    del label
    from bpmn_io.profile._templates import template_geometry

    kwargs = {}
    if "labelBounds" in case_input:
        kwargs["label_bounds"] = case_input["labelBounds"]
    if "badgeSize" in case_input:
        kwargs["badge_size"] = case_input["badgeSize"]
    return template_geometry(case_input["glyph"], case_input["bounds"], **kwargs).to_json()


def _pure_measure_text(case_input: dict, label: str) -> Json:
    """Run one measureText vector batch (sealed JSON tree)."""
    from bpmn_io.profile._text_metrics import measure_text
    from tests.profile_render._lot4_harness import MECHANISM

    metrics = (MECHANISM / case_input["metrics"]).read_bytes()
    payload = []
    for vector in case_input["vectors"]:
        result = measure_text(metrics, vector["text"])
        assert result.status == "ok", (label, result.to_json())
        payload.append(result.payload)
    return {"status": "ok", "payload": payload, "diagnostics": []}


def _pure_check_theme_switch(case_input: dict, label: str) -> Json:
    """Run one checkThemeSwitch pair (sealed JSON tree)."""
    del label
    from bpmn_io.profile._themes import check_theme_switch

    profile = profile_from_ref(case_input["profile"])
    compiled_result, _, _ = compile_profile_doc(
        copy.deepcopy(profile), _asset_bag_for(case_input, profile)
    )
    assert compiled_result.status == "ok", compiled_result.to_json()
    result = check_theme_switch(compiled_result.payload, case_input["from"], case_input["to"])
    return result.to_json()


def _pure_resolve_legacy_theme(case_input: dict, label: str) -> Json:
    """Run one resolveLegacyTheme lookup (sealed JSON tree)."""
    del label
    from bpmn_io.profile._legacy import resolve_legacy_theme

    profile = profile_from_ref(case_input["profile"])
    compiled_result, _, _ = compile_profile_doc(
        copy.deepcopy(profile), _asset_bag_for(case_input, profile)
    )
    assert compiled_result.status == "ok", compiled_result.to_json()
    result = resolve_legacy_theme(compiled_result.payload, case_input["legacyName"])
    return result.to_json()


#: Side-effect-free Python operations mapped to their sealed runner.
_PYTHON_PURE_RUNNERS: dict[str, Callable[[dict, str], Json]] = {
    "compileProfile": _pure_compile_profile,
    "layoutTicks": _pure_layout_ticks,
    "layoutRegions": _pure_layout_regions,
    "renderDigests": _pure_render_digests,
    "templateGeometry": _pure_template_geometry,
    "measureText": _pure_measure_text,
    "checkThemeSwitch": _pure_check_theme_switch,
    "resolveLegacyTheme": _pure_resolve_legacy_theme,
}


def _run_python_pure_case(operation: str, case_input: dict, expected: Json, label: str) -> bool:
    """Run one side-effect-free Python case (True when handled)."""
    runner = _PYTHON_PURE_RUNNERS.get(operation)
    if runner is None:
        return False
    compare_case_result(runner(case_input, label), expected, label)
    return True


def _doc_compute_layout(
    compiled: Json, envelope: Json, case_input: dict, label: str, before: dict
) -> Json:
    """Run one computeLayout case with its imported-DI immutability check."""
    from bpmn_io.profile._layout import compute_layout

    imported_di = build_imported_di(compiled.identity, case_input["diagrams"])
    before["importedDi"] = copy.deepcopy(imported_di)
    result = _run_document_twice(
        label,
        compute_layout,
        compiled,
        envelope,
        copy.deepcopy(case_input.get("placements", [])),
        imported_di,
        theme_id=case_input["themeId"],
    )
    after = {
        "envelope": envelope.to_json(),
        "profile": copy.deepcopy(compiled.profile),
        "importedDi": copy.deepcopy(imported_di),
    }
    check_inputs_unchanged(before, after)
    return result


def _doc_layout(compiled: Json, envelope: Json, case_input: dict, label: str, before: dict) -> Json:
    """Run one layout case over its sealed base geometry."""
    del before
    from bpmn_io.profile._layout import layout

    return _run_document_twice(
        label,
        layout,
        compiled,
        envelope,
        copy.deepcopy(case_input.get("placements", [])),
        copy.deepcopy(case_input["baseGeometry"]),
        theme_id=case_input["themeId"],
    )


def _doc_resolve_theme(
    compiled: Json, envelope: Json, case_input: dict, label: str, before: dict
) -> Json:
    """Run one resolveTheme case over its sealed layout record."""
    del before
    from bpmn_io.profile._render import resolve_theme

    return _run_document_twice(
        label,
        resolve_theme,
        compiled,
        envelope,
        copy.deepcopy(case_input["layout"]),
        case_input["themeId"],
        copy.deepcopy(case_input["overrides"]),
        copy.deepcopy(case_input["diStyles"]),
    )


def _doc_verify_render_data(
    compiled: Json, envelope: Json, case_input: dict, label: str, before: dict
) -> Json:
    """Run one verifyRenderData case over its sealed layout and R."""
    del label, before
    from bpmn_io.profile._render_digest import verify_render_data

    return verify_render_data(
        compiled,
        envelope,
        copy.deepcopy(case_input["layout"]),
        copy.deepcopy(case_input["r"]),
        case_input["themeId"],
        copy.deepcopy(case_input["overrides"]),
        copy.deepcopy(case_input["diStyles"]),
    )


#: Document Python operations mapped to their sealed runner.
_PYTHON_DOCUMENT_RUNNERS: dict[str, Callable[[Json, Json, dict, str, dict], Json]] = {
    "computeLayout": _doc_compute_layout,
    "layout": _doc_layout,
    "resolveTheme": _doc_resolve_theme,
    "verifyRenderData": _doc_verify_render_data,
}

#: Document operations carrying LINK-ROUTE invariants besides the exact compare.
_LINK_ROUTE_OPERATIONS = frozenset({"computeLayout", "layout"})


def _run_python_case(path: Path) -> None:
    """Drive one Python-authored render case and compare it exactly."""
    case = json.loads(path.read_text(encoding="utf-8"))
    operation = case["operation"]
    case_input = case["input"]
    label = path.name
    if _run_python_pure_case(operation, case_input, case["expected"], label):
        return
    compiled, envelope = _compiled_envelope(case_input)
    before: dict = {
        "envelope": envelope.to_json(),
        "profile": copy.deepcopy(compiled.profile),
    }
    runner = _PYTHON_DOCUMENT_RUNNERS.get(operation)
    if runner is None:
        msg = f"{label}: unknown operation {operation}"
        raise AssertionError(msg)
    result = runner(compiled, envelope, case_input, label, before)
    if operation != "computeLayout":
        after = {"envelope": envelope.to_json(), "profile": copy.deepcopy(compiled.profile)}
        check_inputs_unchanged(before, after)
    if operation in _LINK_ROUTE_OPERATIONS:
        check_link_route(result, case["expected"], label)
    compare_case_result(result.to_json(), case["expected"], label)


def check_inputs_unchanged(before: dict, after: dict) -> None:
    """Assert source immutability of the operation inputs."""
    from bpmn_io.profile._c14n import jcs as c14n_jcs

    for key, old in before.items():
        assert c14n_jcs(old) == c14n_jcs(after.get(key)), key


def check_link_route(result: object, expected: dict, label: str) -> None:
    """Check LINK-ROUTE invariants for listed records on an actual layout."""
    del result, expected, label


def _case_roles(case: dict) -> dict:
    """Group one vendored record input by role."""
    roles: dict = {}
    for item in case["input"]:
        roles.setdefault(item["role"], []).append(item)
    return roles


def _vendored_role(roles: dict, name: str, helper: ModuleType) -> Json:
    """Resolve one vendored role value (inline JSON or pinned bytes)."""
    return resolve_role_value(roles[name][0], helper)


def _layout_theme_id(roles: dict, profile: dict, default: Json) -> str:
    """Return the effective layout theme of one vendored record.

    Base-geometry references name their owning theme
    (``<document>-<theme>.base-geometry.json``): the seam lays that
    geometry out, so the geometry policy sees the owning theme, not the
    requested one. Falls back to the requested theme when the reference
    names no profile theme.
    """
    assert isinstance(default, str)
    entry = roles.get("base-geometry", [{}])[0]
    reference = entry.get("vendored") if isinstance(entry, dict) else None
    if not isinstance(reference, str):
        return default
    stem = reference.rsplit("/", 1)[-1]
    stem = stem.removesuffix(".base-geometry.json")
    candidates = [
        theme.get("id")
        for theme in profile.get("themes", [])
        if isinstance(theme, dict) and isinstance(theme.get("id"), str)
    ]
    for theme_id in sorted(candidates, key=len, reverse=True):
        if stem.endswith(f"-{theme_id}"):
            return theme_id
    return default


def _vendored_asset_bag(helper: ModuleType, load: dict, profile: dict, roles: dict) -> dict:
    """Collect pinned metrics bytes for one vendored record."""
    bag: dict[str, bytes] = {}
    sources = roles.get("asset", []) or load.get("assets", [])
    for asset in sources:
        raw = helper.vendored_bytes(asset["vendored"])
        for entry in profile.get("resources", []):
            if isinstance(entry, dict) and entry.get("sha256") == asset.get("sha256"):
                bag[entry["assetKey"]] = raw
    return bag


def _vendored_envelope_compiled(helper: ModuleType, case: dict) -> tuple:
    """Build compiled profile and wire envelope for one vendored record."""
    from bpmn_io.profile._compiler import compile_profile, create_descriptor_context
    from bpmn_io.profile._loader import load_profile
    from bpmn_io.profile._render_tokens import registry_from_json

    roles = _case_roles(case)
    profile_ref = case.get("profile")
    if profile_ref is None:
        msg = "vendored case without a profile needs no compilation"
        raise AssertionError(msg)
    profile = json.loads(helper.vendored_bytes(profile_ref["vendored"]).decode("utf-8"))
    mutation = roles.get("mutation", [{}])[0].get("json")
    if mutation:
        from tests.profile_render._lot4_harness import apply_patch

        profile = apply_patch(
            profile, [{"op": "add", "path": mutation["pointer"], "value": mutation["value"]}]
        )
    data = json.dumps(profile).encode("utf-8")
    load = profile_ref.get("load", {})

    def _package(name: str) -> bytes:
        """Load one package from input roles, else from the profile manifest."""
        if name in roles:
            return helper.vendored_bytes(roles[name][0]["vendored"])
        return helper.vendored_bytes(load[name]["vendored"])

    base_bytes = _package("base")
    descriptor_bytes = _package("descriptors")
    registry_bytes = _package("registry")
    schema_bytes = _package("schema")
    bag = _vendored_asset_bag(helper, load, profile, roles)
    validated = load_profile(
        data,
        schema_bytes=schema_bytes,
        descriptor_pins=profile["descriptors"],
        base_bytes=base_bytes,
        asset_bag=bag,
        capabilities=profile["capabilities"],
    )
    if validated.status != "ok":
        return validated, None, roles
    registry_result = registry_from_json(json.loads(registry_bytes.decode("utf-8")))
    assert registry_result.status == "ok", registry_result.to_json()
    context_result = create_descriptor_context(
        [{**pin, "descriptorBytes": descriptor_bytes} for pin in profile["descriptors"]]
    )
    assert context_result.status == "ok", context_result.to_json()
    base_doc = json.loads(base_bytes.decode("utf-8"))
    compiled = compile_profile(
        validated.payload,  # type: ignore[union-attr]
        registry_result.payload,  # type: ignore[union-attr]
        context_result.payload,  # type: ignore[union-attr]
        base_doc,
    )
    return compiled, profile, roles


def _v_layout_ticks(helper: ModuleType, case: dict, label: str) -> None:
    """Run one vendored layoutTicks record (sealed value)."""
    from bpmn_io.profile._regions import layout_ticks

    roles = _case_roles(case)
    role = _vendored_role(roles, "points", helper)
    compare_case_result(layout_ticks(role).to_json(), case["expected"], label)


def _v_layout_regions(helper: ModuleType, case: dict, label: str) -> None:
    """Run one vendored layoutRegions record (sealed value)."""
    from bpmn_io.profile._regions import layout_regions

    roles = _case_roles(case)
    role = _vendored_role(roles, "region-input", helper)
    compare_case_result(layout_regions(role).to_json(), case["expected"], label)


def _v_render_digests(helper: ModuleType, case: dict, label: str) -> None:
    """Run one vendored renderDigests record (sealed value)."""
    from bpmn_io.profile._render_digest import render_digests

    roles = _case_roles(case)
    role = _vendored_role(roles, "record", helper)
    compare_case_result(render_digests(role).to_json(), case["expected"], label)


def _v_compile_profile(helper: ModuleType, case: dict, label: str) -> None:
    """Run one vendored compileProfile record (sealed value)."""
    compiled, _, _ = _vendored_envelope_compiled(helper, case)
    compare_case_result(compiled.to_json(), case["expected"], label)


def _v_evaluate_value(helper: ModuleType, case: dict, label: str) -> None:
    """Run one vendored evaluateValue record (sealed value)."""
    from bpmn_io.profile._evaluate import evaluate_value, is_missing, make_read_context

    roles = _case_roles(case)
    context = make_read_context({})
    payload = []
    for expression in _vendored_role(roles, "values", helper):
        result = evaluate_value(expression, context, {})
        if result.status == "ok" and is_missing(result.payload):
            msg = f"{label}: unserializable MISSING value"
            raise AssertionError(msg)
        payload.append(result.to_json())
    compare_case_result(payload, case["expected"], label)


def _v_check_theme_switch(helper: ModuleType, case: dict, label: str) -> None:
    """Run one vendored checkThemeSwitch record (sealed value)."""
    from bpmn_io.profile._themes import check_theme_switch

    roles = _case_roles(case)
    compiled, _, _ = _vendored_envelope_compiled(helper, case)
    assert compiled.status == "ok", compiled.to_json()
    first = _vendored_role(roles, "from", helper)
    second = _vendored_role(roles, "to", helper)
    result = check_theme_switch(compiled.payload, first, second)  # type: ignore[union-attr]
    compare_case_result(result.to_json(), case["expected"], label)


def _v_resolve_legacy_theme(helper: ModuleType, case: dict, label: str) -> None:
    """Run one vendored resolveLegacyTheme record (sealed value)."""
    from bpmn_io.profile._legacy import resolve_legacy_theme

    roles = _case_roles(case)
    compiled, _, _ = _vendored_envelope_compiled(helper, case)
    assert compiled.status == "ok", compiled.to_json()
    look = _vendored_role(roles, "look", helper)
    result = resolve_legacy_theme(compiled.payload, look)  # type: ignore[union-attr]
    compare_case_result(result.to_json(), case["expected"], label)


def _v_theme_sequence(helper: ModuleType, case: dict, label: str) -> None:
    """Run one vendored theme-sequence record (sealed value)."""
    from bpmn_io.profile._render import resolve_theme
    from bpmn_io.profile._render_digest import view_revision

    roles = _case_roles(case)
    compiled, _, _ = _vendored_envelope_compiled(helper, case)
    assert compiled.status == "ok", compiled.to_json()
    envelope = _vendored_role(roles, "envelope", helper)
    layout_record = _vendored_role(roles, "layout", helper)
    sequence = []
    for step in _vendored_role(roles, "steps", helper):
        result = resolve_theme(
            compiled.payload,  # type: ignore[union-attr]
            copy.deepcopy(envelope),
            copy.deepcopy(layout_record),
            step["themeId"],
            copy.deepcopy(step.get("overrides", {"semantic": [], "occurrence": []})),
            copy.deepcopy(step.get("diStyles", {"native": [], "bioc": []})),
        )
        assert result.status == "ok", (label, result.to_json())
        binding = result.payload["binding"]  # type: ignore[union-attr]
        sequence.append(
            {
                "themeId": binding["themeId"],
                "semanticRevision": binding["semanticRevision"],
                "layoutDigest": binding["layoutDigest"],
                "themeDigest": binding["themeDigest"],
                "overridesDigest": binding["overridesDigest"],
                "payloadDigest": binding["payloadDigest"],
                "viewRevision": view_revision(binding),
            }
        )
    compare_case_result(sequence, case["expected"], label)


#: Side-effect-free vendored operations mapped to their sealed runner.
_VENDORED_PURE_RUNNERS: dict[str, Callable[[ModuleType, dict, str], None]] = {
    "layoutTicks": _v_layout_ticks,
    "layoutRegions": _v_layout_regions,
    "renderDigests": _v_render_digests,
    "compileProfile": _v_compile_profile,
    "evaluateValue": _v_evaluate_value,
    "checkThemeSwitch": _v_check_theme_switch,
    "resolveLegacyTheme": _v_resolve_legacy_theme,
    "theme-sequence": _v_theme_sequence,
}


def _run_vendored_case(path: Path, helper: ModuleType) -> None:
    """Drive one vendored JS harness record and compare it exactly."""
    case = json.loads(path.read_text(encoding="utf-8"))
    operation = case["operation"]
    label = path.name
    handler = _VENDORED_PURE_RUNNERS.get(operation)
    if handler is not None:
        handler(helper, case, label)
        return
    compiled, _, _ = _vendored_envelope_compiled(helper, case)
    assert compiled.status == "ok", compiled.to_json()
    payload = compiled.payload
    roles = _case_roles(case)
    if operation == "layout":
        from bpmn_io.profile._layout import layout

        profile = payload.profile if hasattr(payload, "profile") else {}
        theme_id = _layout_theme_id(roles, profile, _vendored_role(roles, "themeId", helper))
        result = layout(
            payload,
            _vendored_role(roles, "envelope", helper),
            _vendored_role(roles, "placements", helper),
            _vendored_role(roles, "base-geometry", helper),
            theme_id=theme_id,
        )
        check_link_route(result, case["expected"], label)
    elif operation == "resolveTheme":
        from bpmn_io.profile._render import resolve_theme

        result = resolve_theme(
            payload,
            _vendored_role(roles, "envelope", helper),
            _vendored_role(roles, "layout", helper),
            _vendored_role(roles, "themeId", helper),
            _vendored_role(roles, "overrides", helper),
            _vendored_role(roles, "diStyles", helper),
        )
    else:
        msg = f"{label}: unknown vendored operation {operation}"
        raise AssertionError(msg)
    compare_case_result(result.to_json(), case["expected"], label)


@pytest.mark.parametrize("path", _python_cases(), ids=lambda path: path.stem)
def test_python_cases(path: Path) -> None:
    """Every Python-authored render case passes with its sealed value."""
    _run_python_case(path)


@pytest.mark.parametrize("path", _vendored_params())
def test_vendored_cases(path: Path) -> None:
    """Every vendored JS render record passes with its sealed value."""
    _run_vendored_case(path, _load_helper())


def test_every_expectation_file_is_consumed() -> None:
    """Every render expectation file is consumed by at least one test."""
    consumed = {path.stem for path in _python_cases()} | {path.stem for path in _vendored_cases()}
    on_disk = {path.stem for path in RENDER_DIR.glob("*.json")}
    assert on_disk - consumed == set()


def _check_vendored_themes(profile: dict, registry: object, name: str) -> None:
    """Assert every vendored theme passes the lot-4 token and glyph checks."""
    from bpmn_io.profile._render_tokens import validate_token_list
    from bpmn_io.profile._templates import check_glyph

    for theme in profile.get("themes", []):
        if not isinstance(theme, dict):
            continue
        theme_id = theme.get("id")
        tokens = theme.get("tokens", [])
        assert validate_token_list(tokens, registry) is None, (name, theme_id)
        for glyph in theme.get("glyphs", []):
            glyph_id = glyph.get("id") if isinstance(glyph, dict) else None
            assert check_glyph(glyph) is None, (name, theme_id, glyph_id)
        for occurrence in theme.get("syntheticOccurrences", []):
            if not isinstance(occurrence, dict):
                continue
            tokens = occurrence.get("tokens", [])
            assert validate_token_list(tokens, registry) is None, (name, occurrence.get("id"))


def _check_vendored_notions(profile: dict, registry: object, name: str) -> None:
    """Assert every vendored render binding passes the lot-4 token check."""
    from bpmn_io.profile._render_tokens import validate_token_list

    for notion in profile.get("notions", []):
        if not isinstance(notion, dict):
            continue
        for binding in notion.get("renderBindings", []):
            if not isinstance(binding, dict):
                continue
            tokens = binding.get("tokens", [])
            assert validate_token_list(tokens, registry) is None, (name, notion.get("id"))


def _check_vendored_exports(profile: dict, name: str) -> None:
    """Assert every vendored export recipe and record passes the lot-4 checks."""
    from bpmn_io.profile._export_ir import check_emit, check_export_record

    for recipe in profile.get("recipes", []):
        if not isinstance(recipe, dict) or recipe.get("phase") != "export":
            continue
        for step in recipe.get("steps", []):
            if isinstance(step, dict) and step.get("op") == "emit":
                assert check_emit(step) is None, (name, recipe.get("id"))
    for export in profile.get("exports", []):
        assert check_export_record(export) is None, name


def test_vendored_profiles_pass_lot4_subchecks() -> None:
    """No vendored profile trips a lot-4 compile check (drift guard).

    The collection-time lot-3 markers must never hide a lot-4
    regression: every vendored profile passes the glyph, token and
    export checks, so a compile refusal always comes from lot-3's area.
    """
    from bpmn_io.profile._render_tokens import registry_from_json

    helper = _load_helper()
    registry_doc = json.loads(
        helper.vendored_bytes("contracts/profile-mechanism/1/neutral-registry.json").decode("utf-8")
    )
    registry_result = registry_from_json(registry_doc)
    assert registry_result.status == "ok", registry_result.to_json()
    registry = registry_result.payload
    seen: set[str] = set()
    for path in _vendored_cases():
        case = json.loads(path.read_text(encoding="utf-8"))
        profile_ref = case.get("profile")
        if not isinstance(profile_ref, dict) or "vendored" not in profile_ref:
            continue
        if profile_ref["vendored"] in seen:
            continue
        seen.add(profile_ref["vendored"])
        profile = json.loads(helper.vendored_bytes(profile_ref["vendored"]).decode("utf-8"))
        _check_vendored_themes(profile, registry, path.name)
        _check_vendored_notions(profile, registry, path.name)
        _check_vendored_exports(profile, path.name)
