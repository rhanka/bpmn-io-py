"""Standalone derivation helper for the lot-3 C/N sealed expectations.

Stdlib only; imports nothing from ``bpmn_io`` (the seal test checks this with
an AST scan). This file holds the hand-authored inputs and expected outputs of
every case as literal data. Its code only computes what DESIGN R3.3 fixes
arithmetically: ``profile-c14n/2`` canonical text, SHA-256 digests,
``stable-id/1`` identifiers, §3.2 content signatures, §3.1 semantic
revisions, §9.2 descriptor digests, RFC 6902 profile deltas, the §10.1 report
entry order (with the harmonization G2 tie-breaks) and the §7.2 placement
order, plus the verbatim profile-parity-corpus/1 projection of the harness
cases. It never interprets a recipe, predicate or selector: every expected
tree, binding, placement, plan and report entry below is written by hand.

Running ``python tests/profile_cn/expected/derive_helper.py`` from the
repository root rewrites the sealed files from this hand-authored data and
refreshes ``MANIFEST.sha256``. No implementation output is ever an input.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

Json = object

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
ART = OUT / "artifacts"
MECH = ROOT / "contracts" / "profile-mechanism" / "1"
ART_REL = "tests/profile_cn/expected/artifacts/"
MECH_REL = "contracts/profile-mechanism/1/"

AUTHOR = "spec-seal"
ABSENT = object()
SAME = object()


# ---------------------------------------------------------------------------
# Primitives (DESIGN R3.3 §3.1, §3.2)
# ---------------------------------------------------------------------------


def utf16(text: str) -> bytes:
    """Return the UTF-16 code-unit sort key of one string."""
    return text.encode("utf-16-be")


def jcs(value: Json) -> str:  # noqa: PLR0911
    """Return the profile-c14n/2 (RFC 8785) text of one integer-only JSON value."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ",".join(jcs(item) for item in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value, key=utf16)
        members = (json.dumps(key, ensure_ascii=False) + ":" + jcs(value[key]) for key in keys)
        return "{" + ",".join(members) + "}"
    message = f"unsupported JSON value {value!r}"
    raise TypeError(message)


def digest(value: Json) -> str:
    """Return H(x): lowercase hex SHA-256 of the UTF-8 canonical text."""
    return hashlib.sha256(jcs(value).encode("utf-8")).hexdigest()


def raw_digest(data: bytes) -> str:
    """Return B(bytes): lowercase hex SHA-256 of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def sid(owner_id: str, slot: str, key: str) -> str:
    """Return one stable-id/1 identifier."""
    return "g_" + digest(["profile-mechanism/1", owner_id, slot, key])


def strip_ids(node: Json) -> Json:
    """Return a copy of one subtree with every ``id`` member removed (§3.2)."""
    if isinstance(node, dict):
        return {key: strip_ids(value) for key, value in node.items() if key != "id"}
    if isinstance(node, list):
        return [strip_ids(item) for item in node]
    return node


def content_signature(node: Json) -> str:
    """Return the §3.2 contentSignature of one raw ID-less subtree."""
    return digest(strip_ids(node))


def stable_key(signature: str, ordinal: int) -> str:
    """Return the §3.2 stableKey JCS([contentSignature, duplicateOrdinal])."""
    return jcs([signature, ordinal])


def c_id(owner_id: str, slot: str, node: Json, ordinal: int) -> str:
    """Return the C identity of one initially ID-less node (§3.2)."""
    return sid(owner_id, slot, stable_key(content_signature(node), ordinal))


def binding(owner_id: str, role: str, target_id: str) -> dict[str, str]:
    """Return one envelope support binding record."""
    return {"ownerId": owner_id, "role": role, "targetId": target_id}


def sort_bindings(bindings: list[dict[str, str]]) -> list[dict[str, str]]:
    """Sort bindings by ownerId, role, targetId in UTF-16 order (§5.1)."""
    return sorted(
        bindings,
        key=lambda b: (utf16(b["ownerId"]), utf16(b["role"]), utf16(b["targetId"])),
    )


def semantic_revision(tree: Json, identity: Json, bindings: list[dict[str, str]]) -> str:
    """Return the §3.1 semanticRevision of one DI-free committed tree."""
    return digest({"tree": tree, "profileIdentity": identity, "bindings": sort_bindings(bindings)})


def envelope(identity: Json, tree: Json, bindings: list[dict[str, str]]) -> dict[str, Json]:
    """Return one DocumentEnvelope/1 wire value with sorted bindings and revision."""
    return {
        "documentVersion": "1",
        "profileIdentity": copy.deepcopy(identity),
        "tree": copy.deepcopy(tree),
        "bindings": sort_bindings(copy.deepcopy(bindings)),
        "semanticRevision": semantic_revision(tree, identity, bindings),
    }


def pretty_bytes(value: Json) -> bytes:
    """Return the vendored pretty form: 2-space JSON plus one LF."""
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _unescape(segment: str) -> str:
    return segment.replace("~1", "/").replace("~0", "~")


def at(document: Json, pointer: str) -> Json:
    """Read one RFC 6901 pointer from hand-authored data."""
    current = document
    if pointer == "":
        return current
    for raw in pointer[1:].split("/"):
        segment = _unescape(raw)
        current = current[int(segment)] if isinstance(current, list) else current[segment]  # type: ignore[index]
    return current


def _patch_list(parent: list[Json], kind: str, last: str, value: Json) -> None:
    if kind == "add":
        if last == "-":
            parent.append(value)
        else:
            parent.insert(int(last), value)
    elif kind == "replace":
        parent[int(last)] = value
    else:
        del parent[int(last)]


def _patch_dict(parent: dict[str, Json], kind: str, last: str, value: Json) -> None:
    if kind == "remove":
        del parent[last]
        return
    if kind == "replace" and last not in parent:
        message = f"replace of absent member {last}"
        raise KeyError(message)
    parent[last] = value


def apply_patch(document: Json, operations: list[dict[str, Json]]) -> Json:
    """Apply the RFC 6902 subset add/replace/remove used by profile deltas."""
    result = copy.deepcopy(document)
    for operation in operations:
        parts = [_unescape(raw) for raw in str(operation["path"])[1:].split("/")]
        parent = result
        for segment in parts[:-1]:
            parent = parent[int(segment)] if isinstance(parent, list) else parent[segment]  # type: ignore[index]
        kind = str(operation["op"])
        value = copy.deepcopy(operation.get("value"))
        if isinstance(parent, list):
            _patch_list(parent, kind, parts[-1], value)
        elif isinstance(parent, dict):
            _patch_dict(parent, kind, parts[-1], value)
        else:
            message = f"bad patch target {operation['path']}"
            raise TypeError(message)
    return result


def load_json(path: Path) -> Json:
    """Load one vendored JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Report, result and placement shapes (DESIGN R3.3 §10.1, §7.2; spec §4)
# ---------------------------------------------------------------------------

STAGES = (
    "load",
    "import",
    "complete",
    "pre-normalize",
    "normalize",
    "post-normalize",
    "layout",
    "post-layout",
    "release",
    "render",
    "export",
)

NONE_COORD: dict[str, Json] = {
    "domain": "none",
    "pointer": None,
    "targetId": None,
    "provenance": "generated",
}


def coord(pointer: str, target_id: str | None, provenance: str = "exact") -> dict[str, Json]:
    """Return one tree coordinate."""
    return {"domain": "tree", "pointer": pointer, "targetId": target_id, "provenance": provenance}


def escape(segment: str) -> str:
    """Return one RFC 6901 escaped pointer segment."""
    return segment.replace("~", "~0").replace("/", "~1")


def at_property(pointer: str, prop: str) -> str:
    """Return the written-location pointer of one property of one element (H B9)."""
    return pointer + "/" + escape(prop)


def entry(  # noqa: PLR0913
    *,
    stage: str,
    code: str,
    rule: str,
    message: str,
    severity: str,
    classification: str,
    disposition: str,
    source: dict[str, Json],
    result: dict[str, Json],
    prop: str | None = None,
    before: Json = ABSENT,
    after: Json = ABSENT,
) -> dict[str, Json]:
    """Return one Report/2 entry wire value."""
    record: dict[str, Json] = {
        "code": code,
        "severity": severity,
        "classification": classification,
        "stage": stage,
        "ruleId": rule,
        "messageKey": message,
        "disposition": disposition,
        "source": copy.deepcopy(source),
        "result": copy.deepcopy(result),
        "beforePresent": before is not ABSENT,
        "afterPresent": after is not ABSENT,
    }
    if before is not ABSENT:
        record["before"] = copy.deepcopy(before)
    if after is not ABSENT:
        record["after"] = copy.deepcopy(after)
    if prop is not None:
        record["property"] = prop
    return record


def change(  # noqa: PLR0913, PLR0917
    stage: str,
    op: str,
    rule: str,
    source: dict[str, Json],
    result: dict[str, Json],
    prop: str,
    *,
    before: Json = ABSENT,
    after: Json = ABSENT,
) -> dict[str, Json]:
    """Return one C/N change entry (spec §4.3 vocabulary)."""
    return entry(
        stage=stage,
        code=f"{stage}/{op}",
        rule=rule,
        message=f"{stage}.{op}",
        severity="info",
        classification="repairable",
        disposition="corrected",
        source=source,
        result=result,
        prop=prop,
        before=before,
        after=after,
    )


def _optional_key(value: Json) -> tuple[int, bytes]:
    return (0, b"") if value is None else (1, utf16(str(value)))


def _value_key(record: dict[str, Json], name: str) -> tuple[int, bytes]:
    if not record[name + "Present"]:
        return (0, b"")
    return (1, utf16(jcs(record[name])))


def entry_key(record: dict[str, Json]) -> tuple[Json, ...]:
    """Return the profile-report/2 order key (§10.1 keys, then the H G2 tie-breaks).

    §10.1: stage rank, ruleId, source domain, source pointer, source targetId,
    code, pageId, occurrenceKey, canonical before then after (absent first).
    H G2 tie-breaks: result domain, result pointer, result targetId (null
    first), then property (absent first). UTF-16 throughout.
    """
    source = record["source"]
    result = record["result"]
    return (
        STAGES.index(str(record["stage"])),
        utf16(str(record["ruleId"])),
        utf16(str(source["domain"])),  # type: ignore[index]
        _optional_key(source["pointer"]),  # type: ignore[index]
        _optional_key(source["targetId"]),  # type: ignore[index]
        utf16(str(record["code"])),
        _optional_key(record.get("pageId")),
        _optional_key(record.get("occurrenceKey")),
        _value_key(record, "before"),
        _value_key(record, "after"),
        utf16(str(result["domain"])),  # type: ignore[index]
        _optional_key(result["pointer"]),  # type: ignore[index]
        _optional_key(result["targetId"]),  # type: ignore[index]
        _optional_key(record.get("property")),
    )


def sort_entries(entries: list[dict[str, Json]]) -> list[dict[str, Json]]:
    """Sort entries in profile-report/2 order, coalescing exact duplicates.

    Sealed entry lists never contain two wire-different entries with equal
    keys, so the sealed order is the same under any stable sorter.
    """
    ordered: list[dict[str, Json]] = []
    for record in sorted(entries, key=entry_key):
        if ordered and jcs(ordered[-1]) == jcs(record):
            continue
        if ordered and entry_key(ordered[-1]) == entry_key(record):
            message = f"ambiguous report order at {record['result']}"
            raise ValueError(message)
        ordered.append(record)
    return ordered


