"""Unified report entries (DESIGN R3.3 section 6.4 and section 10.1)."""

from __future__ import annotations

from bpmn_io.profile._lint.report import (
    adapter_entry,
    build_unified,
    merge_key,
    profile_entry,
    sort_entries,
    to_jsonable,
)


def _policy() -> dict[str, dict[str, str]]:
    return {
        "label-required": {"severity": "error", "classification": "readiness"},
        "ad-hoc-sub-process": {"severity": "info", "classification": "advisory"},
        "profile:ready-check": {"severity": "warn", "classification": "readiness"},
    }


def _compiled() -> dict[str, dict[str, object]]:
    return {
        "profile:ready-check": {
            "id": "ready-check",
            "phase": "post-normalize",
            "code": "ready-missing",
            "message": "ready.missing",
        }
    }


def _index() -> dict[str, str]:
    return {"Task_1": "/rootElements/0/flowElements/0"}


def test_pointer_escaping_and_append() -> None:
    """Reported IDs resolve and escaped segments append (corpus vectors)."""
    entries, _ = build_unified(
        {"label-required": [{"id": "Task_1", "message": "m", "path": ["a~b", "c/d", 0]}]},
        phase="post-normalize",
        policy=_policy(),
        compiled_rules={},
        index=_index(),
        known_pointers=set(),
    )
    (entry,) = entries
    assert entry["source"]["pointer"] == "/rootElements/0/flowElements/0/a~0b/c~1d/0"
    assert entry["source"]["provenance"] == "exact"
    assert entry["source"]["targetId"] == "Task_1"


def test_unresolvable_id_yields_unavailable() -> None:
    """Unknown IDs and empty paths yield null pointers, never fabricated roots."""
    entries, _ = build_unified(
        {"label-required": [{"id": "ghost", "message": "m", "path": []}]},
        phase="post-normalize",
        policy=_policy(),
        compiled_rules={},
        index=_index(),
        known_pointers=set(),
    )
    (entry,) = entries
    assert entry["source"]["pointer"] is None
    assert entry["source"]["provenance"] == "unavailable"
    assert entry["source"]["targetId"] == "ghost"


def test_absolute_pointer_passthrough() -> None:
    """Generic producers may supply an already absolute pointer that exists."""
    entries, _ = build_unified(
        {
            "label-required": [
                {"id": None, "message": "m", "path": "/rootElements/0/flowElements/0"}
            ]
        },
        phase="post-normalize",
        policy=_policy(),
        compiled_rules={},
        index=_index(),
        known_pointers=set(_index().values()),
    )
    (entry,) = entries
    assert entry["source"]["pointer"] == "/rootElements/0/flowElements/0"
    assert entry["source"]["provenance"] == "exact"


def test_absolute_pointer_missing_refused() -> None:
    """A well-formed but unknown absolute pointer stays unavailable."""
    entries, _ = build_unified(
        {"label-required": [{"id": None, "message": "m", "path": "/abs/pointer"}]},
        phase="post-normalize",
        policy=_policy(),
        compiled_rules={},
        index=_index(),
        known_pointers=set(),
    )
    (entry,) = entries
    assert entry["source"]["pointer"] is None
    assert entry["source"]["provenance"] == "unavailable"


def test_standard_identity_and_severity() -> None:
    """Standard findings keep rule identity with the effective policy row."""
    entries, counts = build_unified(
        {"label-required": [{"id": "Task_1", "message": "m", "category": "warn"}]},
        phase="post-normalize",
        policy=_policy(),
        compiled_rules={},
        index=_index(),
        known_pointers=set(),
    )
    (entry,) = entries
    assert entry["ruleId"] == "label-required"
    assert entry["code"] == "bpmnlint/label-required"
    assert entry["messageKey"] == "bpmnlint.label-required"
    assert entry["severity"] == "error"
    assert entry["classification"] == "readiness"
    assert entry["disposition"] == "observed"
    assert counts == {"info": 0, "warn": 0, "error": 1}


def test_info_restored_from_warn_transport() -> None:
    """Effective info survives the warn transport in unified entries."""
    entries, counts = build_unified(
        {"ad-hoc-sub-process": [{"id": "Task_1", "message": "m", "category": "warn"}]},
        phase="import",
        policy=_policy(),
        compiled_rules={},
        index=_index(),
        known_pointers=set(),
    )
    (entry,) = entries
    assert entry["severity"] == "info"
    assert counts == {"info": 1, "warn": 0, "error": 0}


def test_profile_entry_and_transport() -> None:
    """Profile subfindings restore warn from the error transport (corpus vector)."""
    raw = {
        "profile-mechanism/profile": [
            {
                "id": "Task_1",
                "message": "ready.missing",
                "profileRuleId": "profile:ready-check",
                "code": "ready-missing",
                "messageKey": "ready.missing",
                "sourcePointer": "/rootElements/0/flowElements/0",
            }
        ]
    }
    entries, counts = build_unified(
        raw, phase="post-normalize", policy=_policy(), compiled_rules=_compiled(), index=_index()
    )
    (entry,) = entries
    assert entry["ruleId"] == "profile:ready-check"
    assert entry["code"] == "ready-missing"
    assert entry["messageKey"] == "ready.missing"
    assert entry["severity"] == "warn"
    assert entry["classification"] == "readiness"
    assert counts == {"info": 0, "warn": 1, "error": 0}


