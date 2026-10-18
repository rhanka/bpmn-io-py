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


def _profile_variant(tmp_path: Path, mutate: str) -> Path:
    """Write a contract-breaking profile variant (reviewer probes for #1)."""
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    if mutate == "mechanism":
        profile["mechanismVersion"] = "999"
    elif mutate == "forbidden":
        profile["zzzForbidden"] = 1
    else:
        msg = f"unknown profile mutation: {mutate}"
        raise AssertionError(msg)
    variant = tmp_path / f"profile-{mutate}.json"
    variant.write_text(json.dumps(profile), encoding="utf-8")
    return variant


def _argv_for(
    tmp_path: Path,
    input_doc: dict[str, Any],
    *,
    overrides: dict[str, Path] | None = None,
) -> list[str]:
    """Stage one envelope/XML input and return the ``profile lint`` argv."""
    paths = {
        "profile": PROFILE,
        "schema": SCHEMA,
        "base": BASE,
        "descriptors": DESCRIPTORS,
    }
    if overrides:
        paths.update(overrides)
    input_path = tmp_path / "probe-input.json"
    input_path.write_text(json.dumps(input_doc), encoding="utf-8")
    return [
        "profile",
        "lint",
        "--input",
        str(input_path),
        "--profile",
        str(paths["profile"]),
        "--schema",
        str(paths["schema"]),
        "--base",
        str(paths["base"]),
        "--descriptors",
        str(paths["descriptors"]),
        "--registry",
        str(REGISTRY),
        "--phase",
        "post-normalize",
        "--readiness-policy",
        "accept",
        "--json",
    ]


def _refused(stdout: str, code: str) -> dict[str, Any]:
    """Parse stdout as a refused Result/1 carrying ``code``."""
    result = json.loads(stdout)
    assert result["status"] == "refused"
    assert result["code"] == code
    assert result["operation"] == "validate"
    (entry,) = result["report"]["entries"]
    assert entry["code"] == code
    assert entry["disposition"] == "refused"
    return result


def test_unsupported_mechanism_refuses_exit_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unsupported mechanismVersion refuses instead of reporting ok."""
    argv = _argv_for(
        tmp_path, {"xml": CLEAN_DOC}, overrides={"profile": _profile_variant(tmp_path, "mechanism")}
    )
    code, out, err = _run(argv, capsys)
    assert code == 1
    assert err == ""
    _refused(out, "profile-schema")


def test_forbidden_profile_field_refuses_exit_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A forbidden profile field refuses instead of reporting ok."""
    argv = _argv_for(
        tmp_path, {"xml": CLEAN_DOC}, overrides={"profile": _profile_variant(tmp_path, "forbidden")}
    )
    code, out, err = _run(argv, capsys)
    assert code == 1
    assert err == ""
    _refused(out, "profile-schema")


def test_id_only_schema_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A schema reduced to $id is not the pinned profile schema (exit 2)."""
    schema = tmp_path / "id-only-schema.json"
    schema.write_text(json.dumps({"$id": "urn:profile-mechanism:1:profile"}), encoding="utf-8")
    argv = _argv_for(tmp_path, {"xml": CLEAN_DOC}, overrides={"schema": schema})
    code, out, err = _run(argv, capsys)
    assert code == 2
    assert out == ""
    assert err.count("\n") == 1


def test_wrong_base_pin_refuses_exit_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A base file disagreeing with the profile pin refuses profile-pin."""
    base = json.loads(BASE.read_text(encoding="utf-8"))
    base["version"] = "tampered"
    base_path = tmp_path / "tampered-base.json"
    base_path.write_text(json.dumps(base), encoding="utf-8")
    argv = _argv_for(tmp_path, {"xml": CLEAN_DOC}, overrides={"base": base_path})
    code, out, err = _run(argv, capsys)
    assert code == 1
    assert err == ""
    _refused(out, "profile-pin")


