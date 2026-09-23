#!/usr/bin/env node
// Generic oracle runner: one JSON call from argv becomes one JSON envelope on stdout.
//
//   node run.mjs '{"op":"ping"}'
//   node run.mjs '{"op":"call","package":"min-dash","path":"flatten","args":[[[1],[2]]]}'
//
// Ops: `ping` (node version + pinned package versions), `call` (invoke a dotted
// export path of an installed package with JSON args, awaiting thenables).
// Results must be JSON-serializable; canonical model dumps go through dump.mjs.
//
// `call` args revive two markers (test-only, so callbacks can cross the JSON
// boundary): `{ "$fn": "<source>" }` compiles to a function, `{ "$undefined": true }`
// becomes `undefined`. Results still serialize to JSON (`undefined` → `null`).
import { createRequire } from 'node:module';
import process from 'node:process';

import { descriptorDump, modelDump, modelSerializeBatch } from './dump.mjs';

const requirePkg = createRequire(import.meta.url);
const PINNED = ['saxen', 'min-dash', 'moddle', 'moddle-xml', 'bpmn-moddle', 'bpmn-in-color-moddle', 'bpmn-auto-layout'];

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

function revive(value) {
  if (Array.isArray(value)) {
    return value.map(revive);
  }
  if (value !== null && typeof value === 'object') {
    const keys = Object.keys(value);
    if (keys.length === 1 && typeof value.$fn === 'string') {
      return new Function(`return (${value.$fn})`)();
    }
    if (keys.length === 1 && value.$undefined === true) {
      return undefined;
    }
    // Preserve own `__proto__` keys (fromEntries would set the prototype instead).
    const out = {};
    for (const [key, entry] of Object.entries(value)) {
      const revived = revive(entry);
      if (key === '__proto__') {
        Object.defineProperty(out, key, {
          value: revived,
          enumerable: true,
          writable: true,
          configurable: true,
        });
      } else {
        out[key] = revived;
      }
    }
    return out;
  }
  return value;
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
  return await target(...revive(args ?? []));
}

function serializeError(err) {
  return err instanceof Error ? err.message : String(err);
}

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (chunk) => {
      data += chunk;
    });
    process.stdin.on('end', () => resolve(data));
    process.stdin.on('error', reject);
  });
}

async function saxen({ inputs }) {
  const { Parser } = await import('saxen');
  return (inputs ?? []).map(({ xml, chunks, options }) => {
    const parser = new Parser();
    if (options && options.ns) {
      parser.ns(options.ns);
    }
    const events = [];
    parser.on('openTag', (name, getAttrs, _decode, tagEnd, getContext) => {
      events.push(['openTag', name, getAttrs(), tagEnd, getContext()]);
    });
    parser.on('closeTag', (name, _decode, tagStart, getContext) => {
      events.push(['closeTag', name, tagStart, getContext()]);
    });
    parser.on('text', (chars, _decode, getContext) => {
      events.push(['text', chars, getContext()]);
    });
    parser.on('comment', (value, _decode, getContext) => {
      events.push(['comment', value, getContext()]);
    });
    parser.on('attention', (value, _decode, getContext) => {
      events.push(['attention', value, getContext()]);
    });
    parser.on('cdata', (data, getContext) => {
      events.push(['cdata', data, getContext()]);
    });
    parser.on('question', (value, getContext) => {
      events.push(['question', value, getContext()]);
    });
    parser.on('error', (err, getContext) => {
      events.push(['error', serializeError(err), getContext()]);
    });
    parser.on('warn', (err, getContext) => {
      events.push(['warn', serializeError(err), getContext()]);
    });
    let returned;
    if (chunks) {
      for (const chunk of chunks) {
        returned = parser.write(chunk);
      }
      returned = parser.end();
    } else {
      returned = parser.parse(xml);
    }
    return { events, error: returned == null ? null : serializeError(returned) };
  });
}

async function main() {
  let payload;
  try {
    const raw = process.argv[2] === '@stdin' ? await readStdin() : (process.argv[2] ?? '{}');
    payload = JSON.parse(raw);
  } catch (error) {
    fail(`invalid JSON payload: ${error.message}`);
    return;
  }
  try {
    const OPS = {
      ping: () => ping(),
      call: (args) => call(args),
      'descriptor-dump': (args) => descriptorDump(args.packages),
      'model-dump': (args) => modelDump(args.xml, args.type),
      'model-dump-batch': (args) => Promise.all(
        (args.inputs ?? []).map((input) => modelDump(input.xml, input.type).then(
          (dump) => ({ dump }),
          (error) => ({ error: error?.message ?? String(error) }),
        )),
      ),
      'model-serialize-batch': (args) => modelSerializeBatch(args.inputs),
      saxen: (args) => saxen(args),
    };
    const run = OPS[payload.op];
    if (!run) {
      throw new Error(`unknown op: ${payload.op}`);
    }
    const result = await run(payload);
    process.stdout.write(`${JSON.stringify({ ok: true, result: result ?? null })}\n`);
  } catch (error) {
    fail(error?.message ?? String(error));
  }
}

await main();
