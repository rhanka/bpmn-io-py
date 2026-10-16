#!/usr/bin/env node
// Independent Node references for the profile parity corpus (lot 21).
//
// Ops (all print one JSON result envelope to stdout, exit 0):
//   ajv --schema <schema.json> [--data <data.json>] [--registry <id=json-path>...]
//       Validate data with Ajv 2020 in strict mode, like the design validator
//       (strict:true, allowUnionTypes:true, allErrors:true). With --data,
//       prints {ok, errors}; without, prints {ok:true} when the schema itself
//       compiles (unknown $refs refuse at load).
//   canonicalize --data <json-file>
//       RFC 8785 bytes of the parsed value via the pinned `canonicalize`
//       package, plus {bytes, sha256} (Node crypto).
//   lexical --hex <utf8-hex>
//       DESIGN section 2.1 strict pre-parse over the decoded bytes:
//       {status:"ok"} or {status:"refused", code}. Codes: profile-json,
//       profile-json-duplicate-key, profile-unicode, profile-number.
//   sha256 --file <path>
//       Lowercase hex SHA-256 of the raw file bytes (Node crypto).
import { readFileSync } from 'node:fs';
import crypto from 'node:crypto';
import process from 'node:process';
import { createRequire } from 'node:module';

const requirePkg = createRequire(import.meta.url);
const Ajv2020 = requirePkg('ajv/dist/2020').default;
const canonicalize = requirePkg('canonicalize').default ?? requirePkg('canonicalize');

const sha256 = (bytes) => crypto.createHash('sha256').update(bytes).digest('hex');

function fail(message) {
  process.stdout.write(`${JSON.stringify({ ok: false, error: { message } })}\n`);
  process.exitCode = 1;
}

function flag(args, name) {
  const values = [];
  const rest = [];
  for (let i = 0; i < args.length; i += 1) {
    if (args[i] === name) {
      values.push(args[i + 1]);
      i += 1;
    } else {
      rest.push(args[i]);
    }
  }
  return { values, rest };
}

function ajvOp(args) {
  const { values: schemas, rest: r1 } = flag(args, '--schema');
  const { values: datas, rest: r2 } = flag(r1, '--data');
  const { values: registries } = flag(r2, '--registry');
  if (schemas.length !== 1 || datas.length > 1) {
    fail('ajv needs exactly one --schema and zero or one --data');
    return;
  }
  try {
    // Same options as the design validator (validate-r2.mjs).
    const ajv = new Ajv2020({
      strict: true,
      strictRequired: false,
      allowUnionTypes: true,
      allErrors: true,
    });
    for (const entry of registries) {
      const eq = entry.indexOf('=');
      if (eq < 0) throw new Error(`bad --registry ${entry}`);
      ajv.addSchema(JSON.parse(readFileSync(entry.slice(eq + 1), 'utf8')));
    }
    const schema = JSON.parse(readFileSync(schemas[0], 'utf8'));
    const validate = ajv.compile(schema);
    if (datas.length === 0) {
      process.stdout.write(`${JSON.stringify({ ok: true, compiled: true })}\n`);
      return;
    }
    const data = JSON.parse(readFileSync(datas[0], 'utf8'));
    const valid = validate(data);
    process.stdout.write(
      `${JSON.stringify({ ok: valid === true, errors: validate.errors ?? null })}\n`,
    );
  } catch (error) {
    process.stdout.write(
      `${JSON.stringify({ ok: false, error: { message: String(error?.message ?? error) } })}\n`,
    );
  }
}

function canonicalizeOp(args) {
  const { values: datas } = flag(args, '--data');
  if (datas.length !== 1) {
    fail('canonicalize needs exactly one --data');
    return;
  }
  try {
    const value = JSON.parse(readFileSync(datas[0], 'utf8'));
    const bytes = canonicalize(value);
    process.stdout.write(`${JSON.stringify({ ok: true, bytes, sha256: sha256(bytes) })}\n`);
  } catch (error) {
    process.stdout.write(
      `${JSON.stringify({ ok: false, error: { message: String(error?.message ?? error) } })}\n`,
    );
  }
}

