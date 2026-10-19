"""Parity-corpus lint cases against the lot-1 bridge (DESIGN R3.3 section 6.4)."""

from __future__ import annotations

from bpmn_io.profile._lint import lint
from bpmn_io.profile._lint.index import resolve_pointer
from bpmn_io.profile._lint.report import build_unified
from bpmn_io.profile._lint.severity import normalize_severity, transport_severity
from bpmn_io.profile._lint.transform import flatten_policy as _flatten
from bpmn_io.profile._lint.transform import select_record as _select
from tests.profile_lint.helpers import (
    NAMED_TASK_DOC,
    Json,
    by_role,
    contract,
    corpus_case,
    expected_role,
    make_compiled,
    parse,
)

LINT_CASES = [
    "lint-warning-through-error",
    "lint-info-through-warn",
    "lint-alternating-profiles",
    "lint-extends-cycle",
    "lint-pointer-escaping",
    "lint-unknown-lookup-none",
    "lint-unknown-lookup-thrown",
    "lint-whitelist-escape",
]


def test_lint_cases_pin_lot1_comparator() -> None:
    """Every lint case names the lot-1 comparator and the validate operation."""
    for case_id in LINT_CASES:
        case = corpus_case(case_id)
        assert case["operation"] == "validate"
        assert "lot-1-lint" in case["comparatorIds"]
        assert case["phase"] == "post-normalize"


def test_warning_through_error_transport() -> None:
    """A profile warn travels as error and restores to warn (unified)."""
    case = corpus_case("lint-warning-through-error")
    subrule = by_role(case, "subrule")
    assert isinstance(subrule, dict)
    assert case["expectedStatus"] == "ok"
    unified = expected_role(case, "unified")
    assert isinstance(unified, dict)
    raw = {
        "profile-mechanism/profile": [
            {
                "id": "Task_1",
                "message": subrule["message"],
                "profileRuleId": subrule["ruleId"],
                "code": subrule["code"],
                "messageKey": subrule["message"],
                "sourcePointer": "/rootElements/0/flowElements/0",
                "category": "error",
            }
        ]
    }
    entries, counts = build_unified(
        raw,
        phase=case["phase"],
        policy={
            subrule["ruleId"]: {
                "severity": subrule["severity"],
                "classification": subrule["classification"],
            }
        },
        compiled_rules={
            subrule["ruleId"]: {"code": subrule["code"], "message": subrule["message"]}
        },
        index={"Task_1": "/rootElements/0/flowElements/0"},
    )
    (entry,) = entries
    assert entry["ruleId"] == unified["ruleId"]
    assert entry["severity"] == unified["unifiedSeverity"]
    assert counts == unified["counts"]
    assert (counts["error"] == 0) == unified["ok"]


def test_info_through_warn_transport() -> None:
    """Numeric info resolves to effective info and transported warn, both policies."""
    case = corpus_case("lint-info-through-warn")
    assert case["expectedStatus"] == "ok"
    table = by_role(case, "validationTable")
    assert isinstance(table, dict)
    assert table["severity"] == 3
    effective = normalize_severity(table["severity"])
    transported = transport_severity(effective)
    assert effective == "info"
    assert transported == "warn"
    expected = expected_role(case, "transport")
    assert isinstance(expected, dict)
    for policy in ("accept", "draft"):
        assert expected[policy] == {
            "effective": "info",
            "rule": table["rule"],
            "transport": "warn",
        }


