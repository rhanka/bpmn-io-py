# Profile mechanism (Python)

Neutral implementation of DESIGN R3.3 for loading, compiling and evaluating
profiles over the native moddle tree, plus canonical bytes, identities,
compatibility, envelopes, results and the headless bridge.

Sources: DESIGN R3.3 and the F1 plan rev d (see vendored contracts). The
Python binding follows `spec/SPEC_PROFILE_MECHANISM_PY.md`.

## Layout

- `src/bpmn_io/profile/_lexical.py` — strict pre-parse (§2.1.1 codes).
- `src/bpmn_io/profile/_schema.py` — closed 29-keyword validator.
- `src/bpmn_io/profile/_c14n.py` — `profile-c14n/2` JCS bytes (§3.1).
- `src/bpmn_io/profile/_stable_id.py` — `stable-id/1` allocation (§3.2).
- `src/bpmn_io/profile/_unicode_case.py` — full default case, pinned 15.0.0.
- `src/bpmn_io/profile/_unicode15.py` — generated frozen 15.0.0 tables
  (from `contracts/unicode-case/15.0.0/case-table.json`, never edited by hand).
- `src/bpmn_io/profile/_loader.py` — `load_profile` with digest pins.
- `src/bpmn_io/profile/_compiler.py` — selectors, predicates, recipes (§2.4.1).
- `src/bpmn_io/profile/_evaluate.py` — read-only bounded evaluation.
- `src/bpmn_io/profile/_compat.py` — `check_compatibility` matrix (§3.3).
- `src/bpmn_io/profile/_envelope.py` — envelope, support, import (§5).
- `src/bpmn_io/profile/_results.py` — `PureResult`/`Result` and `Report/2`.
- `src/bpmn_io/profile/_bridge.py` — headless native counterpart (§8.1).
- `src/bpmn_io/profile/_inventory.py` — hash-only externalization checks (§12).
- `src/bpmn_io/profile/_lint/` — lint bridge over the literal port (§6.4),
  re-exported as `bpmn_io.profile.lint`.

## Usage

```python
from bpmn_io.profile import check_lexical, compile_profile, jcs, load_profile

raw = open("neutral-profile.json", "rb").read()
schema = open("profile-mechanism-1.schema.json", "rb").read()
lexical = check_lexical(raw)
loaded = load_profile(raw, schema_bytes=schema)
compiled = compile_profile(loaded.payload)
text = jcs({"b": 1, "a": 2})
```

`import_envelope` accepts an injected `codec` callable for raw sources;
by default the wired `bpmn_io.codec` decodes them (document JSON for
`native-json`, parse then project for `bpmn-xml`). Unparseable sources
refuse with `document-not-loaded`. `lint` accepts the `CompiledProfile`
from `compile_profile` (see `docs/profile-lint.md`) as well as the
transport dicts.

## Compatibility

`check_compatibility` applies the §3.3 rows in order with the source
remedies and the schema axis. The parity suite covers all 151 corpus
verdicts plus ordering probes.

## Tests

- `tests/profile/test_foundation.py` — lexical, JCS and identity parity.
- `tests/profile/test_schema_parity.py` — closed subset parity.
- `tests/profile/test_compat_parity.py` — 151 verdicts and cross-product.
- `tests/profile/test_loader_compiler.py` — neutral substitution and negatives.
- `tests/profile/test_evaluate.py` — native-tree evaluation.
- `tests/profile/test_envelope_bridge.py` — envelope, codec and bridge.
- `tests/profile/test_lint_wiring.py` — load → compile → lint and the
  XML → codec → envelope → compatibility chain.
