"""Ported tester tests (upstream ``test/spec/testers/*-spec.mjs``)."""

from __future__ import annotations  # noqa: I001

import json
import pytest

from bpmn_io._bpmnlint_utils import is_
from bpmn_io.bpmn_moddle import BpmnModdle
from bpmn_io.lint.testers.helper import create_moddle, read_moddle
from bpmn_io.lint.testers.rule_tester import expect_equal, get_title, replacer, verify
from tests.conftest import upstream_dir

TESTERS_DIR = upstream_dir("bpmnlint") / "test" / "spec" / "testers"

_TEST_MODDLE: dict[str, object] = {
    "name": "TestModdle",
    "uri": "http://test/schema",
    "prefix": "t",
    "xml": {"tagAlias": "lowerCase"},
    "types": [
        {
            "name": "TestDefinitions",
            "extends": ["bpmn:Definitions"],
            "properties": [],
        },
    ],
}

_XML = """
<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions
    xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
    id="Definitions"
    targetNamespace="http://bpmn.io/bpmn">
  <bpmn:process id="Process_1">
  </bpmn:process>
</bpmn:definitions>
"""


@pytest.mark.upstream(
    "bpmnlint/test/spec/testers/helpers-spec.mjs",
    "testers/helper > #createModdle > should create moddle with extension",
)
def test_create_moddle_with_extension() -> None:
    root = create_moddle(_XML, {"t": _TEST_MODDLE})["root"]
    assert is_(root, "t:TestDefinitions") is True


@pytest.mark.upstream(
    "bpmnlint/test/spec/testers/helpers-spec.mjs",
    "testers/helper > #readModdle > should read moddle with extension",
)
def test_read_moddle_with_extension() -> None:
    root = read_moddle(TESTERS_DIR / "diagram.bpmn", {"t": _TEST_MODDLE})["root"]
    assert is_(root, "t:TestDefinitions") is True


@pytest.fixture
def moddle() -> BpmnModdle:
    return BpmnModdle()


@pytest.mark.upstream(
    "bpmnlint/test/spec/testers/rule-tester-spec.mjs",
    "testers/rule-tester > #expectEqual > should not be equal",
)
def test_expect_equal_not_equal() -> None:
    with pytest.raises(AssertionError):
        expect_equal({"foo": "bar"}, {"foo": "baz"})


@pytest.mark.upstream(
    "bpmnlint/test/spec/testers/rule-tester-spec.mjs",
    "testers/rule-tester > #expectEqual > should be equal (moddle element with ID)",
)
def test_expect_equal_element_with_id(moddle: BpmnModdle) -> None:
    expect_equal({"node": moddle.create("bpmn:Task", {"id": "Task_1"})}, {"node": "Task_1"})


@pytest.mark.upstream(
    "bpmnlint/test/spec/testers/rule-tester-spec.mjs",
    "testers/rule-tester > #expectEqual > should be equal (moddle element with no ID)",
)
def test_expect_equal_element_without_id(moddle: BpmnModdle) -> None:
    expect_equal({"node": moddle.create("bpmn:Task")}, {"node": "bpmn:Task"})


@pytest.mark.upstream(
    "bpmnlint/test/spec/testers/rule-tester-spec.mjs",
    "testers/rule-tester > #getTitle > it should get name (index)",
)
def test_get_title_index() -> None:
    assert get_title(1) == "test case #2"


@pytest.mark.upstream(
    "bpmnlint/test/spec/testers/rule-tester-spec.mjs",
    "testers/rule-tester > #getTitle > it should get name (index and name)",
)
def test_get_title_index_and_name() -> None:
    assert get_title(1, "foo") == "test case #2 foo"


@pytest.mark.upstream(
    "bpmnlint/test/spec/testers/rule-tester-spec.mjs",
    "testers/rule-tester > #replacer > should replace node",
)
def test_replacer_replace_node(moddle: BpmnModdle) -> None:
    report = {
        "foo": "bar",
        "bar": 0,
        "baz": [
            {"foo": "bar"},
            moddle.create("bpmn:Task"),
            1,
        ],
    }
    actual = json.dumps(report, default=lambda value: replacer("", value), indent=2)
    expected = json.dumps(
        {
            "foo": "bar",
            "bar": 0,
            "baz": [
                {"foo": "bar"},
                "bpmn:Task",
                1,
            ],
        },
        indent=2,
    )
    assert actual == expected


def _local_config_factory(config: object = None) -> dict[str, object]:
    def check(node: object, reporter: object) -> None:
        reporter.report(node.get("id"), config)

    return {"check": check}


def _local_config_factory_with_meta(config: object = None) -> dict[str, object]:
    def check(node: object, reporter: object) -> None:
        reporter.report(node.get("id"), config)

    return {"check": check, "meta": {"foo": 1}}


@pytest.mark.upstream(
    "bpmnlint/test/spec/testers/rule-tester-spec.mjs",
    "testers/rule-tester > #verify > with local config > rules/with-local-config > should lint invalid > test case #1 with config",  # noqa: E501
)
def test_verify_with_local_config() -> None:
    root = create_moddle('<bpmn:Task id="Task_1" />', "bpmn:Task")["root"]
    verify(
        "with-local-config",
        _local_config_factory,
        {
            "valid": [],
            "invalid": [
                {
                    "name": "with config",
                    "config": "foo",
                    "moddle_element": root,
                    "report": {"id": "Task_1", "message": "foo"},
                },
            ],
        },
    )


@pytest.mark.upstream(
    "bpmnlint/test/spec/testers/rule-tester-spec.mjs",
    "testers/rule-tester > #verify > with <meta> > rules/with-local-config > should lint invalid > test case #1 with config",  # noqa: E501
)
def test_verify_with_meta() -> None:
    root = create_moddle('<bpmn:Task id="Task_1" />', "bpmn:Task")["root"]
    verify(
        "with-local-config",
        _local_config_factory_with_meta,
        {
            "valid": [],
            "invalid": [
                {
                    "name": "with config",
                    "config": "foo",
                    "moddle_element": root,
                    "report": {"id": "Task_1", "message": "foo"},
                },
            ],
        },
    )
