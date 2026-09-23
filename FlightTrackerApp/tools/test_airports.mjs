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
import { ALIASES, METRO_ALIASES } from './aliases.mjs';

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
console.log('-- normalizeTerm folds accents and keeps every script the table writes in --');
const nf = (t) => A.normalizeTerm(t);
check('"São Paulo" folds to "sao paulo"', nf('São Paulo') === 'sao paulo', nf('São Paulo'));
check('"İstanbul" is one word again', nf('İstanbul') === 'istanbul', nf('İstanbul'));
check('"Zürich", "Genève", "Bogotá", "Kraków" fold', [nf('Zürich'), nf('Genève'), nf('Bogotá'), nf('Kraków')].join() === 'zurich,geneve,bogota,krakow');
check('"Malmø", "Wrocław", "Straße" map the letters NFD leaves whole', [nf('Malmø'), nf('Wrocław'), nf('Straße')].join() === 'malmo,wroclaw,strasse');
check('Cyrillic, CJK, Devanagari, Arabic, Thai and Hangul survive', ['Москва', '東京', 'दिल्ली', 'القاهرة', 'กรุงเทพ', '서울'].every(t => nf(t) !== '' && nf(t) === nf(nf(t))));
check('a hyphenated Cyrillic name becomes two words', nf('Санкт-Петербург') === 'санкт петербург', nf('Санкт-Петербург'));
check('"東京" is Latin to nobody, "tokyo" is', !A.isLatinTerm(nf('東京')) && A.isLatinTerm(nf('tokyo')));

console.log();
console.log('-- the fold reaches the city tier: accents no longer split a city --');
// The OPTIONS, not findAirports: that list runs on down the ranks and picks
// up San José del Cabo as a prefix, which is not an equal reading.
check('"san jose" offers California AND Costa Rica as equals', res('san jose')?.options.map(a => a.iata).sort().join() === 'SJC,SJO', hit('san jose'));
check('"san josé" offers the same two', res('san josé')?.options.map(a => a.iata).sort().join() === 'SJC,SJO', hit('san josé'));
check('"bogotá" is Bogotá at rank 1, not by a typo', hit('bogotá')?.iata === 'BOG' && hit('bogotá').rank === 1, hit('bogotá'));
check('"zürich" ranks as "zurich" does', hit('zürich')?.rank === 1, hit('zürich'));
check('"st petersburg" is Pulkovo, not Pinellas Park', hit('st petersburg')?.iata === 'LED' && hit('st petersburg').rank === 1, hit('st petersburg'));
check('"münchen" is Munich', hit('münchen')?.iata === 'MUC' && hit('münchen').rank <= 2, hit('münchen'));

console.log();
console.log('-- names that used to fall into the typo tier and land elsewhere --');
for (const [name, iata] of [['praha', 'PRG'], ['roma', 'FCO'], ['sampa', 'GRU'], ['kampala', 'EBB'], ['londres', 'LHR'], ['macao', 'MFM'], ['peking', 'PEK'], ['canton', 'CAN'], ['kyiv', null]]) {
  const h = hit(name);
  if (iata === null) check(`"${name}" is nothing -- there is no row for it, and no guess is made`, h === null || h.rank > A.RANK_LAST_EXACT, h);
  else check(`"${name}" -> ${iata} at an exact tier`, h?.iata === iata && h.rank <= 2, h);
}

console.log();
console.log('-- two-letter nicknames reach the curated map; two-letter guesses still do not --');
check('"la" is Los Angeles, the group', res('la')?.airport.iata === 'LAX' && res('la').rank === 0, hit('la'));
check('"sf" is San Francisco, the group', res('sf')?.airport.iata === 'SFO' && res('sf').rank === 0, hit('sf'));
check('"dc" is Washington, the group', res('dc')?.airport.iata === 'IAD' && res('dc').rank === 0, hit('dc'));
check('"hk" is Hong Kong, alone', res('hk')?.airport.iata === 'HKG' && res('hk').options.length === 1, hit('hk'));
check('"de" is still nothing', res('de') === null, hit('de'));
check('"la" is a known place, "de" is not', A.isKnownPlace('la') === true && A.isKnownPlace('de') === false);

console.log();
console.log('-- native scripts resolve on the device --');
for (const [name, iata] of [['東京', 'HND'], ['大阪', 'KIX'], ['北京', 'PEK'], ['上海', 'PVG'], ['서울', 'ICN'], ['москва', 'SVO'], ['дубай', 'DXB'], ['دبي', 'DXB'], ['القاهرة', 'CAI'], ['दिल्ली', 'DEL'], ['मुंबई', 'BOM'], ['बेंगलुरु', 'BLR'], ['கொழும்பு', 'CMB'], ['กรุงเทพ', 'BKK'], ['ਅੰਮ੍ਰਿਤਸਰ', 'ATQ'], ['ঢাকা', 'DAC'], ['תל אביב', 'TLV']]) {
  const h = hit(name);
  check(`"${name}" -> ${iata}`, h?.iata === iata && h.rank <= 2, h);
}
check('a two-character CJK city is not too short', hit('東京') !== null && hit('香港') !== null);
check('a script the table never wrote in still resolves to nothing rather than crashing', A.resolveAirportName('ᚠᚢᚦ') === null);

