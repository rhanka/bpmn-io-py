#!/usr/bin/env node
// Reference profile-c14n/2 digest helper (DESIGN.md R3.1, section 3.1).
//
// Independent Node reference used by tests/contracts: JCS canonicalization
// (UTF-16 key order via default Array sort, no whitespace, UTF-8, ECMAScript
// number rendering through JSON.stringify, -0 rendered by JSON.stringify as
// 0) then lowercase SHA-256 over UTF-8 bytes (Node crypto).
//
// Usage:
//   node tests/oracle/profile_c14n.mjs <json-file>...   # prints "<sha>  <file>" per file
//   node tests/oracle/profile_c14n.mjs --jcs <json-file>  # prints canonical bytes
import { readFileSync } from 'node:fs';
import crypto from 'node:crypto';
import process from 'node:process';

export const jcs = (x) =>
  x === null || typeof x !== 'object'
    ? JSON.stringify(x)
    : Array.isArray(x)
      ? `[${x.map(jcs).join(',')}]`
      : `{${Object.keys(x)
          .sort()
          .map((k) => `${JSON.stringify(k)}:${jcs(x[k])}`)
          .join(',')}}`;

export const sha256 = (bytes) => crypto.createHash('sha256').update(bytes).digest('hex');
export const digest = (value) => sha256(jcs(value));

const args = process.argv.slice(2);
if (args.length === 0) {
  process.stderr.write('Usage: node tests/oracle/profile_c14n.mjs [--jcs] <json-file>...\n');
  process.exit(2);
}
let onlyJcs = false;
const files = [];
for (const arg of args) {
  if (arg === '--jcs') {
    onlyJcs = true;
  } else {
    files.push(arg);
  }
}
for (const file of files) {
  const raw = readFileSync(file, 'utf8');
  const value = JSON.parse(raw);
  if (onlyJcs) {
    process.stdout.write(`${jcs(value)}\n`);
  } else {
    process.stdout.write(`${digest(value)}  ${file}\n`);
  }
}
