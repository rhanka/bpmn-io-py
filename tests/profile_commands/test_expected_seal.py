"""Seal integrity of the lot-5 command expectations (DESIGN R3.3 §8.1-§8.3).

The expectation tree under ``expected/`` is sealed: the bytes of every harness
case, committed byte artifact (``artifacts/``), parity projection (``parity/``)
and vendored JS file (``vendor/js/``, block-B parity sync) are pinned by
``expected/MANIFEST.sha256`` (sha256sum format, sorted by path), the standalone
``derive_helper.py`` imports nothing from the library under test, and every
derived digest, stable identifier, revision, Result/Report bookkeeping value,
parity record and vendored harness record recomputes from the helper. This test
never imports ``bpmn_io``.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import ModuleType

HERE = Path(__file__).resolve().parent
EXPECTED = HERE / "expected"
MANIFEST = EXPECTED / "MANIFEST.sha256"
HELPER = EXPECTED / "derive_helper.py"
SPEC = HERE.parent.parent / "spec" / "SPEC_PROFILE_COMMANDS_PY.md"
REQUIRED_KEYS = frozenset({"case", "clause", "derivation", "input", "expected", "author"})
STEP_KEYS = frozenset({"result", "equal", "differ", "signal"})
UNSEALED_REASONS = frozenset(
    {
        "lot4-view-revision",
        "lot4-presentation",
        "session-history-epoch",
        "session-subscription",
        "raw-lint-transport",
        "compiled-profile",
    }
)
#: The PureResult compile success (DESIGN R3.3 §10.1 L737, parity sync PS-35).
COMPILE_SUCCESS = {"status": "ok", "payload": {"$unsealed": "compiled-profile"}, "diagnostics": []}
#: Harness files authored for this lot (101 cases and 5 fixtures).
NATIVE_FILES = 106
#: Vendored JS cases per family (block-B parity sync: 150 lot-5 cases, one lot-3 script).
VENDORED_FAMILIES = {
    "surfaces": 12,
    "palette": 26,
    "context": 6,
    "connect": 8,
    "replace": 7,
    "delete": 9,
    "fields": 61,
    "paste": 13,
    "history": 6,
    "twin": 1,
    "demo": 1,
    "l3-tx": 1,
}
VENDORED_OPERATIONS = frozenset(
    {
        "applyCommands",
        "checkField",
        "compileProfile",
        "copy",
        "listEntries",
        "listFields",
        "queryReferences",
        "sequence",
    }
)
VENDORED_KEYS = frozenset(
    {"case", "clause", "derivation", "author", "operation", "profile", "input", "expected"}
)
VENDORED_INPUT_KEYS = frozenset({"source", "pathBase", "inputArtifacts", "commandArtifact"})
#: Reasons of the JS markers {"$unsealed": reason, "type": t} inside vendored values.
VENDORED_UNSEALED_REASONS = frozenset({"twin-presentation", "replacement-map-multi-create"})
FORBIDDEN_MODULE = "bpmn_io"
#: Prefix of an absolute local home path, assembled so this file carries none.
LOCAL_PATH_PREFIX = chr(0x2F) + "home" + chr(0x2F)


def _manifest_entries() -> list[tuple[str, str]]:
    entries = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        digest, _, name = line.partition("  ")
        entries.append((digest, name))
    return entries


def _sealed_files() -> list[str]:
    names = [
        path.relative_to(EXPECTED).as_posix()
        for path in EXPECTED.rglob("*")
        if path.is_file() and path.suffix in (".json", ".py") and "__pycache__" not in path.parts
    ]
    return sorted(names)


def _load_helper() -> ModuleType:
    spec = importlib.util.spec_from_file_location("profile_commands_derive_helper", HELPER)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _expectations() -> list[tuple[str, dict[str, object]]]:
    found = []
    for path in sorted(EXPECTED.glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(value, dict), path.name
        found.append((path.stem, value))
    return found


def _is_vendored(value: dict[str, object]) -> bool:
    profile = value.get("profile")
    return isinstance(profile, dict) and "vendored" in profile


def _markers(node: object, keys: frozenset[str] = frozenset({"$unsealed"})) -> Iterator[object]:
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if "$unsealed" in current and set(current) <= keys:
                yield current["$unsealed"]
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


def test_manifest_pins_every_sealed_file() -> None:
    """Each sealed file is listed once, in sorted order, with its exact SHA-256."""
    entries = _manifest_entries()
    names = [name for _, name in entries]
    assert names == sorted(names)
    assert names == _sealed_files()
    for digest, name in entries:
        actual = hashlib.sha256((EXPECTED / name).read_bytes()).hexdigest()
        assert actual == digest, f"sealed file changed: {name}"


def test_helper_imports_nothing_from_the_library() -> None:
    """The derivation helper is standalone (AST check, including string imports)."""
    tree = ast.parse(HELPER.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] != FORBIDDEN_MODULE for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] != FORBIDDEN_MODULE
            assert node.level == 0
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert FORBIDDEN_MODULE not in node.value
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"__import__", "exec", "eval"}


def test_expectation_files_carry_the_required_keys() -> None:
    """Every file names its case, clause, derivation, input, expected and author."""
    for stem, value in _expectations():
        assert set(value) >= REQUIRED_KEYS, stem
        assert value["author"] == "spec-seal", stem
        assert value["case"] == stem, stem
        clause = value["clause"]
        assert isinstance(clause, str)
        assert clause.startswith("DESIGN R3.3 §"), stem
        assert isinstance(value["derivation"], str)
        assert value["derivation"], stem


def test_case_shapes_are_closed() -> None:
    """Fixtures carry a source; cases carry a committed profile and steps or a compile outcome."""
    for stem, value in _expectations():
        case_input = value["input"]
        expected = value["expected"]
        assert isinstance(case_input, dict)
        assert isinstance(expected, dict)
        if _is_vendored(value):
            profile = value["profile"]
            assert isinstance(profile, dict)
            assert set(value) == VENDORED_KEYS, stem
            assert set(profile) == {"vendored", "sha256"}, stem
            assert VENDORED_INPUT_KEYS - {"commandArtifact"} <= set(case_input), stem
            assert set(case_input) <= VENDORED_INPUT_KEYS, stem
            continue
        if stem.startswith("fixture-"):
            assert set(case_input) == {"source"}, stem
            assert "artifact" in expected, stem
            continue
        profile = case_input["profile"]
        assert isinstance(profile, dict)
        assert set(profile) == {"fixture", "delta", "artifact"}, stem
        if "compile" in expected:
            outcome = expected["compile"]
            assert isinstance(outcome, dict)
            assert set(case_input) == {"profile"}, stem
            if outcome["status"] == "ok":
                assert outcome == COMPILE_SUCCESS, stem
                assert set(expected) == {"compile", "compiledIdentity"}, stem
            else:
                assert set(outcome) == {"status", "code", "diagnostics"}, stem
                assert outcome["diagnostics"] == [], stem
                assert set(expected) == {"compile"}, stem
            continue
        steps = case_input["steps"]
        expected_steps = expected["steps"]
        assert isinstance(steps, list)
        assert isinstance(expected_steps, list)
        assert steps, stem
        assert len(steps) == len(expected_steps), stem
        assert ("document" in case_input) == ("setup" in expected), stem
        for item in expected_steps:
            assert isinstance(item, dict)
            assert "result" in item, stem
            assert set(item) <= STEP_KEYS, stem


def test_unsealed_markers_name_a_declared_reason() -> None:
    """Every excluded member carries one of the reasons listed in the binding spec."""
    text = SPEC.read_text(encoding="utf-8")
    for reason in UNSEALED_REASONS | VENDORED_UNSEALED_REASONS:
        assert f"`{reason}`" in text, reason
    js_keys = frozenset({"$unsealed", "type", "optional"})
    for stem, value in _expectations():
        if _is_vendored(value):
            for reason in _markers(value["expected"], js_keys):
                assert reason in VENDORED_UNSEALED_REASONS, stem
            continue
        assert list(_markers(value["expected"], js_keys)) == list(_markers(value["expected"]))
        for reason in _markers(value["expected"]):
            assert reason in UNSEALED_REASONS, stem


def test_vendored_cases_are_counted() -> None:
    """The plan's 151 vendored cases are present, per family, with the planned operations."""
    families: dict[str, int] = {}
    operations: set[object] = set()
    native = 0
    for stem, value in _expectations():
        if not _is_vendored(value):
            native += 1
            continue
        family = "l3-tx" if stem.startswith("l3-tx-") else stem.split("-")[1]
        families[family] = families.get(family, 0) + 1
        operations.add(value["operation"])
    assert native == NATIVE_FILES
    assert families == VENDORED_FAMILIES
    assert operations == VENDORED_OPERATIONS


