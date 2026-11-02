"""Focused headless query tests on the grid profile (no lot-3 dependency).

The grid profile compiles without the lot-3 block-A fixes, so listings,
field records, on-change validation, copy fragments and localization verify
here directly. Neutral-profile query behaviour is covered by the sealed
case runner.
"""

from __future__ import annotations

from tests.profile_commands import harness


def _grid_setup() -> harness.Setup:
    case = harness.read_case("surface-palette-entries-grid")
    setup = harness.make_setup(case)
    assert setup.compiled is not None, getattr(setup, "compile_refusal", None)
    assert setup.bridge is not None
    return setup


def test_palette_listing_order() -> None:
    """Palette entries group by first appearance, ordered numerically."""
    setup = _grid_setup()
    assert setup.bridge is not None
    result = setup.bridge.list_entries(
        base_revision=setup.base_revision,
        surface="palette",
        subject="Process_1",
        locale="en",
    )
    actual = result.to_json()
    assert actual["status"] == "ok", actual
    assert [group["group"] for group in actual["payload"]["groups"]] == ["basic"]
    assert [entry["id"] for entry in actual["payload"]["groups"][0]["entries"]] == [
        "task-create",
        "aid-create",
    ]
    assert actual["payload"]["groups"][0]["entries"][0]["label"] == {
        "key": "label",
        "text": "Task",
    }


def test_unknown_surface_refuses() -> None:
    """A surface outside the eight schema surfaces refuses."""
    setup = _grid_setup()
    assert setup.bridge is not None
    result = setup.bridge.list_entries(
        base_revision=setup.base_revision,
        surface="toolbar",
        subject="Process_1",
        locale="en",
    )
    assert result.to_json()["status"] == "refused"
    assert result.to_json()["code"] == "profile-type"  # type: ignore[union-attr]


def test_dangling_subject_refuses() -> None:
    """A listing for a missing subject refuses."""
    setup = _grid_setup()
    assert setup.bridge is not None
    result = setup.bridge.list_entries(
        base_revision=setup.base_revision,
        surface="palette",
        subject="Ghost_9",
        locale="en",
    )
    assert result.to_json()["code"] == "reference-dangling"  # type: ignore[union-attr]


def test_field_record_for_task() -> None:
    """The task name field carries its stored value and label."""
    setup = _grid_setup()
    assert setup.bridge is not None
    result = setup.bridge.list_fields(
        base_revision=setup.base_revision, target_id="Task_1", locale="en"
    )
    actual = result.to_json()
    assert actual["status"] == "ok", actual
    assert actual["payload"]["fields"] == [
        {
            "notion": "task",
            "field": "name",
            "widget": "text",
            "path": "/name",
            "label": {"key": "label", "text": "Task"},
            "message": {"key": "invalid", "text": "Name is required."},
            "present": True,
            "display": "Review",
            "value": "Review",
            "mutable": True,
            "choices": [],
            "targetTypes": [],
        }
    ]


def test_check_field_accepts_and_rejects_text() -> None:
    """On-change validation mirrors the commit typing for text."""
    setup = _grid_setup()
    assert setup.bridge is not None
    good = setup.bridge.check_field(
        base_revision=setup.base_revision,
        target_id="Task_1",
        field_id="name",
        value="Renamed",
    )
    assert good.to_json()["payload"] == {"revision": setup.base_revision, "valid": True}
    bad = setup.bridge.check_field(
        base_revision=setup.base_revision,
        target_id="Task_1",
        field_id="name",
        value=7,
    )
    assert bad.to_json()["payload"] == {
        "revision": setup.base_revision,
        "valid": False,
        "code": "profile-type",
        "messageKey": "invalid",
    }


def test_check_field_unknown_refuses() -> None:
    """Unknown fields and dangling targets refuse on change."""
    setup = _grid_setup()
    assert setup.bridge is not None
    unknown = setup.bridge.check_field(
        base_revision=setup.base_revision,
        target_id="Task_1",
        field_id="nope",
        value="x",
    )
    assert unknown.to_json()["code"] == "profile-symbol"  # type: ignore[union-attr]
    dangling = setup.bridge.check_field(
        base_revision=setup.base_revision,
        target_id="Ghost_9",
        field_id="name",
        value="x",
    )
    assert dangling.to_json()["code"] == "reference-dangling"  # type: ignore[union-attr]


def test_copy_fragment_shape() -> None:
    """Copy returns the canonical fragment with the stage revision."""
    setup = _grid_setup()
    assert setup.bridge is not None
    result = setup.bridge.copy(base_revision=setup.base_revision, element_ids=["Task_1"])
    actual = result.to_json()
    assert actual["status"] == "ok", actual
    assert actual["payload"]["fragmentVersion"] == "1"
    assert actual["payload"]["sourceRevision"] == setup.base_revision
    assert [entry["property"] for entry in actual["payload"]["elements"]] == ["flowElements"]
    assert actual["payload"]["elements"][0]["element"]["id"] == "Task_1"


def test_localize_sources() -> None:
    """Localization reports exact, fallback and key sources."""
    setup = _grid_setup()
    assert setup.bridge is not None
    from bpmn_io.profile import localize as localize_fn

    assert setup.compiled is not None
    assert localize_fn(setup.compiled, "label.aid", "en").to_json() == {
        "status": "ok",
        "payload": {"key": "label.aid", "text": "Aid", "source": "exact"},
        "diagnostics": [],
    }
    assert localize_fn(setup.compiled, "label.aid", "fr").to_json()["payload"] == {
        "key": "label.aid",
        "text": "Aid",
        "source": "fallback",
    }
    assert localize_fn(setup.compiled, "label.missing", "en").to_json()["payload"] == {
        "key": "label.missing",
        "text": "label.missing",
        "source": "key",
    }
