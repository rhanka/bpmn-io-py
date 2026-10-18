# SPEC PROFILE RENDER EXPORT PY — lot 4 Python binding (layout, R, themes, exporters)

Status: sealed binding contract for lot 4 of `bpmn_io.profile` (target 0.3.0, no
version bump in this lot). This document adds no production code. It binds the
lot-4 sections of the design to Python signatures, closed shapes, refusal codes
and gates, and indexes the sealed expectation files under
`tests/profile_render/expected/` and `tests/profile_export/expected/`.

Authority: DESIGN R3.3 (SHA-256
`48139f5fd5bd789eacbf271081a95432c54d8361b1e52404e3443a25fa65782f`), sections
§9.1–§9.5, §10.1 (results, coordinates, reports, idMap, artifacts), §10.2,
§2.2/§2.4 (selectors, `outputId`, `emit`, `loss`, `refuse`), §3.1 (H, B,
rounding, ticks), §13 OPEN register and §16 owner decisions (all eleven ratified
2026-10-14). Pinned contract bytes: `contracts/profile-mechanism/1/`. Binding
predecessor: `spec/SPEC_PROFILE_MECHANISM_PY.md` (signature table §6, result
unions, Report/2). Lot 3 (`complete`, `normalize`, placements) is consumed only
through the signatures of that predecessor table. Where this spec and a pinned
contract byte disagree, the byte wins and the mismatch is an erratum.

Conventions. "DESIGN §x" means DESIGN R3.3 §x. JSON names are DESIGN's wire
names; Python functions are snake_case (`docs/naming.md`). Every computation is
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
| `_layout.py` | `compute_layout`, the Python generic layout adapter `generic-di-layout/1` (§4) |
| `_render.py` | `resolve_theme` producing RenderData/1, coverage, theme chain, legacy theme alias lookup |
| `_export_ir.py` | export-ir/1 field vocabulary (CR-11), symbol table, ID policies |
| `_export.py` | `map_export`, capability, loss mapping, idMap, artifacts |
| `_serialize.py` | `serialize_prepared` and the `drawio/1` structural serializer |
| `_prepare.py` | `prepare_export` orchestration |
| `_legacy.py` | `map_legacy_diagnostics` (legacy diagnostic adapter table, §10.2) |

Public names re-exported from `bpmn_io.profile` (and added to `__all__`):
`compute_layout`, `resolve_theme`, `map_export`, `serialize_prepared`,
`prepare_export`, `render_digests`, `view_revision`, `verify_render_data`,
`measure_text`, `template_geometry`, `map_legacy_diagnostics`,
`resolve_legacy_theme`, `registry_from_json`. Stubs are regenerated with
`scripts/gen_stubs.py`.

Additive changes to block-A types (backward compatible, defaults keep every
existing call valid):

- `ValidatedProfile` gains `assets: dict[str, bytes]` (resource `id` → raw bytes
  verified against the `resources[].sha256` pin through `asset_bag[assetKey]`;
  empty when no asset bag is supplied).
- `CompiledProfile` gains `profile: dict` (the complete validated profile JSON,
  deep-copied at the boundary), `identity: dict` (the closed §5.1
  `profileIdentity` record: `mechanismVersion, schemaVersion, profile, version,
  sha256 = H(profile), base, descriptors`), `assets` (copied from the validated
  profile) and `render_registry` (the render-token signatures of the
  `RegistrySet` used at compile time, below).
- `RegistrySet` gains `render_tokens: dict[str, dict]` (token name → JSON Schema
  signature), `region_token_pattern: str | None` and `region_token_schema: dict |
  None`. `registry_from_json(data) -> PureResult[RegistrySet]` returns the
  default block-A operator registry extended with the `renderTokens`,
  `regionTokenPattern` and `regionTokenSchema` of a pinned registry document
  (shape of `neutral-registry.json`). With the default registry (no render
  tokens) the generic DESIGN §9.3 signatures apply and no `fontFamily` or `dash`
  value is admitted (no injected family or registered style).

## 2. Signatures

Document operations return `Result/1` (`ResultSuccess | ResultRefused`, block A
`_results.py`); helpers return `PureResult`. Read-only operations set
`baseRevision == revision`.

| DESIGN ABI | Python | Union, `operation` | Inputs → payload |
| --- | --- | --- | --- |
| (layout primitive, §9.1/§9.4) | `compute_layout(compiled, envelope, placements, imported_di, *, theme_id)` | Result, `"layout"` | Layout/1 |
| `resolveTheme` | `resolve_theme(compiled, envelope, layout, theme_id, overrides, di_styles)` | Result, `"resolveTheme"` | RenderData/1 |
| `mapExport` | `map_export(compiled, envelope, layout, r, format)` | Result, `"mapExport"` | PreparedArtifact |
| `serializePrepared` | `serialize_prepared(prepared, pinned_writer_options)` | Result, `"serializePrepared"` | `{format, bytes, digest, idMap, capability}` |
| `prepareExport` | `prepare_export(compiled, envelope, options)` | Result, `"prepareExport"` | PreparedArtifact |
| (§9.2 formulas) | `render_digests(record)` | PureResult | digest record (§6.1) |
| (§9.2) | `view_revision(binding)` | `str` | viewRevision |
| (§9.2 freshness) | `verify_render_data(compiled, envelope, layout, r, theme_id, overrides, di_styles)` | PureResult | `{"viewRevision": str}` |
| (§9.3 widths) | `measure_text(metrics, text)` | PureResult | `{"lines", "width", "height"}` |
| (§9.3 templates) | `template_geometry(glyph, bounds, *, label_bounds=None, badge_size=None)` | PureResult | template geometry (§8.2) |
| (§10.2 legacy table) | `map_legacy_diagnostics(legacy, manifest, *, source_index=None)` | PureResult | Report/2 entry list |
| (§9.5) | `resolve_legacy_theme(compiled, legacy_name)` | PureResult | `{"themeId": str}` |

Arguments: `compiled` is the extended `CompiledProfile`; `envelope` a block-A
`DocumentEnvelope`; `placements` the §7.2 placement records (lot 3 `normalize`
output); `imported_di` the Snapshot/1 `importedDi` record `{descriptorDigest,
diagrams, sha256}`; `layout`, `r`, `overrides`, `di_styles`, `prepared` are the
JSON records defined in §3; `format` is a profile `exports[].format` value;
`pinned_writer_options` is an `exports[].serializer` record; `metrics` is the raw
bytes of a metrics resource; `glyph` a theme glyph record.

Errata against `spec/SPEC_PROFILE_MECHANISM_PY.md` §6 (each justified):

1. `prepare_export` options are exactly `{format, themeId, overrides, diStyles,
   importedDi}`. DESIGN §8.1 lists `{format, themeId, overrides, diStyles,
   signal?}`: Python is synchronous (no `signal`), and the headless adapter takes
   its geometry from the archived imported DI (§4), which the JS canvas reads
   from its live modeler instead.
2. `compute_layout` has no DESIGN ABI name (DESIGN §8.1 names only the canvas
   `/layout` entry); it is the Python binding of "the pinned generic layout
   adapter" of DESIGN §9.1 and returns `Result/1` because it reads a document.
3. The helper functions of the table above have no DESIGN ABI names; they bind
   formulas the DESIGN fixes (§9.2, §9.3, §10.2) so that snapshot validation
   (lot 5) and export freshness share one implementation.

## 3. Closed records

All records are closed: unknown members, `null` (outside Report/2 coordinates
and before/after values), non-finite numbers and integral numbers outside the
safe range refuse with the code stated for each operation.

