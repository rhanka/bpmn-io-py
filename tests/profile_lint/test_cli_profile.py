"""In-process tests for ``bpmn-io profile lint`` (argv and exit codes)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from bpmn_io.cli import main
from tests.profile_lint.helpers import CLEAN_DOC, CONTRACTS, NAMED_TASK_DOC

PROFILE = CONTRACTS / "neutral-profile.json"
SCHEMA = CONTRACTS / "profile-mechanism-1.schema.json"
BASE = CONTRACTS / "neutral-base.json"
DESCRIPTORS = CONTRACTS / "neutral-descriptors.json"
REGISTRY = CONTRACTS / "neutral-registry.json"


def _stage(tmp_path: Path, xml: str, profile_path: Path = PROFILE) -> list[str]:
    """Stage CLI input files and return the ``profile lint`` argv."""
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps({"xml": xml}), encoding="utf-8")
    return [
        "profile",
        "lint",
        "--input",
        str(input_path),
        "--profile",
        str(profile_path),
        "--schema",
        str(SCHEMA),
        "--base",
        str(BASE),
        "--descriptors",
        str(DESCRIPTORS),
        "--registry",
        str(REGISTRY),
        "--phase",
        "post-normalize",
        "--readiness-policy",
        "accept",
        "--json",
    ]


def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    """Run the CLI and return ``(exit, stdout, stderr)``."""
    code = main(argv)
    out, err = capsys.readouterr()
    return code, out, err


def test_clean_document_exits_zero_with_result(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A clean document exits 0 with one Result/1 on stdout and no stderr."""
    code, out, err = _run(_stage(tmp_path, CLEAN_DOC), capsys)
    assert code == 0
    assert err == ""
    result = json.loads(out)
    assert result["status"] == "ok"
    assert result["operation"] == "validate"
    assert result["payload"]["ok"] is True
    assert result["report"]["reportVersion"] == "2"


def test_findings_exit_one_with_result(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A document with error findings exits 1 with one Result/1 on stdout."""
    code, out, err = _run(_stage(tmp_path, NAMED_TASK_DOC), capsys)
    assert code == 1
    assert err == ""
    result = json.loads(out)
    assert result["status"] == "ok"
    assert result["payload"]["ok"] is False
    assert result["payload"]["counts"]["error"] > 0


def test_unknown_extends_refuses_with_exit_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unknown extends target exits 1 with a refused Result/1 on stdout."""
    profile_doc: dict[str, Any] = json.loads(PROFILE.read_text(encoding="utf-8"))
    validation = []
    for entry in profile_doc["validation"]:
        assert isinstance(entry, dict)
        patched = entry
        if entry.get("id") == "post-normalize" and entry.get("policy") == "accept":
            patched = {**entry, "extends": ["plugin:ghost/missing"]}
        validation.append(patched)
    ghost = tmp_path / "ghost-profile.json"
    ghost.write_text(json.dumps({**profile_doc, "validation": validation}), encoding="utf-8")
    code, out, err = _run(_stage(tmp_path, NAMED_TASK_DOC, ghost), capsys)
    assert code == 1
    assert err == ""
    result = json.loads(out)
    assert result["status"] == "refused"
    assert result["code"] == "lint-config-unknown"


def test_missing_input_file_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """An unreadable input exits 2 with one stderr line and no stdout."""
    argv = _stage(tmp_path, NAMED_TASK_DOC)
    argv[argv.index("--input") + 1] = str(tmp_path / "absent.json")
    code, out, err = _run(argv, capsys)
    assert code == 2
    assert out == ""
    assert err.count("\n") == 1


def test_malformed_profile_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A profile that is not a JSON object exits 2 with one stderr line."""
    bad = tmp_path / "bad-profile.json"
    bad.write_text("[1, 2]", encoding="utf-8")
    code, out, err = _run(_stage(tmp_path, NAMED_TASK_DOC, bad), capsys)
    assert code == 2
    assert out == ""
    assert err.count("\n") == 1


def test_wrong_schema_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A schema pin that is not the profile schema exits 2."""
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps({"$id": "urn:elsewhere:1:other"}), encoding="utf-8")
    argv = _stage(tmp_path, NAMED_TASK_DOC)
    argv[argv.index("--schema") + 1] = str(schema)
    code, out, err = _run(argv, capsys)
    assert code == 2
    assert out == ""
    assert "pinned profile schema" in err


def test_invalid_phase_choice_exits_two(capsys: pytest.CaptureFixture[str]) -> None:
    """An unknown phase is rejected by argv parsing (exit 2, argparse)."""
    with pytest.raises(SystemExit) as excinfo:
        main(["profile", "lint", "--phase", "draft"])
    assert excinfo.value.code == 2
    _out, _err = capsys.readouterr()


def test_standard_lint_json_is_untouched(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The standard ``lint --json`` path ignores profile data entirely."""
    from bpmn_io.bpmn_moddle.simple import create_moddle
    from bpmn_io.cli import _jsonable
    from bpmn_io.lint import Linter
    from bpmn_io.lint.resolver import NodeResolver

    diagram = tmp_path / "diagram.bpmn"
    diagram.write_text(NAMED_TASK_DOC, encoding="utf-8")
    code, out, err = _run(["lint", "--config", "recommended", str(diagram), "--json"], capsys)
    assert code == 1
    assert err == ""
    cli_payload = json.loads(out)
    root = create_moddle().from_xml(NAMED_TASK_DOC).root_element
    direct = Linter(config={"extends": "bpmnlint:recommended"}, resolver=NodeResolver()).lint(root)
    assert cli_payload["reports"] == json.loads(json.dumps(_jsonable(direct)))
    assert cli_payload["ok"] is False
    assert "profile" not in json.dumps(cli_payload)
