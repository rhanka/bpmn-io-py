# SPEC PROFILE MECHANISM PY — Python binding of `profile-mechanism/1` (lot 0)

Status: binding contract for `bpmn_io.profile` (target 0.3.0). This spec produces
**no interpreter**: no loader, compiler, evaluator, validator, encoder, lint bridge
or CLI code. It freezes the Python-side meaning of every R3.3 contract so lots 1–2
can implement against it. Normative design authority is DESIGN.md R3.3 (SHA-256
`48139f5fd5bd789eacbf271081a95432c54d8361b1e52404e3443a25fa65782f`), through the
lineage R3.1 (SHA-256 `020270f65e0be7b119365bb402ff062cf406fca92940709dd987d9dfdc8173f8`)
→ R3.2 lexical erratum (DESIGN §2.1.1) → R3.3 compatibility erratum (DESIGN §3.3),
with `CONVERGENCE-R3.md` lot-0 errata and `CONSENSUS-R3-bpmn-py.md` item M1. Pinned
contract bytes live in `contracts/profile-mechanism/1/` (`CONTRACTS.toml` /
`CONTRACTS.lock`). Where this spec and a pinned byte disagree, the byte wins and
the mismatch is reported in the plan Feedback Loop, never patched locally.

Naming follows `docs/naming.md`: DESIGN camelCase operations become snake_case
functions, types stay PascalCase, BPMN property names are unchanged. All
computation is synchronous (async-to-sync mechanical mapping); editor scheduling
from DESIGN §8 stays out of the headless scope.

## 1. JSON Schema 2020-12 validation strategy (consensus M1)

`bpmn_io.profile` ships a dedicated standard-library validator for the closed
`profile-mechanism/1` schema subset, with no runtime dependency. `jsonschema`
stays a test-only differential reference against Ajv.

### 1.1 Closed keyword set

The supported keywords are exactly the 29 DESIGN §2.1 names:

`$schema`, `$id`, `$comment`, `title`, `$defs`, `$ref`, `type`, `properties`,
`required`, `additionalProperties` (Boolean closure only), `items`, `minItems`,
`maxItems`, `uniqueItems`, `minLength`, `pattern`, `enum`, `const`, `minimum`,
`maximum`, `exclusiveMinimum`, `exclusiveMaximum`, `allOf`, `anyOf`, `oneOf`,
`not`, `if`, `then`, `else`. Boolean schemas are admitted.

Audit result (verified against the pinned bytes before writing this spec,
extended to R3.3): the four pinned schemas (`profile-mechanism-1`,
`compiled-lint-options`, `neutral-provider-arguments`,
`compatibility-verdict`) use only these keywords — the verdict schema uses
exactly `$schema`, `$id`, `$comment`, `$defs`, `$ref`, `type`, `properties`,
`required`, `additionalProperties`, `enum`, `const`, `oneOf`, with no `pattern`
and a single local `$ref` (`#/$defs/refusalCode`) — and every one of the 29
is exercised by at least one of them. A supplied schema using any other keyword
(`format`, `patternProperties`, `unevaluated*`, …) refuses schema loading with
`profile-schema-keyword`. Visit schema positions only: a data property named
`format` is not a keyword. Unknown regexes refuse with `profile-schema-pattern`.

### 1.2 Pattern evaluation

Python pattern validation MUST use `re.fullmatch` on the expression with its
outer `^`/`$` anchors removed (equivalently `\Z` end). Rationale: Python `$`
accepts a trailing newline, so `re.match`/`re.search` accept `"id\n"` where Ajv
refuses it. The distinct pinned regex inventory is exactly these eight
(displayed with schema anchors):

~~~text
^[A-Za-z_][A-Za-z0-9_.:/-]*$
^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$
^[a-z]{2}(?:-[A-Z]{2})?$
^[0-9a-f]{64}$
^[A-Za-z_][A-Za-z0-9_]*$
^(?:/(?:[^~/]|~[01])*)*$
^(?:bpmnlint:recommended|plugin:[A-Za-z_][A-Za-z0-9_.-]*/[A-Za-z_][A-Za-z0-9_.-]*)$
^[A-Za-z_][A-Za-z0-9_.:/-]*/[1-9][0-9]*$
~~~

