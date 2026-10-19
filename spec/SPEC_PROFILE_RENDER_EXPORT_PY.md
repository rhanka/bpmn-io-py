# SPEC PROFILE RENDER EXPORT PY — lot 4 Python binding (layout, R, themes, exporters)

Status: sealed binding contract for lot 4 of `bpmn_io.profile` (target 0.3.0, no
version bump in this lot), resealed in the single block-B seal fix round and again
in the block-B JS/Python parity sync (§22). This document adds no production code.
It binds the lot-4 sections of the design to Python signatures, closed shapes,
refusal codes and gates, and indexes the sealed expectation files under
`tests/profile_render/expected/` and `tests/profile_export/expected/`, including
the vendored JS lot-4 cases (§17.6).

Authority, in precedence order: DESIGN R3.3 (SHA-256
`48139f5fd5bd789eacbf271081a95432c54d8361b1e52404e3443a25fa65782f`) sections
§9.1–§9.5, §10.1 (results, coordinates, reports, idMap, artifacts), §10.2,
§2.2/§2.4 (selectors, `outputId`, `emit`, `loss`, `refuse`), §3.1 (H, B, rounding,
ticks), §6.2/§6.4 (preparation stages, repairable findings), §13 OPEN register and
§16 owner decisions (all eleven ratified 2026-10-14); then the block-B JS/Python
harmonization decisions (cited by their row id, for example "harmonization K2");
then the seal review findings. Where a review finding proved with a DESIGN line
that a harmonization decision contradicts DESIGN, DESIGN wins (§21.3). Pinned
contract bytes: `contracts/profile-mechanism/1/`. Binding predecessor:
`spec/SPEC_PROFILE_MECHANISM_PY.md` (signature table §6, result unions,
Report/2). Lot 3 (`complete`, `normalize`, placements, C/N change entries) is
consumed only through the lot-3 binding (`complete(compiled, envelope, mode, *,
activation)`, `normalize(compiled, envelope, placement_intent=None, *,
activation)`, C/N entry vocabulary). Where this spec and a pinned contract byte
disagree, the byte wins and the mismatch is an erratum.

Conventions. "DESIGN §x" means DESIGN R3.3 §x. JSON names are DESIGN's wire
names; Python functions are snake_case (`docs/naming.md`); case files use the
shared camelCase operation names (harmonization A4). Every computation is
synchronous. "ticks" are integer micro-point ticks (1 tick = 0.001 pt, DESIGN
§3.1). UTF-16 order means UTF-16 code-unit order of strings (`profile-c14n/2`).
`H(x)` and `B(bytes)` are the DESIGN §3.1 digests. "Refuses `c`" means the
operation returns its closed refusal union with `code == c` and no payload.

## 1. Module layout

New private modules under `src/bpmn_io/profile/` (names binding for review,
internal helpers free):

| Module | Content |
| --- | --- |
| `_render_tokens.py` | render-token/1 signatures, registry loading, token validation, Overrides/1 and DiStyles/1 normalization |
| `_render_digest.py` | §9.2 digest formulas, `render_digests`, `view_revision`, `verify_render_data` |
| `_text_metrics.py` | `measure_text` (scalar widths with declared fallback) |
| `_templates.py` | glyph shape checks (CR-09) and `template_geometry` for the four closed templates |
| `_regions.py` | `layout_ticks`, `layout_regions` (shared pure seams, §4.1) |
| `_layout.py` | `layout` (shared base-geometry seam, §4.2) and `compute_layout` (the Python DI adapter `generic-di-layout/1`, §4.3–§4.6) |
| `_themes.py` | theme and alias resolution, fallback chains, `check_theme_switch` (§14) |
| `_render.py` | `resolve_theme` producing RenderData/1, coverage, diagnostics |
| `_export_ir.py` | export-ir/1 field vocabulary (CR-11), symbol table, ID policies |
| `_export.py` | `map_export`, capability, loss mapping, idMap, artifacts |
| `_serialize.py` | `serialize_prepared` and the `drawio/1` structural serializer |
| `_prepare.py` | `prepare_export` orchestration and its stage observer seam (§12) |
| `_legacy.py` | `map_legacy_diagnostics` (legacy diagnostic adapter table, §13), `resolve_legacy_theme` |

Public names re-exported from `bpmn_io.profile` (and added to `__all__`):
`compute_layout`, `layout`, `layout_regions`, `layout_ticks`, `resolve_theme`,
`check_theme_switch`, `map_export`, `serialize_prepared`, `prepare_export`,
`render_digests`, `view_revision`, `verify_render_data`, `measure_text`,
`template_geometry`, `map_legacy_diagnostics`, `resolve_legacy_theme`,
`registry_from_json`. Stubs are regenerated with `scripts/gen_stubs.py`.

Additive changes to block-A types (backward compatible, defaults keep every
existing call valid):

- `ValidatedProfile` gains `assets: dict[str, bytes]` (resource `id` → raw bytes
  verified against the `resources[].sha256` pin through `asset_bag[assetKey]`;
  empty when no asset bag is supplied).
- `CompiledProfile` gains `profile: dict` (the complete validated profile JSON,
  deep-copied at the boundary), `identity: dict` (the closed §5.1
  `profileIdentity` record: `mechanismVersion, schemaVersion, profile, version,
  sha256 = H(profile), base, descriptors`; the same field the lot-3 binding
  requires), `assets` (copied from the validated profile) and `render_registry`
  (the render-token signatures of the `RegistrySet` used at compile time).
- `RegistrySet` gains `render_tokens: dict[str, dict]` (token name → JSON Schema
  signature), `region_token_pattern: str | None` and `region_token_schema: dict |
  None`. `registry_from_json(data) -> PureResult[RegistrySet]` returns the
  default block-A operator registry extended with the `renderTokens`,
  `regionTokenPattern` and `regionTokenSchema` of a pinned registry document
  (shape of `neutral-registry.json`). With the default registry (no render
  tokens) the generic DESIGN §9.3 signatures apply and no `fontFamily` or `dash`
  value is admitted (no injected family or registered style).

Every document operation of this lot (and lot 3) requires a profile compiled with
`descriptor_context` and `base` (the lot-3 binding refuses `descriptor-mismatch`
otherwise); §17 builds every sealed profile that way.

## 2. Signatures

Document operations return `Result/1` (`ResultSuccess | ResultRefused`, block A
`_results.py`); helpers return `PureResult`. Read-only operations set
`baseRevision == revision` (every Result/1 operation of this lot is read-only,
§3.5).

| Case operation (A4) | Python | Union | Inputs → payload |
| --- | --- | --- | --- |
| `computeLayout` | `compute_layout(compiled, envelope, placements, imported_di, *, theme_id)` | Result `"computeLayout"` | Layout/1 (Python DI adapter, runtime-specific) |
| `layout` | `layout(compiled, envelope, placements, base_geometry, *, theme_id)` | Result `"layout"` | Layout/1 (shared seam: base geometry → Layout/1) |
| `layoutRegions` | `layout_regions(region_input)` | PureResult | region output (§4.1) |
| `layoutTicks` | `layout_ticks(points)` | PureResult | integer ticks |
| `resolveTheme` (DESIGN) | `resolve_theme(compiled, envelope, layout, theme_id, overrides, di_styles)` | Result `"resolveTheme"` | RenderData/1 |
| `checkThemeSwitch` | `check_theme_switch(compiled, from_theme, to_theme)` | PureResult | `{"relayoutRequired": false}` |
| `mapExport` (DESIGN) | `map_export(compiled, envelope, layout, r, format)` | Result `"mapExport"` | PreparedArtifact |
| `serializePrepared` (DESIGN) | `serialize_prepared(prepared, pinned_writer_options)` | Result `"serializePrepared"` | `{format, bytes, digest, idMap, capability}` |
| `prepareExport` (DESIGN) | `prepare_export(compiled, envelope, options)` | Result `"prepareExport"` | PreparedArtifact |
| `renderDigests` | `render_digests(record)` | PureResult | digest record (§6.1) |
| — | `view_revision(binding)` | `str` | viewRevision |
| `verifyRenderData` | `verify_render_data(compiled, envelope, layout, r, theme_id, overrides, di_styles)` | PureResult | `{"viewRevision": str}` |
| `measureText` | `measure_text(metrics, text)` | PureResult | `{"lines", "width", "height"}` (runtime-specific, harmonization K17) |
| `templateGeometry` | `template_geometry(glyph, bounds, *, label_bounds=None, badge_size=None)` | PureResult | template geometry (§8.2) |
| `mapLegacyDiagnostics` | `map_legacy_diagnostics(legacy, manifest, *, source_index=None)` | PureResult | Report/2 entry list |
| `resolveLegacyTheme` | `resolve_legacy_theme(compiled, legacy_name)` | PureResult | `{"themeId": str}` |

Arguments: `compiled` is the extended `CompiledProfile`; `envelope` is a block-A
`DocumentEnvelope` or its DocumentEnvelope/1 wire mapping (the value lot-3
`complete`/`normalize` return); both forms are accepted and validated with block-A
`validate_envelope(..., committed=True)` before use (a mapping is never trusted
unvalidated); `placements` the DESIGN §7.2 placement records (lot-3 `normalize`
`payload.placements`); `imported_di` the Snapshot/1 `importedDi` record
`{descriptorDigest, diagrams, sha256}`; `base_geometry`, `layout`, `r`,
`overrides`, `di_styles`, `prepared` are the JSON records of §3; `format` is a
profile `exports[].format` value; `pinned_writer_options` is an
`exports[].serializer` record; `metrics` is the raw bytes of a metrics resource;
`glyph` a theme glyph record.

Errata against `spec/SPEC_PROFILE_MECHANISM_PY.md` §6 (each justified):

1. `prepare_export` options are the closed record `{format, themeId, overrides,
   diStyles, importedDi?}` (block-B parity sync PS-34). DESIGN §8.1 lists `{format,
   themeId, overrides, diStyles, signal?}`. `importedDi` (the Snapshot/1
   `importedDi` record) is the geometry source of a headless adapter: the Python DI
   adapter (§4.3) needs it at the layout stage, which the JS canvas serves from its
   live modeler; when it is absent there, the preparation refuses
   `operation-error` at that stage, never earlier (§12). `signal?` is a JS-only
   runtime member, never written in a corpus file; Python is synchronous, so
   `signal` is an unknown member there and refuses `operation-error` at the
   options stage (runtime-specific, §17.5).
2. `compute_layout`, `layout`, `layout_regions`, `layout_ticks` and
   `check_theme_switch` have no DESIGN ABI name. `layout`, `layout_regions`,
   `layout_ticks` and `check_theme_switch` are the shared seams of harmonization
   K13/K18 (also implemented by the JS twin); `compute_layout` is the Python
   binding of "the pinned generic layout adapter" of DESIGN §9.1 (DI
   transcription, then `layout`).
3. The helper functions of the table have no DESIGN ABI names; they bind formulas
   the DESIGN fixes (§9.2, §9.3, §10.2) so that snapshot validation (lot 5) and
   export freshness share one implementation.

## 3. Closed records and results

All records are closed: unknown members, `null` (outside Report/2 coordinates and
before/after values), non-finite numbers and integral numbers outside the safe
range refuse with the code stated for each operation.

### 3.1 Layout/1 and RenderData/1

- **Layout/1** (DESIGN §9.1): `{layoutVersion:"1", pages, geometry}`. Page:
  `{pageId, name, order, semanticRootId, bounds}`. Geometry record:
  `{pageId, occurrenceKey, semanticId?, role, bounds, label?, sourceOccurrence?,
  targetOccurrence?, waypoints?}`. Bounds `{x, y, width, height}` safe integer
  ticks, width/height ≥ 0. Label `{text, bounds, lines}` with `text` nonempty and
  `lines == text.split("\n")`. Edges carry both endpoints `{pageId,
  occurrenceKey}` and ≥ 2 waypoints `{x, y}`; non-edges omit all three. Pages sort
  by ascending unique `order`; geometry by page order then UTF-16
  `occurrenceKey`; keys are nonempty and unique per page.
- **RenderData/1** (DESIGN §9.1): `{renderVersion:"1", binding, pages,
  occurrences, coverage, diagnostics}`; `pages` equals `layout.pages`; occurrence =
  geometry record plus `emittedType`, `style`, `glyphId`; `binding` =
  `{semanticRevision, profileDigest, descriptorDigest, layoutDigest, themeId,
  themeDigest, overridesDigest, diStylesDigest, metricsDigest, payloadDigest}`;
  coverage `{semanticId, occurrences, disposition}` in native pre-order (§5.3);
  `diagnostics` are Report/2 entries (§5.3).
- **Overrides/1** `{semantic:[{semanticId, tokens}], occurrence:[{pageId,
  occurrenceKey, tokens}]}`; **DiStyles/1** `{native:[{pageId, occurrenceKey,
  tokens}], bioc:[...]}`; token `{name, value}`.
- **PreparedArtifact** (DESIGN §10.1): exactly `{format, profileIdentity,
  semanticRevision, viewRevision, ir, renderBinding, report, capability, idMap}`;
  `renderBinding` is the RenderData/1 `binding` record; `ir` is the export-ir/1
  record list of §10.2.

### 3.2 Report/2 header (harmonization B4)

`Report/2` (block-A `Report`/`ReportEntry`/`Coordinate` wire shapes,
`profile-report/2` ordering through `sort_report_entries` and `sort_id_map`)
carries the optional header members as follows. Success: `sourceIdentity` = the
input profile identity, `targetIdentity` = the output profile identity,
`inputRevision` = `baseRevision`, `outputRevision` = `revision`. Refusal:
`sourceIdentity` and `inputRevision` exactly when the Result echoes
`profileIdentity` and `baseRevision` (§3.4); never `targetIdentity` or
`outputRevision`. The same rule applies inside `PreparedArtifact.report`. For
`serializePrepared` the input identity and revision are the preparation's
`profileIdentity` and `semanticRevision`.

### 3.3 Entry order

DESIGN §10.1 `profile-report/2`: stage rank (load, import, complete,
pre-normalize, normalize, post-normalize, layout, post-layout, release, render,
export), then UTF-16 `ruleId`, source `domain`, source `pointer` and `targetId`
(null first), `code`, `pageId`, `occurrenceKey` (absent first), canonical
`before` then `after` (absent first); then result `domain`, result `pointer`,
result `targetId` (null first), then `property` (absent first); exact
duplicates coalesce (harmonization G2 tie-breaks).

### 3.4 Refusal record (harmonization B2, B3)

A Result/1 refusal is exactly `{status:"refused", operation, profileIdentity?,
baseRevision?, code, diagnostics, report}`. It echoes `profileIdentity` and
`baseRevision` whenever the input envelope is a JSON object with
`documentVersion:"1"`, a shape-valid `profileIdentity` and a string
`semanticRevision`, even if a later envelope check fails (every sealed refusal
echoes); `serializePrepared` echoes the preparation's `profileIdentity` and
`semanticRevision`. `report.entries` are the unified findings of the lint stages
executed before the refusal (`[]` when none ran; never change entries: there is no
candidate); `diagnostics` equals `report.entries`; `report.idMap` and
`report.artifacts` are `[]`. PureResult refusals are `{status:"refused", code,
diagnostics:[]}` for every lot-4 helper and for `compileProfile` (load then
compile; block-B parity sync PS-25: compile refusals carry no diagnostic).
`compileProfile` success is the PureResult `{status:"ok", payload,
diagnostics:[]}`; its `payload` (the CompiledProfile) has no closed wire shape and
is UNSEALED (`/payload`), and no compiled identity is sealed in lot 4 (parity sync
PS-35; when a seal pins the §5.1 compiled identity it is a separate
`compiled-identity` artifact).

### 3.5 Revisions

Every Result/1 operation of this lot is read-only (DESIGN §10.1 "Read-only
Result operations have baseRevision=revision"): `baseRevision == revision ==` the
input envelope `semanticRevision`, including `prepareExport`, which commits
nothing. The prepared artifact's `semanticRevision` (and its
`renderBinding.semanticRevision`) is the revision of the staged envelope the
artifact was prepared from (after C/N on the staged copy); it equals the input
revision when C/N change nothing.

## 4. Layout

Python has no automatic layout engine. The shared pure seams (§4.1, §4.2) are
the parity surface; the DI transcription (§4.3) is the Python adapter, runtime
specific (harmonization K18). Nothing in this section invents a position, a
size, a route of a non-relocated element or a line break.

### 4.1 Pure seams `layout_ticks` and `layout_regions`

`layout_ticks(points)`: each JSON number (binary64) is converted through the exact
rational of its shortest round-trip decimal form, multiplied by 1000 and rounded
once, ties to even; a negative zero result is the integer 0 (DESIGN §3.1;
harmonization E3). Non-numbers refuse `operation-error`.

