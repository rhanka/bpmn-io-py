"""Subprocess bridge to the Node oracle runner (``tests/oracle/run.mjs``)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ORACLE_DIR = Path(__file__).parent
RUNNER = ORACLE_DIR / "run.mjs"
_TIMEOUT_S = 120
#: Payloads above this size travel over stdin (``@stdin`` marker argv): a single
#: argv string is capped by the OS (Linux ``MAX_ARG_STRLEN`` = 128 KiB).
_STDIN_THRESHOLD_BYTES = 100_000


class OracleError(Exception):
    """The Node oracle runner failed or reported an error."""


def available() -> bool:
    """True when node, the oracle ``node_modules`` and the runner are all present."""
    return (
        shutil.which("node") is not None
        and (ORACLE_DIR / "node_modules").is_dir()
        and RUNNER.is_file()
    )


def _node_executable() -> str:
    """Full path to node, or raise when it is missing from PATH."""
    exe = shutil.which("node")
    if exe is None:
        msg = "oracle runner needs node on PATH"
        raise OracleError(msg)
    return exe


def run(payload: dict[str, object]) -> object:
    """Send one JSON call to the runner and return its result object.

    Raises :class:`OracleError` on transport failure, timeout or runner-reported error.
    """
    data = json.dumps(payload)
    if len(data.encode("utf-8")) > _STDIN_THRESHOLD_BYTES:
        argv: list[str] = [_node_executable(), str(RUNNER), "@stdin"]
    else:
        argv = [_node_executable(), str(RUNNER), data]
        data = None
    try:
        proc = subprocess.run(  # noqa: S603 — fixed argv ([node, runner, JSON]), no shell.
            argv,
            input=data,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
            cwd=ORACLE_DIR,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        msg = f"oracle runner timed out after {_TIMEOUT_S}s: {payload.get('op')}"
        raise OracleError(msg) from exc
    if proc.returncode != 0:
        tail = proc.stderr.strip().splitlines()[-5:]
        msg = f"oracle runner exited {proc.returncode}: {' | '.join(tail)}"
        raise OracleError(msg)
    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        msg = f"oracle runner returned invalid JSON: {exc}"
        raise OracleError(msg) from exc
    if not isinstance(envelope, dict) or not envelope.get("ok", False):
        msg = f"oracle runner error: {envelope}"
        raise OracleError(msg)
    return envelope.get("result")
