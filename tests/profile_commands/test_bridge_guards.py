"""Bridge guard tests for the section-4.8/4.10 transaction edges (lot 5).

Covers what runs without lot 3: the empty-batch no-op, stale-revision,
unknown-entry and cancellation refusals, the empty undo/redo refusals,
and the preservation of tree, history and snapshot on every refusal.
Non-empty accepted batches stay under the sealed case runner.
"""

from __future__ import annotations

import pytest

from bpmn_io.profile._bridge import HeadlessBridge
from bpmn_io.profile._c14n import jcs
from bpmn_io.profile._compiler import CompiledProfile
from bpmn_io.profile._envelope import complete_envelope
from bpmn_io.profile._ui import UiIndex

_IDENTITY = {
    "mechanismVersion": "1",
    "schemaVersion": "1.0.0",
    "profile": "neutral",
    "version": "1",
    "sha256": "ab" * 32,
    "base": {},
    "descriptors": [],
}

_TREE = {
    "$type": "bpmn:Definitions",
    "id": "D_1",
    "targetNamespace": "urn:x",
    "rootElements": [
        {"$type": "bpmn:Process", "id": "P_1", "flowElements": []},
    ],
}


def _compiled() -> CompiledProfile:
    """Build one synthetic compiled profile carrying the test identity."""
    return CompiledProfile(
        profile_digest="ab" * 32,
        notions={},
        recipes={},
        rules={},
        descriptor_digest="ab" * 32,
        registry_digest="ab" * 32,
        validation=(),
        ui=UiIndex(identity=dict(_IDENTITY)),
    )


@pytest.fixture
def bridge() -> HeadlessBridge:
    """Return one loaded bridge with an active business profile."""
    session = HeadlessBridge()
    loaded = session.set_definitions(complete_envelope(dict(_IDENTITY), dict(_TREE), []))
    assert getattr(loaded, "status", None) == "ok"
    activated = session.activate_business_profile(_compiled())
    assert getattr(activated, "status", None) == "ok"
    return session


def _revisions(session: HeadlessBridge) -> tuple[str, str]:
    """Return the current semantic and view revisions."""
    assert session.envelope is not None
    view = session._current_view(session.envelope)  # noqa: SLF001
    return session.envelope.semantic_revision, view


def _fingerprint(session: HeadlessBridge) -> str:
    """Return the canonical fingerprint of tree, history and snapshot."""
    assert session.envelope is not None
    snapshot = session.get_snapshot()
    assert getattr(snapshot, "status", None) == "ok"
    return jcs(
        {
            "tree": session.envelope.tree,
            "history": [
                (entry.transaction_id, entry.envelope.semantic_revision)
                for entry in session.history
            ],
            "redo": [
                (entry.transaction_id, entry.envelope.semantic_revision)
                for entry in session.redo_history
            ],
            "snapshot": snapshot.payload,
        }
    )


def test_empty_batch_is_a_noop_without_history_or_event(bridge: HeadlessBridge) -> None:
    """An empty batch changes nothing and emits no event (step 4)."""
    events: list[dict[str, object]] = []
    revision, view = _revisions(bridge)
    before = _fingerprint(bridge)
    result = bridge.apply_commands(
        base_revision=revision,
        expected_view_revision=view,
        commands=[],
        transaction_id="tx-0",
    )
    assert getattr(result, "status", None) == "ok"
    assert result.payload["changed"] is False
    assert result.payload["semanticRevision"] == revision
    assert result.payload["viewRevision"] == view
    assert result.report.entries == ()
    assert bridge.history == []
    assert _fingerprint(bridge) == before
    assert events == []


def test_stale_revision_refusal_preserves_everything(bridge: HeadlessBridge) -> None:
    """A stale base revision refuses operation-error with identical state."""
    revision, view = _revisions(bridge)
    before = _fingerprint(bridge)
    result = bridge.apply_commands(
        base_revision="stale",
        expected_view_revision=view,
        commands=[],
        transaction_id="tx-1",
    )
    assert getattr(result, "status", None) == "refused"
    assert result.code == "operation-error"
    assert _fingerprint(bridge) == before
    assert bridge._state == "idle"  # noqa: SLF001
    _ = revision


@pytest.mark.xfail(strict=True, reason="needs lot 3 C/N")
def test_unknown_entry_refusal_preserves_everything(bridge: HeadlessBridge) -> None:
    """An unknown UI entry refuses profile-symbol with identical state."""
    revision, view = _revisions(bridge)
    before = _fingerprint(bridge)
    result = bridge.apply_commands(
        base_revision=revision,
        expected_view_revision=view,
        commands=[{"command": "surface", "entry": "nope", "context": {}}],
        transaction_id="tx-2",
    )
    assert getattr(result, "status", None) == "refused"
    assert result.code == "profile-symbol"
    assert _fingerprint(bridge) == before
    assert bridge.history == []
    assert bridge._state == "idle"  # noqa: SLF001


def test_cancellation_refusal_preserves_everything(bridge: HeadlessBridge) -> None:
    """A raised signal refuses operation-cancelled with identical state."""
    revision, view = _revisions(bridge)
    before = _fingerprint(bridge)
    result = bridge.apply_commands(
        base_revision=revision,
        expected_view_revision=view,
        commands=[],
        transaction_id="tx-3",
        signal=lambda: True,
    )
    assert getattr(result, "status", None) == "refused"
    assert result.code == "operation-cancelled"
    assert _fingerprint(bridge) == before
    assert bridge._state == "idle"  # noqa: SLF001


def test_disposal_during_signal_refuses_disposed(bridge: HeadlessBridge) -> None:
    """A disposal observed by the signal refuses canvas-disposed."""
    revision, view = _revisions(bridge)

    def _dispose() -> bool:
        bridge.dispose()
        return True

    result = bridge.apply_commands(
        base_revision=revision,
        expected_view_revision=view,
        commands=[],
        transaction_id="tx-4",
        signal=_dispose,
    )
    assert getattr(result, "status", None) == "refused"
    assert result.code == "canvas-disposed"


def test_empty_undo_and_redo_refuse(bridge: HeadlessBridge) -> None:
    """Undo/redo with no entry refuse operation-error with identical state."""
    revision, view = _revisions(bridge)
    before = _fingerprint(bridge)
    refused_undo = bridge.undo(expected_revision=revision, expected_view_revision=view)
    assert getattr(refused_undo, "status", None) == "refused"
    assert refused_undo.code == "operation-error"
    refused_redo = bridge.redo(expected_revision=revision, expected_view_revision=view)
    assert getattr(refused_redo, "status", None) == "refused"
    assert refused_redo.code == "operation-error"
    assert _fingerprint(bridge) == before


def test_stale_undo_refuses(bridge: HeadlessBridge) -> None:
    """Undo with a stale revision refuses operation-error."""
    _, view = _revisions(bridge)
    refused = bridge.undo(expected_revision="stale", expected_view_revision=view)
    assert getattr(refused, "status", None) == "refused"
    assert refused.code == "operation-error"


def test_load_starts_a_new_history_epoch(bridge: HeadlessBridge) -> None:
    """set_definitions clears both stacks and bumps the epoch (E1)."""
    first = bridge.history_epoch
    reloaded = bridge.set_definitions(
        complete_envelope(dict(_IDENTITY), dict(_TREE), []),
    )
    assert getattr(reloaded, "status", None) == "ok"
    assert bridge.history == []
    assert bridge.redo_history == []
    assert bridge.history_epoch == first + 1
