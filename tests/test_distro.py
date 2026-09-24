"""Packaging-bundle claims for the upstream distro checks (Lot 10).

Each upstream ``distro`` suite asserts its npm package exposes a working
bundle. The Python equivalent — building the wheel and importing it in a
fresh interpreter — runs in the CI ``build`` job ("Install-from-wheel smoke
test"), not in pytest, so every case below is claimed and skipped with the
reason stated.
"""

from __future__ import annotations

import pytest

_DISTRO_REASON = (
    "npm packaging check; covered by the CI install-from-wheel smoke test "
    "(.github/workflows/ci.yml, build job)"
)


@pytest.mark.upstream("bpmn-moddle/test/integration/distro.cjs", "should expose CJS bundle")
def test_bpmn_moddle_cjs_bundle() -> None:
    """Claimed N-A (see module docstring for the reason)."""
    pytest.skip(_DISTRO_REASON)


@pytest.mark.upstream("bpmn-moddle/test/integration/distro.cjs", "should expose ESM bundle")
def test_bpmn_moddle_esm_bundle() -> None:
    """Claimed N-A (see module docstring for the reason)."""
    pytest.skip(_DISTRO_REASON)


@pytest.mark.upstream("moddle/test/integration/distro.cjs", "should expose CJS bundle")
def test_moddle_cjs_bundle() -> None:
    """Claimed N-A (see module docstring for the reason)."""
    pytest.skip(_DISTRO_REASON)


@pytest.mark.upstream("moddle/test/integration/distro.cjs", "should expose ESM bundle")
def test_moddle_esm_bundle() -> None:
    """Claimed N-A (see module docstring for the reason)."""
    pytest.skip(_DISTRO_REASON)


@pytest.mark.upstream("moddle/test/integration/distro.ts", "should expose typed bundle")
def test_moddle_ts_typed_bundle() -> None:
    """Claimed N-A (see module docstring for the reason)."""
    pytest.skip(_DISTRO_REASON)


@pytest.mark.upstream("moddle/test/integration/distro.ts", "should expose element types")
def test_moddle_ts_element_types() -> None:
    """Claimed N-A (see module docstring for the reason)."""
    pytest.skip(_DISTRO_REASON)


@pytest.mark.upstream("moddle-xml/test/integration/distro.cjs", "should expose CJS bundle")
def test_moddle_xml_cjs_bundle() -> None:
    """Claimed N-A (see module docstring for the reason)."""
    pytest.skip(_DISTRO_REASON)


@pytest.mark.upstream("moddle-xml/test/integration/distro.cjs", "should expose ESM bundle")
def test_moddle_xml_esm_bundle() -> None:
    """Claimed N-A (see module docstring for the reason)."""
    pytest.skip(_DISTRO_REASON)
