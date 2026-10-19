"""Terminal serialization of prepared artifacts (DESIGN R3.3 §10.2, spec §11).

`serialize_prepared` revalidates one PreparedArtifact against its echoed
binding, then writes deterministic structural XML (`drawio/1`, shared by
`sparx/1`; DESIGN fixes no engine bytes). Refusal returns the §3.4 record
with no bytes.
"""

from __future__ import annotations

import copy
from typing import Any

from bpmn_io.profile._c14n import digest_bytes
from bpmn_io.profile._export import ADAPTERS
from bpmn_io.profile._render_digest import descriptor_digest, view_revision
from bpmn_io.profile._results import (
    Coordinate,
    ReportEntry,
    ResultRefused,
    ResultSuccess,
    make_coordinate,
    refused_result,
    report_with_header,
)

__all__ = ["serialize_prepared"]

Json = Any

#: Canonical writer attribute order (a reordered sequence is invalid).
_ATTRIBUTE_ORDER = ("id", "value", "style", "parent", "vertex", "edge", "source", "target")

#: Admitted writer versions (all three write the same structural bytes).
_WRITER_VERSIONS = ("1.0", "fixture-1", "lot4-2")

#: Layer cell id (mapped to `$layer` by the structure projection).
_LAYER_ID = "layer"


def _coordinate_from_json(record: object) -> Coordinate | None:
    """Restore one coordinate record (None when malformed)."""
    if not isinstance(record, dict):
        return None
    domain = record.get("domain")
    pointer = record.get("pointer")
    target_id = record.get("targetId")
    provenance = record.get("provenance")
    if (
        not isinstance(domain, str)
        or (pointer is not None and not isinstance(pointer, str))
        or (target_id is not None and not isinstance(target_id, str))
        or not isinstance(provenance, str)
    ):
        return None
    try:
        return make_coordinate(domain, pointer, target_id, provenance)
    except ValueError:
        return None


def _entry_from_json(record: object) -> ReportEntry | None:
    """Restore one report entry record (None when malformed)."""
    if not isinstance(record, dict):
        return None
    source = _coordinate_from_json(record.get("source"))
    result = _coordinate_from_json(record.get("result"))
    code = record.get("code")
    severity = record.get("severity")
    classification = record.get("classification")
    stage = record.get("stage")
    rule_id = record.get("ruleId")
    message_key = record.get("messageKey")
    disposition = record.get("disposition")
    if (
        source is None
        or result is None
        or not isinstance(code, str)
        or not isinstance(severity, str)
        or not isinstance(classification, str)
        or not isinstance(stage, str)
        or not isinstance(rule_id, str)
        or not isinstance(message_key, str)
        or not isinstance(disposition, str)
    ):
        return None
    legacy_code = record.get("legacyCode")
    loss_class = record.get("lossClass")
    if severity not in ("info", "warn", "error"):
        return None
    if classification not in ("integrity", "readiness", "repairable", "advisory", "loss"):
        return None
    if disposition not in ("observed", "corrected", "dropped", "mapped", "refused"):
        return None
    return ReportEntry(
        code=code,
        severity=severity,  # type: ignore[arg-type]
        classification=classification,  # type: ignore[arg-type]
        stage=stage,
        rule_id=rule_id,
        message_key=message_key,
        disposition=disposition,  # type: ignore[arg-type]
        source=source,
        result=result,
        before_present=bool(record.get("beforePresent", False)),
        after_present=bool(record.get("afterPresent", False)),
        page_id=record.get("pageId") if isinstance(record.get("pageId"), str) else None,
        occurrence_key=record.get("occurrenceKey")
        if isinstance(record.get("occurrenceKey"), str)
        else None,
        emitted_type=record.get("emittedType")
        if isinstance(record.get("emittedType"), str)
        else None,
        legacy_code=legacy_code if isinstance(legacy_code, str) else None,
        loss_class=loss_class if isinstance(loss_class, str) else None,
    )


def _check_writer_options(options: object) -> str | None:
    """Validate pinned writer options (refusal code or None, spec §11)."""
    if not isinstance(options, dict):
        return "serialize-options-invalid"
    version = options.get("version")
    encoding = options.get("encoding")
    newline = options.get("newline")
    indent = options.get("indent")
    compression = options.get("compression")
    attribute_order = options.get("attributeOrder")
    empty_element = options.get("emptyElement")
    if (
        not isinstance(version, str)
        or version not in _WRITER_VERSIONS
        or encoding != "UTF-8"
        or newline != "LF"
        or type(indent) is not int
        or indent != 0
        or compression != "none"
        or not isinstance(attribute_order, list)
        or any(not isinstance(entry, str) for entry in attribute_order)
        or (len(attribute_order) > 0 and list(attribute_order) != list(_ATTRIBUTE_ORDER))
        or empty_element != "short"
    ):
        return "serialize-options-invalid"
    known = {
        "version",
        "encoding",
        "newline",
        "indent",
        "compression",
        "attributeOrder",
        "emptyElement",
    }
    if any(key not in known or options.get(key) is None for key in options):
        return "serialize-options-invalid"
    return None


