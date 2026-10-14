"""Oracle differential: canonical lint reports on every bpmnlint test diagram.

For each ``test/rules/**/*.bpmn`` and ``test/spec/*.bpmn`` fixture of the
vendored bpmnlint suite, the Python linter (built-in rules, ``recommended``
config) must produce exactly the reports of the pinned JS implementation.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from bpmn_io import BpmnModdle
from bpmn_io.lint import Linter
from bpmn_io.lint.resolver import NodeResolver
from tests.conftest import upstream_dir

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

pytestmark = pytest.mark.oracle

CONFIG = {"extends": "bpmnlint:recommended"}


def _diagrams() -> list[Path]:
    root = upstream_dir("bpmnlint") / "test"
    found = sorted((root / "rules").rglob("*.bpmn"))
    found += sorted((root / "spec").glob("*.bpmn"))
    return found


def _canonical(reports: object) -> str:
    return json.dumps(reports, sort_keys=True, ensure_ascii=False)


def test_lint_reports_match_oracle_on_all_diagrams(
    oracle_call: Callable[[dict[str, object]], object],
) -> None:
    diagrams = _diagrams()
    assert diagrams, "expected vendored bpmnlint test diagrams"

    items = [{"xml": path.read_text(encoding="utf-8"), "config": CONFIG} for path in diagrams]
    expected = oracle_call({"op": "lint-reports-batch", "items": items})
    assert isinstance(expected, list)
    assert len(expected) == len(diagrams)

    moddle = BpmnModdle()

    mismatches: list[str] = []
    for path, expected_reports in zip(diagrams, expected, strict=True):
        try:
            root = moddle.from_xml(path.read_text(encoding="utf-8")).root_element
        except Exception as err:  # noqa: BLE001 - record and continue collecting
            mismatches.append(f"{path.name}: python parse failed: {err}")
            continue
        # A fresh linter per diagram, like the oracle: rule instances carry
        # per-lint state (upstream caches resolved rules on the instance).
        actual = Linter(resolver=NodeResolver()).lint(root, CONFIG)
        if _canonical(actual) != _canonical(expected_reports):
            mismatches.append(
                f"{path.relative_to(upstream_dir('bpmnlint'))}: "
                f"python={_canonical(actual)[:300]} oracle={_canonical(expected_reports)[:300]}",
            )

    assert not mismatches, "\n".join(mismatches[:10])
