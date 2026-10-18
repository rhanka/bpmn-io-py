"""Seal integrity of the lot-3 C/N expectations (spec SPEC_PROFILE_CN_PY.md §9).

Checks the manifest (any one-byte change fails), the derivation helper's
imports (stdlib only, nothing from ``bpmn_io``), the required keys of every
expectation file, and that the helper reproduces every sealed byte from its
hand-authored data. Imports nothing from ``bpmn_io``.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

EXPECTED = Path(__file__).resolve().parent / "expected"
MANIFEST = EXPECTED / "MANIFEST.sha256"
HELPER = EXPECTED / "derive_helper.py"
REQUIRED_KEYS = {"case", "clause", "derivation", "input", "expected", "author"}
OPERATIONS = {
    "apply_plan",
    "bind_supports",
    "compile_profile",
    "complete",
    "gates",
    "normalize",
    "plan_recipe+apply_plan",
    "propose_support_bindings",
    "remap_ids",
    "sort_placements",
}
STDLIB_IMPORTS = {"__future__", "copy", "hashlib", "json", "pathlib", "sys"}
FORBIDDEN_CALLS = {"__import__", "eval", "exec", "compile"}


def _sealed_files() -> dict[str, bytes]:
    """Return every sealed file under expected/ (manifest excluded)."""
    files: dict[str, bytes] = {}
    for path in sorted(EXPECTED.rglob("*")):
        if not path.is_file() or path == MANIFEST:
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        files[path.relative_to(EXPECTED).as_posix()] = path.read_bytes()
    return files


def _manifest_rows() -> list[tuple[str, str]]:
    rows = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        digest, _, name = line.partition("  ")
        rows.append((name, digest))
    return rows


def manifest_problems(files: dict[str, bytes], rows: list[tuple[str, str]]) -> list[str]:
    """Return every mismatch between sealed bytes and manifest rows."""
    problems = []
    listed = dict(rows)
    if sorted(listed) != [name for name, _ in rows]:
        problems.append("manifest rows are not sorted by path")
    if set(listed) != set(files):
        problems.append(f"file set differs: {sorted(set(listed) ^ set(files))}")
    for name, data in files.items():
        if name in listed and hashlib.sha256(data).hexdigest() != listed[name]:
            problems.append(f"digest mismatch: {name}")
    return problems


def test_manifest_matches_every_sealed_byte() -> None:
    """Every sealed file is listed once, sorted, with its exact SHA-256."""
    assert manifest_problems(_sealed_files(), _manifest_rows()) == []


def test_one_byte_change_fails_the_manifest() -> None:
    """Flipping any single byte of any sealed file is detected."""
    files = _sealed_files()
    rows = _manifest_rows()
    for name, data in files.items():
        mutated = dict(files)
        mutated[name] = data[:-1] + bytes([data[-1] ^ 0x01])
        assert manifest_problems(mutated, rows) == [f"digest mismatch: {name}"]


def _imported_modules(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add((node.module or "").split(".")[0])
    return names


def test_helper_imports_stdlib_only() -> None:
    """The derivation helper imports only the stdlib and never bpmn_io."""
    tree = ast.parse(HELPER.read_text(encoding="utf-8"))
    modules = _imported_modules(tree)
    assert not any(name.startswith("bpmn_io") for name in modules)
    assert modules <= STDLIB_IMPORTS
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in FORBIDDEN_CALLS
        if isinstance(node, ast.Attribute):
            assert node.attr not in {"import_module", "spec_from_file_location"}


def test_helper_check_detects_a_bpmn_io_import() -> None:
    """The import scan rejects direct and dotted bpmn_io imports."""
    for source in ("import bpmn_io.profile\n", "from bpmn_io.profile import jcs\n"):
        assert "bpmn_io" in _imported_modules(ast.parse(source))


def _case_files() -> list[Path]:
    return sorted(EXPECTED.glob("*.json"))


@pytest.mark.parametrize("path", _case_files(), ids=lambda p: p.stem)
def test_expectation_file_shape(path: Path) -> None:
    """Every expectation carries the required keys and the seal author."""
    record = json.loads(path.read_text(encoding="utf-8"))
    assert set(record) >= REQUIRED_KEYS
    assert record["author"] == "spec-seal"
    assert record["case"] == path.stem
    assert str(record["clause"]).startswith("DESIGN R3.3 ")
    assert record["operation"] in OPERATIONS
    assert record["derivation"]


def test_case_count_is_sealed() -> None:
    """The sealed case set is exactly the 102 cases listed in the spec case table."""
    assert len(_case_files()) == 102


def _load_helper() -> ModuleType:
    spec = importlib.util.spec_from_file_location("profile_cn_derive_helper", HELPER)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_helper_reproduces_every_sealed_byte() -> None:
    """Regenerating from the hand-authored data yields the sealed bytes exactly."""
    sys.dont_write_bytecode = True
    built = _load_helper().build()
    assert built == _sealed_files()


def test_variant_pins_match_artifact_bytes() -> None:
    """Every variant's descriptor/base pins equal the raw SHA-256 of its bytes."""
    root = EXPECTED.parents[2]
    document = json.loads((EXPECTED / "artifacts" / "profile-variants.json").read_text())
    for row in document["variants"]:
        identity = row["identity"]
        base = hashlib.sha256((root / row["baseBytes"]).read_bytes()).hexdigest()
        descriptors = hashlib.sha256((root / row["descriptorBytes"]).read_bytes()).hexdigest()
        assert identity["base"]["sha256"] == base
        assert identity["descriptors"][0]["sha256"] == descriptors
