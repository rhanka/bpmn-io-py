// Minimal `chai` stand-in for the ledger dry-run: only `expect`/`use` shapes matter,
// assertions inside `it()` bodies never execute.
import { absurd } from './absurd.mjs';

export const expect = absurd();
export const assert = absurd();
export const should = absurd();

export function use() {}

export default { expect, assert, should, use };
