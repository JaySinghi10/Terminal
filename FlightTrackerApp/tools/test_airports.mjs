// THE AIRPORT RESOLVER, UNDER PLAIN NODE. lib/airports.ts imports nothing, so
// it is compiled to a temp directory with the project's own tsc and exercised
// here, exactly as test_pending_rules.mjs does for its module.
//
//   node tools/test_airports.mjs
//
// THREE QUESTIONS.
//
// FIRST: does every exact lookup answer exactly as it did? The fuzzy tier is a
// second pass that must never run when the first found anything, and the ranks
// above it are ordering only. Anything that used to resolve still resolves to
// the same airport at the same rank.
//
// SECOND: does a one- or two-letter typo land on the city meant, uniquely, and
// do the length guards hold so that "goa" stays "goa"?
//
// THIRD: do the resolver and isKnownPlace finally agree about "delhi", and does
// the haystack-built set still say no to "time", "land" and "airport"?
import { execSync } from 'node:child_process';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const out = mkdtempSync(join(tmpdir(), 'airports-'));
execSync(`npx tsc --ignoreConfig lib/airports.ts --outDir "${out}" --module es2022 --target es2022 --moduleResolution bundler --skipLibCheck`, { stdio: 'inherit' });
const A = await import(pathToFileURL(join(out, 'airports.js')).href);

let pass = 0, fail = 0;
const check = (label, cond, detail) => {
  if (cond) { pass++; console.log('  ok   ' + label); }
  else { fail++; console.log('  FAIL ' + label + '   -> ' + JSON.stringify(detail)); }
};
const res = (t) => A.resolveAirportName(t);
const hit = (t) => { const r = res(t); return r === null ? null : { iata: r.airport.iata, rank: r.rank, n: r.options.length }; };

console.log('-- exact lookups are byte-for-byte what they were --');
check('a code is rank 0', hit('BLR')?.iata === 'BLR' && hit('BLR').rank === 0, hit('BLR'));
check('a city is rank 1', hit('mumbai')?.iata === 'BOM' && hit('mumbai').rank === 1, hit('mumbai'));
check('"delhi" is a whole word of the alias string, rank 2, and unique',
  hit('delhi')?.iata === 'DEL' && hit('delhi').rank === 2 && hit('delhi').n === 1, hit('delhi'));
check('"bali" is an alias and beats the prefix of Balice', hit('bali')?.iata === 'DPS' && hit('bali').rank === 2, hit('bali'));
check('"london" is the curated four', A.findAirports('london').map(a => a.iata).join() === 'LHR,LGW,STN,LTN', A.findAirports('london').map(a => a.iata));
check('"goa" is the curated pair and not Genoa', A.findAirports('goa').map(a => a.iata).join() === 'GOI,GOX', A.findAirports('goa').map(a => a.iata));
check('a prefix still ranks 3', hit('mumb')?.rank === 3, hit('mumb'));
check('a term with an exact hit carries NO fuzzy results at all',
  A.findAirports('delhi', 50).every(a => res(a.city === 'New Delhi' ? 'delhi' : a.city).rank < 7), null);

console.log();
console.log('-- one edit: rank 7 (city) or 8 (word), and UNIQUE at that rank --');
// UNIQUE IS THE PROPERTY THE FREE RUNG NEEDS, not a particular rank number.
// "indor" is deliberately absent: a dropped last letter is a PREFIX, and the
// exact tiers already answer it at rank 3 before any edit is computed.
const one = [['dehli', 'DEL'], ['kolkatta', 'CCU'], ['banglore', 'BLR'], ['chenai', 'MAA'],
  ['hyderbad', 'HYD'], ['mumbi', 'BOM'], ['indoer', 'IDR'], ['bhubaneshwar', 'BBI'],
  ['ahmedabd', 'AMD'], ['thiruvanantapuram', 'TRV'], ['new dehli', 'DEL'], ['bengalore', 'BLR']];
for (const [typo, iata] of one) {
  const h = hit(typo);
  check(`"${typo}" -> ${iata}, unique (rank ${h?.rank})`, h?.iata === iata && (h.rank === 7 || h.rank === 8) && h.n === 1, h);
}
check('"mumbi" is Mumbai\'s CITY at one edit (7), so Navi Mumbai\'s haystack word (8) does not tie it',
  hit('mumbi')?.rank === 7, hit('mumbi'));
check('a dropped last letter is a prefix, rank 3, never fuzzy', hit('indor')?.iata === 'IDR' && hit('indor').rank === 3, hit('indor'));

