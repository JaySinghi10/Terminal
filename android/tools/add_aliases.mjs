// WRITES tools/aliases.mjs INTO lib/airports.ts, in place, idempotently.
//
//   node tools/add_aliases.mjs            rewrite the rows and report
//   node tools/add_aliases.mjs --check    report only, change nothing
//
// A ROW ALIAS is appended to the row's search string -- the eighth element --
// which is created from the folded "name city" when the row has none, because
// that string REPLACES the derived haystack rather than extending it. Latin
// aliases are stored folded, as every other word in a search string is; an
// alias in another script is stored as written, and build() folds it with the
// rest. A METRO ALIAS becomes a new key of CITY_AIRPORTS over the same group,
// inserted under the key it extends.
//
// The row's other seven fields are never rewritten: the line is spliced at the
// last two numbers, so the coordinates keep the digits they had.
import { readFileSync, writeFileSync, mkdtempSync } from 'node:fs';
import { execSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { ALIASES, METRO_ALIASES } from './aliases.mjs';

const FILE = 'lib/airports.ts';
const check = process.argv.includes('--check');

const out = mkdtempSync(join(tmpdir(), 'airports-'));
execSync(`npx tsc --ignoreConfig ${FILE} --outDir "${out}" --module es2022 --target es2022 --moduleResolution bundler --skipLibCheck`, { stdio: 'inherit' });
const A = await import(pathToFileURL(join(out, 'airports.js')).href);
const norm = A.normalizeTerm;

const src = readFileSync(FILE, 'utf8');
const nl = src.includes('\r\n') ? '\r\n' : '\n';
const lines = src.split(nl);

const hasWord = (s, q) => s === q || s.startsWith(`${q} `) || s.endsWith(` ${q}`) || s.includes(` ${q} `);

// ── rows ─────────────────────────────────────────────────────────────────────
const rowAt = new Map();
for (let i = 0; i < lines.length; i++) {
  const m = /^\s*\["([A-Z0-9]{3})", /.exec(lines[i]);
  if (m) rowAt.set(m[1], i);
}
const ROW_RE = /^(\s*\["[A-Z0-9]{3}", .*?, -?\d+\.\d+, -?\d+\.\d+)(?:, "((?:[^"\\]|\\.)*)")?(\],?)\s*$/;

const report = {};
const missing = [];
const dupes = [];
const seen = new Map();
let rowsTouched = 0;
for (const [region, rows] of Object.entries(ALIASES)) {
  report[region] = { aliases: 0, rows: 0, already: 0 };
  for (const [code, aliases] of Object.entries(rows)) {
    const i = rowAt.get(code);
    if (i === undefined) { missing.push(`${region}:${code}`); continue; }
    const m = ROW_RE.exec(lines[i]);
    if (!m) throw new Error(`row for ${code} did not parse: ${lines[i]}`);
    const fields = JSON.parse(lines[i].trim().replace(/,$/, ''));
    let search = m[2] !== undefined ? JSON.parse(`"${m[2]}"`) : norm(`${fields[1]} ${fields[2]}`);
    let added = 0;
    for (const alias of aliases) {
      const n = norm(alias);
      if (n === '') { console.log(`  empty after normalisation: ${code} ${JSON.stringify(alias)}`); continue; }
      const key = n;
      if (seen.has(key) && seen.get(key) !== code) dupes.push(`${JSON.stringify(alias)} on ${code} and ${seen.get(key)}`);
      seen.set(key, code);
      if (hasWord(norm(search), n)) { report[region].already++; continue; }
      search += ' ' + (A.isLatinTerm(n) ? n : alias.trim().toLowerCase());
      added++;
    }
    if (added > 0) {
      lines[i] = `${m[1]}, ${JSON.stringify(search)}${m[3]}`;
      report[region].aliases += added;
      report[region].rows++;
      rowsTouched++;
    }
  }
}

// ── metro keys ───────────────────────────────────────────────────────────────
let metroAdded = 0;
const metroMissing = [];
const keyLine = (key) => lines.findIndex(l => new RegExp(`^\\s*"${key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}": \\[`).test(l));
for (const [base, aliases] of Object.entries(METRO_ALIASES)) {
  const i = keyLine(base);
  if (i < 0) { metroMissing.push(base); continue; }
  const arr = /(\[.*\]),?\s*$/.exec(lines[i])[1];
  const indent = /^(\s*)/.exec(lines[i])[1];
  let insertAt = i + 1;
  for (const alias of aliases) {
    const key = A.isLatinTerm(norm(alias)) ? norm(alias) : alias.trim().toLowerCase();
    if (norm(key) === '') { console.log(`  empty after normalisation: metro ${JSON.stringify(alias)}`); continue; }
    if (seen.has(norm(key)) && seen.get(norm(key)) !== `metro:${base}`) dupes.push(`${JSON.stringify(alias)} on metro ${base} and ${seen.get(norm(key))}`);
    seen.set(norm(key), `metro:${base}`);
    if (keyLine(key) >= 0) continue;
    lines.splice(insertAt, 0, `${indent}${JSON.stringify(key)}: ${arr},`);
    insertAt++;
    metroAdded++;
  }
}

// ── report ───────────────────────────────────────────────────────────────────
let total = 0;
console.log('\nregion              aliases  rows  already-present');
for (const [region, r] of Object.entries(report)) {
  total += r.aliases;
  console.log(`${region.padEnd(20)}${String(r.aliases).padStart(7)}${String(r.rows).padStart(6)}${String(r.already).padStart(10)}`);
}
console.log(`${'row aliases'.padEnd(20)}${String(total).padStart(7)}${String(rowsTouched).padStart(6)}`);
console.log(`metro keys added: ${metroAdded}`);
if (missing.length) console.log(`anchors not in the dataset (skipped): ${missing.join(' ')}`);
if (metroMissing.length) console.log(`metro keys not in CITY_AIRPORTS (skipped): ${metroMissing.join(' ')}`);
if (dupes.length) { console.log(`DUPLICATE ALIASES:\n  ${dupes.join('\n  ')}`); process.exitCode = 1; }

if (check) { console.log('(check only, nothing written)'); }
else {
  writeFileSync(FILE, lines.join(nl), 'utf8');
  console.log(`wrote ${FILE}`);
}
