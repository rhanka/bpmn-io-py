"""Differential schema tests against Ajv 8.17.1 (finding #9).

Expectations are produced at test time by ``tests/oracle/profile_references.mjs``
(``ajv`` op, Ajv 2020 strict mode like the design validator); the Python
closed validator must agree. Needs node plus ``npm ci`` in ``tests/oracle``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ORACLE_DIR = Path(__file__).parent
ORACLE_SCRIPT = ORACLE_DIR / "profile_references.mjs"
ROOT = ORACLE_DIR.parent.parent
MECHANISM = ROOT / "contracts" / "profile-mechanism" / "1"


def _ajv(
    node_exe: str,
    schema: object,
    data: object | None,
    registry: dict[str, object] | None = None,
) -> dict[str, object]:
    """Validate ``data`` against ``schema`` through the Ajv oracle."""
    args = [node_exe, str(ORACLE_SCRIPT), "ajv"]
    with tempfile.TemporaryDirectory() as tmp:
        schema_path = Path(tmp) / "schema.json"
        schema_path.write_text(json.dumps(schema), encoding="utf-8")
        args += ["--schema", str(schema_path)]
        if data is not None:
            data_path = Path(tmp) / "data.json"
            data_path.write_text(json.dumps(data), encoding="utf-8")
            args += ["--data", str(data_path)]
        for uri, document in (registry or {}).items():
            entry_path = Path(tmp) / f"{abs(hash(uri)) % 10_000_000}.json"
            entry_path.write_text(json.dumps(document), encoding="utf-8")
            args += ["--registry", f"{uri}={entry_path}"]
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell.
            args,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=ORACLE_DIR,
            check=False,
        )
    if proc.returncode != 0:
        msg = "oracle ajv call failed"
        raise RuntimeError(msg)
    result = json.loads(proc.stdout)
    if not isinstance(result, dict):
        msg = "oracle ajv call misbehaved"
        raise TypeError(msg)
    return result


def _check_oracle() -> str:
    node_exe = shutil.which("node")
    if node_exe is None or not (ORACLE_DIR / "node_modules").is_dir():
        pytest.skip("oracle needs node and `npm ci` in tests/oracle")
    return node_exe


@pytest.mark.oracle
def test_options_with_rule_agrees_with_ajv() -> None:
    """A real rule item validates on both runtimes with the pinned registry."""
    from bpmn_io.profile import validate

    node_exe = _check_oracle()
    lint_schema = json.loads((MECHANISM / "compiled-lint-options.schema.json").read_bytes())
    profile_schema = json.loads((MECHANISM / "profile-mechanism-1.schema.json").read_bytes())
    profile = json.loads((MECHANISM / "neutral-profile.json").read_bytes())
    assert isinstance(profile, dict)
    rules = profile["rules"]
    value = {
        "mechanismVersion": "1",
        "profileDigest": "0" * 64,
        "phase": "post-normalize",
        "readinessPolicy": "accept",
        "compiledRules": rules,
        "bindings": [],
        "severityPolicyDigest": "1" * 64,
    }
    registry = {"urn:profile-mechanism:1:profile": profile_schema}
    assert validate(lint_schema, value, registry) is True
    wanted = _ajv(node_exe, lint_schema, value, registry)
    assert wanted["ok"] is True


@pytest.mark.oracle
def test_external_nested_ref_agrees_with_ajv() -> None:
    """Nested local refs re-anchor identically on both runtimes."""
    from bpmn_io.profile import validate

    node_exe = _check_oracle()
    external = {
        "$id": "urn:review:extern/1",
        "$defs": {"thing": {"type": "string"}},
        "type": "object",
        "properties": {"a": {"$ref": "#/$defs/thing"}},
    }
    schema = {"$ref": "urn:review:extern/1#/properties/a"}
    registry = {"urn:review:extern/1": external}
    assert validate(schema, "hello", registry) is True
    assert validate(schema, 42, registry) is False
    wanted_ok = _ajv(node_exe, schema, "hello", registry)
    assert wanted_ok["ok"] is True
    wanted_bad = _ajv(node_exe, schema, 42, registry)
    assert wanted_bad["ok"] is False
