// A READ-ONLY PROBE OF THE RESOLVER, for planning the global alias audit.
//
//   node tools/probe_airports.mjs
//
// Compiles lib/airports.ts the way test_airports.mjs does and prints: the
// dataset's size by region, and how a list of world cities and duplicate names
// resolve today -- the airport chosen, the rank, and every option offered.
import { execSync } from 'node:child_process';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const out = mkdtempSync(join(tmpdir(), 'airports-'));
execSync(`npx tsc --ignoreConfig lib/airports.ts --outDir "${out}" --module es2022 --target es2022 --moduleResolution bundler --skipLibCheck`, { stdio: 'inherit' });
const A = await import(pathToFileURL(join(out, 'airports.js')).href);

const all = A.allAirports();
console.log('airports:', all.length, ' sample:', JSON.stringify(all[0]));

// Region by country, matched on whatever the row carries (a code or a name).
const REGION = {
  europe: 'GB IE FR DE NL BE LU CH AT IT ES PT GR TR RU UA PL CZ SK HU RO BG RS HR SI BA MK AL ME XK DK SE NO FI IS EE LV LT BY MD CY MT United Kingdom Ireland France Germany Netherlands Belgium Luxembourg Switzerland Austria Italy Spain Portugal Greece Turkey Türkiye Russia Ukraine Poland Czechia Czech Republic Slovakia Hungary Romania Bulgaria Serbia Croatia Slovenia Bosnia and Herzegovina North Macedonia Albania Montenegro Kosovo Denmark Sweden Norway Finland Iceland Estonia Latvia Lithuania Belarus Moldova Cyprus Malta Georgia Armenia Azerbaijan GE AM AZ',
  'north america': 'US CA MX United States Canada Mexico',
  'latin america': 'BR AR CL CO PE EC BO PY UY VE GT HN SV NI CR PA CU DO PR JM BS TT BB HT BZ GY SR Brazil Argentina Chile Colombia Peru Ecuador Bolivia Paraguay Uruguay Venezuela Guatemala Honduras El Salvador Nicaragua Costa Rica Panama Cuba Dominican Republic Puerto Rico Jamaica Bahamas Trinidad and Tobago Barbados Haiti Belize Guyana Suriname Aruba AW Curaçao CW Cayman Islands KY Bermuda BM',
  'middle east': 'AE SA QA KW BH OM YE IQ IR IL JO LB SY PS United Arab Emirates Saudi Arabia Qatar Kuwait Bahrain Oman Yemen Iraq Iran Israel Jordan Lebanon Syria Palestine',
  'south asia': 'IN PK BD LK NP BT MV AF India Pakistan Bangladesh Sri Lanka Nepal Bhutan Maldives Afghanistan',
  'east asia': 'CN JP KR TW HK MO MN KP China Japan South Korea Korea Taiwan Hong Kong Macau Macao Mongolia North Korea',
  'southeast asia': 'TH VN MY SG ID PH KH LA MM BN TL Thailand Vietnam Malaysia Singapore Indonesia Philippines Cambodia Laos Myanmar Brunei Timor-Leste',
  'central asia': 'KZ UZ KG TJ TM Kazakhstan Uzbekistan Kyrgyzstan Tajikistan Turkmenistan',
  africa: 'EG MA DZ TN LY SD ET KE TZ UG RW NG GH CI SN CM ZA ZW ZM MZ AO NA BW MU SC MG RE CV ML BF NE TD GA CG CD GN SL LR TG BJ MW LS SZ SO DJ ER SS GM GW GQ ST KM YT Egypt Morocco Algeria Tunisia Libya Sudan Ethiopia Kenya Tanzania Uganda Rwanda Nigeria Ghana Ivory Coast Côte d\'Ivoire Senegal Cameroon South Africa Zimbabwe Zambia Mozambique Angola Namibia Botswana Mauritius Seychelles Madagascar Réunion Cape Verde Cabo Verde Mali Burkina Faso Niger Chad Gabon Congo DR Congo Guinea Sierra Leone Liberia Togo Benin Malawi Lesotho Eswatini Somalia Djibouti Eritrea South Sudan Gambia',
  oceania: 'AU NZ FJ PG NC PF WS TO VU SB GU Australia New Zealand Fiji Papua New Guinea New Caledonia French Polynesia Samoa Tonga Vanuatu Solomon Islands Guam',
};
const regionOf = (c) => {
  for (const [r, list] of Object.entries(REGION)) {
    if (list.split(/\s(?=[A-Z])/).some(x => x.trim().toLowerCase() === String(c).trim().toLowerCase())) return r;
  }
  return 'other:' + c;
};
const byRegion = {};
for (const a of all) { const r = regionOf(a.country); byRegion[r] = (byRegion[r] ?? 0) + 1; }
console.log('by region:', JSON.stringify(byRegion, null, 0));

