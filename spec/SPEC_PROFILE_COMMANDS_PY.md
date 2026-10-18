# SPEC PROFILE COMMANDS PY — headless commands, fields and transactions (lot 5, Python part)

Status: binding contract for the lot-5 Python part of `bpmn_io.profile` (target
0.3.0, no version bump in block B). It produces no production code: it binds
DESIGN R3.3 (SHA-256
`48139f5fd5bd789eacbf271081a95432c54d8361b1e52404e3443a25fa65782f`) §8.3, the
headless lifecycle of §8.1 and the parts of the §8.2 transaction adapter that
apply without a browser, together with the sections they rely on (§2.2, §2.4,
§2.4.1, §3.1, §3.2, §5.1, §7.1, §7.2, §10.1, §13, §16). The sealed expectations
live in `tests/profile_commands/expected/` (pinned by `MANIFEST.sha256`, checked by
`tests/profile_commands/test_expected_seal.py`). A code job implements against
them and never edits them; if a sealed value disagrees with the DESIGN, the code
job keeps it, adds an `xfail(strict=True)` test naming the DESIGN line and the
expectation file, and reports it.

Signatures follow `spec/SPEC_PROFILE_MECHANISM_PY.md` (snake_case operations,
DESIGN wire field names, closed `PureResult`/`Result` unions). Lot 3
(`plan_recipe`, `apply_plan`, `complete`, `normalize`) is consumed by signature
only; lot 4 (layout, R, `viewRevision` digests) is consumed through
`get_snapshot` only. Every sealed outcome below is constructed so that it does
not depend on a lot-3 or lot-4 sealed value: C and N of the fixture profiles
only set `isExecutable`, place tasks and (gate cases only) ensure supports,
which the vendored contract fixtures already pin.

## 1. Module layout

New private modules under `src/bpmn_io/profile/` (no change to the literal
ports pinned by `UPSTREAM.toml`, stdlib only):

| Module | Content |
| --- | --- |
| `_ui.py` | compile-time UI and field rules (§6), compiled surface/field/message index attached to `CompiledProfile`, called by `compile_profile` between CR-09 and CR-11 |
| `_commands.py` | command records, surface/upstream/field resolution, gesture parameter binding, value typing, paste fragment compilation, replacement map |
| `_transaction.py` | guard states, detached stage, C/N pipeline, OPEN-RESERVED-N gate, no-op detection, history entries |
| `_queries.py` | `list_entries`, `list_fields`, `check_field`, `query_references`, `copy`, `localize` |
| `_bridge.py` | `HeadlessBridge` extended with the methods of §2 |

Public names: `bpmn_io.profile.localize` (new) and the new `HeadlessBridge`
methods. `CompiledProfile` gains the compiled UI index and its §5.1 profile
identity record (attribute names are private to the code job; if lot 3 already
exposes the identity record, lot 5 reuses it).

## 2. Signatures and errata

All bridge methods are synchronous (async-to-sync mapping of DESIGN §8.1) and
never raise for an expected refusal: they return the closed union named below.

| DESIGN ABI | Python | Inputs → payload |
| --- | --- | --- |
| `createBpmnCanvas` | `create_bridge(context=None)` | unchanged |
| `setDefinitions` | `set_definitions(envelope, *, expected_revision=None, codec=None, imported_di=None) -> Result` | unchanged signature; **erratum E1**: a load starts a new history epoch (undo and redo stacks cleared, DESIGN §8.2 L643) instead of pushing the previous envelope |
| `activateBusinessProfile` | `activate_business_profile(compiled, explicit_migration_plan=None) -> Result` (new) | payload `{envelope, semanticRevision, viewRevision, historyEpoch}` |
| `applyCommands` | `apply_commands(*, base_revision, expected_view_revision, commands, transaction_id, signal=None, codec=None) -> Result` | **erratum E2**: `expected_view_revision: str` and `transaction_id: str` become required keywords (DESIGN L587); payload `{envelope, semanticRevision, viewRevision, transactionId, changed}` (DESIGN L588); `signal: Callable[[], bool] \| None` is the sync form of the DESIGN `signal?`; `codec` is kept and unused by lot 5 |
| `getDefinitions` / `getSnapshot` | `get_definitions()` / `get_snapshot()` | unchanged |
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

Operation names in `Result` and `Report/2`: `setDefinitions`,
`activateBusinessProfile`, `applyCommands`, `getDefinitions`, `getSnapshot`,
`undo`, `redo`. `PureResult` methods carry no operation name (DESIGN §10.1 L737:
read-only reference query/copy, subscription management and disposal are
`PureResult`).

## 3. Closed shapes

### 3.1 Command records (`commands` items)

Each command is one JSON object with exactly one discriminator and gesture
sources:

~~~text
{"entry": <UI entry id>    | "upstream": <upstream entry id> | "field": <field id>,
 "owner"?: <element id>, "target"?: <element id>, "source"?: <element id>,
 "value"?: <string|number|boolean>, "key"?: <string>, "fragment"?: <Fragment>}
~~~

- `entry` names a profile UI entry; `upstream` names an upstream editor entry ID
  resolved through `upstreamEntries` (§8.3 L659); `field` names a field of a
  notion recognized for `target`.
- A record without exactly one discriminator (for example a bare
  `{"recipe", "parameters"}` command) is an unadapted entry:
  `transaction-entry-unsupported` (DESIGN §8.2 L635, L637). Every mutation of
  the headless bridge therefore passes through a UI entry or a field.
- Any other key is an ambient parameter: `profile-ui-parameters` (L655).
- The **subject** of a surface command is the handle its `ui.when` sees as
  `self`: `owner` for palette and paste, `target` for context, replace, delete
  and direct-edit, `source` for append and connect. The subject of a field
  command is `target`.
- A command must supply exactly the subject plus every source bound by the
  entry or field parameter map, plus `fragment` iff the surface is `paste`;
  a missing or an extra source refuses `profile-ui-parameters` (L655).
- `value` is the typed submitted value (never `null`); `key` is the
  transaction-scoped insertion key; both are supplied by the caller.

### 3.2 Fragment (copy payload, paste input)

~~~text
{"fragmentVersion": "1", "sourceRevision": <semanticRevision at copy>,
 "elements": [{"property": <containment property in the original parent>,
               "element": <deep, DI-free copy of the native subtree>}]}
~~~

`elements` holds the requested ID-bearing elements, deduplicated, without
elements contained in another requested element, ordered by UTF-16 ID.

### 3.3 Payloads

| Operation | Payload (closed) |
| --- | --- |
| `list_entries` | `{revision, surface, groups: [{group, entries: [{id, label: {key, text}, icon: {theme, glyph}, order, upstreamEntries}]}]}` |
| `list_fields` | `{revision, targetId, fields: [{notion, field, widget, path, label: {key, text}, message: {key, text}, present, display?, mutable, choices, targetTypes}]}` |
| `check_field` | `{revision, valid: true}` or `{revision, valid: false, code, messageKey}` |
| `query_references` | `{candidates: [{id, type, label}], revision}` |
| `copy` | the fragment of §3.2 |
| `localize` | `{key, text, source}` with `source` one of `exact`, `fallback`, `key` |
| change event | `{envelope, semanticRevision, viewRevision, transactionId, origin, report}` (DESIGN L606), `origin` one of `load`, `command`, `undo`, `redo` in lot 5 |

`display` is present iff `present` is true. `mutable` is the evaluated
`mutable` predicate, and false for a readonly widget or a field without
command. `revision` is the current `semanticRevision` (equal to the supplied
`base_revision`).

## 4. Semantics

### 4.1 Activation

`activate_business_profile` requires a loaded envelope. The descriptor pins of
the bridge context (`{id, version, sha256}` of each package) must equal the
compiled profile descriptor pins, otherwise `descriptor-mismatch` (DESIGN L617).
The envelope `profileIdentity` must equal the compiled identity; a difference
is decided by the §3.3 matrix (`check_compatibility`) and never migrates
silently (L615). A non-null `explicit_migration_plan` is the migration lot's
contract and is refused `operation-error` until that lot binds it. Success runs
no C/N, clears history, increments the session-local `historyEpoch` (excluded
from parity, DESIGN §3.1 L268) and emits no change event.

### 4.2 Surfaces and authorization (DESIGN §8.3 L649, L659)

- An entry is visible in `list_entries` and authorized in `apply_commands` iff
  its `when` predicate is true with bindings `root` and `self` = subject; the
  same evaluation serves both, and a programmatic call of an entry whose `when`
  is false refuses `profile-producer` (the DESIGN names no code; L649 makes this
  evaluation the security/producer boundary).
- `list_entries` keeps the entries of one surface (one of the eight schema
  surfaces, otherwise `profile-type`) whose `when` holds, groups them in the
  order of first appearance of each group in the profile `ui` array, omits
  empty groups and sorts entries by numeric `order`, then UTF-16 `id`. Sealed
  listings never distinguish first appearance in the whole array from first
  appearance among the entries of the listed surface.
- An `upstream` ID maps to the unique entry listing it; an unlisted upstream ID
  refuses `transaction-entry-unsupported` (L659: unlisted create/append/connect/
  replace entries are disabled; every headless upstream command is a mutation).
- Keyboard gestures have no separate command form: they are the canonical
  surface command (L657). `copy` evaluates no `ui.when` and grants no paste
  authorization (L657).