def test_alternating_profiles_do_not_leak_options() -> None:
    """A->B->A evaluations keep their own options on a fresh Linter each."""
    case = corpus_case("lint-alternating-profiles")
    assert case["expectedStatus"] == "ok"
    evaluations = [entry["json"] for entry in case["inputArtifacts"]]
    assert [entry["options"] for entry in evaluations] == [
        {"no-disconnected": "error"},
        {"no-disconnected": "warn"},
    ]
    profile = contract("neutral-profile.json")
    assert isinstance(profile, dict)

    def _compiled_for(severity: str) -> dict[str, Json]:
        compiled = make_compiled(profile, phase="post-normalize", readiness_policy="accept")
        assert isinstance(compiled["validation"], list)
        settings = None
        for record in compiled["validation"]:
            assert isinstance(record, dict)
            if record.get("id") == "post-normalize" and record.get("policy") == "accept":
                settings = record["settings"]
        assert isinstance(settings, list)
        for setting in settings:
            assert isinstance(setting, dict)
            if setting.get("rule") == "no-disconnected":
                setting["severity"] = severity
        record = _select(compiled["validation"], phase="post-normalize", readiness_policy="accept")
        flattened = _flatten(record, None)
        assert isinstance(compiled["compiledOptions"], dict)
        compiled["compiledOptions"]["severityPolicyDigest"] = flattened.severity_policy_digest
        return compiled

    first = lint(
        parse(NAMED_TASK_DOC),
        _compiled_for("error"),
        phase="post-normalize",
        readiness_policy="accept",
    )
    middle = lint(
        parse(NAMED_TASK_DOC),
        _compiled_for("warn"),
        phase="post-normalize",
        readiness_policy="accept",
    )
    again = lint(
        parse(NAMED_TASK_DOC),
        _compiled_for("error"),
        phase="post-normalize",
        readiness_policy="accept",
    )
    assert first["payload"] == again["payload"]
    assert first["payload"] != middle["payload"]


def _refused_for_table(table: Json, registry: dict[str, Json] | None = None) -> dict[str, Json]:
    """Drive ``lint`` with a corpus table fragment over neutral settings."""
    profile = contract("neutral-profile.json")
    assert isinstance(profile, dict)
    compiled = make_compiled(profile, phase="post-normalize", readiness_policy="accept")
    assert isinstance(table, dict)
    settings = table.get("settings")
    if settings is None:
        assert isinstance(compiled["validation"], list)
        for record in compiled["validation"]:
            assert isinstance(record, dict)
            if record.get("id") == "post-normalize" and record.get("policy") == "accept":
                settings = record["settings"]
    compiled["validation"] = [
        {
            "id": "post-normalize",
            "extends": table["extends"],
            "settings": settings,
            "profileRule": "profile-mechanism/profile",
            "policy": "accept",
        }
    ]
    table_registry = table.get("registry")
    if registry is None and isinstance(table_registry, dict):
        registry = table_registry
    if registry is not None:
        compiled["registry"] = registry
    return lint(parse(NAMED_TASK_DOC), compiled, phase="post-normalize", readiness_policy="accept")


def test_extends_cycle_refuses() -> None:
    """The corpus cycle refuses with the active stack and refused disposition."""
    case = corpus_case("lint-extends-cycle")
    assert case["expectedStatus"] == "refused:lint-config-cycle"
    table = by_role(case, "validationTable")
    refused = _refused_for_table(table)
    assert refused["status"] == "refused"
    unified = expected_role(case, "unified")
    assert isinstance(unified, dict)
    assert refused["code"] == unified["code"] == "lint-config-cycle"
    assert refused["diagnostics"] == [f"extends cycle: {' -> '.join(unified['cycle'])}"]
    (entry,) = refused["report"]["entries"]
    assert entry["code"] == unified["code"]
    assert entry["severity"] == unified["severity"]
    assert entry["disposition"] == unified["disposition"]