- **Layout/1** (DESIGN §9.1): `{layoutVersion:"1", pages, geometry}`. Page:
  `{pageId, name, order, semanticRootId, bounds}`. Geometry record:
  `{pageId, occurrenceKey, semanticId?, role, bounds, label?, sourceOccurrence?,
  targetOccurrence?, waypoints?}`. Bounds `{x, y, width, height}` safe integer
  ticks, width/height ≥ 0. Label `{text, bounds, lines}`. Edges carry both
  endpoints `{pageId, occurrenceKey}` and ≥ 2 waypoints `{x, y}`; non-edges omit
  all three. Pages sort by ascending unique `order`; geometry by page order then
  UTF-16 `occurrenceKey`; keys are nonempty and unique per page.
- **RenderData/1** (DESIGN §9.1): `{renderVersion:"1", binding, pages,
  occurrences, coverage, diagnostics}`; `pages` equals `layout.pages`;
  occurrence = geometry record plus `emittedType`, `style`, `glyphId`;
  `binding` = `{semanticRevision, profileDigest, descriptorDigest, layoutDigest,
  themeId, themeDigest, overridesDigest, diStylesDigest, metricsDigest,
  payloadDigest}`; coverage `{semanticId, occurrences, disposition}` sorted by
  UTF-16 `semanticId`; `diagnostics` uses the Report/2 entry shape.
- **Overrides/1** `{semantic:[{semanticId, tokens}], occurrence:[{pageId,
  occurrenceKey, tokens}]}`; **DiStyles/1** `{native:[{pageId, occurrenceKey,
  tokens}], bioc:[...]}`; token `{name, value}`.
- **PreparedArtifact** (DESIGN §10.1): exactly `{format, profileIdentity,
  semanticRevision, viewRevision, ir, renderBinding, report, capability,
  idMap}`; `renderBinding` is the RenderData/1 `binding` record; `ir` is the
  export-ir/1 record list of §10.2 below.
- **Report/2** and coordinates: block-A `Report`/`ReportEntry`/`Coordinate`
  wire shapes and `profile-report/2` ordering (`sort_report_entries`,
  `sort_id_map`).

## 4. Python generic layout adapter `generic-di-layout/1`

Python has no automatic layout engine. The Python "pinned generic layout
adapter" of DESIGN §9.1 is `generic-di-layout/1`: it transcribes the archived
imported DI (Snapshot/1 `importedDi`) into Layout/1, applies the DESIGN §9.4
region rule to placed elements and the §9.3 synthetic occurrences of the
selected theme, and refuses everything else. It never invents a position, a
size, a route or a line break.

### 4.1 Input checks (in this order)

1. Compatibility: `envelope.profileIdentity` against `compiled.identity` with the
   DESIGN §3.3 decision (block-A `check_compatibility`); a non-ok verdict refuses
   with its code.
2. Theme: `theme_id` resolves to the theme with that `id`, else to the unique
   theme listing it in `aliases`; otherwise refuses `render-stale` (unresolved
   input, DESIGN §9.2). The resolved theme's `id` is used everywhere after.
3. Geometry policy (OPEN-DI/OPEN-LOOK, §16.6 ratified shared geometry): a
   selected theme with `geometry:"theme"` refuses `profile-open`; when the
   themes with `geometry:"shared"` do not all resolve identical values for every
   `region.*` token name present in any of them (each through its own fallback
   chain; a name absent from one chain counts as a different value), refuses
   `theme-geometry-conflict`.
4. Imported DI: `sha256 == H({descriptorDigest, diagrams})` and `descriptorDigest
   == descriptorDigest(envelope.profileIdentity.descriptors)` (§6.1), else
   refuses `render-stale`.
5. DI resolution: every diagram plane `bpmnElement` and every shape/edge
   `bpmnElement` resolves to an ID-bearing element of `envelope.tree`, every DI
   element carries a nonempty `id`, and DI ids are unique on their page;
   otherwise refuses `render-stale` (unresolved input).

### 4.2 Pages and transcription

- One page per `BPMNDiagram`, in `diagrams` array order: `pageId` = diagram
  `id`; `name` = diagram `name` exactly (empty string when the diagram has no
  `name`; never derived from `pageId`); `order` = array index; `semanticRootId`
  = plane `bpmnElement`; `bounds` = the smallest rectangle containing every
  geometry bounds and label bounds of the page (`{0,0,0,0}` for an empty page).
- Units: one DI user unit is 1000 ticks; each converted value is rounded once,
  ties to even (DESIGN §3.1), exactly integral for DI values with at most three
  decimals.
- Each `BPMNShape` yields a non-edge geometry record: `occurrenceKey` = the DI
  element `id`; `semanticId` = its `bpmnElement`; `bounds` = its `dc:Bounds`.
- Each `BPMNEdge` yields an edge record: `waypoints` = its `waypoint` points;
  `bounds` = the smallest rectangle containing the waypoints; endpoints =
  `{pageId, occurrenceKey}` of the shape on the same page named by the edge
  `sourceElement`/`targetElement` when present, else of the unique shape on the
  page whose `bpmnElement` is the semantic `sourceRef`/`targetRef`. An endpoint
  that does not resolve to exactly one shape refuses `render-unsupported`.
- `role`: the placement `regionKey` for a placed element (§4.3), else the
  support binding `role` for a support target, else `"shape"` for a
  `BPMNShape` and `"edge"` for a `BPMNEdge`.
- Label: the element's matched render bindings for the selected theme (§5.2)
  give one label Value expression; it is evaluated with native `self` and
  `root` (block-A evaluator). A string result `t` yields `label = {text: t,
  bounds, lines: t.split("\n")}` (line feed only, no wrapping: width-based
  wrapping of `engine-scalar-A/1` is not defined in DESIGN R3.3); `MISSING`
  yields no label; a non-string refuses `profile-type`. Label `bounds` are the
  DI `BPMNLabel` bounds when present, else the record `bounds` (embedded
  label). Unequal label expressions among matched bindings refuse
  `render-style-conflict` (no declaration-order winner, DESIGN §9.3).

### 4.3 Region rule (DESIGN §9.4)

A placement `{elementId, ownerProcessId, regionKey, anchorAssociationId?,
relatedAssociationIds}` resolves its region through the verified support binding
`{ownerId: ownerProcessId, role: regionKey, targetId}` (the opaque `regionKey`
names the support binding role):

1. Binding present: the region rectangle on a page is the geometry of the bound
   support target on that page. A placed element shown on a page where the
   support has no geometry refuses `render-region-missing`; for a region with at
   least one placement, a missing
   `region.<regionKey>.headerWidth|padding|gap|minHeight` token in the resolved
   theme chain refuses `render-region-missing` (no hidden default). A region
   used only by a band-stripe synthetic occurrence needs no row token.
2. No binding, and the selected theme declares an `attached-badge` synthetic
   occurrence with this `region`: an attachment region (§4.4); the placed
   element keeps its transcribed geometry.
3. Otherwise refuses `profile-open`: a missing support invokes gated N and the
   layout never creates semantics (OPEN-RESERVED-N, §16.11, technical gate open).

Row computation for each (region, page), with the region rectangle `(Lx, Ly, Lw,
Lh)` and tokens `hw, p, g, mh` (ticks), in exact rational arithmetic with every
output coordinate rounded once, ties to even:

- Items: the placements of the region whose element has a `BPMNShape` on the
  page, sorted by the total §7.2 placement order. Object size `(w, h)` is the
  element's DI shape size; its DI position is ignored.
- Item label: label text as in §4.2; label size = the DI `BPMNLabel` size when
  present, else `measure_text` of the theme's metrics resource (§7); no label
  text means size `(0, 0)`. Footprint `f = max(w, label width)`; stack height
  `s = h + label height` (object above label, no gap).
