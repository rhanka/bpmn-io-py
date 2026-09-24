"""Ported bpmn-moddle model cases (Lot 7).

Transcribes every ``bpmn-moddle/test/spec/bpmn-moddle.js`` ``it()`` title:
one test per claim (17 claims). Verification mirrors the upstream
assertions: ``exist`` becomes ``is not None``, ``eql`` becomes ``==``,
``jsonEqual`` becomes ``json_equal`` and ``$instanceOf`` becomes
``instance_of``. Only the public ``bpmn_io`` API (``create_moddle``) is used.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from bpmn_io import create_moddle
from bpmn_io._js import UNDEFINED
from tests._matchers import json_equal

if TYPE_CHECKING:
    from bpmn_io.bpmn_moddle import BpmnModdle


def _moddle() -> BpmnModdle:
    """Create the default six-package BPMN model, as the upstream helper."""
    return create_moddle()


# parsing


@pytest.mark.upstream("bpmn-moddle/test/spec/bpmn-moddle.js", "should publish type")
def test_001_publish_type() -> None:
    moddle = _moddle()

    element_type = moddle.get_type("bpmn:Process")

    assert element_type is not None
    assert moddle.get_element_descriptor(element_type) is not None


@pytest.mark.upstream("bpmn-moddle/test/spec/bpmn-moddle.js", "should redefine property")
def test_002_redefine_property() -> None:
    moddle = _moddle()

    element_type = moddle.get_type("bpmndi:BPMNShape")

    assert element_type is not None

    descriptor = moddle.get_element_descriptor(element_type)

    assert descriptor is not None
    assert (
        descriptor.properties_by_name["di:modelElement"]
        is descriptor.properties_by_name["bpmndi:bpmnElement"]
    )


# creation


@pytest.mark.upstream("bpmn-moddle/test/spec/bpmn-moddle.js", "should create SequenceFlow")
def test_003_create_sequence_flow() -> None:
    moddle = _moddle()

    sequence_flow = moddle.create("bpmn:SequenceFlow")

    assert sequence_flow.type_ == "bpmn:SequenceFlow"


@pytest.mark.upstream("bpmn-moddle/test/spec/bpmn-moddle.js", "should create Definitions")
def test_004_create_definitions() -> None:
    moddle = _moddle()

    definitions = moddle.create("bpmn:Definitions")

    assert definitions.type_ == "bpmn:Definitions"


@pytest.mark.upstream("bpmn-moddle/test/spec/bpmn-moddle.js", "should create Process")
def test_005_create_process() -> None:
    moddle = _moddle()

    process = moddle.create("bpmn:Process")

    assert process.type_ == "bpmn:Process"
    assert process.instance_of("bpmn:FlowElementsContainer") is True


@pytest.mark.upstream("bpmn-moddle/test/spec/bpmn-moddle.js", "should create SubProcess")
def test_006_create_sub_process() -> None:
    moddle = _moddle()

    task = moddle.create("bpmn:Task")
    sub_process = moddle.create("bpmn:SubProcess", {"flowElements": [task]})

    assert sub_process.type_ == "bpmn:SubProcess"
    assert sub_process.instance_of("bpmn:InteractionNode") is True
    assert sub_process.get("flowElements") == [task]


@pytest.mark.upstream("bpmn-moddle/test/spec/bpmn-moddle.js", "should create CallActivity")
def test_007_create_call_activity() -> None:
    moddle = _moddle()

    call_activity = moddle.create("bpmn:CallActivity")

    assert call_activity.type_ == "bpmn:CallActivity"
    assert call_activity.instance_of("bpmn:InteractionNode") is True


# creation > defaults


@pytest.mark.upstream("bpmn-moddle/test/spec/bpmn-moddle.js", "should init Gateway")
def test_008_init_gateway() -> None:
    moddle = _moddle()

    gateway = moddle.create("bpmn:Gateway")

    assert gateway.get("gatewayDirection") == "Unspecified"


@pytest.mark.upstream("bpmn-moddle/test/spec/bpmn-moddle.js", "should init BPMNShape")
def test_009_init_bpmn_shape() -> None:
    moddle = _moddle()

    bpmn_edge = moddle.create("bpmndi:BPMNEdge")

    assert bpmn_edge.get("messageVisibleKind") == "initiating"


@pytest.mark.upstream("bpmn-moddle/test/spec/bpmn-moddle.js", "should init EventBasedGateway")
def test_010_init_event_based_gateway() -> None:
    moddle = _moddle()

    gateway = moddle.create("bpmn:EventBasedGateway")

    assert gateway.get("eventGatewayType") == "Exclusive"


@pytest.mark.upstream("bpmn-moddle/test/spec/bpmn-moddle.js", "should init CatchEvent")
def test_011_init_catch_event() -> None:
    moddle = _moddle()

    event = moddle.create("bpmn:CatchEvent")

    assert event.get("parallelMultiple") is False


@pytest.mark.upstream("bpmn-moddle/test/spec/bpmn-moddle.js", "should init ParticipantMultiplicity")
def test_012_init_participant_multiplicity() -> None:
    moddle = _moddle()

    multiplicity = moddle.create("bpmn:ParticipantMultiplicity")

    assert multiplicity.get("minimum") == 0
    assert multiplicity.get("maximum") == 1


@pytest.mark.upstream("bpmn-moddle/test/spec/bpmn-moddle.js", "should init Activity")
def test_013_init_activity() -> None:
    moddle = _moddle()

    activity = moddle.create("bpmn:Activity")

    assert activity.get("startQuantity") == 1
    assert activity.get("completionQuantity") == 1


# property access > singleton properties


@pytest.mark.upstream("bpmn-moddle/test/spec/bpmn-moddle.js", "should set attribute")
def test_014_set_attribute() -> None:
    moddle = _moddle()

    process = moddle.create("bpmn:Process")

    assert process.get("isExecutable") is UNDEFINED

    process.set("isExecutable", True)  # noqa: FBT003

    assert json_equal(process, {"$type": "bpmn:Process", "isExecutable": True})


@pytest.mark.upstream("bpmn-moddle/test/spec/bpmn-moddle.js", "should set attribute (ns)")
def test_015_set_attribute_ns() -> None:
    moddle = _moddle()

    process = moddle.create("bpmn:Process")

    process.set("bpmn:isExecutable", True)  # noqa: FBT003

    assert json_equal(process, {"$type": "bpmn:Process", "isExecutable": True})


@pytest.mark.upstream("bpmn-moddle/test/spec/bpmn-moddle.js", "should set id attribute")
def test_016_set_id_attribute() -> None:
    moddle = _moddle()

    definitions = moddle.create("bpmn:Definitions")

    definitions.set("id", 10)

    assert json_equal(definitions, {"$type": "bpmn:Definitions", "id": 10})


# property access > builder


@pytest.mark.upstream("bpmn-moddle/test/spec/bpmn-moddle.js", "should create simple hierarchy")
def test_017_create_simple_hierarchy() -> None:
    moddle = _moddle()

    definitions = moddle.create("bpmn:Definitions")
    root_elements = definitions.get("bpmn:rootElements")

    assert isinstance(root_elements, list)

    process = moddle.create("bpmn:Process")
    collaboration = moddle.create("bpmn:Collaboration")

    root_elements.append(collaboration)
    root_elements.append(process)

    assert root_elements == [collaboration, process]
    assert definitions.get("rootElements") == [collaboration, process]

    assert json_equal(
        definitions,
        {
            "$type": "bpmn:Definitions",
            "rootElements": [
                {"$type": "bpmn:Collaboration"},
                {"$type": "bpmn:Process"},
            ],
        },
    )