Corpus witnesses: rejected `"id\n"`, accepted `1.0`, rejected fractional `1.5`,
rejected unregistered external `$ref` (lot 21).

### 1.3 Scalar semantics (JSON Schema, not Python accidents)

- `bool` is never `number`/`integer`, despite Python subclassing.
- Integer means any finite number with zero fractional part: `1.0` in an
  integer field is accepted (canonical form `1`); `1.5` refuses.
- String length counts Unicode code points.
- `enum`/`const`/`uniqueItems` compare JSON values structurally and distinguish
  `true` from `1`.
- The lexical checks of §2 still precede validation.

### 1.4 Reference scope

`$ref` resolves only within the current schema (`#/$defs/...`, including JSON
Pointer escapes) or against an explicitly supplied, digest-pinned schema
registry passed as `schema_bytes`. The profile schema is self-contained. The
compiled-lint schema references one pinned external URN,
`urn:profile-mechanism:1:profile#/$defs/rule`, which must be supplied
explicitly; without that pin it refuses with `profile-schema-ref`. No
filesystem or network resolution. Data failures validate as `profile-schema`.

## 2. Strict lexical pre-parse (DESIGN §2.1)

Before `json.loads`, reject with these codes. Provenance: DESIGN §2.1.1 (R3.2,
normative; DESIGN.md R3.3 lines 83–101) defines these four codes and their
first-failure reporting order — this closes the Lot 20 open conductor question
(plan Feedback Loop) with the DESIGN line. Reporting order: first failure in the
recursive source-order walk (per object member: decode the key, then check its
Unicode scalars, then check the decoded duplicate, then require the colon, then
traverse the value; string and number values are checked in source order;
trailing-data and whole-text grammar checks run after the root value completes).
Every lexical code precedes schema validation and any compiler diagnostic for
the same profile text:

| Check | Code |
|---|---|
| Duplicate decoded object keys (`"a"` vs `"a"`) | `profile-json-duplicate-key` |
| Lone surrogates in decoded strings | `profile-unicode` |
| Non-finite numeric tokens (including `1e400`) | `profile-number` |
| Number tokens whose binary64 conversion (ECMAScript `Number`) is non-finite, or integral and outside ±9007199254740991 (DESIGN:92) | `profile-number` |
| Malformed JSON otherwise | `profile-json` |

Negative zero is accepted and canonicalizes to zero. Fractional binary64 values
must be finite; a token whose converted binary64 value is integral is judged by
the integer rule above even when the token itself is not mathematically
integral (`9007199254740991.5` converts to the unsafe integer
`9007199254740992`). A syntax parser cannot rely on a runtime accepting
Infinity or silently rounding an unsafe integer.

## 3. Canonical bytes `profile-c14n/2` (DESIGN §3.1)

`H(x) = lowercase_hex(SHA256(UTF8(JCS(x))))`; `B(bytes)` is the same over raw
bytes. JCS: UTF-16 code-unit key ordering, no insignificant whitespace, UTF-8
without BOM, ECMAScript shortest binary64 number rendering, `-0` as `0`, JSON
escaping, no Unicode normalization, no trailing newline in hashed bytes. Arrays
keep order. Reject NaN/infinities, duplicate keys, lone surrogates.

Number rendering follows ECMAScript Number-to-string exactly (no locale,
shortest round-trip digits): `-0` renders `0`; for a positive magnitude with
digit string `s` (`k` digits) and decimal exponent `n` (value = `s × 10^(n-k)`):
plain digits when `k ≤ n ≤ 21`, fraction form when `0 < n ≤ 21`, leading-zero
fraction when `-6 < n ≤ 0`, otherwise single-digit mantissa with `e±` exponent.
Consequences: `1.0`→`1`, `1e20`→`100000000000000000000`,
`123456789012345680000` stays plain digits, `1e21`→`1e+21`, `1e-6`→`0.000001`,
`1e-7`→`1e-7`, `5e-324`→`5e-324`. Python MUST NOT render integral floats via
`int()` (`int(1e21)` prints `1000…000`) nor reuse `json.dumps` float formatting
unchecked (`1.0`→`1.0`, `1.2345678901234568e+20` instead of plain digits); keys
sort by UTF-16 code units, `ensure_ascii=False`. Normative vectors (DESIGN
§14.3 plus boundary cases, all confirmed against Node): `1.0`→`1`,
`1e20`→`100000000000000000000`, `123456789012345680000` unchanged,
`1e21`→`1e+21`, `1e-6`→`0.000001`, `1e-7`→`1e-7`, `5e-324`→`5e-324`, `-0`→`0`.
A key `U+10000` sorts before `U+E000` (UTF-16 order); neither runtime may
substitute its default scalar-key sort.

