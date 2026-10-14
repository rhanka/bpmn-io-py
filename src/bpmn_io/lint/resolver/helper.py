# Transposed from bpmn-io/bpmnlint@de71146 lib/resolver/helper.js (MIT).
"""Scoped ``require`` for the resolver, adapted from ``lib/resolver/helper.js``.

Upstream builds a Node ``require`` anchored at the working directory. The
Python adaptation returns a callable with the same shape (``require(path)``
plus ``require.resolve(path)``) backed by Python plugin discovery:
``entry_points(group="bpmnlint.plugins")`` first, then ``importlib`` (dash
segments of a node-style path map to underscores). See ``docs/naming.md``.
"""

from __future__ import annotations

import importlib
import posixpath
import tomllib
from importlib import metadata
from pathlib import Path

__all__ = ["create_scoped_require"]


class PythonRequire:
    """Callable mimicking a scoped Node ``require`` over Python packages."""

    def __init__(self, cwd: str) -> None:
        """Anchor relative resolution at ``cwd`` (upstream ``createScopedRequire``)."""
        self.cwd = cwd

    def __call__(self, path: str) -> object:
        """Load ``path`` as a module-like object (dicts and modules both qualify)."""
        if path == "./package.json":
            return {"name": self._local_package_name()}

        entry_point = self._entry_point(path)
        if entry_point is not None:
            return entry_point.load()

        return importlib.import_module(_module_name(path))

    def resolve(self, path: str) -> str:
        """Return the file path ``path`` would load from (upstream ``require.resolve``)."""
        if path.endswith("/package.json"):
            pkg = path[: -len("/package.json")]
            module = importlib.import_module(_module_name(pkg))
            package_dir = Path(module.__file__ or "").parent
            return posixpath.join(package_dir.as_posix(), "package.json")

        module = importlib.import_module(_module_name(path))
        return Path(module.__file__ or "").as_posix()

    def _entry_point(self, path: str) -> metadata.EntryPoint | None:
        """Return the ``bpmnlint.plugins`` entry point named ``path``, if any."""
        if "/" in path:
            return None
        try:
            points = metadata.entry_points(group="bpmnlint.plugins")
        except Exception:  # noqa: BLE001 - discovery must never break resolution
            return None
        for point in points:
            if point.name == path:
                return point
        return None

    def _local_package_name(self) -> str:
        """Read the ``[project] name`` of the ``pyproject.toml`` at the anchor directory."""
        pyproject = Path(self.cwd) / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        name: str = data["project"]["name"]
        return name


def create_scoped_require(cwd: str) -> PythonRequire:
    """Create a ``require`` callable anchored at ``cwd`` (upstream ``createScopedRequire``)."""
    return PythonRequire(cwd)


def _module_name(path: str) -> str:
    """Map a node-style module path to a Python module name (dashes to underscores)."""
    return ".".join(segment.replace("-", "_") for segment in path.split("/"))
