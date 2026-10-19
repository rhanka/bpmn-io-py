"""Synchronous export preparation pipeline (DESIGN R3.3 §10.2, spec §12)."""

from __future__ import annotations

import copy
import importlib
from collections.abc import Callable
from dataclasses import replace
from functools import partial
from typing import Any

from bpmn_io.codec.json import hydrate
from bpmn_io.profile._export import ADAPTERS, map_export
from bpmn_io.profile._layout import _placement_region_key, compute_layout
from bpmn_io.profile._lint import lint
from bpmn_io.profile._render import resolve_theme
from bpmn_io.profile._results import (
    PureRefused,
    ReportEntry,
    ResultRefused,
    ResultSuccess,
    refused_result,
    report_with_header,
    sort_report_entries,
)
from bpmn_io.profile._serialize import _entry_from_json
from bpmn_io.profile._themes import check_compatibility_gate, envelope_echo, resolve_theme_id


def _lot3_function(module_name: str, function_name: str) -> Json:
    """Load one lot-3 function (absent until the lots merge at integration)."""
    module = importlib.import_module(f"bpmn_io.profile.{module_name}")
    return getattr(module, function_name)


Json = Any

#: Observer called with each stage name before that stage runs.
PrepareObserver = Callable[[str], None]

_PREPARE_OPERATION = "prepareExport"

#: The twelve §12.1 stages in pipeline order.
PREPARE_STAGES = (
    "options",
    "compatibility",
    "graph",
    "complete",
    "pre-normalize",
    "normalize",
    "post-normalize",
    "layout",
    "post-layout",
    "release",
    "render",
    "map",
)

_LINT_STAGES = ("pre-normalize", "post-normalize", "post-layout", "release")

_OPTIONS_REQUIRED = ("format", "themeId", "overrides", "diStyles")
_OPTIONS_KNOWN = ("format", "themeId", "overrides", "diStyles", "importedDi")


def describe_prepare_stages() -> tuple[str, ...]:
    """Return the twelve §12.1 stage names in pipeline order."""
    return PREPARE_STAGES


def _copy(value: Json) -> Json:
    return copy.deepcopy(value)


def _take_entries(entries: object) -> list[ReportEntry]:
    """Take owned ReportEntry objects (shared, they are immutable)."""
    taken: list[ReportEntry] = []
    if isinstance(entries, (list, tuple)):
        for record in entries:
            if isinstance(record, ReportEntry):
                taken.append(record)
                continue
            entry = _entry_from_json(record)
            if entry is not None:
                taken.append(entry)
    return taken


class _Run:
    """Mutable pipeline state for one ``run_pipeline`` call."""

    def __init__(
        self,
        compiled: object,
        envelope: object,
        options: object,
        observer: PrepareObserver | None,
    ) -> None:
        self.compiled = compiled
        self.options = options if isinstance(options, dict) else None
        self.observer = observer
        wire = envelope.to_json() if hasattr(envelope, "to_json") else envelope
        self.staged: Json = _copy(wire)
        self.echo_identity: dict[str, object] | None = None
        self.echo_revision: str | None = None
        self.identity: dict[str, object] = {}
        self.revision = ""
        self.theme: dict[str, Json] = {}
        self.theme_id = ""
        self.format = ""
        self.placements: Json = None
        self.layout: Json = None
        self.render: Json = None
        self.prepared: Json = None
        self.map_id_map: list[Json] = []
        self.map_artifact: dict[str, Json] = {}
        self.c_entries: list[ReportEntry] = []
        self.n_entries: list[ReportEntry] = []
        self.r_entries: list[ReportEntry] = []
        self.export_entries: list[ReportEntry] = []
        self.lint_entries: list[ReportEntry] = []
        self.deferred: list[int] = []
        self.deferred_recipes: list[str] = []
        self.raw_findings: dict[str, list[Json]] = {}
        self.read_echo(wire)

    def read_echo(self, envelope: object) -> None:
        """Capture the §3.4 refusal echo from the input envelope."""
        identity, revision = envelope_echo(envelope)
        if identity is not None and revision is not None:
            self.echo_identity = _copy(identity)
            self.echo_revision = revision

    def observe(self, name: str) -> None:
        """Notify the observer that one stage is about to run."""
        if self.observer is not None:
            self.observer(name)

    def refuse(self, code: str) -> ResultRefused:
        """Refuse with the §3.4 record: lint findings so far, no change entries."""
        return refused_result(
            _PREPARE_OPERATION,
            code,
            self.echo_identity,
            self.echo_revision,
            sort_report_entries(self.lint_entries),
        )