`semanticRevision = H({tree, profileIdentity, bindings})` (acceptance context);
`baseRevision` for ordinary operations is the input envelope revision; initial
import and `viewRevision` follow §3.1 exactly.

## 4. Identity `stable-id/1` (DESIGN §3.2)

~~~text
g_ + lowercase_hex_sha256(UTF8(JCS(["profile-mechanism/1", ownerId, slot, stableKey])))
~~~

Full-length digest. For an allocated create, `ownerId` is the explicitly
evaluated argument, never inferred from the nearest container; the virtual root
allocation owner is the literal `document-root/1`. Containment identity writes
no id/slot/key/ownerId. Existing valid imported IDs survive; collisions refuse
with `id-collision`, never suffix or overwrite. Authoring grammar
`^[A-Za-z_][A-Za-z0-9_.-]{0,255}$` applies to native IDs and ID references.

Pinned fixture vector (both runtimes agree): owner `Process_1`, slot `aid`,
key `new-note` allocates
`g_61b268027699fa668a9b0e3eced8130a2b2e188f426051e9ad25ebb1e33a800c`
(`neutral-fixture.json`).

## 5. Unicode case policy (UCD 15.0.0, no runtime `str.upper()`)

Casing uses the pinned Unicode full default case mappings (multi-code-point
mappings included), version 15.0.0, with no locale-dependent behavior and no
normalization. Primary sources (Unicode Character Database 15.0.0, read-only,
never vendored by this branch):

- `UnicodeData.txt` (1 913 704 bytes, SHA-256
  `806e9aed65037197f1ec85e12be6e8cd870fc5608b4de0fffd990f689f376a73`):
  simple (1-to-1) uppercase mapping per code point;
- `SpecialCasing.txt` (16 832 bytes, SHA-256
  `78b29c64b5840d25c11a9f31b665ee551b8a499eca6c70d770fcad7dd710f494`):
  full mappings; unconditional entries override the simple mapping,
  conditional (locale-sensitive) entries are excluded (16 in 15.0.0).

Generation rule: start from the simple uppercase mapping, apply the
unconditional special entries (single- or multi-code-point result, e.g.
`ß`→`SS`), drop conditional entries; total 1526 entries including one identity
(`İ`→`İ`). Cross-check only (never a source): the workbench table agrees on
all 1525 entries it carries and omits just that identity entry. The symmetric
lower table is generated by the same rule in lot 2. Vendoring the table
requires the Unicode license attribution (plan BR04-EX3).

## 6. Signature table (DESIGN §2.5, results §10.1)

Pure operations return `PureResult`: success `{status: "ok", payload,
diagnostics}`, refusal `{status: "refused", code, diagnostics}`. Document
operations return `Result`: success `{status: "ok", operation, profileIdentity,
baseRevision, revision, report, payload}`, refusal `{status: "refused",
operation, profileIdentity?, baseRevision?, code, diagnostics, report}`.
Python names are snake_case with identical fields.

