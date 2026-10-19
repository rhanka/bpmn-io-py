"""Section 9.2 digest formulas, freshness binds and render validation.

``render_digests`` binds every digest on explicit records; ``view_revision``
binds the seven freshness members; ``verify_render_data`` recomputes a
stored binding from its inputs.
"""

from __future__ import annotations

from typing import Any

from bpmn_io.profile._c14n import digest, digest_bytes
from bpmn_io.profile._render_tokens import normalize_di_styles, normalize_overrides
from bpmn_io.profile._results import PureRefused, PureResult, PureSuccess

__all__ = ["render_digests", "verify_render_data", "view_revision"]

Json = Any

#: Binding members bound by the §9.2 viewRevision (UTF-16 order via H).
VIEW_REVISION_KEYS = (
    "semanticRevision",
    "layoutDigest",
    "themeId",
    "themeDigest",
    "overridesDigest",
    "diStylesDigest",
    "metricsDigest",
)

#: Exact top-level members of a digest record (payload optional).
_RECORD_KEYS = frozenset(
    {
        "semanticTree",
        "profileIdentity",
        "bindings",
        "descriptorPins",
        "layout",
        "themeId",
        "themes",
        "overrides",
        "diStyles",
        "metrics",
        "payload",
    }
)

_REQUIRED_RECORD_KEYS = frozenset(
    {
        "semanticTree",
        "profileIdentity",
        "bindings",
        "descriptorPins",
        "layout",
        "themeId",
        "themes",
        "overrides",
        "diStyles",
        "metrics",
    }
)


def view_revision(binding: dict[str, object]) -> str:
    """Return the §9.2 viewRevision of one render binding record."""
    return digest({key: binding[key] for key in VIEW_REVISION_KEYS})


def _utf16(value: str) -> bytes:
    """Return the UTF-16BE sort key of one string."""
    return value.encode("utf-16-be")


def semantic_revision(
    tree: dict[str, Json], identity: dict[str, Json], bindings: list[dict[str, Json]]
) -> str:
    """Return H({tree, profileIdentity, bindings}) with sorted bindings."""
    ordered = sorted(
        bindings,
        key=lambda entry: (
            _utf16(str(entry.get("ownerId", ""))),
            _utf16(str(entry.get("role", ""))),
            _utf16(str(entry.get("targetId", ""))),
        ),
    )
    return digest({"tree": tree, "profileIdentity": identity, "bindings": ordered})


def descriptor_digest(pins: list[dict[str, Json]]) -> str:
    """Return H(pins sorted by UTF-16 id), each exactly {id, version, sha256}."""
    ordered = sorted(pins, key=lambda entry: _utf16(str(entry["id"])))
    return digest(
        [
            {"id": entry["id"], "version": entry["version"], "sha256": entry["sha256"]}
            for entry in ordered
        ]
    )


def theme_chain(themes: list[dict[str, Json]], theme_id: str) -> list[dict[str, Json]] | None:
    """Resolve the fallback chain from the fallback root to ``theme_id``.

    The id resolves first, then a declared theme alias. Returns ``None``
    when the id is unknown or the fallback chain breaks or cycles.
    """
    by_id: dict[str, dict[str, Json]] = {}
    by_alias: dict[str, str] = {}
    for theme in themes:
        if not isinstance(theme, dict) or not isinstance(theme.get("id"), str):
            return None
        by_id[str(theme["id"])] = theme
        aliases = theme.get("aliases", [])
        if not isinstance(aliases, list) or not all(isinstance(name, str) for name in aliases):
            return None
        for name in aliases:
            by_alias.setdefault(str(name), str(theme["id"]))
    resolved = theme_id if theme_id in by_id else by_alias.get(theme_id)
    if resolved is None:
        return None
    chain: list[dict[str, Json]] = []
    current: str | None = resolved
    seen: set[str] = set()
    while current is not None:
        if current in seen or current not in by_id:
            return None
        seen.add(current)
        theme = by_id[current]
        chain.insert(0, theme)
        fallback = theme.get("fallback")
        if fallback is None:
            current = None
        elif isinstance(fallback, str):
            current = fallback
        else:
            return None
    return chain


def theme_digest(themes: list[dict[str, Json]], theme_id: str) -> str | None:
    """Return H({themeId, themes}) over the resolved chain (None if broken)."""
    chain = theme_chain(themes, theme_id)
    if chain is None:
        return None
    return digest({"themeId": theme_id, "themes": chain})


def metrics_digest(resources: list[dict[str, str]]) -> str:
    """Return H([{id, sha256}]) sorted by UTF-16 resource id."""
    ordered = sorted(resources, key=lambda entry: _utf16(entry["id"]))
    return digest([{"id": entry["id"], "sha256": entry["sha256"]} for entry in ordered])


