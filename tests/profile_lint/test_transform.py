"""Exact configuration transform (DESIGN R3.3 section 6.3)."""

from __future__ import annotations

import hashlib

import pytest

from bpmn_io.profile._lint.c14n import digest, dumps_jcs
from bpmn_io.profile._lint.errors import (
    ConfigCycleError,
    ConfigIncompleteError,
    ConfigUnknownError,
    ProfileDataError,
)
from bpmn_io.profile._lint.transform import (
    FlattenedPolicy,
    build_transport_options,
    build_upstream_config,
    flatten_policy,
    select_record,
    validate_compiled_options,
)
from tests.profile_lint.helpers import Json, contract, make_compiled


def _record(profile: str, phase: str, policy: str) -> dict[str, Json]:
    data = contract(profile)
    assert isinstance(data, dict)
    return select_record(data["validation"], phase=phase, readiness_policy=policy)


def _flat(record: dict[str, Json], registry: dict[str, Json] | None = None) -> FlattenedPolicy:
    validated = select_record([record], phase=record["id"], readiness_policy=record["policy"])
    return flatten_policy(validated, registry)


def test_flatten_regenerates_contract_tables() -> None:
    """The flattened tables match lint-policy-r3.json byte-for-byte."""
    from tests.profile_lint.helpers import CONTRACTS

    policy_file = contract("lint-policy-r3.json")
    raw_manifest = (CONTRACTS / "bpmnlint-11.15.0-recommended.json").read_bytes()
    assert hashlib.sha256(raw_manifest).hexdigest() == policy_file["upstreamManifestSha256"]
    profiles = {
        "neutral/1": "neutral-profile.json",
        "neutral-grid/1": "neutral-grid-profile.json",
    }
    seen = 0
    for entry in policy_file["profiles"]:
        profile = contract(profiles[entry["profile"]])
        for table in entry["tables"]:
            record = select_record(
                profile["validation"],
                phase=table["phase"],
                readiness_policy=table["readinessPolicy"],
            )
            flattened = _flat(record)
            regenerated = {
                "phase": table["phase"],
                "readinessPolicy": table["readinessPolicy"],
                "standard": {name: row["severity"] for name, row in flattened.standard.items()},
                "subRules": {name: row["severity"] for name, row in flattened.subrules.items()},
                "upstream": {name: row["severity"] for name, row in flattened.standard.items()},
                "transport": "error",
                "severityPolicyDigest": flattened.severity_policy_digest,
            }
            assert dumps_jcs(regenerated) == dumps_jcs(table)
            seen += 1
    assert seen == 20


def test_transport_registration_is_single_error() -> None:
    """The upstream config carries exactly one transport registration."""
    record = _record("neutral-profile.json", "post-normalize", "accept")
    flattened = _flat(record)
    compiled = make_compiled(
        contract("neutral-profile.json"), phase="post-normalize", readiness_policy="accept"
    )
    options = build_transport_options(
        compiled["compiledOptions"], flattened, compiled["compiledOptions"]["compiledRules"]
    )
    config = build_upstream_config(flattened, options)
    assert config["rules"]["profile-mechanism/profile"] == ["error", options]
    assert "profile:task-named" not in config["rules"]
    assert config["rules"]["no-bpmndi"] == "off"
    assert set(config["rules"]) == set(flattened.standard) | {"profile-mechanism/profile"}


def test_info_travels_as_warn_in_upstream_config() -> None:
    """Numeric info becomes effective info but transported warn."""
    record = {
        "id": "import",
        "extends": ["bpmnlint:recommended"],
        "settings": [
            {"rule": name, "severity": "error", "classification": "integrity"}
            for name in (
                "conditional-flows",
                "end-event-required",
                "event-based-gateway",
                "event-sub-process-typed-start-event",
                "fake-join",
                "global",
                "label-required",
                "link-event",
                "no-bpmndi",
                "no-complex-gateway",
                "no-disconnected",
                "no-duplicate-sequence-flows",
                "no-gateway-join-fork",
                "no-implicit-split",
                "no-implicit-end",
                "no-implicit-start",
                "no-inclusive-gateway",
                "no-overlapping-elements",
                "single-blank-start-event",
                "single-event-definition",
                "start-event-required",
                "sub-process-blank-start-event",
                "superfluous-gateway",
                "superfluous-label",
                "superfluous-termination",
            )
        ]
        + [{"rule": "ad-hoc-sub-process", "severity": 3, "classification": "advisory"}],
        "profileRule": "profile-mechanism/profile",
        "policy": "accept",
    }
    validated = select_record([record], phase="import", readiness_policy="accept")
    flattened = flatten_policy(validated, None)
    assert flattened.standard["ad-hoc-sub-process"] == {
        "severity": "info",
        "classification": "advisory",
    }
    config = build_upstream_config(flattened, {"compiledRules": []})
    assert config["rules"]["ad-hoc-sub-process"] == "warn"


