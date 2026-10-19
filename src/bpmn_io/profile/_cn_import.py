"""Lot-3 import projection (DESIGN §5.3, H B15).

``import_projection`` projects one source document onto the effective base:
every element whose ``$type`` the base does not admit is dropped with its
subtree, relations with a dropped endpoint cascade, dropped ids are removed
from retained reference arrays, and the retained graph index decides the
rest. The projection commits nothing: revision equals baseRevision.
"""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Any

from bpmn_io.profile._c14n import digest
from bpmn_io.profile._cn_context import (
    build_tree_index,
    check_compiled,
    check_graph,
    refuse_result,
)
from bpmn_io.profile._cn_plan import _RefusalError, _refuse
from bpmn_io.profile._cn_remap import _reference_members, _walk_elements
from bpmn_io.profile._results import (
    Coordinate,
    Report,
    ReportEntry,
    ResultRefused,
    ResultSuccess,
    result_success,
)

if TYPE_CHECKING:
    from bpmn_io.profile._compiler import CompiledProfile


def _parse_source(source: object, source_format: str) -> dict[str, Any]:
    """Parse one import source to a JSON tree (raises the refusal code)."""
    if source_format == "bpmn-xml":
        # No XML importer in this lot: every XML source is unloadable.
        _refuse("document-not-loaded")
    if isinstance(source, dict):
        return copy.deepcopy(source)
    if isinstance(source, (bytes, bytearray)):
        try:
            text = bytes(source).decode("utf-8")
        except (UnicodeDecodeError, ValueError):
            _refuse("document-not-loaded")
        try:
            parsed = json.loads(text)
        except ValueError:
            _refuse("document-not-loaded")
        if not isinstance(parsed, dict):
            _refuse("document-not-loaded")
        return parsed
    error = _RefusalError("operation-error")
    raise error


def _check_duplicate_ids(parsed: dict[str, Any]) -> None:
    """Refuse repeated element ids (``id-collision``)."""
    seen: set[str] = set()
    for element in _walk_elements(parsed):
        element_id = element.get("id")
        if not isinstance(element_id, str):
            continue
        if element_id in seen:
            _refuse("id-collision")
        seen.add(element_id)


def _has_doomed_ancestor(
    parents: dict[int, dict[str, Any]], doomed: set[int], element: dict[str, Any]
) -> bool:
    """Return whether one element sits inside a dropped subtree."""
    node = parents.get(id(element))
    seen: set[int] = set()
    while isinstance(node, dict) and id(node) not in seen:
        if id(node) in doomed:
            return True
        seen.add(id(node))
        node = parents.get(id(node))
    return False


def _drop_subtree(tree: dict[str, Any], doomed: set[int]) -> None:
    """Detach every doomed node from its container in place."""
    stack: list[object] = [tree]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key in list(current.keys()):
                child = current[key]
                if isinstance(child, dict):
                    if id(child) in doomed:
                        del current[key]
                    else:
                        stack.append(child)
                elif isinstance(child, list):
                    kept = [
                        entry
                        for entry in child
                        if not (isinstance(entry, dict) and id(entry) in doomed)
                    ]
                    if len(kept) != len(child):
                        current[key] = kept
                    stack.extend(entry for entry in kept if isinstance(entry, dict))
        elif isinstance(current, list):
            stack.extend(entry for entry in current if isinstance(entry, dict))


#: Data association types (endpoint arrays clean, emptied ones drop).
_DATA_ASSOCIATIONS = frozenset({"bpmn:DataInputAssociation", "bpmn:DataOutputAssociation"})


def _cascade(parsed: dict[str, Any], doomed: set[int], dropped_ids: set[str]) -> None:
    """Cascade drops through relations with a dropped scalar endpoint."""
    changed = True
    while changed:
        changed = False
        for element in _walk_elements(parsed):
            if id(element) in doomed:
                continue
            if "sourceRef" not in element or "targetRef" not in element:
                continue
            for key in ("sourceRef", "targetRef"):
                value = element.get(key)
                if isinstance(value, str) and value in dropped_ids:
                    doomed.add(id(element))
                    element_id = element.get("id")
                    if isinstance(element_id, str):
                        dropped_ids.add(element_id)
                    changed = True
                    break


def _drop_emptied(parsed: dict[str, Any], doomed: set[int]) -> None:
    """Drop data associations left with an empty endpoint array."""
    for element in _walk_elements(parsed):
        if id(element) in doomed:
            continue
        if element.get("$type") not in _DATA_ASSOCIATIONS:
            continue
        for key in ("sourceRef", "targetRef"):
            value = element.get(key)
            if isinstance(value, list) and not value:
                doomed.add(id(element))
                break


