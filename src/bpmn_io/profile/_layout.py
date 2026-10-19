"""Shared layout seam and Python DI adapter (DESIGN R3.3 §§4.2-4.6, 9.4).

``compute_layout`` transcribes imported DI to base geometry, then
``layout`` applies the region rule, routes relocated links, emits
synthetic occurrences and grows pages. Exact rationals inside, integer
ticks at output, no invented positions.
"""

from __future__ import annotations

import copy
import dataclasses
from typing import Any

from bpmn_io.profile._c14n import digest as c14n_digest
from bpmn_io.profile._c14n import jcs
from bpmn_io.profile._envelope import DocumentEnvelope
from bpmn_io.profile._evaluate import (
    ReadContext,
    evaluate_predicate,
    evaluate_value,
    is_missing,
    make_read_context,
    select,
)
from bpmn_io.profile._regions import layout_regions, layout_ticks
from bpmn_io.profile._render_digest import descriptor_digest
from bpmn_io.profile._results import (
    PureRefused,
    ResultRefused,
    ResultSuccess,
    refused_result,
    report_with_header,
)
from bpmn_io.profile._text_metrics import measure_text
from bpmn_io.profile._themes import (
    check_compatibility_gate,
    coerce_envelope,
    envelope_echo,
    resolve_theme_id,
    theme_chain,
)

__all__ = ["compute_layout", "layout"]

Json = Any

_MAX_TRAVERSAL_NODES = 4000000


@dataclasses.dataclass(frozen=True)
class _ThemeView:
    """One resolved theme with its fallback chain."""

    theme: dict[str, Json]
    chain: list[dict[str, Json]]


@dataclasses.dataclass(frozen=True)
class _LabelScope:
    """Label transcription environment shared by one transcribe pass."""

    compiled: object
    tree: dict[str, Json]
    view: _ThemeView
    placements: Json
    bindings: list[Json]
    by_id: dict[str, Json]
    bearing: set[str]


@dataclasses.dataclass(frozen=True)
class _LayoutInputs:
    """Validated inputs of one base-geometry seam run."""

    operation: str
    compiled: object
    wire: dict[str, Json]
    placements: Json
    base_geometry: dict[str, Json]
    view: _ThemeView
    echo_identity: dict[str, Json] | None
    echo_revision: str | None


@dataclasses.dataclass
class _StagedLayout:
    """Mutable staged geometry of one seam run."""

    tree: dict[str, Json]
    bindings: list[Json]
    by_id: dict[str, Json]
    bearing: set[str]
    geometry: list[dict[str, Json]]
    pages: list[dict[str, Json]]
    pages_by_id: dict[str, dict[str, Json]]


def _escape_segment(segment: str) -> str:
    """Escape one RFC 6901 reference token."""
    return segment.replace("~", "~0").replace("/", "~1")


def index_tree(tree: dict[str, Json]) -> tuple[dict[str, Json], dict[str, str], set[str]]:
    """Index one JSON tree: id to element, id to pointer, ID-bearing ids."""
    by_id: dict[str, Json] = {}
    pointers: dict[str, str] = {}
    bearing: set[str] = set()
    stack: list[tuple[Json, str]] = [(tree, "")]
    seen = 0
    while stack:
        node, pointer = stack.pop()
        seen += 1
        if seen > _MAX_TRAVERSAL_NODES:
            break
        if isinstance(node, dict):
            _index_element(node, pointer, by_id, pointers, bearing)
            for key, child in reversed(_index_child_entries(node)):
                segments = [_escape_segment(part) for part in key.split("/")]
                stack.append((child, pointer + "/" + "/".join(segments)))
        elif isinstance(node, list):
            stack.extend(_index_list_entries(node, pointer))
    return by_id, pointers, bearing


def _index_element(
    node: dict[str, Json],
    pointer: str,
    by_id: dict[str, Json],
    pointers: dict[str, str],
    bearing: set[str],
) -> None:
    """Index one typed element id in place."""
    type_name = node.get("$type")
    element_id = node.get("id")
    if not isinstance(type_name, str) or not isinstance(element_id, str):
        return
    bearing.add(element_id)
    if element_id not in by_id:
        by_id[element_id] = node
        pointers[element_id] = pointer


def _index_child_entries(node: dict[str, Json]) -> list[tuple[str, Json]]:
    """Collect one mapping node's child entries in sorted key order."""
    children: list[tuple[str, Json]] = []
    for key in sorted(node.keys()):
        value = node[key]
        if isinstance(value, dict):
            children.append((key, value))
        elif isinstance(value, list):
            for index, entry in enumerate(value):
                if isinstance(entry, (dict, list)):
                    children.append((f"{key}/{index}", entry))
    return children


def _index_list_entries(node: list[Json], pointer: str) -> list[tuple[Json, str]]:
    """Collect one sequence node's entries reversed for stack order."""
    entries: list[tuple[Json, str]] = []
    for index in range(len(node) - 1, -1, -1):
        entry = node[index]
        if isinstance(entry, (dict, list)):
            entries.append((entry, pointer + "/" + str(index)))
    return entries


def _ref_id(value: Json) -> str | None:
    """Extract one semantic reference id (string, $ref or element)."""
    if isinstance(value, str):
        return value or None
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str) and ref:
            return ref
        element_id = value.get("id")
        if isinstance(element_id, str) and element_id:
            return element_id
    return None


def _check_bounds_record(bounds: object) -> bool:
    """Return whether one bounds record holds safe integer ticks."""
    if not isinstance(bounds, dict) or set(bounds.keys()) != {"x", "y", "width", "height"}:
        return False
    for key in ("x", "y", "width", "height"):
        entry = bounds.get(key)
        if not isinstance(entry, int) or isinstance(entry, bool):
            return False
    return bool(bounds["width"] >= 0 and bounds["height"] >= 0)


def _check_label_record(label: object) -> bool:
    """Return whether one label record is closed and LF-consistent."""
    if not isinstance(label, dict) or set(label.keys()) != {"text", "bounds", "lines"}:
        return False
    text = label.get("text")
    if not isinstance(text, str) or not text:
        return False
    if not _check_bounds_record(label.get("bounds")):
        return False
    return bool(label.get("lines") == text.split("\n"))


def _check_geometry_identity(record: dict[str, Json]) -> bool:
    """Return whether one geometry record has closed identity members."""
    keys = set(record.keys())
    required = {"pageId", "occurrenceKey", "role", "bounds"}
    allowed = required | {
        "semanticId",
        "label",
        "sourceOccurrence",
        "targetOccurrence",
        "waypoints",
    }
    if not required <= keys or keys - allowed:
        return False
    for key in ("pageId", "occurrenceKey"):
        if not isinstance(record.get(key), str) or not record.get(key):
            return False
    return isinstance(record.get("role"), str)


def _check_edge_endpoints(record: dict[str, Json]) -> bool:
    """Return whether one edge record has closed endpoints and waypoints."""
    for key in ("sourceOccurrence", "targetOccurrence"):
        endpoint = record.get(key)
        if (
            not isinstance(endpoint, dict)
            or set(endpoint.keys()) != {"pageId", "occurrenceKey"}
            or not isinstance(endpoint.get("pageId"), str)
            or not isinstance(endpoint.get("occurrenceKey"), str)
        ):
            return False
    waypoints = record.get("waypoints")
    if not isinstance(waypoints, list) or len(waypoints) < 2:
        return False
    for point in waypoints:
        if (
            not isinstance(point, dict)
            or set(point.keys()) != {"x", "y"}
            or not isinstance(point.get("x"), int)
            or isinstance(point.get("x"), bool)
            or not isinstance(point.get("y"), int)
            or isinstance(point.get("y"), bool)
        ):
            return False
    return True


