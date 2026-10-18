# SPEC PROFILE CN PY — Python binding of lot 3 (recipes, C, N, supports, import adapters)

Status: binding contract for the lot-3 code job in `bpmn_io.profile` (target 0.3.0
at lot 6, no version bump in block B). Normative design authority is DESIGN R3.3
(SHA-256 `48139f5fd5bd789eacbf271081a95432c54d8361b1e52404e3443a25fa65782f`),
sections §2.4, §2.4.1, §3.2, §5.2–5.3, §7.1–7.3, the §13 gates OPEN-RESERVED-N,
OPEN-EXTERNAL, OPEN-IO, OPEN-MACHINE, OPEN-SHARING, OPEN-ID and the owner decisions
of §16 (items 1, 2, 4, 6, 8, 11, ratified 2026-10-14). It extends
`spec/SPEC_PROFILE_MECHANISM_PY.md` (the lot-0 binding, cited below as MECH);
every divergence from MECH §6 is a listed erratum (§10).

The sealed expectations live in `tests/profile_cn/expected/` and are pinned by
`MANIFEST.sha256` (102 cases, 5 input artifacts, the derivation helper). They are
hand-derived from the DESIGN text and the vendored contracts in
`contracts/profile-mechanism/1/`; the standalone stdlib helper `derive_helper.py`
only computes canonical bytes, SHA-256, `stable-id/1`, content signatures,
revisions, profile deltas and the DESIGN orderings. A code job implements against
them and never edits them: on a disagreement with the DESIGN it keeps the
expectation, adds an `xfail(strict=True)` test naming the DESIGN line and the
expectation file, and reports it.

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
  `profile-variants.json` (16 profile variants as explicit RFC 6902 deltas, §2.4).
- "Element": a JSON object with a string `$type`. "ID-bearing": its descriptor type
  has `id: true`. "UTF-16 order": comparison by UTF-16 code units (MECH §3).
- Activation: `"edit"` (default; every open technical gate enforced) or
  `"qualification"` (read-only preview and neutral qualification, DESIGN §7.2 and §13:
  "read-only preview and neutral qualification may proceed"). A qualification result
  is a candidate for inspection or qualification receipts; it is never committed to an
  editor history or exported while a gate is open (lots 4/5 always pass `"edit"`).

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

Public names re-exported from `bpmn_io.profile` and added to `__all__` (stubs
regenerated with `scripts/gen_stubs.py`): `Authority`, `GATES`, `apply_plan`,
`bind_supports`, `complete`, `create_read_context`, `normalize`, `plan_recipe`,
`propose_support_bindings`, `remap_ids`, `sort_placements`.

### 2.2 Block A prerequisites (errata applied by the lot-3 code job)

The sealed variants are schema-valid (`load_profile` accepts all 16). Compiling them
needs the following corrections of existing profile modules; each restores the pinned
schema or the DESIGN rule. None touches a literal port.

| Id | Module | Current Block A behaviour | Required behaviour (authority) |
| --- | --- | --- | --- |
| B1 | `_compiler`, `_evaluate` | `count` reads `selector`; `reachable` reads `source`/`target` | `count.select`; `reachable.from`/`to` (pinned `profile-mechanism-1.schema.json` `$defs/predicate`) |
| B2 | `_compiler` | `inverseReference` property checked on the `from` binding's type | the property belongs to the referencing (candidate) type: admitted iff some descriptor type declares it as a reference (DESIGN §2.2: inverse traversal over a descriptor reference) |
| B3 | `_compiler` | `ensure` returns without checks: its `as` handle is unknown to later steps (`profile-symbol`) and its writes are not demanded | CR-05/06/07 for ensure (§6.3): type restricted to `bpmn:Collaboration`, `bpmn:Participant`, `bpmn:LaneSet`, `bpmn:Lane` (else `profile-producer`), known type (`profile-type`), declared `owner`/`parent` bindings (`profile-symbol`), containment admission (`profile-type`), scalar fields admitted and produced by `code`, `id` produced by `code`, demands `{parent,/property,create}` and `{envelope,/bindings,binding}`, `as` registered with the ensured type |
| B4 | `_compiler` | CR-06 write-set compared as a multiset | compared as a set: identical demands coalesce (DESIGN §2.4 "Identical writes coalesce"; the R3.1 checker) |
| B5 | `_evaluate` | `owner` only follows a native `parent_` attribute | `owner` resolves the immediate containing element of plain native JSON trees (C/N operate on envelope JSON) |
| B6 | `_compiler` | descriptor type records drop unknown facets | keep the optional `many` (multi-valued reference properties) and `single` (single-valued containment properties) facets; absent facets mean references single-valued and containment multi-valued (the vendored slices) |
| B7 | `_compiler` | `CompiledProfile` lacks identity, types and producers | add read-only fields (with defaults, additive): `identity` (the §5.1 record: `mechanismVersion`, `schemaVersion`, `profile`, `version`, `sha256 = H(profile)`, `base`, `descriptors`), `types` (descriptor index with facets) and `producers` (effective producer matrix). C/N and the adapters require a profile compiled with `descriptor_context` and `base`; otherwise they refuse `descriptor-mismatch` |

The witness `cn-compile-support-profile` (R3.1 "Ensure fixture compiles") and
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
Collaboration, Participant, LaneSet, Lane (`flowNodeRef` many).

### 2.4 Profile variants

`profile-variants.json` lists, per variant: `name`, `source` (vendored file) or
`parent` (another variant), the ordered `delta` (RFC 6902 `add`/`replace`/`remove`),
`descriptorBytes`, `baseBytes` (repository-relative paths) and the expected
`identity`. To build a variant: apply the delta chain to the parsed source JSON,
serialize it, `load_profile(bytes, schema_bytes=<profile-mechanism-1.schema.json>,
base_bytes=<baseBytes>)`, `create_descriptor_context([{**profile["descriptors"][0],
"descriptorBytes": <descriptorBytes>}])`, `compile_profile(validated,
descriptor_context=..., base=json.loads(<baseBytes>))`. The compiled `identity` must
equal the listed one.