def test_wrong_descriptors_pin_refuses_exit_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Descriptors disagreeing with the profile pin refuse descriptor-mismatch."""
    descriptors = json.loads(DESCRIPTORS.read_text(encoding="utf-8"))
    descriptors["scope"] = "tampered"
    descriptors_path = tmp_path / "tampered-descriptors.json"
    descriptors_path.write_text(json.dumps(descriptors), encoding="utf-8")
    argv = _argv_for(tmp_path, {"xml": CLEAN_DOC}, overrides={"descriptors": descriptors_path})
    code, out, err = _run(argv, capsys)
    assert code == 1
    assert err == ""
    _refused(out, "descriptor-mismatch")


def _neutral_envelope(xml: str, *, digest_override: str | None = None) -> dict[str, Any]:
    """Build a real DocumentEnvelope for ``xml`` through codec and envelope."""
    from bpmn_io.codec import parse_xml, project
    from bpmn_io.profile._c14n import digest
    from bpmn_io.profile._envelope import import_envelope

    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    parsed = parse_xml(xml.encode("utf-8"))
    assert parsed.ok
    projected = project(parsed.value)
    assert projected.ok
    assert isinstance(projected.value, dict)
    identity: dict[str, Any] = {
        "mechanismVersion": "1",
        "schemaVersion": "1.0.0",
        "profile": profile["profile"],
        "version": profile["version"],
        "sha256": digest_override or digest(profile),
        "base": profile["base"],
        "descriptors": [
            {"id": entry["id"], "sha256": entry["sha256"]} for entry in profile["descriptors"]
        ],
    }
    imported = import_envelope(projected.value, identity, source_format="bpmn-xml")
    assert imported.status == "ok"
    return imported.payload.to_json()  # type: ignore[union-attr]


def test_document_envelope_input_works(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A real DocumentEnvelope lints with its own revision on stdout."""
    envelope = _neutral_envelope(CLEAN_DOC)
    argv = _argv_for(tmp_path, envelope)
    code, out, err = _run(argv, capsys)
    assert code == 0
    assert err == ""
    result = json.loads(out)
    assert result["status"] == "ok"
    assert result["payload"]["ok"] is True
    assert result["revision"] == envelope["semanticRevision"]
    assert result["baseRevision"] == envelope["semanticRevision"]


def test_tampered_envelope_revision_refuses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An envelope revision that recomputes differently refuses profile-schema."""
    envelope = _neutral_envelope(CLEAN_DOC)
    envelope["semanticRevision"] = "0" * 64
    argv = _argv_for(tmp_path, envelope)
    code, out, err = _run(argv, capsys)
    assert code == 1
    assert err == ""
    _refused(out, "profile-schema")


def test_foreign_envelope_identity_refuses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An envelope under another profile digest refuses compatibility."""
    from bpmn_io.profile._c14n import digest

    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    real = digest(profile)
    foreign = ("0" if real[0] != "0" else "1") + real[1:]
    envelope = _neutral_envelope(CLEAN_DOC, digest_override=foreign)
    argv = _argv_for(tmp_path, envelope)
    code, out, err = _run(argv, capsys)
    assert code == 1
    assert err == ""
    refused = _refused(out, "profile-digest-mismatch")
    assert refused["revision"] == envelope["semanticRevision"]


def test_xml_input_carries_import_revisions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An XML source reports the §3.1 initial-import base and output revision."""
    from bpmn_io.profile._envelope import initial_base_revision

    argv = _argv_for(tmp_path, {"xml": CLEAN_DOC})
    code, out, err = _run(argv, capsys)
    assert code == 0
    assert err == ""
    result = json.loads(out)
    assert result["status"] == "ok"
    assert result["baseRevision"] == initial_base_revision(
        "bpmn-xml", source_bytes=CLEAN_DOC.encode("utf-8")
    )
    assert result["revision"] != result["baseRevision"]
    assert result["report"]["inputRevision"] == result["baseRevision"]
    assert result["report"]["outputRevision"] == result["revision"]


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
