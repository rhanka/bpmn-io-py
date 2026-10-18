# DESIGN R3.3 §6.3: exact configuration transform and generated outcomes.
"""Flatten profile validation records into upstream bpmnlint configs.

For one ``(stage, policy)`` pair, allowlisted ``extends`` entries and the
explicit validation ``settings`` flatten by whole-setting replacement
(depth-first, left-to-right, then local records; options are never
deep-merged). Numeric severities resolve to words, standard-rule coverage
is checked against the pinned recommended manifest, ``profile:<id>``
settings partition out of the upstream config, and the single transport
registration ``"profile-mechanism/profile": ["error", compiledOptions]``
carries the closed compiled options. ``severityPolicyDigest`` is
``H({phase, readinessPolicy, settings})`` over the fully flattened
effective setting array sorted by UTF-16 rule name (subrules included,
transport rule excluded).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Mapping

    from bpmn_io.lint.linter import Resolver

from bpmn_io.lint import Linter
from bpmn_io.lint.resolver import StaticResolver
from bpmn_io.profile._lint.c14n import digest, utf16_key
from bpmn_io.profile._lint.errors import (
    ConfigCycleError,
    ConfigIncompleteError,
    ConfigUnknownError,
    ProfileDataError,
)
from bpmn_io.profile._lint.plugin import RULE_ID as TRANSPORT_RULE_ID
from bpmn_io.profile._lint.plugin import TRANSPORT_CATEGORY
from bpmn_io.profile._lint.resolver import (
    HOST_PACKAGE,
    HOST_RECOMMENDED_CONFIG_NAME,
    PINNED_RULE_NAMES,
    recommended_rules,
)
from bpmn_io.profile._lint.severity import (
    CLASSIFICATIONS,
    normalize_severity,
    transport_severity,
)

__all__ = [
    "EXTENDS_PATTERN",
    "POLICIES",
    "STAGES",
    "FlattenedPolicy",
    "build_transport_options",
    "build_upstream_config",
    "flatten_policy",
    "select_record",
    "split_rule_name",
    "validate_compiled_options",
]

#: Execution stages (DESIGN R3.3 §6.2; draft/accept are policies, not stages).
STAGES = ("import", "pre-normalize", "post-normalize", "post-layout", "release")

#: Readiness policies.
POLICIES = ("draft", "accept")

#: Allowed ``extends`` syntaxes (DESIGN R3.3 §6.1); matched with
#: ``fullmatch`` on the anchor-stripped expression (spec §1.2).
EXTENDS_PATTERN = re.compile(
    r"(?:bpmnlint:recommended|plugin:[A-Za-z_][A-Za-z0-9_.-]*/[A-Za-z_][A-Za-z0-9_.-]*)"
)

#: Closed setting rule-name shape (pinned ``lintSetting`` pattern).
_RULE_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_.:/-]*")

#: Lowercase SHA-256 shape (pinned digest fields).
_DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}")

#: Canonical key of the pinned host config (raw and normalized spellings).
_PINNED_CONFIG_KEYS = frozenset(
    {
        f"{HOST_PACKAGE}:{HOST_RECOMMENDED_CONFIG_NAME}",
        f"{HOST_PACKAGE}/{HOST_RECOMMENDED_CONFIG_NAME}",
    }
)

#: Name parser reusing the literal port (never duplicated here). The cast is
#: safe: the parser instance only serves the pure ``parse_*`` helpers and
#: never resolves through the dummy resolver.
_NAME_PARSER = Linter(resolver=cast("Resolver", StaticResolver({})))


def split_rule_name(name: str) -> tuple[str, str]:
    """Split an upstream rule name into ``(package, rule)`` (port semantics)."""
    parsed = _NAME_PARSER.parse_rule_name(name)
    return parsed["pkg"], parsed["rule_name"]


@dataclass
class FlattenedPolicy:
    """The flattened effective policy of one ``(stage, policy)`` pair."""

    phase: str
    readiness_policy: str
    settings: list[dict[str, Any]] = field(default_factory=list)
    standard: dict[str, dict[str, str]] = field(default_factory=dict)
    subrules: dict[str, dict[str, str]] = field(default_factory=dict)
    severity_policy_digest: str = ""


def select_record(validation: Any, *, phase: str, readiness_policy: str) -> dict[str, Any]:  # noqa: ANN401
    """Select and validate the ``(phase, policy)`` validation record."""
    if not isinstance(validation, list) or not validation:
        msg = "compiled validation records must be a nonempty array"
        raise ProfileDataError(msg)
    matches = [
        record
        for record in validation
        if isinstance(record, dict)
        and record.get("id") == phase
        and record.get("policy") == readiness_policy
    ]
    if not matches:
        msg = f"no validation record for stage <{phase}> policy <{readiness_policy}>"
        raise ConfigIncompleteError(msg, detail={"phase": phase, "policy": readiness_policy})
    if len(matches) > 1:
        msg = f"duplicate validation record for stage <{phase}> policy <{readiness_policy}>"
        raise ProfileDataError(msg)
    return _validated_record(matches[0])


def _validated_record(record: dict[str, Any]) -> dict[str, Any]:
    """Validate the closed validation-record shape (pinned ``lintPhase``)."""
    expected = {"id", "extends", "settings", "profileRule", "policy"}
    keys = set(record.keys())
    if keys != expected:
        msg = f"validation record keys must be {sorted(expected)}, got {sorted(keys)}"
        raise ProfileDataError(msg)
    if record.get("id") not in STAGES:
        msg = f"invalid validation stage: {record.get('id')!r}"
        raise ProfileDataError(msg)
    if record.get("policy") not in POLICIES:
        msg = f"invalid validation policy: {record.get('policy')!r}"
        raise ProfileDataError(msg)
    if record.get("profileRule") != TRANSPORT_RULE_ID:
        msg = f"invalid profileRule: {record.get('profileRule')!r}"
        raise ProfileDataError(msg)
    extends = record.get("extends")
    if not isinstance(extends, list) or any(not isinstance(entry, str) for entry in extends):
        msg = "validation extends must be an array of strings"
        raise ProfileDataError(msg)
    for entry in extends:
        if EXTENDS_PATTERN.fullmatch(entry) is None:
            msg = f"forbidden extends syntax: {entry!r}"
            raise ProfileDataError(msg)
    settings = record.get("settings")
    if not isinstance(settings, list):
        msg = "validation settings must be an array"
        raise ProfileDataError(msg)
    return {
        "id": record["id"],
        "extends": list(extends),
        "settings": [_validated_setting(entry) for entry in settings],
        "profileRule": TRANSPORT_RULE_ID,
        "policy": record["policy"],
    }


def _validated_setting(entry: Any) -> dict[str, str]:  # noqa: ANN401
    """Validate the closed setting shape (pinned ``lintSetting``)."""
    if not isinstance(entry, dict) or set(entry.keys()) != {"rule", "severity", "classification"}:
        msg = f"setting keys must be rule/severity/classification, got {entry!r}"
        raise ProfileDataError(msg)
    rule = entry["rule"]
    if not isinstance(rule, str) or _RULE_PATTERN.fullmatch(rule) is None:
        msg = f"invalid setting rule: {rule!r}"
        raise ProfileDataError(msg)
    severity = normalize_severity(entry["severity"])
    classification = entry["classification"]
    if classification not in CLASSIFICATIONS:
        msg = f"invalid classification: {classification!r}"
        raise ProfileDataError(msg)
    return {"rule": rule, "severity": severity, "classification": classification}


def _canonical_config_key(name: str) -> str:
    """Normalize an ``extends`` entry to its ``pkg/name`` canonical key."""
    try:
        parsed = _NAME_PARSER.parse_config_name(name)
    except ValueError as err:
        msg = f"forbidden extends syntax: {name!r}"
        raise ProfileDataError(msg) from err
    return f"{parsed['pkg']}/{parsed['config_name']}"


def _registry_lookup(registry: Mapping[str, Any] | None, name: str) -> dict[str, Any] | None:
    """Look up an ``extends`` target in the caller registry (raw, then canonical).

    A missing entry resolves to ``None``; a lookup that raises (a
    Node-style thrown lookup) is caught by the caller and mapped to
    ``lint-config-unknown`` exactly like ``None``.
    """
    if registry is None:
        return None
    try:
        entry = registry[name]
    except KeyError:
        entry = None
    if entry is None:
        try:
            entry = registry[_canonical_config_key(name)]
        except KeyError:
            return None
    if entry is None:
        return None
    if not isinstance(entry, dict):
        msg = f"registry config <{name}> must be an object"
        raise ProfileDataError(msg)
    return entry


def _parent_extends(config: dict[str, Any], *, name: str) -> list[str]:
    """Read and validate the ``extends`` list of a parent config."""
    extends = config.get("extends", [])
    if isinstance(extends, str):
        extends = [extends]
    if not isinstance(extends, list) or any(not isinstance(entry, str) for entry in extends):
        msg = f"registry config <{name}> extends must be an array of strings"
        raise ProfileDataError(msg)
    for entry in extends:
        if EXTENDS_PATTERN.fullmatch(entry) is None:
            msg = f"forbidden extends syntax: {entry!r}"
            raise ProfileDataError(msg)
    return list(extends)


def _parent_rule_severity(rule_name: Any, value: Any, *, config_name: str) -> str:  # noqa: ANN401
    """Resolve one parent rule setting to its severity word (options reset)."""
    if not isinstance(rule_name, str) or _RULE_PATTERN.fullmatch(rule_name) is None:
        msg = f"invalid parent rule name: {rule_name!r}"
        raise ProfileDataError(msg)
    options: Any = None
    severity_value = value
    if isinstance(value, (list, tuple)):
        if len(value) == 0 or len(value) > 2:
            msg = f"invalid parent rule setting: {rule_name!r}"
            raise ProfileDataError(msg)
        options = value[1] if len(value) > 1 else None
        severity_value = value[0]
    severity = normalize_severity(severity_value)
    if options is not None and options != {}:
        msg = f"parent rule of <{config_name}> needs pinned per-rule schemas: {rule_name!r}"
        raise ProfileDataError(msg)
    return severity


def _parent_settings(config: Any, *, name: str) -> tuple[list[str], dict[str, str]]:  # noqa: ANN401
    """Split a parent config into ``(extends, rules)`` with resolved severities."""
    if not isinstance(config, dict):
        msg = f"registry config <{name}> must be an object"
        raise ProfileDataError(msg)
    extends = _parent_extends(config, name=name)
    rules = config.get("rules", {})
    if not isinstance(rules, dict):
        msg = f"registry config <{name}> rules must be an object"
        raise ProfileDataError(msg)
    resolved = {
        rule_name: _parent_rule_severity(rule_name, value, config_name=name)
        for rule_name, value in rules.items()
    }
    return extends, resolved


def flatten_policy(
    record: dict[str, Any],
    registry: Mapping[str, Any] | None = None,
) -> FlattenedPolicy:
    """Flatten one validated record to its effective policy (DESIGN §6.3).

    Allowlisted ``extends`` resolve depth-first, left-to-right, with an
    active recursion stack for cycle detection (``lint-config-cycle``);
    unknown targets refuse (``lint-config-unknown``) whether the lookup
    returns ``None`` or throws. Explicit settings replace whole inherited
    settings and reset options. Standard-rule coverage against the pinned
    recommended manifest must be complete with known classifications
    (``lint-config-incomplete`` otherwise).
    """
    phase = record["id"]
    policy = record["policy"]
    flat: dict[str, dict[str, str | None]] = {}
    _inherit(record["extends"], registry, flat, [f"{phase}/{policy}"])
    for setting in record["settings"]:
        flat[setting["rule"]] = {
            "severity": setting["severity"],
            "classification": setting["classification"],
        }
    missing = sorted(name for name in PINNED_RULE_NAMES if _unclassified(flat.get(name)))
    if missing:
        msg = f"standard-rule coverage misses classified settings: {missing}"
        raise ConfigIncompleteError(msg, detail={"missing": missing, "phase": phase})
    unclassified = sorted(
        name for name, entry in flat.items() if entry.get("classification") is None
    )
    if unclassified:
        msg = f"flattened settings miss classifications: {unclassified}"
        raise ConfigIncompleteError(msg, detail={"missing": unclassified, "phase": phase})
    settings = [_setting_row(name, entry) for name, entry in sorted(flat.items(), key=_flat_key)]
    standard = {
        name: _policy_row(entry) for name, entry in flat.items() if not name.startswith("profile:")
    }
    subrules = {
        name: _policy_row(entry) for name, entry in flat.items() if name.startswith("profile:")
    }
    return FlattenedPolicy(
        phase=phase,
        readiness_policy=policy,
        settings=settings,
        standard=standard,
        subrules=subrules,
        severity_policy_digest=digest(
            {"phase": phase, "readinessPolicy": policy, "settings": settings}
        ),
    )


def _unclassified(entry: dict[str, str | None] | None) -> bool:
    """Return whether a flattened entry still misses its classification."""
    return entry is None or entry.get("classification") is None


def _flat_key(item: tuple[str, dict[str, str | None]]) -> bytes:
    """Return the UTF-16 sort key of a flattened setting name."""
    return utf16_key(item[0])


def _setting_row(name: str, entry: dict[str, str | None]) -> dict[str, str]:
    """Render one flattened setting for the digest array (UTF-16 order outside)."""
    return {
        "rule": name,
        "severity": str(entry["severity"]),
        "classification": str(entry["classification"]),
    }


def _policy_row(entry: dict[str, str | None]) -> dict[str, str]:
    """Render one effective policy row (severity and classification words)."""
    return {
        "severity": str(entry["severity"]),
        "classification": str(entry["classification"]),
    }


def _shadows_pinned(registry: Mapping[str, Any], name: str, canonical: str) -> bool:
    """Return whether ``registry`` carries a pinned host config key."""
    for key in (name, canonical):
        try:
            present = key in registry
        except Exception as err:
            msg = f"registry rejects membership probe for <{key}>: {err}"
            raise ProfileDataError(msg) from err
        if present:
            return True
    return False


def _cycle_from(stack: list[str], name: str, canonical: str) -> list[str]:
    """Report the active extends cycle starting at the first revisit."""
    for position, entry in enumerate(stack):
        if position == 0:
            continue
        if entry == name or _canonical_config_key(entry) == canonical:
            return stack[position:]
    return [*stack[1:], name]


def _inherit(
    extends: list[str],
    registry: Mapping[str, Any] | None,
    flat: dict[str, dict[str, str | None]],
    stack: list[str],
) -> None:
    """Resolve ``extends`` depth-first, left-to-right into ``flat``."""
    for name in extends:
        canonical = _canonical_config_key(name)
        if any(entry == name or _canonical_config_key(entry) == canonical for entry in stack[1:]):
            raise ConfigCycleError(_cycle_from(stack, name, canonical))
        if name in _PINNED_CONFIG_KEYS or canonical in _PINNED_CONFIG_KEYS:
            if registry is not None and _shadows_pinned(registry, name, canonical):
                msg = f"registry must not shadow the pinned host config: {name!r}"
                raise ProfileDataError(msg)
            parent_extends: list[str] = []
            parent_rules = recommended_rules()
        else:
            try:
                config = _registry_lookup(registry, name)
            except ProfileDataError:
                raise
            except Exception as err:
                raise ConfigUnknownError(name) from err
            if config is None:
                raise ConfigUnknownError(name)
            parent_extends, parent_rules = _parent_settings(config, name=name)
        stack.append(name)
        try:
            _inherit(parent_extends, registry, flat, stack)
            for rule_name, severity in parent_rules.items():
                flat[rule_name] = {"severity": severity, "classification": None}
        finally:
            stack.pop()


def build_upstream_config(
    flattened: FlattenedPolicy, transport_options: dict[str, Any]
) -> dict[str, Any]:
    """Build the upstream rules object with the single transport registration.

    Standard severities travel with effective ``info`` sent as ``warn``
    (restored by the adapter); ``profile:<id>`` settings never enter the
    upstream config.
    """
    rules: dict[str, Any] = {}
    for name in sorted(flattened.standard.keys()):
        severity = flattened.standard[name]["severity"]
        rules[name] = transport_severity(severity)
    rules[TRANSPORT_RULE_ID] = [TRANSPORT_CATEGORY, transport_options]
    return {"rules": rules}


def build_transport_options(
    compiled_options: dict[str, Any],
    flattened: FlattenedPolicy,
    compiled_rules: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the validated transport options for the current stage/policy.

    Only enabled current-stage rules travel: ``off`` removes the subrule
    before evaluation, and other phases never evaluate here.
    """
    enabled = {name for name, row in flattened.subrules.items() if row["severity"] != "off"}
    selected = [
        rule
        for rule in compiled_rules
        if isinstance(rule, dict)
        and rule.get("phase") == flattened.phase
        and f"profile:{rule.get('id')}" in enabled
    ]
    options = dict(compiled_options)
    options["compiledRules"] = selected
    validate_compiled_options(options)
    return options


