// WHERE A DEPARTURE STANDS, UNDER PLAIN NODE. lib/departure.ts imports only
// lib/time.ts and lib/landing.ts, neither of which touches React Native, so it
// is compiled to a temp directory with the project's own tsc and exercised
// here, as test_pending_rules.mjs does for its module.
//
//   node tools/test_departure.mjs
//
// THE BOUNDARIES ARE THE POINT: the first minute of the count, the estimate
// against the clock, the half hour after which a record is too old to count
// on, the hour before the schedule a takeoff may not come from, and the
// forty-five minutes a taxi is believed.
//
// effectiveStatus IS NOT HERE. It lives in lib/saved.tsx with the store, which
// plain node cannot load, so every case passes the effective status in -- as
// departurePhase does -- and the FR24 promotion is checked through
// fr24TakeoffTs, the one function that decision reads.
import { execSync } from 'node:child_process';
import { mkdtempSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const out = mkdtempSync(join(tmpdir(), 'departure-'));
execSync(`npx tsc --ignoreConfig lib/departure.ts --outDir "${out}" --module es2022 --target es2022 --moduleResolution bundler --skipLibCheck`, { stdio: 'inherit' });
// NODE WANTS THE EXTENSION THE BUNDLER DOES NOT. The app's imports are written
// for Metro, which resolves './time' to time.ts; plain node resolves nothing
// it is not told the name of, so the emitted relative imports get their '.js'.
for (const name of readdirSync(out)) {
  if (!name.endsWith('.js')) continue;
  const p = join(out, name);
  writeFileSync(p, readFileSync(p, 'utf8').replace(
    /(from\s+['"])(\.{1,2}\/[^'"]+?)(['"])/g,
    (m, a, spec, b) => (spec.endsWith('.js') ? m : `${a}${spec}.js${b}`)));
}
const D = await import(pathToFileURL(join(out, 'departure.js')).href);

let pass = 0, fail = 0;
const check = (label, cond, detail) => {
  if (cond) { pass++; console.log('  ok   ' + label); }
  else { fail++; console.log('  FAIL ' + label + '   -> ' + JSON.stringify(detail)); }
};

const SEC = 1000;
const MIN = 60 * SEC;
// A FIXED MOMENT, so every run asks the same questions: 14:00 UTC, which is
// 19:30 in Mumbai.
const NOW = Date.UTC(2026, 8, 24, 14, 0, 0);
const TZ = 'Asia/Kolkata';
const OFFSET = 330;

// Local wall clock with a true offset, as the provider writes every *Iso.
function zoned(ms) {
  const d = new Date(ms + OFFSET * MIN);
  const p = n => String(n).padStart(2, '0');
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())}`
    + `T${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}+05:30`;
}
// FR24's own format: UTC, no zone marker, to the second.
const utc = ms => new Date(ms).toISOString().slice(0, 19);

// ONE DEPARTURE FROM BOM, with only the fields the rule reads set to anything.
function f({
  sched = NOW - 12 * MIN, delay = null, actual = null, actualSource = 'revised',
  live = true, runway = null, takeoff = null, takeoffText = null, updatedAt = NOW,
  noSchedule = false,
} = {}) {
  return {
    updatedAt,
    takeoffUtc: takeoffText ?? (takeoff === null ? null : utc(takeoff)),
    from: {
      scheduledIso: noSchedule ? null : zoned(sched),
      actualIso: actual === null ? null : zoned(actual),
      actualSource: actual === null ? null : actualSource,
      runwayIso: runway === null ? null : zoned(runway),
      liveFeed: live,
      delay,
      timezone: TZ,
    },
  };
}
const phase = (rec, eff = 'scheduled', now = NOW) => D.phaseOfDeparture(rec, now, eff);
const is = (p, kind, extra = {}) =>
  p.kind === kind && Object.entries(extra).every(([k, v]) => p[k] === v);

console.log('-- counting: the first minute --');
check('at the scheduled minute itself, nothing is late yet',
  is(phase(f({ sched: NOW })), 'before'), phase(f({ sched: NOW })));
check('59 seconds past, still nothing',
  is(phase(f({ sched: NOW - 59 * SEC })), 'before'), phase(f({ sched: NOW - 59 * SEC })));
check('60 seconds past, delayed 1m',
  is(phase(f({ sched: NOW - MIN })), 'counting', { minutes: 1 }), phase(f({ sched: NOW - MIN })));
check('12 minutes past, delayed 12m',
  is(phase(f()), 'counting', { minutes: 12 }), phase(f()));
check('12m59s past is still 12m -- whole minutes, floored',
  is(phase(f({ sched: NOW - 12 * MIN - 59 * SEC })), 'counting', { minutes: 12 }),
  phase(f({ sched: NOW - 12 * MIN - 59 * SEC })));
check('before its time, no count, even with an estimate',
  is(phase(f({ sched: NOW + 5 * MIN, delay: 30 })), 'before'), phase(f({ sched: NOW + 5 * MIN, delay: 30 })));
check('no readable schedule, no count',
  is(phase(f({ noSchedule: true })), 'before'), phase(f({ noSchedule: true })));

console.log('-- counting: the larger of the clock and the airline --');
check('announced 45 late, 10 past: 45',
  is(phase(f({ sched: NOW - 10 * MIN, delay: 45 })), 'counting', { minutes: 45 }),
  phase(f({ sched: NOW - 10 * MIN, delay: 45 })));
check('announced 5 late, 12 past: 12',
  is(phase(f({ delay: 5 })), 'counting', { minutes: 12 }), phase(f({ delay: 5 })));
check('announced 45 late at its very minute: 45 from the start',
  is(phase(f({ sched: NOW, delay: 45 })), 'counting', { minutes: 45 }), phase(f({ sched: NOW, delay: 45 })));
check('an early estimate never counts backwards: 1 past, 5 early, delayed 1m',
  is(phase(f({ sched: NOW - MIN, delay: -5 })), 'counting', { minutes: 1 }),
  phase(f({ sched: NOW - MIN, delay: -5 })));

console.log('-- counting: only on a record recent enough to say --');
check('updated exactly 30 minutes ago still counts',
  is(phase(f({ updatedAt: NOW - 30 * MIN })), 'counting', { minutes: 12 }),
  phase(f({ updatedAt: NOW - 30 * MIN })));
check('updated 30 minutes and a second ago does not',
  is(phase(f({ updatedAt: NOW - 30 * MIN - SEC })), 'unknown'),
  phase(f({ updatedAt: NOW - 30 * MIN - SEC })));
check('an old record before its time is still simply before',
  is(phase(f({ sched: NOW + MIN, updatedAt: NOW - 5 * 60 * MIN })), 'before'),
  phase(f({ sched: NOW + MIN, updatedAt: NOW - 5 * 60 * MIN })));

console.log('-- statuses that are not counted --');
check('cancelled is off', is(phase(f(), 'cancelled'), 'off'), phase(f(), 'cancelled'));
check('diverted is off', is(phase(f(), 'diverted'), 'off'), phase(f(), 'diverted'));
check('a provider with no opinion is not counted for it',
  is(phase(f(), 'unknown'), 'unknown'), phase(f(), 'unknown'));

console.log('-- left the gate --');
const sched25 = NOW - 25 * MIN;
const gate18 = sched25 + 18 * MIN;
check('a live revised actual in the past: left the gate, 18m late, at the gate time',
  is(phase(f({ sched: sched25, actual: gate18 }), 'active'), 'leftGate', { lateMin: 18, at: gate18 }),
  phase(f({ sched: sched25, actual: gate18 }), 'active'));
check('the count had reached 25; the gate time says 18, and 18 is shown',
  phase(f({ sched: sched25 }), 'scheduled').minutes === 25
    && phase(f({ sched: sched25, actual: gate18 }), 'active').lateMin === 18);
check('three minutes early off the gate is -3, which the words call on time',
  is(phase(f({ sched: sched25, actual: sched25 - 3 * MIN }), 'active'), 'leftGate', { lateMin: -3 }),
  phase(f({ sched: sched25, actual: sched25 - 3 * MIN }), 'active'));
check('a gate time in the future is a forecast, not a departure',
  is(phase(f({ sched: sched25, actual: NOW + 2 * MIN }), 'active'), 'tookOff', { at: null }),
  phase(f({ sched: sched25, actual: NOW + 2 * MIN }), 'active'));
check('no live coverage: the gate time is not believed',
  is(phase(f({ sched: sched25, actual: gate18, live: false }), 'active'), 'tookOff', { at: null }),
  phase(f({ sched: sched25, actual: gate18, live: false }), 'active'));
check('coverage unknown, as on a record from before v15: not believed either',
  is(phase(f({ sched: sched25, actual: gate18, live: null }), 'active'), 'tookOff', { at: null }),
  phase(f({ sched: sched25, actual: gate18, live: null }), 'active'));
check('a gate time over an hour before the schedule is not this flight',
  is(phase(f({ sched: NOW + 30 * MIN, actual: NOW - 31 * MIN - SEC }), 'active'), 'tookOff', { at: null }),
  phase(f({ sched: NOW + 30 * MIN, actual: NOW - 31 * MIN - SEC }), 'active'));
check('a runway time in the actual field is a takeoff, not a gate',
  is(phase(f({ sched: sched25, actual: gate18, actualSource: 'runway', runway: gate18 }), 'active'),
    'tookOff', { at: gate18 }),
  phase(f({ sched: sched25, actual: gate18, actualSource: 'runway', runway: gate18 }), 'active'));
check('a landed flight is never shown at the gate',
  is(phase(f({ sched: sched25, actual: gate18 }), 'landed'), 'tookOff', { at: null }),
  phase(f({ sched: sched25, actual: gate18 }), 'landed'));

console.log('-- the taxi: forty-five minutes --');
const early = NOW - 2 * 60 * MIN;
check('44m59s after the gate, still taxiing',
  is(phase(f({ sched: early, actual: NOW - 45 * MIN + SEC }), 'active'), 'leftGate'),
  phase(f({ sched: early, actual: NOW - 45 * MIN + SEC }), 'active'));
check('45 minutes after the gate with no takeoff timed, it is taken to be in the air',
  is(phase(f({ sched: early, actual: NOW - 45 * MIN }), 'active'), 'tookOff', { at: null }),
  phase(f({ sched: early, actual: NOW - 45 * MIN }), 'active'));

console.log('-- took off --');
const takeoff4 = NOW - 4 * MIN;
check('FR24 saw it four minutes ago: took off, at that minute',
  is(phase(f({ sched: NOW - 30 * MIN, takeoff: takeoff4 }), 'active'), 'tookOff', { at: takeoff4 }),
  phase(f({ sched: NOW - 30 * MIN, takeoff: takeoff4 }), 'active'));
check('a takeoff ends the taxi, whatever the gate time',
  is(phase(f({ sched: sched25, actual: gate18, takeoff: takeoff4 }), 'active'), 'tookOff', { at: takeoff4 }),
  phase(f({ sched: sched25, actual: gate18, takeoff: takeoff4 }), 'active'));
check('the runway time does the same',
  is(phase(f({ sched: sched25, actual: gate18, runway: NOW - 3 * MIN }), 'active'), 'tookOff', { at: NOW - 3 * MIN }),
  phase(f({ sched: sched25, actual: gate18, runway: NOW - 3 * MIN }), 'active'));
check('FR24 is read before the runway time',
  phase(f({ sched: sched25, takeoff: takeoff4, runway: NOW - 3 * MIN }), 'active').at === takeoff4);
check('a runway time still ahead is not a takeoff',
  is(phase(f({ sched: sched25, actual: gate18, runway: NOW + MIN }), 'active'), 'leftGate'),
  phase(f({ sched: sched25, actual: gate18, runway: NOW + MIN }), 'active'));
check('FR24 with a Z on the end is read the same',
  is(phase(f({ sched: NOW - 30 * MIN, takeoffText: utc(takeoff4) + 'Z' }), 'active'), 'tookOff', { at: takeoff4 }),
  phase(f({ sched: NOW - 30 * MIN, takeoffText: utc(takeoff4) + 'Z' }), 'active'));

console.log('-- the FR24 promotion reads fr24TakeoffTs, so its limits are these --');
check('a takeoff in the past, after the schedule: believed',
  D.fr24TakeoffTs(f({ sched: NOW - 30 * MIN, takeoff: takeoff4 }), NOW) === takeoff4);
check('a takeoff in the future: refused',
  D.fr24TakeoffTs(f({ sched: NOW - 30 * MIN, takeoff: NOW + MIN }), NOW) === null);
check('exactly sixty minutes before the schedule: believed',
  D.fr24TakeoffTs(f({ sched: NOW + 55 * MIN, takeoff: NOW - 5 * MIN }), NOW) === NOW - 5 * MIN);
check('sixty minutes and a second before: another rotation, refused',
  D.fr24TakeoffTs(f({ sched: NOW + 55 * MIN, takeoff: NOW - 5 * MIN - SEC }), NOW) === null);
check('no schedule to check it against: refused outright',
  D.fr24TakeoffTs(f({ takeoff: takeoff4, noSchedule: true }), NOW) === null);
check('no takeoff: nothing', D.fr24TakeoffTs(f(), NOW) === null);

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail === 0 ? 0 : 1);
