#!/usr/bin/env python3
"""Vendor profile-mechanism/1 contract artifacts at a pinned R3.3 revision.

Usage:
  scripts/sync_contracts.py --source <conductor-folder>
  scripts/sync_contracts.py --check    # verify pins, vendored files and absence of extras (CI)

Pins live in CONTRACTS.toml at the repository root. The conductor folder is
read-only: this script copies bytes and verifies them against the conductor
manifest (MANIFEST-R33.sha256) before writing; it never writes back there.
The folder location is deliberately NOT committed: copy mode takes it from
``--source`` (or env ``PROFILE_CONTRACTS_SOURCE``), while ``--check`` is
offline (like scripts/sync_upstream.py --check) and never needs it.
stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 fallback (repo requires >=3.11).
    import tomli as tomllib  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parent.parent
PINS = ROOT / "CONTRACTS.toml"
LOCK = ROOT / "CONTRACTS.lock"
SOURCE_ENV = "PROFILE_CONTRACTS_SOURCE"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_pins() -> dict[str, object]:
    return tomllib.loads(PINS.read_text(encoding="utf-8"))


def _contract_section(pins: dict[str, object]) -> dict[str, object]:
    section = pins.get("profile-mechanism")
    if not isinstance(section, dict):
        msg = "CONTRACTS.toml: missing [profile-mechanism] section"
        raise SystemExit(msg)
    return section


def _expected_files(section: dict[str, object]) -> dict[str, str]:
    """Vendored relative paths from the TOML artifact list plus extras.

    Manifest artifacts are pinned by the conductor manifest; the R2 migration
    source (absent from that manifest) is pinned by its raw SHA-256 in
    [profile-mechanism.extra].
    """
    dest = str(section["dest"])
    artifacts = section["artifacts"]
    extra = section.get("extra", {})
    if not isinstance(artifacts, list) or not all(isinstance(a, str) for a in artifacts):
        msg = "CONTRACTS.toml: [profile-mechanism] artifacts must be a list of str"
        raise SystemExit(msg)
    if not isinstance(extra, dict):
        msg = "CONTRACTS.toml: [profile-mechanism.extra] must be a table"
        raise SystemExit(msg)
    expected: dict[str, str] = {}
    for name in artifacts:
        expected[f"{dest}/{name}"] = ""
    for name in extra:
        expected[f"{dest}/{name}"] = ""
    return expected


def _parse_manifest(text: str) -> dict[str, str]:
    """Parse `<sha> <filename>` conductor manifest lines."""
    entries: dict[str, str] = {}
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) != 2 or len(parts[0]) != 64:
            msg = f"malformed manifest line {lineno}: {line!r}"
            raise SystemExit(msg)
        digest, name = parts
        entries[name] = digest
    return entries


def _resolve_source(explicit: str | None) -> Path:
    name = explicit or os.environ.get(SOURCE_ENV)
    if not name:
        msg = f"copy mode needs --source <dir> or env {SOURCE_ENV}"
        raise SystemExit(msg)
    source = Path(name)
    if not source.is_dir():
        msg = f"source is not a directory: {name}"
        raise SystemExit(msg)
    return source


def vendor(explicit_source: str | None) -> None:
    pins = load_pins()
    section = _contract_section(pins)
    source_dir = _resolve_source(explicit_source)
    design_file = str(section["design_file"])
    manifest_file = str(section["manifest_file"])
    dest = ROOT / str(section["dest"])
    artifacts = section["artifacts"]
    extra = section.get("extra", {})
    if not isinstance(artifacts, list) or not isinstance(extra, dict):
        msg = "CONTRACTS.toml: malformed [profile-mechanism] section"
        raise SystemExit(msg)

    design_bytes = (source_dir / design_file).read_bytes()
    design_digest = sha256(design_bytes)
    if design_digest != section["design_sha256"]:
        msg = (
            f"DESIGN hash mismatch: {design_file} is {design_digest}, "
            f"CONTRACTS.toml pins {section['design_sha256']}"
        )
        raise SystemExit(msg)

    manifest_bytes = (source_dir / manifest_file).read_bytes()
    manifest_digest = sha256(manifest_bytes)
    if manifest_digest != section["manifest_sha256"]:
        msg = (
            f"conductor manifest hash mismatch: {manifest_file} is {manifest_digest}, "
            f"CONTRACTS.toml pins {section['manifest_sha256']}"
        )
        raise SystemExit(msg)
    manifest = _parse_manifest(manifest_bytes.decode("utf-8"))

    dest.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}
    for name in artifacts:
        if not isinstance(name, str) or "/" in name or name in (".", ".."):
            msg = f"refusing unsafe artifact name {name!r}"
            raise SystemExit(msg)
        if name not in manifest:
            msg = f"artifact {name!r} absent from conductor manifest {manifest_file}"
            raise SystemExit(msg)
        data = (source_dir / name).read_bytes()
        if sha256(data) != manifest[name]:
            msg = f"artifact {name!r} does not match conductor manifest line"
            raise SystemExit(msg)
        target = dest / name
        target.write_bytes(data)
        files[str(target.relative_to(ROOT))] = sha256(data)
    for name, spec in extra.items():
        if not isinstance(spec, dict) or "sha256" not in spec:
            msg = f"CONTRACTS.toml: extra {name!r} needs a sha256 pin"
            raise SystemExit(msg)
        data = (source_dir / name).read_bytes()
        if sha256(data) != spec["sha256"]:
            msg = f"extra artifact {name!r} does not match CONTRACTS.toml pin"
            raise SystemExit(msg)
        target = dest / name
        target.write_bytes(data)
        files[str(target.relative_to(ROOT))] = sha256(data)

    ledger = {
        "design_file": design_file,
        "design_sha256": section["design_sha256"],
        "dest": str(section["dest"]),
        "files": dict(sorted(files.items())),
        "manifest_file": manifest_file,
        "manifest_sha256": section["manifest_sha256"],
        "source": section.get("source", ""),
    }
    LOCK.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {LOCK.relative_to(ROOT)} ({len(files)} files)")


def _check_pins(section: dict[str, object], ledger: dict[str, object]) -> int:
    bad = 0
    for field in ("design_sha256", "manifest_sha256", "dest"):
        if ledger.get(field) != section.get(field):
            print(f"PINS     {field}: lock {ledger.get(field)!r} != toml {section.get(field)!r}")
            bad += 1
    # The vendored set must be exactly the TOML artifact list plus extras.
    want = set(_expected_files(section))
    got = set(ledger.get("files", {}))
    if got != want:
        for rel in sorted(want - got):
            print(f"PINS     lock is missing {rel}")
        for rel in sorted(got - want):
            print(f"PINS     lock lists {rel} not pinned in CONTRACTS.toml")
        bad += 1
    return bad


def _check_bytes(section: dict[str, object], ledger: dict[str, object]) -> int:
    bad = 0
    locked = ledger.get("files", {})
    if not isinstance(locked, dict):
        print("PINS     lock files is not a table")
        return 1
    for rel, digest in locked.items():
        path = ROOT / str(rel)
        if not path.is_file():
            print(f"MISSING  {rel}")
            bad += 1
        elif sha256(path.read_bytes()) != digest:
            print(f"MODIFIED {rel}")
            bad += 1
    dest_root = ROOT / str(section["dest"])
    if dest_root.is_dir():
        for path in sorted(dest_root.rglob("*")):
            if path.is_file() and str(path.relative_to(ROOT)) not in locked:
                print(f"EXTRA    {path.relative_to(ROOT)}")
                bad += 1
    else:
        print(f"MISSING  {section['dest']}/")
        bad += 1
    return bad


def check() -> int:
    pins = load_pins()
    section = _contract_section(pins)
    try:
        ledger = json.loads(LOCK.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"MISSING  {LOCK.relative_to(ROOT)}")
        return 1
    if not isinstance(ledger, dict):
        print(f"PINS     {LOCK.relative_to(ROOT)} is not a JSON object")
        return 1
    bad = _check_pins(section, ledger) + _check_bytes(section, ledger)
    print("ok" if not bad else f"{bad} problem(s)")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vendor pinned profile-mechanism/1 contracts.")
    parser.add_argument("--check", action="store_true", help="offline pin verification (CI)")
    parser.add_argument("--source", default=None, help="conductor folder (copy mode only)")
    args = parser.parse_args(argv)
    if args.check:
        return check()
    vendor(args.source)
    return 0


if __name__ == "__main__":
    sys.exit(main())
