"""Lot 21: parity-corpus expectations checked against independent references.

Every schema/JCS/identity expectation authored from the DESIGN text is
verified here against Ajv 2020 (strict, design validator options), an RFC 8785
reference canonicalizer, Node ``crypto`` / Python ``hashlib`` digests, and
``jsonschema`` 4.26 as a second schema reference (with a ``fullmatch`` pattern
override; its stock ``re.search`` divergence is a documented expected
difference, asserted, never hidden). Any disagreement with the authored
expectation fails. Lint-adapter cases are expectations only (``lot-1-lint``):
shape-checked here, executed in lot 1.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, validators
from jsonschema.exceptions import ValidationError

from tests.contracts.test_contracts import _jcs

ROOT = Path(__file__).resolve().parent.parent.parent
CORPUS = ROOT / "contracts" / "profile-parity-corpus" / "1"
MANIFEST = CORPUS / "manifest.json"
REFERENCES = ROOT / "tests" / "oracle" / "profile_references.mjs"
C14N = ROOT / "tests" / "oracle" / "profile_c14n.mjs"
LOCK = json.loads((ROOT / "CONTRACTS.lock").read_text(encoding="utf-8"))

Json = dict[str, "Json"] | list["Json"] | str | int | float | bool | None

CASE_KEYS = frozenset(
    {
        "caseId",
        "operation",
        "phase",
        "profileArtifact",
        "inputArtifacts",
        "commandArtifact",
        "expectedArtifacts",
        "expectedStatus",
        "comparatorIds",
    }
)
OPERATIONS = frozenset({"loadProfile", "profile-c14n/2", "stable-id/1", "validate"})


def _node() -> str:
    exe = shutil.which("node")
    if exe is None or not REFERENCES.is_file():
        pytest.skip("corpus references need node and tests/oracle/profile_references.mjs")
    return exe


def _reference(op: str, *argv: str) -> Json:
    proc = subprocess.run(  # noqa: S603 — fixed argv ([node, probe, op, files]), no shell.
        [_node(), str(REFERENCES), op, *argv],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        pytest.fail(f"reference probe failed: {proc.stderr.strip()}")
    envelope = json.loads(proc.stdout)
    assert isinstance(envelope, dict)
    return envelope


def _node_digest(value: Json) -> str:
    exe = shutil.which("node")
    if exe is None or not C14N.is_file():
        pytest.skip("stable-id reference needs node and tests/oracle/profile_c14n.mjs")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        json.dump(value, tmp)
        tmp_path = tmp.name
    proc = subprocess.run(  # noqa: S603 — fixed argv ([node, canonicalizer, file]), no shell.
        [exe, str(C14N), tmp_path],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    Path(tmp_path).unlink()
    if proc.returncode != 0:
        pytest.fail(f"node canonicalizer failed: {proc.stderr.strip()}")
    return proc.stdout.split()[0]


def _fullmatch_validator() -> type[Draft202012Validator]:
    def fullmatch_pattern(
        validator: Draft202012Validator, pattern: str, instance: object, _schema: Json
    ) -> object:
        if not validator.is_type(instance, "string"):
            return
        body = pattern[1:-1] if pattern.startswith("^") and pattern.endswith("$") else pattern
        if re.fullmatch(body, str(instance)) is None:
            yield ValidationError(f"{instance!r} does not fullmatch {pattern!r}")
        return

    return validators.extend(Draft202012Validator, {"pattern": fullmatch_pattern})


def _cases() -> list[tuple[str, Json]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return [
        (rel, json.loads((ROOT / "contracts" / rel).read_text(encoding="utf-8")))
        for rel in sorted(manifest["files"])
    ]


def _artifact_path(entry: Json) -> Path:
    assert isinstance(entry, dict)
    assert "path" in entry
    assert "sha256" in entry
    path = ROOT / "contracts" / str(entry["path"])
    assert path.is_file(), f"missing referenced artifact {entry['path']}"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == entry["sha256"], f"stale pin for {entry['path']}"
    return path


def _by_role(entries: list[Json], role: str) -> Json:
    matches = [e for e in entries if isinstance(e, dict) and e.get("role") == role]
    assert len(matches) == 1, f"expected exactly one {role!r} artifact"
    return matches[0]


def test_manifest_covers_every_corpus_file() -> None:
    """The manifest lists every corpus file (but itself) with a matching hash."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["format"] == "profile-parity-corpus/1"
    assert manifest["sourceRepository"] == "rhanka/bpmn-io-py"
    assert manifest["sourceTag"].startswith("profile-corpus-v")
    on_disk = {
        p.relative_to(ROOT / "contracts").as_posix()
        for p in CORPUS.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    }
    assert set(manifest["files"]) == on_disk, "manifest must list every corpus file, nothing else"
    comparator_ids = {c["id"] for c in manifest["comparators"]}
    assert "lot-1-lint" in comparator_ids
    for rel, digest in manifest["files"].items():
        path = ROOT / "contracts" / rel
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, f"hash drift: {rel}"
        case = json.loads(path.read_text(encoding="utf-8"))
        assert set(case) <= CASE_KEYS, f"unexpected keys in {rel}"
        assert set(case) >= CASE_KEYS - {"commandArtifact"}, f"missing keys in {rel}"
        assert case["operation"] in OPERATIONS, f"unknown operation in {rel}"
        status = case["expectedStatus"]
        assert status == "ok" or (
            status.startswith("refused:") and len(status) > len("refused:")
        ), f"bad status in {rel}"
        assert set(case["comparatorIds"]) <= comparator_ids, f"unknown comparator in {rel}"


