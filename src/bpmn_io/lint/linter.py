# Transposed from bpmn-io/bpmnlint@de71146 lib/linter.js (MIT).
"""The bpmnlint linter, transposed from ``lib/linter.js`` (sync per EVOL D4.1).

A rule definition is a plain dict ``{"check": check, "meta": {...}}`` where
``check`` is either a callable ``check(node, reporter)`` or a dict with
``enter``/``leave`` callables. A rule factory is a callable taking the
per-rule config and returning a rule definition. Reports are plain dicts
keyed as upstream (``id``, ``message``, ``path``, ``meta``, ``category``).
"""

from __future__ import annotations

import re
import sys
from typing import TYPE_CHECKING, Any, Protocol

from bpmn_io._js import UNDEFINED
from bpmn_io.lint.test_rule import test_rule

if TYPE_CHECKING:
    from collections.abc import Callable

    from bpmn_io.moddle.base import ModdleElement

__all__ = ["Linter", "Resolver"]


class Resolver(Protocol):
    """Structural type of rule/config resolvers (upstream ``Resolver``)."""

    def resolve_rule(self, pkg: str, rule_name: str) -> Callable[..., dict[str, Any]] | None:
        """Return the rule factory for ``pkg``/``rule_name``."""
        ...

    def resolve_config(self, pkg: str, config_name: str) -> dict[str, Any] | None:
        """Return the config dict for ``pkg``/``config_name``."""
        ...


def _noop_transform_rule(
    rule: dict[str, Any],
    options: dict[str, str],  # noqa: ARG001 - upstream signature
) -> dict[str, Any]:
    """Upstream ``noopTransformRule``: return the rule unchanged."""
    return rule


#: Upstream ``categoryMap``: numeric flags 0..3 (3 = info, BR02 plan note).
_CATEGORY_MAP: dict[str, str] = {
    "0": "off",
    "1": "warn",
    "2": "error",
    "3": "info",
}

#: Upstream ``ruleErrorCategory``.
_RULE_ERROR_CATEGORY = "rule-error"

_RULE_NAME_RE = re.compile(r"^(?:(?:(@[^/]+)/)?([^@]{1}[^/]*)/)?([^/]+)$")
_CONFIG_NAME_RE = re.compile(r"^(?:(?:plugin:(?:(@[^/]+)/)?([^@]{1}[^/]*)/)|bpmnlint:)([^/]+)$")
_PACKAGE_NAME_RE = re.compile(r"^(?:(@[^/]+)/)?([^/]+)$")