- Horizontal: `contentLeft = Lx + hw + p`. The anchor is available when the
  placement has `anchorAssociationId` and the association endpoint opposite to
  the placed element (for a data association: its owning activity) has exactly
  one transcribed geometry record on the page (its DI geometry, before any
  region placement); then `left = max(contentLeft, ax - f/2)` with `ax` the
  anchor bounds centre x; otherwise `left = contentLeft` for the first item and
  `prevRight + g` after it. Collision: `left = max(left, prevRight + g)` for
  every item after the first. `right = left + f`.
- Growth: when `lastRight + p > Lx + Lw`, the support width becomes
  `lastRight + p - Lx`. Row height `RH = max(mh, max(s) + 2p)`; the support
  height becomes `max(Lh, RH)`. No other element moves (not covered).
- Vertical: every stack is centred on `cy = Ly + height'/2` (`height'` the
  possibly grown support height): object `y = cy - s/2`, label `y = object y +
  h`; object `x = left + (f - w)/2`, label `x = left + (f - label width)/2`.
- A region with no item keeps the support geometry unchanged (empty processes
  need no row). Several processes and pages resolve their own rectangle; a
  shared element gets one geometry record per page.
- Links are not re-routed: a `BPMNEdge` whose source or target element is
  region-placed refuses `render-unsupported` (routing after expansion is not
  defined in DESIGN R3.3; not covered).

### 4.4 Synthetic occurrences (DESIGN §9.3)

For each `syntheticOccurrences` declaration of the selected theme (theme record
only, fallback themes do not contribute), evaluate `select` once on the tree;
each selected owner is represented on a page when the page `semanticRootId` is
the owner `id` or the page has a transcribed geometry record with `semanticId`
equal to the owner `id`. For each represented (owner, page) emit one geometry
record without `semanticId`: `occurrenceKey = JCS([declaration id, owner id,
pageId])`, `role` = declaration role, label from the declaration `label`
expression (self = owner) with `bounds` = the record bounds.

- `band-stripe`: the region is the owner's support region (owner = process,
  binding role = declaration `region`) after §4.3 growth; none refuses
  `render-region-missing`. Bounds `(rx, ry, min(stripeWidth, rw), rh)` with
  `stripeWidth` the parameter of a `band-stripe` template glyph; a glyph without
  `stripeWidth` imposes no width bound (`rw`).
- `attached-badge`: the owner's placement with `regionKey ==` declaration
  `region` gives `anchorAssociationId`; the anchor node is the association
  endpoint opposite to the owner and must have exactly one geometry record on
  the page; no placement, no anchor or not exactly one anchor record refuses
  `render-region-missing` (ambiguous anchor, no nearest-activity repair). Bounds
  `(node.x + offsetX, node.y + node.height + offsetY, badgeWidth, badgeHeight)`
  with the badge size = glyph `viewBox` width and height converted like DI
  units (×1000 ticks). `hideSource:true` refuses `render-unsupported`
  (source-hiding interaction unqualified, OPEN-RENDER-PRIMITIVES; the headless
  ABI carries no placement into `resolve_theme`). `markerShift` has no
  RenderData/1 field (renderer concern, not covered).

## 5. Theme resolution — `resolve_theme` (DESIGN §9.1–§9.3)

### 5.1 Checks (in this order)

1. Compatibility (as §4.1.1). 2. Theme resolution and geometry policy (as
§4.1.2–3). 3. Layout/1 shape (closed records, sorted unique pages and keys,
edge endpoints resolving in the layout) else `render-stale`. 4. Overrides/1 and
DiStyles/1: shape violations (unknown or missing member, null, non-array,
duplicate target, duplicate token name in one target) and token signature
failures refuse `render-token-invalid`; a semantic target absent from the tree
or an occurrence target absent from `layout.geometry` refuses `render-stale`.
5. Per geometry record with `semanticId`: render bindings and conflicts (§5.2).
6. Every geometry record without `semanticId` must be a synthetic occurrence of
the selected theme (key and role match a declaration), else `render-stale`.

### 5.2 Bindings, glyph, style

- Recognition (block-A evaluator, immutable tree) gives the matched notions:
  every matching facet plus at most one notion per exclusive group. For the
  selected theme `T` each matched notion contributes its render binding for the
  nearest theme of the chain `T → … → root` that has one.
- Glyph: the matched bindings must name one glyph id; unequal glyph ids refuse
  `render-style-conflict`. The glyph is looked up in the chain (selected theme
  first).
- Token precedence (DESIGN §9.3), each token name resolved independently:
  occurrence override > semantic-ID override > native color-DI > bioc-DI >
  notion render-binding tokens > selected theme tokens > fallback chain (nearest
  ancestor first). Matched bindings contribute at one level: equal values
  coalesce, unequal values for one name refuse `render-style-conflict`.
  Synthetic occurrences use their declaration `tokens` at the binding level and
  have no semantic or DI level.
- `style` = the resolved tokens over the union of names of all applicable
  levels, excluding `region.*` geometry tokens, sorted by UTF-16 name. Sparse
  overrides stay sparse: the Overrides/1 record is digested as supplied (after
  normalization), never expanded.
- render-token/1 signatures (registry `renderTokens`, DESIGN §9.3):
  `fill|stroke|textColor` match `^#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?$` under
  `re.fullmatch` (a trailing line feed refuses); `fontSize|strokeWidth` are
  finite non-negative numbers (bool is not a number; integral values outside the
  safe range refuse); `fontWeight ∈ {normal, bold}`; `arrow ∈ {none, open,
  filled, hollow-triangle}`; `fontFamily` and `dash` only the injected registry
  values; `region.<key>.(headerWidth|padding|gap|minHeight)` non-negative
  integers. Other names refuse (`render-token-invalid` for runtime bags,
  `profile-type` at compile time, §8.1).

### 5.3 Occurrences and coverage

- One occurrence per geometry record whose element has a glyph: the record plus
  `emittedType` (`"edge"` for edge records, `"node"` otherwise, synthetic
  included), `style`, `glyphId`. Order: page order, then UTF-16 key.
- Coverage covers every ID-bearing element (`$type` and string `id`) of
  `envelope.tree`, sorted by UTF-16 `semanticId`; `occurrences` lists its
  occurrence pairs in R order. `rendered` iff it has occurrences; otherwise
  `unsupported` when it has a layout geometry record or a glyph for the
  selected theme (drawn in the source view, or deliberately styled, but not
  rendered: no automatic standard-notation fallback, DESIGN §9.3), else
  `nonvisual`. `diagnostics` is `[]` in every sealed case (not covered:
  render-stage findings for ID-less children).
- `binding` per §6.1 with `themeId` the resolved theme id.

## 6. Digests and freshness (DESIGN §9.2)

### 6.1 Formulas

`descriptorDigest = H(pins sorted by UTF-16 id)` (pins exactly `{id, version,
sha256}` from `profileIdentity.descriptors`); `layoutDigest = H(layout)`;
`themeDigest = H({themeId, themes})` with `themes` the complete theme records of
the chain from the fallback root to the selected theme; `overridesDigest` and
`diStylesDigest` = H of the normalized record (semantic by `semanticId`,
occurrence records by `pageId` then `occurrenceKey`, tokens by `name`, all
UTF-16); `metricsDigest = H([{id, sha256}])` over the metric resources referenced
by `metricsResource` of the chain themes, unique, sorted by UTF-16 `id`,
`sha256 = B(raw bytes)`; `payloadDigest = H({pages, occurrences, coverage,
diagnostics})`; `profileDigest = H(profile)`; `semanticRevision` per DESIGN §3.1;
`viewRevision = H({semanticRevision, layoutDigest, themeId, themeDigest,
overridesDigest, diStylesDigest, metricsDigest})`.

