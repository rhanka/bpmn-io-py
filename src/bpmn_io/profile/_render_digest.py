"""Section 9.2 digest formulas (skeleton)."""

from __future__ import annotations

from bpmn_io.profile._c14n import digest

__all__ = ["view_revision"]


#: Binding members bound by the §9.2 viewRevision (UTF-16 order via H).
VIEW_REVISION_KEYS = (
    "semanticRevision",
    "layoutDigest",
    "themeId",
    "themeDigest",
    "overridesDigest",
    "diStylesDigest",
    "metricsDigest",
)


def view_revision(binding: dict[str, object]) -> str:
    """Return the §9.2 viewRevision of one render binding record."""
    return digest({key: binding[key] for key in VIEW_REVISION_KEYS})
