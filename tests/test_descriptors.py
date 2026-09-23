from __future__ import annotations

import pytest

from bpmn_io import DESCRIPTOR_NAMES, UPSTREAM_VERSIONS, __version__, load_descriptor

EXPECTED_TYPE_COUNTS = {"bpmn": 137, "bpmndi": 6, "dc": 7, "di": 11, "bioc": 2}


def test_version_is_exposed() -> None:
    assert __version__


@pytest.mark.parametrize("name", sorted(DESCRIPTOR_NAMES))
def test_descriptor_loads_with_upstream_type_count(name: str) -> None:
    descriptor = load_descriptor(name)
    assert descriptor["prefix"] == name
    assert len(descriptor["types"]) == EXPECTED_TYPE_COUNTS[name]


def test_unknown_descriptor_is_rejected() -> None:
    with pytest.raises(KeyError, match="unknown descriptor"):
        load_descriptor("nope")


def test_upstream_versions_match_pins() -> None:
    import tomllib
    from pathlib import Path

    pins = tomllib.loads((Path(__file__).parents[1] / "UPSTREAM.toml").read_text())
    assert {k: v["version"] for k, v in pins["upstream"].items()} == UPSTREAM_VERSIONS
