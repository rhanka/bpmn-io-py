"""Import projection branches without sealed cases (lot 3, §6.8)."""

from __future__ import annotations

import json
from pathlib import Path

from bpmn_io.profile import import_projection
from bpmn_io.profile._cn_import import _parse_source
from tests.profile_cn.test_cn_cases import _compiled as _compile_case

EXPECTED = Path(__file__).resolve().parents[2] / "tests" / "profile_cn" / "expected"


def _compiled() -> object:
    case = json.loads((EXPECTED / "l3-imp-projection-out-of-base.json").read_text(encoding="utf-8"))
    return _compile_case(case["profile"])


def test_bad_source_format() -> None:
    """An unclosed source_format refuses operation-error."""
    outcome = import_projection(_compiled(), b"{}", source_format="xml-ok")  # type: ignore[arg-type]
    assert outcome.status == "refused"
    assert outcome.code == "operation-error"  # type: ignore[union-attr]


def test_unparseable_source() -> None:
    """Unparseable bytes refuse document-not-loaded."""
    outcome = import_projection(_compiled(), b"{nope", source_format="native-json")  # type: ignore[arg-type]
    assert outcome.status == "refused"
    assert outcome.code == "document-not-loaded"  # type: ignore[union-attr]


def test_wrong_source_type() -> None:
    """A source that is neither bytes nor a mapping refuses operation-error."""
    outcome = import_projection(_compiled(), "{}", source_format="native-json")  # type: ignore[arg-type]
    assert outcome.status == "refused"
    assert outcome.code == "operation-error"  # type: ignore[union-attr]


def test_non_object_document() -> None:
    """A JSON array source refuses document-not-loaded."""
    outcome = import_projection(_compiled(), b"[1]", source_format="native-json")  # type: ignore[arg-type]
    assert outcome.status == "refused"
    assert outcome.code == "document-not-loaded"  # type: ignore[union-attr]


def test_duplicate_ids() -> None:
    """Repeated element ids refuse id-collision."""
    tree = {
        "$type": "bpmn:Definitions",
        "id": "D",
        "rootElements": [
            {"$type": "bpmn:Process", "id": "P"},
            {"$type": "bpmn:Process", "id": "P"},
        ],
    }
    outcome = import_projection(_compiled(), json.dumps(tree).encode(), source_format="native-json")  # type: ignore[arg-type]
    assert outcome.status == "refused"
    assert outcome.code == "id-collision"  # type: ignore[union-attr]


def test_parse_source_mapping_identity() -> None:
    """A mapping source parses to an equal, detached tree."""
    tree = {"$type": "bpmn:Definitions", "id": "D"}
    parsed = _parse_source(tree, "native-json")
    assert parsed == tree
    assert parsed is not tree
