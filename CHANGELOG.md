# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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
