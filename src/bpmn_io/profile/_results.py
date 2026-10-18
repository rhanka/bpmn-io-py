"""Closed operation results and coordinates (DESIGN R3.3 §10.1).

Pure operations return ``PureResult``; document operations return ``Result``.
``Report/2`` entries carry exact coordinates, presence flags and deterministic
UTF-16 ordering. Wire field names stay exactly DESIGN's.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from bpmn_io.profile._c14n import jcs

__all__ = [
    "CAPABILITY_ORDER",
    "Coordinate",
    "PureRefused",
    "PureResult",
    "PureSuccess",
    "Report",
    "ReportEntry",
    "ResultRefused",
    "ResultSuccess",
    "escape_pointer",
    "make_coordinate",
    "make_report",
    "pure_refused",
    "pure_success",
    "result_refused",
    "result_success",
    "sort_id_map",
    "sort_report_entries",
    "worst_capability",
]

#: Capability ordering, best to worst.
CAPABILITY_ORDER: tuple[str, ...] = (
    "engine-byte-compatible",
    "structural",
    "unsupported",
)

_SEVERITIES = frozenset({"info", "warn", "error"})
_CLASSIFICATIONS = frozenset({"integrity", "readiness", "repairable", "advisory", "loss"})
_DISPOSITIONS = frozenset({"observed", "corrected", "dropped", "mapped", "refused"})
_DOMAINS = frozenset({"tree", "profile", "artifact", "none"})
_PROVENANCES = frozenset({"exact", "unavailable", "generated"})


@dataclass(frozen=True)
class Coordinate:
    """One source or result coordinate (DESIGN §10.1)."""

    domain: Literal["tree", "profile", "artifact", "none"]
    pointer: str | None
    target_id: str | None
    provenance: Literal["exact", "unavailable", "generated"]

    def to_json(self) -> dict[str, object]:
        """Return the wire representation with DESIGN field names."""
        return {
            "domain": self.domain,
            "pointer": self.pointer,
            "targetId": self.target_id,
            "provenance": self.provenance,
        }


@dataclass(frozen=True)
class ReportEntry:
    """One unified ``Report/2`` entry with exact coordinates."""

    code: str
    severity: Literal["info", "warn", "error"]
    classification: Literal["integrity", "readiness", "repairable", "advisory", "loss"]
    stage: str
    rule_id: str
    message_key: str
    disposition: Literal["observed", "corrected", "dropped", "mapped", "refused"]
    source: Coordinate
    result: Coordinate
    before_present: bool
    after_present: bool
    before: object = None
    after: object = None
    original_type: str | None = None
    property: str | None = None
    caused_by: str | None = None
    page_id: str | None = None
    occurrence_key: str | None = None
    emitted_type: str | None = None
    legacy_code: str | None = None
    loss_class: str | None = None

    def to_json(self) -> dict[str, object]:  # noqa: C901
        """Return the wire representation with DESIGN field names."""
        payload: dict[str, object] = {
            "code": self.code,
            "severity": self.severity,
            "classification": self.classification,
            "stage": self.stage,
            "ruleId": self.rule_id,
            "messageKey": self.message_key,
            "disposition": self.disposition,
            "source": self.source.to_json(),
            "result": self.result.to_json(),
            "beforePresent": self.before_present,
            "afterPresent": self.after_present,
        }
        if self.before_present:
            payload["before"] = self.before
        if self.after_present:
            payload["after"] = self.after
        if self.original_type is not None:
            payload["originalType"] = self.original_type
        if self.property is not None:
            payload["property"] = self.property
        if self.caused_by is not None:
            payload["causedBy"] = self.caused_by
        if self.page_id is not None:
            payload["pageId"] = self.page_id
        if self.occurrence_key is not None:
            payload["occurrenceKey"] = self.occurrence_key
        if self.emitted_type is not None:
            payload["emittedType"] = self.emitted_type
        if self.legacy_code is not None:
            payload["legacyCode"] = self.legacy_code
        if self.loss_class is not None:
            payload["lossClass"] = self.loss_class
        return payload


@dataclass(frozen=True)
class Report:
    """Unified ``Report/2`` container."""

    operation: str
    entries: tuple[ReportEntry, ...] = ()
    raw_standard_findings: tuple[object, ...] = ()
    id_map: tuple[dict[str, object], ...] = ()
    artifacts: tuple[dict[str, object], ...] = ()
    source_identity: dict[str, object] | None = None
    target_identity: dict[str, object] | None = None
    input_revision: str | None = None
    output_revision: str | None = None

    def to_json(self) -> dict[str, object]:
        """Return the wire representation."""
        payload: dict[str, object] = {
            "reportVersion": "2",
            "operation": self.operation,
            "entries": [entry.to_json() for entry in sort_report_entries(self.entries)],
            "rawStandardFindings": list(self.raw_standard_findings),
            "idMap": list(sort_id_map(self.id_map)),
            "artifacts": list(self.artifacts),
        }
        if self.source_identity is not None:
            payload["sourceIdentity"] = self.source_identity
        if self.target_identity is not None:
            payload["targetIdentity"] = self.target_identity
        if self.input_revision is not None:
            payload["inputRevision"] = self.input_revision
        if self.output_revision is not None:
            payload["outputRevision"] = self.output_revision
        return payload


@dataclass(frozen=True)
class PureSuccess:
    """Successful pure operation result."""

    payload: object
    diagnostics: tuple[object, ...] = ()
    status: str = "ok"

    def to_json(self) -> dict[str, object]:
        """Return the wire representation."""
        return {
            "status": "ok",
            "payload": self.payload,
            "diagnostics": list(self.diagnostics),
        }


@dataclass(frozen=True)
class PureRefused:
    """Refused pure operation result."""

    code: str
    diagnostics: tuple[object, ...] = ()
    status: str = "refused"

    def to_json(self) -> dict[str, object]:
        """Return the wire representation."""
        return {
            "status": "refused",
            "code": self.code,
            "diagnostics": list(self.diagnostics),
        }


#: Pure operation outcome union.
PureResult = PureSuccess | PureRefused


@dataclass(frozen=True)
class ResultSuccess:
    """Successful document operation result."""

    operation: str
    profile_identity: dict[str, object]
    base_revision: str
    revision: str
    report: Report
    payload: object
    status: str = "ok"

    def to_json(self) -> dict[str, object]:
        """Return the wire representation."""
        return {
            "status": "ok",
            "operation": self.operation,
            "profileIdentity": self.profile_identity,
            "baseRevision": self.base_revision,
            "revision": self.revision,
            "report": self.report.to_json(),
            "payload": self.payload,
        }


@dataclass(frozen=True)
class ResultRefused:
    """Refused document operation result (no committed candidate)."""

    operation: str
    code: str
    diagnostics: tuple[object, ...]
    report: Report
    profile_identity: dict[str, object] | None = None
    base_revision: str | None = None
    status: str = "refused"

    def to_json(self) -> dict[str, object]:
        """Return the wire representation."""
        payload: dict[str, object] = {
            "status": "refused",
            "operation": self.operation,
            "code": self.code,
            "diagnostics": list(self.diagnostics),
            "report": self.report.to_json(),
        }
        if self.profile_identity is not None:
            payload["profileIdentity"] = self.profile_identity
        if self.base_revision is not None:
            payload["baseRevision"] = self.base_revision
        return payload


def pure_success(payload: object, diagnostics: tuple[object, ...] = ()) -> PureSuccess:
    """Build one successful pure result."""
    return PureSuccess(payload=payload, diagnostics=diagnostics)


def pure_refused(code: str, diagnostics: tuple[object, ...] = ()) -> PureRefused:
    """Build one refused pure result."""
    return PureRefused(code=code, diagnostics=diagnostics)


def result_success(  # noqa: PLR0913, PLR0917
    operation: str,
    profile_identity: dict[str, object],
    base_revision: str,
    revision: str,
    report: Report,
    payload: object,
) -> ResultSuccess:
    """Build one successful document result."""
    return ResultSuccess(
        operation=operation,
        profile_identity=profile_identity,
        base_revision=base_revision,
        revision=revision,
        report=report,
        payload=payload,
    )


def result_refused(  # noqa: PLR0913, PLR0917
    operation: str,
    code: str,
    report: Report,
    diagnostics: tuple[object, ...] = (),
    profile_identity: dict[str, object] | None = None,
    base_revision: str | None = None,
) -> ResultRefused:
    """Build one refused document result."""
    return ResultRefused(
        operation=operation,
        code=code,
        diagnostics=diagnostics,
        report=report,
        profile_identity=profile_identity,
        base_revision=base_revision,
    )


def escape_pointer(path: str) -> str:
    """Escape one RFC 6901 pointer segment set (``~`` then ``/``)."""
    return path.replace("~", "~0").replace("/", "~1")


def make_pointer(segments: list[str]) -> str:
    """Build one RFC 6901 pointer from unescaped segments."""
    if not segments:
        return ""
    return "/" + "/".join(escape_pointer(part) for part in segments)


def make_coordinate(
    domain: str,
    pointer: str | None,
    target_id: str | None,
    provenance: str,
) -> Coordinate:
    """Build one coordinate, validating its closed vocabularies."""
    if domain not in _DOMAINS:
        message = f"unknown coordinate domain {domain!r}"
        raise ValueError(message)
    if provenance not in _PROVENANCES:
        message = f"unknown provenance {provenance!r}"
        raise ValueError(message)
    return Coordinate(
        domain=domain,  # type: ignore[arg-type]
        pointer=pointer,
        target_id=target_id,
        provenance=provenance,  # type: ignore[arg-type]
    )


def make_report(operation: str, entries: list[ReportEntry] | None = None) -> Report:
    """Build one empty report for ``operation``."""
    return Report(operation=operation, entries=tuple(entries or ()))


def _entry_sort_key(entry: ReportEntry) -> tuple[str, ...]:
    """Return the deterministic UTF-16 sort key for one entry."""
    source_pointer = entry.source.pointer or ""
    return (
        entry.stage,
        entry.rule_id,
        entry.source.domain,
        source_pointer,
        entry.source.target_id or "",
        entry.code,
        entry.page_id or "",
        entry.occurrence_key or "",
        jcs(entry.before) if entry.before_present else "",
        jcs(entry.after) if entry.after_present else "",
    )


def sort_report_entries(
    entries: tuple[ReportEntry, ...] | list[ReportEntry],
) -> list[ReportEntry]:
    """Sort entries by stage, rule, coordinates and canonical values."""
    ranked = sorted(entries, key=_entry_sort_key)
    return sorted(
        ranked,
        key=lambda e: (
            e.stage.encode("utf-16-be"),
            e.rule_id.encode("utf-16-be"),
            (e.source.pointer or "").encode("utf-16-be"),
            (e.source.target_id or "").encode("utf-16-be"),
            e.code.encode("utf-16-be"),
        ),
    )


def sort_id_map(
    rows: tuple[dict[str, object], ...] | list[dict[str, object]],
) -> list[dict[str, object]]:
    """Sort idMap rows by domain, page, key and ids in UTF-16 order."""

    def _key(row: dict[str, object]) -> tuple[bytes, ...]:
        def _enc(value: object) -> bytes:
            return str(value or "").encode("utf-16-be")

        # Absent page/occurrence keys sort before present ones.
        page_absent = b"\x00" if row.get("pageId") is None else b"\x01"
        key_absent = b"\x00" if row.get("occurrenceKey") is None else b"\x01"
        return (
            _enc(row.get("domain")),
            page_absent,
            _enc(row.get("pageId")),
            key_absent,
            _enc(row.get("occurrenceKey")),
            _enc(row.get("sourceId")),
            _enc(row.get("resultId")),
        )

    return sorted(rows, key=_key)


def worst_capability(values: list[str]) -> str:
    """Return the worst capability outcome (unsupported wins)."""
    rank = {name: index for index, name in enumerate(CAPABILITY_ORDER)}
    worst = "engine-byte-compatible"
    for value in values:
        if rank.get(value, -1) >= rank.get(worst, -1):
            worst = value
    if worst not in CAPABILITY_ORDER:
        message = f"unknown capability {worst!r}"
        raise ValueError(message)
    return worst
