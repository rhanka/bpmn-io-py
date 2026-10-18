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

if TYPE_CHECKING:
    import types

HELPER = Path(__file__).resolve().parent / "expected" / "derive_helper.py"
MANIFEST_NAME = "MANIFEST.sha256"
REQUIRED_KEYS = ("case", "clause", "derivation", "input", "expected", "author")
STATUSES = frozenset({"ok", "refused", "sequence"})
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
    """Load every case file of one tree (sorted by path)."""
    return [
        (path, json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(directory.glob("*.json"))
    ]


def check_case_shapes(directory: Path, prefix: str) -> None:
    """Each case carries the required keys, its file name and the seal author."""
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
        assert isinstance(case["operation"], str), path.name
        assert case["expected"]["status"] in STATUSES, path.name
        if case["expected"]["status"] == "refused":
            assert isinstance(case["expected"]["code"], str), path.name


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


def load_helper() -> types.ModuleType:
    """Load the standalone derivation helper by path."""
    spec = importlib.util.spec_from_file_location("derive_helper", HELPER)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
