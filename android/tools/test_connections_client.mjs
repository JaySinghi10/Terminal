// THE CONNECTION STREAM'S CLIENT STATE, UNDER PLAIN NODE. lib/connections.ts
// imports nothing, so it is compiled to a temp directory with the project's own
// tsc and exercised here, as test_airports.mjs does for the resolver.
//
//   node tools/test_connections_client.mjs
import { execSync } from 'node:child_process';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const out = mkdtempSync(join(tmpdir(), 'conn-'));
execSync(`npx tsc --ignoreConfig lib/connections.ts --outDir "${out}" --module es2022 --target es2022 --moduleResolution bundler --skipLibCheck`, { stdio: 'inherit' });
const C = await import(pathToFileURL(join(out, 'connections.js')).href);

let pass = 0, fail = 0;
const check = (label, cond, detail) => {
  if (cond) { pass++; console.log('  ok   ' + label); }
  else { fail++; console.log('  FAIL ' + label + '   -> ' + JSON.stringify(detail)); }
};

const it = (hub, a, b) => ({ kind: 'via', legs: [{ flight_number: a }, { flight_number: b }], hub, overnight: false, international: false, transfer: 'self' });

console.log('-- the splitter: whole lines only, whatever the chunks --');
{
  const split = C.lineSplitter();
  const lines = [];
  const body = '{"type":"plan","hub_days":3}\n{"type":"hub","hub":"BOM"}\n{"type":"done"}\n';
  // Every possible cut point, in three pieces.
  let allGood = true;
  for (let i = 1; i < body.length - 1; i++) {
    for (let j = i + 1; j < body.length; j++) {
      const s = C.lineSplitter();
      const got = [...s(body.slice(0, i)), ...s(body.slice(i, j)), ...s(body.slice(j)), ...s('\n')];
      if (got.length !== 3 || got.some(l => { try { JSON.parse(l); return false; } catch { return true; } })) {
        allGood = false;
      }
    }
  }
  check('every way of cutting three lines into three chunks yields the three lines', allGood);
  lines.push(...split('{"a":1}\n\n\n{"b":'));
  check('empty lines are dropped and a half line is held back', lines.length === 1 && lines[0] === '{"a":1}', lines);
  lines.push(...split('2}'));
  check('nothing more until its newline', lines.length === 1, lines);
  lines.push(...split('\n'));
  check('then the held line comes out whole', lines.length === 2 && JSON.parse(lines[1]).b === 2, lines);
  const s2 = C.lineSplitter();
  check('a last line with no newline is flushed by the final feed', s2('{"x":1}').length === 0 && s2('\n').length === 1);
}

console.log();
console.log('-- the reducer, across a whole stream --');
{
  let s = C.connLoading(C.connKey('IDR', 'COK', '2026-09-26'));
  check('the key names origin, destination and day', s.key === 'IDR-COK-2026-09-26' && C.connKey('A', 'B', null) === 'A-B-rolling');
  s = C.connReduce(s, { type: 'direct' });
  check('the direct event changes nothing', s.status === 'loading' && s.total === null);
  s = C.connReduce(s, { type: 'plan', hub_days: 4, hubs: ['BOM', 'BLR'] });
  check('the plan sets the total', s.total === 4 && s.resolved === 0);
  s = C.connReduce(s, { type: 'hub', hub: 'BOM', day: 'd', itineraries: [it('BOM', 'A1', 'A2')] });
  s = C.connReduce(s, { type: 'progress', resolved: 1, total: 4 });
  check('a hub event and a progress event', C.connItineraries(s).length === 1 && s.resolved === 1, s);
  s = C.connReduce(s, { type: 'hub', hub: 'BOM', day: 'd2', itineraries: [it('BOM', 'A1', 'A2'), it('BOM', 'A3', 'A4')] });
  check('a later event for the same hub REPLACES it', C.connItineraries(s).length === 2, C.connItineraries(s));
  s = C.connReduce(s, { type: 'hub', hub: 'BLR', day: 'd', itineraries: [it('BLR', 'B1', 'B2')] });
  check('other hubs add', C.connItineraries(s).length === 3);
  check('nothing is fastest while the stream is open', C.connFastestAllowed(s) === false);
  s = C.connReduce(s, { type: 'done', itineraries: [it('BLR', 'B1', 'B2'), it('BOM', 'A1', 'A2')], complete: true, unchecked: [], error: null });
  check('done: the server\'s ranked list replaces the provisional one',
    s.status === 'done' && C.connItineraries(s).map(x => x.hub).join() === 'BLR,BOM', C.connItineraries(s));
  check('done and complete: a connection may be fastest', C.connFastestAllowed(s) === true);
  check('the count reads finished', s.resolved === s.total);
  const after = C.connReduce(s, { type: 'hub', hub: 'DEL', day: 'd', itineraries: [it('DEL', 'x', 'y')] });
  check('an event after done changes nothing', after === s);
}

console.log();
console.log('-- the other endings --');
{
  const base = C.connLoading('k');
  const partial = C.connReduce(base, { type: 'done', itineraries: [it('BOM', 'a', 'b')], complete: false, unchecked: ['GOI 2026-09-27'], error: null });
  check('incomplete: shown, but never fastest', partial.status === 'done' && C.connItineraries(partial).length === 1
    && C.connFastestAllowed(partial) === false && partial.unchecked.length === 1);
  const deferred = C.connReduce(base, { type: 'done', itineraries: [], complete: true, unchecked: [], deferred: true, error: null });
  check('deferred by the budget', deferred.status === 'deferred' && C.connFastestAllowed(deferred) === false);
  const err = C.connReduce(base, { type: 'done', itineraries: [], complete: false, unchecked: [], error: 'Could not load' });
  check('an error', err.status === 'error' && err.error === 'Could not load');
  const idle = C.connIdle();
  check('an idle state ignores events', C.connReduce(idle, { type: 'plan', hub_days: 3, hubs: [] }) === idle);
}

console.log(`\nPASSED: ${pass}   FAILURES: ${fail}`);
process.exit(fail ? 1 : 0);