### 4.3 Parameter binding and typing (DESIGN §8.3 L655, L659)

- Each `{name, source}` binding feeds recipe parameter `name` from the command
  source: `owner`, `target`, `source` give element IDs (validated handles),
  `value` the submitted value, `key` the insertion key.
- Handles must be IDs of ID-bearing elements present on the stage, otherwise
  `reference-dangling`; a non-string handle refuses `profile-type`.
- A bound value must match the recipe parameter type without coercion:
  `string` ↔ str, `number` ↔ finite int/float that is not a Boolean, `boolean` ↔
  bool; `null` is never accepted; otherwise `profile-type`.
- Field widgets add: `enum` — the value must equal one choice `value` (JSON
  equality, a choice `name` is not a value); `reference` — the value is an ID
  (not a label): missing element `reference-dangling`, type outside
  `targetTypes` or outside the effective reference ownership of §4.6
  `profile-type`. These checks run on change (`check_field`) and again at commit.

### 4.4 Fields (DESIGN §8.3 L653, L655, L659)

- A field applies to `target` when a notion recognized for `target` (profile
  notion order) declares it; an unknown field ID refuses `profile-symbol`, the
  same field ID declared by two recognized notions refuses
  `profile-ambiguous-notion`. `list_fields` returns the visible fields of the
  recognized notions in profile notion order, then field declaration order; a
  target without recognized notion or fields yields `fields: []`.
- A hidden field (`visible` false), an immutable field (`mutable` false), a
  readonly widget or a field without command refuses `profile-producer` on
  edit; `check_field` reports the same code with `valid: false`.
- `display` is the field `display` Value when declared (for example
  `stripPrefix`, `case`), otherwise the raw stored value at `path` (scalar,
  reference ID or ID array); it never writes storage. The edit recipe restores
  the configured marker exactly once (`concat` of the literal marker and the
  submitted body).
- The empty string is stored as an explicit empty string; omitting `value`
  refuses `profile-ui-parameters`. Clearing an optional reference is an explicit
  remove-reference command (an entry whose recipe uses `assignRef` mode
  `remove`); the property becomes absent, never `null`.

### 4.5 Creation, reference link, IO sets, replace, delete (DESIGN §8.3 L651, L653)

- `create` appends the new element to the end of its containment array (no
  position field exists); removing elements keeps an emptied containment array.
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
  `report.idMap` (the DESIGN replacement map, L651; `idMap.domain` is closed to
  `migration|export`, DESIGN L753). Other convert shapes are not covered.
- The `remove` action computes the inbound closure first; a closure larger than
  the declared dependents with `refuseIfReferenced` refuses
  `reference-dangling` (the DESIGN names no code; the refused result would leave
  a dangling reference, DESIGN §2.2 L132). `includeDeclared` removes the target
  and its declared dependents together.

### 4.6 Reference picking (DESIGN §8.3 L657)

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

### 4.7 Paste (DESIGN §8.3 L653, L655; §3.2 L276-L288)

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

### 4.8 Transaction pipeline (DESIGN §8.2)

States `idle → staging → applying → idle`, plus `restoring` for undo/redo. For
`apply_commands`:

1. Reject disposed, re-entrant (state not `idle`) and not-loaded calls; require
   an active business profile; validate argument types.
2. Acquire the guard (state `staging`); from here every caller callback runs
   with the guard held. Poll `signal` (cancellation → `operation-cancelled`).
3. Compare `base_revision` with the current `semanticRevision` and
   `expected_view_revision` with the current `viewRevision`.
4. An empty `commands` list is a no-op (`changed: false`, no C/N).
5. Stage a deep copy of the envelope and presentation. Apply the commands in
   order, each validated against the stage left by the previous ones
   (`plan_recipe`/`apply_plan` under the editor actor); poll `signal` after each
   command.
6. Run C once (`complete`), then N once (`normalize`) on the stage; a refusal
   from either passes through with its code unchanged.
7. OPEN-RESERVED-N gate (§5): a support binding `(ownerId, role)` present after N
   but absent before N refuses `profile-open`.
8. Poll `signal`; disposal during the transaction refuses `canvas-disposed` and
   commits nothing.
9. If the staged tree, bindings and presentation equal the committed ones, return
   `changed: false` with the current revisions and no history entry (DESIGN
   L641).
10. Commit (state `applying`): one history entry `{transactionId, before, after}`
    and one change event with origin `command`, delivered after the guard is
    released; a committed batch after an undo discards the redo entries.

Getters and queries called during a transaction return the last committed state
(the stage is detached). Any other entry (`apply_commands`, `undo`, `redo`,
`set_definitions`, `activate_business_profile`) refuses `transaction-reentrant`.
Lint stages of the §6.2 edit row are not run by `apply_commands` in lot 5
(§9); their findings never decide a lot-5 outcome.