class Linter:
    """Lint a moddle root against a bpmnlint config (upstream ``Linter``)."""

    def __init__(
        self,
        options: dict[str, Any] | None = None,
        *,
        config: dict[str, Any] | None = None,
        resolver: Resolver | None = None,
        transform_rule: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        """Create a linter; ``resolver`` is required (upstream constructor contract)."""
        opts: dict[str, Any] = dict(options) if options else {}
        if config is not None:
            opts["config"] = config
        if resolver is not None:
            opts["resolver"] = resolver
        if transform_rule is not None:
            opts["transform_rule"] = transform_rule

        resolved_resolver = opts.get("resolver", UNDEFINED)
        if resolved_resolver is UNDEFINED:
            msg = "must provide <options.resolver>"
            raise ValueError(msg)

        self.config: dict[str, Any] = opts.get("config") or {}
        self.resolver: Resolver = resolved_resolver
        self.transform_rule: Callable[..., dict[str, Any]] = (
            opts.get("transform_rule") or opts.get("transformRule") or _noop_transform_rule
        )
        self.cached_rules: dict[str, dict[str, Any]] = {}
        self.cached_configs: dict[str, dict[str, Any]] = {}

    def apply_rule(
        self,
        moddle_root: ModdleElement,
        rule_definition: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Apply one resolved rule and annotate its reports (upstream ``applyRule``)."""
        rule: dict[str, Any] = rule_definition["rule"]
        category = rule_definition["category"]
        name = rule_definition["name"]

        try:
            reports = test_rule(moddle_root, rule)

            return [
                {
                    **report,
                    "meta": rule.get("meta", UNDEFINED),
                    "category": category,
                }
                for report in reports
            ]
        except Exception as err:  # noqa: BLE001 - upstream catches every rule failure
            sys.stderr.write(f"rule <{name}> failed with error:  {err}\n")
            return [
                {
                    "message": str(err),
                    "category": _RULE_ERROR_CATEGORY,
                },
            ]

    def resolve_rule(self, name: str, config: object = None) -> dict[str, Any]:
        """Resolve (and cache) the rule definition for ``name`` (upstream ``resolveRule``)."""
        parsed = self.parse_rule_name(name)
        pkg: str = parsed["pkg"]
        rule_name: str = parsed["rule_name"]

        cache_id = f"{pkg}-{rule_name}"

        rule = self.cached_rules.get(cache_id)
        if rule is not None:
            return rule

        rule_factory = self.resolver.resolve_rule(pkg, rule_name)

        if not rule_factory:
            msg = f"unknown rule <{name}>"
            raise ValueError(msg)

        resolved = self.transform_rule(
            rule_factory(config),
            {"pkg": pkg, "ruleName": rule_name},
        )
        self.cached_rules[cache_id] = resolved
        return resolved

    def resolve_config(self, name: str) -> dict[str, Any]:
        """Resolve (and cache) the config for ``name`` (upstream ``resolveConfig``)."""
        parsed = self.parse_config_name(name)
        pkg: str = parsed["pkg"]
        config_name: str = parsed["config_name"]

        cache_id = f"{pkg}-{config_name}"

        cached = self.cached_configs.get(cache_id)
        if cached is not None:
            return cached

        config = self.resolver.resolve_config(pkg, config_name)

        if not config:
            msg = f"unknown config <{name}>"
            raise ValueError(msg)

        actual_config = self.normalize_config(config, pkg)
        self.cached_configs[cache_id] = actual_config
        return actual_config

    def resolve_rules(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        """Resolve the enabled rule definitions of ``config`` (upstream ``resolveRules``)."""
        rules_config = self.resolve_configured_rules(config)

        parsed_rules: list[dict[str, Any]] = []
        for name, value in rules_config.items():
            parsed = self.parse_rule_value(value)
            parsed_rules.append(
                {
                    "name": name,
                    "category": parsed["category"],
                    "config": parsed["config"],
                },
            )

        enabled = [d for d in parsed_rules if d["category"] != "off"]

        return [
            {
                **definition,
                "rule": self.resolve_rule(definition["name"], definition["config"]),
            }
            for definition in enabled
        ]

    def resolve_configured_rules(self, config: dict[str, Any]) -> dict[str, Any]:
        """Resolve ``extends`` chains into one rules dict (upstream ``resolveConfiguredRules``)."""
        parents = config.get("extends", UNDEFINED)

        if isinstance(parents, str):
            parents = [parents]

        if parents is UNDEFINED or parents is None:
            parents = []

        rules: dict[str, Any] = {}
        for config_name in parents:
            parent_config = self.resolve_config(config_name)
            inherited = self.resolve_configured_rules(parent_config)
            rules = {**rules, **inherited}

        override_rules = self.normalize_config(config, "bpmnlint").get("rules", {})
        return {**rules, **override_rules}

    def lint(
        self,
        moddle_root: ModdleElement,
        config: dict[str, Any] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Lint ``moddle_root``; returns reports keyed by rule name (upstream ``lint``)."""
        effective_config = self.config if config is None else config

        rule_definitions = self.resolve_rules(effective_config)

        all_reports: dict[str, list[dict[str, Any]]] = {}

        for rule_definition in rule_definitions:
            name: str = rule_definition["name"]
            reports = self.apply_rule(moddle_root, rule_definition)

            if reports:
                all_reports[name] = reports

        return all_reports

    def parse_rule_value(self, value: object) -> dict[str, Any]:
        """Split a rule config value into ``category``/``config`` (upstream ``parseRuleValue``)."""
        if isinstance(value, (list, tuple)):
            category: object = value[0] if value else UNDEFINED
            rule_config: object = value[1] if len(value) > 1 else {}
        else:
            category = value
            rule_config = {}

        if isinstance(category, str):
            category = category.lower()

        category = _CATEGORY_MAP.get(str(category), category)

        return {
            "config": rule_config,
            "category": category,
        }

    def parse_rule_name(self, name: str, local_package: str = "bpmnlint") -> dict[str, str]:
        """Parse a rule name into ``pkg``/``rule_name`` (upstream ``parseRuleName``)."""
        match = _RULE_NAME_RE.match(name)

        if not match:
            msg = f"unparseable rule name <{name}>"
            raise ValueError(msg)

        ns, package_name, rule_name = match.groups()

        if not package_name:
            return {
                "pkg": local_package,
                "rule_name": rule_name,
            }

        pkg = f"{ns + '/' if ns else ''}{_prefix_package(package_name)}"

        return {
            "pkg": pkg,
            "rule_name": rule_name,
        }

    def parse_config_name(self, name: str) -> dict[str, str]:
        """Parse a config name into ``pkg``/``config_name`` (upstream ``parseConfigName``)."""
        match = _CONFIG_NAME_RE.match(name)

        if not match:
            msg = f"unparseable config name <{name}>"
            raise ValueError(msg)

        ns, package_name, config_name = match.groups()

        if not package_name:
            return {
                "pkg": "bpmnlint",
                "config_name": config_name,
            }

        pkg = f"{ns + '/' if ns else ''}{_prefix_package(package_name)}"

        return {
            "pkg": pkg,
            "config_name": config_name,
        }

    def get_simple_package_name(self, name: str) -> str:
        """Strip the ``bpmnlint-plugin-`` prefix (upstream ``getSimplePackageName``)."""
        match = _PACKAGE_NAME_RE.match(name)

        if not match:
            msg = f"unparseable package name <{name}>"
            raise ValueError(msg)

        ns, package_name = match.groups()

        return f"{ns + '/' if ns else ''}{_unprefix_package(package_name)}"

    def normalize_config(self, config: dict[str, Any], local_package: str) -> dict[str, Any]:
        """Validate and normalize rule names in ``config`` (upstream ``normalizeConfig``)."""
        rules = config.get("rules") or {}

        validated_rules: dict[str, Any] = {}
        for name, value in rules.items():
            parsed = self.parse_rule_name(name, local_package)
            pkg: str = parsed["pkg"]
            rule_name: str = parsed["rule_name"]

            normalized_name = (
                rule_name
                if pkg == "bpmnlint"
                else f"{self.get_simple_package_name(pkg)}/{rule_name}"
            )

            validated_rules[normalized_name] = value

        return {
            **config,
            "rules": validated_rules,
        }


def _prefix_package(pkg: str) -> str:
    """Upstream ``prefixPackage`` helper."""
    if pkg == "bpmnlint":
        return "bpmnlint"

    if pkg.startswith("bpmnlint-plugin-"):
        return pkg

    return f"bpmnlint-plugin-{pkg}"


def _unprefix_package(pkg: str) -> str:
    """Upstream ``unprefixPackage`` helper."""
    if pkg.startswith("bpmnlint-plugin-"):
        return pkg[len("bpmnlint-plugin-") :]

    return pkg
