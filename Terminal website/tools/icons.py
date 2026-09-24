"""Writes the site's icons from one drawing: a green T on near-black.

    python tools/icons.py

favicon.ico and apple-touch-icon.png sit at the site root, where browsers and
iOS ask for them by default. assets/icon.svg is the same mark for browsers
that take an SVG icon. The app has no icon of its own yet -- it still ships
Expo's template -- so this is a plain placeholder: replace these files when
Terminal has one.
"""
import os
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(HERE)
BG = (17, 17, 17, 255)
GREEN = (74, 222, 128, 255)
# THE T, ON A 64-UNIT GRID: a bar 34 wide and 7 deep, a stem 7 wide, 32 tall
# in all, centred. The SVG below draws the same numbers.
BAR = (15, 16, 49, 23)
STEM = (28.5, 23, 35.5, 48)
SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
       '<rect width="64" height="64" rx="14" fill="#111"/>'
       '<path fill="#4ade80" d="M15 16h34v7h-13.5v25h-7v-25h-13.5z"/></svg>\n')


def draw(size, rounded):
    k = 8  # drawn large and scaled down, which is the anti-aliasing
    s = size * k
    u = s / 64.0
    im = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if rounded:
        d.rounded_rectangle((0, 0, s - 1, s - 1), radius=int(14 * u), fill=BG)
    else:
        d.rectangle((0, 0, s, s), fill=BG)
    for x0, y0, x1, y1 in (BAR, STEM):
        d.rectangle((x0 * u, y0 * u, x1 * u - 1, y1 * u - 1), fill=GREEN)
    return im.resize((size, size), Image.LANCZOS)


def main():
    draw(48, True).save(os.path.join(SITE, 'favicon.ico'), sizes=[(16, 16), (32, 32), (48, 48)])
    # iOS draws its own rounded corners, and a transparent corner would show
    # as black, so the touch icon is square and opaque.
    draw(180, False).convert('RGB').save(os.path.join(SITE, 'apple-touch-icon.png'), optimize=True)
    with open(os.path.join(SITE, 'assets', 'icon.svg'), 'w', encoding='utf8', newline='\n') as f:
        f.write(SVG)
    for name in ('favicon.ico', 'apple-touch-icon.png', os.path.join('assets', 'icon.svg')):
        print(name, os.path.getsize(os.path.join(SITE, name)), 'bytes')


if __name__ == '__main__':
    main()
