"""Seal integrity of the lot-5 command expectations (DESIGN R3.3 §8.1-§8.3).

The expectation files under ``expected/`` are sealed: their bytes are pinned
by ``expected/MANIFEST.sha256`` (sha256sum format, sorted by path), the
standalone ``derive_helper.py`` imports nothing from the library under test,
and every derived digest, stable identifier and revision recomputes from the
helper. This test never imports ``bpmn_io``.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType

HERE = Path(__file__).resolve().parent
EXPECTED = HERE / "expected"
MANIFEST = EXPECTED / "MANIFEST.sha256"
HELPER = EXPECTED / "derive_helper.py"
SPEC = HERE.parent.parent / "spec" / "SPEC_PROFILE_COMMANDS_PY.md"
REQUIRED_KEYS = frozenset({"case", "clause", "derivation", "input", "expected", "author"})
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
    names = [path.name for path in EXPECTED.glob("*.json")]
    names.append(HELPER.name)
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
    """Fixtures carry a source; cases carry a profile and steps or a compile outcome."""
    for stem, value in _expectations():
        case_input = value["input"]
        expected = value["expected"]
        assert isinstance(case_input, dict)
        assert isinstance(expected, dict)
        if stem.startswith("fixture-"):
            assert set(case_input) == {"source"}, stem
            continue
        assert "profile" in case_input, stem
        if "compile" in expected:
            assert set(expected) == {"compile"}, stem
            assert set(case_input) == {"profile"}, stem
            continue
        steps = case_input["steps"]
        expected_steps = expected["steps"]
        assert isinstance(steps, list)
        assert isinstance(expected_steps, list)
        assert steps, stem
        assert len(steps) == len(expected_steps), stem
        assert ("document" in case_input) == ("setup" in expected), stem


def test_derived_values_recompute() -> None:
    """Digests, stable IDs, compositions and revisions recompute from the helper."""
    helper = _load_helper()
    assert helper.check_all() == []


def test_spec_case_table_lists_every_file() -> None:
    """The binding spec has one case-table row per sealed expectation file."""
    text = SPEC.read_text(encoding="utf-8")
    for stem, _ in _expectations():
        assert f"| `{stem}` |" in text, stem


def test_sealed_text_has_no_local_paths() -> None:
    """No sealed file or spec embeds an absolute local path."""
    for path in [*EXPECTED.iterdir(), SPEC]:
        if path.is_file():
            assert LOCAL_PATH_PREFIX not in path.read_text(encoding="utf-8"), path.name
