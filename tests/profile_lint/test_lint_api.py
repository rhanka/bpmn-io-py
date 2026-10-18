"""The public lint bridge (DESIGN R3.3 section 6.4)."""

from __future__ import annotations

import json

import pytest

from bpmn_io.bpmn_moddle.simple import create_moddle
from bpmn_io.profile._lint import lint
from tests.profile_lint.helpers import (
    CLEAN_DOC,
    NAMED_TASK_DOC,
    Json,
    contract,
    make_compiled,
    parse,
)


def _compiled() -> dict[str, Json]:
    profile = contract("neutral-profile.json")
    assert isinstance(profile, dict)
    return make_compiled(profile, phase="post-normalize", readiness_policy="accept")


def test_ok_result_shape() -> None:
    """A clean document returns the exact success shape with zero counts."""
    result = lint(
        parse(CLEAN_DOC),
        _compiled(),
        phase="post-normalize",
        readiness_policy="accept",
    )
    assert result["status"] == "ok"
    assert result["operation"] == "validate"
    assert set(result) == {"status", "operation", "report", "payload"}
    report = result["report"]
    assert report["reportVersion"] == "2"
    assert report["operation"] == "validate"
    assert set(report) == {
        "reportVersion",
        "operation",
        "entries",
        "rawStandardFindings",
        "idMap",
        "artifacts",
    }
    assert report["idMap"] == []
    assert report["artifacts"] == []
    assert result["payload"] == {"ok": True, "counts": {"info": 0, "warn": 0, "error": 0}}


def test_findings_unify_with_policy_severity() -> None:
    """The unnamed task unifies under its policy row, raw transport preserved."""
    result = lint(
        parse(NAMED_TASK_DOC),
        _compiled(),
        phase="post-normalize",
        readiness_policy="accept",
    )
    assert result["status"] == "ok"
    assert result["payload"]["ok"] is False
    profile_entries = [
        entry for entry in result["report"]["entries"] if entry["ruleId"] == "profile:task-named"
    ]
    assert len(profile_entries) == 1
    (entry,) = profile_entries
    assert entry["code"] == "task-name-missing"
    assert entry["messageKey"] == "invalid"
    assert entry["severity"] == "error"
    assert entry["classification"] == "readiness"
    assert entry["source"]["pointer"] == "/rootElements/0/flowElements/0"
    raw = result["report"]["rawStandardFindings"]["profile-mechanism/profile"]
    assert raw[0]["category"] == "error"
    assert raw[0]["profileRuleId"] == "profile:task-named"


def test_invalid_invocations_raise() -> None:
    """Contradictory calls raise TypeError (types) or ValueError (values)."""
    profile = contract("neutral-profile.json")
    assert isinstance(profile, dict)
    root = parse(CLEAN_DOC)
    good = make_compiled(profile, phase="import", readiness_policy="draft")
    with pytest.raises(ValueError, match="unknown lint phase"):
        lint(root, good, phase="nope", readiness_policy="draft")
    with pytest.raises(ValueError, match="unknown readiness policy"):
        lint(root, good, phase="import", readiness_policy="maybe")
    with pytest.raises(TypeError, match="moddle Definitions element"):
        lint("xml", good, phase="import", readiness_policy="draft")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="compiled must be an object"):
        lint(root, [], phase="import", readiness_policy="draft")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="compiledOptions object"):
        lint(root, {"validation": []}, phase="import", readiness_policy="draft")
    mismatched = make_compiled(profile, phase="import", readiness_policy="draft")
    with pytest.raises(ValueError, match="another stage/policy"):
        lint(root, mismatched, phase="post-normalize", readiness_policy="accept")


def test_refused_paths_carry_stable_codes() -> None:
    """Unknown lookups, cycles and incomplete tables refuse with stable codes."""
    profile = contract("neutral-profile.json")
    assert isinstance(profile, dict)
    root = parse(CLEAN_DOC)
    unknown = make_compiled(profile, phase="post-normalize", readiness_policy="accept")
    unknown["validation"] = [
        {
            "id": "post-normalize",
            "extends": ["plugin:ghost/missing"],
            "settings": record_settings(profile, "post-normalize", "accept"),
            "profileRule": "profile-mechanism/profile",
            "policy": "accept",
        }
    ]
    refused = lint(root, unknown, phase="post-normalize", readiness_policy="accept")
    assert refused["status"] == "refused"
    assert refused["code"] == "lint-config-unknown"
    assert set(refused) == {"status", "operation", "code", "diagnostics", "report"}
    assert refused["report"]["entries"][0]["disposition"] == "refused"

    cyclic = make_compiled(
        profile,
        phase="post-normalize",
        readiness_policy="accept",
        registry={
            "plugin:cycle/a": {"extends": ["plugin:cycle/b"]},
            "plugin:cycle/b": {"extends": ["plugin:cycle/a"]},
        },
    )
    cyclic["validation"] = [
        {
            "id": "post-normalize",
            "extends": ["plugin:cycle/a"],
            "settings": record_settings(profile, "post-normalize", "accept"),
            "profileRule": "profile-mechanism/profile",
            "policy": "accept",
        }
    ]
    refused = lint(root, cyclic, phase="post-normalize", readiness_policy="accept")
    assert refused["code"] == "lint-config-cycle"
    assert refused["report"]["entries"][0]["ruleId"] == "adapter"


def record_settings(profile: dict[str, Json], phase: str, policy: str) -> list[Json]:
    """Return the raw settings of one validation record."""
    assert isinstance(profile.get("validation"), list)
    for record in profile["validation"]:
        assert isinstance(record, dict)
        if record.get("id") == phase and record.get("policy") == policy:
            settings = record.get("settings")
            assert isinstance(settings, list)
            return settings
    msg = "missing fixture record"
    raise AssertionError(msg)