| Variant | Delta (summary) | Purpose |
| --- | --- | --- |
| `neutral`, `grid` | none | vendored profiles (opposite `isExecutable` defaults, Task vs ServiceTask, `content` vs anchored `side` placements) |
| `support` | neutral − `place-task` + R3.1 `ensure-supports`; pins re-pinned to the support slice | R3.1 support fixture (as the R3.1 check builds it) |
| `support-abort` | support + `refuse fixture-abort` after the five ensures | R3.1 explicit refusal |
| `support-task-ensure` | support with the lane ensure turned into a `bpmn:Task` ensure | CR-06 ensure restriction |
| `grid-extraction` | grid + producerDelta `import → ai` on `rootElements`, `flowElements`, `ServiceTask.name` | extraction actor schema |
| `cn-c` | neutral + cn pins + 13 complete recipes (topology, gateway direction, backing objects, ports, IO sets) | C policy data |
| `cn-c-unfixed`, `cn-c-noauth` | cn-c + a self-feeding rename / producerDelta `code → dropped` on `DataInputAssociation.targetRef` | rollback, port authority |
| `cn-n` | neutral − `place-task` + cn pins + 7 normalize recipes + 5 command recipes | N policy data, deletion/remap chain |
| `cn-n-conflict`, `cn-n-relocate`, `cn-n-unfixed` | cn-n + conflicting direction / membership release / self-feeding rename | conflicts, responsibility, rollback |
| `cn-n-ensure-conflict` | cn-n + an ensure of the reference band with another name | conflicting ensure definitions |
| `support-no-binding-write`, `neutral-containment-task` | support without the envelope binding write / create-task with containment identity | CR-06 write set, CR-07 identity |

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
"deletionIntent"}`. `create_read_context` applies §5.1 steps 1–4 (argument, envelope,
compatibility and graph checks) and returns the Block A `ReadContext` extended with
read-only fields (additive, with defaults): the compiled profile, the immutable deep
copy of the envelope, its source pointers and revision. `stage` is one of the §10.1
stages (informational; plans never depend on it; the case runner passes `"load"`).

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
(`profile-symbol` otherwise). Export recipes are planned by `map_export` (lot 4):
`profile-action-phase`. Pure: never mutates its arguments.

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
| `create` | `recipeId, type, parent, property, fields` (object), `id` only for `identity: allocated` |
| `ensure` | `recipeId, decision` (`reuse` or `create`), `ownerId, role, type, parent, property, id, fields` |
| `set` | `recipeId, target, property, value` |
| `unset` | `recipeId, target, property` |
| `assignRef` | `recipeId, target, property, mode, ids` (flattened one level) |
| `reparent` | `recipeId, target, parent, property, position` |
| `place` | `recipeId, elementId, ownerProcessId, regionKey, relatedAssociationIds`, `anchorAssociationId` when bound |
| `remove` | `recipeId, target, policy, deleteIds` (ID-bearing ids of the deletion closure, UTF-16 sorted) |

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
"distinct actor schemas"): `extraction` = AI output (actor `ai`), `retained` =
admitted retained native content.

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

`operation` is `"normalize"`; `payload` is exactly `{envelope, placements, report}`:
`envelope` the normalized DocumentEnvelope/1 wire value, `placements` the derived
placement records (§4.6), `report` the same Report/2 wire value as `result.report`.
`placement_intent` is `None` or a list of closed records `{"elementId": <id>}` naming
moved/resized/reattached shapes (DESIGN §8.2 step 3). It is validated (§5.2) and does
not change the semantic outputs: a DI-only move changes only `viewRevision`, which N
does not compute; layout consumes the intent (lots 4/5).

### 3.6 Placement ordering

```python
def sort_placements(placements: Sequence[Mapping[str, object]]) -> list[dict[str, object]]
```

Pure; returns deep copies in the §4.6 order.

### 3.7 Support binding and import adapters (Python-only, no DESIGN ABI name)

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
    id_map: Mapping[str, str],
    *,
    activation: Literal["edit", "qualification"] = "edit",
) -> ResultSuccess | ResultRefused  # operation "remapIds", payload: envelope
```

`propose_support_bindings` is the read-only recovery/import preview of DESIGN §5.2
(OPEN-MACHINE: "supply/review support bindings"); `bind_supports` is the explicit
binding (and recovery activation) transaction; `remap_ids` is the separate approved
import ID-remapping migration. None is ever invoked implicitly by C or N.

### 3.8 Gate table

```python
GATES: Mapping[str, Mapping[str, str]]  # read-only (MappingProxyType), §7
```

## 4. Output shapes

### 4.1 Envelope in and out

Inputs accept a `DocumentEnvelope` (converted with `to_json()`) or its wire mapping;
both are validated with Block A `validate_envelope(..., committed=True)`. Outputs are
built with Block A `complete_envelope(identity, tree, bindings)` (sorted bindings,
recomputed revision) and returned as wire values. `baseRevision` is the input
`semanticRevision`; `revision` is the output one (equal when nothing changed).

### 4.2 Tree write canon

- A created or ensured element is `{"$type", "id"?, <declared fields>}` and is appended
  at the end of its parent's containment array (the array is created when absent); a
  `single` containment property receives the object (an occupied single property
  refuses `profile-type`).
- An assignRef/remove/unset that leaves a reference or containment array empty removes
  the property; no write produces an empty array. Untouched empty arrays of the input
  are preserved.
- Multi-valued references (`many`): `replace` stores the given ids in the given order
  (`ids` operands come in selector order, i.e. UTF-16 id order); duplicate ids refuse
  `profile-type`. `appendUnique` and `remove` deltas on one property coalesce by id:
  stored order minus removals, then new ids in UTF-16 order (DESIGN §2.4).
  Single-valued references: `replace` requires exactly one id (`profile-type`
  otherwise); `remove` of the current id deletes the property; `appendUnique` refuses
  `profile-type`.
- Every referenced id must name an element of the staged tree, including elements
  planned earlier in the same plan (`reference-dangling`), whose type the descriptor
  admits for that reference (`profile-type`). Reference writes never create an
  endpoint.
- A write whose canonical result equals the stored value is a no-op: no change entry.

### 4.3 C/N change entries (Report/2, DESIGN §10.1 "New C/N")

One entry per effective change. Common fields: `severity: "info"`,
`classification: "repairable"`, `disposition: "corrected"`, `stage` = `complete` or
`normalize`, `code` = `<stage>/<action>`, `messageKey` = `<stage>.<action>`.

| Change | `code` | `ruleId` | `property` | `before` | `after` |
| --- | --- | --- | --- | --- | --- |
| C identity allocation | `complete/allocate-id` | `stable-id/1` | `id` | absent | new id |
| recipe `set` | `<stage>/set` | recipe id | property name | stored value or absent | written value |
| recipe `unset` | `<stage>/unset` | recipe id | property name | stored value | absent |
| recipe `assignRef` | `<stage>/assignRef` | recipe id | property name | stored value or absent | final value or absent (emptied) |
| `create` (C) | `complete/create` | recipe id | containment property | absent | final subtree at the result pointer |
| `ensure` that creates (N) | `normalize/ensure` | recipe id | containment property | absent | final subtree at the result pointer |
| `reparent` | `<stage>/reparent` | recipe id | destination containment property | source parent id | destination parent id |