def _read_staged_revision(run: _Run) -> None:
    if isinstance(run.staged, dict):
        identity = run.staged.get("profileIdentity")
        revision = run.staged.get("semanticRevision")
        if isinstance(identity, dict):
            run.identity = _copy(identity)
        if isinstance(revision, str):
            run.revision = revision


def _run_options(run: _Run) -> str | None:
    """Run stage 1 (options): closed record, registered format, resolvable theme."""
    run.observe("options")
    options = run.options
    if options is None:
        return "operation-error"
    for key in options:
        if key not in _OPTIONS_KNOWN:
            return "operation-error"
    for key in _OPTIONS_REQUIRED:
        if options.get(key) is None:
            return "operation-error"
    format_value = options.get("format")
    profile = getattr(run.compiled, "profile", None)
    profile_dict = profile if isinstance(profile, dict) else {}
    records = profile_dict.get("exports")
    declared = (
        any(isinstance(record, dict) and record.get("format") == format_value for record in records)
        if isinstance(records, list)
        else False
    )
    if not declared or format_value not in ADAPTERS:
        return "export-format-unsupported"
    return _resolve_options_theme(run, profile_dict)


def _resolve_options_theme(run: _Run, profile: dict[str, Json]) -> str | None:
    """Resolve the options theme id or alias (else ``render-stale``)."""
    if run.options is None:
        return "operation-error"
    theme_id = run.options.get("themeId")
    theme, _resolved = resolve_theme_id(profile, theme_id if isinstance(theme_id, str) else "")
    if theme is None:
        return "render-stale"
    run.theme = theme
    run.theme_id = theme_id if isinstance(theme_id, str) else ""
    format_value = run.options.get("format")
    run.format = format_value if isinstance(format_value, str) else ""
    return None


def _run_compat(run: _Run) -> str | None:
    """Run stage 2 (compatibility) as §4.2.1."""
    run.observe("compatibility")
    identity = run.staged.get("profileIdentity") if isinstance(run.staged, dict) else None
    if not isinstance(identity, dict):
        return "operation-error"
    return check_compatibility_gate(run.compiled, identity)


def _run_graph(run: _Run) -> str | None:
    """Run stage 3 (graph): the lot-3 envelope and graph checks."""
    run.observe("graph")
    create_read_context = _lot3_function("_cn_context", "create_read_context")
    context = create_read_context(run.compiled, run.staged, stage="load")
    if isinstance(context, PureRefused):
        return context.code
    return None


def _run_complete(run: _Run) -> str | None:
    """Run stage 4 (complete): retained completion over the staged copy."""
    run.observe("complete")
    lot3_complete = _lot3_function("_cn_complete", "complete")
    result = lot3_complete(run.compiled, run.staged, "retained", activation="edit")
    if isinstance(result, ResultRefused):
        return result.code
    if isinstance(result.payload, dict):
        run.staged = _copy(result.payload)
    _read_staged_revision(run)
    run.c_entries = _take_entries(result.report.entries)
    return None


def _staged_bindings(run: _Run) -> list[Json] | None:
    if isinstance(run.staged, dict):
        bindings = run.staged.get("bindings")
        if isinstance(bindings, list):
            return list(bindings)
    return None