`render_digests(record)` binds the formulas on explicit records: input keys
`semanticTree, profileIdentity, bindings, descriptorPins, layout, themeId,
themes` (all profile themes; the chain is resolved inside), `overrides,
diStyles, metrics` (`[{id, utf8}]`, raw bytes = UTF-8 of `utf8`) and optional
`payload`; output `{semanticRevision, descriptorDigest, layoutDigest,
themeDigest, overridesDigest, diStylesDigest, metricsDigest, viewRevision}` plus
`payloadDigest` when `payload` is given. Record-shape violations refuse
`render-token-invalid`; token signatures are not checked here (no registry).

### 6.2 Freshness

`verify_render_data` recomputes every binding field from its inputs and refuses
`render-stale` on the first difference in this order: R shape, `themeId`
resolution, `semanticRevision`, `profileDigest`, `descriptorDigest`,
`layoutDigest`, `themeDigest`, `overridesDigest`, `diStylesDigest`,
`metricsDigest`, `payloadDigest`, `pages == layout.pages`, and equality of each
occurrence with its layout geometry record minus `emittedType`, `style`,
`glyphId`. Success returns `{"viewRevision"}`. `map_export` applies the same
checks except `overridesDigest`/`diStylesDigest` (not among its inputs; they
stay bound through `viewRevision`). Terminal serialization never repairs R.

## 7. Text (DESIGN §9.3)

- `stripPrefix` and `case` are the block-A value operators; `case` uses the
  pinned Unicode 15.0.0 full mappings (`contracts/unicode-case/15.0.0/`), never
  `str.upper`/`str.lower` (`İ` stays `İ` in upper, `ɤ` stays `ɤ`, `ß` → `SS`,
  Final_Sigma in lower).
- `measure_text(metrics, text)`: `lines = text.split("\n")`; the width of a
  line is the sum over its Unicode scalars (not UTF-16 units) of `spaceAdvance`
  for U+0020 and of the declared fallback `defaultAdvance` for every other
  scalar (the pinned neutral metrics carry no per-scalar table); `width` is the
  maximum line width; `height = len(lines) * (ascent + descent)`; values are
  ticks (`unit:"micro-point"`). No NFC, no accent stripping, no platform font
  measurement; case and width are separate (measure the final text).
  Per-scalar width tables and scalar-to-width-alias maps are not covered (no
  pinned field names).

## 8. Glyphs and templates (DESIGN §9.3)

### 8.1 Compile-time checks (lot 4 extension of `compile_profile`, CR-09/CR-11)

- Schema first: glyph conditionals expressed by the pinned schema (native
  requires `nativeType` and empty `commands`; path requires nonempty commands
  with M/L two, C six, Q four, Z zero values; template requires `template` and
  `parameters`; closed template enum) refuse `profile-schema` at
  `load_profile` (DESIGN §2.4.1: the schema is the sole authority for keys,
  unions, requiredness and enumerations).
- Compiler: every glyph `viewBox` needs width (`[2]`) > 0 and height (`[3]`) > 0,
  else `profile-glyph-shape`. Template parameters must be exactly the signature
  below (no duplicate, missing or extra name, exact types), else
  `profile-glyph-shape`: `header-band {headerHeight: non-negative safe
  integer}`; `corner-fold {foldRatio: number in [0, 0.5], headerRotation: 0 |
  90 | 270}`; `attached-badge {offsetX, offsetY: safe integers, hideSource:
  boolean, markerShift: safe integer}`; `band-stripe {stripeWidth: non-negative
  safe integer}`.
- Theme, render-binding and synthetic tokens follow §5.2 signatures; an unknown
  name, a wrong value or a duplicate name in one token list refuses
  `profile-type`.
- Export (CR-11): the §10.2 field rules below refuse `profile-export-field`; a `page` emit
  with `parent` and a nonzero `counterOrigin` with a non-counter `idPolicy`
  refuse `profile-type`.

### 8.2 `template_geometry`

`glyph` is a template glyph record (parameters checked as §8.1, refusal
`profile-glyph-shape`; a non-template glyph refuses `render-unsupported`).
`bounds` is the shape (header-band, corner-fold), region (band-stripe) or node
(attached-badge) rectangle. Exact rationals, one roundEven at output:

- `header-band`: `header = (x, y, w, min(headerHeight, h))`, `body = (x, y +
  min(headerHeight, h), w, h - min(headerHeight, h))`; the header height never
  scales with the body.
- `corner-fold`: `fold = roundEven(min(w, h) * foldRatio)` with `foldRatio`
  taken as the exact rational of its shortest round-trip decimal form;
  `foldPath = [(x+w-fold, y), (x+w-fold, y+fold), (x+w, y+fold)]`; with
  `label_bounds`, `labelRotation = {angle: headerRotation, center:
  (roundEven(lx + lw/2), roundEven(ly + lh/2))}`.
- `band-stripe`: `stripe = (x, y, min(stripeWidth, w), h)`.
- `attached-badge`: `badge = (x + offsetX, y + h + offsetY, badge_size.width,
  badge_size.height)`, plus `markerShift` and `hideSource` echoed.

Payload keys: `header, body` | `fold, foldPath[, labelRotation]` | `stripe` |
`badge, markerShift, hideSource`.

## 9. Legacy themes (DESIGN §9.5)

Generic code uses opaque theme ids. `resolve_theme` never consults
`compatibilityAliases` (a legacy name such as `standard` that is not a theme id
or declared theme alias refuses `render-stale`). `resolve_legacy_theme` is the
explicit legacy adapter path: the unique `compatibilityAliases` record with
`kind:"theme"`, `old == legacy_name` and `mode != "remove"` gives
`destination`, which must be a theme id (else `render-stale`); no record, or a
`remove` record, refuses `legacy-unmapped`.

## 10. Export (DESIGN §10.2)

### 10.1 `map_export` steps (refusal precedence in this order)

1. Compatibility (as §4.1.1).
2. Format: the unique `exports[]` record whose `format == format` and a
   registered Python adapter for that format; lot 4 registers `drawio/1` only.
   Otherwise refuses `export-format-unsupported`.
3. Freshness (§6.2) → `render-stale`. `map_export` trusts a fresh R: it does
   not re-run `resolve_theme` (a fresh R whose occurrences equal the supplied
   layout is admitted even if no theme declares an anonymous record).
4. Coverage: any `unsupported` coverage entry refuses `render-unsupported`
   (an unsupported necessary occurrence refuses the entire artifact).
5. Capability: every capability record is evaluated once per R occurrence with
   `self` = the occurrence, `root`, `render`, `page` = its PageHandle and
   `semantic` (absent for synthetic occurrences); applicable classes aggregate by
   worst outcome together with the adapter ceiling `structural`
   (OPEN-EXPORT-EVIDENCE: no feature is byte-compatible by declaration; lot 4
   has no qualified engine goldens). An `unsupported` outcome refuses
   `export-format-unsupported`.
6. Planning pass: the export recipes of the record run in order over their
   selector results (page-occurrence order), evaluating every value; each
   `outputId` request `(pageId, occurrenceKey, domain)` is recorded (PageHandle
   uses the reserved empty key; implicit page parents request the page key).
   `refuse` actions refuse with their code; `bind` cardinality errors refuse
   `profile-ambiguous-binding`; `outputId` on a native handle without exactly
   one occurrence of that element on the current page refuses
   `export-occurrence-ambiguous`; a required field evaluating to `MISSING`
   refuses `export-field-invalid` (an optional field evaluating to `MISSING` is
   omitted).
7. ID allocation (per call, no state across calls):
   - `counter`: requested keys sorted by domain (`page, node, edge, label`), then
     page `order`, then UTF-16 `occurrenceKey`, numbered from `counterOrigin`;
     `e_` + decimal; repeated requests reuse one ID; unrequested keys get none.
   - `digest`: `e_` + `H([pageId, occurrenceKey, domain])`.
   - `native`: `pageId` for a page, `semanticId` for a semantic occurrence, only
     when the resulting ID is unique among all requested keys of the call; a
     synthetic or anonymous occurrence, or a duplicate, refuses
     `export-id-ambiguous`.
