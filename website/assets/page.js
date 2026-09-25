/* The home page's moving parts, apart from the board (board.js): the step
   lists beside the phones, the dining table, and the dates in the example
   email. Without script the page rests on each first state. */
(function () {
  'use strict';

  var still = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  var FADE = 300;  // --fade in page.css
  function $(id) { return document.getElementById(id); }
  function each(list, fn) { Array.prototype.forEach.call(list, fn); }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text) e.textContent = text;
    return e;
  }

  /* ── WHERE THE POINTER CROSSED THE EDGE ────────────────────────────────
     A button's ink grows from, and drains back to, the point where the
     pointer came in or went out (page.css), in a disc sized to cover the
     button from any corner. */
  each(document.querySelectorAll('.btn'), function (b) {
    function at(e) {
      var r = b.getBoundingClientRect();
      b.style.setProperty('--x', (e.clientX - r.left) + 'px');
      b.style.setProperty('--y', (e.clientY - r.top) + 'px');
      b.style.setProperty('--d', Math.ceil(2 * Math.hypot(r.width, r.height)) + 'px');
    }
    b.addEventListener('pointerenter', at);
    b.addEventListener('pointerleave', at);
  });

  /* ── A STEP LIST AND ITS PHONE ─────────────────────────────────────────
     A tab list: each step selects one screenshot. The new one fades in over
     the old, which stays fully drawn beneath it until the fade ends, so the
     bezel -- the same pixels in both -- never changes at all. Arrow keys,
     Home and End move between steps. */
  each(document.querySelectorAll('[data-steps]'), function (list) {
    var tabs = list.querySelectorAll('[role=tab]');
    var shots = $(list.getAttribute('data-steps')).querySelectorAll('.shot');
    var cur = 0, timer = 0;
    function show(i) {
      if (i === cur || !shots[i]) return;
      each(tabs, function (t, j) {
        t.setAttribute('aria-selected', j === i ? 'true' : 'false');
        t.tabIndex = j === i ? 0 : -1;
      });
      var from = shots[cur], to = shots[i];
      clearTimeout(timer);
      each(shots, function (s) { if (s !== from && s !== to) s.classList.remove('on', 'rise'); });
      cur = i;
      if (still) { from.classList.remove('on', 'rise'); to.classList.add('on'); return; }
      from.classList.remove('rise');
      to.classList.add('rise');
      void to.offsetWidth;
      to.classList.add('on');
      timer = setTimeout(function () { from.classList.remove('on'); to.classList.remove('rise'); }, FADE);
    }
    each(tabs, function (t, i) { t.addEventListener('click', function () { show(i); }); });
    list.addEventListener('keydown', function (e) {
      var n = tabs.length, i = cur;
      if (e.key === 'ArrowDown' || e.key === 'ArrowRight') i = (cur + 1) % n;
      else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') i = (cur + n - 1) % n;
      else if (e.key === 'Home') i = 0;
      else if (e.key === 'End') i = n - 1;
      else return;
      e.preventDefault();
      show(i);
      tabs[i].focus();
    });
  });

  /* ── WHERE TO EAT ────────────────────────────────────────────────────────
     Rows from assets/dining.js, which tools/dining_sample.py writes from the
     app's own dataset. Open or closed is the deck's openNow, in the airport's
     time: shown where the airport publishes hours, and nowhere else.
     THE PICTOGRAM FOLLOWS THE AIRPORT'S OWN CATEGORY: a bar, a café (with
     bakeries and desserts), or a place to eat. Where the airport gave none,
     the name decides between those, and anything else is a place to eat. */
  var dine = $('dine');
  if (dine && window.DINING) {
    var D = window.DINING.airports;
    var ORDER = ['JFK', 'LHR', 'EWR', 'LGA', 'FRA', 'ARN', 'HKG'];
    var tabs = $('dineTabs');
    var panel = $('dinePanel');
    var WEEK = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    var SVGNS = 'http://www.w3.org/2000/svg';
    var WORD = { bar: 'Bar', coffee: 'Café', food: 'Restaurant' };
    function kind(r) {
      var c = r.c || '';
      if (/\bBar\b/.test(c)) return 'bar';
      if (/Café|Bakery|Dessert/.test(c)) return 'coffee';
      if (c) return 'food';
      if (/\b(bar|pub|tavern|brew)/i.test(r.n)) return 'bar';
      if (/(coffee|caf[eé]|espresso|bakery)/i.test(r.n)) return 'coffee';
      return 'food';
    }
    function pict(k) {
      var box = el('span', 'pict');
      box.setAttribute('aria-hidden', 'true');
      var svg = document.createElementNS(SVGNS, 'svg');
      svg.setAttribute('viewBox', '0 0 100 100');
      var use = document.createElementNS(SVGNS, 'use');
      use.setAttribute('href', '#p-' + (k === 'food' ? 'food' : k));
      svg.appendChild(use);
      box.appendChild(svg);
      return box;
    }
    function toMin(hhmm) {
      var m = /^(\d{1,2}):(\d{2})$/.exec(hhmm || '');
      return m ? +m[1] * 60 + +m[2] : null;
    }
    function covers(w, d) { return w[0] <= w[1] ? d >= w[0] && d <= w[1] : d >= w[0] || d <= w[1]; }
    function openNow(r, tz) {
      if (r.a) return true;
      if (!r.w || !r.w.length) return null;
      var parts;
      try {
        parts = new Intl.DateTimeFormat('en-GB', { timeZone: tz, weekday: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(new Date());
      } catch (e) { return null; }
      function get(t) { for (var i = 0; i < parts.length; i++) if (parts[i].type === t) return parts[i].value; return ''; }
      var wk = WEEK.indexOf(get('weekday'));
      if (wk < 0) return null;
      var now = parseInt(get('hour'), 10) % 24 * 60 + parseInt(get('minute'), 10);
      for (var i = 0; i < r.w.length; i++) {
        var w = r.w[i];
        if (!covers(w, wk)) continue;
        var o = toMin(w[2]), c = toMin(w[3]);
        if (o === null || c === null) continue;
        if (c > o ? now >= o && now < c : now >= o || now < c) return true;
      }
      return false;
    }
    function row(r, tz) {
      var li = el('li');
      var k = kind(r);
      li.appendChild(pict(k));
      var body = el('div', 'r-body');
      var top = el('div', 'r-top');
      var name = el('span', 'r-name', r.n);
      name.appendChild(el('span', 'sr', ', ' + WORD[k]));
      top.appendChild(name);
      if (typeof r.s === 'number') top.appendChild(el('span', 'r-serve', r.s + ' min'));
      body.appendChild(top);
      var meta = el('div', 'r-meta');
      if (r.p) meta.appendChild(el('span', '', r.p));
      var open = openNow(r, tz);
      if (open === true) meta.appendChild(el('span', 'r-open', 'Open'));
      if (open === false) meta.appendChild(el('span', '', 'Closed'));
      if (meta.childNodes.length) body.appendChild(meta);
      if (r.h) body.appendChild(el('div', 'r-hours', r.h));
      li.appendChild(body);
      return li;
    }
    var shown = null;
    function showAirport(code) {
      var a = D[code];
      if (!a) return;
      shown = code;
      var nameEl = $('dineName');
      nameEl.firstChild.nodeValue = a.name + ' ';
      nameEl.lastChild.textContent = code;
      var countEl = $('dineCount');
      countEl.textContent = '';
      countEl.appendChild(el('b', '', a.air + ' after security'));
      countEl.appendChild(document.createTextNode(' · ' + a.land + ' before' + (a.arrivals ? ' · ' + a.arrivals + ' in arrivals' : '')));
      var before = $('dineBefore'), after = $('dineAfter');
      before.textContent = '';
      after.textContent = '';
      a.rowsLand.forEach(function (r) { before.appendChild(row(r, a.tz)); });
      a.rowsAir.forEach(function (r) { after.appendChild(row(r, a.tz)); });
      $('dineNote').textContent = a.note || '';
      each(tabs.children, function (b) {
        var on = b.getAttribute('data-code') === code;
        b.setAttribute('aria-selected', on ? 'true' : 'false');
        b.tabIndex = on ? 0 : -1;
      });
    }
    // A CHANGE OF AIRPORT CROSSFADES, a state change rather than a movement.
    function switchTo(code) {
      if (code === shown) return;
      if (still) { showAirport(code); return; }
      panel.classList.add('swap');
      setTimeout(function () { showAirport(code); panel.classList.remove('swap'); }, 120);
    }
    ORDER.forEach(function (code) {
      if (!D[code]) return;
      var b = el('button', '', code);
      b.type = 'button';
      b.setAttribute('role', 'tab');
      b.setAttribute('data-code', code);
      b.setAttribute('aria-controls', 'dinePanel');
      b.title = D[code].name;
      b.addEventListener('click', function () { switchTo(code); });
      tabs.appendChild(b);
    });
    tabs.addEventListener('keydown', function (e) {
      if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
      e.preventDefault();
      var i = ORDER.indexOf(shown);
      var next = ORDER[(i + (e.key === 'ArrowRight' ? 1 : ORDER.length - 1)) % ORDER.length];
      switchTo(next);
      tabs.querySelector('[data-code="' + next + '"]').focus();
    });
    tabs.hidden = false;
    showAirport(ORDER[0]);
  }

  /* ── DATES IN THE EXAMPLE EMAIL ── today plus the attribute's days, in the
     app's own format: "Thu 25 Sep". */
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  var DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  each(document.querySelectorAll('[data-date]'), function (e) {
    var d = new Date();
    d.setHours(12, 0, 0, 0);
    d.setDate(d.getDate() + +e.getAttribute('data-date'));
    e.textContent = DAYS[d.getDay()] + ' ' + d.getDate() + ' ' + MONTHS[d.getMonth()];
  });
})();
