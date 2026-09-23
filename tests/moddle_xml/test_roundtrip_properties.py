"""Roundtrip property tests (Lot 6): serialization is a fixed point.

The byte gate (``tests/oracle/test_moddle_xml_serialize.py``) pins writer
bytes against Node; these node-free properties pin serializer stability over
the fixture corpus: serializing twice yields identical bytes. Comparing
parsed models directly would be stricter than the domain — the writer
(rightly, as upstream) drops default-valued attributes, so only the
serialized form is a fixed point. ``bpmn-in-color.bpmn`` is excluded
(BR01-COLOR: 6th descriptor package, Lot 7).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from bpmn_io.moddle import Moddle
from bpmn_io.moddle_xml import Reader, Writer

if TYPE_CHECKING:
    from bpmn_io.moddle.base import ModdleElement

FIXTURES = (
    Path(__file__).resolve().parent.parent
    / "upstream"
    / "bpmn-moddle"
    / "test"
    / "fixtures"
    / "bpmn"
)
RESOURCES = Path(__file__).resolve().parent.parent.parent / "src" / "bpmn_io" / "resources"

SKIP = frozenset({"bpmn-in-color.bpmn"})

CORPUS = sorted(str(p) for p in FIXTURES.rglob("*.bpmn") if p.name not in SKIP)


def _model() -> Moddle:
    """Build the five-package model both sides of the oracle use."""
    packages = [
        json.loads((RESOURCES / "bpmn" / f"{name}.json").read_text(encoding="utf-8"))
        for name in ("bpmn", "bpmndi", "dc", "di")
    ]
    packages.append(json.loads((RESOURCES / "bpmn-io" / "bioc.json").read_text(encoding="utf-8")))
    return Moddle(packages)


def _parse(xml: str) -> ModdleElement:
    """Parse lax, mirroring the oracle corpus."""
    return Reader(_model(), lax=True).from_xml(xml, "bpmn:Definitions").root_element


def _serialize(
    element: ModdleElement,
    format: bool,  # noqa: A002, FBT001 - upstream option
) -> str:
    """Serialize with the oracle-corpus options."""
    return Writer(format=format, preamble=True).to_xml(element)


@settings(max_examples=25, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(path=st.sampled_from(CORPUS), format=st.booleans())
def test_serialize_fixed_point(
    path: str,
    format: bool,  # noqa: A002, FBT001 - upstream option
) -> None:
    xml = Path(path).read_text(encoding="utf-8", errors="replace")
    try:
        once = _serialize(_parse(xml), format)
    except Exception:  # noqa: BLE001 - unparsable fragments have no fixed point
        return
    assert _serialize(_parse(once), format) == once