### 4.9 History

`undo`/`redo` check disposal, re-entrancy, loading, then `expected_revision` and
`expected_view_revision` (`operation-error` when stale), then the presence of an
entry (`operation-error` when there is nothing to undo or redo). They restore
the stored before/after state exactly (state `restoring`): no recipe, no C/N, no
ID computation, no redo truncation. Each emits one change event whose
`transactionId` is the entry's. A refused batch leaves history and snapshot
byte-identical.

### 4.10 Localization (DESIGN §8.3 L659)

For a profile message: the text named exactly `locale` (`source: exact`), else
the text named `policies.localeFallback` (`source: fallback`). For any other key
(for example a library diagnostic key): the key itself (`source: key`). Locale
names compare exactly: no case folding, no BCP 47 truncation.

## 5. Refusal codes and precedence

| Operation | Order of checks → code |
| --- | --- |
| every bridge method | disposed → `canvas-disposed`; then (mutating entries) guard held → `transaction-reentrant`; then no envelope → `document-not-loaded` |
| `apply_commands` | no active profile, bad argument types → `operation-error`; signal → `operation-cancelled`; stale `base_revision` or `expected_view_revision` → `operation-error`; then each command in order (a)–(i) below; then C, N → their codes; gate → `profile-open`; disposal during → `canvas-disposed` |
| `activate_business_profile` | `descriptor-mismatch`; identity → §3.3 code; plan → `operation-error` |
| `undo`, `redo` | stale → `operation-error`; nothing to restore → `operation-error` |
| `list_entries` | stale → `operation-error`; surface → `profile-type`; subject → `reference-dangling` |
| `list_fields` | stale → `operation-error`; target → `reference-dangling` |
| `check_field` | stale → `operation-error`; target → `reference-dangling`; field → `profile-symbol`; then the value outcome as `valid: false` with the commit code |
| `query_references` | argument types → `operation-error`; paging → `profile-bounds`; stale → `operation-error`; target → `reference-dangling`; field → `profile-symbol`; widget → `profile-type` |
| `copy` | stale → `operation-error`; missing ID → `reference-dangling`; Definitions root → `profile-type` |
| `compile_profile` (§6) | CR order; inside CR-10 the order of §6 |

Per command of `apply_commands`, first failure wins:

- (a) not exactly one of `entry`/`upstream`/`field` → `transaction-entry-unsupported`;
- (b) a key outside §3.1 → `profile-ui-parameters`;
- (c) resolution: unknown entry → `profile-symbol`; unlisted upstream →
  `transaction-entry-unsupported`; field command without `target` →
  `profile-ui-parameters`, `target` absent from the stage → `reference-dangling`,
  field not declared by a recognized notion → `profile-symbol`;
- (d) gesture sources not exactly the subject plus the bound sources (and
  `fragment` iff paste) → `profile-ui-parameters`;
- (e) handles: non-string → `profile-type`, absent from the stage →
  `reference-dangling`;
- (f) authorization (`ui.when`, field visibility/mutability/readonly/command) →
  `profile-producer`;
- (g) value typing and widget rules → `profile-type` or `reference-dangling`;
- (h) paste fragment → `profile-type`, `reference-dangling` or `id-collision`;
- (i) recipe execution on the stage (lot 3 `plan_recipe`/`apply_plan`) → its
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
L165, §2.4.1 L206).

## 7. Gates

| DESIGN item (§13) | State given §16 | Python lot-5 behaviour |
| --- | --- | --- |
| OPEN-HOOK (L923) | canvas pointer/keyboard receipt | N-A for Python: no browser gesture; headless commands use detached staging only |
| OPEN-PANEL (L925, §16.5) | owner choice after canvas evidence | N-A for Python: no panel dependency; the field contract of §4.4 is panel-independent |
| OPEN-EXTERNAL (L910, §16.2) | owner default ratified; encoding proof pending, external creation unavailable | the library has no external branch; a profile gates its external entry with a `refuse` step, which refuses `profile-open` atomically (`gate-external-creation`) |
| OPEN-RESERVED-N (L917, §16.11) | owner default ratified; twin atomicity proof pending | an edit whose N would persist a new support binding refuses `profile-open`; reuse of bound supports commits (`gate-reserved-n-*`) |
| OPEN-DRAFT (L911, §16.3) | ratified | edits commit in draft; lint postcheck not run by lot 5 (§9) |

## 8. Case file format

