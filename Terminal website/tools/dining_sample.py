"""Writes assets/dining.js, the rows the home page shows for each airport.

Read from FlightTrackerApp/lib/dining.ts, the app's own dataset, so the site
can never show a place the app does not have. Run it again whenever the app's
dining data is regenerated:

    python tools/dining_sample.py

The site shows seven airports. The counts it prints come from the same rows.
"""
import io
import json
import os
import re
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(HERE)
DATA = os.path.join(SITE, '..', 'FlightTrackerApp', 'lib', 'dining.ts')
OUT = os.path.join(SITE, 'assets', 'dining.js')
PAGE = os.path.join(SITE, 'index.html')
START = '<!-- dining:start (written by tools/dining_sample.py; do not edit by hand) -->'
END = '<!-- dining:end -->'

AIRPORTS = [
    ('JFK', 'New York JFK', 'America/New_York'),
    ('LHR', 'London Heathrow', 'Europe/London'),
    ('EWR', 'Newark', 'America/New_York'),
    ('LGA', 'New York LaGuardia', 'America/New_York'),
    ('FRA', 'Frankfurt', 'Europe/Berlin'),
    ('ARN', 'Stockholm Arlanda', 'Europe/Stockholm'),
    ('HKG', 'Hong Kong', 'Asia/Hong_Kong'),
]
AIR_ROWS = 7
LAND_ROWS = 5

# The app's own words for a category -- CATEGORY_LABEL in app/(tabs)/deck.tsx.
CATEGORY_LABEL = {
    'fast_food': 'Fast food', 'cafe': 'Café', 'bakery': 'Bakery', 'dessert': 'Dessert',
    'bar': 'Bar', 'asian': 'Asian', 'chinese': 'Chinese', 'indian': 'Indian',
    'western': 'Western', 'middle_eastern': 'Middle Eastern', 'vegetarian': 'Vegetarian',
    'halal': 'Halal', 'food_court': 'Food court', 'lounge': 'Lounge',
    'vending': 'Vending machine', 'other': '',
}
FIELDS = ['airport', 'name', 'sourceId', 'terminalRaw', 'terminal', 'level', 'area', 'gateHint',
          'isAirside', 'zone', 'securityRaw', 'securityBasis', 'flightScope', 'categoryRaw',
          'category', 'serveMinutes', 'hoursRaw', 'hours', 'is24H', 'lat', 'lon']


def rows():
    text = io.open(DATA, encoding='utf8').read()
    body = text[text.index('const ROWS: Row[] = ['):]
    out = []
    for line in body.splitlines():
        t = line.strip()
        if t.startswith('["'):
            out.append(dict(zip(FIELDS, json.loads(t.rstrip(',')))))
    return out


def words(d):
    seen = []
    for c in d['category'].split('|'):
        label = CATEGORY_LABEL.get(c)
        if label and label not in seen:
            seen.append(label)
    return ' · '.join(seen)


def place(d):
    # The row's place line, as the deck builds it.
    parts = [d['terminal'] or None, d['level'] or None, ('Gate ' + d['gateHint']) if d['gateHint'] else None]
    return ' · '.join(p for p in parts if p)


def key(name):
    return ' '.join(name.lower().replace('’', "'").split())


# THE PLACES A NOTE ON THE PAGE NAMES, shown on both lists so the note can be
# checked against the rows under it.
FEATURED = {
    'JFK': ["dunkin'"],
    'LHR': ['pret a manger', 'caffè nero'],
    'HKG': ['pret a manger', 'starbucks'],
}
# (airport, name) -> the first terminal with that place on both sides; main()
# fills it before anything is picked.
SHARED = {}


def usable(d):
    """Rows that read plainly as an example: no vending machines, no gate hint
    the source left unparsed ("39and41"), and no before-security place that
    the source also ties to a gate, or after-security one filed under a
    security or arrivals level. The app shows those rows as the airports give
    them; a sample of seven should not lead with the odd ones."""
    if 'vending' in d['category'] or 'vend' in d['name'].lower():
        return False
    if 'and' in d['gateHint']:
        return False
    if d['zone'] == 'departures_landside' and (d['gateHint'] or 'gate' in d['name'].lower()):
        return False
    level = d['level'].lower()
    if d['zone'] == 'departures_airside' and any(w in level for w in ('security', 'arrival', 'baggage', 'bus')):
        return False
    return True


