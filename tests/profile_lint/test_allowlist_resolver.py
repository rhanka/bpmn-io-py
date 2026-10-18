"""Pinned allowlist resolver (DESIGN R3.3 section 6.1)."""

from __future__ import annotations

from typing import TYPE_CHECKING, NoReturn

from bpmn_io.profile._lint.c14n import digest

if TYPE_CHECKING:
    import pytest
from bpmn_io.profile._lint.resolver import (
    HOST_PACKAGE,
    PINNED_RULE_NAMES,
    PLUGIN_PACKAGE,
    PLUGIN_RULE_EXPORT,
    REGISTRY_DIGEST,
    UPSTREAM_SOURCE_SHA256,
    ProfileResolver,
    discover_plugin_entry_point,
    recommended_rules,
)
from tests.profile_lint.helpers import contract


def test_allowlist_matches_pinned_manifest() -> None:
    """The hardcoded allowlist equals the pinned recommended manifest rules."""
    manifest = contract("bpmnlint-11.15.0-recommended.json")
    assert set(PINNED_RULE_NAMES) == set(manifest["rules"])
    assert len(PINNED_RULE_NAMES) == 26
    assert recommended_rules() == manifest["rules"]
    assert manifest["sourceSha256"] == UPSTREAM_SOURCE_SHA256


def test_registry_digest_pins_allowlist() -> None:
    """The registry digest binds the exact allowlist content."""
    assert (
        digest(
            {
                "configs": [f"{HOST_PACKAGE}/recommended"],
                "pluginRule": f"{PLUGIN_PACKAGE}/{PLUGIN_RULE_EXPORT}",
                "rules": sorted(PINNED_RULE_NAMES),
                "upstreamSourceSha256": UPSTREAM_SOURCE_SHA256,
            }
        )
        == REGISTRY_DIGEST
    )


def test_allowlisted_rules_resolve() -> None:
    """Every allowlisted rule and the pinned config resolve."""
    resolver = ProfileResolver()
    for name in PINNED_RULE_NAMES:
        assert callable(resolver.resolve_rule("bpmnlint", name))
    assert resolver.resolve_rule(PLUGIN_PACKAGE, PLUGIN_RULE_EXPORT) is not None
    assert resolver.resolve_rule("profile-mechanism", PLUGIN_RULE_EXPORT) is not None
    config = resolver.resolve_config("bpmnlint", "recommended")
    assert isinstance(config, dict)
    assert set(config["rules"]) == set(PINNED_RULE_NAMES)


def test_unknown_names_resolve_to_none() -> None:
    """Non-allowlisted rules and configs resolve to None (never raise)."""
    resolver = ProfileResolver()
    assert resolver.resolve_rule("bpmnlint", "no-such-rule") is None
    assert resolver.resolve_rule("bpmnlint", "conditional-event") is None
    assert resolver.resolve_rule("ghost", "missing") is None
    assert resolver.resolve_rule(".", "profile") is None
    assert resolver.resolve_config("bpmnlint", "all") is None
    assert resolver.resolve_config("ghost", "missing") is None


def test_resolve_path_loads_no_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    """Profile-path resolution never touches importlib or entry points."""
    import importlib
    import importlib.metadata

    def _forbidden(*_args: object, **_kwargs: object) -> NoReturn:
        msg = "module loading is forbidden on the profile path"
        raise AssertionError(msg)

    monkeypatch.setattr(importlib, "import_module", _forbidden)
    monkeypatch.setattr(importlib.metadata, "entry_points", _forbidden)
    resolver = ProfileResolver()
    assert resolver.resolve_rule("bpmnlint", "label-required") is not None
    assert resolver.resolve_rule("ghost", "missing") is None
    assert resolver.resolve_config("ghost", "missing") is None


def test_cache_keys_and_boundaries() -> None:
    """Factories cache by the exact section 6.1 key; instances never cache."""
    assert ProfileResolver.cache_key("bpmnlint", "rule", "label-required") == (
        UPSTREAM_SOURCE_SHA256,
        REGISTRY_DIGEST,
        "bpmnlint",
        "rule",
        "label-required",
    )
    resolver = ProfileResolver()
    first = resolver.resolve_rule("bpmnlint", "label-required")
    assert resolver.resolve_rule("bpmnlint", "label-required") is first
    assert callable(first)
    assert first({}) is not first({})
    plugin = resolver.resolve_rule(PLUGIN_PACKAGE, PLUGIN_RULE_EXPORT)
    assert resolver.resolve_rule(PLUGIN_PACKAGE, PLUGIN_RULE_EXPORT) is plugin


def test_short_package_name_normalizes() -> None:
    """Upstream plugin semantics prefix short package names."""
    assert ProfileResolver.normalize_package("bpmnlint") == "bpmnlint"
    assert ProfileResolver.normalize_package("profile-mechanism") == PLUGIN_PACKAGE
    assert ProfileResolver.normalize_package(PLUGIN_PACKAGE) == PLUGIN_PACKAGE


def test_entry_point_discovery_follows_whitelist(monkeypatch: pytest.MonkeyPatch) -> None:
    """Entry-point discovery loads the whitelisted plugin when installed."""
    import importlib.metadata

    seen: list[str] = []

    class _Point:
        name = PLUGIN_PACKAGE

        def load(self) -> str:
            return "plugin-object"

    def _entry_points(**_kwargs: object) -> list[_Point]:
        seen.append(str(_kwargs.get("group")))
        return [_Point()]

    monkeypatch.setattr(importlib.metadata, "entry_points", _entry_points)
    assert discover_plugin_entry_point() == "plugin-object"
    assert seen == ["bpmnlint.plugins"]


def test_entry_point_discovery_absent_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing distribution metadata refuses softly with None."""
    import importlib.metadata

    def _raise(*_args: object, **_kwargs: object) -> NoReturn:
        msg = "no metadata"
        raise ValueError(msg)

    monkeypatch.setattr(importlib.metadata, "entry_points", _raise)
    assert discover_plugin_entry_point() is None
