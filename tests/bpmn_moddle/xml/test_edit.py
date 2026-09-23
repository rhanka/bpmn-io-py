"""Ported bpmn-moddle edit cases (Lot 7).

Transcribes every ``bpmn-moddle/test/spec/xml/edit.js`` ``it()`` title: one
test per claim (4 claims). The two ``generate DI`` cases validate their
output with ``validate(xml)`` through ``lxml`` against the OMG XSDs vendored
with the fixtures (see ``docs/xsd-divergences.md``). Only the public
``bpmn_io`` API is used.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from lxml import etree

from bpmn_io import create_moddle

if TYPE_CHECKING:
    from bpmn_io.bpmn_moddle import BpmnModdle
    from bpmn_io.moddle.base import AnyModdleElement, ModdleElement

FIXTURES = (
    Path(__file__).resolve().parent.parent.parent
    / "upstream"
    / "bpmn-moddle"
    / "test"
    / "fixtures"
    / "bpmn"
)
XSD_FIXTURES = (
    Path(__file__).resolve().parent.parent.parent
    / "upstream"
    / "bpmn-moddle"
    / "test"
    / "fixtures"
    / "xsd"
)
OMG_XSD = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "tests"
    / "oracle"
    / "node_modules"
    / "bpmn-moddle"
    / "resources"
    / "bpmn"
    / "xsd"
)


@cache
def _schema() -> etree.XMLSchema:
    """Compile the vendored ``BPMN20.xsd`` with absolute OMG ``schemaLocation``."""
    text = (XSD_FIXTURES / "BPMN20.xsd").read_text(encoding="utf-8")
    fixed = text.replace(
        "../../../resources/bpmn/xsd/BPMNDI.xsd",
        (OMG_XSD / "BPMNDI.xsd").resolve().as_uri(),
    )
    fixed = fixed.replace(
        "../../../resources/bpmn/xsd/Semantic.xsd",
        (OMG_XSD / "Semantic.xsd").resolve().as_uri(),
    )
    fixed = fixed.replace("Vendor.xsd", (XSD_FIXTURES / "Vendor.xsd").resolve().as_uri())
    return etree.XMLSchema(etree.fromstring(fixed.encode("utf-8")))


def _validate(xml: str) -> None:
    """Assert ``xml`` validates against ``BPMN20.xsd`` (the ``validate`` port)."""
    assert xml, "XML is not defined"
    document = etree.fromstring(xml.encode("utf-8"))
    schema = _schema()
    assert schema.validate(document), str(schema.error_log)


def _moddle() -> BpmnModdle:
    """Create the default six-package BPMN model, as the upstream helper."""
    return create_moddle()


def _from_fixture(name: str) -> ModdleElement | AnyModdleElement:
    """Parse a vendored BPMN fixture, as the upstream ``fromFile`` helper."""
    xml = (FIXTURES / name).read_text(encoding="utf-8")
    return _moddle().from_xml(xml).root_element


def _read_and_generate_di(name: str) -> ModdleElement | AnyModdleElement:
    """Parse ``name`` and attach generated DI, as the upstream helper does."""
    definitions = _from_fixture(name)
    root_elements = definitions.get("rootElements")
    assert isinstance(root_elements, list)
    process = root_elements[0]
    flow_elements = process.get("flowElements")
    assert isinstance(flow_elements, list)
    start, task, flow = flow_elements[0], flow_elements[1], flow_elements[2]

    diagrams = definitions.get("diagrams")
    assert isinstance(diagrams, list)
    plane = diagrams[0].get("plane")

    model = definitions.model_
    plane_elements = plane.get("planeElement")
    assert isinstance(plane_elements, list)
    plane_elements.append(
        model.create(
            "bpmndi:BPMNEdge",
            {
                "id": "Flow_di",
                "bpmnElement": flow,
                "waypoint": [
                    model.create("dc:Point", {"x": 100, "y": 100}),
                    model.create("dc:Point", {"x": 150, "y": 150}),
                ],
            },
        )
    )
    plane_elements.append(
        model.create(
            "bpmndi:BPMNShape",
            {
                "id": "Start_di",
                "bpmnElement": start,
                "bounds": model.create(
                    "dc:Bounds", {"x": 50, "y": 50, "width": 100, "height": 100}
                ),
            },
        )
    )
    plane_elements.append(
        model.create(
            "bpmndi:BPMNShape",
            {
                "id": "Task_di",
                "bpmnElement": task,
                "bounds": model.create(
                    "dc:Bounds", {"x": 100, "y": 100, "width": 100, "height": 100}
                ),
            },
        )
    )
    return definitions


# save after change


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/edit.js", "should serialize changed name")
def test_001_serialize_changed_name() -> None:
    definitions = _from_fixture("simple.bpmn")

    root_elements = definitions.get("rootElements")
    assert isinstance(root_elements, list)
    root_elements[0].set("name", "OTHER PROCESS")

    xml = _moddle().to_xml(definitions, {"format": True}).xml

    assert 'name="OTHER PROCESS"' in xml


# dataObjectRef


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/edit.js", "should update")
def test_002_data_object_ref_update() -> None:
    definitions = _from_fixture("data-object-reference.bpmn")

    root_elements = definitions.get("rootElements")
    assert isinstance(root_elements, list)
    process = root_elements[0]
    flow_elements = process.get("flowElements")
    assert isinstance(flow_elements, list)
    data_object_reference = flow_elements[0]

    moddle = _moddle()
    data_object_2 = moddle.create("bpmn:DataObject", {"id": "dataObject_2"})
    flow_elements.append(data_object_2)
    data_object_reference.set("dataObjectRef", data_object_2)

    xml = moddle.to_xml(definitions, {"format": True}).xml

    assert '<bpmn:dataObject id="dataObject_2" />' in xml
    assert (
        '<bpmn:dataObjectReference id="DataObjectReference_1" '
        'dataObjectRef="dataObject_2" />' in xml
    )


# generate DI


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/edit.js", "should auto-add wellknown")
def test_003_auto_add_wellknown() -> None:
    definitions = _read_and_generate_di("local-ns-no-di.bpmn")

    xml = _moddle().to_xml(definitions, {"format": True}).xml

    assert 'xmlns:di="http://www.omg.org/spec/DD/20100524/DI"' in xml
    assert 'xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"' in xml

    _validate(xml)


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/edit.js", "should reuse global namespace")
def test_004_reuse_global_namespace() -> None:
    definitions = _read_and_generate_di("local-ns-no-di.bpmn")

    definitions.attrs_["xmlns:di"] = "http://www.omg.org/spec/DD/20100524/DI"
    definitions.attrs_["xmlns:dc"] = "http://www.omg.org/spec/DD/20100524/DC"

    xml = _moddle().to_xml(definitions, {"format": True}).xml

    assert 'xmlns:di="http://www.omg.org/spec/DD/20100524/DI"' in xml
    assert 'xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"' in xml

    _validate(xml)
