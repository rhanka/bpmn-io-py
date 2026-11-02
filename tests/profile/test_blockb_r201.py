"""Block-B R2-01: compatibility decision order (compatibility.ts:38-76).

Public ``check_compatibility`` witnesses for the J1-J21 transcription:
target knowledge, canonical equality and the unconditional J14 row.
"""

from __future__ import annotations

import copy

RUNTIME: dict[str, object] = {
    "mechanisms": ["1"],
    "schemas": ["1.0.0"],
    "capabilities": [],
    "assets": [],
}

DOCUMENT: dict[str, object] = {
    "mechanismVersion": "1",
    "schemaVersion": "1.0.0",
    "profile": "neutral/1",
    "version": "1.1.0",
    "sha256": "a" * 64,
    "base": {
        "id": "neutral-base/1",
        "version": "fixture-2",
        "sha256": "b" * 64,
    },
    "descriptors": [
        {"id": "d1", "version": "fixture-2", "sha256": "c" * 64},
        {"id": "d2", "version": "fixture-1", "sha256": "d" * 64},
    ],
}


def _check(
    injected: dict[str, object] | None,
    document: dict[str, object] | None,
    document_version: str | None = "1",
) -> dict[str, object]:
    """Run the public compatibility decision for one injected identity."""
    from bpmn_io.profile import check_compatibility

    return check_compatibility(
        dict(RUNTIME),
        injected,
        document,
        document_version=document_version,
        source_availability="known-and-available",
    )


def test_r201_target_digest_unknown_refuses_source_unavailable() -> None:
    """An unknown target digest refuses even with exact versions (J17)."""
    injected = copy.deepcopy(DOCUMENT)
    injected["sha256"] = "unknown"
    got = _check(injected, copy.deepcopy(DOCUMENT))
    assert got == {"status": "refused", "code": "profile-source-unavailable"}


def test_r201_target_version_unknown_refuses_source_unavailable() -> None:
    """An unknown target version refuses unconditionally (J14)."""
    injected = copy.deepcopy(DOCUMENT)
    injected["version"] = "unknown"
    got = _check(injected, copy.deepcopy(DOCUMENT))
    assert got == {"status": "refused", "code": "profile-source-unavailable"}


def test_r201_extra_identity_key_refuses_bare() -> None:
    """An extra identity key breaks canonical equality (J20 bare refusal)."""
    injected = copy.deepcopy(DOCUMENT)
    injected["extra"] = "x"
    got = _check(injected, copy.deepcopy(DOCUMENT))
    assert got == {"status": "refused"}


def test_r201_extra_pin_key_refuses_descriptor_mismatch() -> None:
    """An extra pin key breaks canonical descriptor equality (J13)."""
    injected = copy.deepcopy(DOCUMENT)
    descriptors = injected["descriptors"]
    assert isinstance(descriptors, list)
    first = dict(descriptors[0])  # type: ignore[arg-type]
    first["extra"] = "x"
    descriptors[0] = first
    got = _check(injected, copy.deepcopy(DOCUMENT))
    assert got == {"status": "refused", "code": "descriptor-mismatch"}
