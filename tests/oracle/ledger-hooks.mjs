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
]);

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
  if (PINNED.has(specifier)) {
    return { url: pinnedEntry(specifier), shortCircuit: true };
  }
  if (STUBS.has(specifier)) {
    return { url: new URL(STUBS.get(specifier), HERE).href, shortCircuit: true };
  }
  const resolved = await next(specifier, context);
  if (resolved.url.includes('/tests/upstream/') && resolved.url.endsWith('.js')) {
    return { ...resolved, format: 'module' };
  }
  return resolved;
}