def test_extends_chain_traversal_and_explicit_supremacy() -> None:
    """Extends chains traverse depth-first; explicit records replace wholesale."""
    registry = {
        "plugin:base/main": {
            "extends": ["plugin:mid/main"],
            "rules": {"no-disconnected": "warn", "label-required": "warn"},
        },
        "plugin:mid/main": {"rules": {"no-disconnected": "error"}},
    }
    sparse = {
        "id": "import",
        "extends": ["plugin:base/main"],
        "settings": [
            {"rule": "no-disconnected", "severity": "off", "classification": "integrity"},
        ],
        "profileRule": "profile-mechanism/profile",
        "policy": "accept",
    }
    # The chain is traversed (label-required is reached through it) but a
    # parent-only severity carries no classification, so coverage refuses.
    with pytest.raises(ConfigIncompleteError) as excinfo:
        _flat(_complete(sparse, {}, skip=frozenset({"label-required"})), registry)
    assert "label-required" in str(excinfo.value.detail.get("missing"))
    # Classifying every rule explicitly lets the traversal complete, with the
    # explicit record supreme over every inherited severity.
    filled = _complete(
        sparse, {"label-required": ("warn", "readiness"), "no-disconnected": ("off", "integrity")}
    )
    flattened = _flat(filled, registry)
    assert flattened.standard["no-disconnected"]["severity"] == "off"
    assert flattened.standard["label-required"] == {
        "severity": "warn",
        "classification": "readiness",
    }


def _complete(
    record: dict[str, Json],
    extra: dict[str, tuple[str, str]],
    *,
    skip: frozenset[str] = frozenset(),
) -> dict[str, Json]:
    """Fill a sparse record with classified settings for every manifest rule."""
    from bpmn_io.profile._lint.resolver import PINNED_RULE_NAMES

    names = {setting["rule"] for setting in record["settings"]}
    settings = list(record["settings"])
    for name in sorted(PINNED_RULE_NAMES):
        if name not in names and name not in skip:
            severity, classification = extra.get(name, ("error", "integrity"))
            settings.append({"rule": name, "severity": severity, "classification": classification})
    return {**record, "settings": settings}


def test_extends_cycle_refuses() -> None:
    """An extends cycle refuses lint-config-cycle with the active stack."""
    registry = {
        "plugin:cycle/a": {"extends": ["plugin:cycle/b"]},
        "plugin:cycle/b": {"extends": ["plugin:cycle/a"]},
    }
    record = _complete(
        {
            "id": "post-normalize",
            "extends": ["plugin:cycle/a"],
            "settings": [],
            "profileRule": "profile-mechanism/profile",
            "policy": "accept",
        },
        {},
    )
    with pytest.raises(ConfigCycleError) as excinfo:
        _flat(record, registry)
    assert excinfo.value.code == "lint-config-cycle"
    assert excinfo.value.cycle == ["plugin:cycle/a", "plugin:cycle/b"]


def test_unknown_extends_refuses() -> None:
    """Missing extends targets refuse lint-config-unknown (None lookup)."""
    record = _complete(
        {
            "id": "post-normalize",
            "extends": ["plugin:ghost/missing"],
            "settings": [],
            "profileRule": "profile-mechanism/profile",
            "policy": "accept",
        },
        {},
    )
    with pytest.raises(ConfigUnknownError) as excinfo:
        _flat(record, {})
    assert excinfo.value.code == "lint-config-unknown"


def test_thrown_lookup_refuses_unknown() -> None:
    """A thrown registry lookup maps to lint-config-unknown like None."""

    class _Throwing(dict):  # type: ignore[type-arg]
        def __getitem__(self, key: object) -> Json:
            msg = "node require threw"
            raise RuntimeError(msg)

    record = _complete(
        {
            "id": "post-normalize",
            "extends": ["plugin:ghost/missing"],
            "settings": [],
            "profileRule": "profile-mechanism/profile",
            "policy": "accept",
        },
        {},
    )
    with pytest.raises(ConfigUnknownError) as excinfo:
        _flat(record, _Throwing())
    assert excinfo.value.code == "lint-config-unknown"