function lexicalCheck(text) {
  const code = (c) => ({ status: 'refused', code: c });
  const tokens =
    text.match(
      /"(?:[^"\\\u0000-\u001F]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?|true|false|null|[{}[\]:,]|\S/g,
    ) ?? [];
  let i = 0;
  const UNICODE = 'unicode';
  const DUPLICATE = 'duplicate';
  const stringOf = (t) => {
    let s;
    try {
      s = JSON.parse(t);
    } catch {
      throw new Error('malformed');
    }
    if (typeof s !== 'string') throw new Error('malformed');
    for (const c of s) {
      const n = c.codePointAt(0);
      if (n >= 0xd800 && n <= 0xdfff) throw new Error(UNICODE);
    }
    return s;
  };
  const parseValue = () => {
    const t = tokens[i++];
    if (t === '{') {
      const keys = new Set();
      if (tokens[i] === '}') {
        i += 1;
        return true;
      }
      for (;;) {
        const k = stringOf(tokens[i++]);
        if (keys.has(k)) throw new Error(DUPLICATE);
        keys.add(k);
        if (tokens[i++] !== ':') return 'malformed';
        const r = parseValue();
        if (r !== true) return r;
        if (tokens[i] !== ',') break;
        i += 1;
      }
      if (tokens[i++] !== '}') return 'malformed';
      return true;
    }
    if (t === '[') {
      if (tokens[i] === ']') {
        i += 1;
        return true;
      }
      for (;;) {
        const r = parseValue();
        if (r !== true) return r;
        if (tokens[i] !== ',') break;
        i += 1;
      }
      if (tokens[i++] !== ']') return 'malformed';
      return true;
    }
    if (t?.startsWith('"')) {
      stringOf(t);
      return true;
    }
    if (/^-?[0-9]/.test(t ?? '')) {
      const n = Number(t);
      if (!Number.isFinite(n) || (Number.isInteger(n) && !Number.isSafeInteger(n))) {
        return 'number';
      }
      return true;
    }
    if (['true', 'false', 'null'].includes(t)) return true;
    return 'malformed';
  };
  let r;
  try {
    r = parseValue();
  } catch (error) {
    if (error?.message === UNICODE) return code('profile-unicode');
    if (error?.message === DUPLICATE) return code('profile-json-duplicate-key');
    return code('profile-json');
  }
  if (r === 'number') return code('profile-number');
  if (r !== true || i !== tokens.length) return code('profile-json');
  // DESIGN §2.1.1 step 3: the traversal above already decoded every string
  // token and checked its Unicode scalars, so any remaining whole-text grammar
  // failure (for example leading U+00A0 skipped by the pre-scan) is
  // profile-json, never profile-unicode.
  try {
    JSON.parse(text);
  } catch {
    return code('profile-json');
  }
  return { status: 'ok' };
}

function lexicalOp(args) {
  const { values: hexes } = flag(args, '--hex');
  if (hexes.length !== 1) {
    fail('lexical needs exactly one --hex');
    return;
  }
  let text;
  try {
    text = Buffer.from(hexes[0], 'hex').toString('utf8');
  } catch (error) {
    process.stdout.write(`${JSON.stringify({ status: 'refused', code: 'profile-unicode' })}\n`);
    return;
  }
  process.stdout.write(`${JSON.stringify(lexicalCheck(text))}\n`);
}

function shaOp(args) {
  const { values: files } = flag(args, '--file');
  if (files.length !== 1) {
    fail('sha256 needs exactly one --file');
    return;
  }
  process.stdout.write(
    `${JSON.stringify({ ok: true, sha256: sha256(readFileSync(files[0])) })}\n`,
  );
}

const [op, ...rest] = process.argv.slice(2);
if (op === 'ajv') ajvOp(rest);
else if (op === 'canonicalize') canonicalizeOp(rest);
else if (op === 'lexical') lexicalOp(rest);
else if (op === 'sha256') shaOp(rest);
else {
  fail('usage: profile_references.mjs (ajv|canonicalize|lexical|sha256) ...');
}
