# Transposed from bpmn-io/bpmnlint@de71146 lib/support/compile-config.js (MIT).
"""Compile a bpmnlint config to a JS bundle, transposed from ``lib/support/compile-config.js``.

The generated JavaScript text is byte-identical to upstream (it is a JS
packaging artefact); the resolver driving it is the Python resolver port.
"""

from __future__ import annotations

import json
import posixpath
from typing import Any, cast

from bpmn_io._min_dash import is_string
from bpmn_io.lint.linter import Linter, Resolver
from bpmn_io.lint.resolver.node_resolver import NodeResolver

__all__ = ["compile_config"]


def compile_config(config: dict[str, Any], resolver: NodeResolver | None = None) -> str:
    """Compile ``config`` to a JS file exporting a ``{config, resolver}`` bundle."""
    if resolver is None:
        resolver = NodeResolver()

    linter = Linter(resolver=cast("Resolver", resolver))

    resolved_rules = linter.resolve_configured_rules(config)

    # only process and serialize enabled rules
    rules: dict[str, Any] = {}
    for key, value in resolved_rules.items():
        category = linter.parse_rule_value(value)["category"]

        rules[key] = 0 if category == "off" else value

    serialized_rules = json.dumps(rules, indent=2, ensure_ascii=False)

    preamble_code = f"""
const cache = {{}};

/**
 * A resolver that caches rules and configuration as part of the bundle,
 * making them accessible in the browser.
 *
 * @param {{Object}} cache
 */
function Resolver() {{}}

Resolver.prototype.resolveRule = function(pkg, ruleName) {{

  const rule = cache[pkg + '/' + ruleName];

  if (!rule) {{
    throw new Error('cannot resolve rule <' + pkg + '/' + ruleName + '>: not bundled');
  }}

  return rule;
}};

Resolver.prototype.resolveConfig = function(pkg, configName) {{
  throw new Error(
    'cannot resolve config <' + configName + '> in <' + pkg +'>: not bundled'
  );
}};

const resolver = new Resolver();

const rules = {serialized_rules};

const config = {{
  rules: rules
}};

const moddleExtensions = {{}};

const bundle = {{
  resolver: resolver,
  config: config,
  moddleExtensions: moddleExtensions
}};

export {{ resolver, config, moddleExtensions }};

export default bundle;
"""

    rule_import_code = "\n".join(
        statement
        for statement in (
            _create_rule_import_statement(
                linter.parse_rule_name(key)["pkg"],
                linter.parse_rule_name(key)["rule_name"],
                idx,
                resolver,
            )
            if value
            else None
            for idx, (key, value) in enumerate(rules.items())
        )
        if statement
    )

    moddle_extensions = config.get("moddleExtensions") or {}
    moddle_import_code = "\n".join(
        statement
        for statement in (
            _create_moddle_extension_statement(key, import_path, idx)
            for idx, (key, import_path) in enumerate(moddle_extensions.items())
        )
        if statement
    )

    return f"{preamble_code}{rule_import_code}\n{moddle_import_code}"


def _require_pkg(resolver: NodeResolver, pkg: str) -> object:
    """Upstream ``requirePkg``: the required package, or ``None`` when unresolvable."""
    try:
        return resolver.require(pkg)
    except Exception:  # noqa: BLE001 - upstream returns null on failure
        return None


def _create_rule_import_statement(
    pkg: str,
    rule_name: str,
    idx: int,
    resolver: NodeResolver,
) -> str:
    """Upstream ``createRuleImportStatement``."""
    original_pkg = pkg

    pkg = resolver.normalize_pkg(pkg)

    pkg_export = _require_pkg(resolver, pkg)

    # (1) try resolving rule via $PKG.rules[$NAME]
    if pkg_export and _member(pkg_export, "rules"):
        rules = cast("dict[Any, Any]", _member(pkg_export, "rules"))

        if rule_name in rules:
            rule = rules[rule_name]

            if not is_string(rule):
                msg = (
                    f"failed to bundle rule <{rule_name}> from <{pkg}>: "
                    "illegal rule export (expected path reference)"
                )
                raise ValueError(msg)

            rule_path = _compute_rule_import(resolver, pkg, original_pkg, rule)

            return f"""
import rule_{idx} from '{rule_path}';

cache['{original_pkg}/{rule_name}'] = rule_{idx};"""

    # (2) resolve rule via $PKG/rules/$NAME
    return f"""
import rule_{idx} from '{pkg}/rules/{rule_name}';

cache['{original_pkg}/{rule_name}'] = rule_{idx};"""


def _create_moddle_extension_statement(key: str, import_path: object, idx: int) -> str:
    """Upstream ``createModdleExtensionStatement``."""
    if not isinstance(import_path, str):
        msg = f"illegal value for moddle-extension {key}: expected <string>"
        raise TypeError(msg)

    return f"""
import moddle_extension_{idx} from '{import_path}';

moddleExtensions['{key}'] = moddle_extension_{idx};"""


def _compute_rule_import(resolver: NodeResolver, pkg: str, original_pkg: str, rule: str) -> str:
    """Upstream ``computeRuleImport``."""
    # local reference, resolved relative to pkg location
    if rule.startswith("."):
        pkg_json_path: str = resolver.require.resolve(f"{pkg}/package.json")

        pkg_main_path: str = resolver.require.resolve(pkg)

        relative_pkg_main_path = posixpath.relpath(
            posixpath.dirname(pkg_main_path),
            posixpath.dirname(pkg_json_path),
        )

        return posixpath.normpath(f"{original_pkg}/{relative_pkg_main_path}/{rule}")

    # absolute reference
    return posixpath.normpath(rule)


def _member(instance: object, name: str) -> object:
    """Read ``name`` from a module-like object (dict entry or attribute)."""
    if isinstance(instance, dict):
        return instance.get(name)
    return getattr(instance, name, None)
