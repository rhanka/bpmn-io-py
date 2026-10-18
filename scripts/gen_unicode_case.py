#!/usr/bin/env python3
"""Generate the pinned Unicode 15.0.0 case tables (language-neutral contract).

Usage:
  scripts/gen_unicode_case.py --ucd-dir <dir> --oracle-vectors <json>
      [--contracts-dir <dir>] [--module <path>]
  scripts/gen_unicode_case.py --check --ucd-dir <dir> --oracle-vectors <json>
      [--contracts-dir <dir>] [--module <path>]

The ``--oracle-vectors`` JSON comes from ``tests/oracle/unicode_case_oracle.py``
run under a Unicode 15.0.0 interpreter; expected vectors are never derived
from the tables built here.

Reads the three Unicode Character Database 15.0.0 sources (read-only, never
vendored) from ``--ucd-dir`` after verifying their sizes and SHA-256 digests
against the pins in ``CONTRACTS.toml`` (``[unicode-case.sources]``), then
derives the full default case mappings exactly per the ``spec``
``Unicode case policy`` generation rule: start from the simple uppercase /
lowercase mappings in ``UnicodeData.txt``, apply the unconditional
``SpecialCasing.txt`` entries, exclude the 15 language-tagged conditional
entries, and keep the single untagged context rule Final_Sigma (lower path
only; it carries no uppercase entry). The ``Cased`` / ``Case_Ignorable`` sets
come from ``DerivedCoreProperties.txt``.

Primary output is the language-neutral contract ``contracts/unicode-case/1``:
``case-table.json`` (upper/lower full mappings as code-point arrays, the two
sets as sorted ``[start, end]`` ranges, the Final_Sigma rule descriptor;
compact JSON with UTF-16 key order), ``vectors.json`` (fixed input vectors
with expected upper/lower results), and ``manifest.json`` (format, version,
source names/sizes/hashes, file hashes). ``src/bpmn_io/profile/_unicode15.py``
is generated FROM ``case-table.json`` because the wheel does not ship
``contracts/``. ``--check`` re-derives everything from the hash-verified
sources passed by path and compares it with the committed bytes; it writes
nothing. stdlib only, deterministic.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import NamedTuple, NoReturn

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 fallback (repo requires >=3.11).
    import tomli as tomllib  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parent.parent
PINS = ROOT / "CONTRACTS.toml"

CAPITAL_SIGMA = 0x03A3
SMALL_SIGMA = 0x03C3
FINAL_SIGMA = 0x03C2


class CaseTables(NamedTuple):
    """Derived case data: full mappings plus the Final_Sigma property sets."""

    upper: dict[int, tuple[int, ...]]
    lower: dict[int, tuple[int, ...]]
    cased: list[tuple[int, int]]
    ignorable: list[tuple[int, int]]


def _fail(msg: str) -> NoReturn:
    """Abort generation on an internal invariant breach (never assert)."""
    text = f"gen_unicode_case: {msg}"
    raise SystemExit(text)


def _as_list(value: object, what: str) -> list[object]:
    """Narrow a contract value to a list or abort."""
    if not isinstance(value, list):
        _fail(f"case table {what} is not a list")
    return value


def _as_dict(value: object, what: str) -> dict[object, object]:
    """Narrow a contract value to a dict or abort."""
    if not isinstance(value, dict):
        _fail(f"case table {what} is not an object")
    return value


#: Inputs whose expected upper/lower results ship in ``vectors.json``.
VECTOR_INPUTS = (
    "\u00df",  # ß LATIN SMALL LETTER SHARP S
    "\u0130",  # İ LATIN CAPITAL LETTER I WITH DOT ABOVE
    "\u039f\u03a3",  # ΟΣ word-final sigma
    "\u039f\u03a3\u0391",  # ΟΣΑ non-final sigma
    "\u03a3",  # lone capital sigma (no cased before)
    "\u0264",  # ɤ unchanged in 15.0.0 (mapped only from 16.0.0)
    "Task",
    "SS",
    "\ufb06",  # ﬆ ligature
    "\u03c2",  # already-final sigma
)


def sha256(data: bytes) -> str:
    """Return the lowercase hex SHA-256 of ``data``."""
    return hashlib.sha256(data).hexdigest()


def utf16_key(key: str) -> bytes:
    """Sort key for profile-c14n/2 style UTF-16 code-unit ordering."""
    return key.encode("utf-16-be")


def dumps_c14n(value: object) -> str:
    """Render compact JSON with UTF-16 key order (ASCII-only, deterministic)."""
    if isinstance(value, dict):
        items = sorted(value.items(), key=lambda kv: utf16_key(str(kv[0])))
        return "{" + ",".join(dumps_c14n(k) + ":" + dumps_c14n(v) for k, v in items) + "}"
    if isinstance(value, list):
        return "[" + ",".join(dumps_c14n(v) for v in value) + "]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return json.dumps(value, ensure_ascii=True)


def load_section() -> dict[str, object]:
    """Return the ``[unicode-case]`` pins from ``CONTRACTS.toml``."""
    pins = tomllib.loads(PINS.read_text(encoding="utf-8"))
    section = pins.get("unicode-case")
    if not isinstance(section, dict):
        msg = "CONTRACTS.toml: missing [unicode-case] section"
        raise SystemExit(msg)
    return section


def read_sources(ucd_dir: Path, section: dict[str, object]) -> dict[str, bytes]:
    """Read the UCD sources after verifying size and hash against the pins."""
    raw_sources = section.get("sources")
    if not isinstance(raw_sources, dict) or not raw_sources:
        msg = "CONTRACTS.toml: [unicode-case.sources] must be a non-empty table"
        raise SystemExit(msg)
    sources: dict[str, bytes] = {}
    for name in sorted(raw_sources):
        spec = raw_sources[name]
        if not isinstance(spec, dict):
            msg = f"CONTRACTS.toml: source {name!r} needs a size/sha256 pin"
            raise SystemExit(msg)
        data = (ucd_dir / name).read_bytes()
        problems: list[str] = []
        if len(data) != spec.get("size"):
            problems.append(f"size {len(data)} != pinned {spec.get('size')}")
        if sha256(data) != spec.get("sha256"):
            problems.append("sha256 mismatch")
        if problems:
            msg = f"UCD source {name}: " + "; ".join(problems)
            raise SystemExit(msg)
        sources[name] = data
    return sources


def parse_unicode_data(data: bytes) -> tuple[dict[int, int], dict[int, int]]:
    """Return (simple_upper, simple_lower) single-code-point mappings."""
    upper: dict[int, int] = {}
    lower: dict[int, int] = {}
    for raw in data.decode("utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        fields = line.split(";")
        code = int(fields[0], 16)
        if len(fields) > 12 and fields[12].strip():
            upper[code] = int(fields[12].strip(), 16)
        if len(fields) > 13 and fields[13].strip():
            lower[code] = int(fields[13].strip(), 16)
    return upper, lower


def parse_special(data: bytes) -> tuple[dict[int, list[int]], dict[int, list[int]]]:
    """Return unconditional (upper, lower) full mappings; keep Final_Sigma out.

    The 15 language-tagged conditional entries are excluded per the spec rule.
    The single untagged context rule Final_Sigma is validated and left to the
    runtime context check (it carries no uppercase entry); its lower value is
    already the simple mapping, so the plain lower table needs no entry.
    """
    upper: dict[int, list[int]] = {}
    lower: dict[int, list[int]] = {}
    for raw in data.decode("utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = [field.strip() for field in line.split(";")]
        if len(fields) == 6:
            condition = fields[4]
            if any(tag in condition.split() for tag in ("tr", "az", "lt")):
                continue
            if condition != "Final_Sigma":
                msg = f"unexpected kept SpecialCasing condition: {line!r}"
                raise SystemExit(msg)
            if [int(x, 16) for x in fields[1].split()] != [FINAL_SIGMA]:
                msg = f"unexpected Final_Sigma lower mapping: {line!r}"
                raise SystemExit(msg)
            if [int(x, 16) for x in fields[3].split()] != [CAPITAL_SIGMA]:
                msg = f"unexpected Final_Sigma upper mapping: {line!r}"
                raise SystemExit(msg)
            continue
        code = int(fields[0], 16)
        upper[code] = [int(x, 16) for x in fields[3].split()]
        lower[code] = [int(x, 16) for x in fields[1].split()]
    return upper, lower


def parse_derived(data: bytes, wanted: str) -> list[tuple[int, int]]:
    """Return the sorted, merged ``[start, end]`` ranges of one property."""
    ranges: list[tuple[int, int]] = []
    for raw in data.decode("utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        span, _, prop = (part.strip() for part in line.partition(";"))
        if prop != wanted:
            continue
        if ".." in span:
            first, _, last = span.partition("..")
            ranges.append((int(first, 16), int(last, 16)))
        else:
            code = int(span, 16)
            ranges.append((code, code))
    merged: list[list[int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def load_oracle_vectors(path: Path) -> list[dict[str, object]]:
    """Load expected vectors from the independent interpreter oracle output.

    The oracle JSON must be produced by ``tests/oracle/unicode_case_oracle.py``
    under a Unicode 15.0.0 interpreter (``uv run --no-project --python 3.12``);
    its ``upper``/``lower`` results come from that interpreter's own case
    mapping, never from the tables derived here.
    """
    try:
        document = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        _fail(f"oracle vectors at {path} did not parse: {exc}")
    if not isinstance(document, dict):
        _fail(f"oracle vectors at {path} is not an object")
    if document.get("unicodeVersion") != "15.0.0":
        _fail(f"oracle vectors at {path} are not Unicode 15.0.0")
    raw_vectors = document.get("vectors")
    if not isinstance(raw_vectors, list):
        _fail(f"oracle vectors at {path} carry no vector list")
    vectors: list[dict[str, object]] = []
    for entry in raw_vectors:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("input"), str)
            or not isinstance(entry.get("upper"), str)
            or not isinstance(entry.get("lower"), str)
        ):
            _fail(f"oracle vectors at {path} carry a malformed entry")
        vectors.append({"input": entry["input"], "upper": entry["upper"], "lower": entry["lower"]})
    if [entry["input"] for entry in vectors] != list(VECTOR_INPUTS):
        _fail(f"oracle vectors at {path} do not cover exactly VECTOR_INPUTS")
    return vectors


def derive(sources: dict[str, bytes], oracle_vectors: list[dict[str, object]]) -> dict[str, object]:
    """Derive tables, sets and the rule descriptor from verified sources.

    Expected vectors are not derived here: they come from the independent
    interpreter oracle (see ``load_oracle_vectors``) so the sealed
    expectations never mirror the runtime tables.
    """
    simple_upper, simple_lower = parse_unicode_data(sources["UnicodeData.txt"])
    special_upper, special_lower = parse_special(sources["SpecialCasing.txt"])
    upper: dict[int, tuple[int, ...]] = {cp: (m,) for cp, m in simple_upper.items()}
    upper.update({cp: tuple(m) for cp, m in special_upper.items()})
    lower: dict[int, tuple[int, ...]] = {cp: (m,) for cp, m in simple_lower.items()}
    lower.update({cp: tuple(m) for cp, m in special_lower.items()})
    derived = sources["DerivedCoreProperties.txt"]
    tables = CaseTables(
        upper=upper,
        lower=lower,
        cased=parse_derived(derived, "Cased"),
        ignorable=parse_derived(derived, "Case_Ignorable"),
    )
    table = {
        "caseIgnorable": [[s, e] for s, e in tables.ignorable],
        "cased": [[s, e] for s, e in tables.cased],
        "finalSigma": {
            "capital": CAPITAL_SIGMA,
            "lowerFinal": FINAL_SIGMA,
            "lowerNonFinal": SMALL_SIGMA,
            "requiresCasedBefore": True,
            "requiresNoCasedAfter": True,
            "rule": "Final_Sigma",
            "skipProperties": ["Case_Ignorable"],
        },
        "lower": [[cp, list(m)] for cp, m in sorted(tables.lower.items())],
        "upper": [[cp, list(m)] for cp, m in sorted(tables.upper.items())],
    }
    return {"table": table, "vectors": oracle_vectors}


def _mapping_block(label: str, key: str, entries: list[object]) -> list[str]:
    """Render one UPPER/LOWER table block for the generated module."""
    mode = "upper" if key == "upper" else "lower"
    header = f"{label}: Final[MappingProxyType[int, tuple[int, ...]]] = MappingProxyType("
    block = [f"#: Pinned full {mode}case mapping table.", header, "    {"]
    for raw_entry in entries:
        if not isinstance(raw_entry, list) or len(raw_entry) != 2:
            _fail(f"case table {key} entry is not a [code, mapping] pair")
        code, mapped = raw_entry
        if not isinstance(code, int) or not isinstance(mapped, list):
            _fail(f"case table {key} entry has a non-integer code or mapping")
        if not mapped or not all(isinstance(m, int) for m in mapped):
            _fail(f"case table {key} entry 0x{code:X} has an empty mapping")
        inner = ", ".join(f"0x{m:X}" for m in mapped)
        trailer = "," if len(mapped) == 1 else ""
        block.append(f"        0x{code:X}: ({inner}{trailer}),")
    block.extend(("    }", ")", ""))
    return block


def _ranges_block(title: str, const: str, pairs: list[tuple[int, int]]) -> list[str]:
    """Render one sorted range-tuple block for the generated module."""
    block = [title, f"{const}: Final[tuple[tuple[int, int], ...]] = ("]
    block.extend(_range_line(start, end) for start, end in pairs)
    block.extend((")", ""))
    return block


def _final_sigma_block(final: dict[object, object]) -> list[str]:
    """Render the Final_Sigma descriptor block for the generated module."""
    block = [
        "#: Final_Sigma context rule descriptor (lower path only).",
        "FINAL_SIGMA: Final[MappingProxyType[str, object]] = MappingProxyType(",
        "    {",
    ]
    for key in ("capital", "lowerFinal", "lowerNonFinal"):
        point = final.get(key)
        if not isinstance(point, int):
            _fail(f"case table finalSigma {key} is not a code point")
        block.append(f'        "{key}": 0x{point:X},')
    block.extend(
        (
            '        "requiresCasedBefore": True,',
            '        "requiresNoCasedAfter": True,',
            '        "rule": "Final_Sigma",',
            '        "skipProperties": ("Case_Ignorable",),',
            "    }",
            ")",
        )
    )
    return block


def render_module(table: dict[str, object], sources: dict[str, bytes]) -> str:
    """Render ``_unicode15.py`` from the case table (deterministic text)."""
    lines = [
        '"""Pinned Unicode 15.0.0 full default case data (generated, do not edit).',
        "",
        "Generated from ``contracts/unicode-case/15.0.0/case-table.json`` by",
        "``scripts/gen_unicode_case.py``. Sources (Unicode Character Database",
        "15.0.0, read-only, never vendored):",
    ]
    for name in sorted(sources):
        lines.append(f"- {name} ({len(sources[name])} bytes,")
        lines.append(f"  SHA-256 {sha256(sources[name])}")
    upper = _as_list(table["upper"], "upper")
    lower = _as_list(table["lower"], "lower")
    lines.extend(
        [
            "",
            f"Upper table: {len(upper)} entries; lower table: {len(lower)} entries.",
            "The 15 language-tagged SpecialCasing entries are excluded; the",
            "untagged Final_Sigma context rule applies on the lower path.",
            '"""',
            "",
            "from __future__ import annotations",
            "",
            "from types import MappingProxyType",
            "from typing import Final",
            "",
            "__all__ = [",
            '    "CASED_RANGES",',
            '    "CASE_IGNORABLE_RANGES",',
            '    "FINAL_SIGMA",',
            '    "LOWER",',
            '    "SOURCE_HASHES",',
            '    "UNICODE_VERSION",',
            '    "UPPER",',
            "]",
            "",
            "#: Pinned Unicode version for the ``case`` operator.",
            'UNICODE_VERSION: Final[str] = "15.0.0"',
            "",
            "#: SHA-256 of the UCD 15.0.0 sources this module was generated from.",
            "SOURCE_HASHES: Final[MappingProxyType[str, str]] = MappingProxyType(",
            "    {",
        ]
    )
    # Hash literals are unwrappable: overlong lines carry a targeted noqa.
    for name in sorted(sources):
        entry = f'        "{name}": "{sha256(sources[name])}",'
        if len(entry) > 100:
            entry += "  # noqa: E501"
        lines.append(entry)
    lines.append("    }")
    lines.append(")")
    lines.append("")
    for label, key in (("UPPER", "upper"), ("LOWER", "lower")):
        lines.extend(_mapping_block(label, key, _as_list(table[key], key)))
    lines.extend(
        _ranges_block(
            "#: Sorted merged Cased ranges ([start, end], inclusive).",
            "CASED_RANGES",
            _as_pairs(_as_list(table["cased"], "cased"), "cased"),
        )
    )
    lines.extend(
        _ranges_block(
            "#: Sorted merged Case_Ignorable ranges ([start, end], inclusive).",
            "CASE_IGNORABLE_RANGES",
            _as_pairs(_as_list(table["caseIgnorable"], "caseIgnorable"), "ignorable"),
        )
    )
    lines.extend(_final_sigma_block(_as_dict(table["finalSigma"], "finalSigma")))
    return "\n".join(lines) + "\n"


