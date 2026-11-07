"""Section 9.2 digest formulas, freshness binds and render validation.

``render_digests`` binds every digest on explicit records; ``view_revision``
binds the seven freshness members; ``verify_render_data`` recomputes a
stored binding from its inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bpmn_io.profile._c14n import digest, digest_bytes
from bpmn_io.profile._render_tokens import normalize_di_styles, normalize_overrides
from bpmn_io.profile._results import PureRefused, PureResult, PureSuccess

__all__ = ["check_render_freshness", "render_digests", "verify_render_data", "view_revision"]

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


@dataclass(frozen=True)
class _FreshnessState:
    """Validated inputs for one freshness recomputation."""

    identity: dict[str, Json]
    descriptors: list[Json]
    themes: list[Json]
    chain: list[dict[str, Json]]
    canonical: str
    assets: object
    tree: dict[str, Json]
    bindings: list[Json]
    layout: dict[str, Json]
    render: dict[str, Json]
    echoes: dict[str, Json]
    normalized_overrides: dict[str, Json] | None
    normalized_styles: dict[str, Json] | None


def _render_echoes(render: object) -> dict[str, Json] | None:
    """Return one RenderData/1 binding echoes record (None when stale)."""
    if not isinstance(render, dict):
        return None
    echoes = render.get("binding")
    return echoes if isinstance(echoes, dict) else None


def _freshness_source(compiled: object, theme_id: object) -> _FreshnessSource | None:
    """Validate compiled parts and the theme chain (None when stale)."""
    identity = getattr(compiled, "identity", None)
    profile = getattr(compiled, "profile", None)
    assets = getattr(compiled, "assets", None)
    if not isinstance(identity, dict) or not isinstance(profile, dict):
        return None
    descriptors = identity.get("descriptors")
    if not isinstance(descriptors, list):
        return None
    themes = profile.get("themes")
    if (
        not isinstance(theme_id, str)
        or not isinstance(themes, list)
        or not all(isinstance(theme, dict) for theme in themes)
    ):
        return None
    chain = theme_chain(themes, theme_id)
    if chain is None:
        return None
    return _FreshnessSource(identity, descriptors, themes, chain, str(chain[-1].get("id")), assets)


@dataclass(frozen=True)
class _FreshnessSource:
    """Compiled profile parts of one freshness check."""

    identity: dict[str, Json]
    descriptors: list[Json]
    themes: list[Json]
    chain: list[dict[str, Json]]
    canonical: str
    assets: object


def _freshness_bags(
    overrides: object, di_styles: object
) -> tuple[dict[str, Json] | None, dict[str, Json] | None] | None:
    """Normalize one overrides/diStyles pair (None when stale)."""
    normalized_overrides = None if overrides is None else normalize_overrides(overrides)
    normalized_styles = None if di_styles is None else normalize_di_styles(di_styles)
    if (overrides is not None and normalized_overrides is None) or (
        di_styles is not None and normalized_styles is None
    ):
        return None
    return normalized_overrides, normalized_styles


def _fresh_static_digests(
    state: _FreshnessState,
) -> tuple[list[dict[str, str]], str] | None:
    """Compute one check's metrics entries and theme digest (None when stale)."""
    metric_entries = _metric_resources(state.chain, state.assets)
    if metric_entries is None:
        return None
    theme_hash = theme_digest(state.themes, state.canonical)
    if theme_hash is None:
        return None
    return metric_entries, theme_hash


def _check_fresh_digests(state: _FreshnessState) -> str | None:
    """Recompute one binding echo by echo (code or None)."""
    static = _fresh_static_digests(state)
    if static is None:
        return "render-stale"
    metric_entries, theme_hash = static
    try:
        fresh: dict[str, object] = {
            "semanticRevision": semantic_revision(state.tree, state.identity, state.bindings),
            "profileDigest": state.identity.get("sha256"),
            "descriptorDigest": descriptor_digest(state.descriptors),
            "layoutDigest": digest(state.layout),
            "themeId": state.canonical,
            "themeDigest": theme_hash,
            "metricsDigest": metrics_digest(metric_entries),
        }
    except Exception:  # noqa: BLE001 - malformed pins are stale input
        return "render-stale"
    if state.normalized_overrides is not None:
        fresh["overridesDigest"] = digest(state.normalized_overrides)
    if state.normalized_styles is not None:
        fresh["diStylesDigest"] = digest(state.normalized_styles)
    try:
        fresh["payloadDigest"] = payload_digest(
            {
                "pages": state.render["pages"],
                "occurrences": state.render["occurrences"],
                "coverage": state.render["coverage"],
                "diagnostics": state.render["diagnostics"],
            }
        )
    except (KeyError, TypeError):
        return "render-stale"
    for key, value in fresh.items():
        if state.echoes.get(key) != value:
            return "render-stale"
    if state.render.get("pages") != state.layout.get("pages"):
        return "render-stale"
    return None