| DESIGN ABI | Python name | Inputs → payload |
|---|---|---|
| `loadProfile` | `load_profile` | `(data: bytes, *, schema_bytes, descriptor_pins, base_bytes, asset_bag, capabilities)` → `ValidatedProfile` |
| `compileProfile` | `compile_profile` | `(validated, registry_set)` → `CompiledProfile` |
| `evaluatePredicate` | `evaluate_predicate` | `(ast, read_context, bindings)` → `bool` |
| `select` | `select` | `(selector, read_context, bindings)` → ordered `ElementHandle[]` |
| `planRecipe` | `plan_recipe` | `(recipe, read_context, params, authority)` → `WritePlan` |
| `applyPlan` | `apply_plan` | `(plan, staged_tree, staged_envelope)` → `ChangeReport` |
| `complete` | `complete` | `(compiled, envelope, mode)` → `DocumentEnvelope` |
| `normalize` | `normalize` | `(compiled, envelope, placement_intent?)` → `{envelope, placements, report}` |
| `validate` | `validate` | `(compiled, envelope, *, phase, readiness_policy)` → `ValidationReport` |
| `resolveTheme` | `resolve_theme` | `(compiled, envelope, layout, theme_id, overrides, di_styles)` → `RenderData` |
| `mapExport` | `map_export` | `(compiled, envelope, layout, r, format)` → `PreparedArtifact` |
| `serializePrepared` | `serialize_prepared` | `(prepared, pinned_writer_options)` → `{format, bytes, digest, idMap, capability}` |
| `prepareExport` | `prepare_export` | `(compiled, envelope, options)` → `PreparedArtifact` (synchronous in Python) |
| compatibility decision (§3.3, no DESIGN ABI name) | `check_compatibility` | `(runtime, injected_identity, document_identity, *, document_version, host_identity, snapshot_identity, source_availability, selected_migration, required_capabilities, required_assets, envelope_valid)` → verdict `{status: "ok"}` or `{status: "refused", code?}` (§9.1) |

Wire/result field names are exactly DESIGN's (`idMap` in `serializePrepared`, `code` in verdicts); a Python attribute may use a different spelling only if the serialized field stays the DESIGN name. A refusal without `code` is only the exact-but-invalid envelope bare refusal (DESIGN:324); every other refusal carries a `code`.

`validate` here is `bpmn_io.profile.validate`, distinct from the schema
validator of §1. `ReadContext` carries only profile identity, descriptor /
effective-base index, immutable native tree/index, immutable source
coordinates, support bindings, stage and validated command inputs, plus
immutable layout/R bindings for theme/export evaluation.

`Report/2` entries carry exactly `code, severity, classification, stage, ruleId,
messageKey, disposition`, `source`/`result` coordinates
(`domain, pointer, targetId, provenance`), required `beforePresent,
afterPresent`, optional `originalType?, property?, before?, after?, causedBy?,
pageId?, occurrenceKey?, emittedType?, legacyCode?, lossClass?`. `idMap` sorts by
`(domain, pageId, occurrenceKey, sourceId, resultId)` in UTF-16. Capability is
the worst occurrence/page/format outcome (`engine-byte-compatible < structural
< unsupported`).

## 7. Reconciliation with the pinned schemas

Checked field by field before writing this spec; no mismatch found:

- Compiled lint options (§6.3): the pinned schema requires exactly the seven
  keys `mechanismVersion, profileDigest, phase, readinessPolicy, compiledRules,
  bindings, severityPolicyDigest`, and `compiledRules` items resolve through
  the pinned profile URN (§1.4).
- Provider arguments (§11): the pinned schema requires exactly `id, adapter,
  apiVersion, allowedKeywords, optionalTransport, maxOutputTokens, models,
  qualification, argumentSchemaDigest`.
- Registry: `providerAdapters` (id + `argumentSchemaDigest`),
  `regionTokenPattern`/`regionTokenSchema`, `renderTokens` — as consumed by
  §§2.5/9.3.
- Profile `$defs` (27: `action, citation, exportSpec, field, glyph, lintPhase,
  lintSetting, literalEntry, message, migration, namedText, namedValue, notion,
  parameter, pathCommand, pin, predicate, producerDelta, provider, recipe,
  resource, rule, selector, surface, theme, value, write`) cover the §2
  operator/action tables; compiler rules CR-01–CR-14 and the action/write
  matrix are enforced by the lot-2 implementation, not the syntax schema.

