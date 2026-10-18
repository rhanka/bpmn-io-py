# DESIGN R3.3 §6.1: the single executable profile plugin.
"""The ``bpmnlint-plugin-profile-mechanism`` plugin (rule ``profile``).

Business checks are declarative records interpreted by this single rule;
no executable rule is ever registered under a business ID. The rule
evaluates once at Definitions with a per-call guard and never mutates the
input moddle tree: evaluation only reads through element accessors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bpmn_io.profile._lint.errors import ProfileDataError
from bpmn_io.profile._lint.evaluate import EvaluationError, evaluate_rule

if TYPE_CHECKING:
    from bpmn_io.lint.test_rule import Reporter
    from bpmn_io.moddle.base import ModdleElement

__all__ = [
    "PLUGIN_NAME",
    "RULE_ID",
    "TRANSPORT_CATEGORY",
    "configs",
    "factory",
    "rules",
]

#: Registered plugin package name (entry-point name and whitelist key).
PLUGIN_NAME = "bpmnlint-plugin-profile-mechanism"

#: Fully qualified rule name used in upstream configs.
RULE_ID = "profile-mechanism/profile"

#: Transport category of the single generated registration: upstream must
#: never suppress a subfinding, so the transport is always ``error`` and the
#: adapter restores the exact per-subrule severity afterwards.
TRANSPORT_CATEGORY = "error"

#: Rule export map of the plugin (``rules`` member of the plugin object).
rules: dict[str, Any] = {}

#: Config export map of the plugin (no plugin configs in lot 1: ``extends``
#: targets resolve through the caller-supplied registry and the pinned host
#: manifests, never through plugin-owned configs).
configs: dict[str, Any] = {}


def _compiled_rules(config: Any) -> tuple[list[dict[str, Any]], str]:  # noqa: ANN401
    """Extract ``(compiledRules, phase)`` from the transport rule options."""
    if not isinstance(config, dict):
        msg = f"profile rule needs its compiled options object, got {type(config).__name__}"
        raise ProfileDataError(msg)
    required = (
        "mechanismVersion",
        "profileDigest",
        "phase",
        "readinessPolicy",
        "compiledRules",
        "bindings",
        "severityPolicyDigest",
    )
    missing = [key for key in required if key not in config]
    if missing:
        msg = f"profile rule misses compiled options keys: {sorted(missing)}"
        raise ProfileDataError(msg)
    compiled = config["compiledRules"]
    phase = config["phase"]
    if not isinstance(compiled, list) or not isinstance(phase, str):
        msg = "profile rule needs a compiledRules array and a phase string"
        raise ProfileDataError(msg)
    return compiled, phase


def factory(
    config: Any = None,  # noqa: ANN401 - upstream factory shape
    *,
    notions: dict[str, dict[str, Any]] | None = None,
    bindings: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
) -> dict[str, Any]:
    """Create the ``profile-mechanism/profile`` rule for ``compiledOptions``.

    The factory itself is immutable and safe to cache only without a stage
    context; every call returns a fresh rule instance with its own per-call
    guard, so ``A→B→A`` reuse of the factory can never leak options or
    findings between evaluations. ``notions`` and ``bindings`` supply the
    stage evaluation context (compiled notions, envelope support bindings);
    the lint bridge passes them through its resolver, never through the
    closed transport options.
    """
    context_notions = dict(notions) if notions else {}
    context_bindings = list(bindings) if bindings else []
    state = {"evaluated": False}

    def check(node: ModdleElement, reporter: Reporter) -> None:
        """Evaluate once at Definitions; ignore every other visited node."""
        if node is not reporter.moddle_root or state["evaluated"]:
            return
        state["evaluated"] = True
        try:
            compiled, phase = _compiled_rules(config)
            stage_rules = [
                rule for rule in compiled if isinstance(rule, dict) and rule.get("phase") == phase
            ]
            for rule in stage_rules:
                for finding in evaluate_rule(
                    rule,
                    reporter.moddle_root,
                    phase=phase,
                    notions=context_notions,
                    bindings=context_bindings,
                ):
                    report = finding.raw_report()
                    reporter.report(
                        report["id"],
                        report["message"],
                        {
                            key: report[key]
                            for key in ("profileRuleId", "code", "messageKey", "sourcePointer")
                        },
                    )
        except (EvaluationError, ProfileDataError) as err:
            reporter.report(None, str(err), {"profileRuleError": "evaluator"})
        except Exception as err:  # noqa: BLE001 - a rule failure must stay a finding
            reporter.report(None, f"profile rule failed: {err}", {"profileRuleError": "evaluator"})

    return {"check": check, "meta": {}}


rules["profile"] = factory
