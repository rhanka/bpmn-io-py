# SPEC PROFILE CN PY — Python binding of lot 3 (recipes, C, N, supports, import adapters)

Status: binding contract for the lot-3 code job in `bpmn_io.profile` (target 0.3.0
at lot 6, no version bump in block B). Normative design authority is DESIGN R3.3
(SHA-256 `48139f5fd5bd789eacbf271081a95432c54d8361b1e52404e3443a25fa65782f`),
sections §2.4, §2.4.1, §3.2, §5.2–5.3, §7.1–7.3, the §13 gates OPEN-RESERVED-N,
OPEN-EXTERNAL, OPEN-IO, OPEN-MACHINE, OPEN-SHARING, OPEN-ID and the owner decisions
of §16 (items 1, 2, 4, 6, 8, 11, ratified 2026-10-14). It extends
`spec/SPEC_PROFILE_MECHANISM_PY.md` (the lot-0 binding, cited below as MECH);
every divergence from MECH §6 is a listed erratum (§10).

This revision is the single seal fix round of block B lot 3. It applies, in this
precedence order: the DESIGN R3.3 text, the block-B JS/Python harmonization decisions
(cited "H <row>", for example H D1; each decision binds both runtimes) and the seal
review findings. §14 maps every applied decision and finding to the sections and
cases it changed. The block-B parity sync then reconciled this seal with the JS
lot-3 seal: its decisions are cited "PS-nn" and its import rows "PS-Hnn" (each binds
both runtimes); §14.3 lists the values it changed and the cases it vendored. The
block-B Unicode-integrity audit (2026-10-19) found no code point lost in the own
cases since their first seal; it gives `cn-c-unicode-names` the witnesses its
derivation claims for no NFC and no case folding (`draft`, `Caf` + U+00E9 and
`Cafe` + U+0301 after the five former names): eight distinct IDs, the former five
unchanged (§11). Vendored JS cases keep the bytes of the JS seal that owns them.

The sealed expectations live in `tests/profile_cn/expected/` and are pinned by
`MANIFEST.sha256` (196 harness cases: 127 own cases and 69 vendored JS cases; 5 input
artifacts, the derivation helper, the vendored JS bytes under `vendor/js/` (§9.2) and
the profile-parity-corpus/1 projection under `parity/`, §9.1). The own cases are
hand-derived from the DESIGN text, the H decisions and the vendored contracts in
`contracts/profile-mechanism/1/`; the vendored cases copy the values of the JS seal
that owns them (§9.2). The standalone stdlib helper `derive_helper.py`
only computes canonical bytes, SHA-256, `stable-id/1`, content signatures,
revisions, profile deltas, the DESIGN orderings and the corpus projection. A code job
implements against them and never edits them: on a disagreement with the DESIGN it
keeps the expectation, adds an `xfail(strict=True)` test naming the DESIGN line and
the expectation file, and reports it.

`complete` and `normalize` (§3.4, §3.5) and their output shapes (§4) are final:
lots 4 and 5 code against them in parallel.

## 1. Inputs and vocabulary

- Vendored contracts: `neutral-profile.json` (`neutral/1`), `neutral-grid-profile.json`
  (`neutral-grid/1`), `neutral-descriptors.json`, `neutral-base.json`,
  `neutral-support-fixture.R31.json` (descriptor slice, base, `ensure-supports`
  recipe, 3 cases, 4 negatives), `neutral-fixture.json` and
  `neutral-grid-fixture.json` (completed trees and placements).
- Sealed input artifacts (`tests/profile_cn/expected/artifacts/`):
  `support-descriptors.json` / `support-base.json` (the R3.1 fixture slice and base,
  2-space JSON plus LF, exactly as the R3.1 check pins them), `cn-descriptors.json` /
  `cn-base.json` (a synthetic slice covering the lot-3 native types, §2.3) and
  `profile-variants.json` (19 profile variants as explicit RFC 6902 deltas, §2.4).
- "Element": a JSON object with a string `$type`. "ID-bearing": its descriptor type
  has `id: true`. "UTF-16 order": comparison by UTF-16 code units (MECH §3).