def _ajv(tmp: Path, schema: Json, data: Json | None, registry: list[Json]) -> Json:
    schema_file = tmp / "schema.json"
    schema_file.write_text(json.dumps(schema), encoding="utf-8")
    argv = ["--schema", str(schema_file)]
    for entry in registry:
        reg_file = tmp / f"registry-{len(argv)}.json"
        reg_file.write_text(_artifact_path(entry).read_text(encoding="utf-8"), encoding="utf-8")
        argv += ["--registry", f"{entry['path']}={reg_file}"]
    if data is not None:
        data_file = tmp / "data.json"
        data_file.write_text(json.dumps(data), encoding="utf-8")
        argv += ["--data", str(data_file)]
    return _reference("ajv", *argv)


CLOSED_29 = (
    "$schema",
    "$id",
    "$comment",
    "title",
    "$defs",
    "$ref",
    "type",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "minItems",
    "maxItems",
    "uniqueItems",
    "minLength",
    "pattern",
    "enum",
    "const",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "allOf",
    "anyOf",
    "oneOf",
    "not",
    "if",
    "then",
    "else",
)


def _roles(inputs: list[Json]) -> set[str]:
    return {str(e["role"]) for e in inputs if isinstance(e, dict) and "role" in e}


def _check_mutation_case(tmp: Path, rel: str, case: dict[str, Json]) -> None:
    """Full-profile Ajv check with the authored mutation applied."""
    inputs = case["inputArtifacts"]
    assert isinstance(inputs, list)
    mutation = _by_role(inputs, "mutation")
    assert isinstance(mutation, dict)
    spec = mutation["json"]
    assert isinstance(spec, dict)
    profile = json.loads(_artifact_path(case["profileArtifact"]).read_text())
    pointer = str(spec["pointer"]).split("/")[1:]
    target = profile
    for part in pointer[:-1]:
        target = target[int(part) if part.isdigit() else part]
    target[pointer[-1]] = spec["value"]
    schema = json.loads(
        _artifact_path(
            {
                "path": "profile-mechanism/1/profile-mechanism-1.schema.json",
                "sha256": LOCK["files"][
                    "contracts/profile-mechanism/1/profile-mechanism-1.schema.json"
                ],
            }
        ).read_text()
    )
    result = _ajv(tmp, schema, profile, [])
    assert isinstance(result, dict)
    if case["expectedStatus"] == "ok":
        assert result["ok"] is True, f"{rel}: Ajv disagrees (refuses)"
    else:
        assert result["ok"] is False, f"{rel}: Ajv disagrees (accepts)"


