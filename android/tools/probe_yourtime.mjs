// A PROBE, NOT A TEST: what the new labels read for her three flights, with the
// phone in San Francisco and again in Mumbai.
//
//   node tools/probe_yourtime.mjs America/Los_Angeles
if (process.argv[2]) process.env.TZ = process.argv[2];
import { execSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const out = mkdtempSync(join(tmpdir(), 'time-'));
execSync(`npx tsc --ignoreConfig lib/time.ts lib/zoneAbbr.ts --outDir "${out}" --module es2022 --target es2022 --moduleResolution bundler --skipLibCheck`, { stdio: 'inherit' });
// NODE WANTS THE EXTENSION METRO DOES NOT: tsc keeps "./zoneAbbr" as written.
const timeJs = join(out, 'time.js');
writeFileSync(timeJs, readFileSync(timeJs, 'utf8').replace("from './zoneAbbr'", "from './zoneAbbr.js'"));
const T = await import(pathToFileURL(join(out, 'time.js')).href);

const ends = [
  ['KL606 dep SFO', '2026-09-23T13:45', 'America/Los_Angeles', 'PDT'],
  ['KL606 arr AMS', '2026-09-24T09:05', 'Europe/Amsterdam', 'CEST'],
  ['KL877 dep AMS', '2026-09-24T11:45', 'Europe/Amsterdam', 'CEST'],
  ['KL877 arr BOM', '2026-09-25T00:01', 'Asia/Kolkata', 'IST'],
  ['AI1891 dep BOM', '2026-09-25T08:10', 'Asia/Kolkata', 'IST'],
  ['AI1891 arr IDR', '2026-09-25T09:35', 'Asia/Kolkata', 'IST'],
];
console.log(`phone zone: ${Intl.DateTimeFormat().resolvedOptions().timeZone}`);
for (const [what, iso, tz, label] of ends) {
  const ts = T.zonedIsoToTs(iso, tz);
  const yours = T.yourTime(ts, tz);
  console.log(`${what.padEnd(16)} ${iso.slice(11)} ${label}${yours === null ? '' : ' · ' + yours}`);
}