def _check_geometry_optional(record: dict[str, Json]) -> bool:
    """Return whether one geometry record has closed optional members."""
    if "semanticId" in record and not isinstance(record.get("semanticId"), str):
        return False
    return "label" not in record or _check_label_record(record.get("label"))


def _check_geometry_record(record: object) -> bool:
    """Return whether one geometry record is closed (order checked later)."""
    if not isinstance(record, dict):
        return False
    if not _check_geometry_identity(record):
        return False
    if not _check_bounds_record(record.get("bounds")):
        return False
    if not _check_geometry_optional(record):
        return False
    if record.get("role") == "edge":
        return _check_edge_endpoints(record)
    has_endpoints = "sourceOccurrence" in record or "targetOccurrence" in record
    return not (has_endpoints or "waypoints" in record)


def _check_page_record(page: object) -> bool:
    """Return whether one page record is closed."""
    if not isinstance(page, dict):
        return False
    if set(page.keys()) != {"pageId", "name", "order", "semanticRootId", "bounds"}:
        return False
    if not isinstance(page.get("pageId"), str) or not page.get("pageId"):
        return False
    for key in ("name", "semanticRootId"):
        if not isinstance(page.get(key), str):
            return False
    if not isinstance(page.get("order"), int) or isinstance(page.get("order"), bool):
        return False
    return _check_bounds_record(page.get("bounds"))


def _check_layout_pages(pages: object) -> dict[str, int] | None:
    """Index closed pages by id in order (None when malformed)."""
    if not isinstance(pages, list):
        return None
    seen_orders: set[int] = set()
    page_ids: set[str] = set()
    page_order: dict[str, int] = {}
    for page in pages:
        if not isinstance(page, dict) or not _check_page_record(page):
            return None
        if page["order"] in seen_orders or page["pageId"] in page_ids:
            return None
        seen_orders.add(page["order"])
        page_ids.add(str(page["pageId"]))
        page_order[str(page["pageId"])] = int(page["order"])
    if sorted(seen_orders) != sorted(page_order.values()):
        return None
    if [page["order"] for page in pages if isinstance(page, dict)] != sorted(seen_orders):
        return None
    return page_order


def _check_layout_geometry(
    geometry: object, page_ids: set[str], page_order: dict[str, int]
) -> bool:
    """Return whether geometry records are closed, known and ordered."""
    if not isinstance(geometry, list):
        return False
    seen_keys: set[tuple[str, str]] = set()
    last_key: tuple[bytes, bytes] | None = None
    for record in geometry:
        if not isinstance(record, dict) or not _check_geometry_record(record):
            return False
        key = (str(record["pageId"]), str(record["occurrenceKey"]))
        if key in seen_keys or record["pageId"] not in page_ids:
            return False
        seen_keys.add(key)
        order_key = (
            str(page_order[key[0]]).encode("utf-16-be"),
            key[1].encode("utf-16-be"),
        )
        if last_key is not None and order_key < last_key:
            return False
        last_key = order_key
    return True


def check_layout_record(value: object) -> bool:
    """Return whether one value is a closed Layout/1 record in order."""
    if not isinstance(value, dict) or set(value.keys()) != {"layoutVersion", "pages", "geometry"}:
        return False
    if value.get("layoutVersion") != "1":
        return False
    pages = value.get("pages")
    geometry = value.get("geometry")
    if not isinstance(pages, list) or not isinstance(geometry, list):
        return False
    page_order = _check_layout_pages(pages)
    if page_order is None:
        return False
    page_ids = set(page_order.keys())
    return _check_layout_geometry(geometry, page_ids, page_order)


def _matched_bindings_for_theme(
    contributions: list[dict[str, Json]], chain: list[dict[str, Json]]
) -> dict[str, Json] | None:
    """Return the nearest-chain render binding of one notion (or None)."""
    for theme in chain:
        theme_id = str(theme.get("id"))
        for binding in contributions:
            if binding.get("theme") == theme_id:
                return binding
    return None


def _read_context_for(compiled: object, tree: dict[str, Json], support: list[Json]) -> ReadContext:
    """Build one native read context with support bindings attached."""
    context = make_read_context(tree, notions=getattr(compiled, "notions", {}))
    return dataclasses.replace(
        context, bindings=tuple(entry for entry in support if isinstance(entry, dict))
    )


def matched_notions(
    compiled: object,
    tree: dict[str, Json],
    element: dict[str, Json],
    support: list[Json] | None = None,
) -> list[dict[str, Json]]:
    """Return every notion matching one native element (facets plus groups)."""
    profile = getattr(compiled, "profile", None)
    notions = profile.get("notions", []) if isinstance(profile, dict) else []
    context = _read_context_for(compiled, tree, support or [])
    matched: list[dict[str, Json]] = []
    for notion in notions:
        if not isinstance(notion, dict) or "recognition" not in notion:
            continue
        try:
            result = evaluate_predicate(
                notion.get("recognition"), context, {"root": tree, "self": element}
            )
        except Exception:  # noqa: BLE001, S112 - recognition stays total
            continue
        if isinstance(result, PureRefused):
            continue
        if result.payload is not True:
            continue
        matched.append(notion)
    matched.sort(key=lambda notion: str(notion.get("id")).encode("utf-16-be"))
    return matched


def evaluate_label_value(
    compiled: object,
    tree: dict[str, Json],
    label_ast: Json,
    element: Json,
    support: list[Json] | None = None,
) -> tuple[str | None, str | None]:
    """Evaluate one label Value expression (text-or-None, refusal code)."""
    context = _read_context_for(compiled, tree, support or [])
    result = evaluate_value(label_ast, context, {"root": tree, "self": element})
    if isinstance(result, PureRefused):
        return None, str(result.code)
    value = result.payload
    if is_missing(value):
        return None, None
    if not isinstance(value, str):
        return None, "profile-type"
    if not value:
        return None, None
    return value, None


def _notion_label_asts(
    matched: list[dict[str, Json]], chain: list[dict[str, Json]]
) -> tuple[list[Json], str | None]:
    """Collect the agreed label ASTs of matched notions (conflict code)."""
    seen: list[Json] = []
    for notion in matched:
        bindings = notion.get("renderBindings", [])
        binding = _matched_bindings_for_theme(bindings if isinstance(bindings, list) else [], chain)
        if binding is None or "label" not in binding:
            continue
        ast = binding.get("label")
        if not any(jcs(ast) == jcs(entry) for entry in seen):
            if seen:
                return [], "render-style-conflict"
            seen.append(ast)
    return seen, None


def _notion_glyph_id(
    matched: list[dict[str, Json]], chain: list[dict[str, Json]]
) -> tuple[str | None, str | None]:
    """Collect the agreed glyph id of matched notions (conflict code)."""
    glyph_id: str | None = None
    for notion in matched:
        bindings = notion.get("renderBindings", [])
        binding = _matched_bindings_for_theme(bindings if isinstance(bindings, list) else [], chain)
        if binding is None:
            continue
        candidate = binding.get("glyph")
        if not isinstance(candidate, str):
            continue
        if glyph_id is None:
            glyph_id = candidate
        elif glyph_id != candidate:
            return None, "render-style-conflict"
    return glyph_id, None


def _begin_operation(
    operation: str, compiled: object, envelope: object
) -> tuple[dict[str, Json] | None, dict[str, Json] | None, str | None, ResultRefused | None]:
    """Coerce, echo, validate and compat-check one operation envelope."""
    wire, code = coerce_envelope(envelope)
    if isinstance(envelope, DocumentEnvelope):
        echo_wire: object = envelope.to_json()
    elif isinstance(envelope, dict):
        echo_wire = copy.deepcopy(envelope)
    else:
        echo_wire = None
    echo_identity, echo_revision = envelope_echo(wire if wire is not None else echo_wire)
    if wire is None:
        return (
            None,
            echo_identity,
            echo_revision,
            refused_result(operation, code or "profile-schema", echo_identity, echo_revision),
        )
    compat_code = check_compatibility_gate(compiled, wire["profileIdentity"])
    if compat_code is not None:
        return (
            None,
            echo_identity,
            echo_revision,
            refused_result(operation, compat_code, echo_identity, echo_revision),
        )
    return wire, echo_identity, echo_revision, None


