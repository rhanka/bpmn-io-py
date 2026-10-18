# Profile lint bridge

The `bpmn_io.profile._lint` subpackage evaluates profile rules over the
literal `bpmn_io.lint` port (bpmnlint 11.15.0) and returns the unified
`Result/1` report, re-exported as `bpmn_io.profile.lint`. The `compiled`
argument of `lint` carries the compiled lint data either as plain
JSON-compatible dicts (`compiledOptions` — the seven closed keys, validated
against the contract schema — plus `validation`, the validation records the
stage table is selected from, and an optional `registry` of named
`plugin:<package>/<config>` configs for `extends`) or as the
`CompiledProfile` produced by `compile_profile`, from which the same
transport is derived (an optional `registry` argument supplies the extends
configs in that form only, and an optional `bindings` argument supplies the
envelope support bindings the `boundRole` predicate reads — the transport
dict already carries its own). The pinned `bpmnlint:recommended` parent always
comes from the literal port.

## Plugin

`bpmnlint-plugin-profile-mechanism` (rule `profile-mechanism/profile`) is
the single executable plugin. Business checks are declarative records
interpreted by this one rule; no executable rule is ever registered under
a business ID. The rule evaluates once at Definitions with a per-call
guard and never mutates the input moddle tree. The entry point
`bpmnlint.plugins = bpmnlint-plugin-profile-mechanism` in
`pyproject.toml` proves the wiring; evaluation always uses the directly
imported factory, never entry-point discovery.

## Resolver

`ProfileResolver` serves only immutable factories and configs: the pinned
upstream rules, the pinned `bpmnlint:recommended` config and the single
profile rule factory. Anything else resolves to `None` (mapped to
`lint-rule-unknown` / `lint-config-unknown`); the adapter never falls back
to `importlib` and never consults entry points on the resolve path. The
factory cache is keyed by `(upstream artifact digest, resolver-registry
digest, normalized package name, rule-or-config kind, export name)`.

## Configuration transform

For one `(phase, readiness_policy)` pair, allowlisted `extends` entries
and the explicit validation `settings` flatten by whole-setting replacement
(depth-first, left-to-right, then local records; options are never
deep-merged). Unknown targets refuse `lint-config-unknown`, cycles refuse
`lint-config-cycle`, and incomplete standard-rule coverage refuses
`lint-config-incomplete`. Numeric severities resolve (`0=off`, `1=warn`,
`2=error`, `3=info`); effective `info` travels upstream as `warn` and the
adapter restores it. `profile:<id>` settings partition out of the upstream
config, which carries the single transport registration
`"profile-mechanism/profile": ["error", compiledOptions]`.
`severityPolicyDigest` is `H({phase, readinessPolicy, settings})` over the
flattened setting array sorted in UTF-16 code-unit order.

## Unified report

Standard findings keep their rule identity; profile subfindings keep
theirs (`profile:<id>`, rule `code` / `message` key); adapter conditions
use rule `adapter` with the stable outcome code. Severity and
classification always come from the effective policy row. Entries merge by
`(origin, ruleId, code, targetId, sourcePointer, stage)`; `ok` is true when
no `error` entry remains, and `rawStandardFindings` preserves the upstream
reports verbatim.

## Rule evaluation

Profile rules evaluate on the full `bpmn_io.profile` evaluator
(`evaluate_predicate`, `select`) over one immutable `ReadContext` built
from the lint input tree. The context carries the lint phase, the
envelope support bindings and the compiled notions; declared rule
bindings (`bind` records with `as` / `select` / `cardinality`) evaluate
per candidate before the assertion (`one` needs exactly one handle,
`zeroOrOne` at most one, `first` takes the ordered head). A refused
selection or assertion — unknown operator, unbound name, cardinality
mismatch, missing source pointer, unavailable capability — is reported
as `lint-rule-error`, never silently false. Failing assertions emit one
subfinding per candidate: ID-bearing candidates first in selector order,
then ID-less candidates by source pointer.

Upstream report paths resolve per DESIGN R3.3 §6.4: a property-name
string or segment array resolves the reported ID in the input index and
appends escaped segments; a verbatim absolute pointer passes through
only with no reported ID or a known one (an unknown ID is refused, never
exact). Report entries sort by execution-stage rank (`import`,
`pre-normalize`, `post-normalize`, `post-layout`, `release`) before the
UTF-16 keys.

## CLI

```sh
bpmn-io profile lint --input envelope.json --profile profile.json \
  --schema profile.schema.json --base base.json \
  --descriptors descriptors.json --registry registry.json \
  --phase post-normalize --readiness-policy accept --json
```

`--input` carries either a `DocumentEnvelope` or an object with an `xml`
string. The profile travels the contract path before evaluation: the
loader (with the supplied schema bytes and base pin), the descriptor
pin-check, the compiler, the codec, envelope validation and the §3.3
compatibility rows. A schema reduced to `$id` is not the pinned schema
and exits `2`; unsupported mechanisms, forbidden fields and wrong pins
refuse with their stable code and exit `1`. Revisions follow §3.1: an
XML source reports the initial-import base revision and the committed
output revision, while a `DocumentEnvelope` input keeps its own
revision for both (read-only operation).

Exit `0` means ok, `1` means refused or a remaining error, `2` means
invalid invocation. Exactly one `Result/1` goes to stdout; invocation
diagnostics go to stderr. No module discovery or network follows profile
data.

## Browser budget

The browser bundle budget is canvas-only and is not covered here.
