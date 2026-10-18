# DESIGN R3.3 §6.4 + §10.1 (Report/2): unified lint entries.
"""Unified report entries for the profile lint bridge.

Standard findings keep their rule identity (``ruleId`` ``r``, code
``bpmnlint/r``, message key ``bpmnlint.r``); profile subfindings keep
theirs (``ruleId`` ``profile:<id>``, the rule ``code`` / ``message`` key);
adapter conditions use ``ruleId`` ``adapter`` with the stable outcome code
as both code and message key. Severity and classification always come from
the exact effective policy row — never from the transported upstream
category. Entries merge by ``(origin, ruleId, code, targetId,
sourcePointer, stage)``; exact duplicates coalesce. Counts run over
unresolved ``info`` / ``warn`` / ``error`` entries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bpmn_io._js import UNDEFINED
from bpmn_io.profile._lint.c14n import utf16_key
from bpmn_io.profile._lint.errors import ADAPTER_RULE_ID
from bpmn_io.profile._lint.index import resolve_pointer
from bpmn_io.profile._lint.plugin import RULE_ID as TRANSPORT_RULE_ID

__all__ = [
    "Finding",
    "adapter_entry",
    "build_unified",
    "entry_of",
    "merge_key",
    "profile_entry",
    "sort_entries",
    "standard_entry",
    "to_jsonable",
]


def to_jsonable(value: Any) -> Any:  # noqa: ANN401 - upstream report content
    """Convert raw upstream reports to JSON-safe data (``JSON.stringify`` semantics).

    Object keys whose value is ``UNDEFINED`` are omitted; ``UNDEFINED``
    array entries become ``None``. The library report path keeps the live
    values; only the serialized ``rawStandardFindings`` convert.
    """
    if value is UNDEFINED:
        return None
    if isinstance(value, dict):
        return {key: to_jsonable(entry) for key, entry in value.items() if entry is not UNDEFINED}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(entry) for entry in value]
    return value


#: Finding origins used by the merge key (DESIGN R3.3 §6.4).
ORIGIN_STANDARD = "standard"
ORIGIN_PROFILE = "profile"
ORIGIN_ADAPTER = "adapter"

#: Upstream category of a rule that threw during evaluation.
_RULE_ERROR_CATEGORY = "rule-error"


@dataclass(frozen=True)
class Finding:
    """One normalized finding; :func:`entry_of` renders its exact entry."""

    rule_id: str
    code: str
    message_key: str
    severity: str
    classification: str
    stage: str
    pointer: str | None
    target_id: str | None
    provenance: str
    disposition: str
    domain: str = "tree"


def entry_of(finding: Finding) -> dict[str, Any]:
    """Render the exact Report/2 entry shape of one normalized finding."""
    coordinates = {
        "domain": finding.domain,
        "pointer": finding.pointer,
        "targetId": finding.target_id,
        "provenance": finding.provenance,
    }
    return {
        "code": finding.code,
        "severity": finding.severity,
        "classification": finding.classification,
        "stage": finding.stage,
        "ruleId": finding.rule_id,
        "messageKey": finding.message_key,
        "disposition": finding.disposition,
        "source": coordinates,
        "result": dict(coordinates),
        "beforePresent": False,
        "afterPresent": False,
    }


def profile_entry(  # noqa: PLR0913 - Report/2 constructors carry the exact entry field set
    *,
    profile_rule_id: str,
    code: str,
    message_key: str,
    severity: str,
    classification: str,
    stage: str,
    pointer: str | None,
    target_id: str | None,
    provenance: str,
) -> dict[str, Any]:
    """Build the unified entry of one validated profile subfinding."""
    return entry_of(
        Finding(
            rule_id=profile_rule_id,
            code=code,
            message_key=message_key,
            severity=severity,
            classification=classification,
            stage=stage,
            pointer=pointer,
            target_id=target_id,
            provenance=provenance,
            disposition="observed",
        )
    )


def standard_entry(  # noqa: PLR0913 - Report/2 constructors carry the exact entry field set
    *,
    rule_name: str,
    severity: str,
    classification: str,
    stage: str,
    pointer: str | None,
    target_id: str | None,
    provenance: str,
) -> dict[str, Any]:
    """Build the unified entry of one standard upstream finding."""
    return entry_of(
        Finding(
            rule_id=rule_name,
            code=f"bpmnlint/{rule_name}",
            message_key=f"bpmnlint.{rule_name}",
            severity=severity,
            classification=classification,
            stage=stage,
            pointer=pointer,
            target_id=target_id,
            provenance=provenance,
            disposition="observed",
        )
    )


def adapter_entry(code: str, *, stage: str, disposition: str = "observed") -> dict[str, Any]:
    """Build an adapter-origin entry (stable code as code and message key)."""
    return entry_of(
        Finding(
            rule_id=ADAPTER_RULE_ID,
            code=code,
            message_key=code,
            severity="error",
            classification="integrity",
            stage=stage,
            pointer=None,
            target_id=None,
            provenance="unavailable",
            disposition=disposition,
            domain="none",
        )
    )


def merge_key(entry: dict[str, Any], origin: str) -> tuple[str, str, str, str, str, str]:
    """Return the merge identity of an entry (DESIGN R3.3 §6.4).

    Findings from different stages never merge; translated message strings
    never merge either (the key carries the stable code, not text).
    """
    source = entry.get("source")
    pointer = source.get("pointer") if isinstance(source, dict) else None
    target = source.get("targetId") if isinstance(source, dict) else None
    return (
        origin,
        str(entry.get("ruleId")),
        str(entry.get("code")),
        target if isinstance(target, str) else "",
        pointer if isinstance(pointer, str) else "",
        str(entry.get("stage")),
    )


#: Execution-stage rank for the Report/2 comparator (DESIGN R3.3 §6.2
#: pipeline order, not alphabet). Unknown stages sort after the known ones.
_STAGE_RANK = {
    "import": 0,
    "pre-normalize": 1,
    "post-normalize": 2,
    "post-layout": 3,
    "release": 4,
}


def sort_entries(entries: list[dict[str, Any]], origins: list[str]) -> list[dict[str, Any]]:
    """Sort entries per the Report/2 comparator (stage rank, then UTF-16)."""
    paired = sorted(zip(entries, origins, strict=True), key=lambda pair: _sort_tuple(pair[0]))
    return [entry for entry, _ in paired]


def build_unified(
    raw: dict[str, list[dict[str, Any]]],
    *,
    phase: str,
    policy: dict[str, dict[str, str]],
    compiled_rules: dict[str, dict[str, Any]],
    index: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Build unified entries and severity counts from raw upstream reports.

    ``policy`` maps every effective rule name (standard names and
    ``profile:<id>``) to its ``{"severity", "classification"}`` row;
    ``compiled_rules`` maps ``profile:<id>`` to its compiled rule record
    for metadata validation; ``index`` resolves reported IDs. Returns
    ``(entries, counts)`` with entries merged, deduplicated and sorted.
    """
    entries: list[dict[str, Any]] = []
    origins: list[str] = []

    def _emit(entry: dict[str, Any], origin: str) -> None:
        entries.append(entry)
        origins.append(origin)

    for rule_name, reports in raw.items():
        if rule_name == TRANSPORT_RULE_ID:
            for report in reports:
                validated = _profile_report(
                    report, phase=phase, policy=policy, compiled=compiled_rules, index=index
                )
                _emit(validated, ORIGIN_PROFILE)
            continue
        row = policy.get(rule_name)
        for report in reports:
            if row is not None and _raw_category(report) != _RULE_ERROR_CATEGORY:
                _emit(
                    _standard_report(
                        report, rule_name=rule_name, phase=phase, row=row, index=index
                    ),
                    ORIGIN_STANDARD,
                )
            else:
                _emit(
                    _standard_report(
                        report, rule_name=rule_name, phase=phase, row=row, index=index
                    ),
                    ORIGIN_ADAPTER,
                )
    merged = _dedupe(entries, origins)
    ordered = sort_entries([entry for entry, _ in merged], [origin for _, origin in merged])
    counts = {"info": 0, "warn": 0, "error": 0}
    for entry in ordered:
        severity = entry.get("severity")
        if severity in counts:
            counts[severity] += 1
    return ordered, counts


