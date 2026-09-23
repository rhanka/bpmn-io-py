#!/usr/bin/env node
// Generic oracle runner: one JSON call from argv becomes one JSON envelope on stdout.
//
//   node run.mjs '{"op":"ping"}'
//   node run.mjs '{"op":"call","package":"min-dash","path":"flatten","args":[[[1],[2]]]}'
//
// Ops: `ping` (node version + pinned package versions), `call` (invoke a dotted
// export path of an installed package with JSON args, awaiting thenables).
// Results must be JSON-serializable; canonical model dumps go through dump.mjs.
import { createRequire } from 'node:module';
import process from 'node:process';

const requirePkg = createRequire(import.meta.url);
const PINNED = ['saxen', 'min-dash', 'moddle', 'moddle-xml', 'bpmn-moddle', 'bpmn-auto-layout'];

function fail(message) {
  process.stdout.write(`${JSON.stringify({ ok: false, error: { message } })}\n`);
}

async function ping() {
  const packages = {};
  for (const name of PINNED) {
    packages[name] = requirePkg(`./node_modules/${name}/package.json`).version;
  }
  return { node: process.version, packages };
}

async function call({ package: name, path: dotted, args }) {
  if (!/^[A-Za-z0-9_-]+$/.test(name ?? '')) {
    throw new Error(`invalid package: ${name}`);
  }
  const segments = String(dotted ?? '').split('.');
  if (segments.some((s) => !/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(s))) {
    throw new Error(`invalid path: ${dotted}`);
  }
  let target = await import(name);
  for (const segment of segments) {
    target = target?.[segment];
  }
  if (typeof target !== 'function') {
    throw new Error(`not a function: ${name}.${dotted}`);
  }
  return await target(...(args ?? []));
}

async function main() {
  let payload;
  try {
    payload = JSON.parse(process.argv[2] ?? '{}');
  } catch (error) {
    fail(`invalid JSON payload: ${error.message}`);
    return;
  }
  try {
    const result =
      payload.op === 'ping' ? await ping() : payload.op === 'call' ? await call(payload) : null;
    if (payload.op !== 'ping' && payload.op !== 'call') {
      throw new Error(`unknown op: ${payload.op}`);
    }
    process.stdout.write(`${JSON.stringify({ ok: true, result: result ?? null })}\n`);
  } catch (error) {
    fail(error?.message ?? String(error));
  }
}

await main();