`layout_regions(region_input)` binds the DESIGN §9.4 region arithmetic on explicit
numbers (shape shared with the JS seam). Input `{page, body, tokens, items}`:
`page` and `body` are Bounds (the page bounds and the support's visual body),
`tokens` is exactly `{headerWidth, padding, gap, minHeight}` (nonnegative safe
integers; a missing member refuses `render-region-missing`, other shape errors
`operation-error`), `items` are in §7.2 placement order, each `{elementId,
occurrenceKey, object:{width, height}, label?:{width, height}, anchor?: Bounds}`
(`label` absent = no label, size (0, 0); `anchor` absent = no available anchor).
Output `{pageBounds, body, items:[{elementId, occurrenceKey, bounds,
labelBounds?}]}`.

Row rule (exact rationals; every output coordinate rounded once, ties to even):

- `contentLeft = body.x + headerWidth + padding`.
- Item footprint `f = max(object.width, label.width)`; stack `s = object.height +
  label.height` (label directly below the object, no gap).
- Horizontal: for an item with an anchor, `desired = anchor.x + anchor.width/2 −
  f/2`; without an anchor, `desired = contentLeft` for the first item and
  `prevRight + gap` after it; `left = max(desired, contentLeft)`; for every item
  after the first `left = max(left, prevRight + gap)` (a later item shifts right,
  never the earlier one); `right = left + f`.
- Row: one row at the top of the body, `[body.y, body.y + RH]` with `RH =
  max(minHeight, max(s) + 2·padding)` (harmonization K2).
- Vertical: every object centre lies on one line `cy = body.y + max(A, (RH + A −
  B)/2)` with `A = max(object.height/2)` and `B = max(object.height/2 +
  label.height)`: the union of the stacks is centred in the row, and its top never
  rises above the body top (DESIGN §9.4 "Align centers on one IO row"; §21.3).
- Object bounds `(left + (f − w)/2, cy − h/2, w, h)`; label bounds `(left + (f −
  lw)/2, cy + h/2, lw, lh)`.
- Growth: `body.width' = max(body.width, lastRight + padding − body.x)`,
  `body.height' = max(body.height, RH, cy + B − body.y)`; `pageBounds` = the
  smallest rectangle containing `page` and the grown body.
- An empty item list returns the body and the page unchanged (no minHeight or
  padding growth).

### 4.2 Shared seam `layout` (base geometry → Layout/1)

`layout(compiled, envelope, placements, base_geometry, *, theme_id)` takes the
adapter's base geometry (a Layout/1 record, before region placement) and returns
the final Layout/1. Checks in this order:

1. Compatibility: `envelope.profileIdentity` against `compiled.identity` with the
   DESIGN §3.3 decision (block-A `check_compatibility`); a non-ok verdict refuses
   with its code.
2. Theme: `theme_id` resolves to the theme with that `id`, else to the unique
   theme listing it in `aliases`; otherwise refuses `render-stale` (unresolved
   input, DESIGN §9.2). The resolved theme's `id` is used everywhere after.
3. Geometry policy: a selected theme with `geometry:"theme"` refuses
   `profile-open` (OPEN-DI/OPEN-LOOK: no geometry:theme policy is approved, DESIGN
   §9.4, §16 item 6; harmonization H5). No comparison with the other themes of the
   profile runs here (harmonization K13; the switch check is §14).
4. Base geometry: a closed Layout/1 record (§3.1) whose `semanticId` values name
   ID-bearing elements of `envelope.tree`; otherwise refuses `render-stale`.
5. Region rule (§4.4) and synthetic occurrences (§4.5).

Only region items change (bounds, label bounds, `role` = region key), supports
grow, links incident to a relocated item are routed (§4.4), synthetic records are
added (§4.5) and page bounds grow: the final page bounds are the smallest
rectangle containing the base page bounds and every final geometry bounds and
label bounds of the page. Every other record is returned unchanged.

### 4.3 Python DI adapter `compute_layout` (`generic-di-layout/1`)

`compute_layout` = checks 1–3 of §4.2, the imported-DI checks below, the
transcription of this section, then `layout` on the transcribed base geometry.

Imported DI checks: `sha256 == H({descriptorDigest, diagrams})` and
`descriptorDigest == descriptorDigest(envelope.profileIdentity.descriptors)`
(§6.1), else `render-stale`; every diagram plane `bpmnElement` and every
shape/edge `bpmnElement` resolves to an ID-bearing element of `envelope.tree`,
every DI element carries a nonempty `id`, and DI ids are unique on their page;
otherwise refuses `render-stale` (unresolved input).

Transcription:

- One page per `BPMNDiagram`, in `diagrams` array order: `pageId` = diagram `id`;
  `name` = diagram `name` exactly (empty string when the diagram has no `name`;
  never derived from `pageId`); `order` = array index; `semanticRootId` = plane
  `bpmnElement`; base page `bounds` = the smallest rectangle containing every
  transcribed geometry bounds and label bounds of the page (`{0,0,0,0}` for an
  empty page).
- Units: one DI user unit is 1000 ticks, converted with `layout_ticks`.
- Each `BPMNShape` yields a non-edge record: `occurrenceKey` = the DI element
  `id`; `semanticId` = its `bpmnElement`; `bounds` = its `dc:Bounds`.
- Each `BPMNEdge` yields an edge record: `waypoints` = its `waypoint` points;
  `bounds` = the smallest rectangle containing the waypoints; endpoints =
  `{pageId, occurrenceKey}` of the shape on the same page named by the edge
  `sourceElement`/`targetElement` when present, else of the unique shape on the
  page whose `bpmnElement` is the semantic `sourceRef`/`targetRef`. An endpoint that
  does not resolve to exactly one shape refuses `render-unsupported`.
- `role`: the support binding `role` for a support target, else `"shape"` for a
  `BPMNShape` and `"edge"` for a `BPMNEdge` (`layout` then sets the region key on
  region items).
- Label: the element's matched render bindings for the selected theme (§5.2) give
  one label Value expression, evaluated with native `self` and `root` (block-A
  evaluator). A nonempty string `t` yields `label = {text: t, bounds, lines:
  t.split("\n")}` (line feed only, no wrapping); the empty string and `MISSING`
  yield no label (harmonization F3); a non-string refuses `profile-type`; unequal
  label expressions among matched bindings refuse `render-style-conflict`. Label
  `bounds`: the DI `BPMNLabel` bounds when present; else, for a region item (an
  element with a placement whose region resolves, §4.4), `(x, y, measured width,
  measured height)` at the record position with `measure_text` of the selected
  theme's metrics resource (absent metrics bytes refuse `profile-resource-missing`);
  else the record bounds (embedded label).

### 4.4 Region rule (DESIGN §9.4)

A placement `{elementId, ownerProcessId, regionKey, anchorAssociationId?,
relatedAssociationIds}` resolves its region through the verified support binding
whose `ownerId` is `ownerProcessId` and whose `role` equals `regionKey`
(harmonization K1, to be pinned in R3.4; no translation table, label or business
string maps a region key to another role):

1. Binding present: the region rectangle on a page is the geometry of the bound
   support target on that page (its visual body). A placed element shown on a page
   where the support has no geometry refuses `render-region-missing`; for a region
   with at least one item, a missing `region.<regionKey>.headerWidth|padding|gap|
   minHeight` token in the resolved theme chain refuses `render-region-missing`
   (no hidden default). A region used only by a band-stripe synthetic occurrence
   needs no row token.
2. No binding, and the selected theme declares an `attached-badge` synthetic
   occurrence with this `region`: an attachment region (DESIGN §9.4 "attached aids
   use explicit placement anchors"); the placed element keeps its base geometry.
3. Otherwise refuses `render-region-missing`: the layout primitive has no matching
   region, never creates semantics, a lane, a default region or a page/plane
   fallback (DESIGN §9.3 "no matching region refuses render-region-missing", §9.4;
   harmonization C13). The gated preparation path refuses `profile-open` instead
   (§12).

Items of a (region, page): the placements of the region whose element has a base
record on the page, in §7.2 placement order. Object size = the base record size
(position ignored); label size = the base record label bounds size (no label:
(0, 0)); the anchor is available when the placement has `anchorAssociationId` and
the association endpoint opposite to the placed element (for a data association:
its owning activity) has exactly one base record on the page (harmonization K4),
whose bounds are the anchor. The row rule of §4.1 places the items with the region
rectangle as `body`; the support record takes the grown body. Several processes
and pages resolve their own rectangle; a shared element gets one record per page.
A region with no item keeps the support unchanged (empty processes need no row).

Links (harmonization K5): an edge record whose source or target occurrence was
relocated is routed after expansion (DESIGN §9.4 "Route all links after
expansion"); the Python adapter routes it by the two-point centre route (final
source bounds centre to final target bounds centre, each rounded once, ties to
even; `bounds` = the waypoint bounding box), keeping its endpoints and label. The
DESIGN defines no routing rule (R3.4 erratum E-11), so the sealed cases leave
those `waypoints` and `bounds` (and the page bounds they can extend) UNSEALED and
check the LINK-ROUTE invariants instead (§17.4).

### 4.5 Synthetic occurrences (DESIGN §9.3)

For each `syntheticOccurrences` declaration of the selected theme (theme record
only, fallback themes do not contribute), evaluate `select` once on the tree; each
selected owner is represented on a page when the page `semanticRootId` is the
owner `id` or the page has a base record with `semanticId` equal to the owner `id`
(harmonization K7). For each represented (owner, page) emit one geometry record
without `semanticId`: `occurrenceKey = JCS([declaration id, owner id, pageId])`,
`role` = declaration role, label from the declaration `label` expression
(self = owner; nonempty string only) with `bounds` = the record bounds.

- `band-stripe`: the region is the owner's support region (owner = process,
  binding role = declaration `region`) after the §4.4 growth; none refuses
  `render-region-missing`. Bounds `(rx, ry, min(stripeWidth, rw), rh)` with
  `stripeWidth` the parameter of a `band-stripe` template glyph; a glyph without
  `stripeWidth` imposes no width bound (`rw`) (harmonization K8).
- `attached-badge`: the owner's placement with `regionKey ==` declaration `region`
  gives `anchorAssociationId`; the anchor node is the association endpoint opposite
  to the owner and must have exactly one base record on the page; no placement, no
  anchor or not exactly one anchor record refuses `render-region-missing`
  (DESIGN §9.3 "Ambiguous anchor refuses"; harmonization C14). Bounds `(node.x +
  offsetX, node.y + node.height + offsetY, badgeWidth, badgeHeight)` with the badge
  size = glyph `viewBox` width and height × 1000 ticks (harmonization K6, until
  R3.4). `hideSource:true` refuses `render-unsupported` (source-hiding interaction
  unqualified, OPEN-RENDER-PRIMITIVES; harmonization C15). `markerShift` has no
  RenderData/1 field (renderer concern, not covered).

## 5. Theme resolution — `resolve_theme` (DESIGN §9.1–§9.3)

### 5.1 Checks (in this order)

1. Compatibility (as §4.2.1).
2. Theme resolution and geometry policy (as §4.2.2–3; no comparison with other
   themes, harmonization K13).
3. Layout/1 shape (closed records, sorted unique pages and keys, edge endpoints
   resolving in the layout, label lines equal to the LF split of the text) else
   `render-stale`.
4. Overrides/1 and DiStyles/1: shape violations (unknown or missing member, null,
   non-array, duplicate target, duplicate token name in one target) and token
   signature failures refuse `render-token-invalid`; a semantic target absent from
   the tree or an occurrence target absent from `layout.geometry` refuses
   `render-stale`.
5. Per geometry record with `semanticId`, in page/key order: render bindings of
   the matched notions (§5.2); unequal glyph ids or label expressions refuse
   `render-style-conflict`; then the evaluated label (nonempty string, or none for
   the empty string and `MISSING`) must equal the layout record's label text, with
   the same presence, else `render-stale` (R copies the layout label; a stale or
   missing fitted label is a stale input; harmonization K16); token conflicts
   refuse `render-style-conflict`.
6. Every geometry record without `semanticId` must be a synthetic occurrence of the
   selected theme (key and role match a declaration), else `render-stale`.

### 5.2 Bindings, glyph, style

- Recognition (block-A evaluator, immutable tree) gives the matched notions: every
  matching facet plus at most one notion per exclusive group. For the selected
  theme `T` each matched notion contributes its render binding for the nearest
  theme of the chain `T → … → root` that has one.
- Glyph: the matched bindings must name one glyph id; unequal glyph ids refuse
  `render-style-conflict`. The glyph is looked up in the chain (selected theme
  first).
- Token precedence (DESIGN §9.3), each token name resolved independently:
  occurrence override > semantic-ID override > native color-DI > bioc-DI > notion
  render-binding tokens > selected theme tokens > fallback chain (nearest ancestor
  first). Matched bindings contribute at one level: equal values coalesce, unequal
  values for one name refuse `render-style-conflict`. Synthetic occurrences use
  their declaration `tokens` at the binding level and have no semantic or DI
  level.
- `style` = the resolved tokens over the union of names of all applicable levels,
  excluding `region.*` geometry tokens, sorted by UTF-16 name (harmonization K9).
  Sparse overrides stay sparse: the Overrides/1 record is digested as supplied
  (after normalization), never expanded.
- render-token/1 signatures (registry `renderTokens`, DESIGN §9.3):
  `fill|stroke|textColor` match `^#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?$` under
  `re.fullmatch` (a trailing line feed refuses); `fontSize|strokeWidth` are finite
  non-negative numbers (bool is not a number; integral values outside the safe
  range refuse); `fontWeight ∈ {normal, bold}`; `arrow ∈ {none, open, filled,
  hollow-triangle}`; `fontFamily` and `dash` only the injected registry values;
  `region.<key>.(headerWidth|padding|gap|minHeight)` non-negative integers. Other
  names refuse (`render-token-invalid` for runtime bags, `profile-type` at compile
  time, §8.1).

### 5.3 Occurrences, coverage, diagnostics

- One occurrence per geometry record whose element (or synthetic declaration) has
  a glyph: the record plus `emittedType` (`"edge"` for edge records, `"node"`
  otherwise, synthetic included), `style`, `glyphId`. Order: page order, then
  UTF-16 key.
- Coverage lists every ID-bearing element (`$type` and string `id`) of
  `envelope.tree` in native pre-order: an element precedes its contained
  elements, containment members are visited in UTF-16 member-name order and arrays
  in index order; ID-less elements (Documentation, InputOutputSpecification) are
  traversed but not listed (harmonization G3, lot-0 precedent). `occurrences`
  lists its occurrence pairs in R order. `disposition`: `rendered` iff it has
  occurrences; `unsupported` iff it has a layout geometry record but no glyph for
  the selected theme (drawn but not rendered: no automatic standard-notation
  fallback, DESIGN §9.3); otherwise `nonvisual` (harmonization K10: an element
  absent from the layout is nonvisual, even with a glyph).
- `diagnostics`: one entry per layout geometry record of an `unsupported` element
  (harmonization B25): `{code:"render-unsupported", severity:"error",
  classification:"integrity", stage:"render", ruleId:"adapter",
  messageKey:"render-unsupported", disposition:"observed", source:{domain:"tree",
  pointer:<RFC 6901 pointer of the element in envelope.tree>, targetId:<id>,
  provenance:"exact"}, result:{domain:"none", pointer:null, targetId:null,
  provenance:"unavailable"}, beforePresent:false, afterPresent:false, pageId,
  occurrenceKey}`, in `profile-report/2` order. The `resolveTheme` report entries
  are exactly these diagnostics.
- `binding` per §6.1 with `themeId` the resolved theme id.

## 6. Digests and freshness (DESIGN §9.2)

### 6.1 Formulas

`descriptorDigest = H(pins sorted by UTF-16 id)` (pins exactly `{id, version,
sha256}` from `profileIdentity.descriptors`); `layoutDigest = H(layout)`;
`themeDigest = H({themeId, themes})` with `themes` the complete theme records of
the chain from the fallback root to the selected theme; `overridesDigest` and
`diStylesDigest` = H of the normalized record (semantic by `semanticId`, occurrence
records by `pageId` then `occurrenceKey`, tokens by `name`, all UTF-16);
`metricsDigest = H([{id, sha256}])` over the metric resources referenced by
`metricsResource` of the chain themes, unique, sorted by UTF-16 `id`, `sha256 =
B(raw bytes)`; `payloadDigest = H({pages, occurrences, coverage, diagnostics})`;
`profileDigest = H(profile)`; `semanticRevision` per DESIGN §3.1; `viewRevision =
H({semanticRevision, layoutDigest, themeId, themeDigest, overridesDigest,
diStylesDigest, metricsDigest})`.

`render_digests(record)` binds the formulas on explicit records: input keys
`semanticTree, profileIdentity, bindings, descriptorPins, layout, themeId, themes`
(all profile themes; the chain is resolved inside), `overrides, diStyles, metrics`
(`[{id, utf8}]`, raw bytes = UTF-8 of `utf8`) and optional `payload`; output
`{semanticRevision, descriptorDigest, layoutDigest, themeDigest, overridesDigest,
diStylesDigest, metricsDigest, viewRevision}` plus `payloadDigest` when `payload` is
given. Record-shape violations refuse `render-token-invalid`; token signatures are
not checked here (no registry).

### 6.2 Freshness

`verify_render_data` recomputes every binding field from its inputs and refuses
`render-stale` on the first difference in this order: R shape, `themeId`
resolution, `semanticRevision`, `profileDigest`, `descriptorDigest`,
`layoutDigest`, `themeDigest`, `overridesDigest`, `diStylesDigest`,
`metricsDigest`, `payloadDigest`, `pages == layout.pages`, and equality of each
occurrence with its layout geometry record minus `emittedType`, `style`, `glyphId`
(harmonization K14). Success returns `{"viewRevision"}`. `map_export` applies the
same checks except `overridesDigest`/`diStylesDigest` (not among its inputs; they
stay bound through `viewRevision`). Terminal serialization never repairs R.

## 7. Text (DESIGN §9.3)

- `stripPrefix` and `case` are the block-A value operators; `case` uses the pinned
  Unicode 15.0.0 full mappings (`contracts/unicode-case/15.0.0/`), never
  `str.upper`/`str.lower` (`İ` stays `İ` in upper, `ɤ` stays `ɤ`, `ß` → `SS`,
  Final_Sigma in lower).
- `measure_text(metrics, text)`: `lines = text.split("\n")`; the width of a line is
  the sum over its Unicode scalars (not UTF-16 units) of `spaceAdvance` for U+0020
  and of the declared fallback `defaultAdvance` for every other scalar (the pinned
  neutral metrics carry no per-scalar table); `width` is the maximum line width;
  `height = len(lines) * (ascent + descent)`; values are ticks
  (`unit:"micro-point"`). No NFC, no accent stripping, no platform font
  measurement; case and width are separate (measure the final text). Text
  measurement is runtime-specific until `engine-scalar-A/1` is defined
  (harmonization K17).

## 8. Glyphs and templates (DESIGN §9.3)

### 8.1 Compile-time checks (lot-4 extension of `compile_profile`, CR-09/CR-11)

- Schema first: glyph conditionals expressed by the pinned schema (native requires
  `nativeType` and empty `commands`; path requires nonempty commands with M/L two,
  C six, Q four, Z zero values; template requires `template` and `parameters`;
  closed template enum) refuse `profile-schema` at `load_profile` (DESIGN §2.4.1:
  the schema is the sole authority for keys, unions, requiredness and
  enumerations).
- Compiler: every glyph `viewBox` needs width (`[2]`) > 0 and height (`[3]`) > 0,
  else `profile-glyph-shape`. Template parameters must be exactly the signature
  below (no duplicate, missing or extra name, exact types), else
  `profile-glyph-shape`: `header-band {headerHeight: non-negative safe integer}`;
  `corner-fold {foldRatio: number in [0, 0.5], headerRotation: 0 | 90 | 270}`;
  `attached-badge {offsetX, offsetY: safe integers, hideSource: boolean,
  markerShift: safe integer}`; `band-stripe {stripeWidth: non-negative safe
  integer}`.
- Theme, render-binding and synthetic tokens follow §5.2 signatures; an unknown
  name, a wrong value or a duplicate name in one token list refuses `profile-type`.
- Export (CR-11): the §10.2 field rules refuse `profile-export-field`; a `page` emit
  with `parent` and a nonzero `counterOrigin` with a non-counter `idPolicy` refuse
  `profile-type`.

### 8.2 `template_geometry`

`glyph` is a template glyph record (parameters checked as §8.1, refusal
`profile-glyph-shape`; a non-template glyph refuses `render-unsupported`). `bounds`
is the shape (header-band, corner-fold), region (band-stripe) or node
(attached-badge) rectangle. Exact rationals, one roundEven at output:

- `header-band`: `header = (x, y, w, min(headerHeight, h))`, `body = (x, y +
  min(headerHeight, h), w, h − min(headerHeight, h))`; the header height never
  scales with the body.
- `corner-fold`: `fold = roundEven(min(w, h) * foldRatio)` with `foldRatio` taken as
  the exact rational of its shortest round-trip decimal form; `foldPath = [(x+w−fold,
  y), (x+w−fold, y+fold), (x+w, y+fold)]`; with `label_bounds`, `labelRotation =
  {angle: headerRotation, center: (roundEven(lx + lw/2), roundEven(ly + lh/2))}`.
- `band-stripe`: `stripe = (x, y, min(stripeWidth, w), h)`.
- `attached-badge`: `badge = (x + offsetX, y + h + offsetY, badge_size.width,
  badge_size.height)` (explicit badge size input, harmonization K6), plus
  `markerShift` and `hideSource` echoed.

Payload keys: `header, body` | `fold, foldPath[, labelRotation]` | `stripe` |
`badge, markerShift, hideSource`.

## 9. Legacy themes (DESIGN §9.5)

Generic code uses opaque theme ids. `resolve_theme` never consults
`compatibilityAliases` (a legacy name such as `standard` that is not a theme id or
declared theme alias refuses `render-stale`). `resolve_legacy_theme` is the
explicit legacy adapter path: the unique `compatibilityAliases` record with
`kind:"theme"`, `old == legacy_name` (exact, no case folding) and `mode !=
"remove"` gives `destination`, which must be a theme id. Every unresolved legacy
look — no record, a `remove` record, a record of another kind, a different case or
a destination that is not a theme — refuses `render-stale` (unresolved input,
DESIGN §9.2; `legacy-unmapped` is reserved for legacy diagnostic codes, §13;
harmonization C17).

## 10. Export (DESIGN §10.2)

### 10.1 `map_export` steps (refusal precedence in this order)

1. Compatibility (as §4.2.1).
2. Format: the unique `exports[]` record whose `format == format` and a registered
   Python adapter for that format; lot 4 registers `drawio/1` and `sparx/1`.
   Otherwise refuses `export-format-unsupported`.
3. Freshness (§6.2) → `render-stale`. `map_export` trusts a fresh R: it does not
   re-run `resolve_theme`.
4. Coverage: any `unsupported` coverage entry refuses `render-unsupported` (an
   unsupported necessary occurrence refuses the entire artifact).
5. Capability: every capability record is evaluated once per R occurrence with
   `self` = the occurrence, `root`, `render`, `page` = its PageHandle and `semantic`
   (absent for synthetic occurrences); applicable classes aggregate by worst outcome
   together with the adapter ceiling `structural` (OPEN-EXPORT-EVIDENCE: no feature
   is byte-compatible by declaration; lot 4 has no qualified engine goldens). An
   `unsupported` outcome refuses `render-unsupported` (DESIGN §9.3 unknown glyph
   capability, §10.1 unsupported necessary occurrence; `export-format-unsupported`
   is a format-level code; harmonization C16).
6. Planning pass: the export recipes of the record run in order over their selector
   results (page-occurrence order), evaluating every value; each `outputId` request
   `(pageId, occurrenceKey, domain)` is recorded (PageHandle uses the reserved
   empty key; implicit page parents request the page key). `refuse` actions refuse
   with their code; `bind` cardinality errors refuse `profile-ambiguous-binding`;
   `outputId` on a native handle without exactly one occurrence of that element on
   the current page refuses `export-occurrence-ambiguous`; a required field
   evaluating to `MISSING` refuses `export-field-invalid` (an optional field
   evaluating to `MISSING` is omitted).
7. ID allocation (per call, no state across calls):
   - `counter`: requested keys sorted by domain (`page, node, edge, label`), then
     page `order`, then UTF-16 `occurrenceKey`, numbered from `counterOrigin`; `e_` +
     decimal; repeated requests reuse one ID; unrequested keys get none.
   - `digest`: `e_` + `H([pageId, occurrenceKey, domain])`.
   - `native`: `pageId` for a page, `semanticId` for a semantic occurrence, only
     when the resulting ID is unique among all requested keys of the call; a
     synthetic or anonymous occurrence, or a duplicate, refuses
     `export-id-ambiguous`.
8. Emission pass with a symbol table that lasts for exactly this call (discarded on
   refusal; nothing survives A→B→A). `page` emits at the root. For
   `node|edge|label` an omitted parent is the id emitted for the current page;
   `metadata` without parent is artifact-global. Parent and edge endpoints
   (`source`, `target`) must be earlier emitted `page|node` ids (endpoints: node
   ids): a value emitted later in the same call refuses `export-parent-order`; the
   record's own id, an id never emitted in this call (cross-call handle), an
   incompatible kind, or an id emitted twice refuse `export-parent-invalid`.
9. Losses: a `loss` action appends one entry (§10.3); capability records append one
   entry per applicable record, occurrence and loss class; the adapter appends one
   entry per emitted record kind it does not serialize (§10.3, §11).

### 10.2 export-ir/1 records

A record is `{kind, <named fields>, parent?}` (exactly the emitted field values;
`parent` omitted for `page` and artifact-global `metadata`) plus the values copied
from current immutable R (DESIGN §10.2 "Geometry, label lines and default style
copy from current immutable R"; harmonization B21), present only when `self` is the
matching typed record: `page` ← PageHandle `bounds`; `node` ← occurrence `bounds`,
`style`, `label: {bounds, lines}` (when the occurrence has a label); `edge` ←
`bounds`, `waypoints`, `style`, `label`; `label` ← the occurrence label `bounds`
and `lines`. Field vocabulary (DESIGN §10.2): page `id, name`; node `id` +
optional `name, shape, fill, stroke, textColor, fontFamily` (strings) and
`fontSize, strokeWidth` (numbers); edge `id, source, target` + optional `name,
stroke, dash, arrow` (strings) and `strokeWidth` (number); label `id, text`;
metadata `name, value`. The projection of `ir` on `{kind, id, name, parent}` of the
neutral fixtures equals their pinned `expected.exportIR`.

### 10.3 Report, idMap, artifacts

- Loss entry (every source): `code = "export-loss/" + class`, `messageKey =
  "export.loss." + class`, `classification "loss"`, `severity "warn"`, `stage
  "export"`, `disposition "mapped"`, `lossClass = class`, `beforePresent` and
  `afterPresent` false. `pageId`, `occurrenceKey`, `emittedType` of the occurrence
  (the `loss` target when it is an occurrence, else the current `self`
  occurrence); a PageHandle `self` gives `pageId` only; a native `self` none.
  `source`: the semantic element of that occurrence, or the native element named
  by the `loss` target (an ID-less target uses its own pointer and the nearest
  ID-bearing ancestor as `targetId`), as `{domain:"tree", pointer, targetId,
  provenance:"exact"}` (RFC 6901 pointer into `envelope.tree`), else
  `{domain:"none", pointer:null, targetId:null, provenance:"unavailable"}`; for an
  adapter-declared loss the element is the one the emitting `self` names (a native
  `self` gives its own pointer, the root pointer `""` for Definitions; an
  occurrence its semantic element; a PageHandle none).
  `ruleId`: the export recipe id for a `loss` action, the `exports[].id` for a
  capability-declared loss, `adapter` for an adapter-declared loss. `result`: for a
  `loss` action, the last record emitted in the same recipe iteration
  `{domain:"artifact", pointer:"/ir/<index>", targetId, provenance:"exact"}`, else
  unavailable; capability losses: unavailable (harmonization B23); adapter losses:
  the unserialized record `/ir/<index>` (`targetId` null for a metadata record).
- Adapter-declared losses: `drawio/1` serializes no `metadata` record, so it
  declares one `export-loss/metadata` entry per emitted metadata record (DESIGN
  §10.2 "a claimed export-ir/1 adapter cannot arbitrarily omit a common supported
  field without advertising a capability loss"; §21.3).
- `report = {reportVersion:"2", operation, sourceIdentity, targetIdentity,
  inputRevision, outputRevision, entries, rawStandardFindings:[], idMap, artifacts}`
  (§3.2).
- `idMap` rows `{sourceId, resultId, domain:"export", pageId, occurrenceKey?}`: one
  per emitted record with an `id` whose `self` is a PageHandle (`sourceId = pageId`,
  no `occurrenceKey`) or an occurrence with `semanticId` (`sourceId = semanticId`);
  sorted per DESIGN §10.1; repeated views stay separate (harmonization L2).
  `PreparedArtifact.idMap` equals `report.idMap`.
- `artifacts = [{format, capability, digest: H(ir), entryIndexes}]`: one record per
  output file, no `pageId`, every entry index (harmonization B22); only
  `serialize_prepared` reports `B(bytes)`.
- `PreparedArtifact.viewRevision = view_revision(renderBinding)`;
  `semanticRevision = envelope.semanticRevision`; `profileIdentity =
  envelope.profileIdentity`; the Result report and `PreparedArtifact.report` are the
  same record.

## 11. `serialize_prepared` and `drawio/1`

Checks in this order: `prepared.format` has a registered adapter (else
`export-format-unsupported`); `prepared.viewRevision ==
view_revision(renderBinding)`, `prepared.semanticRevision ==
renderBinding.semanticRevision`, `profileIdentity.sha256 ==
renderBinding.profileDigest` and `descriptorDigest(profileIdentity.descriptors) ==
renderBinding.descriptorDigest` (harmonization K15), else `render-stale`.

Result: `profileIdentity` = `prepared.profileIdentity`, `baseRevision = revision =
prepared.semanticRevision`, `report` with that identity/revision header, `entries =
prepared.report.entries` (unchanged, in their `profile-report/2` order), `idMap =
prepared.idMap` and `artifacts = [{format, capability, digest: B(bytes),
entryIndexes: [0, …, len(entries) − 1]}]`; payload `{format, bytes, digest:
B(bytes), idMap: prepared.idMap, capability: prepared.capability}` (block-B parity
sync PS-26: the download context carries the full report, DESIGN §8.1.1; every
loss stays reachable through `entryIndexes`, §10.1; downloads consume the Result
directly, §10.2).

`drawio/1` structural contract (DESIGN R3.3 fixes no draw.io bytes: structural
until engine goldens, OPEN-EXPORT-EVIDENCE): UTF-8 without BOM; newline per the
writer options (`LF`: no CR); no compression for `compression:"none"`; empty
elements in the `short` form; root `mxfile`; one `diagram` per IR page record in IR
order carrying the page `id` and `name`; inside it the layer cell and, in IR
emission order, one `mxCell` per node (`vertex="1"`, `value` = IR `name` when
present), per label record (`vertex="1"`, `value` = IR `text`) and per edge
(`edge="1"`, `source`, `target`, `value` = IR `name` when present), each with
`parent` = the IR parent (the page parent is the diagram's layer cell) and an
`mxGeometry` child from the copied R geometry; metadata records are not serialized
(their losses are declared at map time, §10.3); the same input gives the same
bytes. The sealed expectations compare the shared `drawio-structure/1` projection
(harmonization L3): per diagram `{id, name, cells:[{id, kind ("vertex"|"edge"),
parent ("$layer" for the layer cell), value?, source?, target?}]}` in document
order, plus the byte invariants; geometry and style attributes are not compared
(DESIGN R3.3 pins no draw.io unit or style mapping).

## 12. `prepare_export` (DESIGN §10.2, §6.2, §6.4)

`prepare_export` is implemented over a private pipeline that calls an observer
with each stage name before running that stage:
`_prepare.run_pipeline(compiled, envelope, options, *, observer=None) -> Result`;
`prepare_export(compiled, envelope, options)` calls it with `observer=None`. The
case harness passes an observer and compares the sealed `trace` (§17.4).

Stages, in this order, each run exactly once on a staged deep copy:

1. `options`: closed record `{format, themeId, overrides, diStyles, importedDi?}`
   (an unknown member, or a missing `format`, `themeId`, `overrides` or
   `diStyles`, refuses `operation-error`; an absent `importedDi` is not checked
   here, parity sync PS-34); `format` declared in `exports[]` with a registered
   adapter (else `export-format-unsupported`); `themeId` resolvable (id or alias,
   else `render-stale`) (harmonization C18).
2. `compatibility` (as §4.2.1). 3. `graph`: the lot-3 envelope and graph checks
   (`create_read_context(compiled, staged, stage="load")`: block-A
   `validate_envelope`, duplicate ids, unclassified members, dangling or
   wrong-type native references refuse `reference-dangling`, harmonization C2). 4. `complete`: lot-3 `complete(compiled, staged, "retained",
   activation="edit")`. 5. `pre-normalize` lint (accept). 6. `normalize`: lot-3
   `normalize(compiled, staged, None, activation="edit")`. 7. `post-normalize` lint.
   8. `layout`: every placement region must have a bound support or be an attachment
   region (§4.4), else `profile-open` (a missing support invokes gated N, never
   layout-created semantics; support creation is disabled while OPEN-RESERVED-N's
   technical gate is open, DESIGN §9.4; harmonization C13); then an absent
   `options.importedDi` refuses `operation-error` (the Python adapter has no other
   geometry source; parity sync PS-34); then `compute_layout(compiled, staged,
   placements, options.importedDi, theme_id=options.themeId)`. 9. `post-layout` lint on the staged tree hydrated
   with BPMNDI derived from the Layout/1 (per page a BPMNDiagram whose plane names
   `semanticRootId`; one BPMNShape per non-edge geometry record with `semanticId`
   and one BPMNEdge per edge record, ticks / 1000 as DI units). 10. `release` lint.
   11. `render`: `resolve_theme(compiled, staged, layout, options.themeId,
   options.overrides, options.diStyles)`. 12. `map`: `map_export(..., options.format)`.

Lint stages use block-A `lint(..., phase=<stage>, readiness_policy="accept")`. An
unresolved error entry blocks: post-normalize, post-layout and release errors block
at their stage; a pre-normalize error blocks at pre-normalize unless its rule is
classified `repairable` and declares a `repairRecipe` naming a normalize recipe
(DESIGN §6.2 "a repairable pre-N error may continue only with its declared bounded
repair recipe"). Such a finding is reported with disposition `corrected` when N
applied at least one change entry whose `ruleId` is that recipe and whose result
`targetId` is the finding's `source.targetId` (DESIGN §6.4 "corrected pre-N findings
remain history with disposition corrected"); otherwise it stays `observed` and is
an unresolved error at the post-normalize stage. A blocked stage refuses with the
`code` of the first unresolved error entry in `profile-report/2` order
(harmonization C19). A non-lint stage refusal refuses with that stage's code.

Refusals carry the §3.4 record: `report.entries` and `diagnostics` = the findings
of the lint stages executed so far (no change entry), no artifact. Success returns
the PreparedArtifact of `map_export` with `report` replaced by the complete report:
operation `"prepareExport"`, §3.2 header (read-only, §3.5), entries = C entries,
lint findings of every stage (with their dispositions), N entries (counted once:
`normalize` `payload.report` equals `result.report`), R diagnostics and export
entries, in `profile-report/2` order; `idMap` of the map stage; `artifacts[0]` with
`digest = H(ir)` and every entry index of the complete report;
`rawStandardFindings` = the concatenation of the lint stages' raw standard findings
in stage order. The Result report is the same record. No input (envelope, compiled
profile, options) is mutated.

## 13. Legacy diagnostic adapter (DESIGN §10.2 table)

`legacy = {producer, code, ids?, lossClass?}` with `producer ∈ {"io-error",
"fidelity-notice"}` or any other string; `manifest = {adapter, entries:[{producer,
legacyCode, lossClasses?}]}` (the adapter's finite per-code manifest;
`lossClasses` lists the loss classes a fidelity-notice code may carry);
`source_index` maps ids to tree pointers. Output: entries in `profile-report/2`
order, `stage "export"`, `ruleId "adapter"` (adapter-originated entries, DESIGN §6.4
convention; harmonization B24), `legacyCode = code`, `beforePresent/afterPresent`
false, `result` unavailable `{none, null, null, unavailable}`:

| Legacy record (listed in the manifest) | code / messageKey / classification / severity / disposition |
| --- | --- |
| io-error `unknown-format`, `unsupported-format` | `export-format-unsupported` / `export.format-unsupported` / integrity / error / refused |
| io-error `invalid-reference`, `missing-endpoint` | `reference-dangling` / `reference-dangling` / integrity / error / refused |
| io-error `duplicate-id` | `id-collision` / `id-collision` / integrity / error / refused |
| fidelity-notice whose `lossClass` is in the closed set and in the entry's `lossClasses` | `export-loss/<class>` / `export.loss.<class>` / loss / warn / mapped, `lossClass` (harmonization L4) |
| anything else (unlisted code, io-error code outside the five, notice class outside the closed set or not declared by the manifest) | `legacy-unmapped` / `legacy.unmapped` / integrity / error / refused |

io-error entries are one per id: `source = {tree, pointer, id, exact}` when
`source_index` has the id, else `{tree, null, id, unavailable}`; no ids gives one
entry with source `{none, null, null, unavailable}`. `legacy-unmapped` entries keep
unavailable coordinates (`{tree, null, id, unavailable}` per id, or `none` without
ids). No code is guessed from message text. Per-library code inventories stay
runtime-specific; the mapping rule is shared.

## 14. Theme switch check — `check_theme_switch` (DESIGN §9.4, §16 item 6)

`check_theme_switch(compiled, from_theme, to_theme)`: both ids resolve (id or
alias), else `render-stale`; a target (or source) theme with `geometry:"theme"`
refuses `profile-open` (no geometry:theme policy approved; harmonization H5). The
geometry-affecting values of a theme are its resolved `region.*`, `fontFamily`,
`fontSize` and `fontWeight` tokens (each name resolved through the theme's own
fallback chain, nearest first) and its `metricsResource` (harmonization K12). Two
shared themes whose geometry-affecting values differ — a name present in one chain
only is a difference — refuse `theme-geometry-conflict`; otherwise the payload is
`{"relayoutRequired": false}` (shared geometry is kept). The check compares the two
selected themes only; `compute_layout`, `layout` and `resolve_theme` never compare
the other themes of the profile (harmonization K13).

## 15. Gates (DESIGN §13, state after §16)

| Gate | State | Python lot-4 behaviour while open |
| --- | --- | --- |
| OPEN-RENDER-PRIMITIVES | technical gate open (composite grammar not supplied) | the four closed templates only; `hideSource:true` refuses `render-unsupported`; template ids outside the enum refuse `profile-schema`; no composite |
| OPEN-EXPORT-EVIDENCE | open (no engine goldens) | capability ceiling `structural`; `unsupported` refuses `render-unsupported`; serializer bytes structural only |
| OPEN-DI / OPEN-LOOK | owner default ratified (§16 item 6, shared geometry); per-theme geometry not approved | `geometry:"theme"` refuses `profile-open`; a switch between shared themes with different geometry-affecting values refuses `theme-geometry-conflict`; imported DI is the Python geometry input |
| OPEN-RESERVED-N | owner default ratified (§16 item 11), technical proof gate open | the layout primitive refuses `render-region-missing` for an unbound region; preparation refuses `profile-open` (support creation disabled; lot-3 N in edit activation refuses `profile-open` for an ensure that would create a support) |

## 16. Refusal codes by operation

- `layout`, `compute_layout`: compatibility codes, `render-stale`, `profile-open`,
  `render-region-missing`, `render-unsupported`, `render-style-conflict`,
  `profile-type`, `profile-resource-missing` (metrics bytes absent when a label must
  be measured).
- `layout_regions`: `render-region-missing` (missing token), `operation-error`;
  `layout_ticks`: `operation-error`.
- `resolve_theme`: compatibility codes, `render-stale`, `profile-open`,
  `render-token-invalid`, `render-style-conflict`.
- `check_theme_switch`: `render-stale`, `profile-open`, `theme-geometry-conflict`.
- `map_export`: compatibility codes, `export-format-unsupported`, `render-stale`,
  `render-unsupported`, `export-occurrence-ambiguous`, `export-field-invalid`,
  `profile-ambiguous-binding`, `export-id-ambiguous`, `export-parent-order`,
  `export-parent-invalid`, profile `refuse` codes.
- `serialize_prepared`: `export-format-unsupported`, `render-stale`.
- `prepare_export`: `operation-error`, every code above, lot-3 C/N codes and lint
  entry codes.
- `compile_profile` (lot-4 checks): `profile-glyph-shape`, `profile-type`,
  `profile-export-field`; `load_profile`: `profile-schema`.
- Helpers: `render-token-invalid`, `render-stale` (`render_digests`,
  `verify_render_data`), `profile-glyph-shape`, `render-unsupported`
  (`template_geometry`), `render-stale` (`resolve_legacy_theme`).

## 17. Case harness binding

### 17.1 Case files

Every expectation file is one JSON object with `case`, `clause`, `derivation`,
`operation` (shared camelCase name, harmonization A4), `input`, `expected`,
`author:"spec-seal"`, optional `witness` and `inputFrom` (another case whose value
is reused verbatim at a stated input pointer; the seal test checks the equality).
Python-authored cases are named `render.*` and `export.*`; the vendored JS cases
keep their JS case ids and have the record form of §17.6.

### 17.2 Profiles and packages

`input.profile = {base, patch}`: load `contracts/profile-mechanism/1/<base>`, apply
the RFC 6902 `patch` (`add`/`remove`/`replace`), serialize to UTF-8 JSON. The
profile's `base` and `descriptors` pins name packages of this closed table (raw
SHA-256 pins):

| Package id | Version | Bytes |
| --- | --- | --- |
| `neutral-descriptors/1` | `fixture-2` | `contracts/profile-mechanism/1/neutral-descriptors.json` |
| `neutral-base/1` | `fixture-2` | `contracts/profile-mechanism/1/neutral-base.json` |
| `neutral-render-descriptors/1` | `fixture-1` | `tests/profile_render/expected/artifacts/render-descriptors.json` |
| `neutral-render-base/1` | `fixture-1` | `tests/profile_render/expected/artifacts/render-base.json` |

The two `neutral-render-*` packages are the lot-4 neutral extension: a superset of
the vendored neutral slices (every vendored type and field kept with producers
code/editor/import) adding Lane/LaneSet, Collaboration/Participant, DataStore and
DataStoreReference, InputOutputSpecification, DataInput/DataOutput,
InputSet/OutputSet, Property, DataInputAssociation/DataOutputAssociation,
CallActivity (`calledElement`), EndEvent with TerminateEventDefinition, Task
`incoming`/`outgoing`, with the lot-3 optional facets `many` (multi-valued
references) and `single` (single-valued containment). A case whose tree uses a type
outside the vendored slice pins these packages (`replace /base`, `replace
/descriptors` in its patch); the seal test checks that every element type of every
case tree is admitted by the packages its profile pins.

Build: `validated = load_profile(bytes, schema_bytes=<profile-mechanism-1.schema.json>,
descriptor_pins=profile.descriptors, base_bytes=<base package bytes>,
asset_bag={"neutral-metrics.json": <bytes>}, capabilities=profile.capabilities)`
(`input.assetBag: "absent"` → `asset_bag=None`); `context =
create_descriptor_context([{**pin, "descriptorBytes": <package bytes>} for pin in
profile.descriptors])`; `compiled = compile_profile(validated,
registry_from_json(<neutral-registry.json>), descriptor_context=context,
base=json.loads(<base package bytes>))`. A `compileProfile` case compares the
PureResult record of §3.4: `{status:"refused", code, diagnostics:[]}`, or
`{status:"ok", diagnostics:[]}` with `/payload` UNSEALED (block-B parity sync
PS-25, PS-35).

### 17.3 Inputs

- Envelope: `complete_envelope(identity(profile), input.tree, input.bindings)` with
  `identity` the §1 record (`sha256 = H(profile)`), passed either as the
  `DocumentEnvelope` or as its wire mapping (both forms must give the same result).
  A case may override the envelope identity with `input.envelopeIdentity`.
- `input.diagrams` → `imported_di = {descriptorDigest:
  descriptorDigest(identity.descriptors), diagrams, sha256: H({descriptorDigest,
  diagrams})}` (`prepareExport`: `options.diagrams` becomes `options.importedDi`).
- Operation inputs: `computeLayout` (`profile, themeId, tree, bindings, placements,
  diagrams`, optional `assetBag`); `layout` (`profile, themeId, tree, bindings,
  placements, baseGeometry`); `layoutRegions` (`region`); `layoutTicks` (`points`);
  `resolveTheme` (`profile, themeId, tree, bindings, layout, overrides, diStyles`);
  `checkThemeSwitch` (`profile, from, to`); `renderDigests` (`record`, metrics as
  `[{id, utf8}]`); `verifyRenderData` (`profile, themeId, tree, bindings, layout, r,
  overrides, diStyles`); `measureText` (`metrics` = a vendored file name, `vectors:
  [{text, note}]`; one result per vector); `templateGeometry` (`glyph, bounds`,
  optional `labelBounds` → `label_bounds`, `badgeSize` → `badge_size`);
  `resolveLegacyTheme` (`profile, legacyName`); `mapExport` (`profile, tree,
  bindings, layout, r, format`, optional `envelopeIdentity`); `mapExportSequence`
  (`steps`: each a `mapExport` input, run in order in one process);
  `serializePrepared` (`prepared, writerOptions`); `prepareExport` (`profile, tree,
  bindings, options`, optional `envelopeIdentity`); `mapLegacyDiagnostics`
  (`legacy, manifest`, optional `sourceIndex`).

### 17.4 Comparison

`expected` is the complete wire record of the result (`result.to_json()` for
Result/1 and PureResult, `compileProfile` included: §3.4, with `/payload`
UNSEALED on success; for `mapExportSequence`, `{status:"sequence", steps:[<one
record per call>]}`), plus these harness members, which are not part of the wire
record:

- `unsealed`: RFC 6901 pointers (relative to the result record) removed from the
  actual result before comparison (and from the expected record when present);
  each must resolve in the actual result.
- `includes` (with `unsealed` covering the entry lists): each listed partial entry
  must match at least one actual report entry on the listed members (`targetId`
  compares `source.targetId`), checked before the removal.
- `trace` (`prepareExport`): the stage names the observer received, in order,
  each exactly once (§12).
- `inputsUnchanged`: the JCS bytes of the envelope wire value, the compiled profile
  JSON and the options are identical before and after the call. Every runner also
  deep-copies `input` before the call and asserts it is unchanged afterwards, for
  every case, success or refusal; the member makes the check explicit for
  `prepareExport`.
- `linkRoute` (`computeLayout`): for each listed record, the LINK-ROUTE invariants
  on the actual layout: at least two waypoints, the first inside or on the final
  source occurrence bounds, the last inside or on the final target bounds, `bounds`
  equal to the waypoint bounding box, endpoints equal to the sealed ones.
- `structural` (`serializePrepared`): `{comparator:"drawio-structure/1", diagrams,
  byteInvariants, deterministic}` checked on the actual bytes (§11): the projection
  equals `diagrams`; `byteInvariants` `{encoding:"UTF-8", byteOrderMark:false,
  carriageReturn:false, compressed:false, pairedEmptyElements:false,
  digestIsSha256OfBytes:true}`; a second call returns identical bytes.

Comparison tolerance is zero. A code job never rewrites a sealed file; a
disagreement with DESIGN keeps the expectation and adds an `xfail(strict=True)` test
naming the DESIGN line and the expectation file.

### 17.5 Parity classification

Parity cases (shared seams and DESIGN ABI operations, published for the JS twin):
`render.compile.*`, `render.digest.*`, `render.fresh.*`, `render.r.*`,
`render.template.*`, `render.legacy.*`, `render.regions.*`, `render.ticks.*`,
`render.switch.*`, `render.base.*`, `export.compile.*`, `export.map.*`,
`export.serialize.*`, `export.prepare.*` except the three below. Runtime-specific:
`render.layout.*` (DI transcription; their region outcomes are re-expressed as
`render.regions.*` and `render.base.*` cases), `render.text.*` (harmonization K17),
`export.legacy.*` (per-library code inventories, shared rule),
`export.prepare.success` and `export.prepare.repairable-pre-normalize` (their
layout stage runs through the Python DI transcription, harmonization K18) and
`export.prepare.options-unknown-member` (its unknown member `signal` is a JS
runtime member, §2 erratum 1) — block-B parity sync PS-36. Preparation refusals
before the layout stage and the layout-stage support pre-check stay parity cases.

Every parity case is also published as one `profile-parity-corpus/1` record
(DESIGN §14.3; harmonization A1–A3, A5) under `tests/profile_render/expected/parity/`:
`cases/<case>.json` (`caseId, operation, phase, profileArtifact, inputArtifacts,
expectedArtifacts, expectedStatus, comparatorIds`), `artifacts/` (the composed
profile bytes of every variant and the deduplicated large inputs, referenced by
`{role, path, sha256}` with raw SHA-256) and `manifest.json` (`pathBase`,
comparators, the package table, the load inputs and the SHA-256 of every corpus
file). Inputs are the DocumentEnvelope/1 wire value (`envelope`), the Snapshot/1
`importedDi` record and the other harness inputs by name; expected artifacts are
the wire record (`result`, or `results` for the sequence case) and the harness
members (`unsealed`, `includes`, `trace`, `linkRoute`, `drawio-structure`). The
values are a transcription of the harness files; the render seal test checks their
identity. Vendored JS cases (§17.6) are not re-published there: the manifest lists
them in `vendored` (`{caseId, source, sha256}`) and the twin pairs in `aliases`
(`{caseId, aliasOf, sha256}`).

### 17.6 Vendored JS cases (block-B parity sync)

The JS lot-4 seal owns the values of the 155 lot-4 cases the harmonization (§3)
assigns to the Python parity run (block-B parity sync PS-H17, PS-H18, PS-H19). They
are vendored, never re-authored, from the JS corpus
`bpmn-canvas:tests/fixtures/lot4-layout-export/expectations` whose `seal.json`
SHA-256 is `f953942a2a86387120737c9f8d263e082e3ff94ec60036695c236abbbef4ae43`.

- Files: the JS case files, every artifact file they reference, the package inputs
  of their profiles, `seal.json` and `manifest.json` are committed raw, in the JS
  layout (`cases/`, `artifacts/`), under `tests/profile_render/expected/vendor/js/`
  (PS-H17 `ticks-*`, `region-*`, `layout-*`; PS-H18 `admission-*`, `render-*`,
  `synthetic-*`, `decision-*`, `digest-*`, `legacy-001…008`, `history-001/002`,
  `switch-*`) and `tests/profile_export/expected/vendor/js/` (PS-H19 `export-*`,
  `idplan-*`, `serialize-*`, `bpmn-*`). A JS reference into the lot-0 corpus
  (`profile-parity-corpus/profile-mechanism/1/<file>`) resolves to the identical
  vendored lot-0 contract bytes `contracts/profile-mechanism/1/<file>` (same raw
  SHA-256).
- Pins: `derive_helper.py` carries `JS_SEAL_SHA256`, the `VENDORED` tables of both
  trees (path relative to `vendor/js/` → raw SHA-256, equal to the digest the JS
  `seal.json` lists for that file), `VENDORED_CONTRACTS` and `ALIASES`;
  `vendored_bytes(path)` returns the bytes of a vendored file only after checking
  its pin. The seal tests check every vendored file against its pin and against
  the vendored JS `seal.json`.
- Harness record: one `expected/<JS caseId>.json` per vendored case, closed members
  `case, clause, derivation, operation, profile, input, expected, expectedStatus,
  comparatorIds, artifacts?, source, paritySync?, author` (`author:"spec-seal"`).
  Paths are repository-relative.
  - `clause`: the JS clause (DESIGN section and line range); `operation`: the
    shared A4 name of the JS case; `derivation`: the vendored statement (JS seal
    digest, case file SHA-256, owning seal, parity-sync row), the JS derivation and
    the wrong implementation it fails against.
  - `profile`: `null`, or `{vendored, sha256, load}` with `load = {base,
    descriptors, registry, schema, assets}` (the JS manifest package record of
    that profile, each a `{vendored, sha256}` reference).
  - `input`: the JS input artifacts in order, each `{role, vendored, sha256}` or
    `{role, json}`.
  - `expected`: the JS `result` artifact (`output` for a seam without one), plus
    `unsealed` (the pointers of the JS `unsealed` artifact, removed as in §17.4).
  - `expectedStatus`, `comparatorIds`: the JS values; the comparators are those
    of the vendored JS `manifest.json`. `artifacts`: the other JS expected
    artifacts (`drawio-structure`, `byte-invariants`, `relations`, `invariants`)
    verbatim, read by those comparators.
  - `source`: the vendored JS case file `{vendored, sha256}`.
- Section-1 decisions applied to imported values (a value a decision changes is
  derived from the JS case and the decision, never copied); `paritySync` lists the
  decision ids:
  - PS-33 (DESIGN §10.1 L737, PureResult always wraps output in payload): the 19
    vendored `ticks-*` and `region-*` records seal `{status:"ok", payload: <JS
    output>, diagnostics:[]}` and compare with `result-exact/1` (JS
    `seam-exact/1`).
  - PS-06 (DESIGN §9.4 L723, IO object centres on one row line, §4.1):
    `layout-008-neutral-successor` and `layout-009-grid-successor` move Task_A
    (`a-first`, no label, beside the labelled Task_B) from y 7008 to y 8 on Z-page;
    their consumers `render-021`, `render-022`, `export-025` and `export-026`
    carry that layout, the R occurrence, `layoutDigest`, `payloadDigest`,
    `renderBinding`, `viewRevision`, the Task_A IR node bounds and `H(ir)`.
    `paritySync.changes` lists every changed value `{pointer, from, to}` with
    `from` the sealed JS value; the seal test reverts them to the JS case and
    recomputes every changed digest.
- Twins (PS-37): `ticks-001-half-even` ≡ `render.ticks.half-even` (after PS-33) and
  `region-010-mixed-heights` ≡ `render.regions.mixed-label-heights` (after PS-06 and
  PS-33): no file is copied and no record is written; `ALIASES` and the parity
  manifest list `{caseId, aliasOf, sha256}` (`sha256` of the JS case file).
- Runner binding (JS role → Python argument; `compiled` built as §17.2 from
  `profile` and `profile.load`):

| Operation | Python | Roles |
| --- | --- | --- |
| `layoutTicks` | `layout_ticks(points)` | `points` |
| `layoutRegions` | `layout_regions(region_input)` | `region-input` |
| `layout` | `layout(compiled, envelope, placements, base_geometry, theme_id=…)` | `envelope`, `placements`, `base-geometry`, `themeId` |
| `compileProfile` | `load_profile` then `compile_profile` (§17.2) | `base`, `descriptors`, `registry`, `schema`, `asset` (one per asset); `mutation` `{pointer, value}` is added to the profile JSON at `pointer` (RFC 6902 `add`) before loading |
| `resolveTheme` | `resolve_theme(compiled, envelope, layout, theme_id, overrides, di_styles)` | `envelope`, `layout`, `themeId`, `overrides`, `diStyles` |
| `evaluateValue` | the block-A Value evaluator, one PureResult per expression, without bindings | `values` |
| `renderDigests` | `render_digests(record)` | `record` |
| `theme-sequence` | one `resolve_theme` per step on the same envelope and layout (absent step bags are empty); per step `{themeId, semanticRevision, layoutDigest, themeDigest, overridesDigest, payloadDigest, viewRevision}` | `envelope`, `layout`, `steps` |
| `checkThemeSwitch` | `check_theme_switch(compiled, from_theme, to_theme)` | `from`, `to` |
| `resolveLegacyTheme` | `resolve_legacy_theme(compiled, legacy_name)` | `look` |
| `mapExport` | `map_export(compiled, envelope, layout, r, format)` | `envelope`, `layout`, `render`, `format` |
| `exportIdPlan` | the §10.1 step-7 ID allocation of `_export_ir.py` on the explicit plan (private seam), PureResult `{ids}` | `plan-input` |
| `serializePrepared` | `serialize_prepared(prepared, pinned_writer_options)` | `prepared`, `writerOptions` |
| `serializePrepared-sequence` | `serialize_prepared` in the listed call order | `prepared-a`, `prepared-b`, `writerOptions`, `order` |
| `serializeBpmn` | block-A `hydrate` of `envelope.tree`, then `serialize_xml` with the writer options (BPMN column, harmonization L6) | `envelope`, `writerOptions` |

The runner compares `expected` as §17.4 and applies the other listed comparators
with the record's `artifacts`; `source-immutability/1` is the input check every
runner performs (§17.4).

## 18. Case tables

The per-file case tables (one row per expectation file: case, DESIGN clause, what
it witnesses, expected status/code) are in Appendix A (render tree) and Appendix B
(export tree) at the end of this document; the vendored JS cases and twins (§17.6)
are listed in Appendix C (render tree) and Appendix D (export tree).

## 19. Not covered

- Automatic layout of elements without DI, width-based wrapping, font-size
  scaling, kerning, per-scalar width tables and width-alias maps
  (`engine-scalar-A/1` is named but not defined in DESIGN R3.3; harmonization K17).
- An exact route for links incident to relocated region items (UNSEALED, LINK-ROUTE
  invariants only; R3.4 erratum E-11); growth of containers beyond the bound
  support; moving elements below a grown support.
- DI colour decoding into DiStyles/1 (import adapter; DiStyles is an input here) and
  the explicit discard report for archived DI of non-admitted elements (refused
  `render-stale`).
- `hideSource`, `markerShift`, badge rows and composites (OPEN-RENDER-PRIMITIVES).
- Synthetic owners represented only through a collaboration participant; synthetic
  declarations inherited from fallback themes.
- `bpmn` and `svg` export adapters (refused `export-format-unsupported` in
  lot 4), exact draw.io bytes and draw.io geometry/style attribute values,
  compression `deflate-raw`, engine byte-compatibility (OPEN-EXPORT-EVIDENCE,
  private goldens). BPMN XML column facts (harmonization L6) are covered by the
  vendored JS `bpmn-001…003` cases (§17.6, block-A writer).
- `sparx/1` is registered beside `drawio/1` (conductor decision after the parity
  sync, DESIGN §10.2 and §12): declared `sparx` formats map with native IDs and
  refuse `export-id-ambiguous`; serialization goes exactly as far as the JS lot-4
  seal fixes it, anything beyond stays not covered.
- The exact block-A lint bridge output for standard bpmnlint findings in a refused
  preparation (sealed through `includes`, entry lists UNSEALED); raw standard
  findings of a preparation where standard rules fire.
- JS lot-4 cases not vendored (parity sync §5 and §1 rows): `legacy-adapter-001…013`
  (per-library legacy code inventories, harmonization B24, L4; the mapping rule is
  shared) and the two-sided `prepare-001…003`, `signature-*`, `template-*`,
  `verify-*` (each behaviour is witnessed on both sides by each side's own
  fixtures). Synthetic occurrences are Layout/1 records of the layout primitive
  styled by R on both sides (parity sync PS-23, converged).
- Cross-runtime witnesses (JS↔Python R/IR/report parity, three-process runs,
  browser rendering) — conductor joint run.
- Metrics resources whose `textPolicy`/`unicode` differ from the neutral pins;
  render diagnostics for ID-less children.

## 20. Design defaults (DESIGN silent or ambiguous)

Current defaults; items superseded in the fix round are marked.

1. regionKey ↔ support binding role identity (§4.4); shared decision
   (harmonization K1, R3.4 erratum E-12).
2. Superseded by harmonization C13: an unbound region refuses
   `render-region-missing` in the layout primitive (was `profile-open`); the
   attached-badge attachment region stays (DESIGN §9.4 "attached aids use explicit
   placement anchors"); preparation refuses `profile-open` (§12).
3. DI user unit = 1000 ticks (§4.3); shared tick rule (harmonization E3).
4. Occurrence key = DI element id; role vocabulary `shape`/`edge` and support
   binding role for transcribed records (§4.3, runtime-specific).
5. Superseded by harmonization K2 and §21.3: one row at the top of the support body,
   object centres on one line, the union of the stacks centred in the row (was:
   each stack centred on the support centre).
6. Band-stripe without `stripeWidth` spans the region width (harmonization K8).
   Badge part superseded by harmonization K6: template seam badge size is an
   explicit input; layout badges use the glyph viewBox × 1000 (same rule, now
   shared).
7. Superseded by harmonization G3/K10/B25: native pre-order coverage; unsupported =
   laid out without a glyph, with one `render-unsupported` diagnostic per record;
   nonvisual otherwise; export refuses `render-unsupported` on unsupported coverage.
8. Override/DI-style shape violations refuse `render-token-invalid`; unknown targets
   refuse `render-stale` (§5.1).
9. Code superseded by harmonization C16: an unsupported capability outcome refuses
   `render-unsupported` (was `export-format-unsupported`); capability losses keep
   `ruleId = exports[].id` and unavailable result coordinates (harmonization B23).
10. export-ir/1 records carry the R-copied `bounds/style/label/waypoints/lines`
    (harmonization B21); edge endpoints obey the parent order rules.
11. `prepare_export` lint refusal code = first unresolved error entry (harmonization
    C19, shared).
12. Legacy manifest shape and dispositions (§13); `resolve_legacy_theme` and the
    generic path never share `compatibilityAliases` (§9).
13. `metricsDigest` over the selected chain's metric resources (§6.1).
14. `counterOrigin` nonzero under a non-counter policy and `page` with `parent`
    refuse `profile-type` (CR-11 lists both codes).
15. `measure_text`: `spaceAdvance` applies to U+0020 only; metric values are ticks;
    `height = lines × (ascent + descent)` (§7).
16. Labels: line-feed split only, no wrapping; label bounds = DI `BPMNLabel` bounds,
    else the measured size for region items, else the record bounds. Empty-label
    part superseded by harmonization F3: the empty string yields no label.
17. A declared theme `aliases` entry selects that theme; the binding records the
    theme id (harmonization K11).
18. Synthetic occurrences are laid out by `layout` (selected theme only) and styled
    by `resolve_theme`; "represented page" = page root or a base record of the owner
    (harmonization K7).
19. Render bindings follow the selected theme's fallback chain (nearest theme first)
    (§5.2).
20. `corner-fold` uses the exact rational of the shortest decimal form of
    `foldRatio` (§8.2).
21. Coverage includes `Definitions` and every ID-bearing element (§5.3).
22. Unresolved DI references refuse `render-stale`; unresolvable edge endpoints
    refuse `render-unsupported` (§4.3).
23. Loss-action result coordinates point at the last record emitted in the same
    recipe iteration (`/ir/<index>`), else unavailable (harmonization B23).
24. idMap rows only for records emitted while `self` is a PageHandle or a semantic
    occurrence; artifact `digest = H(ir)` before serialization (harmonization B22,
    L2).
25. `map_export` checks R freshness including occurrence/layout equality, not
    provenance (harmonization K14).
26. Additive block-A type extensions and `registry_from_json` (§1).
27. Every Result/1 operation of this lot is read-only (`baseRevision == revision`),
    `prepareExport` included; the prepared artifact carries the staged revision
    (§3.5).
28. `serializePrepared` echoes the preparation identity and revision (§3.4, §11).
29. The `prepareExport` trace is observed through the private
    `_prepare.run_pipeline(..., observer=...)` seam (§12).
30. A pre-N repairable finding counts as corrected when N applied a change entry of
    its repair recipe on the same target; otherwise it is unresolved after N (§12).
31. The post-layout lint sees BPMNDI derived from the Layout/1 (§12).

## 21. Fix-round record

### 21.1 Harmonization decisions applied

A1–A6, A8 (shared camelCase operation names, corpus/1 projections of every parity
case, §17.5), B2, B3, B4, B21–B25, C2 (graph stage of preparation), C13–C19, E3, F3, G2,
G3, H5–H7, K1–K18, L2–L5. L6 (BPMN column) was not covered in this round; the
parity sync covers it through the vendored JS `bpmn-*` cases (§17.6, §22).

### 21.2 Review findings applied

IO object centres on one row line (§4.1, §21.3); lot-4 neutral extension packages
with pins and identities (§17.2); repairable pre-N errors with their declared repair
recipe and the stage trace (§12); DESIGN §10.2 feature-table witnesses and the
`profile-resource-missing`/`profile-ambiguous-binding` cases; draw.io structural
success defined by the shared projection plus declared metadata losses (§10.3, §11);
profiles compiled with `descriptor_context` and `base` (§17.2); envelope mappings
accepted and validated (§2); region resolution kept on the binding role (K1) with
the N→layout passage sealed (`render.layout.region-key-role-mismatch`,
`render.layout.neutral-fixture-content-unbound`, `render.layout.io-anchored`).

### 21.3 DESIGN over harmonization

- IO row (harmonization K2 "each object+label block centred in the row"): DESIGN
  §9.4 "Align centers on one IO row inside the lane" requires the IO object centres
  on one line; per-block centring breaks it when label heights differ. The row stays
  at the top of the body with the DESIGN row height; the common centre line is
  `cy = Ly + max(A, (RH + A − B)/2)` (§4.1).
- drawio/1 metadata (harmonization L3 projection, metadata not projected): DESIGN
  §10.2 "a claimed export-ir/1 adapter cannot arbitrarily omit a common supported
  field without advertising a capability loss" requires a declared loss for every
  metadata record the serializer drops (§10.3).

## 22. Block-B parity sync record

The JS/Python parity sync reconciles the two lot-4 seals after their fix rounds
(row ids PS-nn; DESIGN R3.3 first, then the harmonization). It changes sealed
values only through the hand-decided transformations below; no implementation was
imported or run, and every vendored value is the JS seal's value or is derived from
it by a listed decision.

### 22.1 Decisions applied

| Row | Decision | Effect on this seal |
| --- | --- | --- |
| PS-25 | A PureResult refusal is exactly `{status, code, diagnostics}`; compile refusals carry `diagnostics: []` | the 27 `render.compile.*` and `export.compile.*` refusals (§3.4, §17.2) |
| PS-35 | Compile success is `{status:"ok", payload, diagnostics:[]}` with `payload` UNSEALED; a sealed compiled identity is a separate `compiled-identity` artifact | the 4 compile successes (no identity sealed) |
| PS-26 | `serializePrepared` carries the prepared report entries and idMap and one artifact whose `entryIndexes` list every entry | `export.serialize.drawio-kinds` (12 entries), `-drawio-neutral-fixture` (3), `-drawio-grid-fixture` (3) (§11) |
| PS-34 | `prepareExport` options `{format, themeId, overrides, diStyles, importedDi?}`; an absent `importedDi` refuses `operation-error` at the layout stage; `signal` is JS-only | §2 erratum 1, §12 stages 1 and 8; no value change |
| PS-36 | Preparation cases whose layout stage is the DI transcription, and the `signal` case, are runtime-specific | `export.prepare.success`, `-repairable-pre-normalize`, `-options-unknown-member` leave `parity/` (§17.5) |
| PS-33 | `layoutTicks` and `layoutRegions` return PureResult | the 19 vendored `ticks-*`/`region-*` records (§17.6) |
| PS-06 | IO object centres on one row line (the §4.1 rule) | vendored `layout-008`, `layout-009`, `render-021`, `render-022`, `export-025`, `export-026`; twin `region-010` (§17.6) |
| PS-37 | Byte-identical twins are aliases | `ticks-001-half-even`, `region-010-mixed-heights` |

Rows already satisfied by this seal (no change): PS-07 (adapter-declared metadata
losses, §10.3), PS-23 (synthetic occurrences are Layout/1 records of the layout
primitive styled by R), PS-24 (bindings validated generically; the lot-4 envelopes
bind `content` and `side` without an ensure recipe).

### 22.2 Imports

| Row | JS cases | Tree |
| --- | --- | --- |
| PS-H17 | `ticks-001…004`, `region-001…017`, `layout-001…011` (32 ids, 2 twins) | render |
| PS-H18 | `admission-001…010`, `render-001…024`, `synthetic-001…013`, `decision-001…005`, `digest-001…008`, `legacy-001…008`, `history-001/002`, `switch-001…007` (77) | render |
| PS-H19 | `export-001…028`, `idplan-001…007`, `serialize-001…008`, `bpmn-001…003` (46) | export |

155 ids: 153 harness records (25 derived: 19 by PS-33, 6 by PS-06) and 2 twins,
from the JS seal `f953942a2a86387120737c9f8d263e082e3ff94ec60036695c236abbbef4ae43`.
After the sync the render tree holds 194 Python cases and 107 vendored records, the
export tree 83 and 46, and the parity corpus publishes 224 records and lists 153
vendored cases and 2 aliases (Appendices C and D).

### 22.3 Open items

- R3.4 errata candidates recorded by the sync for these points: E-33
  (`serializePrepared` report), E-34 (helper PureResult, compile payload), E-35
  (`prepareExport` options), E-36 (IO row centre line), E-37 (adapter-declared
  losses), E-40 (binding role declaration).

## Appendix A — render tree (`tests/profile_render/expected/`, 194 cases)

| Case | DESIGN clause | Witness | Expected |
| --- | --- | --- | --- |
| `render.base.base-unsorted` | §9.4 Region geometry, including Process IO | base geometry is a closed Layout/1 record in page/occurrence order | refused `render-stale` |
| `render.base.io-row` | §9.4 Region geometry, including Process IO | the shared layout seam applies the region rule to adapter base geometry | ok |
| `render.base.region-unbound` | §9.4 Region geometry, including Process IO | the shared layout seam refuses a region without a bound support | refused `render-region-missing` |
| `render.compile.binding-token-duplicate` | §2.4.1 CR-09 presentation | duplicate token name in one render binding | refused `profile-type` |
| `render.compile.grid-profile` | §9.3 Per-notion style, text and glyph contracts | the second neutral profile with its header-band glyph and synthetic side stripe compiles | ok |
| `render.compile.native-with-commands` | §2.4.1 schema authority; §9.3 glyph shape conditionals | native glyph with commands is a schema violation | refused `profile-schema` |
| `render.compile.path-bad-arity` | §2.4.1 schema authority; §9.3 glyph shape conditionals | path command L with three values is a schema violation | refused `profile-schema` |
| `render.compile.path-valid` | §9.3 Per-notion style, text and glyph contracts | path glyph with M, L, C, Q, Z of the right arities and a positive viewBox compiles | ok |
| `render.compile.region-token-fraction` | §2.4.1 CR-09 presentation | region tokens are nonnegative integer ticks | refused `profile-type` |
| `render.compile.synthetic-token-invalid` | §2.4.1 CR-09 presentation | synthetic occurrence tokens follow the same signatures | refused `profile-type` |
| `render.compile.template-param-duplicate` | §9.3 Per-notion style, text and glyph contracts | duplicate template parameter | refused `profile-glyph-shape` |
| `render.compile.template-param-extra` | §9.3 Per-notion style, text and glyph contracts | template glyph with an extra parameter | refused `profile-glyph-shape` |
| `render.compile.template-param-missing` | §9.3 Per-notion style, text and glyph contracts | template glyph without its exact parameter set | refused `profile-glyph-shape` |
| `render.compile.template-param-type` | §9.3 Per-notion style, text and glyph contracts | template parameter of the wrong type | refused `profile-glyph-shape` |
| `render.compile.template-unknown` | §9.3 OPEN-RENDER-PRIMITIVES; §2.4.1 schema authority | a composite outside the closed template set cannot be expressed | refused `profile-schema` |
| `render.compile.theme-token-type` | §2.4.1 CR-09 presentation | theme token with a value outside its render-token/1 signature | refused `profile-type` |
| `render.compile.theme-token-unknown` | §2.4.1 CR-09 presentation | token without a pinned signature | refused `profile-type` |
| `render.compile.viewbox-negative-height` | §9.3 Per-notion style, text and glyph contracts | path glyph viewBox needs a positive height | refused `profile-glyph-shape` |
| `render.compile.viewbox-zero-width` | §9.3 Per-notion style, text and glyph contracts | native glyph viewBox needs a positive width | refused `profile-glyph-shape` |
| `render.digest.bag-duplicate-target` | §9.2 Digest formulas and freshness | duplicate DiStyles/1 targets refuse | refused `render-token-invalid` |
| `render.digest.bag-null-token` | §9.2 Digest formulas and freshness | null token values refuse | refused `render-token-invalid` |
| `render.digest.bag-unknown-member` | §9.2 Digest formulas and freshness | Overrides/1 records are closed: an unknown member refuses | refused `render-token-invalid` |
| `render.digest.bags-reordered` | §9.2 Digest formulas and freshness | reordered override/style records and tokens normalize identically | ok |
| `render.digest.bags-sorted` | §9.2 Digest formulas and freshness | non-empty Overrides/1 and DiStyles/1 already in normalized order; overrides change viewRevision but not semanticRevision | ok |
| `render.digest.distinct-pages` | §9.2 Digest formulas and freshness | two pages with distinct IDs and names in page order (Z-page order 0 before A-page order 1) | ok |
| `render.digest.metric-byte-changed` | §9.2 Digest formulas and freshness | one changed metric byte changes metricsDigest and viewRevision | ok |
| `render.digest.metric-bytes` | §9.2 Digest formulas and freshness | metricsDigest over {id, sha256=B(raw metric bytes)} of the vendored neutral metrics | ok |
| `render.digest.occurrence-payload-changed` | §9.2 Digest formulas and freshness | one changed occurrence payload changes payloadDigest but not viewRevision | ok |
| `render.digest.occurrence-payload` | §9.2 Digest formulas and freshness | payloadDigest over one occurrence record | ok |
| `render.digest.page-id-changed` | §9.2 Digest formulas and freshness | distinct page ID with an identical name changes layoutDigest, payloadDigest and viewRevision only | ok |
| `render.digest.page-name-changed` | §9.2 Digest formulas and freshness | one changed page name with the same pageId invalidates layoutDigest (§9.1) and viewRevision | ok |
| `render.digest.r3-vectors` | §9.2 Digest formulas and freshness | every binding digest and viewRevision on the pinned R3 vector, empty override/style bags, reordered descriptor pins | ok |
| `render.digest.theme-selection` | §9.2 Digest formulas and freshness | selecting another theme changes themeDigest and viewRevision only; the chain runs from the fallback root to the selected theme | ok |
| `render.digest.theme-two-themes-plain` | §9.2 Digest formulas and freshness | theme list with a second theme; selecting plain hashes only its own chain | ok |
| `render.fresh.alias-same-theme` | §9.2 Digest formulas and freshness | a theme alias names the same theme: still fresh | ok |
| `render.fresh.di-styles-changed` | §9.2 Digest formulas and freshness | a DI style added after R makes diStylesDigest stale | refused `render-stale` |
| `render.fresh.overrides-changed` | §9.2 Digest formulas and freshness | an override added after R makes overridesDigest stale | refused `render-stale` |
| `render.fresh.payload-tampered` | §9.2 Digest formulas and freshness | a payload edited after binding fails payloadDigest | refused `render-stale` |
| `render.fresh.plain-fresh` | §9.2 Digest formulas and freshness | a fresh R verifies and yields its viewRevision | ok |
| `render.fresh.semantic-changed` | §9.2 Digest formulas and freshness | a semantic edit after R makes semanticRevision stale | refused `render-stale` |
| `render.fresh.staircase-fresh` | §9.2 Digest formulas and freshness | the same theme with its overrides and DI styles verifies | ok |
| `render.fresh.theme-selection-changed` | §9.2 Digest formulas and freshness | selecting another theme after R makes the binding stale | refused `render-stale` |
| `render.layout.attached-badge` | §9.3 Per-notion style, text and glyph contracts | attached-badge synthetic: placement anchor's opposite node, offsets, declared size; attachment region needs no support | ok |
| `render.layout.badge-ambiguous-anchor` | §9.3 Per-notion style, text and glyph contracts | ambiguous anchor refuses (no nearest-activity repair) | refused `render-region-missing` |
| `render.layout.badge-hide-source-gated` | §9.3 synthetic occurrences; §13 OPEN-RENDER-PRIMITIVES | hideSource source-hiding interaction stays disabled | refused `render-unsupported` |
| `render.layout.badge-no-anchor` | §9.3 Per-notion style, text and glyph contracts | source association hiding/attachment requires the unique approved placement anchor | refused `render-region-missing` |
| `render.layout.band-stripe-width` | §9.3 Per-notion style, text and glyph contracts | band-stripe role with a band-stripe glyph: leading rectangle min(stripeWidth, region.width), full height | ok |
| `render.layout.di-two-pages` | §9.1 Closed layout and render data | Layout/1 transcribed from DI: page order and names, repeated semantic IDs, key order opposite to semantic IDs, stripPrefix label | ok |
| `render.layout.di-unresolved-element` | §9.2 Digest formulas and freshness | DI naming an element absent from the semantic tree is an unresolved input | refused `render-stale` |
| `render.layout.di-unresolved-plane` | §9.2 Digest formulas and freshness | a page root must resolve | refused `render-stale` |
| `render.layout.edge-endpoint-unresolved` | §9.1 Closed layout and render data | edge endpoints must resolve exactly on the same page | refused `render-unsupported` |
| `render.layout.edge-without-notion` | §9.1 Closed layout and render data | an element with DI but no matched binding is transcribed without a label | ok |
| `render.layout.edge` | §9.1 Closed layout and render data | edge geometry: waypoints, bbox bounds, endpoints resolved on the same page, DI label bounds | ok |
| `render.layout.grid-missing-support` | §9.4 Region geometry (no matching region refuses render-region-missing); §9.3 | placements into a region without a bound support refuse render-region-missing (layout never creates supports) | refused `render-region-missing` |
| `render.layout.grid-side-stripe` | §9.4 Region geometry, including Process IO | second neutral profile: region row in the side lane with anchors, collision and growth; synthetic stripe key; casing ss | ok |
| `render.layout.io-anchored` | §9.4 Region geometry, including Process IO | Process IO row: anchor centres, clamp, collision shift, placement order not x order, row at the top of the body | ok |
| `render.layout.io-disagreeing-theme-not-compared` | §9.4 Region geometry, including Process IO | a single-theme layout never refuses theme-geometry-conflict: the shared-geometry check runs only between two selected themes | ok |
| `render.layout.io-empty-process` | §9.4 Region geometry, including Process IO | an empty process without IO needs no IO row; several processes resolve their own rectangle | ok |
| `render.layout.io-geometry-theme-gated` | §13 OPEN-DI / OPEN-LOOK (§16.6) | per-theme geometry stays disabled | refused `profile-open` |
| `render.layout.io-growth` | §9.4 Region geometry, including Process IO | the support lane grows in width and height instead of drawing outside it | ok |
| `render.layout.io-link-rerouted` | §9.4 Region geometry, including Process IO | links incident to a relocated region item are routed after expansion; their route members are UNSEALED and checked by the LINK-ROUTE invariants | ok |
| `render.layout.io-missing-lane` | §9.4 Region geometry (no matching region refuses render-region-missing); §9.3 | missing external support: the layout primitive refuses render-region-missing (support creation belongs to gated N) | refused `render-region-missing` |
| `render.layout.io-no-anchor` | §9.4 Region geometry, including Process IO | IO without anchor: content left edge, then after the previous IO by gap | ok |
| `render.layout.io-pinned-neutral-tokens` | §9.4 Region geometry, including Process IO | the pinned neutral region tokens (headerWidth 0, padding 8, gap 8, minHeight 40) | ok |
| `render.layout.io-region-missing-on-page` | §9.4 Region geometry, including Process IO | a placed element shown on a page without its support rectangle refuses | refused `render-region-missing` |
| `render.layout.io-region-token-missing` | §9.4 Region geometry, including Process IO | region numeric inputs are injected tokens; no hidden default | refused `render-region-missing` |
| `render.layout.io-repeated-views` | §9.4 Region geometry, including Process IO | repeated views: each page resolves its own bound rectangle; shared IO gets separate geometry; anchor absent on a page | ok |
| `render.layout.io-round-half-even` | §9.4 Region geometry, including Process IO | rational computations round once at output, ties to even | ok |
| `render.layout.io-shared-theme-switch` | §9.4 Region geometry, including Process IO | selecting another shared theme with identical geometry tokens leaves the layout unchanged | ok |
| `render.layout.io-wider-labels` | §9.4 Region geometry, including Process IO | labels wider than their IO object widen the footprint; DI label sizes kept, missing label measured; object centres on one row line | ok |
| `render.layout.label-case-lower` | §9.3 Per-notion style, text and glyph contracts | Unicode 15.0.0 full lower mapping with the untagged Final_Sigma context | ok |
| `render.layout.label-case-upper` | §9.3 Per-notion style, text and glyph contracts | Unicode 15.0.0 full upper mapping after stripPrefix, prefix removed exactly once | ok |
| `render.layout.label-empty-string` | §9.3 Per-notion style, text and glyph contracts | a label Value evaluating to the empty string yields no label (like MISSING) | ok |
| `render.layout.label-strip-prefix-trim` | §9.3 Per-notion style, text and glyph contracts | stripPrefix after the ecma262-2024-start leading trim; U+0085 and U+200B are not trimmed; the body is never trimmed | ok |
| `render.layout.metrics-missing` | §9.4 Region geometry, including Process IO | a label that must be measured needs the theme's metrics bytes: absent metrics refuse profile-resource-missing | refused `profile-resource-missing` |
| `render.layout.neutral-fixture-content-unbound` | §9.4 Region geometry (no matching region refuses render-region-missing); §9.3 | N->layout passage on the lot-0 neutral fixture: content placements without a bound support refuse | refused `render-region-missing` |
| `render.layout.page-name-absent` | §9.1 Closed layout and render data | page name is captured from the diagram record, never guessed from pageId | ok |
| `render.layout.reference-band` | §9.4 Region geometry, including Process IO | reference band uses its bound participant rectangle with the same header/padding rule | ok |
| `render.layout.region-key-role-mismatch` | §9.4 Region geometry (no matching region refuses render-region-missing); §9.3 | N->layout passage: a placement region key resolves only through a binding whose role equals it | refused `render-region-missing` |
| `render.layout.stripe-region-missing` | §9.3 Per-notion style, text and glyph contracts | a synthetic stripe whose owner has no matching region refuses | refused `render-region-missing` |
| `render.layout.style-conflict-label` | §9.3 Per-notion style, text and glyph contracts | matched bindings with different label expressions refuse at layout | refused `render-style-conflict` |
| `render.legacy.alias-absent` | §9.5 Legacy themes | no built-in legacy look mapping | refused `render-stale` |
| `render.legacy.alias-dangling` | §9.5 Legacy themes | a legacy alias must land on a declared theme | refused `render-stale` |
| `render.legacy.alias-exact-name` | §9.5 Legacy themes | legacy alias names match exactly (no case folding) | refused `render-stale` |
| `render.legacy.alias-mapped` | §9.5 Legacy themes | a legacy look name resolves only through injected compatibility data | ok |
| `render.legacy.alias-removed` | §9.5 Legacy themes | a removed legacy alias maps to nothing | refused `render-stale` |
| `render.legacy.alias-wrong-kind` | §9.5 Legacy themes | only kind theme records map looks | refused `render-stale` |
| `render.r.attached-badge` | §9.3 Per-notion style, text and glyph contracts | badge occurrence styled from its declaration tokens; source occurrence kept (hideSource false) | ok |
| `render.r.coverage-unsupported` | §9.3 Per-notion style, text and glyph contracts | no automatic standard-notation fallback: drawn element without a deliberate glyph is covered as unsupported with one render-unsupported diagnostic | ok |
| `render.r.di-style-unknown-page` | §9.2 Digest formulas and freshness | Overrides/1 and DiStyles/1 reject unknown targets/members, duplicate targets and non-closed shapes | refused `render-stale` |
| `render.r.edge` | §9.1 Closed layout and render data | edge occurrence: emittedType edge, binding stroke beats theme stroke | ok |
| `render.r.facet-disjoint` | §9.3 Per-notion style, text and glyph contracts | multiple matched facets contribute disjoint tokens | ok |
| `render.r.facet-equal-values` | §9.3 Per-notion style, text and glyph contracts | equal values for one token at the same precedence coalesce | ok |
| `render.r.geometry-theme-gated` | §13 OPEN-DI / OPEN-LOOK; §9.4 shared geometry | per-theme geometry is not approved while OPEN-DI/OPEN-LOOK keeps shared geometry | refused `profile-open` |
| `render.r.grid-side-stripe` | §9.3 Per-notion style, text and glyph contracts | R of the second neutral profile: header-band glyph, ServiceTask glyph, synthetic stripe style, unsupported support lane with its diagnostic | ok |
| `render.r.label-empty-string` | §9.3 Per-notion style, text and glyph contracts | an occurrence whose evaluated label is the empty string carries no label | ok |
| `render.r.label-extra` | §9.2 Digest formulas and freshness | a layout label for an element whose bindings produce no label is stale | refused `render-stale` |
| `render.r.label-missing` | §9.2 Digest formulas and freshness | a layout record without the label the binding evaluates is stale | refused `render-stale` |
| `render.r.label-stale-text` | §9.2 Digest formulas and freshness | a layout label whose text differs from the evaluated binding label is stale | refused `render-stale` |
| `render.r.layout-foreign-synthetic` | §9.3 Per-notion style, text and glyph contracts | a geometry record without semanticId must be a synthetic occurrence of the selected theme | refused `render-stale` |
| `render.r.layout-unsorted` | §9.1 Closed layout and render data | Layout/1 geometry must use page/occurrence order | refused `render-stale` |
| `render.r.override-duplicate-target` | §9.2 Digest formulas and freshness | Overrides/1 and DiStyles/1 reject unknown targets/members, duplicate targets and non-closed shapes | refused `render-token-invalid` |
| `render.r.override-tokens-not-array` | §9.2 Digest formulas and freshness | Overrides/1 and DiStyles/1 reject unknown targets/members, duplicate targets and non-closed shapes | refused `render-token-invalid` |
| `render.r.override-unknown-member` | §9.2 Digest formulas and freshness | Overrides/1 and DiStyles/1 reject unknown targets/members, duplicate targets and non-closed shapes | refused `render-token-invalid` |
| `render.r.override-unknown-occurrence-target` | §9.2 Digest formulas and freshness | Overrides/1 and DiStyles/1 reject unknown targets/members, duplicate targets and non-closed shapes | refused `render-stale` |
| `render.r.override-unknown-semantic-target` | §9.2 Digest formulas and freshness | Overrides/1 and DiStyles/1 reject unknown targets/members, duplicate targets and non-closed shapes | refused `render-stale` |
| `render.r.plain` | §9.1 Closed layout and render data | RenderData/1 for the neutral profile: style from binding then theme, glyphs, coverage of every ID-bearing element, full binding | ok |
| `render.r.precedence-shuffled-input` | §9.2 Digest formulas and freshness | reordered override/style tokens normalize identically (same R, same digests) | ok |
| `render.r.precedence-staircase` | §9.3 Per-notion style, text and glyph contracts | token precedence chain, each of the seven levels winning once; fallback chain root-first in themeDigest | ok |
| `render.r.shared-theme-not-compared` | §9.4 Region geometry, including Process IO | a single-theme render never refuses theme-geometry-conflict: the shared-geometry check runs only between two selected themes | ok |
| `render.r.sparse-override` | §9.3 Per-notion style, text and glyph contracts | sparse overrides stay sparse: one token on one occurrence, digest over the sparse record | ok |
| `render.r.style-conflict-glyph` | §9.3 Per-notion style, text and glyph contracts | matched bindings naming different glyphs refuse | refused `render-style-conflict` |
| `render.r.style-conflict-token` | §9.3 Per-notion style, text and glyph contracts | unequal values for one token at the same precedence refuse (no declaration-order winner) | refused `render-style-conflict` |
| `render.r.theme-alias` | §9.5 Legacy themes | a declared theme alias selects the theme; the binding records the theme id | ok |
| `render.r.theme-legacy-name-not-generic` | §9.5 Legacy themes | generic theme resolution never reads compatibility aliases | refused `render-stale` |
| `render.r.theme-unknown` | §9.2 Digest formulas and freshness | an unresolvable theme id is an unresolved input | refused `render-stale` |
| `render.r.token-arrow-unknown` | §9.3 Per-notion style, text and glyph contracts | render-token/1 boundary violation refuses | refused `render-token-invalid` |
| `render.r.token-bioc-invalid` | §9.3 Per-notion style, text and glyph contracts | DI style bags are validated with the same signatures | refused `render-token-invalid` |
| `render.r.token-color-trailing-newline` | §9.3 Per-notion style, text and glyph contracts | render-token/1 boundary violation refuses | refused `render-token-invalid` |
| `render.r.token-dash-unregistered` | §9.3 Per-notion style, text and glyph contracts | render-token/1 boundary violation refuses | refused `render-token-invalid` |
| `render.r.token-duplicate-name` | §9.3 Per-notion style, text and glyph contracts | render-token/1 boundary violation refuses | refused `render-token-invalid` |
| `render.r.token-fill-no-hash` | §9.3 Per-notion style, text and glyph contracts | render-token/1 boundary violation refuses | refused `render-token-invalid` |
| `render.r.token-fill-non-hex` | §9.3 Per-notion style, text and glyph contracts | render-token/1 boundary violation refuses | refused `render-token-invalid` |
| `render.r.token-fill-seven` | §9.3 Per-notion style, text and glyph contracts | render-token/1 boundary violation refuses | refused `render-token-invalid` |
| `render.r.token-fill-short` | §9.3 Per-notion style, text and glyph contracts | render-token/1 boundary violation refuses | refused `render-token-invalid` |
| `render.r.token-font-family-not-injected` | §9.3 Per-notion style, text and glyph contracts | render-token/1 boundary violation refuses | refused `render-token-invalid` |
| `render.r.token-font-size-boolean` | §9.3 Per-notion style, text and glyph contracts | render-token/1 boundary violation refuses | refused `render-token-invalid` |
| `render.r.token-font-size-negative` | §9.3 Per-notion style, text and glyph contracts | render-token/1 boundary violation refuses | refused `render-token-invalid` |
| `render.r.token-font-size-string` | §9.3 Per-notion style, text and glyph contracts | render-token/1 boundary violation refuses | refused `render-token-invalid` |
| `render.r.token-font-size-unsafe` | §9.3 Per-notion style, text and glyph contracts | render-token/1 boundary violation refuses | refused `render-token-invalid` |
| `render.r.token-font-weight-case` | §9.3 Per-notion style, text and glyph contracts | render-token/1 boundary violation refuses | refused `render-token-invalid` |
| `render.r.token-font-weight-unknown` | §9.3 Per-notion style, text and glyph contracts | render-token/1 boundary violation refuses | refused `render-token-invalid` |
| `render.r.token-null` | §9.3 Per-notion style, text and glyph contracts | render-token/1 boundary violation refuses | refused `render-token-invalid` |
| `render.r.token-semantic-invalid` | §9.3 Per-notion style, text and glyph contracts | semantic override bags are validated with the same signatures | refused `render-token-invalid` |
| `render.r.token-stroke-number` | §9.3 Per-notion style, text and glyph contracts | render-token/1 boundary violation refuses | refused `render-token-invalid` |
| `render.r.token-stroke-width-negative` | §9.3 Per-notion style, text and glyph contracts | render-token/1 boundary violation refuses | refused `render-token-invalid` |
| `render.r.token-unknown-name` | §9.3 Per-notion style, text and glyph contracts | render-token/1 boundary violation refuses | refused `render-token-invalid` |
| `render.r.token-valid-boundaries` | §9.3 Per-notion style, text and glyph contracts | each render-token/1 type at an admitted boundary | ok |
| `render.regions.clamp-left` | §9.4 Region geometry, including Process IO | an anchor left of the content box clamps to contentLeft | ok |
| `render.regions.empty-region` | §9.4 Region geometry, including Process IO | an empty item list leaves the body and the page unchanged (no minHeight or padding growth) | ok |
| `render.regions.grid-side` | §9.4 Region geometry, including Process IO | the second neutral profile's side row: label sizes, collision and width growth | ok |
| `render.regions.grow-page` | §9.4 Region geometry, including Process IO | a grown body beyond the page grows the page bounds | ok |
| `render.regions.grow-width-height` | §9.4 Region geometry, including Process IO | the body grows to the last right edge plus padding and to the row height; the page grows to contain it | ok |
| `render.regions.io-anchored` | §9.4 Region geometry, including Process IO | the shared region seam on the render.layout.io-anchored row | ok |
| `render.regions.min-height-centred` | §9.4 Region geometry, including Process IO | when minHeight dominates, the stacks are centred in the row | ok |
| `render.regions.mixed-label-heights` | §9.4 Region geometry, including Process IO | object centres stay on one line when label heights differ (no per-stack centring) | ok |
| `render.regions.mixed-object-heights` | §9.4 Region geometry, including Process IO | a tall object without label next to a short object with a tall label: centres on one line and the body grows to contain the union | ok |
| `render.regions.no-anchor` | §9.4 Region geometry, including Process IO | items without an available anchor follow contentLeft then previous right + gap | ok |
| `render.regions.reference-band` | §9.4 Region geometry, including Process IO | a reference band uses the same header/padding rule with its own tokens | ok |
| `render.regions.round-half-even` | §9.4 Region geometry, including Process IO | exact rationals, one roundEven per output coordinate | ok |
| `render.regions.token-missing` | §9.4 Region geometry, including Process IO | region numeric inputs are injected tokens; a missing token refuses | refused `render-region-missing` |
| `render.regions.wider-labels` | §9.4 Region geometry, including Process IO | label-wide footprints, object and label centred in the footprint, object centres on one line | ok |
| `render.regions.zero-tokens` | §9.4 Region geometry, including Process IO | zero-valued tokens are used as given (no hidden default) | ok |
| `render.switch.chain-resolution` | §9.4 shared geometry; §16 item 6 (OPEN-DI / OPEN-LOOK) | geometry tokens resolve through the fallback chain | ok |
| `render.switch.metrics-resource-differs` | §9.4 shared geometry; §16 item 6 (OPEN-DI / OPEN-LOOK) | the metrics resource is geometry-affecting | refused `theme-geometry-conflict` |
| `render.switch.missing-token` | §9.4 shared geometry; §16 item 6 (OPEN-DI / OPEN-LOOK) | a token missing from one chain is a difference, never equal by default | refused `theme-geometry-conflict` |
| `render.switch.own-geometry-gated` | §9.4 shared geometry; §16 item 6 (OPEN-DI / OPEN-LOOK) | a geometry:theme target stays disabled while the policy is not approved | refused `profile-open` |
| `render.switch.paint-only` | §9.4 shared geometry; §16 item 6 (OPEN-DI / OPEN-LOOK) | a paint-only switch keeps the shared geometry | ok |
| `render.switch.region-token-differs` | §9.4 shared geometry; §16 item 6 (OPEN-DI / OPEN-LOOK) | shared themes with different region tokens refuse | refused `theme-geometry-conflict` |
| `render.switch.text-fit-token-differs` | §9.4 shared geometry; §16 item 6 (OPEN-DI / OPEN-LOOK) | font tokens are geometry-affecting | refused `theme-geometry-conflict` |
| `render.switch.unknown-theme` | §9.2 Digest formulas and freshness | an unknown theme id is an unresolved input | refused `render-stale` |
| `render.template.attached-badge-negative-offset` | §9.3 Per-notion style, text and glyph contracts | signed tick offsets | ok |
| `render.template.attached-badge` | §9.3 Per-notion style, text and glyph contracts | badge at (node.x+offsetX, node.y+node.height+offsetY) with the declared badge size; markerShift echoed | ok |
| `render.template.band-stripe-clamped` | §9.3 Per-notion style, text and glyph contracts | band-stripe takes a leading vertical rectangle of width min(stripeWidth, region.width), full height | ok |
| `render.template.band-stripe-zero` | §9.3 Per-notion style, text and glyph contracts | band-stripe takes a leading vertical rectangle of width min(stripeWidth, region.width), full height | ok |
| `render.template.band-stripe` | §9.3 Per-notion style, text and glyph contracts | band-stripe takes a leading vertical rectangle of width min(stripeWidth, region.width), full height | ok |
| `render.template.corner-fold-decimal-ratio` | §9.3 Per-notion style, text and glyph contracts | corner-fold size roundEven(min(w,h)*foldRatio) and its three-point path | ok |
| `render.template.corner-fold-height-min` | §9.3 Per-notion style, text and glyph contracts | corner-fold size roundEven(min(w,h)*foldRatio) and its three-point path | ok |
| `render.template.corner-fold-rotation-center-up` | §9.3 Per-notion style, text and glyph contracts | rotation centre ties round to the even neighbour upwards | ok |
| `render.template.corner-fold-rotation-center` | §9.3 Per-notion style, text and glyph contracts | header text rotates about its label bounds centre; the centre rounds once, ties to even | ok |
| `render.template.corner-fold-tie-down` | §9.3 Per-notion style, text and glyph contracts | corner-fold size roundEven(min(w,h)*foldRatio) and its three-point path | ok |
| `render.template.corner-fold-tie-up` | §9.3 Per-notion style, text and glyph contracts | corner-fold size roundEven(min(w,h)*foldRatio) and its three-point path | ok |
| `render.template.corner-fold-zero` | §9.3 Per-notion style, text and glyph contracts | corner-fold size roundEven(min(w,h)*foldRatio) and its three-point path | ok |
| `render.template.corner-fold` | §9.3 Per-notion style, text and glyph contracts | corner-fold size roundEven(min(w,h)*foldRatio) and its three-point path | ok |
| `render.template.header-band-body-grows` | §9.3 Per-notion style, text and glyph contracts | the header keeps its fixed height when the body grows (no uniform scaling) | ok |
| `render.template.header-band-clamped` | §9.3 Per-notion style, text and glyph contracts | headerHeight larger than h is clamped by min(headerHeight,h) | ok |
| `render.template.header-band-grid-glyph` | §9.3 Per-notion style, text and glyph contracts | the second neutral profile's own header-band glyph (headerHeight 12) | ok |
| `render.template.header-band` | §9.3 Per-notion style, text and glyph contracts | header-band divides at y+min(headerHeight,h) | ok |
| `render.template.native-glyph` | §9.3 Per-notion style, text and glyph contracts | template geometry exists only for template glyphs | refused `render-unsupported` |
| `render.template.param-boolean` | §9.3 Per-notion style, text and glyph contracts | template parameter or viewBox violation refuses | refused `profile-glyph-shape` |
| `render.template.param-duplicate` | §9.3 Per-notion style, text and glyph contracts | template parameter or viewBox violation refuses | refused `profile-glyph-shape` |
| `render.template.param-extra` | §9.3 Per-notion style, text and glyph contracts | template parameter or viewBox violation refuses | refused `profile-glyph-shape` |
| `render.template.param-fraction` | §9.3 Per-notion style, text and glyph contracts | template parameter or viewBox violation refuses | refused `profile-glyph-shape` |
| `render.template.param-missing` | §9.3 Per-notion style, text and glyph contracts | template parameter or viewBox violation refuses | refused `profile-glyph-shape` |
| `render.template.param-negative` | §9.3 Per-notion style, text and glyph contracts | template parameter or viewBox violation refuses | refused `profile-glyph-shape` |
| `render.template.param-ratio-range` | §9.3 Per-notion style, text and glyph contracts | template parameter or viewBox violation refuses | refused `profile-glyph-shape` |
| `render.template.param-rotation` | §9.3 Per-notion style, text and glyph contracts | template parameter or viewBox violation refuses | refused `profile-glyph-shape` |
| `render.template.param-string` | §9.3 Per-notion style, text and glyph contracts | template parameter or viewBox violation refuses | refused `profile-glyph-shape` |
| `render.template.viewbox-zero` | §9.3 Per-notion style, text and glyph contracts | template parameter or viewBox violation refuses | refused `profile-glyph-shape` |
| `render.text.measure-fallback-widths` | §9.3 Per-notion style, text and glyph contracts | missing scalar widths use the declared fallback width; scalars not UTF-16 units; no NFC; case and width separate | ok |
| `render.ticks.half-even` | §3.1 Canonicalization (rounding, ticks) | pt values times 1000 round once, ties to even (also below zero) | ok |
| `render.ticks.large-and-integral` | §3.1 Canonicalization (rounding, ticks) | integral DI values are exact and large values keep exact ties | ok |
| `render.ticks.negative-zero-and-tiny` | §3.1 Canonicalization (rounding, ticks) | negative zero and sub-half values become integer 0 | ok |
| `render.ticks.rational-not-binary` | §3.1 Canonicalization (rounding, ticks) | the conversion uses the exact rational of the shortest decimal form, not the binary64 product | ok |

## Appendix B — export tree (`tests/profile_export/expected/`, 83 cases)

| Case | DESIGN clause | Witness | Expected |
| --- | --- | --- | --- |
| `export.compile.all-fields-valid` | §2.4.1 CR-11; §10.2 export-ir/1 | every optional common field with its type compiles | ok |
| `export.compile.digest-nonzero-origin` | §2.4.1 CR-11; §10.2 export-ir/1 | non-counter policies require counterOrigin zero | refused `profile-type` |
| `export.compile.digest-zero-origin` | §2.4.1 CR-11; §10.2 export-ir/1 | a non-counter policy with counterOrigin 0 compiles | ok |
| `export.compile.edge-fill` | §2.4.1 CR-11; §10.2 export-ir/1 | fill is a node field, not an edge field | refused `profile-export-field` |
| `export.compile.edge-missing-target` | §2.4.1 CR-11; §10.2 export-ir/1 | edge requires id, source and target | refused `profile-export-field` |
| `export.compile.label-missing-text` | §2.4.1 CR-11; §10.2 export-ir/1 | label requires id and text | refused `profile-export-field` |
| `export.compile.metadata-missing-value` | §2.4.1 CR-11; §10.2 export-ir/1 | metadata requires name and value | refused `profile-export-field` |
| `export.compile.native-nonzero-origin` | §2.4.1 CR-11; §10.2 export-ir/1 | non-counter policies require counterOrigin zero | refused `profile-type` |
| `export.compile.node-duplicate-field` | §2.4.1 CR-11; §10.2 export-ir/1 | duplicate fields refuse | refused `profile-export-field` |
| `export.compile.node-fill-number` | §2.4.1 CR-11; §10.2 export-ir/1 | string fields need strings | refused `profile-export-field` |
| `export.compile.node-font-size-string` | §2.4.1 CR-11; §10.2 export-ir/1 | numeric fields need numbers | refused `profile-export-field` |
| `export.compile.node-unknown-field` | §2.4.1 CR-11; §10.2 export-ir/1 | fields outside the node vocabulary refuse | refused `profile-export-field` |
| `export.compile.page-missing-name` | §2.4.1 CR-11; §10.2 export-ir/1 | page requires string id and name | refused `profile-export-field` |
| `export.compile.page-parent` | §2.4.1 CR-11; §10.2 export-ir/1 | a page emits at the artifact root and must omit parent | refused `profile-type` |
| `export.compile.page-shape` | §2.4.1 CR-11; §10.2 export-ir/1 | page.shape cannot pass | refused `profile-export-field` |
| `export.legacy.duplicate-id` | §10.2 legacy diagnostic adapter table; §10.1 adapters | IoError duplicate-id row | ok |
| `export.legacy.fidelity-notice-loss` | §10.2 legacy diagnostic adapter table; §10.1 adapters | known FidelityNotice with a declared loss class maps like the loss action | ok |
| `export.legacy.fidelity-notice-undeclared-class` | §10.2 legacy diagnostic adapter table; §10.1 adapters | a FidelityNotice maps only when the manifest declares its loss class | ok |
| `export.legacy.fidelity-notice-unknown-class` | §10.2 legacy diagnostic adapter table; §10.1 adapters | a FidelityNotice without a closed loss class is not known | ok |
| `export.legacy.invalid-reference` | §10.2 legacy diagnostic adapter table; §10.1 adapters | IoError invalid-reference: one integrity entry per ID, pointer only when indexed | ok |
| `export.legacy.known-family-not-in-manifest` | §10.2 legacy diagnostic adapter table; §10.1 adapters | no code is guessed: a table code missing from the adapter manifest is legacy-unmapped | ok |
| `export.legacy.missing-endpoint` | §10.2 legacy diagnostic adapter table; §10.1 adapters | IoError missing-endpoint row | ok |
| `export.legacy.unknown-format` | §10.2 legacy diagnostic adapter table; §10.1 adapters | IoError unknown-format row | ok |
| `export.legacy.unlisted-code` | §10.2 legacy diagnostic adapter table; §10.1 adapters | closed fallback: an unlisted legacy code is legacy-unmapped | ok |
| `export.legacy.unsupported-format` | §10.2 legacy diagnostic adapter table; §10.1 adapters | IoError unsupported-format row | ok |
| `export.map.bind-ambiguous` | §2.4 bind; §10.2 | a bind with cardinality one over several handles refuses profile-ambiguous-binding | refused `profile-ambiguous-binding` |
| `export.map.capability-byte-claim` | §10.2; §13 OPEN-EXPORT-EVIDENCE | no feature becomes byte-compatible by declaration alone | ok |
| `export.map.capability-losses` | §10.2 Export recipe, capability and loss contract | capability predicates evaluate once per occurrence; declared losses map like the loss action | ok |
| `export.map.capability-none` | §10.2 Export recipe, capability and loss contract | with no applicable capability record the artifact stays at the structural ceiling | ok |
| `export.map.capability-unsupported` | §10.2 Export recipe, capability and loss contract | an unsupported necessary occurrence refuses the entire artifact (no partially valid download) | refused `render-unsupported` |
| `export.map.compat-digest-mismatch` | §3.3 compatibility decision; §10.2 | compatibility rows apply before export | refused `profile-digest-mismatch` |
| `export.map.counter-reuse` | §10.2 Export recipe, capability and loss contract | repeated outputId requests reuse one ID; only requested keys are allocated | ok |
| `export.map.digest-policy` | §10.2 Export recipe, capability and loss contract | digest output IDs are e_ + full SHA-256 of JCS [pageId, occurrenceKey, domain] | ok |
| `export.map.edge-before-nodes` | §10.2 Export recipe, capability and loss contract | nodes before edges: an edge endpoint emitted later refuses export-parent-order | refused `export-parent-order` |
| `export.map.feature-table-witnesses` | §10.2 Export recipe, capability and loss contract | the DESIGN §10.2 feature rows on one drawio artifact: DataStore + DataStoreReference, reference-band and main Participants, Process IO and data associations, Documentation markers, internal calledElement navigation, Terminate | ok |
| `export.map.field-missing-required` | §10.2 Export recipe, capability and loss contract | a required named field evaluating to MISSING refuses export-field-invalid | refused `export-field-invalid` |
| `export.map.format-unknown` | §10.2 Export recipe, capability and loss contract | a format absent from the profile exports refuses export-format-unsupported | refused `export-format-unsupported` |
| `export.map.format-without-adapter` | §10.2 Export recipe, capability and loss contract | a declared format without a registered Python adapter refuses export-format-unsupported | refused `export-format-unsupported` |
| `export.map.grid-fixture` | §10.2 Export recipe, capability and loss contract | counterOrigin 10, a later child emission uses an earlier preallocated number, node parent of a node | ok |
| `export.map.kinds-and-losses` | §10.2 Export recipe, capability and loss contract | every export-ir/1 kind, edge endpoints, artifact-global and page metadata, each loss class through the loss action mapping, adapter-declared metadata losses | ok |
| `export.map.native-policy-anonymous` | §10.2 Export recipe, capability and loss contract | an occurrence without semanticId cannot take a native ID | refused `export-id-ambiguous` |
| `export.map.native-policy-duplicate` | §10.2 Export recipe, capability and loss contract | native IDs that are not unique in the artifact refuse export-id-ambiguous | refused `export-id-ambiguous` |
| `export.map.native-policy-repeated-view` | §10.2 Export recipe, capability and loss contract | repeated views of one semantic ID make native IDs ambiguous | refused `export-id-ambiguous` |
| `export.map.native-policy` | §10.2 Export recipe, capability and loss contract | native ID policy: pageId for a page, semanticId for a semantic occurrence when unique | ok |
| `export.map.neutral-fixture` | §10.2 Export recipe, capability and loss contract | export IR of the first neutral fixture: counter order, implicit page parents, copied R values, capability losses, repeated-view idMap | ok |
| `export.map.optional-field-missing` | §10.2 Export recipe, capability and loss contract | an optional named field evaluating to MISSING is omitted; no idMap row without a source identity | ok |
| `export.map.output-id-native-ambiguous` | §2.2 outputId; §10.2 | a native handle with two occurrences on the current page refuses export-occurrence-ambiguous | refused `export-occurrence-ambiguous` |
| `export.map.output-id-native-handle` | §2.2 outputId; §10.2 | outputId on a native handle resolves the one exact current-page occurrence | ok |
| `export.map.parent-invalid-cycle` | §10.2 Export recipe, capability and loss contract | a parent equal to the record's own id is a cycle | refused `export-parent-invalid` |
| `export.map.parent-invalid-duplicate` | §10.2 Export recipe, capability and loss contract | duplicate artifact keys refuse export-parent-invalid | refused `export-parent-invalid` |
| `export.map.parent-invalid-kind` | §10.2 Export recipe, capability and loss contract | a parent of incompatible kind refuses export-parent-invalid | refused `export-parent-invalid` |
| `export.map.parent-invalid-unknown` | §10.2 Export recipe, capability and loss contract | a handle that this call never emits (cross-call handle) refuses export-parent-invalid | refused `export-parent-invalid` |
| `export.map.parent-order` | §10.2 Export recipe, capability and loss contract | pages before containers: an implicit page parent not yet emitted refuses export-parent-order | refused `export-parent-order` |
| `export.map.refuse-action` | §2.4 refuse; §10.2 | a refuse action aborts the complete export atomically | refused `export-blocked` |
| `export.map.render-unsupported` | §9.3; §10.1 unsupported necessary occurrence | R coverage with an unsupported element refuses the export | refused `render-unsupported` |
| `export.map.sequence-aba` | §10.2 Export recipe, capability and loss contract | the symbol table lasts one call, is discarded on refusal and never survives A->B->A | sequence: ok, refused `export-parent-order`, ok |
| `export.map.stale-descriptor` | §9.2 Digest formulas and freshness | each stale binding field returns render-stale | refused `render-stale` |
| `export.map.stale-layout` | §9.2 Digest formulas and freshness | a changed page name after R invalidates layoutDigest | refused `render-stale` |
| `export.map.stale-metrics` | §9.2 Digest formulas and freshness | each stale binding field returns render-stale | refused `render-stale` |
| `export.map.stale-occurrence-geometry` | §9.2 Digest formulas and freshness | an R whose occurrence geometry differs from the supplied layout record is stale even when its digests were recomputed | refused `render-stale` |
| `export.map.stale-payload` | §9.2 Digest formulas and freshness | a payload edited after binding fails payloadDigest | refused `render-stale` |
| `export.map.stale-profile` | §9.2 Digest formulas and freshness | each stale binding field returns render-stale | refused `render-stale` |
| `export.map.stale-semantic` | §9.2 Digest formulas and freshness | R bound to an older semantic revision is stale | refused `render-stale` |
| `export.map.stale-theme-digest` | §9.2 Digest formulas and freshness | each stale binding field returns render-stale | refused `render-stale` |
| `export.map.stale-theme-unknown` | §9.2 Digest formulas and freshness | each stale binding field returns render-stale | refused `render-stale` |
| `export.prepare.compat-refusal` | §10.2 prepareExport; §6.2 stage table | compatibility runs right after option validation: refusal with an empty report, no artifact, no mutation | refused `profile-digest-mismatch` |
| `export.prepare.lint-refusal-stage-order` | §10.2 prepareExport; §6.2 stage table | stage order: the first blocking lint stage (pre-normalize, accept) refuses with the complete report so far | refused `bpmnlint/end-event-required` |
| `export.prepare.missing-support` | §10.2 prepareExport; §6.2 stage table | preparation never creates supports: placements into an unbound region refuse profile-open | refused `profile-open` |
| `export.prepare.options-unknown-member` | §10.2 prepareExport; §6.2 stage table | the option record is closed | refused `operation-error` |
| `export.prepare.repairable-not-repaired` | §10.2 prepareExport; §6.2 stage table | a declared repair recipe that does not repair leaves the pre-N error unresolved after N | refused `association-direction-missing` |
| `export.prepare.repairable-pre-normalize` | §10.2 prepareExport; §6.2 stage table | a repairable pre-N error with its declared bounded repair recipe continues, is repaired by N and stays in the report as corrected | ok |
| `export.prepare.repairable-without-recipe` | §10.2 prepareExport; §6.2 stage table | a repairable pre-N error without a declared repair recipe blocks at pre-normalize | refused `association-direction-missing` |
| `export.prepare.success` | §10.2 prepareExport; §6.2 stage table | end-to-end preparation on a post-N fixed point: C, lint, N, layout, R and map under accept | ok |
| `export.prepare.unknown-format` | §10.2 prepareExport; §6.2 stage table | an option format without an exports[] record and adapter refuses before the pipeline | refused `export-format-unsupported` |
| `export.prepare.unknown-theme` | §10.2 prepareExport; §6.2 stage table | an option theme that resolves to no theme refuses before the pipeline | refused `render-stale` |
| `export.serialize.drawio-grid-fixture` | §10.1 serializePrepared; §10.2 OPEN-EXPORT-EVIDENCE | a node parented to another node keeps that parent in the serialized cells | ok (structural) |
| `export.serialize.drawio-kinds` | §10.1 serializePrepared; §10.2 OPEN-EXPORT-EVIDENCE | structural serialization with an edge, a label record and metadata records | ok (structural) |
| `export.serialize.drawio-neutral-fixture` | §10.1 serializePrepared; §10.2 OPEN-EXPORT-EVIDENCE | structural draw.io serialization of a prepared artifact; digest = B(bytes); idMap and capability carried | ok (structural) |
| `export.serialize.format-unsupported` | §10.1 serializePrepared; §10.2 OPEN-EXPORT-EVIDENCE | only registered adapters serialize | refused `export-format-unsupported` |
| `export.serialize.stale-descriptor-digest` | §10.1 serializePrepared; §10.2 OPEN-EXPORT-EVIDENCE | the preparation descriptor pins must still match its renderBinding | refused `render-stale` |
| `export.serialize.stale-profile-digest` | §10.1 serializePrepared; §10.2 OPEN-EXPORT-EVIDENCE | the preparation identity must still name the profile its renderBinding was bound to | refused `render-stale` |
| `export.serialize.stale-semantic` | §10.1 serializePrepared; §10.2 OPEN-EXPORT-EVIDENCE | the prepared semantic revision must match its renderBinding | refused `render-stale` |
| `export.serialize.stale-view` | §10.1 serializePrepared; §10.2 OPEN-EXPORT-EVIDENCE | serialization verifies renderBinding freshness | refused `render-stale` |

## Appendix C — vendored JS cases of the render tree (`tests/profile_render/expected/`, 107 records + 2 twins)

| Case | DESIGN clause | Operation | Expected | Parity sync |
| --- | --- | --- | --- | --- |
| `admission-001-lot4-package` | §2.4.1 L186–L199; §2.4 L164 | `compileProfile` | ok | vendored unchanged |
| `admission-002-variant-conflict` | §2.4.1 L194–L196; §10.2 L770–L774 | `compileProfile` | ok | vendored unchanged |
| `admission-003-variant-labels-native` | §2.4.1 L194–L196; §10.2 L770–L774 | `compileProfile` | ok | vendored unchanged |
| `admission-004-variant-byte-claim` | §2.4.1 L194–L196; §10.2 L770–L774 | `compileProfile` | ok | vendored unchanged |
| `admission-005-variant-unsupported` | §2.4.1 L194–L196; §10.2 L770–L774 | `compileProfile` | ok | vendored unchanged |
| `admission-006-variant-parent-order` | §2.4.1 L194–L196; §10.2 L770–L774 | `compileProfile` | ok | vendored unchanged |
| `admission-007-variant-dup-emit` | §2.4.1 L194–L196; §10.2 L770–L774 | `compileProfile` | ok | vendored unchanged |
| `admission-008-variant-missing-field` | §2.4.1 L194–L196; §10.2 L770–L774 | `compileProfile` | ok | vendored unchanged |
| `admission-009-neutral-successor` | §14.3 L961; §2.4 L164 | `compileProfile` | ok | vendored unchanged |
| `admission-010-grid-successor` | §14.3 L961; §2.4 L164 | `compileProfile` | ok | vendored unchanged |
| `decision-001-question-and-choices` | §14.3 L971; §9.3 L698–L702 | `resolveTheme` | ok | vendored unchanged |
| `decision-002-lower-final-sigma` | §9.3 L702; §2.2 L116 | `resolveTheme` | ok | vendored unchanged |
| `decision-003-host-case-stale` | §9.3 L702; §9.2 L690 | `resolveTheme` | refused `render-stale` | vendored unchanged |
| `decision-004-locale-case-stale` | §9.3 L702; §2.2 L116 | `resolveTheme` | refused `render-stale` | vendored unchanged |
| `decision-005-case-operator` | §2.2 L116; §9.3 L702 | `evaluateValue` | ok | vendored unchanged |
| `digest-001-page-rename` | §9.1 L667; §9.2 L683–L690 | `resolveTheme` | ok | vendored unchanged |
| `digest-002-label-move` | §9.2 L683–L690 | `resolveTheme` | ok | vendored unchanged |
| `digest-003-baseline` | §9.2 L679–L690 | `renderDigests` | ok | vendored unchanged |
| `digest-004-descriptor-pins-reversed` | §9.2 L682; §9.2 L694 | `renderDigests` | ok | vendored unchanged |
| `digest-005-metric-resources-reversed` | §9.2 L687; §9.2 L694 | `renderDigests` | ok | vendored unchanged |
| `digest-006-metric-byte-changed` | §9.2 L687; §9.2 L694 | `renderDigests` | ok | vendored unchanged |
| `digest-007-bags-sorted` | §9.2 L685–L686; §9.2 L692–L694 | `renderDigests` | ok | vendored unchanged |
| `digest-008-bags-reversed` | §9.2 L692–L694 | `renderDigests` | ok | vendored unchanged |
| `history-001-theme-round-trip` | §8.2 L643; §9.2 L694 | `theme-sequence` | ok | vendored unchanged |
| `history-002-override-round-trip` | §9.2 L694; §8.2 L643 | `theme-sequence` | ok | vendored unchanged |
| `layout-001-main` | §9.1 L667; §9.4 L721–L723 | `layout` | ok | vendored unchanged |
| `layout-002-repeated-views` | §9.4 L725; §9.1 L667 | `layout` | ok | vendored unchanged |
| `layout-003-multi-process` | §9.4 L725 | `layout` | ok | vendored unchanged |
| `layout-004-empty-process` | §9.4 L725 | `layout` | ok | vendored unchanged |
| `layout-005-missing-lane` | §9.4 L721; §9.3 L715 | `layout` | refused `render-region-missing` | vendored unchanged |
| `layout-006-neutral-fixture` | §9.4 L721; §9.3 L715 | `layout` | refused `render-region-missing` | vendored unchanged |
| `layout-007-grid-fixture` | §9.4 L721; §9.3 L715 | `layout` | refused `render-region-missing` | vendored unchanged |
| `layout-008-neutral-successor` | §14.3 L961; §9.4 L721–L723 | `layout` | ok | PS-06 |
| `layout-009-grid-successor` | §14.3 L961; §9.4 L721–L723; §9.3 L713–L715 | `layout` | ok | PS-06 |
| `layout-010-anchor-twice` | §9.4 L723 | `layout` | ok | vendored unchanged |
| `layout-011-geometry-theme-gated` | §9.4 L721; §13 L928; §16 L1150 | `layout` | refused `profile-open` | vendored unchanged |
| `legacy-001-standard` | §9.5 L729 | `resolveLegacyTheme` | ok | vendored unchanged |
| `legacy-002-legend` | §9.5 L729 | `resolveLegacyTheme` | ok | vendored unchanged |
| `legacy-003-colored` | §9.5 L729 | `resolveLegacyTheme` | ok | vendored unchanged |
| `legacy-004-no-alias-data` | §9.5 L729; §9.2 L690 | `resolveLegacyTheme` | refused `render-stale` | vendored unchanged |
| `legacy-005-exact-name` | §9.5 L729; §9.2 L690 | `resolveLegacyTheme` | refused `render-stale` | vendored unchanged |
| `legacy-006-alias-not-theme` | §9.5 L729; §9.2 L690 | `resolveTheme` | refused `render-stale` | vendored unchanged |
| `legacy-007-colored-sparse-di` | §9.5 L729; §9.3 L700 | `resolveTheme` | ok | vendored unchanged |
| `legacy-008-look-independent-recognition` | §9.5 L729; §9.3 L698 | `resolveTheme` | ok | vendored unchanged |
| `region-001-single-anchored` | §9.4 L721–L723 | `layoutRegions` | ok | PS-33 |
| `region-002-wider-label` | §9.4 L721–L723 | `layoutRegions` | ok | PS-33 |
| `region-003-collision-shift` | §9.4 L721–L723 | `layoutRegions` | ok | PS-33 |
| `region-004-no-anchor-sequence` | §9.4 L721–L723 | `layoutRegions` | ok | PS-33 |
| `region-005-mixed-anchor` | §9.4 L721–L723 | `layoutRegions` | ok | PS-33 |
| `region-006-clamp-left` | §9.4 L721–L723 | `layoutRegions` | ok | PS-33 |
| `region-007-grow-lane-width` | §9.4 L721–L723 | `layoutRegions` | ok | PS-33 |
| `region-008-grow-page` | §9.4 L721–L723 | `layoutRegions` | ok | PS-33 |
| `region-009-grow-lane-height` | §9.4 L721–L723 | `layoutRegions` | ok | PS-33 |
| `region-010-mixed-heights` | — | — | — | twin of `render.regions.mixed-label-heights` (PS-06, PS-33; PS-37), no record |
| `region-011-single-rounding` | §9.4 L721–L723 | `layoutRegions` | ok | PS-33 |
| `region-012-band-row` | §9.4 L721–L725 | `layoutRegions` | ok | PS-33 |
| `region-013-empty-region` | §9.4 L723–L725 | `layoutRegions` | ok | PS-33 |
| `region-014-zero-tokens` | §9.4 L721–L723 | `layoutRegions` | ok | PS-33 |
| `region-015-repeated-view` | §9.4 L721–L725 | `layoutRegions` | ok | PS-33 |
| `region-016-multi-band-a` | §9.4 L721–L725 | `layoutRegions` | ok | PS-33 |
| `region-017-multi-band-b` | §9.4 L721–L725 | `layoutRegions` | ok | PS-33 |
| `render-001-main-plain` | §9.1 L669–L673; §9.2 L679–L690; §9.3 L698–L700 | `resolveTheme` | ok | vendored unchanged |
| `render-002-repeated-views` | §9.1 L671–L673; §2.2 L126 | `resolveTheme` | ok | vendored unchanged |
| `render-003-multi-process` | §9.1 L671–L673 | `resolveTheme` | ok | vendored unchanged |
| `render-004-empty-process` | §9.1 L673; §9.4 L725 | `resolveTheme` | ok | vendored unchanged |
| `render-005-neutral-fixture` | §9.1 L669–L673; §9.3 L698–L702 | `resolveTheme` | ok | vendored unchanged |
| `render-006-token-precedence` | §9.3 L700; §9.2 L692 | `resolveTheme` | ok | vendored unchanged |
| `render-007-reordered-bags` | §9.2 L692–L694 | `resolveTheme` | ok | vendored unchanged |
| `render-008-sparse-occurrence-override` | §9.3 L700; §9.2 L692 | `resolveTheme` | ok | vendored unchanged |
| `render-009-semantic-override` | §9.3 L700; §9.1 L673 | `resolveTheme` | ok | vendored unchanged |
| `render-010-style-conflict` | §9.3 L698 | `resolveTheme` | refused `render-style-conflict` | vendored unchanged |
| `render-011-token-unknown` | §9.3 L700; §9.1 L673 | `resolveTheme` | refused `render-token-invalid` | vendored unchanged |
| `render-012-token-value` | §9.3 L700; §9.1 L673 | `resolveTheme` | refused `render-token-invalid` | vendored unchanged |
| `render-013-token-negative` | §9.3 L700; §9.1 L673 | `resolveTheme` | refused `render-token-invalid` | vendored unchanged |
| `render-014-stale-choice-label` | §9.2 L690; §9.3 L698 | `resolveTheme` | refused `render-stale` | vendored unchanged |
| `render-015-missing-label` | §9.2 L690; §9.1 L671 | `resolveTheme` | refused `render-stale` | vendored unchanged |
| `render-016-extra-label` | §9.2 L690; §9.3 L698 | `resolveTheme` | refused `render-stale` | vendored unchanged |
| `render-017-unsupported-coverage` | §9.1 L673; §9.3 L704 | `resolveTheme` | ok | vendored unchanged |
| `render-018-unknown-theme` | §9.2 L690 | `resolveTheme` | refused `render-stale` | vendored unchanged |
| `render-019-theme-alias` | §12 L837; §9.2 L684 | `resolveTheme` | ok | vendored unchanged |
| `render-020-geometry-theme-gated` | §9.4 L721; §13 L928; §16 L1150 | `resolveTheme` | refused `profile-open` | vendored unchanged |
| `render-021-neutral-successor` | §14.3 L961; §9.1 L669–L673 | `resolveTheme` | ok | PS-06 |
| `render-022-grid-successor` | §14.3 L961; §9.3 L713–L715; §9.3 L702 | `resolveTheme` | ok | PS-06 |
| `render-023-metric-chain` | §9.2 L687; §9.2 L694 | `resolveTheme` | ok | vendored unchanged |
| `render-024-variety` | §9.3 L698; §9.1 L673 | `resolveTheme` | ok | vendored unchanged |
| `switch-001-paint-only` | §9.4 L721; §16 L1150 | `checkThemeSwitch` | ok | vendored unchanged |
| `switch-002-region-token` | §9.4 L721; §16 L1150 | `checkThemeSwitch` | refused `theme-geometry-conflict` | vendored unchanged |
| `switch-003-text-fit-token` | §9.4 L721; §16 L1150 | `checkThemeSwitch` | refused `theme-geometry-conflict` | vendored unchanged |
| `switch-004-own-geometry` | §9.4 L721; §13 L928; §16 L1150 | `checkThemeSwitch` | refused `profile-open` | vendored unchanged |
| `switch-005-missing-token` | §9.4 L721; §16 L1150 | `checkThemeSwitch` | refused `theme-geometry-conflict` | vendored unchanged |
| `switch-006-legacy-chain` | §9.4 L721; §16 L1150 | `checkThemeSwitch` | ok | vendored unchanged |
| `switch-007-metrics-resource` | §9.4 L721; §9.3 L702 | `checkThemeSwitch` | refused `theme-geometry-conflict` | vendored unchanged |
| `synthetic-001-band-stripe` | §9.3 L713–L715; §9.1 L667 | `layout` | ok | vendored unchanged |
| `synthetic-002-per-page` | §9.3 L715 | `layout` | ok | vendored unchanged |
| `synthetic-003-per-owner` | §9.3 L715 | `layout` | ok | vendored unchanged |
| `synthetic-004-region-missing` | §9.3 L715 | `layout` | refused `render-region-missing` | vendored unchanged |
| `synthetic-005-grid-fixture` | §9.3 L715 | `layout` | refused `render-region-missing` | vendored unchanged |
| `synthetic-006-attached-badge` | §9.3 L712; §9.4 L725 | `layout` | ok | vendored unchanged |
| `synthetic-007-badge-ambiguous-anchor` | §9.3 L712; §9.3 L715 | `layout` | refused `render-region-missing` | vendored unchanged |
| `synthetic-008-badge-no-anchor` | §9.3 L712; §9.3 L715 | `layout` | refused `render-region-missing` | vendored unchanged |
| `synthetic-009-badge-hide-source` | §9.3 L712; §9.3 L717; §13 L924 | `layout` | refused `render-unsupported` | vendored unchanged |
| `synthetic-010-unbound-region` | §9.4 L721; §9.3 L715 | `layout` | refused `render-region-missing` | vendored unchanged |
| `synthetic-011-stripe-styled` | §9.3 L715; §9.1 L673 | `resolveTheme` | ok | vendored unchanged |
| `synthetic-012-badge-styled` | §9.3 L712; §9.3 L715 | `resolveTheme` | ok | vendored unchanged |
| `synthetic-013-foreign-record` | §9.1 L673; §9.2 L690 | `resolveTheme` | refused `render-stale` | vendored unchanged |
| `ticks-001-half-even` | — | — | — | twin of `render.ticks.half-even` (PS-33; PS-37), no record |
| `ticks-002-rational-not-binary` | §3.1 L270 | `layoutTicks` | ok | PS-33 |
| `ticks-003-negative-zero-and-tiny` | §3.1 L270 | `layoutTicks` | ok | PS-33 |
| `ticks-004-large-and-integral` | §3.1 L270 | `layoutTicks` | ok | PS-33 |

## Appendix D — vendored JS cases of the export tree (`tests/profile_export/expected/`, 46 records)

| Case | DESIGN clause | Operation | Expected | Parity sync |
| --- | --- | --- | --- | --- |
| `bpmn-001-main-native` | §10.2 L790–L793 | `serializeBpmn` | ok | vendored unchanged |
| `bpmn-002-multi-native` | §10.2 L790–L791 | `serializeBpmn` | ok | vendored unchanged |
| `bpmn-003-variety-native` | §10.2 L794–L796 | `serializeBpmn` | ok | vendored unchanged |
| `export-001-main-drawio` | §10.2 L770–L776; §10.2 L801; §10.1 L751–L753 | `mapExport` | ok | vendored unchanged |
| `export-002-main-sparx-native` | §2.2 L130; §10.2 L776; §10.2 L793 | `mapExport` | ok | vendored unchanged |
| `export-003-repeated-drawio` | §2.2 L130; §10.2 L801; §10.1 L753 | `mapExport` | ok | vendored unchanged |
| `export-004-repeated-sparx-ambiguous` | §2.2 L130 | `mapExport` | refused `export-id-ambiguous` | vendored unchanged |
| `export-005-multi-drawio` | §10.2 L790–L791; §10.2 L801 | `mapExport` | ok | vendored unchanged |
| `export-006-empty-drawio` | §10.2 L770–L774 | `mapExport` | ok | vendored unchanged |
| `export-007-synthetic-drawio` | §10.2 L770; §10.1 L753; §2.2 L130 | `mapExport` | ok | vendored unchanged |
| `export-008-synthetic-sparx-ambiguous` | §2.2 L130 | `mapExport` | refused `export-id-ambiguous` | vendored unchanged |
| `export-009-neutral-fixture` | §10.2 L770–L776; §10.2 L801 | `mapExport` | ok | vendored unchanged |
| `export-010-decision-labels` | §14.3 L971; §10.2 L772 | `mapExport` | ok | vendored unchanged |
| `export-011-labels-native-ambiguous` | §2.2 L130 | `mapExport` | refused `export-id-ambiguous` | vendored unchanged |
| `export-012-parent-order` | §10.2 L774 | `mapExport` | refused `export-parent-order` | vendored unchanged |
| `export-013-duplicate-key` | §10.2 L774 | `mapExport` | refused `export-parent-invalid` | vendored unchanged |
| `export-014-missing-required` | §10.2 L770 | `mapExport` | refused `export-field-invalid` | vendored unchanged |
| `export-015-unknown-format` | §10.2 L770; §10.2 L780 | `mapExport` | refused `export-format-unsupported` | vendored unchanged |
| `export-016-page-shape` | §10.2 L772 | `compileProfile` | refused `profile-export-field` | vendored unchanged |
| `export-017-byte-claim-unqualified` | §10.2 L799; §10.1 L753; §13 L933 | `mapExport` | ok | vendored unchanged |
| `export-018-unsupported-capability` | §10.1 L753; §10.2 L797 | `mapExport` | refused `render-unsupported` | vendored unchanged |
| `export-019-unsupported-coverage` | §10.2 L797; §10.1 L753 | `mapExport` | refused `render-unsupported` | vendored unchanged |
| `export-020-stale-layout` | §9.2 L690 | `mapExport` | refused `render-stale` | vendored unchanged |
| `export-021-stale-envelope` | §9.2 L690 | `mapExport` | refused `render-stale` | vendored unchanged |
| `export-022-stale-payload` | §9.2 L690 | `mapExport` | refused `render-stale` | vendored unchanged |
| `export-023-stale-theme` | §9.2 L690 | `mapExport` | refused `render-stale` | vendored unchanged |
| `export-024-occurrence-mismatch` | §9.2 L690 | `mapExport` | refused `render-stale` | vendored unchanged |
| `export-025-neutral-successor` | §14.3 L961; §10.2 L776; §10.2 L801 | `mapExport` | ok | PS-06 |
| `export-026-grid-successor` | §14.3 L961; §10.2 L774; §10.2 L801 | `mapExport` | ok | PS-06 |
| `export-027-variety-drawio` | §10.2 L794–L796; §10.2 L776 | `mapExport` | ok | vendored unchanged |
| `export-028-variety-sparx` | §10.2 L794–L796; §2.2 L130 | `mapExport` | ok | vendored unchanged |
| `idplan-001-counter-grid` | §10.2 L801 | `exportIdPlan` | ok | vendored unchanged |
| `idplan-002-counter-domains` | §10.2 L801 | `exportIdPlan` | ok | vendored unchanged |
| `idplan-003-digest` | §10.2 L801 | `exportIdPlan` | ok | vendored unchanged |
| `idplan-004-native-unique` | §2.2 L130 | `exportIdPlan` | ok | vendored unchanged |
| `idplan-005-native-duplicate` | §2.2 L130 | `exportIdPlan` | refused `export-id-ambiguous` | vendored unchanged |
| `idplan-006-native-synthetic` | §2.2 L130 | `exportIdPlan` | refused `export-id-ambiguous` | vendored unchanged |
| `idplan-007-utf16-key-order` | §10.2 L801; §2.2 L126 | `exportIdPlan` | ok | vendored unchanged |
| `serialize-001-main-drawio` | §10.2 L801; §10.1 L737 | `serializePrepared` | ok | vendored unchanged |
| `serialize-002-repeated-drawio` | §10.2 L801; §10.1 L737 | `serializePrepared` | ok | vendored unchanged |
| `serialize-003-xml-escaping` | §10.2 L801; §10.1 L737 | `serializePrepared` | ok | vendored unchanged |
| `serialize-004-determinism` | §10.2 L801; §14.3 L963 | `serializePrepared-sequence` | ok | vendored unchanged |
| `serialize-005-stale-binding` | §10.1 L737; §9.2 L690 | `serializePrepared` | refused `render-stale` | vendored unchanged |
| `serialize-006-revision-mismatch` | §10.1 L737; §9.2 L690 | `serializePrepared` | refused `render-stale` | vendored unchanged |
| `serialize-007-stale-profile-digest` | §10.1 L737; §9.2 L681; §9.2 L690 | `serializePrepared` | refused `render-stale` | vendored unchanged |
| `serialize-008-stale-descriptor-digest` | §10.1 L737; §9.2 L682; §9.2 L690 | `serializePrepared` | refused `render-stale` | vendored unchanged |