def _check_second_references(
    frag_schema: Json, data: Json, authored: dict[str, Json], rel: str
) -> None:
    """jsonschema second reference agrees; stock divergences stay documented."""
    fullmatch_cls = _fullmatch_validator()
    if "pythonJsonschemaFullmatch" in authored:
        expected_second = authored["pythonJsonschemaFullmatch"]
        assert isinstance(expected_second, dict)
        second_ok = fullmatch_cls(frag_schema).is_valid(data)
        assert second_ok is expected_second["ok"], f"{rel}: fullmatch second reference disagrees"
    if "pythonJsonschemaStock" in authored:
        expected_stock = authored["pythonJsonschemaStock"]
        assert isinstance(expected_stock, dict)
        stock_ok = Draft202012Validator(frag_schema).is_valid(data)
        assert stock_ok is expected_stock["ok"], f"{rel}: stock divergence record is wrong"
        assert "documentedDivergence" in expected_stock


def _check_fragment_case(tmp: Path, rel: str, case: dict[str, Json]) -> None:
    """Fragment Ajv check plus second references."""
    inputs = case["inputArtifacts"]
    assert isinstance(inputs, list)
    verdict = _by_role(case["expectedArtifacts"], "verdict")
    assert isinstance(verdict, dict)
    authored = verdict["json"]
    assert isinstance(authored, dict)
    frag_schema = _by_role(inputs, "fragmentSchema")
    assert isinstance(frag_schema, dict)
    data = _by_role(inputs, "fragmentData")["json"]
    frag_result = _ajv(tmp, frag_schema["json"], data, [])
    assert isinstance(frag_result, dict)
    if "error" in frag_result:
        expected_load_error = authored.get("ajvStrict", {}).get("loadError")
        assert expected_load_error is not None, f"{rel}: unexpected Ajv load error"
        assert expected_load_error in str(frag_result["error"]), rel
    elif case["expectedStatus"] == "ok":
        assert frag_result["ok"] is True, f"{rel}: Ajv fragment disagrees"
    else:
        assert frag_result["ok"] is False, f"{rel}: Ajv fragment disagrees"
    _check_second_references(frag_schema["json"], data, authored, rel)


def _check_registry_cases(tmp: Path, rel: str, case: dict[str, Json]) -> None:
    """Pinned vs unknown external $ref behavior."""
    inputs = case["inputArtifacts"]
    assert isinstance(inputs, list)
    schema = json.loads(_artifact_path(_by_role(inputs, "schema")).read_text())
    if case["caseId"] == "schema-external-ref-pinned":
        registry = [_by_role(inputs, "registry")]
        data = _by_role(inputs, "fragmentData")
        assert isinstance(data, dict)
        result = _ajv(tmp, schema, data["json"], registry)
        assert result.get("ok") is True, f"{rel}: pinned external ref must compile"
    if case["caseId"] == "schema-external-ref-unknown":
        result = _ajv(tmp, schema, None, [])
        assert result.get("ok") is False, f"{rel}: unknown ref must fail load"
        assert "can't resolve reference" in str(result.get("error", "")), rel
    if case["caseId"] == "schema-keyword-subset":
        assert len(CLOSED_29) == 29
        assert "format" not in CLOSED_29, "subset audit constant drifted"


@pytest.mark.oracle
def test_schema_group_matches_references() -> None:
    """Ajv + jsonschema agree with every authored schema expectation."""
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        for rel, case in _cases():
            assert isinstance(case, dict)
            if not str(case["caseId"]).startswith("schema-"):
                continue
            inputs = case["inputArtifacts"]
            assert isinstance(inputs, list)
            roles = _roles(inputs)
            if "mutation" in roles:
                _check_mutation_case(tmp, rel, case)
            if "fragmentSchema" in roles:
                _check_fragment_case(tmp, rel, case)
            if "schema" in roles:
                _check_registry_cases(tmp, rel, case)