Coordinates: `source` is `{domain: "tree", pointer: <input pointer of the element>,
targetId: <its input id, else the input id of its nearest ID-bearing ancestor that had
one, else null>, provenance: "exact"}` for an element of the input, and `{domain:
"none", pointer: null, targetId: null, provenance: "generated"}` for an element created
by the operation. `result` is `{domain: "tree", pointer: <output pointer>, targetId:
<output id, or nearest ID-bearing ancestor for ID-less content>, provenance:
"generated"` when the element was created or its id allocated by the operation,
otherwise `"exact"}`. `before`/`after` are read from the immutable input and the final
output. A coalesced write (identical plans of two recipes) is reported once, under the
recipe that planned it first. Successful reports carry `inputRevision` =
`baseRevision` and `outputRevision` = `revision`, empty `rawStandardFindings`,
`idMap` and `artifacts` (except `remapIds`, §6.6).

### 4.4 Entry order

DESIGN §10.1 order (stage rank; then UTF-16 `ruleId`, source `domain`, source
`pointer` and `targetId` with null first, `code`, `pageId`, `occurrenceKey`, canonical
`before` then `after` with absent first), then Block A's result `targetId`, then
`property` (UTF-16, absent first) as final tie-breaks. Exact duplicates coalesce. No
sealed report contains two entries equal on the DESIGN and Block A keys, so the sealed
order does not depend on the last tie-break.

### 4.5 Refusals

A refusal carries no candidate. Its `report` is `{reportVersion: "2", operation,
entries: [], rawStandardFindings: [], idMap: [], artifacts: []}` and `diagnostics` is
`[]`. It echoes `profileIdentity` and `baseRevision` (the input envelope's) only when
the input envelope passed `validate_envelope`; an invalid invocation or envelope
echoes neither (DESIGN §10.1: missing identity is omitted, not fabricated).

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
first). No theme field appears.

## 5. Pipelines and refusal precedence

The first refusal in the listed order is returned; nothing is committed and no input
object is mutated (DESIGN §7.3 rollback).

### 5.1 `complete`

1. Arguments: `compiled` with B7 fields (`descriptor-mismatch` if absent), `mode` in
   the closed set, `activation` in the closed set — else `operation-error`.
2. Envelope: Block A `validate_envelope` code (`profile-schema`,
   `document-version-unsupported`, `support-binding-conflict`, …), no echo.
3. Compatibility: Block A `check_compatibility(runtime, P, D, document_version=...,
   source_availability=..., selected_migration=False, required_capabilities=<profile
   capabilities>, required_assets=[], envelope_valid=True)` with P = `compiled.identity`,
   D = the envelope identity, runtime `{mechanisms: ["1"], schemas: ["1.0.0"],
   capabilities: <the six DESIGN §2.1 ids>, assets: []}` and `source_availability =
   "known-and-available"` iff D equals P (C/N never load another package; DESIGN §3.3
   P1), else `"unavailable"`. A refused verdict refuses with its code (DESIGN §7.1
   "reject source version mismatch first").
4. Graph index (one pre-order pass, members in UTF-16 key order, arrays by index):
   unknown element type or member key not classified by the descriptor (`$type`
   excepted) → `descriptor-role-unknown` (DESIGN §3.1); a repeated element id →
   `id-collision`.
5. Extraction actor schema (`mode == "extraction"` only): every present member of every
   element must admit actor `ai` in the effective producer matrix → else
   `profile-producer` (DESIGN §2.4.1 "AI may author only AI fields in extraction").
6. Identity allocation (§6.2) → `id-collision` on a computed collision.
7. Plan every `complete` recipe in profile declaration order with
   `Authority("code", activation)` on the identity-allocated snapshot (all plans read
   that same snapshot); plan refusals (§5.3) propagate.
8. Apply the concatenated plan (§5.4).
9. Fixed point: rerun steps 6–8 on the result; any change entry →
   `normalization-not-fixed` (DESIGN §2.4 bounded second evaluation).

### 5.2 `normalize`

1. Arguments (`operation-error`; malformed or duplicated `placement_intent` records
   included), 2. envelope, 3. compatibility and 4. graph index as in §5.1.
5. Bindings: every binding's `ownerId` and `targetId` name existing elements and no
   `targetId` is bound twice → else `support-binding-conflict`.
6. Placement intent: every `elementId` names an existing element → else
   `reference-dangling`.
7. Plan every `normalize` recipe in declaration order with `Authority("code",
   activation)` on the input snapshot; ensure semantics §6.3, gates §7.
8. Support Participants: every Participant handle produced by an ensure (reused or
   created) must end with exactly the `processRef` the plan assigns to it, or none when
   no write targets it → else `support-binding-conflict` (DESIGN §5.2 no-processRef
   band; R3.1 negative "reference band cannot carry processRef").
9. Apply (§5.4), then placements (§4.6).
10. Fixed point: rerun steps 7–9 on the result with the result bindings; any change
    entry or a different placement list → `normalization-not-fixed`.

### 5.3 `plan_recipe`

Context or plan shape invalid → `operation-error`; recipe not compiled →
`profile-symbol`; export phase → `profile-action-phase`; actor not the phase actor
(`editor` for create/edit/reference/convert/migrate, `code` for complete/normalize)
→ `profile-producer`; parameters in declaration order: missing required or undeclared
supplied → `profile-ui-parameters`, wrong JSON type → `profile-type`, element
parameter naming no element → `reference-dangling`. Then candidates in selector order
and steps in order: selector/predicate/value errors (Block A codes;
`reference-dangling` when a `reference` traversal meets a dangling id, DESIGN §2.2),
`bind` cardinality (`profile-ambiguous-binding` for `one` without exactly one result
or `zeroOrOne` with several), a required use of MISSING (`profile-type`), runtime
producer check of each written (type, property) for the actor (`profile-producer`),
ensure (§6.3), gates (§7), `remove` without `deletion_intent` (`profile-producer`) or
with a retained inbound reference (`reference-dangling`), a reached `refuse` step
(its `code`).

### 5.4 `apply_plan`

Plan shape → `operation-error`; staged envelope → `validate_envelope` code; staged
tree not canonically equal to the staged envelope tree → `input-conflict`;
`plan.baseRevision` ≠ staged `semanticRevision` → `operation-error` (stale plan,
DESIGN §8.2 step 1, aligned with the Block A bridge); then coalescing in plan order:
different values for one (target, property), `replace` mixed with a non-identical
write, an id both appended and removed, two different reparentings, two different
placements for one target/region → `profile-write-conflict`; creations: a created id
equal to an existing id or to a different planned element → `id-collision` (identical
planned creations coalesce); reference checks of §4.2.

