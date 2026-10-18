"""Compatibility decision (DESIGN R3.3 §3.3, binding §9.1).

Applies the matrix rows in order with P1 source-dependent remedies and the
P2 schema axis. Returns exactly one verdict: ``ok`` or a refusal with a code
from the 20-code registry, plus the bare refusal for an otherwise exact but
invalid envelope.
"""

from __future__ import annotations

import re

__all__ = ["check_compatibility"]

_SEMVER_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")

_KNOWN_AND_AVAILABLE = "known-and-available"


def _parse_version(value: object) -> tuple[int, int, int] | None:
    """Parse one business version; ``None`` when unknown or unparseable."""
    if not isinstance(value, str):
        return None
    match = _SEMVER_RE.fullmatch(value)
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _identity_equal(first: object, second: object) -> bool:
    """Compare two profile identities for exact equality."""
    if first is None or second is None:
        return first is None and second is None
    if not isinstance(first, dict) or not isinstance(second, dict):
        return False
    keys = (
        "mechanismVersion",
        "schemaVersion",
        "profile",
        "version",
        "sha256",
        "base",
        "descriptors",
    )
    for key in keys:
        first_value = first.get(key)
        second_value = second.get(key)
        if key == "descriptors":
            if _descriptors_equal(first_value, second_value) is False:
                return False
        elif first_value != second_value:
            return False
    return True


def _descriptors_equal(first: object, second: object) -> bool:
    """Compare two descriptor pin lists as multisets."""
    if not isinstance(first, list) or not isinstance(second, list):
        return first == second

    def _sort_key(entry: object) -> tuple[str, str, str]:
        if not isinstance(entry, dict):
            return ("", "", "")
        return (
            str(entry.get("id", "")),
            str(entry.get("version", "")),
            str(entry.get("sha256", "")),
        )

    return sorted(first, key=_sort_key) == sorted(second, key=_sort_key)


def _known_digest(value: object) -> bool:
    """Return whether a profile digest counts as known."""
    return (
        isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    )


def _known_version(value: object) -> bool:
    """Return whether a business version counts as known."""
    return _parse_version(value) is not None


def _source_ok(source_availability: object) -> bool:
    """Return whether the exact source package is known and available."""
    return source_availability == _KNOWN_AND_AVAILABLE


def _doc_known(document_identity: object) -> bool:
    """Return whether the document version and digest are both known."""
    if not isinstance(document_identity, dict):
        return False
    return _known_version(document_identity.get("version")) and _known_digest(
        document_identity.get("sha256")
    )


