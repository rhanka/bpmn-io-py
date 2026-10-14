// Resolve hook for the oracle ledger dry-run (loaded via module.register).
//
// * the six pinned packages resolve to tests/oracle/node_modules (the vendored
//   trees carry no node_modules of their own);
// * test-only helpers (chai, sinon, ajv, fast-glob, ...) resolve to local stubs;
// * `.js` files under tests/upstream/ load as ESM (no package.json there).
import { readFileSync } from 'node:fs';

const HERE = new URL('./', import.meta.url);

const PINNED = new Set([
  'saxen',
  'min-dash',
  'moddle',
  'moddle-xml',
  'bpmn-moddle',
  'bpmn-auto-layout',
  'bpmnlint',
  'bpmnlint-utils',
  '@bpmn-io/moddle-utils',
]);

function pinnedName(specifier) {
  for (const name of PINNED) {
    if (specifier === name || specifier.startsWith(`${name}/`)) {
      return name;
    }
  }
  return null;
}

const STUBS = new Map(
  Object.entries({
    chai: './stubs/chai.mjs',
    sinon: './stubs/misc.mjs',
    'sinon-chai': './stubs/misc.mjs',
    'xsd-schema-validator': './stubs/misc.mjs',
    ajv: './stubs/misc.mjs',
    table: './stubs/misc.mjs',
    'fast-glob': './stubs/fast-glob.mjs',
    '@rollup/plugin-node-resolve': './stubs/misc.mjs',
    'zeebe-bpmn-moddle/resources/zeebe.json': './stubs/zeebe.json',
  }),
);

function pinnedEntry(name) {
  const dir = new URL(`./node_modules/${name}/`, HERE);
  const pkg = JSON.parse(readFileSync(new URL('./package.json', dir), 'utf8'));
  const exported = pkg.exports?.['.'];
  const entry =
    typeof exported === 'string'
      ? exported
      : (exported?.import ?? exported?.default ?? pkg.main ?? 'index.js');
  return new URL(entry, dir).href;
}

export async function resolve(specifier, context, next) {
  const pinned = pinnedName(specifier);
  if (pinned === specifier) {
    return { url: pinnedEntry(specifier), shortCircuit: true };
  }
  if (pinned) {
    const sub = specifier.slice(pinned.length + 1);
    return { url: new URL(`./node_modules/${pinned}/${sub}`, HERE).href, shortCircuit: true };
  }
  if (STUBS.has(specifier)) {
    return { url: new URL(STUBS.get(specifier), HERE).href, shortCircuit: true };
  }
  const resolved = await next(specifier, context);
  // bpmnlint ships CommonJS `.js` files; forcing ESM there breaks the CJS
  // default-export interop its `.mjs` suites rely on. Every other vendored
  // package ships ESM `.js` files that need the explicit format (the vendored
  // trees carry no package.json of their own).
  if (
    resolved.url.includes('/tests/upstream/') &&
    !resolved.url.includes('/tests/upstream/bpmnlint/') &&
    resolved.url.endsWith('.js')
  ) {
    return { ...resolved, format: 'module' };
  }
  return resolved;
}