def validate_compiled_options(options: Any) -> dict[str, Any]:  # noqa: ANN401
    """Validate the closed compiled-options shape (pinned schema mirror).

    Exactly the seven keys ``mechanismVersion, profileDigest, phase,
    readinessPolicy, compiledRules, bindings, severityPolicyDigest``;
    unknown fields refuse. Returns the validated options.
    """
    expected = {
        "mechanismVersion",
        "profileDigest",
        "phase",
        "readinessPolicy",
        "compiledRules",
        "bindings",
        "severityPolicyDigest",
    }
    if not isinstance(options, dict) or set(options.keys()) != expected:
        msg = "compiled options must carry exactly the seven closed keys"
        raise ProfileDataError(msg)
    if options["mechanismVersion"] != "1":
        msg = f"unsupported mechanismVersion: {options['mechanismVersion']!r}"
        raise ProfileDataError(msg)
    for key in ("profileDigest", "severityPolicyDigest"):
        value = options[key]
        if not isinstance(value, str) or _DIGEST_PATTERN.fullmatch(value) is None:
            msg = f"invalid {key}: {value!r}"
            raise ProfileDataError(msg)
    if options["phase"] not in STAGES:
        msg = f"invalid compiled phase: {options['phase']!r}"
        raise ProfileDataError(msg)
    if options["readinessPolicy"] not in POLICIES:
        msg = f"invalid compiled readinessPolicy: {options['readinessPolicy']!r}"
        raise ProfileDataError(msg)
    _validated_rules_list(options["compiledRules"])
    _validated_bindings(options["bindings"])
    return options


