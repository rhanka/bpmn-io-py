# Brief — implementing agent for `plan/02-BRANCH_lint.md`

You are the implementing agent for this repository (GitHub `rhanka/bpmn-io-py`, PyPI `bpmn-io`),
on branch `port-lint` (already created, draft PR #5). A supervising session reviews your commits
and the CI; you do not need its permission to execute the plan.

## Mission

Execute, lot by lot and in order, `plan/02-BRANCH_lint.md` (Lots 11 → 15): a literal, byte-exact
transposition of `bpmnlint` 11.15.0 and its helpers to pure Python, then the 0.2.0 release.
Read first, completely: `plan/02-BRANCH_lint.md`, `plan/done/01-BRANCH_port-v1.md` (how the v1 port
was executed), `spec/SPEC_EVOL_BPMN_PY.md`, `CONTRIBUTING.md`, `docs/naming.md`, `docs/porting.md`.

## Method (identical to the v1 port)

- Sources to transpose: only `tests/upstream/{bpmnlint,bpmnlint-utils,moddle-utils}/**` after Lot 11
  vendors them at the pinned commits. Never copy from `tmp/wb-functions` (non-literal workbench).
- Same file split, function order and names (snake_case), same messages, rule names and report
  shapes; module header `# Transposed from <repo>@<short-sha> <path> (MIT).`
- Every upstream test case claimed by one Python test with
  `@pytest.mark.upstream("<file relative to tests/upstream>", "<title>")`; RuleTester cases use
  the FULL mocha title from `tests/upstream/LEDGER.json`. N-A cases are still claimed by a
  `pytest.skip` test stating the reason.
- Oracle differential (Node, `tests/oracle`) on every lint report: same rules, same element ids,
  same messages, same order.

## Hard rules

1. Never edit `tests/upstream/**` (except the generated `LEDGER.json`), `src/bpmn_io/resources/**`,
   `UPSTREAM.lock`, `LICENSE`, `plan/done/**`, `tmp/**`.
2. Conditional paths need the `BR02-EXn` exception already declared in the plan's Feedback Loop.
3. Commit discipline: one logical change per commit, `git add <explicit files>` only, plan
   checkboxes updated in the same commit. ABSOLUTELY NO attribution trailers: no `Co-Authored-By`,
   no `Generated with`, no session or agent ids in commit messages.
4. Local gate before every commit (see the plan). Push to `origin port-lint` at least at the end of
   every lot; CI must be green (`gh run list --branch port-lint`).
5. Repository text in English. Decide routine questions yourself and record the rationale in the
   plan's Feedback Loop. For a real blocker, write a `blocked` entry in the Feedback Loop, commit,
   push and stop.

## Release (Lot 15)

Once `scripts/port_coverage.py --strict` is 100 % and CI is green on PR #5: mark it ready, merge it
with a merge commit (`gh pr merge 5 --merge`), then on `main` tag `v0.2.0` and push the tag; the
`Release` workflow publishes to PyPI through Trusted Publishing. Verify
`https://pypi.org/pypi/bpmn-io/0.2.0/json` and the GitHub release, then archive the plan.
