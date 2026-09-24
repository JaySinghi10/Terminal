"""App screenshots into Apple's iPhone 17 bezel, as the images the home page
shows.

    python tools/phones.py s09=path/to/cancelled.png s01=path/to/gate.png ...

Each name becomes assets/phone/<name>-700.webp and <name>-1050.webp. The
page's names and the dev menu's screenshot shots (Profile > Dev only >
website screenshots) they take:

    s09  Site 9  BA286 cancelled, the list open        (the hero)
    s01  Site 1  Gate changed to B32                   (a change arrives)
    s02  Site 2  Delayed 25 min
    s03  Site 3  Took off
    s04  Site 4  Landed
    s05  Site 5  Bags on belt 9
    s06  Site 6  Layover comfortable                   (the connection)
    s07  Site 7  Connection at risk
    s08  Site 8  Connection won't hold
    s11  Site 11 Trip just imported                    (confirmation emails)

Every screenshot must be the iPhone 17's own 1206 x 2622, with full signal,
Wi-Fi and battery in the status bar.

THE BEZEL IS NOT IN THE REPOSITORY, and must not be: Apple's licence lets it
be shown in mock-ups, like these images, not redistributed on its own, and
this repository is public. Download Bezel-iPhone-17.dmg from
developer.apple.com/design/resources (Product Bezels), open it with 7-Zip,
and put "PNG/iPhone 17/iPhone 17 - White - Portrait.png" in tools/bezel/,
which git ignores.

THE SCREENSHOT SITS BEHIND THE BEZEL, cut to the screen's own shape: the
region of the bezel that is see-through at its centre, with the island's hole
filled. A plain rectangle would show through the see-through corners outside
the device too. The bezel itself is used whole: nothing cropped, shadowed,
tilted or drawn over it.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
BEZEL = os.path.join(HERE, 'bezel', 'iPhone 17 - White - Portrait.png')
OUT = os.path.join(HERE, '..', 'assets', 'phone')
SCREEN = (72, 69, 1206, 2622)  # left, top, width, height, measured from the bezel
WIDTHS = (700, 1050)


def screen_mask(bezel):
    """Where the screen shows: the see-through region holding the centre,
    each row filled end to end (the island is opaque, and a hole under it
    would let the page show round its edge), grown two pixels under the
    bezel's soft inner edge."""
    alpha = np.asarray(bezel.getchannel('A'))
    # copied: an image made from an array shares its memory read-only, and
    # the fill would land in a throwaway copy
    seed = Image.fromarray(np.where(alpha < 128, 255, 0).astype(np.uint8)).copy()
    w, h = seed.size
    ImageDraw.floodfill(seed, (w // 2, h // 2), 128)
    region = np.array(seed) == 128
    assert region.sum() > 0.9 * SCREEN[2] * SCREEN[3], 'screen mask too small'
    rows = np.zeros_like(region)
    for y in np.nonzero(region.any(axis=1))[0]:
        xs = np.nonzero(region[y])[0]
        rows[y, xs[0]:xs[-1] + 1] = True
    return Image.fromarray((rows * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5))


def main(pairs):
    if not os.path.exists(BEZEL):
        raise SystemExit('no bezel at %s -- see the note at the top of this file' % BEZEL)
    bezel = Image.open(BEZEL).convert('RGBA')
    mask = screen_mask(bezel)
    os.makedirs(OUT, exist_ok=True)
    for name, path in pairs:
        shot = Image.open(path).convert('RGBA')
        if shot.size != SCREEN[2:]:
            raise SystemExit('%s is %dx%d; an iPhone 17 screenshot is %dx%d' % ((path,) + shot.size + SCREEN[2:]))
        layer = Image.new('RGBA', bezel.size, (0, 0, 0, 0))
        layer.paste(shot, SCREEN[:2])
        canvas = Image.new('RGBA', bezel.size, (0, 0, 0, 0))
        canvas.paste(layer, (0, 0), mask)
        canvas.alpha_composite(bezel)
        for w in WIDTHS:
            h = round(canvas.height * w / canvas.width)
            p = os.path.join(OUT, '%s-%d.webp' % (name, w))
            canvas.resize((w, h), Image.LANCZOS).save(p, quality=90, method=6)
            print('%-18s %dx%d %6.1f KB' % (os.path.basename(p), w, h, os.path.getsize(p) / 1024))


if __name__ == '__main__':
    main([a.split('=', 1) for a in sys.argv[1:]])
