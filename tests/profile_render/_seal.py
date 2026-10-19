"""Shared seal-integrity checks for the lot-4 expectation trees.

Imports nothing from ``bpmn_io``: the sealed files are checked against their
manifest, their closed case shape and the standalone derivation helper only.
"""

from __future__ import annotations

import ast
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
    """Load every case file of one tree (sorted by path; artifacts excluded)."""
    return [
        (path, json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(directory.glob("*.json"))
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
            assert set(expected) <= {"status", "code"}, path.name
        for key in set(expected) & HARNESS_KEYS:
            check_harness_key(path.name, key, expected[key], expected)


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
        if case["case"].startswith(PARITY_PREFIXES)
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


def load_helper() -> types.ModuleType:
    """Load the standalone derivation helper by path."""
    spec = importlib.util.spec_from_file_location("derive_helper", HELPER)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