def _resolve_operation_theme(
    operation: str,
    compiled: object,
    theme_id: str,
    echo_identity: dict[str, Json] | None,
    echo_revision: str | None,
) -> tuple[dict[str, Json] | None, str | None, list[dict[str, Json]] | None, ResultRefused | None]:
    """Resolve one operation theme with its fallback chain and geometry gate."""
    profile = getattr(compiled, "profile", None)
    if not isinstance(profile, dict):
        return (
            None,
            None,
            None,
            refused_result(operation, "render-stale", echo_identity, echo_revision),
        )
    theme, resolved_id = resolve_theme_id(profile, theme_id)
    if theme is None or resolved_id is None:
        return (
            None,
            None,
            None,
            refused_result(operation, "render-stale", echo_identity, echo_revision),
        )
    if theme.get("geometry") == "theme":
        return (
            None,
            None,
            None,
            refused_result(operation, "profile-open", echo_identity, echo_revision),
        )
    themes = [entry for entry in profile.get("themes", []) if isinstance(entry, dict)]
    chain = theme_chain(themes, resolved_id)
    if chain is None:
        return (
            None,
            None,
            None,
            refused_result(operation, "render-stale", echo_identity, echo_revision),
        )
    return theme, resolved_id, chain, None


def _transcribe_bounds(di_bounds: Json) -> dict[str, int] | None:
    """Transcribe one dc:Bounds record to tick bounds (None when malformed)."""
    if not isinstance(di_bounds, dict):
        return None
    ticks = layout_ticks(
        [di_bounds.get("x"), di_bounds.get("y"), di_bounds.get("width"), di_bounds.get("height")]
    )
    if isinstance(ticks, PureRefused):
        return None
    values = ticks.payload
    if not isinstance(values, list) or len(values) != 4:
        return None
    width = int(values[2])
    height = int(values[3])
    if width < 0 or height < 0:
        return None
    return {"x": int(values[0]), "y": int(values[1]), "width": width, "height": height}


def _transcribe_waypoints(waypoints: Json) -> list[dict[str, int]] | None:
    """Transcribe one waypoint list to tick points (None when malformed)."""
    if not isinstance(waypoints, list) or not waypoints:
        return None
    raw: list[Json] = []
    for point in waypoints:
        if not isinstance(point, dict):
            return None
        raw.extend([point.get("x"), point.get("y")])
    ticks = layout_ticks(raw)
    if isinstance(ticks, PureRefused) or not isinstance(ticks.payload, list):
        return None
    numbers = list(ticks.payload)
    return [
        {"x": int(numbers[index]), "y": int(numbers[index + 1])}
        for index in range(0, len(numbers), 2)
    ]


def compute_layout(
    compiled: object,
    envelope: object,
    placements: object,
    imported_di: object,
    *,
    theme_id: str,
) -> ResultSuccess | ResultRefused:
    """Transcribe imported DI to base geometry, then run the shared seam."""
    wire, echo_identity, echo_revision, refused = _begin_operation(
        "computeLayout", compiled, envelope
    )
    if refused is not None:
        return refused
    if wire is None:
        return refused_result("computeLayout", "render-stale", echo_identity, echo_revision)
    theme, resolved_id, chain, theme_refused = _resolve_operation_theme(
        "computeLayout", compiled, theme_id, echo_identity, echo_revision
    )
    if theme_refused is not None:
        return theme_refused
    if theme is None or resolved_id is None or chain is None:
        return refused_result("computeLayout", "render-stale", echo_identity, echo_revision)
    base, code = _transcribe_imported_di(
        compiled, wire, placements, imported_di, _ThemeView(theme, chain)
    )
    if code is not None or base is None:
        return refused_result("computeLayout", code or "render-stale", echo_identity, echo_revision)
    inputs = _LayoutInputs(
        "computeLayout",
        compiled,
        wire,
        placements,
        base,
        _ThemeView(theme, chain),
        echo_identity,
        echo_revision,
    )
    return _run_layout(inputs)


def _support_role(bindings: list[Json], semantic_id: str) -> str | None:
    """Return the support binding role for one support target (or None)."""
    for binding in bindings:
        if isinstance(binding, dict) and binding.get("targetId") == semantic_id:
            role = binding.get("role")
            if isinstance(role, str):
                return role
    return None


def _check_imported_di(
    imported_di: object, identity: dict[str, Json]
) -> tuple[dict[str, Json] | None, str | None]:
    """Validate one Snapshot/1 importedDi record (record, code)."""
    if not isinstance(imported_di, dict):
        return None, "render-stale"
    if set(imported_di.keys()) != {"descriptorDigest", "diagrams", "sha256"}:
        return None, "render-stale"
    diagrams = imported_di.get("diagrams")
    if not isinstance(diagrams, list):
        return None, "render-stale"
    descriptors = identity.get("descriptors")
    if not isinstance(descriptors, list):
        return None, "render-stale"
    want_descriptor, code = _imported_di_pins(imported_di, diagrams, descriptors)
    if code is not None or want_descriptor is None:
        return None, code or "render-stale"
    return {"descriptorDigest": want_descriptor, "diagrams": diagrams}, None


def _imported_di_pins(
    imported_di: dict[str, Json], diagrams: list[Json], descriptors: list[Json]
) -> tuple[str | None, str | None]:
    """Check one importedDi descriptor pin and sha (want, code)."""
    try:
        want_descriptor = descriptor_digest(descriptors)
    except Exception:  # noqa: BLE001 - malformed pins are stale input
        return None, "render-stale"
    if imported_di.get("descriptorDigest") != want_descriptor:
        return None, "render-stale"
    if imported_di.get("sha256") != c14n_digest(
        {"descriptorDigest": imported_di.get("descriptorDigest"), "diagrams": diagrams}
    ):
        return None, "render-stale"
    return want_descriptor, None


def _placement_region_key(
    placement: Json, bindings: list[Json], theme: dict[str, Json]
) -> tuple[dict[str, Json] | None, bool]:
    """Match one placement to its binding (attachment flag when binding-less)."""
    owner = placement.get("ownerProcessId")
    region = placement.get("regionKey")
    for binding in bindings:
        if (
            isinstance(binding, dict)
            and binding.get("ownerId") == owner
            and binding.get("role") == region
        ):
            return binding, False
    for declaration in theme.get("syntheticOccurrences", []):
        if (
            isinstance(declaration, dict)
            and declaration.get("region") == region
            and declaration.get("role") == "attached-badge"
        ):
            return None, True
    return None, False


def _is_region_item(
    placements: Json, bindings: list[Json], theme: dict[str, Json], semantic_id: str
) -> bool:
    """Return whether one element has a placement whose region resolves."""
    if not isinstance(placements, list):
        return False
    for placement in placements:
        if not isinstance(placement, dict) or placement.get("elementId") != semantic_id:
            continue
        binding, _attached = _placement_region_key(placement, bindings, theme)
        if binding is not None:
            return True
    return False


def _evaluate_record_label(
    compiled: object,
    tree: dict[str, Json],
    chain: list[dict[str, Json]],
    element: dict[str, Json],
    support: list[Json] | None = None,
) -> tuple[str | None, str | None]:
    """Evaluate the agreed label of one element (text-or-None, code)."""
    matched = matched_notions(compiled, tree, element, support)
    asts, code = _notion_label_asts(matched, chain)
    if code is not None:
        return None, code
    if not asts:
        return None, None
    return evaluate_label_value(compiled, tree, asts[0], element, support)


