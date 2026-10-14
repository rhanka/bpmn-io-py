"""Tests for the ``bpmn-io lint`` CLI subcommand (adapted JS CLI, Lot 14)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from bpmn_io.cli import main
from tests.conftest import upstream_dir

VALID = (
    upstream_dir("bpmnlint")
    / "test"
    / "rules"
    / "conditional-flows"
    / "valid-conditional-fork.bpmn"
)
INVALID = upstream_dir("bpmnlint") / "test" / "rules" / "label-required" / "invalid-task.bpmn"


@pytest.fixture(autouse=True)
def _chdir_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_lint_missing_config(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["lint", str(VALID)]) == 2
    assert ".bpmnlintrc" in capsys.readouterr().err


def test_lint_init_creates_config(tmp_path: Path) -> None:
    assert main(["lint", "--init"]) == 0
    created = tmp_path / ".bpmnlintrc"
    assert json.loads(created.read_text()) == {"extends": "bpmnlint:recommended"}
    # second init refuses to override
    assert main(["lint", "--init"]) == 1


def test_lint_reports_errors_and_exit_1(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / ".bpmnlintrc").write_text('{"extends": "bpmnlint:recommended"}')
    assert main(["lint", str(INVALID)]) == 1
    out = capsys.readouterr().out
    assert "Element is missing label/name" in out
    assert "label-required" in out


def test_lint_valid_file_exit_0(tmp_path: Path) -> None:
    (tmp_path / ".bpmnlintrc").write_text(
        '{"rules": {"conditional-flows": "error"}}',
    )
    assert main(["lint", str(VALID)]) == 0


def test_lint_config_override_and_glob(tmp_path: Path) -> None:
    config = tmp_path / "custom.json"
    config.write_text('{"extends": "bpmnlint:correctness"}')
    assert main(["lint", "--config", str(config), str(tmp_path / "*.bpmn")]) == 0


FAKE_JOIN_INVALID = upstream_dir("bpmnlint") / "test" / "rules" / "fake-join" / "invalid-task.bpmn"


def test_lint_max_warnings(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / ".bpmnlintrc").write_text('{"rules": {"fake-join": "warn"}}')
    # warnings only: exit 0 by default, exit 1 with --max-warnings=0
    assert main(["lint", str(FAKE_JOIN_INVALID)]) == 0
    capsys.readouterr()
    assert main(["lint", "--max-warnings", "0", str(FAKE_JOIN_INVALID)]) == 1
