"""Command-line interface for bpmn-io: check, roundtrip, lay out and lint BPMN files."""

from __future__ import annotations

import argparse
import contextlib
import glob as glob_module
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from bpmn_io.bpmn_moddle import BpmnModdle
    from bpmn_io.lint.linter import Resolver

from bpmn_io._js import UNDEFINED
from bpmn_io._moddle_utils import path_stringify
from bpmn_io.auto_layout import LayoutError, layout_process
from bpmn_io.bpmn_moddle.simple import create_moddle
from bpmn_io.check import check
from bpmn_io.lint import Linter
from bpmn_io.lint.resolver import NodeResolver
from bpmn_io.moddle.base import ModdleElement
from bpmn_io.moddle_xml.read import ParseError
from bpmn_io.profile import lint as run_profile_lint
from bpmn_io.profile._lint.c14n import digest as profile_digest
from bpmn_io.profile._lint.errors import ProfileLintError
from bpmn_io.profile._lint.report import adapter_entry as profile_adapter_entry
from bpmn_io.profile._lint.transform import (
    flatten_policy,
    select_record,
    validate_compiled_options,
)

__all__ = ["main"]

#: Control characters that must never reach the terminal raw (cyber-review S3:
#: error text embeds offending input slices verbatim). Tab/newline survive;
#: everything else becomes a ``\\xNN`` escape. Non-ASCII text is untouched.
_UNSAFE_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _safe(text: str) -> str:
    """Escape terminal-unsafe control characters (payload XML never passes here)."""
    return _UNSAFE_CONTROL.sub(lambda match: f"\\x{ord(match.group()):02x}", text)


class _OutputError(Exception):
    """Stdout failed; ``message`` is None on a broken pipe (nothing to report to)."""

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message)
        self.message = message


def _out(text: str) -> None:
    """Write one normal-output line to stdout (cyber-review S2/S4).

    A closed pipe becomes ``_OutputError`` (exit 1, quietly); unencodable
    output (e.g. lone surrogates from numeric references) becomes
    ``_OutputError`` with a clean message instead of a traceback.
    """
    try:
        sys.stdout.write(text + "\n")
    except BrokenPipeError as err:
        raise _OutputError from err
    except UnicodeError as err:
        raise _OutputError(str(err)) from err


def _err(text: str) -> None:
    """Write one diagnostic line to stderr (sanitized, pipe-safe)."""
    with contextlib.suppress(BrokenPipeError):
        sys.stderr.write(_safe(text) + "\n")


def _fail_usage(message: str) -> int:
    """Report a usage/IO problem on stderr (exit code 2)."""
    _err(f"bpmn-io: {message}")
    return 2


def _read_input(file: str) -> str | None:
    """Read ``file`` as UTF-8, reporting problems on stderr (None on failure)."""
    try:
        return Path(file).read_text(encoding="utf-8")
    except (OSError, UnicodeError, ValueError) as err:
        # ValueError: embedded-NUL path (reachable via API use of main()).
        _err(f"bpmn-io: cannot read {file!r}: {err}")
        return None


def _cmd_check(file: str, *, as_json: bool) -> int:
    """Parse ``file`` and report L0 integrity findings."""
    xml = _read_input(file)
    if xml is None:
        return 2
    report = check(xml)
    if as_json:
        _out(
            json.dumps(
                {
                    "ok": report.ok,
                    "errors": list(report.errors),
                    "warnings": [warning.message for warning in report.warnings],
                    "file": file,
                }
            )
        )
    else:
        if report.ok:
            _out(f"ok: {file}")
        for warning in report.warnings:
            _out(f"warning: {_safe(warning.message)}")
        for error in report.errors:
            _out(f"error: {_safe(error)}")
    return 0 if report.ok else 1


