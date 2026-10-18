"""Severity normalization and the info-through-warn transport (DESIGN R3.3 section 6.3)."""

from __future__ import annotations

import pytest

from bpmn_io.profile._lint.errors import ProfileDataError
from bpmn_io.profile._lint.severity import normalize_severity, transport_severity


def test_words_resolve_case_insensitively() -> None:
    """Severity words resolve to their lowercase effective form."""
    assert normalize_severity("error") == "error"
    assert normalize_severity("Warn") == "warn"
    assert normalize_severity("OFF") == "off"
    assert normalize_severity("info") == "info"


def test_ascii_fold_is_exact_and_non_ascii_refuses() -> None:
    """ASCII casing folds to the word; non-ASCII letters never fold to one."""
    assert normalize_severity("Error") == "error"
    assert normalize_severity("InFo") == "info"
    for bad in ("οff", "İNFO", "oﬀ", "errοr"):  # noqa: RUF001 - non-ASCII fold boundary
        with pytest.raises(ProfileDataError):
            normalize_severity(bad)


def test_numerics_resolve() -> None:
    """Numeric severities resolve 0=off, 1=warn, 2=error, 3=info."""
    assert [normalize_severity(n) for n in (0, 1, 2, 3)] == ["off", "warn", "error", "info"]
    assert normalize_severity(1.0) == "warn"


def test_invalid_severities_refuse() -> None:
    """Booleans, out-of-range and non-integral severities refuse."""
    for bad in (True, False, 4, -1, 1.5, "warning", "", None, ["error"]):
        with pytest.raises(ProfileDataError):
            normalize_severity(bad)


def test_info_travels_as_warn() -> None:
    """Effective info is transported as warn and restored by the adapter."""
    assert transport_severity("info") == "warn"
    assert transport_severity("error") == "error"
    assert transport_severity("warn") == "warn"
    assert transport_severity("off") == "off"
