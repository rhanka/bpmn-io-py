"""F1 contract pins: code, tables and corpus agree with the implementation."""

from __future__ import annotations

import json
from pathlib import Path

from bpmn_io.codec._model import ERROR_CODES, LIMITS, RESERVED_NAMES, utf16_key
from bpmn_io.codec.xml_boundary import ENCODING_NAMES

ROOT = Path(__file__).resolve().parent.parent.parent
F1 = ROOT / "contracts" / "f1-extensions" / "1"


def _load(name: str) -> dict:
    return json.loads((F1 / name).read_text(encoding="utf-8"))


def test_reserved_names_match_implementation() -> None:
    """The frozen code set equals the contract list, in UTF-16 order."""
    contract = _load("reserved-names.json")
    assert set(contract["names"]) == set(RESERVED_NAMES)
    assert contract["names"] == sorted(contract["names"], key=lambda s: s.encode("utf-16-be"))
    union = set(contract["families"]["wire"]) | set(contract["families"]["pythonMembers"])
    union |= set(contract["families"]["jsHooks"]) | set(contract["families"]["dunders"])
    assert union == set(RESERVED_NAMES)


def test_limits_match_implementation() -> None:
    """Every contract limit value is enforced with the same number in code."""
    contract = _load("limits.json")
    assert {key: entry["value"] for key, entry in contract["limits"].items()} == LIMITS
    assert contract["limits"]["warning-cap"]["value"] == 1000


def test_encodings_match_implementation() -> None:
    """The registry names are identical in contract and code."""
    contract = _load("encodings.json")
    assert set(contract["encodings"]) == set(ENCODING_NAMES)
    assert contract["default"] == "utf-8"
    assert contract["emitted"] == "utf-8"


def test_diagnostic_enum_is_closed_and_ordered() -> None:
    """26 codes, full priority coverage, error severities match the codec."""
    contract = _load("diagnostics.json")
    codes = contract["codes"]
    assert len(codes) == 26
    assert set(contract["intraNodePriority"]) == set(codes)
    assert {code for code, spec in codes.items() if spec["severity"] == "error"} == set(ERROR_CODES)
    assert contract["warningCap"] == 1000


def test_wire_schema_validates_corpus() -> None:
    """Every sealed wire and JSON input validates against f1-wire.schema.json."""
    import jsonschema

    schema = _load("f1-wire.schema.json")
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)
    vectors = F1 / "vectors"
    checked = 0
    for path in sorted(vectors.glob("*.wire.json")):
        validator.validate(json.loads(path.read_text(encoding="utf-8")))
        checked += 1
    for name in ("prefix-gen-01", "o1-positive-01"):
        validator.validate(json.loads((vectors / f"{name}.input.json").read_text(encoding="utf-8")))
        checked += 1
    assert checked > 30


def test_canonical_expectations_hold() -> None:
    """Sealed UTF-16 canonical bytes match the implementation metric."""
    from bpmn_io.codec._model import c14n_bytes

    vectors = F1 / "vectors"
    for path in sorted(vectors.glob("*.expect.txt")):
        source = json.loads(path.with_suffix("").with_suffix(".input.json").read_text())
        assert c14n_bytes(source).decode("utf-8") == path.read_text(encoding="utf-8").rstrip("\n")


def test_miwg_hashes_match_notices() -> None:
    """The MIWG hashes in THIRD_PARTY_NOTICES.md equal the contract bytes."""
    import hashlib
    import re

    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    for name in ("B.1.0.bpmn", "C.4.0.bpmn", "C.5.0.bpmn", "LICENSE.txt"):
        digest = hashlib.sha256((F1 / "miwg" / name).read_bytes()).hexdigest()
        assert digest in notices, name
        assert re.search(r"\b" + digest + r"\b", notices) is not None


def test_f1_manifest_covers_tree() -> None:
    """The self-hosted manifest lists exactly the contract tree files."""
    lines = (F1 / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines()
    listed = sorted(line.split()[1] for line in lines if line.strip())
    on_disk = sorted(
        p.relative_to(F1).as_posix()
        for p in F1.rglob("*")
        if p.is_file() and p.name != "MANIFEST.sha256"
    )
    assert listed == on_disk


def test_f1_brand_guard() -> None:
    """No business or private name or marker in the new canonical corpus."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_contracts import _scan_text

    hits = []
    for path in sorted(F1.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_bytes().decode("utf-8", errors="ignore")
        hits.extend(f"{path.relative_to(ROOT)} {entry}" for entry in _scan_text(text))
    assert hits == []


def test_coordinates_domain_is_versioned() -> None:
    """The source-coordinate domain id and grammar stay frozen."""
    contract = _load("coordinates.json")
    assert contract["domain"] == "f1-xml-source/1"
    assert "comment" in contract["grammar"]
    assert "cdata-boundary" in contract["grammar"]


def test_order_tables_match_reference() -> None:
    """Effective-order tables keep descriptor order for the pinned types."""
    contract = _load("order.json")
    table = contract["effectiveOrder"]
    assert table["bpmn:ExtensionElements"] == ["valueRef", "values", "extensionAttributeDefinition"]
    assert table["bpmn:Definitions"][:4] == [
        "id",
        "documentation",
        "extensionDefinitions",
        "extensionElements",
    ]
    assert table["bpmn:FormalExpression"][-3:] == ["body", "language", "evaluatesToTypeRef"]
    assert len(table["bpmn:Task"]) == 24


def test_utf16_key_orders_astral_first() -> None:
    """U+10000 sorts before U+E000 in the contract key order (codes only)."""
    astral = chr(0x10000) + "k"
    bmp_private = chr(0xE000) + "k"
    assert utf16_key(astral) < utf16_key(bmp_private)
    assert sorted([bmp_private, astral, "a"], key=utf16_key) == ["a", astral, bmp_private]