const show = (t) => {
  const r = A.resolveAirportName(t);
  if (r === null) return `${t.padEnd(22)} -> nothing`;
  const opts = r.options.map(a => `${a.iata}${a.country && a.country !== r.airport.country ? '(' + a.country + ')' : ''}`).join(',');
  return `${t.padEnd(22)} -> ${r.airport.iata} rank ${r.rank}  options [${opts}]  city "${r.airport.city}"`;
};

console.log('\n-- the twelve multi-airport cities --');
for (const t of ['tokyo', 'moscow', 'milan', 'paris', 'new york', 'washington', 'buenos aires', 'sao paulo', 'são paulo', 'shanghai', 'seoul', 'bangkok', 'istanbul', 'london']) console.log(show(t));

console.log('\n-- duplicates across countries --');
for (const t of ['portland', 'springfield', 'san jose', 'san josé', 'santiago', 'hyderabad', 'birmingham', 'manchester', 'valencia', 'cordoba', 'cordova', 'san juan', 'la paz', 'santa cruz', 'georgetown', 'victoria', 'salem', 'kingston', 'sydney', 'st petersburg', 'saint petersburg', 'leon', 'merida', 'nice', 'trujillo']) console.log(show(t));

console.log('\n-- names a local would type, sampled --');
const local = ['münchen', 'munchen', 'muenchen', 'köln', 'wien', 'praha', 'warszawa', 'moskva', 'roma', 'firenze', 'venezia', 'napoli', 'lisboa', 'genève', 'geneve', 'zürich', 'zurich', 'bruxelles', 'brussel', 'københavn', 'kopenhagen', 'göteborg', 'athina', 'krung thep', 'kaapstad', 'al qahirah', 'cairo', 'dubayy', 'riyadh', 'ar riyadh', 'bayrut', 'beirut', 'tehran', 'teheran', 'peking', 'beijing', 'canton', 'guangzhou', 'saigon', 'ho chi minh', 'rangoon', 'yangon', 'kiev', 'kyiv', 'leningrad', 'st petersburg', 'nyc', 'la', 'sf', 'vegas', 'philly', 'dc', 'joburg', 'jozi', 'cape town', 'bombay', 'nueva york', 'londres', 'new york city', 'frankfurt am main', 'ciudad de mexico', 'mexico city', 'cdmx', 'bogota', 'bogotá', 'rio', 'rio de janeiro', 'sampa', 'baires', 'santiago de chile', 'lima', 'la habana', 'havana', 'quebec', 'montreal', 'montréal', 'toronto', 'vancouver', 'hongkong', 'hong kong', 'hk', 'kl', 'kuala lumpur', 'singapore', 'sg', 'jakarta', 'jkt', 'denpasar', 'bali', 'manila', 'hanoi', 'ha noi', 'da nang', 'phnom penh', 'busan', 'pusan', 'osaka', 'kansai', 'nagoya', 'sapporo', 'okinawa', 'taipei', 'taibei', 'macau', 'macao', 'ulaanbaatar', 'ulan bator', 'almaty', 'tashkent', 'toshkent', 'baku', 'tbilisi', 'yerevan', 'doha', 'muscat', 'kuwait', 'amman', 'tel aviv', 'jerusalem', 'jeddah', 'jiddah', 'dammam', 'lagos', 'abuja', 'accra', 'nairobi', 'mombasa', 'addis', 'addis ababa', 'dar es salaam', 'dar', 'kigali', 'entebbe', 'kampala', 'casablanca', 'casa', 'marrakech', 'marrakesh', 'tunis', 'algiers', 'alger', 'khartoum', 'luanda', 'maputo', 'harare', 'lusaka', 'windhoek', 'durban', 'port elizabeth', 'gqeberha', '東京', 'موسكو', 'москва', 'दिल्ली', '北京', '서울'];
for (const t of local) console.log(show(t));

console.log('\n-- normalizeTerm on scripts and diacritics --');
for (const t of ['São Paulo', 'München', 'Zürich', 'Genève', '東京', 'Москва', 'दिल्ली', 'القاهرة', 'İstanbul', 'Kraków', 'Reykjavík']) console.log(JSON.stringify(t), '->', JSON.stringify(A.normalizeTerm(t)));