def _cmd_roundtrip(file: str, *, as_json: bool) -> int:
    """Parse ``file`` and print it back out serialized."""
    xml = _read_input(file)
    if xml is None:
        return 2
    model = create_moddle()
    try:
        root = model.from_xml(xml).root_element
    except ParseError as err:
        return _fail_processing(file, err.message, as_json=as_json)
    try:
        out = model.to_xml(root, {"format": False, "preamble": True}).xml
    except Exception as err:  # noqa: BLE001 - CLI reports any serialization failure
        return _fail_processing(file, str(err), as_json=as_json)
    if as_json:
        _out(json.dumps({"ok": True, "file": file, "xml": out}))
    else:
        _out(out)
    return 0


def _cmd_layout(file: str, *, as_json: bool) -> int:
    """Lay out the first root process of ``file`` and print the DI XML."""
    xml = _read_input(file)
    if xml is None:
        return 2
    try:
        out = layout_process(xml)
    except (LayoutError, ParseError) as err:
        return _fail_processing(file, str(err), as_json=as_json)
    except Exception as err:  # noqa: BLE001 - CLI reports any layout failure
        return _fail_processing(file, str(err), as_json=as_json)
    if as_json:
        _out(json.dumps({"ok": True, "file": file, "xml": out}))
    else:
        _out(out)
    return 0


def _lint_category(category: str) -> str:
    """Map a lint report category to its CLI label (upstream ``categoryMap``)."""
    return {"warn": "warning"}.get(category, category)


def _print_lint_reports(file: str, results: dict[str, list[dict[str, Any]]]) -> tuple[int, int]:
    """Print one file's lint reports (upstream table output); return (errors, warnings)."""
    error_count = 0
    warning_count = 0
    rows: list[tuple[str, str, str, str]] = []
    for name, reports in results.items():
        for report in reports:
            category = str(report.get("category", ""))
            report_id = str(report.get("id") or "")
            path = report.get("path")
            if isinstance(path, list):
                report_id = f"{report_id}#{path_stringify(path)}"
            rows.append(
                (
                    report_id,
                    _lint_category(category),
                    str(report.get("message", "")),
                    str(report.get("name") or name),
                ),
            )
            if category == "error":
                error_count += 1
            else:
                warning_count += 1

    if rows:
        _out("")
        _out(str(Path(file).resolve()))
        for report_id, category, message, name in rows:
            _out(f"  {report_id}  {category}  {_safe(message)}  {name}")

    return error_count, warning_count


#: Built-in config names accepted by ``lint --config NAME``.
_LINT_BUILTIN_CONFIGS = ("all", "correctness", "recommended")


