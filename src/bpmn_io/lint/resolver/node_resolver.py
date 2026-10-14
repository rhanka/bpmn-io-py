# Transposed from bpmn-io/bpmnlint@de71146 lib/resolver/node-resolver.js (MIT).
"""Node-style resolver, transposed from ``lib/resolver/node-resolver.js``.

The resolution steps (exported ``rules``/``configs`` maps first, default
``rules/``/``config/`` locations second, identical error messages) are kept;
the underlying ``require`` is the Python scoped require from
``resolver/helper.py`` (``entry_points(group="bpmnlint.plugins")`` plus
``importlib``), injectable for tests exactly as upstream injects Node's.
"""

from __future__ import annotations

import contextlib
import posixpath
from pathlib import Path
from typing import Any, cast

from bpmn_io._min_dash import is_string
from bpmn_io.lint.resolver.helper import create_scoped_require

__all__ = ["NodeResolver"]


def _member(instance: object, name: str) -> object:
    """Read ``name`` from a module-like object (dict entry or attribute)."""
    if isinstance(instance, dict):
        return instance.get(name)
    return getattr(instance, name, None)


def _local_require(path: str) -> object:
    """Default ``requireLocal``: resolve bpmnlint's own rules and configs."""
    if path.startswith("../../rules/"):
        rule_name = path[len("../../rules/") :]
        module_name = rule_name.replace("-", "_")
        if module_name == "global":
            module_name = "global_"
        module = __import__(
            f"bpmn_io.lint.rules.{module_name}",
            fromlist=["factory"],
        )
        return module.factory

    if path.startswith("../../config/"):
        config_name = path[len("../../config/") :]
        module = __import__(
            f"bpmn_io.lint.config.{config_name.replace('-', '_')}",
            fromlist=["CONFIG"],
        )
        return module.CONFIG

    msg = f"not found: {path}"
    raise ModuleNotFoundError(msg)


class NodeResolver:
    """Resolve rules and configs through a scoped ``require`` (upstream ``NodeResolver``)."""

    def __init__(
        self,
        options: dict[str, Any] | None = None,
        *,
        require: object = None,
        require_local: object = None,
    ) -> None:
        """Create the resolver; ``require``/``require_local`` are injectable callables."""
        opts: dict[str, Any] = dict(options) if options else {}
        if require is not None:
            opts["require"] = require
        if require_local is not None:
            opts["require_local"] = require_local

        self.require = opts.get("require") or create_scoped_require(str(Path.cwd()))
        self.require_local = opts.get("require_local") or opts.get("requireLocal") or _local_require

        try:
            self.pkg: str = cast("dict[str, str]", self.require("./package.json"))["name"]
        except Exception:  # noqa: BLE001 - upstream falls back to '__unknown'
            self.pkg = "__unknown"

    def resolve_rule(self, pkg: str, rule_name: str) -> object:
        """Resolve the rule factory ``rule_name`` from ``pkg`` (upstream ``resolveRule``)."""
        original_pkg = pkg

        pkg = self.normalize_pkg(pkg)

        pkg_instance: Any = None

        # (1) try resolving rule via $PKG.rules[$NAME]
        try:
            pkg_instance = self.require(pkg)
        except Exception:  # noqa: BLE001 - upstream ignores resolution failures here
            pkg_instance = None

        if pkg_instance:
            rules = cast("dict[Any, Any]", _member(pkg_instance, "rules") or {})

            if rule_name in rules:
                rule = rules[rule_name]

                if not is_string(rule):
                    msg = (
                        f"cannot resolve rule <{rule_name}> from <{original_pkg}>: "
                        "illegal rule export (expected path reference)"
                    )
                    raise ValueError(msg)

                # local reference, resolved relative to pkg location
                if rule.startswith("."):
                    pkg_dir = posixpath.dirname(self.require.resolve(pkg))

                    return self.require(posixpath.normpath(f"{pkg_dir}/{rule}"))

                # absolute reference
                return self.require(rule)

        # (2) try resolving rule via $PKG/rules/$NAME
        with contextlib.suppress(Exception):
            if pkg == "bpmnlint":
                return self.require_local(f"../../rules/{rule_name}")
            return self.require(f"{pkg}/rules/{rule_name}")

        msg = f"cannot resolve rule <{rule_name}> from <{original_pkg}>"
        raise ValueError(msg)

    def resolve_config(self, pkg: str, config_name: str) -> object:
        """Resolve the config ``config_name`` from ``pkg`` (upstream ``resolveConfig``)."""
        original_pkg = pkg

        pkg = self.normalize_pkg(pkg)

        # (1) try resolving config via $PKG.configs[$NAME]
        with contextlib.suppress(Exception):
            instance = self.require(pkg)

            configs = cast("dict[Any, Any]", _member(instance, "configs") or {})

            if config_name in configs:
                return configs[config_name]

        # (2) try resolving config via $PKG/config/$NAME
        with contextlib.suppress(Exception):
            if pkg == "bpmnlint":
                return self.require_local(f"../../config/{config_name}")
            return self.require(f"{pkg}/config/{config_name}")

        msg = f"cannot resolve config <{config_name}> from <{original_pkg}>"
        raise ValueError(msg)

    def normalize_pkg(self, pkg: str) -> str:
        """Map the local package name to ``.`` (upstream ``normalizePkg``)."""
        if pkg != "bpmnlint" and pkg == self.pkg:
            pkg = "."

        return pkg