def test_alternating_profiles_do_not_leak() -> None:
    """A->B->A evaluations keep their own options; inputs stay immutable."""
    profile = contract("neutral-profile.json")
    assert isinstance(profile, dict)
    accept = make_compiled(profile, phase="post-normalize", readiness_policy="accept")
    draft = make_compiled(profile, phase="post-normalize", readiness_policy="draft")
    snapshot = json.dumps(accept, sort_keys=True)
    first = lint(parse(NAMED_TASK_DOC), accept, phase="post-normalize", readiness_policy="accept")
    middle = lint(parse(NAMED_TASK_DOC), draft, phase="post-normalize", readiness_policy="draft")
    again = lint(parse(NAMED_TASK_DOC), accept, phase="post-normalize", readiness_policy="accept")
    assert json.dumps(accept, sort_keys=True) == snapshot
    assert first["payload"] == again["payload"]
    assert first["payload"] != middle["payload"]
    first_rules = {entry["ruleId"]: entry["severity"] for entry in first["report"]["entries"]}
    middle_rules = {entry["ruleId"]: entry["severity"] for entry in middle["report"]["entries"]}
    assert first_rules["profile:task-named"] == "error"
    assert middle_rules["profile:task-named"] == "warn"


def test_envelope_never_mutates() -> None:
    """Linting never mutates the input tree (byte-identical serialization)."""
    model = create_moddle()
    root = model.from_xml(NAMED_TASK_DOC).root_element
    before = model.to_xml(root)
    lint(
        root,
        _compiled(),
        phase="post-normalize",
        readiness_policy="accept",
    )
    assert model.to_xml(root) == before


def test_digest_mismatch_refuses() -> None:
    """Compiled options disagreeing with the records refuse (no injection)."""
    compiled = _compiled()
    assert isinstance(compiled["compiledOptions"], dict)
    compiled["compiledOptions"] = {
        **compiled["compiledOptions"],
        "severityPolicyDigest": "f" * 64,
    }
    refused = lint(parse(CLEAN_DOC), compiled, phase="post-normalize", readiness_policy="accept")
    assert refused["status"] == "refused"
    assert refused["code"] == "profile-schema"


def _prefixed_profile() -> dict[str, Json]:
    """Neutral profile plus one valid textPrefix rule and its setting."""
    profile = contract("neutral-profile.json")
    assert isinstance(profile, dict)
    rule: dict[str, Json] = {
        "id": "task-prefixed",
        "phase": "post-normalize",
        "select": {
            "from": "root",
            "via": "all",
            "where": {
                "op": "typeIs",
                "binding": "self",
                "type": "bpmn:Task",
                "mode": "exact",
            },
            "order": "id",
        },
        "assert": {
            "op": "textPrefix",
            "value": {"op": "read", "binding": "self", "path": "/name"},
            "prefix": "R",
            "trim": "none",
        },
        "code": "task-prefix-missing",
        "message": "invalid",
        "classification": "readiness",
    }
    rules = [*(profile["rules"] if isinstance(profile["rules"], list) else []), rule]
    validation = profile["validation"]
    assert isinstance(validation, list)
    records = []
    for entry in validation:
        assert isinstance(entry, dict)
        patched = entry
        if entry.get("id") == "post-normalize" and entry.get("policy") == "accept":
            settings = [*entry["settings"]] if isinstance(entry.get("settings"), list) else []
            settings.append(
                {
                    "rule": "profile:task-prefixed",
                    "severity": "error",
                    "classification": "readiness",
                }
            )
            patched = {**entry, "settings": settings}
        records.append(patched)
    return {**profile, "rules": rules, "validation": records}


def test_text_prefix_rule_evaluates_end_to_end() -> None:
    """A valid textPrefix rule evaluates instead of refusing lint-rule-error."""
    compiled = make_compiled(_prefixed_profile(), phase="post-normalize", readiness_policy="accept")
    result = lint(
        parse(NAMED_TASK_DOC), compiled, phase="post-normalize", readiness_policy="accept"
    )
    assert result["status"] == "ok"
    entries = result["report"]["entries"]
    assert [entry["code"] for entry in entries if entry["ruleId"] == "adapter"] == []
    prefixed = [entry for entry in entries if entry["ruleId"] == "profile:task-prefixed"]
    assert [(entry["code"], entry["source"]["targetId"]) for entry in prefixed] == [
        ("task-prefix-missing", "Task_A")
    ]


def test_compiled_profile_path_matches_transport() -> None:
    """lint() over compile_profile output agrees with the transport dicts."""
    from bpmn_io.profile import compile_profile, load_profile

    root = parse(NAMED_TASK_DOC)
    profile = contract("neutral-profile.json")
    assert isinstance(profile, dict)
    expected = lint(root, _compiled(), phase="post-normalize", readiness_policy="accept")
    schema = contract("profile-mechanism-1.schema.json")
    import json as _json

    loaded = load_profile(
        _json.dumps(profile).encode("utf-8"),
        schema_bytes=_json.dumps(schema).encode("utf-8"),
    )
    assert loaded.status == "ok"
    assert isinstance(loaded.payload, object)
    compiled_result = compile_profile(loaded.payload)  # type: ignore[arg-type]
    assert compiled_result.status == "ok"
    actual = lint(
        root,
        compiled_result.payload,  # type: ignore[arg-type]
        phase="post-normalize",
        readiness_policy="accept",
    )
    assert actual["status"] == "ok"
    assert actual["payload"] == expected["payload"]
    assert actual["report"]["entries"] == expected["report"]["entries"]