Boundary (not a mismatch): `DocumentEnvelope/1`, `Snapshot/1`, `Layout/1`,
`RenderData/1`, `Result/1` and `Report/2` are DESIGN-prose contracts with no JSON
Schema pinned in lot 0 — they govern operation results, not profile authoring
data. Their shapes in §6 (the signature table and the `Report/2` entry fields)
are the binding until lot 2 decides whether they need pinned schemas. The §3.3 compatibility decision function stays prose (no
executable matrix in lot 0), but its refusal-code registry and verdict shape are
pinned since R3.3 (`compatibility-codes.json`, 20 codes;
`compatibility-verdict.schema.json`, `refusalCode` enum plus `ok`/`refused`
shape); the §9.1 binding applies them in DESIGN row order with P1/P2.

## 8. Lot 1 interface (copied from DESIGN R3.3, not re-decided)

New profile entry point, distinct from the literal `bpmn-io lint`:

- Python: `bpmn_io.profile.lint(envelope, compiled, *, phase, readiness_policy)`
  returning the unified `Result/1`. Profile ok holds iff the operation
  succeeded and no unresolved unified error entry remains; counts are over
  unresolved unified info/warn/error entries.
- CLI: `bpmn-io profile lint --input envelope.json --profile profile.json
  --schema profile-mechanism-1.schema.json --base base.json --descriptors
  descriptors.json --registry registry.json --phase post-normalize
  --readiness-policy accept --json`. Each path is an explicit local pinned
  input; `--phase` accepts only the five §6.2 stages (`import, pre-normalize,
  post-normalize, post-layout, release`); `--readiness-policy` is `draft` or
  `accept`; `--json` writes one `Result/1` to stdout, diagnostics to stderr.
  Exit 0 means ok, 1 means refused/remaining error, 2 means invalid invocation.
  CLI implementation and exit-code tests remain lot 1.
- `StaticResolver` over an explicit pinned allowlist (or an equivalently
  filtering wrapper); unrestricted `importlib` fallback is prohibited in the
  profile path. Unknown names resolve to `None` (adapter: `lint-rule-unknown` /
  `lint-config-unknown`); thrown lookup exceptions from a wrapped Node-style
  resolver are caught and mapped the same way. Cache key: exact upstream
  artifact digest, pinned resolver-registry digest, normalized package name,
  rule-or-config kind, export name — immutable factories/configs only, never
  configured rule instances or findings; options, profile digest and severity
  policy digest stay per stage/evaluation. A fresh `Linter` and fresh rule
  instances per stage/evaluation, so A→B→A cannot reuse B options.
- Severity transport: numeric `0=off, 1=warn, 2=error, 3=info`; effective `info`
  travels as `warn` and is restored by the adapter in both runtimes (adapter
  choice, pinned by the lot-1 transport vector).

## 9. Refusal code inventory (verbatim from DESIGN)

All codes below are DESIGN prose, including `profile-json`,
`profile-json-duplicate-key`, `profile-unicode`, `profile-number` (normative
since R3.2, DESIGN §2.1.1) and the §3.3 compatibility set (reconciled with the
pinned `compatibility-codes.json` registry and the verdict-schema enum, R3.3).

