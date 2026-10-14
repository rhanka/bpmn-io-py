"""Command-line interface for bpmn-io: check, roundtrip, lay out and lint BPMN files."""

from __future__ import annotations

import argparse
import contextlib
import glob as glob_module
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from bpmn_io.bpmn_moddle import BpmnModdle
    from bpmn_io.lint.linter import Resolver
    from bpmn_io.moddle.base import ModdleElement

from bpmn_io._js import UNDEFINED
from bpmn_io._moddle_utils import path_stringify
from bpmn_io.auto_layout import LayoutError, layout_process
from bpmn_io.bpmn_moddle.simple import create_moddle
from bpmn_io.check import check
from bpmn_io.lint import Linter
from bpmn_io.lint.resolver import NodeResolver
from bpmn_io.moddle_xml.read import ParseError

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


def build_parser() -> argparse.ArgumentParser:
    """Create the bpmn-io argument parser."""
    parser = argparse.ArgumentParser(
        prog="bpmn-io",
        description="Check, roundtrip, lay out and lint BPMN 2.0 files.",
        epilog="exit codes: 0 success (check passes with no errors), "
        "1 finding or processing failure, 2 usage or IO error.",
    )
    sub = parser.add_subparsers(
        dest="command", metavar="check|roundtrip|layout|lint", required=True
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