def _check_fresh_geometry(state: _FreshnessState) -> str | None:
    """Check stripped occurrences equal the layout geometry (code or None)."""
    geometry = state.layout.get("geometry") if isinstance(state.layout, dict) else None
    if not isinstance(geometry, list):
        return "render-stale"
    records: dict[tuple[str, str], dict[str, Json]] = {
        (str(record.get("pageId")), str(record.get("occurrenceKey"))): record
        for record in geometry
        if isinstance(record, dict)
    }
    occurrences = state.render.get("occurrences")
    if not isinstance(occurrences, list):
        return "render-stale"
    for occurrence in occurrences:
        if not isinstance(occurrence, dict):
            return "render-stale"
        lookup = (str(occurrence.get("pageId")), str(occurrence.get("occurrenceKey")))
        record = records.get(lookup)
        if record is None:
            return "render-stale"
        stripped = {name: value for name, value in occurrence.items() if name not in _R_ONLY_KEYS}
        if stripped != record:
            return "render-stale"
    return None


def check_render_freshness(  # noqa: PLR0913, PLR0917 - spec §6.2 binding signature
    compiled: object,
    tree: object,
    bindings: object,
    layout: object,
    render: object,
    theme_id: object,
    overrides: object = None,
    di_styles: object = None,
) -> str | None:
    """Check one RenderData/1 binding echo by echo (spec §6.2).

    Returns a refusal code or ``None``. ``overrides``/``di_styles``
    ``None`` skips the two bag digests (``map_export`` does not take
    them; they stay bound through ``viewRevision``). Geometry equality
    strips ``emittedType``, ``style`` and ``glyphId`` (harmonization
    K14).
    """
    echoes = _render_echoes(render)
    if echoes is None:
        return "render-stale"
    source = _freshness_source(compiled, theme_id)
    if source is None:
        return "render-stale"
    bags = _freshness_bags(overrides, di_styles)
    if bags is None:
        return "render-stale"
    normalized_overrides, normalized_styles = bags
    if (
        not isinstance(tree, dict)
        or not isinstance(bindings, list)
        or not isinstance(layout, dict)
        or not isinstance(render, dict)
    ):
        return "render-stale"
    state = _FreshnessState(
        source.identity,
        source.descriptors,
        source.themes,
        source.chain,
        source.canonical,
        source.assets,
        tree,
        bindings,
        layout,
        render,
        echoes,
        normalized_overrides,
        normalized_styles,
    )
    code = _check_fresh_digests(state)
    if code is not None:
        return code
    return _check_fresh_geometry(state)


#: RenderData/1 members no layout geometry record carries (harmonization K14).
_R_ONLY_KEYS = frozenset({"emittedType", "style", "glyphId"})


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
    wire = envelope.to_json() if hasattr(envelope, "to_json") else envelope
    if not isinstance(wire, dict):
        return PureRefused(code="render-stale")
    code = check_render_freshness(
        compiled,
        wire.get("tree"),
        wire.get("bindings"),
        layout,
        render,
        theme_id,
        overrides,
        di_styles,
    )
    if code is not None:
        return PureRefused(code=code)
    echoes = render.get("binding") if isinstance(render, dict) else None
    if not isinstance(echoes, dict):
        return PureRefused(code="render-stale")
    return PureSuccess(payload={"viewRevision": view_revision(echoes)})


def _metric_resources(chain: list[dict[str, Json]], assets: object) -> list[dict[str, str]] | None:
    """Collect ``{id, sha256}`` metrics resources along one theme chain.

    Returns ``None`` when a referenced resource has no verified bytes.
    """
    seen: list[str] = []
    for theme in reversed(chain):
        resource = theme.get("metricsResource")
        if isinstance(resource, str) and resource not in seen:
            seen.append(resource)
    resources: list[dict[str, str]] = []
    for resource in seen:
        raw = assets.get(resource) if isinstance(assets, dict) else None
        if not isinstance(raw, (bytes, bytearray)):
            return None
        resources.append({"id": resource, "sha256": digest_bytes(bytes(raw))})
    return resources