def _as_pairs(entries: list[object], what: str) -> list[tuple[int, int]]:
    """Narrow range entries to integer pairs or abort."""
    pairs: list[tuple[int, int]] = []
    for raw in entries:
        if not isinstance(raw, list) or len(raw) != 2:
            _fail(f"case table {what} entry is not a [start, end] pair")
        start, end = raw
        if not isinstance(start, int) or not isinstance(end, int):
            _fail(f"case table {what} entry bounds are not integers")
        pairs.append((start, end))
    return pairs


def _range_line(start: int, end: int) -> str:
    """Render one range tuple line for the generated module."""
    return f"    (0x{start:X}, 0x{end:X}),"


def build_contract(
    section: dict[str, object], derived: dict[str, object], sources: dict[str, bytes]
) -> dict[str, bytes]:
    """Render the three contract files (deterministic bytes, no trailing newline)."""
    table = _as_dict(derived["table"], "table")
    vectors = _as_list(derived["vectors"], "vectors")
    case_bytes = dumps_c14n(table).encode("utf-8")
    vectors_doc = {"unicodeVersion": "15.0.0", "vectors": vectors}
    vectors_bytes = dumps_c14n(vectors_doc).encode("utf-8")
    raw_sources = section.get("sources")
    if not isinstance(raw_sources, dict):
        _fail("CONTRACTS.toml [unicode-case.sources] must be a table")
    manifest_doc = {
        "files": {
            "case-table.json": sha256(case_bytes),
            "vectors.json": sha256(vectors_bytes),
        },
        "format": "unicode-case/1",
        "sources": [
            {
                "file": name,
                "sha256": sha256(sources[name]),
                "size": len(sources[name]),
            }
            for name in sorted(sources)
        ],
        "unicodeVersion": "15.0.0",
    }
    manifest_bytes = dumps_c14n(manifest_doc).encode("utf-8")
    return {
        "case-table.json": case_bytes,
        "manifest.json": manifest_bytes,
        "vectors.json": vectors_bytes,
    }


