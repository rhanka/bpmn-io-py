"""Shared per-case runner for the ported RuleTester rule suites."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bpmn_io.lint.testers.helper import read_moddle
from bpmn_io.lint.testers.rule_tester import verify
from tests.conftest import upstream_dir

if TYPE_CHECKING:
    from collections.abc import Callable

RULES_DIR = upstream_dir("bpmnlint") / "test" / "rules"


def assert_valid(
    rule_name: str,
    factory: Callable[..., dict[str, Any]],
    case: dict[str, Any],
) -> None:
    """Assert one upstream valid case lints clean (RuleTester ``should lint valid``)."""
    root = read_moddle(RULES_DIR / case["fixture"])["root"]
    verify(
        rule_name,
        factory,
        {
            "valid": [{"moddle_element": root, "config": case.get("config") or {}}],
            "invalid": [],
        },
    )


def assert_invalid(
    rule_name: str,
    factory: Callable[..., dict[str, Any]],
    case: dict[str, Any],
) -> None:
    """Assert one upstream invalid case produces exactly its reports."""
    root = read_moddle(RULES_DIR / case["fixture"])["root"]
    verify(
        rule_name,
        factory,
        {
            "valid": [],
            "invalid": [
                {
                    "moddle_element": root,
                    "config": case.get("config") or {},
                    "report": case["report"],
                },
            ],
        },
    )
