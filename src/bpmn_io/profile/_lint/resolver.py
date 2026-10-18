# DESIGN R3.3 §6.1: StaticResolver adapter over an explicit pinned allowlist.
"""Pinned allowlist resolver for the profile lint path.

The adapter serves only immutable factories and configs: the 26 upstream
rules of the pinned ``bpmnlint:recommended`` manifest, the pinned
``bpmnlint:recommended`` config itself, and the single profile rule factory.
Anything else resolves to ``None`` (the caller maps it to
``lint-rule-unknown`` / ``lint-config-unknown``); the adapter never falls
back to ``importlib`` and never consults entry points on the resolve path,
so profile data cannot cause module loading.

Entry-point discovery lives in :func:`discover_plugin_entry_point`, which
checks the pinned whitelist *before* touching ``importlib.metadata``; the
evaluation path always uses the directly imported (pinned) factory.
"""

from __future__ import annotations

from importlib import metadata
from typing import Any

from bpmn_io.lint.config.recommended import CONFIG as _RECOMMENDED_CONFIG
from bpmn_io.lint.rules import (
    ad_hoc_sub_process,
    conditional_flows,
    end_event_required,
    event_based_gateway,
    event_sub_process_typed_start_event,
    fake_join,
    global_,
    label_required,
    link_event,
    no_bpmndi,
    no_complex_gateway,
    no_disconnected,
    no_duplicate_sequence_flows,
    no_gateway_join_fork,
    no_implicit_end,
    no_implicit_split,
    no_implicit_start,
    no_inclusive_gateway,
    no_overlapping_elements,
    single_blank_start_event,
    single_event_definition,
    start_event_required,
    sub_process_blank_start_event,
    superfluous_gateway,
    superfluous_label,
    superfluous_termination,
)
from bpmn_io.profile._lint.c14n import digest
from bpmn_io.profile._lint.plugin import factory as _plugin_factory

__all__ = [
    "HOST_PACKAGE",
    "HOST_RECOMMENDED_CONFIG_NAME",
    "PINNED_RULE_NAMES",
    "PLUGIN_PACKAGE",
    "PLUGIN_RULE_EXPORT",
    "PLUGIN_RULE_NAME",
    "REGISTRY_DIGEST",
    "UPSTREAM_SOURCE_SHA256",
    "ProfileResolver",
    "discover_plugin_entry_point",
    "recommended_rules",
]

#: Host package served by the adapter (literal upstream port).
HOST_PACKAGE = "bpmnlint"

#: The single pinned host config (DESIGN R3.3 §6.1 extends syntax).
HOST_RECOMMENDED_CONFIG_NAME = "recommended"

#: Entry-point group used for plugin discovery (whitelist-gated, never
#: consulted on the evaluation resolve path).
ENTRY_POINT_GROUP = "bpmnlint.plugins"

#: The only executable profile plugin (DESIGN R3.3 §6.1).
PLUGIN_PACKAGE = "bpmnlint-plugin-profile-mechanism"

#: Export name of the profile rule inside the plugin (``rules`` map key).
PLUGIN_RULE_EXPORT = "profile"

#: Fully qualified profile rule name registered in upstream configs.
PLUGIN_RULE_NAME = "profile-mechanism/profile"

#: Pinned upstream artifact digest: SHA-256 over the exact
#: ``bpmnlint@11.15.0`` recommended source bytes (``sourceSha256`` of the
#: vendored manifest; cross-checked by test against the manifest and the
#: upstream sources).
UPSTREAM_SOURCE_SHA256 = "cda5e72d34e90c15a8c2991fec81ae8562574e99167611a8a7053f3f791f0cc7"

#: The 26 upstream rules covered by the pinned recommended manifest.
PINNED_RULE_NAMES = frozenset(
    {
        "ad-hoc-sub-process",
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
    }
)

#: Explicit pinned rule factories (no dynamic import: every module is named).
_PINNED_FACTORIES: dict[str, Any] = {
    "ad-hoc-sub-process": ad_hoc_sub_process.factory,
    "conditional-flows": conditional_flows.factory,
    "end-event-required": end_event_required.factory,
    "event-based-gateway": event_based_gateway.factory,
    "event-sub-process-typed-start-event": event_sub_process_typed_start_event.factory,
    "fake-join": fake_join.factory,
    "global": global_.factory,
    "label-required": label_required.factory,
    "link-event": link_event.factory,
    "no-bpmndi": no_bpmndi.factory,
    "no-complex-gateway": no_complex_gateway.factory,
    "no-disconnected": no_disconnected.factory,
    "no-duplicate-sequence-flows": no_duplicate_sequence_flows.factory,
    "no-gateway-join-fork": no_gateway_join_fork.factory,
    "no-implicit-split": no_implicit_split.factory,
    "no-implicit-end": no_implicit_end.factory,
    "no-implicit-start": no_implicit_start.factory,
    "no-inclusive-gateway": no_inclusive_gateway.factory,
    "no-overlapping-elements": no_overlapping_elements.factory,
    "single-blank-start-event": single_blank_start_event.factory,
    "single-event-definition": single_event_definition.factory,
    "start-event-required": start_event_required.factory,
    "sub-process-blank-start-event": sub_process_blank_start_event.factory,
    "superfluous-gateway": superfluous_gateway.factory,
    "superfluous-label": superfluous_label.factory,
    "superfluous-termination": superfluous_termination.factory,
}

