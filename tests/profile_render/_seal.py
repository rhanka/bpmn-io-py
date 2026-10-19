"""Shared seal-integrity checks for the lot-4 expectation trees.

Imports nothing from ``bpmn_io``: the sealed files are checked against their
manifest, their closed case shape and the standalone derivation helper only.
Vendored JS cases (block-B parity sync) are checked against their pinned raw
source files and the vendored JS seal.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

Json = Any

if TYPE_CHECKING:
    import types

HELPER = Path(__file__).resolve().parent / "expected" / "derive_helper.py"
MANIFEST_NAME = "MANIFEST.sha256"
OWN_PREFIXES = ("render.", "export.")
REQUIRED_KEYS = ("case", "clause", "derivation", "input", "expected", "author")
STATUSES = frozenset({"ok", "refused", "sequence"})
HARNESS_KEYS = frozenset(
    {"unsealed", "inputsUnchanged", "trace", "includes", "linkRoute", "structural"}
)
RESULT_OPERATIONS = frozenset(
    {"computeLayout", "layout", "resolveTheme", "mapExport", "prepareExport", "serializePrepared"}
)
PURE_OPERATIONS = frozenset(
    {
        "renderDigests",
        "verifyRenderData",
        "measureText",
        "templateGeometry",
        "resolveLegacyTheme",
        "layoutRegions",
        "layoutTicks",
        "checkThemeSwitch",
        "mapLegacyDiagnostics",
    }
)
PREPARE_STAGES = (
    "options",
    "compatibility",
    "graph",
    "complete",
    "pre-normalize",
    "normalize",
    "post-normalize",
    "layout",
    "post-layout",
    "release",
    "render",
    "map",
)
_LINE = re.compile(r"^([0-9a-f]{64})  (\S+)$")


def sealed_files(directory: Path) -> list[str]:
    """Every sealed file of one expectation tree, relative and sorted by path."""
    return sorted(
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file() and path.name != MANIFEST_NAME and "__pycache__" not in path.parts
    )


def manifest_entries(directory: Path) -> list[tuple[str, str]]:
    """Parse ``MANIFEST.sha256`` (sha256sum format) into (digest, path) pairs."""
    lines = (directory / MANIFEST_NAME).read_text(encoding="utf-8").splitlines()
    entries = []
    for line in lines:
        match = _LINE.match(line)
        assert match is not None, f"malformed manifest line: {line!r}"
        entries.append((match.group(1), match.group(2)))
    return entries


def check_manifest(directory: Path) -> None:
    """Every sealed file is listed once, in path order, with its exact SHA-256."""
    entries = manifest_entries(directory)
    paths = [path for _, path in entries]
    assert paths == sorted(paths), "manifest is not sorted by path"
    assert paths == sealed_files(directory), "manifest does not list exactly the sealed files"
    for want, path in entries:
        got = hashlib.sha256((directory / path).read_bytes()).hexdigest()
        assert got == want, f"{path}: sealed bytes changed"


def check_helper_imports(path: Path = HELPER) -> None:
    """The derivation helper imports nothing from ``bpmn_io``, directly or dynamically."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        elif isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute)):
            callee = node.func.id if isinstance(node.func, ast.Name) else node.func.attr
            assert callee not in ("__import__", "import_module", "spec_from_file_location"), (
                "derivation helper uses a dynamic import"
            )
            continue
        else:
            continue
        for name in names:
            assert not name.split(".")[0].startswith("bpmn_io"), f"helper imports {name}"
            assert name.split(".")[0] != "tests", f"helper imports {name}"