def _resolve_pointer(tree: dict[str, Any], pointer: str) -> object:
    """Resolve one RFC 6901 pointer against a pristine tree."""
    current: object = tree
    for raw in pointer.split("/")[1:]:
        segment = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            current = current.get(segment, None)
        elif isinstance(current, list):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return current


def _clean_arrays(
    parsed: dict[str, Any],
    types: dict[str, dict[str, Any]],
    ref_fields: frozenset[tuple[str, str]],
    dropped_ids: set[str],
) -> None:
    """Remove dropped ids from retained reference arrays (emptied stay ``[]``)."""
    if not dropped_ids:
        return
    for element in _walk_elements(parsed):
        type_name = element.get("$type")
        if not isinstance(type_name, str):
            continue
        references = _reference_members(types, type_name, ref_fields)
        for member in references:
            value = element.get(member)
            if isinstance(value, list):
                element[member] = [
                    item for item in value if not (isinstance(item, str) and item in dropped_ids)
                ]


def import_projection(
    compiled: CompiledProfile,
    source: object,
    *,
    source_format: str = "native-json",
) -> ResultSuccess | ResultRefused:
    """Project one source document onto the effective base (§6.8)."""
    if source_format not in ("native-json", "bpmn-xml"):
        return refuse_result("importProjection", "operation-error", {})
    if not check_compiled(compiled):
        return refuse_result("importProjection", "descriptor-mismatch", {})
    try:
        parsed = _parse_source(source, source_format)
    except _RefusalError as exc:
        return refuse_result("importProjection", exc.code, {})
    source_digest = digest(parsed)
    base_revision = digest(
        {
            "domain": "profile-import/1",
            "format": source_format,
            "sourceDigest": source_digest,
        }
    )
    try:
        _check_duplicate_ids(parsed)
        return _project_result(compiled, parsed, base_revision)
    except _RefusalError as exc:
        return refuse_result("importProjection", exc.code, {})


def _project_result(
    compiled: CompiledProfile, parsed: dict[str, Any], base_revision: str
) -> ResultSuccess | ResultRefused:
    """Project, index and assemble one import result (raises the refusal code)."""
    types = compiled.types or {}
    admitted = set(compiled.base_types) if compiled.base_types is not None else set()
    if not admitted:
        _refuse("descriptor-mismatch")
    doomed: set[int] = set()
    dropped_ids: set[str] = set()
    for element in _walk_elements(parsed):
        type_name = element.get("$type")
        if isinstance(type_name, str) and type_name not in admitted:
            doomed.add(id(element))
            element_id = element.get("id")
            if isinstance(element_id, str):
                dropped_ids.add(element_id)
    _cascade(parsed, doomed, dropped_ids)
    pristine = copy.deepcopy(parsed)
    _clean_arrays(parsed, types, compiled.ref_fields or frozenset(), dropped_ids)
    _drop_emptied(parsed, doomed)
    index = build_tree_index(parsed)
    entries: list[ReportEntry] = []
    for element in index.elements:
        if id(element) not in doomed:
            continue
        if _has_doomed_ancestor(index.parents, doomed, element):
            continue
        pointer = index.pointers.get(id(element), "")
        before = _resolve_pointer(pristine, pointer)
        target = element.get("id")
        entries.append(
            ReportEntry(
                code="import-loss/unsupported-feature",
                severity="warn",
                classification="loss",
                stage="import",
                rule_id="adapter",
                message_key="import.loss.unsupported-feature",
                disposition="dropped",
                source=Coordinate(
                    domain="tree",
                    pointer=pointer,
                    target_id=target if isinstance(target, str) else None,
                    provenance="exact",
                ),
                result=Coordinate(
                    domain="none",
                    pointer=None,
                    target_id=None,
                    provenance="unavailable",
                ),
                before_present=True,
                after_present=False,
                before=before,
                loss_class="unsupported-feature",
            )
        )
    _drop_subtree(parsed, doomed)
    retained = build_tree_index(parsed)
    failed = check_graph(retained, types, compiled.ref_fields or frozenset())
    if failed is not None:
        _refuse(failed)
    identity = copy.deepcopy(compiled.identity)
    report = Report(
        operation="importProjection",
        target_identity=identity,
        input_revision=base_revision,
        output_revision=base_revision,
        entries=tuple(entries),
    )
    return result_success(
        operation="importProjection",
        profile_identity=copy.deepcopy(compiled.identity),
        base_revision=base_revision,
        revision=base_revision,
        report=report,
        payload={"tree": parsed},
    )
