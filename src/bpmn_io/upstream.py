"""Upstream bpmn.io versions this release transposes (kept in sync with ``UPSTREAM.toml``)."""

from __future__ import annotations

from typing import Final

#: npm package name -> exact upstream version whose algorithms and tests this package ports.
UPSTREAM_VERSIONS: Final[dict[str, str]] = {
    "saxen": "11.2.0",
    "min-dash": "5.1.0",
    "moddle": "8.2.1",
    "moddle-xml": "12.3.1",
    "bpmn-moddle": "10.3.1",
    "bpmn-auto-layout": "1.3.0",
}
