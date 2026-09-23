"""Ported moddle meta cases (Lot 4).

Transcribes every ``moddle/test/spec/meta.js`` ``it()`` title: one test per
unique ledger title (3 claims). Only the public ``bpmn_io.moddle`` API is used.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from bpmn_io.moddle import Moddle

FIXTURES = (
    Path(__file__).resolve().parent.parent / "upstream" / "moddle" / "test" / "fixtures" / "model"
)


def _load(*names: str) -> list[dict[str, Any]]:
    """Load model fixture packages by name."""
    return [json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8")) for name in names]


@pytest.mark.upstream("moddle/test/spec/meta.js", 'should have the "meta" attribute')
def test_001_have_meta_attribute() -> None:
    model = Moddle(_load("meta"))

    meta = model.get_type_descriptor("c:Car")["meta"]

    assert meta is not None
    assert isinstance(meta, dict)


@pytest.mark.upstream("moddle/test/spec/meta.js", 'should have a "owners" property inside "meta"')
def test_002_have_owners_inside_meta() -> None:
    model = Moddle(_load("meta"))

    meta = model.get_type_descriptor("c:Car")["meta"]

    assert meta["owners"] is not None
    assert meta["owners"] == ["the pope", "donald trump"]


@pytest.mark.upstream("moddle/test/spec/meta.js", 'should copy "meta" from type definition')
def test_003_copy_meta_from_type_definition() -> None:
    type_meta = {"owners": ["the pope"]}
    pkg: dict[str, Any] = {
        "name": "Cars",
        "uri": "http://cars",
        "prefix": "c",
        "types": [{"name": "Car", "meta": type_meta}],
    }

    registered_model = Moddle([pkg])

    meta = registered_model.get_type_descriptor("c:Car")["meta"]

    assert meta == type_meta
    assert meta is not type_meta
