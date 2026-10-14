"""Oracle differential: canonical lint reports on the full vendored corpus.

For every vendored ``.bpmn`` diagram (all upstream suites, 394 files) and
each built-in config (``bpmnlint:recommended`` and ``bpmnlint:all``), the
Python linter must produce exactly the reports of the pinned JS
implementation. Diagrams that the JS side cannot parse must fail to parse
on the Python side too (and the other way round); parseable diagrams are
compared report by report.

Canonical form uses JSON.stringify semantics on both sides: object keys
whose value is ``undefined`` (Python ``UNDEFINED``) are dropped, and
``undefined`` array entries become ``null``. Keys are sorted afterwards,
so key order does not matter.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from bpmn_io import BpmnModdle
from bpmn_io._js import UNDEFINED
from bpmn_io.lint import Linter
from bpmn_io.lint.resolver import NodeResolver

if TYPE_CHECKING:
    from collections.abc import Callable

pytestmark = pytest.mark.oracle

UPSTREAM_ROOT = Path(__file__).parent.parent / "upstream"

CONFIGS = ("recommended", "all")


def _diagrams() -> list[Path]:
    return sorted(UPSTREAM_ROOT.rglob("*.bpmn"))


def _relative(path: Path) -> str:
    return path.relative_to(UPSTREAM_ROOT).as_posix()


def _canonical(value: object) -> str:
    """JSON text with JSON.stringify semantics (undefined keys dropped)."""

    def convert(item: object) -> object:
        if item is UNDEFINED:
            return None
        if isinstance(item, dict):
            return {key: convert(entry) for key, entry in item.items() if entry is not UNDEFINED}
        if isinstance(item, (list, tuple)):
            return [convert(entry) for entry in item]
        return item

    return json.dumps(convert(value), sort_keys=True, ensure_ascii=False)


def _params() -> list[pytest.param]:  # type: ignore[type-arg]
    params: list[pytest.param] = []  # type: ignore[type-arg]
    for path in _diagrams():
        relative = _relative(path)
        params.extend(
            pytest.param(relative, config_name, id=f"{relative}::{config_name}")
            for config_name in CONFIGS
        )
    return params


@pytest.fixture(scope="session")
def expected_reports(
    oracle_call: Callable[[dict[str, object]], object],
) -> dict[tuple[str, str], dict[str, object]]:
    """JS oracle reports (or parse error) for every diagram x config."""
    diagrams = _diagrams()
    expected: dict[tuple[str, str], dict[str, object]] = {}
    for config_name in CONFIGS:
        config = {"extends": f"bpmnlint:{config_name}"}
        items = [{"xml": path.read_text(encoding="utf-8"), "config": config} for path in diagrams]
        result = oracle_call({"op": "lint-reports-batch", "items": items})
        assert isinstance(result, list)
        assert len(result) == len(diagrams)
        for path, entry in zip(diagrams, result, strict=True):
            assert isinstance(entry, dict)
            expected[(_relative(path), config_name)] = entry
    return expected


@pytest.mark.parametrize(("relative", "config_name"), _params())
def test_lint_reports_match_oracle_full_corpus(
    relative: str,
    config_name: str,
    expected_reports: dict[tuple[str, str], dict[str, object]],
) -> None:
    path = UPSTREAM_ROOT / relative
    expected = expected_reports[(relative, config_name)]
    js_parse_failed = "error" in expected

    moddle = BpmnModdle()
    root = None
    py_error = ""
    try:
        root = moddle.from_xml(path.read_text(encoding="utf-8")).root_element
    except Exception as err:  # noqa: BLE001 - parse outcome is the assertion
        py_error = str(err)

    if root is None:
        assert js_parse_failed, (
            f"{relative}: python parse failed ({py_error}) but the JS side parsed it"
        )
        return

    assert not js_parse_failed, (
        f"{relative}: JS parse failed ({expected.get('error')}) but python parsed it"
    )

    # A fresh linter per diagram, like the oracle: rule instances carry
    # per-lint state (upstream caches resolved rules on the instance).
    config = {"extends": f"bpmnlint:{config_name}"}
    actual = Linter(resolver=NodeResolver()).lint(root, config)
    assert _canonical(actual) == _canonical(expected.get("reports"))
