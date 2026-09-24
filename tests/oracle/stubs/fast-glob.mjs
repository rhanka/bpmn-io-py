// Minimal working `fast-glob` stand-in: only `globSync` with `*`/`?`/`**`
// segments is needed (moddle schema.js enumerates its fixture models at
// collection time). Results are files only, sorted for determinism.
import { readdirSync, statSync } from 'node:fs';
import path from 'node:path';

function matchPart(part, name) {
  const source = [...part]
    .map((ch) => {
      if (ch === '*') {
        return '[^/]*';
      }
      if (ch === '?') {
        return '[^/]';
      }
      if ('\\^$.|+(){}[]'.includes(ch)) {
        return `\\${ch}`;
      }
      return ch;
    })
    .join('');
  return new RegExp(`^${source}$`).exec(name) !== null;
}

function walkDirs(dir, out) {
  out.push(dir);
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const entry of entries) {
    if (entry.isDirectory()) {
      walkDirs(path.join(dir, entry.name), out);
    }
  }
}

export function globSync(pattern) {
  let candidates = ['.'];
  for (const part of String(pattern).split('/')) {
    if (part === '**') {
      const all = [];
      for (const dir of candidates) {
        walkDirs(dir, all);
      }
      candidates = all;
      continue;
    }
    const next = [];
    for (const dir of candidates) {
      let entries;
      try {
        entries = readdirSync(dir, { withFileTypes: true });
      } catch {
        continue;
      }
      for (const entry of entries) {
        if (matchPart(part, entry.name)) {
          next.push(path.join(dir, entry.name));
        }
      }
    }
    candidates = next;
  }
  return candidates
    .filter((candidate) => {
      try {
        return statSync(candidate).isFile();
      } catch {
        return false;
      }
    })
    .sort();
}

export default { globSync };
