"""In-process tests for the bpmn-io CLI (exit-code contract)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bpmn_io.bpmn_moddle.simple import create_moddle
from bpmn_io.cli import main

FIXTURES = Path(__file__).resolve().parent / "upstream"
SIMPLE = FIXTURES / "bpmn-moddle" / "test" / "fixtures" / "bpmn" / "simple.bpmn"
LAYOUT_INPUT = FIXTURES / "bpmn-auto-layout" / "test" / "fixtures" / "ad-hoc-sub-process.bpmn"


def test_check_ok_text(capsys: pytest.CaptureFixture[str]) -> None:
    """check on a valid file exits 0 with an ok line on stdout."""
    assert main(["check", str(SIMPLE)]) == 0
    out, err = capsys.readouterr()
    assert f"ok: {SIMPLE}" in out
    assert err == ""


def test_check_ok_json(capsys: pytest.CaptureFixture[str]) -> None:
    """check --json emits the result schema on stdout."""
    assert main(["check", str(SIMPLE), "--json"]) == 0
    out, err = capsys.readouterr()
    payload = json.loads(out)
    assert payload == {"ok": True, "errors": [], "warnings": [], "file": str(SIMPLE)}
    assert err == ""


def test_check_errors_text(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """check on garbage exits 1 with error lines on stdout."""
    bad = tmp_path / "bad.bpmn"
    bad.write_text("not xml at all", encoding="utf-8")
    assert main(["check", str(bad)]) == 1
    out, _err = capsys.readouterr()
    assert "error:" in out


def test_check_errors_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """check --json on garbage exits 1 with a parseable failure document."""
    bad = tmp_path / "bad.bpmn"
    bad.write_text("not xml at all", encoding="utf-8")
    assert main(["check", str(bad), "--json"]) == 1
    out, err = capsys.readouterr()
    payload = json.loads(out)
    assert payload["ok"] is False
    assert payload["errors"] != []
    assert payload["file"] == str(bad)
    assert err == ""


def test_roundtrip_ok_text(capsys: pytest.CaptureFixture[str]) -> None:
    """roundtrip prints XML that parses again."""
    assert main(["roundtrip", str(SIMPLE)]) == 0
    out, err = capsys.readouterr()
    assert "definitions" in out
    create_moddle().from_xml(out)
    assert err == ""


def test_roundtrip_ok_json(capsys: pytest.CaptureFixture[str]) -> None:
    """roundtrip --json wraps the XML in the result document."""
    assert main(["roundtrip", str(SIMPLE), "--json"]) == 0
    out, err = capsys.readouterr()
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["file"] == str(SIMPLE)
    create_moddle().from_xml(payload["xml"])
    assert err == ""


def test_roundtrip_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """roundtrip on garbage exits 1 with a stderr diagnostic."""
    bad = tmp_path / "bad.bpmn"
    bad.write_text("not xml at all", encoding="utf-8")
    assert main(["roundtrip", str(bad)]) == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert err != ""


def test_roundtrip_failure_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """roundtrip --json on garbage exits 1 with a parseable failure document."""
    bad = tmp_path / "bad.bpmn"
    bad.write_text("not xml at all", encoding="utf-8")
    assert main(["roundtrip", str(bad), "--json"]) == 1
    out, _err = capsys.readouterr()
    payload = json.loads(out)
    assert payload["ok"] is False
    assert payload["file"] == str(bad)


def test_layout_ok_text(capsys: pytest.CaptureFixture[str]) -> None:
    """layout prints DI XML for a process without diagrams."""
    assert main(["layout", str(LAYOUT_INPUT)]) == 0
    out, err = capsys.readouterr()
    assert "BPMNDiagram" in out
    assert err == ""


def test_layout_ok_json(capsys: pytest.CaptureFixture[str]) -> None:
    """layout --json wraps the DI XML in the result document."""
    assert main(["layout", str(LAYOUT_INPUT), "--json"]) == 0
    out, err = capsys.readouterr()
    payload = json.loads(out)
    assert payload["ok"] is True
    assert "BPMNDiagram" in payload["xml"]
    assert err == ""


def test_layout_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """layout on garbage exits 1 with a stderr diagnostic."""
    bad = tmp_path / "bad.bpmn"
    bad.write_text("not xml at all", encoding="utf-8")
    assert main(["layout", str(bad)]) == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert err != ""


def test_missing_file_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Every command reports a missing file on stderr with exit code 2."""
    missing = str(tmp_path / "missing.bpmn")
    for argv in (
        ["check", missing],
        ["check", missing, "--json"],
        ["roundtrip", missing],
        ["roundtrip", missing, "--json"],
        ["layout", missing],
        ["layout", missing, "--json"],
    ):
        assert main(argv) == 2
        out, err = capsys.readouterr()
        assert out == ""
        assert err != ""


def test_unknown_command_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    """argparse maps unknown commands to exit code 2."""
    with pytest.raises(SystemExit) as exc:
        main(["bogus", str(SIMPLE)])
    assert exc.value.code == 2
    _out, err = capsys.readouterr()
    assert err != ""
