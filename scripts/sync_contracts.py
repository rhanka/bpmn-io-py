#!/usr/bin/env python3
"""Vendor profile-mechanism/1 contract artifacts at a pinned R3.3 revision.

Usage:
  scripts/sync_contracts.py --source <conductor-folder>
  scripts/sync_contracts.py --check    # verify pins, vendored files and absence of extras (CI)
  scripts/sync_contracts.py --f1-manifest  # rewrite the f1-extensions manifest+lock (write mode)

Pins live in CONTRACTS.toml at the repository root. The conductor folder is
read-only: this script copies bytes and verifies them against the conductor
manifest (MANIFEST-R33.sha256) before writing; it never writes back there.
Files listed under [profile-mechanism.addendum] are verified the same way
against a second conductor manifest (for example MANIFEST-R33-ADDENDUM.sha256
for the public matrix-vector variant); the non-public bytes it replaces are
never vendored here.
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
    addendum = section.get("addendum", {})
    if not isinstance(artifacts, list) or not all(isinstance(a, str) for a in artifacts):
        msg = "CONTRACTS.toml: [profile-mechanism] artifacts must be a list of str"
        raise SystemExit(msg)
    if not isinstance(extra, dict):
        msg = "CONTRACTS.toml: [profile-mechanism.extra] must be a table"
        raise SystemExit(msg)
    if not isinstance(addendum, dict):
        msg = "CONTRACTS.toml: [profile-mechanism.addendum] must be a table"
        raise SystemExit(msg)
    addendum_artifacts = addendum.get("artifacts", [])
    if not isinstance(addendum_artifacts, list) or not all(
        isinstance(a, str) for a in addendum_artifacts
    ):
        msg = "CONTRACTS.toml: [profile-mechanism.addendum] artifacts must be a list of str"
        raise SystemExit(msg)
    expected: dict[str, str] = {}
    for name in artifacts:
        expected[f"{dest}/{name}"] = ""
    for name in extra:
        expected[f"{dest}/{name}"] = ""
    for name in addendum_artifacts:
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


def _verified_manifest(source_dir: Path, manifest_file: str, pinned: str) -> dict[str, str]:
    """Read a conductor manifest after checking its file hash against the pin."""
    manifest_bytes = (source_dir / manifest_file).read_bytes()
    manifest_digest = sha256(manifest_bytes)
    if manifest_digest != pinned:
        msg = (
            f"conductor manifest hash mismatch: {manifest_file} is {manifest_digest}, "
            f"CONTRACTS.toml pins {pinned}"
        )
        raise SystemExit(msg)
    return _parse_manifest(manifest_bytes.decode("utf-8"))


def _copy_manifest_artifacts(
    source_dir: Path,
    dest: Path,
    manifest: dict[str, str],
    manifest_file: str,
    names: list[object],
) -> dict[str, str]:
    """Copy manifest-pinned artifacts into the destination directory."""
    files: dict[str, str] = {}
    for name in names:
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
        files[target.relative_to(ROOT).as_posix()] = sha256(data)
    return files


def vendor(explicit_source: str | None) -> None:
    pins = load_pins()
    section = _contract_section(pins)
    source_dir = _resolve_source(explicit_source)
    design_file = str(section["design_file"])
    manifest_file = str(section["manifest_file"])
    dest = ROOT / str(section["dest"])
    artifacts = section["artifacts"]
    extra = section.get("extra", {})
    addendum = section.get("addendum", {})
    if (
        not isinstance(artifacts, list)
        or not isinstance(extra, dict)
        or not isinstance(addendum, dict)
    ):
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

    manifest = _verified_manifest(source_dir, manifest_file, str(section["manifest_sha256"]))

    dest.mkdir(parents=True, exist_ok=True)
    files = _copy_manifest_artifacts(source_dir, dest, manifest, manifest_file, artifacts)
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
        files[target.relative_to(ROOT).as_posix()] = sha256(data)

    if addendum:
        addendum_manifest_file = str(addendum["manifest_file"])
        addendum_manifest = _verified_manifest(
            source_dir, addendum_manifest_file, str(addendum["manifest_sha256"])
        )
        names = addendum.get("artifacts", [])
        if not isinstance(names, list):
            msg = "CONTRACTS.toml: [profile-mechanism.addendum] artifacts must be a list"
            raise SystemExit(msg)
        files.update(
            _copy_manifest_artifacts(
                source_dir, dest, addendum_manifest, addendum_manifest_file, names
            )
        )

    ledger = {
        "design_file": design_file,
        "design_sha256": section["design_sha256"],
        "dest": str(section["dest"]),
        "files": dict(sorted(files.items())),
        "manifest_file": manifest_file,
        "manifest_sha256": section["manifest_sha256"],
        "source": section.get("source", ""),
    }
    if addendum:
        ledger["addendum_manifest_file"] = addendum["manifest_file"]
        ledger["addendum_manifest_sha256"] = addendum["manifest_sha256"]
    LOCK.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {LOCK.relative_to(ROOT)} ({len(files)} files)")


def _check_extra_pins(section: dict[str, object], ledger: dict[str, object]) -> int:
    """Compare every [profile-mechanism.extra] TOML pin with the lock digest."""
    bad = 0
    extra = section.get("extra", {})
    locked_files = ledger.get("files", {})
    if not isinstance(extra, dict) or not isinstance(locked_files, dict):
        print("PINS     extra/files is not a table")
        return 1
    dest = str(section.get("dest", ""))
    for name, spec in extra.items():
        want = spec.get("sha256") if isinstance(spec, dict) else None
        rel = f"{dest}/{name}"
        if locked_files.get(rel) != want:
            print(f"PINS     extra {rel}: lock digest != toml pin")
            bad += 1
    return bad


def _check_pins(section: dict[str, object], ledger: dict[str, object]) -> int:
    bad = 0
    for field in ("design_file", "design_sha256", "manifest_file", "manifest_sha256", "dest"):
        if ledger.get(field) != section.get(field):
            print(f"PINS     {field}: lock {ledger.get(field)!r} != toml {section.get(field)!r}")
            bad += 1
    bad += _check_extra_pins(section, ledger)
    # The vendored set must be exactly the TOML artifact list plus extras
    # and addendum artifacts.
    addendum = section.get("addendum", {})
    if addendum:
        for toml_field, lock_field in (
            ("manifest_file", "addendum_manifest_file"),
            ("manifest_sha256", "addendum_manifest_sha256"),
        ):
            if ledger.get(lock_field) != addendum.get(toml_field):
                print(f"PINS     {lock_field}: lock != toml")
                print(f"         lock {ledger.get(lock_field)!r}")
                print(f"         toml {addendum.get(toml_field)!r}")
                bad += 1
    elif ledger.get("addendum_manifest_file") or ledger.get("addendum_manifest_sha256"):
        print("PINS     lock carries addendum pins not pinned in CONTRACTS.toml")
        bad += 1
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
            rel = path.relative_to(ROOT).as_posix()
            if path.is_file() and rel not in locked:
                print(f"EXTRA    {rel}")
                bad += 1
    else:
        print(f"MISSING  {section['dest']}/")
        bad += 1
    return bad


def _unicode_case_targets(
    pins: dict[str, object], ledger: dict[str, object]
) -> tuple[dict[str, object], dict[str, object]] | None:
    """Return the ([unicode-case], lock entry) pair, or None after reporting."""
    section = pins.get("unicode-case")
    locked = ledger.get("unicode-case")
    if not isinstance(section, dict):
        print("PINS     CONTRACTS.toml: missing [unicode-case] section")
        return None
    if not isinstance(locked, dict):
        print("PINS     CONTRACTS.lock: missing unicode-case entry")
        return None
    return section, locked


def _unicode_case_want(section: dict[str, object]) -> set[str] | None:
    """Return the expected vendored paths, or None after reporting."""
    artifacts = section.get("artifacts")
    if not isinstance(artifacts, list) or not all(isinstance(a, str) for a in artifacts):
        print("PINS     CONTRACTS.toml: [unicode-case] artifacts must be a list of str")
        return None
    dest = str(section.get("dest", ""))
    return {f"{dest}/{name}" for name in artifacts}


def _check_unicode_case_files(
    section: dict[str, object], locked: dict[str, object], want: set[str]
) -> int:
    """Compare lock digests with the contract bytes; flag extras."""
    bad = 0
    dest = str(section.get("dest", ""))
    locked_files = locked.get("files")
    if not isinstance(locked_files, dict):
        print("PINS     CONTRACTS.lock: unicode-case files is not a table")
        return 1
    if set(locked_files) != want:
        for rel in sorted(want - set(locked_files)):
            print(f"PINS     unicode-case lock is missing {rel}")
        for rel in sorted(set(locked_files) - want):
            print(f"PINS     unicode-case lock lists {rel} not pinned in CONTRACTS.toml")
        bad += 1
    for rel in sorted(want):
        path = ROOT / rel
        if not path.is_file():
            print(f"MISSING  {rel}")
            bad += 1
        elif sha256(path.read_bytes()) != locked_files.get(rel):
            print(f"MODIFIED {rel}")
            bad += 1
    dest_root = ROOT / dest
    if not dest_root.is_dir():
        print(f"MISSING  {dest}/")
        return bad + 1
    for path in sorted(dest_root.rglob("*")):
        rel = path.relative_to(ROOT).as_posix()
        if path.is_file() and rel not in locked_files:
            print(f"EXTRA    {rel}")
            bad += 1
    return bad


def _check_unicode_case_manifest(section: dict[str, object], locked: dict[str, object]) -> int:
    """Compare the manifest record with the TOML pins and the file bytes."""
    bad = 0
    dest = str(section.get("dest", ""))
    try:
        manifest = json.loads((ROOT / dest / "manifest.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"MISSING  {dest}/manifest.json")
        return 1
    except json.JSONDecodeError:
        print(f"PINS     {dest}/manifest.json is not JSON")
        return 1
    if not isinstance(manifest, dict):
        print(f"PINS     {dest}/manifest.json is not a JSON object")
        return 1
    if manifest.get("format") != section.get("format"):
        print(f"PINS     {dest}/manifest.json format != toml")
        bad += 1
    if manifest.get("unicodeVersion") != section.get("unicode_version"):
        print(f"PINS     {dest}/manifest.json unicodeVersion != toml")
        bad += 1
    bad += _check_unicode_case_manifest_files(locked, manifest, dest)
    bad += _check_unicode_case_manifest_sources(section, manifest, dest)
    return bad


def _check_unicode_case_manifest_files(
    locked: dict[str, object],
    manifest: dict[str, object],
    dest: str,
) -> int:
    """Compare the manifest file record with the lock digests and file bytes."""
    bad = 0
    manifest_files = manifest.get("files")
    locked_files = locked.get("files")
    if not isinstance(manifest_files, dict) or not isinstance(locked_files, dict):
        print(f"PINS     {dest}/manifest.json files is not a table")
        return 1
    for name in ("case-table.json", "vectors.json"):
        path = ROOT / dest / name
        actual = sha256(path.read_bytes()) if path.is_file() else None
        if manifest_files.get(name) != actual or locked_files.get(f"{dest}/{name}") != actual:
            print(f"PINS     {dest}/manifest.json files[{name}] != file bytes")
            bad += 1
    return bad


def _check_unicode_case_manifest_sources(
    section: dict[str, object], manifest: dict[str, object], dest: str
) -> int:
    """Compare the manifest source record with the TOML source pins."""
    toml_sources = section.get("sources")
    manifest_sources = manifest.get("sources")
    if not isinstance(toml_sources, dict):
        print("PINS     CONTRACTS.toml: [unicode-case.sources] must be a table")
        return 1
    if not isinstance(manifest_sources, list):
        print(f"PINS     {dest}/manifest.json sources is not a list")
        return 1
    pinned = {
        name: (spec.get("size"), spec.get("sha256"))
        for name, spec in toml_sources.items()
        if isinstance(spec, dict)
    }
    recorded = {
        entry.get("file"): (entry.get("size"), entry.get("sha256"))
        for entry in manifest_sources
        if isinstance(entry, dict)
    }
    if recorded != pinned or len(pinned) != len(toml_sources):
        print(f"PINS     {dest}/manifest.json sources != toml pins")
        return 1
    return 0


def _check_unicode_case(pins: dict[str, object], ledger: dict[str, object]) -> int:
    """Verify the self-hosted unicode-case/1 contract (offline, hash-based).

    The raw UCD sources are never vendored, so their pins in
    ``[unicode-case.sources]`` are compared with the manifest's source record;
    every contract file is compared with the lock digest and the manifest's
    file record.
    """
    targets = _unicode_case_targets(pins, ledger)
    if targets is None:
        return 1
    section, locked = targets
    bad = 0
    for field in ("format", "unicode_version", "dest"):
        if locked.get(field) != section.get(field):
            print(f"PINS     unicode-case {field}: lock != toml")
            bad += 1
    want = _unicode_case_want(section)
    if want is None:
        return bad + 1
    bad += _check_unicode_case_files(section, locked, want)
    return bad + _check_unicode_case_manifest(section, locked)


def _check_f1_from_pins(pins: dict[str, object], ledger: dict[str, object]) -> int:
    """Verify the self-hosted f1-extensions contract from the pin/ledger pair.

    Missing ``[f1-extensions]`` pins count as a failure (like the
    unicode-case targets helper) instead of raising, so the unified
    self-hosted dispatch always reports through ``check()``.
    """
    section = pins.get("f1-extensions")
    if not isinstance(section, dict):
        print("PINS     CONTRACTS.toml: missing [f1-extensions] section")
        return 1
    return _check_f1(section, ledger)


#: Every self-hosted (repo-owned) contract check, one coherent dispatch.
_SELF_HOSTED_CHECKS = (
    _check_unicode_case,
    _check_f1_from_pins,
)


def _check_self_hosted(pins: dict[str, object], ledger: dict[str, object]) -> int:
    """Run every self-hosted contract check through one dispatch table."""
    bad = 0
    for check_one in _SELF_HOSTED_CHECKS:
        bad += check_one(pins, ledger)
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
    bad = (
        _check_pins(section, ledger)
        + _check_bytes(section, ledger)
        + _check_self_hosted(pins, ledger)
    )
    print("ok" if not bad else f"{bad} problem(s)")
    return 1 if bad else 0


def _f1_section(pins: dict[str, object]) -> dict[str, object]:
    section = pins.get("f1-extensions")
    if not isinstance(section, dict):
        msg = "CONTRACTS.toml: missing [f1-extensions] section"
        raise SystemExit(msg)
    return section


def _f1_manifest_entries(dest: Path, manifest_name: str) -> dict[str, str]:
    """Parse the self-hosted ``<sha>  <name>`` manifest lines (Node-verifiable)."""
    text = (dest / manifest_name).read_text(encoding="utf-8")
    entries: dict[str, str] = {}
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) != 2 or len(parts[0]) != 64:
            msg = f"malformed f1 manifest line {lineno}: {line!r}"
            raise SystemExit(msg)
        digest, name = parts
        if name in (".", "..") or ".." in name.split("/") or name.startswith("/"):
            msg = f"unsafe f1 manifest name {name!r}"
            raise SystemExit(msg)
        entries[name] = digest
    return entries


def _check_f1(section: dict[str, object], ledger: dict[str, object]) -> int:
    """Verify the self-hosted f1-extensions contract (offline, no source)."""
    block, bad = _f1_lock_block(section, ledger)
    if block is None:
        return bad
    dest = ROOT / str(section.get("dest", ""))
    manifest_name = str(section.get("manifest", ""))
    manifest_path = dest / manifest_name
    if not manifest_path.is_file():
        print(f"F1       missing {manifest_path.relative_to(ROOT)}")
        return bad + 1
    if block.get("manifest_sha256") != sha256(manifest_path.read_bytes()):
        print("F1       manifest bytes != lock manifest_sha256")
        bad += 1
    try:
        entries = _f1_manifest_entries(dest, manifest_name)
    except SystemExit as err:
        print(f"F1       {err}")
        return bad + 1
    locked_files = block.get("files", {})
    if not isinstance(locked_files, dict):
        print("F1       lock files is not a table")
        return bad + 1
    want = {f"{section.get('dest')}/{name}": digest for name, digest in entries.items()}
    bad += _check_f1_file_set(want, locked_files)
    bad += _check_f1_file_bytes(section, manifest_name, want, locked_files)
    bad += _check_f1_extras(dest, manifest_name, want)
    return bad


def _f1_lock_block(
    section: dict[str, object], ledger: dict[str, object]
) -> tuple[dict[str, object] | None, int]:
    """Validate the lock's f1-extensions block header against the TOML pins."""
    block = ledger.get("f1-extensions")
    if not isinstance(block, dict):
        print("F1       lock has no f1-extensions block")
        return None, 1
    bad = 0
    for field in ("dest", "manifest"):
        if block.get(field) != section.get(field):
            print(f"F1       {field}: lock {block.get(field)!r} != toml {section.get(field)!r}")
            bad += 1
    return block, bad