def _measured_label_bounds(
    scope: _LabelScope, text: str, semantic_id: str, record_bounds: dict[str, int]
) -> tuple[dict[str, int] | None, str | None]:
    """Measure one region-item label (bounds, code)."""
    if not _is_region_item(scope.placements, scope.bindings, scope.view.theme, semantic_id):
        return dict(record_bounds), None
    metrics_id = scope.view.theme.get("metricsResource")
    assets = getattr(scope.compiled, "assets", {})
    raw = assets.get(metrics_id) if isinstance(assets, dict) else None
    if not isinstance(raw, (bytes, bytearray)):
        return None, "profile-resource-missing"
    measured = measure_text(bytes(raw), text)
    if isinstance(measured, PureRefused):
        return None, "profile-resource-missing"
    size = measured.payload
    if not isinstance(size, dict):
        return None, "profile-resource-missing"
    return {
        "x": record_bounds["x"],
        "y": record_bounds["y"],
        "width": size["width"],
        "height": size["height"],
    }, None


def _transcribe_label(
    scope: _LabelScope,
    element: dict[str, Json],
    semantic_id: str,
    record_bounds: dict[str, int],
    di_label_bounds: dict[str, int] | None,
) -> tuple[dict[str, Json] | None, str | None]:
    """Transcribe one record label (record, code)."""
    text, code = _evaluate_record_label(
        scope.compiled, scope.tree, scope.view.chain, element, scope.bindings
    )
    if code is not None:
        return None, code
    if text is None:
        return None, None
    if di_label_bounds is not None:
        label_bounds: dict[str, Json] = di_label_bounds
    else:
        measured_bounds, code = _measured_label_bounds(scope, text, semantic_id, record_bounds)
        if code is not None or measured_bounds is None:
            return None, code or "profile-resource-missing"
        label_bounds = measured_bounds
    return {"text": text, "bounds": label_bounds, "lines": text.split("\n")}, None


def _grow_bounds(box: dict[str, int], extra: dict[str, int]) -> dict[str, int]:
    """Grow one bbox with a record or label bounds."""
    if box["width"] == 0 and box["height"] == 0 and box["x"] == 0 and box["y"] == 0:
        return dict(extra)
    right = max(box["x"] + box["width"], extra["x"] + extra["width"])
    bottom = max(box["y"] + box["height"], extra["y"] + extra["height"])
    origin_x = min(box["x"], extra["x"])
    origin_y = min(box["y"], extra["y"])
    return {
        "x": origin_x,
        "y": origin_y,
        "width": right - origin_x,
        "height": bottom - origin_y,
    }


def _check_member_ids(members: list[Json]) -> str | None:
    """Check one plane member list has unique ids (code)."""
    seen_di: set[str] = set()
    for member in members:
        if not isinstance(member, dict):
            return "render-stale"
        member_id = member.get("id")
        if not isinstance(member_id, str) or not member_id or member_id in seen_di:
            return "render-stale"
        seen_di.add(member_id)
    return None


def _check_diagram_shape(
    diagram: object, bearing: set[str]
) -> tuple[tuple[str, str, list[Json]] | None, str | None]:
    """Validate one diagram shape (ids triple, code)."""
    if not isinstance(diagram, dict):
        return None, "render-stale"
    diagram_id = diagram.get("id")
    if not isinstance(diagram_id, str) or not diagram_id:
        return None, "render-stale"
    plane = diagram.get("plane")
    members = plane.get("planeElement", []) if isinstance(plane, dict) else None
    root_id = plane.get("bpmnElement") if isinstance(plane, dict) else None
    if not isinstance(members, list) or not isinstance(root_id, str) or root_id not in bearing:
        return None, "render-stale"
    code = _check_member_ids(members)
    if code is not None:
        return None, code
    return (diagram_id, root_id, members), None


def _member_bounds(
    scope: _LabelScope, member: dict[str, Json], member_type: Json, semantic_id: str
) -> tuple[dict[str, int] | None, str | None, list[dict[str, int]] | None, str | None]:
    """Transcribe one member geometry (bounds, role, waypoints, code)."""
    if member_type == "bpmndi:BPMNShape":
        bounds = _transcribe_bounds(member.get("bounds"))
        if bounds is None:
            return None, None, None, "render-stale"
        return bounds, _support_role(scope.bindings, semantic_id) or "shape", None, None
    if member_type == "bpmndi:BPMNEdge":
        waypoints = _transcribe_waypoints(member.get("waypoint"))
        if waypoints is None:
            return None, None, None, "render-stale"
        right = max(point["x"] for point in waypoints)
        bottom = max(point["y"] for point in waypoints)
        origin_x = min(point["x"] for point in waypoints)
        origin_y = min(point["y"] for point in waypoints)
        bounds = {
            "x": origin_x,
            "y": origin_y,
            "width": right - origin_x,
            "height": bottom - origin_y,
        }
        return bounds, "edge", waypoints, None
    return None, None, None, "render-stale"


def _member_label(
    scope: _LabelScope,
    member: dict[str, Json],
    element: dict[str, Json],
    semantic_id: str,
    bounds: dict[str, int],
) -> tuple[dict[str, Json] | None, str | None]:
    """Transcribe one member label (label, code)."""
    di_label = member.get("label")
    di_label_bounds = None
    if isinstance(di_label, dict):
        di_label_bounds = _transcribe_bounds(di_label.get("bounds"))
        if di_label_bounds is None:
            return None, "render-stale"
    return _transcribe_label(scope, element, semantic_id, bounds, di_label_bounds)


def _member_edge(
    member: dict[str, Json],
    element: dict[str, Json],
    diagram_id: str,
    members: list[Json],
    waypoints: list[dict[str, int]] | None,
) -> tuple[dict[str, Json] | None, str | None]:
    """Resolve one edge member endpoints (endpoint record, code)."""
    source, target, edge_code = _resolve_edge_endpoints(member, element, diagram_id, members)
    if edge_code is not None:
        return None, edge_code
    if source is None or target is None or waypoints is None:
        return None, "render-unsupported"
    return {
        "sourceOccurrence": source,
        "targetOccurrence": target,
        "waypoints": waypoints,
    }, None


def _transcribe_member(
    scope: _LabelScope, diagram_id: str, member: Json, members: list[Json]
) -> tuple[dict[str, Json] | None, str | None]:
    """Transcribe one plane member to a geometry record (record, code)."""
    if not isinstance(member, dict):
        return None, "render-stale"
    semantic_id = member.get("bpmnElement")
    element = scope.by_id.get(semantic_id) if isinstance(semantic_id, str) else None
    if (
        not isinstance(semantic_id, str)
        or semantic_id not in scope.bearing
        or not isinstance(element, dict)
    ):
        return None, "render-stale"
    bounds, role, waypoints, code = _member_bounds(scope, member, member.get("$type"), semantic_id)
    if code is not None or bounds is None or role is None:
        return None, code or "render-stale"
    record: dict[str, Json] = {
        "pageId": diagram_id,
        "occurrenceKey": member.get("id"),
        "semanticId": semantic_id,
        "role": role,
        "bounds": bounds,
    }
    label, code = _member_label(scope, member, element, semantic_id, bounds)
    if code is not None:
        return None, code
    if label is not None:
        record["label"] = label
    if role == "edge":
        edge, code = _member_edge(member, element, diagram_id, members, waypoints)
        if code is not None or edge is None:
            return None, code or "render-unsupported"
        record.update(edge)
    return record, None