Every file in `tests/profile_commands/expected/` is one JSON object with `case`
(= file stem), `clause` (starts with `DESIGN R3.3 §`), `derivation`, `author`
(`spec-seal`), `input`, `expected`, and optionally `derived` (`loadRevision`,
`ids`, `identity`, recomputed by `derive_helper.py check`).

**Fixtures.** `fixture-descriptors.json` and `fixture-base.json` give
`input.source = {file, delta}` (RFC 6902 against a vendored contract file) and
`expected = {document, pin}`; the package/base bytes are the UTF-8
profile-c14n/2 bytes of `document`, so `pin.sha256 = H(document)`.
`fixture-profile-neutral.json` and `fixture-profile-grid.json` give the profile
composition and `expected = {profileSha256, identity}`.

**Setup.** `input.profile = {fixture, delta}`: the profile is the fixture
composition followed by the case delta (RFC 6902 `add`, `replace`, `remove`,
`test`). With `pin`/`document` the expected values of `fixture-descriptors.json`
and `base` the `expected.document` of `fixture-base.json`:

1. `context = create_descriptor_context([{**pin, "descriptorBytes": JCS(document)}])`,
   unless `input.bridge.descriptorPackages` lists `{file, pin}` records, whose
   `descriptorBytes` are the raw file bytes (the profile still compiles with the
   fixture context);
2. `load_profile(<UTF-8 JSON of the profile>, schema_bytes=<pinned
   profile-mechanism-1.schema.json>, base_bytes=JCS(base), descriptor_pins=[pin])`
   (the profile digest is `H(profile)`, independent of the serialization);
3. `compile_profile(validated, descriptor_context=<fixture context>, base=base)`;
4. the case identity is `{mechanismVersion, schemaVersion, profile, version,
   sha256: H(profile), base, descriptors}` of the composed profile (the fixture
   `identity`, or `derived.identity` when the case adds a delta);
5. with `input.document = {tree, bindings}`: `bridge = create_bridge(context)`,
   `bridge.set_definitions(complete_envelope(identity, tree, bindings))`, then
   `bridge.activate_business_profile(compiled)` matched against
   `expected.setup.activate`; without `input.document` only the bridge is created.

`expected.compile` (compile cases) is the first refusal of steps 2–3, or
`{status: "ok"}`.

**Steps.** `input.steps[i] = {op, args?, save?}` with ops `apply_commands`,
`undo`, `redo`, `get_snapshot`, `get_definitions`, `dispose`, `activate`,
`set_definitions` (`{document}` with the case identity), `list_entries`,
`list_fields`, `check_field`, `query_references`, `copy`, `localize` (module
function), `on_change` (`{collect: name}`: the listener appends each event) and
`events` (`{name}`: actual value `{"events": [...]}`); argument names are the
DESIGN camelCase names of §2. Placeholders: `{"$current": "viewRevision"}` is
`get_snapshot().payload.viewRevision` at that moment; `{"$saved": name,
"pointer": p}` is the JSON at `p` of a saved actual result. `save: name` stores
the step's actual result (`to_json()` form). Signals:
`{kind: "constant", returns}`, `{kind: "reenter", calls: [steps], returns}`
(each call is performed on the same bridge and its result recorded per op) and
`{kind: "dispose", returns}`.

**Matching.** `expected.steps[i]` is a template for the actual result:

- keys other than `payload`, `report`, `payloadKeys`, `equal`, `differ`,
  `signal`, `events` must equal the actual value;
- `payload` and `report`: each listed key must equal the actual value below it;
- `payloadKeys`: the sorted keys of the actual payload;
- `equal`/`differ`: `[{pointer, saved, savedPointer}]` profile-c14n/2 equality or
  difference with a saved result;
- `signal`: `{minCalls, results}`: the signal ran at least `minCalls` times and
  every recorded result of an op matches `results[op]`;
- `events`: same length, each event matching its template key by key.

Equality is profile-c14n/2 byte equality (key order irrelevant, `true` is not
`1`). `viewRevision`, `historyEpoch`, `subscriptionId`, `diagnostics` and report
entries are never sealed (lot 4 digests, session-local counters).

## 9. Design-default resolutions and cross-lot points

`design-default` lines (DESIGN names no value; the lot-5 binding chooses):

