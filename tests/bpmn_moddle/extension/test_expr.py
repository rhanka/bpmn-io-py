"""Ported bpmn-moddle expr extension cases (Lot 7).

Transcribes every ``bpmn-moddle/test/spec/extension/expr.js`` ``it()`` title:
one test per claim (2 claims: reading and writing ``expr:Guard`` as a
sub-class of ``bpmn:FormalExpression``). Only the public ``bpmn_io`` API plus
the ``tests._matchers`` helper is used.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from bpmn_io import create_moddle
from tests._matchers import json_equal

if TYPE_CHECKING:
    from bpmn_io.bpmn_moddle import BpmnModdle

FIXTURES = Path(__file__).resolve().parent.parent.parent / "upstream" / "bpmn-moddle" / "test"


def _moddle() -> BpmnModdle:
    """Create the model with the ``expr`` extension package, as upstream."""
    descriptor: dict[str, Any] = json.loads(
        (FIXTURES / "fixtures" / "json" / "model" / "expr.json").read_text(encoding="utf-8")
    )
    return create_moddle({"expr": descriptor})


@pytest.mark.upstream(
    "bpmn-moddle/test/spec/extension/expr.js",
    "should read expr:Guard (sub-class of bpmn:FormalExpression)",
)
def test_001_read_expr_guard() -> None:
    moddle = _moddle()
    xml = (FIXTURES / "spec" / "extension" / "expr-Guard.part.bpmn").read_text(encoding="utf-8")

    result = moddle.from_xml(xml, "bpmn:SequenceFlow")

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmn:SequenceFlow",
            "id": "SequenceFlow_1",
            "conditionExpression": {
                "$type": "expr:Guard",
                "body": "${ foo < bar }",
            },
        },
    )


@pytest.mark.upstream(
    "bpmn-moddle/test/spec/extension/expr.js",
    "should write expr:Guard (sub-class of bpmn:FormalExpression)",
)
def test_002_write_expr_guard() -> None:
    moddle = _moddle()
    sequence_flow = moddle.create("bpmn:SequenceFlow", {"id": "SequenceFlow_1"})
    sequence_flow.set(
        "conditionExpression",
        moddle.create("expr:Guard", {"body": "${ foo < bar }"}),
    )

    expected_xml = (
        '<bpmn:sequenceFlow xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:expr="http://expr" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'id="SequenceFlow_1">\n'
        '  <bpmn:conditionExpression xsi:type="expr:Guard">'
        "${ foo &lt; bar }</bpmn:conditionExpression>\n"
        "</bpmn:sequenceFlow>\n"
    )

    xml = moddle.to_xml(sequence_flow, {"preamble": False, "format": True}).xml

    assert xml == expected_xml