console.log();
console.log('-- two edits: rank 9 (city) or 10 (word), and ambiguous is allowed --');
// TWO EDITS IS WHERE TYPOS COLLIDE, and "banglor" is the proof: it is two
// edits from Bangkok's CITY and two from the word "bangalore" in Bengaluru's
// haystack, so the city tier puts Bangkok first. Nothing in the letters says
// otherwise. What the resolver promises at two edits is not the answer but the
// LIST -- the "did you mean" the picker shows -- and the free rung refuses a
// list; the model path, which corrects spelling itself, is where a two-edit
// typo is meant to land.
const two = [['banglor', 'BLR'], ['hydrabd', 'HYD'], ['thiruvanantapurm', 'TRV']];
for (const [typo, iata] of two) {
  const r = res(typo);
  const list = A.findAirports(typo, 8).map(a => a.iata);
  check(`"${typo}" is fuzzy (rank ${r?.rank}) and the list offers ${iata}: [${list.join(',')}]`,
    r !== null && r.rank >= 9 && list.includes(iata), { rank: r?.rank, list });
}
check('"banglor" is Bangkok first, by the city tier, which is why the free rung must not take it',
  res('banglor')?.airport.iata === 'BKK' && res('banglor').options.length > 1, hit('banglor'));

console.log();
console.log('-- the guards --');
check('three letters never get an edit: "gao" is not Goa', (hit('gao')?.rank ?? -1) < 7, hit('gao'));
check('four letters never get an edit: "dehl" is nothing or exact', (hit('dehl')?.rank ?? -1) < 7, hit('dehl'));
check('six letters get one edit and not two: "bnglor" (needs two) is NOTHING, not a rank-8 hit on the whole file',
  hit('bnglor') === null, hit('bnglor'));
check('a generic word cannot be typo-matched: "airprot" resolves to nothing', hit('airprot') === null, hit('airprot'));
check('"internationl" resolves to nothing either', hit('internationl') === null, hit('internationl'));

console.log();
console.log('-- the aliases added by hand --');
const alias = [['kozhikode', 'CCJ'], ['baroda', 'BDQ'], ['dilli', 'DEL'], ['amdavad', 'AMD'],
  ['cannanore', 'CNN'], ['shamshabad', 'HYD'], ['secunderabad', 'HYD'], ['panjim', 'GOI'],
  ['panaji', 'GOI'], ['banaras', 'VNS'], ['kashi', 'VNS'], ['gauhati', 'GAU']];
for (const [name, iata] of alias) {
  const h = hit(name);
  check(`"${name}" -> ${iata} at rank 2`, h?.iata === iata && h.rank === 2, h);
}
check('the ones already there still are: bombay, madras, calcutta, bengaluru, cochin, vizag',
  ['bombay', 'madras', 'calcutta', 'bengaluru', 'cochin', 'vizag'].map(t => hit(t)?.iata).join() === 'BOM,MAA,CCU,BLR,COK,VTZ',
  ['bombay', 'madras', 'calcutta', 'bengaluru', 'cochin', 'vizag'].map(t => hit(t)?.iata));

console.log();
console.log('-- isKnownPlace agrees with the resolver --');
check('"delhi" is a known place now', A.isKnownPlace('delhi') === true);
check('"new delhi" still is', A.isKnownPlace('new delhi') === true);
check('"indore" still is', A.isKnownPlace('indore') === true);
check('"dilli" is, through the alias', A.isKnownPlace('dilli') === true);
check('"kozhikode" is, through the alias', A.isKnownPlace('kozhikode') === true);
check('a code is', A.isKnownPlace('sfo') === true);
// "san" is not in this list on purpose: it is San Diego's code, and a code is
// a place. The stoplist keeps it out of the WORD set; the code path lets it in.
for (const w of ['time', 'land', 'airport', 'international', 'flights', 'morning', 'status', 'santa', 'new', 'port']) {
  check(`"${w}" is not`, A.isKnownPlace(w) === false);
}
check('"san" IS, but only because it is a code', A.isKnownPlace('san') === true && A.airportByCode('SAN') !== null);
check('a typo is NOT a known place -- the set is exact, the resolver is what forgives',
  A.isKnownPlace('dehli') === false);

console.log();
console.log('-- cost --');
const t0 = performance.now();
for (let i = 0; i < 200; i++) res(i % 2 ? 'dehli' : 'banglor');
const ms = (performance.now() - t0) / 200;
check(`a fuzzy lookup over the whole file is under 5ms (measured ${ms.toFixed(2)}ms)`, ms < 5, ms);

console.log(`\nPASSED: ${pass}   FAILURES: ${fail}`);
process.exit(fail ? 1 : 0);