Schema/data: `profile-schema`, `profile-schema-keyword`,
`profile-schema-pattern`, `profile-schema-ref`,
`profile-symbol`, `profile-type`, `profile-cycle`, `profile-value-context`,
`profile-selector-order`, `profile-selector-property`, `profile-bounds`,
`profile-create-identity`, `profile-bind-fallbacks`, `profile-action-phase`,
`profile-ui-parameters`, `profile-export-field`, `profile-migration-endpoint`,
`profile-write-set`, `profile-write-conflict`,
`profile-producer`, `profile-pin`,
`profile-notion-kind`, `profile-glyph-shape`, `profile-ambiguous-notion`,
`profile-ambiguous-binding`, `profile-open`. Lexical: `profile-json`,
`profile-json-duplicate-key`, `profile-unicode`, `profile-number`.
Compatibility (§3.3, R3.3 registry order): `document-version-unsupported`,
`profile-metadata-missing`, `profile-metadata-conflict`, `profile-schema-version`
(unsupported injected P schema only), `mechanism-version-unsupported`,
`document-mechanism-unsupported`, `document-schema-unsupported` (new R3.3),
`mechanism-migration-required`, `profile-schema-migration-required` (new R3.3),
`profile-capability`, `profile-resource-missing`, `base-mismatch`,
`descriptor-mismatch`, `profile-major-mismatch`, `profile-digest-mismatch`,
`profile-patch-migration-required`, `profile-patch-downgrade-required`,
`profile-minor-migration-required`, `profile-minor-downgrade-required`,
`profile-source-unavailable`.
Identity/graph: `id-collision`, `descriptor-role-unknown`,
`support-binding-conflict`, `io-set-selection-required`,
`responsibility-preservation-required`, `normalization-not-fixed`,
`reference-dangling`. Lint adapter (§6): `lint-config-incomplete`,
`lint-config-unknown`, `lint-rule-unknown`, `lint-config-cycle`,
`lint-rule-error`. Export/render (§§9–10): `export-field-invalid`,
`export-parent-order`, `export-parent-invalid`, `export-id-ambiguous`,
`export-occurrence-ambiguous`, `export-format-unsupported`, `legacy-unmapped`,
`render-stale`, `render-unsupported`, `render-region-missing`,
`render-style-conflict`, `render-token-invalid`, `theme-geometry-conflict`,
`snapshot-schema`, `snapshot-stale`, `transaction-reentrant`,
`transaction-entry-unsupported`, `input-conflict`, `document-not-loaded`,
`operation-cancelled`, `operation-error`, `canvas-disposed`,
`resource-limit`. Call/migration evidence: `call-kind-ambiguous`,
`call-kind-marker-duplicate`, `call-kind-marker-invalid`, `call-kind-conflict`,
`call-target-empty`, `call-target-type`, `call-target-required`,
`profile-migration-endpoint`, `ambiguous-evidence`. Losses use
`export-loss/<class>` with `lossClass` from the closed §10.2 set.

### 9.1 Compatibility decision binding (DESIGN §3.3, R3.3)

`check_compatibility` applies the DESIGN §3.3 rows in order (DESIGN.md R3.3
lines 294–324, changelog §15.5) before C/N/theme/export or edit, and returns
exactly one verdict: `{status: "ok"}` or `{status: "refused", code?}` with `code`
from the 20-code registry when present. Its inputs carry the envelope
`document_version` and the host, snapshot and document identities that the
first rows decide on (lines 302–304), alongside the runtime, the injected and
document profile identities, source availability, the selected migration, the
required capabilities/assets and envelope validity. Source-dependent remedies (P1, lines 298–299): at the
first applicable row whose only remedies need the exact source package or a
source-validated migration — mechanism-differ, schema-differ,
base/descriptor-mismatch, business-ID/major-mismatch, patch/minor rows — an
unknown D version/digest or an unavailable source yields
`profile-source-unavailable`, never a latest fallback. Schema axis (P2, lines
305–310): `profile-schema-version` fires only for an injected P schema
unsupported by R; a D schema unsupported by R refuses with
`document-schema-unsupported`; supported but unequal P/D schemas require the
exact source path or an explicit migration
(`profile-schema-migration-required`, subject to P1), placed immediately after
the mechanism-differ row. A known same-version unequal digest refuses
`profile-digest-mismatch` (no migration waiver, no P1 override); missing
capability/asset keeps its ordered `profile-capability` /
`profile-resource-missing` diagnostic. Row order governs every reading: earlier
identity/version conflicts precede source availability, and an otherwise exact
but invalid envelope stays a bare refusal with no new code (verdict-schema
`$comment`).

## 10. Open points for lots 1–2 (not decided here)

- Symmetric lower-case table generated by the §5 rule, with corpus vectors.
- Whether operation envelopes (`Result/1`, `Report/2`, `Snapshot/1`, R) need
  pinned JSON Schemas or stay prose contracts with golden corpus cases.
- `prepare_export` orchestration detail (C → lint → N → layout → R → map under
  accept policy) and receipt format, lot 1.
- Call-kind discriminator encoding and producer-base admission stay governed by
  the design's owner gates; this spec quotes neither the marker text nor its
  carrier field, and adds no new policy.
