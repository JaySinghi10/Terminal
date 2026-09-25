// WHEN A FLIGHT CAME DOWN, UNDER PLAIN NODE. lib/arrival.ts imports only
// lib/time.ts and lib/landing.ts, neither of which touches React Native, so it
// is compiled to a temp directory with the project's own tsc and exercised
// here, as test_departure.mjs does for its module.
//
//   node tools/test_arrival.mjs
//
// THE QUESTIONS: which measured time wins, which word goes with it, what the
// figure is against the schedule, and that nothing is said about a landing the
// effective status does not stand behind or a time that has not happened.
import { execSync } from 'node:child_process';
import { mkdtempSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const out = mkdtempSync(join(tmpdir(), 'arrival-'));
execSync(`npx tsc --ignoreConfig lib/arrival.ts --outDir "${out}" --module es2022 --target es2022 --moduleResolution bundler --skipLibCheck`, { stdio: 'inherit' });
// NODE WANTS THE EXTENSION THE BUNDLER DOES NOT. See test_departure.mjs.
for (const name of readdirSync(out)) {
  if (!name.endsWith('.js')) continue;
  const p = join(out, name);
  writeFileSync(p, readFileSync(p, 'utf8').replace(
    /(from\s+['"])(\.{1,2}\/[^'"]+?)(['"])/g,
    (m, a, spec, b) => (spec.endsWith('.js') ? m : `${a}${spec}.js${b}`)));
}
const A = await import(pathToFileURL(join(out, 'arrival.js')).href);

let pass = 0, fail = 0;
const check = (label, cond, detail) => {
  if (cond) { pass++; console.log('  ok   ' + label); }
  else { fail++; console.log('  FAIL ' + label + '   -> ' + JSON.stringify(detail)); }
};

const SEC = 1000;
const MIN = 60 * SEC;
// A FIXED MOMENT: 14:00 UTC, 19:30 in Delhi, where these flights land.
const NOW = Date.UTC(2026, 8, 24, 14, 0, 0);
const TZ = 'Asia/Kolkata';
const OFFSET = 330;

function zoned(ms) {
  const d = new Date(ms + OFFSET * MIN);
  const p = n => String(n).padStart(2, '0');
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())}`
    + `T${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}+05:30`;
}
// FR24's format: UTC, no zone marker, to the second.
const utc = ms => new Date(ms).toISOString().slice(0, 19);

// ONE ARRIVAL AT DEL, due an hour ago, with only the fields the rule reads.
const SCHED = NOW - 60 * MIN;
function f({
  sched = SCHED, touchdown = null, runway = null, actual = null, actualSource = 'revised',
  noSchedule = false,
} = {}) {
  return {
    landedUtc: touchdown === null ? null : utc(touchdown),
    to: {
      scheduledIso: noSchedule ? null : zoned(sched),
      runwayIso: runway === null ? null : zoned(runway),
      actualIso: actual === null ? null : zoned(actual),
      actualSource: actual === null ? null : actualSource,
      timezone: TZ,
    },
  };
}
const at = (rec, eff = 'landed', now = NOW) => A.arrivalOutcomeOf(rec, now, eff);

console.log('-- which time, and which word --');
const td = SCHED - 38 * MIN;
check('FR24 touchdown: landed, at the touchdown',
  at(f({ touchdown: td }))?.word === 'landed' && at(f({ touchdown: td })).at === td, at(f({ touchdown: td })));
check('FR24 wins over the provider runway time and the gate time',
  at(f({ touchdown: td, runway: td + 2 * MIN, actual: td + 9 * MIN })).at === td);
check('no FR24: the provider runway time, still landed',
  at(f({ runway: td })).word === 'landed' && at(f({ runway: td })).at === td);
check('only a gate time: arrived, at the gate time',
  at(f({ actual: td + 7 * MIN })).word === 'arrived' && at(f({ actual: td + 7 * MIN })).at === td + 7 * MIN);
check('a runway time the server wrote into actualIso is a landing',
  at(f({ actual: td, actualSource: 'runway' })).word === 'landed');
check('nothing measured: nothing said', at(f()) === null, at(f()));

console.log('-- only what has happened, only when it has landed --');
check('a touchdown still ahead is passed over for the gate time',
  at(f({ touchdown: NOW + 5 * MIN, actual: NOW - MIN })).word === 'arrived');
check('every time still ahead: nothing', at(f({ touchdown: NOW + MIN, runway: NOW + MIN, actual: NOW + MIN })) === null);
check('a touchdown this very second counts', at(f({ touchdown: NOW }))?.at === NOW);
check('not landed by the effective status: nothing, whatever is on the record',
  at(f({ touchdown: td }), 'active') === null && at(f({ touchdown: td }), 'stale') === null
    && at(f({ touchdown: td }), 'scheduled') === null);

console.log('-- the figure against the schedule --');
check('38 minutes before the schedule is -38', at(f({ touchdown: td })).offsetMin === -38, at(f({ touchdown: td })));
check('12 minutes after is 12', at(f({ touchdown: SCHED + 12 * MIN })).offsetMin === 12);
check('on the minute is 0', at(f({ touchdown: SCHED })).offsetMin === 0);
check('29 seconds late rounds to 0', at(f({ touchdown: SCHED + 29 * SEC })).offsetMin === 0);
check('31 seconds late rounds to 1', at(f({ touchdown: SCHED + 31 * SEC })).offsetMin === 1);
check('a gate time is measured the same way: 31 early',
  at(f({ actual: SCHED - 31 * MIN })).offsetMin === -31);
check('no schedule: the time, and no figure',
  at(f({ touchdown: td, noSchedule: true })).offsetMin === null && at(f({ touchdown: td, noSchedule: true })).at === td);

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail === 0 ? 0 : 1);
