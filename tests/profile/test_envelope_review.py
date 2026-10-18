"""Envelope and projection review regressions (finding #5).

Expectations come from DESIGN R3.3 §5: the projection is driven by
descriptor roles/value types (never bare names), the committed tree is the
DI-free projection with DI preserved separately, and identity/tree/bindings
face closed validation.
"""

from __future__ import annotations

from typing import Any

_DIAGRAMS = [
    {
        "$type": "bpmndi:BPMNDiagram",
        "id": "D1_di",
        "plane": {
            "$type": "bpmndi:BPMNPlane",
            "bpmnElement": "P1",
            "shapes": [{"$type": "bpmndi:BPMNShape", "bounds": {"$type": "dc:Bounds"}}],
        },
    }
]


def _tree(bounds: str = "one") -> dict[str, Any]:
    return {
        "$type": "bpmn:Definitions",
        "id": "D1",
        "$attrs": {"bounds": bounds, "xmlns:bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL"},
        "diagrams": [dict(_DIAGRAMS[0])],
        "rootElements": [
            {
                "$type": "bpmn:Process",
                "id": "P1",
                "x": "keep-me",
                "flowElements": [{"$type": "bpmn:Task", "id": "T1", "name": "T"}],
            }
        ],
    }


def _identity() -> dict[str, Any]:
    return {
        "mechanismVersion": "1",
        "schemaVersion": "1.0.0",
        "profile": "neutral/1",
        "version": "1.0.0",
        "sha256": "00" * 32,
        "base": {"id": "neutral-base/1", "version": "1.0.0", "sha256": "11" * 32},
        "descriptors": [{"id": "neutral-descriptors/1", "version": "1.0.0", "sha256": "22" * 32}],
    }


def test_attrs_bounds_survives_and_moves_revision() -> None:
    """A semantic ``bounds`` attribute in ``$attrs`` survives projection."""
    from bpmn_io.profile import complete_envelope, project_semantic

    first = project_semantic(_tree("one"))
    assert isinstance(first, dict)
    assert first["$attrs"]["bounds"] == "one"
    assert "diagrams" not in first
    assert first["rootElements"][0]["x"] == "keep-me"
    one = complete_envelope(_identity(), _tree("one"), [])
    two = complete_envelope(_identity(), _tree("two"), [])
    assert one.semantic_revision != two.semantic_revision


def test_committed_tree_is_di_free_with_same_revision() -> None:
    """Completing drops diagrams; revision equals the DI-free revision."""
    from bpmn_io.profile import complete_envelope, project_semantic

    envelope = complete_envelope(_identity(), _tree(), [])
    assert "diagrams" not in envelope.tree
    bare = {k: v for k, v in _tree().items() if k != "diagrams"}
    again = complete_envelope(_identity(), bare, [])
    assert envelope.semantic_revision == again.semantic_revision
    assert project_semantic(envelope.tree) == envelope.tree


def test_validate_rejects_empty_identity_and_tree() -> None:
    """Empty identity and empty tree fail closed validation."""
    from bpmn_io.profile import complete_envelope, validate_envelope

    envelope = complete_envelope(_identity(), _tree(), [])
    base = envelope.to_json()
    tree = base["tree"]
    identity = base["profileIdentity"]
    assert isinstance(tree, dict)
    assert isinstance(identity, dict)
    fresh_for_empty_identity = complete_envelope({}, tree, []).semantic_revision
    assert (
        validate_envelope(
            {**base, "profileIdentity": {}, "semanticRevision": fresh_for_empty_identity}
        )
        == "profile-schema"
    )
    fresh_for_empty_tree = complete_envelope(identity, {}, []).semantic_revision
    assert (
        validate_envelope({**base, "tree": {}, "semanticRevision": fresh_for_empty_tree})
        == "profile-schema"
    )


def test_validate_rejects_diagrams_bearing_tree() -> None:
    """A tree that is not its own projection is not committable."""
    from bpmn_io.profile import complete_envelope, validate_envelope

    committed = complete_envelope(_identity(), _tree(), [])
    candidate = {**committed.to_json(), "tree": _tree()}
    assert validate_envelope(candidate) == "profile-schema"


def test_bridge_stores_di_separately_from_tree() -> None:
    """Loading a diagrams-bearing envelope commits a DI-free tree plus DI."""
    from bpmn_io.profile import HeadlessBridge, complete_envelope
    from bpmn_io.profile._envelope import DocumentEnvelope

    committed = complete_envelope(_identity(), _tree(), [])
    raw = DocumentEnvelope(
        document_version="1",
        profile_identity=dict(_identity()),
        tree=_tree(),
        bindings=[],
        semantic_revision=committed.semantic_revision,
    )
    bridge = HeadlessBridge()
    loaded = bridge.set_definitions(raw)
    assert loaded.status == "ok", loaded
    stored = bridge.get_definitions()
    assert stored.status == "ok"
    payload = stored.payload  # type: ignore[union-attr]
    assert "diagrams" not in payload["tree"]
    assert payload["tree"]["$attrs"]["bounds"] == "one"
    snapshot = bridge.get_snapshot()
    assert snapshot.status == "ok"
    presentation = snapshot.payload["presentation"]  # type: ignore[union-attr]
    assert isinstance(presentation, dict)
    imported = presentation["importedDi"]
    assert imported["diagrams"] == _DIAGRAMS
    assert imported["descriptorDigest"] == ""


def test_imported_di_record_round_trips_digest() -> None:
    """The separate DI record carries its own integrity digest."""
    from bpmn_io.profile import make_imported_di

    record = make_imported_di(_tree(), descriptor_digest="abc")
    assert record["diagrams"] == _DIAGRAMS
    assert record["descriptorDigest"] == "abc"
    assert len(record["sha256"]) == 64
    again = make_imported_di(_tree(), descriptor_digest="abc")
    assert again == record
    other = make_imported_di(_tree(), descriptor_digest="abd")
    assert other != record