def check(contracts_dir: Path, module_path: Path, files: dict[str, bytes], module_text: str) -> int:
    """Compare re-derived bytes with the committed contract and module (no writes)."""
    bad = 0
    for name, want in files.items():
        path = contracts_dir / name
        if not path.is_file():
            print(f"MISSING  {path}")
            bad += 1
        elif path.read_bytes() != want:
            print(f"MODIFIED {path}")
            bad += 1
    current = module_path.read_text(encoding="utf-8") if module_path.is_file() else ""
    if current != module_text:
        print(f"MODIFIED {module_path}")
        bad += 1
    print("ok" if not bad else f"{bad} problem(s)")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    """Generate the contract and module, or verify them with ``--check``."""
    parser = argparse.ArgumentParser(description="Generate pinned Unicode 15.0.0 case tables.")
    parser.add_argument("--check", action="store_true", help="verify only; write nothing")
    parser.add_argument("--ucd-dir", required=True, help="directory with the 3 UCD 15.0.0 sources")
    parser.add_argument(
        "--oracle-vectors",
        required=True,
        help="oracle JSON from tests/oracle/unicode_case_oracle.py under UCD 15.0.0",
    )
    parser.add_argument(
        "--contracts-dir",
        default=None,
        help="contract directory (default: CONTRACTS.toml [unicode-case] dest)",
    )
    parser.add_argument(
        "--module",
        default=None,
        help="generated module path (default: src/bpmn_io/profile/_unicode15.py)",
    )
    args = parser.parse_args(argv)
    section = load_section()
    if str(section.get("format")) != "unicode-case/1":
        print("CONTRACTS.toml: [unicode-case] format must be 'unicode-case/1'")
        return 1
    if str(section.get("unicode_version")) != "15.0.0":
        print("CONTRACTS.toml: [unicode-case] unicode_version must be '15.0.0'")
        return 1
    contracts_dir = Path(args.contracts_dir) if args.contracts_dir else ROOT / str(section["dest"])
    module_path = (
        Path(args.module) if args.module else ROOT / "src" / "bpmn_io" / "profile" / "_unicode15.py"
    )
    sources = read_sources(Path(args.ucd_dir), section)
    oracle_vectors = load_oracle_vectors(Path(str(args.oracle_vectors)))
    derived = derive(sources, oracle_vectors)
    files = build_contract(section, derived, sources)
    module_text = render_module(_as_dict(derived["table"], "table"), sources)
    if args.check:
        return check(contracts_dir, module_path, files, module_text)
    contracts_dir.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (contracts_dir / name).write_bytes(data)
        print(f"wrote {(contracts_dir / name).relative_to(ROOT)}")
    module_path.write_text(module_text, encoding="utf-8")
    print(f"wrote {module_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
