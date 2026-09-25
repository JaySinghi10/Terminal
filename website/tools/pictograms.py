"""The three AIGA/DOT pictograms the dining table uses, as one inline SVG
sprite: each symbol centred in a 100 x 100 box, filled with currentColor, with
its holes (the cup's handle, the olive) cut out so the plate behind shows
through. Public domain: AIGA and the US DOT, 1974 and 1979."""

# (id, fill rule, source width, source height, path data). The bar is
# nonzero: its stem and foot overlap the bowl, and even-odd would punch holes
# where they meet; the olive winds the other way, so it is still cut out.
RESTAURANT = ('p-food', 'nonzero', 248.746, 472.182,
              'M115.158 154.044c0 15.334-13.97 31.75-32.084 31.75v258.833c0 36.74-50.081 36.74-50.081 0V185.794C15.353 185.794 0 172.211 0 151.857V9.41901c0-12.39899 17.92-12.87799 17.92.479V115.196h15V8.94c0-11.39599 17.25-12.12799 17.25.47901V115.196h15.5V9.065c0-11.89898 16.75-12.37799 16.75.47901V115.196h15.25V9.065c0-11.77398 17.497-12.25299 17.497.47901l-.009 144.49999zm133.588-111.52v401.977c0 35.933-50.177 35.401-50.177 0V285.006H171.85V42.524c0-56.445 76.896-56.445 76.896 0z')
COFFEE = ('p-coffee', 'evenodd', 443.14, 273.32,
          'M443.14,226.35H0c0,32.09,24.449,46.97,44.075,46.97h355c23.49,0,44.06-18.47,44.06-46.97H443.14z'
          'M359.08,0H94.56v173.6c0,23.51,20.3,42.14,42.26,42.14h171.49c24.79,0,41.67-20.8,41.67-42.14v-14.49'
          'c48.89,0,84.41-36.76,84.41-79.56C434.39,35.85,399.58,0,359.08,0z M349.98,126.1V32.59l9.1,0.01l0.01,0.02'
          'c33.47,0,44.22,31.69,44.11,46.98C403.2,104.55,384.82,128.36,349.98,126.1z')
# The bar symbol is drawn from primitives in its source; the same shapes as
# one path: the glass's bowl with the olive cut out, the stem, the foot.
BAR = ('p-bar', 'nonzero', 660, 660,
       'M0,0H660L330,390Z'
       'M430,200a50,50 0 1 0 -100,0a50,50 0 1 0 100,0Z'
       'M290,300H370V660H290Z'
       'M180,580H480a40,40 0 0 1 0,80H180a40,40 0 0 1 0,-80Z')

BOX = 100.0
INNER = 66.0  # the symbol's longer side, inside the box


def symbol(sym):
    sid, rule, w, h, d = sym
    s = INNER / max(w, h)
    tx = (BOX - w * s) / 2
    ty = (BOX - h * s) / 2
    return ('<symbol id="%s" viewBox="0 0 100 100"><path fill="currentColor" fill-rule="%s" '
            'transform="translate(%.2f %.2f) scale(%.5f)" d="%s"/></symbol>') % (sid, rule, tx, ty, s, d)


print('<svg class="sprite" aria-hidden="true" focusable="false">'
      + ''.join(symbol(x) for x in (RESTAURANT, COFFEE, BAR)) + '</svg>')
