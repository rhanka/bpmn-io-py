"""Legacy theme and diagnostic adapters (spec §9, §13)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bpmn_io.profile._results import (
    PureRefused,
    PureResult,
    PureSuccess,
    ReportEntry,
    make_coordinate,
    sort_report_entries,
)

__all__ = ["map_legacy_diagnostics", "resolve_legacy_theme"]

Json = Any

#: Closed loss classes a fidelity notice may carry (DESIGN §10.2).
_LOSS_CLASSES = frozenset(
    {
        "semantic-type",
        "relation-kind",
        "navigation",
        "appearance",
        "layout",
        "metadata",
        "unsupported-feature",
        "provenance-unavailable",
    }
)

#: io-error codes mapped to export refusals (spec §13 table).
_IO_ERROR_CODES = {
    "unknown-format": ("export-format-unsupported", "export.format-unsupported"),
    "unsupported-format": ("export-format-unsupported", "export.format-unsupported"),
    "invalid-reference": ("reference-dangling", "reference-dangling"),
    "missing-endpoint": ("reference-dangling", "reference-dangling"),
    "duplicate-id": ("id-collision", "id-collision"),
}


def resolve_legacy_theme(compiled: object, legacy_name: str) -> PureResult:
    """Resolve one legacy look name through ``compatibilityAliases`` (spec §9).

    The unique record with ``kind:"theme"``, ``old == legacy_name``
    (exact, no case folding) and ``mode != "remove"`` gives the
    destination, which must be a theme id. Every other input refuses
    ``render-stale``.
    """
    stale = PureRefused(code="render-stale")
    profile = getattr(compiled, "profile", None)
    if not isinstance(profile, dict):
        return stale
    aliases = profile.get("compatibilityAliases")
    themes = profile.get("themes")
    if not isinstance(aliases, list) or not isinstance(themes, list):
        return stale
    theme_ids = {str(theme.get("id")) for theme in themes if isinstance(theme, dict)}
    matches = [
        record
        for record in aliases
        if isinstance(record, dict)
        and record.get("kind") == "theme"
        and record.get("old") == legacy_name
        and record.get("mode") != "remove"
    ]
    if len(matches) != 1:
        return stale
    destination = matches[0].get("destination")
    if not isinstance(destination, str) or destination not in theme_ids:
        return stale
    return PureSuccess(payload={"themeId": destination})


def _manifest_entry(
    manifest: dict[str, Json], producer: object, code: object
) -> dict[str, Json] | None:
    """Find one manifest entry by producer and legacy code."""
    records = manifest.get("entries")
    if not isinstance(records, list):
        return None
    for record in records:
        if (
            isinstance(record, dict)
            and record.get("producer") == producer
            and record.get("legacyCode") == code
        ):
            return record
    return None


def _legacy_source(
    source_index: dict[str, Json], element_id: str | None, *, mapped: bool
) -> dict[str, Json]:
    """Build one legacy entry source (exact when indexed and mapped)."""
    if element_id is None:
        return {"domain": "none", "pointer": None, "targetId": None, "provenance": "unavailable"}
    pointer = source_index.get(element_id)
    if mapped and isinstance(pointer, str):
        return {"domain": "tree", "pointer": pointer, "targetId": element_id, "provenance": "exact"}
    return {"domain": "tree", "pointer": None, "targetId": element_id, "provenance": "unavailable"}


@dataclass(frozen=True)
class _LegacyEntrySpec:
    """Field bundle for one legacy adapter entry (spec §13)."""

    code: str
    message_key: str
    classification: str
    severity: str
    disposition: str
    legacy_code: str
    source: dict[str, Json]
    loss_class: str | None = None


def _legacy_entry(spec: _LegacyEntrySpec) -> ReportEntry:
    """Build one legacy adapter entry (spec §13)."""
    return ReportEntry(
        code=spec.code,
        severity=spec.severity,  # type: ignore[arg-type]
        classification=spec.classification,  # type: ignore[arg-type]
        stage="export",
        rule_id="adapter",
        message_key=spec.message_key,
        disposition=spec.disposition,  # type: ignore[arg-type]
        source=make_coordinate(
            str(spec.source.get("domain", "none")),
            spec.source.get("pointer") if isinstance(spec.source.get("pointer"), str) else None,
            spec.source.get("targetId") if isinstance(spec.source.get("targetId"), str) else None,
            str(spec.source.get("provenance", "unavailable")),
        ),
        result=make_coordinate("none", None, None, "unavailable"),
        before_present=False,
        after_present=False,
        legacy_code=spec.legacy_code,
        loss_class=spec.loss_class,
    )


def map_legacy_diagnostics(
    legacy: object, manifest: object, *, source_index: object = None
) -> PureResult:
    """Map one legacy diagnostic record through an adapter manifest (spec §13)."""
    if not isinstance(legacy, dict) or not isinstance(manifest, dict):
        return PureSuccess(payload=[])
    index = source_index if isinstance(source_index, dict) else {}
    producer = legacy.get("producer")
    code = legacy.get("code")
    ids = legacy.get("ids", [])
    loss_class = legacy.get("lossClass")
    if not isinstance(ids, list):
        ids = []
    element_ids = [element_id for element_id in ids if isinstance(element_id, str)]
    entry_manifest = _manifest_entry(manifest, producer, code)
    targets: list[str | None] = list(element_ids) or [None]
    if not isinstance(code, str):
        return PureSuccess(payload=[])
    if producer == "io-error" and entry_manifest is not None and code in _IO_ERROR_CODES:
        mapped_code, message_key = _IO_ERROR_CODES[code]
        records = [
            _legacy_entry(
                _LegacyEntrySpec(
                    code=mapped_code,
                    message_key=message_key,
                    classification="integrity",
                    severity="error",
                    disposition="refused",
                    legacy_code=code,
                    source=_legacy_source(index, element_id, mapped=True),
                )
            )
            for element_id in targets
        ]
    elif (
        producer == "fidelity-notice"
        and entry_manifest is not None
        and isinstance(loss_class, str)
        and loss_class in _LOSS_CLASSES
        and isinstance(entry_manifest.get("lossClasses"), list)
        and loss_class in entry_manifest["lossClasses"]
    ):
        first = element_ids[0] if element_ids else None
        records = [
            _legacy_entry(
                _LegacyEntrySpec(
                    code=f"export-loss/{loss_class}",
                    message_key=f"export.loss.{loss_class}",
                    classification="loss",
                    severity="warn",
                    disposition="mapped",
                    legacy_code=code,
                    source=_legacy_source(index, first, mapped=True),
                    loss_class=loss_class,
                )
            )
        ]
    else:
        records = [
            _legacy_entry(
                _LegacyEntrySpec(
                    code="legacy-unmapped",
                    message_key="legacy.unmapped",
                    classification="integrity",
                    severity="error",
                    disposition="refused",
                    legacy_code=code,
                    source=_legacy_source(index, element_id, mapped=False),
                )
            )
            for element_id in targets
        ]
    ordered = sort_report_entries(records)
    return PureSuccess(payload=[entry.to_json() for entry in ordered])
