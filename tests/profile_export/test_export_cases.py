"""Lot-4 export case runner: every export expectation file drives the API.

Python-authored ``export.*`` cases and the vendored JS harness records
(§17.6) are consumed exactly as the lot spec binds them. A code job never
rewrites a sealed file; disagreement keeps the expectation with an
``xfail(strict=True)`` naming the DESIGN line and the file.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import xml.etree.ElementTree as ET
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

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType

Json = Any

EXPORT_DIR = Path(__file__).resolve().parent / "expected"
RENDER_DIR = Path(__file__).resolve().parent.parent / "profile_render" / "expected"

PYTHON_PREFIX = "export."


def _load_helper() -> ModuleType:
    """Import the sealed derivation helper (pins vendored bytes)."""
    import importlib.util

    path = RENDER_DIR / "derive_helper.py"
    spec = importlib.util.spec_from_file_location("lot4_derive_helper_export", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _python_cases() -> list[Path]:
    """Collect every Python-authored export expectation file."""
    return sorted(EXPORT_DIR.glob(f"{PYTHON_PREFIX}*.json"))


def _vendored_cases() -> list[Path]:
    """Collect every vendored JS harness record of the export tree."""
    records = []
    for path in sorted(EXPORT_DIR.glob("*.json")):
        if path.name.startswith(PYTHON_PREFIX):
            continue
        case = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(case.get("input"), list):
            records.append(path)
    return records


def _python_params() -> list[pytest.ParamSet]:
    """Collect Python cases (lot 3 is merged: no blockage markers)."""
    return [pytest.param(path, id=path.stem) for path in _python_cases()]


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


def _compiled_envelope(case_input: dict) -> tuple[object, object]:
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


def check_inputs_unchanged(before: dict, after: dict) -> None:
    """Assert source immutability of the operation inputs."""
    from bpmn_io.profile._c14n import jcs as c14n_jcs

    for key, old in before.items():
        assert c14n_jcs(old) == c14n_jcs(after.get(key)), key


def _run_document_twice(
    label: str,
    operation: Callable[..., object],
    compiled: object,
    envelope: object,
    *args: object,
    **kwargs: object,
) -> object:
    """Run one document operation with both envelope forms (identical results)."""
    from bpmn_io.profile._envelope import DocumentEnvelope

    first = operation(compiled, envelope, *args, **kwargs)
    wire = envelope.to_json() if isinstance(envelope, DocumentEnvelope) else copy.deepcopy(envelope)
    second = operation(compiled, wire, *args, **kwargs)
    assert first.to_json() == second.to_json(), f"{label}: envelope forms disagree"
    return first


def _snapshot_case_input(case_input: dict) -> dict:
    """Deep-copy one case input for the immutability check."""
    return copy.deepcopy(case_input)


def _run_python_case(path: Path) -> None:
    """Drive one Python-authored export case and compare it exactly."""
    case = json.loads(path.read_text(encoding="utf-8"))
    operation = case["operation"]
    case_input = case["input"]
    label = path.name
    snapshot = _snapshot_case_input(case_input)
    if operation == "compileProfile":
        profile = profile_from_ref(case_input["profile"])
        result, _, _ = compile_profile_doc(
            copy.deepcopy(profile), _asset_bag_for(case_input, profile)
        )
        compare_case_result(result.to_json(), case["expected"], label)
    elif operation == "mapExport":
        _run_python_map(case_input, case, label)
    elif operation == "mapExportSequence":
        _run_python_map_sequence(case_input, case, label)
    elif operation == "serializePrepared":
        _run_python_serialize(case_input, case, label)
    elif operation == "prepareExport":
        _run_python_prepare(case_input, case, label)
    elif operation == "mapLegacyDiagnostics":
        from bpmn_io.profile._legacy import map_legacy_diagnostics

        result = map_legacy_diagnostics(
            copy.deepcopy(case_input["legacy"]),
            copy.deepcopy(case_input["manifest"]),
            source_index=copy.deepcopy(case_input.get("sourceIndex")),
        )
        compare_case_result(result.to_json(), case["expected"], label)
    else:
        msg = f"{label}: unknown operation {operation}"
        raise AssertionError(msg)
    assert copy.deepcopy(case_input) == snapshot, f"{label}: case input mutated"


def _run_python_map(case_input: dict, case: dict, label: str) -> None:
    """Drive one Python-authored mapExport case."""
    from bpmn_io.profile._export import map_export

    compiled, envelope = _compiled_envelope(case_input)
    before = {
        "envelope": envelope.to_json(),
        "profile": copy.deepcopy(compiled.profile),
        "layout": copy.deepcopy(case_input["layout"]),
        "r": copy.deepcopy(case_input["r"]),
    }
    result = _run_document_twice(
        label,
        map_export,
        compiled,
        envelope,
        copy.deepcopy(case_input["layout"]),
        copy.deepcopy(case_input["r"]),
        case_input["format"],
    )
    after = {
        "envelope": envelope.to_json(),
        "profile": copy.deepcopy(compiled.profile),
        "layout": copy.deepcopy(case_input["layout"]),
        "r": copy.deepcopy(case_input["r"]),
    }
    check_inputs_unchanged(before, after)
    compare_case_result(result.to_json(), case["expected"], label)


def _run_python_map_sequence(case_input: dict, case: dict, label: str) -> None:
    """Drive one mapExportSequence case (steps run in order in one process)."""
    from bpmn_io.profile._export import map_export

    steps = []
    for step in case_input["steps"]:
        compiled, envelope = _compiled_envelope(step)
        result = map_export(
            compiled,
            envelope,
            copy.deepcopy(step["layout"]),
            copy.deepcopy(step["r"]),
            step["format"],
        )
        steps.append(result.to_json())
    compare_case_result({"status": "sequence", "steps": steps}, case["expected"], label)


def _run_python_serialize(case_input: dict, case: dict, label: str) -> None:
    """Drive one Python-authored serializePrepared case."""
    from bpmn_io.profile._serialize import serialize_prepared

    prepared = copy.deepcopy(case_input["prepared"])
    writer_options = copy.deepcopy(case_input["writerOptions"])
    before = {"prepared": copy.deepcopy(prepared)}
    result = serialize_prepared(prepared, writer_options)
    check_inputs_unchanged(before, {"prepared": prepared})
    record = result.to_json()
    _check_structural(record, case["expected"], label, prepared, writer_options)
    compare_case_result(record, case["expected"], label)


def _check_structural(
    record: dict, expected: dict, label: str, prepared: dict, writer_options: dict
) -> None:
    """Check the drawio-structure/1 projection on actual serialize bytes."""
    structural = expected.get("structural")
    if not isinstance(structural, dict) or record.get("status") != "ok":
        return
    assert structural.get("comparator") == "drawio-structure/1", label
    payload = record.get("payload", {})
    raw = payload.get("bytes", "")
    data = raw.encode("utf-8") if isinstance(raw, str) else b""
    assert _project_drawio(data) == structural.get("diagrams"), f"{label}: diagrams differ"
    _check_byte_invariants(data, structural.get("byteInvariants", {}), payload, label)
    if structural.get("deterministic"):
        from bpmn_io.profile._serialize import serialize_prepared

        again = serialize_prepared(copy.deepcopy(prepared), copy.deepcopy(writer_options))
        assert again.status == "ok", label
        assert again.payload.get("bytes") == raw, f"{label}: second call differs"  # type: ignore[union-attr]


def _project_drawio(data: bytes) -> list[dict]:
    """Project draw.io bytes to the drawio-structure/1 diagrams list."""
    root = ET.fromstring(data.decode("utf-8"))  # noqa: S314 - parses library output
    diagrams = []
    for diagram in root.iter("diagram"):
        cells = []
        for cell in diagram.iter("mxCell"):
            if cell.get("id") == "layer":
                continue
            projected: dict = {"id": cell.get("id")}
            if cell.get("vertex") == "1":
                projected["kind"] = "vertex"
            elif cell.get("edge") == "1":
                projected["kind"] = "edge"
            parent = cell.get("parent")
            projected["parent"] = "$layer" if parent == "layer" else parent
            if cell.get("value") is not None:
                projected["value"] = cell.get("value")
            if cell.get("source") is not None:
                projected["source"] = cell.get("source")
            if cell.get("target") is not None:
                projected["target"] = cell.get("target")
            cells.append(projected)
        diagrams.append({"id": diagram.get("id"), "name": diagram.get("name"), "cells": cells})
    return diagrams


def _check_byte_invariants(data: bytes, invariants: dict, payload: dict, label: str) -> None:
    """Check the §11 byte invariants on actual serialize bytes."""
    text = data.decode("utf-8")
    assert text, f"{label}: bytes are not UTF-8"
    if "byteOrderMark" in invariants:
        assert data.startswith(b"\xef\xbb\xbf") == invariants["byteOrderMark"], f"{label}: BOM"
    if "carriageReturn" in invariants:
        assert (b"\r" in data) == invariants["carriageReturn"], f"{label}: CR"
    if "compressed" in invariants:
        assert (data[:2] == b"\x1f\x8b") == invariants["compressed"], f"{label}: gzip magic"
    if "pairedEmptyElements" in invariants:
        paired = re.search(r"<([A-Za-z_][\w.:-]*)(\s[^>]*)?></\1>", text)
        assert (paired is not None) == invariants["pairedEmptyElements"], f"{label}: empty pairs"
    if invariants.get("digestIsSha256OfBytes"):
        assert hashlib.sha256(data).hexdigest() == payload.get("digest"), f"{label}: digest"


def _run_python_prepare(case_input: dict, case: dict, label: str) -> None:
    """Drive one Python-authored prepareExport case with an observing trace."""
    from bpmn_io.profile._c14n import jcs as c14n_jcs
    from bpmn_io.profile._prepare import run_pipeline

    profile = profile_from_ref(case_input["profile"])
    compiled_result, _, _ = compile_profile_doc(
        copy.deepcopy(profile), _asset_bag_for(case_input, profile)
    )
    assert compiled_result.status == "ok", compiled_result.to_json()
    compiled = compiled_result.payload
    envelope = build_case_envelope(
        compiled,
        profile,
        copy.deepcopy(case_input["tree"]),
        copy.deepcopy(case_input.get("bindings", [])),
        case_input.get("envelopeIdentity"),
    )
    options = copy.deepcopy(case_input["options"])
    diagrams = options.pop("diagrams", None)
    if diagrams is not None:
        options["importedDi"] = build_imported_di(compiled.identity, diagrams)
    before_envelope = c14n_jcs(envelope.to_json())
    before_profile = c14n_jcs(compiled.profile)
    before_options = c14n_jcs(options)
    trace: list[str] = []
    result = run_pipeline(compiled, envelope, options, observer=trace.append)
    assert c14n_jcs(envelope.to_json()) == before_envelope, f"{label}: envelope mutated"
    assert c14n_jcs(compiled.profile) == before_profile, f"{label}: profile mutated"
    assert c14n_jcs(options) == before_options, f"{label}: options mutated"
    record = result.to_json()
    expected = copy.deepcopy(case["expected"])
    assert trace == expected.get("trace"), f"{label}: trace differs: {trace}"
    assert expected.get("inputsUnchanged") is True, f"{label}: inputsUnchanged not sealed true"
    includes = expected.get("includes")
    if includes:
        from tests.profile_render._lot4_harness import check_includes

        entries = record.get("report", {}).get("entries", [])
        check_includes(entries, includes)
    compare_case_result(record, expected, label)


def _vendored_params() -> list[pytest.ParamSet]:
    """Build vendored case params with lot-3 blockage markers."""
    helper = _load_helper()
    params = []
    for path in _vendored_cases():
        case = json.loads(path.read_text(encoding="utf-8"))
        _assert_lot3_vendored_compiles(helper, case)
        params.append(pytest.param(path, id=path.stem))
    return params


def _assert_lot3_vendored_compiles(helper: ModuleType, case: dict) -> None:
    """Compile the vendored profile of an export case (lot 3 is merged)."""
    from tests.profile_render.test_lot4_cases import _assert_lot3_compiles

    operation = case.get("operation")
    if operation in ("mapExport", "compileProfile"):
        _assert_lot3_compiles(helper, case)


def _run_vendored_case(path: Path, helper: ModuleType) -> None:
    """Drive one vendored JS harness record and compare it exactly."""
    case = json.loads(path.read_text(encoding="utf-8"))
    operation = case["operation"]
    label = path.name
    roles: dict[str, list] = {}
    for item in case["input"]:
        roles.setdefault(item["role"], []).append(item)

    def _role(name: str) -> Json:
        """Resolve one role value (inline JSON or pinned vendored bytes)."""
        return resolve_role_value(roles[name][0], helper)

    if operation == "compileProfile":
        from tests.profile_render.test_lot4_cases import (
            _vendored_envelope_compiled as _compile_case,
        )

        compiled, _, _ = _compile_case(helper, case)
        compare_case_result(compiled.to_json(), case["expected"], label)
        return
    if operation == "exportIdPlan":
        from bpmn_io.profile._export_ir import plan_ids

        compare_case_result(plan_ids(_role("plan-input")).to_json(), case["expected"], label)
        return
    if operation == "serializePrepared":
        from bpmn_io.profile._serialize import serialize_prepared

        record = serialize_prepared(_role("prepared"), _role("writerOptions")).to_json()
        compare_case_result(record, case["expected"], label)
        return
    if operation == "serializePrepared-sequence":
        compare_case_result(_run_serialize_sequence(_role), case["expected"], label)
        return
    if operation == "serializeBpmn":
        _run_serialize_bpmn(_role, case["expected"], label)
        return
    if operation == "mapExport":
        from bpmn_io.profile._export import map_export
        from tests.profile_render.test_lot4_cases import _vendored_envelope_compiled

        compiled, _, _ = _vendored_envelope_compiled(helper, case)
        assert compiled.status == "ok", compiled.to_json()
        result = map_export(
            compiled.payload,  # type: ignore[union-attr]
            _role("envelope"),
            _role("layout"),
            _role("render"),
            _role("format"),
        )
        compare_case_result(result.to_json(), case["expected"], label)
        return
    msg = f"{label}: unknown vendored operation {operation}"
    raise AssertionError(msg)


def _run_serialize_sequence(role: Callable[[str], Json]) -> dict:
    """Serialize prepared-a/b in the listed call order and compare repetitions."""
    from bpmn_io.profile._serialize import serialize_prepared

    prepared = {"a": role("prepared-a"), "b": role("prepared-b")}
    writer_options = role("writerOptions")
    outputs: dict[str, list[str]] = {}
    for name in role("order"):
        result = serialize_prepared(copy.deepcopy(prepared[name]), copy.deepcopy(writer_options))
        assert result.status == "ok", (name, result.to_json())
        outputs.setdefault(name, []).append(result.payload["bytes"])  # type: ignore[union-attr]
    same = all(len(set(items)) == 1 for items in outputs.values())
    first = role("order")[0]
    repetitions = outputs.get(first, [])
    aba = len(set(repetitions)) == 1
    return {"sameBytesForSameInput": same, "abaUnchanged": aba}


def _reference_slot_names() -> set[str]:
    """Collect every reference property local name of the default model."""
    from bpmn_io.bpmn_moddle.simple import create_moddle

    names = set()
    for typedef in create_moddle().registry.type_map.values():
        for prop in typedef.get("properties", []):
            if prop.get("isReference"):
                names.add(str(prop.get("name", "")).split(":")[-1])
    return names


def _to_ref_form(tree: dict) -> dict:
    """Rewrite bare-string JS-twin references to ``{"$ref": id}`` form."""
    slots = _reference_slot_names()

    def convert(value: Json) -> Json:
        if isinstance(value, dict):
            out = {}
            for key, item in value.items():
                if key in slots and isinstance(item, str):
                    out[key] = {"$ref": item}
                elif (
                    key in slots
                    and isinstance(item, list)
                    and all(isinstance(entry, str) for entry in item)
                ):
                    out[key] = [{"$ref": entry} for entry in item]
                else:
                    out[key] = convert(item)
            return out
        if isinstance(value, list):
            return [convert(item) for item in value]
        return value

    converted = convert(tree)
    assert isinstance(converted, dict)
    return converted


def _run_serialize_bpmn(role: Callable[[str], Json], queries: list[dict], label: str) -> list[dict]:
    """Check every bpmn-structure/1 query entry against actual serialize bytes.

    The sealed expectation is a query list, not a projection: each entry
    selects elements of the actual output and constrains them. The queries
    themselves are returned after every check passes so the exact comparison
    holds.
    """
    from bpmn_io.codec.json import hydrate
    from bpmn_io.codec.serialize import serialize_xml

    envelope = role("envelope")
    writer_options = role("writerOptions")
    hydrated = hydrate(_to_ref_form(copy.deepcopy(envelope["tree"])))
    assert hydrated.ok, [d.to_json() for d in hydrated.diagnostics]
    serialized = serialize_xml(
        hydrated.value,
        format=bool(writer_options.get("format", False)),
        preamble=bool(writer_options.get("preamble", True)),
    )
    assert serialized.ok, [d.to_json() for d in serialized.diagnostics]
    value = serialized.value
    data = value if isinstance(value, bytes) else str(value).encode("utf-8")
    root = ET.fromstring(data.decode("utf-8"))  # noqa: S314 - parses library output
    elements = [child for child in root.iter() if child is not root]
    for entry in queries:
        check_bpmn_entry(entry, elements, root, label)
    return queries


def _local(tag: str) -> str:
    """Strip the namespace of one XML tag or attribute name."""
    return tag.split("}", 1)[-1].rsplit(":", 1)[-1]


def _parent_name(element: ET.Element, root: ET.Element) -> str:
    """Render one parent descriptor (``local:id`` off-root, bare local name on)."""
    by_child = {child: parent for parent in root.iter() for child in parent}
    parent = by_child.get(element)
    assert parent is not None
    if parent is root:
        return _local(parent.tag)
    parent_id = parent.get("id")
    if parent_id:
        return f"{_local(parent.tag)}:{parent_id}"
    return _local(parent.tag)


def _owner_name(element: ET.Element, root: ET.Element) -> str:
    """Render the nearest process/collaboration ancestor descriptor."""
    by_child = {child: parent for parent in root.iter() for child in parent}
    current = by_child.get(element)
    while current is not None and current is not root:
        if _local(current.tag) in ("process", "collaboration", "choreography"):
            identifier = current.get("id", "")
            return f"{_local(current.tag)}:{identifier}"
        current = by_child.get(current)
    msg = "element without a process owner"
    raise AssertionError(msg)


def check_bpmn_entry(entry: dict, elements: list[ET.Element], root: ET.Element, label: str) -> None:
    """Check one bpmn-structure/1 query entry against the parsed elements."""
    matched = [el for el in elements if _local(el.tag) == entry["element"]]
    if "id" in entry:
        matched = [el for el in matched if el.get("id") == entry["id"]]
    if "count" in entry:
        assert len(matched) == entry["count"], (label, entry)
        return
    assert len(matched) == 1, (label, entry)
    element = matched[0]
    if "parent" in entry:
        assert _parent_name(element, root) == entry["parent"], (label, entry)
    if "owner" in entry:
        assert _owner_name(element, root) == entry["owner"], (label, entry)
    attributes = entry.get("attributes", {})
    for name, value in attributes.items():
        assert element.get(name) == value, (label, entry)
    for name in entry.get("absent", []):
        assert element.get(name) is None, (label, entry)
    for tag, values in entry.get("children", {}).items():
        texts = [(child.text or "").strip() for child in element if _local(child.tag) == tag]
        assert texts == values, (label, entry)


@pytest.mark.parametrize("path", _python_params(), ids=lambda param: param.stem)
def test_python_cases(path: Path) -> None:
    """Every Python-authored export case passes with its sealed value."""
    _run_python_case(path)


@pytest.mark.parametrize("path", _vendored_params())
def test_vendored_cases(path: Path) -> None:
    """Every vendored JS export record passes with its sealed value."""
    _run_vendored_case(path, _load_helper())


def test_every_expectation_file_is_consumed() -> None:
    """Every export expectation file is consumed by at least one test."""
    consumed = {path.stem for path in _python_cases()} | {path.stem for path in _vendored_cases()}
    on_disk = {path.stem for path in EXPORT_DIR.glob("*.json")}
    assert on_disk - consumed == set()
