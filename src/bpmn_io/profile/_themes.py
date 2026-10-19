"""Theme resolution, fallback chains and shared operation gates (DESIGN §9).

Theme ids resolve by id first, then by a unique declared alias. Shared
operation helpers coerce envelopes (object or validated wire mapping) and
run the DESIGN §3.3 compatibility decision before any lot-4 stage.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from bpmn_io.profile._compat import check_compatibility
from bpmn_io.profile._envelope import DocumentEnvelope, validate_envelope
from bpmn_io.profile._results import PureRefused, PureResult, PureSuccess

__all__ = [
    "GENERIC_REGION_PATTERN",
    "GEOMETRY_TOKEN_NAMES",
    "check_compatibility_gate",
    "check_theme_switch",
    "coerce_envelope",
    "resolve_theme_id",
    "resolved_geometry_map",
    "theme_chain",
]

Json = Any

#: Generic region-token pattern (DESIGN §9.3) for geometry-map collection.
GENERIC_REGION_PATTERN = r"^region\.[A-Za-z_][A-Za-z0-9_-]*\.(headerWidth|padding|gap|minHeight)$"

#: Non-region token names that affect geometry (DESIGN §9.4, spec §14).
GEOMETRY_TOKEN_NAMES = frozenset({"fontFamily", "fontSize", "fontWeight"})

_RUNTIME = {
    "mechanisms": ["1"],
    "schemas": ["1.0.0"],
    "capabilities": [],
    "assets": [],
}


def _profile_themes(compiled: object) -> list[dict[str, Json]]:
    """Return the compiled profile theme records (empty when absent)."""
    profile = getattr(compiled, "profile", None)
    if not isinstance(profile, dict):
        return []
    themes = profile.get("themes")
    return (
        [theme for theme in themes if isinstance(theme, dict)] if isinstance(themes, list) else []
    )


def resolve_theme_id(
    profile: dict[str, Json], theme_id: str
) -> tuple[dict[str, Json] | None, str | None]:
    """Resolve one theme id or alias to ``(theme, id)`` or ``(None, code)``.

    The id wins first; otherwise the unique theme listing it in
    ``aliases`` resolves (an ambiguous or unknown name is stale input).
    """
    themes = profile.get("themes")
    if not isinstance(themes, list) or not isinstance(theme_id, str):
        return None, "render-stale"
    for theme in themes:
        if isinstance(theme, dict) and theme.get("id") == theme_id:
            return theme, str(theme.get("id"))
    matches = [
        theme
        for theme in themes
        if isinstance(theme, dict) and theme_id in (theme.get("aliases") or [])
    ]
    if len(matches) == 1 and isinstance(matches[0].get("id"), str):
        return matches[0], str(matches[0].get("id"))
    return None, "render-stale"


def theme_chain(themes: list[dict[str, Json]], theme_id: str) -> list[dict[str, Json]] | None:
    """Resolve the fallback chain from the fallback root to ``theme_id``.

    Returns ``None`` when the id is unknown or the chain breaks or cycles.
    """
    by_id = {
        str(theme["id"]): theme
        for theme in themes
        if isinstance(theme, dict) and isinstance(theme.get("id"), str)
    }
    if theme_id not in by_id:
        return None
    chain: list[dict[str, Json]] = []
    current: str | None = theme_id
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


def _theme_token_map(theme: dict[str, Json]) -> dict[str, Json]:
    """Return one theme's own token map (name to value)."""
    tokens = theme.get("tokens")
    if not isinstance(tokens, list):
        return {}
    return {
        str(entry["name"]): entry["value"]
        for entry in tokens
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    }


def resolved_geometry_map(chain: list[dict[str, Json]]) -> dict[str, Json]:
    """Resolve geometry-affecting tokens through a chain, nearest first.

    Region tokens match the generic DESIGN §9.3 pattern; ``fontFamily``,
    ``fontSize`` and ``fontWeight`` are geometry-affecting by name. A name
    present in one chain only is a difference the caller reports.
    """
    try:
        pattern = re.compile(GENERIC_REGION_PATTERN)
    except re.error:
        return {}
    resolved: dict[str, Json] = {}
    for theme in reversed(chain):
        for name, value in _theme_token_map(theme).items():
            if name in resolved:
                continue
            if name not in GEOMETRY_TOKEN_NAMES and pattern.fullmatch(name) is None:
                continue
            resolved[name] = value
    return resolved


