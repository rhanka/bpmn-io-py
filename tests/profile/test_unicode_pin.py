"""Pinned Unicode 15.0.0 case tables: counts, vectors, contract identity, platform ban.

Expectations come from the hash-verified UCD 15.0.0 sources via the
language-neutral ``unicode-case/1`` contract (``contracts/unicode-case/1``),
never from the implementation under test: the module must equal the contract
JSON exactly, and the contract bytes must equal the manifest hashes.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
CONTRACT_DIR = ROOT / "contracts" / "unicode-case" / "15.0.0"
PROFILE_SRC = ROOT / "src" / "bpmn_io" / "profile"


def _case_table() -> dict[str, object]:
    return json.loads((CONTRACT_DIR / "case-table.json").read_text(encoding="utf-8"))


def test_upper_table_count_and_dotted_i_identity() -> None:
    """Upper table size and single identity entry, per the spec rule."""
    from bpmn_io.profile._unicode15 import UPPER

    assert len(UPPER) == 1526
    assert UPPER[0x130] == (0x130,)
    assert [cp for cp, mapped in UPPER.items() if mapped == (cp,)] == [0x130]


def test_lower_table_has_1508_entries() -> None:
    """Lower table size from the same verified derivation."""
    from bpmn_io.profile._unicode15 import LOWER

    assert len(LOWER) == 1508


def test_sharp_s_expands_on_upper() -> None:
    """ß maps to SS on upper, stays itself on lower."""
    from bpmn_io.profile import apply_case

    assert apply_case("ß", "upper") == "SS"
    assert apply_case("ß", "lower") == "ß"


def test_dotted_i_upper_identity_and_lower_split() -> None:
    """Dotted I stays itself on upper; lower keeps the combining dot."""
    from bpmn_io.profile import apply_case

    assert apply_case("İ", "upper") == "İ"
    assert apply_case("İ", "lower") == "i̇"


def test_final_sigma_context_rule() -> None:
    """Word-final capital sigma lowers to the final form, non-final stays put."""
    from bpmn_io.profile import apply_case

    assert apply_case("ΟΣ", "lower") == "ος"
    assert apply_case("ΟΣΑ", "lower") == "οσα"  # noqa: RUF001
    assert apply_case("Σ", "lower") == "σ"  # noqa: RUF001
    assert apply_case("ς", "upper") == "Σ"
    assert apply_case("ς", "lower") == "ς"


def test_rams_horn_unchanged_proves_1500_pin() -> None:
    """U+0264 stays unchanged: 15.0.0 carries no mapping for it."""
    from bpmn_io.profile import apply_case
    from bpmn_io.profile._unicode15 import UPPER

    assert 0x264 not in UPPER
    # 16.0.0 maps this input to U+A7CB instead (witnessed on two runtimes).
    assert apply_case("ɤ", "upper") == "ɤ"
    assert apply_case("ɤ", "lower") == "ɤ"


def test_rams_horn_differs_from_newer_platform() -> None:
    """The pin is load-bearing where the platform moved on (16.0.0 maps U+A7CB)."""
    import unicodedata

    from bpmn_io.profile import apply_case

    pinned = apply_case("ɤ", "upper")
    assert pinned == "ɤ"
    platform = "ɤ".upper()
    if platform == pinned:
        pytest.skip(
            "platform unicodedata "
            + unicodedata.unidata_version
            + " agrees with the 15.0.0 pin here;"
            + " divergence witnessed on 16.0.0 (U+A7CB)"
        )
    assert platform != pinned
    if unicodedata.unidata_version == "16.0.0":
        assert platform == "Ɤ"


def test_case_version_is_pinned() -> None:
    """No platform version leaks into the case policy."""
    from bpmn_io.profile._unicode15 import UNICODE_VERSION
    from bpmn_io.profile._unicode_case import UNICODE_VERSION_PIN, case_version

    assert case_version() == "15.0.0"
    assert UNICODE_VERSION_PIN == "15.0.0"
    assert UNICODE_VERSION == "15.0.0"


def _table_mapping(entries: object) -> dict[int, tuple[int, ...]]:
    assert isinstance(entries, list)
    mapping: dict[int, tuple[int, ...]] = {}
    for entry in entries:
        assert isinstance(entry, list)
        assert len(entry) == 2
        code, mapped = entry
        assert isinstance(code, int)
        assert isinstance(mapped, list)
        assert all(isinstance(point, int) for point in mapped)
        mapping[code] = tuple(mapped)
    return mapping


def _table_ranges(entries: object) -> tuple[tuple[int, int], ...]:
    assert isinstance(entries, list)
    ranges: list[tuple[int, int]] = []
    for entry in entries:
        assert isinstance(entry, list)
        assert len(entry) == 2
        start, end = entry
        assert isinstance(start, int)
        assert isinstance(end, int)
        ranges.append((start, end))
    return tuple(ranges)


def test_module_tables_equal_contract_json_exactly() -> None:
    """The generated module carries the contract tables verbatim."""
    from bpmn_io.profile._unicode15 import (
        CASE_IGNORABLE_RANGES,
        CASED_RANGES,
        FINAL_SIGMA,
        LOWER,
        UPPER,
    )

    table = _case_table()
    assert dict(UPPER) == _table_mapping(table["upper"])
    assert dict(LOWER) == _table_mapping(table["lower"])
    assert _table_ranges(table["cased"]) == CASED_RANGES
    assert _table_ranges(table["caseIgnorable"]) == CASE_IGNORABLE_RANGES
    final = table["finalSigma"]
    assert isinstance(final, dict)
    assert final["capital"] == FINAL_SIGMA["capital"]
    assert final["lowerFinal"] == FINAL_SIGMA["lowerFinal"]
    assert final["lowerNonFinal"] == FINAL_SIGMA["lowerNonFinal"]


def test_contract_bytes_equal_manifest_hashes() -> None:
    """Manifest file hashes match the contract bytes on disk."""
    manifest = json.loads((CONTRACT_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["format"] == "unicode-case/1"
    assert manifest["unicodeVersion"] == "15.0.0"
    for name in ("case-table.json", "vectors.json"):
        digest = hashlib.sha256((CONTRACT_DIR / name).read_bytes()).hexdigest()
        assert manifest["files"][name] == digest
    sources = {entry["file"]: entry for entry in manifest["sources"]}
    assert sources["UnicodeData.txt"]["sha256"] == (
        "806e9aed65037197f1ec85e12be6e8cd870fc5608b4de0fffd990f689f376a73"
    )
    assert sources["SpecialCasing.txt"]["sha256"] == (
        "78b29c64b5840d25c11a9f31b665ee551b8a499eca6c70d770fcad7dd710f494"
    )
    assert sources["DerivedCoreProperties.txt"]["sha256"] == (
        "d367290bc0867e6b484c68370530bdd1a08b6b32404601b8c7accaf83e05628d"
    )
    assert all(entry["size"] > 0 for entry in manifest["sources"])


def test_vectors_run_against_implementation() -> None:
    """Every contract vector yields its expected upper/lower result."""
    from bpmn_io.profile import apply_case

    vectors = json.loads((CONTRACT_DIR / "vectors.json").read_text(encoding="utf-8"))
    assert vectors["unicodeVersion"] == "15.0.0"
    assert len(vectors["vectors"]) >= 10
    for vector in vectors["vectors"]:
        assert apply_case(vector["input"], "upper") == vector["upper"]
        assert apply_case(vector["input"], "lower") == vector["lower"]


def test_no_platform_case_api_in_profile_package() -> None:
    """AST guard: no unicodedata import and no upper/lower/casefold calls."""
    hits: list[str] = []
    for path in sorted(PROFILE_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any(alias.name.split(".")[0] == "unicodedata" for alias in node.names):
                    hits.append(f"{path.name}: imports unicodedata")
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[0] == "unicodedata":
                    hits.append(f"{path.name}: imports unicodedata")
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"upper", "lower", "casefold"}
            ):
                hits.append(f"{path.name}: calls .{node.func.attr}()")
    assert hits == []