def check_compatibility(  # noqa: C901, PLR0912, PLR0911, PLR0915, PLR0913
    runtime: dict[str, object],
    injected_identity: dict[str, object] | None,
    document_identity: dict[str, object] | None,
    *,
    document_version: str | None = None,
    host_identity: dict[str, object] | None = None,
    snapshot_identity: dict[str, object] | None = None,
    source_availability: str = "unknown",
    selected_migration: bool = False,
    required_capabilities: list[str] | None = None,
    required_assets: list[str] | None = None,
    envelope_valid: bool = True,
) -> dict[str, object]:
    """Decide compatibility per DESIGN §3.3 in row order with P1/P2.

    Inputs carry the envelope ``document_version`` and the host, snapshot
    and document identities alongside the runtime, the injected and document
    profile identities, source availability, the selected migration flag,
    required capabilities/assets and envelope validity. Returns
    ``{"status": "ok"}`` or ``{"status": "refused", "code": ...}`` (the exact
    but invalid envelope yields a bare ``{"status": "refused"}`` with no code).
    """
    _ = selected_migration
    required_caps: list[str] = list(required_capabilities or [])
    required_ass: list[str] = list(required_assets or [])
    mechanisms = runtime.get("mechanisms")
    schemas = runtime.get("schemas")
    runtime_capabilities = runtime.get("capabilities")
    runtime_assets = runtime.get("assets")
    runtime_mechanisms: list[str] = (
        [str(m) for m in mechanisms] if isinstance(mechanisms, list) else []
    )
    runtime_schemas: list[str] = [str(s) for s in schemas] if isinstance(schemas, list) else []
    runtime_caps: list[str] = (
        [str(c) for c in runtime_capabilities] if isinstance(runtime_capabilities, list) else []
    )
    runtime_ass: list[str] = (
        [str(a) for a in runtime_assets] if isinstance(runtime_assets, list) else []
    )

    # Standalone XML (no envelope at all) previews as missing metadata.
    if document_version is None and not isinstance(document_identity, dict):
        return {"status": "refused", "code": "profile-metadata-missing"}

    # Row 1: unknown envelope document version.
    if document_version != "1":
        return {"status": "refused", "code": "document-version-unsupported"}

    # Row 2: missing envelope/profile metadata.
    if not isinstance(document_identity, dict) or not isinstance(injected_identity, dict):
        return {"status": "refused", "code": "profile-metadata-missing"}

    # Row 3: conflicting host, snapshot and document identities.
    present: list[dict[str, object]] = [
        candidate
        for candidate in (host_identity, snapshot_identity, document_identity)
        if isinstance(candidate, dict)
    ]
    for i in range(len(present)):
        for j in range(i + 1, len(present)):
            if not _identity_equal(present[i], present[j]):
                return {"status": "refused", "code": "profile-metadata-conflict"}

    injected_mechanism = injected_identity.get("mechanismVersion")
    injected_schema = injected_identity.get("schemaVersion")
    document_mechanism = document_identity.get("mechanismVersion")
    document_schema = document_identity.get("schemaVersion")

    # Row 4 (P2): injected P schema unsupported by R.
    if not isinstance(injected_schema, str) or injected_schema not in runtime_schemas:
        return {"status": "refused", "code": "profile-schema-version"}

    # Row 5: injected P mechanism unsupported by R.
    if not isinstance(injected_mechanism, str) or injected_mechanism not in runtime_mechanisms:
        return {"status": "refused", "code": "mechanism-version-unsupported"}

    # Row 6: document D mechanism unsupported by R.
    if not isinstance(document_mechanism, str) or document_mechanism not in runtime_mechanisms:
        return {"status": "refused", "code": "document-mechanism-unsupported"}

    # Row 7 (P2): document D schema unsupported by R.
    if not isinstance(document_schema, str) or document_schema not in runtime_schemas:
        return {"status": "refused", "code": "document-schema-unsupported"}

    source_ok = _source_ok(source_availability)
    doc_known = _doc_known(document_identity)

    def _p1() -> dict[str, object]:
        """Yield the P1 remedy override for source-dependent rows."""
        return {"status": "refused", "code": "profile-source-unavailable"}

    # Row 8: supported unequal mechanisms (source-dependent, P1).
    if injected_mechanism != document_mechanism:
        if not source_ok or not doc_known:
            return _p1()
        return {"status": "refused", "code": "mechanism-migration-required"}

    # Row 9 (P2): supported unequal schemas (source-dependent, P1).
    if injected_schema != document_schema:
        if not source_ok or not doc_known:
            return _p1()
        return {"status": "refused", "code": "profile-schema-migration-required"}

    # Row 10: missing capability/asset (ordered, never P1-overridden).
    for name in required_caps:
        if name not in runtime_caps:
            return {"status": "refused", "code": "profile-capability"}
    for name in required_ass:
        if name not in runtime_ass:
            return {"status": "refused", "code": "profile-resource-missing"}

    # Row 11: base/descriptor pins differ (source-dependent, P1).
    injected_base = injected_identity.get("base")
    document_base = document_identity.get("base")
    if injected_base != document_base:
        if not source_ok or not doc_known:
            return _p1()
        return {"status": "refused", "code": "base-mismatch"}
    if not _descriptors_equal(
        injected_identity.get("descriptors"), document_identity.get("descriptors")
    ):
        if not source_ok or not doc_known:
            return _p1()
        return {"status": "refused", "code": "descriptor-mismatch"}

    # Row 12: business IDs/majors differ (source-dependent, P1).
    injected_profile = injected_identity.get("profile")
    document_profile = document_identity.get("profile")
    injected_version = injected_identity.get("version")
    document_version_value = document_identity.get("version")
    injected_parsed = _parse_version(injected_version)
    document_parsed = _parse_version(document_version_value)
    if injected_profile != document_profile:
        if not source_ok or not doc_known:
            return _p1()
        return {"status": "refused", "code": "profile-major-mismatch"}
    if (
        injected_parsed is not None
        and document_parsed is not None
        and injected_parsed[0] != document_parsed[0]
    ):
        if not source_ok or not doc_known:
            return _p1()
        return {"status": "refused", "code": "profile-major-mismatch"}
    if injected_parsed is None or document_parsed is None:
        # Unparseable business versions with equal IDs fall through to the
        # source row when the document side is unknown; otherwise treat as a
        # major mismatch only when the source is available and known.
        if injected_profile == document_profile and (not source_ok or not doc_known):
            return _p1()
        if injected_profile == document_profile and (
            injected_parsed is None or document_parsed is None
        ):
            # When both sides carry the same ID but versions cannot be ordered
            # and the source is available, keep the ordered major diagnostic.
            if source_ok and doc_known:
                return {"status": "refused", "code": "profile-major-mismatch"}
            return _p1()

    # Row 13: same ID/version with known unequal digests (never P1).
    injected_digest = injected_identity.get("sha256")
    document_digest = document_identity.get("sha256")
    if (
        injected_profile == document_profile
        and injected_version == document_version_value
        and isinstance(injected_digest, str)
        and isinstance(document_digest, str)
        and injected_digest != document_digest
        and _known_digest(injected_digest)
        and _known_digest(document_digest)
    ):
        return {"status": "refused", "code": "profile-digest-mismatch"}

    # Rows 14-17: patch/minor steps (source-dependent, P1).
    if (
        injected_profile == document_profile
        and injected_parsed is not None
        and document_parsed is not None
        and injected_parsed != document_parsed
        and injected_parsed[0] == document_parsed[0]
    ):
        if not source_ok or not doc_known:
            return _p1()
        injected_major, injected_minor, injected_patch = injected_parsed
        document_major, document_minor, document_patch = document_parsed
        _ = (injected_major, document_major)
        if injected_minor == document_minor:
            if injected_patch > document_patch:
                return {
                    "status": "refused",
                    "code": "profile-patch-migration-required",
                }
            return {
                "status": "refused",
                "code": "profile-patch-downgrade-required",
            }
        if injected_minor > document_minor:
            return {
                "status": "refused",
                "code": "profile-minor-migration-required",
            }
        return {"status": "refused", "code": "profile-minor-downgrade-required"}

    # Row 18: unknown version/digest or unavailable source.
    if not source_ok or not doc_known:
        return {"status": "refused", "code": "profile-source-unavailable"}

    # Row 19: exact and valid accepts; exact but invalid stays bare.
    if not envelope_valid:
        return {"status": "refused"}
    return {"status": "ok"}