def _transcribe_diagram(
    scope: _LabelScope, order: int, diagram: Json
) -> tuple[dict[str, Json] | None, list[dict[str, Json]] | None, str | None]:
    """Transcribe one diagram to a page and its records (page, records, code)."""
    shaped, code = _check_diagram_shape(diagram, scope.bearing)
    if code is not None or shaped is None:
        return None, None, code or "render-stale"
    diagram_id, root_id, members = shaped
    name = diagram.get("name") if isinstance(diagram, dict) else None
    page_bounds: dict[str, int] | None = None
    records: list[dict[str, Json]] = []
    for member in members:
        record, code = _transcribe_member(scope, diagram_id, member, members)
        if code is not None or record is None:
            return None, None, code or "render-stale"
        records.append(record)
        page_bounds = _grow_bounds(
            page_bounds or {"x": 0, "y": 0, "width": 0, "height": 0},
            record["bounds"],
        )
        label = record.get("label")
        if isinstance(label, dict):
            page_bounds = _grow_bounds(page_bounds, label["bounds"])
    page = {
        "pageId": diagram_id,
        "name": name if isinstance(name, str) else "",
        "order": order,
        "semanticRootId": root_id,
        "bounds": page_bounds or {"x": 0, "y": 0, "width": 0, "height": 0},
    }
    return page, records, None


def _transcribe_imported_di(
    compiled: object,
    wire: dict[str, Json],
    placements: object,
    imported_di: object,
    view: _ThemeView,
) -> tuple[dict[str, Json] | None, str | None]:
    """Transcribe Snapshot/1 diagrams to base geometry (record, code)."""
    snapshot, code = _check_imported_di(imported_di, wire["profileIdentity"])
    if code is not None or snapshot is None:
        return None, code or "render-stale"
    tree = wire["tree"]
    if not isinstance(tree, dict):
        return None, "render-stale"
    by_id, _, bearing = index_tree(tree)
    bindings = wire.get("bindings")
    if not isinstance(bindings, list):
        return None, "render-stale"
    scope = _LabelScope(compiled, tree, view, placements, bindings, by_id, bearing)
    pages: list[dict[str, Json]] = []
    geometry: list[dict[str, Json]] = []
    for order, diagram in enumerate(snapshot["diagrams"]):
        page, records, code = _transcribe_diagram(scope, order, diagram)
        if code is not None or page is None or records is None:
            return None, code or "render-stale"
        pages.append(page)
        geometry.extend(records)
    order_of = {str(page.get("pageId")): int(page.get("order")) for page in pages}  # type: ignore[arg-type]
    geometry.sort(
        key=lambda record: (
            str(order_of.get(str(record.get("pageId")), 0)).encode("utf-16-be"),
            str(record.get("occurrenceKey")).encode("utf-16-be"),
        )
    )
    return {"layoutVersion": "1", "pages": pages, "geometry": geometry}, None


def _resolve_edge_endpoints(
    member: dict[str, Json],
    element: dict[str, Json],
    page_id: str,
    members: list[Json],
) -> tuple[dict[str, str] | None, dict[str, str] | None, str | None]:
    """Resolve one transcribed edge's endpoint occurrences (source, target, code)."""
    shapes = [
        entry
        for entry in members
        if isinstance(entry, dict) and entry.get("$type") == "bpmndi:BPMNShape"
    ]
    endpoints: list[dict[str, str]] = []
    for _position, di_key, semantic_key in (
        ("source", "sourceElement", "sourceRef"),
        ("target", "targetElement", "targetRef"),
    ):
        di_ref = member.get(di_key)
        match: dict[str, str] | None = None
        if isinstance(di_ref, str) and di_ref:
            for shape in shapes:
                if shape.get("id") == di_ref:
                    match = {"pageId": page_id, "occurrenceKey": str(shape.get("id"))}
                    break
            if match is None:
                return None, None, "render-unsupported"
        else:
            semantic_ref = _ref_id(element.get(semantic_key))
            candidates = [
                {"pageId": page_id, "occurrenceKey": str(shape.get("id"))}
                for shape in shapes
                if shape.get("bpmnElement") == semantic_ref and semantic_ref is not None
            ]
            if len(candidates) != 1:
                return None, None, "render-unsupported"
            match = candidates[0]
        endpoints.append(match)
    return endpoints[0], endpoints[1], None


def _check_placement_record(placement: object) -> bool:
    """Return whether one placement record is closed."""
    if not isinstance(placement, dict):
        return False
    keys = set(placement.keys())
    required = {"elementId", "ownerProcessId", "regionKey"}
    allowed = required | {"anchorAssociationId", "relatedAssociationIds"}
    if not required <= keys or keys - allowed:
        return False
    for key in ("elementId", "ownerProcessId", "regionKey"):
        if not isinstance(placement.get(key), str):
            return False
    anchor = placement.get("anchorAssociationId")
    if "anchorAssociationId" in placement and (not isinstance(anchor, str) or not anchor):
        return False
    related = placement.get("relatedAssociationIds")
    return "relatedAssociationIds" not in placement or (
        isinstance(related, list) and all(isinstance(entry, str) for entry in related)
    )


def _check_placements(placements: object) -> bool:
    """Return whether placements are closed placement records."""
    if not isinstance(placements, list):
        return False
    return all(_check_placement_record(placement) for placement in placements)


def _chain_token(chain: list[dict[str, Json]], name: str) -> tuple[Json, bool]:
    """Resolve one token through a theme chain, nearest first (value, found)."""
    for theme in chain:
        tokens = theme.get("tokens")
        if not isinstance(tokens, list):
            continue
        for entry in tokens:
            if isinstance(entry, dict) and entry.get("name") == name:
                return entry.get("value"), True
    return None, False


def _region_tokens(
    chain: list[dict[str, Json]], region_key: str
) -> tuple[dict[str, int] | None, bool]:
    """Resolve the four row tokens of one region (tokens, missing)."""
    tokens: dict[str, int] = {}
    for name in ("headerWidth", "padding", "gap", "minHeight"):
        value, found = _chain_token(chain, f"region.{region_key}.{name}")
        if not found or not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return None, True
        tokens[name] = value
    return tokens, False


def _association_opposite(
    by_id: dict[str, Json], association_id: str, element_id: str
) -> str | None:
    """Return the association endpoint opposite one element (or None)."""
    association = by_id.get(association_id)
    if not isinstance(association, dict):
        return None
    endpoints = [_ref_id(association.get("sourceRef")), _ref_id(association.get("targetRef"))]
    others = [endpoint for endpoint in endpoints if endpoint is not None and endpoint != element_id]
    involved = [endpoint for endpoint in endpoints if endpoint == element_id]
    if not involved or len(others) != 1:
        return None
    return others[0]


def _region_support(
    staged: _StagedLayout, page_id: str, support_target: Json
) -> dict[str, Json] | None:
    """Find one page's region support record (or None)."""
    for record in staged.geometry:
        if record.get("pageId") == page_id and record.get("semanticId") == support_target:
            return record
    return None


def _region_page_items(
    region_placements: list[Json], page_id: str, staged: _StagedLayout
) -> tuple[list[dict[str, Json]] | None, str | None]:
    """Collect one page's region items with anchors (items, code)."""
    items: list[dict[str, Json]] = []
    for placement in region_placements:
        element_id = placement.get("elementId")
        for record in staged.geometry:
            if record.get("pageId") != page_id or record.get("semanticId") != element_id:
                continue
            bounds = record.get("bounds")
            if not isinstance(bounds, dict):
                return None, "render-stale"
            item: dict[str, Json] = {
                "elementId": element_id,
                "occurrenceKey": record.get("occurrenceKey"),
                "object": {"width": bounds.get("width"), "height": bounds.get("height")},
            }
            label = record.get("label")
            if isinstance(label, dict) and isinstance(label.get("bounds"), dict):
                label_bounds = label["bounds"]
                item["label"] = {
                    "width": label_bounds.get("width"),
                    "height": label_bounds.get("height"),
                }
            anchor_id = placement.get("anchorAssociationId")
            if isinstance(anchor_id, str) and anchor_id:
                opposite = _association_opposite(staged.by_id, anchor_id, str(element_id))
                if opposite is not None:
                    anchors = [
                        entry.get("bounds")
                        for entry in staged.geometry
                        if entry.get("pageId") == page_id and entry.get("semanticId") == opposite
                    ]
                    if len(anchors) == 1 and isinstance(anchors[0], dict):
                        item["anchor"] = anchors[0]
            items.append(item)
    return items, None