def test_parity_projection_is_closed() -> None:
    """parity/ projects exactly the authored cases; vendored cases are listed, not projected."""
    authored = set()
    vendored = set()
    for stem, value in _expectations():
        if _is_vendored(value):
            vendored.add(stem)
        elif not stem.startswith("fixture-"):
            authored.add(f"lot5-py-{stem}")
    records = {path.stem for path in (EXPECTED / "parity").glob("*.json")} - {"manifest"}
    assert records == authored
    manifest = json.loads((EXPECTED / "parity" / "manifest.json").read_text(encoding="utf-8"))
    assert {entry["caseId"] for entry in manifest["vendored"]} == vendored
    assert not any(name.startswith("vendor/") for name in manifest["files"])


def test_derived_values_recompute() -> None:
    """Digests, IDs, compositions, revisions, results and parity records recompute."""
    helper = _load_helper()
    assert helper.check_all() == []


def test_spec_case_table_lists_every_file() -> None:
    """The binding spec has one case-table row per sealed expectation file."""
    text = SPEC.read_text(encoding="utf-8")
    for stem, _ in _expectations():
        assert f"| `{stem}` |" in text, stem


def test_sealed_text_has_no_local_paths() -> None:
    """No sealed file or spec embeds an absolute local path."""
    for path in [*EXPECTED.rglob("*"), SPEC]:
        if path.is_file() and "__pycache__" not in path.parts:
            assert LOCAL_PATH_PREFIX not in path.read_text(encoding="utf-8"), path.name