1. `ui.when` false, hidden/immutable/readonly field edit → `profile-producer` (§8.3 L649).
2. Stale `baseRevision`/`expectedViewRevision`/`expectedRevision` and nothing to undo/redo → `operation-error` (existing bridge binding; §8.2 L629 names no code).
3. Unlisted upstream entry, bare recipe command → `transaction-entry-unsupported` (§8.2 L635, L637).
4. Unknown UI entry or field, duplicate upstream mapping, missing fallback text → `profile-symbol` (CR-05).
5. `remove` closure violation → `reference-dangling` (§2.4 L171, §2.2 L132); lot 3 seals `remove` too and the integrator reconciles the code.
6. Paging violations → `profile-bounds` (CR-04).
7. Paste allocation `stable-id/1(owner, "paste", JCS([key, X]))` (§3.2).
8. Replacement map in `report.idMap` with domain `migration` (§10.1 L753).
9. Surface subjects per §3.1; effective reference ownership per §4.6; candidate label per §4.6.
10. C and N run once after the whole batch, commands stage sequentially (§8.2 L631, §8.3 L653).
11. Lint stages are not run inside `apply_commands` by lot 5 (§16.3 DRAFT; the §6.2 edit-row postcheck stays not covered).
12. OPEN-RESERVED-N detected by new `(ownerId, role)` bindings after N.

Observed block-A defects that the lot-5 code job must fix first (DESIGN
conformance): the `count` predicate is read from key `selector` instead of the
schema key `select` (compiler and evaluator); `inverseReference` property
admission is checked on the source type instead of the referring type; CR-10 is
not implemented; `ensure` (lot 3) registers neither its alias nor its write
demands. `reachable` reads `source`/`target` instead of the schema keys
`from`/`to` (not used by lot-5 cases).

## 10. Case table

One row per sealed file (status summary: `ok xN` counts successful steps).

