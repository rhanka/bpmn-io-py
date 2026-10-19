# SPEC PROFILE COMMANDS PY — headless commands, fields and transactions (lot 5, Python part)

Status: binding contract for the lot-5 Python part of `bpmn_io.profile` (target
0.3.0, no version bump in block B). It produces no production code: it binds
DESIGN R3.3 (SHA-256
`48139f5fd5bd789eacbf271081a95432c54d8361b1e52404e3443a25fa65782f`) §8.3, the
headless lifecycle of §8.1 and the parts of the §8.2 transaction adapter that
apply without a browser, together with the sections they rely on (§2.2, §2.4,
§2.4.1, §3.1, §3.2, §5.1, §6.2, §6.4, §7.1, §7.2, §10.1, §13, §14.3, §16).
Revision SF (seal fix round, 2026-10-18): it applies the block-B JS↔Python
harmonization decisions of 2026-10-18 (cited below as "harmonization <row>", for
example harmonization J1) with the precedence DESIGN text > harmonization
decision > review finding, and follows the lot-3 C/N freeze for every contract
shared with lot 3 that no harmonization row changes. Revision PS (block-B
JS↔Python parity sync, 2026-10-19, cited as "parity sync PS-nn"): the compile
success observable of PS-35 (§6), the Python rules adopted as shared contract by
PS-12, PS-14 and PS-17 (§3.2, §4.3, §11), and the JS-owned cases vendored
unchanged with their values (§9.1, §12.1).

The sealed expectations live in `tests/profile_commands/expected/` (harness
cases, committed byte artifacts under `artifacts/`, the
`profile-parity-corpus/1` projection under `parity/`, all pinned by
`MANIFEST.sha256` and checked by `tests/profile_commands/test_expected_seal.py`).
A code job implements against them and never edits them; if a sealed value
disagrees with the DESIGN, the code job keeps it, adds an `xfail(strict=True)`
test naming the DESIGN line and the expectation file, and reports it.

Signatures follow `spec/SPEC_PROFILE_MECHANISM_PY.md` (snake_case operations,
DESIGN wire field names, closed `PureResult`/`Result` unions). Lot 3
(`plan_recipe`, `apply_plan`, `complete`, `normalize`) is consumed through its
frozen signatures and output shapes (§10); lot 4 (layout, R, `viewRevision`
digests) is consumed through `get_snapshot` only and every lot-4 value is an
explicitly unsealed member (§8.3). The lint stages run the block-A profile lint
bridge (§10.3).

## 1. Module layout

New private modules under `src/bpmn_io/profile/` (no change to the literal
ports pinned by `UPSTREAM.toml`, stdlib only):

| Module | Content |
| --- | --- |
| `_ui.py` | compile-time UI and field rules (§6), compiled surface/field/message index attached to `CompiledProfile`, called by `compile_profile` between CR-09 and CR-11 |
| `_commands.py` | command records (§3.1), surface/upstream/field resolution, gesture parameter binding, value typing, paste fragment compilation, replacement map |
| `_transaction.py` | guard states, detached stage, the C → pre-normalize lint → N → post-normalize lint pipeline (§4.8), report composition (§4.9), no-op detection, history entries |
| `_queries.py` | `list_entries`, `list_fields`, `check_field`, `query_references`, `copy`, `localize` |
| `_bridge.py` | `HeadlessBridge` extended with the methods of §2 |

Public names: `bpmn_io.profile.localize` (new) and the new `HeadlessBridge`
methods. `CompiledProfile` gains the compiled UI index; it reuses the lot-3
`identity` field (lot-3 prerequisite B7).

## 2. Signatures and errata

All bridge methods are synchronous (async-to-sync mapping of DESIGN §8.1) and
never raise for an expected refusal: they return the closed union named below.

| DESIGN ABI | Python | Inputs → payload |
| --- | --- | --- |
| `createBpmnCanvas` | `create_bridge(context=None)` | unchanged |
| `setDefinitions` | `set_definitions(envelope, *, expected_revision=None, codec=None, imported_di=None) -> Result` | unchanged signature; **erratum E1**: a load starts a new history epoch (undo and redo stacks cleared, DESIGN §8.2 L643) instead of pushing the previous envelope; payload `{envelope, semanticRevision, viewRevision}` |
| `activateBusinessProfile` | `activate_business_profile(compiled, explicit_migration_plan=None) -> Result` (new) | payload `{envelope, semanticRevision, viewRevision, historyEpoch}` |
| `applyCommands` | `apply_commands(*, base_revision, expected_view_revision, commands, transaction_id, signal=None, codec=None) -> Result` | **erratum E2**: `expected_view_revision: str` and `transaction_id: str` become required keywords (DESIGN L587); payload `{envelope, semanticRevision, viewRevision, transactionId, changed}` (DESIGN L588); `signal: Callable[[], bool] \| None` is the sync form of the DESIGN `signal?`; `codec` is kept and unused by lot 5 |
| `getDefinitions` / `getSnapshot` | `get_definitions()` / `get_snapshot()` | unchanged signatures; reports per §3.4 |
| `undo` | `undo(*, expected_revision, expected_view_revision) -> Result` | **erratum E3**: guarded inputs (DESIGN L595); payload is the restored `Snapshot/1` |
| `redo` | `redo(*, expected_revision, expected_view_revision) -> Result` (new) | payload is the restored `Snapshot/1` |
| `onChange` | `on_change(listener) -> PureResult` (new) | payload `{subscriptionId}`; `listener(event: dict) -> None` |
| `unsubscribe` | `unsubscribe(subscription_id) -> PureResult` (new) | payload `{unsubscribed: true}` |
| `dispose` | `dispose() -> PureResult` | **erratum E4**: returns `{disposed: true}` (DESIGN L599) instead of `None` |
| (§8.3 L659 surfaces) | `list_entries(*, base_revision, surface, subject, locale) -> PureResult` (new) | `{revision, surface, groups}` |
| (§8.3 L653 fields) | `list_fields(*, base_revision, target_id, locale) -> PureResult` (new) | `{revision, targetId, fields}` |
| (§8.3 L659 on-change validation) | `check_field(*, base_revision, target_id, field_id, value) -> PureResult` (new) | `{revision, valid}` or `{revision, valid, code, messageKey}` |
| (§8.3 L657 reference picking) | `query_references(*, base_revision, target_id, field_id, query, offset, limit) -> PureResult` (new) | `{candidates, revision}` |
| (§8.3 L657 copy) | `copy(*, base_revision, element_ids) -> PureResult` (new) | the fragment of §3.2 |
| (§8.3 L659 localization) | `localize(compiled, message_key, locale) -> PureResult` (module function, new) | `{key, text, source}` |

**Erratum E5** (undo/redo revisions): `baseRevision` is the revision committed
before the restoration (the guarded `expectedRevision`) and `revision` the
restored one (DESIGN §3.1 L268, §10.1 L735: the input envelope is the current
one, the committed output is the restored one); block A used the restored
revision for both.

Operation names in `Result` and `Report/2`: `setDefinitions`,
`activateBusinessProfile`, `applyCommands`, `getDefinitions`, `getSnapshot`,
`undo`, `redo`. `PureResult` methods carry no operation name (DESIGN §10.1 L737:
read-only reference query/copy, subscription management and disposal are
`PureResult`); every lot-5 `PureResult` has `diagnostics: []`.

## 3. Closed shapes

### 3.1 Command records (`commands` items, harmonization I3, C8)

Each command is one closed JSON object of exactly one of these kinds:

~~~text
{"command": "surface",  "entry": <UI entry id>,       "context": <SurfaceContext>, "fragment"?: <Fragment>}
{"command": "upstream", "upstream": <upstream id>,     "context": <SurfaceContext>, "fragment"?: <Fragment>}
{"command": "field",    "notion": <notion id>, "field": <field id>, "context": {"target", "value"}}
SurfaceContext = {"owner"?, "target"?, "source"?, "key"?, "value"?}
~~~

- `entry` names a profile UI entry; `upstream` names an upstream editor entry ID
  resolved through `upstreamEntries` (§8.3 L659); a field command names its
  notion and one field declared by it (notion-qualified fields remove the
  ambiguity of a field ID declared by two recognized notions).
- A record without a `command` member, or whose `command` is not one of
  `surface`, `upstream`, `field` (for example a bare `{"recipe", "parameters"}`
  record), is an unadapted entry: `transaction-entry-unsupported` (DESIGN §8.2
  L635, L637). Every mutation of the headless bridge passes through a UI entry or
  a field.
- Any other member, a missing required member, a non-object `context` and any
  other `context` member are ambient parameters: `profile-ui-parameters` (L655).
- The **subject** of a surface command is the handle its `ui.when` sees as
  `self`: `owner` for palette and paste, `target` for context, replace, delete
  and direct-edit, `source` for append and connect. The subject of a field
  command is `context.target`.
- A command must supply in `context` exactly the subject plus every source bound
  by the entry or field parameter map, plus `fragment` iff the surface is
  `paste`; a missing or an extra source refuses `profile-ui-parameters` (L655).
- `value` is the typed submitted value (never `null`); `key` is the
  transaction-scoped insertion key; both are supplied by the caller.

### 3.2 Fragment (copy payload, paste input)

~~~text
{"fragmentVersion": "1", "sourceRevision": <semanticRevision at copy>,
 "elements": [{"property": <containment property in the original parent>,
               "element": <deep, DI-free copy of the native subtree>}]}
~~~

`elements` holds the requested ID-bearing elements, deduplicated, without
elements contained in another requested element, in **source document
pre-order** (harmonization B20): a depth-first walk of the canonical
(profile-c14n/2) document from Definitions, an element before its descendants,
object members in UTF-16 key order (the canonical member order: for a Process,
`artifacts` before `flowElements`) and array items by index. This member order
is the shared contract of both libraries (block-B parity sync PS-14; the same
traversal as the coverage order of harmonization G3).

### 3.3 Payloads

| Operation | Payload (closed) |
| --- | --- |
| `list_entries` | `{revision, surface, groups: [{group, entries: [{id, label: {key, text}, icon: {theme, glyph}, order, upstreamEntries}]}]}` (harmonization B17) |
| `list_fields` | `{revision, targetId, fields: [{notion, field, widget, path, label: {key, text}, message: {key, text}, present, display?, value?, mutable, choices, targetTypes}]}` (harmonization B18) |
| `check_field` | `{revision, valid: true}` or `{revision, valid: false, code, messageKey}` |
| `query_references` | `{candidates: [{id, type, label}], revision}` (harmonization B19) |
| `copy` | the fragment of §3.2 |
| `localize` | `{key, text, source}` with `source` one of `exact`, `fallback`, `key` |
| `get_snapshot`, `undo`, `redo` | `Snapshot/1` `{snapshotVersion: "1", envelope, presentation, viewRevision}` (DESIGN §8.1.1) |
| change event | `{envelope, semanticRevision, viewRevision, transactionId, origin, report}` (DESIGN L606), `origin` one of `load`, `command`, `undo`, `redo` in lot 5; `report` is the report of the result that produced it |

`display` and `value` are present iff `present` is true; `value` is the raw
stored value at `path` (scalar, reference ID or ID array). `mutable` is the
evaluated `mutable` predicate, and false for a readonly widget or a field
without command. Only visible fields are listed. `revision` is the current
`semanticRevision` (equal to the supplied `base_revision`). The headless bridge
has no selection API: `presentation.selection` is always `[]`.

### 3.4 Result/1 and Report/2 of every bridge method (DESIGN §10.1, harmonization A8, B2, B3, B4)

Every `Result` is the closed DESIGN union, sealed in full:

- success `{status: "ok", operation, profileIdentity, baseRevision, revision,
  report, payload}`; read-only operations (`getDefinitions`, `getSnapshot`),
  `setDefinitions`, `activateBusinessProfile` and a no-op `applyCommands` have
  `baseRevision == revision`;
- refusal `{status: "refused", operation, profileIdentity?, baseRevision?, code,
  diagnostics, report}` with `diagnostics == report.entries`.