def test_pointer_escaping_vectors() -> None:
    """Escaped segments append; ghosts and bad forms stay unavailable."""
    case = corpus_case("lint-pointer-escaping")
    assert case["expectedStatus"] == "ok"
    assert isinstance(case["inputArtifacts"], list)
    assert isinstance(case["expectedArtifacts"], list)
    paths = [entry["json"] for entry in case["inputArtifacts"] if entry.get("role") == "reportPath"]
    expected = [
        entry["json"] for entry in case["expectedArtifacts"] if entry.get("role") == "coordinates"
    ]
    assert len(paths) == len(expected) == 2
    index = {"Task_1": "/rootElements/0/flowElements/0"}
    for report_path, coordinates in zip(paths, expected, strict=True):
        assert isinstance(report_path, dict)
        assert isinstance(coordinates, dict)
        pointer, provenance = resolve_pointer(
            index, report_path["reportedId"], report_path["path"], set()
        )
        assert pointer == coordinates["pointer"]
        assert provenance == coordinates["provenance"]
        assert coordinates.get("targetId", report_path["reportedId"]) == report_path["reportedId"]
    pointer, provenance = resolve_pointer(index, "Task_1", [{"bad": 1}], set())
    assert pointer is None
    assert provenance == "unavailable"


def test_unknown_lookup_none_refuses() -> None:
    """An extends target resolving to None refuses lint-config-unknown."""
    case = corpus_case("lint-unknown-lookup-none")
    assert case["expectedStatus"] == "refused:lint-config-unknown"
    table = by_role(case, "validationTable")
    assert isinstance(table, dict)
    assert table.get("lookup", "none") == "none"
    refused = _refused_for_table(table, None)
    assert refused["status"] == "refused"
    unified = expected_role(case, "unified")
    assert refused["code"] == unified["code"] == "lint-config-unknown"
    (entry,) = refused["report"]["entries"]
    assert entry["disposition"] == unified["disposition"] == "refused"
    assert entry["severity"] == unified["severity"] == "error"


def test_unknown_lookup_thrown_refuses() -> None:
    """A thrown extends lookup refuses exactly like a None lookup."""
    case = corpus_case("lint-unknown-lookup-thrown")
    assert case["expectedStatus"] == "refused:lint-config-unknown"
    table = by_role(case, "validationTable")
    assert isinstance(table, dict)
    assert table.get("lookup") == "thrown"

    class _Throwing(dict):  # type: ignore[type-arg]
        def __getitem__(self, key: object) -> Json:
            msg = "node require threw"
            raise RuntimeError(msg)

    refused = _refused_for_table(table, _Throwing())
    assert refused["status"] == "refused"
    assert refused["code"] == "lint-config-unknown"


def test_whitelist_escape_refuses() -> None:
    """Filesystem paths in extends refuse (closed syntax, no module loading)."""
    case = corpus_case("lint-whitelist-escape")
    assert case["expectedStatus"] == "refused:profile-schema"
    table = by_role(case, "validationTable")
    refused = _refused_for_table(table, None)
    assert refused["status"] == "refused"
    unified = expected_role(case, "unified")
    assert refused["code"] == unified["code"] == "profile-schema"
    assert refused["report"]["entries"][0]["disposition"] == "refused"


def _table_settings(table: dict[str, Json]) -> Json:
    """Return a table's settings, falling back to the neutral record."""
    settings = table.get("settings")
    if isinstance(settings, list):
        return settings
    profile = contract("neutral-profile.json")
    assert isinstance(profile, dict)
    assert isinstance(profile["validation"], list)
    for record in profile["validation"]:
        assert isinstance(record, dict)
        if record.get("id") == "post-normalize" and record.get("policy") == "accept":
            record_settings = record.get("settings")
            assert isinstance(record_settings, list)
            return record_settings
    msg = "missing neutral post-normalize/accept record"
    raise AssertionError(msg)


def test_corpus_tables_validate_through_select() -> None:
    """Corpus extends/settings fragments validate through the record gate."""
    case = corpus_case("lint-extends-cycle")
    table = by_role(case, "validationTable")
    assert isinstance(table, dict)
    record = _select(
        [
            {
                "id": "post-normalize",
                "extends": table["extends"],
                "settings": _table_settings(table),
                "profileRule": "profile-mechanism/profile",
                "policy": "accept",
            }
        ],
        phase="post-normalize",
        readiness_policy="accept",
    )
    assert record["extends"] == table["extends"]