def _load_lint_config(config_arg: str | None) -> dict[str, Any] | None:
    """Load the lint config (built-in name, ``--config`` path or ``.bpmnlintrc``)."""
    if config_arg in _LINT_BUILTIN_CONFIGS:
        return {"extends": f"bpmnlint:{config_arg}"}
    if config_arg and config_arg.startswith("bpmnlint:"):
        return {"extends": config_arg}
    config_path = config_arg or ".bpmnlintrc"
    try:
        config_string = Path(config_path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        if config_arg:
            _err(f"bpmn-io: could not read {config_arg}")
        else:
            _err("bpmn-io: could not locate local .bpmnlintrc file. Create one via")
            _err("")
            _err("  bpmn-io lint --init")
        return None
    try:
        config = json.loads(config_string)
    except json.JSONDecodeError as err:
        _err(f"bpmn-io: could not parse {config_path}: {err}")
        return None
    if not isinstance(config, dict):
        _err(f"bpmn-io: could not parse {config_path}: expected a JSON object")
        return None
    return config


def _lint_moddle(config: dict[str, Any]) -> BpmnModdle | None:
    """Create the moddle instance with the config's ``moddleExtensions`` loaded."""
    extensions: dict[str, Any] = {}
    raw_extensions = config.get("moddleExtensions") or {}
    if isinstance(raw_extensions, dict):
        for name, extension_path in raw_extensions.items():
            try:
                loaded = json.loads(Path(str(extension_path)).read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as err:
                _err(
                    f"bpmn-io: could not load moddle extension <{name}> "
                    f"from {extension_path}: {err}",
                )
                return None
            extensions[name] = loaded
    if extensions:
        return create_moddle(extensions)
    return create_moddle()


def _jsonable(value: object) -> object:
    """Convert lint reports to JSON-safe data (JSON.stringify semantics).

    Object keys whose value is ``UNDEFINED`` are omitted (upstream
    ``JSON.stringify`` drops them); ``UNDEFINED`` array entries become
    ``None`` (``null``). The library API keeps ``UNDEFINED`` untouched.
    """
    if value is UNDEFINED:
        return None
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items() if item is not UNDEFINED}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _lint_file(
    file: str,
    config: dict[str, Any],
    model: BpmnModdle,
    *,
    as_json: bool = False,
) -> tuple[int, int]:
    """Lint one diagram file and print its reports."""
    xml = _read_input(file)
    if xml is None:
        return 1, 0

    try:
        result = model.from_xml(xml)
    except ParseError as err:
        reports: dict[str, list[dict[str, Any]]] = {
            "": [{"message": f"Parse error: {err.message}", "category": "error"}],
        }
        if as_json:
            _out(json.dumps({"ok": False, "file": file, "reports": _jsonable(reports)}))
            return 1, 0
        return _print_lint_reports(file, reports)

    import_reports: dict[str, list[dict[str, Any]]] = {}
    if result.warnings:
        import_reports = {
            "": [
                {
                    "id": getattr(getattr(warning, "element", None), "id", None) or "",
                    "message": (
                        "Import warning: "
                        + (str(warning.message).splitlines()[0] if warning.message else "")
                    ),
                    "category": "error",
                }
                for warning in result.warnings
            ],
        }

    linter = Linter(config=config, resolver=cast("Resolver", NodeResolver()))
    try:
        lint_reports = linter.lint(cast("ModdleElement", result.root_element))
    except Exception as err:  # noqa: BLE001 - CLI reports any lint failure
        _err(f"bpmn-io: {err}")
        return 1, 0

    all_reports = {**import_reports, **lint_reports}
    if as_json:
        error_count = sum(
            1
            for reports in all_reports.values()
            for report in reports
            if report.get("category") == "error"
        )
        warning_count = sum(
            1
            for reports in all_reports.values()
            for report in reports
            if report.get("category") != "error"
        )
        _out(
            json.dumps(
                {
                    "ok": error_count == 0,
                    "file": file,
                    "reports": _jsonable(all_reports),
                },
            ),
        )
        return error_count, warning_count

    return _print_lint_reports(file, all_reports)


def _cmd_lint(
    files: list[str],
    *,
    config_arg: str | None,
    init: bool,
    max_warnings: int,
    as_json: bool = False,
) -> int:
    """Lint diagram files against a bpmnlint config (adapted JS CLI)."""
    if init:
        target = Path(".bpmnlintrc")
        if target.exists():
            _err("bpmn-io: not overriding existing .bpmnlintrc")
            return 1
        target.write_text('{\n  "extends": "bpmnlint:recommended"\n}', encoding="utf-8")
        _out("Created .bpmnlintrc file")
        return 0

    if not files:
        _err("bpmn-io: lint: BPMN file path missing")
        return 2

    config = _load_lint_config(config_arg)
    model = _lint_moddle(config) if config is not None else None
    if config is None or model is None:
        return 2

    actual_files = _expand_lint_files(files)
    if actual_files is None:
        return 2

    error_count = 0
    warning_count = 0
    if not as_json:
        _out("")
    for file in actual_files:
        errors, warnings = _lint_file(file, config, model, as_json=as_json)
        error_count += errors
        warning_count += warnings

    problem_count = error_count + warning_count
    if problem_count and not as_json:
        _out("")
        _out(
            f"✖ {problem_count} problem{'s' if problem_count != 1 else ''} "
            f"({error_count} error{'s' if error_count != 1 else ''}, "
            f"{warning_count} warning{'s' if warning_count != 1 else ''})",
        )

    return 1 if error_count or (max_warnings != -1 and warning_count > max_warnings) else 0


def _expand_lint_files(files: list[str]) -> list[str] | None:
    """Expand glob patterns to the diagram files to lint (None on a missing file)."""
    actual_files: list[str] = []
    for pattern in files:
        matches = sorted(glob_module.glob(pattern, recursive=True))  # noqa: PTH207
        if matches:
            actual_files.extend(matches)
        elif glob_module.has_magic(pattern):
            continue
        elif Path(pattern).exists():
            actual_files.append(pattern)
        else:
            _err(f"bpmn-io: cannot read {pattern!r}: no such file")
            return None
    return actual_files


def _fail_processing(file: str, message: str, *, as_json: bool) -> int:
    """Report a processing failure (exit code 1), as JSON when requested."""
    if as_json:
        # json.dumps escapes control characters; no _safe needed.
        _out(json.dumps({"ok": False, "file": file, "error": message}))
    else:
        _err(f"bpmn-io: {_safe(message)}")
    return 1


def _run_check(args: argparse.Namespace) -> int:
    """Dispatch the check subcommand."""
    return _cmd_check(args.file, as_json=args.json)


def _run_roundtrip(args: argparse.Namespace) -> int:
    """Dispatch the roundtrip subcommand."""
    return _cmd_roundtrip(args.file, as_json=args.json)


def _run_layout(args: argparse.Namespace) -> int:
    """Dispatch the layout subcommand."""
    return _cmd_layout(args.file, as_json=args.json)


def _run_lint(args: argparse.Namespace) -> int:
    """Dispatch the lint subcommand."""
    return _cmd_lint(
        list(args.files),
        config_arg=args.config,
        init=args.init,
        max_warnings=args.max_warnings,
        as_json=args.json,
    )


class _InvalidInvocationError(Exception):
    """A profile-lint input problem (one stderr line, exit 2)."""


@dataclass(frozen=True)
class _ProfileLintArgs:
    """Parsed ``profile lint`` invocation (paths plus stage and policy)."""

    input_path: str
    profile_path: str
    schema_path: str
    base_path: str
    descriptors_path: str
    registry_path: str
    phase: str
    readiness_policy: str


@dataclass
class _ProfileInputs:
    """Parsed profile-lint documents ready for the lint bridge."""

    xml: str
    envelope_bytes: bytes
    profile_doc: dict[str, Any]
    base_doc: dict[str, Any]
    descriptors_doc: dict[str, Any]
    validation: list[Any]
    compiled_rules: list[Any]
    extra_configs: dict[str, Any]


def _read_json_input(label: str, path: str) -> tuple[dict[str, Any], bytes]:
    """Read and parse a profile-lint JSON input (raises on any problem)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError, ValueError) as err:
        msg = f"cannot read {label} {path!r}: {err}"
        raise _InvalidInvocationError(msg) from err
    try:
        data = json.loads(text)
    except json.JSONDecodeError as err:
        msg = f"could not parse {label} {path}: {err}"
        raise _InvalidInvocationError(msg) from err
    if not isinstance(data, dict):
        msg = f"could not parse {label} {path}: expected a JSON object"
        raise _InvalidInvocationError(msg)
    return data, text.encode("utf-8")


def _require_doc_id(label: str, doc: dict[str, Any]) -> None:
    """Require a string ``id`` on a profile-lint identity document."""
    doc_id = doc.get("id")
    if not isinstance(doc_id, str) or not doc_id:
        msg = f"{label} must carry a string id"
        raise _InvalidInvocationError(msg)


def _read_profile_inputs(args: _ProfileLintArgs) -> _ProfileInputs:
    """Read and shape-check every profile-lint input file."""
    envelope_doc, envelope_bytes = _read_json_input("--input", args.input_path)
    profile_doc, _ = _read_json_input("--profile", args.profile_path)
    schema_doc, _ = _read_json_input("--schema", args.schema_path)
    base_doc, _ = _read_json_input("--base", args.base_path)
    descriptors_doc, _ = _read_json_input("--descriptors", args.descriptors_path)
    registry_doc, _ = _read_json_input("--registry", args.registry_path)
    if schema_doc.get("$id") != "urn:profile-mechanism:1:profile":
        msg = "--schema is not the pinned profile schema"
        raise _InvalidInvocationError(msg)
    xml = envelope_doc.get("xml")
    if not isinstance(xml, str) or not xml:
        msg = "--input must be a JSON object with an xml string"
        raise _InvalidInvocationError(msg)
    _require_doc_id("--base", base_doc)
    _require_doc_id("--descriptors", descriptors_doc)
    _require_doc_id("--registry", registry_doc)
    validation = profile_doc.get("validation")
    compiled_rules = profile_doc.get("rules")
    if not isinstance(validation, list) or not isinstance(compiled_rules, list):
        msg = "--profile must carry validation and rules arrays"
        raise _InvalidInvocationError(msg)
    extra_configs = registry_doc.get("configs")
    if extra_configs is None:
        extra_configs = {}
    if not isinstance(extra_configs, dict):
        msg = "--registry configs must be an object when present"
        raise _InvalidInvocationError(msg)
    return _ProfileInputs(
        xml=xml,
        envelope_bytes=envelope_bytes,
        profile_doc=profile_doc,
        base_doc=base_doc,
        descriptors_doc=descriptors_doc,
        validation=validation,
        compiled_rules=compiled_rules,
        extra_configs=extra_configs,
    )


def _profile_identity_for(inputs: _ProfileInputs) -> dict[str, Any]:
    """Build the ``Result/1`` profile identity from the pinned inputs."""
    return {
        "mechanismVersion": str(inputs.profile_doc.get("mechanismVersion", "1")),
        "schemaVersion": str(inputs.profile_doc.get("schemaVersion", "")),
        "profile": str(inputs.profile_doc.get("profile", "")),
        "version": str(inputs.profile_doc.get("version", "")),
        "sha256": profile_digest(inputs.profile_doc),
        "base": {
            "id": str(inputs.base_doc.get("id")),
            "version": str(inputs.base_doc.get("version", "")),
            "sha256": profile_digest(inputs.base_doc),
        },
        "descriptors": [
            {
                "id": str(inputs.descriptors_doc.get("id")),
                "sha256": profile_digest(inputs.descriptors_doc),
            }
        ],
    }


def _build_cli_transport(
    inputs: _ProfileInputs,
    profile_digest_value: str,
    *,
    phase: str,
    readiness_policy: str,
) -> dict[str, Any]:
    """Build the validated transport options for the CLI invocation."""
    record = select_record(inputs.validation, phase=phase, readiness_policy=readiness_policy)
    flattened = flatten_policy(record, inputs.extra_configs)
    transport = {
        "mechanismVersion": "1",
        "profileDigest": profile_digest_value,
        "phase": phase,
        "readinessPolicy": readiness_policy,
        "compiledRules": inputs.compiled_rules,
        "bindings": [],
        "severityPolicyDigest": flattened.severity_policy_digest,
    }
    validate_compiled_options(transport)
    return transport


def _cmd_profile_lint(args: _ProfileLintArgs) -> int:
    """Lint one document envelope against a profile (DESIGN R3.3 §6.4).

    Exit 0 means ok, 1 means refused or a remaining error, 2 means invalid
    invocation. Exactly one ``Result/1`` goes to stdout; diagnostics use
    stderr. No module discovery or network follows profile data.
    """
    try:
        inputs = _read_profile_inputs(args)
    except _InvalidInvocationError as err:
        _err(f"bpmn-io: profile lint: {err}")
        return 2
    profile_identity = _profile_identity_for(inputs)
    revision = hashlib.sha256(inputs.envelope_bytes).hexdigest()

    try:
        transport = _build_cli_transport(
            inputs,
            str(profile_identity["sha256"]),
            phase=args.phase,
            readiness_policy=args.readiness_policy,
        )
    except Exception as err:  # noqa: BLE001 - profile data failures are refused results
        return _profile_lint_refused(
            str(err),
            code=_profile_lint_code(err),
            phase=args.phase,
            identity=profile_identity,
            revision=revision,
        )

    model = create_moddle()
    try:
        parsed = model.from_xml(inputs.xml)
    except ParseError as err:
        return _profile_lint_refused(
            f"input does not parse: {err.message}",
            code="operation-error",
            phase=args.phase,
            identity=profile_identity,
            revision=revision,
        )
    root = parsed.root_element
    if not isinstance(root, ModdleElement):
        _err("bpmn-io: profile lint: input is not a BPMN definitions tree")
        return 2
    try:
        result = run_profile_lint(
            root,
            {
                "compiledOptions": transport,
                "validation": inputs.validation,
                "registry": inputs.extra_configs,
            },
            phase=args.phase,
            readiness_policy=args.readiness_policy,
        )
    except (ValueError, TypeError) as err:
        _err(f"bpmn-io: profile lint: {err}")
        return 2
    result["profileIdentity"] = profile_identity
    result["baseRevision"] = revision
    result["revision"] = revision
    report = result.get("report")
    if isinstance(report, dict):
        report["inputRevision"] = revision
        report["outputRevision"] = revision
    if parsed.warnings:
        _attach_import_warnings(result, parsed.warnings, phase=args.phase)
    ordered: dict[str, Any] = {
        key: result[key]
        for key in (
            "status",
            "operation",
            "profileIdentity",
            "baseRevision",
            "revision",
            "report",
            "payload",
        )
        if key in result
    }
    ordered.update({key: result[key] for key in result if key not in ordered})
    _out(json.dumps(ordered, sort_keys=True))
    payload = result.get("payload")
    ok = result.get("status") == "ok" and isinstance(payload, dict) and payload.get("ok") is True
    return 0 if ok else 1


def _profile_lint_code(err: Exception) -> str:
    """Map a pre-evaluation profile failure to its stable refusal code."""
    if isinstance(err, ProfileLintError):
        return err.code
    return "operation-error"


def _profile_lint_refused(
    message: str,
    *,
    code: str,
    phase: str,
    identity: dict[str, Any] | None = None,
    revision: str | None = None,
) -> int:
    """Print a refused profile-lint ``Result/1`` on stdout (exit 1)."""
    result: dict[str, Any] = {
        "status": "refused",
        "operation": "validate",
        "code": code,
        "diagnostics": [message],
        "report": {
            "reportVersion": "2",
            "operation": "validate",
            "entries": [profile_adapter_entry(code, stage=phase, disposition="refused")],
            "rawStandardFindings": {},
            "idMap": [],
            "artifacts": [],
        },
    }
    if identity is not None:
        result["profileIdentity"] = identity
    if revision is not None:
        result["baseRevision"] = revision
        result["revision"] = revision
    _out(json.dumps(result, sort_keys=True))
    return 1


def _attach_import_warnings(
    result: dict[str, Any],
    warnings: list[Any],
    *,
    phase: str,
) -> None:
    """Surface native import warnings as integrity entries (never dropped).

    Each warning becomes an observed ``lint-rule-error`` entry (like the
    standard interface, which reports them as errors) and its text joins
    ``payload.importWarnings`` so nothing is lost from the unified shape.
    """
    texts: list[str] = []
    for warning in warnings:
        message = str(getattr(warning, "message", warning)).splitlines()
        texts.append(f"Import warning: {message[0] if message else warning}")
    report = result.get("report")
    if isinstance(report, dict) and isinstance(report.get("entries"), list):
        report["entries"].extend(
            profile_adapter_entry("lint-rule-error", stage=phase) for _ in texts
        )
    payload = result.get("payload")
    if isinstance(payload, dict):
        payload["importWarnings"] = texts
        payload["ok"] = False


def _run_profile_lint(args: argparse.Namespace) -> int:
    """Dispatch the profile lint subcommand."""
    return _cmd_profile_lint(
        _ProfileLintArgs(
            input_path=args.input,
            profile_path=args.profile,
            schema_path=args.schema,
            base_path=args.base,
            descriptors_path=args.descriptors,
            registry_path=args.registry,
            phase=args.phase,
            readiness_policy=args.readiness_policy,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    """Create the bpmn-io argument parser."""
    parser = argparse.ArgumentParser(
        prog="bpmn-io",
        description="Check, roundtrip, lay out and lint BPMN 2.0 files.",
        epilog="exit codes: 0 success (check passes with no errors), "
        "1 finding or processing failure, 2 usage or IO error.",
    )
    sub = parser.add_subparsers(
        dest="command", metavar="check|roundtrip|layout|lint|profile", required=True
    )
    commands: tuple[tuple[str, str, Any], ...] = (
        ("check", "parse a file and report integrity findings", _run_check),
        ("roundtrip", "parse a file and print it back out serialized", _run_roundtrip),
        ("layout", "lay out a file and print the DI XML", _run_layout),
    )
    for name, help_text, func in commands:
        subparser = sub.add_parser(name, help=help_text)
        subparser.add_argument("file", help="BPMN XML file to process")
        subparser.add_argument("--json", action="store_true", help="JSON output on stdout")
        subparser.set_defaults(func=func)

    lint_parser = sub.add_parser(
        "lint",
        help="lint diagram files against a bpmnlint config (built-in rules)",
    )
    lint_parser.add_argument("files", nargs="*", help="BPMN files or glob patterns to lint")
    lint_parser.add_argument(
        "--config",
        "-c",
        default=None,
        help="built-in config name (all, correctness, recommended) or path to a "
        "configuration file; overrides .bpmnlintrc if present",
    )
    lint_parser.add_argument(
        "--init",
        action="store_true",
        help="generate a .bpmnlintrc file in the current working directory",
    )
    lint_parser.add_argument("--json", action="store_true", help="JSON output on stdout")
    lint_parser.add_argument(
        "--max-warnings",
        type=int,
        default=-1,
        help="number of warnings to trigger nonzero exit code - default: -1",
    )
    lint_parser.set_defaults(func=_run_lint)

    profile_parser = sub.add_parser(
        "profile",
        help="profile mechanism operations (lot 1: lint only)",
    )
    profile_sub = profile_parser.add_subparsers(
        dest="profile_command", metavar="lint", required=True
    )
    profile_lint_parser = profile_sub.add_parser(
        "lint",
        help="lint a document envelope against a profile (unified Result/1)",
    )
    profile_lint_parser.add_argument("--input", required=True, help="envelope JSON file")
    profile_lint_parser.add_argument("--profile", required=True, help="profile JSON file")
    profile_lint_parser.add_argument("--schema", required=True, help="profile schema JSON file")
    profile_lint_parser.add_argument("--base", required=True, help="effective-base JSON file")
    profile_lint_parser.add_argument("--descriptors", required=True, help="descriptors JSON file")
    profile_lint_parser.add_argument("--registry", required=True, help="registry JSON file")
    profile_lint_parser.add_argument(
        "--phase",
        required=True,
        choices=("import", "pre-normalize", "post-normalize", "post-layout", "release"),
        help="execution stage to lint",
    )
    profile_lint_parser.add_argument(
        "--readiness-policy",
        required=True,
        choices=("draft", "accept"),
        help="readiness policy to lint under",
    )
    profile_lint_parser.add_argument(
        "--json", action="store_true", required=True, help="write one Result/1 to stdout"
    )
    profile_lint_parser.set_defaults(func=_run_profile_lint)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI (importable entry point; returns the exit code)."""
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except _OutputError as err:
        if err.message is not None:
            _err(f"bpmn-io: cannot write output: {err.message}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