def _run_row_inputs(
    region_key: str,
    page_id: str,
    support: dict[str, Json],
    row_input: dict[str, Json],
    geometry: list[dict[str, Json]],
) -> tuple[set[tuple[str, str]] | None, str | None]:
    """Run one region row and apply it in place (moved, code)."""
    row = layout_regions(row_input)
    if isinstance(row, PureRefused):
        return None, str(row.code)
    payload = row.payload
    if not isinstance(payload, dict):
        return None, "render-stale"
    support["bounds"] = payload["body"]
    moved: set[tuple[str, str]] = set()
    for item in payload["items"]:
        for record in geometry:
            if (
                record.get("pageId") == page_id
                and record.get("occurrenceKey") == item["occurrenceKey"]
            ):
                record["bounds"] = item["bounds"]
                if "labelBounds" in item:
                    base_label = record.get("label")
                    if isinstance(base_label, dict):
                        record["label"] = {
                            "text": base_label.get("text"),
                            "bounds": item["labelBounds"],
                            "lines": base_label.get("lines"),
                        }
                record["role"] = region_key
                moved.add((page_id, str(item["occurrenceKey"])))
                break
    return moved, None


def _region_setup(
    inputs: _LayoutInputs, binding: dict[str, Json], region_key: str
) -> tuple[Json, list[Json], dict[str, Json] | None]:
    """Bundle one region row setup (support target, placements, tokens)."""
    owner = binding.get("ownerId")
    placements = inputs.placements if isinstance(inputs.placements, list) else []
    region_placements = [
        placement
        for placement in placements
        if isinstance(placement, dict)
        and placement.get("ownerProcessId") == owner
        and placement.get("regionKey") == region_key
    ]
    tokens, missing = _region_tokens(inputs.view.chain, region_key)
    return binding.get("targetId"), region_placements, None if missing else tokens


@dataclasses.dataclass
class _RegionRow:
    """One region row application over the staged pages."""

    region_key: str
    support_target: Json
    placements: list[Json]
    tokens: dict[str, Json]
    staged: _StagedLayout

    def run_page(
        self, page_id: str, page: dict[str, Json]
    ) -> tuple[set[tuple[str, str]] | None, str | None]:
        """Apply the row on one page (relocated delta, code)."""
        support = _region_support(self.staged, page_id, self.support_target)
        items, code = _region_page_items(self.placements, page_id, self.staged)
        if code is not None or items is None:
            return None, code or "render-stale"
        if not items:
            return None, None
        if support is None:
            return None, "render-region-missing"
        support_bounds = support.get("bounds")
        if not isinstance(support_bounds, dict):
            return None, "render-stale"
        return _run_row_inputs(
            self.region_key,
            page_id,
            support,
            {
                "page": page.get("bounds"),
                "body": support_bounds,
                "tokens": self.tokens,
                "items": items,
            },
            self.staged.geometry,
        )


def _apply_region_row(
    region_key: str,
    binding: dict[str, Json],
    inputs: _LayoutInputs,
    staged: _StagedLayout,
) -> tuple[set[tuple[str, str]], str | None]:
    """Apply one region row on every page holding its items (relocated, code)."""
    support_target, region_placements, tokens = _region_setup(inputs, binding, region_key)
    if not region_placements:
        return set(), None
    if tokens is None:
        return set(), "render-region-missing"
    runner = _RegionRow(region_key, support_target, region_placements, tokens, staged)
    relocated: set[tuple[str, str]] = set()
    for page_id, page in staged.pages_by_id.items():
        moved, code = runner.run_page(page_id, page)
        if code is not None:
            return set(), code
        if moved:
            relocated.update(moved)
    return relocated, None


def _round_half(total: int) -> int:
    """Round one doubled integer coordinate, ties to even."""
    half, odd = divmod(total, 2)
    if not odd:
        return half
    return half if half % 2 == 0 else half + 1


def _reroute_links(geometry: list[dict[str, Json]], relocated: set[tuple[str, str]]) -> None:
    """Route relocated links as two-point centre routes in place."""
    if not relocated:
        return
    final = {
        (str(record.get("pageId")), str(record.get("occurrenceKey"))): record for record in geometry
    }
    for record in geometry:
        if record.get("role") != "edge":
            continue
        source = record.get("sourceOccurrence")
        target = record.get("targetOccurrence")
        if not isinstance(source, dict) or not isinstance(target, dict):
            continue
        source_key = (str(source.get("pageId")), str(source.get("occurrenceKey")))
        target_key = (str(target.get("pageId")), str(target.get("occurrenceKey")))
        if source_key not in relocated and target_key not in relocated:
            continue
        source_box = final.get(source_key, {}).get("bounds")
        target_box = final.get(target_key, {}).get("bounds")
        if not isinstance(source_box, dict) or not isinstance(target_box, dict):
            continue
        waypoints = [
            {
                "x": _round_half(2 * int(source_box["x"]) + int(source_box["width"])),
                "y": _round_half(2 * int(source_box["y"]) + int(source_box["height"])),
            },
            {
                "x": _round_half(2 * int(target_box["x"]) + int(target_box["width"])),
                "y": _round_half(2 * int(target_box["y"]) + int(target_box["height"])),
            },
        ]
        record["waypoints"] = waypoints
        origin_x = min(point["x"] for point in waypoints)
        origin_y = min(point["y"] for point in waypoints)
        record["bounds"] = {
            "x": origin_x,
            "y": origin_y,
            "width": max(point["x"] for point in waypoints) - origin_x,
            "height": max(point["y"] for point in waypoints) - origin_y,
        }


def _glyph_by_id(chain: list[dict[str, Json]], glyph_id: str) -> dict[str, Json] | None:
    """Look one glyph id up through a theme chain (selected first)."""
    for theme in chain:
        glyphs = theme.get("glyphs")
        if not isinstance(glyphs, list):
            continue
        for glyph in glyphs:
            if isinstance(glyph, dict) and glyph.get("id") == glyph_id:
                return glyph
    return None


def _glyph_param(glyph: dict[str, Json], name: str) -> Json:
    """Read one template parameter value (None when absent)."""
    for entry in glyph.get("parameters", []):
        if isinstance(entry, dict) and entry.get("name") == name:
            return entry.get("value")
    return None