**Echo rule.** A refusal echoes `profileIdentity` and `baseRevision` = the
identity and `semanticRevision` of the committed envelope whenever an envelope is
loaded and the bridge is not disposed (stale revisions, command refusals, C/N
and lint refusals, `transaction-reentrant`, nothing to undo/redo,
`descriptor-mismatch` at activation); it echoes neither for `canvas-disposed`
and `document-not-loaded` (DESIGN L735: missing identity is omitted, not
fabricated). A `setDefinitions` refusal echoes the argument's identity and
revision when it is a shape-valid `documentVersion: "1"` envelope (harmonization
B3).

**Report header (harmonization B4).** Success: `sourceIdentity` = the input
identity, `targetIdentity` = the output identity, `inputRevision` =
`baseRevision`, `outputRevision` = `revision`. Refusal: `sourceIdentity` and
`inputRevision` iff the result echoes them, never `targetIdentity` or
`outputRevision`. `reportVersion` is `"2"`, `operation` is the result operation,
`entries`, `rawStandardFindings`, `idMap` and `artifacts` are always present
arrays (`artifacts` is `[]` in lot 5).

**Entries.** `setDefinitions`, `activateBusinessProfile`, the getters, `undo` and
`redo` run no recipe, C, N or lint stage: their reports have no entry (undo/redo
restore stored states, DESIGN L641). The `applyCommands` report is composed by
§4.9. Every `PureResult` has `diagnostics: []`.

## 4. Semantics

### 4.1 Activation

`activate_business_profile` requires a loaded envelope. The descriptor pins of
the bridge context (`{id, version, sha256}` of each package) must equal the
compiled profile descriptor pins, otherwise `descriptor-mismatch` (DESIGN L617).
The envelope `profileIdentity` must equal the compiled identity; a difference
is decided by the §3.3 matrix (`check_compatibility`) and never migrates
silently (L615). A non-null `explicit_migration_plan` is the migration lot's
contract and is refused `operation-error` until that lot binds it. Success runs
no C/N and no lint, clears history, increments the session-local `historyEpoch`
(excluded from parity, DESIGN §3.1 L268) and emits no change event.

### 4.2 Surfaces and authorization (DESIGN §8.3 L649, L659)

- An entry is visible in `list_entries` and authorized in `apply_commands` iff
  its `when` predicate is true with bindings `root` and `self` = subject; the
  same evaluation serves both, and a programmatic call of an entry whose `when`
  is false refuses `profile-producer` (harmonization C7; L649 makes this
  evaluation the security/producer boundary).
- `list_entries` keeps the entries of one surface (one of the eight schema
  surfaces, otherwise `profile-type`) whose `when` holds, groups them in the
  order of first appearance of each group in the profile `ui` array, omits
  empty groups and sorts entries by numeric `order`, then UTF-16 `id`
  (harmonization G5). Sealed listings never distinguish first appearance in the
  whole array from first appearance among the entries of the listed surface.
- An `upstream` ID maps to the unique entry listing it; an unlisted upstream ID
  refuses `transaction-entry-unsupported` (L659; harmonization C8).
- Keyboard gestures have no separate command form: they are the canonical
  surface command (L657). `copy` evaluates no `ui.when` and grants no paste
  authorization (L657).

### 4.3 Parameter binding and typing (DESIGN §8.3 L655, L659)

- Each `{name, source}` binding feeds recipe parameter `name` from the command
  `context` member `source`: `owner`, `target`, `source` give element IDs
  (validated handles), `value` the submitted value, `key` the insertion key.
- Handles must be IDs of ID-bearing elements present on the stage, otherwise
  `reference-dangling`; a non-string handle refuses `profile-type`. A field
  command whose `context.target` is not recognized as the named notion refuses
  `profile-type` (shared contract, block-B parity sync PS-12).
- A bound value must match the recipe parameter type without coercion:
  `string` ↔ str, `number` ↔ finite int/float that is not a Boolean, `boolean` ↔
  bool; `null` is never accepted; otherwise `profile-type`.
- Field widgets add: `enum` — the value must equal one choice `value` (JSON
  equality, a choice `name` is not a value); `reference` — the value is an ID
  (not a label): missing element `reference-dangling`, type outside
  `targetTypes` or outside the effective reference ownership of §4.6
  `profile-type`. These checks run on change (`check_field`) and again at commit.
- Commands of the `delete` and `replace` surfaces (and upstream IDs mapped to
  them) are planned with explicit deletion intent (lot-3 `Authority(actor="editor",
  deletion_intent=True)`); every other command without it, so a `remove` action
  reached from them refuses `profile-producer` (lot-3 freeze; shared contract,
  block-B parity sync PS-17).

### 4.4 Fields (DESIGN §8.3 L653, L655, L659)

- A field command resolves `notion` (unknown → `profile-symbol`) and `field`
  among that notion's fields (undeclared → `profile-symbol`); `check_field` and
  `query_references` take the DESIGN reference-query input
  `{baseRevision, targetId, fieldId, ...}` (L657) and resolve `fieldId` among
  the notions recognized for the target (unknown → `profile-symbol`, declared
  by two recognized notions → `profile-ambiguous-notion`). `list_fields`
  returns the visible fields of the recognized notions in profile notion order,
  then field declaration order; a target without recognized notion or fields
  yields `fields: []`.
- A hidden field (`visible` false), an immutable field (`mutable` false), a
  readonly widget or a field without command refuses `profile-producer` on
  edit (harmonization C7); `check_field` reports the same code with `valid:
  false`.
- `display` is the field `display` Value when declared (for example
  `stripPrefix`, `case`), otherwise the raw stored value; `value` is always the
  raw stored value (harmonization B18). Neither writes storage. The edit recipe
  restores the configured marker exactly once (`concat` of the literal marker
  and the submitted body).
- The empty string is stored as an explicit empty string; omitting `value`
  refuses `profile-ui-parameters`. Clearing an optional single-valued reference
  is an explicit remove-reference command (an entry whose recipe uses `assignRef`
  mode `remove`); the property becomes absent, never `null`.

### 4.5 Creation, reference link, IO sets, replace, delete (DESIGN §8.3 L651, L653)

- `create` appends the new element to the end of its containment array (no
  position field exists, harmonization G6). A removal that empties a
  containment or reference array keeps the empty array `[]` (harmonization F1).
- The reference recipe creates the root `DataStore` (named by the value) and the
  unnamed `DataStoreReference` with `dataStoreRef` assigned natively (§4.4
  L408). The connect entry mapped by upstream `connect` creates an
  `Association`; no `DataInputAssociation` or port is created.
- IO set selection is profile data: the neutral fixture's complete recipe
  refuses `io-set-selection-required` for a DataInput covered by no InputSet
  while two or more InputSets exist (DESIGN §7.1 L547). An explicit selection
  command in the same batch satisfies it because C runs once after the batch.
- Replace is a convert-phase recipe. A conversion within the same native type
  keeps the ID and reports no idMap row. A convert execution that removes its
  selected element and creates exactly one ID-bearing element reports
  `{sourceId: removed, resultId: created, domain: "migration"}` in
  `report.idMap` (the DESIGN replacement map, L651; harmonization D7). Other
  convert shapes are not covered.
- The `remove` action computes the inbound closure first; a closure larger than
  the declared dependents with `refuseIfReferenced` refuses
  `reference-dangling` (harmonization C12; DESIGN §2.2 L132). `includeDeclared`
  removes the target and its declared dependents together. A support binding
  whose target is removed is removed with it (lot-3 freeze); undo restores the
  element, its ID and its binding (DESIGN §7.2 L565).

### 4.6 Reference picking (DESIGN §8.3 L657, harmonization B19)

- Arguments: `query` is a string; `offset` and `limit` are safe nonnegative
  integers (not Booleans, not fractional), otherwise `profile-bounds`.
- The field must be a `reference` widget (`profile-type` otherwise). If it is not
  visible or not mutable for `target`, `candidates` is empty.
- Candidates are ID-bearing elements whose `$type` is in `targetTypes` and that
  satisfy effective reference ownership: a root element of Definitions is
  admitted for any target; any other candidate must share the nearest Process
  ancestor of `target`.
- `label` is the candidate `name` when it is a string, otherwise the empty
  string. A candidate matches when `query` is a literal substring of `label`
  (code points, case-sensitive, no normalization; the empty query matches all).
- Matches are sorted by UTF-16 ID, then `candidates = matches[offset:offset+limit]`.

### 4.7 Paste (DESIGN §8.3 L653, L655; §3.2 L276-L288; harmonization D6)

- Every ID `X` inside the fragment is reallocated to
  `stable-id/1(owner.id, "paste", JCS([key, X]))`.
- A reference value equal to a fragment ID is rewritten to its new ID; any other
  reference is external and is kept only when its target exists on the stage
  (`reference-dangling` otherwise) with an admitted type (`profile-type`
  otherwise).
- Each fragment root is appended to `owner[property]` in fragment order; a root
  type not admitted there refuses `profile-type`; a new ID already present on
  the stage refuses `id-collision` (never suffix).
- The paste entry's recipe then runs with its bound parameters. Pasted elements
  are on the stage for the following commands of the batch.

### 4.8 Transaction pipeline (DESIGN §8.2, §6.2 L474, L481; harmonization J1, H1, I1–I5)

States `idle → staging → applying → idle`, plus `restoring` for undo/redo. For
`apply_commands`, first refusal wins and nothing is committed:

1. Disposed → `canvas-disposed`; state not `idle` → `transaction-reentrant`; no
   envelope → `document-not-loaded`; no active business profile or wrong argument
   types → `operation-error`.
2. Acquire the guard (state `staging`); from here every caller callback runs
   with the guard held. Poll `signal` (poll **P1**): true → `operation-cancelled`;
   a disposal during the callback → `canvas-disposed`.
3. Compare `base_revision` with the current `semanticRevision` and
   `expected_view_revision` with the current `viewRevision` (stale →
   `operation-error`, harmonization C10).
4. An empty `commands` list is a no-op (`changed: false`) that runs no C, N or
   lint stage.
5. Stage a deep copy of the envelope and presentation. Validate and apply the
   commands in order (§5 (a)–(i)), each against the stage left by the previous
   ones (lot-3 `plan_recipe`/`apply_plan` under the editor actor); poll `signal`
   after each command (poll **P2**).
6. C once: `complete(compiled, stage, "retained", activation="edit")`
   (harmonization B7, H1); a refusal passes through with its code unchanged.
7. `pre-normalize` lint of the C output under the `draft` policy (block-A profile
   lint bridge, DESIGN §6.2 edit row). An `error` entry whose classification is
   not `repairable` blocks: refuse with the code of the first unresolved error
   entry in `profile-report/2` order (harmonization C19). A draft policy never
   downgrades integrity (L481).
8. N once: `normalize(compiled, c_output, None, activation="edit")`; a refusal
   passes through with its code unchanged (OPEN-RESERVED-N support creation
   refuses `profile-open` inside N, harmonization H1/H2).
9. `post-normalize` lint of the N output under `draft`: any unresolved `error`
   entry blocks with the code of the first one in `profile-report/2` order.
10. Poll `signal` (poll **P3**).
11. If the staged tree, bindings and presentation equal the committed ones,
    return `changed: false` with the current revisions, the full report of §4.9
    (a correction notice) and no history entry and no event (DESIGN L641).
12. Commit (state `applying`): one history entry `{transactionId, before, after}`
    and one change event with origin `command` carrying the result report,
    delivered after the guard is released; a committed batch after an undo
    discards the redo entries.

Getters and queries called during a transaction return the last committed state
(the stage is detached). Any other entry (`apply_commands`, `undo`, `redo`,
`set_definitions`, `activate_business_profile`) refuses `transaction-reentrant`.

### 4.9 Report composition of `applyCommands` (DESIGN §10.1 L739-L755)

- `entries` = C's report entries (stage `complete`, unchanged) ∪ the
  `pre-normalize` lint entries ∪ N's report entries (stage `normalize`; N's
  `payload.report` equals its `result.report`, lot-3 freeze E5) ∪ the
  `post-normalize` lint entries, sorted in `profile-report/2` order and exact
  duplicates coalesced. Command writes contribute **no** entry: explicit edits
  are recorded by the history delta (lot-3 freeze: `apply_plan` reports entries
  only for complete/normalize plans; DESIGN §10.1 L751 has no command stage).