#: Pinned resolver-registry digest: ``H`` over the allowlist itself, so the
#: cache key binds the exact registry content (DESIGN R3.3 §6.1 key).
REGISTRY_DIGEST = digest(
    {
        "configs": [f"{HOST_PACKAGE}/{HOST_RECOMMENDED_CONFIG_NAME}"],
        "pluginRule": f"{PLUGIN_PACKAGE}/{PLUGIN_RULE_EXPORT}",
        "rules": sorted(PINNED_RULE_NAMES),
        "upstreamSourceSha256": UPSTREAM_SOURCE_SHA256,
    }
)


def recommended_rules() -> dict[str, str]:
    """Return the pinned ``bpmnlint:recommended`` rules (severity words)."""
    rules = _RECOMMENDED_CONFIG["rules"]
    return dict(rules)


def discover_plugin_entry_point() -> Any:  # noqa: ANN401 - plugin object shape
    """Discover the whitelisted plugin entry point, if it is installed.

    The pinned whitelist is checked *before* ``importlib.metadata`` is
    consulted: the exact entry name must equal :data:`PLUGIN_PACKAGE`.
    Returns the loaded entry-point object (whose ``rules`` map carries the
    profile factory) or ``None`` when the distribution metadata is absent.
    This proves the ``pyproject.toml`` wiring; evaluation always uses the
    directly imported factory, never this lookup.
    """
    if PLUGIN_PACKAGE != "bpmnlint-plugin-profile-mechanism":
        return None
    try:
        points = metadata.entry_points(group=ENTRY_POINT_GROUP)
    except Exception:  # noqa: BLE001 - discovery must never break resolution
        return None
    for point in points:
        if point.name == PLUGIN_PACKAGE:
            try:
                return point.load()
            except Exception:  # noqa: BLE001 - a broken install refuses softly
                return None
    return None


class ProfileResolver:
    """StaticResolver adapter over the explicit pinned allowlist.

    The cache holds only immutable factories and configs, keyed exactly as
    DESIGN R3.3 §6.1 requires: ``(upstream artifact digest, pinned
    resolver-registry digest, normalized package name, rule-or-config kind,
    export name)``. Configured rule instances and findings are never cached;
    options, profile digests and severity policy digests stay with each
    fresh stage/evaluation (fresh ``Linter`` per call in :func:`lint`).
    """

    def __init__(self) -> None:
        """Create the adapter with an empty immutable-factory cache."""
        self._plugin_factory = _plugin_factory
        self._cache: dict[tuple[str, str, str, str, str], Any] = {}

    @staticmethod
    def normalize_package(pkg: str) -> str:
        """Normalize a package name with upstream plugin semantics.

        ``bpmnlint`` stays bare; already-prefixed names stay untouched;
        short names gain the ``bpmnlint-plugin-`` prefix. Anything else
        (including the local ``.`` reference) resolves to ``None`` later:
        only allowlisted (package, kind, name) triples serve.
        """
        if pkg == HOST_PACKAGE or pkg.startswith("bpmnlint-plugin-"):
            return pkg
        return f"bpmnlint-plugin-{pkg}"

    @staticmethod
    def cache_key(pkg: str, kind: str, name: str) -> tuple[str, str, str, str, str]:
        """Return the immutable-factory cache key (DESIGN R3.3 section 6.1).

        The key binds the exact upstream artifact digest, the pinned
        resolver-registry digest, the normalized package name, the
        rule-or-config kind and the export name.
        """
        return (UPSTREAM_SOURCE_SHA256, REGISTRY_DIGEST, pkg, kind, name)

    def resolve_rule(self, pkg: str, rule_name: str) -> Any | None:  # noqa: ANN401
        """Return the immutable rule factory, or ``None`` when not allowlisted."""
        normalized = self.normalize_package(pkg)
        key = self.cache_key(normalized, "rule", rule_name)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        factory: Any | None = None
        if normalized == PLUGIN_PACKAGE and rule_name == PLUGIN_RULE_EXPORT:
            factory = self._plugin_factory
        elif normalized == HOST_PACKAGE and rule_name in _PINNED_FACTORIES:
            factory = _PINNED_FACTORIES[rule_name]
        if factory is None or not callable(factory):
            return None
        self._cache[key] = factory
        return factory

    def resolve_config(self, pkg: str, config_name: str) -> Any | None:  # noqa: ANN401
        """Return the immutable config, or ``None`` when not allowlisted."""
        normalized = self.normalize_package(pkg)
        key = self.cache_key(normalized, "config", config_name)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        config: Any | None = None
        if normalized == HOST_PACKAGE and config_name == HOST_RECOMMENDED_CONFIG_NAME:
            config = {"rules": recommended_rules()}
        if config is None:
            return None
        self._cache[key] = config
        return config