console.log();
console.log('-- THE WHOLE TABLE: every alias lands on its own row at an exact tier, with no rival --');
let aliasCount = 0;
let aliasBad = 0;
for (const [region, rows] of Object.entries(ALIASES)) {
  for (const [code, list] of Object.entries(rows)) {
    if (A.airportByCode(code) === null) continue;      // reported by the generator, not a test failure
    for (const alias of list) {
      aliasCount++;
      const r = A.resolveAirportName(alias);
      const good = r !== null && r.rank <= 2 && r.airport.iata === code && r.options.length === 1;
      if (!good) {
        aliasBad++;
        console.log(`  FAIL ${region} ${code} ${JSON.stringify(alias)} -> ${r === null ? 'nothing' : `${r.airport.iata} rank ${r.rank} [${r.options.map(o => o.iata).join(',')}]`}`);
      }
    }
  }
}
check(`${aliasCount} row aliases, ${aliasBad} astray`, aliasBad === 0, aliasBad);
let metroCount = 0;
let metroBad = 0;
for (const [base, list] of Object.entries(METRO_ALIASES)) {
  const want = A.findAirports(base).map(a => a.iata).join();
  for (const alias of list) {
    metroCount++;
    const r = A.resolveAirportName(alias);
    const good = want !== '' && r !== null && r.rank === 0 && r.options.map(a => a.iata).join() === want;
    if (!good) {
      metroBad++;
      console.log(`  FAIL metro ${base} ${JSON.stringify(alias)} -> ${r === null ? 'nothing' : `${r.airport.iata} rank ${r.rank} [${r.options.map(o => o.iata).join(',')}]`} (want ${want})`);
    }
  }
}
check(`${metroCount} metro aliases, ${metroBad} astray`, metroBad === 0, metroBad);

console.log();
console.log('-- one name, several cities: a written order, then a country first --');
const opts = (t) => res(t)?.options.map(a => a.iata).join(',');
check('"santiago" is Chile, then the Dominican Republic, then Cuba', opts('santiago') === 'SCL,STI,SCU', opts('santiago'));
check('"portland" is Oregon before Maine', opts('portland') === 'PDX,PWM', opts('portland'));
check('"barcelona" is Spain before Venezuela', opts('barcelona') === 'BCN,BLA', opts('barcelona'));
check('"san jose" is California before Costa Rica', opts('san jose') === 'SJC,SJO', opts('san jose'));
check('Birmingham and Victoria keep their curated order', opts('birmingham') === 'BHX,BHM' && opts('victoria') === 'YYJ,SEZ');
const santiago = res('santiago').options;
check('a country puts its airport first', A.orderByCountry(santiago, 'Cuba').map(a => a.iata).join() === 'SCU,SCL,STI');
check('and drops nothing', A.orderByCountry(santiago, 'Cuba').length === 3);
check('a country with none of them changes nothing', A.orderByCountry(santiago, 'Peru') === santiago);
check('no country changes nothing', A.orderByCountry(santiago, null) === santiago);
check('the model\'s country names reach the dataset\'s',
  [A.countryNamed('USA'), A.countryNamed('UK'), A.countryNamed('Ivory Coast'), A.countryNamed('Türkiye'), A.countryNamed('Chile'), A.countryNamed('south korea')].join('|')
    === "United States|United Kingdom|Côte d'Ivoire|Turkey|Chile|South Korea",
  [A.countryNamed('USA'), A.countryNamed('UK'), A.countryNamed('Ivory Coast'), A.countryNamed('Türkiye'), A.countryNamed('Chile'), A.countryNamed('south korea')]);
check('a country the dataset does not hold is null, never a refusal', A.countryNamed('Narnia') === null && A.countryNamed('') === null);

console.log();
console.log('-- the two lines the search rung draws across the ranks --');
check('RANK_LAST_EXACT is 6 and RANK_LAST_ONE_EDIT is 8', A.RANK_LAST_EXACT === 6 && A.RANK_LAST_ONE_EDIT === 8);
check('a one-edit hit sits between them', res('dehli').rank > A.RANK_LAST_EXACT && res('dehli').rank <= A.RANK_LAST_ONE_EDIT, res('dehli').rank);
check('a two-edit hit sits above the second', res('banglor').rank > A.RANK_LAST_ONE_EDIT, res('banglor').rank);
check('every exact lookup sits at or below the first', ['BLR', 'mumbai', 'delhi', 'mumb'].every(t => res(t).rank <= A.RANK_LAST_EXACT));

console.log();
console.log('-- cost --');
const t0 = performance.now();
for (let i = 0; i < 200; i++) res(i % 2 ? 'dehli' : 'banglor');
const ms = (performance.now() - t0) / 200;
// TWELVE. It was five, then eight when the world table added 767 words to the
// haystacks -- the non-Latin ones are skipped but still walked. Eight sat too
// close to the machine: one loaded run measured 8.18ms where the reruns gave
// 5.5 to 6.5 and a quiet one 3.3. The check is for a regression of several
// times, which twelve still catches, not for a busy laptop.
check(`a fuzzy lookup over the whole file is under 12ms (measured ${ms.toFixed(2)}ms)`, ms < 12, ms);

console.log(`\nPASSED: ${pass}   FAILURES: ${fail}`);
process.exit(fail ? 1 : 0);