| Case | DESIGN clause | Witness | Expected |
| --- | --- | --- | --- |
| `compile-enum-duplicate-records` | §8.3 L655 | identical enum choice records (schema uniqueItems) | compile refused `profile-schema` |
| `compile-enum-duplicate-values` | §2.4.1 L195 | enum choices share a JSON value under different names | compile refused `profile-ui-parameters` |
| `compile-enum-empty-choices` | §8.3 L655 | enum widget without choices (schema) | compile refused `profile-schema` |
| `compile-field-parameter-missing` | §8.3 L655; §2.4.1 L195 | mutable field map incomplete | compile refused `profile-ui-parameters` |
| `compile-grid-l5-ok` | §2.4.1 L195; §8.3 L655 | every CR-10 rule satisfied (grid) | compile ok |
| `compile-id-not-ordinary-input` | §8.3 L653; §2.4 L165; §2.4.1 L206 | a recipe writing an existing ID | compile refused `profile-producer` |
| `compile-message-missing-fallback` | §8.3 L659 | message without policies.localeFallback text | compile refused `profile-symbol` |
| `compile-mutable-without-command` | §8.3 L659 | mutable field without command (schema) | compile refused `profile-schema` |
| `compile-mutable-without-parameters` | §8.3 L655 | mutable field without parameter map (schema) | compile refused `profile-schema` |
| `compile-neutral-l5-ok` | §2.4.1 L195; §8.3 L655 | every CR-10 rule satisfied (neutral) | compile ok |
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
| `copy-fragment-read-only` | §8.3 L657; §10.1 L737 | copy returns an ordered fragment, no state change | ok x3; refused `operation-error` |
| `copy-unknown-id` | §8.3 L657; §2.2 L132 | copy of a missing ID; stale copy | refused `reference-dangling`, `operation-error` |
| `create-append-task` | §8.3 L649; §2.4 L163 | append creates task and link | ok x2 |
| `create-reference-then-connect` | §8.3 L651; §4.4 L408 | DataStore + DataStoreReference, then Association on connect (no DataInputAssociation) | ok x3 |
| `create-task-palette-grid` | §8.3 L649; §7.1 L538; §3.2 L284 | grid create: ServiceTask, same ID, isExecutable true | ok x2 |
| `create-task-palette-neutral` | §8.3 L649; §2.4 L163; §3.2 L276-L282 | palette create with stable-id/1, C keeps isExecutable false | ok x2 |
| `delete-includes-dependents` | §8.3 L653; §2.4 L171 | delete includes all declared dependent edges | ok x2 |
| `delete-refuses-dependents` | §8.3 L653; §2.4 L171 | delete refuses an unlisted dependent edge | ok x1; refused `reference-dangling` |
| `delete-unreferenced` | §8.3 L653; §2.4 L171 | delete of an unreferenced task | ok x2 |
| `field-clear-optional-reference` | §8.3 L659; §2.4 L166 | explicit remove-reference command; property absent | ok x2 |
| `field-display-edit-grid` | §8.3 L655; §2.2 L116 | display independent of storage, full Unicode upper case | ok x3 |
| `field-display-prefix-exact` | §2.2 L115; §8.3 L655 | stripPrefix only removes an exact prefix | ok x1 |
| `field-edit-restores-marker` | §8.3 L653 | edit restores the marker once | ok x2 |
| `field-empty-string-explicit` | §8.3 L659 | empty string stored, not omitted | ok x2 |
| `field-enum-validation` | §8.3 L659 | on-change validation equals submit validation (enum) | ok x5; refused `profile-type` |
| `field-listing-widgets` | §8.3 L653 | field records for text, multiline, readonly, reference, enum widgets | ok x7 |
| `field-not-editable` | §8.3 L653; §8.3 L649 | immutable, hidden, readonly and predicate-locked fields | ok x3; refused `profile-producer` |
| `field-reference-submits-ids` | §8.3 L659 | reference widget submits IDs; label and wrong type refused | ok x2; refused `reference-dangling`, `profile-type` |
| `field-unknown` | §2.4.1 L190; §8.3 L655 | unknown field ID; dangling target | ok x1; refused `profile-symbol`, `reference-dangling` |
| `field-value-omitted-or-coerced` | §8.3 L659 | omitted value refused; null, number, Boolean not coerced | ok x1; refused `profile-ui-parameters`, `profile-type` |
| `field-visible-predicate` | §8.3 L653 | visible predicate exposes a field | ok x3 |
| `fixture-base` | §2.4.1 L191; §1.1 L28 | lot-5 effective base and its pin | derived values |
| `fixture-descriptors` | §8.1 L606; §2.1 L48 | lot-5 descriptor slice and its pin (union of vendored slices + IO/store types) | derived values |
| `fixture-profile-grid` | §8.3 L649-L659; §7.1 L538 | grid lot-5 profile composition, digest and identity | derived values |
| `fixture-profile-neutral` | §8.3 L649-L659; §2.1 L67-L77 | neutral lot-5 profile composition, digest and identity | derived values |
| `gate-external-creation` | §8.3 L651; §4.1 L364; §13 L910 | OPEN-EXTERNAL: external entry refused | ok x1; refused `profile-open` |
| `gate-reserved-n-creation` | §7.2 L554; §13 L917; §16 L1160 | OPEN-RESERVED-N: edit needing new supports refused | ok x1; refused `profile-open` |
| `gate-reserved-n-reuse` | §7.2 L552; §5.2 L440 | bound supports reused, edit commits | ok x2 |
| `history-batch-one-step` | §8.2 L632 | multi-command batch is one history step | ok x5 |
| `history-change-events` | §8.2 L633; §8.1 L606 | one event per commit/undo/redo; none for refusal or no-op | ok x5; refused `profile-symbol` |
| `history-load-epoch` | §8.2 L643; §8.1 L584 | load starts a new history epoch | ok x3; refused `operation-error` |
| `history-noop-no-entry` | §8.2 L641 | no-op and empty batches add no history step | ok x6; refused `operation-error` |
| `history-refusal-preserves-state` | §8.2 L633 | refusal leaves snapshot and history unchanged | ok x6; refused `profile-symbol` |
| `history-stale-revisions` | §8.2 L629; §3.1 L268 | stale baseRevision/expectedViewRevision refused before commands | ok x2; refused `operation-error` |
| `history-undo-redo-guards` | §8.1 L595-L596; §8.2 L629 | stale undo/redo refused, cursor kept | ok x3; refused `operation-error` |
| `history-undo-redo-roundtrip` | §8.2 L641; §8.1 L595-L596 | byte-identical undo/redo, redo not truncated | ok x10; refused `operation-error` |
| `io-set-explicit-selection` | §8.3 L651; §7.1 L547; §8.3 L653 | explicit set selection in the same batch; C once per batch | ok x2 |
| `io-set-selection-required` | §8.3 L651; §7.1 L547 | uncovered IO with two sets refused by C on the stage | ok x1; refused `io-set-selection-required`, `operation-error` |
| `l10n-resolution-order` | §8.3 L659 | exact, fallback, stable key | ok x8 |
| `lifecycle-activation-descriptor-mismatch` | §8.1 L617 | activation with a differing descriptor package | ok x1; refused activate `descriptor-mismatch` |
| `lifecycle-dispose` | §8.1 L599 | dispose result and disposed-state refusals | ok x1; refused `canvas-disposed` |
| `lifecycle-not-loaded` | §10.1 L737; §8.1 L589 | operations before load | refused `document-not-loaded` |
| `paste-batch-one-step` | §8.3 L653; §8.2 L632 | paste then edit of the remapped ID in one undo step | ok x4 |
| `paste-dangling-external-refused` | §8.3 L653; §2.2 L132 | paste with a dangling external ref refused | ok x3; refused `reference-dangling` |
| `paste-key-collision` | §8.3 L655; §3.2 L288 | same paste key collides; new key gets new IDs | ok x3; refused `id-collision` |
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
| `replace-replacement-map` | §8.3 L651; §10.1 L753 | type change reports the replacement map | ok x2 |
| `surface-append-when` | §8.3 L649 | append: same predicate for listing and call | ok x3; refused `profile-producer` |
| `surface-connect-when` | §8.3 L649 | connect: same predicate for listing and call | ok x3; refused `profile-producer` |
| `surface-context-when` | §8.3 L649 | context: same predicate for listing and call | ok x3; refused `profile-producer` |
| `surface-delete-when` | §8.3 L649 | delete: same predicate for listing and call | ok x4; refused `profile-producer` |
| `surface-direct-edit-when` | §8.3 L649; §8.3 L657 | direct edit: refused then authorized call | ok x4; refused `profile-producer` |
| `surface-gesture-parameters` | §8.3 L655 | missing/extra gesture sources, ambient field; explicit empty value accepted | ok x2; refused `profile-ui-parameters` |
| `surface-handles-and-values` | §8.3 L655; §2.2 L132 | dangling handle; no scalar coercion; null refused | ok x1; refused `reference-dangling`, `profile-type` |
| `surface-palette-entries-grid` | §8.3 L659; §7.1 L538 | grid palette order | ok x1 |
| `surface-palette-entries-localized` | §8.3 L659 | labels: exact locale, fallback, no BCP 47 truncation, case-sensitive locale | ok x3 |
| `surface-palette-entries-order` | §8.3 L659; §8.3 L649 | groups by first appearance; order numeric then UTF-16 ID; hidden entry omitted | ok x1 |
| `surface-palette-when` | §8.3 L649 | palette: hidden entry refused programmatically | ok x2; refused `profile-producer` |
| `surface-paste-when` | §8.3 L649; §8.3 L657 | paste: copy grants no paste authority | ok x3; refused `profile-producer` |
| `surface-raw-recipe-command` | §8.3 L649; §8.2 L635 | bare recipe command disabled | ok x1; refused `transaction-entry-unsupported` |
| `surface-replace-when` | §8.3 L649 | replace: same predicate for listing and call | ok x4; refused `profile-producer` |
| `surface-unknown-entry` | §2.4.1 L190 | unknown entry ID | ok x1; refused `profile-symbol` |
| `surface-unlisted-upstream` | §8.3 L659; §8.2 L635 | unlisted upstream entry disabled | ok x1; refused `transaction-entry-unsupported` |
| `surface-upstream-mapped` | §8.3 L659 | upstream ID resolves to its entry (same tree) | ok x2 |
| `twin-grid-fixture-commands` | §14.2 L954; §7.1 L538 | vendored grid commands through UI entries reproduce expected.completed | ok x2 |
| `twin-neutral-fixture-commands` | §14.2 L954; §8.3 L649; §7.1 L538 | vendored neutral commands through UI entries reproduce expected.completed | ok x2 |
| `tx-cancelled` | §8.1 L604; §8.2 L629 | cancellation refused without change | ok x1; refused `operation-cancelled`, `operation-error` |
| `tx-dispose-during-transaction` | §8.1 L619; §8.2 L635 | dispose during a batch commits nothing | refused `canvas-disposed` |
| `tx-reentrant-refused` | §8.2 L635 | re-entrant command refused; reads see the committed state | ok x2 |

