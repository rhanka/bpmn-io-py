"""Sanity checks for the upstream Node oracle environment (run with ``pytest -m oracle``)."""

from __future__ import annotations

import json
import shutil
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
ORACLE = ROOT / "tests" / "oracle"

pytestmark = pytest.mark.oracle


@pytest.fixture(scope="session", autouse=True)
def _require_node() -> None:
    if shutil.which("node") is None or not (ORACLE / "node_modules").is_dir():
        pytest.skip("oracle needs node and `npm ci` in tests/oracle")


def test_oracle_pins_match_upstream_toml() -> None:
    package = json.loads((ORACLE / "package.json").read_text())["dependencies"]
    pins = tomllib.loads((ROOT / "UPSTREAM.toml").read_text())["upstream"]
    for name, version in package.items():
        assert pins[name]["version"] == version, f"{name}: oracle {version} != UPSTREAM.toml"


def test_oracle_packages_installed_at_pinned_versions() -> None:
    package = json.loads((ORACLE / "package.json").read_text())["dependencies"]
    for name, version in package.items():
        installed = json.loads((ORACLE / "node_modules" / name / "package.json").read_text())
        assert installed["version"] == version
