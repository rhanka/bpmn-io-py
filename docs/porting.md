# Porting guide

How each `src/bpmn_io/**` module maps to its upstream source, and how to resync
after an upstream version bump.

## Module map

Every ported module carries a `# Transposed from <org>/<repo>@<pin> <path> (MIT).`
header naming the exact upstream file and pinned version. The layout is
one-to-one:

| Port module | Upstream source (vendored under `tests/upstream/`) |
|---|---|
| `bpmn_io/saxen/` | `saxen` `lib/` — lenient SAX parser |
| `bpmn_io/moddle/` | `moddle` `lib/` — meta-model runtime |
| `bpmn_io/moddle_xml/` | `moddle-xml` `lib/` — XML reader/writer |
| `bpmn_io/bpmn_moddle/` | `bpmn-moddle` `lib/` — `BpmnModdle` wiring |
| `bpmn_io/auto_layout/` | `bpmn-auto-layout` `lib/` — automatic DI layout |
| `bpmn_io/check.py` | `bpmn-moddle` L0 integrity check |
| `bpmn_io/cli.py` | new (no upstream equivalent): `bpmn-io` console script |
| `bpmn_io/bpmn_moddle/types.py` | new: `is_a` narrowing helper |
| `bpmn_io/_js.py`, `bpmn_io/_min_dash.py` | JS semantic helpers (`Math.round`, `undefined`, iteration order) and the transposed `min-dash` subset |

Descriptors (`src/bpmn_io/resources/`) are vendored verbatim from the upstream
repositories and must never be hand-edited.

## Naming

JavaScript names map mechanically to Python: `camelCase` → `snake_case`,
`$`-prefixed moddle internals → explicit attributes (see
[`docs/naming.md`](naming.md) for the full inventory, including per-lot tables
and deliberate non-transpositions).

## Test idioms

Upstream mocha suites map to pytest modules fixture-for-fixture
(`scripts/port_coverage.py` reports the claim status; CI enforces it).
Byte-identical conformance goes through the Node differential oracle
(`tests/oracle/`): canonical model dumps, serialized XML, and layout output
must match the pinned upstream packages exactly.

## Resyncing after an upstream bump

A version bump is a new branch, never an edit on a release branch:

1. Bump the pin in `UPSTREAM.toml` and run `scripts/sync_upstream.py` (updates
   `UPSTREAM.lock`, the vendored files, `THIRD_PARTY_NOTICES.md`).
2. Port the upstream diff into `src/bpmn_io/` (keep the `# Transposed from`
   headers accurate) and claim any new upstream test cases.
3. Run the Lot gate: `ruff check`, `ruff format --check`, `mypy`,
   `pytest` (incl. `-m oracle`), `scripts/port_coverage.py`,
   `scripts/sync_upstream.py --check`, `node tests/oracle/ledger.mjs --check`.
4. Regenerate derived artifacts: `scripts/gen_stubs.py` (committed `types.pyi`,
   checked by `gen_stubs.py --check`) and `node tests/oracle/ledger.mjs`
   (committed `tests/upstream/LEDGER.json`, checked with `--check`).

## Generated files policy

Generated files are committed and drift-checked in CI, never hand-edited:

| Generated file | Generator | Drift gate |
|---|---|---|
| `tests/upstream/LEDGER.json` | `node tests/oracle/ledger.mjs` | `ledger.mjs --check` |
| `src/bpmn_io/bpmn_moddle/types.pyi` | `scripts/gen_stubs.py` | `gen_stubs.py --check` |
| `UPSTREAM.lock` + vendored files | `scripts/sync_upstream.py` | `sync_upstream.py --check` |