- `profile-report/2` order (harmonization G2): stage rank in the DESIGN L751
  stage order, then UTF-16 `ruleId`, source `domain`, source `pointer` and
  `targetId` (null first), `code`, `pageId`, `occurrenceKey` (absent first),
  canonical `before` then `after` (absent first), then result `domain`,
  `pointer`, `targetId`, then `property` (absent first).
- C/N change entries use the lot-3 vocabulary (harmonization B8, B9, B10): for a
  recipe `set`, `code` `<stage>/set`, `messageKey` `<stage>.set`, severity
  `info`, classification `repairable`, disposition `corrected`, `ruleId` the
  recipe id, `source` and `result` `{domain: "tree", pointer: <element pointer> +
  "/" + <escaped property>, targetId: <element id>, provenance: "exact"}`,
  `property`, `beforePresent`/`before`, `afterPresent`/`after`.
- Lint entries (harmonization B12): disposition `observed`, `source` `{domain:
  "tree", pointer: <RFC 6901 pointer of the reported element in that stage's
  snapshot>, targetId: <reported id>, provenance: "exact"}` (plus escaped path
  segments, DESIGN §6.4 L510), `result` `{domain: "none", pointer: null,
  targetId: null, provenance: "unavailable"}`, `beforePresent` and
  `afterPresent` false. Standard rule `r`: `ruleId` `r`, `code` `bpmnlint/r`,
  `messageKey` `bpmnlint.r`; profile subrule `r`: `ruleId` `r` (the bare rule id,
  DESIGN §6.4 L515), `code` and `messageKey` the rule's `code` and `message`;
  severity and classification from the exact effective `(stage, draft)` policy
  row.
- `rawStandardFindings` = the raw upstream reports of the standard rules (the
  transport rule `profile-mechanism/profile` excluded: its findings are the
  unified profile entries) of the executed lint stages, stage by stage. With
  every standard rule off it is `[]`; its record shape is not fixed by DESIGN
  R3.3 (§6.4 L520) and is unsealed (`raw-lint-transport`) where standard rules
  run.
- `idMap` = the replacement-map rows of the batch (§4.5), sorted per DESIGN L753.
- A refusal report carries exactly the lint entries of the stages executed
  before the refusal (`[]` when none ran: command, C, stale, cancellation
  refusals), never a change entry (harmonization B2).

### 4.10 History

`undo`/`redo` check disposal, re-entrancy, loading, then `expected_revision` and
`expected_view_revision` (`operation-error` when stale), then the presence of an
entry (`operation-error` when there is nothing to undo or redo). They restore
the stored before/after state exactly (state `restoring`), presentation
included: no recipe, no C/N, no lint, no ID computation, no redo truncation.
Each emits one change event whose `transactionId` is the entry's and whose report
is the undo/redo result report (entry-free). A refused batch leaves history and
snapshot byte-identical.

### 4.11 Localization (DESIGN §8.3 L659)

For a profile message: the text named exactly `locale` (`source: exact`), else
the text named `policies.localeFallback` (`source: fallback`). For any other key
(for example a library diagnostic key): the key itself (`source: key`). Locale
names compare exactly: no case folding, no BCP 47 truncation.

## 5. Refusal codes and precedence

| Operation | Order of checks → code |
| --- | --- |
| every bridge method | disposed → `canvas-disposed`; then (mutating entries) guard held → `transaction-reentrant`; then no envelope → `document-not-loaded` |
| `apply_commands` | §4.8 steps 1–12; per command (a)–(i) below |
| `activate_business_profile` | `descriptor-mismatch`; identity → §3.3 code; plan → `operation-error` |
| `undo`, `redo` | stale → `operation-error`; nothing to restore → `operation-error` |
| `list_entries` | stale → `operation-error`; surface → `profile-type`; subject → `reference-dangling` |
| `list_fields` | stale → `operation-error`; target → `reference-dangling` |
| `check_field` | stale → `operation-error`; target → `reference-dangling`; field → `profile-symbol`; then the value outcome as `valid: false` with the commit code |
| `query_references` | argument types → `operation-error`; paging → `profile-bounds`; stale → `operation-error`; target → `reference-dangling`; field → `profile-symbol`; widget → `profile-type` |
| `copy` | stale → `operation-error`; missing ID → `reference-dangling`; Definitions root → `profile-type` |
| `compile_profile` (§6) | CR order; inside CR-10 the order of §6 |

Per command of `apply_commands`, first failure wins:

- (a) not an object, or `command` missing or not `surface`/`upstream`/`field` →
  `transaction-entry-unsupported`;
- (b) closed members (§3.1): missing or unknown member, `context` not an object
  or carrying an unknown member → `profile-ui-parameters`;
- (c) resolution: unknown entry → `profile-symbol`; unlisted upstream →
  `transaction-entry-unsupported`; unknown notion or field not declared by the
  notion → `profile-symbol`;
- (d) `context` sources not exactly the subject plus the bound sources (and
  `fragment` iff paste) → `profile-ui-parameters`;
- (e) handles: non-string → `profile-type`, absent from the stage →
  `reference-dangling`; field target not recognized as the notion → `profile-type`;
- (f) authorization (`ui.when`, field visibility/mutability/readonly/command) →
  `profile-producer`;
- (g) value typing and widget rules → `profile-type` or `reference-dangling`;
- (h) paste fragment → `profile-type`, `reference-dangling` or `id-collision`;
- (i) recipe execution on the stage (lot-3 `plan_recipe`/`apply_plan`) → its
  code, including a `refuse` action code and the `remove` code of §4.5.

## 6. Compile rules added to `compile_profile` (CR-10 and §8.3)

1. Each UI entry and each field with `command`: parameter names unique, declared
   by the recipe, type-compatible with their source (`owner`/`target`/`source` →
   `element`, `value` → `string`/`number`/`boolean`, `key` → `string`), and every
   required recipe parameter bound → otherwise `profile-ui-parameters`.