8. Emission pass with a symbol table that lasts for exactly this call (discarded
   on refusal; nothing survives A→B→A). `page` emits at the root. For
   `node|edge|label` an omitted parent is the id emitted for the current page;
   `metadata` without parent is artifact-global. Parent and edge endpoints
   (`source`, `target`) must be earlier emitted `page|node` ids (endpoints: node
   ids): a value emitted later in the same call refuses `export-parent-order`;
   the record's own id, an id never emitted in this call (cross-call handle), an
   incompatible kind, or an id emitted twice refuse `export-parent-invalid`.
9. Losses: a `loss` action appends one entry (§10.3); capability records append
   one entry per applicable record, occurrence and loss class.

### 10.2 export-ir/1 records (Python binding)

A record is `{kind, <named fields>, parent?}` (exactly the emitted field
values; `parent` omitted for `page` and artifact-global `metadata`) plus the
values copied from current immutable R (DESIGN §10.2), present only when `self`
is the matching typed record: `page` ← PageHandle `bounds`; `node` ← occurrence
`bounds`, `style`, `label: {bounds, lines}` (when the occurrence has a label);
`edge` ← `bounds`, `waypoints`, `style`, `label`; `label` ← the occurrence
label `bounds` and `lines`. Field vocabulary (DESIGN §10.2): page `id, name`;
node `id` + optional `name, shape, fill, stroke, textColor, fontFamily`
(strings) and `fontSize, strokeWidth` (numbers); edge `id, source, target` +
optional `name, stroke, dash, arrow` (strings) and `strokeWidth` (number); label
`id, text`; metadata `name, value`. The projection of `ir` on `{kind, id, name,
parent}` of the neutral fixtures equals their pinned `expected.exportIR`.

### 10.3 Report, idMap, artifacts

- Loss entry (both sources): `code = "export-loss/" + class`, `messageKey =
  "export.loss." + class`, `classification "loss"`, `severity "warn"`, `stage
  "export"`, `disposition "mapped"`, `lossClass = class`, `beforePresent` and
  `afterPresent` false, `pageId`, `occurrenceKey`, `emittedType` of the
  occurrence (the `loss` target when it is an occurrence, else the current
  `self` occurrence). `source`: the semantic element of that occurrence, or the
  native element named by the `loss` target, as `{domain:"tree", pointer,
  targetId, provenance:"exact"}` (RFC 6901 pointer into `envelope.tree`), else
  `{domain:"none", pointer:null, targetId:null, provenance:"unavailable"}`
  (synthetic or anonymous occurrence). `ruleId`: the export recipe id for a `loss` action,
  the `exports[].id` for a capability-declared loss. `result`: for a `loss`
  action, the last record emitted in the same recipe iteration
  `{domain:"artifact", pointer:"/ir/<index>", targetId, provenance:"exact"}`,
  else (and for capability losses) `{domain:"none", pointer:null,
  targetId:null, provenance:"unavailable"}`.
- `report = {reportVersion:"2", operation, entries, rawStandardFindings:[],
  idMap, artifacts}` (no optional identity/revision members).
- `idMap` rows `{sourceId, resultId, domain:"export", pageId, occurrenceKey?}`:
  one per emitted record with an `id` whose `self` is a PageHandle (`sourceId =
  pageId`, no `occurrenceKey`) or an occurrence with `semanticId` (`sourceId =
  semanticId`); sorted per DESIGN §10.1. `PreparedArtifact.idMap` equals
  `report.idMap`.
- `artifacts = [{format, capability, digest: H(ir), entryIndexes}]` (all entry
  indexes); `serialize_prepared` reports `digest = B(bytes)`.
- `PreparedArtifact.viewRevision = view_revision(renderBinding)`;
  `semanticRevision = envelope.semanticRevision`; `profileIdentity =
  envelope.profileIdentity`.

## 11. `serialize_prepared` and `drawio/1`

Checks: `prepared.format` has a registered adapter (else
`export-format-unsupported`); `prepared.viewRevision ==
view_revision(renderBinding)`, `prepared.semanticRevision ==
renderBinding.semanticRevision`, `profileIdentity.sha256 ==
renderBinding.profileDigest` and `descriptorDigest(profileIdentity.descriptors)
== renderBinding.descriptorDigest`, else `render-stale`. Output: `{format,
bytes, digest: B(bytes), idMap: prepared.idMap, capability:
prepared.capability}`. DESIGN R3.3 fixes no draw.io bytes (structural until
engine goldens, OPEN-EXPORT-EVIDENCE); the sealed expectations are structural:
UTF-8 without BOM, no CR for `newline:"LF"`, well-formed XML with root
`mxfile`, one `diagram` element per page record in IR order carrying the page
`id` and `name`, and every node/edge record id present as exactly one `id`
attribute value; the same input gives the same bytes.

## 12. `prepare_export` (DESIGN §10.2, §6.2)

Stages, each run once on a deep copy: compatibility → graph checks
(`validate_envelope`) → C (lot 3 `complete`) → `pre-normalize` lint (accept) → N
(lot 3 `normalize`) → `post-normalize` lint → `compute_layout` (options
`importedDi`, `themeId`) → `post-layout` lint → `release` lint → `resolve_theme`
→ `map_export`. A stage refusal refuses `prepare_export` with that code; a lint
stage leaving unresolved error entries refuses with the `code` of its first
unresolved error entry in `profile-report/2` order. Refusals carry the complete
report of the executed stages (operation `"prepareExport"`) and no artifact.
Success returns the PreparedArtifact of `map_export` with `report` replaced by
the complete report (operation `"prepareExport"`, entries of every stage,
`artifacts[].entryIndexes` re-indexed into it). No input (envelope, compiled
profile, options) is mutated.

## 13. Legacy diagnostic adapter (DESIGN §10.2 table)