def test_forbidden_extends_syntax_refuses() -> None:
    """Filesystem paths and URLs in extends refuse (closed syntax)."""
    record = {
        "id": "post-normalize",
        "extends": ["../../outside"],
        "settings": [],
        "profileRule": "profile-mechanism/profile",
        "policy": "accept",
    }
    with pytest.raises(ProfileDataError) as excinfo:
        select_record([record], phase="post-normalize", readiness_policy="accept")
    assert excinfo.value.code == "profile-schema"


def test_missing_coverage_refuses_incomplete() -> None:
    """Manifest rules without classified settings refuse lint-config-incomplete."""
    record = {
        "id": "post-normalize",
        "extends": ["bpmnlint:recommended"],
        "settings": [],
        "profileRule": "profile-mechanism/profile",
        "policy": "accept",
    }
    with pytest.raises(ConfigIncompleteError) as excinfo:
        _flat(record)
    assert excinfo.value.code == "lint-config-incomplete"


def test_parent_options_refuse() -> None:
    """Parent rule options need pinned per-rule schemas (refused in lot 1)."""
    registry = {"plugin:host/main": {"rules": {"no-disconnected": ["error", {"since": "x"}]}}}
    record = _complete(
        {
            "id": "post-normalize",
            "extends": ["plugin:host/main"],
            "settings": [],
            "profileRule": "profile-mechanism/profile",
            "policy": "accept",
        },
        {},
    )
    with pytest.raises(ProfileDataError):
        _flat(record, registry)


def test_registry_shadowing_pinned_refuses() -> None:
    """A registry must not shadow the pinned host config."""
    registry = {"bpmnlint:recommended": {"rules": {}}}
    record = _record("neutral-profile.json", "import", "draft")
    with pytest.raises(ProfileDataError):
        _flat(record, registry)


def test_select_record_missing_and_duplicate() -> None:
    """Missing tables refuse incomplete; duplicate tables refuse data errors."""
    profile = contract("neutral-profile.json")
    truncated = [
        record
        for record in profile["validation"]
        if (record["id"], record["policy"]) != ("release", "draft")
    ]
    with pytest.raises(ConfigIncompleteError):
        select_record(truncated, phase="release", readiness_policy="draft")
    with pytest.raises(ProfileDataError):
        select_record(
            [*profile["validation"], profile["validation"][0]],
            phase="import",
            readiness_policy="draft",
        )


def test_validate_compiled_options_negatives() -> None:
    """Closed-schema violations refuse (seven keys, digests, enums, records)."""
    compiled = make_compiled(
        contract("neutral-profile.json"), phase="import", readiness_policy="draft"
    )
    good = compiled["compiledOptions"]
    validate_compiled_options(good)
    bad_extra = {**good, "extra": 1}
    with pytest.raises(ProfileDataError):
        validate_compiled_options(bad_extra)
    for key, bad in (
        ("mechanismVersion", "2"),
        ("profileDigest", "xyz"),
        ("phase", "draft"),
        ("readinessPolicy", "maybe"),
        ("compiledRules", {}),
        ("bindings", {}),
    ):
        broken = {**good, key: bad}
        with pytest.raises(ProfileDataError):
            validate_compiled_options(broken)
    with pytest.raises(ProfileDataError):
        validate_compiled_options(
            {**good, "bindings": [{"ownerId": "", "role": "r", "targetId": "t"}]}
        )
    with pytest.raises(ProfileDataError):
        validate_compiled_options({**good, "compiledRules": [{"id": "x"}]})
    assert digest({"a": 1}) != good["severityPolicyDigest"]


def test_off_removes_subrule_before_evaluation() -> None:
    """Off settings stay in the digest but leave the transport options."""
    profile = contract("neutral-profile.json")
    record = select_record(profile["validation"], phase="import", readiness_policy="draft")
    switched = {
        **record,
        "settings": [
            {**setting, "severity": "off"}
            if setting["rule"] == "profile:task-named-import"
            else setting
            for setting in record["settings"]
        ],
    }
    flattened = _flat(switched)
    assert flattened.subrules["profile:task-named-import"]["severity"] == "off"
    options = build_transport_options(
        {
            "mechanismVersion": "1",
            "profileDigest": "0" * 64,
            "phase": "import",
            "readinessPolicy": "draft",
            "compiledRules": profile["rules"],
            "bindings": [],
            "severityPolicyDigest": flattened.severity_policy_digest,
        },
        flattened,
        profile["rules"],
    )
    assert options["compiledRules"] == []