def _run_lint(run: _Run, name: str) -> str | None:
    """Run one lint stage, deferring repairable pre-normalize errors."""
    run.observe(name)
    root = _hydrate_for_lint(run, name)
    if root is None:
        return "operation-error"
    unified = lint(
        root,  # type: ignore[arg-type]
        run.compiled,  # type: ignore[arg-type]
        phase=name,
        readiness_policy="accept",
        bindings=_staged_bindings(run),
    )
    report = unified.get("report") if isinstance(unified, dict) else None
    raw_entries = report.get("entries") if isinstance(report, dict) else None
    raw_list = list(raw_entries) if isinstance(raw_entries, list) else []
    raw_findings = report.get("rawStandardFindings") if isinstance(report, dict) else None
    run.raw_findings[name] = list(raw_findings) if isinstance(raw_findings, list) else []
    if name == "post-normalize":
        _resolve_deferred(run)
    if name == "pre-normalize":
        _defer_repairable(run, raw_list)
    else:
        run.lint_entries.extend(_take_entries(raw_list))
    return _first_unresolved(run, name)


def _defer_repairable(run: _Run, raw_list: list[Json]) -> None:
    """Append pre-normalize findings, deferring repairable errors with a recipe."""
    recipes = getattr(run.compiled, "recipes", None)
    for raw in raw_list:
        entry = _entry_from_json(raw)
        if entry is None:
            continue
        run.lint_entries.append(entry)
        if entry.severity != "error" or entry.disposition != "observed":
            continue
        if entry.classification != "repairable":
            continue
        recipe = raw.get("repairRecipe") if isinstance(raw, dict) else None
        if not isinstance(recipe, str) or not recipe:
            continue
        if isinstance(recipes, dict):
            record = recipes.get(recipe)
            if not isinstance(record, dict) or record.get("phase") != "normalize":
                continue
        run.deferred.append(len(run.lint_entries) - 1)
        run.deferred_recipes.append(recipe)


def _resolve_deferred(run: _Run) -> None:
    """Mark deferred pre-normalize findings corrected where N applied the recipe."""
    for index, recipe in zip(sorted(run.deferred), run.deferred_recipes, strict=True):
        if index >= len(run.lint_entries):
            continue
        entry = run.lint_entries[index]
        if _normalize_applied(run, recipe, entry):
            run.lint_entries[index] = replace(entry, disposition="corrected")
    run.deferred = []
    run.deferred_recipes = []


def _normalize_applied(run: _Run, recipe: str, entry: ReportEntry) -> bool:
    """Return whether N applied a change entry of the recipe on the finding target."""
    for change in run.n_entries:
        if change.rule_id != recipe:
            continue
        if change.result.target_id != entry.source.target_id:
            continue
        return True
    return False


def _first_unresolved(run: _Run, name: str) -> str | None:
    """Return the code of the first unresolved error entry in report order."""
    deferred = set(run.deferred)
    candidates = [
        entry
        for index, entry in enumerate(run.lint_entries)
        if index not in deferred
        and (entry.stage == name or (name == "post-normalize" and entry.stage == "pre-normalize"))
    ]
    unresolved = [
        entry
        for entry in candidates
        if entry.severity == "error" and entry.disposition == "observed"
    ]
    ordered = sort_report_entries(unresolved)
    return ordered[0].code if ordered else None


def _run_normalize(run: _Run) -> str | None:
    """Run stage 6 (normalize) with no placement intent."""
    run.observe("normalize")
    lot3_normalize = _lot3_function("_cn_normalize", "normalize")
    result = lot3_normalize(run.compiled, run.staged, None, activation="edit")
    if isinstance(result, ResultRefused):
        return result.code
    payload = result.payload if isinstance(result.payload, dict) else {}
    envelope_value = payload.get("envelope")
    if isinstance(envelope_value, dict):
        run.staged = _copy(envelope_value)
    _read_staged_revision(run)
    run.placements = _copy(payload.get("placements"))
    run.n_entries = _take_entries(result.report.entries)
    return None