def pick(code, candidates, n):
    """The featured places first, then an even spread through the alphabet of
    the rest, preferring rows the app can say more about."""
    featured = FEATURED.get(code, [])
    first = []
    for f in featured:
        # THE SAME TERMINAL ON BOTH LISTS where the airport has one, so the
        # pair reads as one place on two sides of one checkpoint.
        match = sorted((d for d in candidates if key(d['name']) == f),
                       key=lambda d: (d['terminal'] != SHARED.get((code, f)), d['terminal']))
        if match:
            first.append(match[0])
    seen = {key(d['name']) for d in first}
    rest = []
    for d in sorted(candidates, key=lambda d: key(d['name'])):
        if key(d['name']) in seen or not usable(d):
            continue
        seen.add(key(d['name']))
        rest.append(d)
    rich = [d for d in rest if d['serveMinutes'] is not None or d['gateHint'] or d['hoursRaw']]
    pool = rich if len(rich) >= n - len(first) else rest
    room = n - len(first)
    if room <= 0 or not pool:
        return first[:n]
    step = max(1, len(pool) // room)
    spread = pool[::step][:room]
    # ARLANDA IS THE ONE AIRPORT THAT SAYS HOW LONG A PLACE TAKES, so its
    # example keeps a few rows that carry the figure.
    timed = [d for d in pool if d['serveMinutes'] is not None and d not in spread]
    while timed and sum(1 for d in spread if d['serveMinutes'] is not None) < 3:
        spread[-1 - sum(1 for d in spread[::-1] if d['serveMinutes'] is not None)] = timed.pop(0)
    return first + sorted(spread, key=lambda d: key(d['name']))


NUMBER = {2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six', 7: 'seven', 8: 'eight', 9: 'nine'}


def note(code, rs):
    """One true, specific line per airport, with its numbers counted here.
    A line whose fact stops holding is dropped with a warning, never printed
    wrong."""
    air = [d for d in rs if d['zone'] == 'departures_airside']
    land = [d for d in rs if d['zone'] == 'departures_landside']

    def terminals(rows, name):
        return {d['terminal'] for d in rows if key(d['name']) == name}

    if code == 'JFK':
        both = terminals(air, "dunkin'") & terminals(land, "dunkin'")
        if len(both) in NUMBER:
            return ("At JFK, Dunkin' is on both sides of security in %s terminals. "
                    "The list says which one you can walk to." % NUMBER[len(both)])
    if code == 'LHR':
        n = sum(1 for d in rs if d['zone'] == 'arrivals')
        if n in NUMBER:
            return ("Heathrow lists %s more in arrivals: somewhere to eat after you land, "
                    "not on a layover." % NUMBER[n])
    if code == 'EWR':
        n = sum(1 for d in rs if d['gateHint'])
        if n:
            return "Newark gives a gate for %d of its %d places, and Terminal shows it on the row." % (n, len(rs))
    if code == 'LGA':
        return "At LaGuardia, %d of the %d are after security. Eat once you're through." % (len(air), len(rs))
    if code == 'FRA':
        if all(d['hours'] for d in rs):
            return ("Frankfurt publishes opening hours for all %d, so Terminal can say which are "
                    "open now, on Frankfurt time." % len(rs))
    if code == 'ARN':
        timed = sorted(d['serveMinutes'] for d in rs if d['serveMinutes'] is not None)
        if len(timed) > 1:
            return ("Arlanda says how long %d of its places take to serve you, from %d to %d minutes. "
                    "On a layover, the ones that fit your time turn green." % (len(timed), timed[0], timed[-1]))
    if code == 'HKG':
        on_both = all(terminals(air, n) and terminals(land, n) for n in ('pret a manger', 'starbucks'))
        if on_both:
            return "Pret and Starbucks are on both sides at Hong Kong: same names, opposite sides of the checkpoint."
    print('WARNING: no note for', code, '-- its fact no longer holds')
    return ''


def slim(d):
    r = {'n': d['name'], 'p': place(d), 'c': words(d)}
    if d['hoursRaw']:
        r['h'] = d['hoursRaw']
    if d['hours']:
        r['w'] = [[w['startDay'], w['endDay'], w['open'], w['close']] for w in d['hours']]
    if d['is24H']:
        r['a'] = 1
    if d['serveMinutes'] is not None:
        r['s'] = d['serveMinutes']
    return r


def esc(t):
    return (t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


KIND_WORD = {'bar': 'Bar', 'coffee': 'Café', 'food': 'Restaurant'}


def kind(r):
    """Which airport pictogram a place gets: assets/page.js's kind(), line for
    line. The airport's own category decides between a bar, a café (with
    bakeries and desserts) and a place to eat; where the airport gave none,
    the name decides, and anything else is a place to eat."""
    c = r.get('c') or ''
    if re.search(r'\bBar\b', c):
        return 'bar'
    if re.search(r'Café|Bakery|Dessert', c):
        return 'coffee'
    if c:
        return 'food'
    if re.search(r'\b(bar|pub|tavern|brew)', r['n'], re.I):
        return 'bar'
    if re.search(r'(coffee|caf[eé]|espresso|bakery)', r['n'], re.I):
        return 'coffee'
    return 'food'


def static_block(code, a):
    """The first airport as plain HTML, for a page read without its script:
    the same markup page.js draws, pictograms included. Open and closed are
    left out: they depend on the moment of reading, and the script adds
    them."""
    def rows(rs):
        out = []
        for r in rs:
            k = kind(r)
            serve = '<span class="r-serve">%d min</span>' % r['s'] if 's' in r else ''
            meta = '<div class="r-meta"><span>%s</span></div>' % esc(r['p']) if r['p'] else ''
            hours = '<div class="r-hours">%s</div>' % esc(r['h']) if r.get('h') else ''
            out.append('<li><span class="pict" aria-hidden="true"><svg viewBox="0 0 100 100"><use href="#p-%s"/></svg></span>'
                       '<div class="r-body"><div class="r-top"><span class="r-name">%s<span class="sr">, %s</span></span>%s</div>%s%s</div></li>'
                       % (k, esc(r['n']), KIND_WORD[k], serve, meta, hours))
        return ''.join(out)
    count = '<b>%d after security</b> · %d before' % (a['air'], a['land'])
    if a['arrivals']:
        count += ' · %d in arrivals' % a['arrivals']
    ind = '        '
    return '\n'.join([
        ind + START,
        ind + '<div class="dine-head"><span class="dine-name" id="dineName">%s <span class="code">%s</span></span>'
              '<span class="dine-count" id="dineCount">%s</span></div>' % (esc(a['name']), code, count),
        ind + '<div class="sides">',
        ind + '  <div class="side before"><div class="side-title">Before security</div>'
              '<div class="side-note">you would have to leave and clear security again</div>'
              '<ul id="dineBefore">%s</ul></div>' % rows(a['rowsLand']),
        ind + '  <div class="checkpoint" aria-hidden="true"><span>Security</span></div>',
        ind + '  <div class="side after"><div class="side-title">After security</div>'
              '<div class="side-note">past the checkpoint, where your gate is</div>'
              '<ul id="dineAfter">%s</ul></div>' % rows(a['rowsAir']),
        ind + '</div>',
        ind + '<p class="dine-note" id="dineNote">%s</p>' % esc(a['note']),
        ind + END,
    ])


def write_page(first, airport):
    page = io.open(PAGE, encoding='utf8').read()
    a, b = page.index(START), page.index(END) + len(END)
    a = page.rindex('\n', 0, a) + 1
    page = page[:a] + static_block(first, airport) + page[b:]
    with io.open(PAGE, 'w', encoding='utf8', newline='\n') as f:
        f.write(page)
    print('wrote the', first, 'rows into', PAGE)


def main():
    all_rows = rows()
    out, total = {}, 0
    for code, name, tz in AIRPORTS:
        rs = [d for d in all_rows if d['airport'] == code]
        zones = Counter(d['zone'] for d in rs)
        air = [d for d in rs if d['zone'] == 'departures_airside']
        land = [d for d in rs if d['zone'] == 'departures_landside']
        for f in FEATURED.get(code, []):
            both = ({d['terminal'] for d in air if key(d['name']) == f}
                    & {d['terminal'] for d in land if key(d['name']) == f})
            if both:
                SHARED[(code, f)] = sorted(both)[0]
        out[code] = {
            'name': name, 'tz': tz, 'total': len(rs),
            'air': zones['departures_airside'], 'land': zones['departures_landside'],
            'arrivals': zones['arrivals'], 'unknown': zones['unknown'],
            'note': note(code, rs),
            'rowsAir': [slim(d) for d in pick(code, air, AIR_ROWS)],
            'rowsLand': [slim(d) for d in pick(code, land, LAND_ROWS)],
        }
        total += len(rs)
        print(code, len(rs), dict(zones))
    print('seven airports:', total)
    head = ('/* Generated by tools/dining_sample.py from FlightTrackerApp/lib/dining.ts.\n'
            '   Do not edit: run the script again when the app\'s dining data changes. */\n')
    with io.open(OUT, 'w', encoding='utf8', newline='\n') as f:
        f.write(head)
        f.write('window.DINING = ')
        f.write(json.dumps({'total': total, 'airports': out}, ensure_ascii=False, separators=(',', ':')))
        f.write(';\n')
    print('wrote', OUT, os.path.getsize(OUT), 'bytes')
    first = AIRPORTS[0][0]
    write_page(first, out[first])


if __name__ == '__main__':
    main()
