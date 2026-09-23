#!/usr/bin/env python3
"""Vendor upstream artefacts at a pinned commit and keep a provenance ledger.

Usage:
  scripts/sync_upstream.py            # (re)vendor every pinned path, rewrite UPSTREAM.lock
  scripts/sync_upstream.py --check    # verify pins, vendored files and absence of extras (CI)
  scripts/sync_upstream.py --latest   # print the latest upstream versions (no changes)

Pins live in UPSTREAM.toml at the repository root. GitHub sources are fetched by *commit* (immutable
archive URL), npm sources by exact version. stdlib only.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import sys
import tarfile
import tomllib
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PINS = ROOT / "UPSTREAM.toml"
LOCK = ROOT / "UPSTREAM.lock"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as resp:
        return resp.read()


def npm_tarball(name: str, version: str) -> tarfile.TarFile:
    url = f"https://registry.npmjs.org/{name}/-/{name}-{version}.tgz"
    return tarfile.open(fileobj=io.BytesIO(fetch(url)), mode="r:gz")


def github_commit_tarball(repo: str, commit: str) -> tarfile.TarFile:
    url = f"https://github.com/{repo}/archive/{commit}.tar.gz"
    return tarfile.open(fileobj=io.BytesIO(fetch(url)), mode="r:gz")


def _safe_relative(rel: str) -> PurePosixPath:
    path = PurePosixPath(rel)
    if path.is_absolute() or ".." in path.parts:
        msg = f"refusing unsafe archive member path {rel!r}"
        raise SystemExit(msg)
    return path


def extract_members(tar: tarfile.TarFile, prefix: str, dest: Path) -> dict[str, str]:
    """Copy every regular file at/under `prefix` (after the archive's root folder) into `dest`."""
    written: dict[str, str] = {}
    prefix = prefix.strip("/")
    for member in tar.getmembers():
        if not member.isfile():
            continue
        parts = member.name.split("/", 1)
        if len(parts) != 2:
            continue
        inner = parts[1]
        if inner == prefix:
            rel = ""
        elif inner.startswith(prefix + "/"):
            rel = inner[len(prefix) + 1 :]
        else:
            continue
        target = dest / _safe_relative(rel) if rel else dest
        target.parent.mkdir(parents=True, exist_ok=True)
        stream = tar.extractfile(member)
        if stream is None:  # pragma: no cover - defensive
            continue
        data = stream.read()
        target.write_bytes(data)
        written[str(target.relative_to(ROOT))] = sha256(data)
    if not written:
        msg = f"nothing extracted for path {prefix!r} into {dest.relative_to(ROOT)}"
        raise SystemExit(msg)
    return written


def load_pins() -> dict[str, dict[str, Any]]:
    pins: dict[str, dict[str, Any]] = tomllib.loads(PINS.read_text())["upstream"]
    return pins


def vendor() -> None:
    ledger: dict[str, Any] = {"sources": {}}
    for key, pin in load_pins().items():
        entry: dict[str, Any] = {
            "npm": pin["npm"],
            "version": pin["version"],
            "repo": pin["repo"],
            "tag": pin["tag"],
            "commit": pin["commit"],
            "license": pin["license"],
            "dests": sorted(spec["dest"] for spec in pin.get("vendor", [])),
        }
        files: dict[str, str] = {}
        archives: dict[str, tarfile.TarFile] = {}
        for spec in pin.get("vendor", []):
            dest = ROOT / spec["dest"]
            if dest.is_dir():
                shutil.rmtree(dest)
            elif dest.exists():
                dest.unlink()
            source = spec["from"]
            if source not in archives:
                if source == "npm":
                    archives[source] = npm_tarball(pin["npm"], pin["version"])
                elif source == "github":
                    archives[source] = github_commit_tarball(pin["repo"], pin["commit"])
                else:
                    msg = f"unknown source {source!r} for {key}"
                    raise SystemExit(msg)
            files |= extract_members(archives[source], spec["path"], dest)
        entry["files"] = dict(sorted(files.items()))
        ledger["sources"][key] = entry
    LOCK.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")
    print(f"wrote {LOCK.relative_to(ROOT)}")


def check() -> int:
    ledger = json.loads(LOCK.read_text())
    pins = load_pins()
    bad = 0
    if set(ledger["sources"]) != set(pins):
        print(f"PINS     lock sources {sorted(ledger['sources'])} != toml {sorted(pins)}")
        bad += 1
    for key, entry in ledger["sources"].items():
        pin = pins.get(key, {})
        for field in ("version", "commit", "tag"):
            if pin.get(field) != entry.get(field):
                lock_value, toml_value = entry.get(field), pin.get(field)
                print(f"PINS     {key}.{field}: lock {lock_value!r} != toml {toml_value!r}")
                bad += 1
        expected = set(entry["files"])
        for rel, digest in entry["files"].items():
            path = ROOT / rel
            if not path.exists():
                print(f"MISSING  {rel} ({key})")
                bad += 1
            elif sha256(path.read_bytes()) != digest:
                print(f"MODIFIED {rel} ({key})")
                bad += 1
        for dest in entry.get("dests", []):
            root = ROOT / dest
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                if path.is_file() and str(path.relative_to(ROOT)) not in expected:
                    print(f"EXTRA    {path.relative_to(ROOT)} ({key})")
                    bad += 1
    print("ok" if not bad else f"{bad} problem(s)")
    return 1 if bad else 0


def latest() -> None:
    for key, pin in load_pins().items():
        meta = json.loads(fetch(f"https://registry.npmjs.org/{pin['npm']}/latest"))
        flag = "" if meta["version"] == pin["version"] else "  <-- newer upstream"
        print(f"{key}: pinned {pin['version']}, latest {meta['version']}{flag}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["--check"]:
        sys.exit(check())
    elif args == ["--latest"]:
        latest()
    elif not args:
        vendor()
    else:
        print(__doc__)
        sys.exit(2)
