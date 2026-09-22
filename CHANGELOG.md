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
