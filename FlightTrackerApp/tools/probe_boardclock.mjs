// A PROBE, NOT A TEST: what a board clock's zone label reads, next to the label
// the server wrote for the same airport, and what "your time" says.
//
//   node tools/probe_boardclock.mjs America/Los_Angeles
if (process.argv[2]) process.env.TZ = process.argv[2];
import { execSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const out = mkdtempSync(join(tmpdir(), 'board-'));
execSync(`npx tsc --ignoreConfig lib/time.ts lib/zoneAbbr.ts lib/airports.ts --outDir "${out}" --module es2022 --target es2022 --moduleResolution bundler --skipLibCheck`, { stdio: 'inherit' });
// NODE WANTS THE EXTENSION METRO DOES NOT: tsc keeps "./zoneAbbr" as written.
const timeJs = join(out, 'time.js');
writeFileSync(timeJs, readFileSync(timeJs, 'utf8').replace("from './zoneAbbr'", "from './zoneAbbr.js'"));
const T = await import(pathToFileURL(join(out, 'time.js')).href);
const A = await import(pathToFileURL(join(out, 'airports.js')).href);

console.log(`phone zone: ${Intl.DateTimeFormat().resolvedOptions().timeZone}`);
// [what, board ISO with its true offset, IATA, the label the server printed]
const cases = [
  ['KL877 dep AMS', '2026-09-24T11:45+02:00', 'AMS', 'CEST'],
  ['KL877 arr BOM', '2026-09-25T00:01+05:30', 'BOM', 'IST'],
  ['KL606 dep SFO', '2026-09-23T13:45-07:00', 'SFO', 'PDT'],
  ['EK500 dep DXB', '2026-09-24T09:30+04:00', 'DXB', 'GMT+4'],
  ['QF1 dep SYD', '2026-09-24T15:55+10:00', 'SYD', 'AEST'],
  ['LH dep FRA in Jan', '2027-01-10T10:00+01:00', 'FRA', 'CET'],
  ['JL dep HND', '2026-09-24T08:00+09:00', 'HND', 'JST'],
  ['LA dep GRU', '2026-09-24T22:10-03:00', 'GRU', 'GMT-3'],
];
let bad = 0;
for (const [what, iso, iata, server] of cases) {
  const tz = A.airportByCode(iata)?.tz ?? null;
  const ts = Date.parse(iso);
  const zone = T.zoneAbbrAt(ts, tz);
  const yours = T.yourTime(ts, tz);
  if (zone !== server) bad++;
  console.log(`${what.padEnd(18)} ${iso.slice(11, 16)} ${String(zone).padEnd(7)} server ${server.padEnd(6)} ${zone === server ? 'same' : 'DIFFERENT'}${yours ? '  · ' + yours : ''}`);
}
console.log(bad === 0 ? 'every label matches the server' : `${bad} label(s) differ from the server`);