`legacy = {producer, code, ids?, lossClass?}` with `producer ∈ {"io-error",
"fidelity-notice"}` or any other string; `manifest = {adapter, entries:
[{producer, legacyCode}]}` (the adapter's finite per-code manifest);
`source_index` maps ids to tree pointers. Output: entries in `profile-report/2`
order, `stage "export"`, `ruleId = manifest.adapter`, `legacyCode = code`,
`beforePresent/afterPresent` false, `result` unavailable `{none, null, null,
unavailable}`:

| Legacy record (listed in the manifest) | code / messageKey / classification / severity / disposition |
| --- | --- |
| io-error `unknown-format`, `unsupported-format` | `export-format-unsupported` / `export.format-unsupported` / integrity / error / refused |
| io-error `invalid-reference`, `missing-endpoint` | `reference-dangling` / `reference-dangling` / integrity / error / refused |
| io-error `duplicate-id` | `id-collision` / `id-collision` / integrity / error / refused |
| fidelity-notice with `lossClass` in the closed set | `export-loss/<class>` / `export.loss.<class>` / loss / warn / mapped, `lossClass` |
| anything else (unlisted code, io-error code outside the five, fidelity notice without a closed class) | `legacy-unmapped` / `legacy.unmapped` / integrity / error / refused |

io-error entries are one per id: `source = {tree, pointer, id, exact}` when
`source_index` has the id, else `{tree, null, id, unavailable}`; no ids gives
one entry with source `{none, null, null, unavailable}`. `legacy-unmapped`
entries keep unavailable coordinates (`{tree, null, id, unavailable}` per id,
or `none` without ids). No code is guessed from message text.

## 14. Gates (DESIGN §13, state after §16)

| Gate | State | Python lot-4 behaviour while open |
| --- | --- | --- |
| OPEN-RENDER-PRIMITIVES | technical gate open (composite grammar not supplied) | the four closed templates only; `hideSource:true` refuses `render-unsupported`; template ids outside the enum refuse `profile-schema`; no composite |
| OPEN-EXPORT-EVIDENCE | open (no engine goldens) | capability ceiling `structural`; `unsupported` refuses `export-format-unsupported`; serializer bytes structural only |
| OPEN-DI / OPEN-LOOK | owner default ratified (§16.6, shared geometry); per-theme geometry not approved | `geometry:"theme"` refuses `profile-open`; shared-theme disagreement refuses `theme-geometry-conflict`; imported DI is the geometry input |
| OPEN-RESERVED-N | owner default ratified (§16.11), technical proof gate open | missing region support refuses `profile-open` (layout and preparation never create supports) |

## 15. Refusal codes by operation

- `compute_layout`: compatibility codes, `render-stale`, `profile-open`,
  `theme-geometry-conflict`, `render-region-missing`, `render-unsupported`,
  `render-style-conflict`, `profile-type`, `profile-resource-missing` (metrics
  bytes absent when a label must be measured).
- `resolve_theme`: compatibility codes, `render-stale`, `profile-open`,
  `theme-geometry-conflict`, `render-token-invalid`, `render-style-conflict`.
- `map_export`: compatibility codes, `export-format-unsupported`, `render-stale`,
  `render-unsupported`, `export-occurrence-ambiguous`, `export-field-invalid`,
  `profile-ambiguous-binding`, `export-id-ambiguous`, `export-parent-order`,
  `export-parent-invalid`, profile `refuse` codes.
- `serialize_prepared`: `export-format-unsupported`, `render-stale`.
- `prepare_export`: every code above plus lot 3 and lint codes.
- `compile_profile` (lot 4 checks): `profile-glyph-shape`, `profile-type`,
  `profile-export-field`; `load_profile`: `profile-schema`.
- Helpers: `render-token-invalid`, `render-stale` (`render_digests`,
  `verify_render_data`), `profile-glyph-shape`, `render-unsupported`
  (`template_geometry`), `legacy-unmapped`, `render-stale`
  (`resolve_legacy_theme`).

## 16. Case harness binding

Every expectation file is one JSON object with `case`, `clause`, `derivation`,
`operation`, `input`, `expected`, `author:"spec-seal"`. Shared conventions:

- `input.profile = {base, patch}`: load `contracts/profile-mechanism/1/<base>`,
  apply the RFC 6902 `patch` (`add`/`remove`/`replace`), serialize to UTF-8 JSON,
  `load_profile(bytes, schema_bytes=<profile-mechanism-1.schema.json>,
  descriptor_pins=profile.descriptors, base_bytes=<neutral-base.json>,
  asset_bag={"neutral-metrics.json": <bytes>},
  capabilities=profile.capabilities)` then `compile_profile(validated,
  registry_from_json(<neutral-registry.json>))`.
- Envelope: `complete_envelope(identity(profile), input.tree, input.bindings)`
  with `identity` the §1 record (`sha256 = H(profile)`). A case may override the
  envelope identity with `input.envelopeIdentity`.
- `input.diagrams` → `imported_di = {descriptorDigest:
  descriptorDigest(identity.descriptors), diagrams, sha256: H({descriptorDigest,
  diagrams})}`.
- Comparison of `expected`:
  - `{status:"ok", payload}`: the result is a success and its payload equals
    `payload` (JSON equality after `json.loads`; wire field names). Optional
    `report` (the Result report), `baseRevision` and `revision` compare
    likewise. `{status:"ok"}` alone (compile cases) checks success only.
  - `{status:"refused", code}`: the result is a refusal with that code and no
    payload.
  - `{status:"sequence", steps}` (`map_export_sequence`): one expectation per
    call, in order, each compared as above.
  - `unsealed`: RFC 6901 pointers (relative to `{payload, report}`) removed from
    both sides before comparison; each must exist and be an array.
  - `inputsUnchanged: true`: the JCS bytes of `envelope.to_json()`, the compiled
    profile JSON and the options are identical before and after the call.
  - `prepare_export` refusals may be structural: `stagesOnly` (every report entry
    `stage` belongs to the list; `[]` means no entry) and `includes` (each listed
    partial entry matches at least one report entry on the listed keys,
    `targetId` comparing `source.targetId`).
  - `serialize_prepared` success uses `structural` (§11): `format`,
    `digestIsSha256OfBytes` (`digest == B(bytes)`), `idMap`, `capability`,
    `utf8NoBom`, `noCarriageReturn`, `xmlRoot` (local name of the root element),
    `diagrams` (`id`/`name` attributes of the root's `diagram` children, in
    order), `cellIds` (each occurs exactly once as an `id` attribute value),
    `deterministic` (a second call returns identical bytes).
- `operation` values and their inputs: `load_and_compile` (`profile`);
  `compute_layout` (`profile, themeId, tree, bindings, placements, diagrams`);
  `resolve_theme` (`profile, themeId, tree, bindings, layout, overrides,
  diStyles`); `render_digests` (`record`, metrics as `[{id, utf8}]`);
  `verify_render_data` (`profile, themeId, tree, bindings, layout, r,
  overrides, diStyles`); `measure_text` (`metrics` = a vendored file name,
  `vectors: [{text, note}]`; the expected payload lists one result per vector);
  `template_geometry` (`glyph, bounds`, optional `labelBounds` →
  `label_bounds`, `badgeSize` → `badge_size`); `resolve_legacy_theme`
  (`profile, legacyName`); `map_export` (`profile, tree, bindings, layout, r,
  format`, optional `envelopeIdentity`); `map_export_sequence` (`steps`: each a
  `map_export` input); `serialize_prepared` (`prepared, writerOptions`);
  `prepare_export` (`profile, tree, bindings, options`, optional
  `envelopeIdentity`; `options.diagrams` becomes `options.importedDi` as for
  `compute_layout`); `map_legacy_diagnostics` (`legacy, manifest`, optional
  `sourceIndex`).
- `inputFrom` (optional) names another case whose expected value is reused
  verbatim at a stated input pointer; the seal test checks the equality.
- A code job never rewrites a sealed file; a disagreement with DESIGN keeps the
  expectation and adds an `xfail(strict=True)` test naming the DESIGN line and
  the expectation file.

## 17. Case tables

The per-file case tables (one row per expectation file: case, DESIGN clause,
what it witnesses, expected status/code) are in Appendix A (render tree) and
Appendix B (export tree) at the end of this document.

## 18. Not covered

- Automatic layout of elements without DI, width-based wrapping, font-size
  scaling, kerning, per-scalar width tables and width-alias maps
  (`engine-scalar-A/1` is named but not defined in DESIGN R3.3).
- Link routing after region expansion (refused `render-unsupported`), growth of
  containers beyond the bound support, moving elements below a grown support.
- DI colour decoding into DiStyles/1 (import adapter; DiStyles is an input here)
  and the explicit discard report for archived DI of non-admitted elements
  (refused `render-stale`).
- `hideSource`, `markerShift`, badge rows and composites (OPEN-RENDER-PRIMITIVES).
- Synthetic owners represented only through a collaboration participant;
  synthetic declarations inherited from fallback themes.
- `bpmn`, `sparx` and `svg` export adapters (refused `export-format-unsupported`
  in lot 4), exact draw.io bytes, compression `deflate-raw`, engine
  byte-compatibility (OPEN-EXPORT-EVIDENCE, private goldens).
- Cross-runtime witnesses (JS↔Python R/IR/report parity, three-process runs,
  browser rendering) — conductor joint run.
- Metrics resources whose `textPolicy`/`unicode` differ from the neutral pins;
  R diagnostics for ID-less children.

## 19. Design ambiguities resolved here (defaults, for review)

1. regionKey ↔ support binding role identity (§4.3): the only link DESIGN §9.4
   gives between an opaque region key and a verified support binding.
2. Unbound region with an attached-badge declaration = attachment region; any
   other unbound region refuses `profile-open` (§4.3).
3. DI user unit = 1000 ticks (§4.2); DESIGN fixes ticks but no DI unit.
4. Occurrence key = DI element id; role vocabulary `shape`/`edge` for
   transcribed elements (§4.2).
5. Anchor centres use transcribed DI geometry; IO stacks centred on the
   (grown) support centre; collisions keep `gap` (§4.3).
6. Band-stripe without `stripeWidth` spans the region width; badge size = glyph
   viewBox ×1000 (§4.4).
7. Coverage rule rendered/unsupported/nonvisual and export refusal
   `render-unsupported` on any unsupported coverage (§5.3, §10.1).
8. Override/DI-style shape violations refuse `render-token-invalid`; unknown
   targets refuse `render-stale` (§5.1).
9. Capability refusal code `export-format-unsupported`; capability losses use
   `ruleId = exports[].id` and unavailable result coordinates (§10.1, §10.3).
10. export-ir/1 records carry the R-copied `bounds/style/label/waypoints/lines`
    (§10.2); edge endpoints obey the parent order rules.
11. `prepare_export` lint refusal code = first unresolved error entry (§12).
12. Legacy manifest shape and dispositions (§13); `resolve_legacy_theme` and
    the generic path never sharing `compatibilityAliases` (§9).
13. `metricsDigest` over the selected chain's metric resources (§6.1).
14. `counterOrigin` nonzero under a non-counter policy and `page` with `parent`
    refuse `profile-type` (CR-11 lists both codes).
15. `measure_text`: `spaceAdvance` applies to U+0020 only; metric values are
    ticks; `height = lines × (ascent + descent)` (§7).
16. Labels: line-feed split only, no wrapping; label bounds = DI `BPMNLabel`
    bounds, else the record bounds; region items keep the DI label size, else
    the measured size (§4.2, §4.3).
17. A declared theme `aliases` entry selects that theme; the binding records the
    theme id (§4.1, §5.1).
18. Synthetic occurrences are laid out by `compute_layout` (selected theme only)
    and styled by `resolve_theme`; "represented page" = page root or a
    transcribed record of the owner (§4.4).
19. Render bindings follow the selected theme's fallback chain (nearest theme
    first) (§5.2).