def sort_id_map(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Sort idMap rows by domain, pageId, occurrenceKey, sourceId, resultId (§10.1)."""
    return sorted(
        rows,
        key=lambda r: (
            utf16(r["domain"]),
            _optional_key(r.get("pageId")),
            _optional_key(r.get("occurrenceKey")),
            utf16(r["sourceId"]),
            utf16(r["resultId"]),
        ),
    )


def report(  # noqa: PLR0913
    operation: str,
    entries: list[dict[str, Json]],
    input_revision: str | None = None,
    output_revision: str | None = None,
    id_map: list[dict[str, str]] | None = None,
    *,
    source_identity: Json = None,
    target_identity: Json = None,
) -> dict[str, Json]:
    """Return one Report/2 wire value (optional header members per H B4)."""
    record: dict[str, Json] = {
        "reportVersion": "2",
        "operation": operation,
        "entries": sort_entries(entries),
        "rawStandardFindings": [],
        "idMap": sort_id_map(id_map or []),
        "artifacts": [],
    }
    if source_identity is not None:
        record["sourceIdentity"] = copy.deepcopy(source_identity)
    if target_identity is not None:
        record["targetIdentity"] = copy.deepcopy(target_identity)
    if input_revision is not None:
        record["inputRevision"] = input_revision
    if output_revision is not None:
        record["outputRevision"] = output_revision
    return record


def success_report(  # noqa: PLR0913, PLR0917
    operation: str,
    identity: Json,
    base_revision: str,
    revision: str,
    entries: list[dict[str, Json]],
    id_map: list[dict[str, str]] | None = None,
) -> dict[str, Json]:
    """Return the Report/2 of one success: all four header members (H B4).

    sourceIdentity is the input envelope identity, targetIdentity the output
    envelope identity (equal for every lot-3 operation), inputRevision the
    baseRevision and outputRevision the revision.
    """
    return report(
        operation,
        entries,
        base_revision,
        revision,
        id_map,
        source_identity=identity,
        target_identity=identity,
    )


def ok_result(  # noqa: PLR0913, PLR0917
    operation: str,
    identity: Json,
    base_revision: str,
    revision: str,
    rep: dict[str, Json],
    payload: Json,
) -> dict[str, Json]:
    """Return one Result/1 success wire value."""
    return {
        "status": "ok",
        "operation": operation,
        "profileIdentity": copy.deepcopy(identity),
        "baseRevision": base_revision,
        "revision": revision,
        "report": rep,
        "payload": payload,
    }


def refused_result(
    operation: str,
    code: str,
    identity: Json = None,
    base_revision: str | None = None,
) -> dict[str, Json]:
    """Return one Result/1 refusal wire value (spec §4.5, H B2/B3/B4).

    No candidate and no change entry: report.entries and diagnostics are
    empty (C/N run no lint stage). The echoed identity and baseRevision, when
    given, are repeated as report sourceIdentity and inputRevision; a refusal
    never carries targetIdentity or outputRevision.
    """
    record: dict[str, Json] = {
        "status": "refused",
        "operation": operation,
        "code": code,
        "diagnostics": [],
        "report": report(operation, [], base_revision, source_identity=identity),
    }
    if identity is not None:
        record["profileIdentity"] = copy.deepcopy(identity)
    if base_revision is not None:
        record["baseRevision"] = base_revision
    return record


def echoes(env_in: Json) -> bool:
    """Return whether a refusal echoes the input identity and revision (H B3).

    Echo iff the input is a JSON object with documentVersion "1", a closed
    shape-valid §5.1 profileIdentity record (seven members, string scalars,
    mechanismVersion "1", schemaVersion "1.0.0", 64-hex sha256, pin records)
    and a string semanticRevision, even when a later envelope check fails.
    """
    if not isinstance(env_in, dict) or env_in.get("documentVersion") != "1":
        return False
    ident = env_in.get("profileIdentity")
    keys = {"mechanismVersion", "schemaVersion", "profile", "version", "sha256", "base"}
    if not isinstance(ident, dict) or set(ident) != {*keys, "descriptors"}:
        return False
    if ident["mechanismVersion"] != "1" or ident["schemaVersion"] != "1.0.0":
        return False
    sha = ident["sha256"]
    if not isinstance(sha, str) or len(sha) != 64 or set(sha) - set("0123456789abcdef"):
        return False
    pins = [ident["base"], *ident["descriptors"]] if isinstance(ident["descriptors"], list) else []
    if not pins[1:] or any(
        not isinstance(p, dict) or set(p) != {"id", "version", "sha256"} for p in pins
    ):
        return False
    return isinstance(env_in.get("semanticRevision"), str)


def pure_ok(payload: Json) -> dict[str, Json]:
    """Return one PureResult success wire value."""
    return {"status": "ok", "payload": payload, "diagnostics": []}


def pure_refused(code: str) -> dict[str, Json]:
    """Return one PureResult refusal wire value."""
    return {"status": "refused", "code": code, "diagnostics": []}


def placement(
    element_id: str,
    owner_process_id: str,
    region_key: str,
    related: list[str],
    anchor: str | None = None,
) -> dict[str, Json]:
    """Return one derived placement record (§7.2)."""
    record: dict[str, Json] = {
        "elementId": element_id,
        "ownerProcessId": owner_process_id,
        "regionKey": region_key,
        "relatedAssociationIds": sorted(set(related), key=utf16),
    }
    if anchor is not None:
        record["anchorAssociationId"] = anchor
    return record


def placement_key(record: dict[str, Json]) -> tuple[Json, ...]:
    """Return the §7.2 placement order key (absent anchor before present)."""
    related = record["relatedAssociationIds"]
    return (
        utf16(str(record["ownerProcessId"])),
        utf16(str(record["regionKey"])),
        utf16(str(record["elementId"])),
        _optional_key(record.get("anchorAssociationId")),
        [utf16(str(item)) for item in related],  # type: ignore[union-attr]
    )


def sort_placements(records: list[dict[str, Json]]) -> list[dict[str, Json]]:
    """Sort placements in the total §7.2 UTF-16 tuple order."""
    return sorted(records, key=placement_key)


# ---------------------------------------------------------------------------
# Synthetic "cn" descriptor slice and effective base (spec §2.3)
# ---------------------------------------------------------------------------

FLOW_NODES = ["bpmn:Task", "bpmn:ServiceTask", "bpmn:CallActivity", "bpmn:StartEvent"]
ASSOCIATION_ENDS = [
    "bpmn:Task",
    "bpmn:ServiceTask",
    "bpmn:CallActivity",
    "bpmn:TextAnnotation",
    "bpmn:DataStoreReference",
    "bpmn:DataInput",
    "bpmn:DataOutput",
]


def _type(  # noqa: PLR0913
    scalars: list[str],
    containment: dict[str, list[str]] | None = None,
    references: dict[str, list[str]] | None = None,
    *,
    has_id: bool = True,
    many: list[str] | None = None,
    single: list[str] | None = None,
) -> dict[str, Json]:
    record: dict[str, Json] = {
        "id": has_id,
        "scalars": scalars,
        "containment": containment or {},
        "references": references or {},
    }
    if many:
        record["many"] = many
    if single:
        record["single"] = single
    return record


CN_TYPES: dict[str, dict[str, Json]] = {
    "bpmn:Definitions": _type(
        ["id", "name", "targetNamespace"],
        {"rootElements": ["bpmn:Process", "bpmn:Collaboration", "bpmn:DataStore"]},
    ),
    "bpmn:Process": _type(
        ["id", "name", "isExecutable"],
        {
            "flowElements": [
                "bpmn:Task",
                "bpmn:ServiceTask",
                "bpmn:CallActivity",
                "bpmn:StartEvent",
                "bpmn:ExclusiveGateway",
                "bpmn:SequenceFlow",
                "bpmn:DataObject",
                "bpmn:DataObjectReference",
                "bpmn:DataStoreReference",
            ],
            "artifacts": ["bpmn:TextAnnotation", "bpmn:Association"],
            "documentation": ["bpmn:Documentation"],
            "laneSets": ["bpmn:LaneSet"],
            "ioSpecification": ["bpmn:InputOutputSpecification"],
        },
        single=["ioSpecification"],
    ),
    "bpmn:Task": _type(
        ["id", "name"],
        {
            "documentation": ["bpmn:Documentation"],
            "properties": ["bpmn:Property"],
            "dataInputAssociations": ["bpmn:DataInputAssociation"],
            "dataOutputAssociations": ["bpmn:DataOutputAssociation"],
        },
        {"incoming": ["bpmn:SequenceFlow"], "outgoing": ["bpmn:SequenceFlow"]},
        many=["incoming", "outgoing"],
    ),
    "bpmn:ServiceTask": _type(["id", "name"], {"documentation": ["bpmn:Documentation"]}),
    "bpmn:CallActivity": _type(
        ["id", "name"],
        {"documentation": ["bpmn:Documentation"]},
        {"calledElement": ["bpmn:Process"]},
    ),
    "bpmn:StartEvent": _type(
        ["id", "name"],
        {"eventDefinitions": ["bpmn:TimerEventDefinition"]},
        {"outgoing": ["bpmn:SequenceFlow"]},
        many=["outgoing"],
    ),
    "bpmn:TimerEventDefinition": _type(
        ["id"], {"timeDuration": ["bpmn:FormalExpression"]}, single=["timeDuration"]
    ),
    "bpmn:FormalExpression": _type(["body", "language"], has_id=False),
    "bpmn:ExclusiveGateway": _type(
        ["id", "name", "gatewayDirection"],
        None,
        {"incoming": ["bpmn:SequenceFlow"], "outgoing": ["bpmn:SequenceFlow"]},
        many=["incoming", "outgoing"],
    ),
    "bpmn:SequenceFlow": _type(
        ["id", "name"],
        None,
        {
            "sourceRef": ["bpmn:StartEvent", "bpmn:ExclusiveGateway", "bpmn:Task"],
            "targetRef": ["bpmn:ExclusiveGateway", "bpmn:Task"],
        },
    ),
    "bpmn:TextAnnotation": _type(["id", "text"]),
    "bpmn:Association": _type(
        ["id", "associationDirection"],
        None,
        {"sourceRef": ASSOCIATION_ENDS, "targetRef": ASSOCIATION_ENDS},
    ),
    "bpmn:Documentation": _type(["text", "textFormat"], has_id=False),
    "bpmn:DataObject": _type(["id", "name"]),
    "bpmn:DataObjectReference": _type(["id", "name"], None, {"dataObjectRef": ["bpmn:DataObject"]}),
    "bpmn:DataStore": _type(["id", "name"]),
    "bpmn:DataStoreReference": _type(["id", "name"], None, {"dataStoreRef": ["bpmn:DataStore"]}),
    "bpmn:InputOutputSpecification": _type(
        [],
        {
            "dataInputs": ["bpmn:DataInput"],
            "dataOutputs": ["bpmn:DataOutput"],
            "inputSets": ["bpmn:InputSet"],
            "outputSets": ["bpmn:OutputSet"],
        },
        has_id=False,
    ),
    "bpmn:DataInput": _type(["id", "name"]),
    "bpmn:DataOutput": _type(["id", "name"]),
    "bpmn:InputSet": _type(
        ["id"], None, {"dataInputRefs": ["bpmn:DataInput"]}, many=["dataInputRefs"]
    ),
    "bpmn:OutputSet": _type(
        ["id"], None, {"dataOutputRefs": ["bpmn:DataOutput"]}, many=["dataOutputRefs"]
    ),
    "bpmn:Property": _type(["id", "name"]),
    "bpmn:DataInputAssociation": _type(
        ["id"],
        None,
        {
            "sourceRef": [
                "bpmn:DataObjectReference",
                "bpmn:DataStoreReference",
                "bpmn:DataInput",
                "bpmn:Property",
            ],
            "targetRef": ["bpmn:Property"],
        },
        many=["sourceRef"],
    ),
    "bpmn:DataOutputAssociation": _type(
        ["id"],
        None,
        {
            "sourceRef": ["bpmn:Property"],
            "targetRef": ["bpmn:DataObjectReference", "bpmn:DataOutput"],
        },
        many=["sourceRef"],
    ),
    "bpmn:Collaboration": _type(["id", "name"], {"participants": ["bpmn:Participant"]}),
    "bpmn:Participant": _type(["id", "name"], None, {"processRef": ["bpmn:Process"]}),
    "bpmn:LaneSet": _type(["id", "name"], {"lanes": ["bpmn:Lane"]}),
    "bpmn:Lane": _type(
        ["id", "name"],
        None,
        {"flowNodeRef": [*FLOW_NODES, "bpmn:ExclusiveGateway"]},
        many=["flowNodeRef"],
    ),
}

CN_DESCRIPTORS: dict[str, Json] = {
    "id": "neutral-cn-descriptors/1",
    "scope": (
        "Synthetic descriptor slice for the lot-3 C/N sealed expectations; not the complete"
        " BPMN descriptor set. Optional facets: many lists multi-valued reference properties,"
        " single lists single-valued containment properties."
    ),
    "types": CN_TYPES,
}


def _base_fields(types: dict[str, dict[str, Json]]) -> list[dict[str, Json]]:
    fields: list[dict[str, Json]] = []
    for type_name, record in types.items():
        for facet, kind in (
            ("scalars", "scalar"),
            ("containment", "containment"),
            ("references", "reference"),
        ):
            fields.extend(_field(type_name, name, kind) for name in record[facet])  # type: ignore[union-attr]
    return fields


def _field(type_name: str, name: str, kind: str) -> dict[str, Json]:
    return {
        "type": type_name,
        "field": name,
        "producers": ["code", "editor", "import"],
        "kind": kind,
    }


CN_BASE: dict[str, Json] = {
    "id": "neutral-cn-base/1",
    "version": "fixture-1",
    "descriptor": "neutral-cn-descriptors/1",
    "types": list(CN_TYPES),
    "producerPolicy": "fixture-explicit",
    "fields": _base_fields(CN_TYPES),
}


# ---------------------------------------------------------------------------
# Recipe data constructors (pure literal sugar; nothing is evaluated)
# ---------------------------------------------------------------------------

TRUE: dict[str, Json] = {"op": "true"}
FALSE: dict[str, Json] = {"op": "false"}
MARKER_FORMAT = "text/x-neutral-call-kind"


def type_is(type_name: str, binding_name: str = "self") -> dict[str, Json]:
    """Return one exact typeIs predicate."""
    return {"op": "typeIs", "binding": binding_name, "type": type_name, "mode": "exact"}


def all_of(*args: Json) -> dict[str, Json]:
    """Return one all predicate."""
    return {"op": "all", "args": list(args)}


def any_of(*args: Json) -> dict[str, Json]:
    """Return one any predicate."""
    return {"op": "any", "args": list(args)}


def not_(arg: Json) -> dict[str, Json]:
    """Return one not predicate."""
    return {"op": "not", "arg": arg}


def lit(value: Json) -> dict[str, Json]:
    """Return one literal value."""
    return {"op": "literal", "value": value}


def read(binding_name: str, path: str) -> dict[str, Json]:
    """Return one read value."""
    return {"op": "read", "binding": binding_name, "path": path}


def id_of(binding_name: str) -> dict[str, Json]:
    """Return one id value."""
    return {"op": "id", "binding": binding_name}


def param(name: str) -> dict[str, Json]:
    """Return one param value."""
    return {"op": "param", "name": name}


def eq(left: Json, right: Json) -> dict[str, Json]:
    """Return one equal predicate."""
    return {"op": "equal", "left": left, "right": right}


def present(value: Json) -> dict[str, Json]:
    """Return one present predicate."""
    return {"op": "present", "value": value}


def sel(frm: str, via: str, where: Json = TRUE, prop: str | None = None) -> dict[str, Json]:
    """Return one native selector (order id)."""
    record: dict[str, Json] = {"from": frm, "via": via}
    if prop is not None:
        record["property"] = prop
    record["where"] = where
    record["order"] = "id"
    return record


def count(select: Json, minimum: int, maximum: int | None = None) -> dict[str, Json]:
    """Return one count predicate."""
    record: dict[str, Json] = {"op": "count", "select": select, "min": minimum}
    if maximum is not None:
        record["max"] = maximum
    return record


def ids(select: Json) -> dict[str, Json]:
    """Return one ids value."""
    return {"op": "ids", "select": select}


def bind(name: str, select: Json, cardinality: str = "one") -> dict[str, Json]:
    """Return one bind action."""
    return {"op": "bind", "as": name, "select": select, "cardinality": cardinality}


def write(binding_name: str, path: str, mode: str) -> dict[str, Json]:
    """Return one declared write."""
    return {"binding": binding_name, "path": path, "mode": mode}


def assign(target: str, path: str, mode: str, values: list[Json]) -> dict[str, Json]:
    """Return one assignRef action."""
    return {"op": "assignRef", "target": target, "path": path, "mode": mode, "values": values}


def set_(target: str, path: str, value: Json) -> dict[str, Json]:
    """Return one set action."""
    return {"op": "set", "target": target, "path": path, "value": value}


def name_field(value: str) -> list[dict[str, Json]]:
    """Return one literal name field list."""
    return [{"name": "name", "value": lit(value)}]


def recipe(  # noqa: PLR0913, PLR0917
    rid: str,
    phase: str,
    select: Json,
    when: Json,
    writes: list[Json],
    steps: list[Json],
    parameters: list[Json] | None = None,
) -> dict[str, Json]:
    """Return one recipe record."""
    return {
        "id": rid,
        "phase": phase,
        "parameters": parameters or [],
        "select": select,
        "when": when,
        "writes": writes,
        "steps": steps,
    }


def select_all(where: Json) -> dict[str, Json]:
    """Return the root containment-index selector."""
    return sel("root", "all", where)


def element_param(name: str) -> dict[str, Json]:
    """Return one required element parameter."""
    return {"name": name, "type": "element", "required": True}


def string_param(name: str) -> dict[str, Json]:
    """Return one required string parameter."""
    return {"name": name, "type": "string", "required": True}


# --- complete (C) policy data for the cn profiles -------------------------


def same_container() -> dict[str, Json]:
    """Candidate flow owned by the bound ``container`` (per-container rule)."""
    return count(sel("self", "owner", eq(id_of("self"), id_of("container"))), 1)


def derived_flows(prop: str) -> dict[str, Json]:
    """Ids of same-container SequenceFlows whose ``prop`` targets self."""
    return ids(
        sel(
            "self", "inverseReference", all_of(type_is("bpmn:SequenceFlow"), same_container()), prop
        )
    )


def topology_recipe(rid: str, type_name: str, props: list[tuple[str, str]]) -> dict[str, Json]:
    """Replace incoming/outgoing with selector-derived flows (§7.1 Topology)."""
    steps: list[Json] = [bind("container", sel("self", "owner"))]
    steps += [assign("self", "/" + name, "replace", [derived_flows(ref)]) for name, ref in props]
    writes: list[Json] = [write("self", "/" + name, "reference") for name, _ in props]
    return recipe(rid, "complete", select_all(type_is(type_name)), TRUE, writes, steps)


def flow_count(prop: str, minimum: int, maximum: int | None) -> dict[str, Json]:
    """Count SequenceFlows whose ``prop`` targets self."""
    return count(
        sel("self", "inverseReference", type_is("bpmn:SequenceFlow"), prop), minimum, maximum
    )


def direction_recipe(
    rid: str, value: str, incoming: tuple[int, int | None], outgoing: tuple[int, int | None]
) -> dict[str, Json]:
    """Set gatewayDirection for one in/out cardinality class (§7.1 Topology)."""
    when = all_of(flow_count("targetRef", *incoming), flow_count("sourceRef", *outgoing))
    return recipe(
        rid,
        "complete",
        select_all(type_is("bpmn:ExclusiveGateway")),
        when,
        [write("self", "/gatewayDirection", "set")],
        [set_("self", "/gatewayDirection", lit(value))],
    )


def port_recipe(rid: str, association: str, path: str, slot: str) -> dict[str, Json]:
    """Create one missing association-specific port keyed by association (§7.1 Ports)."""
    return recipe(
        rid,
        "complete",
        select_all(all_of(type_is(association), not_(present(read("self", path))))),
        TRUE,
        [write("activity", "/properties", "create"), write("self", path, "reference")],
        [
            bind("activity", sel("self", "owner")),
            {
                "op": "create",
                "as": "port",
                "type": "bpmn:Property",
                "parent": "activity",
                "property": "properties",
                "identity": "allocated",
                "ownerId": id_of("activity"),
                "slot": slot,
                "key": id_of("self"),
                "fields": [],
            },
            assign("self", path, "replace", [id_of("port")]),
        ],
    )


def default_set_recipe(
    rid: str, sets: str, members: str, set_type: str, refs: str
) -> dict[str, Json]:
    """Create the deterministic default set for declared Process IO (§7.1 Sets)."""
    when = all_of(
        count(sel("self", "children", TRUE, sets), 0, 0),
        count(sel("self", "children", TRUE, members), 1),
    )
    return recipe(
        rid,
        "complete",
        select_all(type_is("bpmn:InputOutputSpecification")),
        when,
        [write("self", "/" + sets, "create"), write("created", "/" + refs, "reference")],
        [
            bind("process", sel("self", "owner")),
            {
                "op": "create",
                "as": "created",
                "type": set_type,
                "parent": "self",
                "property": sets,
                "identity": "allocated",
                "ownerId": id_of("process"),
                "slot": "input-set" if sets == "inputSets" else "output-set",
                "key": lit("default"),
                "fields": [],
            },
            assign("created", "/" + refs, "replace", [ids(sel("self", "children", TRUE, members))]),
        ],
    )


def selection_recipe() -> dict[str, Json]:
    """Refuse uncovered Process input with several input sets (§7.1 Sets)."""
    uncovered = sel(
        "self",
        "children",
        count(sel("self", "inverseReference", TRUE, "dataInputRefs"), 0, 0),
        "dataInputs",
    )
    when = all_of(count(sel("self", "children", TRUE, "inputSets"), 2), count(uncovered, 1))
    return recipe(
        "complete-input-set-selection",
        "complete",
        select_all(type_is("bpmn:InputOutputSpecification")),
        when,
        [],
        [{"op": "refuse", "code": "io-set-selection-required", "target": "self"}],
    )


def backing_object_recipe() -> dict[str, Json]:
    """Create the missing backing DataObject of a reference (§7.1 Internal item)."""
    return recipe(
        "complete-backing-object",
        "complete",
        select_all(
            all_of(
                type_is("bpmn:DataObjectReference"),
                not_(present(read("self", "/dataObjectRef"))),
            )
        ),
        TRUE,
        [
            write("container", "/flowElements", "create"),
            write("self", "/dataObjectRef", "reference"),
        ],
        [
            bind("container", sel("self", "owner")),
            {
                "op": "create",
                "as": "backing",
                "type": "bpmn:DataObject",
                "parent": "container",
                "property": "flowElements",
                "identity": "allocated",
                "ownerId": id_of("container"),
                "slot": "backing-object",
                "key": id_of("self"),
                "fields": [],
            },
            assign("self", "/dataObjectRef", "replace", [id_of("backing")]),
        ],
    )


CN_COMPLETE_RECIPES: list[dict[str, Json]] = [
    topology_recipe("complete-start-topology", "bpmn:StartEvent", [("outgoing", "sourceRef")]),
    topology_recipe(
        "complete-gateway-topology",
        "bpmn:ExclusiveGateway",
        [("incoming", "targetRef"), ("outgoing", "sourceRef")],
    ),
    topology_recipe(
        "complete-task-topology",
        "bpmn:Task",
        [("incoming", "targetRef"), ("outgoing", "sourceRef")],
    ),
    direction_recipe("gateway-direction-mixed", "Mixed", (2, None), (2, None)),
    direction_recipe("gateway-direction-converging", "Converging", (2, None), (0, 1)),
    direction_recipe("gateway-direction-diverging", "Diverging", (0, 1), (2, None)),
    direction_recipe("gateway-direction-unspecified", "Unspecified", (0, 1), (0, 1)),
    backing_object_recipe(),
    port_recipe("complete-input-port", "bpmn:DataInputAssociation", "/targetRef", "input-port"),
    port_recipe("complete-output-port", "bpmn:DataOutputAssociation", "/sourceRef", "output-port"),
    default_set_recipe(
        "complete-default-input-set", "inputSets", "dataInputs", "bpmn:InputSet", "dataInputRefs"
    ),
    default_set_recipe(
        "complete-default-output-set",
        "outputSets",
        "dataOutputs",
        "bpmn:OutputSet",
        "dataOutputRefs",
    ),
    selection_recipe(),
]

SUFFIX_RECIPE = recipe(
    "suffix-task-name",
    "complete",
    select_all(type_is("bpmn:Task")),
    TRUE,
    [write("self", "/name", "set")],
    [set_("self", "/name", {"op": "concat", "values": [read("self", "/name"), lit("!")]})],
)

FIXTURE_REFUSAL = "fixture-second-pass"


def refuse_named(rid: str, phase: str, type_name: str) -> dict[str, Json]:
    """Refuse every element of one type whose name is the literal 'marked'."""
    return recipe(
        rid,
        phase,
        select_all(all_of(type_is(type_name), eq(read("self", "/name"), lit("marked")))),
        TRUE,
        [],
        [{"op": "refuse", "code": FIXTURE_REFUSAL, "target": "self"}],
    )


MARK_TASK_RECIPE = recipe(
    "mark-task-name",
    "complete",
    select_all(type_is("bpmn:Task")),
    TRUE,
    [write("self", "/name", "set")],
    [set_("self", "/name", lit("marked"))],
)
REFUSE_MARKED_TASK_RECIPE = refuse_named("refuse-marked-task", "complete", "bpmn:Task")


# --- normalize (N) policy data for the cn profiles ------------------------


def marked_call(binding_name: str = "self") -> dict[str, Json]:
    """Candidate external call: one marker of the candidate encoding, no target (§4.1)."""
    markers = sel(
        binding_name,
        "children",
        eq(read("self", "/textFormat"), lit(MARKER_FORMAT)),
        "documentation",
    )
    external = sel(
        binding_name,
        "children",
        all_of(
            eq(read("self", "/textFormat"), lit(MARKER_FORMAT)),
            eq(read("self", "/text"), lit("external")),
        ),
        "documentation",
    )
    return all_of(
        type_is("bpmn:CallActivity", binding_name),
        count(markers, 1, 1),
        count(external, 1, 1),
        not_(present(read(binding_name, "/calledElement"))),
    )


def ensure_collaboration(owner: str) -> dict[str, Json]:
    """Ensure the per-Process Collaboration (Definitions allocation domain, §3.2)."""
    return {
        "op": "ensure",
        "as": "collaboration",
        "type": "bpmn:Collaboration",
        "parent": "root",
        "property": "rootElements",
        "owner": owner,
        "role": "collaboration",
        "ownerId": id_of("root"),
        "slot": "collaboration",
        "key": id_of(owner),
        "fields": name_field("collaboration"),
    }


def ensure_role(  # noqa: PLR0913, PLR0917
    name: str, type_name: str, parent: str, prop: str, owner: str, role: str
) -> dict[str, Json]:
    """Ensure one Process-owned support role (Process allocation domain, §3.2)."""
    return {
        "op": "ensure",
        "as": name,
        "type": type_name,
        "parent": parent,
        "property": prop,
        "owner": owner,
        "role": role,
        "ownerId": id_of(owner),
        "slot": role,
        "key": lit(role),
        "fields": name_field(role),
    }


def ensure_lane_set(owner: str) -> dict[str, Json]:
    """Ensure the bound LaneSet of one Process."""
    return ensure_role("laneSet", "bpmn:LaneSet", owner, "laneSets", owner, "lane-set")


def ensure_lane(owner: str) -> dict[str, Json]:
    """Ensure the bound reserved external Lane of one Process."""
    return ensure_role("lane", "bpmn:Lane", "laneSet", "lanes", owner, "external-lane")


def touching(binding_name: str) -> dict[str, Json]:
    """Associations whose sourceRef or targetRef is the bound element."""
    return sel(
        "root",
        "all",
        all_of(
            type_is("bpmn:Association"),
            any_of(
                eq(read("self", "/sourceRef"), id_of(binding_name)),
                eq(read("self", "/targetRef"), id_of(binding_name)),
            ),
        ),
    )


#: Opaque region keys of the cn-n placements. They equal the support roles whose
#: bound rectangle the layout primitive uses (DESIGN §9.4: references in the bound
#: band, Process IO in the bound external lane; H K1 regionKey = binding role).
REFERENCE_REGION = "reference-band"
INTERFACE_REGION = "external-lane"


def place_step(region: str) -> dict[str, Json]:
    """Place self in one opaque region of its owner Process with its anchor."""
    return {
        "op": "place",
        "target": "self",
        "owner": "process",
        "region": region,
        "related": touching("current"),
        "anchor": "anchor",
    }


CN_NORMALIZE_RECIPES: list[dict[str, Json]] = [
    recipe(
        "ensure-base-supports",
        "normalize",
        select_all(type_is("bpmn:Process")),
        TRUE,
        [
            write("root", "/rootElements", "create"),
            write("envelope", "/bindings", "binding"),
            write("collaboration", "/participants", "create"),
            write("main", "/processRef", "reference"),
        ],
        [
            ensure_collaboration("self"),
            ensure_role(
                "main",
                "bpmn:Participant",
                "collaboration",
                "participants",
                "self",
                "main-participant",
            ),
            assign("main", "/processRef", "replace", [id_of("self")]),
        ],
    ),
    recipe(
        "ensure-external-lane",
        "normalize",
        select_all(type_is("bpmn:Process")),
        any_of(
            count(sel("self", "children", marked_call(), "flowElements"), 1),
            count(
                sel(
                    "self",
                    "descendants",
                    any_of(type_is("bpmn:DataInput"), type_is("bpmn:DataOutput")),
                ),
                1,
            ),
        ),
        [
            write("self", "/laneSets", "create"),
            write("envelope", "/bindings", "binding"),
            write("laneSet", "/lanes", "create"),
        ],
        [ensure_lane_set("self"), ensure_lane("self")],
    ),
    recipe(
        "ensure-reference-band",
        "normalize",
        select_all(type_is("bpmn:Process")),
        count(sel("self", "children", type_is("bpmn:DataStoreReference"), "flowElements"), 1),
        [
            write("root", "/rootElements", "create"),
            write("envelope", "/bindings", "binding"),
            write("collaboration", "/participants", "create"),
        ],
        [
            ensure_collaboration("self"),
            ensure_role(
                "band",
                "bpmn:Participant",
                "collaboration",
                "participants",
                "self",
                "reference-band",
            ),
        ],
    ),
    recipe(
        "relocate-marked-calls",
        "normalize",
        select_all(marked_call()),
        TRUE,
        [
            write("process", "/laneSets", "create"),
            write("envelope", "/bindings", "binding"),
            write("laneSet", "/lanes", "create"),
            write("lane", "/flowNodeRef", "reference"),
        ],
        [
            bind("process", sel("self", "owner")),
            ensure_lane_set("process"),
            ensure_lane("process"),
            assign("lane", "/flowNodeRef", "appendUnique", [id_of("self")]),
        ],
    ),
    recipe(
        "reverse-reference-links",
        "normalize",
        select_all(
            all_of(
                type_is("bpmn:Association"),
                count(sel("self", "reference", type_is("bpmn:Task"), "sourceRef"), 1),
                count(sel("self", "reference", type_is("bpmn:DataStoreReference"), "targetRef"), 1),
            )
        ),
        TRUE,
        [
            write("self", "/sourceRef", "reference"),
            write("self", "/targetRef", "reference"),
            write("self", "/associationDirection", "set"),
        ],
        [
            bind("source", sel("self", "reference", TRUE, "sourceRef")),
            bind("target", sel("self", "reference", TRUE, "targetRef")),
            assign("self", "/sourceRef", "replace", [id_of("target")]),
            assign("self", "/targetRef", "replace", [id_of("source")]),
            set_("self", "/associationDirection", lit("One")),
        ],
    ),
    recipe(
        "place-references",
        "normalize",
        select_all(type_is("bpmn:DataStoreReference")),
        TRUE,
        [write("self", "", "placement")],
        [
            bind("current", sel("self", "self")),
            bind("process", sel("self", "owner")),
            bind("anchor", touching("current"), "first"),
            place_step(REFERENCE_REGION),
        ],
    ),
    recipe(
        "place-interface",
        "normalize",
        select_all(any_of(type_is("bpmn:DataInput"), type_is("bpmn:DataOutput"))),
        TRUE,
        [write("self", "", "placement")],
        [
            bind("current", sel("self", "self")),
            bind("spec", sel("self", "owner")),
            bind("process", sel("spec", "owner")),
            bind("anchor", touching("current"), "first"),
            place_step(INTERFACE_REGION),
        ],
    ),
]

ASSIGN_LANE_MEMBER_RECIPE = recipe(
    "assign-lane-member",
    "edit",
    sel("lane", "self"),
    TRUE,
    [write("self", "/flowNodeRef", "reference")],
    [assign("self", "/flowNodeRef", "replace", [id_of("node")])],
    [element_param("lane"), element_param("node")],
)

CN_COMMAND_RECIPES: list[dict[str, Json]] = [
    recipe(
        "create-process-input",
        "create",
        sel("owner", "self"),
        TRUE,
        [write("owner", "/ioSpecification", "create"), write("spec", "/dataInputs", "create")],
        [
            {
                "op": "create",
                "as": "spec",
                "type": "bpmn:InputOutputSpecification",
                "parent": "owner",
                "property": "ioSpecification",
                "identity": "containment",
                "fields": [],
            },
            {
                "op": "create",
                "as": "input",
                "type": "bpmn:DataInput",
                "parent": "spec",
                "property": "dataInputs",
                "identity": "allocated",
                "ownerId": id_of("owner"),
                "slot": "process-input",
                "key": param("key"),
                "fields": [{"name": "name", "value": param("name")}],
            },
        ],
        [element_param("owner"), string_param("key"), string_param("name")],
    ),
    recipe(
        "remove-element",
        "edit",
        sel("target", "self"),
        TRUE,
        [write("self", "", "remove")],
        [
            {
                "op": "remove",
                "target": "self",
                "dependents": sel("self", "self", FALSE),
                "policy": "refuseIfReferenced",
            }
        ],
        [element_param("target")],
    ),
    recipe(
        "conflicting-rename",
        "edit",
        sel("target", "self"),
        TRUE,
        [write("self", "/name", "set")],
        [set_("self", "/name", lit("first")), set_("self", "/name", lit("second"))],
        [element_param("target")],
    ),
    recipe(
        "toggle-membership",
        "edit",
        sel("lane", "self"),
        TRUE,
        [write("self", "/flowNodeRef", "reference")],
        [
            assign("self", "/flowNodeRef", "appendUnique", [id_of("node")]),
            assign("self", "/flowNodeRef", "remove", [id_of("node")]),
        ],
        [element_param("lane"), element_param("node")],
    ),
    recipe(
        "rename-only-task",
        "edit",
        sel("owner", "self"),
        TRUE,
        [write("task", "/name", "set")],
        [
            bind("task", sel("owner", "children", type_is("bpmn:Task"), "flowElements")),
            set_("task", "/name", lit("Only")),
        ],
        [element_param("owner")],
    ),
    recipe(
        "clear-name",
        "edit",
        sel("target", "self"),
        TRUE,
        [write("self", "/name", "unset")],
        [{"op": "unset", "target": "self", "path": "/name"}],
        [element_param("target")],
    ),
    recipe(
        "rename-optional-task",
        "edit",
        sel("owner", "self"),
        TRUE,
        [write("task", "/name", "set")],
        [
            bind(
                "task",
                sel("owner", "children", type_is("bpmn:Task"), "flowElements"),
                "zeroOrOne",
            ),
            set_("task", "/name", lit("Only")),
        ],
        [element_param("owner")],
    ),
    ASSIGN_LANE_MEMBER_RECIPE,
    recipe(
        "move-annotation",
        "edit",
        sel("note", "self"),
        TRUE,
        [write("self", "", "reparent"), write("process", "/artifacts", "reparent")],
        [
            {
                "op": "reparent",
                "target": "self",
                "parent": "process",
                "property": "artifacts",
                "position": "last",
            }
        ],
        [element_param("note"), element_param("process")],
    ),
]

ENSURE_CONFLICT_RECIPE = recipe(
    "ensure-band-other-name",
    "normalize",
    select_all(type_is("bpmn:Process")),
    count(sel("self", "children", type_is("bpmn:DataStoreReference"), "flowElements"), 1),
    [
        write("root", "/rootElements", "create"),
        write("envelope", "/bindings", "binding"),
        write("collaboration", "/participants", "create"),
    ],
    [
        ensure_collaboration("self"),
        {
            **ensure_role(
                "band",
                "bpmn:Participant",
                "collaboration",
                "participants",
                "self",
                "reference-band",
            ),
            "fields": name_field("band"),
        },
    ],
)

CONFLICT_RECIPE = recipe(
    "orient-reference-links-both",
    "normalize",
    CN_NORMALIZE_RECIPES[4]["select"],
    TRUE,
    [write("self", "/associationDirection", "set")],
    [set_("self", "/associationDirection", lit("Both"))],
)

RELEASE_RECIPE = recipe(
    "release-marked-calls",
    "normalize",
    select_all(
        all_of(marked_call(), count(sel("self", "inverseReference", TRUE, "flowNodeRef"), 1))
    ),
    TRUE,
    [
        write("process", "/laneSets", "create"),
        write("envelope", "/bindings", "binding"),
        write("laneSet", "/lanes", "create"),
        write("business", "/flowNodeRef", "reference"),
    ],
    [
        bind("call", sel("self", "self")),
        bind("process", sel("self", "owner")),
        ensure_lane_set("process"),
        ensure_lane("process"),
        bind(
            "business",
            sel("call", "inverseReference", not_(eq(id_of("self"), id_of("lane"))), "flowNodeRef"),
            "first",
        ),
        assign("business", "/flowNodeRef", "remove", [id_of("call")]),
    ],
)

UNFIXED_N_RECIPE = recipe(
    "decorate-main-participant",
    "normalize",
    select_all(
        all_of(type_is("bpmn:Participant"), count(sel("self", "reference", TRUE, "processRef"), 1))
    ),
    TRUE,
    [write("self", "/name", "set")],
    [set_("self", "/name", {"op": "concat", "values": [read("self", "/name"), lit("*")]})],
)

MARK_PARTICIPANT_RECIPE = recipe(
    "mark-main-participant",
    "normalize",
    UNFIXED_N_RECIPE["select"],
    TRUE,
    [write("self", "/name", "set")],
    [set_("self", "/name", lit("marked"))],
)
REFUSE_MARKED_PARTICIPANT_RECIPE = refuse_named(
    "refuse-marked-participant", "normalize", "bpmn:Participant"
)


# ---------------------------------------------------------------------------
# Vendored inputs, input artifacts and profile variants (spec §2.4)
# ---------------------------------------------------------------------------

NEUTRAL = load_json(MECH / "neutral-profile.json")
GRID = load_json(MECH / "neutral-grid-profile.json")
SUPPORT_FIXTURE = load_json(MECH / "neutral-support-fixture.R31.json")
NEUTRAL_FIXTURE = load_json(MECH / "neutral-fixture.json")
GRID_FIXTURE = load_json(MECH / "neutral-grid-fixture.json")

ARTIFACTS: dict[str, bytes] = {
    "cn-base.json": pretty_bytes(CN_BASE),
    "cn-descriptors.json": pretty_bytes(CN_DESCRIPTORS),
    "support-base.json": pretty_bytes(SUPPORT_FIXTURE["base"]),  # type: ignore[index]
    "support-descriptors.json": pretty_bytes(SUPPORT_FIXTURE["descriptors"]),  # type: ignore[index]
}

SUPPORT_RECIPE_INDEX = 9
LANE_ENSURE_INDEX = 4


def _cn_identity_delta(profile_id: str) -> list[dict[str, Json]]:
    return [
        {"op": "replace", "path": "/profile", "value": profile_id},
        {"op": "replace", "path": "/version", "value": "1.0.0"},
        {
            "op": "replace",
            "path": "/base",
            "value": {
                "id": "neutral-cn-base/1",
                "version": "fixture-1",
                "sha256": raw_digest(ARTIFACTS["cn-base.json"]),
            },
        },
        {
            "op": "replace",
            "path": "/descriptors",
            "value": [
                {
                    "id": "neutral-cn-descriptors/1",
                    "version": "fixture-1",
                    "sha256": raw_digest(ARTIFACTS["cn-descriptors.json"]),
                }
            ],
        },
    ]


def _add_recipes(recipes: list[dict[str, Json]]) -> list[dict[str, Json]]:
    return [{"op": "add", "path": "/recipes/-", "value": item} for item in recipes]


def _task_ensure() -> dict[str, Json]:
    step = copy.deepcopy(SUPPORT_FIXTURE["recipe"]["steps"][LANE_ENSURE_INDEX])  # type: ignore[index]
    step.update({"type": "bpmn:Task", "parent": "self", "property": "flowElements"})
    return step


def _extraction_delta() -> list[dict[str, Json]]:
    reason = "Synthetic extraction authority for the lot-3 seal (spec section 6.1)."
    grants = [
        ("bpmn:Definitions", "/rootElements"),
        ("bpmn:Process", "/flowElements"),
        ("bpmn:ServiceTask", "/name"),
    ]
    value = [
        {"nativeType": t, "path": p, "from": "import", "to": "ai", "reason": reason}
        for t, p in grants
    ]
    return [{"op": "replace", "path": "/producerDelta", "value": value}]


VARIANT_SPECS: list[dict[str, Json]] = [
    {
        "name": "neutral",
        "source": MECH_REL + "neutral-profile.json",
        "delta": [],
        "descriptorBytes": MECH_REL + "neutral-descriptors.json",
        "baseBytes": MECH_REL + "neutral-base.json",
    },
    {
        "name": "grid",
        "source": MECH_REL + "neutral-grid-profile.json",
        "delta": [],
        "descriptorBytes": MECH_REL + "neutral-descriptors.json",
        "baseBytes": MECH_REL + "neutral-base.json",
    },
    {
        "name": "support",
        "source": MECH_REL + "neutral-profile.json",
        "delta": [
            {"op": "remove", "path": "/recipes/4"},
            {"op": "add", "path": "/recipes/-", "value": SUPPORT_FIXTURE["recipe"]},  # type: ignore[index]
            {
                "op": "replace",
                "path": "/base/sha256",
                "value": raw_digest(ARTIFACTS["support-base.json"]),
            },
            {
                "op": "replace",
                "path": "/descriptors/0/sha256",
                "value": raw_digest(ARTIFACTS["support-descriptors.json"]),
            },
        ],
        "descriptorBytes": ART_REL + "support-descriptors.json",
        "baseBytes": ART_REL + "support-base.json",
    },
    {
        "name": "support-abort",
        "parent": "support",
        "delta": [
            {
                "op": "add",
                "path": f"/recipes/{SUPPORT_RECIPE_INDEX}/steps/-",
                "value": {"op": "refuse", "code": "fixture-abort", "target": "self"},
            }
        ],
    },
    {
        "name": "support-task-ensure",
        "parent": "support",
        "delta": [
            {
                "op": "replace",
                "path": f"/recipes/{SUPPORT_RECIPE_INDEX}/steps/{LANE_ENSURE_INDEX}",
                "value": _task_ensure(),
            },
            {
                "op": "replace",
                "path": f"/recipes/{SUPPORT_RECIPE_INDEX}/writes/5",
                "value": write("self", "/flowElements", "create"),
            },
        ],
    },
    {
        "name": "grid-extraction",
        "source": MECH_REL + "neutral-grid-profile.json",
        "delta": _extraction_delta(),
        "descriptorBytes": MECH_REL + "neutral-descriptors.json",
        "baseBytes": MECH_REL + "neutral-base.json",
    },
    {
        "name": "cn-c",
        "source": MECH_REL + "neutral-profile.json",
        "delta": _cn_identity_delta("neutral-cn-c/1") + _add_recipes(CN_COMPLETE_RECIPES),
        "descriptorBytes": ART_REL + "cn-descriptors.json",
        "baseBytes": ART_REL + "cn-base.json",
    },
    {
        "name": "cn-c-unfixed",
        "parent": "cn-c",
        "delta": [
            {"op": "replace", "path": "/profile", "value": "neutral-cn-c-unfixed/1"},
            *_add_recipes([SUFFIX_RECIPE]),
        ],
    },
    {
        "name": "cn-c-noauth",
        "parent": "cn-c",
        "delta": [
            {"op": "replace", "path": "/profile", "value": "neutral-cn-c-noauth/1"},
            {
                "op": "replace",
                "path": "/producerDelta",
                "value": [
                    {
                        "nativeType": "bpmn:DataInputAssociation",
                        "path": "/targetRef",
                        "from": "code",
                        "to": "dropped",
                        "reason": "Synthetic withdrawal of port authority (spec section 2.4).",
                    }
                ],
            },
        ],
    },
    {
        "name": "cn-n",
        "source": MECH_REL + "neutral-profile.json",
        "delta": [
            *_cn_identity_delta("neutral-cn-n/1"),
            {"op": "remove", "path": "/recipes/4"},
            *_add_recipes(CN_NORMALIZE_RECIPES),
            *_add_recipes(CN_COMMAND_RECIPES),
        ],
        "descriptorBytes": ART_REL + "cn-descriptors.json",
        "baseBytes": ART_REL + "cn-base.json",
    },
    {
        "name": "cn-n-conflict",
        "parent": "cn-n",
        "delta": [
            {"op": "replace", "path": "/profile", "value": "neutral-cn-n-conflict/1"},
            *_add_recipes([CONFLICT_RECIPE]),
        ],
    },
    {
        "name": "cn-n-relocate",
        "parent": "cn-n",
        "delta": [
            {"op": "replace", "path": "/profile", "value": "neutral-cn-n-relocate/1"},
            *_add_recipes([RELEASE_RECIPE]),
        ],
    },
    {
        "name": "cn-n-unfixed",
        "parent": "cn-n",
        "delta": [
            {"op": "replace", "path": "/profile", "value": "neutral-cn-n-unfixed/1"},
            *_add_recipes([UNFIXED_N_RECIPE]),
        ],
    },
    {
        "name": "cn-n-ensure-conflict",
        "parent": "cn-n",
        "delta": [
            {"op": "replace", "path": "/profile", "value": "neutral-cn-n-ensure-conflict/1"},
            *_add_recipes([ENSURE_CONFLICT_RECIPE]),
        ],
    },
    {
        "name": "support-no-binding-write",
        "parent": "support",
        "delta": [{"op": "remove", "path": f"/recipes/{SUPPORT_RECIPE_INDEX}/writes/1"}],
    },
    {
        "name": "support-cmd",
        "parent": "support",
        "delta": [
            {"op": "replace", "path": "/profile", "value": "neutral-support-cmd/1"},
            *_add_recipes([ASSIGN_LANE_MEMBER_RECIPE]),
        ],
    },
    {
        "name": "cn-c-second-pass",
        "parent": "cn-c",
        "delta": [
            {"op": "replace", "path": "/profile", "value": "neutral-cn-c-second-pass/1"},
            *_add_recipes([MARK_TASK_RECIPE, REFUSE_MARKED_TASK_RECIPE]),
        ],
    },
    {
        "name": "cn-n-second-pass",
        "parent": "cn-n",
        "delta": [
            {"op": "replace", "path": "/profile", "value": "neutral-cn-n-second-pass/1"},
            *_add_recipes([MARK_PARTICIPANT_RECIPE, REFUSE_MARKED_PARTICIPANT_RECIPE]),
        ],
    },
    {
        "name": "neutral-containment-task",
        "parent": "neutral",
        "delta": [
            {
                "op": "replace",
                "path": "/recipes/0/steps/0",
                "value": {
                    "op": "create",
                    "as": "created",
                    "type": "bpmn:Task",
                    "parent": "owner",
                    "property": "flowElements",
                    "identity": "containment",
                    "fields": [{"name": "name", "value": param("name")}],
                },
            }
        ],
    },
]


def _spec(name: str) -> dict[str, Json]:
    for item in VARIANT_SPECS:
        if item["name"] == name:
            return item
    message = f"unknown variant {name}"
    raise KeyError(message)


def resolve_variant(name: str) -> dict[str, Json]:
    """Apply one variant delta chain to its vendored source profile."""
    item = _spec(name)
    parent = item.get("parent")
    base = resolve_variant(str(parent)) if parent else load_json(ROOT / str(item["source"]))
    return apply_patch(base, item["delta"])  # type: ignore[arg-type,return-value]


def variant_files(name: str) -> tuple[str, str]:
    """Return the descriptor and base byte paths of one variant (inherited)."""
    item = _spec(name)
    if "descriptorBytes" in item:
        return str(item["descriptorBytes"]), str(item["baseBytes"])
    return variant_files(str(item["parent"]))


def identity_of(profile: dict[str, Json]) -> dict[str, Json]:
    """Return the §5.1 profileIdentity record of one compiled profile."""
    return {
        "mechanismVersion": profile["mechanismVersion"],
        "schemaVersion": profile["schemaVersion"],
        "profile": profile["profile"],
        "version": profile["version"],
        "sha256": digest(profile),
        "base": copy.deepcopy(profile["base"]),
        "descriptors": copy.deepcopy(profile["descriptors"]),
    }


PROFILES: dict[str, dict[str, Json]] = {
    str(item["name"]): resolve_variant(str(item["name"])) for item in VARIANT_SPECS
}
IDENTITY: dict[str, dict[str, Json]] = {name: identity_of(p) for name, p in PROFILES.items()}


def variants_document() -> dict[str, Json]:
    """Return the sealed profile-variants artifact."""
    rows = []
    for item in VARIANT_SPECS:
        name = str(item["name"])
        descriptors, base = variant_files(name)
        row: dict[str, Json] = {"name": name}
        if "parent" in item:
            row["parent"] = item["parent"]
        else:
            row["source"] = item["source"]
        row["delta"] = item["delta"]
        row["descriptorBytes"] = descriptors
        row["baseBytes"] = base
        row["identity"] = IDENTITY[name]
        rows.append(row)
    return {
        "author": AUTHOR,
        "format": "profile-variants/1",
        "note": (
            "Each variant is the vendored source profile (or its parent variant) with the"
            " explicit RFC 6902 add/replace/remove delta applied in order. identity is the"
            " DESIGN R3.3 section 5.1 profileIdentity of the result; sha256 is H(profile)."
            " Load the variant with the listed descriptor and base bytes."
        ),
        "variants": rows,
    }


# ---------------------------------------------------------------------------
# Case assembly helpers
# ---------------------------------------------------------------------------


def ptr(*parts: object) -> str:
    """Build one RFC 6901 pointer from unescaped segments."""
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def result_note(expected: Json) -> str:
    """Return the shared Result/1 shape sentence of one sealed case (H B2, B3, B4)."""
    if not isinstance(expected, dict) or "report" not in expected or "status" not in expected:
        return ""
    if expected["status"] == "ok":
        return (
            " Report header (H B4): sourceIdentity and targetIdentity are the envelope"
            " identity, inputRevision is baseRevision, outputRevision is revision."
        )
    if "profileIdentity" in expected:
        return (
            " Refusal record (H B2, B3, B4): no candidate; diagnostics and report entries"
            " are empty (no lint stage ran); the input identity and revision are echoed and"
            " repeated as report sourceIdentity and inputRevision."
        )
    return (
        " Refusal record (H B2, B3, B4): no candidate; diagnostics and report entries are"
        " empty; nothing is echoed."
    )


def make_case(  # noqa: PLR0913, PLR0917
    cid: str,
    clause: str,
    derivation: str,
    operation: str,
    profile: str | None,
    inp: Json,
    expected: Json,
    *,
    fixed_point: bool = False,
) -> dict[str, Json]:
    """Return one sealed case record (Result/1 cases get the shared shape note)."""
    record: dict[str, Json] = {
        "case": cid,
        "clause": clause,
        "author": AUTHOR,
        "operation": operation,
        "profile": profile,
        "derivation": derivation + result_note(expected),
        "input": inp,
        "expected": expected,
    }
    if fixed_point:
        record["fixedPoint"] = True
    return record


def alloc(pointer: str, source_target: str | None, new_id: str) -> dict[str, Json]:
    """Return one C identity allocation entry (C never moves a node).

    H B9: both coordinates address the written location ``<element>/id``; the
    source targetId is the nearest original ID-bearing ancestor (or null).
    """
    return change(
        "complete",
        "allocate-id",
        "stable-id/1",
        coord(at_property(pointer, "id"), source_target),
        coord(at_property(pointer, "id"), new_id, "generated"),
        "id",
        after=new_id,
    )


def edit_entry(  # noqa: PLR0913, PLR0917
    stage: str,
    op: str,
    rule: str,
    pointer: str,
    target: str,
    prop: str,
    *,
    before: Json = ABSENT,
    after: Json = ABSENT,
    created: bool = False,
    source_target: Json = SAME,
    allocated: bool = False,
) -> dict[str, Json]:
    """Return one set/unset/assignRef change entry on one element.

    ``source_target`` defaults to the result target; an element whose id C
    allocated in the same operation passes its original source targetId.
    H B9: source and result pointers address the written location, the
    element pointer plus the escaped property, also when it was absent.
    """
    written = at_property(pointer, prop)
    if created:
        source = NONE_COORD
    else:
        source = coord(written, target if source_target is SAME else source_target)  # type: ignore[arg-type]
    provenance = "generated" if created or allocated else "exact"
    return change(
        stage,
        op,
        rule,
        source,
        coord(written, target, provenance),
        prop,
        before=before,
        after=after,
    )


def empty_topology(  # noqa: PLR0913
    pointer: str,
    target: str,
    props: tuple[str, ...] = ("incoming", "outgoing"),
    *,
    rule: str = "complete-task-topology",
    source_target: Json = SAME,
    allocated: bool = False,
) -> list[dict[str, Json]]:
    """Return the absent -> [] topology entries of one flowless flow node (H F1)."""
    return [
        edit_entry(
            "complete",
            "assignRef",
            rule,
            pointer,
            target,
            prop,
            after=[],
            source_target=source_target,
            allocated=allocated,
        )
        for prop in props
    ]


def create_entry(stage: str, op: str, rule: str, tree: Json, pointer: str) -> dict[str, Json]:
    """Return one creation entry whose after is the final subtree at ``pointer``.

    H B9: a created element is addressed by its own pointer; property is the
    containment property; source is the none/generated coordinate.
    """
    node = at(tree, pointer)
    prop = pointer.split("/")[-2]
    return change(
        stage,
        op,
        rule,
        NONE_COORD,
        coord(pointer, node["id"], "generated"),  # type: ignore[index]
        prop,
        after=node,
    )


def complete_case(  # noqa: PLR0913, PLR0917
    cid: str,
    clause: str,
    derivation: str,
    variant: str,
    tree_in: Json,
    tree_out: Json,
    entries: list[dict[str, Json]],
    *,
    mode: str = "retained",
    activation: str = "edit",
) -> dict[str, Json]:
    """Return one accepted complete case with its exact Result/1."""
    ident = IDENTITY[variant]
    env_in = envelope(ident, tree_in, [])
    env_out = envelope(ident, tree_out, [])
    base, rev = str(env_in["semanticRevision"]), str(env_out["semanticRevision"])
    rep = success_report("complete", ident, base, rev, entries)
    expected = ok_result("complete", ident, base, rev, rep, env_out)
    inp = {"envelope": env_in, "mode": mode, "activation": activation}
    return make_case(cid, clause, derivation, "complete", variant, inp, expected, fixed_point=True)


def echo_fields(env_in: Json) -> tuple[Json, str | None]:
    """Return the (profileIdentity, baseRevision) a refusal echoes (H B3), or Nones."""
    if not echoes(env_in):
        return None, None
    return env_in["profileIdentity"], str(env_in["semanticRevision"])  # type: ignore[index]


def complete_refusal(  # noqa: PLR0913, PLR0917
    cid: str,
    clause: str,
    derivation: str,
    variant: str,
    env_in: dict[str, Json],
    code: str,
    *,
    mode: str = "retained",
    activation: str = "edit",
) -> dict[str, Json]:
    """Return one refused complete case (input envelope given exactly)."""
    identity, base = echo_fields(env_in)
    expected = refused_result("complete", code, identity, base)
    inp = {"envelope": env_in, "mode": mode, "activation": activation}
    return make_case(cid, clause, derivation, "complete", variant, inp, expected)


def definitions(def_id: str | None, *roots: Json) -> dict[str, Json]:
    """Return one Definitions tree (``def_id`` None means initially ID-less)."""
    tree: dict[str, Json] = {"$type": "bpmn:Definitions"}
    if def_id is not None:
        tree["id"] = def_id
    tree["rootElements"] = list(roots)
    return tree


def node(type_name: str, node_id: str | None = None, **members: Json) -> dict[str, Json]:
    """Return one native element literal (``node_id`` None means ID-less)."""
    record: dict[str, Json] = {"$type": "bpmn:" + type_name}
    if node_id is not None:
        record["id"] = node_id
    record.update(members)
    return record


def doc(text: str, text_format: str | None = None) -> dict[str, Json]:
    """Return one ID-less Documentation literal."""
    record: dict[str, Json] = {"$type": "bpmn:Documentation", "text": text}
    if text_format is not None:
        record["textFormat"] = text_format
    return record


def flow(flow_id: str, source: str, target: str) -> dict[str, Json]:
    """Return one SequenceFlow literal."""
    return node("SequenceFlow", flow_id, sourceRef=source, targetRef=target)


def with_ids(tree: Json, assignments: dict[str, str]) -> Json:
    """Return a copy of ``tree`` with ``id`` written at the given pointers."""
    result = copy.deepcopy(tree)
    for pointer, new_id in assignments.items():
        target = at(result, pointer)
        target["id"] = new_id  # type: ignore[index]
    return result


def with_members(tree: Json, pointer: str, **members: Json) -> Json:
    """Return a copy of ``tree`` with members written on the node at ``pointer``."""
    result = copy.deepcopy(tree)
    target = at(result, pointer)
    target.update(copy.deepcopy(members))  # type: ignore[union-attr]
    return result


DEF_ROOT_ID = sid("document-root/1", "definitions", "root")


def slot(parent_type: str, prop: str) -> str:
    """Return the C identity slot: containing $type, '.', containment property (H D1)."""
    return parent_type + "." + prop


SLOT_ROOT = slot("bpmn:Definitions", "rootElements")
SLOT_FLOW = slot("bpmn:Process", "flowElements")
SLOT_EVENT_DEFINITIONS = slot("bpmn:StartEvent", "eventDefinitions")

C_CLAUSE_ID = "DESIGN R3.3 §3.2 ID allocation; §7.1 Completion C (Identity/defaults, Process)"
C_CLAUSE_TOPOLOGY = "DESIGN R3.3 §7.1 Completion C (Topology); §2.2 ids; §2.4 assignRef"
C_CLAUSE_ITEM = "DESIGN R3.3 §7.1 Completion C (Internal item); §2.4 create, assignRef"
C_CLAUSE_PORTS = "DESIGN R3.3 §7.1 Completion C (Ports); §13 OPEN-IO; §16 item 8"
C_CLAUSE_SETS = "DESIGN R3.3 §7.1 Completion C (Sets); §16 item 8"
C_CLAUSE_CONTENT = "DESIGN R3.3 §7.1 Completion C (Content); §3.2 identity mode containment"
FIXED_POINT = "DESIGN R3.3 §2.4 fixed point; §7.3 Fixed-point and preservation proofs"


# ---------------------------------------------------------------------------
# Cases for the complete operation
# ---------------------------------------------------------------------------


def _identity_tree(task_type: str) -> dict[str, Json]:
    return definitions(
        None,
        node(
            "Process",
            flowElements=[
                node(task_type, name="Review"),
                node(task_type, name="Review"),
                node(task_type, "Task_kept", name="Kept"),
                node(task_type, name="Other", documentation=[doc("Source note")]),
            ],
        ),
        node("Process", "Process_empty"),
    )


def _identity_case(cid: str, variant: str, task_type: str, *, executable: bool) -> dict[str, Json]:
    tree_in = _identity_tree(task_type)
    process_node = at(tree_in, ptr("rootElements", 0))
    process_id = c_id(DEF_ROOT_ID, SLOT_ROOT, process_node, 0)
    review = {"$type": "bpmn:" + task_type, "name": "Review"}
    other = at(tree_in, ptr("rootElements", 0, "flowElements", 3))
    t0 = c_id(process_id, SLOT_FLOW, review, 0)
    t1 = c_id(process_id, SLOT_FLOW, review, 1)
    t3 = c_id(process_id, SLOT_FLOW, other, 0)
    tree_out = with_ids(
        tree_in,
        {
            "": DEF_ROOT_ID,
            ptr("rootElements", 0): process_id,
            ptr("rootElements", 0, "flowElements", 0): t0,
            ptr("rootElements", 0, "flowElements", 1): t1,
            ptr("rootElements", 0, "flowElements", 3): t3,
        },
    )
    tree_out = with_members(tree_out, ptr("rootElements", 0), isExecutable=executable)
    tree_out = with_members(tree_out, ptr("rootElements", 1), isExecutable=executable)
    entries = [
        alloc("", None, DEF_ROOT_ID),
        alloc(ptr("rootElements", 0), None, process_id),
        alloc(ptr("rootElements", 0, "flowElements", 0), None, t0),
        alloc(ptr("rootElements", 0, "flowElements", 1), None, t1),
        alloc(ptr("rootElements", 0, "flowElements", 3), None, t3),
        # The allocated Process existed without an id and has no original
        # ID-bearing ancestor: its source targetId stays null.
        edit_entry(
            "complete",
            "set",
            "complete-process",
            ptr("rootElements", 0),
            process_id,
            "isExecutable",
            after=executable,
            source_target=None,
            allocated=True,
        ),
        edit_entry(
            "complete",
            "set",
            "complete-process",
            ptr("rootElements", 1),
            "Process_empty",
            "isExecutable",
            after=executable,
        ),
    ]
    derivation = (
        "C first allocates the missing Definitions id with owner document-root/1, slot"
        " definitions, key root, then fills missing child ids top-down with ownerId = the"
        " containing element id, slot = the descriptor-qualified containment property"
        " <containing $type>.<property> (bpmn:Definitions.rootElements,"
        " bpmn:Process.flowElements; H D1) and stableKey = JCS([contentSignature,"
        " duplicateOrdinal]); the two identical ID-less Review tasks get ordinals 0 and 1,"
        " Task_kept and Process_empty keep their ids, the ID-less Documentation stays ID-less."
        f" The profile complete-process recipe then sets isExecutable={str(executable).lower()}"
        " on every Process including the empty one (the neutral profiles declare no topology"
        " recipe and their Task types no incoming/outgoing). Entries address the written"
        " location (<element>/id, <element>/isExecutable; H B9) and are sorted per §10.1"
        " plus the H G2 tie-breaks."
    )
    return complete_case(cid, C_CLAUSE_ID, derivation, variant, tree_in, tree_out, entries)


def case_c_identity_neutral() -> dict[str, Json]:
    """C identity allocation and isExecutable=false on the neutral profile."""
    return _identity_case("cn-c-identity-neutral", "neutral", "Task", executable=False)


def case_c_identity_grid() -> dict[str, Json]:
    """C identity allocation and isExecutable=true on the grid profile."""
    return _identity_case("cn-c-identity-grid", "grid", "ServiceTask", executable=True)


def _executable_case(cid: str, variant: str, task_type: str, *, value: bool) -> dict[str, Json]:
    tree_in = definitions(
        "Definitions_exec",
        node(
            "Process",
            "Process_main",
            isExecutable=not value,
            flowElements=[node(task_type, "Task_main", name="Work")],
        ),
        node("Process", "Process_empty"),
    )
    tree_out = with_members(tree_in, ptr("rootElements", 0), isExecutable=value)
    tree_out = with_members(tree_out, ptr("rootElements", 1), isExecutable=value)
    entries = [
        edit_entry(
            "complete",
            "set",
            "complete-process",
            ptr("rootElements", 0),
            "Process_main",
            "isExecutable",
            before=not value,
            after=value,
        ),
        edit_entry(
            "complete",
            "set",
            "complete-process",
            ptr("rootElements", 1),
            "Process_empty",
            "isExecutable",
            after=value,
        ),
    ]
    derivation = (
        f"The {variant} profile's only complete recipe sets isExecutable to the literal"
        f" {str(value).lower()} on every Process: the existing opposite value is overwritten"
        " (set has no only-if-absent mode) and the empty Process receives it too. The two"
        " neutral profiles choose opposite literals, so a hard-coded default fails one case."
    )
    return complete_case(
        cid,
        "DESIGN R3.3 §7.1 Completion C (Process); §14.4",
        derivation,
        variant,
        tree_in,
        tree_out,
        entries,
    )


def case_c_is_executable_neutral() -> dict[str, Json]:
    """Neutral profile writes isExecutable=false, including on empty Processes."""
    return _executable_case("cn-c-is-executable-neutral", "neutral", "Task", value=False)


def case_c_is_executable_grid() -> dict[str, Json]:
    """Grid profile writes isExecutable=true, including on empty Processes."""
    return _executable_case("cn-c-is-executable-grid", "grid", "ServiceTask", value=True)


def _mismatch_identity(variant: str, version: str, sha: str) -> dict[str, Json]:
    ident = copy.deepcopy(IDENTITY[variant])
    ident["version"] = version
    ident["sha256"] = sha
    return ident


def case_c_version_mismatch_first() -> dict[str, Json]:
    """An older document minor refuses before any C identity allocation."""
    ident = _mismatch_identity("neutral", "1.0.0", "1" * 64)
    env_in = envelope(ident, _identity_tree("Task"), [])
    derivation = (
        "The envelope identity differs from the compiled neutral identity only by an older"
        " minor version (1.0.0 vs 1.1.0) and its digest. §3.3 rows apply before C"
        " (precedence step 3, H C1): the minor row is source-dependent and C/N never load"
        " another package, so P1 yields profile-source-unavailable before any id is"
        " allocated (§7.1 reject source version mismatch first). The input tree has missing"
        " ids that must stay missing."
    )
    return complete_refusal(
        "cn-c-version-mismatch-first",
        "DESIGN R3.3 §7.1 Identity/defaults (reject source version mismatch first); §3.3 P1",
        derivation,
        "neutral",
        env_in,
        "profile-source-unavailable",
    )


def case_c_digest_mismatch_first() -> dict[str, Json]:
    """Same id and version with unequal known digests refuses before C."""
    ident = _mismatch_identity("grid", "2.0.0", "2" * 64)
    env_in = envelope(ident, _identity_tree("ServiceTask"), [])
    derivation = (
        "Same profile id and version as the compiled grid profile, known unequal digests:"
        " the §3.3 identity-conflict row refuses profile-digest-mismatch (no P1 override)"
        " before any C write (precedence step 3)."
    )
    return complete_refusal(
        "cn-c-digest-mismatch-first",
        "DESIGN R3.3 §7.1 Identity/defaults; §3.3 same-version digest row",
        derivation,
        "grid",
        env_in,
        "profile-digest-mismatch",
    )


def case_c_document_version() -> dict[str, Json]:
    """An unknown envelope documentVersion refuses before C (no echoed identity)."""
    env_in = envelope(IDENTITY["neutral"], _identity_tree("Task"), [])
    env_in["documentVersion"] = "2"
    derivation = (
        "documentVersion 2 is unknown: the first §3.3 row (and the closed §5.1 envelope"
        " check, precedence step 2) refuses document-version-unsupported. An unknown"
        " documentVersion is the H B3 no-echo case, so the refusal and its report carry"
        " neither profileIdentity/sourceIdentity nor baseRevision/inputRevision (§10.1:"
        " missing identity is omitted, not fabricated)."
    )
    return complete_refusal(
        "cn-c-document-version",
        "DESIGN R3.3 §3.3 row 1; §5.1; §10.1 missing identity omitted",
        derivation,
        "neutral",
        env_in,
        "document-version-unsupported",
    )


def _gateway_tree() -> dict[str, Json]:
    return definitions(
        "Definitions_G",
        node(
            "Process",
            "Process_G",
            isExecutable=False,
            flowElements=[
                node("StartEvent", "S1"),
                node("StartEvent", "S2"),
                node("ExclusiveGateway", "G_div"),
                node("ExclusiveGateway", "G_mix", incoming=["F4", "F2"], outgoing=["F6"]),
                node("ExclusiveGateway", "G_conv", gatewayDirection="Diverging"),
                node("ExclusiveGateway", "G_none"),
                node("Task", "T_end", name="End work"),
                node("Task", "T_end2", name="Other end work"),
                flow("F1", "S1", "G_div"),
                flow("F2", "G_div", "G_mix"),
                flow("F3", "G_div", "G_conv"),
                flow("F4", "G_none", "G_mix"),
                flow("F5", "G_mix", "G_conv"),
                flow("F6", "G_mix", "T_end"),
                flow("F7", "G_conv", "T_end2"),
                flow("F8", "S2", "G_none"),
            ],
        ),
    )


def case_c_gateway_direction() -> dict[str, Json]:
    """GatewayDirection four cases plus derived incoming/outgoing arrays."""
    tree_in = _gateway_tree()
    fe = ptr("rootElements", 0, "flowElements")
    updates = {
        0: {"outgoing": ["F1"]},
        1: {"outgoing": ["F8"]},
        2: {"incoming": ["F1"], "outgoing": ["F2", "F3"], "gatewayDirection": "Diverging"},
        3: {"incoming": ["F2", "F4"], "outgoing": ["F5", "F6"], "gatewayDirection": "Mixed"},
        4: {"incoming": ["F3", "F5"], "outgoing": ["F7"], "gatewayDirection": "Converging"},
        5: {"incoming": ["F8"], "outgoing": ["F4"], "gatewayDirection": "Unspecified"},
        6: {"incoming": ["F6"], "outgoing": []},
        7: {"incoming": ["F7"], "outgoing": []},
    }
    tree_out = tree_in
    for index, members in updates.items():
        tree_out = with_members(tree_out, f"{fe}/{index}", **members)

    def ref(rule: str, index: int, target: str, prop: str, before: Json = ABSENT) -> Json:
        return edit_entry(
            "complete",
            "assignRef",
            rule,
            f"{fe}/{index}",
            target,
            prop,
            before=before,
            after=updates[index][prop],
        )

    def direction(rule: str, index: int, target: str, before: Json = ABSENT) -> Json:
        return edit_entry(
            "complete",
            "set",
            rule,
            f"{fe}/{index}",
            target,
            "gatewayDirection",
            before=before,
            after=updates[index]["gatewayDirection"],
        )

    entries = [
        ref("complete-start-topology", 0, "S1", "outgoing"),
        ref("complete-start-topology", 1, "S2", "outgoing"),
        ref("complete-gateway-topology", 2, "G_div", "incoming"),
        ref("complete-gateway-topology", 2, "G_div", "outgoing"),
        ref("complete-gateway-topology", 3, "G_mix", "incoming", ["F4", "F2"]),
        ref("complete-gateway-topology", 3, "G_mix", "outgoing", ["F6"]),
        ref("complete-gateway-topology", 4, "G_conv", "incoming"),
        ref("complete-gateway-topology", 4, "G_conv", "outgoing"),
        ref("complete-gateway-topology", 5, "G_none", "incoming"),
        ref("complete-gateway-topology", 5, "G_none", "outgoing"),
        ref("complete-task-topology", 6, "T_end", "incoming"),
        ref("complete-task-topology", 6, "T_end", "outgoing"),
        ref("complete-task-topology", 7, "T_end2", "incoming"),
        ref("complete-task-topology", 7, "T_end2", "outgoing"),
        direction("gateway-direction-diverging", 2, "G_div"),
        direction("gateway-direction-mixed", 3, "G_mix"),
        direction("gateway-direction-converging", 4, "G_conv", "Diverging"),
        direction("gateway-direction-unspecified", 5, "G_none"),
    ]
    derivation = (
        "Counting SequenceFlows that target/source each gateway: G_mix 2 in/2 out -> Mixed,"
        " G_conv 2 in/1 out -> Converging (the stored Diverging is corrected), G_div 1 in/2 out"
        " -> Diverging, G_none 1 in/1 out -> Unspecified. The topology recipes replace stored"
        " incoming/outgoing with the same-container flow ids in UTF-16 id order (G_mix stale"
        " [F4,F2]/[F6] become [F2,F4]/[F5,F6]); the end tasks T_end and T_end2 have no"
        " outgoing flow, so replace writes an empty outgoing array (absent -> [] is a change,"
        " H F1): 18 entries. Directions use the flows, never the stale stored arrays."
    )
    return complete_case(
        "cn-c-gateway-direction",
        C_CLAUSE_TOPOLOGY,
        derivation,
        "cn-c",
        tree_in,
        tree_out,
        entries,
    )


def case_c_gateway_direction_control() -> dict[str, Json]:
    """The plain neutral profile has no topology policy: gateways stay untouched."""
    tree_in = definitions(
        "Definitions_ctl",
        node(
            "Process",
            "Process_ctl",
            flowElements=[
                node("StartEvent", "S1"),
                node("ExclusiveGateway", "G_ctl", incoming=["F2"]),
                node("Task", "T_ctl", name="Work"),
                flow("F1", "S1", "G_ctl"),
                flow("F2", "G_ctl", "T_ctl"),
            ],
        ),
    )
    tree_out = with_members(tree_in, ptr("rootElements", 0), isExecutable=False)
    entries = [
        edit_entry(
            "complete",
            "set",
            "complete-process",
            ptr("rootElements", 0),
            "Process_ctl",
            "isExecutable",
            after=False,
        )
    ]
    derivation = (
        "The topology and GatewayDirection rules are private effective-base policy data, not"
        " library rules (§7.1). The neutral profile declares none, so C changes only"
        " isExecutable: the stale G_ctl incoming [F2], the absent S1 outgoing and the absent"
        " gatewayDirection stay exactly as imported."
    )
    return complete_case(
        "cn-c-gateway-direction-control",
        "DESIGN R3.3 §7.1 (private policy, not a universal library rule); §14.4",
        derivation,
        "neutral",
        tree_in,
        tree_out,
        entries,
    )


def case_c_topology_per_container() -> dict[str, Json]:
    """Per-container incoming/outgoing; the cross-container flow is never retargeted."""
    tree_in = definitions(
        "Definitions_top",
        node(
            "Process",
            "Process_A",
            isExecutable=False,
            flowElements=[
                node("StartEvent", "S_A"),
                node("ExclusiveGateway", "G_A", outgoing=["F_A1", "F_A2"]),
                node("Task", "T_A1", name="First", outgoing=["F_X"]),
                node("Task", "T_A2", name="Second", incoming=["F_X"]),
                flow("F_A1", "S_A", "G_A"),
                flow("F_A2", "G_A", "T_A1"),
            ],
        ),
        node(
            "Process",
            "Process_B",
            isExecutable=False,
            flowElements=[
                node("Task", "T_B1", name="Third", outgoing=["F_X"]),
                node("Task", "T_B2", name="Fourth"),
                flow("F_B1", "T_B1", "T_B2"),
                flow("F_X", "T_A1", "T_A2"),
            ],
        ),
    )
    a = ptr("rootElements", 0, "flowElements")
    b = ptr("rootElements", 1, "flowElements")
    tree_out = with_members(tree_in, f"{a}/0", outgoing=["F_A1"])
    tree_out = with_members(
        tree_out, f"{a}/1", incoming=["F_A1"], outgoing=["F_A2"], gatewayDirection="Unspecified"
    )
    tree_out = with_members(tree_out, f"{a}/2", incoming=["F_A2"], outgoing=[])
    tree_out = with_members(tree_out, f"{a}/3", incoming=[], outgoing=[])
    tree_out = with_members(tree_out, f"{b}/0", incoming=[], outgoing=["F_B1"])
    tree_out = with_members(tree_out, f"{b}/1", incoming=["F_B1"], outgoing=[])
    entries = [
        edit_entry(
            "complete",
            "assignRef",
            "complete-start-topology",
            f"{a}/0",
            "S_A",
            "outgoing",
            after=["F_A1"],
        ),
        edit_entry(
            "complete",
            "assignRef",
            "complete-gateway-topology",
            f"{a}/1",
            "G_A",
            "incoming",
            after=["F_A1"],
        ),
        edit_entry(
            "complete",
            "assignRef",
            "complete-gateway-topology",
            f"{a}/1",
            "G_A",
            "outgoing",
            before=["F_A1", "F_A2"],
            after=["F_A2"],
        ),
        edit_entry(
            "complete",
            "assignRef",
            "complete-task-topology",
            f"{a}/2",
            "T_A1",
            "incoming",
            after=["F_A2"],
        ),
        edit_entry(
            "complete",
            "assignRef",
            "complete-task-topology",
            f"{a}/2",
            "T_A1",
            "outgoing",
            before=["F_X"],
            after=[],
        ),
        edit_entry(
            "complete",
            "assignRef",
            "complete-task-topology",
            f"{a}/3",
            "T_A2",
            "incoming",
            before=["F_X"],
            after=[],
        ),
        edit_entry(
            "complete",
            "assignRef",
            "complete-task-topology",
            f"{a}/3",
            "T_A2",
            "outgoing",
            after=[],
        ),
        edit_entry(
            "complete",
            "assignRef",
            "complete-task-topology",
            f"{b}/0",
            "T_B1",
            "incoming",
            after=[],
        ),
        edit_entry(
            "complete",
            "assignRef",
            "complete-task-topology",
            f"{b}/0",
            "T_B1",
            "outgoing",
            before=["F_X"],
            after=["F_B1"],
        ),
        edit_entry(
            "complete",
            "assignRef",
            "complete-task-topology",
            f"{b}/1",
            "T_B2",
            "incoming",
            after=["F_B1"],
        ),
        edit_entry(
            "complete",
            "assignRef",
            "complete-task-topology",
            f"{b}/1",
            "T_B2",
            "outgoing",
            after=[],
        ),
        edit_entry(
            "complete",
            "set",
            "gateway-direction-unspecified",
            f"{a}/1",
            "G_A",
            "gatewayDirection",
            after="Unspecified",
        ),
    ]
    derivation = (
        "F_X lives in Process_B but connects T_A1 to T_A2 of Process_A: it is an invalid"
        " cross-container flow (its endpoints exist with admitted types, so it is not a"
        " dangling reference). Derived arrays keep only flows owned by the node's own"
        " container, so F_X leaves T_A1.outgoing and T_A2.incoming, which become [] (an"
        " emptied array stays [], H F1), T_B1.outgoing becomes [F_B1], and every task"
        " without a same-container flow on one side receives [] (absent -> [] is a change:"
        " T_A2.outgoing, T_B1.incoming, T_B2.outgoing). F_X itself keeps its"
        " sourceRef/targetRef (never retargeted, moved or deleted). G_A has one inverse flow"
        " each way -> Unspecified. 12 entries."
    )
    return complete_case(
        "cn-c-topology-per-container",
        C_CLAUSE_TOPOLOGY,
        derivation,
        "cn-c",
        tree_in,
        tree_out,
        entries,
    )


def case_c_backing_object() -> dict[str, Json]:
    """Missing backing DataObjects are created; valid backing and stores untouched."""
    tree_in = definitions(
        "Definitions_item",
        node(
            "Process",
            "Process_D",
            isExecutable=False,
            flowElements=[
                node("DataObjectReference", "Ref_new", name="Draft form"),
                node("DataObjectReference", "Ref_kept", dataObjectRef="DataObject_kept"),
                node("DataObject", "DataObject_kept"),
                node("DataObjectReference", "Ref_store", name="Archive store"),
                node("DataStoreReference", "StoreRef_1", name="Archive"),
            ],
        ),
    )
    fe = ptr("rootElements", 0, "flowElements")
    do_new = sid("Process_D", "backing-object", "Ref_new")
    do_store = sid("Process_D", "backing-object", "Ref_store")
    tree_out = copy.deepcopy(tree_in)
    at(tree_out, fe).extend([node("DataObject", do_new), node("DataObject", do_store)])  # type: ignore[attr-defined]
    tree_out = with_members(tree_out, f"{fe}/0", dataObjectRef=do_new)
    tree_out = with_members(tree_out, f"{fe}/3", dataObjectRef=do_store)
    rule = "complete-backing-object"
    entries = [
        create_entry("complete", "create", rule, tree_out, f"{fe}/5"),
        create_entry("complete", "create", rule, tree_out, f"{fe}/6"),
        edit_entry(
            "complete", "assignRef", rule, f"{fe}/0", "Ref_new", "dataObjectRef", after=do_new
        ),
        edit_entry(
            "complete", "assignRef", rule, f"{fe}/3", "Ref_store", "dataObjectRef", after=do_store
        ),
    ]
    derivation = (
        "Candidates are the DataObjectReferences without dataObjectRef in id order (Ref_new,"
        " Ref_store). Each gets a DataObject allocated as stable-id(Process_D, backing-object,"
        " <reference id>), appended to Process_D.flowElements in candidate order, then the"
        " reference is assigned. Ref_kept's valid backing is preserved; the name 'Archive"
        " store' does not make a DataStore and the DataStoreReference without store gets none."
    )
    return complete_case(
        "cn-c-backing-object", C_CLAUSE_ITEM, derivation, "cn-c", tree_in, tree_out, entries
    )


def _input_port_tree() -> dict[str, Json]:
    return definitions(
        "Definitions_port",
        node(
            "Process",
            "Process_P",
            isExecutable=False,
            flowElements=[
                node("DataObject", "DO_P"),
                node("DataObjectReference", "Ref_P", dataObjectRef="DO_P"),
                node(
                    "Task",
                    "Task_P",
                    name="Use input",
                    properties=[node("Property", "Prop_valid")],
                    dataInputAssociations=[
                        node(
                            "DataInputAssociation",
                            "DIA_valid",
                            sourceRef=["Ref_P"],
                            targetRef="Prop_valid",
                        ),
                        node("DataInputAssociation", "DIA_missing", sourceRef=["Ref_P"]),
                    ],
                ),
            ],
        ),
    )


def case_c_input_port() -> dict[str, Json]:
    """Valid ports preserved; the missing input port is keyed by its association."""
    tree_in = _input_port_tree()
    task = ptr("rootElements", 0, "flowElements", 2)
    port = sid("Task_P", "input-port", "DIA_missing")
    tree_out = copy.deepcopy(tree_in)
    at(tree_out, f"{task}/properties").append(node("Property", port))  # type: ignore[attr-defined]
    tree_out = with_members(tree_out, f"{task}/dataInputAssociations/1", targetRef=port)
    tree_out = with_members(tree_out, task, incoming=[], outgoing=[])
    rule = "complete-input-port"
    entries = [
        create_entry("complete", "create", rule, tree_out, f"{task}/properties/1"),
        edit_entry(
            "complete",
            "assignRef",
            rule,
            f"{task}/dataInputAssociations/1",
            "DIA_missing",
            "targetRef",
            after=port,
        ),
        *empty_topology(task, "Task_P"),
    ]
    derivation = (
        "DIA_valid's activity-owned Property target is preserved byte for byte. DIA_missing"
        " lacks its required target port: under the base's explicit code authority C creates"
        " one Property in Task_P.properties keyed by the association id,"
        " stable-id(Task_P, input-port, DIA_missing), and assigns it. No first-port shortcut:"
        " Prop_valid is not reused. The cn-c topology recipe also gives the flowless Task_P"
        " empty incoming/outgoing arrays (absent -> [], H F1)."
    )
    return complete_case(
        "cn-c-input-port", C_CLAUSE_PORTS, derivation, "cn-c", tree_in, tree_out, entries
    )


def _output_port_tree() -> dict[str, Json]:
    return definitions(
        "Definitions_out",
        node(
            "Process",
            "Process_O",
            isExecutable=False,
            flowElements=[
                node("DataObject", "DO_O"),
                node("DataObjectReference", "Ref_O", dataObjectRef="DO_O"),
                node(
                    "Task",
                    "Task_O",
                    name="Produce output",
                    dataOutputAssociations=[
                        node("DataOutputAssociation", "DOA_missing", targetRef="Ref_O")
                    ],
                ),
            ],
        ),
    )


def case_c_output_port_gated() -> dict[str, Json]:
    """The missing-output-source producer exception refuses profile-open in edit."""
    env_in = envelope(IDENTITY["cn-c"], _output_port_tree(), [])
    derivation = (
        "Filling the absent sourceRef of a DataOutputAssociation is the missing-output-source"
        " producer exception gated by OPEN-IO (technical gate open; §16 item 8 requires an"
        " explicitly accepted code-creation authority). With the default edit activation C"
        " refuses profile-open at that recipe step (the earlier ungated topology plans do not"
        " matter: nothing is applied) and commits nothing."
    )
    return complete_refusal(
        "cn-c-output-port-gated",
        C_CLAUSE_PORTS,
        derivation,
        "cn-c",
        env_in,
        "profile-open",
    )


def case_c_output_port_qualification() -> dict[str, Json]:
    """Neutral qualification exercises the gated output port creation."""
    tree_in = _output_port_tree()
    task = ptr("rootElements", 0, "flowElements", 2)
    port = sid("Task_O", "output-port", "DOA_missing")
    tree_out = with_members(tree_in, task, properties=[node("Property", port)])
    tree_out = with_members(tree_out, f"{task}/dataOutputAssociations/0", sourceRef=[port])
    tree_out = with_members(tree_out, task, incoming=[], outgoing=[])
    rule = "complete-output-port"
    entries = [
        create_entry("complete", "create", rule, tree_out, f"{task}/properties/0"),
        edit_entry(
            "complete",
            "assignRef",
            rule,
            f"{task}/dataOutputAssociations/0",
            "DOA_missing",
            "sourceRef",
            after=[port],
        ),
        *empty_topology(task, "Task_O"),
    ]
    derivation = (
        "Same input as cn-c-output-port-gated under activation=qualification (§7.2/§13 neutral"
        " qualification may proceed): C creates stable-id(Task_O, output-port, DOA_missing) in"
        " Task_O.properties (absent before; the array is created) and assigns sourceRef, a"
        " multi-valued reference; the flowless Task_O receives empty incoming/outgoing"
        " arrays (H F1)."
    )
    return complete_case(
        "cn-c-output-port-qualification",
        C_CLAUSE_PORTS,
        derivation,
        "cn-c",
        tree_in,
        tree_out,
        entries,
        activation="qualification",
    )


def case_c_io_default_sets() -> dict[str, Json]:
    """No sets: deterministic default InputSet/OutputSet for declared Process IO."""
    tree_in = definitions(
        "Definitions_io",
        node(
            "Process",
            "Process_IO",
            isExecutable=False,
            ioSpecification=node(
                "InputOutputSpecification",
                dataInputs=[
                    node("DataInput", "DI_b", name="Second input"),
                    node("DataInput", "DI_a", name="First input"),
                ],
                dataOutputs=[node("DataOutput", "DO_1", name="Result")],
            ),
            flowElements=[node("Task", "Task_IO", name="Work")],
        ),
    )
    spec = ptr("rootElements", 0, "ioSpecification")
    input_set = sid("Process_IO", "input-set", "default")
    output_set = sid("Process_IO", "output-set", "default")
    tree_out = with_members(
        tree_in,
        spec,
        inputSets=[node("InputSet", input_set, dataInputRefs=["DI_a", "DI_b"])],
        outputSets=[node("OutputSet", output_set, dataOutputRefs=["DO_1"])],
    )
    task = ptr("rootElements", 0, "flowElements", 0)
    tree_out = with_members(tree_out, task, incoming=[], outgoing=[])
    entries = [
        *empty_topology(task, "Task_IO"),
        create_entry(
            "complete", "create", "complete-default-input-set", tree_out, f"{spec}/inputSets/0"
        ),
        edit_entry(
            "complete",
            "assignRef",
            "complete-default-input-set",
            f"{spec}/inputSets/0",
            input_set,
            "dataInputRefs",
            after=["DI_a", "DI_b"],
            created=True,
        ),
        create_entry(
            "complete", "create", "complete-default-output-set", tree_out, f"{spec}/outputSets/0"
        ),
        edit_entry(
            "complete",
            "assignRef",
            "complete-default-output-set",
            f"{spec}/outputSets/0",
            output_set,
            "dataOutputRefs",
            after=["DO_1"],
            created=True,
        ),
    ]
    derivation = (
        "The ID-less ioSpecification declares two inputs and one output and no sets. C"
        " creates one default InputSet and OutputSet whose ownerId is the explicitly"
        " evaluated Process id (never the ID-less parent): stable-id(Process_IO, input-set,"
        " default) and stable-id(Process_IO, output-set, default); membership is every"
        " declared IO id in UTF-16 order (DI_a before DI_b although declared second). The"
        " flowless Task_IO receives empty incoming/outgoing arrays (H F1). The assignRef of a"
        " created set is a write on a created element: source none/generated, result at"
        " <set>/dataInputRefs (H B9)."
    )
    return complete_case(
        "cn-c-io-default-sets", C_CLAUSE_SETS, derivation, "cn-c", tree_in, tree_out, entries
    )


def _io_sets_tree(*, uncovered: bool) -> dict[str, Json]:
    inputs = [node("DataInput", "DI_1", name="One"), node("DataInput", "DI_2", name="Two")]
    if uncovered:
        inputs.append(node("DataInput", "DI_3", name="Three"))
    return definitions(
        "Definitions_sets",
        node(
            "Process",
            "Process_IO2",
            isExecutable=False,
            ioSpecification=node(
                "InputOutputSpecification",
                dataInputs=inputs,
                dataOutputs=[node("DataOutput", "DO_1", name="Result")],
                inputSets=[
                    node("InputSet", "IS_A", dataInputRefs=["DI_1"]),
                    node("InputSet", "IS_B", dataInputRefs=["DI_2"]),
                ],
                outputSets=[node("OutputSet", "OS_A", dataOutputRefs=["DO_1"])],
            ),
        ),
    )


def case_c_io_sets_preserved() -> dict[str, Json]:
    """Existing sets keep every membership; nothing to complete."""
    tree = _io_sets_tree(uncovered=False)
    derivation = (
        "Two InputSets and one OutputSet already cover every declared IO: no default set is"
        " created, no membership is removed or reordered, the result equals the input and"
        " the report has no entry (baseRevision = revision)."
    )
    return complete_case(
        "cn-c-io-sets-preserved", C_CLAUSE_SETS, derivation, "cn-c", tree, tree, []
    )


def case_c_io_set_selection_required() -> dict[str, Json]:
    """New uncovered input with several sets refuses io-set-selection-required."""
    env_in = envelope(IDENTITY["cn-c"], _io_sets_tree(uncovered=True), [])
    derivation = (
        "DI_3 is covered by no InputSet while two InputSets exist: the profile refuse step"
        " aborts C with io-set-selection-required; the first set is never updated silently"
        " and the caller tree is unchanged."
    )
    return complete_refusal(
        "cn-c-io-set-selection-required",
        C_CLAUSE_SETS,
        derivation,
        "cn-c",
        env_in,
        "io-set-selection-required",
    )


def case_c_documentation_preserved() -> dict[str, Json]:
    """Documentation text and textFormat are preserved; no parsing, no ids."""
    tree_in = definitions(
        "Definitions_doc",
        node(
            "Process",
            "Process_doc",
            flowElements=[
                node(
                    "Task",
                    "Task_doc",
                    name="Documented",
                    documentation=[
                        doc('{"kind": "json-looking"}', "application/json"),
                        doc("  two  spaces\n"),
                        doc("plain", "text/plain"),
                    ],
                )
            ],
            artifacts=[node("TextAnnotation", "Ann_1", text="[Aid] keep  this")],
        ),
    )
    tree_out = with_members(tree_in, ptr("rootElements", 0), isExecutable=False)
    entries = [
        edit_entry(
            "complete",
            "set",
            "complete-process",
            ptr("rootElements", 0),
            "Process_doc",
            "isExecutable",
            after=False,
        )
    ]
    derivation = (
        "Documentation.text is source evidence and textFormat an explicit contract field: C"
        " keeps the JSON-looking text unparsed, the whitespace bytes intact, the absent"
        " textFormat absent, the annotation text unchanged, and allocates no id for ID-less"
        " Documentation (identity mode containment). Only isExecutable changes."
    )
    return complete_case(
        "cn-c-documentation-preserved",
        C_CLAUSE_CONTENT,
        derivation,
        "neutral",
        tree_in,
        tree_out,
        entries,
    )


def case_c_unicode_names() -> dict[str, Json]:
    """Private-use, astral and whitespace names give distinct deterministic ids."""
    names = ["\ue000 private use", "\U00010000 astral", " Draft", "\u00a0Draft", "Draft"]
    tree_in = definitions(
        "Definitions_uni",
        node(
            "Process",
            "Process_uni",
            isExecutable=False,
            flowElements=[node("Task", name=n) for n in names],
        ),
    )
    fe = ptr("rootElements", 0, "flowElements")
    assignments = {}
    entries = []
    for index, name in enumerate(names):
        new_id = c_id("Process_uni", SLOT_FLOW, {"$type": "bpmn:Task", "name": name}, 0)
        assignments[f"{fe}/{index}"] = new_id
        entries.append(alloc(f"{fe}/{index}", "Process_uni", new_id))
    tree_out = with_ids(tree_in, assignments)
    derivation = (
        "Each ID-less task's contentSignature hashes its exact UTF-8 JCS name with no trim,"
        " no NFC and no case folding, so U+E000, U+10000, a leading space, a leading NBSP and"
        " the bare name give five distinct signatures, each ordinal 0. Names are preserved."
        " Source targetId is the nearest original ID-bearing ancestor, Process_uni."
    )
    return complete_case(
        "cn-c-unicode-names",
        "DESIGN R3.3 §3.2 contentSignature; §14.3 Unicode U+E000/U+10000 and whitespace",
        derivation,
        "neutral",
        tree_in,
        tree_out,
        entries,
    )


def _timer_start() -> dict[str, Json]:
    return node(
        "StartEvent",
        name="Every hour",
        eventDefinitions=[
            node(
                "TimerEventDefinition",
                timeDuration={"$type": "bpmn:FormalExpression", "body": "PT1H"},
            )
        ],
    )


def _timer_ids() -> tuple[str, str, str, str]:
    start = _timer_start()
    timer = start["eventDefinitions"][0]  # type: ignore[index]
    s0 = c_id("Process_T", SLOT_FLOW, start, 0)
    s1 = c_id("Process_T", SLOT_FLOW, start, 1)
    t0 = c_id(s0, SLOT_EVENT_DEFINITIONS, timer, 0)
    t1 = c_id(s1, SLOT_EVENT_DEFINITIONS, timer, 0)
    return s0, s1, t0, t1


def _timer_tree() -> dict[str, Json]:
    return definitions(
        "Definitions_timer",
        node(
            "Process",
            "Process_T",
            isExecutable=False,
            flowElements=[_timer_start(), _timer_start(), node("Task", "Task_T", name="Hourly")],
        ),
    )


def _timer_output() -> dict[str, Json]:
    s0, s1, t0, t1 = _timer_ids()
    fe = ptr("rootElements", 0, "flowElements")
    tree = with_ids(
        _timer_tree(),
        {
            f"{fe}/0": s0,
            f"{fe}/0/eventDefinitions/0": t0,
            f"{fe}/1": s1,
            f"{fe}/1/eventDefinitions/0": t1,
        },
    )
    tree = with_members(tree, f"{fe}/0", outgoing=[])
    tree = with_members(tree, f"{fe}/1", outgoing=[])
    return with_members(tree, f"{fe}/2", incoming=[], outgoing=[])


def case_c_timer_siblings() -> dict[str, Json]:
    """Identical ID-less timer starts get ordinals 0 and 1; nested ids follow."""
    s0, s1, t0, t1 = _timer_ids()
    fe = ptr("rootElements", 0, "flowElements")
    start_topology = {
        "props": ("outgoing",),
        "rule": "complete-start-topology",
        "source_target": "Process_T",
        "allocated": True,
    }
    entries = [
        alloc(f"{fe}/0", "Process_T", s0),
        alloc(f"{fe}/0/eventDefinitions/0", "Process_T", t0),
        alloc(f"{fe}/1", "Process_T", s1),
        alloc(f"{fe}/1/eventDefinitions/0", "Process_T", t1),
        *empty_topology(f"{fe}/0", s0, **start_topology),  # type: ignore[arg-type]
        *empty_topology(f"{fe}/1", s1, **start_topology),  # type: ignore[arg-type]
        *empty_topology(f"{fe}/2", "Task_T"),
    ]
    derivation = (
        "The two identical ID-less StartEvents share one contentSignature (raw input subtree,"
        " no generated default) in Process_T under slot bpmn:Process.flowElements (H D1):"
        " ordinals 0 and 1 give distinct ids. Each TimerEventDefinition is then identified"
        " under its own new StartEvent id (slot bpmn:StartEvent.eventDefinitions, ordinal 0);"
        " the ID-less FormalExpression body stays ID-less. The topology recipes then write"
        " empty outgoing arrays on both flowless starts and empty incoming/outgoing on"
        " Task_T (absent -> [], H F1); the starts' entries carry generated result"
        " provenance and the original ancestor Process_T as source targetId. 8 entries."
    )
    return complete_case(
        "cn-c-timer-siblings",
        "DESIGN R3.3 §3.2 duplicateOrdinal; §14.3 ID collisions/reorders/timers",
        derivation,
        "cn-c",
        _timer_tree(),
        _timer_output(),
        entries,
    )


def case_c_timer_siblings_reordered() -> dict[str, Json]:
    """Reordering identified siblings never reallocates their ids."""
    tree = _timer_output()
    fe = at(tree, ptr("rootElements", 0, "flowElements"))
    fe[0], fe[1] = fe[1], fe[0]  # type: ignore[index]
    derivation = (
        "Input is the cn-c-timer-siblings output with the two identified starts swapped:"
        " every id is present, later reorders never reallocate, and the stored empty"
        " topology arrays already equal the derived sets, so C is a no-op (no entry)."
    )
    return complete_case(
        "cn-c-timer-siblings-reordered",
        "DESIGN R3.3 §3.2 (later reorders never reallocate IDs)",
        derivation,
        "cn-c",
        tree,
        tree,
        [],
    )


def case_c_id_collision() -> dict[str, Json]:
    """A computed id equal to a different existing element refuses id-collision."""
    dup = {"$type": "bpmn:Task", "name": "Dup"}
    occupant = c_id("Process_1", SLOT_FLOW, dup, 0)
    tree = definitions(
        "Definitions_col",
        node(
            "Process",
            "Process_1",
            isExecutable=False,
            flowElements=[node("Task", name="Dup"), node("Task", occupant, name="Occupant")],
        ),
    )
    derivation = (
        "The ID-less task would receive stable-id(Process_1, bpmn:Process.flowElements,"
        " JCS([H({$type:bpmn:Task,name:Dup}),0])) (slot per H D1), which another task already"
        " carries: a computed collision with a different object refuses id-collision"
        " (precedence step 7); no suffix, overwrite or reidentification, and nothing is"
        " committed."
    )
    return complete_refusal(
        "cn-c-id-collision",
        "DESIGN R3.3 §3.2 (computed collision is id-collision); §7.3 rollback",
        derivation,
        "neutral",
        envelope(IDENTITY["neutral"], tree, []),
        "id-collision",
    )


def case_c_duplicate_source_ids() -> dict[str, Json]:
    """Duplicate existing ids refuse before any C write."""
    tree = definitions(
        "Definitions_dup",
        node(
            "Process",
            "Process_1",
            flowElements=[
                node("Task", "Task_same", name="One"),
                node("Task", "Task_same", name="Two"),
            ],
        ),
    )
    derivation = (
        "Two elements carry Task_same. Duplicate source ids are refused structurally"
        " (graph index, precedence step 5, H C1/C4) with id-collision; isExecutable is not"
        " stamped."
    )
    return complete_refusal(
        "cn-c-duplicate-source-ids",
        "DESIGN R3.3 §3.2 (duplicate source IDs refuse); §10.2 duplicate-id -> id-collision",
        derivation,
        "neutral",
        envelope(IDENTITY["neutral"], tree, []),
        "id-collision",
    )


def case_c_not_fixed() -> dict[str, Json]:
    """A self-feeding completion recipe fails the bounded fixed point."""
    tree = definitions(
        "Definitions_nf",
        node(
            "Process",
            "Process_1",
            isExecutable=False,
            flowElements=[node("Task", "Task_1", name="A")],
        ),
    )
    derivation = (
        "suffix-task-name sets name := concat(name, '!'): the first pass gives 'A!' (and the"
        " empty topology arrays of Task_1), the bounded second evaluation succeeds but"
        " changes the name again to 'A!!', so C(C(x)) != C(x) and C refuses"
        " normalization-not-fixed, rolling back the whole stage (no candidate exposed)."
        " Witness of the 'second evaluation still changes a value' branch; the refusal"
        " branch is cn-c-second-pass-refused."
    )
    return complete_refusal(
        "cn-c-not-fixed",
        "DESIGN R3.3 §2.4 bounded second evaluation; §7.3 rollback on non-fixed point",
        derivation,
        "cn-c-unfixed",
        envelope(IDENTITY["cn-c-unfixed"], tree, []),
        "normalization-not-fixed",
    )


def _extraction_tree(task_type: str) -> dict[str, Json]:
    return definitions(
        None,
        node("Process", flowElements=[node(task_type, name="Extracted step")]),
    )


def case_c_extraction_authorized() -> dict[str, Json]:
    """Extraction mode admits only AI-produced fields, then C identifies them."""
    tree_in = _extraction_tree("ServiceTask")
    process_id = c_id(DEF_ROOT_ID, SLOT_ROOT, at(tree_in, ptr("rootElements", 0)), 0)
    task_node = at(tree_in, ptr("rootElements", 0, "flowElements", 0))
    task_id = c_id(process_id, SLOT_FLOW, task_node, 0)
    tree_out = with_ids(
        tree_in,
        {
            "": DEF_ROOT_ID,
            ptr("rootElements", 0): process_id,
            ptr("rootElements", 0, "flowElements", 0): task_id,
        },
    )
    tree_out = with_members(tree_out, ptr("rootElements", 0), isExecutable=True)
    entries = [
        alloc("", None, DEF_ROOT_ID),
        alloc(ptr("rootElements", 0), None, process_id),
        alloc(ptr("rootElements", 0, "flowElements", 0), None, task_id),
        edit_entry(
            "complete",
            "set",
            "complete-process",
            ptr("rootElements", 0),
            process_id,
            "isExecutable",
            after=True,
            allocated=True,
            source_target=None,
        ),
    ]
    derivation = (
        "The grid-extraction delta moves rootElements, flowElements and ServiceTask.name from"
        " import to ai, so every field present in the AI extraction is admitted to actor ai"
        " (spec §6.1). C then allocates the three missing ids and the grid default"
        " isExecutable=true. The fixed-point rerun uses mode retained (the output is retained"
        " content)."
    )
    return complete_case(
        "cn-c-extraction-authorized",
        "DESIGN R3.3 §7.1 (extraction actor schema); §2.4.1 actor matrix",
        derivation,
        "grid-extraction",
        tree_in,
        tree_out,
        entries,
        mode="extraction",
    )


def case_c_extraction_unauthorized() -> dict[str, Json]:
    """Extraction mode refuses fields not produced by the ai actor."""
    env_in = envelope(IDENTITY["neutral"], _extraction_tree("Task"), [])
    derivation = (
        "The neutral base grants no field to actor ai; in extraction mode the first present"
        " field (Definitions.rootElements) is not AI-producible, so C refuses profile-producer"
        " before identity allocation."
    )
    return complete_refusal(
        "cn-c-extraction-unauthorized",
        "DESIGN R3.3 §7.1 (extraction actor schema); §2.4.1 CR-06 profile-producer",
        derivation,
        "neutral",
        env_in,
        "profile-producer",
        mode="extraction",
    )


def case_c_descriptor_role_unknown() -> dict[str, Json]:
    """An unclassified property refuses descriptor-role-unknown."""
    tree = definitions(
        "Definitions_role",
        node(
            "Process", "Process_1", flowElements=[node("Task", "Task_1", name="Work", colour="red")]
        ),
    )
    derivation = (
        "Task.colour is classified by no descriptor role of the neutral slice; the graph index"
        " check before C (precedence step 5, H C1) refuses descriptor-role-unknown (§3.1)."
    )
    return complete_refusal(
        "cn-c-descriptor-role-unknown",
        "DESIGN R3.3 §3.1 (unclassified foreign property); §2.5 execution order",
        derivation,
        "neutral",
        envelope(IDENTITY["neutral"], tree, []),
        "descriptor-role-unknown",
    )


def case_c_invalid_mode() -> dict[str, Json]:
    """A mode outside the closed set is an invalid invocation."""
    tree = definitions("Definitions_mode", node("Process", "Process_1"))
    derivation = (
        "mode accepts exactly extraction or retained (spec §3.4, H B7); 'draft' is a"
        " readiness policy, not a C mode, so the call refuses operation-error at precedence"
        " step 1 (H C1/C11). The envelope argument is itself a JSON object with"
        " documentVersion 1, a shape-valid identity and a semanticRevision, so the refusal"
        " echoes them (H B3: only an unknown documentVersion, an unparseable input or the"
        " not-loaded state omit the echo)."
    )
    return complete_refusal(
        "cn-c-invalid-mode",
        "DESIGN R3.3 §2.5 complete(compiled, envelope, mode); §10.1 refusal record; spec §3.4",
        derivation,
        "neutral",
        envelope(IDENTITY["neutral"], tree, []),
        "operation-error",
        mode="draft",
    )


def case_c_second_pass_refused() -> dict[str, Json]:
    """A refusal during the bounded second evaluation fails the C fixed point."""
    tree = definitions(
        "Definitions_sp",
        node(
            "Process",
            "Process_1",
            isExecutable=False,
            flowElements=[node("Task", "Task_1", name="A")],
        ),
    )
    derivation = (
        "mark-task-name sets name := 'marked' (idempotent) and refuse-marked-task refuses"
        " fixture-second-pass for a Task named 'marked'. First pass: every plan reads the"
        " phase-start snapshot (name 'A'), so the refuse recipe has no candidate and the"
        " pass succeeds with name 'marked' plus the empty topology arrays. The bounded second"
        " evaluation changes nothing but reaches the refuse step: the second run does not"
        " return the identical result, so the fixed-point proof fails with"
        " normalization-not-fixed (DESIGN §2.4), never with the second-pass code, and no"
        " candidate is exposed."
    )
    return complete_refusal(
        "cn-c-second-pass-refused",
        "DESIGN R3.3 §2.4 bounded second evaluation (failure is normalization-not-fixed);"
        " §7.3 rollback",
        derivation,
        "cn-c-second-pass",
        envelope(IDENTITY["cn-c-second-pass"], tree, []),
        "normalization-not-fixed",
    )


def case_c_dangling_call() -> dict[str, Json]:
    """A nonempty unresolved calledElement refuses reference-dangling before C."""
    tree = definitions(
        "Definitions_dang",
        node(
            "Process",
            "Process_1",
            isExecutable=False,
            flowElements=[
                node("CallActivity", "Call_1", name="Call missing", calledElement="Process_ghost")
            ],
        ),
    )
    derivation = (
        "calledElement is a declared ID-valued reference to bpmn:Process in the cn slice;"
        " Process_ghost names no element. Dangling references produce integrity refusals"
        " before evaluation and never count as absent (DESIGN §2.2, §4.1 nonempty unresolved"
        " target): the graph index (precedence step 5, H C1/C2) refuses reference-dangling"
        " before any C write."
    )
    return complete_refusal(
        "cn-c-dangling-call",
        "DESIGN R3.3 §2.2 (dangling references before evaluation); §4.1; §5.2",
        derivation,
        "cn-c",
        envelope(IDENTITY["cn-c"], tree, []),
        "reference-dangling",
    )


def case_c_wrong_type_reference() -> dict[str, Json]:
    """A reference to an element of a non-admitted type refuses reference-dangling."""
    tree = definitions(
        "Definitions_wt",
        node(
            "Process",
            "Process_1",
            isExecutable=False,
            flowElements=[
                node("Task", "Task_1", name="Work"),
                node("DataObject", "DO_1"),
                flow("Flow_1", "Task_1", "DO_1"),
            ],
        ),
    )
    derivation = (
        "Flow_1.targetRef names DO_1, an existing bpmn:DataObject, while the cn slice admits"
        " only bpmn:ExclusiveGateway and bpmn:Task as SequenceFlow targets. Wrong-type"
        " references are integrity errors before evaluation (DESIGN §2.2): the graph index"
        " refuses reference-dangling (H C1 step 5, C2) instead of completing topology."
    )
    return complete_refusal(
        "cn-c-wrong-type-reference",
        "DESIGN R3.3 §2.2 (dangling or wrong-type references before evaluation)",
        derivation,
        "cn-c",
        envelope(IDENTITY["cn-c"], tree, []),
        "reference-dangling",
    )


def case_c_empty_called_element() -> dict[str, Json]:
    """An empty calledElement is a classification state, not a dangling reference."""
    tree = definitions(
        "Definitions_empty",
        node(
            "Process",
            "Process_1",
            isExecutable=False,
            flowElements=[node("CallActivity", "Call_1", name="Undecided", calledElement="")],
        ),
    )
    derivation = (
        "An empty calledElement is classified by §4.1 (call-target-empty without marker,"
        " call-kind-conflict with one), a validate finding, never reference-dangling (H C3)."
        " The graph index therefore accepts it; no cn-c recipe applies to a CallActivity and"
        " the Process already carries isExecutable=false, so C is a no-op: ok, no entry."
    )
    return complete_case(
        "cn-c-empty-called-element",
        "DESIGN R3.3 §4.1 (empty calledElement rows); §2.2",
        derivation,
        "cn-c",
        tree,
        tree,
        [],
    )


def case_c_uncompiled_context() -> dict[str, Json]:
    """C/N need a profile compiled with its descriptor context and effective base."""
    tree = definitions("Definitions_ctx", node("Process", "Process_1", isExecutable=False))
    record = complete_refusal(
        "cn-c-uncompiled-context",
        "DESIGN R3.3 §2.5 ReadContext (descriptor/effective-base index); §8.1 descriptor-mismatch",
        (
            "The harness compiles the neutral variant without descriptor_context and base"
            " (input.compile = without-descriptor-context): the CompiledProfile lacks the"
            " identity, type index and producer matrix that C reads (spec §2.2 B7), so complete"
            " refuses descriptor-mismatch at precedence step 1 for an otherwise valid"
            " envelope. Runtime-specific harness case (no"
            " parity projection): lots 4 and 5 must compile with both inputs before calling"
            " complete or normalize."
        ),
        "neutral",
        envelope(IDENTITY["neutral"], tree, []),
        "descriptor-mismatch",
    )
    record["input"]["compile"] = "without-descriptor-context"  # type: ignore[index]
    return record


C_CASES = [
    case_c_identity_neutral,
    case_c_identity_grid,
    case_c_is_executable_neutral,
    case_c_is_executable_grid,
    case_c_version_mismatch_first,
    case_c_digest_mismatch_first,
    case_c_document_version,
    case_c_gateway_direction,
    case_c_gateway_direction_control,
    case_c_topology_per_container,
    case_c_backing_object,
    case_c_input_port,
    case_c_output_port_gated,
    case_c_output_port_qualification,
    case_c_io_default_sets,
    case_c_io_sets_preserved,
    case_c_io_set_selection_required,
    case_c_documentation_preserved,
    case_c_unicode_names,
    case_c_timer_siblings,
    case_c_timer_siblings_reordered,
    case_c_id_collision,
    case_c_duplicate_source_ids,
    case_c_not_fixed,
    case_c_extraction_authorized,
    case_c_extraction_unauthorized,
    case_c_descriptor_role_unknown,
    case_c_invalid_mode,
    case_c_second_pass_refused,
    case_c_dangling_call,
    case_c_wrong_type_reference,
    case_c_empty_called_element,
    case_c_uncompiled_context,
]


# ---------------------------------------------------------------------------
# Cases for the normalize operation
# ---------------------------------------------------------------------------

N_CLAUSE_SUPPORT = (
    "DESIGN R3.3 §7.2 Structure; §7.3 neutral-support-fixture.R31.json; §3.2 multi-Process"
    " support domain witness; §5.2"
)
N_CLAUSE_GATE = "DESIGN R3.3 §7.2 OPEN-RESERVED-N; §13; §16 item 11"
N_CLAUSE_PLACE = "DESIGN R3.3 §7.2 derived placements; §2.4.1 shared anchoring; §4.4 anchors"


def normalize_case(  # noqa: PLR0913, PLR0917
    cid: str,
    clause: str,
    derivation: str,
    variant: str,
    inputs: tuple[Json, list[dict[str, str]]],
    outputs: tuple[Json, list[dict[str, str]]],
    entries: list[dict[str, Json]],
    placements: list[dict[str, Json]],
    *,
    activation: str = "edit",
    intent: Json = None,
) -> dict[str, Json]:
    """Return one accepted normalize case with its exact Result/1."""
    ident = IDENTITY[variant]
    env_in = envelope(ident, inputs[0], inputs[1])
    env_out = envelope(ident, outputs[0], outputs[1])
    base, rev = str(env_in["semanticRevision"]), str(env_out["semanticRevision"])
    rep = success_report("normalize", ident, base, rev, entries)
    payload = {"envelope": env_out, "placements": sort_placements(placements), "report": rep}
    expected = ok_result("normalize", ident, base, rev, rep, payload)
    inp = {"envelope": env_in, "activation": activation, "placementIntent": intent}
    return make_case(cid, clause, derivation, "normalize", variant, inp, expected, fixed_point=True)


def normalize_refusal(  # noqa: PLR0913, PLR0917
    cid: str,
    clause: str,
    derivation: str,
    variant: str,
    env_in: dict[str, Json],
    code: str,
    *,
    activation: str = "edit",
    intent: Json = None,
) -> dict[str, Json]:
    """Return one refused normalize case."""
    identity, base = echo_fields(env_in)
    expected = refused_result("normalize", code, identity, base)
    inp = {"envelope": env_in, "activation": activation, "placementIntent": intent}
    return make_case(cid, clause, derivation, "normalize", variant, inp, expected)


def _support_case(index: int) -> dict[str, Json]:
    return SUPPORT_FIXTURE["cases"][index]  # type: ignore[index,return-value]


def _support_negative(index: int) -> dict[str, Json]:
    return SUPPORT_FIXTURE["negatives"][index]  # type: ignore[index,return-value]


def _support_ids(definitions_id: str, process_id: str) -> list[str]:
    return [
        sid(definitions_id, "collaboration", process_id),
        sid(process_id, "main-participant", "main-participant"),
        sid(process_id, "lane-set", "lane-set"),
        sid(process_id, "external-lane", "external-lane"),
        sid(process_id, "reference-band", "reference-band"),
    ]


def _support_entries(tree: Json, process_index: int, collab_index: int) -> list[dict[str, Json]]:
    rule = "ensure-supports"
    collab = ptr("rootElements", collab_index)
    process = ptr("rootElements", process_index)
    main_id = at(tree, f"{collab}/participants/0/id")
    process_id = at(tree, f"{process}/id")
    return [
        create_entry("normalize", "ensure", rule, tree, collab),
        create_entry("normalize", "ensure", rule, tree, f"{collab}/participants/0"),
        edit_entry(
            "normalize",
            "assignRef",
            rule,
            f"{collab}/participants/0",
            str(main_id),
            "processRef",
            after=process_id,
            created=True,
        ),
        create_entry("normalize", "ensure", rule, tree, f"{process}/laneSets/0"),
        create_entry("normalize", "ensure", rule, tree, f"{process}/laneSets/0/lanes/0"),
        create_entry("normalize", "ensure", rule, tree, f"{collab}/participants/1"),
    ]


def case_n_support_one_process() -> dict[str, Json]:
    """All five ensure actions plus processRef for one Process (R3.1 fixture)."""
    fixture = _support_case(0)
    expected = fixture["expected"]
    assert _support_ids("Definitions_support", "Process_A") == expected["createdIds"]  # type: ignore[index]
    tree_out = expected["tree"]  # type: ignore[index]
    entries = _support_entries(tree_out, 0, 1)
    derivation = (
        "Exact vendored expectation of neutral-support-fixture.R31.json case 'complete support"
        " creation': five ensures (Collaboration under Definitions with ownerId"
        " Definitions_support and key Process_A; main Participant, LaneSet, reserved Lane and"
        " reference-band Participant in the Process_A domain) plus the main processRef"
        " assignment give exactly six change entries (fixture changeCount 6); creation order"
        " is the fixture createdIds order (Collaboration appended after the Process, main"
        " before band). Bindings sort by ownerId/role/targetId."
    )
    return normalize_case(
        "cn-n-support-one-process",
        N_CLAUSE_SUPPORT,
        derivation,
        "support",
        (fixture["input"], []),
        (tree_out, expected["bindings"]),  # type: ignore[index]
        entries,
        [],
        activation="qualification",
    )


def case_n_support_two_processes() -> dict[str, Json]:
    """Two Process domains get separate Collaborations (R3.1 fixture)."""
    fixture = _support_case(1)
    expected = fixture["expected"]
    ids_a = _support_ids("Definitions_support", "Process_A")
    ids_b = _support_ids("Definitions_support", "Process_B")
    assert ids_a + ids_b == expected["createdIds"]  # type: ignore[index]
    tree_out = expected["tree"]  # type: ignore[index]
    entries = _support_entries(tree_out, 0, 2) + _support_entries(tree_out, 1, 3)
    derivation = (
        "Vendored case 'two processes have separate collaborations': each Process gets its own"
        " Collaboration (ownerId Definitions_support, keys Process_A and Process_B), bound to"
        " that Process, plus its own four Process-domain supports; twelve change entries"
        " (fixture changeCount 12), creation order Process_A then Process_B."
    )
    return normalize_case(
        "cn-n-support-two-processes",
        N_CLAUSE_SUPPORT,
        derivation,
        "support",
        (fixture["input"], []),
        (tree_out, expected["bindings"]),  # type: ignore[index]
        entries,
        [],
        activation="qualification",
    )


def _imported_case(cid: str, activation: str) -> dict[str, Json]:
    fixture = _support_case(2)
    derivation = (
        "Vendored case 'imported support IDs survive': every role is correctly bound to an"
        " imported non-generated id (type, parent/property and declared fields agree), so N"
        " reuses all five, the processRef write is a no-op, no id is allocated and the report"
        " is empty (fixture changeCount 0). Reuse is not a gated mutation, so the"
        f" {activation} activation accepts it."
    )
    tree = fixture["input"]
    bindings = fixture["bindings"]
    return normalize_case(
        cid,
        N_CLAUSE_SUPPORT + "; §5.2 imported ID reuse",
        derivation,
        "support",
        (tree, bindings),  # type: ignore[arg-type]
        (tree, bindings),  # type: ignore[arg-type]
        [],
        [],
        activation=activation,
    )


def case_n_support_imported_ids() -> dict[str, Json]:
    """Imported non-generated support ids survive (qualification)."""
    return _imported_case("cn-n-support-imported-ids", "qualification")


def case_n_support_imported_ids_edit() -> dict[str, Json]:
    """Imported supports survive in edit activation too (reuse is not gated)."""
    return _imported_case("cn-n-support-imported-ids-edit", "edit")


def case_n_support_creation_gated() -> dict[str, Json]:
    """Support creation refuses profile-open while OPEN-RESERVED-N is open."""
    fixture = _support_case(0)
    env_in = envelope(IDENTITY["support"], fixture["input"], [])
    derivation = (
        "Same input as cn-n-support-one-process with the default edit activation: the first"
        " ensure would create a persisted support while the OPEN-RESERVED-N technical gate is"
        " open (§16 item 11 owner part ratified, twin proof pending), so N refuses"
        " profile-open and the caller tree and bindings are unchanged."
    )
    return normalize_refusal(
        "cn-n-support-creation-gated",
        N_CLAUSE_GATE,
        derivation,
        "support",
        env_in,
        "profile-open",
    )


def _negative_case(cid: str, index: int, detail: str) -> dict[str, Json]:
    fixture = _support_negative(index)
    env_in = envelope(IDENTITY["support"], fixture["input"], fixture["bindings"])  # type: ignore[arg-type]
    derivation = (
        f"Vendored negative '{fixture['name']}' under activation=qualification: refusal"
        f" {fixture['code']}, the whole staged operation rolls back and the caller tree and"
        f" bindings are unchanged. {detail}"
    )
    return normalize_refusal(
        cid,
        N_CLAUSE_SUPPORT + "; §7.3 rollback",
        derivation,
        "support",
        env_in,
        str(fixture["code"]),
        activation="qualification",
    )


def case_n_support_late_band_collision() -> dict[str, Json]:
    """Late band id collision rolls back four earlier supports."""
    return _negative_case(
        "cn-n-support-late-band-collision",
        0,
        "The four earlier ensures plan creations; the band ensure's allocator id is occupied"
        " by an unrelated, unbound Participant (precedence step 8, §6.3).",
    )


def case_n_support_duplicate_role() -> dict[str, Json]:
    """A duplicated owner+role binding refuses at envelope integrity."""
    return _negative_case(
        "cn-n-support-duplicate-role",
        1,
        "The duplicate (ownerId, role) binding is rejected by envelope integrity (precedence"
        " step 4, H C1), after the §3.3 compatibility row accepted the exact identity; the"
        " envelope still has documentVersion 1, a shape-valid identity and a"
        " semanticRevision, so the refusal echoes them (H B3; the revision string is echoed"
        " as given).",
    )


def case_n_support_wrong_parent() -> dict[str, Json]:
    """An imported band under the wrong parent refuses support-binding-conflict."""
    return _negative_case(
        "cn-n-support-wrong-parent",
        2,
        "The graph index accepts the misplaced Participant (Process.artifacts is a classified"
        " member; containment admission is not a graph-index check); reuse validation of the"
        " bound band then fails on parent/containment property (§5.2, H C5).",
    )


def case_n_support_band_process_ref() -> dict[str, Json]:
    """A reference band carrying processRef refuses support-binding-conflict."""
    return _negative_case(
        "cn-n-support-band-process-ref",
        3,
        "Reuse validation of the bound band fails on the no-processRef relationship (§5.2,"
        " H C5 keeps this check).",
    )


def case_n_support_refusal_after_five_ensures() -> dict[str, Json]:
    """An explicit refuse step after five ensures aborts atomically."""
    fixture = _support_case(0)
    env_in = envelope(IDENTITY["support-abort"], fixture["input"], [])
    derivation = (
        "R3.1 check 'explicit refusal after five ensures rolls back': the support-abort"
        " variant appends {op:refuse, code:fixture-abort} after the five ensures and the"
        " processRef assignment; the refusal code is the profile's, nothing is committed and"
        " the caller tree and bindings are unchanged."
    )
    return normalize_refusal(
        "cn-n-support-refusal-after-five-ensures",
        "DESIGN R3.3 §7.3 (explicit refusal after five ensures); §2.4 refuse",
        derivation,
        "support-abort",
        env_in,
        "fixture-abort",
        activation="qualification",
    )


def case_n_support_late_band_collision_edit() -> dict[str, Json]:
    """In edit activation the gate refuses before the late collision is reached."""
    fixture = _support_negative(0)
    env_in = envelope(IDENTITY["support"], fixture["input"], [])
    derivation = (
        "Same input as cn-n-support-late-band-collision with the default edit activation:"
        " the first ensure (Collaboration) would create, so profile-open is reported before"
        " the fifth ensure's id-collision (refusals follow recipe/candidate/step order)."
    )
    return normalize_refusal(
        "cn-n-support-late-band-collision-edit",
        N_CLAUSE_GATE,
        derivation,
        "support",
        env_in,
        "profile-open",
    )


def _fixture_completed(fixture: Json) -> Json:
    return copy.deepcopy(fixture["expected"]["completed"])  # type: ignore[index]


def case_n_place_neutral() -> dict[str, Json]:
    """Neutral placements: content region, no anchor, no related associations."""
    tree = _fixture_completed(NEUTRAL_FIXTURE)
    placements = NEUTRAL_FIXTURE["expected"]["placements"]  # type: ignore[index]
    derivation = (
        "The neutral place-task recipe on the vendored neutral-fixture completed tree: each"
        " bpmn:Task is placed in region content of its owner Process with an empty related"
        " selector and no anchor; the derived placements equal the vendored expectation and"
        " no tree change occurs (place writes no tree, no report entry)."
    )
    return normalize_case(
        "cn-n-place-neutral",
        N_CLAUSE_PLACE,
        derivation,
        "neutral",
        (tree, []),
        (tree, []),
        [],
        placements,  # type: ignore[arg-type]
    )


def case_n_place_grid_shared_anchor() -> dict[str, Json]:
    """Grid placements: every related association, minimum eligible anchor."""
    tree = _fixture_completed(GRID_FIXTURE)
    placements = GRID_FIXTURE["expected"]["placements"]  # type: ignore[index]
    derivation = (
        "The grid place-task recipe on the vendored grid completed tree: related lists every"
        " Association touching the task (A-producer, Y-consumer, Z-consumer, id-sorted); the"
        " anchor is bind(first) over consuming associations (sourceRef = task) then producing"
        " ones: Task_A -> Y-consumer (minimum of Y/Z), Task_B -> A-producer. Equals the"
        " vendored expectation; no relation is deleted."
    )
    return normalize_case(
        "cn-n-place-grid-shared-anchor",
        N_CLAUSE_PLACE,
        derivation,
        "grid",
        (tree, []),
        (tree, []),
        [],
        placements,  # type: ignore[arg-type]
    )


def case_n_place_grid_inserted_association() -> dict[str, Json]:
    """An inserted lower-id association becomes the anchor; all links retained."""
    tree = _fixture_completed(GRID_FIXTURE)
    at(tree, ptr("rootElements", 0, "artifacts")).append(  # type: ignore[attr-defined]
        node(
            "Association",
            "X-consumer",
            sourceRef="Task_A",
            targetRef="Task_B",
            associationDirection="One",
        )
    )
    every = ["A-producer", "X-consumer", "Y-consumer", "Z-consumer"]
    placements = [
        placement("Task_A", "Process_1", "side", every, "X-consumer"),
        placement("Task_B", "Process_1", "side", every, "A-producer"),
    ]
    derivation = (
        "Inserting X-consumer (Task_A -> Task_B) adds it to both related lists and, being the"
        " lowest consuming id for Task_A, makes it Task_A's anchor; Task_B still anchors on"
        " A-producer, its only consuming association."
    )
    return normalize_case(
        "cn-n-place-grid-inserted-association",
        N_CLAUSE_PLACE + "; §7.3 inserted/deleted associations",
        derivation,
        "grid",
        (tree, []),
        (tree, []),
        [],
        placements,
    )


def case_n_place_grid_deleted_association() -> dict[str, Json]:
    """Deleting the only consuming association falls back to producing ones."""
    tree = _fixture_completed(GRID_FIXTURE)
    artifacts = at(tree, ptr("rootElements", 0, "artifacts"))
    artifacts[:] = [a for a in artifacts if a.get("id") != "A-producer"]  # type: ignore[index,union-attr]
    related = ["Y-consumer", "Z-consumer"]
    placements = [
        placement("Task_A", "Process_1", "side", related, "Y-consumer"),
        placement("Task_B", "Process_1", "side", related, "Y-consumer"),
    ]
    derivation = (
        "Without A-producer, Task_B has no association with sourceRef Task_B, so bind(first)"
        " falls back to the producing selector (targetRef Task_B) and picks its minimum id"
        " Y-consumer; both tasks relate to the remaining Y/Z associations."
    )
    return normalize_case(
        "cn-n-place-grid-deleted-association",
        N_CLAUSE_PLACE + "; §7.3 inserted/deleted associations",
        derivation,
        "grid",
        (tree, []),
        (tree, []),
        [],
        placements,
    )


def case_n_placement_intent_di_only() -> dict[str, Json]:
    """A DI-only placement intent changes neither semantics nor placements."""
    record = case_n_place_neutral()
    record["case"] = "cn-n-placement-intent-di-only"
    record["clause"] = "DESIGN R3.3 §8.2 step 3 (placement intent, DI-only moves); §3.1"
    record["input"]["placementIntent"] = [{"elementId": "Task_A"}]  # type: ignore[index]
    record["derivation"] = (
        "Same as cn-n-place-neutral with placement intent [{elementId: Task_A}] for a DI-only"
        " move: the intent is validated but N's semantic outputs depend only on the tree, so"
        " envelope, placements and report are identical (a DI-only drag changes only"
        " viewRevision, which N does not compute)."
    ) + result_note(record["expected"])
    return record


def case_n_placement_intent_unknown() -> dict[str, Json]:
    """A placement intent naming no element refuses reference-dangling."""
    env_in = envelope(IDENTITY["neutral"], _fixture_completed(NEUTRAL_FIXTURE), [])
    derivation = (
        "The intent names Task_ghost, absent from the tree: the validated intent refuses"
        " reference-dangling after envelope and compatibility checks."
    )
    return normalize_refusal(
        "cn-n-placement-intent-unknown",
        "DESIGN R3.3 §8.2 step 3; spec §3.5 placement intent",
        derivation,
        "neutral",
        env_in,
        "reference-dangling",
        intent=[{"elementId": "Task_ghost"}],
    )


def case_sort_placements() -> dict[str, Json]:
    """Total placement order: UTF-16 tuple, absent anchor first, arrays lexicographic."""
    r1 = placement("E", "P_2", "a", [])
    r2 = placement("E", "P_10", "a", [])
    r3 = placement("E", "P_10", "b", [])
    r4 = placement("E", "P_10", "a", ["A1"], "A1")
    r5 = placement("E", "P_10", "a", ["A1", "B2"], "A1")
    r6 = placement("E", "P_10", "a", ["A2"], "A1")
    r7 = placement("\U00010000x", "P_10", "a", [])
    r8 = placement("\ue000x", "P_10", "a", [])
    unsorted = [r8, r1, r6, r3, r5, r7, r4, r2]
    expected = [r2, r4, r5, r6, r7, r8, r3, r1]
    assert sort_placements(unsorted) == expected
    derivation = (
        "Order by UTF-16 (ownerProcessId, regionKey, elementId, anchorAssociationId with"
        " absent before present, relatedAssociationIds compared element-wise, prefix first)."
        " P_10 precedes P_2; for the same target the anchorless record comes first, then"
        " related [A1] < [A1,B2] < [A2]; U+10000 (surrogates D800 DC00) precedes U+E000 in"
        " UTF-16 although it follows it in code-point order."
    )
    return make_case(
        "cn-sort-placements",
        "DESIGN R3.3 §7.2 placement sort order; §3.1 UTF-16 ordering",
        derivation,
        "sort_placements",
        None,
        {"placements": unsorted},
        expected,
    )


N_SUPPORT_CASES = [
    case_n_support_one_process,
    case_n_support_two_processes,
    case_n_support_imported_ids,
    case_n_support_imported_ids_edit,
    case_n_support_creation_gated,
    case_n_support_late_band_collision,
    case_n_support_duplicate_role,
    case_n_support_wrong_parent,
    case_n_support_band_process_ref,
    case_n_support_refusal_after_five_ensures,
    case_n_support_late_band_collision_edit,
    case_n_place_neutral,
    case_n_place_grid_shared_anchor,
    case_n_place_grid_inserted_association,
    case_n_place_grid_deleted_association,
    case_n_placement_intent_di_only,
    case_n_placement_intent_unknown,
    case_sort_placements,
]


# --- normalize on the cn profile -------------------------------------------


def collaboration(collab_id: str, *participants: Json) -> dict[str, Json]:
    """Return one Collaboration support literal."""
    return node("Collaboration", collab_id, name="collaboration", participants=list(participants))


def main_participant(participant_id: str, process_id: str) -> dict[str, Json]:
    """Return one main Participant literal."""
    return node("Participant", participant_id, name="main-participant", processRef=process_id)


def band(participant_id: str) -> dict[str, Json]:
    """Return one reference-band Participant literal (no processRef)."""
    return node("Participant", participant_id, name="reference-band")


def _ref_tree() -> dict[str, Json]:
    return definitions(
        "Definitions_ref",
        node("DataStore", "Store_shared", name="Shared register"),
        node(
            "Process",
            "Process_A",
            isExecutable=False,
            flowElements=[
                node("Task", "Task_A", name="Use register A"),
                node("DataStoreReference", "Ref_A", dataStoreRef="Store_shared"),
            ],
            artifacts=[
                node(
                    "Association",
                    "Link_A",
                    sourceRef="Ref_A",
                    targetRef="Task_A",
                    associationDirection="One",
                )
            ],
        ),
        node(
            "Process",
            "Process_B",
            isExecutable=False,
            flowElements=[
                node("Task", "Task_B", name="Use register B"),
                node("DataStoreReference", "Ref_B", dataStoreRef="Store_shared"),
            ],
            artifacts=[
                node(
                    "Association",
                    "Link_B",
                    sourceRef="Task_B",
                    targetRef="Ref_B",
                    associationDirection="None",
                )
            ],
        ),
    )


def reversal_entries(pointer: str, link: str, task: str, ref: str) -> list[dict[str, Json]]:
    """Return the three entries of one reference-link reversal."""
    rule = "reverse-reference-links"
    return [
        edit_entry(
            "normalize", "assignRef", rule, pointer, link, "sourceRef", before=task, after=ref
        ),
        edit_entry(
            "normalize", "assignRef", rule, pointer, link, "targetRef", before=ref, after=task
        ),
        edit_entry(
            "normalize",
            "set",
            rule,
            pointer,
            link,
            "associationDirection",
            before="None",
            after="One",
        ),
    ]


def case_n_reference_region_multi_process() -> dict[str, Json]:
    """Shared store, one reference per Process, supports created, link reversed."""
    tree_in = _ref_tree()
    c_a = sid("Definitions_ref", "collaboration", "Process_A")
    c_b = sid("Definitions_ref", "collaboration", "Process_B")
    m_a = sid("Process_A", "main-participant", "main-participant")
    m_b = sid("Process_B", "main-participant", "main-participant")
    b_a = sid("Process_A", "reference-band", "reference-band")
    b_b = sid("Process_B", "reference-band", "reference-band")
    tree_out = copy.deepcopy(tree_in)
    roots = tree_out["rootElements"]
    roots.append(collaboration(c_a, main_participant(m_a, "Process_A"), band(b_a)))  # type: ignore[attr-defined]
    roots.append(collaboration(c_b, main_participant(m_b, "Process_B"), band(b_b)))  # type: ignore[attr-defined]
    link_b = ptr("rootElements", 2, "artifacts", 0)
    tree_out = with_members(
        tree_out, link_b, sourceRef="Ref_B", targetRef="Task_B", associationDirection="One"
    )
    base_rule = "ensure-base-supports"
    entries = [
        create_entry("normalize", "ensure", base_rule, tree_out, ptr("rootElements", 3)),
        create_entry(
            "normalize", "ensure", base_rule, tree_out, ptr("rootElements", 3, "participants", 0)
        ),
        edit_entry(
            "normalize",
            "assignRef",
            base_rule,
            ptr("rootElements", 3, "participants", 0),
            m_a,
            "processRef",
            after="Process_A",
            created=True,
        ),
        create_entry("normalize", "ensure", base_rule, tree_out, ptr("rootElements", 4)),
        create_entry(
            "normalize", "ensure", base_rule, tree_out, ptr("rootElements", 4, "participants", 0)
        ),
        edit_entry(
            "normalize",
            "assignRef",
            base_rule,
            ptr("rootElements", 4, "participants", 0),
            m_b,
            "processRef",
            after="Process_B",
            created=True,
        ),
        create_entry(
            "normalize",
            "ensure",
            "ensure-reference-band",
            tree_out,
            ptr("rootElements", 3, "participants", 1),
        ),
        create_entry(
            "normalize",
            "ensure",
            "ensure-reference-band",
            tree_out,
            ptr("rootElements", 4, "participants", 1),
        ),
        *reversal_entries(link_b, "Link_B", "Task_B", "Ref_B"),
    ]
    bindings_out = [
        binding("Process_A", "collaboration", c_a),
        binding("Process_A", "main-participant", m_a),
        binding("Process_A", "reference-band", b_a),
        binding("Process_B", "collaboration", c_b),
        binding("Process_B", "main-participant", m_b),
        binding("Process_B", "reference-band", b_b),
    ]
    placements = [
        placement("Ref_A", "Process_A", REFERENCE_REGION, ["Link_A"], "Link_A"),
        placement("Ref_B", "Process_B", REFERENCE_REGION, ["Link_B"], "Link_B"),
    ]
    derivation = (
        "One root DataStore shared by two Processes, one DataStoreReference per Process: each"
        " Process gets its own Collaboration and main Participant (ensure-base-supports) and,"
        " because references need it, its own reference band; the second ensure of each"
        " Collaboration in ensure-reference-band is an identical plan and coalesces (reported"
        " once, under the first recipe). Link_B (Task -> reference) is the unambiguous"
        " reversed pair: ids preserved, endpoints swapped, direction One. Each reference is"
        " placed in region reference-band (the opaque region key equals the band's binding"
        " role, H K1) of its own Process with its own link; the store is neither duplicated"
        " nor placed. Entries: created supports at their own pointer, the processRef writes"
        " on created Participants at <participant>/processRef with source none, the"
        " reversal writes at <link>/<property> (H B9)."
    )
    return normalize_case(
        "cn-n-reference-region-multi-process",
        "DESIGN R3.3 §7.2 Reference region, Relation direction, Structure; §4.4 sharing;"
        " §7.3 multi-process/shared references",
        derivation,
        "cn-n",
        (tree_in, []),
        (tree_out, bindings_out),
        entries,
        placements,
        activation="qualification",
    )


def case_n_reference_region_edit() -> dict[str, Json]:
    """The same input refuses profile-open in edit (band creation needed)."""
    env_in = envelope(IDENTITY["cn-n"], _ref_tree(), [])
    derivation = (
        "Same input as cn-n-reference-region-multi-process with the default edit activation:"
        " the Collaboration ensure would create a support, so N refuses profile-open."
    )
    return normalize_refusal(
        "cn-n-reference-region-edit", N_CLAUSE_GATE, derivation, "cn-n", env_in, "profile-open"
    )


def case_n_interface_region() -> dict[str, Json]:
    """Process IO is placed in the interface region without lane membership."""
    tree_in = definitions(
        "Definitions_iface",
        node(
            "Process",
            "Process_IO",
            isExecutable=False,
            ioSpecification=node(
                "InputOutputSpecification",
                dataInputs=[node("DataInput", "DI_1", name="Order")],
                dataOutputs=[node("DataOutput", "DO_1", name="Invoice")],
                inputSets=[node("InputSet", "IS_1", dataInputRefs=["DI_1"])],
                outputSets=[node("OutputSet", "OS_1", dataOutputRefs=["DO_1"])],
            ),
            flowElements=[
                node("Task", "Task_supplier", name="Supplier step"),
                node("Task", "Task_work", name="Work"),
            ],
            artifacts=[
                node(
                    "Association",
                    "Assoc_in",
                    sourceRef="Task_supplier",
                    targetRef="DI_1",
                    associationDirection="One",
                )
            ],
        ),
    )
    c_io = sid("Definitions_iface", "collaboration", "Process_IO")
    m_io = sid("Process_IO", "main-participant", "main-participant")
    ls_io = sid("Process_IO", "lane-set", "lane-set")
    l_io = sid("Process_IO", "external-lane", "external-lane")
    tree_out = with_members(
        tree_in,
        ptr("rootElements", 0),
        laneSets=[
            node(
                "LaneSet", ls_io, name="lane-set", lanes=[node("Lane", l_io, name="external-lane")]
            )
        ],
    )
    tree_out["rootElements"].append(collaboration(c_io, main_participant(m_io, "Process_IO")))  # type: ignore[index,union-attr]
    entries = [
        create_entry(
            "normalize", "ensure", "ensure-base-supports", tree_out, ptr("rootElements", 1)
        ),
        create_entry(
            "normalize",
            "ensure",
            "ensure-base-supports",
            tree_out,
            ptr("rootElements", 1, "participants", 0),
        ),
        edit_entry(
            "normalize",
            "assignRef",
            "ensure-base-supports",
            ptr("rootElements", 1, "participants", 0),
            m_io,
            "processRef",
            after="Process_IO",
            created=True,
        ),
        create_entry(
            "normalize",
            "ensure",
            "ensure-external-lane",
            tree_out,
            ptr("rootElements", 0, "laneSets", 0),
        ),
        create_entry(
            "normalize",
            "ensure",
            "ensure-external-lane",
            tree_out,
            ptr("rootElements", 0, "laneSets", 0, "lanes", 0),
        ),
    ]
    bindings_out = [
        binding("Process_IO", "collaboration", c_io),
        binding("Process_IO", "external-lane", l_io),
        binding("Process_IO", "lane-set", ls_io),
        binding("Process_IO", "main-participant", m_io),
    ]
    placements = [
        placement("DI_1", "Process_IO", INTERFACE_REGION, ["Assoc_in"], "Assoc_in"),
        placement("DO_1", "Process_IO", INTERFACE_REGION, []),
    ]
    derivation = (
        "Declared Process IO needs the bound external lane, so N ensures the LaneSet and the"
        " reserved Lane; DI_1 and DO_1 are placed in region external-lane (the bound lane"
        " whose body hosts Process IO, DESIGN §9.4; region key = binding role, H K1) of"
        " Process_IO (owner reached through the ID-less ioSpecification), DI_1 anchored on"
        " its supplier"
        " association, DO_1 without anchor (absent, not null) and with no related"
        " association. No Lane.flowNodeRef is written for IO; the missing consumer edge stays"
        " a diagnostic, never an invented relation."
    )
    return normalize_case(
        "cn-n-interface-region",
        "DESIGN R3.3 §7.2 Interface region, Structure; §9.4 (IO never in Lane.flowNodeRef)",
        derivation,
        "cn-n",
        (tree_in, []),
        (tree_out, bindings_out),
        entries,
        placements,
        activation="qualification",
    )


def _rev_tree() -> dict[str, Json]:
    return definitions(
        "Definitions_rev",
        node("DataStore", "Store_S", name="Register"),
        node(
            "Process",
            "Process_R",
            isExecutable=False,
            flowElements=[
                node("Task", "Task_R", name="Consult"),
                node("DataStoreReference", "Ref_R", dataStoreRef="Store_S"),
            ],
            artifacts=[
                node(
                    "Association",
                    "Link_R",
                    sourceRef="Task_R",
                    targetRef="Ref_R",
                    associationDirection="None",
                )
            ],
        ),
        collaboration("Collab_R", main_participant("Main_R", "Process_R"), band("Band_R")),
    )


REV_BINDINGS = [
    binding("Process_R", "collaboration", "Collab_R"),
    binding("Process_R", "main-participant", "Main_R"),
    binding("Process_R", "reference-band", "Band_R"),
]


def case_n_relation_direction_reversal() -> dict[str, Json]:
    """Unambiguous reversal with every support already bound (edit activation)."""
    tree_in = _rev_tree()
    link = ptr("rootElements", 1, "artifacts", 0)
    tree_out = with_members(
        tree_in, link, sourceRef="Ref_R", targetRef="Task_R", associationDirection="One"
    )
    derivation = (
        "Supports are imported and bound, so no support is created and the edit activation"
        " accepts: N reverses the unambiguous Task -> DataStoreReference pair (id Link_R"
        " preserved, before/after reported) and sets its declared direction One; relation"
        " direction is not a gated mutation. The reference is placed with its link."
    )
    return normalize_case(
        "cn-n-relation-direction-reversal",
        "DESIGN R3.3 §7.2 Relation direction; §10.1 N direction reversal coordinates",
        derivation,
        "cn-n",
        (tree_in, REV_BINDINGS),
        (tree_out, REV_BINDINGS),
        reversal_entries(link, "Link_R", "Task_R", "Ref_R"),
        [placement("Ref_R", "Process_R", REFERENCE_REGION, ["Link_R"], "Link_R")],
    )


def case_n_relation_direction_conflict() -> dict[str, Json]:
    """Two recipes planning different directions refuse profile-write-conflict."""
    env_in = envelope(IDENTITY["cn-n-conflict"], _rev_tree(), REV_BINDINGS)
    derivation = (
        "The conflict variant adds a recipe setting the same reversed association's"
        " associationDirection to Both while reverse-reference-links sets One: two different"
        " scalar values for one target/path refuse profile-write-conflict; nothing is applied."
    )
    return normalize_refusal(
        "cn-n-relation-direction-conflict",
        "DESIGN R3.3 §7.2 Relation direction (conflicting pairs refuse); §2.4 write conflicts",
        derivation,
        "cn-n-conflict",
        env_in,
        "profile-write-conflict",
    )


def _ext_tree(
    *,
    alpha_name: str = "Alpha",
    ext_name: str = "external-lane",
    alpha_members: Json = None,
    ext_members: Json = None,
) -> dict[str, Json]:
    alpha = node("Lane", "Lane_alpha", name=alpha_name)
    if alpha_members is not None:
        alpha["flowNodeRef"] = alpha_members
    ext = node("Lane", "Lane_ext", name=ext_name)
    if ext_members is not None:
        ext["flowNodeRef"] = ext_members
    lanes = [
        node("Lane", "Lane_zeta", name="Zeta", flowNodeRef=["Call_int", "Call_inc", "Task_E"]),
        alpha,
        ext,
    ]
    return definitions(
        "Definitions_ext",
        node(
            "Process",
            "Process_E",
            isExecutable=False,
            flowElements=[
                node(
                    "CallActivity",
                    "Call_ext",
                    name="External supplier",
                    documentation=[
                        doc("Source: supplier call", "text/plain"),
                        doc("external", MARKER_FORMAT),
                    ],
                ),
                node(
                    "CallActivity", "Call_int", name="Run sub-process", calledElement="Process_sub"
                ),
                node("CallActivity", "Call_inc", name="Undecided call"),
                node("Task", "Task_E", name="Prepare"),
            ],
            laneSets=[node("LaneSet", "LS_E", name="lane-set", lanes=lanes)],
        ),
        node("Process", "Process_sub", isExecutable=False),
        collaboration("Collab_E", main_participant("Main_E", "Process_E")),
        collaboration("Collab_sub", main_participant("Main_sub", "Process_sub")),
    )


EXT_BINDINGS = [
    binding("Process_E", "collaboration", "Collab_E"),
    binding("Process_E", "external-lane", "Lane_ext"),
    binding("Process_E", "lane-set", "LS_E"),
    binding("Process_E", "main-participant", "Main_E"),
    binding("Process_sub", "collaboration", "Collab_sub"),
    binding("Process_sub", "main-participant", "Main_sub"),
]
EXT_LANE = ptr("rootElements", 0, "laneSets", 0, "lanes", 2)
EXT_CLAUSE = (
    "DESIGN R3.3 §7.2 External membership; §4.1 external/internal/incomplete calls; §4.4;"
    " §13 OPEN-EXTERNAL, OPEN-SHARING; §16 items 2, 4"
)


def _ext_append_case(cid: str, alpha_name: str, extra: str) -> dict[str, Json]:
    tree_in = _ext_tree(alpha_name=alpha_name)
    tree_out = with_members(tree_in, EXT_LANE, flowNodeRef=["Call_ext"])
    entries = [
        edit_entry(
            "normalize",
            "assignRef",
            "relocate-marked-calls",
            EXT_LANE,
            "Lane_ext",
            "flowNodeRef",
            after=["Call_ext"],
        )
    ]
    derivation = (
        "Call_ext carries exactly one marker of the candidate encoding (text external, no"
        " calledElement) and belongs to no lane: under activation=qualification (fixtures may"
        " exercise the candidate encoding, §4.1) appendUnique adds it to the bound external"
        " lane. Call_int (internal target) and Call_inc (incomplete) stay untouched in"
        " Lane_zeta, whose stored member order [Call_int, Call_inc, Task_E] and the lane order"
        " [Lane_zeta, Lane_alpha, Lane_ext] are preserved. No membership is removed, so the"
        " responsibility check is not involved." + extra
    )
    return normalize_case(
        cid,
        EXT_CLAUSE + "; §7.3 external/internal/incomplete calls, role reorder/rename",
        derivation,
        "cn-n",
        (tree_in, EXT_BINDINGS),
        (tree_out, EXT_BINDINGS),
        entries,
        [],
        activation="qualification",
    )


def case_n_external_membership_append() -> dict[str, Json]:
    """Qualification appends the marked call to the bound external lane."""
    return _ext_append_case("cn-n-external-membership-append", "Alpha", "")


def case_n_role_rename_business_lane() -> dict[str, Json]:
    """Renaming a business lane changes nothing but its own name."""
    return _ext_append_case(
        "cn-n-role-rename-business-lane",
        "Alpha (renamed)",
        " Lane_alpha is renamed: supports are found by binding, never by name, so the output"
        " differs from cn-n-external-membership-append only by that name.",
    )


def case_n_external_membership_edit() -> dict[str, Json]:
    """Lane membership changes refuse profile-open in edit activation."""
    env_in = envelope(IDENTITY["cn-n"], _ext_tree(), EXT_BINDINGS)
    derivation = (
        "Same input as cn-n-external-membership-append with the default edit activation: the"
        " appendUnique is an effective Lane.flowNodeRef change of the external branch of N,"
        " gated by OPEN-EXTERNAL (encoding proof) and OPEN-RESERVED-N, so N refuses"
        " profile-open."
    )
    return normalize_refusal(
        "cn-n-external-membership-edit", EXT_CLAUSE, derivation, "cn-n", env_in, "profile-open"
    )


def case_n_external_membership_remove_refused() -> dict[str, Json]:
    """Removing an existing membership refuses responsibility-preservation-required."""
    env_in = envelope(
        IDENTITY["cn-n-relocate"], _ext_tree(alpha_members=["Call_ext"]), EXT_BINDINGS
    )
    derivation = (
        "Call_ext is already a member of business lane Lane_alpha; the relocate variant plans"
        " assignRef(remove) of that membership. No accepted persisted representation of"
        " original responsibility exists (§4.4, §16 item 4), so its status is unresolved and"
        " N refuses responsibility-preservation-required atomically, retaining every original"
        " membership."
    )
    return normalize_refusal(
        "cn-n-external-membership-remove-refused",
        EXT_CLAUSE + "; §7.3 preserved original memberships",
        derivation,
        "cn-n-relocate",
        env_in,
        "responsibility-preservation-required",
        activation="qualification",
    )


def case_n_reserved_lane_renamed() -> dict[str, Json]:
    """A renamed bound reserved lane is reused unchanged (fields are creation fields)."""
    tree = _ext_tree(ext_name="External (renamed)", ext_members=["Call_ext"])
    derivation = (
        "The bound external lane carries a user-chosen name, not the ensure declaration's"
        " creation field (external-lane). Reuse validation checks only type, parent and"
        " containment property, the processRef/owner relationship and the single binding"
        " (DESIGN §5.2; H C5: declared ensure fields are creation fields, a renamed bound"
        " support is reused unchanged): the lane is reused, never renamed back, and supports"
        " are never found by name. The marked Call_ext is already its member, so the"
        " appendUnique is a no-op; no effective change is gated, so the edit activation"
        " accepts with no entry (fixed point)."
    )
    return normalize_case(
        "cn-n-reserved-lane-renamed",
        "DESIGN R3.3 §5.2 support validation; §2.4 ensure; §7.3 role rename",
        derivation,
        "cn-n",
        (tree, EXT_BINDINGS),
        (tree, EXT_BINDINGS),
        [],
        [],
    )


def _pool_tree() -> dict[str, Json]:
    return definitions(
        "Definitions_pool",
        node("DataStore", "Store_P", name="Register"),
        node(
            "Process",
            "Process_P",
            isExecutable=False,
            flowElements=[
                node("Task", "Task_P", name="Consult register"),
                node("DataStoreReference", "Ref_P", dataStoreRef="Store_P"),
            ],
        ),
        collaboration("Collab_X", node("Participant", "Pool_X", name="reference-band")),
    )


POOL_IDS = {
    "collab": sid("Definitions_pool", "collaboration", "Process_P"),
    "main": sid("Process_P", "main-participant", "main-participant"),
    "band": sid("Process_P", "reference-band", "reference-band"),
}


def case_n_black_box_pool_retained() -> dict[str, Json]:
    """An unbound pool labelled like a support stays an ordinary pool."""
    tree_in = _pool_tree()
    tree_out = copy.deepcopy(tree_in)
    tree_out["rootElements"].append(  # type: ignore[index,union-attr]
        collaboration(
            POOL_IDS["collab"],
            main_participant(POOL_IDS["main"], "Process_P"),
            band(POOL_IDS["band"]),
        )
    )
    collab = ptr("rootElements", 3)
    entries = [
        create_entry("normalize", "ensure", "ensure-base-supports", tree_out, collab),
        create_entry(
            "normalize", "ensure", "ensure-base-supports", tree_out, f"{collab}/participants/0"
        ),
        edit_entry(
            "normalize",
            "assignRef",
            "ensure-base-supports",
            f"{collab}/participants/0",
            POOL_IDS["main"],
            "processRef",
            after="Process_P",
            created=True,
        ),
        create_entry(
            "normalize", "ensure", "ensure-reference-band", tree_out, f"{collab}/participants/1"
        ),
    ]
    bindings_out = [
        binding("Process_P", "collaboration", POOL_IDS["collab"]),
        binding("Process_P", "main-participant", POOL_IDS["main"]),
        binding("Process_P", "reference-band", POOL_IDS["band"]),
    ]
    derivation = (
        "Collab_X/Pool_X carry the support labels but no binding and non-allocator ids: N"
        " never finds a support by name and never takes over an ordinary black-box pool, so"
        " it creates a new Collaboration, main Participant and band for Process_P (OPEN-MACHINE"
        " default: create a new band when none is explicitly selected) and leaves Collab_X"
        " and Pool_X byte-identical. Ref_P has no association: placement without anchor."
    )
    return normalize_case(
        "cn-n-black-box-pool-retained",
        "DESIGN R3.3 §5.2 (ordinary pool never taken over); §13 OPEN-MACHINE; §16 item 6",
        derivation,
        "cn-n",
        (tree_in, []),
        (tree_out, bindings_out),
        entries,
        [placement("Ref_P", "Process_P", REFERENCE_REGION, [])],
        activation="qualification",
    )


def case_n_ensure_conflicting_definition() -> dict[str, Json]:
    """Two different ensure plans for one owner+role refuse profile-write-conflict."""
    env_in = envelope(IDENTITY["cn-n-ensure-conflict"], _ref_tree(), [])
    derivation = (
        "The variant appends a recipe ensuring (Process_A, reference-band) with name 'band'"
        " while ensure-reference-band declares 'reference-band': identical ensure plans"
        " coalesce, conflicting definitions refuse profile-write-conflict (qualification, so"
        " no gate intervenes)."
    )
    return normalize_refusal(
        "cn-n-ensure-conflicting-definition",
        "DESIGN R3.3 §2.4 (conflicting ensure definitions refuse); §7.2 Structure",
        derivation,
        "cn-n-ensure-conflict",
        env_in,
        "profile-write-conflict",
        activation="qualification",
    )


def case_n_not_fixed() -> dict[str, Json]:
    """A self-feeding normalize recipe fails the bounded fixed point."""
    env_in = envelope(IDENTITY["cn-n-unfixed"], _rev_tree(), REV_BINDINGS)
    derivation = (
        "decorate-main-participant sets name := concat(name, '*') on every Participant with a"
        " processRef. First pass: Main_R becomes 'main-participant*' (with the Link_R"
        " reversal). The bounded second evaluation succeeds: the bound Main_R is reused"
        " unchanged (reuse validation compares no declared field, H C5), the reversed link"
        " no longer matches, but the recipe changes the name again to"
        " 'main-participant**'. N(N(x)) != N(x), so N refuses normalization-not-fixed and"
        " rolls back the whole stage (no partial reversal either). Witness of the 'second"
        " evaluation still changes a value' branch; the refusal branch is"
        " cn-n-second-pass-refused."
    )
    return normalize_refusal(
        "cn-n-not-fixed",
        "DESIGN R3.3 §2.4 bounded second evaluation; §7.3 rollback on non-fixed point",
        derivation,
        "cn-n-unfixed",
        env_in,
        "normalization-not-fixed",
    )


def case_n_second_pass_refused() -> dict[str, Json]:
    """A refusal during the bounded second evaluation fails the N fixed point."""
    env_in = envelope(IDENTITY["cn-n-second-pass"], _rev_tree(), REV_BINDINGS)
    derivation = (
        "mark-main-participant sets name := 'marked' (idempotent) on Participants with a"
        " processRef; refuse-marked-participant refuses fixture-second-pass for a Participant"
        " named 'marked'. First pass (edit, every support bound, nothing gated): plans read"
        " the phase-start snapshot, so Main_R is renamed 'marked', Link_R reversed and Ref_R"
        " placed, and the refuse recipe has no candidate. The bounded second evaluation"
        " changes nothing (Main_R reused, the rename a no-op) but reaches the refuse step:"
        " the fixed-point proof fails with normalization-not-fixed (DESIGN §2.4), not with"
        " the second-pass code, and no candidate is exposed."
    )
    return normalize_refusal(
        "cn-n-second-pass-refused",
        "DESIGN R3.3 §2.4 bounded second evaluation (failure is normalization-not-fixed);"
        " §7.3 rollback",
        derivation,
        "cn-n-second-pass",
        env_in,
        "normalization-not-fixed",
    )


def case_n_dangling_reference() -> dict[str, Json]:
    """N refuses a dangling native reference at the graph index."""
    tree = definitions(
        "Definitions_dn",
        node(
            "Process",
            "Process_1",
            isExecutable=False,
            flowElements=[node("Task", "Task_1", name="Work")],
            artifacts=[
                node(
                    "Association",
                    "Assoc_ghost",
                    sourceRef="Task_1",
                    targetRef="Ghost",
                    associationDirection="None",
                )
            ],
        ),
    )
    derivation = (
        "Assoc_ghost.targetRef names no element. Dangling references are integrity errors"
        " before evaluation and never count as absent (DESIGN §2.2): the N graph index"
        " (precedence step 5, H C1/C2) refuses reference-dangling before any support plan;"
        " layout therefore only ever receives N outputs whose references resolve."
    )
    return normalize_refusal(
        "cn-n-dangling-reference",
        "DESIGN R3.3 §2.2 (dangling references before evaluation); §7.3 rollback",
        derivation,
        "cn-n",
        envelope(IDENTITY["cn-n"], tree, []),
        "reference-dangling",
    )


def case_n_compat_before_integrity() -> dict[str, Json]:
    """§3.3 compatibility is decided before envelope integrity (bindings)."""
    fixture = _support_negative(1)
    ident = _mismatch_identity("support", "1.0.0", "3" * 64)
    env_in = envelope(ident, fixture["input"], fixture["bindings"])  # type: ignore[arg-type]
    derivation = (
        "The duplicate-role envelope of cn-n-support-duplicate-role with an older document"
        " minor (1.0.0 vs 1.1.0) and its digest: precedence step 3 (§3.3 compatibility,"
        " P1 because C/N never load another package) refuses profile-source-unavailable"
        " before step 4 would report the duplicate binding (H C1: compatibility before"
        " envelope integrity)."
    )
    return normalize_refusal(
        "cn-n-compat-before-integrity",
        "DESIGN R3.3 §2.5 execution order (compatibility first); §3.3 P1; §5.1",
        derivation,
        "support",
        env_in,
        "profile-source-unavailable",
        activation="qualification",
    )


N_CN_CASES = [
    case_n_reference_region_multi_process,
    case_n_reference_region_edit,
    case_n_interface_region,
    case_n_relation_direction_reversal,
    case_n_relation_direction_conflict,
    case_n_external_membership_append,
    case_n_role_rename_business_lane,
    case_n_external_membership_edit,
    case_n_external_membership_remove_refused,
    case_n_reserved_lane_renamed,
    case_n_black_box_pool_retained,
    case_n_ensure_conflicting_definition,
    case_n_not_fixed,
    case_n_second_pass_refused,
    case_n_dangling_reference,
    case_n_compat_before_integrity,
]


# ---------------------------------------------------------------------------
# Cases: plan_recipe / apply_plan, deletion, remap and recreation chain
# ---------------------------------------------------------------------------


NEUTRAL_TYPES: dict[str, dict[str, Json]] = load_json(MECH / "neutral-descriptors.json")["types"]  # type: ignore[index,assignment]
SUPPORT_TYPES: dict[str, dict[str, Json]] = SUPPORT_FIXTURE["descriptors"]["types"]  # type: ignore[index,assignment]


def containment_facts(types: dict[str, dict[str, Json]], owner: str, prop: str) -> dict[str, Json]:
    """Return the descriptive facts a planned create/ensure carries (spec §3.2).

    Containment properties are multi-valued unless the descriptor lists them
    under the optional ``single`` facet.
    """
    single = prop in types[owner].get("single", [])  # type: ignore[operator]
    return {"cardinality": "single" if single else "many"}


def reference_facts(types: dict[str, dict[str, Json]], owner: str, prop: str) -> dict[str, Json]:
    """Return the descriptive facts a planned assignRef carries (spec §3.2).

    References are single-valued unless the descriptor lists them under the
    optional ``many`` facet; targetTypes are the admitted referenced types,
    unique and UTF-16 sorted.
    """
    many = prop in types[owner].get("many", [])  # type: ignore[operator]
    admitted = types[owner]["references"][prop]  # type: ignore[index]
    return {
        "cardinality": "many" if many else "single",
        "targetTypes": sorted(set(admitted), key=utf16),  # type: ignore[arg-type]
    }


def write_plan(phase: str, actor: str, activation: str, base: str, writes: list[Json]) -> Json:
    """Return one WritePlan/1 wire value (spec §3.2)."""
    return {
        "planVersion": "1",
        "phase": phase,
        "actor": actor,
        "activation": activation,
        "baseRevision": base,
        "writes": writes,
    }


def change_report(  # noqa: PLR0913
    tree: Json,
    bindings: list[dict[str, str]],
    *,
    entries: list[dict[str, Json]] | None = None,
    placements: list[dict[str, Json]] | None = None,
    created: list[str] | None = None,
    removed: list[str] | None = None,
) -> Json:
    """Return one ChangeReport/1 wire value (spec §3.3)."""
    return {
        "reportVersion": "change/1",
        "tree": copy.deepcopy(tree),
        "bindings": sort_bindings(copy.deepcopy(bindings)),
        "entries": sort_entries(entries or []),
        "placements": sort_placements(placements or []),
        "created": list(created or []),
        "removed": sorted(removed or [], key=utf16),
    }


def authority(
    actor: str = "editor", activation: str = "edit", *, deletion: bool = False
) -> dict[str, Json]:
    """Return one Authority wire value."""
    return {"actor": actor, "activation": activation, "deletionIntent": deletion}


def plan_case(  # noqa: PLR0913, PLR0917
    cid: str,
    clause: str,
    derivation: str,
    variant: str,
    env_in: Json,
    call: tuple[str, dict[str, Json], dict[str, Json]],
    plan_expected: Json,
    apply_expected: Json = None,
) -> dict[str, Json]:
    """Return one plan_recipe (+ apply_plan on the same envelope) case."""
    recipe_id, params, auth = call
    inp = {"envelope": env_in, "recipe": recipe_id, "params": params, "authority": auth}
    expected: dict[str, Json] = {"plan": plan_expected}
    if apply_expected is not None:
        expected["apply"] = apply_expected
    return make_case(cid, clause, derivation, "plan_recipe+apply_plan", variant, inp, expected)


P_CLAUSE = "DESIGN R3.3 §2.4 action grammar; §2.4.1 action/write matrix; §2.5 planRecipe/applyPlan"
CN_N_IDENTITY_NOTE = (
    " The envelope carries the current cn-n identity (placement regions equal to the support"
    " roles, H K1; edit recipes completing the §2.4 action matrix), which fixes its revision."
)

NEUTRAL_INPUT = copy.deepcopy(NEUTRAL_FIXTURE["input"])  # type: ignore[index]
GRID_INPUT = copy.deepcopy(GRID_FIXTURE["input"])  # type: ignore[index]


def _create_task_case(cid: str, variant: str, tree: Json, task_type: str) -> dict[str, Json]:
    env_in = envelope(IDENTITY[variant], tree, [])
    new_id = sid("Process_1", "task", "k-new")
    writes = [
        {
            "op": "create",
            "recipeId": "create-task",
            "type": "bpmn:" + task_type,
            "parent": {"id": "Process_1"},
            "property": "flowElements",
            "id": new_id,
            "fields": {"name": "New task"},
            **containment_facts(NEUTRAL_TYPES, "bpmn:Process", "flowElements"),
        }
    ]
    tree_out = copy.deepcopy(tree)
    at(tree_out, ptr("rootElements", 0, "flowElements")).append(  # type: ignore[attr-defined]
        node(task_type, new_id, name="New task")
    )
    plan = write_plan("create", "editor", "edit", str(env_in["semanticRevision"]), writes)
    derivation = (
        f"create-task on the vendored {variant} input: one allocated create of"
        f" bpmn:{task_type} (the two profiles differ in task subtype) with ownerId = the owner"
        " parameter's id, slot task, key = the key parameter, appended to"
        " Process_1.flowElements. The planned write carries the descriptive fact apply needs"
        " (Process.flowElements is multi-valued: cardinality many; spec §3.2, DESIGN §2.5"
        " applyPlan has no descriptor argument). Explicit commands report no Report/2 entry"
        " (spec §3.3); created lists the new id."
    )
    return plan_case(
        cid,
        P_CLAUSE + "; §3.2 allocated create",
        derivation,
        variant,
        env_in,
        ("create-task", {"owner": "Process_1", "key": "k-new", "name": "New task"}, authority()),
        pure_ok(plan),
        pure_ok(change_report(tree_out, [], created=[new_id])),
    )


def case_plan_create_task_neutral() -> dict[str, Json]:
    """Allocated create of a bpmn:Task (neutral)."""
    return _create_task_case("cn-plan-create-task-neutral", "neutral", NEUTRAL_INPUT, "Task")


def case_plan_create_task_grid() -> dict[str, Json]:
    """Allocated create of a bpmn:ServiceTask (grid)."""
    return _create_task_case("cn-plan-create-task-grid", "grid", GRID_INPUT, "ServiceTask")


def case_plan_add_note_containment() -> dict[str, Json]:
    """Containment identity: Documentation is created without any id."""
    env_in = envelope(IDENTITY["neutral"], NEUTRAL_INPUT, [])
    writes = [
        {
            "op": "create",
            "recipeId": "add-note",
            "type": "bpmn:Documentation",
            "parent": {"id": "Task_B"},
            "property": "documentation",
            "fields": {"text": "Preserved source", "textFormat": "text/plain"},
            **containment_facts(NEUTRAL_TYPES, "bpmn:Task", "documentation"),
        }
    ]
    tree_out = with_members(
        NEUTRAL_INPUT,
        ptr("rootElements", 0, "flowElements", 0),
        documentation=[doc("Preserved source", "text/plain")],
    )
    plan = write_plan("edit", "editor", "edit", str(env_in["semanticRevision"]), writes)
    derivation = (
        "add-note uses identity containment: the planned create carries no id (no ownerId,"
        " slot or key) and its descriptive fact (Task.documentation is multi-valued:"
        " cardinality many); the Documentation is appended to Task_B.documentation exactly as"
        " the vendored neutral-fixture created[0]; created lists only ID-bearing creations"
        " (empty here)."
    )
    return plan_case(
        "cn-plan-add-note-containment",
        P_CLAUSE + "; §3.2 identity mode containment",
        derivation,
        "neutral",
        env_in,
        ("add-note", {"target": "Task_B", "body": "Preserved source"}, authority()),
        pure_ok(plan),
        pure_ok(change_report(tree_out, [])),
    )


def _create_aid_case(cid: str, variant: str, tree: Json, prefix: str) -> dict[str, Json]:
    env_in = envelope(IDENTITY[variant], tree, [])
    new_id = sid("Process_1", "aid", "new-note")
    text = prefix + "helper"
    writes = [
        {
            "op": "create",
            "recipeId": "create-aid",
            "type": "bpmn:TextAnnotation",
            "parent": {"id": "Process_1"},
            "property": "artifacts",
            "id": new_id,
            "fields": {"text": text},
            **containment_facts(NEUTRAL_TYPES, "bpmn:Process", "artifacts"),
        }
    ]
    tree_out = copy.deepcopy(tree)
    at(tree_out, ptr("rootElements", 0, "artifacts")).append(  # type: ignore[attr-defined]
        node("TextAnnotation", new_id, text=text)
    )
    plan = write_plan("create", "editor", "edit", str(env_in["semanticRevision"]), writes)
    derivation = (
        f"create-aid on the vendored {variant} input: concat of the profile's marker literal"
        f" '{prefix}' and the body gives '{text}'; the allocated id is the pinned fixture"
        " vector stable-id(Process_1, aid, new-note) = g_61b2...800c; the planned create"
        " carries cardinality many (Process.artifacts multi-valued, spec §3.2)."
    )
    return plan_case(
        cid,
        P_CLAUSE + "; §3.2 pinned fixture vector",
        derivation,
        variant,
        env_in,
        ("create-aid", {"owner": "Process_1", "key": "new-note", "body": "helper"}, authority()),
        pure_ok(plan),
        pure_ok(change_report(tree_out, [], created=[new_id])),
    )


def case_plan_create_aid_neutral() -> dict[str, Json]:
    """create-aid with the neutral marker literal."""
    return _create_aid_case("cn-plan-create-aid-neutral", "neutral", NEUTRAL_INPUT, "[Aid] ")


def case_plan_create_aid_grid() -> dict[str, Json]:
    """create-aid with the grid marker literal."""
    return _create_aid_case("cn-plan-create-aid-grid", "grid", GRID_INPUT, "[Note] ")


def case_plan_link() -> dict[str, Json]:
    """create plus two assignRef writes on the created handle."""
    env_in = envelope(IDENTITY["neutral"], NEUTRAL_INPUT, [])
    link = sid("Process_1", "link", "l1")
    writes = [
        {
            "op": "create",
            "recipeId": "link",
            "type": "bpmn:Association",
            "parent": {"id": "Process_1"},
            "property": "artifacts",
            "id": link,
            "fields": {"associationDirection": "None"},
            **containment_facts(NEUTRAL_TYPES, "bpmn:Process", "artifacts"),
        },
        {
            "op": "assignRef",
            "recipeId": "link",
            "target": {"id": link},
            "property": "sourceRef",
            "mode": "replace",
            "ids": ["Task_A"],
            **reference_facts(NEUTRAL_TYPES, "bpmn:Association", "sourceRef"),
        },
        {
            "op": "assignRef",
            "recipeId": "link",
            "target": {"id": link},
            "property": "targetRef",
            "mode": "replace",
            "ids": ["Task_B"],
            **reference_facts(NEUTRAL_TYPES, "bpmn:Association", "targetRef"),
        },
    ]
    tree_out = copy.deepcopy(NEUTRAL_INPUT)
    at(tree_out, ptr("rootElements", 0, "artifacts")).append(  # type: ignore[attr-defined]
        node(
            "Association", link, associationDirection="None", sourceRef="Task_A", targetRef="Task_B"
        )
    )
    plan = write_plan("reference", "editor", "edit", str(env_in["semanticRevision"]), writes)
    derivation = (
        "link creates one Association (allocated under Process_1, slot link, key l1) and"
        " assigns its single-valued sourceRef/targetRef to the element parameters; each"
        " assignRef carries cardinality single and the admitted targetTypes of the neutral"
        " descriptors (spec §3.2), which apply checks; reference writes never create an"
        " endpoint (both exist)."
    )
    return plan_case(
        "cn-plan-link",
        P_CLAUSE + "; §2.4 assignRef",
        derivation,
        "neutral",
        env_in,
        (
            "link",
            {"owner": "Process_1", "source": "Task_A", "target": "Task_B", "key": "l1"},
            authority(),
        ),
        pure_ok(plan),
        pure_ok(change_report(tree_out, [], created=[link])),
    )


def _cmd_tree() -> dict[str, Json]:
    return definitions(
        "Definitions_cmd",
        node(
            "Process",
            "Process_cmd",
            isExecutable=False,
            flowElements=[node("Task", "Task_cmd", name="Original")],
            laneSets=[
                node(
                    "LaneSet", "LS_c", name="Business", lanes=[node("Lane", "Lane_c", name="Team")]
                )
            ],
        ),
    )


def case_plan_scalar_write_conflict() -> dict[str, Json]:
    """Two different scalar values for one target/path refuse at apply."""
    env_in = envelope(IDENTITY["cn-n"], _cmd_tree(), [])
    writes = [
        {
            "op": "set",
            "recipeId": "conflicting-rename",
            "target": {"id": "Task_cmd"},
            "property": "name",
            "value": "first",
        },
        {
            "op": "set",
            "recipeId": "conflicting-rename",
            "target": {"id": "Task_cmd"},
            "property": "name",
            "value": "second",
        },
    ]
    plan = write_plan("edit", "editor", "edit", str(env_in["semanticRevision"]), writes)
    derivation = (
        "Planning records both declared set writes (scalar writes carry no descriptive fact);"
        " application detects two different scalar values for Task_cmd/name and refuses"
        " profile-write-conflict (no last-writer behaviour)." + CN_N_IDENTITY_NOTE
    )
    return plan_case(
        "cn-plan-scalar-write-conflict",
        P_CLAUSE + "; §2.4 write conflicts",
        derivation,
        "cn-n",
        env_in,
        ("conflicting-rename", {"target": "Task_cmd"}, authority()),
        pure_ok(plan),
        pure_refused("profile-write-conflict"),
    )


def case_plan_append_remove_conflict() -> dict[str, Json]:
    """Appending and removing the same id on one reference array conflicts."""
    env_in = envelope(IDENTITY["cn-n"], _cmd_tree(), [])
    writes = [
        {
            "op": "assignRef",
            "recipeId": "toggle-membership",
            "target": {"id": "Lane_c"},
            "property": "flowNodeRef",
            "mode": "appendUnique",
            "ids": ["Task_cmd"],
            **reference_facts(CN_TYPES, "bpmn:Lane", "flowNodeRef"),
        },
        {
            "op": "assignRef",
            "recipeId": "toggle-membership",
            "target": {"id": "Lane_c"},
            "property": "flowNodeRef",
            "mode": "remove",
            "ids": ["Task_cmd"],
            **reference_facts(CN_TYPES, "bpmn:Lane", "flowNodeRef"),
        },
    ]
    plan = write_plan("edit", "editor", "edit", str(env_in["semanticRevision"]), writes)
    derivation = (
        "appendUnique and remove deltas on Lane_c.flowNodeRef coalesce by id, but appending"
        " and removing the same id Task_cmd refuses profile-write-conflict at application."
        " Both planned writes carry the cn facts of Lane.flowNodeRef (cardinality many, the"
        " admitted flow-node targetTypes; spec §3.2)." + CN_N_IDENTITY_NOTE
    )
    return plan_case(
        "cn-plan-append-remove-conflict",
        P_CLAUSE + "; §2.4 appendUnique/remove coalescing",
        derivation,
        "cn-n",
        env_in,
        ("toggle-membership", {"lane": "Lane_c", "node": "Task_cmd"}, authority()),
        pure_ok(plan),
        pure_refused("profile-write-conflict"),
    )


def case_plan_missing_parameter() -> dict[str, Json]:
    """A missing required parameter refuses planning."""
    env_in = envelope(IDENTITY["neutral"], NEUTRAL_INPUT, [])
    derivation = (
        "create-task declares the required string parameter name; omitting it refuses"
        " profile-ui-parameters before any evaluation (no parameter comes from a label or an"
        " ambient variable)."
    )
    return plan_case(
        "cn-plan-missing-parameter",
        P_CLAUSE + "; §8.3 parameter binding",
        derivation,
        "neutral",
        env_in,
        ("create-task", {"owner": "Process_1", "key": "k-new"}, authority()),
        pure_refused("profile-ui-parameters"),
    )


def case_plan_unknown_element_parameter() -> dict[str, Json]:
    """An element parameter naming no element refuses reference-dangling."""
    env_in = envelope(IDENTITY["neutral"], NEUTRAL_INPUT, [])
    derivation = (
        "Element parameters bind existing element ids only; Process_ghost is absent, so"
        " planning refuses reference-dangling."
    )
    return plan_case(
        "cn-plan-unknown-element-parameter",
        P_CLAUSE + "; §2.2 param (element parameters bind an existing element)",
        derivation,
        "neutral",
        env_in,
        ("create-task", {"owner": "Process_ghost", "key": "k", "name": "X"}, authority()),
        pure_refused("reference-dangling"),
    )


def case_apply_stale_plan() -> dict[str, Json]:
    """Applying a plan to a staged envelope of another revision refuses."""
    plan_record = case_plan_create_task_neutral()
    plan = plan_record["expected"]["plan"]["payload"]  # type: ignore[index]
    tree = at(plan_record, "/expected/apply/payload/tree")
    staged = envelope(IDENTITY["neutral"], tree, [])
    derivation = (
        "The plan (with its carried cardinality fact) is the cn-plan-create-task-neutral plan"
        " whose baseRevision is the revision of the neutral input; the staged envelope is the"
        " already-applied output (another revision) and its tree argument equals that"
        " envelope's tree, so apply_plan refuses operation-error (stale plan) and stages"
        " nothing."
    )
    return make_case(
        "cn-apply-stale-plan",
        "DESIGN R3.3 §2.5 applyPlan; §8.2 step 1 (stale revision refused before staging)",
        derivation,
        "apply_plan",
        "neutral",
        {"plan": plan, "envelope": staged},
        {"apply": pure_refused("operation-error")},
    )


def case_plan_ambiguous_binding() -> dict[str, Json]:
    """bind(one) over two candidates refuses profile-ambiguous-binding."""
    tree = definitions(
        "Definitions_amb",
        node(
            "Process",
            "Process_amb",
            isExecutable=False,
            flowElements=[node("Task", "Task_1", name="One"), node("Task", "Task_2", name="Two")],
        ),
    )
    env_in = envelope(IDENTITY["cn-n"], tree, [])
    derivation = (
        "rename-only-task binds one Task among the owner's flowElements with cardinality"
        " one; Process_amb has two, so planning refuses profile-ambiguous-binding (array"
        " order never chooses a winner)." + CN_N_IDENTITY_NOTE
    )
    return plan_case(
        "cn-plan-ambiguous-binding",
        P_CLAUSE + "; §2.4 bind cardinality",
        derivation,
        "cn-n",
        env_in,
        ("rename-only-task", {"owner": "Process_amb"}, authority()),
        pure_refused("profile-ambiguous-binding"),
    )


def case_plan_remove_referenced() -> dict[str, Json]:
    """Removing an element with a retained inbound reference refuses."""
    tree = definitions(
        "Definitions_rm",
        node(
            "Process",
            "Process_rm",
            isExecutable=False,
            flowElements=[node("Task", "Task_A", name="A"), node("Task", "Task_B", name="B")],
            artifacts=[
                node(
                    "Association",
                    "Assoc_1",
                    sourceRef="Task_A",
                    targetRef="Task_B",
                    associationDirection="None",
                )
            ],
        ),
    )
    env_in = envelope(IDENTITY["cn-n"], tree, [])
    derivation = (
        "remove-element(Task_A) with policy refuseIfReferenced and no declared dependents:"
        " the inbound closure contains Assoc_1.sourceRef, a retained reference, so planning"
        " refuses reference-dangling; no cascading delete exists." + CN_N_IDENTITY_NOTE
    )
    return plan_case(
        "cn-plan-remove-referenced",
        P_CLAUSE + "; §2.4 remove dependency closure",
        derivation,
        "cn-n",
        env_in,
        ("remove-element", {"target": "Task_A"}, authority(deletion=True)),
        pure_refused("reference-dangling"),
    )


# --- action / refusal matrix completions (seal review coverage finding) -------


def case_plan_unset_name() -> dict[str, Json]:
    """An authorized unset removes one declared scalar field."""
    tree = _cmd_tree()
    env_in = envelope(IDENTITY["cn-n"], tree, [])
    writes = [
        {
            "op": "unset",
            "recipeId": "clear-name",
            "target": {"id": "Task_cmd"},
            "property": "name",
        }
    ]
    tree_out = copy.deepcopy(tree)
    del at(tree_out, ptr("rootElements", 0, "flowElements", 0))["name"]  # type: ignore[attr-defined]
    plan = write_plan("edit", "editor", "edit", str(env_in["semanticRevision"]), writes)
    derivation = (
        "clear-name declares {self,/name,unset} and one unset step: the edit plan has one"
        " unset write (single-segment scalar path, no value, no descriptive fact needed) and"
        " application removes Task_cmd.name (Task.name is an optional scalar of the cn base,"
        " editor-produced). Explicit commands report no Report/2 entry; nothing is created"
        " or removed."
    )
    return plan_case(
        "cn-plan-unset-name",
        P_CLAUSE + "; §2.4 set/unset",
        derivation,
        "cn-n",
        env_in,
        ("clear-name", {"target": "Task_cmd"}, authority()),
        pure_ok(plan),
        pure_ok(change_report(tree_out, [])),
    )


def case_plan_wrong_parameter_type() -> dict[str, Json]:
    """A parameter of the wrong JSON type refuses profile-type."""
    env_in = envelope(IDENTITY["neutral"], NEUTRAL_INPUT, [])
    derivation = (
        "create-task declares name as a required string parameter; the call supplies the"
        " number 42. Parameters are validated in declaration order before evaluation, with no"
        " implicit coercion (DESIGN §8.3): a wrong JSON type refuses profile-type."
    )
    return plan_case(
        "cn-plan-wrong-parameter-type",
        P_CLAUSE + "; §8.3 typed parameters (no coercion)",
        derivation,
        "neutral",
        env_in,
        ("create-task", {"owner": "Process_1", "key": "k-new", "name": 42}, authority()),
        pure_refused("profile-type"),
    )


def case_plan_recipe_not_compiled() -> dict[str, Json]:
    """A recipe record that is not the compiled one refuses profile-symbol."""
    env_in = envelope(IDENTITY["neutral"], NEUTRAL_INPUT, [])
    record = copy.deepcopy(PROFILES["neutral"]["recipes"][0])  # type: ignore[index]
    record["steps"][0]["slot"] = "task-other"  # type: ignore[index]
    derivation = (
        "The recipe argument keeps the id create-task but changes its allocation slot, so"
        " it differs (JCS) from compiled.recipes['create-task']: planning accepts only"
        " compiled recipes (CR-05 symbols; no recipe from outside the profile), so"
        " plan_recipe refuses profile-symbol before reading parameters."
    )
    return plan_case(
        "cn-plan-recipe-not-compiled",
        P_CLAUSE + "; §2.4.1 CR-05 symbols",
        derivation,
        "neutral",
        env_in,
        (record, {"owner": "Process_1", "key": "k-new", "name": "New task"}, authority()),  # type: ignore[arg-type]
        pure_refused("profile-symbol"),
    )


def case_plan_export_phase() -> dict[str, Json]:
    """An export recipe cannot be planned as a semantic write plan."""
    env_in = envelope(IDENTITY["neutral"], NEUTRAL_INPUT, [])
    derivation = (
        "export-pages is an export recipe (emit actions on the render binding); export has"
        " no native write authority (DESIGN §2.4.1 R3.1 witness) and is planned by"
        " map_export (lot 4), so plan_recipe refuses profile-action-phase."
    )
    return plan_case(
        "cn-plan-export-phase",
        P_CLAUSE + "; §2.4.1 CR-14 action phases",
        derivation,
        "neutral",
        env_in,
        ("export-pages", {}, authority()),
        pure_refused("profile-action-phase"),
    )


def case_plan_actor_mismatch() -> dict[str, Json]:
    """An explicit create recipe planned by the code actor refuses profile-producer."""
    env_in = envelope(IDENTITY["neutral"], NEUTRAL_INPUT, [])
    derivation = (
        "Explicit create/edit/reference/convert/migrate commands use the editor actor,"
        " complete/normalize use code (DESIGN §2.4.1 R3.1 bounded authority witness):"
        " planning create-task with actor code refuses profile-producer."
    )
    return plan_case(
        "cn-plan-actor-mismatch",
        P_CLAUSE + "; §2.4.1 bounded authority witness",
        derivation,
        "neutral",
        env_in,
        (
            "create-task",
            {"owner": "Process_1", "key": "k-new", "name": "New task"},
            authority("code"),
        ),
        pure_refused("profile-producer"),
    )


def case_plan_undeclared_parameter() -> dict[str, Json]:
    """A supplied parameter the recipe does not declare refuses profile-ui-parameters."""
    env_in = envelope(IDENTITY["neutral"], NEUTRAL_INPUT, [])
    derivation = (
        "create-task declares owner, key and name; an additional colour parameter is not a"
        " declared parameter (DESIGN §8.3: parameters bind declared names only), so"
        " planning refuses profile-ui-parameters."
    )
    return plan_case(
        "cn-plan-undeclared-parameter",
        P_CLAUSE + "; §8.3 parameter binding",
        derivation,
        "neutral",
        env_in,
        (
            "create-task",
            {"owner": "Process_1", "key": "k-new", "name": "New task", "colour": "red"},
            authority(),
        ),
        pure_refused("profile-ui-parameters"),
    )


def case_plan_invalid_authority() -> dict[str, Json]:
    """An Authority outside its closed record refuses operation-error."""
    env_in = envelope(IDENTITY["neutral"], NEUTRAL_INPUT, [])
    derivation = (
        "Authority.actor is the closed set editor or code (spec §3.1); 'ai' is not an"
        " explicit-command or C/N actor, so the invocation is invalid: operation-error"
        " (H C11) before any recipe check."
    )
    return plan_case(
        "cn-plan-invalid-authority",
        P_CLAUSE + "; spec §3.1 Authority",
        derivation,
        "neutral",
        env_in,
        (
            "create-task",
            {"owner": "Process_1", "key": "k-new", "name": "New task"},
            authority("ai"),
        ),
        pure_refused("operation-error"),
    )


def case_plan_optional_binding_missing() -> dict[str, Json]:
    """A required use of a MISSING binding refuses profile-type."""
    tree = definitions("Definitions_opt", node("Process", "Process_opt", isExecutable=False))
    env_in = envelope(IDENTITY["cn-n"], tree, [])
    derivation = (
        "rename-optional-task binds task with cardinality zeroOrOne over the owner's Task"
        " children; Process_opt has none, so task is MISSING (DESIGN §2.4 bind) and the set"
        " step is a required use of MISSING, which refuses (DESIGN §2.2): profile-type."
    )
    return plan_case(
        "cn-plan-optional-binding-missing",
        P_CLAUSE + "; §2.2 required use of MISSING; §2.4 bind zeroOrOne",
        derivation,
        "cn-n",
        env_in,
        ("rename-optional-task", {"owner": "Process_opt"}, authority()),
        pure_refused("profile-type"),
    )


def case_plan_link_wrong_target_type() -> dict[str, Json]:
    """apply_plan checks the carried target types of a reference write."""
    env_in = envelope(IDENTITY["neutral"], NEUTRAL_INPUT, [])
    link = sid("Process_1", "link", "l2")
    facts = reference_facts(NEUTRAL_TYPES, "bpmn:Association", "targetRef")
    writes = [
        {
            "op": "create",
            "recipeId": "link",
            "type": "bpmn:Association",
            "parent": {"id": "Process_1"},
            "property": "artifacts",
            "id": link,
            "fields": {"associationDirection": "None"},
            **containment_facts(NEUTRAL_TYPES, "bpmn:Process", "artifacts"),
        },
        {
            "op": "assignRef",
            "recipeId": "link",
            "target": {"id": link},
            "property": "sourceRef",
            "mode": "replace",
            "ids": ["Task_A"],
            **reference_facts(NEUTRAL_TYPES, "bpmn:Association", "sourceRef"),
        },
        {
            "op": "assignRef",
            "recipeId": "link",
            "target": {"id": link},
            "property": "targetRef",
            "mode": "replace",
            "ids": ["Process_1"],
            **facts,
        },
    ]
    plan = write_plan("reference", "editor", "edit", str(env_in["semanticRevision"]), writes)
    derivation = (
        "link with target = Process_1: the element parameter exists, so planning succeeds"
        " and records the targetRef write with the neutral targetTypes"
        f" {facts['targetTypes']}. Before assignment apply validates existence and target"
        " type (DESIGN §2.4 assignRef): a bpmn:Process is not admitted, so apply_plan"
        " refuses profile-type and stages nothing."
    )
    return plan_case(
        "cn-plan-link-wrong-target-type",
        P_CLAUSE + "; §2.4 assignRef (target type validated before assignment)",
        derivation,
        "neutral",
        env_in,
        (
            "link",
            {"owner": "Process_1", "source": "Task_A", "target": "Process_1", "key": "l2"},
            authority(),
        ),
        pure_ok(plan),
        pure_refused("profile-type"),
    )


def case_plan_create_id_collision() -> dict[str, Json]:
    """A planned allocated id already carried by another element refuses id-collision."""
    occupant = sid("Process_1", "task", "k-dup")
    tree = copy.deepcopy(NEUTRAL_INPUT)
    at(tree, ptr("rootElements", 0, "artifacts")).append(  # type: ignore[attr-defined]
        node("TextAnnotation", occupant, text="Occupant")
    )
    env_in = envelope(IDENTITY["neutral"], tree, [])
    writes = [
        {
            "op": "create",
            "recipeId": "create-task",
            "type": "bpmn:Task",
            "parent": {"id": "Process_1"},
            "property": "flowElements",
            "id": occupant,
            "fields": {"name": "Duplicate"},
            **containment_facts(NEUTRAL_TYPES, "bpmn:Process", "flowElements"),
        }
    ]
    plan = write_plan("create", "editor", "edit", str(env_in["semanticRevision"]), writes)
    derivation = (
        "create-task with key k-dup plans stable-id(Process_1, task, k-dup), which an"
        " unrelated TextAnnotation already carries. A computed collision with a different"
        " object is id-collision (DESIGN §3.2): apply_plan refuses it and never suffixes,"
        " overwrites or reidentifies."
    )
    return plan_case(
        "cn-plan-create-id-collision",
        P_CLAUSE + "; §3.2 computed collision",
        derivation,
        "neutral",
        env_in,
        ("create-task", {"owner": "Process_1", "key": "k-dup", "name": "Duplicate"}, authority()),
        pure_ok(plan),
        pure_refused("id-collision"),
    )


def case_apply_input_conflict() -> dict[str, Json]:
    """A staged tree that is not the staged envelope tree refuses input-conflict."""
    plan_record = case_plan_create_task_neutral()
    plan = plan_record["expected"]["plan"]["payload"]  # type: ignore[index]
    env_in = plan_record["input"]["envelope"]  # type: ignore[index]
    staged_tree = with_members(
        NEUTRAL_INPUT, ptr("rootElements", 0, "flowElements", 0), name="Edited"
    )
    derivation = (
        "The plan and the staged envelope are those of cn-plan-create-task-neutral, but the"
        " staged tree argument differs from the staged envelope's tree (Task_B renamed):"
        " two inputs for one staged state (DESIGN §8.1 input-conflict), refused before the"
        " revision check and before staging."
    )
    return make_case(
        "cn-apply-input-conflict",
        "DESIGN R3.3 §2.5 applyPlan(plan, stagedTree, stagedEnvelope); §8.1 input-conflict",
        derivation,
        "apply_plan",
        "neutral",
        {"plan": plan, "envelope": env_in, "stagedTree": staged_tree},
        {"apply": pure_refused("input-conflict")},
    )


def _lane_member_case(  # noqa: PLR0913, PLR0917
    cid: str,
    variant: str,
    types: dict[str, dict[str, Json]],
    tree: Json,
    lane_pointer: str,
    names: tuple[str, str],
    stored: Json,
) -> dict[str, Json]:
    env_in = envelope(IDENTITY[variant], tree, [])
    lane, member = names
    facts = reference_facts(types, "bpmn:Lane", "flowNodeRef")
    writes = [
        {
            "op": "assignRef",
            "recipeId": "assign-lane-member",
            "target": {"id": lane},
            "property": "flowNodeRef",
            "mode": "replace",
            "ids": [member],
            **facts,
        }
    ]
    tree_out = with_members(tree, lane_pointer, flowNodeRef=stored)
    plan = write_plan("edit", "editor", "edit", str(env_in["semanticRevision"]), writes)
    derivation = (
        f"assign-lane-member on the {variant} profile. planRecipe reads the descriptor"
        " index of its own ReadContext and records it in the write: bpmn:Lane.flowNodeRef is"
        f" {facts['cardinality']}-valued with targetTypes {facts['targetTypes']} in this"
        " profile's descriptors. applyPlan(plan, stagedTree, stagedEnvelope) has no"
        " descriptor argument (DESIGN §2.5) and applies the carried facts: the stored value"
        f" is {json.dumps(stored)}. The twin case on the other profile stores the other form,"
        " so a runtime resolving facts from ambient or global state fails one of them."
    )
    return plan_case(
        cid,
        P_CLAUSE + "; §2.5 ReadContext descriptor index; §2.4 assignRef cardinality",
        derivation,
        variant,
        env_in,
        ("assign-lane-member", {"lane": lane, "node": member}, authority()),
        pure_ok(plan),
        pure_ok(change_report(tree_out, [])),
    )


def case_plan_lane_member_cn() -> dict[str, Json]:
    """Descriptive context 1: a multi-valued Lane.flowNodeRef (cn slice)."""
    lane = ptr("rootElements", 0, "laneSets", 0, "lanes", 0)
    return _lane_member_case(
        "cn-plan-lane-member-cn",
        "cn-n",
        CN_TYPES,
        _cmd_tree(),
        lane,
        ("Lane_c", "Task_cmd"),
        ["Task_cmd"],
    )


def case_plan_lane_member_support() -> dict[str, Json]:
    """Descriptive context 2: a single-valued Lane.flowNodeRef (support slice)."""
    tree = definitions(
        "Definitions_support",
        node(
            "Process",
            "Process_A",
            isExecutable=False,
            flowElements=[node("Task", "Task_A", name="Work")],
            laneSets=[
                node(
                    "LaneSet",
                    "LaneSet_A",
                    name="Roles",
                    lanes=[node("Lane", "Lane_A", name="Team")],
                )
            ],
        ),
    )
    lane = ptr("rootElements", 0, "laneSets", 0, "lanes", 0)
    return _lane_member_case(
        "cn-plan-lane-member-support",
        "support-cmd",
        SUPPORT_TYPES,
        tree,
        lane,
        ("Lane_A", "Task_A"),
        "Task_A",
    )


def case_plan_reparent_annotation() -> dict[str, Json]:
    """An explicit reparent keeps the id and moves the element to the last position."""
    tree = definitions(
        "Definitions_mv",
        node(
            "Process",
            "Process_1",
            isExecutable=False,
            artifacts=[node("TextAnnotation", "Note_1", text="Move me")],
        ),
        node(
            "Process",
            "Process_2",
            isExecutable=False,
            artifacts=[node("TextAnnotation", "Note_2", text="Stay")],
        ),
    )
    env_in = envelope(IDENTITY["cn-n"], tree, [])
    writes = [
        {
            "op": "reparent",
            "recipeId": "move-annotation",
            "target": {"id": "Note_1"},
            "parent": {"id": "Process_2"},
            "property": "artifacts",
            "position": "last",
            **containment_facts(CN_TYPES, "bpmn:Process", "artifacts"),
        }
    ]
    tree_out = copy.deepcopy(tree)
    moved = at(tree_out, ptr("rootElements", 0, "artifacts")).pop()  # type: ignore[attr-defined]
    at(tree_out, ptr("rootElements", 1, "artifacts")).append(moved)  # type: ignore[attr-defined]
    plan = write_plan("edit", "editor", "edit", str(env_in["semanticRevision"]), writes)
    derivation = (
        "move-annotation declares {self,'',reparent} and {process,/artifacts,reparent}"
        " (DESIGN §2.4.1 reparent row) and one reparent step with position last: Note_1"
        " keeps its id and is appended after Note_2 in Process_2.artifacts; no reference"
        " names Note_1 and bpmn:TextAnnotation is admitted there. The source array is"
        " emptied and stays [] (H F1). Explicit edit; nothing is created or removed."
    )
    return plan_case(
        "cn-plan-reparent-annotation",
        P_CLAUSE + "; §2.4 reparent",
        derivation,
        "cn-n",
        env_in,
        ("move-annotation", {"note": "Note_1", "process": "Process_2"}, authority()),
        pure_ok(plan),
        pure_ok(change_report(tree_out, [])),
    )


PLAN_MATRIX_CASES = [
    case_plan_unset_name,
    case_plan_wrong_parameter_type,
    case_plan_recipe_not_compiled,
    case_plan_export_phase,
    case_plan_actor_mismatch,
    case_plan_undeclared_parameter,
    case_plan_invalid_authority,
    case_plan_optional_binding_missing,
    case_plan_link_wrong_target_type,
    case_plan_create_id_collision,
    case_apply_input_conflict,
    case_plan_lane_member_cn,
    case_plan_lane_member_support,
    case_plan_reparent_annotation,
]


# --- deletion / remap / recreation chain (cn-n) ----------------------------

DEL = {
    "collab": sid("Definitions_del", "collaboration", "Process_A"),
    "main": sid("Process_A", "main-participant", "main-participant"),
    "laneSet": sid("Process_A", "lane-set", "lane-set"),
    "lane": sid("Process_A", "external-lane", "external-lane"),
    "laneX": sid("Process_X", "external-lane", "external-lane"),
    "inputX": sid("Process_X", "process-input", "in-1"),
}
CHAIN_CLAUSE = "DESIGN R3.3 §7.2 support deletion/recreation/remap; §7.3 deletion/recreation"


def _chain_tree_1() -> dict[str, Json]:
    return definitions(
        "Definitions_del",
        node(
            "Process",
            "Process_A",
            isExecutable=False,
            flowElements=[node("Task", "Task_A1", name="Work")],
            laneSets=[
                node(
                    "LaneSet",
                    DEL["laneSet"],
                    name="lane-set",
                    lanes=[node("Lane", DEL["lane"], name="external-lane")],
                )
            ],
        ),
        collaboration(DEL["collab"], main_participant(DEL["main"], "Process_A")),
    )


CHAIN_BINDINGS_1 = [
    binding("Process_A", "collaboration", DEL["collab"]),
    binding("Process_A", "external-lane", DEL["lane"]),
    binding("Process_A", "lane-set", DEL["laneSet"]),
    binding("Process_A", "main-participant", DEL["main"]),
]


def _chain_tree_2() -> dict[str, Json]:
    """The chain tree after deleting the empty external lane: lanes stays [] (H F1)."""
    tree = _chain_tree_1()
    lane_set = at(tree, ptr("rootElements", 0, "laneSets", 0))
    lane_set["lanes"] = []  # type: ignore[index]
    return tree


CHAIN_BINDINGS_2 = [b for b in CHAIN_BINDINGS_1 if b["role"] != "external-lane"]


def _chain_tree_3() -> dict[str, Json]:
    tree = _chain_tree_2()
    at(tree, ptr("rootElements", 0))["id"] = "Process_X"  # type: ignore[index]
    at(tree, ptr("rootElements", 1, "participants", 0))["processRef"] = "Process_X"  # type: ignore[index]
    return tree


CHAIN_BINDINGS_3 = [binding("Process_X", b["role"], b["targetId"]) for b in CHAIN_BINDINGS_2]


def _chain_tree_4() -> dict[str, Json]:
    tree = _chain_tree_3()
    at(tree, ptr("rootElements", 0))["ioSpecification"] = node(  # type: ignore[index]
        "InputOutputSpecification",
        dataInputs=[node("DataInput", DEL["inputX"], name="Request")],
    )
    return tree


def case_n_empty_support_survives() -> dict[str, Json]:
    """A bound empty external lane survives N while nothing needs it."""
    tree = _chain_tree_1()
    derivation = (
        "Process_A has no marked call and no IO, so ensure-external-lane does not run; the"
        " bound empty external lane is neither validated away nor deleted (N never deletes:"
        " empty existing supports survive until explicit dependency-checked deletion). No"
        " change; accepted in edit activation."
    )
    return normalize_case(
        "cn-n-empty-support-survives",
        CHAIN_CLAUSE + " (empty supports survive)",
        derivation,
        "cn-n",
        (tree, CHAIN_BINDINGS_1),
        (tree, CHAIN_BINDINGS_1),
        [],
        [],
    )


def case_plan_remove_empty_support() -> dict[str, Json]:
    """Explicit dependency-checked deletion of the empty support and its binding."""
    env_in = envelope(IDENTITY["cn-n"], _chain_tree_1(), CHAIN_BINDINGS_1)
    writes = [
        {
            "op": "remove",
            "recipeId": "remove-element",
            "target": {"id": DEL["lane"]},
            "policy": "refuseIfReferenced",
            "deleteIds": [DEL["lane"]],
        }
    ]
    plan = write_plan("edit", "editor", "edit", str(env_in["semanticRevision"]), writes)
    derivation = (
        "remove-element on the empty external lane with explicit deletion intent: the closure"
        " is the lane alone (no retained inbound reference); application deletes it, keeps"
        " the emptied LaneSet.lanes array as [] (an emptied array is stored as written, H F1)"
        " and removes its envelope binding, the support's ownership record. removed lists"
        " the deleted id; explicit commands report no Report/2 entry."
    )
    return plan_case(
        "cn-plan-remove-empty-support",
        CHAIN_CLAUSE + "; §2.4 remove",
        derivation,
        "cn-n",
        env_in,
        ("remove-element", {"target": DEL["lane"]}, authority(deletion=True)),
        pure_ok(plan),
        pure_ok(change_report(_chain_tree_2(), CHAIN_BINDINGS_2, removed=[DEL["lane"]])),
    )


def case_plan_remove_without_intent() -> dict[str, Json]:
    """Deletion without explicit intent refuses profile-producer."""
    env_in = envelope(IDENTITY["cn-n"], _chain_tree_1(), CHAIN_BINDINGS_1)
    derivation = (
        "The remove action requires actor authorization and explicit deletion intent; the"
        " authority carries deletionIntent false, so planning refuses profile-producer."
        + CN_N_IDENTITY_NOTE
    )
    return plan_case(
        "cn-plan-remove-without-intent",
        "DESIGN R3.3 §2.4 remove (explicit deletion intent required)",
        derivation,
        "cn-n",
        env_in,
        ("remove-element", {"target": DEL["lane"]}, authority()),
        pure_refused("profile-producer"),
    )


def case_n_deleted_support_stays_absent() -> dict[str, Json]:
    """A deleted empty support stays absent while no element needs its role."""
    tree = _chain_tree_2()
    derivation = (
        "Input is the cn-plan-remove-empty-support output (LaneSet.lanes stored as []). Nothing"
        " needs the external-lane role, so N does not recreate it and never removes the empty"
        " array: no change, edit activation accepted."
    )
    return normalize_case(
        "cn-n-deleted-support-stays-absent",
        CHAIN_CLAUSE + " (deleted support stays absent)",
        derivation,
        "cn-n",
        (tree, CHAIN_BINDINGS_2),
        (tree, CHAIN_BINDINGS_2),
        [],
        [],
    )


def descriptor_digest(identity: Json) -> str:
    """Return the §9.2 descriptorDigest: H(descriptor pins sorted by unique id)."""
    pins = [
        {"id": p["id"], "version": p["version"], "sha256": p["sha256"]}  # type: ignore[index]
        for p in identity["descriptors"]  # type: ignore[index]
    ]
    return digest(sorted(pins, key=lambda p: utf16(str(p["id"]))))


def imported_di(identity: Json, diagrams: list[Json]) -> dict[str, Json]:
    """Return one Snapshot/1 importedDi record (§8.1.1 sha256 formula)."""
    record_digest = descriptor_digest(identity)
    return {
        "descriptorDigest": record_digest,
        "diagrams": copy.deepcopy(diagrams),
        "sha256": digest({"descriptorDigest": record_digest, "diagrams": diagrams}),
    }


def bounds(x: int, y: int, width: int, height: int) -> dict[str, Json]:
    """Return one DC Bounds literal (presentation, outside the semantic tree)."""
    return {"$type": "dc:Bounds", "x": x, "y": y, "width": width, "height": height}


def diagram(diagram_id: str, plane_element: str, shapes: list[tuple[str, str]]) -> dict[str, Json]:
    """Return one BPMNDiagram literal whose plane and shapes name semantic ids."""
    plane = [
        {
            "$type": "bpmndi:BPMNShape",
            "id": shape_id,
            "bpmnElement": element_id,
            "bounds": bounds(100 * index, 80, 100, 80),
        }
        for index, (shape_id, element_id) in enumerate(shapes, start=1)
    ]
    return {
        "$type": "bpmndi:BPMNDiagram",
        "id": diagram_id,
        "plane": {
            "$type": "bpmndi:BPMNPlane",
            "id": diagram_id + "_plane",
            "bpmnElement": plane_element,
            "planeElement": plane,
        },
    }


def remap_command(
    rows: list[tuple[str, str]],
    attestations: list[Json] | None = None,
    *,
    approved: bool = True,
) -> dict[str, Json]:
    """Return one approved id-remap migration command record (H B14, H9)."""
    return {
        "kind": "id-remap",
        "approved": approved,
        "approval": "technical",
        "map": [{"sourceId": s, "resultId": r, "domain": "migration"} for s, r in rows],
        "referenceFreeAttestations": attestations or [],
    }


def remap_case(  # noqa: PLR0913, PLR0917
    cid: str,
    clause: str,
    derivation: str,
    inputs: tuple[Json, list[dict[str, str]], list[Json]],
    command: dict[str, Json],
    outputs: tuple[Json, list[dict[str, str]], list[Json]],
    rows: list[tuple[str, str]],
    entries: list[dict[str, Json]] | None = None,
) -> dict[str, Json]:
    """Return one accepted remapIds case (cn-n profile, qualification activation).

    inputs/outputs are (tree, bindings, diagrams); rows is the complete
    original->result map of every ID-bearing element (identity rows included).
    """
    ident = IDENTITY["cn-n"]
    env_in = envelope(ident, inputs[0], inputs[1])
    env_out = envelope(ident, outputs[0], outputs[1])
    base, rev = str(env_in["semanticRevision"]), str(env_out["semanticRevision"])
    id_rows = [{"sourceId": s, "resultId": r, "domain": "migration"} for s, r in rows]
    rep = success_report("remapIds", ident, base, rev, entries or [], id_rows)
    payload = {"envelope": env_out, "importedDi": imported_di(ident, outputs[2])}
    expected = ok_result("remapIds", ident, base, rev, rep, payload)
    inp = {
        "envelope": env_in,
        "importedDi": imported_di(ident, inputs[2]),
        "command": command,
        "activation": "qualification",
    }
    return make_case(cid, clause, derivation, "remap_ids", "cn-n", inp, expected)


def remap_refusal(  # noqa: PLR0913, PLR0917
    cid: str,
    clause: str,
    derivation: str,
    env_in: dict[str, Json],
    command: dict[str, Json],
    code: str,
    *,
    activation: str = "qualification",
) -> dict[str, Json]:
    """Return one refused remapIds case (cn-n profile, empty archived DI)."""
    identity, base = echo_fields(env_in)
    expected = refused_result("remapIds", code, identity, base)
    inp = {
        "envelope": env_in,
        "importedDi": imported_di(IDENTITY["cn-n"], []),
        "command": command,
        "activation": activation,
    }
    return make_case(cid, clause, derivation, "remap_ids", "cn-n", inp, expected)


REMAP_CLAUSE = "DESIGN R3.3 §5.2 ID remapping (separate approved import migration); §13 OPEN-ID"


def _chain_diagram(process_id: str) -> list[Json]:
    return [diagram("Diagram_del", process_id, [("Shape_task_A1", "Task_A1")])]


def case_remap_owner() -> dict[str, Json]:
    """Owner remap: references, bindings and DI follow, support ids survive."""
    rows = [
        ("Definitions_del", "Definitions_del"),
        ("Process_A", "Process_X"),
        ("Task_A1", "Task_A1"),
        (DEL["collab"], DEL["collab"]),
        (DEL["main"], DEL["main"]),
        (DEL["laneSet"], DEL["laneSet"]),
    ]
    derivation = (
        "Input is the cn-n-deleted-support-stays-absent document plus its archived imported"
        " DI (one process diagram whose plane names Process_A). The approved command maps"
        " Process_A to Process_X; the total map is identity elsewhere. The main Participant's"
        " processRef, every binding ownerId and the DI plane bpmnElement follow, while the"
        " surviving supports keep their actual stable-id ids allocated under Process_A (never"
        " reallocated) and DI objects keep their own ids. Payload {envelope, importedDi} with"
        " the importedDi digest recomputed; report idMap is the complete original->result map"
        " of every ID-bearing element (identity rows included, domain migration, §10.1"
        " order; H B14). No invalidation flag: the new revision implies it."
    )
    return remap_case(
        "cn-remap-owner",
        REMAP_CLAUSE + "; §7.2 surviving support IDs unchanged through owner remaps",
        derivation,
        (_chain_tree_2(), CHAIN_BINDINGS_2, _chain_diagram("Process_A")),
        remap_command([("Process_A", "Process_X")]),
        (_chain_tree_3(), CHAIN_BINDINGS_3, _chain_diagram("Process_X")),
        rows,
    )


def case_remap_gated() -> dict[str, Json]:
    """ID remap refuses profile-open in edit activation."""
    env_in = envelope(IDENTITY["cn-n"], _chain_tree_2(), CHAIN_BINDINGS_2)
    derivation = (
        "ID remapping is a separate approved import migration: the command record is valid"
        " and approved, but the OPEN-ID technical gate is open, so with the default edit"
        " activation remap_ids refuses profile-open (H H9: approval record and gate both"
        " apply)."
    )
    return remap_refusal(
        "cn-remap-gated",
        REMAP_CLAUSE,
        derivation,
        env_in,
        remap_command([("Process_A", "Process_X")]),
        "profile-open",
        activation="edit",
    )


def case_remap_not_approved() -> dict[str, Json]:
    """A remap command without approval is an invalid invocation."""
    env_in = envelope(IDENTITY["cn-n"], _chain_tree_2(), CHAIN_BINDINGS_2)
    derivation = (
        "The command record carries approved false: the approved import migration requires"
        " approved true and an approval (H H9), so remap_ids refuses operation-error at"
        " argument validation, before the OPEN-ID gate and any map check."
    )
    return remap_refusal(
        "cn-remap-not-approved",
        REMAP_CLAUSE + "; §16 item 1 (approved migration)",
        derivation,
        env_in,
        remap_command([("Process_A", "Process_X")], approved=False),
        "operation-error",
    )


def case_plan_create_process_input() -> dict[str, Json]:
    """Containment ioSpecification plus allocated DataInput under explicit owner."""
    env_in = envelope(IDENTITY["cn-n"], _chain_tree_3(), CHAIN_BINDINGS_3)
    writes = [
        {
            "op": "create",
            "recipeId": "create-process-input",
            "type": "bpmn:InputOutputSpecification",
            "parent": {"id": "Process_X"},
            "property": "ioSpecification",
            "fields": {},
            **containment_facts(CN_TYPES, "bpmn:Process", "ioSpecification"),
        },
        {
            "op": "create",
            "recipeId": "create-process-input",
            "type": "bpmn:DataInput",
            "parent": {"handle": 0},
            "property": "dataInputs",
            "id": DEL["inputX"],
            "fields": {"name": "Request"},
            **containment_facts(CN_TYPES, "bpmn:InputOutputSpecification", "dataInputs"),
        },
    ]
    plan = write_plan("create", "editor", "edit", str(env_in["semanticRevision"]), writes)
    derivation = (
        "Input is the cn-remap-owner output. The ID-less ioSpecification is created by"
        " containment (no id) and addressed within the plan by its handle (index 0); the"
        " DataInput's ownerId is the explicitly evaluated owner id Process_X, never the"
        " ID-less parent: stable-id(Process_X, process-input, in-1). The two planned writes"
        " carry the cn slice facts apply needs: Process.ioSpecification is single-valued"
        " (cardinality single: an object, not an array) and dataInputs multi-valued"
        " (cardinality many); the LaneSet keeps its stored empty lanes array."
    )
    return plan_case(
        "cn-plan-create-process-input",
        P_CLAUSE + "; §3.2 (ownerId explicit, including under an ID-less ioSpecification)",
        derivation,
        "cn-n",
        env_in,
        (
            "create-process-input",
            {"owner": "Process_X", "key": "in-1", "name": "Request"},
            authority(),
        ),
        pure_ok(plan),
        pure_ok(change_report(_chain_tree_4(), CHAIN_BINDINGS_3, created=[DEL["inputX"]])),
    )


def case_n_recreate_after_remap() -> dict[str, Json]:
    """A later need recreates the deleted support with the current ownerId."""
    tree_in = _chain_tree_4()
    tree_out = with_members(
        tree_in,
        ptr("rootElements", 0, "laneSets", 0),
        lanes=[node("Lane", DEL["laneX"], name="external-lane")],
    )
    bindings_out = [*CHAIN_BINDINGS_3, binding("Process_X", "external-lane", DEL["laneX"])]
    entries = [
        create_entry(
            "normalize",
            "ensure",
            "ensure-external-lane",
            tree_out,
            ptr("rootElements", 0, "laneSets", 0, "lanes", 0),
        )
    ]
    derivation = (
        "Input is the cn-plan-create-process-input output: the new Process IO needs the"
        " external-lane role again. The bound LaneSet is reused; the deleted lane's identity"
        " ended, so ensure creates stable-id(Process_X, external-lane, external-lane) with the"
        f" current ownerId ({DEL['laneX'][:10]}...), different from the deleted"
        f" {DEL['lane'][:10]}..., and reports it; the recreated lane is appended to the"
        " LaneSet's stored empty lanes array. The DataInput is placed in region external-lane"
        " without anchor."
    )
    return normalize_case(
        "cn-n-recreate-after-remap",
        CHAIN_CLAUSE + " (later need triggers ensure with the current ownerId)",
        derivation,
        "cn-n",
        (tree_in, CHAIN_BINDINGS_3),
        (tree_out, bindings_out),
        entries,
        [placement(DEL["inputX"], "Process_X", INTERFACE_REGION, [])],
        activation="qualification",
    )


def case_n_recreate_after_remap_edit() -> dict[str, Json]:
    """Recreation is a support creation: profile-open in edit activation."""
    env_in = envelope(IDENTITY["cn-n"], _chain_tree_4(), CHAIN_BINDINGS_3)
    derivation = (
        "Same input as cn-n-recreate-after-remap with the default edit activation: the lane"
        " recreation is a persisted support creation, refused profile-open."
    )
    return normalize_refusal(
        "cn-n-recreate-after-remap-edit",
        N_CLAUSE_GATE,
        derivation,
        "cn-n",
        env_in,
        "profile-open",
    )


def _map_tree(*, opaque: bool = False) -> dict[str, Json]:
    task = node("Task", "Task_m", name="Main work")
    if opaque:
        task["x"] = "Process_sub"
    return definitions(
        "Definitions_map",
        node(
            "Process",
            "Process_main",
            isExecutable=False,
            flowElements=[
                node("CallActivity", "Call_in", name="Call child", calledElement="Process_sub"),
                node(
                    "CallActivity",
                    "Call_out",
                    name="Call outside",
                    calledElement="Process_external",
                ),
                task,
            ],
        ),
        node("Process", "Process_sub", isExecutable=False),
    )


def _map_diagrams(task_id: str, call_id: str = "Call_in") -> list[Json]:
    return [
        diagram(
            "Diagram_map",
            "Process_main",
            [("Shape_call", call_id), ("Shape_task", task_id)],
        )
    ]


def _dangling_call_entry(call_out: str) -> dict[str, Json]:
    """Return the observed reference-dangling entry of Call_out (H C2, B9)."""
    written = at_property(call_out, "calledElement")
    return entry(
        stage="import",
        code="reference-dangling",
        rule="remap-ids",
        message="reference-dangling",
        severity="error",
        classification="integrity",
        disposition="observed",
        source=coord(written, "Call_out"),
        result=coord(written, "Call_out"),
        prop="calledElement",
        before="Process_external",
        after="Process_external",
    )


MAP_ROWS_IDENTITY = [
    ("Call_in", "Call_in"),
    ("Call_out", "Call_out"),
    ("Definitions_map", "Definitions_map"),
    ("Process_main", "Process_main"),
    ("Process_sub", "Process_sub"),
    ("Task_m", "Task_m"),
]


def _map_rows(**changes: str) -> list[tuple[str, str]]:
    """Return the complete idMap rows of the map tree with the given renamings."""
    return [(s, changes.get(s, r)) for s, r in MAP_ROWS_IDENTITY]


def case_remap_internal_call_and_dangling() -> dict[str, Json]:
    """Internal calledElement follows the map; a dangling target stays and is reported."""
    tree_in = _map_tree()
    tree_out = copy.deepcopy(tree_in)
    at(tree_out, ptr("rootElements", 1))["id"] = "Process_child"  # type: ignore[index]
    at(tree_out, ptr("rootElements", 0, "flowElements", 0))["calledElement"] = "Process_child"  # type: ignore[index]
    at(tree_out, ptr("rootElements", 0, "flowElements", 2))["id"] = "Task_main"  # type: ignore[index]
    call_out = ptr("rootElements", 0, "flowElements", 1)
    derivation = (
        "The approved command renames Process_sub and Task_m. Call_in's internal"
        " calledElement is rewritten to Process_child and the DI shape of Task_m now names"
        " Task_main (DI object ids unchanged); Call_out's calledElement names no"
        " in-document element: remapIds keeps it unchanged (never fetched) and reports one"
        " observed reference-dangling integrity entry (stage import, ruleId remap-ids, at"
        " <Call_out>/calledElement; H C2, B9) and succeeds. idMap lists every ID-bearing"
        " element."
    )
    return remap_case(
        "cn-remap-internal-call-and-dangling",
        REMAP_CLAUSE + "; §7.3 ID remaps, native references",
        derivation,
        (tree_in, [], _map_diagrams("Task_m")),
        remap_command([("Process_sub", "Process_child"), ("Task_m", "Task_main")]),
        (tree_out, [], _map_diagrams("Task_main")),
        _map_rows(Process_sub="Process_child", Task_m="Task_main"),
        [_dangling_call_entry(call_out)],
    )


def case_remap_swap() -> dict[str, Json]:
    """A swap is one total map applied at once, never sequential renames."""
    tree_in = _map_tree()
    tree_out = copy.deepcopy(tree_in)
    at(tree_out, ptr("rootElements", 0, "flowElements", 0))["id"] = "Task_m"  # type: ignore[index]
    at(tree_out, ptr("rootElements", 0, "flowElements", 2))["id"] = "Call_in"  # type: ignore[index]
    call_out = ptr("rootElements", 0, "flowElements", 1)
    derivation = (
        "The command swaps Call_in and Task_m. The total map is built before application"
        " (DESIGN §5.2) and is injective over the retained ids, so both elements exchange"
        " their ids in one step (a sequential rename would collide) and both DI shapes"
        " exchange their bpmnElement values. No reference names either id. Call_out stays"
        " dangling and is reported as in cn-remap-internal-call-and-dangling."
    )
    return remap_case(
        "cn-remap-swap",
        REMAP_CLAUSE + " (total map built before application)",
        derivation,
        (tree_in, [], _map_diagrams("Task_m")),
        remap_command([("Call_in", "Task_m"), ("Task_m", "Call_in")]),
        (tree_out, [], _map_diagrams("Call_in", "Task_m")),
        _map_rows(Call_in="Task_m", Task_m="Call_in"),
        [_dangling_call_entry(call_out)],
    )


def case_remap_collision() -> dict[str, Json]:
    """A result id equal to a retained id refuses id-collision."""
    env_in = envelope(IDENTITY["cn-n"], _map_tree(), [])
    derivation = (
        "Mapping Task_m to Call_in while Call_in keeps its id would give two elements one"
        " id: the total map must be injective over retained ids, so remap refuses"
        " id-collision before any write."
    )
    return remap_refusal(
        "cn-remap-collision",
        REMAP_CLAUSE,
        derivation,
        env_in,
        remap_command([("Task_m", "Call_in")]),
        "id-collision",
    )


def case_remap_unknown_source() -> dict[str, Json]:
    """A map key naming no element refuses reference-dangling."""
    env_in = envelope(IDENTITY["cn-n"], _map_tree(), [])
    derivation = (
        "The map row sourceId Ghost names no element of the document: reference-dangling"
        " (H C20, py-only code adopted by both runtimes)."
    )
    return remap_refusal(
        "cn-remap-unknown-source",
        REMAP_CLAUSE,
        derivation,
        env_in,
        remap_command([("Ghost", "Ghost_2")]),
        "reference-dangling",
    )


def _attestation(prop: str) -> dict[str, Json]:
    """Return one pinned reference-free attestation for an unclassified member."""
    pin = IDENTITY["cn-n"]["descriptors"][0]  # type: ignore[index]
    return {"property": prop, "referenceFree": True, "descriptor": copy.deepcopy(pin)}


def case_remap_opaque_property() -> dict[str, Json]:
    """An unclassified property may hide references: migration-reference-opaque."""
    env_in = envelope(IDENTITY["cn-n"], _map_tree(opaque=True), [])
    derivation = (
        "Task_m carries the unclassified property x (no descriptor role) and the command"
        " has no pinned reference-free attestation for it: remap cannot prove it holds no"
        " reference and refuses migration-reference-opaque."
    )
    return remap_refusal(
        "cn-remap-opaque-property",
        REMAP_CLAUSE + " (migration-reference-opaque)",
        derivation,
        env_in,
        remap_command([("Process_sub", "Process_child")]),
        "migration-reference-opaque",
    )


def case_remap_opaque_attested() -> dict[str, Json]:
    """A pinned reference-free attestation lets remap keep an opaque member unchanged."""
    tree_in = _map_tree(opaque=True)
    tree_out = copy.deepcopy(tree_in)
    at(tree_out, ptr("rootElements", 1))["id"] = "Process_child"  # type: ignore[index]
    at(tree_out, ptr("rootElements", 0, "flowElements", 0))["calledElement"] = "Process_child"  # type: ignore[index]
    call_out = ptr("rootElements", 0, "flowElements", 1)
    derivation = (
        "Same input as cn-remap-opaque-property, with an explicit attestation {property"
        " bpmn:Task.x, referenceFree true, descriptor = the pinned cn descriptor package}:"
        " the opaque member is attested reference-free, so remap proceeds and never"
        " rewrites it (x keeps the string Process_sub although Process_sub is renamed to"
        " Process_child); calledElement follows, Call_out stays dangling and is reported."
    )
    return remap_case(
        "cn-remap-opaque-attested",
        REMAP_CLAUSE + " (pinned reference-free attestation)",
        derivation,
        (tree_in, [], []),
        remap_command([("Process_sub", "Process_child")], [_attestation("bpmn:Task.x")]),
        (tree_out, [], []),
        _map_rows(Process_sub="Process_child"),
        [_dangling_call_entry(call_out)],
    )


def case_remap_target_grammar() -> dict[str, Json]:
    """A result id outside the authoring grammar refuses profile-schema."""
    env_in = envelope(IDENTITY["cn-n"], _map_tree(), [])
    derivation = (
        "Result ids must satisfy the authoring subset ^[A-Za-z_][A-Za-z0-9_.-]{0,255}$;"
        " '9-bad' starts with a digit, so remap refuses profile-schema (H C20)."
    )
    return remap_refusal(
        "cn-remap-target-grammar",
        REMAP_CLAUSE + "; §3.2 authoring subset",
        derivation,
        env_in,
        remap_command([("Task_m", "9-bad")]),
        "profile-schema",
    )


CHAIN_CASES = [
    case_plan_create_task_neutral,
    case_plan_create_task_grid,
    case_plan_add_note_containment,
    case_plan_create_aid_neutral,
    case_plan_create_aid_grid,
    case_plan_link,
    case_plan_scalar_write_conflict,
    case_plan_append_remove_conflict,
    case_plan_missing_parameter,
    case_plan_unknown_element_parameter,
    case_apply_stale_plan,
    case_plan_ambiguous_binding,
    case_plan_remove_referenced,
    case_n_empty_support_survives,
    case_plan_remove_empty_support,
    case_plan_remove_without_intent,
    case_n_deleted_support_stays_absent,
    case_remap_owner,
    case_remap_gated,
    case_remap_not_approved,
    case_plan_create_process_input,
    case_n_recreate_after_remap,
    case_n_recreate_after_remap_edit,
    case_remap_internal_call_and_dangling,
    case_remap_swap,
    case_remap_collision,
    case_remap_unknown_source,
    case_remap_opaque_property,
    case_remap_opaque_attested,
    case_remap_target_grammar,
]


# ---------------------------------------------------------------------------
# Cases: support binding adapters, compilation and gates
# ---------------------------------------------------------------------------

S_CLAUSE = "DESIGN R3.3 §5.2 support import rules; §13 OPEN-MACHINE; §16 item 6"


def _recovery_envelope() -> dict[str, Json]:
    tree = _support_case(0)["expected"]["tree"]  # type: ignore[index]
    return envelope(IDENTITY["support"], tree, [])


def _propose_case(
    cid: str, provenance: list[str], proposals: list[dict[str, str]], derivation: str
) -> dict[str, Json]:
    inp = {"envelope": _recovery_envelope(), "provenance": provenance}
    return make_case(
        cid,
        S_CLAUSE + " (recovery proposal)",
        derivation,
        "propose_support_bindings",
        "support",
        inp,
        pure_ok({"proposals": sort_bindings(proposals)}),
    )


def case_propose_recovery_with_provenance() -> dict[str, Json]:
    """Exact allocator id + type/parent/fields + provenance: binding proposed."""
    created = _support_case(0)["expected"]["createdIds"]  # type: ignore[index]
    proposals = _support_case(0)["expected"]["bindings"]  # type: ignore[index]
    derivation = (
        "The trusted generated tree of support case 1 lost its bindings. Every role's"
        " allocator id exists with the expected type, parent/property and declared fields,"
        " and the explicit creation provenance lists it, so the read-only adapter proposes"
        " the five original bindings; the envelope is not modified (activation still needs"
        " an explicit recovery transaction, bind_supports)."
    )
    return _propose_case(
        "cn-propose-recovery-with-provenance",
        list(created),
        proposals,
        derivation,  # type: ignore[arg-type]
    )


def case_propose_recovery_without_provenance() -> dict[str, Json]:
    """A hash-shaped id alone never authorizes reuse."""
    derivation = (
        "Same tree without provenance: matching allocator ids alone (hash-shaped ids) do not"
        " authorize reuse, so nothing is proposed."
    )
    return _propose_case("cn-propose-recovery-without-provenance", [], [], derivation)


def case_propose_recovery_partial_provenance() -> dict[str, Json]:
    """Only provenance-listed supports are proposed."""
    collab = sid("Definitions_support", "collaboration", "Process_A")
    derivation = (
        "Provenance lists only the Collaboration: it alone is proposed; the other four roles"
        " keep no proposal (their ids are occupied but unattested)."
    )
    return _propose_case(
        "cn-propose-recovery-partial-provenance",
        [collab],
        [binding("Process_A", "collaboration", collab)],
        derivation,
    )


def case_n_recovery_missing_binding_collides() -> dict[str, Json]:
    """Without bindings, N does not adopt generated-looking supports: id-collision."""
    derivation = (
        "N on the binding-less generated tree: the Collaboration ensure finds no binding and"
        " its allocator id is already occupied, so N refuses id-collision instead of adopting"
        " the element (recovery is an explicit, separate transaction)."
    )
    return normalize_refusal(
        "cn-n-recovery-missing-binding-collides",
        S_CLAUSE + "; §3.2 id-collision",
        derivation,
        "support",
        _recovery_envelope(),
        "id-collision",
        activation="qualification",
    )


def case_propose_black_box_pool() -> dict[str, Json]:
    """A labelled ordinary pool is never proposed."""
    inp = {"envelope": envelope(IDENTITY["cn-n"], _pool_tree(), []), "provenance": []}
    derivation = (
        "Collab_X/Pool_X carry support labels but no allocator ids and no provenance: no"
        " proposal (labels never classify supports)." + CN_N_IDENTITY_NOTE
    )
    return make_case(
        "cn-propose-black-box-pool",
        S_CLAUSE + " (ordinary pool never taken over)",
        derivation,
        "propose_support_bindings",
        "cn-n",
        inp,
        pure_ok({"proposals": []}),
    )


SELECTED = [binding("Process_P", "collaboration", "Collab_X")]


def case_bind_supports_explicit_selection() -> dict[str, Json]:
    """An explicit support selection binds an imported Collaboration."""
    ident = IDENTITY["cn-n"]
    env_in = envelope(ident, _pool_tree(), [])
    env_out = envelope(ident, _pool_tree(), SELECTED)
    base, rev = str(env_in["semanticRevision"]), str(env_out["semanticRevision"])
    expected = ok_result(
        "bindSupports",
        ident,
        base,
        rev,
        success_report("bindSupports", ident, base, rev, []),
        env_out,
    )
    derivation = (
        "The import plan explicitly selects Collab_X as Process_P's collaboration support"
        " (activation qualification). bind_supports validates owner and target existence and"
        " uniqueness and adds the binding; the tree is unchanged and the revision changes"
        " through the bindings."
    )
    inp = {"envelope": env_in, "bindings": SELECTED, "activation": "qualification"}
    return make_case(
        "cn-bind-supports-explicit-selection",
        S_CLAUSE + " (supply/review support bindings)",
        derivation,
        "bind_supports",
        "cn-n",
        inp,
        expected,
    )


def case_n_after_explicit_selection() -> dict[str, Json]:
    """N reuses the selected Collaboration and keeps the ordinary pool."""
    tree_in = _pool_tree()
    tree_out = copy.deepcopy(tree_in)
    participants = at(tree_out, ptr("rootElements", 2, "participants"))
    participants.extend(  # type: ignore[attr-defined]
        [main_participant(POOL_IDS["main"], "Process_P"), band(POOL_IDS["band"])]
    )
    collab = ptr("rootElements", 2)
    entries = [
        create_entry(
            "normalize", "ensure", "ensure-base-supports", tree_out, f"{collab}/participants/1"
        ),
        edit_entry(
            "normalize",
            "assignRef",
            "ensure-base-supports",
            f"{collab}/participants/1",
            POOL_IDS["main"],
            "processRef",
            after="Process_P",
            created=True,
        ),
        create_entry(
            "normalize", "ensure", "ensure-reference-band", tree_out, f"{collab}/participants/2"
        ),
    ]
    bindings_out = [
        *SELECTED,
        binding("Process_P", "main-participant", POOL_IDS["main"]),
        binding("Process_P", "reference-band", POOL_IDS["band"]),
    ]
    derivation = (
        "Input is the cn-bind-supports-explicit-selection output. The bound Collab_X passes"
        " reuse validation (Definitions.rootElements parent, declared name collaboration);"
        " the main Participant and band are created inside it after Pool_X, which stays an"
        " ordinary unbound participant."
    )
    return normalize_case(
        "cn-n-after-explicit-selection",
        S_CLAUSE + "; §7.2 Structure",
        derivation,
        "cn-n",
        (tree_in, SELECTED),
        (tree_out, bindings_out),
        entries,
        [placement("Ref_P", "Process_P", REFERENCE_REGION, [])],
        activation="qualification",
    )


def case_bind_supports_gated() -> dict[str, Json]:
    """Support binding activation refuses profile-open in edit."""
    env_in = envelope(IDENTITY["cn-n"], _pool_tree(), [])
    derivation = (
        "Import support binding is N/import activation gated by OPEN-MACHINE (technical gate"
        " open): the default edit activation refuses profile-open."
    )
    expected = refused_result(
        "bindSupports", "profile-open", env_in["profileIdentity"], str(env_in["semanticRevision"])
    )
    inp = {"envelope": env_in, "bindings": SELECTED, "activation": "edit"}
    return make_case(
        "cn-bind-supports-gated", S_CLAUSE, derivation, "bind_supports", "cn-n", inp, expected
    )


def case_bind_supports_conflict() -> dict[str, Json]:
    """Binding an already bound owner+role refuses support-binding-conflict."""
    env_in = envelope(IDENTITY["cn-n"], _pool_tree(), SELECTED)
    derivation = (
        "The envelope already binds (Process_P, collaboration); supplying it again would"
        " duplicate owner+role, refused support-binding-conflict."
    )
    expected = refused_result(
        "bindSupports",
        "support-binding-conflict",
        env_in["profileIdentity"],
        str(env_in["semanticRevision"]),
    )
    inp = {"envelope": env_in, "bindings": SELECTED, "activation": "qualification"}
    return make_case(
        "cn-bind-supports-conflict",
        S_CLAUSE + "; §5.1 owner+role unique",
        derivation,
        "bind_supports",
        "cn-n",
        inp,
        expected,
    )


def _compile_case(
    cid: str, clause: str, derivation: str, variant: str, expected: Json
) -> dict[str, Json]:
    return make_case(
        cid, clause, derivation, "compile_profile", variant, {"variant": variant}, expected
    )


def case_compile_support_profile() -> dict[str, Json]:
    """The R3.1 support recipe compiles (ensure aliases, writes, authority)."""
    derivation = (
        "Hand review against DESIGN §2.4/§2.4.1 (no compiler output used). Variant = neutral"
        " minus place-task plus the vendored ensure-supports recipe, pins re-pinned to the"
        " support slice (a superset of the neutral slice: Collaboration/Participant/LaneSet/"
        "Lane, Definitions.rootElements admitting Collaboration, Process.laneSets). CR-05: the"
        " five ensure handles are declared before use (main as assignRef target,"
        " collaboration and laneSet as parents). CR-06 write set: the required demands are"
        " {root,/rootElements,create}, {collaboration,/participants,create} (twice),"
        " {self,/laneSets,create}, {laneSet,/lanes,create}, {envelope,/bindings,binding}"
        " (once per ensure) and {main,/processRef,reference}; identical demands coalesce"
        " (§2.4 'Identical writes coalesce'), giving exactly the six declared writes."
        " CR-06 authority: ensure types are the four support types, each parent containment"
        " admits the ensured type, the name fields are declared scalars, and every written"
        " field (ids, names, containments, processRef) lists actor code in the support base."
        " CR-07: ensure allocates ID-bearing types with string ownerId values (id of root or"
        " self). CR-14: ensure and assignRef belong to normalize. The kept neutral recipes"
        " use only types/fields present in both slices. Expected: ok, identity = §5.1 record"
        " with sha256 = H(variant)."
    )
    return _compile_case(
        "cn-compile-support-profile",
        "DESIGN R3.3 §2.4.1 CR-05/CR-06/CR-07 for ensure; §7.3 (fixture compiles)",
        derivation,
        "support",
        {"status": "ok", "identity": IDENTITY["support"]},
    )


def case_compile_ensure_non_support_type() -> dict[str, Json]:
    """ensure of a non-support native type refuses profile-producer."""
    derivation = (
        "Hand review: the variant turns the lane ensure into an ensure of bpmn:Task under"
        " self.flowElements and replaces the declared {laneSet,/lanes,create} write by"
        " {self,/flowElements,create}, so the declared and required write sets still agree"
        " (no profile-write-set), the type is known and Process.flowElements admits Task (no"
        " profile-type), and the four earlier steps are unchanged. DESIGN §2.4: 'ensure is"
        " restricted to declared structural support roles and native"
        " Collaboration/Participant/LaneSet/Lane'; §2.4.1 action/write table: ensure needs"
        " 'declared structural type/role and ratified support authority', an authority"
        " condition of CR-06 whose authority code is profile-producer (the DESIGN fixture"
        " checker raises profile-producer for a non-support ensure). Expected: refused"
        " profile-producer."
    )
    return _compile_case(
        "cn-compile-ensure-non-support-type",
        "DESIGN R3.3 §2.4 ensure restriction; §2.4.1 CR-06",
        derivation,
        "support-task-ensure",
        {"status": "refused", "code": "profile-producer"},
    )


def case_compile_port_without_authority() -> dict[str, Json]:
    """Port creation without explicit code authority refuses profile-producer."""
    derivation = (
        "Hand review: the delta is valid (DataInputAssociation.targetRef exists and lists"
        " code in the cn base; DESIGN §2.4.1 'each producerDelta replaces its named from actor"
        " with to'), so the effective producers become {dropped, editor, import}."
        " complete-input-port is a complete recipe (actor code) whose assignRef target self"
        " is a generic native binding (its select predicate is an all(...), not a bare"
        " typeIs): 'Generic native bindings conservatively check every admitted target type"
        " supporting the field', i.e. SequenceFlow, Association, DataInputAssociation and"
        " DataOutputAssociation targetRef; DataInputAssociation lacks code, and CR-06"
        " 'rejects a phase actor absent from the resulting field producer set'. No earlier"
        " recipe writes a DataInputAssociation field (link writes a typed Association"
        " targetRef with actor editor). Expected: refused profile-producer."
    )
    return _compile_case(
        "cn-compile-port-without-authority",
        C_CLAUSE_PORTS + "; §2.4.1 CR-06",
        derivation,
        "cn-c-noauth",
        {"status": "refused", "code": "profile-producer"},
    )


def case_compile_ensure_missing_binding_write() -> dict[str, Json]:
    """An ensure recipe must declare its envelope binding write."""
    derivation = (
        "Hand review: every ensure demands {envelope,/bindings,binding} (DESIGN §2.4.1"
        " action/write table: 'parent/property create and envelope /bindings binding'). The"
        " variant removes that declared write from ensure-supports; the per-step type,"
        " containment and producer checks pass exactly as for the support variant, and the"
        " recipe-level comparison finds a required write missing from the declared set"
        " (CR-06 'Every action maps to declared writes'). Expected: refused"
        " profile-write-set."
    )
    return _compile_case(
        "cn-compile-ensure-missing-binding-write",
        "DESIGN R3.3 §2.4.1 CR-06 write set; action/write matrix (ensure)",
        derivation,
        "support-no-binding-write",
        {"status": "refused", "code": "profile-write-set"},
    )


def case_compile_create_identity_mismatch() -> dict[str, Json]:
    """Containment identity on an ID-bearing type refuses profile-create-identity."""
    derivation = (
        "Hand review: create-task's create step is rewritten with identity containment and"
        " no ownerId/slot/key (schema-valid: containment forbids the allocator fields). The"
        " type bpmn:Task is known and ID-bearing (id true in the neutral descriptors, Task.id"
        " admitted by the base); DESIGN §2.4 'identity:containment ... the compiler must prove"
        " that the effective base excludes id for this type' and CR-07 'allocated/containment"
        " agree with effective id admission' fail; the declared write {owner,/flowElements,"
        "create} still matches. Expected: refused profile-create-identity."
    )
    return _compile_case(
        "cn-compile-create-identity-mismatch",
        "DESIGN R3.3 §2.4 create identity; §2.4.1 CR-07",
        derivation,
        "neutral-containment-task",
        {"status": "refused", "code": "profile-create-identity"},
    )


def case_compile_variants() -> dict[str, Json]:
    """Every success-path variant compiles to its listed identity."""
    names = [
        "neutral",
        "grid",
        "support",
        "support-abort",
        "grid-extraction",
        "cn-c",
        "cn-c-unfixed",
        "cn-n",
        "cn-n-conflict",
        "cn-n-relocate",
        "cn-n-unfixed",
        "cn-n-ensure-conflict",
        "support-cmd",
        "cn-c-second-pass",
        "cn-n-second-pass",
    ]
    expected = [{"variant": n, "status": "ok", "identity": IDENTITY[n]} for n in names]
    derivation = (
        "Written CR-01..CR-14 review of every success-path variant (no compiler output"
        " used; spec §11.2): neutral and grid are the vendored profiles; support as in"
        " cn-compile-support-profile, support-abort adds a refuse step (no write);"
        " grid-extraction replaces import by ai on three base fields (valid deltas, no"
        " recipe writes them); the cn variants add recipes whose every action maps to its"
        " declared writes (identical demands coalesce), whose written fields list the phase"
        " actor (code for complete/normalize, editor for commands) in the cn base, whose"
        " created types are admitted by their containment and whose ID modes agree with"
        " id admission; count uses select and reachable from/to as pinned in the schema;"
        " inverseReference properties belong to the referencing type. The compiled"
        " identity is the §5.1 record whose sha256 is H(variant profile)."
    )
    return make_case(
        "cn-compile-variants",
        "DESIGN R3.3 §2.4.1 compiler rejection mapping; §3.1 profile digest; §5.1 identity",
        derivation,
        "compile_profile",
        None,
        {"variants": names},
        expected,
    )


GATES: dict[str, dict[str, str]] = {
    "OPEN-EXTERNAL": {
        "owner": "ratified",
        "ownerRecord": "DESIGN R3.3 §16 item 2",
        "technical": "open",
        "guards": "normalize: an effective bpmn:Lane flowNodeRef membership change",
        "edit": "profile-open",
        "qualification": "proceeds",
    },
    "OPEN-ID": {
        "owner": "ratified",
        "ownerRecord": "DESIGN R3.3 §16 item 1",
        "technical": "open",
        "guards": "remap_ids",
        "edit": "profile-open",
        "qualification": "proceeds",
    },
    "OPEN-IO": {
        "owner": "ratified",
        "ownerRecord": "DESIGN R3.3 §16 item 8",
        "technical": "open",
        "guards": "complete: filling an absent bpmn:DataOutputAssociation sourceRef",
        "edit": "profile-open",
        "qualification": "proceeds",
    },
    "OPEN-MACHINE": {
        "owner": "ratified",
        "ownerRecord": "DESIGN R3.3 §16 item 6",
        "technical": "open",
        "guards": "bind_supports",
        "edit": "profile-open",
        "qualification": "proceeds",
    },
    "OPEN-RESERVED-N": {
        "owner": "ratified",
        "ownerRecord": "DESIGN R3.3 §16 item 11",
        "technical": "open",
        "guards": "normalize: an ensure that would create a support object",
        "edit": "profile-open",
        "qualification": "proceeds",
    },
    "OPEN-SHARING": {
        "owner": "ratified",
        "ownerRecord": "DESIGN R3.3 §16 item 4",
        "technical": "open",
        "guards": "normalize: removal of an existing bpmn:Lane flowNodeRef membership",
        "edit": "profile-open",
        "qualification": "responsibility-preservation-required",
    },
}


def case_gates_table() -> dict[str, Json]:
    """The read-only lot-3 gate table."""
    derivation = (
        "§16 ratified the owner part of items 1, 2, 4, 6, 8 and 11 on 2026-10-14; every"
        " technical gate (conductor + both libraries) is still open, so each guarded mutation"
        " refuses profile-open in edit activation and proceeds only for neutral"
        " qualification, except membership removal whose responsibility representation is"
        " unresolved (§4.4): responsibility-preservation-required."
    )
    return make_case(
        "cn-gates-table",
        "DESIGN R3.3 §13 OPEN register; §16 owner decisions; §7.2",
        derivation,
        "gates",
        None,
        {},
        GATES,
    )


ADAPTER_CASES = [
    case_propose_recovery_with_provenance,
    case_propose_recovery_without_provenance,
    case_propose_recovery_partial_provenance,
    case_n_recovery_missing_binding_collides,
    case_propose_black_box_pool,
    case_bind_supports_explicit_selection,
    case_n_after_explicit_selection,
    case_bind_supports_gated,
    case_bind_supports_conflict,
    case_compile_support_profile,
    case_compile_ensure_non_support_type,
    case_compile_port_without_authority,
    case_compile_ensure_missing_binding_write,
    case_compile_create_identity_mismatch,
    case_compile_variants,
    case_gates_table,
]

ALL_CASES = C_CASES + N_SUPPORT_CASES + N_CN_CASES + CHAIN_CASES + PLAN_MATRIX_CASES + ADAPTER_CASES


# ---------------------------------------------------------------------------
# profile-parity-corpus/1 projection (H A1-A5, A8; spec §9.1)
# ---------------------------------------------------------------------------

#: Harness cases that are runtime-specific, never parity cases (H section 3.1).
RUNTIME_SPECIFIC = {"cn-gates-table", "cn-c-uncompiled-context"}
PARITY_REL = "tests/profile_cn/expected/parity/"
VENDORED_PROFILES = {
    "neutral": MECH_REL + "neutral-profile.json",
    "grid": MECH_REL + "neutral-grid-profile.json",
}
#: A4 shared camelCase operation names.
CORPUS_OPERATIONS = {
    "complete": "complete",
    "normalize": "normalize",
    "plan_recipe+apply_plan": "planRecipe",
    "apply_plan": "applyPlan",
    "compile_profile": "compileProfile",
    "propose_support_bindings": "proposeSupportBindings",
    "bind_supports": "bindSupports",
    "remap_ids": "remapIds",
    "sort_placements": "sortPlacements",
}
CORPUS_COMPARATORS = [
    {
        "id": "profile-c14n/2",
        "kind": "mechanism",
        "note": "canonical byte equality of every expected artifact, DESIGN section 3.1",
    },
    {
        "id": "fixed-point/lot3",
        "kind": "mechanism",
        "note": (
            "rerun the operation on the expected payload envelope (complete: mode retained;"
            " same activation and placement intent): status ok, identical envelope and"
            " placements, zero report entries, baseRevision = revision = the first revision"
        ),
    },
    {
        "id": "plan-apply/lot3",
        "kind": "format",
        "note": (
            "planRecipe cases with an apply artifact also call applyPlan(plan.payload,"
            " envelope.tree, envelope) and compare that PureResult"
        ),
    },
]


def _profile_bytes(name: str) -> bytes:
    """Return the committed bytes of one variant profile (vendored or composed)."""
    if name in VENDORED_PROFILES:
        return (ROOT / VENDORED_PROFILES[name]).read_bytes()
    return pretty_bytes(PROFILES[name])


def _profile_path(name: str) -> str:
    return VENDORED_PROFILES.get(name, PARITY_REL + "profiles/" + name + ".json")


def _profile_ref(name: str) -> dict[str, Json]:
    return {"path": _profile_path(name), "sha256": raw_digest(_profile_bytes(name))}


def _file_ref(rel: str) -> dict[str, Json]:
    return {"path": rel, "sha256": raw_digest((ROOT / rel).read_bytes())}


def _artifact(role: str, value: Json) -> dict[str, Json]:
    return {"role": role, "json": copy.deepcopy(value)}


def _status(value: Json) -> str:
    if value["status"] == "ok":  # type: ignore[index]
        return "ok"
    return "refused:" + str(value["code"])  # type: ignore[index]


def _activation(inp: dict[str, Json]) -> list[dict[str, Json]]:
    """H H1: an activation artifact only when it is qualification (absent = edit)."""
    if inp.get("activation") == "qualification":
        return [_artifact("activation", "qualification")]
    return []


def _recipe_phase(record: dict[str, Json]) -> Json:
    """Return the phase of the recipe a plan case names (or passes verbatim)."""
    recipe_ref = record["input"]["recipe"]  # type: ignore[index]
    if isinstance(recipe_ref, dict):
        return recipe_ref["phase"]
    recipes = PROFILES[str(record["profile"])]["recipes"]
    return next(r["phase"] for r in recipes if r["id"] == recipe_ref)  # type: ignore[attr-defined,index]


def corpus_record(record: dict[str, Json]) -> dict[str, Json]:  # noqa: C901, PLR0912, PLR0915
    """Project one harness case onto the closed profile-parity-corpus/1 record.

    Values are copied verbatim from the harness record (no new value).
    """
    operation = str(record["operation"])
    inp: dict[str, Json] = record["input"]  # type: ignore[assignment]
    exp: dict[str, Json] = record["expected"]  # type: ignore[assignment]
    profile = record["profile"]
    inputs: list[dict[str, Json]] = []
    expected: list[dict[str, Json]] = []
    command: dict[str, Json] | None = None
    comparators = ["profile-c14n/2"]
    phase: Json = None
    status = "ok"
    if operation in {"complete", "normalize"}:
        phase = operation
        inputs.append(_artifact("envelope", inp["envelope"]))
        if operation == "complete":
            inputs.append(_artifact("mode", inp["mode"]))
        elif inp.get("placementIntent") is not None:
            inputs.append(_artifact("placementIntent", inp["placementIntent"]))
        inputs += _activation(inp)
        expected.append(_artifact("result", exp))
        status = _status(exp)
        if record.get("fixedPoint"):
            comparators.append("fixed-point/lot3")
    elif operation == "plan_recipe+apply_plan":
        phase = _recipe_phase(record)
        inputs += [
            _artifact("envelope", inp["envelope"]),
            _artifact("recipe", inp["recipe"]),
            _artifact("params", inp["params"]),
            _artifact("authority", inp["authority"]),
        ]
        expected.append(_artifact("plan", exp["plan"]))
        status = _status(exp["plan"])
        if "apply" in exp:
            expected.append(_artifact("apply", exp["apply"]))
            status = _status(exp["apply"])
            comparators.append("plan-apply/lot3")
    elif operation == "apply_plan":
        inputs += [_artifact("plan", inp["plan"]), _artifact("envelope", inp["envelope"])]
        if "stagedTree" in inp:
            inputs.append(_artifact("stagedTree", inp["stagedTree"]))
        expected.append(_artifact("apply", exp["apply"]))
        status = _status(exp["apply"])
    elif operation == "compile_profile":
        names = inp.get("variants")
        if names is None:
            expected.append(_artifact("compile", exp))
            status = _status(exp)
        else:
            inputs += [{"role": "profile", **_profile_ref(str(n))} for n in names]  # type: ignore[union-attr]
            expected.append(_artifact("identities", exp))
    elif operation == "propose_support_bindings":
        inputs += [
            _artifact("envelope", inp["envelope"]),
            _artifact("provenance", inp["provenance"]),
        ]
        expected.append(_artifact("result", exp))
        status = _status(exp)
    elif operation == "bind_supports":
        inputs += [_artifact("envelope", inp["envelope"]), _artifact("bindings", inp["bindings"])]
        inputs += _activation(inp)
        expected.append(_artifact("result", exp))
        status = _status(exp)
    elif operation == "remap_ids":
        inputs += [
            _artifact("envelope", inp["envelope"]),
            _artifact("importedDi", inp["importedDi"]),
        ]
        inputs += _activation(inp)
        command = _artifact("migration", inp["command"])
        expected.append(_artifact("result", exp))
        status = _status(exp)
    elif operation == "sort_placements":
        inputs.append(_artifact("placements", inp["placements"]))
        expected.append(_artifact("placements", exp))
    else:
        message = f"no corpus projection for {operation}"
        raise ValueError(message)
    corpus: dict[str, Json] = {
        "caseId": record["case"],
        "operation": CORPUS_OPERATIONS[operation],
        "phase": phase,
        "profileArtifact": _profile_ref(str(profile)) if profile is not None else None,
        "inputArtifacts": inputs,
        "expectedArtifacts": expected,
        "expectedStatus": status,
        "comparatorIds": comparators,
    }
    if command is not None:
        corpus["commandArtifact"] = command
    return corpus


def corpus_files(records: list[dict[str, Json]]) -> dict[str, bytes]:
    """Return the parity/ files (relative to the expected directory)."""
    files: dict[str, bytes] = {}
    used: set[str] = set()
    for record in records:
        if record["case"] in RUNTIME_SPECIFIC:
            continue
        corpus = corpus_record(record)
        files["parity/cases/" + str(record["case"]) + ".json"] = jcs(corpus).encode("utf-8")
        if record["profile"] is not None:
            used.add(str(record["profile"]))
        used.update(str(name) for name in record["input"].get("variants", []))  # type: ignore[union-attr]
    for name in sorted(used):
        if name not in VENDORED_PROFILES:
            files["parity/profiles/" + name + ".json"] = _profile_bytes(name)
    profiles = []
    referenced: dict[str, str] = {}
    for name in sorted(used):
        descriptors, base = variant_files(name)
        row = {
            "variant": name,
            **_profile_ref(name),
            "descriptorBytes": _file_ref(descriptors),
            "baseBytes": _file_ref(base),
        }
        profiles.append(row)
        referenced[_profile_path(name)] = str(row["sha256"])
        referenced[descriptors] = str(row["descriptorBytes"]["sha256"])  # type: ignore[index]
        referenced[base] = str(row["baseBytes"]["sha256"])  # type: ignore[index]
    for name, data in files.items():
        if name.startswith("parity/cases/"):
            referenced[PARITY_REL + name.removeprefix("parity/")] = raw_digest(data)
    manifest = {
        "format": "profile-parity-corpus/1",
        "scope": "lot-3 C/N parity projection of the bpmn-io seal (SPEC_PROFILE_CN_PY.md §9.1)",
        "pathBase": ".",
        "author": AUTHOR,
        "comparators": CORPUS_COMPARATORS,
        "profiles": profiles,
        "files": {key: referenced[key] for key in sorted(referenced, key=utf16)},
        "notes": [
            (
                "pathBase is the repository root; every path in this manifest and in the"
                " cases is relative to it."
            ),
            (
                "Each case is the corpus/1 projection of tests/profile_cn/expected/<caseId>.json"
                " with identical values; the harness file keeps the derivation."
            ),
            (
                "Case files are profile-c14n/2 bytes (no trailing newline); profile files are"
                " the composed variant JSON (2-space indent plus LF); sha256 values are raw"
                " file digests (H A6), identity sha256 values are H(profile)."
            ),
            (
                "Runtime-specific harness cases (cn-gates-table, cn-c-uncompiled-context)"
                " have no projection."
            ),
        ],
    }
    files["parity/manifest.json"] = pretty_bytes(manifest)
    return files


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


def _manifest(files: dict[str, bytes]) -> bytes:
    lines = [f"{raw_digest(data)}  {name}\n" for name, data in sorted(files.items())]
    return "".join(lines).encode("utf-8")


def build() -> dict[str, bytes]:
    """Return every sealed file (relative to the expected directory) and its bytes."""
    files: dict[str, bytes] = {}
    for name, data in ARTIFACTS.items():
        files["artifacts/" + name] = data
    files["artifacts/profile-variants.json"] = pretty_bytes(variants_document())
    seen: set[str] = set()
    records: list[dict[str, Json]] = []
    for factory in ALL_CASES:
        record = factory()
        cid = str(record["case"])
        if cid in seen:
            message = f"duplicate case id {cid}"
            raise ValueError(message)
        seen.add(cid)
        records.append(record)
        files[cid + ".json"] = pretty_bytes(record)
    files.update(corpus_files(records))
    files["derive_helper.py"] = Path(__file__).read_bytes()
    return files


def main() -> int:
    """Rewrite the sealed files and the manifest from the hand-authored data."""
    files = build()
    for name, data in files.items():
        if name == "derive_helper.py":
            continue
        target = OUT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (OUT / "MANIFEST.sha256").write_bytes(_manifest(files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