2. Enum choices: unique JSON values even when names differ →
   `profile-ui-parameters` (the executable design checker's code). Empty
   choices, empty reference `targetTypes`, a readonly widget with `command` and a
   mutable field without `command`/`parameters` are rejected by the pinned
   schema → `profile-schema`.
3. An upstream entry ID appears at most once across all UI entries →
   `profile-symbol` (the DESIGN calls duplicate mappings a compile error without
   a code; CR-05 namespace uniqueness).
4. Every message has a text for `policies.localeFallback` → `profile-symbol`
   (the DESIGN calls missing fallback text a compiler error without a code).
5. UI labels, field labels and messages, icon themes and glyphs, UI and field
   recipes exist → `profile-symbol` (CR-05).

Writing an existing ID stays a CR-06 `profile-producer` refusal (DESIGN §2.4
L165, §2.4.1 L206). A compile success is compared as the `PureResult` success
`{status: "ok", payload, diagnostics: []}` whose `payload`, the
`CompiledProfile`, has no wire shape and is unsealed (`compiled-profile`); the
compiled §5.1 identity (`compiled.identity`) is sealed separately as
`expected.compiledIdentity` (parity role `compiled-identity`). A load or compile
refusal is the `PureResult` refusal `{status: "refused", code, diagnostics: []}`
(DESIGN §10.1 L737; shared contract, block-B parity sync PS-25 and PS-35).

## 7. Gates

| DESIGN item (§13) | State given §16 | Python lot-5 behaviour |
| --- | --- | --- |
| OPEN-HOOK (L923) | canvas pointer/keyboard receipt | N-A for Python (harmonization H8): no browser gesture; headless commands use detached staging only |
| OPEN-PANEL (L925, §16.5) | owner choice after canvas evidence | N-A for Python (harmonization H8): no panel dependency; the field contract of §4.4 is panel-independent |
| OPEN-EXTERNAL (L910, §16.2) | owner default ratified; encoding proof pending, external creation unavailable | the library has no external branch; a profile gates its external entry with a `refuse` step, which refuses `profile-open` atomically (harmonization H4; `gate-external-creation`) |
| OPEN-RESERVED-N (L917, §16.11) | owner default ratified; twin atomicity proof pending | `apply_commands` always runs C and N with activation `edit` (harmonization H1): an N ensure that would create a support refuses `profile-open` inside N; reuse of bound supports commits (`gate-reserved-n-*`) |
| OPEN-DRAFT (L911, §16.3) | ratified | edits run both draft lint stages: warnings never block, integrity and post-normalize unresolved errors do (§4.8; `lint-*`) |

## 8. Case file format

Every file `tests/profile_commands/expected/<case>.json` is one JSON object with
`case` (= file stem), `clause` (starts with `DESIGN R3.3 §`), `derivation`,
`author` (`spec-seal`), `input`, `expected`, and optionally `derived`
(`loadRevision`, `ids`, `identity`, recomputed by `derive_helper.py check`).
Vendored JS cases use the record of §9.1.

### 8.1 Fixtures and committed bytes (harmonization A3, A6)

`fixture-descriptors.json` and `fixture-base.json` give `input.source = {file,
delta}` (RFC 6902 against a vendored contract file) and `expected = {document,
pin, artifact}`; the committed file `artifact` holds exactly the UTF-8
profile-c14n/2 bytes of `document` (no BOM, no trailing newline), so its raw
SHA-256 equals `pin.sha256 = H(document)`. `fixture-profile-neutral.json`,
`fixture-profile-neutral-lint.json` and `fixture-profile-grid.json` give the
profile composition and `expected = {profileSha256, identity, artifact}`. Every
case profile is `input.profile = {fixture, delta, artifact}`: the fixture
composition followed by the case delta (RFC 6902 `add`, `replace`, `remove`,
`test`), whose profile-c14n/2 bytes are committed at `artifact`
(`artifacts/profiles/<variant>.json`; raw SHA-256 = `H(profile)` =
`identity.sha256`).

### 8.2 Setup

1. `context = create_descriptor_context([{**pin, "descriptorBytes": <raw bytes of
   artifacts/neutral-descriptors.lot5.json>}])`, unless `input.bridge.descriptorPackages`
   lists `{file, pin}` records, whose `descriptorBytes` are the raw file bytes
   (the profile still compiles with the fixture context);
2. `load_profile(<raw bytes of input.profile.artifact>, schema_bytes=<pinned
   profile-mechanism-1.schema.json>, base_bytes=<raw bytes of
   artifacts/neutral-base.lot5.json>, descriptor_pins=[pin])`;
3. `compile_profile(validated, descriptor_context=<fixture context>, base=<the base
   document>)`;
4. the case identity is the composed profile identity (the fixture `identity`,
   or `derived.identity` when the case adds a delta);
5. with `input.document = {tree, bindings, importedDi?}`: `bridge =
   create_bridge(context)`; `bridge.set_definitions(complete_envelope(identity,
   tree, bindings), imported_di=<importedDi or None>)` matched against
   `expected.setup.load`; `bridge.activate_business_profile(compiled)` matched
   against `expected.setup.activate`. Without `input.document` only the bridge
   is created.

`expected.compile` (compile cases) is the first refusal of steps 2–3, or the
compile success record of §6; a compile success also carries
`expected.compiledIdentity`, the identity record of the compiled profile (equal
to the composed profile identity, recomputed by `derive_helper.py check`).

### 8.3 Steps and matching

`input.steps[i] = {op, args?, save?}` with ops `apply_commands`, `undo`,
`redo`, `get_snapshot`, `get_definitions`, `dispose`, `activate`,
`set_definitions` (`{document}` with the case identity), `list_entries`,
`list_fields`, `check_field`, `query_references`, `copy`, `localize` (module
function), `on_change` (`{collect: name}`: the listener appends each event) and
`events` (`{name}`: actual value `{"events": [...]}`); argument names are the
DESIGN camelCase names of §2. Placeholders: `{"$current": "viewRevision"}` is
`get_snapshot().payload.viewRevision` at that moment; `{"$saved": name,
"pointer": p}` is the JSON at `p` of a saved actual result. `save: name` stores
the step's actual result (`to_json()` form). Signals (`args.signal`):
`{kind: "constant", returns}`; `{kind: "sequence", values}` (call `i` returns
`values[min(i, len - 1)]`); `{kind: "reenter", calls, returns}` (the calls are
performed at the first poll on the same bridge, each result recorded per op);
`{kind: "dispose", returns}` (disposes at the first poll).

`expected.steps[i] = {result, equal?, differ?, signal?}`:

- `result` is the **complete** actual result (`to_json()` of the closed union;
  `{"events": [...]}` for `events`) compared by profile-c14n/2 byte equality after
  each `{"$unsealed": <reason>}` marker is replaced by the actual member at the
  same position (the member must exist). No other member is excluded;
- `equal`/`differ`: `[{pointer, saved, savedPointer}]` profile-c14n/2 equality or
  difference of the actual result at `pointer` with a saved result at
  `savedPointer` (relational checks of lot-4 values, for example whole
  `Snapshot/1` payloads after undo/redo);
- `signal`: `{minCalls, results}`: the signal ran at least `minCalls` times and
  every recorded result of an op equals `results[op]` (same marker rule).

Unsealed reasons (harmonization A8 explicit UNSEALED list):

| Reason | Members | Why |
| --- | --- | --- |
| `lot4-view-revision` | `viewRevision` of payloads, snapshots and events | §9.2 digest tuple over the lot-4 layout (DESIGN L268); lot 5 compares it relationally |
| `lot4-presentation` | `presentation.layout`, `themeId`, `overrides`, `diStyles`, `activePageId`, and `importedDi` when no record was supplied at load | lot-4 layout adapter and theme selection; an explicitly loaded `importedDi` record is sealed exactly |
| `session-history-epoch` | `historyEpoch` | session-local counter excluded from parity (DESIGN §3.1 L268) |
| `session-subscription` | `subscriptionId` | session-local, excluded from parity (DESIGN §8.1 L606) |
| `raw-lint-transport` | `report.rawStandardFindings` of the two vendored-validation witnesses | raw upstream report records are the frozen upstream comparator (DESIGN §3.1 L272, §6.4 L508, L520); their Report/2 record shape is not fixed |
| `compiled-profile` | `payload` of a compile success | the `CompiledProfile` is an in-process object without wire shape (DESIGN §10.1 L737, §2.5 L227); its identity is sealed as `expected.compiledIdentity` (parity sync PS-35) |

## 9. Parity projection (`profile-parity-corpus/1`, harmonization A1–A5)

`expected/parity/lot5-py-<case>.json` is the corpus/1 record of each harness case
(DESIGN §14.3 L959), a pure transcription derived by `derive_helper.py`
(`parity_record`, compact JSON with sorted keys): `caseId` `lot5-py-<case>`;
`operation` the camelCase DESIGN/helper name of the only action of the case,
`compileProfile` for compile cases, otherwise `sequence`; `phase` null;
`profileArtifact` `{path, sha256}` of the committed profile bytes;
`inputArtifacts` the descriptors and base artifacts `{role, path, sha256}`, the
bridge input, the initial envelope and the loaded importedDi (`{role, json}`);
`commandArtifact` `{role: "sequence", json: {sequenceVersion: "1", steps: [{step,
action, request?, save?}]}}`; `expectedArtifacts` the setup and step outcomes
(or the compile outcome, plus the `compiled-identity` artifact of a compile
success, comparator `lot5-py/compiled-identity`); `expectedStatus` `ok`/`refused:<code>` for a
single-step or compile case and `ok` for a sequence (step refusals are step
outcomes); `comparatorIds` from `parity/manifest.json`, whose `pathBase` is
`tests/profile_commands/expected/` and whose `files` pin every parity record and
referenced artifact by SHA-256. The JS↔Python joint run executes these records.

### 9.1 Vendored JS cases (block-B parity sync, harmonization §3)

The block-B parity sync imports into this seal the JS cases that witness a
Python headless behaviour: PS-H23, the 150 JS lot-5 programmatic surface,
palette, context, connect, replace, delete, fields and paste cases carrying a
`twin` artifact, `history-001`…`-005`, `history-012`, `twin-001`, `demo-001`
(steps 1–11) and the surface compile cases `surfaces-013` and `-014`; PS-H24, the
JS lot-3 transaction script `l3-tx-incremental-draft` as a headless sequence
(harmonization J1). Their values stay those of the owning JS seal: they are
vendored unchanged, never recomputed and never obtained from an implementation.
Every section-1 decision of the parity sync was checked against every vendored
value and changes none (PS-08, PS-09, PS-10, PS-11, PS-14, PS-15, PS-16, PS-25,
PS-28 and PS-29 hold as sealed); a JS discrimination text that contradicts a
decision is not carried into the derivation (`lot5-surfaces-009-element-annotation`,
PS-11).

- **Files.** The JS case files and every byte sequence they reference are
  committed raw under `expected/vendor/js/`, a mirror of the JS `tests/fixtures/`
  directory (`lot5-ui/expectations/` for lot 5; `lot3-cn/expectations/` and the
  lot-0 metrics asset under `profile-parity-corpus/` for lot 3).
  `derive_helper.VENDORED` pins each file with the raw SHA-256 of its owning JS
  seal (lot-5 `manifest.json` `files`; lot-3 `manifest.json` `files` for the case,
  lot-3 `seal.json` for its profile, descriptor and base packages and the metrics
  asset), taken from the JS seals whose `seal.json` SHA-256 are
  `0353affc89e60853fa6dac9e99bb1aea40fed7fc9670311dee15964ccb755813` (lot 5) and
  `6b807ee2c219f614d0f434cb8568c8d15acc0cc425a11bfdaa5cf027d86e8b06` (lot 3). The
  schema pin of the vendored lot-5 registry
  (`c97cfba64560ec0e7098294a5e185187de9d1f2207b272c2f002f576865692da`) is the
  committed `contracts/profile-mechanism/1/profile-mechanism-1.schema.json`.
- **Harness record.** `expected/<JS caseId>.json` is `{case, clause, derivation,
  author: "spec-seal", operation, profile: {vendored, sha256}, input: {source:
  {vendored, sha256}, pathBase, inputArtifacts, commandArtifact?}, expected}`.
  `derive_helper.vendored_record` derives every member but `clause` and
  `derivation` from the vendored case file and `check` requires equality;
  `clause` lists the JS DESIGN clauses; `derivation` names the owning seal and
  case file digests (checked), the JS discrimination text and the decision
  notes. `operation` is the JS operation (A4 camelCase), `sequence` for
  `canvas.sequence` and `transaction-script`. `inputArtifacts` and
  `commandArtifact` are the JS records unchanged, their paths relative to
  `pathBase`; the `demo-001` sequence keeps the steps 1–11 the twin replays, each
  gesture step 1–9 written as the `applyCommands` request that carries the
  command record the JS seal seals as staged by that step and that step's sealed
  `baseRevision`.
- **Expected.** The JS `twin` artifact (the Python headless outputs of the same
  input) for every lot-5 case except the two compile cases, which carry the JS
  `result` artifact (`{status: "refused", code, diagnostics: []}`), and `{trace,
  unsealed}` (the JS trace and its UNSEALED pointer list) for
  `l3-tx-incremental-draft`. `check` also recomputes the arithmetic of these
  values: every envelope `semanticRevision` (expected values and vendored input
  snapshots), the closed Result/1 and Report/2 bookkeeping of every result whose
  report is sealed, and every archived `importedDi` digest (PS-15).
- **Execution** (harness support for the code job; the seal test runs nothing):
  - Lot-5 session (JS harness contract item 1): `profileArtifact` is loaded and
    compiled with the vendored registry `fixtures/ui-neutral-registry.json` (raw
    digest domain), base `fixtures/ui-neutral-base.json`, descriptors
    `fixtures/ui-neutral-descriptors.json` and the asset bag
    `{ui-neutral-metrics.json: fixtures/ui-neutral-metrics.json}`; the bridge
    context is the descriptors package. A twin case loads the `envelope` of the
    `snapshot` input with its archived `presentation.importedDi`, activates the
    compiled profile, then runs `commandArtifact` (`transaction` →
    `apply_commands`; `sequence` → its steps in order) or each `queries` record
    (the bridge method of the case operation). `"@current"` is
    `get_snapshot().payload.viewRevision` at that moment; events are those of a
    listener subscribed before the call.
  - The observation compared with `expected`: a transaction gives `{result,
    events, history}`, `history` being `undo` then `redo` (current revisions,
    each `{result, events}`) after a commit, or `{probe, probeEvents}` (the
    refused `undo`) after a refusal or no-op; queries give `{result: [...]}`, one
    `PureResult` per query; a sequence gives `{steps: [{step, result,
    events?}]}`. Comparison is profile-c14n/2 equality after the JS markers:
    `{"$unsealed": reason, "type": t}` (present with JSON type `t`; reasons
    `twin-presentation`, the presentation members, and
    `replacement-map-multi-create`, the `report.idMap` of one conversion that
    creates two ID-bearing elements), `{"$equals": {"member": "twin", "pointer":
    p}}` (equal to the actual observation at `p`) and `{"$equals": {"input":
    "snapshot", "pointer": p}}` (equal to the vendored snapshot at `p`).
  - Compile cases: `load_profile` and `compile_profile` of the variant
    `profileArtifact` with the `compile-inputs` record; the first refusal is
    compared with `expected`.
  - `l3-tx-incremental-draft`: the `lot3-transaction-script/2` steps run on one
    headless bridge set up from the `session` record (profile, descriptors,
    metrics; base `lot3-cn/expectations/profile/neutral-cn-base.json`):
    `onChange` → `on_change`, `setDefinitions` → `set_definitions` then
    `activate_business_profile` of the session profile, `applyCommands` →
    `apply_commands`, `getSnapshot` → `get_snapshot`, `undo`, `redo`;
    `{"$ref": {step, pointer}}` resolves to an earlier actual step value, and the
    trace compares under its `$same`/`$differs` relations and the UNSEALED
    pointers of `unsealed`.
- **Parity.** Vendored cases are not re-published under `parity/` (the owning
  JS seal publishes them); `parity/manifest.json` lists each one under `vendored`
  as `{caseId, source, sha256}` (`source` the JS repository path, `sha256` the
  owning seal's pin). The JS lot-5 seal does not import `tx-cancelled`,
  `tx-dispose-during-transaction` and `tx-reentrant-refused` (parity sync
  section 5: synchronous poll points and re-entrant callbacks are runtime
  mechanics, PS-18); they remain Python records under `parity/`.

## 10. Cross-lot contracts consumed

### 10.1 Lot 3 (frozen C/N contract)

- `complete(compiled, envelope, mode, *, activation)` with `mode` `retained` for
  staged edits (harmonization B7) and `activation="edit"` (harmonization H1);
  payload DocumentEnvelope/1.
- `normalize(compiled, envelope, placement_intent=None, *, activation)`: payload
  `{envelope, placements, report}` with `payload.report == result.report`
  (harmonization B5); lot 5 passes no placement intent (headless commands move
  no shape; DI moves are OPEN-HOOK, canvas).
- `plan_recipe(recipe, read_context, params, authority)` →
  `PureResult<WritePlan/1>` and `apply_plan(plan, staged_tree, staged_envelope)` →
  `PureResult<ChangeReport/1>` `{reportVersion: "change/1", tree, bindings,
  entries, placements, created, removed}`: lot 5 uses `created`/`removed` for the
  replacement map and the stage, and expects no entry for command plans.
- Codes pass through unchanged: `io-set-selection-required`,
  `reference-dangling`, `profile-type`, `id-collision`, `profile-open`,
  `profile-write-conflict`, `support-binding-conflict`, `normalization-not-fixed`
  and any `refuse` code.
- Change entries follow harmonization B8–B10; emptied arrays stay `[]`
  (harmonization F1, which also changes the lot-3 seal).

### 10.2 Lot 4

`get_snapshot` presentation and `viewRevision` come from lot 4 (`compute_layout`
over the archived `importedDi`, theme selection, §9.2 digests). Lot 5 seals only
the loaded `importedDi` record, `selection: []` and the envelope, and compares
the rest relationally. The archived `importedDi.descriptorDigest` is the lot-4
`descriptorDigest(profileIdentity.descriptors)` (H of the pins sorted by UTF-16
id).

### 10.3 Block A prerequisites revealed by this binding (code job fixes first)

1. The `count` predicate is read from key `selector` instead of the schema key
   `select` (compiler and evaluator); `reachable` reads `source`/`target`
   instead of `from`/`to` (not used here).
2. `inverseReference` property admission is checked on the source type instead
   of the referring type; CR-10 is not implemented; `ensure` (lot 3) registers
   neither its alias nor its write demands.
3. The profile lint bridge (`_lint/report.py`) emits profile subrule entries with
   `ruleId` `profile:<id>` and copies the source coordinate into `result`; lot-5
   reports use the bare rule id (DESIGN §6.4 L515) and the unavailable result
   coordinate of harmonization B12, and their `rawStandardFindings` is an array
   that excludes the transport rule.
4. The bridge (`_bridge.py`) pushes history on load (E1), returns `None` from
   `dispose` (E4), has no redo, no guarded undo (E3, E5), and archives a default
   `importedDi` with an empty `descriptorDigest`.

## 11. Design-default resolutions

`design-default` lines (the DESIGN names no value; the lot-5 binding chooses; rows
1, 3, 7 and 8 are now shared contract decisions, harmonization C7, C8, D6, D7;
row 13, the copy pre-order of row 16 and row 17 are shared contract decisions of
the block-B parity sync, PS-12, PS-14 and PS-17):

1. `ui.when` false, hidden/immutable/readonly field edit → `profile-producer` (§8.3 L649; harmonization C7).
2. Stale `baseRevision`/`expectedViewRevision`/`expectedRevision` and nothing to undo/redo → `operation-error` (existing bridge binding; §8.2 L629 names no code; harmonization C10).
3. Unlisted upstream entry, record without an accepted `command` kind → `transaction-entry-unsupported` (§8.2 L635, L637; harmonization C8).
4. Unknown UI entry, notion or field, duplicate upstream mapping, missing fallback text → `profile-symbol` (CR-05; harmonization C9).
5. `remove` closure violation → `reference-dangling` (§2.4 L171, §2.2 L132; harmonization C12).
6. Paging violations → `profile-bounds` (CR-04; harmonization B19).
7. Paste allocation `stable-id/1(owner, "paste", JCS([key, X]))` (§3.2; harmonization D6).
8. Replacement map in `report.idMap` with domain `migration` (§10.1 L753; harmonization D7).
9. Surface subjects per §3.1; effective reference ownership per §4.6; candidate label per §4.6.
10. C and N run once after the whole batch, commands stage sequentially (§8.2 L631, §8.3 L653; harmonization I4).
11. Lint: both draft stages run inside `apply_commands` and their entries are sealed; a pre-normalize error that is not `repairable` and any post-normalize error block with the code of the first unresolved error entry (§6.2 L474, L481; harmonization J1, C19). This reverses the former item 11.
12. OPEN-RESERVED-N is enforced by N itself in activation `edit` (harmonization H1, H2); the former new-binding comparison is withdrawn.
13. A field command whose target is not recognized as the named notion → `profile-type` (parity sync PS-12).
14. The lot-5 fixture profiles set the 26 standard bpmnlint settings to `off` in all ten validation records (the vendored descriptor slice cannot express FlowNode connectivity, so connectivity rules flag every Task); the vendored records are exercised by `fixture-profile-neutral-lint`.
15. Report composition and lint entry coordinates of §4.9; undo/redo `baseRevision` of E5.
16. Signal polls P1, P2 (after each command) and P3 (§4.8; runtime mechanics, parity sync PS-18); `copy` pre-order over the canonical document (§3.2; parity sync PS-14).
17. Deletion intent exactly for `delete` and `replace` surface commands (§4.3; parity sync PS-17).

## 12. Case table

One row per sealed harness file (status summary: `ok xN` counts successful steps).

| Case | DESIGN clause | Witness | Expected |
| --- | --- | --- | --- |
| `compile-enum-duplicate-records` | §8.3 L655 | identical enum choice records (schema uniqueItems) | compile refused `profile-schema` |
| `compile-enum-duplicate-values` | §2.4.1 L195 | enum choices share a JSON value under different names | compile refused `profile-ui-parameters` |
| `compile-enum-empty-choices` | §8.3 L655 | enum widget without choices (schema) | compile refused `profile-schema` |
| `compile-field-parameter-missing` | §8.3 L655; §2.4.1 L195 | mutable field map incomplete | compile refused `profile-ui-parameters` |
| `compile-grid-l5-ok` | §2.4.1 L195; §8.3 L655; §10.1 L737 | every CR-10 rule satisfied (grid) | compile ok (payload unsealed); compiled identity |
| `compile-id-not-ordinary-input` | §8.3 L653; §2.4 L165; §2.4.1 L206 | a recipe writing an existing ID | compile refused `profile-producer` |
| `compile-message-missing-fallback` | §8.3 L659 | message without policies.localeFallback text | compile refused `profile-symbol` |
| `compile-mutable-without-command` | §8.3 L659 | mutable field without command (schema) | compile refused `profile-schema` |
| `compile-mutable-without-parameters` | §8.3 L655 | mutable field without parameter map (schema) | compile refused `profile-schema` |
| `compile-neutral-l5-ok` | §2.4.1 L195; §8.3 L655; §10.1 L737 | every CR-10 rule satisfied (neutral) | compile ok (payload unsealed); compiled identity |
| `compile-readonly-with-command` | §8.3 L655 | readonly widget carrying a command (schema) | compile refused `profile-schema` |
| `compile-reference-empty-target-types` | §8.3 L655 | reference widget without targetTypes (schema) | compile refused `profile-schema` |
| `compile-ui-icon-unknown-glyph` | §8.3 L655; §2.4.1 L190 | UI icon names an undefined glyph | compile refused `profile-symbol` |
| `compile-ui-label-unknown-message` | §2.4.1 L190 | UI label names an undefined message | compile refused `profile-symbol` |
| `compile-ui-parameter-duplicate` | §2.4.1 L195; §8.3 L655 | UI map binds a parameter twice | compile refused `profile-ui-parameters` |
| `compile-ui-parameter-missing` | §2.4.1 L195; §8.3 L655 | UI map omits a required recipe parameter | compile refused `profile-ui-parameters` |
| `compile-ui-parameter-source-type` | §2.4.1 L195; §8.3 L655 | element parameter bound from source value | compile refused `profile-ui-parameters` |
| `compile-ui-parameter-unknown` | §2.4.1 L195; §8.3 L655 | UI map binds an undeclared parameter | compile refused `profile-ui-parameters` |
| `compile-upstream-duplicate-across-entries` | §8.3 L659 | one upstream ID mapped by two entries | compile refused `profile-symbol` |
| `compile-upstream-duplicate-within-entry` | §8.3 L659 | one upstream ID listed twice by one entry | compile refused `profile-symbol` |
| `copy-fragment-preorder` | §8.3 L657 | fragment in source document pre-order, not ID order; contained element dropped | ok x2 |
| `copy-fragment-read-only` | §8.3 L657; §10.1 L737 | copy returns a deduplicated pre-order fragment, no state change | ok x3; refused `operation-error` |
| `copy-unknown-id` | §8.3 L657; §2.2 L132 | copy of a missing ID; stale copy | refused `reference-dangling`, `operation-error` |
| `create-append-task` | §8.3 L649; §2.4 L163 | append creates task and link | ok x2 |
| `create-reference-then-connect` | §8.3 L651; §4.4 L408 | DataStore + DataStoreReference, then Association on connect (no DataInputAssociation) | ok x3 |
| `create-task-palette-grid` | §8.3 L649; §7.1 L538; §3.2 L284 | grid create: ServiceTask, same ID; C sets isExecutable false to true | ok x2 |
| `create-task-palette-neutral` | §8.3 L649; §2.4 L163; §3.2 L276-L282 | palette create with stable-id/1; C resets isExecutable true to false (complete/set entry) | ok x2 |
| `delete-includes-dependents` | §8.3 L653; §2.4 L171 | delete includes all declared dependent edges | ok x2 |
| `delete-refuses-dependents` | §8.3 L653; §2.4 L171 | delete refuses an unlisted dependent edge | ok x1; refused `reference-dangling` |
| `delete-unreferenced` | §8.3 L653; §2.4 L171 | delete of an unreferenced task | ok x2 |
| `field-clear-optional-reference` | §8.3 L659; §2.4 L166 | explicit remove-reference command; property absent | ok x2 |
| `field-display-edit-grid` | §8.3 L655; §2.2 L116 | display independent of storage, full Unicode upper case | ok x3 |
| `field-display-prefix-exact` | §2.2 L115; §8.3 L655 | stripPrefix only removes an exact prefix | ok x1 |
| `field-edit-restores-marker` | §8.3 L653 | edit restores the marker once | ok x2 |
| `field-empty-string-explicit` | §8.3 L659 | empty string stored, not omitted; draft warnings observed | ok x2 |
| `field-enum-validation` | §8.3 L659 | on-change validation equals submit validation (enum) | ok x5; refused `profile-type` |
| `field-listing-widgets` | §8.3 L653 | field records (value included) for text, multiline, readonly, reference, enum widgets | ok x7 |
| `field-not-editable` | §8.3 L653; §8.3 L649 | immutable, hidden, readonly and predicate-locked fields | ok x3; refused `profile-producer` |
| `field-reference-submits-ids` | §8.3 L659 | reference widget submits IDs; label and wrong type refused | ok x2; refused `reference-dangling`, `profile-type` |
| `field-unknown` | §2.4.1 L190; §8.3 L655 | unknown field or notion; unrecognized target notion; dangling target | ok x1; refused `profile-symbol`, `profile-type`, `reference-dangling` |
| `field-value-omitted-or-coerced` | §8.3 L659 | omitted value refused; null, number, Boolean not coerced | ok x1; refused `profile-ui-parameters`, `profile-type` |
| `field-visible-predicate` | §8.3 L653 | visible predicate exposes a field | ok x3 |
| `fixture-base` | §2.4.1 L191; §1.1 L28 | lot-5 effective base, its pin and its committed JCS bytes | derived values |
| `fixture-descriptors` | §8.1 L606; §2.1 L48 | lot-5 descriptor slice, its pin and its committed JCS bytes | derived values |
| `fixture-profile-grid` | §8.3 L649-L659; §7.1 L538 | grid lot-5 profile (quiet validation), digest, identity, bytes | derived values |
| `fixture-profile-neutral-lint` | §6.2 L474; §6.3 L493 | neutral lot-5 profile with the vendored validation records | derived values |
| `fixture-profile-neutral` | §8.3 L649-L659; §6.2 L468 | neutral lot-5 profile (quiet validation), digest, identity, bytes | derived values |
| `gate-external-creation` | §8.3 L651; §4.1 L364; §13 L910 | OPEN-EXTERNAL: external entry refused | ok x1; refused `profile-open` |
| `gate-reserved-n-creation` | §7.2 L554; §13 L917; §16 L1160 | OPEN-RESERVED-N: edit needing new supports refused by N (edit activation) | ok x1; refused `profile-open` |
| `gate-reserved-n-reuse` | §7.2 L552; §5.2 L440 | bound supports reused, edit commits | ok x2 |
| `history-batch-one-step` | §8.2 L632 | multi-command batch is one history step | ok x5 |
| `history-change-events` | §8.2 L633; §8.1 L606 | one event per commit/undo/redo with its report; none for refusal or no-op | ok x5; refused `profile-symbol` |
| `history-load-epoch` | §8.2 L643; §8.1 L584 | load starts a new history epoch | ok x3; refused `operation-error` |
| `history-noop-no-entry` | §8.2 L641 | no-op and empty batches add no history step | ok x6; refused `operation-error` |
| `history-refusal-preserves-state` | §8.2 L633 | refusal after a staged write leaves snapshot and history unchanged | ok x6; refused `profile-symbol` |
| `history-restore-bindings-presentation` | §8.2 L632; §7.2 L565; §8.1.1 L610 | support deletion with bindings and archived importedDi undone/redone byte-identically | ok x6 |
| `history-stale-revisions` | §8.2 L629; §3.1 L268 | stale baseRevision/expectedViewRevision refused before commands | ok x2; refused `operation-error` |
| `history-undo-redo-guards` | §8.1 L595-L596; §8.2 L629 | stale undo/redo refused, cursor kept | ok x3; refused `operation-error` |
| `history-undo-redo-roundtrip` | §8.2 L641; §8.1 L595-L596 | byte-identical undo/redo, redo not truncated | ok x10; refused `operation-error` |
| `io-set-explicit-selection` | §8.3 L651; §7.1 L547; §8.3 L653 | explicit set selection in the same batch; C once per batch | ok x2 |
| `io-set-selection-required` | §8.3 L651; §7.1 L547 | uncovered IO with two sets refused by C on the stage after a staged write | ok x1; refused `io-set-selection-required`, `operation-error` |
| `l10n-resolution-order` | §8.3 L659 | exact, fallback, stable key | ok x8 |
| `lifecycle-activation-descriptor-mismatch` | §8.1 L617 | activation with a differing descriptor package | ok x1; refused activate `descriptor-mismatch` |
| `lifecycle-dispose` | §8.1 L599 | dispose result and disposed-state refusals | ok x1; refused `canvas-disposed` |
| `lifecycle-not-loaded` | §10.1 L737; §8.1 L589 | operations before load (no echoed identity) | refused `document-not-loaded` |
| `lint-draft-integrity-refused` | §6.2 L474; §8.2 L631 | vendored validation: integrity error not downgraded in draft, atomic refusal | ok x1; refused `bpmnlint/no-disconnected`, `operation-error` |
| `lint-draft-warnings-commit` | §6.2 L474; §16 L1144; §10.1 L739 | vendored validation: draft warnings observed, edit commits | ok x2 |
| `lint-noop-correction-report` | §8.2 L641; §10.1 L739 | no-op with a correction notice, no history entry, no event | ok x2; refused `operation-error` |
| `lint-post-normalize-error-blocks` | §6.2 L481; §10.1 L735 | post-normalize unresolved error blocks with the rule code | ok x1; refused `task-name-missing` |
| `paste-batch-one-step` | §8.3 L653; §8.2 L631-L632 | intermediate state N would refuse, final state accepted: one normalization, one undo step | ok x4 |
| `paste-dangling-external-refused` | §8.3 L653; §2.2 L132 | paste with a dangling external ref refused; emptied artifacts kept | ok x3; refused `reference-dangling` |
| `paste-key-collision` | §8.3 L655; §3.2 L288 | same paste key collides; new key gets new IDs | ok x3; refused `id-collision` |
| `paste-normalize-refused` | §8.2 L631; §10.1 L735 | N refuses the staged paste; report holds the executed lint stage entries | ok x3; refused `fixture-duplicate-aid` |
| `paste-remap-preserves-external` | §8.3 L653; §3.2 L276 | paste remaps IDs and internal refs, keeps a valid external ref | ok x3 |
| `pick-field-states` | §8.3 L657; §10.1 L737 | immutable field offers nothing; non-reference, unknown, dangling, stale | ok x1; refused `profile-type`, `profile-symbol`, `reference-dangling`, `operation-error` |
| `pick-filter-sort` | §8.3 L657 | targetTypes filter, UTF-16 ID order | ok x1 |
| `pick-paging-bounds` | §8.3 L657; §2.1 L50 | unsafe, negative, Boolean, fractional paging refused | refused `profile-bounds` |
| `pick-paging` | §8.3 L657 | offset/limit pages | ok x5 |
| `pick-query-case-sensitive` | §8.3 L657 | case-sensitive literal substring | ok x4 |
| `pick-query-no-normalization` | §8.3 L657 | no Unicode normalization; astral substring | ok x4 |
| `pick-reference-ownership` | §8.3 L657 | same-owner candidates only; revalidation at commit | ok x4; refused `profile-type` |
| `replace-dependency-refused` | §8.3 L651; §2.4 L171 | conversion of a referenced element refused | ok x1; refused `reference-dangling` |
| `replace-preserves-id` | §8.3 L651 | same-type conversion keeps the ID, empty idMap | ok x2 |
| `replace-replacement-map` | §8.3 L651; §10.1 L753 | type change reports the replacement map (domain migration) | ok x2 |
| `surface-append-when` | §8.3 L649 | append: same predicate for listing and call | ok x3; refused `profile-producer` |
| `surface-connect-when` | §8.3 L649 | connect: same predicate for listing and call | ok x3; refused `profile-producer` |
| `surface-context-when` | §8.3 L649 | context: same predicate for listing and call | ok x3; refused `profile-producer` |
| `surface-delete-when` | §8.3 L649 | delete: same predicate for listing and call | ok x4; refused `profile-producer` |
| `surface-direct-edit-when` | §8.3 L649; §8.3 L657 | direct edit: refused then authorized call, entry-free report | ok x4; refused `profile-producer` |
| `surface-gesture-parameters` | §8.3 L655 | missing/extra sources, unknown members, missing context; explicit empty value with draft warnings | ok x2; refused `profile-ui-parameters` |
| `surface-handles-and-values` | §8.3 L655; §2.2 L132 | dangling handle; no scalar coercion; null refused | ok x1; refused `reference-dangling`, `profile-type` |
| `surface-palette-entries-grid` | §8.3 L659; §7.1 L538 | grid palette order | ok x1 |
| `surface-palette-entries-localized` | §8.3 L659 | labels: exact locale, fallback, no BCP 47 truncation, case-sensitive locale | ok x3 |
| `surface-palette-entries-order` | §8.3 L659; §8.3 L649 | groups by first appearance; order numeric then UTF-16 ID; hidden entry omitted | ok x1 |
| `surface-palette-when` | §8.3 L649 | palette: hidden entry refused programmatically | ok x2; refused `profile-producer` |
| `surface-paste-when` | §8.3 L649; §8.3 L657 | paste: copy grants no paste authority | ok x3; refused `profile-producer` |
| `surface-raw-recipe-command` | §8.3 L649; §8.2 L635 | bare recipe record and unknown command kind disabled | ok x1; refused `transaction-entry-unsupported` |
| `surface-replace-when` | §8.3 L649 | replace: same predicate for listing and call | ok x4; refused `profile-producer` |
| `surface-unknown-entry` | §2.4.1 L190 | unknown entry ID | ok x1; refused `profile-symbol` |
| `surface-unlisted-upstream` | §8.3 L659; §8.2 L635 | unlisted upstream entry disabled | ok x1; refused `transaction-entry-unsupported` |
| `surface-upstream-mapped` | §8.3 L659 | upstream command resolves to its entry (same result and report) | ok x2 |
| `twin-grid-fixture-commands` | §14.2 L954; §7.1 L538 | vendored grid commands through UI entries reproduce expected.completed and lint | ok x2 |
| `twin-neutral-fixture-commands` | §14.2 L954; §8.3 L649; §7.1 L538 | vendored neutral commands through UI entries reproduce expected.completed and lint | ok x2 |
| `tx-cancelled` | §8.1 L604; §8.2 L629 | cancellation before staging and after a first staged write | ok x1; refused `operation-cancelled`, `operation-error` |
| `tx-dispose-during-transaction` | §8.1 L619; §8.2 L635 | dispose during a batch commits nothing | refused `canvas-disposed` |
| `tx-reentrant-refused` | §8.2 L635 | re-entrant command refused; reads see the committed state | ok x2 |

### 12.1 Vendored JS cases (§9.1)

One row per vendored harness record (clauses from the JS clause records; the
status summary counts the results of the twin, compile outcome or trace).

| Case | DESIGN clause | Witness | Expected |
| --- | --- | --- | --- |
| `l3-tx-incremental-draft` | §8.2 L632-L641; §6.2 L474; §16 L1144; §7.1 L544; §8.1 L595-L596 | vendored JS lot-3 transaction script, incremental draft (headless sequence) | trace ok x11 |
| `lot5-connect-001-flow-programmatic` | §8.3 L649; §4 L347; §3.2 L276; §3.2 L278-L282; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS connect 001: flow programmatic | twin ok x1 |
| `lot5-connect-003-reference-link-programmatic` | §8.3 L651; §4 L353; §3.2 L276; §3.2 L278-L282; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS connect 003: reference link programmatic | twin ok x1 |
| `lot5-connect-005-item-input` | §8.3 L651; §4 L350; §7.1 L546; §3.2 L276; §3.2 L278-L282; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS connect 005: item input | twin ok x1 |
| `lot5-connect-006-item-output` | §8.3 L651; §4 L350; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS connect 006: item output | twin ok x1 |
| `lot5-connect-007-annotation-link` | §4 L354; §8.3 L651; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS connect 007: annotation link | twin ok x1 |
| `lot5-connect-008-reference-to-call` | §4 L353; §8.3 L651; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS connect 008: reference to call | twin ok x1 |
| `lot5-connect-009-ineligible-target-noop` | §2.4 L158; §4 L353; §8.2 L641; §10.1 L735; §10.1 L739 | vendored JS connect 009: ineligible target noop | twin ok x1 |
| `lot5-connect-011-flow-from-end` | §8.3 L649; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS connect 011: flow from end | twin refused `profile-producer` |
| `lot5-context-001-append-task-programmatic` | §8.3 L649; §8.3 L655; §2.4 L163; §3.2 L276; §3.2 L278-L282; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690; §10.1 L751; §6.2 L474; §6.4 L515 | vendored JS context 001: append task programmatic | twin ok x1 |
| `lot5-context-003-append-end` | §8.3 L649; §2.3 L143; §3.2 L276; §3.2 L278-L282; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS context 003: append end | twin ok x1 |
| `lot5-context-004-aid-attach` | §4 L354; §8.3 L653; §3.2 L276; §3.2 L278-L282; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS context 004: aid attach | twin ok x1 |
| `lot5-context-005-append-on-end` | §8.3 L649; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS context 005: append on end | twin refused `profile-producer` |
| `lot5-context-006-call-unlink` | §8.3 L659; §2.4 L165; §8.3 L653; §4 L356; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS context 006: call unlink | twin ok x1 |
| `lot5-context-007-call-unlink-noop` | §2.4 L158; §8.2 L641; §10.1 L735; §10.1 L739 | vendored JS context 007: call unlink noop | twin ok x1 |
| `lot5-delete-001-reference-with-links` | §8.3 L653; §2.4 L171; §4.4 L408; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS delete 001: reference with links | twin ok x1 |
| `lot5-delete-002-unconnected-task` | §8.3 L653; §2.4 L171; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS delete 002: unconnected task | twin ok x1 |
| `lot5-delete-003-outgoing-only` | §8.3 L653; §2.4 L171; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS delete 003: outgoing only | twin ok x1 |
| `lot5-delete-004-incoming-refused` | §8.3 L653; §2.4 L171; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS delete 004: incoming refused | twin refused `reference-dangling` |
| `lot5-delete-005-flow` | §8.3 L653; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS delete 005: flow | twin ok x1 |
| `lot5-delete-008-multi-atomic` | §2.4 L172; §8.2 L643; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS delete 008: multi atomic | twin refused `reference-dangling` |
| `lot5-delete-009-annotation-with-link` | §8.3 L653; §2.4 L171; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS delete 009: annotation with link | twin ok x1 |
| `lot5-delete-010-process-disabled` | §8.3 L649; §2.4 L174; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS delete 010: process disabled | twin refused `profile-producer` |
| `lot5-delete-011-last-element-keeps-empty-array` | §8.3 L653; §2.4 L171; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS delete 011: last element keeps empty array | twin ok x1 |
| `lot5-demo-001-acceptance-script` | §14.2 L954; §8.3 L649; §8.3 L651; §8.3 L653; §8.2 L632; §8.2 L641; §10.2 L803; §2.4 L163 | vendored JS demo 001: acceptance script | twin ok x11 |
| `lot5-fields-001-state-task` | §8.3 L653; §8.3 L655; §10.1 L737 | vendored JS fields 001: state task | twin ok x1 |
| `lot5-fields-002-state-task-fr` | §8.3 L653; §8.3 L655; §8.3 L659; §10.1 L737 | vendored JS fields 002: state task fr | twin ok x1 |
| `lot5-fields-003-state-aid` | §8.3 L653; §8.3 L655; §9.3 L702; §2.2 L115; §10.1 L737 | vendored JS fields 003: state aid | twin ok x1 |
| `lot5-fields-004-state-aid-no-space` | §8.3 L653; §8.3 L655; §2.2 L115; §9.3 L702; §10.1 L737 | vendored JS fields 004: state aid no space | twin ok x1 |
| `lot5-fields-005-state-note-leading-space` | §8.3 L653; §8.3 L655; §2.3 L146; §2.3 L152; §10.1 L737 | vendored JS fields 005: state note leading space | twin ok x1 |
| `lot5-fields-006-state-process` | §8.3 L653; §8.3 L655; §2.1 L79; §8.3 L659; §10.1 L737 | vendored JS fields 006: state process | twin ok x1 |
| `lot5-fields-007-state-call` | §8.3 L653; §8.3 L655; §8.3 L657; §10.1 L737 | vendored JS fields 007: state call | twin ok x1 |
| `lot5-fields-008-state-user-task` | §8.3 L653; §8.3 L655; §2.3 L154; §10.1 L737 | vendored JS fields 008: state user task | twin ok x1 |
| `lot5-fields-009-edit-task-name` | §8.3 L653; §8.3 L655; §8.3 L659; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS fields 009: edit task name | twin ok x1 |
| `lot5-fields-010-edit-situations-crlf` | §8.3 L653; §8.3 L655; §8.3 L659; §4.2 L387; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS fields 010: edit situations crlf | twin ok x1 |
| `lot5-fields-011-edit-empty-name` | §8.3 L653; §8.3 L655; §8.3 L659; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690; §10.1 L751; §6.2 L474; §6.4 L515 | vendored JS fields 011: edit empty name | twin ok x1 |
| `lot5-fields-012-edit-aid-body` | §8.3 L653; §8.3 L655; §8.3 L659; §9.3 L702; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS fields 012: edit aid body | twin ok x1 |
| `lot5-fields-013-edit-aid-body-typed-marker` | §8.3 L653; §8.3 L655; §8.3 L659; §9.3 L702; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS fields 013: edit aid body typed marker | twin ok x1 |
| `lot5-fields-014-edit-aid-no-space-keeps-evidence` | §8.3 L653; §8.3 L655; §8.3 L659; §9.3 L702; §4 L356; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS fields 014: edit aid no space keeps evidence | twin ok x1 |
| `lot5-fields-015-edit-call-target-keeps-evidence` | §8.3 L653; §8.3 L655; §8.3 L659; §8.3 L657; §4 L356; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS fields 015: edit call target keeps evidence | twin ok x1 |
| `lot5-fields-016-edit-process-kind` | §8.3 L653; §8.3 L655; §8.3 L659; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS fields 016: edit process kind | twin ok x1 |
| `lot5-fields-017-edit-reference-override` | §8.3 L653; §8.3 L655; §8.3 L659; §4.4 L408; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS fields 017: edit reference override | twin ok x1 |
| `lot5-fields-018-edit-store-title` | §8.3 L653; §8.3 L655; §8.3 L659; §4.4 L408; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS fields 018: edit store title | twin ok x1 |
| `lot5-fields-019-edit-no-op` | §8.3 L653; §8.3 L655; §8.3 L659; §8.2 L641; §10.1 L735; §10.1 L739 | vendored JS fields 019: edit no op | twin ok x1 |
| `lot5-fields-020-edit-call-target-wrong-type` | §8.3 L657; §8.3 L655; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS fields 020: edit call target wrong type | twin refused `profile-type` |
| `lot5-fields-021-edit-call-target-dangling` | §8.3 L657; §4.1 L378; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS fields 021: edit call target dangling | twin refused `reference-dangling` |
| `lot5-fields-022-edit-enum-not-a-choice` | §8.3 L659; §2.3 L145; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS fields 022: edit enum not a choice | twin refused `profile-type` |
| `lot5-fields-023-edit-readonly` | §8.3 L655; §8.3 L659; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS fields 023: edit readonly | twin refused `profile-producer` |
| `lot5-fields-024-edit-number-no-coercion` | §8.3 L659; §2.2 L114; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS fields 024: edit number no coercion | twin refused `profile-type` |
| `lot5-fields-027-candidates-all` | §8.3 L657; §2.2 L123; §10.1 L737 | vendored JS fields 027: candidates all | twin ok x1 |
| `lot5-fields-028-candidates-case` | §8.3 L657; §10.1 L737 | vendored JS fields 028: candidates case | twin ok x1 |
| `lot5-fields-029-candidates-case-miss` | §8.3 L657; §10.1 L737 | vendored JS fields 029: candidates case miss | twin ok x1 |
| `lot5-fields-030-candidates-normalization` | §8.3 L657; §10.1 L737 | vendored JS fields 030: candidates normalization | twin ok x1 |
| `lot5-fields-031-candidates-paging` | §8.3 L657; §10.1 L737 | vendored JS fields 031: candidates paging | twin ok x1 |
| `lot5-fields-032-candidates-astral` | §8.3 L657; §10.1 L737 | vendored JS fields 032: candidates astral | twin ok x1 |
| `lot5-fields-033-candidates-unknown-field` | §8.3 L657; §2.4.1 L190; §10.1 L737 | vendored JS fields 033: candidates unknown field | twin refused `profile-symbol` |
| `lot5-fields-034-state-call-locked` | §8.3 L653; §8.3 L655; §10.1 L737 | vendored JS fields 034: state call locked | twin ok x1 |
| `lot5-fields-035-state-call-hidden` | §8.3 L653; §8.3 L655; §10.1 L737 | vendored JS fields 035: state call hidden | twin ok x1 |
| `lot5-fields-036-state-choice-upper` | §8.3 L653; §8.3 L655; §2.2 L116; §10.1 L737 | vendored JS fields 036: state choice upper | twin ok x1 |
| `lot5-fields-037-state-aid-link-anchor` | §8.3 L653; §8.3 L655; §10.1 L737 | vendored JS fields 037: state aid link anchor | twin ok x1 |
| `lot5-fields-038-state-no-fields` | §8.3 L653; §8.3 L655; §10.1 L737 | vendored JS fields 038: state no fields | twin ok x1 |
| `lot5-fields-039-check-enum` | §8.3 L659; §8.3 L655; §10.1 L737 | vendored JS fields 039: check enum | twin ok x3 |
| `lot5-fields-040-check-reference` | §8.3 L659; §8.3 L657; §10.1 L737 | vendored JS fields 040: check reference | twin ok x4 |
| `lot5-fields-041-check-text` | §8.3 L659; §2.2 L114; §10.1 L737 | vendored JS fields 041: check text | twin ok x3 |
| `lot5-fields-042-check-denied` | §8.3 L659; §8.3 L653; §8.3 L649; §10.1 L737 | vendored JS fields 042: check denied | twin ok x3 |
| `lot5-fields-043-check-unknown-field` | §8.3 L659; §2.4.1 L190; §10.1 L737 | vendored JS fields 043: check unknown field | twin refused `profile-symbol` |
| `lot5-fields-044-check-unknown-target` | §8.3 L659; §2.2 L132; §10.1 L737 | vendored JS fields 044: check unknown target | twin refused `reference-dangling` |
| `lot5-fields-045-check-stale-revision` | §8.3 L659; §8.2 L629; §10.1 L737 | vendored JS fields 045: check stale revision | twin refused `operation-error` |
| `lot5-fields-046-edit-locked-target` | §8.3 L653; §8.3 L649; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS fields 046: edit locked target | twin refused `profile-producer` |
| `lot5-fields-047-edit-hidden-target` | §8.3 L653; §8.3 L649; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS fields 047: edit hidden target | twin refused `profile-producer` |
| `lot5-fields-048-edit-unknown-field` | §2.4.1 L190; §8.3 L655; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS fields 048: edit unknown field | twin refused `profile-symbol` |
| `lot5-fields-049-edit-unknown-target` | §8.3 L655; §2.2 L132; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS fields 049: edit unknown target | twin refused `reference-dangling` |
| `lot5-fields-050-edit-value-omitted` | §8.3 L655; §8.3 L659; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS fields 050: edit value omitted | twin refused `profile-ui-parameters` |
| `lot5-fields-051-edit-boolean-no-coercion` | §8.3 L659; §2.2 L114; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS fields 051: edit boolean no coercion | twin refused `profile-type` |
| `lot5-fields-052-edit-aid-link-anchor` | §8.3 L653; §8.3 L655; §8.3 L659; §8.3 L657; §2.4 L166; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS fields 052: edit aid link anchor | twin ok x1 |
| `lot5-fields-053-edit-aid-link-other-process` | §8.3 L657; §2.4 L166; §4 L358; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS fields 053: edit aid link other process | twin refused `profile-type` |
| `lot5-fields-054-candidates-anchor-ownership` | §8.3 L657; §4 L358; §10.1 L737 | vendored JS fields 054: candidates anchor ownership | twin ok x1 |
| `lot5-fields-055-candidates-locked-field` | §8.3 L657; §8.3 L653; §10.1 L737 | vendored JS fields 055: candidates locked field | twin ok x1 |
| `lot5-fields-056-candidates-hidden-field` | §8.3 L657; §8.3 L653; §10.1 L737 | vendored JS fields 056: candidates hidden field | twin ok x1 |
| `lot5-fields-057-candidates-not-reference` | §8.3 L657; §10.1 L737 | vendored JS fields 057: candidates not reference | twin refused `profile-type` |
| `lot5-fields-058-candidates-negative-offset` | §8.3 L657; §2.4.1 L189; §10.1 L737 | vendored JS fields 058: candidates negative offset | twin refused `profile-bounds` |
| `lot5-fields-059-candidates-fractional-limit` | §8.3 L657; §2.4.1 L189; §10.1 L737 | vendored JS fields 059: candidates fractional limit | twin refused `profile-bounds` |
| `lot5-fields-060-candidates-boolean-limit` | §8.3 L657; §2.4.1 L189; §10.1 L737 | vendored JS fields 060: candidates boolean limit | twin refused `profile-bounds` |
| `lot5-fields-061-candidates-unknown-target` | §8.3 L657; §2.2 L132; §10.1 L737 | vendored JS fields 061: candidates unknown target | twin refused `reference-dangling` |
| `lot5-fields-062-candidates-stale-revision` | §8.3 L657; §10.1 L737 | vendored JS fields 062: candidates stale revision | twin refused `operation-error` |
| `lot5-fields-063-commit-time-invalidation` | §8.3 L657; §2.4 L166 | vendored JS fields 063: commit time invalidation | twin ok x2; refused `reference-dangling` |
| `lot5-history-001-refusal-leaves-no-entry` | §8.2 L633; §8.2 L641; §3.1 L268; §10.1 L735 | vendored JS history 001: refusal leaves no entry | twin ok x3; refused `reference-dangling` |
| `lot5-history-002-noop-leaves-no-entry` | §8.2 L641; §8.1 L606 | vendored JS history 002: noop leaves no entry | twin ok x3 |
| `lot5-history-003-entry-point-chain` | §8.2 L632; §8.2 L641; §8.3 L649; §8.3 L651; §3.2 L276 | vendored JS history 003: entry point chain | twin ok x15 |
| `lot5-history-004-insertion-key-reuse` | §3.2 L288; §8.3 L655 | vendored JS history 004: insertion key reuse | twin ok x2; refused `id-collision` |
| `lot5-history-005-paste-key-reuse` | §3.2 L288; §8.3 L653 | vendored JS history 005: paste key reuse | twin ok x1; refused `id-collision` |
| `lot5-history-012-empty-batch-noop` | §8.2 L641; §10.1 L735 | vendored JS history 012: empty batch noop | twin ok x1 |
| `lot5-palette-001-task-programmatic` | §8.3 L649; §8.3 L655; §8.3 L659; §2.4 L163; §3.2 L276; §3.2 L278-L282; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690; §10.1 L751; §6.2 L474; §6.4 L515 | vendored JS palette 001: task programmatic | twin ok x1 |
| `lot5-palette-003-user-task` | §8.3 L649; §8.3 L655; §2.4 L163; §3.2 L276; §3.2 L278-L282; §2.3 L143; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690; §10.1 L751; §6.2 L474; §6.4 L515 | vendored JS palette 003: user task | twin ok x1 |
| `lot5-palette-004-start` | §8.3 L649; §8.3 L655; §2.4 L163; §3.2 L276; §3.2 L278-L282; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS palette 004: start | twin ok x1 |
| `lot5-palette-005-end` | §8.3 L649; §8.3 L655; §2.4 L163; §3.2 L276; §3.2 L278-L282; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS palette 005: end | twin ok x1 |
| `lot5-palette-006-gateway` | §8.3 L649; §8.3 L655; §2.4 L163; §3.2 L276; §3.2 L278-L282; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS palette 006: gateway | twin ok x1 |
| `lot5-palette-007-call` | §8.3 L649; §8.3 L655; §2.4 L163; §3.2 L276; §3.2 L278-L282; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS palette 007: call | twin ok x1 |
| `lot5-palette-008-reference` | §8.3 L651; §4 L352; §4.4 L408; §2.4 L163; §3.2 L276; §3.2 L278-L282; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS palette 008: reference | twin ok x1 |
| `lot5-palette-009-item` | §8.3 L651; §4 L349; §2.4 L163; §3.2 L276; §3.2 L278-L282; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS palette 009: item | twin ok x1 |
| `lot5-palette-010-aid` | §8.3 L653; §9.3 L702; §2.4 L163; §3.2 L276; §3.2 L278-L282; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS palette 010: aid | twin ok x1 |
| `lot5-palette-013-input-set-b-programmatic` | §8.3 L651; §7.1 L547; §1.1 L32; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS palette 013: input set b programmatic | twin ok x1 |
| `lot5-palette-015-input-missing-target` | §8.3 L655; §2.4.1 L195; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS palette 015: input missing target | twin refused `profile-ui-parameters` |
| `lot5-palette-016-disabled-owner` | §8.3 L649; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS palette 016: disabled owner | twin refused `profile-producer` |
| `lot5-palette-017-unknown-entry` | §8.3 L659; §2.4.1 L190; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS palette 017: unknown entry | twin refused `profile-symbol` |
| `lot5-palette-018-final-only-report` | §8.2 L631; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS palette 018: final only report | twin ok x1 |
| `lot5-palette-019-contrast-theme-same-tree` | §8.3 L649; §3.1 L264; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690; §10.1 L751; §6.2 L474; §6.4 L515 | vendored JS palette 019: contrast theme same tree | twin ok x1 |
| `lot5-palette-020-upstream-command-mapped` | §8.3 L659; §3.2 L276; §3.2 L278-L282; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690; §10.1 L751; §6.2 L474; §6.4 L515 | vendored JS palette 020: upstream command mapped | twin ok x1 |
| `lot5-palette-021-unlisted-upstream` | §8.3 L659; §8.2 L635; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS palette 021: unlisted upstream | twin refused `transaction-entry-unsupported` |
| `lot5-palette-022-bare-recipe-command` | §8.2 L635; §8.3 L657; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS palette 022: bare recipe command | twin refused `transaction-entry-unsupported` |
| `lot5-palette-023-unknown-member` | §8.3 L655; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS palette 023: unknown member | twin refused `profile-ui-parameters` |
| `lot5-palette-024-extra-source` | §8.3 L655; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS palette 024: extra source | twin refused `profile-ui-parameters` |
| `lot5-palette-025-non-string-handle` | §8.3 L655; §2.2 L113; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS palette 025: non string handle | twin refused `profile-type` |
| `lot5-palette-026-dangling-handle` | §8.3 L655; §2.2 L113; §2.2 L132; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS palette 026: dangling handle | twin refused `reference-dangling` |
| `lot5-palette-027-null-value` | §8.3 L655; §8.3 L659; §2.2 L113; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS palette 027: null value | twin refused `profile-type` |
| `lot5-palette-028-number-value` | §8.3 L659; §2.2 L114; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS palette 028: number value | twin refused `profile-type` |
| `lot5-palette-029-input-loose-two-sets` | §7.1 L547; §8.3 L651; §8.2 L631; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS palette 029: input loose two sets | twin refused `io-set-selection-required` |
| `lot5-palette-030-cancelled-before-call` | §8.1 L604; §8.2 L629; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS palette 030: cancelled before call | twin refused `operation-cancelled` |
| `lot5-paste-001-copy-task` | §8.3 L657; §10.1 L737 | vendored JS paste 001: copy task | twin ok x1 |
| `lot5-paste-002-copy-group` | §8.3 L657; §10.1 L737 | vendored JS paste 002: copy group | twin ok x1 |
| `lot5-paste-003-paste-task` | §8.3 L653; §2.4 L174; §3.2 L288; §3.2 L276; §3.2 L278-L282; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS paste 003: paste task | twin ok x1 |
| `lot5-paste-005-paste-group` | §8.3 L653; §2.4 L174; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS paste 005: paste group | twin ok x1 |
| `lot5-paste-006-paste-reference-shared-store` | §8.3 L653; §4.4 L408; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS paste 006: paste reference shared store | twin ok x1 |
| `lot5-paste-007-paste-cross-document-dangling` | §8.3 L653; §2.2 L132; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS paste 007: paste cross document dangling | twin refused `reference-dangling` |
| `lot5-paste-008-paste-batch-one-pass` | §8.3 L653; §8.2 L631; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690; §10.1 L751; §6.2 L474; §6.4 L515 | vendored JS paste 008: paste batch one pass | twin ok x1 |
| `lot5-paste-009-paste-into-task` | §8.3 L649; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS paste 009: paste into task | twin refused `profile-producer` |
| `lot5-paste-011-copy-stale-revision` | §8.3 L657; §10.1 L737; §8.2 L629 | vendored JS paste 011: copy stale revision | twin refused `operation-error` |
| `lot5-paste-012-copy-unknown-id` | §8.3 L657; §10.1 L737; §2.2 L132 | vendored JS paste 012: copy unknown id | twin refused `reference-dangling` |
| `lot5-paste-013-copy-definitions-root` | §8.3 L657; §10.1 L737; §2.4 L174 | vendored JS paste 013: copy definitions root | twin refused `profile-type` |
| `lot5-paste-014-paste-then-edit-same-batch` | §8.3 L653; §8.2 L631; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS paste 014: paste then edit same batch | twin ok x1 |
| `lot5-paste-015-paste-call-keeps-evidence` | §8.3 L653; §4 L356; §3.2 L288; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS paste 015: paste call keeps evidence | twin ok x1 |
| `lot5-replace-001-task-to-user-programmatic` | §8.3 L651; §2.4 L163; §2.4 L171; §2.4.1 L182; §3.2 L276; §3.2 L278-L282; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690; §10.1 L753 | vendored JS replace 001: task to user programmatic | twin ok x1 |
| `lot5-replace-003-user-to-task` | §8.3 L651; §2.3 L143; §2.4 L171; §3.2 L276; §3.2 L278-L282; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690; §10.1 L753 | vendored JS replace 003: user to task | twin ok x1 |
| `lot5-replace-004-exact-type-refusal` | §8.3 L649; §2.3 L143; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS replace 004: exact type refusal | twin refused `profile-producer` |
| `lot5-replace-005-reference-to-item` | §8.3 L651; §4 L349; §4 L352; §4.4 L408; §2.4 L171; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS replace 005: reference to item | twin ok x1 |
| `lot5-replace-006-reference-to-item-linked` | §8.3 L651; §2.4 L171; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS replace 006: reference to item linked | twin refused `reference-dangling` |
| `lot5-replace-007-referenced-task-refused` | §8.3 L651; §2.4 L171; §2.4.1 L182; §8.2 L633; §10.1 L735; §10.1 L739 | vendored JS replace 007: referenced task refused | twin refused `reference-dangling` |
| `lot5-replace-008-note-to-aid-same-type` | §8.3 L651; §9.3 L702; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690 | vendored JS replace 008: note to aid same type | twin ok x1 |
| `lot5-surfaces-001-palette-plain-en` | §8.3 L649; §8.3 L655; §8.3 L659; §10.1 L737 | vendored JS surfaces 001: palette plain en | twin ok x2 |
| `lot5-surfaces-002-palette-contrast-en` | §8.3 L649; §3.1 L264; §9.2 L694; §8.3 L659; §10.1 L737 | vendored JS surfaces 002: palette contrast en | twin ok x2 |
| `lot5-surfaces-003-palette-locale-fr` | §8.3 L649; §8.3 L659; §10.1 L737 | vendored JS surfaces 003: palette locale fr | twin ok x2 |
| `lot5-surfaces-004-palette-locale-fr-ca` | §8.3 L649; §8.3 L659; §10.1 L737 | vendored JS surfaces 004: palette locale fr ca | twin ok x2 |
| `lot5-surfaces-005-element-task` | §8.3 L649; §2.3 L143; §8.3 L651; §8.3 L659; §10.1 L737 | vendored JS surfaces 005: element task | twin ok x6 |
| `lot5-surfaces-006-element-user-task` | §8.3 L649; §2.3 L143; §8.3 L659; §10.1 L737 | vendored JS surfaces 006: element user task | twin ok x6 |
| `lot5-surfaces-007-element-end` | §8.3 L649; §8.3 L659; §10.1 L737 | vendored JS surfaces 007: element end | twin ok x6 |
| `lot5-surfaces-008-element-reference` | §8.3 L649; §8.3 L651; §8.3 L659; §10.1 L737 | vendored JS surfaces 008: element reference | twin ok x6 |
| `lot5-surfaces-009-element-annotation` | §8.3 L649; §2.3 L141; §8.3 L653; §8.3 L659; §10.1 L737 | vendored JS surfaces 009: element annotation | twin ok x6 |
| `lot5-surfaces-010-element-call` | §8.3 L649; §8.3 L659; §10.1 L737 | vendored JS surfaces 010: element call | twin ok x6 |
| `lot5-surfaces-013-compile-duplicate-upstream` | §8.3 L659; §2.4.1 L190; §2.4.1 L182; §10.1 L737 | vendored JS surfaces 013: compile duplicate upstream | compile refused `profile-symbol` |
| `lot5-surfaces-014-compile-missing-fallback-text` | §8.3 L659; §2.4.1 L190; §2.4.1 L182; §10.1 L737 | vendored JS surfaces 014: compile missing fallback text | compile refused `profile-symbol` |
| `lot5-twin-001-assignable-rule-user-task` | §2.3 L143; §1.1 L32; §14.3 L963; §8.2 L632; §8.2 L633; §8.2 L641; §8.1 L606; §10.1 L735; §10.1 L739; §9.2 L690; §10.1 L751; §6.2 L474; §6.4 L515 | vendored JS twin 001: assignable rule user task | twin ok x1 |

## 13. Not covered

- Browser gestures, pointer capture, drag coalescing, DI-only drag/resize/
  reconnect, placement intent and multi-page rollback (OPEN-HOOK, canvas, §8.2
  L637-L639); theme switching and snapshot restoration (`setTheme`,
  `restoreSnapshot`); navigation index (§8.1 L623); read-only mode (§8.1 L619).
- Every layout/geometry effect of a command (lot 4): presentation members other
  than an explicitly loaded `importedDi` are compared relationally only.
- `rawStandardFindings` record shape where standard rules run (unsealed
  `raw-lint-transport`); `repairable` pre-normalize errors continued by N with a
  `corrected` disposition (no fixture rule is classified `repairable`).
- Activation or load with a different profile identity (§3.3 corpus), the import
  lint stage at load and explicit migration plans (migration lot).
- Internal items with native data associations and ports, reference↔item
  conversion of DataObjectReference, multiple-reference sharing (§8.3 L651,
  §4.4); external-call encoding (OPEN-EXTERNAL).
- `profile-ambiguous-notion` in `check_field`/`query_references`, UI entries naming
  recipes of phases other than create/edit/reference/convert, unknown
  `unsubscribe` IDs, listener re-entrancy and load events.
- Global versus per-surface group first appearance (§4.2).
- Visual placement in a reference-band region (§8.3 L651: never a native
  parent change).
- `unsubscribe`, load-origin events, linear-history redo discard after a new
  batch (§4.8 step 12, normative but not sealed), selection preservation (no
  headless selection API) and unexpected internal exceptions mapped to
  `operation-error` after rollback (§8.1 L604, needs fault injection).
- Closed by the block-B parity sync: the JS-only lot-5 cases marked "add to py"
  by the harmonization (programmatic surfaces, palette, context, connect,
  replace, delete, fields and paste cases, history-001…005, the assignable-rule
  twin and the headless steps of the owner demo script) and the lot-3 headless
  script are vendored (§9.1, §12.1); their execution by the headless runner is
  harness support for the code job and is not run by the seal test.
- Cross-runtime execution: JS→Python→JS transport and the twin canvas command
  artifacts of §14.3 need the conductor's joint run over `parity/`.