def _sort_tuple(entry: dict[str, Any]) -> tuple[int, bytes, bytes, bytes, bytes]:
    """Return the Report/2 sort tuple of one entry."""
    source = entry.get("source")
    pointer = source.get("pointer") if isinstance(source, dict) else None
    target = source.get("targetId") if isinstance(source, dict) else None
    stage = str(entry.get("stage"))
    return (
        _STAGE_RANK.get(stage, len(_STAGE_RANK)),
        utf16_key(str(entry.get("ruleId"))),
        utf16_key(pointer if isinstance(pointer, str) else ""),
        utf16_key(target if isinstance(target, str) else ""),
        utf16_key(str(entry.get("code"))),
    )


def _dedupe(entries: list[dict[str, Any]], origins: list[str]) -> list[tuple[dict[str, Any], str]]:
    """Coalesce exact duplicate merge tuples, keeping the first."""
    seen: set[tuple[str, str, str, str, str, str]] = set()
    merged: list[tuple[dict[str, Any], str]] = []
    for entry, origin in zip(entries, origins, strict=True):
        key = merge_key(entry, origin)
        if key in seen:
            continue
        seen.add(key)
        merged.append((entry, origin))
    return merged


def _raw_category(report: Any) -> str | None:  # noqa: ANN401 - upstream report content
    """Read the transported upstream category of a raw report."""
    if isinstance(report, dict):
        category = report.get("category")
        return category if isinstance(category, str) else None
    return None