def test_profile_metadata_violations_are_rule_errors() -> None:
    """Missing or mismatched subfinding metadata is lint-rule-error."""
    bad_reports = [
        {"id": "Task_1", "message": "m"},
        {"id": "Task_1", "message": "m", "profileRuleError": "evaluator"},
        {
            "id": "Task_1",
            "message": "m",
            "profileRuleId": "profile:ready-check",
            "code": "other-code",
            "messageKey": "ready.missing",
            "sourcePointer": "/rootElements/0/flowElements/0",
        },
        {
            "id": "Task_1",
            "message": "m",
            "profileRuleId": "profile:ready-check",
            "code": "ready-missing",
            "messageKey": "ready.missing",
            "sourcePointer": "/elsewhere",
        },
        "not-a-report",
    ]
    for bad in bad_reports:
        (entry,) = build_unified(
            {"profile-mechanism/profile": [bad]},  # type: ignore[list-item]
            phase="post-normalize",
            policy=_policy(),
            compiled_rules=_compiled(),
            index=_index(),
        )[0]
        assert entry["ruleId"] == "adapter"
        assert entry["code"] == "lint-rule-error"
        assert entry["messageKey"] == "lint-rule-error"
        assert entry["severity"] == "error"
    entries, _ = build_unified(
        {"profile-mechanism/profile": bad_reports},  # type: ignore[list-item]
        phase="post-normalize",
        policy=_policy(),
        compiled_rules=_compiled(),
        index=_index(),
    )
    assert len(entries) == 1


def test_entries_sort_by_execution_stage_order() -> None:
    """Cross-stage entries follow the §6.2 execution order, not alphabet."""
    from bpmn_io.profile._lint.report import standard_entry as _standard

    late = _standard(
        rule_name="label-required",
        severity="error",
        classification="readiness",
        stage="post-layout",
        pointer="/p",
        target_id="Task_1",
        provenance="exact",
    )
    early = _standard(
        rule_name="label-required",
        severity="error",
        classification="readiness",
        stage="pre-normalize",
        pointer="/p",
        target_id="Task_1",
        provenance="exact",
    )
    ordered = sort_entries([late, early], ["standard", "standard"])
    assert [entry["stage"] for entry in ordered] == ["pre-normalize", "post-layout"]


def test_rule_error_category_maps_to_adapter() -> None:
    """A standard rule that threw becomes an adapter lint-rule-error."""
    entries, _ = build_unified(
        {"label-required": [{"message": "boom", "category": "rule-error"}]},
        phase="post-normalize",
        policy=_policy(),
        compiled_rules={},
        index=_index(),
    )
    (entry,) = entries
    assert entry["ruleId"] == "adapter"
    assert entry["code"] == "lint-rule-error"


def test_merge_dedupes_and_sorts_utf16() -> None:
    """Exact duplicates coalesce; entries sort in UTF-16 order."""
    first = profile_entry(
        profile_rule_id="profile:b",
        code="c",
        message_key="m",
        severity="warn",
        classification="readiness",
        stage="post-normalize",
        pointer="/p",
        target_id="\ue000",
        provenance="exact",
    )
    second = profile_entry(
        profile_rule_id="profile:b",
        code="c",
        message_key="m",
        severity="warn",
        classification="readiness",
        stage="post-normalize",
        pointer="/p",
        target_id="\U00010000",
        provenance="exact",
    )
    assert merge_key(first, "profile") != merge_key(second, "profile")
    ordered = sort_entries([first, second], ["profile", "profile"])
    assert [entry["source"]["targetId"] for entry in ordered] == ["\U00010000", "\ue000"]
    assert merge_key(first, "profile") == merge_key(dict(first), "profile")
    raw_subfinding = {
        "id": "Task_1",
        "message": "c",
        "profileRuleId": "profile:b",
        "code": "c",
        "messageKey": "m",
        "sourcePointer": "/p",
    }
    entries, _ = build_unified(
        {"profile-mechanism/profile": [raw_subfinding, dict(raw_subfinding)]},
        phase="post-normalize",
        policy={"profile:b": {"severity": "warn", "classification": "readiness"}},
        compiled_rules={"profile:b": {"code": "c", "message": "m"}},
        index={"Task_1": "/p"},
    )
    assert len(entries) == 1


def test_adapter_entry_shape() -> None:
    """Adapter entries carry the stable code as code and message key."""
    entry = adapter_entry("lint-config-cycle", stage="import", disposition="refused")
    assert entry["ruleId"] == "adapter"
    assert entry["code"] == "lint-config-cycle"
    assert entry["messageKey"] == "lint-config-cycle"
    assert entry["severity"] == "error"
    assert entry["classification"] == "integrity"
    assert entry["source"]["domain"] == "none"
    assert entry["source"]["pointer"] is None


def test_to_jsonable_drops_undefined() -> None:
    """Raw findings serialize with JSON.stringify semantics."""
    from bpmn_io._js import UNDEFINED

    assert to_jsonable({"a": UNDEFINED, "b": [UNDEFINED, 1]}) == {"b": [None, 1]}