- Activation (H H1, the shared JS/Python contract): `"edit"` (default; every open
  technical gate enforced) or `"qualification"` (read-only preview and neutral
  qualification, DESIGN §7.2 and §13: "read-only preview and neutral qualification may
  proceed"). A qualification result is a candidate for inspection or qualification
  receipts; it is never committed to an editor history or exported while a gate is
  open (lots 4/5 always pass `"edit"`). Parity cases carry an `activation` input
  artifact only for `"qualification"` (absent means `"edit"`, §9.1).

## 2. Module layout and prerequisites

### 2.1 New private modules (all under `src/bpmn_io/profile/`)

| Module | Content |
| --- | --- |
| `_cn_gates.py` | `GATES` (§7) |
| `_cn_context.py` | `Authority`, `create_read_context` |
| `_cn_plan.py` | `plan_recipe`, WritePlan/1 |
| `_cn_apply.py` | `apply_plan`, ChangeReport/1, coalescing and tree writes |
| `_cn_identity.py` | C identity allocation (§6.2) |
| `_cn_complete.py` | `complete` |
| `_cn_normalize.py` | `normalize`, `sort_placements` |
| `_cn_supports.py` | `propose_support_bindings`, `bind_supports` |
| `_cn_remap.py` | `remap_ids` |
| `_cn_import.py` | `import_projection` (§3.8) |

Public names re-exported from `bpmn_io.profile` and added to `__all__` (stubs
regenerated with `scripts/gen_stubs.py`): `Authority`, `GATES`, `apply_plan`,
`bind_supports`, `complete`, `create_read_context`, `import_projection`, `normalize`,
`plan_recipe`, `propose_support_bindings`, `remap_ids`, `sort_placements`.

### 2.2 Block A prerequisites (errata applied by the lot-3 code job)

The sealed variants are schema-valid. Compiling them needs the following corrections
of existing profile modules; each restores the pinned schema or the DESIGN rule. None
touches a literal port.

| Id | Module | Current Block A behaviour | Required behaviour (authority) |
| --- | --- | --- | --- |
| B1 | `_compiler`, `_evaluate` | `count` reads `selector`; `reachable` reads `source`/`target` | `count.select`; `reachable.from`/`to` (pinned `profile-mechanism-1.schema.json` `$defs/predicate`) |
| B2 | `_compiler` | `inverseReference` property checked on the `from` binding's type | the property belongs to the referencing (candidate) type: admitted iff some descriptor type declares it as a reference (DESIGN §2.2: inverse traversal over a descriptor reference) |
| B3 | `_compiler` | `ensure` returns without checks: its `as` handle is unknown to later steps (`profile-symbol`) and its writes are not demanded | CR-05/06/07 for ensure (§6.3): type restricted to `bpmn:Collaboration`, `bpmn:Participant`, `bpmn:LaneSet`, `bpmn:Lane` (else `profile-producer`), known type (`profile-type`), declared `owner`/`parent` bindings (`profile-symbol`), containment admission (`profile-type`), scalar fields admitted and produced by `code`, `id` produced by `code`, demands `{parent,/property,create}` and `{envelope,/bindings,binding}`, `as` registered with the ensured type |
| B4 | `_compiler` | CR-06 write-set compared as a multiset | compared as a set: identical demands coalesce (DESIGN §2.4 "Identical writes coalesce"; the R3.1 checker) |
| B5 | `_evaluate` | `owner` only follows a native `parent_` attribute | `owner` resolves the immediate containing element of plain native JSON trees (C/N operate on envelope JSON) |
| B6 | `_compiler` | descriptor type records drop unknown facets | keep the optional `many` (multi-valued reference properties) and `single` (single-valued containment properties) facets; absent facets mean references single-valued and containment multi-valued (the vendored slices) |
| B7 | `_compiler` | `CompiledProfile` lacks identity, types and producers | add read-only fields (with defaults, additive): `identity` (the §5.1 record: `mechanismVersion`, `schemaVersion`, `profile`, `version`, `sha256 = H(profile)`, `base`, `descriptors`), `types` (descriptor index with facets) and `producers` (effective producer matrix). C/N and the adapters require a profile compiled with `descriptor_context` and `base`; otherwise they refuse `descriptor-mismatch` (`cn-c-uncompiled-context`; lots 4 and 5 must compile with both inputs) |
| B8 | `_envelope` | `validate_envelope` checks shape, bindings and revision in one pass | C/N and the adapters split it (H C1, §5.0): the shape needed to read `documentVersion`, identity and revision first, §3.3 compatibility next, then envelope integrity (bindings closure and owner+role uniqueness → `support-binding-conflict`, projection and revision → `profile-schema`) |
| B9 | reference validation | none for C/N inputs | the C/N graph index refuses a nonempty unresolved or wrong-type native reference with `reference-dangling` (H C2); an empty single-valued reference value (`calledElement: ""`) is not a reference (H C3, DESIGN §4.1) |
| B10 | `_compiler` `DescriptorContext.digest` | `H(sorted package ids)` | the archived `importedDi.descriptorDigest` uses the DESIGN §9.2 formula `H(descriptor pins sorted by id)`, pins `{id, version, sha256}` taken from `compiled.identity.descriptors` (§6.6) |

The witnesses `cn-compile-support-profile` (R3.1 "Ensure fixture compiles") and
`cn-compile-variants` currently fail under Block A for B1–B4; that is the expected
test-first failure of the code job.

### 2.3 The `cn` descriptor slice

`cn-descriptors.json` (`neutral-cn-descriptors/1`) and `cn-base.json`
(`neutral-cn-base/1`, `fixture-1`, every field produced by `code`, `editor`,
`import`) admit: Definitions (`rootElements`: Process, Collaboration, DataStore),
Process (`flowElements`, `artifacts`, `documentation`, `laneSets`, single
`ioSpecification`), Task (`incoming`/`outgoing` many, `properties`,
`dataInputAssociations`, `dataOutputAssociations`), ServiceTask, CallActivity
(`calledElement` declared as a single reference to Process), StartEvent
(`eventDefinitions`, `outgoing` many), TimerEventDefinition (single `timeDuration`),
ID-less FormalExpression, ExclusiveGateway (`gatewayDirection`, `incoming`/`outgoing`
many), SequenceFlow, TextAnnotation, Association, ID-less Documentation, DataObject,
DataObjectReference, DataStore, DataStoreReference, ID-less InputOutputSpecification,
DataInput, DataOutput, InputSet/OutputSet (`dataInputRefs`/`dataOutputRefs` many),
Property, DataInputAssociation/DataOutputAssociation (`sourceRef` many),
Collaboration, Participant, LaneSet, Lane (`flowNodeRef` many). The slices pin no
DI/DC descriptor package (§12).

### 2.4 Profile variants

`profile-variants.json` lists, per variant: `name`, `source` (vendored file) or
`parent` (another variant), the ordered `delta` (RFC 6902 `add`/`replace`/`remove`),
`descriptorBytes`, `baseBytes` (repository-relative paths) and the expected
`identity`. To build a variant: apply the delta chain to the parsed source JSON,
serialize it, `load_profile(bytes, schema_bytes=<profile-mechanism-1.schema.json>,
base_bytes=<baseBytes>)`, `create_descriptor_context([{**profile["descriptors"][0],
"descriptorBytes": <descriptorBytes>}])`, `compile_profile(validated,
descriptor_context=..., base=json.loads(<baseBytes>))`. The compiled `identity` must
equal the listed one. The composed bytes of every variant are also committed under
`parity/profiles/` (H A3).

| Variant | Delta (summary) | Purpose |
| --- | --- | --- |
| `neutral`, `grid` | none | vendored profiles (opposite `isExecutable` defaults, Task vs ServiceTask, `content` vs anchored `side` placements) |
| `support` | neutral − `place-task` + R3.1 `ensure-supports`; pins re-pinned to the support slice | R3.1 support fixture (as the R3.1 check builds it) |
| `support-abort` | support + `refuse fixture-abort` after the five ensures | R3.1 explicit refusal |
| `support-task-ensure` | support with the lane ensure turned into a `bpmn:Task` ensure | CR-06 ensure restriction |
| `support-no-binding-write`, `neutral-containment-task` | support without the envelope binding write / create-task with containment identity | CR-06 write set, CR-07 identity |
| `support-cmd` | support + `assign-lane-member` | second descriptive context (single-valued `Lane.flowNodeRef`, §3.2) |
| `grid-extraction` | grid + producerDelta `import → ai` on `rootElements`, `flowElements`, `ServiceTask.name` | extraction actor schema |
| `cn-c` | neutral + cn pins + 13 complete recipes (topology, gateway direction, backing objects, ports, IO sets) | C policy data |
| `cn-c-unfixed`, `cn-c-second-pass`, `cn-c-noauth` | cn-c + a self-feeding rename / an idempotent rename plus a refuse on the renamed value / producerDelta `code → dropped` on `DataInputAssociation.targetRef` | fixed point (change, refusal), port authority |
| `cn-n` | neutral − `place-task` + cn pins + 7 normalize recipes (placement regions `reference-band` and `external-lane`, equal to the support roles, H K1) + 9 command recipes (create-process-input, remove-element, conflicting-rename, toggle-membership, rename-only-task, clear-name, rename-optional-task, assign-lane-member, move-annotation) | N policy data, command matrix, deletion/remap chain |
| `cn-n-conflict`, `cn-n-relocate`, `cn-n-unfixed`, `cn-n-second-pass` | cn-n + conflicting direction / membership release / self-feeding rename / idempotent rename plus refuse | conflicts, responsibility, fixed point (change, refusal) |
| `cn-n-ensure-conflict` | cn-n + an ensure of the reference band with another name | conflicting ensure definitions |

## 3. Signatures

### 3.1 Read context and authority

```python
@dataclass(frozen=True)
class Authority:
    actor: Literal["editor", "code"]
    activation: Literal["edit", "qualification"] = "edit"
    deletion_intent: bool = False

def create_read_context(
    compiled: CompiledProfile,
    envelope: DocumentEnvelope | Mapping[str, object],
    *,
    stage: str,
) -> PureSuccess | PureRefused  # payload: ReadContext
```

Wire form of `Authority` in the sealed cases: `{"actor", "activation",
"deletionIntent"}`; any other actor or member is an invalid invocation
(`operation-error`, `cn-plan-invalid-authority`). `create_read_context` applies §5.0
steps 1–5 and returns the Block A `ReadContext` extended with read-only fields
(additive, with defaults): the compiled profile, its descriptor/effective-base index,
the immutable deep copy of the envelope, its source pointers and revision (DESIGN
§2.5 ReadContext). `stage` is one of the §10.1 stages (informational; plans never
depend on it; the case runner passes `"load"`).

### 3.2 `plan_recipe` (DESIGN `planRecipe`)

```python
def plan_recipe(
    recipe: Mapping[str, object],
    read_context: ReadContext,
    params: Mapping[str, object],
    authority: Authority,
) -> PureSuccess | PureRefused  # payload: WritePlan/1
```

`recipe` must equal (JCS) `compiled.recipes[recipe["id"]]` of the context's profile
(`profile-symbol` otherwise: `cn-plan-recipe-not-compiled`). Export recipes are
planned by `map_export` (lot 4): `profile-action-phase` (`cn-plan-export-phase`).
Pure: never mutates its arguments.

WritePlan/1 (closed):

```text
{planVersion: "1", phase, actor, activation, baseRevision, writes: PlannedWrite[]}
```

`baseRevision` is the context envelope's `semanticRevision`. `writes` lists every
evaluated write in recipe candidate order (selector order on the phase-start
snapshot), then step order, including no-op writes. Target and parent references are
`{"id": <id>}` for an ID-bearing element (existing or planned), `{"pointer": <input
pointer>}` for an existing ID-less element, `{"handle": <index in writes>}` for a
planned ID-less element. PlannedWrite variants (exact keys):

| `op` | Keys |
| --- | --- |
| `create` | `recipeId, type, parent, property, fields` (object), `cardinality`, `id` only for `identity: allocated` |
| `ensure` | `recipeId, decision` (`reuse` or `create`), `ownerId, role, type, parent, property, id, fields, cardinality` |
| `set` | `recipeId, target, property, value` |
| `unset` | `recipeId, target, property` |
| `assignRef` | `recipeId, target, property, mode, ids` (flattened one level), `cardinality, targetTypes` |
| `reparent` | `recipeId, target, parent, property, position, cardinality` |
| `place` | `recipeId, elementId, ownerProcessId, regionKey, relatedAssociationIds`, `anchorAssociationId` when bound |
| `remove` | `recipeId, target, policy, deleteIds` (ID-bearing ids of the deletion closure, UTF-16 sorted) |

Descriptive facts carried by the plan (review blocker resolved per DESIGN): DESIGN §2.5
fixes `applyPlan(plan, stagedTree, stagedEnvelope)` and states that "Python snake_case
methods have identical input/result fields", while DESIGN §2.4 requires assignRef to
"validate cardinality, uniqueness, existence, ownership and target type before
assignment" and creations to respect single-valued containment. `plan_recipe` reads
these facts from the descriptor/effective-base index of its ReadContext (DESIGN §2.5)
and records them in the write: `cardinality` is `"single"` or `"many"` (containment
multi-valued unless the descriptor lists it under `single`; references single-valued
unless listed under `many`), `targetTypes` the admitted referenced types of the
property, unique and UTF-16 sorted. `apply_plan` uses only the carried facts and the
staged inputs; it never resolves them from a global, cached or ambient descriptor
registry. Witness pair: `cn-plan-lane-member-cn` (cn slice, `many`) and
`cn-plan-lane-member-support` (support slice, `single`, the stored value is a
string).

`bind` and `when` produce no write; a reached `refuse` step makes the plan refuse with
its own `code`.

### 3.3 `apply_plan` (DESIGN `applyPlan`)

```python
def apply_plan(
    plan: Mapping[str, object],
    staged_tree: Mapping[str, object],
    staged_envelope: DocumentEnvelope | Mapping[str, object],
) -> PureSuccess | PureRefused  # payload: ChangeReport/1
```

Never mutates its arguments (house rule: deep copy at boundaries); the staged result
is returned. ChangeReport/1 (closed):

```text
{reportVersion: "change/1", tree, bindings, entries, placements, created, removed}
```

`tree` and `bindings` (sorted §5.1) are the staged result; `entries` are Report/2
change entries (§4.3) in §4.4 order, emitted only for `complete` and `normalize`
plans (explicit commands are recorded by the caller's history, lot 5); `placements`
in §4.6 order; `created` lists ids of ID-bearing elements created or ensured, in
application order; `removed` lists deleted ids in UTF-16 order.

### 3.4 `complete` (DESIGN `complete`) — final

```python
def complete(
    compiled: CompiledProfile,
    envelope: DocumentEnvelope | Mapping[str, object],
    mode: Literal["extraction", "retained"],
    *,
    activation: Literal["edit", "qualification"] = "edit",
) -> ResultSuccess | ResultRefused
```

`operation` is `"complete"`; `payload` is the DocumentEnvelope/1 wire value of the
completed envelope (same `profileIdentity`, same sorted `bindings`, recomputed
`semanticRevision`). `mode` names the actor schema of the input content (DESIGN §7.1
"distinct actor schemas", H B7): `extraction` = AI output (actor `ai`), `retained` =
admitted retained native content. A consumer needing a Block A `DocumentEnvelope`
from a payload builds it with `complete_envelope(payload["profileIdentity"],
payload["tree"], payload["bindings"])`, which reproduces the same revision; every
lot-3 operation also accepts the wire mapping as input (§4.1).

### 3.5 `normalize` (DESIGN `normalize`) — final

```python
def normalize(
    compiled: CompiledProfile,
    envelope: DocumentEnvelope | Mapping[str, object],
    placement_intent: Sequence[Mapping[str, object]] | None = None,
    *,
    activation: Literal["edit", "qualification"] = "edit",
) -> ResultSuccess | ResultRefused
```

`operation` is `"normalize"`; `payload` is exactly `{envelope, placements, report}`
(H B5): `envelope` the normalized DocumentEnvelope/1 wire value, `placements` the
derived placement records (§4.6), `report` the same Report/2 wire value as
`result.report`. `placement_intent` is `None` or a list of closed records
`{"elementId": <id>}` naming moved/resized/reattached shapes (DESIGN §8.2 step 3). It
is validated (§5.2) and does not change the semantic outputs: a DI-only move changes
only `viewRevision`, which N does not compute; layout consumes the intent (lots 4/5).

### 3.6 Placement ordering

```python
def sort_placements(placements: Sequence[Mapping[str, object]]) -> list[dict[str, object]]
```

Pure; returns deep copies in the §4.6 order.

### 3.7 Support binding and ID remap adapters (Python names, shared camelCase names)

```python
def propose_support_bindings(
    compiled: CompiledProfile,
    envelope: DocumentEnvelope | Mapping[str, object],
    *,
    provenance: Sequence[str] = (),
) -> PureSuccess | PureRefused  # payload: {"proposals": [binding records]}

def bind_supports(
    compiled: CompiledProfile,
    envelope: DocumentEnvelope | Mapping[str, object],
    bindings: Sequence[Mapping[str, object]],
    *,
    activation: Literal["edit", "qualification"] = "edit",
) -> ResultSuccess | ResultRefused  # operation "bindSupports", payload: envelope

def remap_ids(
    compiled: CompiledProfile,
    envelope: DocumentEnvelope | Mapping[str, object],
    imported_di: Mapping[str, object],
    command: Mapping[str, object],
    *,
    activation: Literal["edit", "qualification"] = "edit",
) -> ResultSuccess | ResultRefused  # operation "remapIds", payload {"envelope", "importedDi"}
```

Shared camelCase names (H A4): `proposeSupportBindings`, `bindSupports`, `remapIds`,
`sortPlacements`. `propose_support_bindings` is the read-only recovery/import preview
of DESIGN §5.2 (OPEN-MACHINE: "supply/review support bindings"); `bind_supports` is
the explicit binding (and recovery activation) transaction; `remap_ids` is the
separate approved import ID-remapping migration (H B14, H9). None is ever invoked
implicitly by C or N.

`imported_di` is the archived Snapshot/1 record `{descriptorDigest, diagrams,
sha256}` (DESIGN §8.1.1). `command` is the closed migration record (H H9):

```text
{kind: "id-remap", approved: true, approval: <nonempty string>,
 map: [{sourceId, resultId, domain: "migration"}],
 referenceFreeAttestations: [{property: "<Type>.<member>", referenceFree: true,
                              descriptor: {id, version, sha256}}],
 namespaces?: [{prefix, uri}]}
```

`map` lists the changed rows (any order, unique `sourceId`); the total map is the
identity elsewhere. `namespaces` (parity sync PS-19, DESIGN §5.2 "Resolve QNames using
captured namespace bindings") is optional: unique `{prefix, uri}` records the import
adapter captured, validated with the closed command record (§5.5). A
QName reference value `<prefix>:<local>` whose prefix is bound to the document's own
namespace (the Definitions `targetNamespace`) resolves to the in-document element
`<local>` and is rewritten keeping its prefix; one bound to another namespace is an
external reference: it stays unchanged with one observed `unsupported-namespace`
entry (§6.6) and the remap succeeds (vendored witness `l3-imp-remap-qname`).

### 3.8 Import projection (H B15)

```python
def import_projection(
    compiled: CompiledProfile,
    source: Mapping[str, object] | bytes,
    *,
    source_format: Literal["native-json", "bpmn-xml"] = "native-json",
) -> ResultSuccess | ResultRefused  # operation "importProjection", payload {"tree"}
```

Shared name `importProjection`. Semantics §6.8. The parity case is the JS-owned
`l3-imp-projection-out-of-base`, vendored by the parity sync with its PS-21 values
(§9.2); the Python slices declare no out-of-base type, so no Python-native case
exists (§12).

### 3.9 Gate table

```python
GATES: Mapping[str, Mapping[str, str]]  # read-only (MappingProxyType), §7
```

## 4. Output shapes

### 4.1 Envelope in and out

Inputs accept a `DocumentEnvelope` (converted with `to_json()`) or its wire mapping,
validated in the two §5.0 steps (shape, then integrity after compatibility). Outputs
are built with Block A `complete_envelope(identity, tree, bindings)` (sorted bindings,
recomputed revision) and returned as wire values. `baseRevision` is the input
`semanticRevision`; `revision` is the output one (equal when nothing changed).

### 4.2 Tree write canon (H F1)

- A created or ensured element is `{"$type", "id"?, <declared fields>}`. For a
  `cardinality: many` containment it is appended at the end of the parent's array
  (the array is created when absent); a `single` containment receives the object (an
  occupied single property refuses `profile-type`).
- An assignRef/remove/unset/reparent result is stored as written: an emptied array
  stays `[]`, and an assignRef `replace` with an empty derived set on an absent
  multi-valued property writes `[]`, which is a change (DESIGN §2.4 assignRef
  "validate then assign", §7.1 "Replace incoming/outgoing with selector-derived ...
  IDs"; H F1). Untouched empty arrays of the input are preserved (H F2).
- Multi-valued references (`many`): `replace` stores the given ids in the given order
  (`ids` operands come in selector order, i.e. UTF-16 id order); duplicate ids refuse
  `profile-type`. `appendUnique` and `remove` deltas on one property coalesce by id:
  stored order minus removals, then new ids in UTF-16 order (DESIGN §2.4).
  Single-valued references: `replace` requires exactly one id (`profile-type`
  otherwise) and stores the string; `remove` of the current id deletes the scalar
  property; `appendUnique` refuses `profile-type`.
- Every referenced id must name an element of the staged tree, including elements
  planned earlier in the same plan (`reference-dangling`), whose `$type` is one of the
  write's `targetTypes` (`profile-type`, `cn-plan-link-wrong-target-type`). Reference
  writes never create an endpoint.
- `reparent` removes the element from its parent array and inserts it into the
  destination at `first`, `last` or (same parent/property only) its current index;
  its id is preserved.
- A write whose canonical result equals the stored value is a no-op: no change entry.

### 4.3 C/N change entries (Report/2, DESIGN §10.1 "New C/N"; H B8, B9, B10)

One entry per distinct written location whose value changes. Common fields:
`severity: "info"`, `classification: "repairable"`, `disposition: "corrected"`,
`stage` = `complete` or `normalize`, `code` = `<stage>/<action>`, `messageKey` =
`<stage>.<action>`.

| Change | `code` | `ruleId` | `property` | `before` | `after` |
| --- | --- | --- | --- | --- | --- |
| C identity allocation | `complete/allocate-id` | `stable-id/1` | `id` | absent | new id |
| recipe `set` | `<stage>/set` | recipe id | property name | stored value or absent | written value |
| recipe `unset` | `<stage>/unset` | recipe id | property name | stored value | absent |
| recipe `assignRef` | `<stage>/assignRef` | recipe id | property name | stored value or absent | final stored value (`[]` when emptied) |
| `create` (C) | `complete/create` | recipe id | containment property | absent | final subtree at the result pointer |
| `ensure` that creates (N) | `normalize/ensure` | recipe id | containment property | absent | final subtree at the result pointer |
| `reparent` | `<stage>/reparent` | recipe id | destination containment property | source parent id | destination parent id |

Coordinates address the exact written location (H B9): the element pointer for a
created element, otherwise the element pointer plus `/` plus the escaped property
(also when the property was absent before, so an allocated id is at `<element>/id`).
`source` is `{domain: "tree", pointer: <input pointer of the written location>,
targetId: <the element's input id, else the input id of its nearest ID-bearing
ancestor that had one, else null>, provenance: "exact"}` for a location of an input
element, and `{domain: "none", pointer: null, targetId: null, provenance:
"generated"}` for a created element and every write on it. `result` is `{domain:
"tree", pointer: <output pointer of the written location>, targetId: <output id, or
nearest ID-bearing ancestor for ID-less content>, provenance: "generated"}` when the
element was created or its id allocated by the operation, otherwise `"exact"`.
`before`/`after` are read from the immutable input and the final output. A coalesced
write (identical plans of two recipes) is reported once, under the recipe that
planned it first (H B11). No entry is emitted for placements or binding records.

### 4.4 Entry order (H G2)

DESIGN §10.1 order (stage rank; then UTF-16 `ruleId`, source `domain`, source
`pointer` and `targetId` with null first, `code`, `pageId`, `occurrenceKey`,
canonical `before` then `after` with absent first), then result `domain`, result
`pointer`, result `targetId` (UTF-16, null first), then `property` (absent first).
Exact duplicates coalesce. No sealed report contains two entries equal on all keys.

### 4.5 Report header and refusals (H B2, B3, B4)

A success report carries all four optional header members: `sourceIdentity` = the
input envelope identity, `targetIdentity` = the output envelope identity (equal for
every lot-3 operation), `inputRevision` = `baseRevision`, `outputRevision` =
`revision`; empty `rawStandardFindings` and `artifacts`; `idMap` empty except for
`remapIds` (§6.6).

A refusal is exactly `{status: "refused", operation, profileIdentity?, baseRevision?,
code, diagnostics, report}` and carries no candidate. `report.entries` are the unified
findings of the lint stages executed before the refusal (none in lot 3, so `[]`) and
`diagnostics` equals `report.entries`; a refusal never carries change entries. Echo
rule (H B3): `profileIdentity` and `baseRevision` (the input `semanticRevision`
string as given) are echoed whenever the envelope argument is a JSON object with
`documentVersion: "1"`, a shape-valid closed §5.1 identity record (seven members,
string scalars, `mechanismVersion` `"1"`, `schemaVersion` `"1.0.0"`, 64-hex `sha256`,
closed `{id, version, sha256}` pins, at least one descriptor pin) and a string
`semanticRevision`, even when a later check fails (`cn-n-support-duplicate-role`) or
the invocation is invalid (`cn-c-invalid-mode`); they are omitted for an unknown
`documentVersion` (`cn-c-document-version`), an unparseable input or the not-loaded
state. The refusal report repeats the echoed values as `sourceIdentity` and
`inputRevision` and never carries `targetIdentity` or `outputRevision`.

### 4.6 Derived placements (DESIGN §7.2)

Each `place` write gives exactly `{elementId, ownerProcessId, regionKey,
anchorAssociationId?, relatedAssociationIds}`: `elementId` the target id,
`ownerProcessId` the id bound to `owner`, `regionKey` the opaque `region`, the anchor
id only when the `anchor` binding is not MISSING (absent, never null),
`relatedAssociationIds` the unique UTF-16-sorted ids of the `related` selector
(ID-less handles refuse `profile-type`). Identical placements coalesce; two different
placements for one (`elementId`, `regionKey`) refuse `profile-write-conflict`. Order:
UTF-16 tuple (`ownerProcessId`, `regionKey`, `elementId`, `anchorAssociationId` absent
before present, `relatedAssociationIds` compared element-wise with a proper prefix
first). No theme field appears. The library treats `regionKey` as opaque; the cn-n
profile data uses region keys equal to the support roles whose bound rectangle the
layout primitive resolves (`reference-band` for DataStoreReferences, `external-lane`
for Process IO; DESIGN §9.4, H K1). The vendored neutral profile keeps `content`.

## 5. Pipelines and refusal precedence

The first refusal in the listed order is returned; nothing is committed and no input
object is mutated (DESIGN §7.3 rollback).

### 5.0 Common prefix (H C1)

1. Invocation: `compiled` with B7 fields (`descriptor-mismatch` if absent); closed
   arguments (`mode`, `activation`, `placement_intent`, `provenance`, the remap
   `command`) — else `operation-error` (H C11); the operation-specific argument codes of
   §5.5 (supplied binding records, `imported_di`) apply at this step.
2. Envelope shape enough to read version, identity and revision: closed envelope
   members and identity record, tree object with `$type` (`document-version-unsupported`
   for an unknown `documentVersion`, else `profile-schema`).
3. §3.3 compatibility: Block A `check_compatibility(runtime, P, D,
   document_version=..., source_availability=..., selected_migration=False,
   required_capabilities=<profile capabilities>, required_assets=[],
   envelope_valid=True)` with P = `compiled.identity`, D = the envelope identity,
   runtime `{mechanisms: ["1"], schemas: ["1.0.0"], capabilities: <the six DESIGN
   §2.1 ids>, assets: []}` and `source_availability = "known-and-available"` iff D
   equals P (C/N never load another package; DESIGN §3.3 P1), else
   `"unavailable"`. A refused verdict refuses with its code (DESIGN §7.1 "reject
   source version mismatch first"; `cn-n-compat-before-integrity`).
4. Envelope integrity: binding record shape → `profile-schema`; owner+role uniqueness,
   duplicate records, every binding `ownerId`/`targetId` naming an element and no
   `targetId` bound twice → else `support-binding-conflict`; committed semantic
   projection and revision → else `profile-schema`.
5. Graph index (one pre-order pass, members in UTF-16 key order, arrays by index):
   repeated element id → `id-collision` (H C4); unknown element type or member key
   not classified by the descriptor (`$type` excepted) → `descriptor-role-unknown`
   (DESIGN §3.1); a nonempty reference value naming no element, or an element whose
   `$type` the descriptor does not admit for that reference → `reference-dangling`
   (DESIGN §2.2, H C2); an empty single-valued reference value is not a reference
   (H C3). Containment admission is not a graph-index check (the R3.1 wrong-parent
   negative needs the misplaced Participant to reach reuse validation).

### 5.1 `complete`

Steps 1–5 of §5.0, then:

6. Extraction actor schema (`mode == "extraction"` only): every present member of every
   element must admit actor `ai` in the effective producer matrix → else
   `profile-producer` (DESIGN §2.4.1 "AI may author only AI fields in extraction").
7. Identity allocation (§6.2) → `id-collision` on a computed collision.
8. Plan every `complete` recipe in profile declaration order with
   `Authority("code", activation)` on the identity-allocated snapshot (all plans read
   that same snapshot); plan refusals (§5.3) and gates (§7) propagate at their step.
9. Apply the concatenated plan (§5.4).
10. Bounded fixed point (§5.6).

### 5.2 `normalize`

Steps 1–5 of §5.0, then:

6. Placement intent: every `elementId` names an existing element → else
   `reference-dangling`.
7. Plan every `normalize` recipe in declaration order with `Authority("code",
   activation)` on the input snapshot; ensure semantics §6.3, gates §7 at their step.
8. Support Participants: every Participant handle produced by an ensure (reused or
   created) must end with exactly the `processRef` the plan assigns to it, or none when
   no write targets it → else `support-binding-conflict` (DESIGN §5.2 no-processRef
   band; R3.1 negative "reference band cannot carry processRef").
9. Apply (§5.4), then placements (§4.6).
10. Bounded fixed point (§5.6).

### 5.3 `plan_recipe`

Context, authority or parameter-map shape invalid → `operation-error`; recipe not
compiled → `profile-symbol`; export phase → `profile-action-phase`; actor not the
phase actor (`editor` for create/edit/reference/convert/migrate, `code` for
complete/normalize) → `profile-producer`; parameters in declaration order: missing
required or undeclared supplied → `profile-ui-parameters`, wrong JSON type (no
coercion) → `profile-type`, element parameter naming no element →
`reference-dangling`. Then candidates in selector order and steps in order:
selector/predicate/value errors (Block A codes; `reference-dangling` when a
`reference` traversal meets a dangling id, DESIGN §2.2), `bind` cardinality
(`profile-ambiguous-binding` for `one` without exactly one result or `zeroOrOne`
with several), a required use of MISSING (`profile-type`), runtime producer check of
each written (type, property) for the actor (`profile-producer`), ensure (§6.3), gates
(§7), `remove` without `deletion_intent` (`profile-producer`) or with a retained
inbound reference (`reference-dangling`), a reached `refuse` step (its `code`).

### 5.4 `apply_plan`

Plan shape → `operation-error`; staged envelope → the §5.0 step 2 and step 4 codes;
staged tree not canonically equal to the staged envelope tree → `input-conflict`
(`cn-apply-input-conflict`); `plan.baseRevision` ≠ staged `semanticRevision` →
`operation-error` (stale plan, DESIGN §8.2 step 1, aligned with the Block A bridge;
`cn-apply-stale-plan`); then coalescing in plan order: different values for one
(target, property), `replace` mixed with a non-identical write, an id both appended
and removed, two different reparentings, two different placements for one
target/region → `profile-write-conflict`; creations: a created id equal to an
existing id or to a different planned element → `id-collision`
(`cn-plan-create-id-collision`; identical planned creations coalesce); reference
checks of §4.2 with the carried facts.

### 5.5 Adapters

- `propose_support_bindings`: §5.0 steps 1–5, then the dry run of §6.7.
- `bind_supports`: §5.0 step 1 (activation closed, else `operation-error`; supplied
  binding records closed `{ownerId, role, targetId}` with nonempty strings, else
  `profile-schema`), steps 2–5, the gate (`edit` → `profile-open`, OPEN-MACHINE), then
  each new binding: (`ownerId`, `role`) already bound or supplied twice, owner or
  target missing, target already bound → `support-binding-conflict`. The tree is
  unchanged; report entries are empty.
- `remap_ids` (H B14, H9, C20): §5.0 step 1 including the command record (closed;
  `kind` `"id-remap"`; `approved` must be `true` and `approval` a nonempty string,
  else `operation-error`: `cn-remap-not-approved`; closed map rows with unique
  `sourceId`; closed attestation records; optional `namespaces` of unique `{prefix,
  uri}` records, PS-19) and the `imported_di` record (closed, `sha256
  = H({descriptorDigest, diagrams})`, else `snapshot-schema`, Block A bridge code);
  steps 2–4; `imported_di.descriptorDigest` ≠ the DESIGN §9.2 digest of
  `compiled.identity.descriptors` → `descriptor-mismatch`; the gate (`edit` →
  `profile-open`, OPEN-ID); repeated element ids → `id-collision`; then each map row in
  UTF-16 `sourceId` order: `sourceId` naming no element → `reference-dangling`;
  `resultId` outside the authoring subset `^[A-Za-z_][A-Za-z0-9_.-]{0,255}$` →
  `profile-schema`; then the total map not injective over the retained ids →
  `id-collision`; then any element member not classified by the descriptor and not
  covered by an attestation whose `property` is `<$type>.<member>` and whose
  `descriptor` pin equals a pin of the compiled identity → `migration-reference-opaque`
  (DESIGN §5.2). Dangling native references and external QName references are kept
  and reported (§6.6, H C2, PS-19).
- `import_projection` (H B15): arguments (`source_format` closed, else
  `operation-error`); parse (`document-not-loaded` for an unparseable source, no
  baseRevision); duplicate ids → `id-collision`; then the §6.8 projection; then the
  retained graph index (§5.0 step 5 rules) → its codes.

### 5.6 Bounded fixed point (DESIGN §2.4; review finding)

After the first pass succeeds, the operation is evaluated once more on its own output
(the output envelope and result bindings; same activation and placement intent;
`complete` in mode `retained`). DESIGN §2.4: "A second C/N run must return the
identical tree, support bindings and placements, with no changes. A bounded second
evaluation verifies the fixed point; failure is normalization-not-fixed". The proof
fails, and the operation refuses `normalization-not-fixed` with no candidate, when the
second evaluation either produces any change entry or a different placement list
(`cn-c-not-fixed`, `cn-n-not-fixed`: the second evaluation succeeds but changes a
value) or refuses with any code (`cn-c-second-pass-refused`,
`cn-n-second-pass-refused`: the second evaluation changes nothing but reaches a
refusal); the second-pass code is never returned.

## 6. Semantics

### 6.1 Modes and actors

`retained` performs no input actor check (the content was accepted before). `extraction`
checks the input content against actor `ai` (§5.1 step 6); the fixed-point rerun of an
extraction case uses `retained` (its output is retained content). Explicit commands use
actor `editor`, C and N use `code` (DESIGN §2.4.1 R3.1 bounded authority witness).

### 6.2 C identity allocation (DESIGN §3.2; H D1, D2, D3, D4)

1. A Definitions root without `id` (ID-bearing) receives
   `stable-id("document-root/1", "definitions", "root")`.
2. Then, in pre-order (members in UTF-16 key order, arrays by index), each other
   ID-bearing element without `id` receives `stable-id(ownerId, slot, stableKey)` with:
   `ownerId` = the id of its nearest ancestor element having an id (after allocation);
   `slot` = the descriptor-qualified containment property `<containing $type>.<property>`,
   i.e. the descriptor key of the containing element's `$type`, `.`, the containment
   property name (H D1: `bpmn:Definitions.rootElements`, `bpmn:Process.flowElements`,
   `bpmn:StartEvent.eventDefinitions`); `stableKey` = `JCS([contentSignature,
   duplicateOrdinal])`; `contentSignature` = `H(subtree with every id member removed)`
   computed on the raw input subtree (no generated default added); `duplicateOrdinal`
   = the number of earlier ID-missing elements, in that pre-order, with the same
   (ownerId, slot, contentSignature) (0 for a single-valued containment; ID-bearing
   siblings never count, H D3).
3. An allocated id equal to an id of the input or to an earlier allocation refuses
   `id-collision`; existing ids are never changed. Each allocation emits one
   `complete/allocate-id` entry. ID-less types (Documentation, FormalExpression,
   InputOutputSpecification in the cn slice) are never identified.

### 6.3 `ensure` (DESIGN §2.4, §5.2, §7.2; H C5, C6)

For each ensure step: evaluate `owner` (an ID-bearing element), `parent` (element or
planned handle), `ownerId` and `key` (strings) — failure → `support-binding-conflict`.
The ensure plan identity is (owner id, role, type, parent, property, fields, ownerId,
slot, key): an identical earlier plan in the same N run aliases its handle (one
change); a different plan for the same (owner id, role) → `profile-write-conflict`
(DESIGN §2.4 "conflicting ensure definitions ... refuse").

If a binding (owner id, role) exists, reuse validation checks only what DESIGN §5.2
lists (H C5): the target exists, has the ensured type, sits in `parent.property`, has
the processRef/owner relationship of its role (§5.2 step 8 for Participants) and is
the target of exactly that binding; otherwise `support-binding-conflict`. The ensure's
declared fields are creation fields: a renamed bound support is reused unchanged and
never renamed back (`cn-n-reserved-lane-renamed`); supports are never found by name.
The handle is the target (reuse, no change).

Without a binding, the ensure would create: in `edit` activation it refuses
`profile-open` (OPEN-RESERVED-N); otherwise the id is `stable-id(ownerId, slot, key)`,
an id already present (including an unbound element of the right type and name: a
hash-shaped id alone never authorizes reuse) refuses `id-collision` (H C6), and the
element plus binding `{ownerId: owner id, role, targetId}` are planned. An assignRef
targeting a support handle may only fill an absent reference or confirm the stored
value; a different stored value refuses `support-binding-conflict`. N never finds a
support by name and never deletes one.

### 6.4 Other actions

`set`/`unset` write one single-segment declared scalar path (`cn-plan-unset-name`).
`create` allocates `stable-id(ownerId, slot, key)` for `identity: allocated` (ownerId
is the evaluated argument, never the nearest container) and writes no id for
`identity: containment`. `reparent` moves the target (id preserved) into the
destination containment (`cn-plan-reparent-annotation`); N plans no reparent (no
approved structural support move exists). `remove` deletes the target and the declared
dependents with their subtrees; any retained element referencing a deleted id (policy
`refuseIfReferenced`, or outside the declared set for `includeDeclared`) refuses
`reference-dangling`; bindings targeting a deleted element are removed with it (the
support's ownership record); a binding owned by a deleted element refuses
`reference-dangling`. `place` writes no tree. `emit` and `loss` are export actions
(lot 4).

### 6.5 Supports across remaps and deletion (DESIGN §7.2)

Empty supports survive N. A deleted support stays absent while no recipe needs its
role (its emptied parent array stays `[]`); a later need ensures it with the current
`ownerId`, which may give a new id (reported as `normalize/ensure`). Surviving
supports keep their ids through owner remaps.

### 6.6 `remap_ids` (DESIGN §5.2; H B14, H9, C2, C20)

The total map is the identity except the command's rows, built before application and
applied at once (`cn-remap-swap`). Rewritten atomically: element ids, every descriptor
reference value (strings and array items, including `calledElement` in the cn slice),
binding `ownerId`/`targetId`, and every `bpmnElement` string of `imported_di.diagrams`
naming a remapped semantic element; DI objects keep their own ids. Members attested
reference-free are kept byte for byte, even when their string equals a remapped id
(`cn-remap-opaque-attested`). Native references naming no element of the input stay
unchanged and each yields one entry `{code: "reference-dangling", messageKey:
"reference-dangling", severity: "error", classification: "integrity", stage: "import",
ruleId: "remap-ids", disposition: "observed"}` with source and result at the written
location `<element>/<property>` (targetId the referencing element, result provenance
`exact`), `property` and `before` = `after` = the value; the remap succeeds (parity sync
PS-32 makes these coordinates the shared rule for every observed property-level entry
of `remapIds`). A DI `bpmnElement` naming no
semantic element is kept unchanged and reported the same way with domain `artifact`
and pointer `/importedDi/diagrams/...` (no sealed case, §12).

QName references (PS-19, command member `namespaces`, §3.7): a resolved in-document
QName follows the map with its prefix kept (`tns:Process_sub_old` →
`tns:Process_sub_new`); an external one (prefix bound to another namespace) stays
unchanged and yields one entry with the same members and coordinates as a dangling
reference except `code` and `messageKey` `"unsupported-namespace"`; no target is ever
fetched (vendored witness `l3-imp-remap-qname`).

Result: `operation` `"remapIds"`, `profileIdentity` the compiled identity,
`baseRevision` the input envelope revision, `revision` the output one; payload
`{envelope, importedDi}` with `importedDi.sha256` recomputed; `report.idMap` = one row
`{sourceId, resultId, domain: "migration"}` per ID-bearing element of the input
(identity rows included: the complete original→result map), sorted per DESIGN §10.1.
No layout/render invalidation flag is returned: the new revision implies it.
Navigation and provenance remaps act outside the envelope (§12).

### 6.7 Recovery proposal (DESIGN §5.2)

`propose_support_bindings` plans the `normalize` recipes as `normalize(...,
activation="qualification")` would, without gates and without applying anything, with
one difference: when an ensure finds no binding and an element E carries exactly its
`stable-id`, E satisfies the §6.3 reuse validation, E is listed in `provenance` and E
is not a binding target, the ensure is planned as a reuse of E and `{ownerId, role,
targetId: E.id}` is proposed; an occupied id not meeting all conditions gives no
proposal and no refusal. Two proposals for one target → `support-binding-conflict`.
Proposals are sorted as bindings. Activation needs an explicit `bind_supports`
transaction.

### 6.8 Import projection (DESIGN §5.3; H B15)

Build immutable source pointers, then drop every element whose `$type` the effective
base does not admit, with its subtree; cascade through SequenceFlows, Associations and
data associations whose endpoint was dropped (a dropped relation is itself an
element); remove the dropped ids from retained reference arrays; a containment array
emptied by the projection stays `[]` (PS-21, H F1); then run the
retained graph index. Result: `operation` `"importProjection"`, `profileIdentity` the
compiled identity, `baseRevision` = `H({domain: "profile-import/1", format,
sourceDigest})` (DESIGN §3.1: `H(parsedSourceTree)` for native JSON, `B(bytes)` for
XML), `revision` = `baseRevision` (PS-21: read-only, nothing is committed), payload
`{tree}`.
One report entry per dropped element (cascaded relations included): code
`import-loss/unsupported-feature`, messageKey `import.loss.unsupported-feature`,
severity `warn`, classification `loss`, `lossClass` `unsupported-feature`, stage
`import`, ruleId `adapter` (PS-21; the DESIGN §6.4 adapter convention),
disposition `dropped`, source = the exact input pointer and targetId, result
`{domain: "none", pointer: null, targetId: null, provenance: "unavailable"}`,
`beforePresent: true`, `before` = the dropped subtree, `afterPresent: false`. The
report omits `sourceIdentity` (an initial import has no input identity) and carries
`targetIdentity`, `inputRevision` and `outputRevision`, with `outputRevision` =
`inputRevision` (PS-21; vendored witness `l3-imp-projection-out-of-base`).

### 6.9 `validate` entry of a dangling call reference (PS-20)

The vendored `validate` cases (§9.2) run the Block A `validate` on the JS neutral-cn
profile. A dangling `calledElement` is reported by the graph index as one entry
`{code: "reference-dangling", severity: "error", classification: "integrity", stage:
<the validate phase>, ruleId: "adapter", messageKey: "reference-dangling",
disposition: "observed", source: {domain: "tree", pointer: <element>/calledElement,
targetId: <element id>, provenance: "exact"}, result: {domain: "none", pointer: null,
targetId: null, provenance: "unavailable"}, beforePresent: false, afterPresent:
false}`; `validate` still succeeds, and the call-target-type rule never traverses a
dangling reference (DESIGN §4.1, §6.4; vendored witness `l3-call-target-dangling-accept`).

## 7. Gates (DESIGN §13 with §16; H H1, H2, H3)

All owner parts below were ratified on 2026-10-14; every technical part (conductor
plus both libraries) is open, so `GATES` is (state of this release):

| Gate | Owner | Technical | Guarded effective change | `edit` | `qualification` |
| --- | --- | --- | --- | --- | --- |
| OPEN-RESERVED-N | ratified (§16 item 11) | open | an N ensure that would create a support | `profile-open` | proceeds |
| OPEN-EXTERNAL | ratified (§16 item 2) | open | an N `bpmn:Lane` `flowNodeRef` change (external branch of N) | `profile-open` | proceeds |
| OPEN-SHARING | ratified (§16 item 4) | open | removal of an existing `bpmn:Lane` `flowNodeRef` member | `profile-open` | `responsibility-preservation-required` (no accepted persisted responsibility representation, DESIGN §4.4; a library gate in both runtimes, H H3) |
| OPEN-IO | ratified (§16 item 8) | open | a C fill of an absent `bpmn:DataOutputAssociation` `sourceRef` (missing-output-source producer exception) | `profile-open` | proceeds |
| OPEN-MACHINE | ratified (§16 item 6) | open | `bind_supports` | `profile-open` | proceeds |
| OPEN-ID | ratified (§16 item 1) | open | `remap_ids` | `profile-open` | proceeds |

"Effective" is judged at plan time against the phase-start snapshot: reuse of a bound
support, an appendUnique of an id already present and any other no-op are never gated
(N(N(x)) must succeed in `edit`). Gates are checked at their step, so a gate earlier in
recipe/candidate/step order wins over a later refusal (`cn-n-support-late-band-collision-edit`).
External creation/migration (OPEN-EXTERNAL) has no generic detection signal in
`profile-mechanism/1` (§12).

## 8. Fixed points and the cross-runtime exchange (H A7)

Every sealed success case of `complete` and `normalize` carries `"fixedPoint": true`:
rerunning the operation on the expected output (`payload` for complete,
`payload.envelope` for normalize; same activation and placement intent; mode
`retained`) must return status ok, the identical payload envelope (and placements),
zero report entries, and `baseRevision == revision ==` the first `revision` (DESIGN
§7.3: C(C(x)) = C(x), N(N(x)) = N(x), empty second-run change entries).

Cross-runtime witnesses JS(N_Py(x)) = N_Py(x) and Python(N_JS(x)) = N_JS(x) are run by
the conductor (§12). The bytes exchanged between hops are the profile-c14n/2 UTF-8
bytes (no BOM, no trailing newline) of the normalized DocumentEnvelope/1 (DESIGN §2.5:
the N input is an envelope; §5.1: the envelope is the stored document). Each hop
compares, separately, its `placements` artifact and its change-entry list against the
sealed values; a refusal is compared as the profile-c14n/2 bytes of its full Result/1
(report included). The receiving runtime's rerun must also produce zero change
entries.

## 9. Sealed expectation files

Each `tests/profile_cn/expected/<case>.json` holds `case` (= file stem), `clause`,
`author: "spec-seal"`, `operation`, `profile` (variant name, vendored profile record
of §9.2, or null), `derivation`, `input`, `expected` and, for accepted
complete/normalize cases, `fixedPoint`. How each `operation` is run (`compiled` = the
built variant, §2.4, or the loaded vendored profile, §9.2; an absent `activation` means
`edit`, H H1):

| `operation` | Call | Compared with `expected` |
| --- | --- | --- |
| `complete` | `complete(compiled, input.envelope, input.mode, activation=input.activation)`; `input.compile == "without-descriptor-context"` builds the variant without `descriptor_context` and `base` | `result.to_json()` |
| `normalize` | `normalize(compiled, input.envelope, input.placementIntent, activation=input.activation)` | `result.to_json()` |
| `plan_recipe+apply_plan` | `ctx = create_read_context(compiled, input.envelope, stage="load")`; recipe = `compiled.recipes[input.recipe]` when `input.recipe` is a string, else `input.recipe` verbatim; `plan_recipe(recipe, ctx, input.params, Authority(actor, activation, deletion_intent=deletionIntent))` from `input.authority` (an invalid authority record is passed through so that it refuses); then, when `expected.apply` exists, `apply_plan(plan.payload, input.envelope["tree"], input.envelope)` | `expected.plan`, `expected.apply` (PureResult wire) |
| `apply_plan` | `apply_plan(input.plan, input.get("stagedTree", input.envelope["tree"]), input.envelope)` | `expected.apply` |
| `compile_profile` | build `input.variant` (or each of `input.variants`, in order) | the PureResult wire (a list for `input.variants`) after each `{"$unsealed": <reason>}` marker is replaced by the actual member at the same position (the member must exist; PS-35: CompiledProfile has no wire shape); `compiled.identity` with `compiledIdentity` (each `compiledIdentities[i].identity`) |
| `propose_support_bindings` | `propose_support_bindings(compiled, input.envelope, provenance=input.provenance)` | PureResult wire |
| `bind_supports` | `bind_supports(compiled, input.envelope, input.bindings, activation=input.activation)` | `result.to_json()` |
| `remap_ids` | `remap_ids(compiled, input.envelope, input.importedDi, input.command, activation=input.activation)` | `result.to_json()` |
| `sort_placements` | `sort_placements(input.placements)` | the list |
| `gates` | `GATES` as plain dicts | the mapping |
| `validate` (vendored) | Block A `validate(compiled, input.envelope, phase=input.options.phase, readiness_policy=input.options.readinessPolicy)` | `result.to_json()` (§6.9) |
| `stable-id/1` (vendored) | `stable-id/1` of each `input.allocations` record `{owner, slot, key}`, in order | the id list |
| `import_projection` (vendored) | `import_projection(compiled, input.source.text.encode("utf-8"), source_format="native-json")` (`input.source.sha256` is the raw digest of those bytes) | `result.to_json()` |
| `normalize_transport` (vendored) | each hop of `input.transportRoute` whose runtime is `python`: `normalize(compiled, <hop input>, activation=<hop activation>)`, the hop input being `input.envelope` (`"envelope"`) or the parsed `expected.transportBytes.text` (`"hop-<n>-transport-bytes"`, every hop emitting the same sealed bytes) | `expected.hopResults[<hop index>]`; the profile-c14n/2 UTF-8 bytes of `payload.envelope` with `expected.transportBytes` (SHA-256 `expected.transport.hops[<hop index>].outputSha256`); the JS hops and the cross-runtime run are the conductor's joint run (§8) |

Every runner deep-copies `input` before the call and asserts it is unchanged
afterwards, success or refusal (DESIGN §7.3: the caller tree and bindings are
preserved; only a successful return exposes a candidate).

`tests/profile_cn/test_expected_seal.py` verifies the manifest (any one-byte change
fails), that the helper imports only `__future__`, `copy`, `hashlib`, `json`,
`pathlib`, `sys` (AST scan, never `bpmn_io`), the required keys of every case, that the
helper regenerates every sealed byte (vendored files included, §9.2), that every
corpus/1 manifest entry equals the raw SHA-256 of its committed file, that the corpus
cases are closed projections of the own harness cases (runtime-specific and vendored
cases excluded), that every vendored case file has its pinned digest and its harness
record copies its result, and that each alias names a projected twin. Comparison
tolerance is zero.

### 9.1 profile-parity-corpus/1 projection (H A1–A6, A8)

`tests/profile_cn/expected/parity/` publishes every own parity case (all own harness
cases except the runtime-specific `cn-gates-table` and `cn-c-uncompiled-context`; the
vendored JS cases of §9.2 are published by the JS seal) as one closed corpus/1 record `{caseId, operation, phase, profileArtifact, inputArtifacts,
commandArtifact?, expectedArtifacts, expectedStatus, comparatorIds}` (DESIGN §14.3)
with the harness values copied verbatim:

- `operation`: the shared camelCase name (H A4): `complete`, `normalize`,
  `planRecipe` (with an `apply` artifact chaining `applyPlan`), `applyPlan`,
  `compileProfile`, `proposeSupportBindings`, `bindSupports`, `remapIds`,
  `sortPlacements`; `phase`: `complete`, `normalize`, the recipe phase for
  `planRecipe`, else null.
- `profileArtifact`: `{path, sha256}` (H A2) naming the vendored profile file or the
  committed composed variant `parity/profiles/<variant>.json`; `sha256` is the raw
  file digest (H A6); null for mechanism-level vectors.
- `inputArtifacts`: `{role, json}` records (`envelope`, `mode`, `placementIntent`,
  `activation` only for qualification, `recipe`, `params`, `authority`, `plan`,
  `stagedTree`, `provenance`, `bindings`, `importedDi`, `placements`) and `{role:
  "profile", path, sha256}` for `compileProfile` variant lists; `commandArtifact` the
  `remapIds` migration command.
- `expectedArtifacts`: the full Result/1 (`result`), PureResults (`plan`, `apply`,
  `compile`), the compiled identities (`compiled-identity`, `compiled-identities`;
  PS-35) or the placement list (H A8: reports and diagnostics sealed in full);
  `expectedStatus` `ok` or `refused:<code>` (H A5) of the last executed step;
  `comparatorIds` from the manifest (`profile-c14n/2`, `fixed-point/lot3`,
  `plan-apply/lot3`, `compile/lot3`).
- `compileProfile` (PS-25, PS-35): `compile` is the PureResult, exactly `{status:
  "refused", code, diagnostics: []}` for a refusal and `{status: "ok", payload,
  diagnostics: []}` for a success, whose `payload` is the marker `{"$unsealed":
  "compiled-profile"}` (the member must exist; it is never compared); a variant list
  gives one PureResult per `profile` input artifact, in order. The compiled §5.1
  identity of a success is the separate `compiled-identity` artifact (a list of
  `{variant, identity}` records, `compiled-identities`, for a variant list). The
  comparator is `compile/lot3`.

`parity/manifest.json` declares `format`, `pathBase` (`.`, the repository root), the
comparators, the profile load table (`variant`, profile path and digest,
`descriptorBytes` and `baseBytes` paths and digests) and `files`: the raw SHA-256 of
every referenced byte sequence (case files, profile files, descriptor and base bytes;
H A3). Case files are profile-c14n/2 bytes without a trailing newline. It also
declares `vendoredSeal` (the JS seal the vendored files come from: runtime, seal
SHA-256, commit, vendored root), `vendored` (one `{caseId, source, sha256}` row per
vendored JS case, `sha256` the raw digest of the committed file, §9.2) and `aliases`
(PS-37: one `{caseId, aliasOf, sha256}` row per byte-identical twin; `caseId` the JS
case, `aliasOf` the projected Python case, `sha256` the JS case file digest; no file is
copied).

### 9.2 Vendored JS cases (block-B parity sync, harmonization §3)

The parity sync imports 69 JS-owned lot-3 cases (rows PS-H01…PS-H07 and PS-H16,
§14.3). Their values stay those of the owning JS seal: they are never recomputed.

- Location: `tests/profile_cn/expected/vendor/js/` mirrors the JS expectations root of
  the JS lot-3 seal `7bd2d206277c123ad027481a42969f013cd91ddc4a2bfaab0e529fbc7120cb3c`
  (commit `1aa0d6f5894ea964e93b4e5842ad0378cc2b2419`): `cases/<caseId>.json` (the raw
  corpus/1 case files), `index.json` (the JS case index: clause, citations and
  discrimination text) and `profile/` (the neutral-cn profile, its `stale`,
  `conflict` and `coalesce` variants and their descriptor and base packages). The
  lot-0 schema and assets they load with are the identical
  `contracts/profile-mechanism/1/` files.
- Pins: `derive_helper.py` carries the `VENDORED` table (relative path → the raw
  SHA-256 the JS seal records), checks every file and returns its bytes unchanged from
  `build()`; `MANIFEST.sha256` lists them.
- Decisions on imported values are carried by the JS seal itself (one source of
  truth: every vendored file is byte-identical to the JS seal head, no overlay). Two
  cases carry a section-1 decision of the parity sync: `l3-imp-projection-out-of-base`
  (PS-21: `revision` and `report.outputRevision` equal the `baseRevision`) and
  `l3-imp-remap-qname` (PS-32: the observed entry's source and result pointers end in
  `/calledElement`).
- Harness record `expected/<caseId>.json`, generated by the helper from the vendored
  file: `case` (the JS case id), `clause` (`DESIGN R3.3` plus the JS index clause
  section and line range), `author: "spec-seal"`, `operation` (`validate`,
  `stable-id/1`, `complete`, `normalize`, `remap_ids`, `import_projection`, or
  `normalize_transport` for the cross-runtime cases), `profile` (`{vendored, sha256,
  descriptorBytes, baseBytes}` with repository-relative paths, or null), `derivation`
  (the vendored statement with the JS seal digest, the case file digest, the import row,
  any decision applied and the JS discrimination text), `input` (one key per JS input
  artifact: the JSON value, or `{text, sha256}` for a text artifact; the role
  `transport-route` becomes `transportRoute`, the command artifact `command`),
  `expected` (the JS `result` artifact; the `ids` list for `stable-id/1`; `{transport,
  transportBytes, hopResults}` for `normalize_transport`) and `fixedPoint: true` on
  complete/normalize successes (DESIGN §7.3).
- The JS `caller-state` artifact is the caller-visible input after the call; the
  helper checks it equals the input artifacts, so the runner's unchanged-input
  assertion (§9) compares it.
- Aliases (PS-37): `l3-n-place-neutral` ≡ `cn-n-place-neutral` and
  `l3-n-place-grid-shared-anchor` ≡ `cn-n-place-grid-shared-anchor` (same profile
  bytes, input and result); no copy, one `aliases` row each (§9.1).

## 10. Errata against MECH §6

| Id | Erratum | Justification |
| --- | --- | --- |
| E1 | `complete`, `normalize`, `bind_supports`, `remap_ids` take keyword-only `activation="edit"`; positional DESIGN signatures unchanged. Shared JS/Python contract (H H1) | DESIGN §7.2/§13: gated mutations disabled, neutral qualification allowed; the safe default never activates a gated mutation |
| E2 | `complete` `mode` is the closed set `extraction`/`retained` (H B7) | DESIGN §7.1 "extraction or admitted retained native content with distinct actor schemas" |
| E3 | `apply_plan` returns the staged result inside ChangeReport/1 and never mutates its arguments | house immutability rule; DESIGN defines no ChangeReport shape (H B13 adopts these shapes for both runtimes) |
| E4 | `plan_recipe` takes the compiled recipe record and a context from `create_read_context` | DESIGN `ReadContext` must carry identity, descriptor index and source coordinates (§2.5), which Block A's `ReadContext` lacks |
| E5 | `normalize` `payload.report` equals `result.report` (H B5) | DESIGN §2.5 payload `{envelope, placements, report}` plus §10.1 `report` |
| E6 | `propose_support_bindings`, `bind_supports`, `remap_ids`, `import_projection`, `sort_placements`, `GATES`, `Authority`, `create_read_context` have no DESIGN ABI name (shared names H A4) | adapters required by DESIGN §5.2, §5.3, §7.2, §13 (as MECH did for `check_compatibility`) |
| E7 | WritePlan/1 carries the descriptive facts (`cardinality`, `targetTypes`) instead of an extra `apply_plan` argument | DESIGN §2.5 fixes `applyPlan(plan, stagedTree, stagedEnvelope)` with identical Python input fields; DESIGN §2.4 validation before assignment needs the facts (§3.2) |
| E8 | `remap_ids` takes the archived `imported_di` and the approved migration `command` and returns `{envelope, importedDi}` (H B14, H9) | DESIGN §5.2 "approved import migration", DI `bpmnElement` rewrite, reference-free attestation |

## 11. Case table

| Case | Operation / profile | DESIGN clause | Witness | Expected |
| --- | --- | --- | --- | --- |
| `cn-c-identity-neutral` | complete / neutral | §3.2 ID allocation; §7.1 Completion C (Identity/defaults, Process) | C identity allocation and isExecutable=false on the neutral profile. | ok, 7 entries, fixed point |
| `cn-c-identity-grid` | complete / grid | §3.2 ID allocation; §7.1 Completion C (Identity/defaults, Process) | C identity allocation and isExecutable=true on the grid profile. | ok, 7 entries, fixed point |
| `cn-c-is-executable-neutral` | complete / neutral | §7.1 Completion C (Process); §14.4 | Neutral profile writes isExecutable=false, including on empty Processes. | ok, 2 entries, fixed point |
| `cn-c-is-executable-grid` | complete / grid | §7.1 Completion C (Process); §14.4 | Grid profile writes isExecutable=true, including on empty Processes. | ok, 2 entries, fixed point |
| `cn-c-version-mismatch-first` | complete / neutral | §7.1 Identity/defaults (reject source version mismatch first); §3.3 P1 | An older document minor refuses before any C identity allocation. | refused `profile-source-unavailable` |
| `cn-c-digest-mismatch-first` | complete / grid | §7.1 Identity/defaults; §3.3 same-version digest row | Same id and version with unequal known digests refuses before C. | refused `profile-digest-mismatch` |
| `cn-c-document-version` | complete / neutral | §3.3 row 1; §5.1; §10.1 missing identity omitted | An unknown envelope documentVersion refuses before C (no echoed identity). | refused `document-version-unsupported` |
| `cn-c-gateway-direction` | complete / cn-c | §7.1 Completion C (Topology); §2.2 ids; §2.4 assignRef | GatewayDirection four cases plus derived incoming/outgoing arrays. | ok, 18 entries, fixed point |
| `cn-c-gateway-direction-control` | complete / neutral | §7.1 (private policy, not a universal library rule); §14.4 | The plain neutral profile has no topology policy: gateways stay untouched. | ok, 1 entry, fixed point |
| `cn-c-topology-per-container` | complete / cn-c | §7.1 Completion C (Topology); §2.2 ids; §2.4 assignRef | Per-container incoming/outgoing; the cross-container flow is never retargeted. | ok, 12 entries, fixed point |
| `cn-c-backing-object` | complete / cn-c | §7.1 Completion C (Internal item); §2.4 create, assignRef | Missing backing DataObjects are created; valid backing and stores untouched. | ok, 4 entries, fixed point |
| `cn-c-input-port` | complete / cn-c | §7.1 Completion C (Ports); §13 OPEN-IO; §16 item 8 | Valid ports preserved; the missing input port is keyed by its association. | ok, 4 entries, fixed point |
| `cn-c-output-port-gated` | complete / cn-c | §7.1 Completion C (Ports); §13 OPEN-IO; §16 item 8 | The missing-output-source producer exception refuses profile-open in edit. | refused `profile-open` |
| `cn-c-output-port-qualification` | complete / cn-c | §7.1 Completion C (Ports); §13 OPEN-IO; §16 item 8 | Neutral qualification exercises the gated output port creation. | ok, 4 entries, fixed point |
| `cn-c-io-default-sets` | complete / cn-c | §7.1 Completion C (Sets); §16 item 8 | No sets: deterministic default InputSet/OutputSet for declared Process IO. | ok, 6 entries, fixed point |
| `cn-c-io-sets-preserved` | complete / cn-c | §7.1 Completion C (Sets); §16 item 8 | Existing sets keep every membership; nothing to complete. | ok, 0 entries, fixed point |
| `cn-c-io-set-selection-required` | complete / cn-c | §7.1 Completion C (Sets); §16 item 8 | New uncovered input with several sets refuses io-set-selection-required. | refused `io-set-selection-required` |
| `cn-c-documentation-preserved` | complete / neutral | §7.1 Completion C (Content); §3.2 identity mode containment | Documentation text and textFormat are preserved; no parsing, no ids. | ok, 1 entry, fixed point |
| `cn-c-unicode-names` | complete / neutral | §3.2 contentSignature; §14.3 Unicode U+E000/U+10000 and whitespace | Private-use, astral, whitespace, case and NFC-pair names give distinct deterministic ids. | ok, 8 entries, fixed point |
| `cn-c-timer-siblings` | complete / cn-c | §3.2 duplicateOrdinal; §14.3 ID collisions/reorders/timers | Identical ID-less timer starts get ordinals 0 and 1; nested ids follow. | ok, 8 entries, fixed point |
| `cn-c-timer-siblings-reordered` | complete / cn-c | §3.2 (later reorders never reallocate IDs) | Reordering identified siblings never reallocates their ids. | ok, 0 entries, fixed point |
| `cn-c-id-collision` | complete / neutral | §3.2 (computed collision is id-collision); §7.3 rollback | A computed id equal to a different existing element refuses id-collision. | refused `id-collision` |
| `cn-c-duplicate-source-ids` | complete / neutral | §3.2 (duplicate source IDs refuse); §10.2 duplicate-id -> id-collision | Duplicate existing ids refuse before any C write. | refused `id-collision` |
| `cn-c-not-fixed` | complete / cn-c-unfixed | §2.4 bounded second evaluation; §7.3 rollback on non-fixed point | A self-feeding completion recipe fails the bounded fixed point. | refused `normalization-not-fixed` |
| `cn-c-extraction-authorized` | complete / grid-extraction | §7.1 (extraction actor schema); §2.4.1 actor matrix | Extraction mode admits only AI-produced fields, then C identifies them. | ok, 4 entries, fixed point |
| `cn-c-extraction-unauthorized` | complete / neutral | §7.1 (extraction actor schema); §2.4.1 CR-06 profile-producer | Extraction mode refuses fields not produced by the ai actor. | refused `profile-producer` |
| `cn-c-descriptor-role-unknown` | complete / neutral | §3.1 (unclassified foreign property); §2.5 execution order | An unclassified property refuses descriptor-role-unknown. | refused `descriptor-role-unknown` |
| `cn-c-invalid-mode` | complete / neutral | §2.5 complete(compiled, envelope, mode); §10.1 refusal record; spec §3.4 | A mode outside the closed set is an invalid invocation. | refused `operation-error` |
| `cn-c-second-pass-refused` | complete / cn-c-second-pass | §2.4 bounded second evaluation (failure is normalization-not-fixed); §7.3 rollback | A refusal during the bounded second evaluation fails the C fixed point. | refused `normalization-not-fixed` |
| `cn-c-dangling-call` | complete / cn-c | §2.2 (dangling references before evaluation); §4.1; §5.2 | A nonempty unresolved calledElement refuses reference-dangling before C. | refused `reference-dangling` |
| `cn-c-wrong-type-reference` | complete / cn-c | §2.2 (dangling or wrong-type references before evaluation) | A reference to an element of a non-admitted type refuses reference-dangling. | refused `reference-dangling` |
| `cn-c-empty-called-element` | complete / cn-c | §4.1 (empty calledElement rows); §2.2 | An empty calledElement is a classification state, not a dangling reference. | ok, 0 entries, fixed point |
| `cn-c-uncompiled-context` | complete / neutral | §2.5 ReadContext (descriptor/effective-base index); §8.1 descriptor-mismatch | C/N need a profile compiled with its descriptor context and effective base. | refused `descriptor-mismatch` |
| `cn-n-support-one-process` | normalize / support | §7.2 Structure; §7.3 neutral-support-fixture.R31.json; §3.2 multi-Process support domain witness; §5.2 | All five ensure actions plus processRef for one Process (R3.1 fixture). | ok, 6 entries, fixed point |
| `cn-n-support-two-processes` | normalize / support | §7.2 Structure; §7.3 neutral-support-fixture.R31.json; §3.2 multi-Process support domain witness; §5.2 | Two Process domains get separate Collaborations (R3.1 fixture). | ok, 12 entries, fixed point |
| `cn-n-support-imported-ids` | normalize / support | §7.2 Structure; §7.3 neutral-support-fixture.R31.json; §3.2 multi-Process support domain witness; §5.2; §5.2 imported ID reuse | Imported non-generated support ids survive (qualification). | ok, 0 entries, fixed point |
| `cn-n-support-imported-ids-edit` | normalize / support | §7.2 Structure; §7.3 neutral-support-fixture.R31.json; §3.2 multi-Process support domain witness; §5.2; §5.2 imported ID reuse | Imported supports survive in edit activation too (reuse is not gated). | ok, 0 entries, fixed point |
| `cn-n-support-creation-gated` | normalize / support | §7.2 OPEN-RESERVED-N; §13; §16 item 11 | Support creation refuses profile-open while OPEN-RESERVED-N is open. | refused `profile-open` |
| `cn-n-support-late-band-collision` | normalize / support | §7.2 Structure; §7.3 neutral-support-fixture.R31.json; §3.2 multi-Process support domain witness; §5.2; §7.3 rollback | Late band id collision rolls back four earlier supports. | refused `id-collision` |
| `cn-n-support-duplicate-role` | normalize / support | §7.2 Structure; §7.3 neutral-support-fixture.R31.json; §3.2 multi-Process support domain witness; §5.2; §7.3 rollback | A duplicated owner+role binding refuses at envelope integrity. | refused `support-binding-conflict` |
| `cn-n-support-wrong-parent` | normalize / support | §7.2 Structure; §7.3 neutral-support-fixture.R31.json; §3.2 multi-Process support domain witness; §5.2; §7.3 rollback | An imported band under the wrong parent refuses support-binding-conflict. | refused `support-binding-conflict` |
| `cn-n-support-band-process-ref` | normalize / support | §7.2 Structure; §7.3 neutral-support-fixture.R31.json; §3.2 multi-Process support domain witness; §5.2; §7.3 rollback | A reference band carrying processRef refuses support-binding-conflict. | refused `support-binding-conflict` |
| `cn-n-support-refusal-after-five-ensures` | normalize / support-abort | §7.3 (explicit refusal after five ensures); §2.4 refuse | An explicit refuse step after five ensures aborts atomically. | refused `fixture-abort` |
| `cn-n-support-late-band-collision-edit` | normalize / support | §7.2 OPEN-RESERVED-N; §13; §16 item 11 | In edit activation the gate refuses before the late collision is reached. | refused `profile-open` |
| `cn-n-place-neutral` | normalize / neutral | §7.2 derived placements; §2.4.1 shared anchoring; §4.4 anchors | Neutral placements: content region, no anchor, no related associations. | ok, 0 entries, fixed point |
| `cn-n-place-grid-shared-anchor` | normalize / grid | §7.2 derived placements; §2.4.1 shared anchoring; §4.4 anchors | Grid placements: every related association, minimum eligible anchor. | ok, 0 entries, fixed point |
| `cn-n-place-grid-inserted-association` | normalize / grid | §7.2 derived placements; §2.4.1 shared anchoring; §4.4 anchors; §7.3 inserted/deleted associations | An inserted lower-id association becomes the anchor; all links retained. | ok, 0 entries, fixed point |
| `cn-n-place-grid-deleted-association` | normalize / grid | §7.2 derived placements; §2.4.1 shared anchoring; §4.4 anchors; §7.3 inserted/deleted associations | Deleting the only consuming association falls back to producing ones. | ok, 0 entries, fixed point |
| `cn-n-placement-intent-di-only` | normalize / neutral | §8.2 step 3 (placement intent, DI-only moves); §3.1 | A DI-only placement intent changes neither semantics nor placements. | ok, 0 entries, fixed point |
| `cn-n-placement-intent-unknown` | normalize / neutral | §8.2 step 3; spec §3.5 placement intent | A placement intent naming no element refuses reference-dangling. | refused `reference-dangling` |
| `cn-sort-placements` | sort_placements / - | §7.2 placement sort order; §3.1 UTF-16 ordering | Total placement order: UTF-16 tuple, absent anchor first, arrays lexicographic. | exact value |
| `cn-n-reference-region-multi-process` | normalize / cn-n | §7.2 Reference region, Relation direction, Structure; §4.4 sharing; §7.3 multi-process/shared references | Shared store, one reference per Process, supports created, link reversed. | ok, 11 entries, fixed point |
| `cn-n-reference-region-edit` | normalize / cn-n | §7.2 OPEN-RESERVED-N; §13; §16 item 11 | The same input refuses profile-open in edit (band creation needed). | refused `profile-open` |
| `cn-n-interface-region` | normalize / cn-n | §7.2 Interface region, Structure; §9.4 (IO never in Lane.flowNodeRef) | Process IO is placed in the interface region without lane membership. | ok, 5 entries, fixed point |
| `cn-n-relation-direction-reversal` | normalize / cn-n | §7.2 Relation direction; §10.1 N direction reversal coordinates | Unambiguous reversal with every support already bound (edit activation). | ok, 3 entries, fixed point |
| `cn-n-relation-direction-conflict` | normalize / cn-n-conflict | §7.2 Relation direction (conflicting pairs refuse); §2.4 write conflicts | Two recipes planning different directions refuse profile-write-conflict. | refused `profile-write-conflict` |
| `cn-n-external-membership-append` | normalize / cn-n | §7.2 External membership; §4.1 external/internal/incomplete calls; §4.4; §13 OPEN-EXTERNAL, OPEN-SHARING; §16 items 2, 4; §7.3 external/internal/incomplete calls, role reorder/rename | Qualification appends the marked call to the bound external lane. | ok, 1 entry, fixed point |
| `cn-n-role-rename-business-lane` | normalize / cn-n | §7.2 External membership; §4.1 external/internal/incomplete calls; §4.4; §13 OPEN-EXTERNAL, OPEN-SHARING; §16 items 2, 4; §7.3 external/internal/incomplete calls, role reorder/rename | Renaming a business lane changes nothing but its own name. | ok, 1 entry, fixed point |
| `cn-n-external-membership-edit` | normalize / cn-n | §7.2 External membership; §4.1 external/internal/incomplete calls; §4.4; §13 OPEN-EXTERNAL, OPEN-SHARING; §16 items 2, 4 | Lane membership changes refuse profile-open in edit activation. | refused `profile-open` |
| `cn-n-external-membership-remove-refused` | normalize / cn-n-relocate | §7.2 External membership; §4.1 external/internal/incomplete calls; §4.4; §13 OPEN-EXTERNAL, OPEN-SHARING; §16 items 2, 4; §7.3 preserved original memberships | Removing an existing membership refuses responsibility-preservation-required. | refused `responsibility-preservation-required` |
| `cn-n-reserved-lane-renamed` | normalize / cn-n | §5.2 support validation; §2.4 ensure; §7.3 role rename | A renamed bound reserved lane is reused unchanged (fields are creation fields). | ok, 0 entries, fixed point |
| `cn-n-black-box-pool-retained` | normalize / cn-n | §5.2 (ordinary pool never taken over); §13 OPEN-MACHINE; §16 item 6 | An unbound pool labelled like a support stays an ordinary pool. | ok, 4 entries, fixed point |
| `cn-n-ensure-conflicting-definition` | normalize / cn-n-ensure-conflict | §2.4 (conflicting ensure definitions refuse); §7.2 Structure | Two different ensure plans for one owner+role refuse profile-write-conflict. | refused `profile-write-conflict` |
| `cn-n-not-fixed` | normalize / cn-n-unfixed | §2.4 bounded second evaluation; §7.3 rollback on non-fixed point | A self-feeding normalize recipe fails the bounded fixed point. | refused `normalization-not-fixed` |
| `cn-n-second-pass-refused` | normalize / cn-n-second-pass | §2.4 bounded second evaluation (failure is normalization-not-fixed); §7.3 rollback | A refusal during the bounded second evaluation fails the N fixed point. | refused `normalization-not-fixed` |
| `cn-n-dangling-reference` | normalize / cn-n | §2.2 (dangling references before evaluation); §7.3 rollback | N refuses a dangling native reference at the graph index. | refused `reference-dangling` |
| `cn-n-compat-before-integrity` | normalize / support | §2.5 execution order (compatibility first); §3.3 P1; §5.1 | §3.3 compatibility is decided before envelope integrity (bindings). | refused `profile-source-unavailable` |
| `cn-plan-create-task-neutral` | plan_recipe+apply_plan / neutral | §2.4 action grammar; §2.4.1 action/write matrix; §2.5 planRecipe/applyPlan; §3.2 allocated create | Allocated create of a bpmn:Task (neutral). | plan ok; apply ok |
| `cn-plan-create-task-grid` | plan_recipe+apply_plan / grid | §2.4 action grammar; §2.4.1 action/write matrix; §2.5 planRecipe/applyPlan; §3.2 allocated create | Allocated create of a bpmn:ServiceTask (grid). | plan ok; apply ok |
| `cn-plan-add-note-containment` | plan_recipe+apply_plan / neutral | §2.4 action grammar; §2.4.1 action/write matrix; §2.5 planRecipe/applyPlan; §3.2 identity mode containment | Containment identity: Documentation is created without any id. | plan ok; apply ok |
| `cn-plan-create-aid-neutral` | plan_recipe+apply_plan / neutral | §2.4 action grammar; §2.4.1 action/write matrix; §2.5 planRecipe/applyPlan; §3.2 pinned fixture vector | create-aid with the neutral marker literal. | plan ok; apply ok |
| `cn-plan-create-aid-grid` | plan_recipe+apply_plan / grid | §2.4 action grammar; §2.4.1 action/write matrix; §2.5 planRecipe/applyPlan; §3.2 pinned fixture vector | create-aid with the grid marker literal. | plan ok; apply ok |
| `cn-plan-link` | plan_recipe+apply_plan / neutral | §2.4 action grammar; §2.4.1 action/write matrix; §2.5 planRecipe/applyPlan; §2.4 assignRef | create plus two assignRef writes on the created handle. | plan ok; apply ok |
| `cn-plan-scalar-write-conflict` | plan_recipe+apply_plan / cn-n | §2.4 action grammar; §2.4.1 action/write matrix; §2.5 planRecipe/applyPlan; §2.4 write conflicts | Two different scalar values for one target/path refuse at apply. | plan ok; apply `profile-write-conflict` |
| `cn-plan-append-remove-conflict` | plan_recipe+apply_plan / cn-n | §2.4 action grammar; §2.4.1 action/write matrix; §2.5 planRecipe/applyPlan; §2.4 appendUnique/remove coalescing | Appending and removing the same id on one reference array conflicts. | plan ok; apply `profile-write-conflict` |
| `cn-plan-missing-parameter` | plan_recipe+apply_plan / neutral | §2.4 action grammar; §2.4.1 action/write matrix; §2.5 planRecipe/applyPlan; §8.3 parameter binding | A missing required parameter refuses planning. | plan `profile-ui-parameters` |
| `cn-plan-unknown-element-parameter` | plan_recipe+apply_plan / neutral | §2.4 action grammar; §2.4.1 action/write matrix; §2.5 planRecipe/applyPlan; §2.2 param (element parameters bind an existing element) | An element parameter naming no element refuses reference-dangling. | plan `reference-dangling` |
| `cn-apply-stale-plan` | apply_plan / neutral | §2.5 applyPlan; §8.2 step 1 (stale revision refused before staging) | Applying a plan to a staged envelope of another revision refuses. | apply `operation-error` |
| `cn-plan-ambiguous-binding` | plan_recipe+apply_plan / cn-n | §2.4 action grammar; §2.4.1 action/write matrix; §2.5 planRecipe/applyPlan; §2.4 bind cardinality | bind(one) over two candidates refuses profile-ambiguous-binding. | plan `profile-ambiguous-binding` |
| `cn-plan-remove-referenced` | plan_recipe+apply_plan / cn-n | §2.4 action grammar; §2.4.1 action/write matrix; §2.5 planRecipe/applyPlan; §2.4 remove dependency closure | Removing an element with a retained inbound reference refuses. | plan `reference-dangling` |
| `cn-n-empty-support-survives` | normalize / cn-n | §7.2 support deletion/recreation/remap; §7.3 deletion/recreation (empty supports survive) | A bound empty external lane survives N while nothing needs it. | ok, 0 entries, fixed point |
| `cn-plan-remove-empty-support` | plan_recipe+apply_plan / cn-n | §7.2 support deletion/recreation/remap; §7.3 deletion/recreation; §2.4 remove | Explicit dependency-checked deletion of the empty support and its binding. | plan ok; apply ok |
| `cn-plan-remove-without-intent` | plan_recipe+apply_plan / cn-n | §2.4 remove (explicit deletion intent required) | Deletion without explicit intent refuses profile-producer. | plan `profile-producer` |
| `cn-n-deleted-support-stays-absent` | normalize / cn-n | §7.2 support deletion/recreation/remap; §7.3 deletion/recreation (deleted support stays absent) | A deleted empty support stays absent while no element needs its role. | ok, 0 entries, fixed point |
| `cn-remap-owner` | remap_ids / cn-n | §5.2 ID remapping (separate approved import migration); §13 OPEN-ID; §7.2 surviving support IDs unchanged through owner remaps | Owner remap: references, bindings and DI follow, support ids survive. | ok, 0 entries |
| `cn-remap-gated` | remap_ids / cn-n | §5.2 ID remapping (separate approved import migration); §13 OPEN-ID | ID remap refuses profile-open in edit activation. | refused `profile-open` |
| `cn-remap-not-approved` | remap_ids / cn-n | §5.2 ID remapping (separate approved import migration); §13 OPEN-ID; §16 item 1 (approved migration) | A remap command without approval is an invalid invocation. | refused `operation-error` |
| `cn-plan-create-process-input` | plan_recipe+apply_plan / cn-n | §2.4 action grammar; §2.4.1 action/write matrix; §2.5 planRecipe/applyPlan; §3.2 (ownerId explicit, including under an ID-less ioSpecification) | Containment ioSpecification plus allocated DataInput under explicit owner. | plan ok; apply ok |
| `cn-n-recreate-after-remap` | normalize / cn-n | §7.2 support deletion/recreation/remap; §7.3 deletion/recreation (later need triggers ensure with the current ownerId) | A later need recreates the deleted support with the current ownerId. | ok, 1 entry, fixed point |
| `cn-n-recreate-after-remap-edit` | normalize / cn-n | §7.2 OPEN-RESERVED-N; §13; §16 item 11 | Recreation is a support creation: profile-open in edit activation. | refused `profile-open` |
| `cn-remap-internal-call-and-dangling` | remap_ids / cn-n | §5.2 ID remapping (separate approved import migration); §13 OPEN-ID; §7.3 ID remaps, native references | Internal calledElement follows the map; a dangling target stays and is reported. | ok, 1 entry |
| `cn-remap-swap` | remap_ids / cn-n | §5.2 ID remapping (separate approved import migration); §13 OPEN-ID (total map built before application) | A swap is one total map applied at once, never sequential renames. | ok, 1 entry |
| `cn-remap-collision` | remap_ids / cn-n | §5.2 ID remapping (separate approved import migration); §13 OPEN-ID | A result id equal to a retained id refuses id-collision. | refused `id-collision` |
| `cn-remap-unknown-source` | remap_ids / cn-n | §5.2 ID remapping (separate approved import migration); §13 OPEN-ID | A map key naming no element refuses reference-dangling. | refused `reference-dangling` |
| `cn-remap-opaque-property` | remap_ids / cn-n | §5.2 ID remapping (separate approved import migration); §13 OPEN-ID (migration-reference-opaque) | An unclassified property may hide references: migration-reference-opaque. | refused `migration-reference-opaque` |
| `cn-remap-opaque-attested` | remap_ids / cn-n | §5.2 ID remapping (separate approved import migration); §13 OPEN-ID (pinned reference-free attestation) | A pinned reference-free attestation lets remap keep an opaque member unchanged. | ok, 1 entry |
| `cn-remap-target-grammar` | remap_ids / cn-n | §5.2 ID remapping (separate approved import migration); §13 OPEN-ID; §3.2 authoring subset | A result id outside the authoring grammar refuses profile-schema. | refused `profile-schema` |
| `cn-plan-unset-name` | plan_recipe+apply_plan / cn-n | §2.4 action grammar; §2.4.1 action/write matrix; §2.5 planRecipe/applyPlan; §2.4 set/unset | An authorized unset removes one declared scalar field. | plan ok; apply ok |
| `cn-plan-wrong-parameter-type` | plan_recipe+apply_plan / neutral | §2.4 action grammar; §2.4.1 action/write matrix; §2.5 planRecipe/applyPlan; §8.3 typed parameters (no coercion) | A parameter of the wrong JSON type refuses profile-type. | plan `profile-type` |
| `cn-plan-recipe-not-compiled` | plan_recipe+apply_plan / neutral | §2.4 action grammar; §2.4.1 action/write matrix; §2.5 planRecipe/applyPlan; §2.4.1 CR-05 symbols | A recipe record that is not the compiled one refuses profile-symbol. | plan `profile-symbol` |
| `cn-plan-export-phase` | plan_recipe+apply_plan / neutral | §2.4 action grammar; §2.4.1 action/write matrix; §2.5 planRecipe/applyPlan; §2.4.1 CR-14 action phases | An export recipe cannot be planned as a semantic write plan. | plan `profile-action-phase` |
| `cn-plan-actor-mismatch` | plan_recipe+apply_plan / neutral | §2.4 action grammar; §2.4.1 action/write matrix; §2.5 planRecipe/applyPlan; §2.4.1 bounded authority witness | An explicit create recipe planned by the code actor refuses profile-producer. | plan `profile-producer` |
| `cn-plan-undeclared-parameter` | plan_recipe+apply_plan / neutral | §2.4 action grammar; §2.4.1 action/write matrix; §2.5 planRecipe/applyPlan; §8.3 parameter binding | A supplied parameter the recipe does not declare refuses profile-ui-parameters. | plan `profile-ui-parameters` |
| `cn-plan-invalid-authority` | plan_recipe+apply_plan / neutral | §2.4 action grammar; §2.4.1 action/write matrix; §2.5 planRecipe/applyPlan; spec §3.1 Authority | An Authority outside its closed record refuses operation-error. | plan `operation-error` |
| `cn-plan-optional-binding-missing` | plan_recipe+apply_plan / cn-n | §2.4 action grammar; §2.4.1 action/write matrix; §2.5 planRecipe/applyPlan; §2.2 required use of MISSING; §2.4 bind zeroOrOne | A required use of a MISSING binding refuses profile-type. | plan `profile-type` |
| `cn-plan-link-wrong-target-type` | plan_recipe+apply_plan / neutral | §2.4 action grammar; §2.4.1 action/write matrix; §2.5 planRecipe/applyPlan; §2.4 assignRef (target type validated before assignment) | apply_plan checks the carried target types of a reference write. | plan ok; apply `profile-type` |
| `cn-plan-create-id-collision` | plan_recipe+apply_plan / neutral | §2.4 action grammar; §2.4.1 action/write matrix; §2.5 planRecipe/applyPlan; §3.2 computed collision | A planned allocated id already carried by another element refuses id-collision. | plan ok; apply `id-collision` |
| `cn-apply-input-conflict` | apply_plan / neutral | §2.5 applyPlan(plan, stagedTree, stagedEnvelope); §8.1 input-conflict | A staged tree that is not the staged envelope tree refuses input-conflict. | apply `input-conflict` |
| `cn-plan-lane-member-cn` | plan_recipe+apply_plan / cn-n | §2.4 action grammar; §2.4.1 action/write matrix; §2.5 planRecipe/applyPlan; §2.5 ReadContext descriptor index; §2.4 assignRef cardinality | Descriptive context 1: a multi-valued Lane.flowNodeRef (cn slice). | plan ok; apply ok |
| `cn-plan-lane-member-support` | plan_recipe+apply_plan / support-cmd | §2.4 action grammar; §2.4.1 action/write matrix; §2.5 planRecipe/applyPlan; §2.5 ReadContext descriptor index; §2.4 assignRef cardinality | Descriptive context 2: a single-valued Lane.flowNodeRef (support slice). | plan ok; apply ok |
| `cn-plan-reparent-annotation` | plan_recipe+apply_plan / cn-n | §2.4 action grammar; §2.4.1 action/write matrix; §2.5 planRecipe/applyPlan; §2.4 reparent | An explicit reparent keeps the id and moves the element to the last position. | plan ok; apply ok |
| `cn-propose-recovery-with-provenance` | propose_support_bindings / support | §5.2 support import rules; §13 OPEN-MACHINE; §16 item 6 (recovery proposal) | Exact allocator id + type/parent/fields + provenance: binding proposed. | ok |
| `cn-propose-recovery-without-provenance` | propose_support_bindings / support | §5.2 support import rules; §13 OPEN-MACHINE; §16 item 6 (recovery proposal) | A hash-shaped id alone never authorizes reuse. | ok |
| `cn-propose-recovery-partial-provenance` | propose_support_bindings / support | §5.2 support import rules; §13 OPEN-MACHINE; §16 item 6 (recovery proposal) | Only provenance-listed supports are proposed. | ok |
| `cn-n-recovery-missing-binding-collides` | normalize / support | §5.2 support import rules; §13 OPEN-MACHINE; §16 item 6; §3.2 id-collision | Without bindings, N does not adopt generated-looking supports: id-collision. | refused `id-collision` |
| `cn-propose-black-box-pool` | propose_support_bindings / cn-n | §5.2 support import rules; §13 OPEN-MACHINE; §16 item 6 (ordinary pool never taken over) | A labelled ordinary pool is never proposed. | ok |
| `cn-bind-supports-explicit-selection` | bind_supports / cn-n | §5.2 support import rules; §13 OPEN-MACHINE; §16 item 6 (supply/review support bindings) | An explicit support selection binds an imported Collaboration. | ok, 0 entries |
| `cn-n-after-explicit-selection` | normalize / cn-n | §5.2 support import rules; §13 OPEN-MACHINE; §16 item 6; §7.2 Structure | N reuses the selected Collaboration and keeps the ordinary pool. | ok, 3 entries, fixed point |
| `cn-bind-supports-gated` | bind_supports / cn-n | §5.2 support import rules; §13 OPEN-MACHINE; §16 item 6 | Support binding activation refuses profile-open in edit. | refused `profile-open` |
| `cn-bind-supports-conflict` | bind_supports / cn-n | §5.2 support import rules; §13 OPEN-MACHINE; §16 item 6; §5.1 owner+role unique | Binding an already bound owner+role refuses support-binding-conflict. | refused `support-binding-conflict` |
| `cn-compile-support-profile` | compile_profile / support | §2.4.1 CR-05/CR-06/CR-07 for ensure; §7.3 (fixture compiles) | The R3.1 support recipe compiles (ensure aliases, writes, authority). | ok (payload UNSEALED), compiled identity |
| `cn-compile-ensure-non-support-type` | compile_profile / support-task-ensure | §2.4 ensure restriction; §2.4.1 CR-06 | ensure of a non-support native type refuses profile-producer. | refused `profile-producer` |
| `cn-compile-port-without-authority` | compile_profile / cn-c-noauth | §7.1 Completion C (Ports); §13 OPEN-IO; §16 item 8; §2.4.1 CR-06 | Port creation without explicit code authority refuses profile-producer. | refused `profile-producer` |
| `cn-compile-ensure-missing-binding-write` | compile_profile / support-no-binding-write | §2.4.1 CR-06 write set; action/write matrix (ensure) | An ensure recipe must declare its envelope binding write. | refused `profile-write-set` |
| `cn-compile-create-identity-mismatch` | compile_profile / neutral-containment-task | §2.4 create identity; §2.4.1 CR-07 | Containment identity on an ID-bearing type refuses profile-create-identity. | refused `profile-create-identity` |
| `cn-compile-variants` | compile_profile / - | §2.4.1 compiler rejection mapping; §3.1 profile digest; §5.1 identity | Every success-path variant compiles to its listed identity. | ok per variant (payload UNSEALED), compiled identities |
| `cn-gates-table` | gates / - | §13 OPEN register; §16 owner decisions; §7.2 | The read-only lot-3 gate table. | exact value |

The table is generated from the sealed files (clause) and the helper docstrings (witness).

### 11.1 DESIGN §7.3 witness list

| Witness | Cases |
| --- | --- |
| external / internal / incomplete calls | `cn-n-external-membership-append` (Call_ext relocated; Call_int and Call_inc untouched), `-edit`, `-remove-refused`; `cn-c-dangling-call`, `cn-c-empty-called-element` (call targets at the graph index) |
| native references | `cn-remap-internal-call-and-dangling`, `cn-c-backing-object`, `cn-n-relation-direction-reversal`, `cn-c-wrong-type-reference`, `cn-n-dangling-reference` |
| supports imported with non-generated IDs | `cn-n-support-imported-ids`, `-edit`, `cn-n-relation-direction-reversal`, `cn-n-external-membership-append`, `cn-n-reserved-lane-renamed` |
| ID remaps | `cn-remap-owner`, `cn-remap-internal-call-and-dangling`, `cn-remap-swap`, `cn-remap-opaque-attested` |
| deletion / recreation | `cn-plan-remove-empty-support`, `cn-n-deleted-support-stays-absent`, `cn-n-recreate-after-remap` |
| multi-process / shared references | `cn-n-reference-region-multi-process`, `cn-n-support-two-processes` |
| preserved original memberships | `cn-n-external-membership-remove-refused`, `cn-n-external-membership-append` |
| unchanged source text | `cn-c-documentation-preserved`, `cn-c-unicode-names` |
| role reorder / rename | `cn-n-external-membership-append` (lane and member order), `cn-n-role-rename-business-lane`, `cn-n-reserved-lane-renamed` (renamed bound support reused unchanged, H C5) |
| inserted / deleted associations | `cn-n-place-grid-inserted-association`, `cn-n-place-grid-deleted-association` |
| timer siblings | `cn-c-timer-siblings`, `cn-c-timer-siblings-reordered` |
| rollback | `cn-c-not-fixed`, `cn-n-not-fixed`, `cn-c-second-pass-refused`, `cn-n-second-pass-refused`, `cn-c-id-collision`, the five support negatives, `cn-n-compat-before-integrity` |
| undo | not covered (§12) |

### 11.2 DESIGN §2.4–§2.4.1 action and refusal matrix (review finding)

Actions (DESIGN §2.4 table):

| Action | Sealed coverage | Status |
| --- | --- | --- |
| `bind` one / zeroOrOne / first with fallbacks | N and command recipes; `cn-plan-ambiguous-binding` (one), `cn-plan-optional-binding-missing` (zeroOrOne binds MISSING), grid placements (first + fallbacks) | covered |
| `create` allocated / containment | `cn-plan-create-task-*`, `cn-plan-create-aid-*`, `cn-plan-link`, `cn-plan-add-note-containment`, `cn-plan-create-process-input`, C backing objects, ports, sets | covered |
| `ensure` reuse / create / conflict | `cn-n-support-*`, `cn-n-*-region*`, `cn-n-ensure-conflicting-definition`, `cn-n-reserved-lane-renamed` | covered |
| `set` | C isExecutable, gateway direction, N association direction, `cn-plan-scalar-write-conflict` | covered |
| `unset` | `cn-plan-unset-name` (explicit edit) | covered (explicit command); no neutral C/N recipe unsets: `complete/unset`/`normalize/unset` entries not covered |
| `assignRef` replace / appendUnique / remove | C topology and ports, `cn-plan-link`, `cn-plan-lane-member-*`, `cn-n-external-membership-append`, `cn-plan-append-remove-conflict`, `cn-n-external-membership-remove-refused` | covered |
| `reparent` | `cn-plan-reparent-annotation` (explicit edit) | covered (explicit command); N reparent not covered (no approved structural support move, DESIGN §2.4.1) |
| `place` | `cn-n-place-*`, `cn-n-*-region*`, `cn-sort-placements` | covered |
| `emit`, `loss` | export actions planned by `map_export` | lot 4 (`cn-plan-export-phase` seals the refusal of planning them here) |
| `remove` refuseIfReferenced | `cn-plan-remove-empty-support`, `cn-plan-remove-referenced`, `cn-plan-remove-without-intent` | covered; `includeDeclared`, protected content and binding-owner removal partial (rules only, §12) |
| `refuse` | `cn-n-support-refusal-after-five-ensures`, `cn-c-io-set-selection-required`, second-pass refusals | covered |

Refusal codes named by §5 (first-pass sealed witness):

| Code | Cases |
| --- | --- |
| `operation-error` | `cn-c-invalid-mode`, `cn-plan-invalid-authority`, `cn-apply-stale-plan`, `cn-remap-not-approved` |
| `descriptor-mismatch` | `cn-c-uncompiled-context` (runtime-specific) |
| `document-version-unsupported` | `cn-c-document-version` |
| `profile-source-unavailable`, `profile-digest-mismatch` | `cn-c-version-mismatch-first`, `cn-n-compat-before-integrity`; `cn-c-digest-mismatch-first` |
| `support-binding-conflict` | `cn-n-support-duplicate-role`, `-wrong-parent`, `-band-process-ref`, `cn-bind-supports-conflict` |
| `id-collision` | `cn-c-duplicate-source-ids`, `cn-c-id-collision`, `cn-n-support-late-band-collision`, `cn-n-recovery-missing-binding-collides`, `cn-plan-create-id-collision`, `cn-remap-collision` |
| `descriptor-role-unknown` | `cn-c-descriptor-role-unknown` |
| `reference-dangling` | `cn-c-dangling-call`, `cn-c-wrong-type-reference`, `cn-n-dangling-reference`, `cn-n-placement-intent-unknown`, `cn-plan-unknown-element-parameter`, `cn-plan-remove-referenced`, `cn-remap-unknown-source` |
| `profile-producer` | `cn-c-extraction-unauthorized`, `cn-plan-actor-mismatch`, `cn-plan-remove-without-intent`, `cn-compile-ensure-non-support-type`, `cn-compile-port-without-authority` |
| `profile-symbol` | `cn-plan-recipe-not-compiled` |
| `profile-action-phase` | `cn-plan-export-phase` |
| `profile-ui-parameters` | `cn-plan-missing-parameter`, `cn-plan-undeclared-parameter` |
| `profile-type` | `cn-plan-wrong-parameter-type`, `cn-plan-optional-binding-missing`, `cn-plan-link-wrong-target-type` |
| `profile-ambiguous-binding` | `cn-plan-ambiguous-binding` |
| `profile-write-conflict` | `cn-plan-scalar-write-conflict`, `cn-plan-append-remove-conflict`, `cn-n-relation-direction-conflict`, `cn-n-ensure-conflicting-definition` |
| `input-conflict` | `cn-apply-input-conflict` |
| `profile-open` | `cn-c-output-port-gated`, `cn-n-support-creation-gated`, `-late-band-collision-edit`, `cn-n-reference-region-edit`, `cn-n-external-membership-edit`, `cn-n-recreate-after-remap-edit`, `cn-bind-supports-gated`, `cn-remap-gated` |
| `responsibility-preservation-required` | `cn-n-external-membership-remove-refused` |
| `io-set-selection-required` | `cn-c-io-set-selection-required` |
| `normalization-not-fixed` | `cn-c-not-fixed`, `cn-n-not-fixed`, `cn-c-second-pass-refused`, `cn-n-second-pass-refused` |
| `migration-reference-opaque` | `cn-remap-opaque-property` |
| `profile-schema` | `cn-remap-target-grammar`; envelope shape and revision errors partial (rule only) |
| profile `refuse` codes | `cn-n-support-refusal-after-five-ensures` (`fixture-abort`), `cn-c-io-set-selection-required` |
| `profile-write-set`, `profile-create-identity` | `cn-compile-ensure-missing-binding-write`, `cn-compile-create-identity-mismatch` |
| `snapshot-schema` (imported DI digest), `document-not-loaded` (projection parse) | partial (rules only, §12) |

### 11.3 Compile expectations (independence)

The six `cn-compile-*` expectations and the 19 identities of
`artifacts/profile-variants.json` are derived without any library run: each status
and code by the written CR-01…CR-14 review recorded in the case `derivation`, against
DESIGN §2.4/§2.4.1 and the DESIGN fixture checker's rule order; each identity as the
§5.1 record of the composed profile with `sha256 = H(profile)` computed by the
standalone helper and recomputed by an independent Node JCS/SHA-256 script. The first
seal's scratch probes (a patched copy of the Block A compiler and loader runs) are
discarded and are not evidence; their schema-validity check of the variants is an
input precondition only. The parity sync changed the wire shape only (PS-25, PS-35,
§9.1): every status, code and identity value is unchanged.

### 11.4 Vendored JS cases (parity sync, §9.2)

Values owned by the JS lot-3 seal (§9.2); the witness of each case is its JS
discrimination text, copied into the harness `derivation`. The clause is the JS index
clause. Generated from the harness records.

| Case | Import row | Operation / JS profile | DESIGN clause | Expected |
| --- | --- | --- | --- | --- |
| `l3-call-ambiguous` | PS-H01 | validate / neutral-cn | §4.1 L370 | ok, 1 entry |
| `l3-call-conflict` | PS-H01 | validate / neutral-cn | §4.1 L373 | ok, 1 entry |
| `l3-call-conflict-empty` | PS-H01 | validate / neutral-cn | §4.1 L373 | ok, 1 entry |
| `l3-call-duplicate` | PS-H01 | validate / neutral-cn | §4.1 L371 | ok, 1 entry |
| `l3-call-external-valid` | PS-H01 | validate / neutral-cn | §4.1 L374 | ok, 0 entries |
| `l3-call-internal` | PS-H01 | validate / neutral-cn | §4.1 L376 | ok, 0 entries |
| `l3-call-marker-invalid` | PS-H01 | validate / neutral-cn | §4.1 L372 | ok, 1 entry |
| `l3-call-source-doc-not-marker` | PS-H01 | validate / neutral-cn | §4.1 L366 | ok, 1 entry |
| `l3-call-target-dangling-accept` | PS-H01 | validate / neutral-cn | §4.1 L378 | ok, 1 entry |
| `l3-call-target-empty-accept` | PS-H01 | validate / neutral-cn | §4.1 L375 | ok, 1 entry |
| `l3-call-target-empty-draft` | PS-H01 | validate / neutral-cn | §4.1 L375 | ok, 1 entry |
| `l3-call-target-required-accept` | PS-H01 | validate / neutral-cn | §4.1 L379 | ok, 1 entry |
| `l3-call-target-required-draft` | PS-H01 | validate / neutral-cn | §4.1 L379 | ok, 1 entry |
| `l3-call-target-type` | PS-H01 | validate / neutral-cn | §4.1 L377 | ok, 1 entry |
| `l3-io-complete-links-accept` | PS-H01 | validate / neutral-cn | §4.3 L397-L400 | ok, 0 entries |
| `l3-io-endpoint-type-accept` | PS-H01 | validate / neutral-cn | §4.3 L401 | ok, 1 entry |
| `l3-io-link-owner-accept` | PS-H01 | validate / neutral-cn | §4.3 L401 | ok, 2 entries |
| `l3-io-link-owner-draft` | PS-H01 | validate / neutral-cn | §4.3 L401 | ok, 2 entries |
| `l3-io-missing-links-accept` | PS-H01 | validate / neutral-cn | §4.3 L397-L400 | ok, 4 entries |
| `l3-io-missing-links-draft` | PS-H01 | validate / neutral-cn | §4.3 L397-L400 | ok, 4 entries |
| `l3-io-wrong-direction-accept` | PS-H01 | validate / neutral-cn | §4.3 L401 | ok, 2 entries |
| `l3-io-wrong-direction-draft` | PS-H01 | validate / neutral-cn | §4.3 L401 | ok, 2 entries |
| `l3-path-cannot-reach-end-accept` | PS-H01 | validate / neutral-cn | §6.3 L501 | ok, 2 entries |
| `l3-path-cross-container-flow-accept` | PS-H01 | validate / neutral-cn | §4 L347 | ok, 4 entries |
| `l3-path-disconnected-task-accept` | PS-H01 | validate / neutral-cn | §6.3 L501 | ok, 4 entries |
| `l3-path-disconnected-task-draft` | PS-H01 | validate / neutral-cn | §6.3 L501 | ok, 4 entries |
| `l3-path-gateway-without-incoming-accept` | PS-H01 | validate / neutral-cn | §6.3 L501 | ok, 2 entries |
| `l3-path-incomplete-call-not-exempt-accept` | PS-H01 | validate / neutral-cn | §6.3 L501 | ok, 5 entries |
| `l3-path-unlinked-external-not-exempt-accept` | PS-H01 | validate / neutral-cn | §6.3 L501 | ok, 4 entries |
| `l3-path-unreachable-component-accept` | PS-H01 | validate / neutral-cn | §6.3 L501 | ok, 3 entries |
| `l3-trig-downstream-branch-accept` | PS-H01 | validate / neutral-cn | §4.2 L389 | ok, 0 entries |
| `l3-trig-no-branch-accept` | PS-H01 | validate / neutral-cn | §4.2 L389 | ok, 1 entry |
| `l3-trig-no-branch-draft` | PS-H01 | validate / neutral-cn | §4.2 L389 | ok, 1 entry |
| `l3-trig-parallel-only-accept` | PS-H01 | validate / neutral-cn | §4.2 L389 | ok, 1 entry |
| `l3-trig-single-trigger-accept` | PS-H01 | validate / neutral-cn | §4.2 L389 | ok, 0 entries |
| `l3-n-binding-wrong-type` | PS-H02 | normalize / neutral-cn | §5.2 L438-L440 | refused `support-binding-conflict` |
| `l3-n-empty-process` | PS-H02 | normalize / neutral-cn | §7.2 L558 | ok, 3 entries, fixed point |
| `l3-n-legacy-marker-ignored` | PS-H02 | normalize / neutral-cn | §4.1 L381-L383 | ok, 3 entries, fixed point |
| `l3-n-unicode-names` | PS-H02 | normalize / neutral-cn | §4.2 L387 | ok, 4 entries, fixed point |
| `l3-trig-normalize-no-invention` | PS-H02 | normalize / neutral-cn | §4.2 L389 | ok, 6 entries, fixed point |
| `l3-id-rename-stable` | PS-H03 | complete / neutral-cn | §3.2 L284 | ok, 0 entries, fixed point |
| `l3-id-stable-vectors` | PS-H03 | stable-id/1 / - | §3.2 L276-L282 | exact value |
| `l3-id-two-owners` | PS-H03 | complete / neutral-cn | §3.2 L292 | ok, 6 entries, fixed point |
| `l3-c-dangling-call` | PS-H04 | complete / neutral-cn | §4.1 L378 | refused `reference-dangling` |
| `l3-c-gateway-phase-start` | PS-H04 | complete / neutral-cn-stale | §2.4 L176 | refused `normalization-not-fixed` |
| `l3-c-gateway-stale-topology` | PS-H04 | complete / neutral-cn | §2.5 L252 | ok, 2 entries, fixed point |
| `l3-c-namespace-defaults` | PS-H04 | complete / neutral-cn | §5.1 L434 | ok, 2 entries, fixed point |
| `l3-c-preserve` | PS-H04 | complete / neutral-cn | §7.1 L536 | ok, 0 entries, fixed point |
| `l3-c-sets-single-uncovered` | PS-H04 | complete / neutral-cn | §7.1 L547 | ok, 1 entry, fixed point |
| `l3-c-write-coalesce` | PS-H04 | complete / neutral-cn-coalesce | §2.4 L176 | ok, 1 entry, fixed point |
| `l3-c-write-conflict` | PS-H04 | complete / neutral-cn-conflict | §2.4 L176 | refused `profile-write-conflict` |
| `l3-fp-c-after-n` | PS-H05 | complete / neutral-cn | §7.3 L569 | ok, 0 entries, fixed point |
| `l3-fp-c-on-n-input` | PS-H05 | complete / neutral-cn | §7.3 L569 | ok, 0 entries, fixed point |
| `l3-imp-projection-out-of-base` | PS-H06 | import_projection / neutral-cn | §5.3 L450 | ok, 7 entries |
| `l3-imp-remap-duplicate-result` | PS-H06 | remap_ids / neutral-cn | §5.2 L444 | refused `id-collision` |
| `l3-imp-remap-nonsubset-id` | PS-H06 | remap_ids / neutral-cn | §3.2 L290 | ok, 0 entries |
| `l3-imp-remap-opaque-attested` | PS-H06 | remap_ids / neutral-cn | §5.2 L444 | ok, 0 entries |
| `l3-imp-remap-swap` | PS-H06 | remap_ids / neutral-cn | §5.2 L444 | ok, 0 entries |
| `l3-mix-n-full-js-py-js` | PS-H07 | normalize_transport / neutral-cn | §7.3 L569 | ok per hop, sealed transport bytes |
| `l3-mix-n-full-py-js-py` | PS-H07 | normalize_transport / neutral-cn | §7.3 L569 | ok per hop, sealed transport bytes |
| `l3-mix-n-two-processes-js-py-js` | PS-H07 | normalize_transport / neutral-cn | §7.3 L569 | ok per hop, sealed transport bytes |
| `l3-mix-n-two-processes-py-js-py` | PS-H07 | normalize_transport / neutral-cn | §7.3 L569 | ok per hop, sealed transport bytes |
| `l3-mix-n-unicode-names-js-py-js` | PS-H07 | normalize_transport / neutral-cn | §7.3 L569 | ok per hop, sealed transport bytes |
| `l3-mix-n-unicode-names-py-js-py` | PS-H07 | normalize_transport / neutral-cn | §7.3 L569 | ok per hop, sealed transport bytes |
| `l3-id-ordinal-missing-only` | PS-H16 | complete / neutral-cn | §3.2 L292 | ok, 8 entries, fixed point |
| `l3-imp-remap-qname` | PS-H16 | remap_ids / neutral-cn | §5.2 L444 | ok, 1 entry |
| `l3-n-after-owner-remap` | PS-H16 | normalize / neutral-cn | §7.2 L565 | ok, 0 entries, fixed point |
| `l3-n-anchor-after-link-removal` | PS-H16 | normalize / neutral-cn | §4.4 L410 | ok, 0 entries, fixed point |
| `l3-n-business-lane-refusal-edit` | PS-H16 | normalize / neutral-cn | §7.2 L559 | refused `profile-open` |

## 12. Not covered

| Item | Status | Reason / owner |
| --- | --- | --- |
| JS(N_Py(x)) = N_Py(x), Python(N_JS(x)) = N_JS(x), JS→Python→JS and Python→JS→Python transport | partial | conductor joint run; exchanged bytes fixed in §8; the six JS transport cases are vendored (§9.2) and only their Python hops run in this harness |
| Undo restores the deleted support and its id (DESIGN §7.2, §7.3 witness "undo") | not covered | history is the lot-5 headless bridge (§8.2). Expected for lot 5: undo after `cn-plan-remove-empty-support` restores exactly the input envelope of that case |
| DI-only drag, resize, palette drop, reconnect, keyboard, cancellation, reentrancy, callback leaks (OPEN-HOOK) | not covered | canvas session and lot 5 |
| External creation/migration gating (OPEN-EXTERNAL) | not covered | `profile-mechanism/1` carries no signal telling the library which recipe creates the external marker; the neutral bases admit no `CallActivity.documentation` (OPEN-BASE). The candidate encoding is exercised only in qualification |
| Python-native import projection case (H B15) | not covered | no Python slice declares a descriptor type outside its base; the JS-owned `l3-imp-projection-out-of-base` is vendored with its PS-21 values (§9.2) |
| DI descriptor validation of `imported_di.diagrams`, dangling DI `bpmnElement`, `snapshot-schema` and DI `descriptor-mismatch` refusals of `remap_ids` | partial | the lot-3 slices pin no DI/DC descriptor package; rules in §5.5 and §6.6 only |
| Navigation index and provenance remap | not covered | outside the envelope (Snapshot/1, lot 5) |
| Acceptance of imported ids outside the authoring subset | not covered | OPEN-ID policy (conductor + both libraries); C/N never normalize ids |
| Ordinals across several ID-less containers under one owner | partial | rule in §6.2, no neutral slice exercises it |
| N `reparent` (approved structural support move) | not covered | no approved move exists (DESIGN §2.4.1); explicit edit reparent is sealed |
| `complete/unset`, `normalize/unset` entries | not covered | no neutral C/N policy unsets a field; explicit edit unset is sealed |
| `remove` with `includeDeclared`, protected content, removal of a binding owner | partial | rules in §6.4, no case |
| Relation pairs that are unknown (no DESIGN code) | partial | expressed by profile `refuse` data; covered generically by `cn-n-support-refusal-after-five-ensures` |
| §7.1 "check required annotation text and expression bodies" | not covered | readiness validation (profile lint), not a C write |
| §5.3 legacy adapters | not covered | each legacy migration needs its own approval (OPEN-MIGRATION); labels/markers are never classification shortcuts (`cn-n-black-box-pool-retained`) |
| `resource-limit` for C/N inputs | not covered | host limits are pinned by receipts |
| `profile-bind-fallbacks` (CR-13), `profile-action-phase` (CR-14) at compile time | not covered | the pinned schema's recipe conditionals reject both first, so `load_profile` refuses `profile-schema` (DESIGN §2.1.1 step 4: schema before compiler); `profile-action-phase` is sealed at planning (`cn-plan-export-phase`) |
| A genuine SHA-256 collision ("hash collisions roll back", DESIGN §7.3) | partial | infeasible to construct; witnessed as allocator-id collisions with existing elements (`cn-c-id-collision`, `cn-n-support-late-band-collision`, `cn-n-recovery-missing-binding-collides`, `cn-plan-create-id-collision`) |

## 13. Design defaults (DESIGN silent or ambiguous)

Each choice is the one recorded in the seal report; changing one requires a reseal.

1. Gate activation keyword (E1) and the gate table of §7 — now the shared contract H H1,
   H2 (DESIGN §7.2, §13, §16).
2. C/N change-entry vocabulary of §4.3 (DESIGN §10.1 fixes the entry shape only), the
   coalesced-write attribution — shared as H B8, B11; the `property` tie-break of §4.4
   is superseded by the H G2 order.
3. `mode` semantics (E2, §6.1): extraction checks actor `ai`; retained checks nothing
   (shared as H B7).
4. Superseded by H D1: the C identity slot is `<containing $type>.<property>`; ownerId
   = nearest ID-bearing ancestor and the ordinal over ID-missing elements are kept (H D2,
   D3).
5. Superseded by H F1: emptied arrays stay `[]`, absent → `[]` writes are changes.
6. Superseded by H C5: reuse validation no longer compares the ensure's declared
   fields; the ensure plan identity still includes them (coalescing, DESIGN §2.4).
7. Compatibility inside C/N: the exact source package is available iff D = P (§5.0
   step 3), now ordered before envelope integrity (H C1).
8. Graph checks before C/N: `descriptor-role-unknown` (DESIGN §3.1), duplicate ids →
   `id-collision` (DESIGN §10.2 legacy mapping of duplicate-id; H C4) and, added by H
   C2, dangling or wrong-type references → `reference-dangling`.
9. Superseded by H B2, B3, B4: refusal records, echo rule and report header of §4.5.
10. Codes where the DESIGN names none: invalid invocation and stale plan →
    `operation-error` (H C11); missing deletion intent → `profile-producer`; unknown
    element parameter, intent element or remap source → `reference-dangling`; remap
    result id outside the authoring subset → `profile-schema` (H C20); missing or
    undeclared parameter → `profile-ui-parameters`; required use of MISSING →
    `profile-type`.
11. `apply_plan` reports Report/2 entries only for complete/normalize plans (§3.3).
12. `remap_ids` idMap includes identity rows (DESIGN "complete original→result map";
    H B14).
13. Recovery provenance is an explicit caller list of support ids (§6.7).
14. Placement intent validated but without semantic effect (§3.5).
15. WritePlan/1 descriptive facts (E7, §3.2); the second-evaluation refusal mapping
    of §5.6 (DESIGN §2.4 text).
16. Remap echo, DI and attestation details of §5.5/§6.6 not fixed by H B14/H9:
    unique `sourceId` rows, attestation `property` spelled `<$type>.<member>` with a
    pin of the compiled identity, `snapshot-schema` for an invalid DI record,
    `descriptor-mismatch` for a foreign DI descriptor digest.

## 14. Seal fix round: decisions and findings applied

### 14.1 Harmonization rows applied

| H row | Effect in this binding | Changed or new cases |
| --- | --- | --- |
| A1–A6, A8 | corpus/1 projection, composed profile bytes, shared names, full artifacts (§9.1) | every parity case (projection only) |
| A7 | transport bytes (§8) | none |
| B2, B3, B4 | refusal record, echo rule, report header (§4.5) | every Result/1 case; echo added to `cn-c-invalid-mode`, `cn-n-support-duplicate-role` |
| B5, B7, B8, B10, B11, B13 | kept as sealed (shared) | none |
| B9, G2 | written-location coordinates and order (§4.3, §4.4) | every case with entries |
| B14, H9, C20 | remap inputs, command record, payload, idMap (§3.7, §5.5, §6.6) | every `cn-remap-*`; new `cn-remap-not-approved`, `-swap`, `-opaque-attested` |
| B15 | import projection binding (§3.8, §6.8) | none (JS-owned case vendored) |
| C1 | precedence prefix (§5.0) | `cn-n-support-duplicate-role` (derivation), new `cn-n-compat-before-integrity` |
| C2, C3 | graph-index reference checks (§5.0 step 5) | new `cn-c-dangling-call`, `cn-c-wrong-type-reference`, `cn-n-dangling-reference`, `cn-c-empty-called-element` |
| C5 | reuse validation without fields (§6.3) | `cn-n-reserved-lane-renamed` (now ok, no entry, edit) |
| D1 | C identity slot (§6.2) | `cn-c-identity-*`, `cn-c-unicode-names`, `cn-c-timer-siblings*`, `cn-c-extraction-authorized`, `cn-c-id-collision` |
| F1 | emptied and empty-derived arrays stored (§4.2) | `cn-c-topology-per-container`, `cn-c-gateway-direction`, `cn-c-input-port`, `cn-c-output-port-qualification`, `cn-c-io-default-sets`, `cn-c-timer-siblings*`, `cn-c-not-fixed` (derivation), the deletion/remap/recreation chain |
| H1, H2, H3 | activation and gate table as the shared contract (§1, §7) | none |
| K1 | cn-n region keys equal to the support roles (§4.6) | every cn-n placement case (`reference-band`, `external-lane`) and every cn-n envelope (identity) |
| section 6 (I-3, I-4) | written compile review, discarded probes (§11.3) | the six `cn-compile-*` (derivations; no status or code changed) |

Review findings applied: the WritePlan descriptive context (E7, §3.2; new
`cn-plan-lane-member-cn`/`-support`), the second-evaluation refusal mapping (§5.6; new
`cn-c-second-pass-refused`, `cn-n-second-pass-refused`), the action/refusal matrix
(§11.2; new `cn-plan-unset-name`, `-wrong-parameter-type`, `-recipe-not-compiled`,
`-export-phase`, `-actor-mismatch`, `-undeclared-parameter`, `-invalid-authority`,
`-optional-binding-missing`, `-link-wrong-target-type`, `-create-id-collision`,
`-reparent-annotation`, `cn-apply-input-conflict`), the compile-context contract for
consumers (`cn-c-uncompiled-context`) and the conversion note of §3.4.

### 14.2 JS-owned cases vendored by the parity sync (H section 3.1)

Vendored in the parity sync (§9.2, §11.4); the values stay those of the owning JS seal.

| JS cases | Python binding used by the harness and the parity run |
| --- | --- |
| `l3-call-*` (14), `l3-path-*` (8), `l3-trig-*` except `l3-trig-normalize-no-invention` (5), `l3-io-*` (8) | Block A `validate` (§6.9) |
| `l3-trig-normalize-no-invention`, `l3-n-legacy-marker-ignored`, `l3-n-empty-process`, `l3-n-unicode-names`, `l3-n-binding-wrong-type` | `normalize` |
| `l3-id-stable-vectors`, `l3-id-rename-stable`, `l3-id-two-owners` | stable-id/1 vectors, `complete` |
| `l3-c-gateway-stale-topology`, `l3-c-gateway-phase-start`, `l3-c-sets-single-uncovered`, `l3-c-preserve`, `l3-c-write-conflict`, `l3-c-write-coalesce`, `l3-c-namespace-defaults`, `l3-c-dangling-call`, `l3-fp-c-on-n-input`, `l3-fp-c-after-n` | `complete` |
| `l3-imp-remap-swap`, `-duplicate-result`, `-opaque-attested`, `-nonsubset-id`, `-qname` | `remap_ids` (§3.7, §6.6) |
| `l3-imp-projection-out-of-base` | `import_projection` (§3.8, §6.8) |
| `l3-mix-*` (6) | Python hops of the conductor joint run (§8, §9) |
| `l3-id-ordinal-missing-only` | `complete` |
| `l3-n-after-owner-remap`, `l3-n-anchor-after-link-removal`, `l3-n-business-lane-refusal-edit` | `normalize` |

The Python runner loads each JS profile with the descriptor and base bytes pinned by
the JS seal (§9.2). Python-native counterparts sealed here with Python-owned values:
`cn-c-dangling-call`, `cn-remap-swap`, `cn-remap-opaque-attested` (two-sided cases:
each seal keeps its own witness).

### 14.3 Parity sync (block-B JS/Python reconciliation)

Decisions applied to this seal's own values. The six cases keep their status, code
and identity; only the wire shape and the parity projection change.

| PS row | Effect in this binding | Changed cases |
| --- | --- | --- |
| PS-25 | a PureResult refusal is exactly `{status: "refused", code, diagnostics}`; a compile refusal carries `diagnostics: []` (§9.1) | `cn-compile-create-identity-mismatch`, `cn-compile-ensure-missing-binding-write`, `cn-compile-ensure-non-support-type`, `cn-compile-port-without-authority` |
| PS-35 | a compile success is `{status: "ok", payload, diagnostics: []}` with `payload` UNSEALED (CompiledProfile has no wire shape); the compiled §5.1 identity is the separate `compiled-identity` artifact (`compiled-identities` for a list); comparator `compile/lot3` (§9, §9.1) | `cn-compile-support-profile`, `cn-compile-variants` |

Decisions recorded in this binding (rules shared with the JS seal):

| PS row | Effect in this binding | Witness |
| --- | --- | --- |
| PS-19 | optional `namespaces` of the `id-remap` command; in-document QNames rewritten keeping their prefix, external ones kept with one observed `unsupported-namespace` entry (§3.7, §5.5, §6.6) | vendored `l3-imp-remap-qname` |
| PS-20 | the `validate` graph-index entry of a dangling `calledElement` (§6.9) | vendored `l3-call-target-dangling-accept` |
| PS-21 | `importProjection` is read-only: `revision` = `baseRevision`, `report.outputRevision` = `inputRevision`; loss entries carry ruleId `adapter`; an emptied containment array stays `[]` (§3.8, §6.8) | vendored `l3-imp-projection-out-of-base` (value applied, §9.2) |
| PS-32 | an observed property-level `remapIds` entry addresses `<element>/<property>`, result provenance `exact` (§6.6) | `cn-remap-internal-call-and-dangling` (already sealed so); vendored `l3-imp-remap-qname` (value applied, §9.2) |
| PS-37 | byte-identical twins are aliases, not copies (§9.1, §9.2) | `l3-n-place-neutral` → `cn-n-place-neutral`, `l3-n-place-grid-shared-anchor` → `cn-n-place-grid-shared-anchor` |

Imported JS cases (69; values owned by the JS seal, §9.2, §11.4): PS-H01 (35: the
`validate` call-kind, ordinary-path, trigger-branch and IO-link witnesses), PS-H02 (5
normalize witnesses), PS-H03 (3 identity vectors), PS-H04 (8 completion witnesses),
PS-H05 (2 completion fixed points), PS-H06 (5 remap and projection cases), PS-H07 (6
cross-runtime transport cases) and PS-H16 (5 cases of the JS seal fix round). §12
rows closed by the import: the JS-owned "add to py" cases and the QName namespace
capture during remap.
