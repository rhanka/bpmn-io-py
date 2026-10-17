"""Lot 19: pinned R3.1 contract artifacts are complete and neutral.

Checks (DESIGN.md R3.1, sections 3.1/3.4 and plan Lot 19):
- every neutral profile migration resolves ``to == "self"`` and its
  ``from.sha256`` equals the profile-c14n/2 digest ``H`` of the vendored
  migration source (``neutral-profile.R2.json``,
  ``neutral-grid-profile.v1.json``);
- ``bpmnlint-11.15.0-recommended.json`` ``sourceSha256`` equals the SHA-256 of
  ``tests/upstream/bpmnlint/config/recommended.js`` and its 26 settings are
  identical;
- no business name or marker enters ``contracts/**`` (brand guard).

The expected digests are authored from the DESIGN text first (``H(x)`` =
lowercase hex SHA-256 over UTF-8 JCS bytes); the Node reference
(``tests/oracle/profile_c14n.mjs``, Node ``crypto``) is the independent
check, not the author.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

Json = dict[str, "Json"] | list["Json"] | str | int | float | bool | None

ROOT = Path(__file__).resolve().parent.parent.parent
CONTRACTS = ROOT / "contracts" / "profile-mechanism" / "1"
ORACLE_C14N = ROOT / "tests" / "oracle" / "profile_c14n.mjs"
UPSTREAM_RECOMMENDED = ROOT / "tests" / "upstream" / "bpmnlint" / "config" / "recommended.js"

MIGRATION_SOURCES = {
    "neutral-profile.json": "neutral-profile.R2.json",
    "neutral-grid-profile.json": "neutral-grid-profile.v1.json",
}

# Brand guard. Only the lowercase SHA-256 of each guarded word is written here,
# so the words themselves appear nowhere in the repository. Same method as the
# bpmn-canvas guard (tests/helpers/brand.mjs): split text into identifiers
# (runs of [A-Za-z0-9_]), check each identifier and its snake_case/camelCase
# parts of length >= 3, lowercased. Whole identifiers never false-positive on
# hex digests that embed a guarded letter run.
#: The bpmn-canvas set (tests/helpers/brand.mjs).
BRAND_SHARED_HASHES = frozenset(
    {
        "36aa04f4333ebc94260a496b27815226e288d9f946e5eca92362e42c09626290",
        "138a62a1a80d724e866794bf5417ccf20e4c406452c2d4b2ba102fbd2288a30e",
        "d040b14773a422aa0191db4a5ebba83974ef6bc308aeca0aebcf35d73d398252",
        "c8e73184b9b79668836ee7b6ebf7da95b1716c2d03410e11937a7fe45326d677",
        "6ee912f4da943f9aa092e0630a282f4cb60cb152b228b19ae33bab9f4150e046",
        "edf9539d742397cb3c267b7ed30d2e5b3060f999b9512612de63a588f975bfc5",
    }
)
#: Library-only identifier hashes (two business words).
BRAND_LIBRARY_HASHES = frozenset(
    {
        "fcb3d245658a5ecf9e75f59050fcc0fd20a92c9eeeb223a99632cd4ef789452c",
        "db66fe349809217e7926360ab81ae6ff26f9816c09a4b362e7dbfd5825b688be",
    }
)
#: Library-only marker hashes: a lowercase two-word phrase (adjacent words
#: joined by one space) and two lowercase bracketed markers (``[word]``).
BRAND_MARKER_HASHES = frozenset(
    {
        "53d8731524013c0d509f1e36af2a69726f60270f88c360d562af794f0bc15fb9",
        "583423608eda0cb63146a67a6ad655858bc511ba6f0d4fd742c0d898b684295a",
        "32ed8e0a3026bc02976abc70f27ddfe1f149b8f4dc5dad00a1451dd7e86e42e9",
    }
)
BRAND_IDENTIFIER_HASHES = BRAND_SHARED_HASHES | BRAND_LIBRARY_HASHES
#: SHA-256 over all guarded hashes (identifiers and markers), sorted and joined by
#: "\n": the union pinned identically by both libraries (cross-repository check).
BRAND_UNION_SHA256 = "a3e22cb4caff99dd72506ba8a770fd6bd838b0e2870f7cbb18ad896755625174"

_IDENTIFIER = re.compile(r"[A-Za-z0-9_]+")
_PART_SPLIT = re.compile(r"_+|(?<=[a-z0-9])(?=[A-Z])")
_BRACKETED = re.compile(r"\[[A-Za-z0-9_]+\]")
_WORD_PAIR = re.compile(r"(?=\b([A-Za-z]+ [A-Za-z]+)\b)")

#: Tracked trees the repo-wide guard does not scan (vendored upstream sources,
#: local workbench material).
GUARD_EXCLUDED_PREFIXES = ("tests/upstream/", "tmp/")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalize_numbers(value: Json) -> Json:
    """Map JSON numbers to ECMAScript shortest-round-trip rendering inputs.

    ``profile-c14n/2`` renders numbers like ECMAScript: a finite float with a
    zero fractional part is an integer (``1.0`` canonicalizes to ``1``) and
    ``-0`` canonicalizes to ``0``. Python ``json.dumps(1.0)`` would emit
    ``1.0``, so integral floats become ``int`` before dumping.
    """
    if isinstance(value, float):
        if value == 0:
            return 0
        if value.is_integer():
            return int(value)
        return value
    if isinstance(value, dict):
        return {key: _normalize_numbers(entry) for key, entry in value.items()}
    if isinstance(value, list):
        return [_normalize_numbers(entry) for entry in value]
    return value


def _jcs(value: Json) -> str:
    """Canonical JSON per DESIGN section 3.1 (ASCII-safe subset).

    UTF-16 code-unit key order (via UTF-16BE byte order, equal to code-point
    order inside the BMP), no insignificant whitespace, ``ensure_ascii=False``
    (UTF-8 without BOM, JSON escaping, no normalization). Number rendering
    goes through :func:`_normalize_numbers` first.
    """
    normalized = _normalize_numbers(value)
    if normalized is None or not isinstance(normalized, (dict, list)):
        return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
    if isinstance(normalized, list):
        return "[" + ",".join(_jcs(entry) for entry in normalized) + "]"
    keys = sorted(normalized.keys(), key=lambda k: k.encode("utf-16-be"))
    return (
        "{"
        + ",".join(
            json.dumps(key, ensure_ascii=False) + ":" + _jcs(normalized[key]) for key in keys
        )
        + "}"
    )


def _digest(value: Json) -> str:
    return _sha256(_jcs(value).encode("utf-8"))


def _node_digest(path: Path) -> str:
    exe = shutil.which("node")
    if exe is None or not ORACLE_C14N.is_file():
        pytest.skip("oracle needs node and tests/oracle/profile_c14n.mjs")
    proc = subprocess.run(  # noqa: S603 — fixed argv ([node, canonicalizer, file]), no shell.
        [exe, str(ORACLE_C14N), str(path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        pytest.fail(f"node canonicalizer failed: {proc.stderr.strip()}")
    return proc.stdout.split()[0]


def test_migration_pins_are_self_and_match_sources() -> None:
    """Each neutral profile migration targets ``self`` with a pinned source digest."""
    for profile_name, source_name in MIGRATION_SOURCES.items():
        profile = json.loads((CONTRACTS / profile_name).read_text(encoding="utf-8"))
        source = json.loads((CONTRACTS / source_name).read_text(encoding="utf-8"))
        assert len(profile["migrations"]) == 1
        (migration,) = profile["migrations"]
        assert migration["to"] == "self"
        assert migration["from"]["sha256"] == _digest(source)


@pytest.mark.oracle
def test_migration_digests_match_node_reference() -> None:
    """The independent Node reference agrees with every migration source digest."""
    for profile_name, source_name in MIGRATION_SOURCES.items():
        profile = json.loads((CONTRACTS / profile_name).read_text(encoding="utf-8"))
        (migration,) = profile["migrations"]
        assert migration["from"]["sha256"] == _node_digest(CONTRACTS / source_name)


def test_bpmnlint_recommended_matches_upstream_source() -> None:
    """The recommended manifest pins the exact upstream 11.15.0 source bytes."""
    manifest = json.loads(
        (CONTRACTS / "bpmnlint-11.15.0-recommended.json").read_text(encoding="utf-8")
    )
    upstream_bytes = UPSTREAM_RECOMMENDED.read_bytes()
    assert manifest["sourceSha256"] == _sha256(upstream_bytes)
    assert manifest["sourceSha256"] == _sha256(manifest["sourceText"].encode("utf-8"))
    upstream_text = upstream_bytes.decode("utf-8")
    settings = dict(re.findall(r"'([^']+)': '(off|warn|error|info)'", upstream_text))
    assert manifest["rules"] == settings
    assert len(manifest["rules"]) == 26


def _brand_hits(
    line: str,
    identifiers: frozenset[str] = BRAND_IDENTIFIER_HASHES,
    markers: frozenset[str] = BRAND_MARKER_HASHES,
) -> list[str]:
    """Guarded words or markers of ``line``, matched by hash only."""
    found: list[str] = []
    for token in _IDENTIFIER.findall(line):
        parts = [token, *(part for part in _PART_SPLIT.split(token) if part and part != token)]
        found.extend(
            part
            for part in parts
            if len(part) >= 3 and _sha256(part.lower().encode()) in identifiers
        )
    candidates = _BRACKETED.findall(line) + _WORD_PAIR.findall(line)
    found.extend(c for c in candidates if _sha256(c.lower().encode()) in markers)
    return found


def _scan_text(text: str) -> list[str]:
    """First guarded hit per line, for readable failure output."""
    found = []
    for lineno, line in enumerate(text.splitlines(), 1):
        hits = _brand_hits(line)
        if hits:
            found.append(f"line {lineno}: {hits[0]!r}")
    return found


def test_brand_union_matches_pinned_digest() -> None:
    """The guarded hash union equals the value pinned by both libraries."""
    union = BRAND_IDENTIFIER_HASHES | BRAND_MARKER_HASHES
    assert (len(BRAND_SHARED_HASHES), len(union)) == (6, 11)
    assert _sha256("\n".join(sorted(union)).encode()) == BRAND_UNION_SHA256


def test_brand_guard_detects_by_hash() -> None:
    """Self-test with synthetic probes: hex runs and short parts never match."""
    assert _brand_hits("digest 1e42b387a0c9f3e1") == []
    assert _brand_hits("ab_cd xY") == []
    assert _brand_hits("[note] other note") == []
    # Synthetic probe hashes ("zqprobe", "zq probe", "[zqprobe]"), not guarded words.
    ident = frozenset({"703e6f28231306b8ea31921aaf46a5e4a7ea75eb110290792ed3f427325b7794"})
    mark = frozenset(
        {
            "867b56a053ad02b4add01f12ac08b6edaba906655e52756d0a7e3f41776c934e",
            "aa122b11a14fa6ce5bc9290f67f7df8e6d45922af6e4d0ea94ae0cc15fd7f15f",
        }
    )
    assert _brand_hits("x ZqProbe y", ident, mark) == ["ZqProbe"]
    assert _brand_hits("my_zqprobe_id fooZqprobe", ident, mark) == ["zqprobe", "Zqprobe"]
    assert _brand_hits("x zqprobed", ident, mark) == []
    assert _brand_hits("digest 1e42zqprobe9f", ident, mark) == []
    assert _brand_hits("an ZQ PROBE tag", ident, mark) == ["ZQ PROBE"]
    assert _brand_hits("see [ZqProbe]", ident, mark) == ["ZqProbe", "[ZqProbe]"]


def test_contracts_have_no_business_names() -> None:
    """Brand guard: no business or private name or marker in contracts/**."""
    hits = []
    for path in sorted(CONTRACTS.rglob("*")):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        hits.extend(f"{path.relative_to(ROOT)} {entry}" for entry in _scan_text(text))
    assert hits == []


def _tracked_files() -> list[str]:
    exe = shutil.which("git")
    if exe is None:
        pytest.skip("repo-wide guard needs git")
    proc = subprocess.run(  # noqa: S603 — fixed argv ([git, ls-files]), no shell.
        [exe, "ls-files"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=ROOT,
        check=False,
    )
    if proc.returncode != 0:
        pytest.skip("repo-wide guard needs a git checkout")
    return [
        line
        for line in proc.stdout.splitlines()
        if line and not line.startswith(GUARD_EXCLUDED_PREFIXES)
    ]


def test_repo_has_no_business_names() -> None:
    """Repo-wide brand guard: no business or private name outside excluded trees.

    No exception: the guard itself holds hashes only.
    """
    hits = []
    for rel in _tracked_files():
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_bytes().decode("utf-8", errors="ignore")
        hits.extend(f"{rel} {entry}" for entry in _scan_text(text))
    assert hits == []
