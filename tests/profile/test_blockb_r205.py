"""Block-B R2-05: absent envelope documentVersion (compatibility.ts:43-44).

Public ``check_compatibility`` witnesses: only a present documentVersion
other than "1" refuses document-version-unsupported; an absent one refuses
profile-metadata-missing.
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
    document_version: str | None,
) -> dict[str, object]:
    """Run the public compatibility decision for one envelope version."""
    from bpmn_io.profile import check_compatibility

    return check_compatibility(
        dict(RUNTIME),
        injected,
        document,
        document_version=document_version,
        source_availability="known-and-available",
    )


def test_r205_absent_document_version_refuses_metadata_missing() -> None:
    """An absent documentVersion refuses profile-metadata-missing (J2)."""
    got = _check(copy.deepcopy(DOCUMENT), copy.deepcopy(DOCUMENT), None)
    assert got == {"status": "refused", "code": "profile-metadata-missing"}


def test_r205_absent_version_unknown_digest_refuses_metadata_missing() -> None:
    """J2 wins before any knowledge row when the version is absent."""
    injected = copy.deepcopy(DOCUMENT)
    injected["sha256"] = "unknown"
    got = _check(injected, copy.deepcopy(DOCUMENT), None)
    assert got == {"status": "refused", "code": "profile-metadata-missing"}


def test_r205_other_version_refuses_unsupported() -> None:
    """A present version other than "1" refuses document-version-unsupported."""
    got = _check(copy.deepcopy(DOCUMENT), copy.deepcopy(DOCUMENT), "2")
    assert got == {"status": "refused", "code": "document-version-unsupported"}


def test_r205_empty_version_refuses_unsupported() -> None:
    """The empty string is a present version and refuses unsupported (J1)."""
    got = _check(copy.deepcopy(DOCUMENT), copy.deepcopy(DOCUMENT), "")
    assert got == {"status": "refused", "code": "document-version-unsupported"}


def test_r205_standalone_absent_identity_refuses_metadata_missing() -> None:
    """An absent document identity refuses profile-metadata-missing (J2)."""
    got = _check(None, None, None)
    assert got == {"status": "refused", "code": "profile-metadata-missing"}