def _run_layout(run: _Run) -> str | None:
    """Run stage 8 (layout): support gate, imported DI, then compute the layout."""
    run.observe("layout")
    if isinstance(run.placements, list) and isinstance(run.staged, dict):
        bindings = run.staged.get("bindings")
        candidates = list(bindings) if isinstance(bindings, list) else []
        for placement in run.placements:
            if not isinstance(placement, dict):
                continue
            binding, attached = _placement_region_key(placement, candidates, run.theme)
            if binding is None and not attached:
                return "profile-open"
    imported_di = run.options.get("importedDi") if run.options is not None else None
    if imported_di is None:
        return "operation-error"
    result = compute_layout(
        run.compiled,
        run.staged,
        _copy(run.placements),
        _copy(imported_di),
        theme_id=run.theme_id,
    )
    if isinstance(result, ResultRefused):
        return result.code
    run.layout = _copy(result.payload)
    return None


def _hydrate_for_lint(run: _Run, name: str) -> object | None:
    """Hydrate the staged tree, with Layout/1-derived BPMNDI for post-layout."""
    if not isinstance(run.staged, dict):
        return None
    tree = _copy(run.staged.get("tree"))
    if not isinstance(tree, dict):
        return None
    if name in ("post-layout", "release") and isinstance(run.layout, dict):
        overlay = _layout_di_overlay(run.layout)
        if overlay is None:
            return None
        existing = tree.get("diagrams")
        tree["diagrams"] = [*existing, *overlay] if isinstance(existing, list) else overlay
    hydrated = hydrate(tree)
    if not hydrated.ok:
        return None
    value: object = hydrated.value
    return value


def _layout_di_overlay(layout: dict[str, Json]) -> list[Json] | None:
    """Derive BPMNDI diagrams from one Layout/1 (ticks / 1000 as DI units)."""
    pages = layout.get("pages")
    geometry = layout.get("geometry")
    if not isinstance(pages, list) or not isinstance(geometry, list):
        return None
    by_page: dict[str, list[Json]] = {}
    for record in geometry:
        if not isinstance(record, dict):
            continue
        page_id = record.get("pageId")
        if not isinstance(page_id, str):
            continue
        element = _di_element(record, page_id)
        if element is None:
            continue
        by_page.setdefault(page_id, []).append(element)
    diagrams: list[Json] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_id = page.get("pageId")
        root_id = page.get("semanticRootId")
        if not isinstance(page_id, str) or not isinstance(root_id, str):
            continue
        diagrams.append(
            {
                "$type": "bpmndi:BPMNDiagram",
                "id": f"di-{page_id}",
                "plane": {
                    "$type": "bpmndi:BPMNPlane",
                    "id": f"di-{page_id}-plane",
                    "bpmnElement": root_id,
                    "planeElement": by_page.get(page_id, []),
                },
            }
        )
    return diagrams


def _di_element(record: dict[str, Json], page_id: str) -> dict[str, Json] | None:
    """Build one BPMNShape or BPMNEdge from a Layout/1 geometry record."""
    occurrence = record.get("occurrenceKey")
    semantic_id = record.get("semanticId")
    bounds = _di_bounds(record.get("bounds"))
    if not isinstance(occurrence, str) or not isinstance(semantic_id, str) or bounds is None:
        return None
    element_id = f"di-{page_id}-{occurrence}"
    # DESIGN §9 edge rule is presence-based (both role vocabularies sealed).
    if "sourceOccurrence" in record or "targetOccurrence" in record:
        waypoints = record.get("waypoints")
        points = [_di_point(point) for point in waypoints] if isinstance(waypoints, list) else []
        if any(point is None for point in points):
            return None
        return {
            "$type": "bpmndi:BPMNEdge",
            "id": element_id,
            "bpmnElement": semantic_id,
            "waypoint": [point for point in points if point is not None],
        }
    return {
        "$type": "bpmndi:BPMNShape",
        "id": element_id,
        "bpmnElement": semantic_id,
        "bounds": bounds,
    }


def _di_bounds(bounds: Json) -> dict[str, Json] | None:
    """Scale one integer-tick bounds record to DI units."""
    if not isinstance(bounds, dict):
        return None
    values: dict[str, Json] = {}
    for key in ("x", "y", "width", "height"):
        value = bounds.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        values[key] = value / 1000
    return {"$type": "dc:Bounds", **values}