def _emit_synthetic_stripe(
    declaration: dict[str, Json],
    owner_id: str,
    page: dict[str, Json],
    inputs: _LayoutInputs,
    staged: _StagedLayout,
) -> tuple[dict[str, Json] | None, str | None]:
    """Emit one band-stripe record (record, code)."""
    region = declaration.get("region")
    support_target = None
    for binding in staged.bindings:
        if (
            isinstance(binding, dict)
            and binding.get("ownerId") == owner_id
            and binding.get("role") == region
        ):
            support_target = binding.get("targetId")
            break
    if support_target is None:
        return None, "render-region-missing"
    support_box = None
    for record in staged.geometry:
        if (
            record.get("pageId") == page.get("pageId")
            and record.get("semanticId") == support_target
        ):
            support_box = record.get("bounds")
            break
    if not isinstance(support_box, dict):
        return None, "render-region-missing"
    width = support_box.get("width")
    glyph = _glyph_by_id(inputs.view.chain, str(declaration.get("glyph")))
    if glyph is not None and glyph.get("template") == "band-stripe":
        stripe_width = _glyph_param(glyph, "stripeWidth")
        if (
            isinstance(stripe_width, int)
            and not isinstance(stripe_width, bool)
            and stripe_width >= 0
        ):
            width = min(stripe_width, width) if isinstance(width, int) else stripe_width
    return {
        "pageId": page.get("pageId"),
        "occurrenceKey": jcs([declaration.get("id"), owner_id, page.get("pageId")]),
        "role": declaration.get("role"),
        "bounds": {
            "x": support_box.get("x"),
            "y": support_box.get("y"),
            "width": width,
            "height": support_box.get("height"),
        },
    }, None


def _badge_node_box(
    inputs: _LayoutInputs, staged: _StagedLayout, page: dict[str, Json], owner_id: str, region: Json
) -> dict[str, Json] | None:
    """Resolve one badge anchor node box (None when missing)."""
    placements = inputs.placements if isinstance(inputs.placements, list) else []
    anchor_id = None
    for placement in placements:
        if (
            isinstance(placement, dict)
            and placement.get("elementId") == owner_id
            and placement.get("regionKey") == region
        ):
            candidate = placement.get("anchorAssociationId")
            if isinstance(candidate, str) and candidate:
                anchor_id = candidate
                break
    if anchor_id is None:
        return None
    opposite = _association_opposite(staged.by_id, anchor_id, owner_id)
    node_box = None
    if opposite is not None:
        matches = [
            entry.get("bounds")
            for entry in staged.geometry
            if entry.get("pageId") == page.get("pageId") and entry.get("semanticId") == opposite
        ]
        if len(matches) == 1 and isinstance(matches[0], dict):
            node_box = matches[0]
    if node_box is None:
        return None
    return node_box


def _badge_glyph_box(
    chain: list[dict[str, Json]], declaration: dict[str, Json]
) -> tuple[tuple[int, int, int, int] | None, str | None]:
    """Validate one badge glyph box (width, height, dx, dy; code)."""
    glyph = _glyph_by_id(chain, str(declaration.get("glyph")))
    if glyph is None:
        return None, "render-region-missing"
    view_box = glyph.get("viewBox")
    if not isinstance(view_box, list) or len(view_box) != 4:
        return None, "render-region-missing"
    if bool(_glyph_param(glyph, "hideSource")):
        return None, "render-unsupported"
    offset_x = _glyph_param(glyph, "offsetX")
    offset_y = _glyph_param(glyph, "offsetY")
    if not isinstance(offset_x, int) or not isinstance(offset_y, int):
        return None, "render-region-missing"
    badge_width = int(view_box[2]) * 1000
    badge_height = int(view_box[3]) * 1000
    return (badge_width, badge_height, offset_x, offset_y), None


def _emit_synthetic_badge(
    declaration: dict[str, Json],
    owner_id: str,
    page: dict[str, Json],
    inputs: _LayoutInputs,
    staged: _StagedLayout,
) -> tuple[dict[str, Json] | None, str | None]:
    """Emit one attached-badge record (record, code)."""
    node_box = _badge_node_box(inputs, staged, page, owner_id, declaration.get("region"))
    if node_box is None:
        return None, "render-region-missing"
    box, code = _badge_glyph_box(inputs.view.chain, declaration)
    if code is not None or box is None:
        return None, code or "render-region-missing"
    if not isinstance(node_box.get("x"), int) or not isinstance(node_box.get("y"), int):
        return None, "render-region-missing"
    badge_width, badge_height, offset_x, offset_y = box
    return {
        "pageId": page.get("pageId"),
        "occurrenceKey": jcs([declaration.get("id"), owner_id, page.get("pageId")]),
        "role": declaration.get("role"),
        "bounds": {
            "x": int(node_box["x"]) + offset_x,
            "y": int(node_box["y"]) + int(node_box["height"]) + offset_y,
            "width": badge_width,
            "height": badge_height,
        },
    }, None


def _synthetic_owner_text(
    inputs: _LayoutInputs,
    staged: _StagedLayout,
    declaration: dict[str, Json],
    element: dict[str, Json],
) -> tuple[str | None, str | None]:
    """Evaluate one synthetic owner label (text, code)."""
    ast = declaration.get("label")
    if ast is None:
        return None, None
    return evaluate_label_value(inputs.compiled, staged.tree, ast, element, staged.bindings)


@dataclasses.dataclass(frozen=True)
class _SyntheticEmission:
    """One synthetic record emission on one page."""

    declaration: dict[str, Json]
    owner_id: str
    page: dict[str, Json]
    text: str | None


def _emit_synthetic_record(
    inputs: _LayoutInputs, staged: _StagedLayout, emission: _SyntheticEmission
) -> str | None:
    """Emit one synthetic record on one page (code)."""
    declaration = emission.declaration
    role = declaration.get("role")
    if role == "band-stripe":
        record, code = _emit_synthetic_stripe(
            declaration, emission.owner_id, emission.page, inputs, staged
        )
    elif role == "attached-badge":
        record, code = _emit_synthetic_badge(
            declaration, emission.owner_id, emission.page, inputs, staged
        )
    else:
        return "render-region-missing"
    if code is not None:
        return code
    if record is None:
        return "render-region-missing"
    if emission.text is not None:
        record["label"] = {
            "text": emission.text,
            "bounds": dict(record["bounds"]),
            "lines": emission.text.split("\n"),
        }
    staged.geometry.append(record)
    return None


def _synthetic_owner_pages(
    inputs: _LayoutInputs,
    staged: _StagedLayout,
    declaration: dict[str, Json],
    owner_id: str,
    text: str | None,
) -> str | None:
    """Emit one synthetic declaration for one owner on every page (code)."""
    for page in staged.pages:
        represented = page.get("semanticRootId") == owner_id or any(
            record.get("pageId") == page.get("pageId") and record.get("semanticId") == owner_id
            for record in staged.geometry
        )
        if not represented:
            continue
        emission = _SyntheticEmission(declaration, owner_id, page, text)
        code = _emit_synthetic_record(inputs, staged, emission)
        if code is not None:
            return code
    return None


def _apply_synthetics(  # noqa: C901, PLR0911
    inputs: _LayoutInputs, staged: _StagedLayout
) -> str | None:
    """Emit the selected theme synthetic occurrences in place (code)."""
    declarations = inputs.view.theme.get("syntheticOccurrences", [])
    if not isinstance(declarations, list) or not declarations:
        return None
    context = _read_context_for(inputs.compiled, staged.tree, staged.bindings)
    for declaration in declarations:
        if not isinstance(declaration, dict):
            return "render-region-missing"
        selector = declaration.get("select")
        try:
            owners = select(selector, context, {"root": staged.tree})
        except Exception:  # noqa: BLE001 - selection stays total
            return "profile-type"
        if isinstance(owners, PureRefused):
            return str(owners.code)
        handles = owners.payload if isinstance(owners.payload, list) else []
        for handle in handles:
            element = handle.element
            if not isinstance(element, dict):
                continue
            owner_id = element.get("id")
            if not isinstance(owner_id, str) or not owner_id:
                continue
            text, code = _synthetic_owner_text(inputs, staged, declaration, element)
            if code is not None:
                return code
            code = _synthetic_owner_pages(inputs, staged, declaration, owner_id, text)
            if code is not None:
                return code
    return None


