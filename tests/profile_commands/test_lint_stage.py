"""Focused lint-stage tests for the section-4.8 pipeline (lot 5).

Covers the draft lint mapping of harmonization B12 (bare rule id, the
unavailable result coordinate, transport exclusion), the pre/post
blocking rules of steps 7 and 9, and the section-4.9 entry order. The
compiled profile reuses the sealed neutral predicates with patched
policy rows; no sealed expectation is involved.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bpmn_io.profile._compiler import CompiledProfile
from bpmn_io.profile._transaction import (
    ApplyError,
    _blocking_code,
    _fix_parents,
    _lint_stage,
    _moddle_of_tree,
    _run_normalize,
    lot5_entry_order_key,
    sort_lot5_entries,
)

_NEUTRAL_PROFILE = json.loads(
    Path("tests/profile_commands/expected/artifacts/profiles/neutral-lot5.json").read_text(
        encoding="utf-8"
    )
)

_TASK_RULES = {
    rule["id"]: rule
    for rule in _NEUTRAL_PROFILE["rules"]
    if rule["id"] in ("task-named", "task-named-pre-normalize")
}

_DRAFT_RECORDS = tuple(
    record
    for record in _NEUTRAL_PROFILE["validation"]
    if record["id"] in ("pre-normalize", "post-normalize") and record["policy"] == "draft"
)

_UNNAMED_TASK_TREE = {
    "$type": "bpmn:Definitions",
    "id": "D_1",
    "targetNamespace": "urn:x",
    "rootElements": [
        {
            "$type": "bpmn:Process",
            "id": "P_1",
            "flowElements": [{"$type": "bpmn:Task", "id": "T_1"}],
        }
    ],
}


def _compiled(pre_row: dict[str, str], post_row: dict[str, str]) -> CompiledProfile:
    """Build one synthetic compiled profile with patched draft policy rows."""
    records = copy.deepcopy(list(_DRAFT_RECORDS))
    for record in records:
        wanted = pre_row if record["id"] == "pre-normalize" else post_row
        settings = [dict(entry) for entry in record["settings"]]
        record["settings"] = [
            entry
            for entry in settings
            if not str(entry.get("rule", "")).startswith("profile:task-named")
        ]
        record["settings"].append(dict(wanted))
    return CompiledProfile(
        profile_digest="ab" * 32,
        notions={},
        recipes={},
        rules=copy.deepcopy(_TASK_RULES),
        descriptor_digest="ab" * 32,
        registry_digest="ab" * 32,
        validation=tuple(records),
        ui=None,
    )


def _warn_readiness(rule: str) -> dict[str, str]:
    """Return one warn/readiness draft policy row for a profile subrule."""
    return {"classification": "readiness", "rule": rule, "severity": "warn"}


def _error_integrity(rule: str) -> dict[str, str]:
    """Return one error/integrity draft policy row for a profile subrule."""
    return {"classification": "integrity", "rule": rule, "severity": "error"}


def _error_repairable(rule: str) -> dict[str, str]:
    """Return one error/repairable draft policy row for a profile subrule."""
    return {"classification": "repairable", "rule": rule, "severity": "error"}


def _named_tree() -> dict[str, object]:
    """Return the stage tree with the task name repaired."""
    tree = copy.deepcopy(_UNNAMED_TASK_TREE)
    root = tree["rootElements"]
    assert isinstance(root, list)
    process = root[0]
    assert isinstance(process, dict)
    flows = process["flowElements"]
    assert isinstance(flows, list)
    task = flows[0]
    assert isinstance(task, dict)
    task["name"] = "N"
    return tree


def test_pre_normalize_maps_bare_rule_coordinates() -> None:
    """The draft lint entry carries the bare rule id and B12 coordinates."""
    compiled = _compiled(
        _warn_readiness("profile:task-named-pre-normalize"),
        _warn_readiness("profile:task-named"),
    )
    entries, raw = _lint_stage(compiled, copy.deepcopy(_UNNAMED_TASK_TREE), [], "pre-normalize")
    assert len(entries) == 1
    (entry,) = entries
    assert entry["ruleId"] == "task-named-pre-normalize"
    assert entry["code"] == "task-name-missing-pre-normalize"
    assert entry["messageKey"] == "invalid"
    assert entry["severity"] == "warn"
    assert entry["classification"] == "readiness"
    assert entry["stage"] == "pre-normalize"
    assert entry["disposition"] == "observed"
    source = entry["source"]
    assert isinstance(source, dict)
    assert source["domain"] == "tree"
    assert source["targetId"] == "T_1"
    assert source["provenance"] == "exact"
    pointer = source["pointer"]
    assert isinstance(pointer, str)
    assert pointer.startswith("/")
    assert entry["result"] == {
        "domain": "none",
        "pointer": None,
        "targetId": None,
        "provenance": "unavailable",
    }
    assert entry["beforePresent"] is False
    assert entry["afterPresent"] is False
    assert raw == []


def test_post_normalize_error_entry_blocks_with_its_code() -> None:
    """A surviving post-normalize error refuses with the subrule code."""
    compiled = _compiled(
        _warn_readiness("profile:task-named-pre-normalize"),
        _error_integrity("profile:task-named"),
    )
    c_envelope: dict[str, object] = {
        "tree": copy.deepcopy(_UNNAMED_TASK_TREE),
        "bindings": [],
    }

    def _normalize(
        _compiled: object, _envelope: object, _support: object, activation: str = "edit"
    ) -> SimpleNamespace:
        assert activation == "edit"
        return SimpleNamespace(
            status="ok",
            payload={
                "envelope": {
                    "tree": copy.deepcopy(_UNNAMED_TASK_TREE),
                    "bindings": [],
                    "semanticRevision": "rev-n",
                },
                "report": {"entries": []},
            },
        )

    with pytest.raises(ApplyError) as excinfo:
        _run_normalize(
            {"normalize": _normalize},
            compiled,
            c_envelope,
            [],
            None,
            lambda: False,
            [],
        )
    assert excinfo.value.code == "task-name-missing"
    assert [entry["stage"] for entry in excinfo.value.entries] == [
        "pre-normalize",
        "post-normalize",
    ]
    assert excinfo.value.raw == []


def test_pre_nonrepairable_error_blocks_before_normalize() -> None:
    """A pre-normalize integrity error refuses without running N."""
    compiled = _compiled(
        _error_integrity("profile:task-named-pre-normalize"),
        _warn_readiness("profile:task-named"),
    )
    c_envelope: dict[str, object] = {
        "tree": copy.deepcopy(_UNNAMED_TASK_TREE),
        "bindings": [],
    }

    def _normalize(
        _compiled: object, _envelope: object, _support: object, activation: str = "edit"
    ) -> SimpleNamespace:
        assert activation == "edit"
        message = "normalize ran after a blocking pre-normalize error"
        raise AssertionError(message)

    with pytest.raises(ApplyError) as excinfo:
        _run_normalize(
            {"normalize": _normalize},
            compiled,
            c_envelope,
            [],
            None,
            lambda: False,
            [],
        )
    assert excinfo.value.code == "task-name-missing-pre-normalize"
    assert [entry["stage"] for entry in excinfo.value.entries] == ["pre-normalize"]


def test_repaired_pre_error_does_not_block_post() -> None:
    """A repairable pre error fixed by N leaves the post gate clean."""
    compiled = _compiled(
        _error_repairable("profile:task-named-pre-normalize"),
        _error_integrity("profile:task-named"),
    )
    c_envelope: dict[str, object] = {
        "tree": copy.deepcopy(_UNNAMED_TASK_TREE),
        "bindings": [],
    }

    def _normalize(
        _compiled: object, _envelope: object, _support: object, activation: str = "edit"
    ) -> SimpleNamespace:
        assert activation == "edit"
        return SimpleNamespace(
            status="ok",
            payload={
                "envelope": {
                    "tree": _named_tree(),
                    "bindings": [],
                    "semanticRevision": "rev-n",
                },
                "report": {"entries": []},
            },
        )

    staged = _run_normalize(
        {"normalize": _normalize},
        compiled,
        c_envelope,
        [],
        None,
        lambda: False,
        [],
    )
    assert staged.changed is True
    assert staged.revision == "rev-n"
    assert [entry["stage"] for entry in staged.entries] == ["pre-normalize"]


def test_blocking_code_skips_repairable_before_normalize_only() -> None:
    """Repairable errors wait for N before it, block after it."""
    entries = [
        {
            "code": "b-code",
            "severity": "error",
            "classification": "repairable",
            "stage": "pre-normalize",
            "ruleId": "b-rule",
            "disposition": "observed",
        },
        {
            "code": "a-code",
            "severity": "warn",
            "classification": "integrity",
            "stage": "pre-normalize",
            "ruleId": "a-rule",
            "disposition": "observed",
        },
    ]
    assert _blocking_code(entries, post=False) is None
    assert _blocking_code(entries, post=True) == "b-code"


def test_blocking_code_prefers_profile_report_order() -> None:
    """The first error in profile-report/2 order wins over input order."""
    entries = [
        {
            "code": "z-code",
            "severity": "error",
            "classification": "integrity",
            "stage": "post-normalize",
            "ruleId": "z-rule",
            "disposition": "observed",
        },
        {
            "code": "a-code",
            "severity": "error",
            "classification": "integrity",
            "stage": "post-normalize",
            "ruleId": "a-rule",
            "disposition": "observed",
        },
    ]
    assert _blocking_code(entries, post=True) == "a-code"


def test_standard_rule_entry_and_raw_projection() -> None:
    """An enabled standard rule maps to bpmnlint coordinates with raw kept."""
    compiled = _compiled(
        _warn_readiness("profile:task-named-pre-normalize"),
        _warn_readiness("profile:task-named"),
    )
    records = [copy.deepcopy(record) for record in compiled.validation]
    for record in records:
        for row in record["settings"]:
            if row.get("rule") == "no-disconnected":
                row["severity"] = "error"
                row["classification"] = "integrity"
    compiled = CompiledProfile(
        profile_digest=compiled.profile_digest,
        notions=dict(compiled.notions),
        recipes=dict(compiled.recipes),
        rules=dict(compiled.rules),
        descriptor_digest=compiled.descriptor_digest,
        registry_digest=compiled.registry_digest,
        validation=tuple(records),
        ui=None,
    )
    tree = _named_tree()
    entries, raw = _lint_stage(compiled, tree, [], "pre-normalize")
    standard = [entry for entry in entries if entry["ruleId"] == "no-disconnected"]
    assert len(standard) == 1
    (entry,) = standard
    assert entry["code"] == "bpmnlint/no-disconnected"
    assert entry["messageKey"] == "bpmnlint.no-disconnected"
    assert entry["severity"] == "error"
    assert entry["classification"] == "integrity"
    assert entry["disposition"] == "observed"
    assert entry["result"] == {
        "domain": "none",
        "pointer": None,
        "targetId": None,
        "provenance": "unavailable",
    }
    assert len(raw) == 1
    (projected,) = raw
    assert set(projected) == {"rule", "findings"}
    assert projected["rule"] == "no-disconnected"
    assert projected["findings"]
    assert all(
        item.get("rule") != "profile-mechanism/profile" for item in raw if isinstance(item, dict)
    )


def test_stage_conversion_keeps_emptied_arrays() -> None:
    """Emptied containment arrays convert as ``[]`` for the lint stages (F1)."""
    tree: dict[str, object] = {
        "$type": "bpmn:Definitions",
        "id": "D_1",
        "targetNamespace": "urn:x",
        "rootElements": [
            {"$type": "bpmn:Process", "id": "P_1", "flowElements": []},
        ],
    }
    root = _moddle_of_tree(tree)
    _fix_parents(root)
    process = root.get("rootElements")[0]
    assert process.get("flowElements") == []
    assert tree["rootElements"][0]["flowElements"] == []  # type: ignore[index]


def test_sort_entries_stage_rank_then_rule_id() -> None:
    """Entries sort by stage rank, then UTF-16 rule id, duplicates coalesce."""
    post: dict[str, object] = {
        "code": "c",
        "severity": "warn",
        "classification": "readiness",
        "stage": "post-normalize",
        "ruleId": "a-rule",
        "messageKey": "k",
        "disposition": "observed",
        "source": {"domain": "tree", "pointer": "/p", "targetId": "T", "provenance": "exact"},
        "result": {
            "domain": "none",
            "pointer": None,
            "targetId": None,
            "provenance": "unavailable",
        },
        "beforePresent": False,
        "afterPresent": False,
    }
    pre = dict(post)
    pre["stage"] = "pre-normalize"
    pre["ruleId"] = "z-rule"
    ordered = sort_lot5_entries([post, pre, copy.deepcopy(post)])
    assert [entry["stage"] for entry in ordered] == ["pre-normalize", "post-normalize"]
    assert lot5_entry_order_key(pre) < lot5_entry_order_key(post)