## 11. Not covered

- Browser gestures, pointer capture, drag coalescing, DI-only drag/resize/
  reconnect, placement intent and multi-page rollback (OPEN-HOOK, canvas, §8.2
  L637-L639); theme switching and snapshot restoration (`setTheme`,
  `restoreSnapshot`); navigation index (§8.1 L623); read-only mode (§8.1 L619).
- Lint stages of the §6.2 edit row inside `apply_commands` and the report
  entries of every operation (only `report.idMap` of replace is sealed).
- Activation or load with a different profile identity (§3.3 corpus) and
  explicit migration plans (migration lot).
- Internal items with native data associations and ports, reference↔item
  conversion of DataObjectReference, multiple-reference sharing (§8.3 L651,
  §4.4); external-call encoding (OPEN-EXTERNAL).
- Field IDs declared by two recognized notions (`profile-ambiguous-notion`),
  UI entries naming recipes of phases other than create/edit/reference/convert,
  unknown `unsubscribe` IDs, listener re-entrancy and load events.
- Global versus per-surface group first appearance (§4.2).
- Visual placement in a reference-band region (§8.3 L651: never a native
  parent change) and every layout/geometry effect of a command (lot 4).
- `unsubscribe`, load-origin events, linear-history redo discard after a new
  batch (§4.8 step 10, normative but not sealed), selection preservation (no
  headless selection API) and unexpected internal exceptions mapped to
  `operation-error` after rollback (§8.1 L604, needs fault injection).
- Cross-runtime witnesses: JS→Python→JS transport and the twin canvas command
  artifacts of §14.3 need the conductor's joint run.