def _check_f1_file_set(want: dict[str, str], locked_files: dict[str, object]) -> int:
    """Compare the manifest file set against the lock file set."""
    if set(locked_files) == set(want):
        return 0
    for rel in sorted(set(want) - set(locked_files)):
        print(f"F1       lock is missing {rel}")
    for rel in sorted(set(locked_files) - set(want)):
        print(f"F1       lock lists {rel} not in the manifest")
    return 1


def _check_f1_file_bytes(
    section: dict[str, object],
    manifest_name: str,
    want: dict[str, str],
    locked_files: dict[str, object],
) -> int:
    """Verify every manifest-listed file exists with matching bytes."""
    bad = 0
    for rel, digest in want.items():
        if rel == f"{section.get('dest')}/{manifest_name}":
            continue
        path = ROOT / rel
        if not path.is_file():
            print(f"F1       missing {rel}")
            bad += 1
        elif sha256(path.read_bytes()) != digest:
            print(f"F1       modified {rel}")
            bad += 1
        elif locked_files.get(rel) != digest:
            print(f"F1       lock digest != manifest for {rel}")
            bad += 1
    return bad


def _check_f1_extras(dest: Path, manifest_name: str, want: dict[str, str]) -> int:
    """Refuse files on disk that the manifest does not list."""
    bad = 0
    on_disk = {
        p.relative_to(ROOT).as_posix()
        for p in dest.rglob("*")
        if p.is_file() and p.name != manifest_name
    }
    for rel in sorted(on_disk - set(want)):
        print(f"F1       extra {rel}")
        bad += 1
    return bad


