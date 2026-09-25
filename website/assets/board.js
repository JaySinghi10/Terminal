/* The departures board in the hero. It opens on BA286 at San Francisco,
   flipping from ON TIME to CANCELLED, then keeps running: every five seconds
   it flips to another flight at another airport, at another moment -- a new
   gate, a delay, boarding -- and comes round again.

   LOADED IN THE HEAD, NOT DEFERRED, for one line: the class that makes the
   status cells show ON TIME. The page's own HTML is the finished frame,
   BA286 CANCELLED, which is what a visitor without script, or with motion
   turned off, reads and keeps; set here, before the first paint, the class
   means the rest never flashes that frame before the opening flip.

   EACH FLAP TURNS THROUGH THE DRUM, a blank, A to Z, 0 to 9, in order, until
   it reaches its letter, so cells settle at different moments the way a real
   board's do, and a letter that does not change does not move. None turns
   more than ten flaps, which keeps every flip under a second.

   IT RUNS ONLY WHILE SOMEONE CAN SEE IT: off screen, or in a hidden tab, it
   waits on the frame it is showing. */
(function () {
  'use strict';
  if (!window.matchMedia || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  var root = document.documentElement;
  root.classList.add('flaps');

  var DRUM = ' ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
  var FLIP = 55;      // one flap, in ms; the CSS fall matches it
  var FIRST = 900;    // ON TIME stays up this long before the opening flip
  var HOLD = 5000;    // from one flip to the next
  var NBSP = ' ';

  // THE MOMENTS, in the order the board shows them: real flights on their
  // real routes, from the airport each leaves. The moments are examples,
  // not reports. The first is the page's own HTML, the finished frame.
  var FRAMES = [
    { at: 'San Francisco', f: 'BA286', to: 'LONDON', gate: '', note: 'CANCELLED', tone: 'off' },
    { at: 'London Heathrow', f: 'BA177', to: 'NEW YORK', gate: 'B32', note: 'NEW GATE', tone: '' },
    { at: 'Dubai', f: 'EK1', to: 'LONDON', gate: 'A12', note: 'DELAYED', tone: 'late' },
    { at: 'New York JFK', f: 'AA100', to: 'LONDON', gate: '12', note: 'BOARDING', tone: 'live' },
    { at: 'Frankfurt', f: 'LH400', to: 'NEW YORK', gate: 'Z25', note: 'NEW GATE', tone: '' },
    { at: 'Singapore', f: 'SQ25', to: 'FRANKFURT', gate: 'B6', note: 'BOARDING', tone: 'live' }
  ];
  var TONES = ['off', 'late', 'live'];

  function ch(s) { return s === NBSP ? ' ' : s; }
  function shown(s) { return s === ' ' ? NBSP : s; }

  function flap(cell, next) {
    var b = cell.querySelector('b');
    var leaf = document.createElement('i');
    var face = document.createElement('span');
    leaf.className = 'leaf';
    face.textContent = b.textContent;
    leaf.appendChild(face);
    cell.insertBefore(leaf, b.nextSibling);
    b.textContent = shown(next);
    void leaf.offsetWidth;
    leaf.classList.add('fall');
    setTimeout(function () { leaf.remove(); }, FLIP);
  }

  // Turns every cell of the row to its letter in `text`, then calls done.
  function turn(cells, text, done) {
    var pending = 0;
    cells.forEach(function (cell, i) {
      var want = text.charAt(i) || ' ';
      var from = DRUM.indexOf(ch(cell.querySelector('b').textContent));
      var to = DRUM.indexOf(want);
      if (from === to) return;
      if (from < 0 || to < 0) { cell.querySelector('b').textContent = shown(want); return; }
      var n = Math.min((to - from + DRUM.length) % DRUM.length, 4 + (i % 7));
      var pos = (to - n + DRUM.length) % DRUM.length;
      var step = 0;
      var token = {};
      cell._turn = token;
      pending++;
      (function tick() {
        if (cell._turn !== token) return;
        if (step === n) { if (--pending === 0) done(); return; }
        step++;
        pos = (pos + 1) % DRUM.length;
        flap(cell, DRUM[pos]);
        setTimeout(tick, FLIP);
      })();
    });
    if (pending === 0) done();
  }

  function pad(s, n) {
    s = s.toUpperCase();
    while (s.length < n) s += ' ';
    return s.slice(0, n);
  }

  document.addEventListener('DOMContentLoaded', function () {
    var board = document.querySelector('.board');
    var note = board && board.querySelector('.status');
    if (!note) { root.classList.remove('flaps'); return; }
    var fields = Array.prototype.slice.call(board.querySelectorAll('.field'));
    var cells = [];
    var widths = fields.map(function (f) {
      var cs = Array.prototype.slice.call(f.querySelectorAll('.cell'));
      cells = cells.concat(cs);
      return cs.length;
    });
    var at = board.querySelector('.board-at');
    function row(fr) {
      var parts = [fr.f, fr.to, fr.gate, fr.note];
      return parts.map(function (p, i) { return pad(p, widths[i]); }).join('');
    }

    // THE FIRST FRAME, NOW IN THE DOM: what the class was showing, so taking
    // the class away changes nothing on screen.
    note.querySelectorAll('.cell').forEach(function (c) {
      c.querySelector('b').textContent = shown(c.getAttribute('data-from') || ' ');
    });
    note.classList.remove('off');
    root.classList.remove('flaps');

    var index = 0, timer = 0, busy = false, seen = false, started = false;
    function show(fr) {
      busy = true;
      TONES.forEach(function (t) { note.classList.remove(t); });
      if (at) at.textContent = fr.at;
      turn(cells, row(fr), function () {
        if (fr.tone) note.classList.add(fr.tone);
        busy = false;
      });
    }
    function next() {
      index = (index + 1) % FRAMES.length;
      show(FRAMES[index]);
      plan(HOLD);
    }
    function plan(ms) {
      clearTimeout(timer);
      if (seen && !document.hidden) timer = setTimeout(started ? next : open, ms);
    }
    function open() {
      started = true;
      show(FRAMES[0]);
      plan(HOLD);
    }
    function wake() { if (!busy) plan(started ? HOLD : FIRST); }
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) clearTimeout(timer); else wake();
    });
    if (!('IntersectionObserver' in window)) { seen = true; wake(); return; }
    new IntersectionObserver(function (es) {
      seen = es.some(function (e) { return e.isIntersecting; });
      if (seen) wake(); else clearTimeout(timer);
    }, { threshold: 0.6 }).observe(board);
  });
})();
