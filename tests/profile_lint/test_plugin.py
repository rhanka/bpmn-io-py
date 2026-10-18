"""The single executable profile plugin (DESIGN R3.3 section 6.1)."""

from __future__ import annotations

from bpmn_io.bpmn_moddle.simple import create_moddle
from bpmn_io.lint import Linter
from bpmn_io.lint.resolver import StaticResolver
from bpmn_io.profile._lint import plugin
from bpmn_io.profile._lint.plugin import RULE_ID, TRANSPORT_CATEGORY, factory
from bpmn_io.profile._lint.resolver import ProfileResolver
from tests.profile_lint.helpers import CLEAN_DOC, NAMED_TASK_DOC, contract, parse


def _options(phase: str = "post-normalize") -> dict[str, object]:
    profile = contract("neutral-profile.json")
    assert isinstance(profile, dict)
    rules = [rule for rule in profile["rules"] if rule["phase"] == phase]
    return {
        "mechanismVersion": "1",
        "profileDigest": "0" * 64,
        "phase": phase,
        "readinessPolicy": "accept",
        "compiledRules": rules,
        "bindings": [],
        "severityPolicyDigest": "0" * 64,
    }


def test_plugin_exports() -> None:
    """The plugin exposes the single rule and no configs."""
    assert RULE_ID == "profile-mechanism/profile"
    assert TRANSPORT_CATEGORY == "error"
    assert set(plugin.rules) == {"profile"}
    assert plugin.configs == {}
    assert plugin.rules["profile"] is factory


def test_rule_evaluates_once_at_definitions() -> None:
    """One evaluation per lint call no matter how many nodes traverse visits."""
    linter = Linter(resolver=StaticResolver({"rule:bpmnlint/label-required": factory}))
    reports = linter.lint(
        parse(NAMED_TASK_DOC), {"rules": {"label-required": ["error", _options()]}}
    )
    profile_reports = reports.get("label-required", [])
    assert len(profile_reports) == 1
    assert profile_reports[0]["profileRuleId"] == "profile:task-named"


def test_fresh_instances_per_evaluation() -> None:
    """A->B->A reuse of the factory never leaks options or findings."""
    first = factory(_options())
    assert first is not factory(_options())
    resolver = ProfileResolver()
    for _ in range(2):
        linter = Linter(resolver=resolver)
        reports = linter.lint(
            parse(NAMED_TASK_DOC),
            {
                "rules": {
                    "profile-mechanism/profile": [
                        "error",
                        _options(),
                    ]
                }
            },
        )
        assert len(reports["profile-mechanism/profile"]) == 1


def test_rule_never_mutates_moddle() -> None:
    """Evaluation only reads: the serialized tree is identical afterwards."""
    model = create_moddle()
    root = model.from_xml(CLEAN_DOC).root_element
    before = model.to_xml(root)
    linter = Linter(resolver=ProfileResolver())
    linter.lint(
        root,
        {"rules": {"profile-mechanism/profile": ["error", _options()]}},
    )
    assert model.to_xml(root) == before


def test_rule_failure_stays_a_finding() -> None:
    """An assertion that cannot evaluate becomes a rule-error report, not a crash."""
    profile = contract("neutral-profile.json")
    assert isinstance(profile, dict)
    broken = [dict(rule) for rule in profile["rules"] if rule["phase"] == "post-normalize"]
    broken[0]["assert"] = {"op": "frobnicate"}
    options = {**_options(), "compiledRules": broken}
    linter = Linter(resolver=StaticResolver({"rule:bpmnlint/label-required": factory}))
    reports = linter.lint(parse(CLEAN_DOC), {"rules": {"label-required": ["error", options]}})
    assert reports["label-required"][0]["profileRuleError"] == "evaluator"


def test_off_stage_rules_do_not_evaluate() -> None:
    """Rules of another phase never evaluate, even when transported."""
    options = _options(phase="post-normalize")
    assert isinstance(options["compiledRules"], list)
    options["compiledRules"] = [{**rule, "phase": "import"} for rule in options["compiledRules"]]
    linter = Linter(resolver=StaticResolver({"rule:bpmnlint/label-required": factory}))
    reports = linter.lint(parse(NAMED_TASK_DOC), {"rules": {"label-required": ["error", options]}})
    assert reports.get("label-required", []) == []
