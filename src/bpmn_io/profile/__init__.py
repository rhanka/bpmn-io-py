"""Neutral profile mechanism (DESIGN R3.3, binding signatures).

Implements profile loading, compilation and evaluation over the native
moddle tree, canonical bytes, identities, compatibility, envelopes, results
and the headless native bridge. The ``lint`` entry point is re-exported
lazily so this package imports without the parallel lint lane.
"""

from __future__ import annotations

from bpmn_io.profile._c14n import digest, digest_bytes, jcs, jcs_bytes
from bpmn_io.profile._lexical import LexicalError, LexicalOk, check_lexical
from bpmn_io.profile._schema import CLOSED_KEYWORDS, SchemaRefusal, validate
from bpmn_io.profile._stable_id import STABLE_ID_PREFIX, allocate_stable_id
from bpmn_io.profile._unicode_case import (
    UNICODE_VERSION_PIN,
    apply_case,
    lower_full,
    upper_full,
)

__all__ = [
    "CLOSED_KEYWORDS",
    "STABLE_ID_PREFIX",
    "UNICODE_VERSION_PIN",
    "LexicalError",
    "LexicalOk",
    "SchemaRefusal",
    "allocate_stable_id",
    "apply_case",
    "check_lexical",
    "digest",
    "digest_bytes",
    "jcs",
    "jcs_bytes",
    "lint",
    "lower_full",
    "upper_full",
    "validate",
]


def lint(*a: object, **k: object) -> object:
    """Profile lint entry point owned by the parallel lane (lazy import)."""
    from ._lint import lint as _l  # type: ignore[import-not-found]  # noqa: PLC0415

    return _l(*a, **k)
