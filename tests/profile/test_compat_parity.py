"""Compatibility parity: all 151 corpus verdicts through this package."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CORPUS = ROOT / "contracts" / "profile-parity-corpus" / "1"

Json = dict[str, "Json"] | list["Json"] | str | int | float | bool | None


def _matrix_inputs(entry: Json) -> Json:
    assert isinstance(entry, dict)
    matches = [
        a for a in entry["inputArtifacts"] if isinstance(a, dict) and a.get("role") == "matrixInput"
    ]
    assert len(matches) == 1
    assert isinstance(matches[0], dict)
    return matches[0]["json"]


def _matrix_verdict(entry: Json) -> Json:
    assert isinstance(entry, dict)
    matches = [
        a for a in entry["expectedArtifacts"] if isinstance(a, dict) and a.get("role") == "verdict"
    ]
    assert len(matches) == 1
    assert isinstance(matches[0], dict)
    return matches[0]["json"]


def test_compat_group_matches_corpus() -> None:
    """Every compat case yields its authored verdict through this package."""
    from bpmn_io.profile import check_compatibility

    files = sorted(str(p) for p in (CORPUS / "cases").glob("compat-*.json"))
    assert len(files) == 151, f"expected 151 compat cases, saw {len(files)}"
    for path in files:
        case = json.loads(Path(path).read_text(encoding="utf-8"))
        matrix = _matrix_inputs(case)
        assert isinstance(matrix, dict)
        wanted = _matrix_verdict(case)
        document = matrix.get("document")
        if isinstance(document, dict):
            document_identity = document.get("profileIdentity")
            document_version = document.get("documentVersion")
            assert isinstance(document_version, str) or document_version is None
            doc_id = document_identity if isinstance(document_identity, dict) else None
            doc_ver = document_version if isinstance(document_version, str) else None
        else:
            doc_id = None
            doc_ver = None
        runtime = matrix.get("runtime")
        assert isinstance(runtime, dict)
        injected = matrix.get("injected")
        assert isinstance(injected, dict) or injected is None
        got = check_compatibility(
            runtime,
            injected,  # type: ignore[arg-type]
            doc_id,  # type: ignore[arg-type]
            document_version=doc_ver,
            host_identity=matrix.get("hostIdentity"),  # type: ignore[arg-type]
            snapshot_identity=matrix.get("snapshotIdentity"),  # type: ignore[arg-type]
            source_availability=str(matrix.get("sourcePackage", "unknown")),
            selected_migration=bool(matrix.get("selectedMigration", False)),
            required_capabilities=matrix.get("requiredCapabilities"),  # type: ignore[arg-type]
            required_assets=matrix.get("requiredAssets"),  # type: ignore[arg-type]
            envelope_valid=bool(matrix.get("envelopeValid", True)),
        )
        assert got == wanted, f"{Path(path).name}: got {got}, want {wanted}"
        expected_status = str(case["expectedStatus"])
        if got == {"status": "ok"}:
            assert expected_status == "ok", path
        elif "code" in got:
            assert expected_status == "refused:" + str(got["code"]), path
        else:
            assert expected_status == "refused", path


def test_compat_cross_product_ordering() -> None:
    """Precedence probes: version, capability and base ordering hold."""
    from bpmn_io.profile import check_compatibility

    base_identity: dict[str, object] = {
        "mechanismVersion": "1",
        "schemaVersion": "1.0.0",
        "profile": "neutral/1",
        "version": "1.1.0",
        "sha256": "51f0b6b2569d1bbd86f3c37bfc94f26b6b86e8f39a4e84b2748eb1dc7f2232c",
        "base": {
            "id": "neutral-base/1",
            "version": "fixture-2",
            "sha256": "a23a15d22585e765caeb8ad83bedb76c20bcb5fa1f7bee81ef062f4e97a15ea9",
        },
        "descriptors": [
            {
                "id": "neutral-descriptors/1",
                "version": "fixture-2",
                "sha256": "d737e07dc2b397bb02261fb5e7e46b51b7225f58fe82bebaa78cca2e613d62d2",
            }
        ],
    }
    runtime: dict[str, object] = {
        "mechanisms": ["1"],
        "schemas": ["1.0.0"],
        "capabilities": ["one"],
        "assets": [],
    }
    # Unknown document version precedes every identity row.
    got = check_compatibility(
        runtime,
        dict(base_identity),
        None,
        document_version="9",
        source_availability="known-and-available",
    )
    assert got == {"status": "refused", "code": "document-version-unsupported"}
    # Missing capability precedes the source fallback.
    got = check_compatibility(
        runtime,
        dict(base_identity),
        dict(base_identity),
        document_version="1",
        source_availability="unavailable",
        required_capabilities=["missing"],
    )
    assert got == {"status": "refused", "code": "profile-capability"}
