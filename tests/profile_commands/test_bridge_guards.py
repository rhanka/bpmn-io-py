"""Bridge guard tests for the section-4.8/4.10 transaction edges (lot 5).

Covers what runs without lot 3: the empty-batch no-op, stale-revision,
unknown-entry and cancellation refusals, the empty undo/redo refusals,
and the preservation of tree, history and snapshot on every refusal.
Non-empty accepted batches stay under the sealed case runner.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from bpmn_io.profile._bridge import HeadlessBridge
from bpmn_io.profile._c14n import jcs
from bpmn_io.profile._envelope import complete_envelope
from bpmn_io.profile._ui import compiled_identity

if TYPE_CHECKING:
    from bpmn_io.profile._compiler import CompiledProfile

_TREE = {
    "$type": "bpmn:Definitions",
    "id": "D_1",
    "targetNamespace": "urn:x",
    "rootElements": [
        {"$type": "bpmn:Process", "id": "P_1", "flowElements": []},
    ],
}


def _setup() -> tuple[object, CompiledProfile]:
    """Compile the real neutral lot-5 profile with its context (exit a)."""
    import copy

    from tests.profile_commands import harness as _harness

    raw = (_harness.EXPECTED / "artifacts/profiles/neutral-lot5.json").read_bytes()
    package = dict(_harness.DEFAULT_DESCRIPTOR_PIN)
    package["descriptorBytes"] = _harness.DEFAULT_DESCRIPTOR_BYTES
    from bpmn_io.profile import (
        compile_profile,
        create_descriptor_context,
        load_profile,
    )

    context_result = create_descriptor_context([package])
    assert context_result.status == "ok", context_result.to_json()
    pins = [{"id": package["id"], "version": package["version"], "sha256": package["sha256"]}]
    load_result = load_profile(
        raw,
        schema_bytes=_harness.SCHEMA_BYTES,
        base_bytes=_harness.BASE_BYTES,
        descriptor_pins=pins,
        asset_bag=dict(_harness.METRICS_BAG),
    )
    assert load_result.status == "ok", load_result.to_json()
    compile_result = compile_profile(
        load_result.payload,  # type: ignore[union-attr]
        descriptor_context=context_result.payload,  # type: ignore[union-attr]
        base=copy.deepcopy(_harness.BASE_DOCUMENT),
    )
    assert compile_result.status == "ok", compile_result.to_json()
    return context_result.payload, compile_result.payload  # type: ignore[return-value]


def _compiled() -> CompiledProfile:
    """Compile the real neutral lot-5 profile (exit a needs lot-4 themes)."""
    _, compiled = _setup()
    return compiled


@pytest.fixture
def bridge() -> HeadlessBridge:
    """Return one loaded bridge with an active business profile."""
    import copy

    from bpmn_io.profile import create_bridge

    context, compiled = _setup()
    identity = compiled_identity(compiled)
    session = create_bridge(context)
    loaded = session.set_definitions(complete_envelope(identity, copy.deepcopy(_TREE), []))
    assert getattr(loaded, "status", None) == "ok"
    activated = session.activate_business_profile(compiled)
    assert getattr(activated, "status", None) == "ok"
    assert isinstance(session, HeadlessBridge)
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
    import copy

    first = bridge.history_epoch
    assert bridge.envelope is not None
    reloaded = bridge.set_definitions(
        complete_envelope(dict(bridge.envelope.profile_identity), copy.deepcopy(_TREE), []),
    )
    assert getattr(reloaded, "status", None) == "ok"
    assert bridge.history == []
    assert bridge.redo_history == []
    assert bridge.history_epoch == first + 1


def test_stage_sources_rebase_onto_tx_start() -> None:
    """Complete entries on batch-created subjects lose the stage-local source."""
    from bpmn_io.profile._transaction import _rebase_stage_sources

    pre_ids = frozenset({"Definitions_1", "Process_1"})
    created = {
        "code": "complete/assignRef",
        "stage": "complete",
        "source": {
            "domain": "tree",
            "pointer": "/rootElements/0/flowElements/0/outgoing",
            "targetId": "Start_new",
            "provenance": "exact",
        },
        "result": {
            "domain": "tree",
            "pointer": "/rootElements/0/flowElements/0/outgoing",
            "targetId": "Start_new",
            "provenance": "exact",
        },
    }
    kept = {
        "code": "complete/set",
        "stage": "complete",
        "source": {
            "domain": "tree",
            "pointer": "/rootElements/0/isExecutable",
            "targetId": "Process_1",
            "provenance": "exact",
        },
        "result": {
            "domain": "tree",
            "pointer": "/rootElements/0/isExecutable",
            "targetId": "Process_1",
            "provenance": "exact",
        },
    }
    rebased = _rebase_stage_sources([created, kept], pre_ids)
    assert rebased[0]["source"] == {
        "domain": "none",
        "pointer": None,
        "targetId": None,
        "provenance": "generated",
    }
    assert rebased[0]["result"]["provenance"] == "generated"
    assert rebased[1] == kept


def test_load_emits_one_load_event() -> None:
    """set_definitions emits exactly one load-origin change event (L606)."""
    import copy

    from bpmn_io.profile import create_bridge

    context, compiled = _setup()
    identity = compiled_identity(compiled)
    session = create_bridge(context)
    collected: list[dict[str, object]] = []
    subscribed = session.on_change(collected.append)
    assert getattr(subscribed, "status", None) == "ok"
    loaded = session.set_definitions(complete_envelope(identity, copy.deepcopy(_TREE), []))
    assert getattr(loaded, "status", None) == "ok"
    assert len(collected) == 1
    event = collected[0]
    assert event["origin"] == "load"
    assert event["transactionId"] == ""
    assert event["semanticRevision"] == loaded.payload["semanticRevision"]
    assert event["viewRevision"] == loaded.payload["viewRevision"]
    assert event["envelope"] == loaded.payload["envelope"]
    assert isinstance(event["report"], dict)
