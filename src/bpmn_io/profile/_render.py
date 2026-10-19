"""Theme resolution to RenderData/1 (DESIGN R3.3 §5, §9).

Recognition runs per ID-bearing element over the native tree; token
precedence merges occurrence, semantic, DI, binding and theme levels;
coverage walks the native tree in pre-order. Freshness binds through the
§9.2 digests; ``verify_render_data`` recomputes a stored binding.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from typing import Any

from bpmn_io.profile._c14n import digest, digest_bytes
from bpmn_io.profile._compiler import RegistrySet
from bpmn_io.profile._layout import (
    _begin_operation,
    _matched_bindings_for_theme,
    _notion_glyph_id,
    _notion_label_asts,
    _resolve_operation_theme,
    check_layout_record,
    evaluate_label_value,
    index_tree,
    matched_notions,
)
from bpmn_io.profile._render_digest import (
    descriptor_digest,
    metrics_digest,
    payload_digest,
    semantic_revision,
    theme_digest,
)
from bpmn_io.profile._render_tokens import validate_bags
from bpmn_io.profile._results import (
    ReportEntry,
    ResultRefused,
    ResultSuccess,
    make_coordinate,
    refused_result,
    report_with_header,
    sort_report_entries,
)
from bpmn_io.profile._themes import GENERIC_REGION_PATTERN, theme_chain

__all__ = ["resolve_theme"]

Json = Any

_MAX_TRAVERSAL_NODES = 4000000


def _escape_segment(segment: str) -> str:
    """Escape one RFC 6901 reference token."""
    return segment.replace("~", "~0").replace("/", "~1")


def native_preorder(tree: dict[str, Json]) -> list[tuple[str, dict[str, Json], str]]:
    """Walk ID-bearing elements in native pre-order with tree pointers."""
    found: list[tuple[str, dict[str, Json], str]] = []
    stack: list[tuple[Json, str]] = [(tree, "")]
    seen = 0
    while stack:
        node, pointer = stack.pop()
        seen += 1
        if seen > _MAX_TRAVERSAL_NODES:
            break
        if not isinstance(node, dict):
            continue
        type_name = node.get("$type")
        element_id = node.get("id")
        if isinstance(type_name, str) and isinstance(element_id, str) and element_id:
            found.append((element_id, node, pointer or ""))
        children: list[tuple[bytes, str, Json]] = []
        for key, value in node.items():
            if isinstance(value, dict) and isinstance(value.get("$type"), str):
                children.append((key.encode("utf-16-be"), key, value))
            elif isinstance(value, list) and all(
                isinstance(entry, dict) and isinstance(entry.get("$type"), str) for entry in value
            ):
                for index, entry in enumerate(value):
                    children.append((key.encode("utf-16-be"), f"{key}/{index}", entry))
        children.sort(key=lambda entry: entry[0])
        for _, key, child in reversed(children):
            segments = [_escape_segment(part) for part in key.split("/")]
            stack.append((child, pointer + "/" + "/".join(segments)))
    return found


def _is_region_token(name: str) -> bool:
    """Return whether one token name is a region geometry token."""
    try:
        return re.fullmatch(GENERIC_REGION_PATTERN, name) is not None
    except re.error:
        return name.startswith("region.")


@dataclass(frozen=True)
class _TokenLevels:
    """Occurrence token levels in increasing precedence order."""

    occurrence: list[dict[str, Json]]
    semantic: list[dict[str, Json]]
    native: list[dict[str, Json]]
    bioc: list[dict[str, Json]]


def _resolve_style(
    chain: list[dict[str, Json]],
    binding_tokens: dict[str, Json],
    levels: _TokenLevels,
) -> list[dict[str, Json]]:
    """Merge one occurrence style by precedence (region tokens excluded)."""
    merged: dict[str, Json] = {}
    for theme in reversed(chain):
        tokens = theme.get("tokens")
        if not isinstance(tokens, list):
            continue
        for entry in tokens:
            if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
                continue
            if entry.get("name") not in merged:
                merged[str(entry.get("name"))] = entry.get("value")
    merged.update(binding_tokens)
    for level in (levels.bioc, levels.native, levels.semantic, levels.occurrence):
        for entry in level:
            merged[str(entry.get("name"))] = entry.get("value")
    return [
        {"name": name, "value": merged[name]}
        for name in sorted(merged.keys(), key=lambda text: text.encode("utf-16-be"))
        if not _is_region_token(name)
    ]


def _binding_token_merge(
    matched: list[dict[str, Json]], chain: list[dict[str, Json]]
) -> tuple[dict[str, Json] | None, str | None]:
    """Merge matched binding tokens (conflict code or None for no binding)."""
    merged: dict[str, Json] = {}
    contributed = False
    for notion in matched:
        bindings = notion.get("renderBindings", [])
        binding = _matched_bindings_for_theme(bindings if isinstance(bindings, list) else [], chain)
        if binding is None:
            continue
        contributed = True
        for entry in binding.get("tokens", []):
            if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
                continue
            name = str(entry.get("name"))
            if name in merged and merged[name] != entry.get("value"):
                return None, "render-style-conflict"
            merged[name] = entry.get("value")
    return (merged, None) if contributed else (None, None)


def _lookup_tokens(records: list[Json], page_id: str, key: str) -> list[dict[str, Json]]:
    """Find occurrence-targeted tokens for one page and key."""
    for record in records:
        if (
            isinstance(record, dict)
            and record.get("pageId") == page_id
            and record.get("occurrenceKey") == key
        ):
            tokens = record.get("tokens")
            if isinstance(tokens, list):
                return [entry for entry in tokens if isinstance(entry, dict)]
    return []


def _lookup_semantic(records: list[Json], semantic_id: str) -> list[dict[str, Json]]:
    """Find semantic-targeted tokens for one semantic id."""
    for record in records:
        if isinstance(record, dict) and record.get("semanticId") == semantic_id:
            tokens = record.get("tokens")
            if isinstance(tokens, list):
                return [entry for entry in tokens if isinstance(entry, dict)]
    return []


def _declaration_for(
    theme: dict[str, Json], occurrence_key: str, role: str, page_id: str, bearing: set[str]
) -> dict[str, Json] | None:
    """Match one key-less occurrence to its synthetic declaration.

    The key is the JCS triple ``[declaration id, owner id, pageId]``; the
    declaration id names a theme synthetic with the record role, the page
    matches, and the owner is an ID-bearing element of the tree.
    """
    try:
        triple = json.loads(occurrence_key)
    except ValueError:
        return None
    if not isinstance(triple, list) or len(triple) != 3:
        return None
    declaration_id, owner_id, key_page = triple
    if key_page != page_id or not isinstance(owner_id, str) or owner_id not in bearing:
        return None
    for declaration in theme.get("syntheticOccurrences", []):
        if not isinstance(declaration, dict):
            continue
        if declaration.get("id") == declaration_id and declaration.get("role") == role:
            return declaration
    return None


def _select_operation_theme(
    compiled: object,
    theme_id: str,
    echo_identity: dict[str, Json] | None,
    echo_revision: str | None,
) -> tuple[dict[str, Json], str, list[dict[str, Json]]] | ResultRefused:
    """Resolve one operation theme (selection triple or refusal)."""
    theme, resolved_id, chain, theme_refused = _resolve_operation_theme(
        "resolveTheme", compiled, theme_id, echo_identity, echo_revision
    )
    if theme_refused is not None:
        return theme_refused
    if theme is None or resolved_id is None or chain is None:
        return refused_result("resolveTheme", "render-stale", echo_identity, echo_revision)
    return theme, resolved_id, chain


def _normalize_inputs(
    compiled: object,
    wire: dict[str, Json],
    layout: object,
    overrides: object,
    di_styles: object,
) -> tuple[dict[str, Json] | None, dict[str, Json] | None, str | None]:
    """Normalize bags and check targets (overrides, styles, code)."""
    registry = RegistrySet(
        capabilities=(),
        signatures={},
        render_tokens=dict(getattr(compiled, "render_registry", {})),
    )
    normalized_overrides, normalized_styles, bags_code = validate_bags(
        copy.deepcopy(overrides), copy.deepcopy(di_styles), registry, check_signatures=True
    )
    if bags_code is not None:
        return None, None, bags_code
    if normalized_overrides is None or normalized_styles is None:
        return None, None, "render-stale"
    target_code = _check_bag_targets(wire, layout, normalized_overrides, normalized_styles)
    if target_code is not None:
        return None, None, target_code
    return normalized_overrides, normalized_styles, None


def resolve_theme(  # noqa: PLR0913, PLR0917 - spec §5 binding signature
    compiled: object,
    envelope: object,
    layout: object,
    theme_id: str,
    overrides: object,
    di_styles: object,
) -> ResultSuccess | ResultRefused:
    """Resolve one theme over a layout into RenderData/1."""
    wire, echo_identity, echo_revision, refused = _begin_operation(
        "resolveTheme", compiled, envelope
    )
    if refused is not None:
        return refused
    if wire is None:
        return refused_result("resolveTheme", "render-stale", echo_identity, echo_revision)
    selected = _select_operation_theme(compiled, theme_id, echo_identity, echo_revision)
    if isinstance(selected, ResultRefused):
        return selected
    theme, resolved_id, chain = selected
    normalized_overrides, normalized_styles, bags_code = _normalize_inputs(
        compiled, wire, layout, overrides, di_styles
    )
    if bags_code is not None or normalized_overrides is None or normalized_styles is None:
        return refused_result(
            "resolveTheme", bags_code or "render-stale", echo_identity, echo_revision
        )
    if not isinstance(layout, dict) or not check_layout_record(layout):
        return refused_result("resolveTheme", "render-stale", echo_identity, echo_revision)
    context = _ResolveContext(
        compiled, wire, layout, theme, chain, normalized_overrides, normalized_styles
    )
    return _finish_resolve(context, resolved_id, echo_identity, echo_revision)


def _check_bag_targets(
    wire: dict[str, Json],
    layout: object,
    normalized_overrides: dict[str, Json],
    normalized_styles: dict[str, Json],
) -> str | None:
    """Check bag targets resolve (semantic ids in tree, occurrences in layout)."""
    tree = wire.get("tree")
    bearing: set[str] = set()
    if isinstance(tree, dict):
        _, _, bearing = index_tree(tree)
    for record in normalized_overrides.get("semantic", []):
        if record.get("semanticId") not in bearing:
            return "render-stale"
    geometry_keys: set[tuple[str, str]] = set()
    if isinstance(layout, dict):
        for record in layout.get("geometry", []):
            if isinstance(record, dict):
                geometry_keys.add((str(record.get("pageId")), str(record.get("occurrenceKey"))))
    for bag in (
        normalized_overrides.get("occurrence", []),
        normalized_styles.get("native", []),
        normalized_styles.get("bioc", []),
    ):
        for record in bag:
            if (str(record.get("pageId")), str(record.get("occurrenceKey"))) not in geometry_keys:
                return "render-stale"
    return None


@dataclass(frozen=True)
class _ResolveContext:
    """Validated inputs shared by the resolve helpers."""

    compiled: object
    wire: dict[str, Json]
    layout: dict[str, Json]
    theme: dict[str, Json]
    chain: list[dict[str, Json]]
    overrides: dict[str, Json]
    styles: dict[str, Json]


def _geometry_endpoints_ok(geometry: list[Json], bearing: set[str]) -> bool:
    """Check geometry semantic ids and edge endpoints resolve."""
    for record in geometry:
        if not isinstance(record, dict):
            return False
        semantic_id = record.get("semanticId")
        if semantic_id is not None and semantic_id not in bearing:
            return False
    known = {
        (str(record.get("pageId")), str(record.get("occurrenceKey")))
        for record in geometry
        if isinstance(record, dict)
    }
    for record in geometry:
        if not isinstance(record, dict):
            return False
        for key in ("sourceOccurrence", "targetOccurrence"):
            endpoint = record.get(key)
            if endpoint is not None and (
                not isinstance(endpoint, dict)
                or (str(endpoint.get("pageId")), str(endpoint.get("occurrenceKey"))) not in known
            ):
                return False
    return True


def _finish_resolve(
    context: _ResolveContext,
    resolved_id: str,
    echo_identity: dict[str, Json] | None,
    echo_revision: str | None,
) -> ResultSuccess | ResultRefused:
    """Resolve one validated layout into RenderData/1 (code paths inline)."""
    tree = context.wire.get("tree")
    bindings = context.wire.get("bindings")
    if not isinstance(tree, dict) or not isinstance(bindings, list):
        return refused_result("resolveTheme", "render-stale", echo_identity, echo_revision)
    by_id, _, bearing = index_tree(tree)
    geometry = context.layout["geometry"]
    if not _geometry_endpoints_ok(geometry, bearing):
        return refused_result("resolveTheme", "render-stale", echo_identity, echo_revision)
    occurrences: list[dict[str, Json]] = []
    diagnostics: list[ReportEntry] = []
    for record in geometry:
        if not isinstance(record, dict):
            return refused_result("resolveTheme", "render-stale", echo_identity, echo_revision)
        occurrence, code, diagnostic = _resolve_record(context, by_id, bearing, bindings, record)
        if code is not None:
            return refused_result("resolveTheme", code, echo_identity, echo_revision)
        if occurrence is not None:
            occurrences.append(occurrence)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
    laid_out = {
        str(record.get("semanticId")) for record in geometry if record.get("semanticId") is not None
    }
    coverage = _resolve_coverage(tree, occurrences, laid_out)
    render = {
        "renderVersion": "1",
        "pages": copy.deepcopy(context.layout["pages"]),
        "occurrences": occurrences,
        "coverage": coverage,
        "diagnostics": [entry.to_json() for entry in sort_report_entries(diagnostics)],
    }
    binding = _resolve_binding(context, resolved_id, render)
    if isinstance(binding, str):
        return refused_result("resolveTheme", binding, echo_identity, echo_revision)
    render["binding"] = binding
    report = report_with_header(
        "resolveTheme",
        echo_identity or {},
        echo_revision or "",
        entries=diagnostics,
    )
    return ResultSuccess(
        operation="resolveTheme",
        profile_identity=copy.deepcopy(echo_identity) if echo_identity is not None else {},
        base_revision=echo_revision or "",
        revision=echo_revision or "",
        payload=render,
        report=report,
    )


def _synthetic_occurrence(
    context: _ResolveContext,
    record: dict[str, Json],
    occurrence: dict[str, Json],
    bearing: set[str],
) -> tuple[dict[str, Json] | None, str | None]:
    """Resolve one key-less geometry record through its synthetic declaration."""
    page_id = str(record.get("pageId"))
    occurrence_key = str(record.get("occurrenceKey"))
    declaration = _declaration_for(
        context.theme, occurrence_key, str(record.get("role")), page_id, bearing
    )
    if declaration is None:
        return None, "render-stale"
    tokens = [entry for entry in declaration.get("tokens", []) if isinstance(entry, dict)]
    role = declaration.get("role")
    occurrence["emittedType"] = (
        "edge" if role == "edge" else ("label" if role == "label" else "node")
    )
    empty = _TokenLevels(occurrence=[], semantic=[], native=[], bioc=[])
    theme_tokens = {str(entry.get("name")): entry.get("value") for entry in tokens}
    occurrence["style"] = _resolve_style(context.chain, theme_tokens, empty)
    glyph = declaration.get("glyph")
    if isinstance(glyph, str):
        occurrence["glyphId"] = glyph
    return occurrence, None


def _unsupported_diagnostic(
    tree: dict[str, Json], semantic_id: str, page_id: str, occurrence_key: str
) -> ReportEntry:
    """Build the render-unsupported diagnostic of one glyph-less occurrence."""
    pointer = _tree_pointer_of(tree, semantic_id)
    return ReportEntry(
        code="render-unsupported",
        severity="error",
        classification="integrity",
        stage="render",
        rule_id="adapter",
        message_key="render-unsupported",
        disposition="observed",
        source=make_coordinate("tree", pointer, semantic_id, "exact"),
        result=make_coordinate("none", None, None, "unavailable"),
        before_present=False,
        after_present=False,
        page_id=page_id,
        occurrence_key=occurrence_key,
    )


def _echo_edge(record: dict[str, Json], occurrence: dict[str, Json]) -> None:
    """Echo edge waypoints and endpoints from one geometry record."""
    waypoints = record.get("waypoints")
    if isinstance(waypoints, list):
        occurrence["waypoints"] = [
            {"x": point["x"], "y": point["y"]}
            for point in waypoints
            if isinstance(point, dict)
            and type(point.get("x")) is int
            and type(point.get("y")) is int
        ]
    for member in ("sourceOccurrence", "targetOccurrence"):
        ref = record.get(member)
        if (
            isinstance(ref, dict)
            and isinstance(ref.get("pageId"), str)
            and isinstance(ref.get("occurrenceKey"), str)
        ):
            occurrence[member] = {"pageId": ref["pageId"], "occurrenceKey": ref["occurrenceKey"]}


def _check_record_text(  # noqa: PLR0913, PLR0917 - label-check frame is fixed
    context: _ResolveContext,
    tree: dict[str, Json],
    element: dict[str, Json],
    bindings: list[Json],
    matched: list[dict[str, Json]],
    record: dict[str, Json],
) -> str | None:
    """Evaluate one occurrence label and check it against the record label."""
    if not matched:
        # No notion means no label contract: a record label on a named
        # element is stale (its bindings produce no label); a nameless
        # element (e.g. an annotation carrying DI text) goes to the
        # unsupported path below instead of refusing here.
        unmatched_named = record.get("label") is not None and isinstance(element.get("name"), str)
        return "render-stale" if unmatched_named else None
    asts, code = _notion_label_asts(matched, context.chain)
    if code is not None:
        return code
    text: str | None = None
    if asts:
        text, code = evaluate_label_value(context.compiled, tree, asts[0], element, bindings)
        if code is not None:
            return code
    record_label = record.get("label")
    if text is None and record_label is not None:
        return "render-stale"
    if text is not None and (
        not isinstance(record_label, dict) or record_label.get("text") != text
    ):
        return "render-stale"
    return None


def _resolve_record(
    context: _ResolveContext,
    by_id: dict[str, Json],
    bearing: set[str],
    bindings: list[Json],
    record: dict[str, Json],
) -> tuple[dict[str, Json] | None, str | None, ReportEntry | None]:
    """Resolve one geometry record to an R occurrence (record, code, diagnostic)."""
    page_id = str(record.get("pageId"))
    occurrence_key = str(record.get("occurrenceKey"))
    occurrence: dict[str, Json] = {
        "pageId": page_id,
        "occurrenceKey": occurrence_key,
    }
    if record.get("semanticId") is not None:
        occurrence["semanticId"] = record.get("semanticId")
    occurrence["role"] = record.get("role")
    occurrence["bounds"] = copy.deepcopy(record.get("bounds"))
    if record.get("label") is not None:
        occurrence["label"] = copy.deepcopy(record.get("label"))
    semantic_id = record.get("semanticId")
    if semantic_id is None:
        resolved, code = _synthetic_occurrence(context, record, occurrence, bearing)
        return resolved, code, None
    return _semantic_occurrence(context, by_id, bindings, record, occurrence)


def _semantic_occurrence(
    context: _ResolveContext,
    by_id: dict[str, Json],
    bindings: list[Json],
    record: dict[str, Json],
    occurrence: dict[str, Json],
) -> tuple[dict[str, Json] | None, str | None, ReportEntry | None]:
    """Resolve one semantic geometry record to an R occurrence."""
    tree = context.wire["tree"]
    page_id = str(record.get("pageId"))
    occurrence_key = str(record.get("occurrenceKey"))
    semantic_id = str(record.get("semanticId"))
    element = by_id.get(semantic_id)
    if not isinstance(element, dict):
        return None, "render-stale", None
    matched = matched_notions(context.compiled, tree, element, bindings)
    glyph_id, code = _notion_glyph_id(matched, context.chain)
    if code is not None:
        return None, code, None
    binding_tokens, code = _binding_token_merge(matched, context.chain)
    if code is not None:
        return None, code, None
    code = _check_record_text(context, tree, element, bindings, matched, record)
    if code is not None:
        return None, code, None
    role = record.get("role")
    # DESIGN §9 edge rule is presence-based (both `edge` and `content`
    # role vocabularies are sealed): endpoints mark an edge record.
    is_edge = "sourceOccurrence" in record or "targetOccurrence" in record
    occurrence["emittedType"] = "edge" if is_edge else ("label" if role == "label" else "node")
    levels = _TokenLevels(
        occurrence=_lookup_tokens(context.overrides["occurrence"], page_id, occurrence_key),
        semantic=_lookup_semantic(context.overrides["semantic"], semantic_id),
        native=_lookup_tokens(context.styles["native"], page_id, occurrence_key),
        bioc=_lookup_tokens(context.styles["bioc"], page_id, occurrence_key),
    )
    occurrence["style"] = _resolve_style(context.chain, binding_tokens or {}, levels)
    if glyph_id is None:
        diagnostic = _unsupported_diagnostic(tree, semantic_id, page_id, occurrence_key)
        return None, None, diagnostic
    occurrence["glyphId"] = glyph_id
    if occurrence["emittedType"] == "edge":
        _echo_edge(record, occurrence)
    return occurrence, None, None


def _tree_pointer_of(tree: dict[str, Json], semantic_id: str) -> str | None:
    """Return the tree pointer of one semantic id (or None)."""
    for found_id, _, pointer in native_preorder(tree):
        if found_id == semantic_id:
            return pointer
    return None


def _resolve_coverage(
    tree: dict[str, Json], occurrences: list[dict[str, Json]], laid_out: set[str]
) -> list[dict[str, Json]]:
    """Walk the native tree in pre-order into the R coverage."""
    by_element: dict[str, list[dict[str, Json]]] = {}
    for occurrence in occurrences:
        semantic_id = occurrence.get("semanticId")
        if isinstance(semantic_id, str):
            by_element.setdefault(semantic_id, []).append(occurrence)
    coverage: list[dict[str, Json]] = []
    for element_id, _, _ in native_preorder(tree):
        records = by_element.get(element_id, [])
        if not records:
            disposition = "unsupported" if element_id in laid_out else "nonvisual"
            coverage.append(
                {"semanticId": element_id, "occurrences": [], "disposition": disposition}
            )
        else:
            pairs = [
                {"pageId": record.get("pageId"), "occurrenceKey": record.get("occurrenceKey")}
                for record in records
            ]
            coverage.append(
                {"semanticId": element_id, "occurrences": pairs, "disposition": "rendered"}
            )
    return coverage


def _resolve_binding(
    context: _ResolveContext,
    resolved_id: str,
    render: dict[str, Json],
) -> dict[str, str] | str:
    """Bind the §9.2 freshness record of one RenderData/1 (or code)."""
    compiled = context.compiled
    wire = context.wire
    layout = context.layout
    identity = getattr(compiled, "identity", None)
    if not isinstance(identity, dict):
        return "render-stale"
    tree = wire["tree"]
    profile_digest = identity.get("sha256")
    try:
        descriptor_hash = descriptor_digest(identity.get("descriptors"))  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001 - malformed pins are stale input
        return "render-stale"
    profile = getattr(compiled, "profile", None)
    themes = profile.get("themes", []) if isinstance(profile, dict) else []
    theme_hash = theme_digest(themes, resolved_id)
    if theme_hash is None:
        return "render-stale"
    metric_refs: list[str] = []
    for theme in _chain_themes(compiled, resolved_id):
        resource = theme.get("metricsResource")
        if isinstance(resource, str) and resource not in metric_refs:
            metric_refs.append(resource)
    assets = getattr(compiled, "assets", {})
    resources: list[dict[str, str]] = []
    for resource in metric_refs:
        raw = assets.get(resource) if isinstance(assets, dict) else None
        if not isinstance(raw, (bytes, bytearray)):
            return "profile-resource-missing"
        resources.append({"id": resource, "sha256": digest_bytes(bytes(raw))})
    binding: dict[str, str] = {
        "semanticRevision": semantic_revision(tree, identity, wire.get("bindings", [])),
        "profileDigest": str(profile_digest),
        "descriptorDigest": descriptor_hash,
        "layoutDigest": digest(layout),
        "themeId": resolved_id,
        "themeDigest": theme_hash,
        "overridesDigest": digest(context.overrides),
        "diStylesDigest": digest(context.styles),
        "metricsDigest": metrics_digest(resources),
    }
    binding["payloadDigest"] = payload_digest(
        {
            "pages": render["pages"],
            "occurrences": render["occurrences"],
            "coverage": render["coverage"],
            "diagnostics": render["diagnostics"],
        }
    )
    return binding


def _chain_themes(compiled: object, resolved_id: str) -> list[dict[str, Json]]:
    """Return the fallback chain of one resolved theme (selected first)."""
    profile = getattr(compiled, "profile", None)
    themes = profile.get("themes", []) if isinstance(profile, dict) else []
    chain = theme_chain([t for t in themes if isinstance(t, dict)], resolved_id)
    if chain is None:
        return []
    return list(reversed(chain))