### 5.5 Adapters

- `propose_support_bindings`: arguments (`provenance` a list of strings, else
  `operation-error`), envelope, compatibility, graph index, bindings (§5.2 step 5),
  then the dry run of §6.7.
- `bind_supports`: arguments (activation → `operation-error`; binding records closed
  `{ownerId, role, targetId}` non-empty strings → else `profile-schema`), envelope,
  compatibility, gate (`edit` → `profile-open`, OPEN-MACHINE), then each new binding:
  (`ownerId`, `role`) already bound or supplied twice, owner or target missing, target
  already bound → `support-binding-conflict`. The tree is unchanged; report entries
  are empty.
- `remap_ids`: arguments (`id_map` a mapping of strings, else `operation-error`),
  envelope, compatibility, gate (`edit` → `profile-open`, OPEN-ID and per-migration
  approval), repeated element ids → `id-collision`, then each map entry in UTF-16 key
  order: key naming no element → `reference-dangling`; value outside the authoring
  subset `^[A-Za-z_][A-Za-z0-9_.-]{0,255}$` → `profile-schema`; total map not injective
  over the retained ids → `id-collision`; then any element member not classified by the
  descriptor → `migration-reference-opaque` (DESIGN §5.2).

## 6. Semantics

### 6.1 Modes and actors

`retained` performs no input actor check (the content was accepted before). `extraction`
checks the input content against actor `ai` (§5.1 step 5); the fixed-point rerun of an
extraction case uses `retained` (its output is retained content). Explicit commands use
actor `editor`, C and N use `code` (DESIGN §2.4.1 R3.1 bounded authority witness).

### 6.2 C identity allocation (DESIGN §3.2)

1. A Definitions root without `id` (ID-bearing) receives
   `stable-id("document-root/1", "definitions", "root")`.
2. Then, in pre-order (members in UTF-16 key order, arrays by index), each other
   ID-bearing element without `id` receives `stable-id(ownerId, slot, stableKey)` with:
   `ownerId` = the id of its nearest ancestor element having an id (after allocation);
   `slot` = the descriptor-qualified containment property `<prefix>:<property>` where
   `<prefix>` is the namespace prefix of the immediate parent's `$type` (for example
   `bpmn:rootElements`, `bpmn:flowElements`, `bpmn:eventDefinitions`);
   `stableKey` = `JCS([contentSignature, duplicateOrdinal])`; `contentSignature` =
   `H(subtree with every id member removed)` computed on the raw input subtree (no
   generated default added); `duplicateOrdinal` = the number of earlier ID-missing
   elements, in that pre-order, with the same (ownerId, slot, contentSignature) (0 for a
   single-valued containment).
3. An allocated id equal to an id of the input or to an earlier allocation refuses
   `id-collision`; existing ids are never changed. Each allocation emits one
   `complete/allocate-id` entry. ID-less types (Documentation, FormalExpression,
   InputOutputSpecification in the cn slice) are never identified.

### 6.3 `ensure` (DESIGN §2.4, §5.2, §7.2)

For each ensure step: evaluate `owner` (an ID-bearing element), `parent` (element or
planned handle), `ownerId` and `key` (strings) — failure → `support-binding-conflict`.
The ensure plan identity is (owner id, role, type, parent, property, fields, ownerId,
slot, key): an identical earlier plan in the same N run aliases its handle (one
change); a different plan for the same (owner id, role) → `profile-write-conflict`.
If a binding (owner id, role) exists, the target must exist, have the ensured type,
sit in `parent.property`, carry the declared field values and be the target of exactly
that binding; otherwise `support-binding-conflict`; the handle is the target (reuse,
no change). Without a binding, the ensure would create: in `edit` activation it
refuses `profile-open` (OPEN-RESERVED-N); otherwise the id is
`stable-id(ownerId, slot, key)`, an id already present (including an unbound element
of the right type and name: a hash-shaped id alone never authorizes reuse) refuses
`id-collision`, and the element plus binding `{ownerId: owner id, role, targetId}` are
planned. An assignRef targeting a support handle may only fill an absent reference or
confirm the stored value; a different stored value refuses `support-binding-conflict`.
N never finds a support by name and never deletes one.

### 6.4 Other actions