def _switch_pair(
    compiled: object, from_theme: str, to_theme: str
) -> tuple[dict[str, Json] | None, dict[str, Json] | None, str | None]:
    """Resolve one theme-switch pair (source, target, code)."""
    profile = getattr(compiled, "profile", None)
    if not isinstance(profile, dict):
        return None, None, "render-stale"
    source, _ = resolve_theme_id(profile, from_theme)
    target, _ = resolve_theme_id(profile, to_theme)
    if source is None or target is None:
        return None, None, "render-stale"
    if source.get("geometry") == "theme" or target.get("geometry") == "theme":
        return None, None, "profile-open"
    return source, target, None


def check_theme_switch(compiled: object, from_theme: str, to_theme: str) -> PureResult:
    """Check one theme switch without comparing other profile themes."""
    source, target, code = _switch_pair(compiled, from_theme, to_theme)
    if code is not None or source is None or target is None:
        return PureRefused(code=code or "render-stale")
    themes = _profile_themes(compiled)
    source_chain = theme_chain(themes, str(source.get("id")))
    target_chain = theme_chain(themes, str(target.get("id")))
    if source_chain is None or target_chain is None:
        return PureRefused(code="render-stale")
    if resolved_geometry_map(source_chain) != resolved_geometry_map(target_chain):
        return PureRefused(code="theme-geometry-conflict")
    if source.get("metricsResource") != target.get("metricsResource"):
        return PureRefused(code="theme-geometry-conflict")
    return PureSuccess(payload={"relayoutRequired": False})


_IDENTITY_KEYS = frozenset(
    {"mechanismVersion", "schemaVersion", "profile", "version", "sha256", "base", "descriptors"}
)

_HEX64_PATTERN = r"[0-9a-f]{64}"


def _identity_shape_code(identity: dict[str, Json]) -> str | None:
    """Check one profile identity shape (None when shape-valid)."""
    if set(identity.keys()) != _IDENTITY_KEYS:
        return "profile-schema"
    for key in ("mechanismVersion", "schemaVersion", "profile", "version", "sha256"):
        if not isinstance(identity.get(key), str):
            return "profile-schema"
    if not isinstance(identity.get("base"), dict) or not isinstance(
        identity.get("descriptors"), list
    ):
        return "profile-schema"
    if identity.get("mechanismVersion") != "1" or identity.get("schemaVersion") != "1.0.0":
        return "profile-schema"
    if re.fullmatch(_HEX64_PATTERN, str(identity.get("sha256"))) is None:
        return "profile-schema"
    return None


def envelope_echo(wire: object) -> tuple[dict[str, Json] | None, str | None]:
    """Echo the envelope identity and revision when the echo shape holds.

    The §3.4 echo needs a JSON object with ``documentVersion: "1"``, a
    shape-valid profile identity and a string revision; otherwise no
    identity or revision is echoed.
    """
    if not isinstance(wire, dict) or wire.get("documentVersion") != "1":
        return None, None
    identity = wire.get("profileIdentity")
    revision = wire.get("semanticRevision")
    if not isinstance(identity, dict) or not isinstance(revision, str):
        return None, None
    if _identity_shape_code(identity) is not None:
        return None, None
    return copy.deepcopy(identity), revision


def coerce_envelope(envelope: object) -> tuple[dict[str, Json] | None, str | None]:
    """Coerce an envelope object or wire mapping to its wire value.

    Returns ``(wire, None)`` or ``(None, code)``. Mappings are validated
    with block-A ``validate_envelope`` before use, never trusted raw.
    """
    if isinstance(envelope, DocumentEnvelope):
        wire = envelope.to_json()
    elif isinstance(envelope, dict):
        wire = copy.deepcopy(envelope)
    else:
        return None, "profile-schema"
    code = validate_envelope(wire, committed=True)
    if code is not None:
        return None, code
    return wire, None


def check_compatibility_gate(compiled: object, identity: dict[str, Json]) -> str | None:
    """Run the DESIGN §3.3 decision for one envelope identity (code or None).

    The exact source package is the compiled profile itself, so the
    source-dependent rows decide with their specific codes (never P1).
    """
    injected = getattr(compiled, "identity", None)
    verdict = check_compatibility(
        dict(_RUNTIME),
        injected if isinstance(injected, dict) else None,
        identity,
        document_version="1",
        source_availability="known-and-available",
    )
    if verdict.get("status") == "ok":
        return None
    code = verdict.get("code")
    return str(code) if isinstance(code, str) else "profile-digest-mismatch"