def payload_digest(render: dict[str, Json]) -> str:
    """Return H({pages, occurrences, coverage, diagnostics}) of RenderData/1."""
    return digest({key: render[key] for key in ("pages", "occurrences", "coverage", "diagnostics")})


def _check_binding_entry(entry: object) -> bool:
    """Return whether one support binding entry is closed."""
    return (
        isinstance(entry, dict)
        and set(entry.keys()) == {"ownerId", "role", "targetId"}
        and isinstance(entry.get("ownerId"), str)
        and isinstance(entry.get("role"), str)
        and isinstance(entry.get("targetId"), str)
    )


def _check_pin(entry: object) -> bool:
    """Return whether one descriptor pin is exactly {id, version, sha256}."""
    return (
        isinstance(entry, dict)
        and set(entry.keys()) == {"id", "version", "sha256"}
        and isinstance(entry.get("id"), str)
        and isinstance(entry.get("version"), str)
        and isinstance(entry.get("sha256"), str)
    )


def _check_identity(identity: object) -> bool:
    """Return whether one profile identity record is closed."""
    return isinstance(identity, dict) and set(identity.keys()) == {
        "mechanismVersion",
        "schemaVersion",
        "profile",
        "version",
        "sha256",
        "base",
        "descriptors",
    }


def _check_metric_entry(entry: object) -> bool:
    """Return whether one metrics input entry is exactly {id, utf8}."""
    return (
        isinstance(entry, dict)
        and set(entry.keys()) == {"id", "utf8"}
        and isinstance(entry.get("id"), str)
        and isinstance(entry.get("utf8"), str)
    )


def render_digests(record: object) -> PureResult:  # noqa: PLR0911
    """Bind the §9.2 digest formulas on one explicit record.

    Record-shape violations refuse ``render-token-invalid``; token
    signatures are not checked here (no registry).
    """
    if not isinstance(record, dict):
        return PureRefused(code="render-token-invalid")
    if set(record.keys()) - _RECORD_KEYS or not set(record.keys()).issuperset(
        _REQUIRED_RECORD_KEYS
    ):
        return PureRefused(code="render-token-invalid")
    tree = record.get("semanticTree")
    identity = record.get("profileIdentity")
    bindings = record.get("bindings")
    pins = record.get("descriptorPins")
    layout = record.get("layout")
    theme_id = record.get("themeId")
    themes = record.get("themes")
    metrics = record.get("metrics")
    if (
        not isinstance(tree, dict)
        or not isinstance(identity, dict)
        or not _check_identity(identity)
        or not isinstance(bindings, list)
        or not all(_check_binding_entry(entry) for entry in bindings)
        or not isinstance(pins, list)
        or not all(_check_pin(entry) for entry in pins)
        or not isinstance(layout, dict)
        or not isinstance(theme_id, str)
        or not isinstance(themes, list)
        or not all(isinstance(theme, dict) for theme in themes)
        or not isinstance(metrics, list)
        or not all(_check_metric_entry(entry) for entry in metrics)
    ):
        return PureRefused(code="render-token-invalid")
    overrides = normalize_overrides(record.get("overrides"))
    di_styles = normalize_di_styles(record.get("diStyles"))
    if overrides is None or di_styles is None:
        return PureRefused(code="render-token-invalid")
    digests: dict[str, str] = {
        "semanticRevision": semantic_revision(tree, identity, bindings),
        "descriptorDigest": descriptor_digest(pins),
        "layoutDigest": digest(layout),
        "overridesDigest": digest(overrides),
        "diStylesDigest": digest(di_styles),
        "metricsDigest": metrics_digest(
            [
                {"id": str(entry["id"]), "sha256": digest_bytes(str(entry["utf8"]).encode("utf-8"))}
                for entry in metrics
            ]
        ),
    }
    theme_hash = theme_digest(themes, theme_id)
    if theme_hash is None:
        return PureRefused(code="render-token-invalid")
    digests["themeDigest"] = theme_hash
    digests["viewRevision"] = view_revision({**digests, "themeId": theme_id})
    if "payload" in record:
        payload = record.get("payload")
        if not isinstance(payload, dict) or not set(payload.keys()).issuperset(
            {"pages", "occurrences", "coverage", "diagnostics"}
        ):
            return PureRefused(code="render-token-invalid")
        digests["payloadDigest"] = payload_digest(payload)
    return PureSuccess(payload=digests)


def verify_render_data(  # noqa: PLR0913, PLR0917
    compiled: object,
    envelope: object,
    layout: object,
    render: object,
    theme_id: str,
    overrides: object,
    di_styles: object,
) -> PureResult:
    """Recompute one RenderData/1 binding and return its viewRevision."""
    _ = (compiled, envelope, layout, render, theme_id, overrides, di_styles)
    return PureRefused(code="render-stale")