def load_cases(directory: Path) -> list[tuple[Path, dict[str, Any]]]:
    """Load every Python-authored case file of one tree (sorted by path; artifacts excluded)."""
    return [
        (path, json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(directory.glob("*.json"))
        if path.stem.startswith(OWN_PREFIXES)
    ]


def load_vendored(directory: Path) -> list[tuple[Path, dict[str, Any]]]:
    """Load every harness record of a vendored JS case of one tree (JS case ids)."""
    return [
        (path, json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(directory.glob("*.json"))
        if not path.stem.startswith(OWN_PREFIXES)
    ]


def _check_report(name: str, report: dict[str, Any], operation: str, *, refused: bool) -> None:
    allowed = {
        "reportVersion",
        "operation",
        "sourceIdentity",
        "targetIdentity",
        "inputRevision",
        "outputRevision",
        "entries",
        "rawStandardFindings",
        "idMap",
        "artifacts",
    }
    assert set(report) <= allowed, name
    assert report["reportVersion"] == "2", name
    assert report["operation"] == operation, name
    for key in ("entries", "rawStandardFindings", "idMap", "artifacts"):
        assert isinstance(report[key], list), name
    if refused:
        assert "targetIdentity" not in report, name
        assert "outputRevision" not in report, name
    else:
        for key in ("sourceIdentity", "targetIdentity", "inputRevision", "outputRevision"):
            assert key in report, f"{name}: B4 header member {key}"


def check_result_shape(name: str, operation: str, expected: dict[str, Any]) -> None:
    """A Result/1 expectation is the complete closed wire record plus harness keys."""
    wire = {key: value for key, value in expected.items() if key not in HARNESS_KEYS}
    assert wire["operation"] == operation, name
    if wire["status"] == "ok":
        assert set(wire) == {
            "status",
            "operation",
            "profileIdentity",
            "baseRevision",
            "revision",
            "report",
            "payload",
        }, name
        assert wire["baseRevision"] == wire["revision"], f"{name}: read-only operation"
        _check_report(name, wire["report"], operation, refused=False)
    else:
        assert set(wire) == {
            "status",
            "operation",
            "profileIdentity",
            "baseRevision",
            "code",
            "diagnostics",
            "report",
        }, name
        assert wire["diagnostics"] == wire["report"]["entries"], name
        _check_report(name, wire["report"], operation, refused=True)


def check_case_shapes(directory: Path, prefix: str) -> None:
    """Each case carries the required keys, its file name, the seal author and a closed result."""
    cases = load_cases(directory)
    assert cases, "no sealed case"
    for path, case in cases:
        for key in REQUIRED_KEYS:
            assert key in case, f"{path.name}: missing {key}"
        assert case["author"] == "spec-seal", path.name
        assert case["case"] == path.stem, path.name
        assert case["case"].startswith(prefix), path.name
        assert case["clause"].startswith("DESIGN R3.3 §"), path.name
        assert isinstance(case["derivation"], str), path.name
        assert len(case["derivation"]) > 20, path.name
        operation = case["operation"]
        assert isinstance(operation, str), path.name
        expected = case["expected"]
        assert expected["status"] in STATUSES, path.name
        if expected["status"] == "refused":
            assert isinstance(expected["code"], str), path.name
        if operation in RESULT_OPERATIONS:
            check_result_shape(path.name, operation, expected)
        elif operation in PURE_OPERATIONS:
            wire = {key: value for key, value in expected.items() if key not in HARNESS_KEYS}
            want = (
                {"status", "payload", "diagnostics"}
                if expected["status"] == "ok"
                else {
                    "status",
                    "code",
                    "diagnostics",
                }
            )
            assert set(wire) == want, path.name
        elif operation == "mapExportSequence":
            for step in expected["steps"]:
                check_result_shape(path.name, "mapExport", step)
        else:
            assert operation == "compileProfile", path.name
            check_compile_shape(path.name, expected)
        for key in set(expected) & HARNESS_KEYS:
            check_harness_key(path.name, key, expected[key], expected)


def check_compile_shape(name: str, expected: dict[str, Any]) -> None:
    """A compileProfile result is a PureResult without diagnostic; success UNSEALs /payload."""
    wire = {key: value for key, value in expected.items() if key not in HARNESS_KEYS}
    assert wire["diagnostics"] == [], name
    if wire["status"] == "ok":
        assert set(wire) == {"status", "diagnostics"}, name
        assert expected.get("unsealed") == ["/payload"], name
    else:
        assert set(wire) == {"status", "code", "diagnostics"}, name


def check_harness_key(name: str, key: str, value: Json, expected: dict[str, Any]) -> None:
    """Harness members are closed and internally coherent."""
    if key == "unsealed":
        assert value, name
        for pointer in value:
            assert pointer.split("/")[1] in ("payload", "report", "diagnostics"), name
    elif key == "trace":
        assert list(value) == list(PREPARE_STAGES[: len(value)]), name
        if expected["status"] == "ok":
            assert list(value) == list(PREPARE_STAGES), name
    elif key == "inputsUnchanged":
        assert value is True, name
    elif key == "includes":
        assert value, name
        assert "/report/entries" in expected.get("unsealed", []), name
    elif key == "linkRoute":
        for target in value:
            check_link_route(name, expected["payload"], target)
    elif key == "structural":
        assert value["comparator"] == "drawio-structure/1", name


def check_link_route(name: str, layout: dict[str, Any], target: dict[str, str]) -> None:
    """The informative route of a re-routed link satisfies the LINK-ROUTE invariants."""
    records = {(g["pageId"], g["occurrenceKey"]): g for g in layout["geometry"]}
    edge = records[(target["pageId"], target["occurrenceKey"])]
    points = edge["waypoints"]
    assert len(points) >= 2, name

    def inside(point: dict[str, int], bounds: dict[str, int]) -> bool:
        return (
            bounds["x"] <= point["x"] <= bounds["x"] + bounds["width"]
            and bounds["y"] <= point["y"] <= bounds["y"] + bounds["height"]
        )

    source = records[
        (edge["sourceOccurrence"]["pageId"], edge["sourceOccurrence"]["occurrenceKey"])
    ]
    target_record = records[
        (edge["targetOccurrence"]["pageId"], edge["targetOccurrence"]["occurrenceKey"])
    ]
    assert inside(points[0], source["bounds"]), name
    assert inside(points[-1], target_record["bounds"]), name
    xs = [p["x"] for p in points]
    ys = [p["y"] for p in points]
    assert edge["bounds"] == {
        "x": min(xs),
        "y": min(ys),
        "width": max(xs) - min(xs),
        "height": max(ys) - min(ys),
    }, name


def resolve(document: object, pointer: str) -> object:
    """Resolve one RFC 6901 pointer."""
    current = document
    for raw in [] if pointer == "" else pointer[1:].split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        current = current[int(part)] if isinstance(current, list) else current[part]  # type: ignore[index]
    return current


def check_input_from(*directories: Path) -> int:
    """Every ``inputFrom`` reference reuses another sealed case verbatim."""
    by_name = {case["case"]: case for directory in directories for _, case in load_cases(directory)}
    seen = 0
    for case in by_name.values():
        for link in case.get("inputFrom", []):
            source = by_name[link["case"]]
            assert resolve(source, link["pointer"]) == resolve(case, link["inputPointer"]), (
                f"{case['case']}: {link['inputPointer']} differs from {link['case']}"
            )
            seen += 1
    return seen


def case_profiles(case: dict[str, Any]) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    """(profile reference, trees) pairs of one case input."""
    inputs = case["input"]
    if "steps" in inputs:
        return [(step["profile"], [step["tree"]]) for step in inputs["steps"]]
    if "profile" in inputs and "tree" in inputs:
        return [(inputs["profile"], [inputs["tree"]])]
    return []


PARITY_PREFIXES = (
    "render.compile.",
    "render.digest.",
    "render.fresh.",
    "render.r.",
    "render.template.",
    "render.legacy.",
    "render.regions.",
    "render.ticks.",
    "render.switch.",
    "render.base.",
    "export.compile.",
    "export.map.",
    "export.serialize.",
    "export.prepare.",
)
# Runtime-specific although under a parity prefix (block-B parity sync PS-36).
RUNTIME_SPECIFIC = frozenset(
    {
        "export.prepare.success",
        "export.prepare.repairable-pre-normalize",
        "export.prepare.options-unknown-member",
    }
)
JS_CORPUS = "bpmn-canvas:tests/fixtures/lot4-layout-export/expectations"


def _artifact_value(parity_dir: Path, artifact: dict[str, Any]) -> Json:
    if "json" in artifact:
        return artifact["json"]
    data = (parity_dir / artifact["path"]).read_bytes()
    assert hashlib.sha256(data).hexdigest() == artifact["sha256"], artifact["path"]
    return json.loads(data.decode("utf-8"))


def _check_parity_inputs(
    helper: types.ModuleType,
    parity_dir: Path,
    name: str,
    inputs: dict[str, Any],
    record: dict[str, Any],
) -> None:
    roles = {a["role"]: _artifact_value(parity_dir, a) for a in record["inputArtifacts"]}
    ref = inputs.get("profile")
    if ref is not None:
        profile = _artifact_value(parity_dir, record["profileArtifact"])
        assert profile == helper.profile_from_ref(ref), name
    else:
        assert record["profileArtifact"] is None, name
    identity = inputs.get("envelopeIdentity")
    if identity is None and ref is not None:
        identity = helper.profile_identity(helper.profile_from_ref(ref))
    consumed = {"profile", "envelopeIdentity"}
    if "tree" in inputs:
        bindings = helper.sort_bindings([dict(b) for b in inputs.get("bindings", [])])
        assert roles.pop("envelope") == {
            "documentVersion": "1",
            "profileIdentity": identity,
            "tree": inputs["tree"],
            "bindings": bindings,
            "semanticRevision": helper.semantic_revision(inputs["tree"], identity, bindings),
        }, name
        consumed |= {"tree", "bindings"}
    for key in ("diagrams", "options"):
        if key not in inputs:
            continue
        diagrams = inputs["diagrams"] if key == "diagrams" else inputs["options"]["diagrams"]
        digest = helper.descriptor_digest(identity["descriptors"])
        imported = {
            "descriptorDigest": digest,
            "diagrams": diagrams,
            "sha256": helper.h({"descriptorDigest": digest, "diagrams": diagrams}),
        }
        if key == "diagrams":
            assert roles.pop("importedDi") == imported, name
        else:
            options = {k: v for k, v in inputs["options"].items() if k != "diagrams"}
            assert roles.pop("options") == {**options, "importedDi": imported}, name
        consumed.add(key)
    if "steps" in inputs:
        steps = roles.pop("steps")
        for step_input, step_record in zip(inputs["steps"], steps, strict=True):
            _check_parity_inputs(helper, parity_dir, name, step_input, step_record)
        consumed.add("steps")
    rest = {k: v for k, v in inputs.items() if k not in consumed}
    assert roles == rest, name


def check_parity_corpus(helper: types.ModuleType, parity_dir: Path, *expected_dirs: Path) -> int:
    """The corpus/1 projection pins its files and repeats every parity case's values exactly."""
    manifest = json.loads((parity_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["format"] == "profile-parity-corpus/1"
    listed = manifest["files"]
    on_disk = sorted(
        p.relative_to(parity_dir).as_posix()
        for p in parity_dir.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    )
    assert sorted(listed) == on_disk, "parity manifest does not list exactly the corpus files"
    for rel, want in listed.items():
        assert hashlib.sha256((parity_dir / rel).read_bytes()).hexdigest() == want, rel
    harness = {
        case["case"]: case
        for directory in expected_dirs
        for _, case in load_cases(directory)
        if case["case"].startswith(PARITY_PREFIXES) and case["case"] not in RUNTIME_SPECIFIC
    }
    records = sorted(parity_dir.glob("cases/*.json"))
    assert sorted(p.stem for p in records) == sorted(harness), (
        "parity cases differ from the harness"
    )
    for path in records:
        record = json.loads(path.read_text(encoding="utf-8"))
        case = harness[record["caseId"]]
        assert record["operation"] == case["operation"], path.name
        expected = case["expected"]
        artifacts = {a["role"]: _artifact_value(parity_dir, a) for a in record["expectedArtifacts"]}
        if expected["status"] == "sequence":
            assert record["expectedStatus"] == "sequence", path.name
            assert artifacts["results"] == expected["steps"], path.name
        else:
            status = "ok" if expected["status"] == "ok" else "refused:" + expected["code"]
            assert record["expectedStatus"] == status, path.name
            wire = {k: v for k, v in expected.items() if k not in HARNESS_KEYS}
            assert artifacts.pop("result") == wire, path.name
            harness_roles = {
                "drawio-structure" if k == "structural" else k: v
                for k, v in expected.items()
                if k in HARNESS_KEYS and k != "inputsUnchanged"
            }
            assert artifacts == harness_roles, path.name
        _check_parity_inputs(helper, parity_dir, path.name, case["input"], record)
    return len(records)


def check_parity_vendored(helper: types.ModuleType, parity_dir: Path, *expected_dirs: Path) -> int:
    """The parity manifest lists every vendored JS case and twin, never as a corpus record."""
    manifest = json.loads((parity_dir / "manifest.json").read_text(encoding="utf-8"))
    rows = [
        {
            "caseId": case["case"],
            "source": f"{JS_CORPUS}/cases/{case['case']}.json",
            "sha256": case["source"]["sha256"],
        }
        for directory in expected_dirs
        for _, case in load_vendored(directory)
    ]
    assert manifest["vendored"] == sorted(rows, key=lambda row: row["caseId"])
    aliases = [
        {"caseId": case_id, "aliasOf": alias["aliasOf"], "sha256": alias["sha256"]}
        for case_id, alias in sorted(helper.ALIASES.items())
    ]
    assert manifest["aliases"] == aliases
    published = {path.stem for path in parity_dir.glob("cases/*.json")}
    assert not published & {row["caseId"] for row in rows}, "a vendored case is re-published"
    assert not published & set(helper.ALIASES), "a twin is re-published"
    assert {alias["aliasOf"] for alias in aliases} <= published, "a twin target is not published"
    return len(rows)


# ----------------------------------------------------------- vendored JS cases

VENDORED_KEYS = frozenset(
    {
        "case",
        "clause",
        "derivation",
        "operation",
        "profile",
        "input",
        "expected",
        "expectedStatus",
        "comparatorIds",
        "artifacts",
        "source",
        "paritySync",
        "author",
    }
)
VENDORED_OPTIONAL = frozenset({"artifacts", "paritySync"})
SEAM_DECISION = "PS-33"  # helper seams return PureResult
ROW_DECISION = "PS-06"  # IO object centres on one row line
SEAM_OPERATIONS = frozenset({"layoutTicks", "layoutRegions"})
ROW_CASES = frozenset(
    {
        "layout-008-neutral-successor",
        "layout-009-grid-successor",
        "render-021-neutral-successor",
        "render-022-grid-successor",
        "export-025-neutral-successor",
        "export-026-grid-successor",
    }
)


def check_vendored_files(helper: types.ModuleType, directory: Path, tree: str) -> int:
    """The vendor/js files are exactly the tree's VENDORED table and the JS seal's bytes."""
    vendor = directory / "vendor" / "js"
    table = helper.VENDORED[tree]
    on_disk = sorted(
        path.relative_to(vendor).as_posix() for path in vendor.rglob("*") if path.is_file()
    )
    assert on_disk == sorted(table), "vendored files differ from the VENDORED table"
    for rel, want in table.items():
        assert hashlib.sha256((vendor / rel).read_bytes()).hexdigest() == want, rel
    assert table["seal.json"] == helper.JS_SEAL_SHA256
    seal = json.loads((vendor / "seal.json").read_text(encoding="utf-8"))
    listed = {entry["path"]: entry["sha256"] for entry in seal["files"]}
    for rel, want in table.items():
        if rel != "seal.json":
            assert listed[rel] == want, f"{rel}: not the bytes of the JS seal"
    return len(table)


def _ref(helper: types.ModuleType, value: dict[str, Any]) -> Json:
    """Resolve one ``{vendored, sha256}`` reference after checking its pin."""
    assert helper.vendored_pin(value["vendored"]) == value["sha256"], value["vendored"]
    return helper.vendored_json(value["vendored"])


def _js_ref(helper: types.ModuleType, tree: str, artifact: dict[str, Any]) -> dict[str, str]:
    """Re-express one JS ``{path, sha256}`` artifact reference as a vendored reference."""
    return {"vendored": helper.js_path(tree, artifact["path"]), "sha256": artifact["sha256"]}


def _set(document: Json, pointer: str, value: Json) -> None:
    """Replace the value at one RFC 6901 pointer."""
    *parents, last = [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]
    holder = document
    for part in parents:
        holder = holder[int(part)] if isinstance(holder, list) else holder[part]
    if isinstance(holder, list):
        holder[int(last)] = value
    else:
        holder[last] = value


def revert_parity_changes(record: dict[str, Any]) -> dict[str, Any]:
    """Copy a vendored record with every parity-sync change set back to its JS value."""
    plain = copy.deepcopy(record)
    for change in record.get("paritySync", {}).get("changes", []):
        assert resolve(plain, change["pointer"]) == change["to"], change["pointer"]
        _set(plain, change["pointer"], copy.deepcopy(change["from"]))
    return plain


def _check_decisions(record: dict[str, Any]) -> None:
    """A section-1 decision is listed exactly where it changes an imported value."""
    name = record["case"]
    sync = record.get("paritySync", {})
    decisions = sync.get("decisions", [])
    assert set(sync) <= {"decisions", "changes"}, name
    assert set(decisions) <= {SEAM_DECISION, ROW_DECISION}, name
    assert (SEAM_DECISION in decisions) == (record["operation"] in SEAM_OPERATIONS), name
    assert (ROW_DECISION in decisions) == (name in ROW_CASES), name
    assert ("changes" in sync) == (ROW_DECISION in decisions), name
    for decision in decisions:
        assert f"parity-sync decision {decision}" in record["derivation"], name


def _check_profile(
    helper: types.ModuleType, tree: str, record: dict[str, Any], js_case: dict[str, Any]
) -> None:
    """The profile reference and its load inputs are the JS manifest package record."""
    artifact = js_case["profileArtifact"]
    if artifact is None:
        assert record["profile"] is None, record["case"]
        return
    manifest = helper.vendored_json(f"{helper.TREES[tree]}/{helper.VENDOR}/manifest.json")
    package = next(p for p in manifest["packages"] if p["profile"]["path"] == artifact["path"])
    load = {
        key: _js_ref(helper, tree, package[key])
        for key in ("base", "descriptors", "registry", "schema")
    }
    assets = [_js_ref(helper, tree, asset) for asset in package["assets"]]
    profile = _js_ref(helper, tree, artifact)
    assert record["profile"] == {**profile, "load": {**load, "assets": assets}}, record["case"]
    for reference in (profile, *load.values(), *assets):
        _ref(helper, reference)


def _check_inputs(
    helper: types.ModuleType, tree: str, plain: dict[str, Any], js_case: dict[str, Any]
) -> None:
    """Inputs are the JS input artifacts in order, by reference or inline."""
    name = plain["case"]
    artifacts = js_case["inputArtifacts"]
    assert [item["role"] for item in plain["input"]] == [a["role"] for a in artifacts], name
    for item, artifact in zip(plain["input"], artifacts, strict=True):
        if "path" not in artifact:
            assert item == {"role": artifact["role"], "json": artifact["json"]}, name
        elif "json" in item:
            assert "paritySync" in plain, f"{name}: inline copy of a vendored input"
            assert item["json"] == _ref(helper, _js_ref(helper, tree, artifact)), name
        else:
            assert item == {"role": artifact["role"], **_js_ref(helper, tree, artifact)}, name
            _ref(helper, item)


def _check_expected(
    helper: types.ModuleType, tree: str, plain: dict[str, Any], js_case: dict[str, Any]
) -> None:
    """The expected record, comparators and other artifacts are the JS ones (PS-33 applied)."""
    values = {
        artifact["role"]: (
            _ref(helper, _js_ref(helper, tree, artifact))
            if "path" in artifact
            else artifact["json"]
        )
        for artifact in js_case["expectedArtifacts"]
    }
    result = values.pop("result") if "result" in values else values.pop("output")
    unsealed = values.pop("unsealed", None)
    comparators = js_case["comparatorIds"]
    if SEAM_DECISION in plain.get("paritySync", {}).get("decisions", []):
        result = {"status": "ok", "payload": result, "diagnostics": []}
        comparators = ["result-exact/1" if c == "seam-exact/1" else c for c in comparators]
    if unsealed is not None:
        result = {**result, "unsealed": [entry["pointer"] for entry in unsealed]}
    name = plain["case"]
    assert plain["expected"] == result, name
    assert plain["comparatorIds"] == comparators, name
    assert plain["expectedStatus"] == js_case["expectedStatus"], name
    others = [{"role": role, "json": value} for role, value in values.items()]
    assert plain.get("artifacts", []) == others, name


def check_vendored_record(
    helper: types.ModuleType, tree: str, path: Path, record: dict[str, Any]
) -> None:
    """One vendored record is the JS case, re-expressed, with only its decisions applied."""
    name = path.name
    assert VENDORED_KEYS - VENDORED_OPTIONAL <= set(record) <= VENDORED_KEYS, name
    assert record["case"] == path.stem, name
    assert record["author"] == "spec-seal", name
    assert record["clause"].startswith("DESIGN R3.3 §"), name
    source = record["source"]
    assert source["vendored"] == f"{helper.TREES[tree]}/{helper.VENDOR}/cases/{path.name}", name
    js_case = _ref(helper, source)
    assert js_case["caseId"] == path.stem, name
    assert helper.JS_SEAL_SHA256 in record["derivation"], name
    assert source["sha256"] in record["derivation"], name
    assert record["operation"] == js_case["operation"], name
    _check_decisions(record)
    _check_profile(helper, tree, record, js_case)
    plain = revert_parity_changes(record)
    _check_inputs(helper, tree, plain, js_case)
    _check_expected(helper, tree, plain, js_case)


def check_vendored(helper: types.ModuleType, directory: Path, tree: str) -> int:
    """Every vendored case of the tree has exactly one checked harness record."""
    records = load_vendored(directory)
    cases = sorted(
        rel.removeprefix("cases/").removesuffix(".json")
        for rel in helper.VENDORED[tree]
        if rel.startswith("cases/")
    )
    assert [path.stem for path, _ in records] == cases, "vendored records differ from the cases"
    for path, record in records:
        check_vendored_record(helper, tree, path, record)
    return len(records)


def _input_value(helper: types.ModuleType, record: dict[str, Any], role: str) -> Json:
    item = next(item for item in record["input"] if item["role"] == role)
    return item["json"] if "json" in item else _ref(helper, item)


def check_vendored_digests(helper: types.ModuleType, record: dict[str, Any]) -> bool:
    """R and PreparedArtifact digests of a vendored success follow the helper formulas."""
    expected = record["expected"]
    if not isinstance(expected, dict) or expected.get("status") != "ok":
        return False
    if record["operation"] == "resolveTheme":
        render = expected["payload"]
    elif record["operation"] == "mapExport":
        render = _input_value(helper, record, "render")
        prepared = expected["payload"]
        assert prepared["renderBinding"] == render["binding"], record["case"]
        assert prepared["viewRevision"] == helper.view_revision(render["binding"]), record["case"]
        digest = prepared["report"]["artifacts"][0]["digest"]
        assert digest == helper.h(prepared["ir"]), record["case"]
        assert expected["report"] == prepared["report"], record["case"]
    else:
        return False
    layout = _input_value(helper, record, "layout")
    assert render["binding"]["layoutDigest"] == helper.h(layout), record["case"]
    assert render["binding"]["payloadDigest"] == helper.payload_digest(render), record["case"]
    return True


def load_helper() -> types.ModuleType:
    """Load the standalone derivation helper by path."""
    spec = importlib.util.spec_from_file_location("derive_helper", HELPER)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