def _di_point(point: Json) -> dict[str, Json] | None:
    """Scale one integer-tick waypoint to DI units."""
    if not isinstance(point, dict):
        return None
    scaled: dict[str, Json] = {}
    for key in ("x", "y"):
        value = point.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        scaled[key] = value / 1000
    return {"$type": "dc:Point", **scaled}


def _run_render(run: _Run) -> str | None:
    """Run stage 11 (render): resolve the theme over the layout."""
    run.observe("render")
    result = resolve_theme(
        run.compiled,
        run.staged,
        _copy(run.layout),
        run.theme_id,
        _copy(run.options.get("overrides")) if run.options is not None else {},
        _copy(run.options.get("diStyles")) if run.options is not None else {},
    )
    if isinstance(result, ResultRefused):
        return result.code
    run.render = _copy(result.payload)
    run.r_entries = _take_entries(result.report.entries)
    return None


def _run_map(run: _Run) -> str | None:
    """Run stage 12 (map): map the RenderData/1 to a PreparedArtifact."""
    run.observe("map")
    result = map_export(run.compiled, run.staged, _copy(run.layout), _copy(run.render), run.format)
    if isinstance(result, ResultRefused):
        return result.code
    if isinstance(result.payload, dict):
        run.prepared = _copy(result.payload)
    run.export_entries = _take_entries(result.report.entries)
    run.map_id_map = [item for item in result.report.id_map if isinstance(item, dict)]
    artifacts = result.report.artifacts
    if artifacts and isinstance(artifacts[0], dict):
        run.map_artifact = dict(artifacts[0])
    return None


def _assemble_success(run: _Run) -> ResultSuccess:
    """Assemble the §12.2 success record with the complete report."""
    if not isinstance(run.prepared, dict):
        msg = "prepared artifact missing"
        raise TypeError(msg)
    entries = sort_report_entries(
        [*run.c_entries, *run.lint_entries, *run.n_entries, *run.r_entries, *run.export_entries]
    )
    artifact: dict[str, Json] = dict(run.map_artifact) if run.map_artifact else {"digest": ""}
    artifact["format"] = run.format
    artifact["entryIndexes"] = list(range(len(entries)))
    if "capability" not in artifact and isinstance(run.prepared.get("capability"), str):
        artifact["capability"] = run.prepared.get("capability")
    raw = [finding for name in _LINT_STAGES for finding in run.raw_findings.get(name, [])]
    report = report_with_header(
        _PREPARE_OPERATION, run.identity, run.revision, entries, run.map_id_map, [artifact]
    )
    report = replace(report, raw_standard_findings=tuple(raw))
    payload = _copy(run.prepared)
    payload["report"] = report.to_json()
    return ResultSuccess(
        operation=_PREPARE_OPERATION,
        profile_identity=_copy(run.identity),
        base_revision=run.revision,
        revision=run.revision,
        report=report,
        payload=payload,
    )


_STAGE_RUNNERS: tuple[Callable[[_Run], str | None], ...] = (
    _run_options,
    _run_compat,
    _run_graph,
    _run_complete,
    partial(_run_lint, name="pre-normalize"),
    _run_normalize,
    partial(_run_lint, name="post-normalize"),
    _run_layout,
    partial(_run_lint, name="post-layout"),
    partial(_run_lint, name="release"),
    _run_render,
    _run_map,
)


def run_pipeline(
    compiled: object,
    envelope: object,
    options: object,
    *,
    observer: PrepareObserver | None = None,
) -> ResultSuccess | ResultRefused:
    """Run the twelve §12.1 stages on a staged deep copy, tracing stage names."""
    run = _Run(compiled, envelope, options, observer)
    for stage in _STAGE_RUNNERS:
        code = stage(run)
        if code is not None:
            return run.refuse(code)
    return _assemble_success(run)


def prepare_export(
    compiled: object, envelope: object, options: object
) -> ResultSuccess | ResultRefused:
    """Prepare one export artifact through the §12.1 pipeline without an observer."""
    return run_pipeline(compiled, envelope, options, observer=None)