def _escape_attribute(value: str) -> str:
    """Escape one XML attribute value (minimal well-formed set)."""
    return (
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _cell_attributes(record: dict[str, Json], page_ids: set[str]) -> list[tuple[str, str]]:
    """Build one mxCell's ordered attributes (id first, canonical order)."""
    kind = record.get("kind")
    attributes: dict[str, str] = {}
    record_id = record.get("id")
    if isinstance(record_id, str):
        attributes["id"] = record_id
    if (kind == "node" and isinstance(record.get("name"), str)) or (
        kind == "edge" and isinstance(record.get("name"), str)
    ):
        attributes["value"] = record["name"]
    elif kind == "label" and isinstance(record.get("text"), str):
        attributes["value"] = record["text"]
    parent = record.get("parent")
    if isinstance(parent, str):
        attributes["parent"] = _LAYER_ID if parent in page_ids else parent
    if kind in ("node", "label"):
        attributes["vertex"] = "1"
    elif kind == "edge":
        attributes["edge"] = "1"
        source = record.get("source")
        target = record.get("target")
        if isinstance(source, str):
            attributes["source"] = source
        if isinstance(target, str):
            attributes["target"] = target
    return [(name, attributes[name]) for name in _ATTRIBUTE_ORDER if name in attributes]


def _geometry_attributes(record: dict[str, Json]) -> list[tuple[str, str]]:
    """Build one mxGeometry's attributes from copied R bounds."""
    bounds = record.get("bounds")
    if not isinstance(bounds, dict):
        return []
    attributes: list[tuple[str, str]] = []
    for name in ("x", "y", "width", "height"):
        value = bounds.get(name)
        if type(value) is int:
            attributes.append((name, str(value)))
    return attributes


def _write_cell(record: dict[str, Json], page_ids: set[str], lines: list[str]) -> None:
    """Write one mxCell with its mxGeometry child."""
    parts = [
        f'{name}="{_escape_attribute(value)}"' for name, value in _cell_attributes(record, page_ids)
    ]
    geometry = _geometry_attributes(record)
    if geometry:
        lines.append(f"<mxCell {' '.join(parts)}>")
        inner = " ".join(f'{name}="{value}"' for name, value in geometry)
        lines.append(f"<mxGeometry {inner} />")
        lines.append("</mxCell>")
    else:
        lines.append(f"<mxCell {' '.join(parts)} />")


def _page_owner_map(ir: list[dict[str, Json]]) -> dict[str, str]:
    """Map non-page record ids to their owning page through parent links."""
    table = {str(record.get("id")): record for record in ir if isinstance(record.get("id"), str)}
    page_of: dict[str, str] = {}
    for record in ir:
        if not isinstance(record, dict) or record.get("kind") == "page":
            continue
        record_id = record.get("id")
        if not isinstance(record_id, str):
            continue
        owner: object = record.get("parent")
        seen = 0
        while isinstance(owner, str) and seen < len(ir) + 1:
            seen += 1
            parent = table.get(owner)
            if parent is None:
                break
            if parent.get("kind") == "page":
                page_of[record_id] = str(parent.get("id"))
                break
            owner = parent.get("parent")
    return page_of


def _write_drawio(ir: list[dict[str, Json]]) -> str | None:
    """Write one structural mxfile document (None when unresolvable)."""
    page_of = _page_owner_map(ir)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<mxfile>"]
    pages = [record for record in ir if isinstance(record, dict) and record.get("kind") == "page"]
    page_ids = {str(page.get("id")) for page in pages if isinstance(page.get("id"), str)}
    for page in pages:
        page_id = page.get("id")
        name = page.get("name")
        if not isinstance(page_id, str):
            return None
        head = f'<diagram id="{_escape_attribute(page_id)}"'
        if isinstance(name, str):
            head += f' name="{_escape_attribute(name)}"'
        head += ">"
        lines.append(head)
        lines.append(f'<mxCell id="{_LAYER_ID}" />')
        for record in ir:
            if not isinstance(record, dict) or record.get("kind") in ("page", "metadata"):
                continue
            record_id = record.get("id")
            if not isinstance(record_id, str) or page_of.get(record_id) != page_id:
                continue
            _write_cell(record, page_ids, lines)
        lines.append("</diagram>")
    lines.append("</mxfile>")
    return "\n".join(lines) + "\n"


def _serialize_checked(
    candidate: dict[str, Json],
) -> tuple[dict[str, Json] | None, str | None]:
    """Validate one prepared candidate (checked record, code)."""
    identity = candidate.get("profileIdentity")
    format_name = candidate.get("format")
    if not isinstance(format_name, str) or format_name not in ADAPTERS:
        return None, "export-format-unsupported"
    binding = candidate.get("binding", candidate.get("renderBinding"))
    if not isinstance(binding, dict):
        return None, "render-stale"
    view = candidate.get("viewRevision")
    semantic = candidate.get("semanticRevision")
    profile_digest = identity.get("sha256") if isinstance(identity, dict) else None
    descriptors = identity.get("descriptors") if isinstance(identity, dict) else None
    try:
        fresh_view = view_revision(binding)
        fresh_descriptor = descriptor_digest(descriptors) if isinstance(descriptors, list) else None
    except Exception:  # noqa: BLE001 - malformed binding pins are stale input
        return None, "render-stale"
    if (
        view != fresh_view
        or semantic != binding.get("semanticRevision")
        or profile_digest != binding.get("profileDigest")
        or fresh_descriptor is None
        or fresh_descriptor != binding.get("descriptorDigest")
    ):
        return None, "render-stale"
    records = candidate.get("ir")
    capability = candidate.get("capability")
    id_map = candidate.get("idMap")
    report = candidate.get("report")
    if (
        not isinstance(records, list)
        or not isinstance(capability, str)
        or not isinstance(id_map, list)
        or not isinstance(report, dict)
    ):
        return None, "render-stale"
    return (
        {
            "format": format_name,
            "records": records,
            "capability": capability,
            "idMap": id_map,
            "report": report,
        },
        None,
    )


def serialize_prepared(
    prepared: object, pinned_writer_options: object
) -> ResultSuccess | ResultRefused:
    """Serialize one prepared artifact to structural bytes (spec §11)."""
    candidate = copy.deepcopy(prepared) if isinstance(prepared, dict) else {}
    identity = candidate.get("profileIdentity")
    revision = candidate.get("semanticRevision")
    options_code = _check_writer_options(pinned_writer_options)
    if options_code is not None:
        return refused_result("serializePrepared", options_code, None, None)
    echo_identity = identity if isinstance(identity, dict) else None
    echo_revision = revision if isinstance(revision, str) else None
    checked, code = _serialize_checked(candidate)
    if checked is None:
        return refused_result(
            "serializePrepared", code or "render-stale", echo_identity, echo_revision
        )
    format_name = checked["format"]
    records = checked["records"]
    capability = checked["capability"]
    id_map = checked["idMap"]
    report = checked["report"]
    text = _write_drawio(records)
    if text is None:
        return refused_result("serializePrepared", "render-stale", echo_identity, echo_revision)
    data = text.encode("utf-8")
    hex_digest = digest_bytes(data)
    raw_entries = report.get("entries", [])
    kept = list(raw_entries) if isinstance(raw_entries, list) else []
    restored = [_entry_from_json(entry) for entry in kept]
    if any(entry is None for entry in restored):
        return refused_result("serializePrepared", "render-stale", echo_identity, echo_revision)
    final = report_with_header(
        "serializePrepared",
        copy.deepcopy(identity) if isinstance(identity, dict) else {},
        revision if isinstance(revision, str) else "",
        entries=[entry for entry in restored if entry is not None],
        id_map=copy.deepcopy(id_map),
        artifacts=[
            {
                "format": format_name,
                "capability": capability,
                "digest": hex_digest,
                "entryIndexes": list(range(len(kept))),
            }
        ],
    )
    payload: dict[str, Json] = {
        "format": format_name,
        "bytes": data.decode("utf-8"),
        "digest": hex_digest,
        "idMap": copy.deepcopy(id_map),
        "capability": capability,
    }
    return ResultSuccess(
        operation="serializePrepared",
        profile_identity=copy.deepcopy(identity) if isinstance(identity, dict) else {},
        base_revision=revision if isinstance(revision, str) else "",
        revision=revision if isinstance(revision, str) else "",
        payload=payload,
        report=final,
    )
