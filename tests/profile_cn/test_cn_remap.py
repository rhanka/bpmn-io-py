"""Remap step-1 validation branches without sealed cases (lot 3, §5.5)."""

from __future__ import annotations

import pytest

from bpmn_io.profile._cn_plan import _RefusalError
from bpmn_io.profile._cn_remap import _check_command, _check_imported_di


def _command(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "kind": "id-remap",
        "approved": True,
        "approval": "technical",
        "map": [{"sourceId": "A", "resultId": "B", "domain": "migration"}],
        "referenceFreeAttestations": [],
    }
    record.update(overrides)
    return record


def test_duplicate_source_id_is_not_closed() -> None:
    """Two rows for one sourceId refuse operation-error."""
    command = _command(
        map=[
            {"sourceId": "A", "resultId": "B", "domain": "migration"},
            {"sourceId": "A", "resultId": "C", "domain": "migration"},
        ]
    )
    with pytest.raises(_RefusalError) as caught:
        _check_command(command)
    assert caught.value.code == "operation-error"


def test_unapproved_command_is_not_closed() -> None:
    """An unapproved command refuses operation-error."""
    with pytest.raises(_RefusalError) as caught:
        _check_command(_command(approved=False))
    assert caught.value.code == "operation-error"


def test_open_map_row_is_not_closed() -> None:
    """A map row with an extra member refuses operation-error."""
    command = _command(map=[{"sourceId": "A", "resultId": "B", "domain": "migration", "extra": 1}])
    with pytest.raises(_RefusalError) as caught:
        _check_command(command)
    assert caught.value.code == "operation-error"


def test_imported_di_hash_mismatch() -> None:
    """A Snapshot/1 record with a wrong sha256 refuses snapshot-schema."""
    record = {
        "descriptorDigest": "d",
        "diagrams": [],
        "sha256": "0" * 64,
    }
    with pytest.raises(_RefusalError) as caught:
        _check_imported_di(record)
    assert caught.value.code == "snapshot-schema"


def test_imported_di_open_shape() -> None:
    """A Snapshot/1 record with an extra member refuses snapshot-schema."""
    record = {
        "descriptorDigest": "d",
        "diagrams": [],
        "sha256": "0" * 64,
        "extra": 1,
    }
    with pytest.raises(_RefusalError) as caught:
        _check_imported_di(record)
    assert caught.value.code == "snapshot-schema"