20. `corner-fold` uses the exact rational of the shortest decimal form of
    `foldRatio` (§8.2).
21. Coverage includes `Definitions` and every ID-bearing element (§5.3).
22. Unresolved DI references refuse `render-stale`; unresolvable edge endpoints
    refuse `render-unsupported` (§4.1, §4.2).
23. Loss-action result coordinates point at the last record emitted in the same
    recipe iteration (`/ir/<index>`), else unavailable (§10.3).
24. idMap rows only for records emitted while `self` is a PageHandle or a
    semantic occurrence; artifact `digest = H(ir)` before serialization (§10.3).
25. `map_export` checks R freshness, not provenance (§10.1).
26. Additive block-A type extensions and `registry_from_json` (§1).

## Appendix A — render tree (`tests/profile_render/expected/`, 155 cases)

| Case | DESIGN clause | Witness | Expected |
| --- | --- | --- | --- |
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
| `render.layout.grid-missing-support` | §9.4 missing support; §13 OPEN-RESERVED-N (§16.11) | placements into a region without a bound support refuse (layout never creates supports) | refused `profile-open` |
| `render.layout.grid-side-stripe` | §9.4 Region geometry, including Process IO | second neutral profile: region row in the side lane with anchors, collision and growth; synthetic stripe key; casing ss | ok |
| `render.layout.io-anchored` | §9.4 Region geometry, including Process IO | Process IO row: anchor centres, clamp, collision shift, placement order not x order | ok |
| `render.layout.io-empty-process` | §9.4 Region geometry, including Process IO | an empty process without IO needs no IO row; several processes resolve their own rectangle | ok |
| `render.layout.io-geometry-theme-gated` | §13 OPEN-DI / OPEN-LOOK (§16.6) | per-theme geometry stays disabled | refused `profile-open` |
| `render.layout.io-growth` | §9.4 Region geometry, including Process IO | the support lane grows in width and height instead of drawing outside it | ok |
| `render.layout.io-link-not-rerouted` | §9.4 Region geometry, including Process IO | links of moved IO are not rerouted by the Python adapter (not covered, refused) | refused `render-unsupported` |
| `render.layout.io-missing-lane` | §9.4 missing support; §13 OPEN-RESERVED-N (§16.11) | missing external support with support creation disabled refuses profile-open | refused `profile-open` |
| `render.layout.io-no-anchor` | §9.4 Region geometry, including Process IO | IO without anchor: content left edge, then after the previous IO by gap | ok |
| `render.layout.io-pinned-neutral-tokens` | §9.4 Region geometry, including Process IO | the pinned neutral region tokens (headerWidth 0, padding 8, gap 8, minHeight 40) | ok |
| `render.layout.io-region-missing-on-page` | §9.4 Region geometry, including Process IO | a placed element shown on a page without its support rectangle refuses | refused `render-region-missing` |
| `render.layout.io-region-token-missing` | §9.4 Region geometry, including Process IO | region numeric inputs are injected tokens; no hidden default | refused `render-region-missing` |
| `render.layout.io-repeated-views` | §9.4 Region geometry, including Process IO | repeated views: each page resolves its own bound rectangle; shared IO gets separate geometry; anchor absent on a page | ok |
| `render.layout.io-round-half-even` | §9.4 Region geometry, including Process IO | rational computations round once at output, ties to even | ok |
| `render.layout.io-shared-theme-switch` | §9.4 Region geometry, including Process IO | selecting another shared theme with identical geometry tokens leaves the layout unchanged | ok |
| `render.layout.io-theme-geometry-conflict` | §9.4 Region geometry, including Process IO | shared themes supplying different geometry-affecting tokens refuse | refused `theme-geometry-conflict` |
| `render.layout.io-wider-labels` | §9.4 Region geometry, including Process IO | labels wider than their IO object widen the footprint; DI label sizes kept, missing label measured; stacks centred | ok |
| `render.layout.label-case-lower` | §9.3 Per-notion style, text and glyph contracts | Unicode 15.0.0 full lower mapping with the untagged Final_Sigma context | ok |
| `render.layout.label-case-upper` | §9.3 Per-notion style, text and glyph contracts | Unicode 15.0.0 full upper mapping after stripPrefix, prefix removed exactly once | ok |
| `render.layout.label-strip-prefix-trim` | §9.3 Per-notion style, text and glyph contracts | stripPrefix after the ecma262-2024-start leading trim; U+0085 and U+200B are not trimmed; the body is never trimmed | ok |
| `render.layout.page-name-absent` | §9.1 Closed layout and render data | page name is captured from the diagram record, never guessed from pageId | ok |
| `render.layout.reference-band` | §9.4 Region geometry, including Process IO | reference band uses its bound participant rectangle with the same header/padding rule | ok |
| `render.layout.stripe-region-missing` | §9.3 Per-notion style, text and glyph contracts | a synthetic stripe whose owner has no matching region refuses | refused `render-region-missing` |
| `render.layout.style-conflict-label` | §9.3 Per-notion style, text and glyph contracts | matched bindings with different label expressions refuse at layout | refused `render-style-conflict` |
| `render.legacy.alias-absent` | §9.5 Legacy themes | no built-in legacy look mapping | refused `legacy-unmapped` |
| `render.legacy.alias-dangling` | §9.5 Legacy themes | a legacy alias must land on a declared theme | refused `render-stale` |
| `render.legacy.alias-mapped` | §9.5 Legacy themes | a legacy look name resolves only through injected compatibility data | ok |
| `render.legacy.alias-removed` | §9.5 Legacy themes | a removed legacy alias maps to nothing | refused `legacy-unmapped` |
| `render.legacy.alias-wrong-kind` | §9.5 Legacy themes | only kind theme records map looks | refused `legacy-unmapped` |
| `render.r.attached-badge` | §9.3 Per-notion style, text and glyph contracts | badge occurrence styled from its declaration tokens; source occurrence kept (hideSource false) | ok |
| `render.r.coverage-unsupported` | §9.3 Per-notion style, text and glyph contracts | no automatic standard-notation fallback: drawn element without a deliberate glyph is covered as unsupported | ok |
| `render.r.di-style-unknown-page` | §9.2 Digest formulas and freshness | Overrides/1 and DiStyles/1 reject unknown targets/members, duplicate targets and non-closed shapes | refused `render-stale` |
| `render.r.edge` | §9.1 Closed layout and render data | edge occurrence: emittedType edge, binding stroke beats theme stroke | ok |
| `render.r.facet-disjoint` | §9.3 Per-notion style, text and glyph contracts | multiple matched facets contribute disjoint tokens | ok |
| `render.r.facet-equal-values` | §9.3 Per-notion style, text and glyph contracts | equal values for one token at the same precedence coalesce | ok |
| `render.r.geometry-conflict` | §9.4 Region geometry, including Process IO | two shared themes with different geometry-affecting tokens refuse | refused `theme-geometry-conflict` |
| `render.r.geometry-theme-gated` | §13 OPEN-DI / OPEN-LOOK; §9.4 shared geometry | per-theme geometry is not approved while OPEN-DI/OPEN-LOOK keeps shared geometry | refused `profile-open` |
| `render.r.grid-side-stripe` | §9.3 Per-notion style, text and glyph contracts | R of the second neutral profile: header-band glyph, ServiceTask glyph, synthetic stripe style, unsupported support lane | ok |
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