`set`/`unset` write one single-segment scalar path. `create` allocates
`stable-id(ownerId, slot, key)` for `identity: allocated` (ownerId is the evaluated
argument, never the nearest container) and writes no id for `identity: containment`.
`remove` deletes the target and the declared dependents with their subtrees; any
retained element referencing a deleted id (policy `refuseIfReferenced`, or outside the
declared set for `includeDeclared`) refuses `reference-dangling`; bindings targeting a
deleted element are removed with it (the support's ownership record); a binding owned
by a deleted element refuses `reference-dangling`. `place` writes no tree.

### 6.5 Supports across remaps and deletion (DESIGN §7.2)

Empty supports survive N. A deleted support stays absent while no recipe needs its
role; a later need ensures it with the current `ownerId`, which may give a new id
(reported as `normalize/ensure`). Surviving supports keep their ids through owner
remaps.

### 6.6 `remap_ids`

The total map is identity except the supplied entries. Rewritten: element ids, every
descriptor reference value (strings and array items, including `calledElement` in the
cn slice), binding `ownerId`/`targetId`. References naming no element of the input stay
unchanged and each yields one entry `{code: "reference-dangling", messageKey:
"reference-dangling", severity: "error", classification: "integrity", stage: "import",
ruleId: "remap-ids", disposition: "observed"}` with the referencing element's
coordinates, `property` and `before` = `after` = the value. Report: `operation:
"remapIds"`, `idMap` = one row `{sourceId, resultId, domain: "migration"}` per
ID-bearing element of the input (identity rows included: the complete original→result
map), sorted per DESIGN §10.1. DI `bpmnElement`, navigation and provenance remaps act
outside the envelope (§12).

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

## 7. Gates (DESIGN §13 with §16)

All owner parts below were ratified on 2026-10-14; every technical part (conductor
plus both libraries) is open, so `GATES` is (state of this release):

| Gate | Owner | Technical | Guarded effective change | `edit` | `qualification` |
| --- | --- | --- | --- | --- | --- |
| OPEN-RESERVED-N | ratified (§16 item 11) | open | an N ensure that would create a support | `profile-open` | proceeds |
| OPEN-EXTERNAL | ratified (§16 item 2) | open | an N `bpmn:Lane` `flowNodeRef` change (external branch of N) | `profile-open` | proceeds |
| OPEN-SHARING | ratified (§16 item 4) | open | removal of an existing `bpmn:Lane` `flowNodeRef` member | `profile-open` | `responsibility-preservation-required` (no accepted persisted responsibility representation, DESIGN §4.4) |
| OPEN-IO | ratified (§16 item 8) | open | a C fill of an absent `bpmn:DataOutputAssociation` `sourceRef` (missing-output-source producer exception) | `profile-open` | proceeds |
| OPEN-MACHINE | ratified (§16 item 6) | open | `bind_supports` | `profile-open` | proceeds |
| OPEN-ID | ratified (§16 item 1) | open | `remap_ids` | `profile-open` | proceeds |

"Effective" is judged at plan time against the phase-start snapshot: reuse of a bound
support, an appendUnique of an id already present and any other no-op are never gated
(N(N(x)) must succeed in `edit`). Gates are checked at their step, so a gate earlier in
recipe/candidate/step order wins over a later refusal (`cn-n-support-late-band-collision-edit`).
External creation/migration (OPEN-EXTERNAL) has no generic detection signal in
`profile-mechanism/1` (§12).

## 8. Fixed points and the cross-runtime exchange

Every sealed success case of `complete` and `normalize` carries `"fixedPoint": true`:
rerunning the operation on the expected output (`payload` for complete,
`payload.envelope` for normalize; same activation and placement intent; mode
`retained`) must return status ok, the identical payload envelope (and placements),
zero report entries, and `baseRevision == revision ==` the first `revision` (DESIGN
§7.3: C(C(x)) = C(x), N(N(x)) = N(x), empty second-run change entries).

Cross-runtime witnesses JS(N_Py(x)) = N_Py(x) and Python(N_JS(x)) = N_JS(x) are run by
the conductor (§12). The exchanged bytes per case are `jcs_bytes({"envelope":
payload.envelope, "placements": payload.placements})` (UTF-8, no BOM, no trailing
newline) for accepted cases and `jcs_bytes(result.to_json())` for refusals; equality is
byte equality, and the receiving runtime's rerun must also produce zero change
entries.

## 9. Sealed expectation files

Each `tests/profile_cn/expected/<case>.json` holds `case` (= file stem), `clause`,
`author: "spec-seal"`, `operation`, `profile` (variant name or null), `derivation`,
`input`, `expected` and, for accepted complete/normalize cases, `fixedPoint`. How each
`operation` is run (`compiled` = the built variant, §2.4):

| `operation` | Call | Compared with `expected` |
| --- | --- | --- |
| `complete` | `complete(compiled, input.envelope, input.mode, activation=input.activation)` | `result.to_json()` |
| `normalize` | `normalize(compiled, input.envelope, input.placementIntent, activation=input.activation)` | `result.to_json()` |
| `plan_recipe+apply_plan` | `ctx = create_read_context(compiled, input.envelope, stage="load")`; `plan_recipe(compiled.recipes[input.recipe], ctx, input.params, Authority(actor, activation, deletion_intent=deletionIntent))` from `input.authority`; then, when `expected.apply` exists, `apply_plan(plan.payload, input.envelope["tree"], input.envelope)` | `expected.plan`, `expected.apply` (PureResult wire) |
| `apply_plan` | `apply_plan(input.plan, input.envelope["tree"], input.envelope)` | `expected.apply` |
| `compile_profile` | build `input.variant` (or each of `input.variants`) | `status`, `code`, `identity` |
| `propose_support_bindings` | `propose_support_bindings(compiled, input.envelope, provenance=input.provenance)` | PureResult wire |
| `bind_supports` | `bind_supports(compiled, input.envelope, input.bindings, activation=input.activation)` | `result.to_json()` |
| `remap_ids` | `remap_ids(compiled, input.envelope, input.idMap, activation=input.activation)` | `result.to_json()` |
| `sort_placements` | `sort_placements(input.placements)` | the list |
| `gates` | `GATES` as plain dicts | the mapping |

Every runner deep-copies `input` before the call and asserts it is unchanged
afterwards, success or refusal (DESIGN §7.3: the caller tree and bindings are
preserved; only a successful return exposes a candidate).

`tests/profile_cn/test_expected_seal.py` verifies the manifest (any one-byte change
fails), that the helper imports only `__future__`, `copy`, `hashlib`, `json`,
`pathlib`, `sys` (AST scan, never `bpmn_io`), the required keys of every case and that
the helper regenerates every sealed byte. Comparison tolerance is zero.

## 10. Errata against MECH §6

| Id | Erratum | Justification |
| --- | --- | --- |
| E1 | `complete`, `normalize` gain keyword-only `activation="edit"`; positional DESIGN signature unchanged | DESIGN §7.2/§13: gated mutations disabled, neutral qualification allowed; the safe default never activates a gated mutation |
| E2 | `complete` `mode` is the closed set `extraction`/`retained` | DESIGN §7.1 "extraction or admitted retained native content with distinct actor schemas" |
| E3 | `apply_plan` returns the staged result inside ChangeReport/1 and never mutates its arguments | house immutability rule; DESIGN defines no ChangeReport shape |
| E4 | `plan_recipe` takes the compiled recipe record and a context from `create_read_context` | DESIGN `ReadContext` must carry identity, descriptor index and source coordinates (§2.5), which Block A's `ReadContext` lacks |
| E5 | `normalize` `payload.report` equals `result.report` | DESIGN §2.5 payload `{envelope, placements, report}` plus §10.1 `report` |
| E6 | `propose_support_bindings`, `bind_supports`, `remap_ids`, `sort_placements`, `GATES`, `Authority`, `create_read_context` have no DESIGN ABI name | adapters required by DESIGN §5.2, §7.2, §13 (as MECH did for `check_compatibility`) |

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
| `cn-c-gateway-direction` | complete / cn-c | §7.1 Completion C (Topology); §2.2 ids; §2.4 assignRef | GatewayDirection four cases plus derived incoming/outgoing arrays. | ok, 16 entries, fixed point |
| `cn-c-gateway-direction-control` | complete / neutral | §7.1 (private policy, not a universal library rule); §14.4 | The plain neutral profile has no topology policy: gateways stay untouched. | ok, 1 entry, fixed point |
| `cn-c-topology-per-container` | complete / cn-c | §7.1 Completion C (Topology); §2.2 ids; §2.4 assignRef | Per-container incoming/outgoing; the cross-container flow is never retargeted. | ok, 9 entries, fixed point |
| `cn-c-backing-object` | complete / cn-c | §7.1 Completion C (Internal item); §2.4 create, assignRef | Missing backing DataObjects are created; valid backing and stores untouched. | ok, 4 entries, fixed point |
| `cn-c-input-port` | complete / cn-c | §7.1 Completion C (Ports); §13 OPEN-IO; §16 item 8 | Valid ports preserved; the missing input port is keyed by its association. | ok, 2 entries, fixed point |
| `cn-c-output-port-gated` | complete / cn-c | §7.1 Completion C (Ports); §13 OPEN-IO; §16 item 8 | The missing-output-source producer exception refuses profile-open in edit. | refused `profile-open` |
| `cn-c-output-port-qualification` | complete / cn-c | §7.1 Completion C (Ports); §13 OPEN-IO; §16 item 8 | Neutral qualification exercises the gated output port creation. | ok, 2 entries, fixed point |
| `cn-c-io-default-sets` | complete / cn-c | §7.1 Completion C (Sets); §16 item 8 | No sets: deterministic default InputSet/OutputSet for declared Process IO. | ok, 4 entries, fixed point |
| `cn-c-io-sets-preserved` | complete / cn-c | §7.1 Completion C (Sets); §16 item 8 | Existing sets keep every membership; nothing to complete. | ok, 0 entries, fixed point |
| `cn-c-io-set-selection-required` | complete / cn-c | §7.1 Completion C (Sets); §16 item 8 | New uncovered input with several sets refuses io-set-selection-required. | refused `io-set-selection-required` |
| `cn-c-documentation-preserved` | complete / neutral | §7.1 Completion C (Content); §3.2 identity mode containment | Documentation text and textFormat are preserved; no parsing, no ids. | ok, 1 entry, fixed point |
| `cn-c-unicode-names` | complete / neutral | §3.2 contentSignature; §14.3 Unicode U+E000/U+10000 and whitespace | Private-use, astral and whitespace names give distinct deterministic ids. | ok, 5 entries, fixed point |
| `cn-c-timer-siblings` | complete / cn-c | §3.2 duplicateOrdinal; §14.3 ID collisions/reorders/timers | Identical ID-less timer starts get ordinals 0 and 1; nested ids follow. | ok, 4 entries, fixed point |
| `cn-c-timer-siblings-reordered` | complete / cn-c | §3.2 (later reorders never reallocate IDs) | Reordering identified siblings never reallocates their ids. | ok, 0 entries, fixed point |
| `cn-c-id-collision` | complete / neutral | §3.2 (computed collision is id-collision); §7.3 rollback | A computed id equal to a different existing element refuses id-collision. | refused `id-collision` |
| `cn-c-duplicate-source-ids` | complete / neutral | §3.2 (duplicate source IDs refuse); §10.2 duplicate-id -> id-collision | Duplicate existing ids refuse before any C write. | refused `id-collision` |
| `cn-c-not-fixed` | complete / cn-c-unfixed | §2.4 bounded second evaluation; §7.3 rollback on non-fixed point | A self-feeding completion recipe fails the bounded fixed point. | refused `normalization-not-fixed` |
| `cn-c-extraction-authorized` | complete / grid-extraction | §7.1 (extraction actor schema); §2.4.1 actor matrix | Extraction mode admits only AI-produced fields, then C identifies them. | ok, 4 entries, fixed point |
| `cn-c-extraction-unauthorized` | complete / neutral | §7.1 (extraction actor schema); §2.4.1 CR-06 profile-producer | Extraction mode refuses fields not produced by the ai actor. | refused `profile-producer` |
| `cn-c-descriptor-role-unknown` | complete / neutral | §3.1 (unclassified foreign property); §2.5 execution order | An unclassified property refuses descriptor-role-unknown. | refused `descriptor-role-unknown` |
| `cn-c-invalid-mode` | complete / neutral | §2.5 complete(compiled, envelope, mode); spec §3.4 | A mode outside the closed set is an invalid invocation. | refused `operation-error` |
| `cn-n-support-one-process` | normalize / support | §7.2 Structure; §7.3 neutral-support-fixture.R31.json; §3.2 multi-Process support domain witness; §5.2 | All five ensure actions plus processRef for one Process (R3.1 fixture). | ok, 6 entries, fixed point |
| `cn-n-support-two-processes` | normalize / support | §7.2 Structure; §7.3 neutral-support-fixture.R31.json; §3.2 multi-Process support domain witness; §5.2 | Two Process domains get separate Collaborations (R3.1 fixture). | ok, 12 entries, fixed point |
| `cn-n-support-imported-ids` | normalize / support | §7.2 Structure; §7.3 neutral-support-fixture.R31.json; §3.2 multi-Process support domain witness; §5.2; §5.2 imported ID reuse | Imported non-generated support ids survive (qualification). | ok, 0 entries, fixed point |
| `cn-n-support-imported-ids-edit` | normalize / support | §7.2 Structure; §7.3 neutral-support-fixture.R31.json; §3.2 multi-Process support domain witness; §5.2; §5.2 imported ID reuse | Imported supports survive in edit activation too (reuse is not gated). | ok, 0 entries, fixed point |
| `cn-n-support-creation-gated` | normalize / support | §7.2 OPEN-RESERVED-N; §13; §16 item 11 | Support creation refuses profile-open while OPEN-RESERVED-N is open. | refused `profile-open` |
| `cn-n-support-late-band-collision` | normalize / support | §7.2 Structure; §7.3 neutral-support-fixture.R31.json; §3.2 multi-Process support domain witness; §5.2; §7.3 rollback | Late band id collision rolls back four earlier supports. | refused `id-collision` |
| `cn-n-support-duplicate-role` | normalize / support | §7.2 Structure; §7.3 neutral-support-fixture.R31.json; §3.2 multi-Process support domain witness; §5.2; §7.3 rollback | A duplicated owner+role binding refuses at envelope validation. | refused `support-binding-conflict` |
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
| `cn-n-reserved-lane-renamed` | normalize / cn-n | §5.2 support validation; §2.4 ensure; §7.3 role rename | A renamed bound reserved lane no longer matches its ensure declaration. | refused `support-binding-conflict` |
| `cn-n-black-box-pool-retained` | normalize / cn-n | §5.2 (ordinary pool never taken over); §13 OPEN-MACHINE; §16 item 6 | An unbound pool labelled like a support stays an ordinary pool. | ok, 4 entries, fixed point |
| `cn-n-ensure-conflicting-definition` | normalize / cn-n-ensure-conflict | §2.4 (conflicting ensure definitions refuse); §7.2 Structure | Two different ensure plans for one owner+role refuse profile-write-conflict. | refused `profile-write-conflict` |
| `cn-n-not-fixed` | normalize / cn-n-unfixed | §2.4 bounded second evaluation; §7.3 rollback on non-fixed point | A self-feeding normalize recipe fails the bounded fixed point. | refused `normalization-not-fixed` |
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
| `cn-remap-owner` | remap_ids / cn-n | §5.2 ID remapping (separate approved import migration); §13 OPEN-ID; §7.2 surviving support IDs unchanged through owner remaps | Owner remap: references and bindings follow, support ids survive. | ok, 0 entries |
| `cn-remap-gated` | remap_ids / cn-n | §5.2 ID remapping (separate approved import migration); §13 OPEN-ID | ID remap refuses profile-open in edit activation. | refused `profile-open` |
| `cn-plan-create-process-input` | plan_recipe+apply_plan / cn-n | §2.4 action grammar; §2.4.1 action/write matrix; §2.5 planRecipe/applyPlan; §3.2 (ownerId explicit, including under an ID-less ioSpecification) | Containment ioSpecification plus allocated DataInput under explicit owner. | plan ok; apply ok |
| `cn-n-recreate-after-remap` | normalize / cn-n | §7.2 support deletion/recreation/remap; §7.3 deletion/recreation (later need triggers ensure with the current ownerId) | A later need recreates the deleted support with the current ownerId. | ok, 1 entry, fixed point |
| `cn-n-recreate-after-remap-edit` | normalize / cn-n | §7.2 OPEN-RESERVED-N; §13; §16 item 11 | Recreation is a support creation: profile-open in edit activation. | refused `profile-open` |
| `cn-remap-internal-call-and-dangling` | remap_ids / cn-n | §5.2 ID remapping (separate approved import migration); §13 OPEN-ID; §7.3 ID remaps, native references | Internal calledElement follows the map; a dangling target stays and is reported. | ok, 1 entry |
| `cn-remap-collision` | remap_ids / cn-n | §5.2 ID remapping (separate approved import migration); §13 OPEN-ID | A result id equal to a retained id refuses id-collision. | refused `id-collision` |
| `cn-remap-unknown-source` | remap_ids / cn-n | §5.2 ID remapping (separate approved import migration); §13 OPEN-ID | A map key naming no element refuses reference-dangling. | refused `reference-dangling` |
| `cn-remap-opaque-property` | remap_ids / cn-n | §5.2 ID remapping (separate approved import migration); §13 OPEN-ID (migration-reference-opaque) | An unclassified property may hide references: migration-reference-opaque. | refused `migration-reference-opaque` |
| `cn-remap-target-grammar` | remap_ids / cn-n | §5.2 ID remapping (separate approved import migration); §13 OPEN-ID; §3.2 authoring subset | A result id outside the authoring grammar refuses profile-schema. | refused `profile-schema` |
| `cn-propose-recovery-with-provenance` | propose_support_bindings / support | §5.2 support import rules; §13 OPEN-MACHINE; §16 item 6 (recovery proposal) | Exact allocator id + type/parent/fields + provenance: binding proposed. | ok |
| `cn-propose-recovery-without-provenance` | propose_support_bindings / support | §5.2 support import rules; §13 OPEN-MACHINE; §16 item 6 (recovery proposal) | A hash-shaped id alone never authorizes reuse. | ok |
| `cn-propose-recovery-partial-provenance` | propose_support_bindings / support | §5.2 support import rules; §13 OPEN-MACHINE; §16 item 6 (recovery proposal) | Only provenance-listed supports are proposed. | ok |
| `cn-n-recovery-missing-binding-collides` | normalize / support | §5.2 support import rules; §13 OPEN-MACHINE; §16 item 6; §3.2 id-collision | Without bindings, N does not adopt generated-looking supports: id-collision. | refused `id-collision` |
| `cn-propose-black-box-pool` | propose_support_bindings / cn-n | §5.2 support import rules; §13 OPEN-MACHINE; §16 item 6 (ordinary pool never taken over) | A labelled ordinary pool is never proposed. | ok |
| `cn-bind-supports-explicit-selection` | bind_supports / cn-n | §5.2 support import rules; §13 OPEN-MACHINE; §16 item 6 (supply/review support bindings) | An explicit support selection binds an imported Collaboration. | ok, 0 entries |
| `cn-n-after-explicit-selection` | normalize / cn-n | §5.2 support import rules; §13 OPEN-MACHINE; §16 item 6; §7.2 Structure | N reuses the selected Collaboration and keeps the ordinary pool. | ok, 3 entries, fixed point |
| `cn-bind-supports-gated` | bind_supports / cn-n | §5.2 support import rules; §13 OPEN-MACHINE; §16 item 6 | Support binding activation refuses profile-open in edit. | refused `profile-open` |
| `cn-bind-supports-conflict` | bind_supports / cn-n | §5.2 support import rules; §13 OPEN-MACHINE; §16 item 6; §5.1 owner+role unique | Binding an already bound owner+role refuses support-binding-conflict. | refused `support-binding-conflict` |
| `cn-compile-support-profile` | compile_profile / support | §2.4.1 CR-05/CR-06/CR-07 for ensure; §7.3 (fixture compiles) | The R3.1 support recipe compiles (ensure aliases, writes, authority). | ok |
| `cn-compile-ensure-non-support-type` | compile_profile / support-task-ensure | §2.4 ensure restriction; §2.4.1 CR-06 | ensure of a non-support native type refuses profile-producer. | refused `profile-producer` |
| `cn-compile-port-without-authority` | compile_profile / cn-c-noauth | §7.1 Completion C (Ports); §13 OPEN-IO; §16 item 8; §2.4.1 CR-06 | Port creation without explicit code authority refuses profile-producer. | refused `profile-producer` |
| `cn-compile-ensure-missing-binding-write` | compile_profile / support-no-binding-write | §2.4.1 CR-06 write set; action/write matrix (ensure) | An ensure recipe must declare its envelope binding write. | refused `profile-write-set` |
| `cn-compile-create-identity-mismatch` | compile_profile / neutral-containment-task | §2.4 create identity; §2.4.1 CR-07 | Containment identity on an ID-bearing type refuses profile-create-identity. | refused `profile-create-identity` |
| `cn-compile-variants` | compile_profile / - | §2.4.1 compiler rejection mapping; §3.1 profile digest; §5.1 identity | Every success-path variant compiles to its listed identity. | exact value |
| `cn-gates-table` | gates / - | §13 OPEN register; §16 owner decisions; §7.2 | The read-only lot-3 gate table. | exact value |

The table is generated from the sealed files (clause) and the helper docstrings (witness).

### 11.1 DESIGN §7.3 witness list

| Witness | Cases |
| --- | --- |
| external / internal / incomplete calls | `cn-n-external-membership-append` (Call_ext relocated; Call_int and Call_inc untouched), `-edit`, `-remove-refused` |
| native references | `cn-remap-internal-call-and-dangling`, `cn-c-backing-object`, `cn-n-relation-direction-reversal` |
| supports imported with non-generated IDs | `cn-n-support-imported-ids`, `-edit`, `cn-n-relation-direction-reversal`, `cn-n-external-membership-append` |
| ID remaps | `cn-remap-owner`, `cn-remap-internal-call-and-dangling` |
| deletion / recreation | `cn-plan-remove-empty-support`, `cn-n-deleted-support-stays-absent`, `cn-n-recreate-after-remap` |
| multi-process / shared references | `cn-n-reference-region-multi-process`, `cn-n-support-two-processes` |
| preserved original memberships | `cn-n-external-membership-remove-refused`, `cn-n-external-membership-append` |
| unchanged source text | `cn-c-documentation-preserved`, `cn-c-unicode-names` |
| role reorder / rename | `cn-n-external-membership-append` (lane and member order), `cn-n-role-rename-business-lane`, `cn-n-reserved-lane-renamed` |
| inserted / deleted associations | `cn-n-place-grid-inserted-association`, `cn-n-place-grid-deleted-association` |
| timer siblings | `cn-c-timer-siblings`, `cn-c-timer-siblings-reordered` |
| rollback | `cn-c-not-fixed`, `cn-n-not-fixed`, `cn-c-id-collision`, the five support negatives |
| undo | not covered (§12) |

## 12. Not covered

| Item | Status | Reason / owner |
| --- | --- | --- |
| JS(N_Py(x)) = N_Py(x), Python(N_JS(x)) = N_JS(x), JS→Python→JS and Python→JS→Python transport | not covered | conductor joint run; exchanged bytes fixed in §8 |
| Undo restores the deleted support and its id (DESIGN §7.2, §7.3 witness "undo") | not covered | history is the lot-5 headless bridge (§8.2). Expected for lot 5: undo after `cn-plan-remove-empty-support` restores exactly the input envelope of that case (`semanticRevision` `65de97d501d1ad81e50a34646c0148e1257884b81a316c8237b2d6f3797e57d5`) |
| DI-only drag, resize, palette drop, reconnect, keyboard, cancellation, reentrancy, callback leaks (OPEN-HOOK) | not covered | canvas session and lot 5 |
| External creation/migration gating (OPEN-EXTERNAL) | not covered | `profile-mechanism/1` carries no signal telling the library which recipe creates the external marker; the neutral bases admit no `CallActivity.documentation` (OPEN-BASE). The candidate encoding is exercised only in qualification |
| DI `bpmnElement`, navigation index and provenance remap | not covered | outside the envelope (Snapshot/1, lot 5) |
| QName namespace capture during remap | not covered | native JSON references carry no QNames |
| Acceptance of imported ids outside the authoring subset | not covered | OPEN-ID policy (conductor + both libraries); C/N never normalize ids |
| Ordinals across several ID-less containers under one owner | partial | rule in §6.2, no neutral slice exercises it |
| N `reparent` (approved structural support move) | not covered | no approved move exists; Block A also excludes `reparent` from the normalize phase while the DESIGN action table and schema admit it (observation for lot 3) |
| `remove` with `includeDeclared`, protected content, removal of a binding owner | partial | rules in §6.4, no case |
| Relation pairs that are unknown (no DESIGN code) | partial | expressed by profile `refuse` data; covered generically by `cn-n-support-refusal-after-five-ensures` |
| §7.1 "check required annotation text and expression bodies" | not covered | readiness validation (profile lint), not a C write |
| §5.3 out-of-base projection with typed losses and legacy adapters | not covered | import projection is Block A; each legacy migration needs its own approval (OPEN-MIGRATION); labels/markers are never classification shortcuts (`cn-n-black-box-pool-retained`) |
| `resource-limit` for C/N inputs | not covered | host limits are pinned by receipts |
| `profile-bind-fallbacks` (CR-13), `profile-action-phase` (CR-14) for recipe steps | not covered | the pinned schema's recipe conditionals reject both first, so `load_profile` refuses `profile-schema` (DESIGN §2.1.1 step 4: schema before compiler); the compiler codes are reachable only for a `ValidatedProfile` built without the loader |
| A genuine SHA-256 collision ("hash collisions roll back", DESIGN §7.3) | partial | infeasible to construct; witnessed as allocator-id collisions with existing elements (`cn-c-id-collision`, `cn-n-support-late-band-collision`, `cn-n-recovery-missing-binding-collides`) |

## 13. Design defaults (DESIGN silent or ambiguous)

Each choice is the one recorded in the seal report; changing one requires a reseal.

1. Gate activation keyword (E1) and the gate table of §7 (DESIGN §7.2, §13, §16).
2. C/N change-entry vocabulary of §4.3 (DESIGN §10.1 fixes the entry shape only), the
   coalesced-write attribution and the `property` tie-break of §4.4.
3. `mode` semantics (E2, §6.1): extraction checks actor `ai`; retained checks nothing.
4. C identity slot = `<prefix>:<property>` of the immediate parent's type; ownerId =
   nearest ID-bearing ancestor; ordinal counts ID-missing elements only (DESIGN §3.2
   defines contentSignature "for initially missing admitted IDs only").
5. Emptied reference/containment arrays are removed, never left empty (§4.2).
6. Reuse validation compares the ensure's declared fields (R3.1 checker); ensure plan
   identity includes ownerId/slot/key.
7. Compatibility inside C/N: the exact source package is available iff D = P (§5.1
   step 3).
8. Graph checks before C/N: `descriptor-role-unknown` (DESIGN §3.1) and duplicate ids →
   `id-collision` (DESIGN §10.2 legacy mapping of duplicate-id).
9. Refusal reports are empty and echo identity only for a valid envelope (§4.5).
10. Codes where the DESIGN names none: invalid invocation and stale plan →
    `operation-error` (Block A bridge); missing deletion intent → `profile-producer`;
    unknown element parameter, intent element or remap source → `reference-dangling`;
    remap result id outside the authoring subset → `profile-schema`; missing
    parameter → `profile-ui-parameters`.
11. `apply_plan` reports Report/2 entries only for complete/normalize plans (§3.3).
12. `remap_ids` idMap includes identity rows (DESIGN "complete original→result map").
13. Recovery provenance is an explicit caller list of support ids (§6.7).
14. Placement intent validated but without semantic effect (§3.5).