@pytest.mark.oracle
def test_lexical_group_matches_reference() -> None:
    """The DESIGN 2.1 probe returns every authored lexical status."""
    for rel, case in _cases():
        assert isinstance(case, dict)
        if not str(case["caseId"]).startswith("lexical-"):
            continue
        document = _by_role(case["inputArtifacts"], "document")
        assert isinstance(document, dict)
        result = _reference("lexical", "--hex", str(document["hex"]))
        assert isinstance(result, dict)
        verdict = _by_role(case["expectedArtifacts"], "verdict")
        assert isinstance(verdict, dict)
        assert result == verdict["json"], f"{rel}: lexical probe disagrees"
        assert (
            "refused:" + str(result.get("code", "")) == case["expectedStatus"]
            if result.get("status") == "refused"
            else case["expectedStatus"] == "ok"
        ), f"{rel}: status mismatch"


@pytest.mark.oracle
def test_jcs_group_matches_reference() -> None:
    """The RFC 8785 reference renders every authored canonical byte string."""
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        for rel, case in _cases():
            assert isinstance(case, dict)
            if not str(case["caseId"]).startswith("jcs-"):
                continue
            inputs = case["inputArtifacts"]
            assert isinstance(inputs, list)
            expected = case["expectedArtifacts"]
            assert isinstance(expected, list)
            assert len(inputs) == len(expected), f"{rel}: input/expected arity"
            for input_entry, expected_entry in zip(inputs, expected, strict=True):
                assert isinstance(input_entry, dict)
                assert isinstance(expected_entry, dict)
                data_file = tmp / "values.json"
                data_file.write_text(
                    json.dumps(input_entry["json"], ensure_ascii=False), encoding="utf-8"
                )
                result = _reference("canonicalize", "--data", str(data_file))
                assert isinstance(result, dict)
                assert result.get("ok") is True, rel
                assert result["bytes"] == expected_entry["text"], f"{rel}: canonical bytes disagree"
            assert case["expectedStatus"] == "ok"


@pytest.mark.oracle
def test_identity_group_matches_references() -> None:
    """Node crypto and Python hashlib agree with every authored stable id."""
    for rel, case in _cases():
        assert isinstance(case, dict)
        if not str(case["caseId"]).startswith("identity-"):
            continue
        allocations = _by_role(case["inputArtifacts"], "allocations")
        assert isinstance(allocations, dict)
        expected_ids = _by_role(case["expectedArtifacts"], "ids")
        assert isinstance(expected_ids, dict)
        wanted = expected_ids["json"]
        assert isinstance(wanted, list)
        entries = allocations["json"]
        assert isinstance(entries, list)
        assert len(entries) == len(wanted)
        for entry, want in zip(entries, wanted, strict=True):
            assert isinstance(entry, dict)
            preimage = ["profile-mechanism/1", entry["owner"], entry["slot"], entry["key"]]
            node_digest = _node_digest(preimage)
            python_digest = hashlib.sha256(_jcs(preimage).encode("utf-8")).hexdigest()
            assert node_digest == python_digest, f"{rel}: runtimes disagree"
            assert f"g_{node_digest}" == want, f"{rel}: golden id mismatch"
        assert case["expectedStatus"] == "ok"


def test_lint_adapter_group_is_shape_only() -> None:
    """Lint cases carry exact keys and valid deferred expectations (run in lot 1)."""
    for rel, case in _cases():
        assert isinstance(case, dict)
        if not str(case["caseId"]).startswith("lint-"):
            continue
        assert "lot-1-lint" in case["comparatorIds"], f"{rel}: lint cases defer"
        assert case["operation"] == "validate"
        assert case["profileArtifact"] is not None
        _artifact_path(case["profileArtifact"])
        status = case["expectedStatus"]
        assert status == "ok" or status.startswith("refused:"), rel
