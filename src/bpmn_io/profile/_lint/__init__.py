# DESIGN R3.3 §6.4: `bpmn_io.profile.lint` (lot-1 bridge; re-exported by lot 2).
"""Profile lint bridge over the literal bpmnlint 11.15.0 port.

:func:`lint` evaluates one ``(phase, readiness_policy)`` stage against the
immutable input tree and returns the unified ``Result/1``. Until lot 2
lands, ``compiled`` carries the compiled lint data as plain JSON-compatible
dicts: ``compiledOptions`` (the seven closed keys, validated here against
the contract schema mirror in :mod:`transform`), ``validation`` (the
validation records to select the stage table from) and an optional
``registry`` (named ``plugin:<package>/<config>`` configs for ``extends``;
the pinned ``bpmnlint:recommended`` parent always comes from the literal
port). Profile identity and revision fields stay absent here: the caller
owning the input bytes (the CLI) patches them in, since identity is
omitted — never fabricated — when the loader has none (DESIGN R3.3 §10.1).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from bpmn_io.lint import Linter
from bpmn_io.moddle.base import ModdleElement
from bpmn_io.profile._lint.errors import (
    ConfigIncompleteError,
    ConfigUnknownError,
    ProfileDataError,
    ProfileLintError,
    RuleUnknownError,
)
from bpmn_io.profile._lint.index import build_id_index
from bpmn_io.profile._lint.report import adapter_entry, build_unified, to_jsonable
from bpmn_io.profile._lint.resolver import ProfileResolver
from bpmn_io.profile._lint.transform import (
    POLICIES,
    STAGES,
    build_transport_options,
    build_upstream_config,
    flatten_policy,
    select_record,
    split_rule_name,
    validate_compiled_options,
)

__all__ = ["lint"]

#: Operation name carried by the lint ``Result/1``.
OPERATION = "validate"

#: Closed report version carried by every lint report (DESIGN R3.3 §10.1).
REPORT_VERSION = "2"


def lint(
    envelope: ModdleElement,
    compiled: dict[str, Any],
    *,
    phase: str,
    readiness_policy: str,
) -> dict[str, Any]:
    """Lint the immutable ``envelope`` tree and return the unified ``Result/1``.

    ``envelope`` is the Definitions root (never mutated); ``phase`` is one
    of the five execution stages and ``readiness_policy`` is ``draft`` or
    ``accept``. Contradictory invocations (unknown stage/policy, a
    non-element envelope, malformed ``compiled`` or compiled options bound
    to another stage/policy) raise ``ValueError``. Domain failures (unknown
    lookups, extends cycles, incomplete tables, profile data violations)
    return a ``refused`` result with the stable adapter code. Wrong types
    raise ``TypeError``; wrong values (unknown stage/policy, options bound
    to another stage/policy) raise ``ValueError``.
    """
    if phase not in STAGES:
        msg = f"unknown lint phase: {phase!r}"
        raise ValueError(msg)
    if readiness_policy not in POLICIES:
        msg = f"unknown readiness policy: {readiness_policy!r}"
        raise ValueError(msg)
    try:
        return _lint(
            _require_envelope(envelope),
            _require_compiled(compiled),
            phase=phase,
            readiness_policy=readiness_policy,
        )
    except ProfileLintError as err:
        return _refused(err, phase=phase)


def _require_envelope(envelope: object) -> ModdleElement:
    """Narrow the envelope to its Definitions element (``TypeError`` otherwise)."""
    if not isinstance(envelope, ModdleElement):
        msg = f"envelope must be a moddle Definitions element, got {type(envelope).__name__}"
        raise TypeError(msg)
    return envelope


def _require_compiled(compiled: object) -> dict[str, Any]:
    """Narrow the compiled data to its object shape (``TypeError`` otherwise)."""
    if not isinstance(compiled, dict):
        msg = f"compiled must be an object, got {type(compiled).__name__}"
        raise TypeError(msg)
    return compiled


def _lint(
    envelope: ModdleElement,
    compiled: dict[str, Any],
    *,
    phase: str,
    readiness_policy: str,
) -> dict[str, Any]:
    """Implement :func:`lint` (domain errors propagate as unified entries)."""
    options = compiled.get("compiledOptions")
    if not isinstance(options, dict):
        msg = "compiled must carry a compiledOptions object"
        raise TypeError(msg)
    validation = compiled.get("validation")
    if not isinstance(validation, list):
        msg = "compiled must carry a validation array"
        raise TypeError(msg)
    registry = compiled.get("registry")
    if registry is not None and not isinstance(registry, Mapping):
        msg = "compiled registry must be an object when present"
        raise TypeError(msg)
    validate_compiled_options(options)
    if options["phase"] != phase or options["readinessPolicy"] != readiness_policy:
        msg = (
            "compiled options bind another stage/policy: "
            f"{options['phase']!r}/{options['readinessPolicy']!r} "
            f"(called for {phase!r}/{readiness_policy!r})"
        )
        raise ValueError(msg)
    record = select_record(validation, phase=phase, readiness_policy=readiness_policy)
    flattened = flatten_policy(record, registry)
    if options["severityPolicyDigest"] != flattened.severity_policy_digest:
        msg = "compiled severityPolicyDigest disagrees with the validation records"
        raise ProfileDataError(msg)
    _check_stage_rules(options["compiledRules"], flattened, phase=phase)
    transport_options = build_transport_options(options, flattened, options["compiledRules"])
    upstream_config = build_upstream_config(flattened, transport_options)
    resolver = ProfileResolver()
    _preresolve(upstream_config, resolver)
    linter = Linter(resolver=resolver)
    try:
        raw = linter.lint(envelope, upstream_config)
    except ValueError as err:
        raise _unknown_from_message(str(err)) from err
    except Exception as err:
        msg = f"lint evaluation failed: {err}"
        raise ProfileLintError(msg) from err
    index = build_id_index(envelope)
    policy = {**flattened.standard, **flattened.subrules}
    stage_rules = [
        rule
        for rule in options["compiledRules"]
        if isinstance(rule, dict) and rule.get("phase") == phase
    ]
    compiled_by_id = {f"profile:{rule['id']}": rule for rule in stage_rules}
    entries, counts = build_unified(
        raw, phase=phase, policy=policy, compiled_rules=compiled_by_id, index=index
    )
    return {
        "status": "ok",
        "operation": OPERATION,
        "report": {
            "reportVersion": REPORT_VERSION,
            "operation": OPERATION,
            "entries": entries,
            "rawStandardFindings": to_jsonable(raw),
            "idMap": [],
            "artifacts": [],
        },
        "payload": {"ok": counts["error"] == 0, "counts": counts},
    }


def _check_stage_rules(
    compiled_rules: Any,  # noqa: ANN401 - validated shape checked here
    flattened: Any,  # noqa: ANN401 - FlattenedPolicy
    *,
    phase: str,
) -> None:
    """Cross-check current-stage rules against the flattened subrule table.

    Every current-stage compiled rule needs its ``profile:<id>`` setting in
    this exact stage/policy table, and no setting may dangle (unknown rule
    ID or off-stage rule); both refuse ``lint-config-incomplete``.
    """
    if not isinstance(compiled_rules, list):
        msg = "compiledRules must be an array"
        raise ProfileDataError(msg)
    stage_ids = {
        rule["id"]
        for rule in compiled_rules
        if isinstance(rule, dict) and rule.get("phase") == phase
    }
    setting_ids = {
        name[len("profile:") :] for name in flattened.subrules if name.startswith("profile:")
    }
    missing = sorted(stage_ids - setting_ids)
    if missing:
        msg = f"stage <{phase}> rules miss profile settings: {missing}"
        raise ConfigIncompleteError(msg, detail={"missing": missing, "phase": phase})
    dangling = sorted(setting_ids - stage_ids)
    if dangling:
        msg = f"stage <{phase}> settings match no current-stage rule: {dangling}"
        raise ConfigIncompleteError(msg, detail={"dangling": dangling, "phase": phase})


def _preresolve(config: dict[str, Any], resolver: ProfileResolver) -> None:
    """Resolve and validate every configured factory before evaluation.

    Unknown rules refuse ``lint-rule-unknown`` here, before any rule runs,
    so a missing factory can never surface as a partial evaluation.
    """
    for name in config.get("rules", {}):
        pkg, rule_name = split_rule_name(name)
        try:
            factory = resolver.resolve_rule(pkg, rule_name)
        except Exception as err:
            raise RuleUnknownError(name) from err
        if factory is None:
            raise RuleUnknownError(name)


def _unknown_from_message(message: str) -> ProfileLintError:
    """Map a literal-port unknown lookup message to its stable adapter error."""
    if message.startswith("unknown config"):
        name = message[len("unknown config ") :].strip("<>")
        return ConfigUnknownError(name)
    if message.startswith("unknown rule"):
        name = message[len("unknown rule ") :].strip("<>")
        return RuleUnknownError(name)
    return ProfileLintError(message)


def _refused(err: ProfileLintError, *, phase: str) -> dict[str, Any]:
    """Build the ``refused`` Result/1 for an adapter error."""
    entry = adapter_entry(err.code, stage=phase, disposition="refused")
    return {
        "status": "refused",
        "operation": OPERATION,
        "code": err.code,
        "diagnostics": [str(err)],
        "report": {
            "reportVersion": REPORT_VERSION,
            "operation": OPERATION,
            "entries": [entry],
            "rawStandardFindings": {},
            "idMap": [],
            "artifacts": [],
        },
    }
