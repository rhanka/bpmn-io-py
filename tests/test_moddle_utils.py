"""Ported tests for ``bpmn_io._moddle_utils`` (upstream ``@bpmn-io/moddle-utils``)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from bpmn_io._js import UNDEFINED
from bpmn_io._moddle_utils import get_path, path_concat, path_equals, path_parse, path_stringify
from bpmn_io.bpmn_moddle import create_moddle

if TYPE_CHECKING:
    from bpmn_io.moddle.base import ModdleElement
from tests.conftest import read_fixture

_ZEEBE: dict[str, object] = {
    "name": "Zeebe",
    "uri": "http://camunda.org/schema/zeebe/1.0",
    "prefix": "zeebe",
    "xml": {"tagAlias": "lowerCase"},
    "types": [
        {
            "name": "TaskDefinition",
            "superClass": ["Element"],
            "properties": [
                {"name": "type", "type": "String", "isAttr": True},
                {"name": "retries", "type": "String", "isAttr": True},
            ],
        },
    ],
    "enumerations": [],
    "associations": [],
}


@pytest.fixture
def definitions() -> ModdleElement:
    moddle = create_moddle({"zeebe": _ZEEBE})
    xml = read_fixture("moddle-utils", "test/diagram.bpmn")
    return moddle.from_xml(xml).root_element


def _extension_value(definitions: ModdleElement) -> ModdleElement:
    return (
        definitions.get("rootElements")[0]
        .get("flowElements")[0]
        .get("extensionElements")
        .get("values")[0]
    )


@pytest.mark.upstream(
    "moddle-utils/test/index.spec.js", "index > #getPath > should return path (flow element)"
)
def test_get_path_flow_element(definitions: ModdleElement) -> None:
    element = definitions.get("rootElements")[0].get("flowElements")[0]
    assert get_path(element) == ["rootElements", 0, "flowElements", 0]


@pytest.mark.upstream(
    "moddle-utils/test/index.spec.js", "index > #getPath > should return path (extension element)"
)
def test_get_path_extension_element(definitions: ModdleElement) -> None:
    assert get_path(_extension_value(definitions)) == [
        "rootElements",
        0,
        "flowElements",
        0,
        "extensionElements",
        "values",
        0,
    ]


@pytest.mark.upstream(
    "moddle-utils/test/index.spec.js",
    "index > #getPath > should return relative path (extension element)",
)
def test_get_path_relative(definitions: ModdleElement) -> None:
    parent = definitions.get("rootElements")[0].get("flowElements")[0]
    assert get_path(_extension_value(definitions), parent) == ["extensionElements", "values", 0]


@pytest.mark.upstream(
    "moddle-utils/test/index.spec.js",
    "index > #getPath > should return null instead of path ($parent=undefined)",
)
def test_get_path_parent_undefined(definitions: ModdleElement) -> None:
    element = _extension_value(definitions)
    definitions.get("rootElements")[0].get("flowElements")[0].parent_ = None
    assert get_path(element) is None


@pytest.mark.upstream(
    "moddle-utils/test/index.spec.js",
    "index > #getPath > should return null instead of relative path ($parent=undefined)",
)
def test_get_path_relative_parent_undefined(definitions: ModdleElement) -> None:
    parent = definitions.get("rootElements")[0].get("flowElements")[0]
    element = _extension_value(definitions)
    element.parent_ = None
    assert get_path(element, parent) is None


@pytest.mark.upstream(
    "moddle-utils/test/index.spec.js",
    "index > #getPath > should return null (moddleElement=undefined)",
)
def test_get_path_undefined() -> None:
    assert get_path() is None


@pytest.mark.upstream(
    "moddle-utils/test/index.spec.js",
    "index > #getPath > should return [] (moddleElement=parentModdleElement)",
)
def test_get_path_same(definitions: ModdleElement) -> None:
    element = _extension_value(definitions)
    element.parent_ = None
    assert get_path(element, element) == []


@pytest.mark.upstream(
    "moddle-utils/test/index.spec.js", "index > #pathConcat > should concat (string[], string[])"
)
def test_path_concat_lists() -> None:
    assert path_concat(["foo"], ["bar", "baz"]) == ["foo", "bar", "baz"]


@pytest.mark.upstream(
    "moddle-utils/test/index.spec.js",
    "index > #pathConcat > should concat (string[], (number|string)[], (number|string)[])",
)
def test_path_concat_mixed() -> None:
    assert path_concat(["foo"], [0, "bar"], [1, "baz"]) == ["foo", 0, "bar", 1, "baz"]


@pytest.mark.upstream(
    "moddle-utils/test/index.spec.js",
    "index > #pathConcat > should concat (string[], number, string)",
)
def test_path_concat_scalars() -> None:
    assert path_concat(["foo"], 0, "bar") == ["foo", 0, "bar"]


@pytest.mark.upstream(
    "moddle-utils/test/index.spec.js", "index > #pathConcat > should return null (null)"
)
def test_path_concat_null() -> None:
    assert path_concat(None, ["bar", "baz"]) is None


@pytest.mark.upstream(
    "moddle-utils/test/index.spec.js", "index > #pathConcat > should return null (undefined)"
)
def test_path_concat_undefined() -> None:
    assert path_concat(UNDEFINED, ["bar", "baz"]) is None


@pytest.mark.upstream(
    "moddle-utils/test/index.spec.js", "index > #pathEquals > should be equal (string, string)"
)
def test_path_equals_strings() -> None:
    assert path_equals("foo.bar.0.baz", "foo.bar.0.baz") is True


@pytest.mark.upstream(
    "moddle-utils/test/index.spec.js", "index > #pathEquals > should not be equal (string, string)"
)
def test_path_equals_strings_not() -> None:
    assert path_equals("foo.bar.0.baz", "foo.bar.baz") is False


@pytest.mark.upstream(
    "moddle-utils/test/index.spec.js", "index > #pathEquals > should be equal (string, string[])"
)
def test_path_equals_string_list() -> None:
    assert path_equals("foo.bar.0.baz", ["foo", "bar", 0, "baz"]) is True


@pytest.mark.upstream(
    "moddle-utils/test/index.spec.js",
    "index > #pathEquals > should not be equal (string, string[])",
)
def test_path_equals_string_list_not() -> None:
    assert path_equals("foo.bar.0.baz", ["foo", "bar", "baz"]) is False


@pytest.mark.upstream(
    "moddle-utils/test/index.spec.js", "index > #pathEquals > should be equal (string[], string[])"
)
def test_path_equals_lists() -> None:
    assert path_equals(["foo", "bar", 0, "baz"], ["foo", "bar", 0, "baz"]) is True


@pytest.mark.upstream(
    "moddle-utils/test/index.spec.js",
    "index > #pathEquals > should not be equal (string[], string[])",
)
def test_path_equals_lists_not() -> None:
    assert path_equals(["foo", "bar", 0, "baz"], ["foo", "bar", "baz"]) is False


@pytest.mark.upstream(
    "moddle-utils/test/index.spec.js", "index > #pathEquals > should be equal (custom separator)"
)
def test_path_equals_custom_separator() -> None:
    assert path_equals("foo-bar-0-baz", "foo-bar-0-baz", "-") is True


@pytest.mark.upstream(
    "moddle-utils/test/index.spec.js", "index > #pathEquals > should not be equal (null)"
)
def test_path_equals_null() -> None:
    assert path_equals(None, ["foo"]) is False


@pytest.mark.upstream(
    "moddle-utils/test/index.spec.js", "index > #pathEquals > should not be equal (undefined)"
)
def test_path_equals_undefined() -> None:
    assert path_equals(UNDEFINED, ["foo"]) is False


@pytest.mark.upstream("moddle-utils/test/index.spec.js", "index > #pathParse > should parse path")
def test_path_parse() -> None:
    assert path_parse("rootElements.0.flowElements.0.extensionElements.values.0.type") == [
        "rootElements",
        0,
        "flowElements",
        0,
        "extensionElements",
        "values",
        0,
        "type",
    ]


@pytest.mark.upstream(
    "moddle-utils/test/index.spec.js", "index > #pathParse > should parse path (custom separator)"
)
def test_path_parse_custom_separator() -> None:
    assert path_parse("rootElements-0-flowElements-0-extensionElements-values-0-type", "-") == [
        "rootElements",
        0,
        "flowElements",
        0,
        "extensionElements",
        "values",
        0,
        "type",
    ]


@pytest.mark.upstream(
    "moddle-utils/test/index.spec.js", "index > #pathParse > should not parse path (null)"
)
def test_path_parse_null() -> None:
    assert path_parse(None) is None


@pytest.mark.upstream(
    "moddle-utils/test/index.spec.js", "index > #pathStringify > should stringify path"
)
def test_path_stringify() -> None:
    path = ["rootElements", 0, "flowElements", 0, "extensionElements", "values", 0, "type"]
    assert path_stringify(path) == "rootElements.0.flowElements.0.extensionElements.values.0.type"


@pytest.mark.upstream(
    "moddle-utils/test/index.spec.js",
    "index > #pathStringify > should stringify path (custom separator)",
)
def test_path_stringify_custom_separator() -> None:
    path = ["rootElements", 0, "flowElements", 0, "extensionElements", "values", 0, "type"]
    assert (
        path_stringify(path, "-") == "rootElements-0-flowElements-0-extensionElements-values-0-type"
    )


@pytest.mark.upstream(
    "moddle-utils/test/index.spec.js", "index > #pathStringify > should not stringify path (null)"
)
def test_path_stringify_null() -> None:
    assert path_stringify(None) is None


@pytest.mark.upstream("moddle-utils/test/index.spec.cjs", "should expose CommonJS export")
def test_cjs_export_na() -> None:
    pytest.skip(
        "CommonJS export shape has no Python equivalent; "
        "the Python module surface is covered by the index.spec.js port"
    )
