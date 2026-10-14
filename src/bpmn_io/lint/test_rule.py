# Transposed from bpmn-io/bpmnlint@de71146 lib/test-rule.js (MIT).
"""Rule execution on a moddle tree, transposed from ``lib/test-rule.js``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bpmn_io._js import UNDEFINED
from bpmn_io.lint.traverse import traverse

if TYPE_CHECKING:
    from collections.abc import Callable

    from bpmn_io.moddle.base import ModdleElement

__all__ = ["Reporter", "test_rule"]


class Reporter:
    """Collects the reports a rule emits while its check runs."""

    def __init__(self, moddle_root: ModdleElement, rule: dict[str, Any]) -> None:
        """Bind the reporter to the linted ``moddle_root`` and ``rule``."""
        self.rule = rule
        self.moddle_root = moddle_root
        self.messages: list[dict[str, Any]] = []

    def report(
        self,
        id: object,  # noqa: A002 - upstream parameter name
        message: object,
        path: list[str | int] | dict[str, Any] | None = None,
    ) -> None:
        """Record one report (``id``, ``message``, optional ``path`` or extra fields)."""
        report: dict[str, Any] = {
            "id": id,
            "message": message,
        }

        if isinstance(path, list):
            report = {
                **report,
                "path": path,
            }

        if isinstance(path, dict):
            report = {
                **report,
                **path,
            }

        self.messages.append(report)


def test_rule(moddle_root: ModdleElement, rule: dict[str, Any]) -> list[dict[str, Any]]:
    """Apply ``rule`` on ``moddle_root`` and return its reports."""
    reporter = Reporter(moddle_root, rule)

    check = rule.get("check") or {}

    enter_fn: Callable[[ModdleElement, Reporter], object] | None = None
    leave_fn: Callable[[ModdleElement, Reporter], object] | None = None

    if isinstance(check, dict):
        raw_enter = check.get("enter", UNDEFINED)
        raw_leave = check.get("leave", UNDEFINED)
        enter_fn = raw_enter if callable(raw_enter) else None
        leave_fn = raw_leave if callable(raw_leave) else None
    elif callable(check):
        enter_fn = check

    if enter_fn is None and leave_fn is None:
        msg = "no check implemented"
        raise ValueError(msg)

    def _enter(node: ModdleElement) -> object:
        assert enter_fn is not None  # noqa: S101 - guarded by the check above
        return enter_fn(node, reporter)

    def _leave(node: ModdleElement) -> object:
        assert leave_fn is not None  # noqa: S101 - guarded by the check above
        return leave_fn(node, reporter)

    traverse(
        moddle_root,
        enter=_enter if enter_fn is not None else None,
        leave=_leave if leave_fn is not None else None,
    )

    return reporter.messages
