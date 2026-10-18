"""Profile loader (DESIGN R3.3 §2).

Lexical pre-parse with §2.1.1 codes and precedence, closed JSON Schema
validation over the actually used keyword subset, schema identity checks and
digest-pinned closure for base, descriptors, assets and capabilities.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from bpmn_io.profile._c14n import digest, digest_bytes
from bpmn_io.profile._lexical import check_lexical
from bpmn_io.profile._results import PureRefused, PureResult, PureSuccess
from bpmn_io.profile._schema import SchemaRefusal, validate

__all__ = ["ValidatedProfile", "load_profile"]


@dataclass(frozen=True)
class ValidatedProfile:
    """One schema-valid profile with its canonical digest and pins."""

    profile: dict[str, object]
    digest: str
    schema_id: str
    base: dict[str, object]
    descriptors: list[dict[str, object]]
    capabilities: list[str]


def _parse_json_bytes(data: bytes) -> tuple[dict[str, object] | None, str | None]:
    """Parse profile bytes after lexical success; refuse junk as profile-json."""
    try:
        text = data.decode("utf-8")
        value = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None, "profile-json"
    if not isinstance(value, dict):
        return None, "profile-schema"
    return value, None


def load_profile(  # noqa: PLR0913, PLR0911, PLR0912, C901
    data: bytes,
    *,
    schema_bytes: bytes | None = None,
    descriptor_pins: list[dict[str, object]] | None = None,
    base_bytes: bytes | None = None,
    asset_bag: dict[str, bytes] | None = None,
    capabilities: list[str] | None = None,
    registry: dict[str, object] | None = None,
) -> PureResult:
    """Load and validate one profile document.

    Runs the strict lexical pre-parse first (exactly one of the four closed
    codes on failure), then validates the parsed value against the supplied
    ``schema_bytes`` with the closed subset validator. Pin arguments are
    optional digest-pinned closure inputs: ``base_bytes`` raw bytes must hash
    to the profile ``base.sha256``, ``descriptor_pins`` must equal the profile
    descriptors when supplied, ``asset_bag`` maps asset keys to raw bytes
    whose digests must match ``resources`` entries, and ``capabilities`` must
    include every profile capability. Pin mismatches refuse ``profile-pin``;
    capability gaps refuse ``profile-capability``.
    """
    lexical = check_lexical(data)
    if lexical.status == "refused":
        return PureRefused(code=lexical.code)
    profile, parse_code = _parse_json_bytes(data)
    if profile is None:
        code = parse_code or "profile-json"
        return PureRefused(code=code)
    if schema_bytes is None:
        return PureRefused(code="profile-schema")
    try:
        schema = json.loads(schema_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return PureRefused(code="profile-schema-keyword")
    pinned: dict[str, object] = dict(registry) if registry else {}
    try:
        valid = validate(schema, profile, pinned)
    except SchemaRefusal as exc:
        return PureRefused(code=exc.code)
    if not valid:
        return PureRefused(code="profile-schema")
    base = profile.get("base")
    descriptors = profile.get("descriptors")
    profile_capabilities = profile.get("capabilities")
    if not isinstance(base, dict) or not isinstance(descriptors, list):
        return PureRefused(code="profile-schema")
    if not isinstance(profile_capabilities, list):
        return PureRefused(code="profile-schema")
    if base_bytes is not None:
        want = base.get("sha256")
        if not isinstance(want, str) or digest_bytes(base_bytes) != want:
            return PureRefused(code="profile-pin")
    if descriptor_pins is not None:
        want_descriptors = [
            dict(entry) if isinstance(entry, dict) else entry for entry in descriptor_pins
        ]
        if list(descriptors) != want_descriptors and digest(descriptors) != digest(
            want_descriptors
        ):
            return PureRefused(code="profile-pin")
    if capabilities is not None:
        for name in profile_capabilities:
            if not isinstance(name, str) or name not in capabilities:
                return PureRefused(code="profile-capability")
    if asset_bag is not None:
        resources = profile.get("resources")
        if isinstance(resources, list):
            for entry in resources:
                if not isinstance(entry, dict):
                    return PureRefused(code="profile-schema")
                key = entry.get("assetKey")
                want_digest = entry.get("sha256")
                if not isinstance(key, str) or not isinstance(want_digest, str):
                    continue
                raw = asset_bag.get(key)
                if raw is None or digest_bytes(raw) != want_digest:
                    return PureRefused(code="profile-pin")
    schema_id = schema.get("$id") if isinstance(schema, dict) else None
    return PureSuccess(
        payload=ValidatedProfile(
            profile=profile,
            digest=digest(profile),
            schema_id=str(schema_id or ""),
            base=dict(base),
            descriptors=[dict(e) for e in descriptors if isinstance(e, dict)],
            capabilities=[str(c) for c in profile_capabilities if isinstance(c, str)],
        )
    )
