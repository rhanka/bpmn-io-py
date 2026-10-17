# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.2.2] - 2026-10-16

### Added

- `contracts/profile-mechanism/1/`: vendored, SHA-256-pinned contract files
  for the profile mechanism, declared in `CONTRACTS.toml` / `CONTRACTS.lock`
  and verified offline by `scripts/sync_contracts.py --check`.
- `contracts/profile-parity-corpus/1/`: language-neutral parity corpus
  (format `profile-parity-corpus/1`, corpus version 1.0.0, git tag
  `profile-corpus-v1.0.0`), shipped in the sdist.
- `spec/SPEC_PROFILE_MECHANISM_PY.md`: Python binding of the profile
  mechanism. No runtime API yet; the library code is unchanged.

## [0.2.1] - 2026-10-14

### Fixed

- bpmnlint isometry on definitions without root elements: the `global` and
  `no-bpmndi` rules now reproduce the upstream `rule-error` reports
  (`Cannot read properties of undefined (reading 'filter')`, resp.
  `'map'`) instead of silently reporting nothing. JS property access in
  lint rules now distinguishes the direct read (`strict_get`, returning
  `UNDEFINED` when unset) from `get()` on an `isMany` property and from
  `|| []` fallbacks (full audit of every `prop_list()` call site in
  `docs/naming.md`).
- `bpmn-io lint --json` now omits report keys whose value is `undefined`
  (JSON.stringify semantics) instead of writing `"id": null` for elements
  without an id. The library API still exposes `UNDEFINED`.

### Changed

- The lint oracle differential now covers every vendored `.bpmn` diagram
  (394 files) under both `bpmnlint:recommended` and `bpmnlint:all`, with
  the same parse outcome asserted on both sides.
- Dependabot no longer opens updates on vendored upstream manifests
  (`tests/upstream/**` excluded); `/tests/oracle` remains the
  upstream-moved signal.

## [0.1.0] - 2026-09-24

### Added

- Repository scaffold: uv project, ruff, mypy strict, pytest, pre-commit, GitHub Actions CI,
  tag-driven PyPI release through Trusted Publishing, Dependabot.
- Vendored upstream descriptors, fixtures and test-suites with a sha256 provenance ledger
  (`UPSTREAM.toml`, `UPSTREAM.lock`, `scripts/sync_upstream.py`).
- `scripts/port_coverage.py`: upstream test-suite port coverage report and CI gate.
- Upstream Node oracle pins (`tests/oracle`).
- Pure-Python port of `moddle`, `moddle-xml`, `bpmn-moddle` (six descriptors) and
  `bpmn-auto-layout`: read, check, build, lay out and write BPMN 2.0 XML with no
  runtime dependency.
- Typed creation surface: generated `bpmn_moddle/types.pyi` (`create` overloads on
  descriptor literals, `is_a` narrowing), verified with `stubtest` + `assert_type`.
- `bpmn-io` CLI: `check | roundtrip | layout <file> [--json]` with stable exit codes.
