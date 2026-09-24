"""Command-line interface for bpmn-io: check, roundtrip and lay out BPMN files."""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from bpmn_io.auto_layout import LayoutError, layout_process
from bpmn_io.bpmn_moddle.simple import create_moddle
from bpmn_io.check import check
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


def build_parser() -> argparse.ArgumentParser:
    """Create the bpmn-io argument parser."""
    parser = argparse.ArgumentParser(
        prog="bpmn-io",
        description="Check, roundtrip and lay out BPMN 2.0 files.",
        epilog="exit codes: 0 success (check passes with no errors), "
        "1 finding or processing failure, 2 usage or IO error.",
    )
    sub = parser.add_subparsers(dest="command", metavar="check|roundtrip|layout", required=True)
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
