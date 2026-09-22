#!/usr/bin/env python3
"""Vendor upstream bpmn.io artefacts at a pinned version and keep a provenance ledger.

Usage:
  scripts/sync_upstream.py            # (re)vendor descriptors + fixtures, rewrite UPSTREAM.lock
  scripts/sync_upstream.py --check    # verify vendored files match UPSTREAM.lock (CI)
  scripts/sync_upstream.py --latest   # print the latest upstream versions (no changes)

Pins live in UPSTREAM.toml at the repository root. stdlib only.
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
from pathlib import Path

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


def github_tag_tarball(repo: str, tag: str) -> tarfile.TarFile:
    url = f"https://github.com/{repo}/archive/refs/tags/{tag}.tar.gz"
    return tarfile.open(fileobj=io.BytesIO(fetch(url)), mode="r:gz")


def extract_members(tar: tarfile.TarFile, prefix: str, dest: Path) -> dict[str, str]:
    """Copy every regular file under `prefix` (after the first path component) into `dest`."""
    written: dict[str, str] = {}
    for member in tar.getmembers():
        if not member.isfile():
            continue
        parts = member.name.split("/", 1)
        if len(parts) != 2 or not parts[1].startswith(prefix):
            continue
        rel = parts[1][len(prefix) :].lstrip("/")
        target = dest / rel if rel else dest  # a single-file spec vendors to `dest` itself
        target.parent.mkdir(parents=True, exist_ok=True)
        data = tar.extractfile(member).read()  # type: ignore[union-attr]
        target.write_bytes(data)
        written[str(target.relative_to(ROOT))] = sha256(data)
    return written


def vendor() -> None:
    pins = tomllib.loads(PINS.read_text())
    ledger: dict[str, object] = {"sources": {}, "files": {}}
    for key, pin in pins["upstream"].items():
        entry = {
            "npm": pin["npm"],
            "version": pin["version"],
            "repo": pin["repo"],
            "tag": pin["tag"],
            "commit": pin["commit"],
            "license": pin["license"],
        }
        files: dict[str, str] = {}
        for spec in pin.get("vendor", []):
            dest = ROOT / spec["dest"]
            if dest.is_dir():
                shutil.rmtree(dest)
            elif dest.exists():
                dest.unlink()
            if spec["from"] == "npm":
                tar = npm_tarball(pin["npm"], pin["version"])
                files |= extract_members(tar, spec["path"], dest)
            elif spec["from"] == "github":
                tar = github_tag_tarball(pin["repo"], pin["tag"])
                files |= extract_members(tar, spec["path"], dest)
            else:  # pragma: no cover - config error
                msg = f"unknown source {spec['from']!r} for {key}"
                raise SystemExit(msg)
        entry["files"] = dict(sorted(files.items()))
        ledger["sources"][key] = entry  # type: ignore[index]
    LOCK.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")
    print(f"wrote {LOCK.relative_to(ROOT)}")


def check() -> int:
    ledger = json.loads(LOCK.read_text())
    bad = 0
    for key, entry in ledger["sources"].items():
        for rel, digest in entry["files"].items():
            path = ROOT / rel
            if not path.exists():
                print(f"MISSING  {rel} ({key})")
                bad += 1
            elif sha256(path.read_bytes()) != digest:
                print(f"MODIFIED {rel} ({key})")
                bad += 1
    print("ok" if not bad else f"{bad} problem(s)")
    return 1 if bad else 0


def latest() -> None:
    pins = tomllib.loads(PINS.read_text())
    for key, pin in pins["upstream"].items():
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
