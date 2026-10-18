"""Envelope, bridge, results codec and inventory checks."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MECHANISM = ROOT / "contracts" / "profile-mechanism" / "1"


def _identity() -> dict[str, object]:
    profile = json.loads((MECHANISM / "neutral-profile.json").read_text(encoding="utf-8"))
    assert isinstance(profile, dict)
    return {
        "mechanismVersion": "1",
        "schemaVersion": "1.0.0",
        "profile": profile["profile"],
        "version": profile["version"],
        "sha256": "00" * 32,
        "base": profile["base"],
        "descriptors": profile["descriptors"],
    }


def test_envelope_round_trip_and_revision() -> None:
    """Bindings sort in UTF-16 order and the revision covers the projection."""
    from bpmn_io.profile import complete_envelope, validate_envelope

    tree: dict[str, object] = {"$type": "bpmn:Definitions", "id": "Defs_1"}
    bindings = [
        {"ownerId": "b", "role": "r", "targetId": "t2"},
        {"ownerId": "a", "role": "r", "targetId": "t1"},
    ]
    envelope = complete_envelope(_identity(), tree, bindings)
    assert [b["ownerId"] for b in envelope.bindings] == ["a", "b"]
    assert validate_envelope(envelope.to_json()) is None
    assert envelope.semantic_revision != ""


def test_envelope_import_codec_boundary() -> None:
    """Bytes decode through the wired default; junk refuses; injection wins."""
    from bpmn_io.profile import import_envelope

    wired = import_envelope(b'{"tree": {}}', _identity())
    assert wired.status == "ok"
    assert wired.payload is not None
    for junk in (b"not json", b"[1, 2]", b"\xff\xfe"):
        refused = import_envelope(junk, _identity())
        assert refused.status == "refused"
        assert refused.code == "document-not-loaded"  # type: ignore[union-attr]
    injected = import_envelope(
        b'{"$type": "bpmn:Definitions"}',
        _identity(),
        codec=lambda raw: json.loads(raw.decode("utf-8")),
    )
    assert injected.status == "ok"


def test_results_codec_is_canonical() -> None:
    """Result payloads encode with profile-c14n key order."""
    from bpmn_io.profile import digest, jcs, make_report, result_success

    report = make_report("complete")
    result = result_success(
        "complete",
        {"profile": "neutral/1"},
        "base-rev",
        "rev",
        report,
        {"b": 1, "a": 2},
    )
    payload = result.to_json()
    assert isinstance(payload, dict)
    assert jcs(payload["payload"]) == '{"a":2,"b":1}'
    assert digest(payload["payload"]) != ""


def test_bridge_headless_lifecycle() -> None:
    """The headless bridge loads, reads and guards revisions."""
    from bpmn_io.profile import complete_envelope, create_bridge

    bridge = create_bridge()
    empty = bridge.get_definitions()
    assert empty.status == "refused"
    envelope = complete_envelope(_identity(), {"$type": "bpmn:Definitions", "id": "Defs_1"}, [])
    loaded = bridge.set_definitions(envelope)
    assert loaded.status == "ok"
    read = bridge.get_definitions()
    assert read.status == "ok"
    guarded = bridge.set_definitions(envelope, expected_revision="stale")
    assert guarded.status == "refused"
    snapshot = bridge.get_snapshot()
    assert snapshot.status == "ok"


def test_inventory_scan_stays_clean() -> None:
    """The generic package carries no hashed lexicon hits."""
    from bpmn_io.profile import INVENTORY_HASHES, scan_paths_for_hashes

    assert len(INVENTORY_HASHES) == 11
    paths = sorted((ROOT / "src" / "bpmn_io" / "profile").rglob("*.py"))
    assert scan_paths_for_hashes(paths) == []
