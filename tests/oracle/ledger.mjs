#!/usr/bin/env node
// Mocha-compatible dry-run: collects nested `describe` + `it()` titles from the
// vendored upstream suites without executing test bodies or hooks, and writes
// tests/upstream/LEDGER.json ({"<file>": ["<full title>", ...]}), the dynamic-title
// source scripts/port_coverage.py reads.
//
// Usage: node tests/oracle/ledger.mjs [--check]
//   default writes LEDGER.json; --check exits 1 when regeneration drifts.
import { Module, register } from 'node:module';
import { readdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath, pathToFileURL } from 'node:url';

register(new URL('./ledger-hooks.mjs', import.meta.url));

const ORACLE_DIR = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(ORACLE_DIR, '..', '..');
const UPSTREAM = path.join(ROOT, 'tests', 'upstream');
const LEDGER = path.join(UPSTREAM, 'LEDGER.json');
// Vendored CommonJS files (bpmnlint lib/) `require()` bare specifiers; point
// the CJS resolver at the oracle's pinned node_modules (ESM imports already
// resolve there through ledger-hooks.mjs).
process.env.NODE_PATH = path.join(ORACLE_DIR, 'node_modules');
Module._initPaths();
const PACKAGES = [
  'saxen',
  'min-dash',
  'moddle',
  'moddle-xml',
  'bpmn-moddle',
  'bpmn-auto-layout',
  'bpmnlint',
  'bpmnlint-utils',
  'moddle-utils',
];
// bpmnlint titles are keyed by their FULL mocha title (describe path joined
// with ' > '), because RuleTester-generated case titles repeat across rules.
const FULL_TITLE_PACKAGES = new Set(['bpmnlint', 'bpmnlint-utils', 'moddle-utils']);
const SUFFIXES = new Set(['.js', '.cjs', '.mjs']);

const noHook = (..._args) => undefined;
const fakeCtx = new Proxy(
  {},
  {
    get: () => (..._args) => undefined,
  },
);

function collectFile(fullTitle = false) {
  const titles = [];
  const stack = [];
  // Bare it() titles (whitespace-normalized): the ledger must use the exact strings
  // scripts/port_coverage.py scans statically, so both sources deduplicate and only
  // genuinely dynamic titles are added. In full-title mode the describe path is
  // prepended (`a > b > title`), matching the RuleTester keying of the plan.
  const recordIt = (title, fn) => {
    // Pending tests (`it('...')` without callback) never execute: omit them,
    // like the static scan (which only matches `it('...', ...)`).
    if (typeof fn !== 'function') {
      return;
    }
    const bare = String(title).replace(/\s+/g, ' ').trim();
    titles.push(fullTitle && stack.length ? [...stack, bare].join(' > ') : bare);
  };
  recordIt.only = recordIt;
  recordIt.skip = noHook;
  // Mocha executes describe callbacks synchronously; mirroring that keeps the
  // title stack exact even when a suite registers sibling describes back to
  // back (RuleTester does, without awaiting anything).
  const runDescribe = (title, cb) => {
    if (typeof cb !== 'function') {
      return;
    }
    stack.push(String(title).replace(/\s+/g, ' ').trim());
    try {
      cb.call(fakeCtx);
    } finally {
      stack.pop();
    }
  };
  runDescribe.only = runDescribe;
  runDescribe.skip = noHook;

  const it = recordIt;
  const describe = runDescribe;
  Object.assign(globalThis, {
    describe,
    context: describe,
    suite: describe,
    it,
    specify: it,
    test: it,
    before: noHook,
    beforeEach: noHook,
    after: noHook,
    afterEach: noHook,
    setup: noHook,
    teardown: noHook,
    suiteSetup: noHook,
    suiteTeardown: noHook,
    xdescribe: runDescribe.skip,
    xcontext: runDescribe.skip,
    xit: recordIt.skip,
    xspecify: recordIt.skip,
  });
  return { titles };
}

function specFiles(pkg) {
  const found = [];
  const walk = (dir) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(full);
      } else if (entry.isFile() && SUFFIXES.has(path.extname(entry.name))) {
        found.push(full);
      }
    }
  };
  walk(path.join(UPSTREAM, pkg, 'test'));
  const sorted = found.sort();
  // bpmnlint integration/performance files execute real work (child processes,
  // config compilation) at import time; they are claimed through the static
  // scan instead (N-A / adapted CLI and packaging suites).
  if (pkg === 'bpmnlint') {
    return sorted.filter((f) => {
      const rel = path.relative(UPSTREAM, f).replace(/\\/g, '/');
      return rel.includes('/test/spec/') || rel.includes('/test/rules/');
    });
  }
  return sorted;
}

async function main() {
  const check = process.argv.includes('--check');
  const ledger = {};
  const failures = [];
  for (const pkg of PACKAGES) {
    process.chdir(path.join(UPSTREAM, pkg));
    for (const file of specFiles(pkg)) {
      const rel = path.relative(UPSTREAM, file).replace(/\\/g, '/');
      const { titles } = collectFile(FULL_TITLE_PACKAGES.has(pkg));
      try {
        await import(`${pathToFileURL(file).href}?ledger=1`);
      } catch (error) {
        failures.push(`${rel}: ${error.message.split('\n')[0]}`);
        continue;
      }
      if (titles.length > 0) {
        ledger[rel] = titles;
      }
    }
  }
  for (const failure of failures) {
    process.stderr.write(`ledger: skip ${failure}\n`);
  }
  const rendered = `${JSON.stringify(ledger, null, 2)}\n`;
  if (check) {
    let committed = null;
    try {
      committed = readFileSync(LEDGER, 'utf8');
    } catch {
      process.stderr.write('ledger: no committed LEDGER.json\n');
      process.exitCode = 1;
      return;
    }
    if (JSON.parse(committed) && JSON.stringify(JSON.parse(committed)) !== JSON.stringify(ledger)) {
      const committedKeys = new Set(Object.keys(JSON.parse(committed)));
      const drifted = Object.keys(ledger).filter((k) => !committedKeys.has(k));
      const missing = [...committedKeys].filter((k) => !(k in ledger));
      process.stderr.write(`ledger: drift in ${drifted.length} files, ${missing.length} files lost\n`);
      for (const key of [...drifted, ...missing]) {
        process.stderr.write(`ledger:   ${key}\n`);
      }
      process.exitCode = 1;
      return;
    }
    process.stdout.write(`ledger: ok (${Object.keys(ledger).length} files)\n`);
    return;
  }
  writeFileSync(LEDGER, rendered);
  process.stdout.write(
    `ledger: wrote ${LEDGER} (${Object.keys(ledger).length} files, ${failures.length} skipped)\n`,
  );
}

await main();
