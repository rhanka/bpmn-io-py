# Contributing

## Setup

- Python 3.11+ and [uv](https://docs.astral.sh/uv/). Node 22 only for the differential oracle.
- `uv sync` installs the project in editable mode with the `dev` dependency group.
- `uv run pre-commit install` enables the local hooks (ruff, uv lock check, hygiene).

## Porting rules

1. **One upstream, one pin.** `UPSTREAM.toml` pins each bpmn.io package by version, tag and commit.
   `scripts/sync_upstream.py` vendors descriptors, fixtures and JS test-suites and writes
   `UPSTREAM.lock`; CI fails if a vendored file was edited by hand.
2. **Literal transposition.** Port from the vendored sources `tests/upstream/<pkg>/lib/**` only.
   Port functions in the same order and with the same names as upstream
   (snake_case). Each ported module starts with a header comment naming the upstream file and commit.
   JavaScript semantics that do not exist in Python (truthiness, `undefined` vs `null`, key order,
   `min-dash` helpers) live in one shared module and are tested there.
3. **Every upstream test is claimed.** Each Python test that transposes an upstream `it(...)` carries
   `@pytest.mark.upstream("<js file relative to tests/upstream>", "<it title>")`. Cases that cannot
   be transposed (browser-only, distro packaging, performance) are still claimed, with a test that is
   `pytest.skip`-ed and states the reason. `scripts/port_coverage.py --strict` becomes a CI gate once
   the count reaches 100 %.
4. **Oracle tests** (`@pytest.mark.oracle`) compare the Python port with the pinned JS packages
   run through Node. They are skipped locally without `tests/oracle/node_modules`.

## Upstream moved

Dependabot opens a PR on `tests/oracle/package.json` when bpmn.io publishes a new version. To adopt
it: bump `UPSTREAM.toml`, run `scripts/sync_upstream.py`, port the diff (upstream changelog + git
diff between commits), update `src/bpmn_py/upstream.py` and `CHANGELOG.md`.

## Release

1. Update `CHANGELOG.md` and bump the version: `uv version <x.y.z>`.
2. Commit, then tag `v<x.y.z>` and push the tag.
3. The `Release` workflow builds, publishes to PyPI through Trusted Publishing (environment `pypi`,
   PEP 740 attestations) and creates the GitHub release with the artifacts attached.
