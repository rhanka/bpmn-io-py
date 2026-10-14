"""Ported tests for ``bpmn_io._bpmnlint_utils`` (upstream ``bpmnlint-utils``)."""

from __future__ import annotations

import pytest

from bpmn_io._bpmnlint_utils import is_, is_any


class _Node:
    """Test double mirroring the upstream ``{ $instanceOf }`` node."""

    def instance_of(self, type: str) -> bool:  # noqa: A002 - upstream property name
        return type == "bpmn:Foo"


@pytest.mark.upstream(
    "bpmnlint-utils/test/spec/index-spec.js", "utils > is(node, type) > should match node"
)
def test_is_match() -> None:
    node = _Node()
    assert is_(node, "Foo") is True
    assert is_(node, "bpmn:Foo") is True


@pytest.mark.upstream(
    "bpmnlint-utils/test/spec/index-spec.js", "utils > is(node, type) > should not match node"
)
def test_is_not_match() -> None:
    assert is_(_Node(), "Baz") is False


@pytest.mark.upstream(
    "bpmnlint-utils/test/spec/index-spec.js",
    "utils > isAny(node, [ ...types ]) > should match node",
)
def test_is_any_match() -> None:
    node = _Node()
    assert is_any(node, ["Foo", "bpmn:Bar"]) is True
    assert is_any(node, ["bpmn:Foo"]) is True


@pytest.mark.upstream(
    "bpmnlint-utils/test/spec/index-spec.js",
    "utils > isAny(node, [ ...types ]) > should not match node",
)
def test_is_any_not_match() -> None:
    assert is_any(_Node(), ["Baz", "bpmn:Blub"]) is False
