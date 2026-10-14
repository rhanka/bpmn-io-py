"""Ported tests for ``bpmn_io.lint.test_rule`` (upstream ``test/spec/test-rule-spec.mjs``)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from bpmn_io._bpmnlint_utils import is_
from bpmn_io.lint.test_rule import Reporter
from bpmn_io.lint.test_rule import test_rule as run_test_rule
from bpmn_io.lint.testers.helper import read_moddle
from tests.conftest import upstream_dir

if TYPE_CHECKING:
    from bpmn_io.moddle.base import ModdleElement

SPEC = upstream_dir("bpmnlint") / "test" / "spec"


@pytest.fixture
def moddle_root() -> ModdleElement:
    return read_moddle(SPEC / "diagram.bpmn")["root"]


def _fake_check_rule_with_reports(_utils: object = None) -> dict[str, object]:
    def check(node: ModdleElement, reporter: Reporter) -> None:
        if is_(node, "Definitions"):
            reporter.report(node.get("id"), "Definitions detected")

    return {"check": check}


def _fake_check_rule_with_path(_utils: object = None) -> dict[str, object]:
    def check(node: ModdleElement, reporter: Reporter) -> None:
        if is_(node, "Collaboration"):
            reporter.report(node.get("id"), "Collaboration detected", ["rootElements", 0])

    return {"check": check}


def _fake_check_rule_with_object(_utils: object = None) -> dict[str, object]:
    def check(node: ModdleElement, reporter: Reporter) -> None:
        if is_(node, "Collaboration"):
            reporter.report(
                node.get("id"),
                "Collaboration detected",
                {"path": ["rootElements", 0], "foo": "foo"},
            )

    return {"check": check}


def _fake_enter_leave_rule_with_reports(_utils: object = None) -> dict[str, object]:
    def enter(node: ModdleElement, reporter: Reporter) -> None:
        if is_(node, "Definitions"):
            reporter.report(node.get("id"), "Definitions enter")

    def leave(node: ModdleElement, reporter: Reporter) -> None:
        if is_(node, "Definitions"):
            reporter.report(node.get("id"), "Definitions leave")

    return {"check": {"enter": enter, "leave": leave}}


def _fake_check_rule_without_reports(_utils: object = None) -> dict[str, object]:
    return {"check": lambda _node, _reporter: None}


@pytest.mark.upstream(
    "bpmnlint/test/spec/test-rule-spec.mjs",
    "test-rule > should return check function reported messages (id, message)",
)
def test_check_reports_id_message(moddle_root: ModdleElement) -> None:
    messages = run_test_rule(moddle_root, _fake_check_rule_with_reports())
    assert messages == [
        {
            "id": "sid-38422fae-e03e-43a3-bef4-bd33b32041b2",
            "message": "Definitions detected",
        },
    ]


@pytest.mark.upstream(
    "bpmnlint/test/spec/test-rule-spec.mjs",
    "test-rule > should return check function reported messages (id, message, path)",
)
def test_check_reports_id_message_path(moddle_root: ModdleElement) -> None:
    messages = run_test_rule(moddle_root, _fake_check_rule_with_path())
    assert messages == [
        {
            "id": "Collaboration_0wzd2dx",
            "message": "Collaboration detected",
            "path": ["rootElements", 0],
        },
    ]


@pytest.mark.upstream(
    "bpmnlint/test/spec/test-rule-spec.mjs",
    "test-rule > should return check function reported messages (id, message, { path })",
)
def test_check_reports_id_message_object(moddle_root: ModdleElement) -> None:
    messages = run_test_rule(moddle_root, _fake_check_rule_with_object())
    assert messages == [
        {
            "id": "Collaboration_0wzd2dx",
            "message": "Collaboration detected",
            "path": ["rootElements", 0],
            "foo": "foo",
        },
    ]


@pytest.mark.upstream(
    "bpmnlint/test/spec/test-rule-spec.mjs",
    "test-rule > should return { enter, leave } hook reported messages",
)
def test_enter_leave_reports(moddle_root: ModdleElement) -> None:
    messages = run_test_rule(moddle_root, _fake_enter_leave_rule_with_reports())
    assert messages == [
        {
            "id": "sid-38422fae-e03e-43a3-bef4-bd33b32041b2",
            "message": "Definitions enter",
        },
        {
            "id": "sid-38422fae-e03e-43a3-bef4-bd33b32041b2",
            "message": "Definitions leave",
        },
    ]


@pytest.mark.upstream(
    "bpmnlint/test/spec/test-rule-spec.mjs",
    "test-rule > should empty messages",
)
def test_empty_messages(moddle_root: ModdleElement) -> None:
    assert run_test_rule(moddle_root, _fake_check_rule_without_reports()) == []