def write_f1_manifest() -> None:
    """Rewrite the f1-extensions manifest and lock block from working-tree bytes."""
    pins = load_pins()
    section = _f1_section(pins)
    dest = ROOT / str(section["dest"])
    manifest_name = str(section["manifest"])
    files = sorted(
        p.relative_to(dest).as_posix()
        for p in dest.rglob("*")
        if p.is_file() and p.name != manifest_name
    )
    lines = []
    digests: dict[str, str] = {}
    for name in files:
        digest = sha256((dest / name).read_bytes())
        digests[f"{section['dest']}/{name}"] = digest
        lines.append(f"{digest}  {name}\n")
    (dest / manifest_name).write_text("".join(lines), encoding="utf-8")
    ledger = json.loads(LOCK.read_text(encoding="utf-8"))
    ledger["f1-extensions"] = {
        "dest": section["dest"],
        "files": dict(sorted(digests.items())),
        "manifest": manifest_name,
        "manifest_sha256": sha256((dest / manifest_name).read_bytes()),
    }
    LOCK.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {dest.relative_to(ROOT)}/{manifest_name} ({len(files)} files)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vendor pinned profile-mechanism/1 contracts.")
    parser.add_argument("--check", action="store_true", help="offline pin verification (CI)")
    parser.add_argument("--source", default=None, help="conductor folder (copy mode only)")
    parser.add_argument(
        "--f1-manifest", action="store_true", help="rewrite the f1-extensions manifest+lock"
    )
    args = parser.parse_args(argv)
    if args.f1_manifest:
        write_f1_manifest()
        return 0
    if args.check:
        return check()
    vendor(args.source)
    return 0


if __name__ == "__main__":
    sys.exit(main())
