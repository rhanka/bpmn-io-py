"""Lot 22a R2: negative tests for scripts/sync_contracts.py --check.

Every case calls the pure pin comparison with crafted in-memory
section/ledger dicts (or read-only reads of the real pins); no test writes
the real ``CONTRACTS.lock`` or any vendored byte.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import types

    import pytest

ROOT = Path(__file__).resolve().parent.parent.parent


def _load() -> types.ModuleType:
    path = ROOT / "scripts" / "sync_contracts.py"
    spec = importlib.util.spec_from_file_location("sync_contracts", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SYNC = _load()
# White-box pin tests access the script's comparison helpers directly.
check_pins = SYNC._check_pins  # noqa: SLF001
contract_section = SYNC._contract_section  # noqa: SLF001
check_unicode_case = SYNC._check_unicode_case  # noqa: SLF001
check_self_hosted = SYNC._check_self_hosted  # noqa: SLF001
check_f1_from_pins = SYNC._check_f1_from_pins  # noqa: SLF001

SECTION: dict[str, Any] = {
    "source": "conductor design folder, revision R3.3 (local, read-only)",
    "design_file": "DESIGN.md",
    "design_sha256": "d" * 64,
    "manifest_file": "MANIFEST-R33.sha256",
    "manifest_sha256": "m" * 64,
    "dest": "contracts/profile-mechanism/1",
    "artifacts": ["a.json"],
    "extra": {"x.json": {"sha256": "e" * 64, "reason": "test pin"}},
    "addendum": {
        "manifest_file": "MANIFEST-R33-ADDENDUM.sha256",
        "manifest_sha256": "n" * 64,
        "artifacts": ["p.json"],
    },
}

LEDGER: dict[str, Any] = {
    "design_file": "DESIGN.md",
    "design_sha256": "d" * 64,
    "dest": "contracts/profile-mechanism/1",
    "files": {
        "contracts/profile-mechanism/1/a.json": "a" * 64,
        "contracts/profile-mechanism/1/x.json": "e" * 64,
        "contracts/profile-mechanism/1/p.json": "p" * 64,
    },
    "manifest_file": "MANIFEST-R33.sha256",
    "manifest_sha256": "m" * 64,
    "addendum_manifest_file": "MANIFEST-R33-ADDENDUM.sha256",
    "addendum_manifest_sha256": "n" * 64,
    "source": "conductor design folder, revision R3.3 (local, read-only)",
}


def test_matching_pins_pass() -> None:
    assert check_pins(copy.deepcopy(SECTION), copy.deepcopy(LEDGER)) == 0


def test_zeroed_extra_pin_fails(capsys: pytest.CaptureFixture[str]) -> None:
    section = copy.deepcopy(SECTION)
    section["extra"]["x.json"]["sha256"] = "0" * 64
    assert check_pins(section, copy.deepcopy(LEDGER)) > 0
    assert "PINS" in capsys.readouterr().out


def test_design_file_mismatch_fails() -> None:
    ledger = copy.deepcopy(LEDGER)
    ledger["design_file"] = "OTHER.md"
    assert check_pins(copy.deepcopy(SECTION), ledger) > 0


def test_manifest_file_mismatch_fails() -> None:
    ledger = copy.deepcopy(LEDGER)
    ledger["manifest_file"] = "MANIFEST-R31.sha256"
    assert check_pins(copy.deepcopy(SECTION), ledger) > 0


def test_addendum_manifest_sha_mismatch_fails() -> None:
    ledger = copy.deepcopy(LEDGER)
    ledger["addendum_manifest_sha256"] = "0" * 64
    assert check_pins(copy.deepcopy(SECTION), ledger) > 0


def test_backslash_lock_key_fails() -> None:
    ledger = copy.deepcopy(LEDGER)
    ledger["files"] = {k.replace("/", "\\"): v for k, v in ledger["files"].items()}
    assert check_pins(copy.deepcopy(SECTION), ledger) > 0


def test_real_repo_pins_pass() -> None:
    section = contract_section(SYNC.load_pins())
    ledger = json.loads((ROOT / "CONTRACTS.lock").read_text(encoding="utf-8"))
    assert check_pins(section, ledger) == 0


def test_real_unicode_case_pins_pass() -> None:
    pins = SYNC.load_pins()
    ledger = json.loads((ROOT / "CONTRACTS.lock").read_text(encoding="utf-8"))
    assert check_unicode_case(pins, ledger) == 0


def test_unicode_case_tampered_lock_fails(capsys: pytest.CaptureFixture[str]) -> None:
    pins = SYNC.load_pins()
    ledger = json.loads((ROOT / "CONTRACTS.lock").read_text(encoding="utf-8"))
    locked = ledger["unicode-case"]["files"]
    locked["contracts/unicode-case/15.0.0/case-table.json"] = "0" * 64
    assert check_unicode_case(pins, ledger) > 0
    assert "PINS" in capsys.readouterr().out or "MODIFIED" in capsys.readouterr().out


def test_unicode_case_missing_section_fails() -> None:
    ledger = json.loads((ROOT / "CONTRACTS.lock").read_text(encoding="utf-8"))
    assert check_unicode_case({}, ledger) > 0
    assert check_unicode_case(SYNC.load_pins(), {}) > 0


def test_real_self_hosted_dispatch_passes() -> None:
    pins = SYNC.load_pins()
    ledger = json.loads((ROOT / "CONTRACTS.lock").read_text(encoding="utf-8"))
    assert check_self_hosted(pins, ledger) == 0


def test_f1_tampered_lock_fails(capsys: pytest.CaptureFixture[str]) -> None:
    pins = SYNC.load_pins()
    ledger = json.loads((ROOT / "CONTRACTS.lock").read_text(encoding="utf-8"))
    locked = ledger["f1-extensions"]["files"]
    first = min(locked)
    locked[first] = "0" * 64
    assert check_f1_from_pins(pins, ledger) > 0
    assert check_self_hosted(pins, ledger) > 0
    assert "F1" in capsys.readouterr().out


def test_f1_missing_section_fails() -> None:
    ledger = json.loads((ROOT / "CONTRACTS.lock").read_text(encoding="utf-8"))
    assert check_f1_from_pins({}, ledger) > 0
    assert check_f1_from_pins(SYNC.load_pins(), {}) > 0


def test_self_hosted_reports_either_side() -> None:
    pins = SYNC.load_pins()
    ledger = json.loads((ROOT / "CONTRACTS.lock").read_text(encoding="utf-8"))
    bad_pins = copy.deepcopy(pins)
    del bad_pins["unicode-case"]
    assert check_self_hosted(bad_pins, ledger) > 0
    bad_ledger = copy.deepcopy(ledger)
    del bad_ledger["f1-extensions"]
    assert check_self_hosted(pins, bad_ledger) > 0