def _grow_page_bounds(
    base_bounds: dict[str, Json], geometry: list[dict[str, Json]], page_id: str
) -> dict[str, int]:
    """Grow one page bounds over its final geometry and label bounds."""
    origin_x = int(base_bounds["x"])
    origin_y = int(base_bounds["y"])
    far_x = origin_x + int(base_bounds["width"])
    far_y = origin_y + int(base_bounds["height"])
    for record in geometry:
        if record.get("pageId") != page_id:
            continue
        for box in (
            record.get("bounds"),
            (record.get("label") or {}).get("bounds")
            if isinstance(record.get("label"), dict)
            else None,
        ):
            if not isinstance(box, dict):
                continue
            origin_x = min(origin_x, int(box["x"]))
            origin_y = min(origin_y, int(box["y"]))
            far_x = max(far_x, int(box["x"]) + int(box["width"]))
            far_y = max(far_y, int(box["y"]) + int(box["height"]))
    return {"x": origin_x, "y": origin_y, "width": far_x - origin_x, "height": far_y - origin_y}


def layout(
    compiled: object,
    envelope: object,
    placements: object,
    base_geometry: object,
    *,
    theme_id: str,
) -> ResultSuccess | ResultRefused:
    """Apply regions, links and synthetics over one base geometry."""
    wire, echo_identity, echo_revision, refused = _begin_operation("layout", compiled, envelope)
    if refused is not None:
        return refused
    if wire is None:
        return refused_result("layout", "render-stale", echo_identity, echo_revision)
    if not isinstance(base_geometry, dict):
        return refused_result("layout", "render-stale", echo_identity, echo_revision)
    theme, resolved_id, chain, theme_refused = _resolve_operation_theme(
        "layout", compiled, theme_id, echo_identity, echo_revision
    )
    if theme_refused is not None:
        return theme_refused
    if theme is None or resolved_id is None or chain is None:
        return refused_result("layout", "render-stale", echo_identity, echo_revision)
    inputs = _LayoutInputs(
        "layout",
        compiled,
        wire,
        placements,
        base_geometry,
        _ThemeView(theme, chain),
        echo_identity,
        echo_revision,
    )
    return _run_layout(inputs)


def _stage_geometry(inputs: _LayoutInputs) -> tuple[_StagedLayout | None, str | None]:
    """Validate and stage one base geometry (staged, code)."""
    base = inputs.base_geometry
    if not isinstance(base, dict) or not check_layout_record(base):
        return None, "render-stale"
    if not _check_placements(inputs.placements):
        return None, "render-stale"
    tree = inputs.wire["tree"]
    if not isinstance(tree, dict):
        return None, "render-stale"
    by_id, _, bearing = index_tree(tree)
    bindings = inputs.wire.get("bindings")
    if not isinstance(bindings, list):
        return None, "render-stale"
    geometry = [copy.deepcopy(record) for record in base["geometry"]]
    pages = [copy.deepcopy(page) for page in base["pages"]]
    return _StagedLayout(
        tree,
        bindings,
        by_id,
        bearing,
        geometry,
        pages,
        {str(page.get("pageId")): page for page in pages},
    ), None


def _check_staged_endpoints(staged: _StagedLayout) -> str | None:
    """Check staged semantic ids and edge endpoints resolve (code)."""
    for record in staged.geometry:
        semantic_id = record.get("semanticId")
        if semantic_id is not None and semantic_id not in staged.bearing:
            return "render-stale"
    known = {
        (str(record.get("pageId")), str(record.get("occurrenceKey"))) for record in staged.geometry
    }
    for record in staged.geometry:
        for key in ("sourceOccurrence", "targetOccurrence"):
            endpoint = record.get(key)
            if endpoint is not None and (
                not isinstance(endpoint, dict)
                or (str(endpoint.get("pageId")), str(endpoint.get("occurrenceKey"))) not in known
            ):
                return "render-stale"
    return None


def _find_region_binding(bindings: list[Json], owner: Json, region: Json) -> dict[str, Json] | None:
    """Find one region support binding (or None)."""
    for entry in bindings:
        if (
            isinstance(entry, dict)
            and entry.get("ownerId") == owner
            and entry.get("role") == region
        ):
            return entry
    return None


def _mark_attached_role(
    inputs: _LayoutInputs, staged: _StagedLayout, placement: dict[str, Json], region: Json
) -> str | None:
    """Mark attached-region records with their region (code)."""
    _, attached = _placement_region_key(placement, staged.bindings, inputs.view.theme)
    if not attached:
        return "render-region-missing"
    for record in staged.geometry:
        if record.get("semanticId") == placement.get("elementId"):
            record["role"] = region
    return None


def _apply_region_phase(
    inputs: _LayoutInputs, staged: _StagedLayout
) -> tuple[set[tuple[str, str]] | None, str | None]:
    """Apply every region row once per owner and region (relocated, code)."""
    relocated: set[tuple[str, str]] = set()
    seen_regions: set[tuple[Json, Json]] = set()
    placements = inputs.placements if isinstance(inputs.placements, list) else []
    for placement in placements:
        if not isinstance(placement, dict):
            continue
        owner = placement.get("ownerProcessId")
        region = placement.get("regionKey")
        if (owner, region) in seen_regions:
            continue
        seen_regions.add((owner, region))
        binding = _find_region_binding(staged.bindings, owner, region)
        if binding is None:
            code = _mark_attached_role(inputs, staged, placement, region)
            if code is not None:
                return None, code
            continue
        moved, code = _apply_region_row(str(region), binding, inputs, staged)
        if code is not None or moved is None:
            return None, code or "render-stale"
        relocated.update(moved)
    return relocated, None


def _finish_layout(
    inputs: _LayoutInputs, staged: _StagedLayout, order_of: dict[str, int]
) -> ResultSuccess:
    """Sort, grow and assemble one staged layout."""
    staged.geometry.sort(
        key=lambda record: (
            str(order_of.get(str(record.get("pageId")), 0)).encode("utf-16-be"),
            str(record.get("occurrenceKey")).encode("utf-16-be"),
        )
    )
    for page in staged.pages:
        page["bounds"] = _grow_page_bounds(page["bounds"], staged.geometry, str(page.get("pageId")))
    final = {"layoutVersion": "1", "pages": staged.pages, "geometry": staged.geometry}
    report = report_with_header(
        inputs.operation, inputs.echo_identity or {}, inputs.echo_revision or ""
    )
    return ResultSuccess(
        operation=inputs.operation,
        profile_identity=copy.deepcopy(inputs.echo_identity)
        if inputs.echo_identity is not None
        else {},
        base_revision=inputs.echo_revision or "",
        revision=inputs.echo_revision or "",
        report=report,
        payload=final,
    )


def _run_layout(inputs: _LayoutInputs) -> ResultSuccess | ResultRefused:
    """Run the shared base-geometry seam under one operation name."""
    staged, code = _stage_geometry(inputs)
    if code is not None or staged is None:
        return refused_result(
            inputs.operation, code or "render-stale", inputs.echo_identity, inputs.echo_revision
        )
    code = _check_staged_endpoints(staged)
    if code is not None:
        return refused_result(inputs.operation, code, inputs.echo_identity, inputs.echo_revision)
    relocated, code = _apply_region_phase(inputs, staged)
    if code is not None or relocated is None:
        return refused_result(
            inputs.operation, code or "render-stale", inputs.echo_identity, inputs.echo_revision
        )
    _reroute_links(staged.geometry, relocated)
    order_of = {str(page.get("pageId")): int(page.get("order")) for page in staged.pages}  # type: ignore[arg-type]
    synthetic_code = _apply_synthetics(inputs, staged)
    if synthetic_code is not None:
        return refused_result(
            inputs.operation, synthetic_code, inputs.echo_identity, inputs.echo_revision
        )
    return _finish_layout(inputs, staged, order_of)