def _validated_rules_list(rules: Any) -> None:  # noqa: ANN401 - JSON-dynamic input
    """Validate the compiled rules array (pinned ``rule`` required keys)."""
    if not isinstance(rules, list):
        msg = "compiledRules must be an array"
        raise ProfileDataError(msg)
    for rule in rules:
        _validated_compiled_rule(rule)


def _validated_bindings(bindings: Any) -> None:  # noqa: ANN401 - JSON-dynamic input
    """Validate the closed owner/role/target binding records."""
    if not isinstance(bindings, list):
        msg = "bindings must be an array"
        raise ProfileDataError(msg)
    for binding in bindings:
        if (
            not isinstance(binding, dict)
            or set(binding.keys()) != {"ownerId", "role", "targetId"}
            or not all(isinstance(binding[key], str) and binding[key] for key in binding)
        ):
            msg = f"invalid binding record: {binding!r}"
            raise ProfileDataError(msg)


def _validated_compiled_rule(rule: Any) -> None:  # noqa: ANN401
    """Validate one compiled rule record (pinned ``rule`` required keys)."""
    required = {"id", "phase", "select", "assert", "code", "message", "classification"}
    if not isinstance(rule, dict) or not required.issubset(set(rule.keys())):
        msg = f"compiled rule misses required keys: {rule!r}"
        raise ProfileDataError(msg)
    if not isinstance(rule["id"], str) or not rule["id"]:
        msg = f"compiled rule misses its string id: {rule!r}"
        raise ProfileDataError(msg)
    if rule["phase"] not in STAGES:
        msg = f"compiled rule has an invalid phase: {rule!r}"
        raise ProfileDataError(msg)
    if not isinstance(rule["select"], dict) or not isinstance(rule["assert"], dict):
        msg = f"compiled rule needs select/assert objects: {rule!r}"
        raise ProfileDataError(msg)
    if not isinstance(rule["code"], str) or not rule["code"]:
        msg = f"compiled rule misses its string code: {rule!r}"
        raise ProfileDataError(msg)
    if not isinstance(rule["message"], str) or not rule["message"]:
        msg = f"compiled rule misses its string message: {rule!r}"
        raise ProfileDataError(msg)
    if rule["classification"] not in CLASSIFICATIONS:
        msg = f"compiled rule has an invalid classification: {rule!r}"
        raise ProfileDataError(msg)