## Appendix B — export tree (`tests/profile_export/expected/`, 70 cases)

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
| `export.legacy.fidelity-notice-unknown-class` | §10.2 legacy diagnostic adapter table; §10.1 adapters | a FidelityNotice without a closed loss class is not known | ok |
| `export.legacy.invalid-reference` | §10.2 legacy diagnostic adapter table; §10.1 adapters | IoError invalid-reference: one integrity entry per ID, pointer only when indexed | ok |
| `export.legacy.known-family-not-in-manifest` | §10.2 legacy diagnostic adapter table; §10.1 adapters | no code is guessed: a table code missing from the adapter manifest is legacy-unmapped | ok |
| `export.legacy.missing-endpoint` | §10.2 legacy diagnostic adapter table; §10.1 adapters | IoError missing-endpoint row | ok |
| `export.legacy.unknown-format` | §10.2 legacy diagnostic adapter table; §10.1 adapters | IoError unknown-format row | ok |
| `export.legacy.unlisted-code` | §10.2 legacy diagnostic adapter table; §10.1 adapters | closed fallback: an unlisted legacy code is legacy-unmapped | ok |
| `export.legacy.unsupported-format` | §10.2 legacy diagnostic adapter table; §10.1 adapters | IoError unsupported-format row | ok |
| `export.map.capability-byte-claim` | §10.2; §13 OPEN-EXPORT-EVIDENCE | no feature becomes byte-compatible by declaration alone | ok |
| `export.map.capability-losses` | §10.2 Export recipe, capability and loss contract | capability predicates evaluate once per occurrence; declared losses map like the loss action | ok |
| `export.map.capability-none` | §10.2 Export recipe, capability and loss contract | with no applicable capability record the artifact stays at the structural ceiling | ok |
| `export.map.capability-unsupported` | §10.2 Export recipe, capability and loss contract | an unsupported necessary occurrence refuses the entire artifact (no partially valid download) | refused `export-format-unsupported` |
| `export.map.compat-digest-mismatch` | §3.3 compatibility decision; §10.2 | compatibility rows apply before export | refused `profile-digest-mismatch` |
| `export.map.counter-reuse` | §10.2 Export recipe, capability and loss contract | repeated outputId requests reuse one ID; only requested keys are allocated | ok |
| `export.map.digest-policy` | §10.2 Export recipe, capability and loss contract | digest output IDs are e_ + full SHA-256 of JCS [pageId, occurrenceKey, domain] | ok |
| `export.map.edge-before-nodes` | §10.2 Export recipe, capability and loss contract | nodes before edges: an edge endpoint emitted later refuses export-parent-order | refused `export-parent-order` |
| `export.map.field-missing-required` | §10.2 Export recipe, capability and loss contract | a required named field evaluating to MISSING refuses export-field-invalid | refused `export-field-invalid` |
| `export.map.format-unknown` | §10.2 Export recipe, capability and loss contract | a format absent from the profile exports refuses export-format-unsupported | refused `export-format-unsupported` |
| `export.map.format-without-adapter` | §10.2 Export recipe, capability and loss contract | a declared format without a registered Python adapter refuses export-format-unsupported | refused `export-format-unsupported` |
| `export.map.grid-fixture` | §10.2 Export recipe, capability and loss contract | counterOrigin 10, a later child emission uses an earlier preallocated number, node parent of a node | ok |
| `export.map.kinds-and-losses` | §10.2 Export recipe, capability and loss contract | every export-ir/1 kind, edge endpoints, artifact-global and page metadata, each loss class through the loss action mapping | ok |
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
| `export.map.stale-payload` | §9.2 Digest formulas and freshness | a payload edited after binding fails payloadDigest | refused `render-stale` |
| `export.map.stale-profile` | §9.2 Digest formulas and freshness | each stale binding field returns render-stale | refused `render-stale` |
| `export.map.stale-semantic` | §9.2 Digest formulas and freshness | R bound to an older semantic revision is stale | refused `render-stale` |
| `export.map.stale-theme-digest` | §9.2 Digest formulas and freshness | each stale binding field returns render-stale | refused `render-stale` |
| `export.map.stale-theme-unknown` | §9.2 Digest formulas and freshness | each stale binding field returns render-stale | refused `render-stale` |
| `export.prepare.compat-refusal` | §10.2 prepareExport; §6.2 stage table | compatibility runs before C: refusal with an empty report, no artifact, no mutation | refused `profile-digest-mismatch` |
| `export.prepare.lint-refusal-stage-order` | §10.2 prepareExport; §6.2 stage table | stage order: the first blocking lint stage (pre-normalize, accept) refuses with the complete report so far | refused `bpmnlint/end-event-required` |
| `export.prepare.missing-support` | §10.2 prepareExport; §6.2 stage table | preparation never creates supports: placements into an unbound region refuse profile-open | refused `profile-open` |
| `export.prepare.success` | §10.2 prepareExport; §6.2 stage table | end-to-end preparation on a post-N fixed point: C, lint, N, layout, R and map under accept | ok |
| `export.serialize.drawio-kinds` | §10.1 serializePrepared; §10.2 OPEN-EXPORT-EVIDENCE | structural serialization with an edge, a label and metadata records | ok (structural) |
| `export.serialize.drawio-neutral-fixture` | §10.1 serializePrepared; §10.2 OPEN-EXPORT-EVIDENCE | structural draw.io serialization of a prepared artifact; digest = B(bytes); idMap and capability carried | ok (structural) |
| `export.serialize.format-unsupported` | §10.1 serializePrepared; §10.2 OPEN-EXPORT-EVIDENCE | only registered adapters serialize | refused `export-format-unsupported` |
| `export.serialize.stale-semantic` | §10.1 serializePrepared; §10.2 OPEN-EXPORT-EVIDENCE | the prepared semantic revision must match its renderBinding | refused `render-stale` |
| `export.serialize.stale-view` | §10.1 serializePrepared; §10.2 OPEN-EXPORT-EVIDENCE | serialization verifies renderBinding freshness | refused `render-stale` |
