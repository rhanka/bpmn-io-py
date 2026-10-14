# Brief — implementing agent for `plan/04-BRANCH_profile-contracts.md`

You are the implementing agent for this repository (GitHub `rhanka/bpmn-io-py`, PyPI `bpmn-io`),
on branch `profile-contracts` (already created). A supervising session reviews your commits and
the CI; you do not need its permission to execute the plan.

## Mission

Execute, lot by lot and in order, `plan/04-BRANCH_profile-contracts.md` (Lots 19 → 21; Lot 22
review is driven by the supervisor): the Python library's share of lot 0 of the
`profile-mechanism/1` design — pinned contract artifacts, the Python binding of every contract,
and parity-corpus cases whose expected outputs are checked by independent Node references.
Read first, completely: the plan; the design `DESIGN.md` R3.1 in
the conductor design folder (local, read-only; path given at launch) (verify its SHA-256 equals
the one given in the plan's Lot 19 / launch message) with `CONVERGENCE-R3.md` and
`CONSENSUS-R3-bpmn-py.md`; then `spec/SPEC_EVOL_BPMN_PY.md`, `docs/naming.md`,
`scripts/sync_upstream.py`, `tests/oracle/README.md`.

## Hard rules

1. **No interpreter in this branch.** Nothing under `src/**`: no loader, compiler, evaluator,
   validator, JCS encoder, lint bridge or CLI. Python in this branch is limited to
   `scripts/sync_contracts.py` (stdlib) and tests under `tests/contracts/**`.
2. Expected outputs are authored from the DESIGN text first, then checked against the Node
   references (Ajv 2020, RFC 8785 reference canonicalizer, Node `crypto`). If a reference disagrees
   with your reading of the DESIGN, do not "fix" the expectation to match: record the
   disagreement in the plan's Feedback Loop (`open`, with DESIGN line and reference output) and
   continue with the other cases.
3. The conductor folder is read-only. Never write there. No business or private-repository name enters this repository.
4. Never edit `src/**`, `tests/upstream/**`, `UPSTREAM.toml`, `UPSTREAM.lock`, `LICENSE`,
   `plan/done/**`, `tmp/**`. Conditional paths need the `BR04-EXn` exception declared in the plan.
5. Commit discipline: one logical change per commit, `git add <explicit files>` only, plan
   checkboxes updated in the same commit. ABSOLUTELY NO attribution trailers: no
   `Co-Authored-By`, no `Generated with`, no session or agent ids in commit messages.
6. Local lot gate (plan bottom) before every commit. Push to `origin profile-contracts` at least
   at the end of every lot; CI must be green (`gh run list --branch profile-contracts`).
7. Repository text in English. Decide routine questions yourself and record the rationale in the
   plan's Feedback Loop. For a real blocker, write a `blocked` entry in the Feedback Loop, commit,
   push and stop.

## End of mission

After Lot 21 is green on CI, open the PR to `main` (title `Profile mechanism lot 0: contracts and
parity corpus`, no release, no version change), put the PR URL in the Feedback Loop, commit,
push and stop. Do not merge: the supervisor runs the double review first.
