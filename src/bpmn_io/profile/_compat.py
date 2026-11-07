"""Compatibility decision (DESIGN R3.3 §3.3, binding §9.1).

Mirrors ``src/profile/compatibility.ts:38-76`` at ``fec4dae`` in its exact
decision order (rows J1-J21). Applies the matrix rows in order with P1
source-dependent remedies and the P2 schema axis. Returns exactly one
verdict: ``ok`` or a refusal with a code from the 20-code registry, plus
the bare refusal for an otherwise exact but invalid envelope.
"""

from __future__ import annotations

import re

from bpmn_io.profile._c14n import jcs

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


def _same(first: object, second: object) -> bool:
    """Compare two values by canonical equality (``compatibility.ts:20``)."""
    return jcs(first) == jcs(second)


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
    """Decide compatibility per ``compatibility.ts:38-76`` in row order J1-J21.

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

    # J1 (compatibility.ts:43): a present documentVersion other than "1".
    if document_version is not None and document_version != "1":
        return {"status": "refused", "code": "document-version-unsupported"}

    # J2 (compatibility.ts:44): absent documentVersion or absent document.
    if document_version is None or not isinstance(document_identity, dict):
        return {"status": "refused", "code": "profile-metadata-missing"}

    # Python-only guard (JS has no verdict: P is required and throws): N-A.
    if not isinstance(injected_identity, dict):
        return {"status": "refused", "code": "profile-metadata-missing"}

    # J3 (compatibility.ts:46): host/snapshot conflicting with the document.
    for candidate in (host_identity, snapshot_identity):
        if candidate is not None and not _same(candidate, document_identity):
            return {"status": "refused", "code": "profile-metadata-conflict"}

    injected_mechanism = injected_identity.get("mechanismVersion")
    injected_schema = injected_identity.get("schemaVersion")
    document_mechanism = document_identity.get("mechanismVersion")
    document_schema = document_identity.get("schemaVersion")

    # J4 (compatibility.ts:47): injected schema unsupported by R.
    if not isinstance(injected_schema, str) or injected_schema not in runtime_schemas:
        return {"status": "refused", "code": "profile-schema-version"}

    # J5 (compatibility.ts:48): injected mechanism unsupported by R.
    if not isinstance(injected_mechanism, str) or injected_mechanism not in runtime_mechanisms:
        return {"status": "refused", "code": "mechanism-version-unsupported"}

    # J6 (compatibility.ts:49): document mechanism unsupported by R.
    if not isinstance(document_mechanism, str) or document_mechanism not in runtime_mechanisms:
        return {"status": "refused", "code": "document-mechanism-unsupported"}

    # J7 (compatibility.ts:50): document schema unsupported by R.
    if not isinstance(document_schema, str) or document_schema not in runtime_schemas:
        return {"status": "refused", "code": "document-schema-unsupported"}

    target = _parse_version(injected_identity.get("version"))
    source = _parse_version(document_identity.get("version"))
    digests_known = _known_digest(injected_identity.get("sha256")) and _known_digest(
        document_identity.get("sha256")
    )
    source_available = (
        _source_ok(source_availability)
        and target is not None
        and source is not None
        and digests_known
    )

    def _remedy(code: str) -> dict[str, object]:
        """Yield the P1 remedy override for source-dependent rows."""
        if source_available:
            return {"status": "refused", "code": code}
        return {"status": "refused", "code": "profile-source-unavailable"}

    # J8 (compatibility.ts:58): supported unequal mechanisms (P1).
    if injected_mechanism != document_mechanism:
        return _remedy("mechanism-migration-required")

    # J9 (compatibility.ts:59): supported unequal schemas (P1).
    if injected_schema != document_schema:
        return _remedy("profile-schema-migration-required")

    # J10 (compatibility.ts:60): missing capability (never P1).
    for name in required_caps:
        if name not in runtime_caps:
            return {"status": "refused", "code": "profile-capability"}
    # J11 (compatibility.ts:61): missing asset (never P1).
    for name in required_ass:
        if name not in runtime_ass:
            return {"status": "refused", "code": "profile-resource-missing"}

    # J12 (compatibility.ts:62): base mismatch (P1, canonical equality).
    if not _same(injected_identity.get("base"), document_identity.get("base")):
        return _remedy("base-mismatch")

    # J13 (compatibility.ts:63): descriptor mismatch (P1, canonical equality).
    if not _same(injected_identity.get("descriptors"), document_identity.get("descriptors")):
        return _remedy("descriptor-mismatch")

    # J14 (compatibility.ts:64): either version unknown (unconditional).
    if target is None or source is None:
        return {"status": "refused", "code": "profile-source-unavailable"}

    # J15 (compatibility.ts:65): ID or major differ (P1).
    injected_profile = injected_identity.get("profile")
    document_profile = document_identity.get("profile")
    if injected_profile != document_profile or target[0] != source[0]:
        return _remedy("profile-major-mismatch")

    # J16 (compatibility.ts:66): same ID/version with known unequal digests.
    injected_digest = injected_identity.get("sha256")
    document_digest = document_identity.get("sha256")
    injected_version = injected_identity.get("version")
    document_version_value = document_identity.get("version")
    if (
        injected_version == document_version_value
        and digests_known
        and injected_digest != document_digest
    ):
        return {"status": "refused", "code": "profile-digest-mismatch"}

    # J17 (compatibility.ts:67): source not fully known and available.
    if not source_available:
        return {"status": "refused", "code": "profile-source-unavailable"}

    # J18 (compatibility.ts:68-71): patch steps (minors equal).
    if target[1] == source[1]:
        if target[2] > source[2]:
            return {"status": "refused", "code": "profile-patch-migration-required"}
        if target[2] < source[2]:
            return {"status": "refused", "code": "profile-patch-downgrade-required"}

    # J19 (compatibility.ts:72-73): minor steps.
    if target[1] > source[1]:
        return {"status": "refused", "code": "profile-minor-migration-required"}
    if target[1] < source[1]:
        return {"status": "refused", "code": "profile-minor-downgrade-required"}

    # J20 (compatibility.ts:74): exact and valid accepts, else bare refusal.
    if not envelope_valid or not _same(injected_identity, document_identity):
        return {"status": "refused"}

    # J21 (compatibility.ts:75): otherwise ok.
    return {"status": "ok"}