def _reported_id(report: Any) -> str | None:  # noqa: ANN401 - upstream report content
    """Read the reported element ID (None when absent or empty)."""
    if isinstance(report, dict):
        reported = report.get("id")
        return reported if isinstance(reported, str) and reported else None
    return None


def _standard_report(
    report: Any,  # noqa: ANN401 - upstream report content
    *,
    rule_name: str,
    phase: str,
    row: dict[str, str] | None,
    index: dict[str, str],
) -> dict[str, Any]:
    """Map one standard raw finding to its unified entry."""
    if _raw_category(report) == _RULE_ERROR_CATEGORY or row is None:
        return adapter_entry("lint-rule-error", stage=phase)
    pointer, provenance = resolve_pointer(index, _reported_id(report), report.get("path", []))
    return standard_entry(
        rule_name=rule_name,
        severity=row["severity"],
        classification=row["classification"],
        stage=phase,
        pointer=pointer,
        target_id=_reported_id(report),
        provenance=provenance,
    )


def _profile_shape(report: Any) -> tuple[str, str, str, str, str | None] | None:  # noqa: ANN401
    """Read validated subfinding metadata, or ``None`` when malformed."""
    if not isinstance(report, dict):
        return None
    if report.get("profileRuleError") is not None:
        return None
    profile_rule_id = report.get("profileRuleId")
    code = report.get("code")
    message_key = report.get("messageKey")
    source_pointer = report.get("sourcePointer")
    if not isinstance(profile_rule_id, str) or not profile_rule_id.startswith("profile:"):
        return None
    if not isinstance(code, str) or not isinstance(message_key, str):
        return None
    if not isinstance(source_pointer, str) or (
        source_pointer != "" and not source_pointer.startswith("/")
    ):
        return None
    return (profile_rule_id, code, message_key, source_pointer, _reported_id(report))


def _profile_report(
    report: Any,  # noqa: ANN401 - upstream report content
    *,
    phase: str,
    policy: dict[str, dict[str, str]],
    compiled: dict[str, dict[str, Any]],
    index: dict[str, str],
) -> dict[str, Any]:
    """Map one transport raw report to its unified entry (or rule-error)."""
    shape = _profile_shape(report)
    if shape is None:
        return adapter_entry("lint-rule-error", stage=phase)
    profile_rule_id, code, message_key, source_pointer, target_id = shape
    rule = compiled.get(profile_rule_id)
    row = policy.get(profile_rule_id)
    if (
        not isinstance(rule, dict)
        or not isinstance(row, dict)
        or code != rule.get("code")
        or message_key != rule.get("message")
    ):
        return adapter_entry("lint-rule-error", stage=phase)
    pointer: str | None = source_pointer
    if target_id is not None and target_id in index:
        if index[target_id] != source_pointer:
            return adapter_entry("lint-rule-error", stage=phase)
        provenance = "exact"
    elif target_id is None:
        provenance = "exact"
    else:
        pointer = None
        provenance = "unavailable"
    return profile_entry(
        profile_rule_id=profile_rule_id,
        code=code,
        message_key=message_key,
        severity=row["severity"],
        classification=row["classification"],
        stage=phase,
        pointer=pointer,
        target_id=target_id,
        provenance=provenance,
    )
