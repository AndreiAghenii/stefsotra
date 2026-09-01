#!/usr/bin/env python3
"""Writes assets/img/logo-400.png from assets/img/logo.png.

The source is 1620x395 and 30 KB. The header draws it at 123x30 and the footer at 107x26,
so every page was carrying thirteen times more logo than any screen could show, above the
fold, 489 times over. 400px wide is still better than 3x on a phone.

Quantising to 64 colours is what makes it small rather than merely smaller: the artwork
holds 254 distinct colours, so 64 is close to lossless on it -- measured mean absolute
error 0.38/255 -- and it takes the file from 17 KB to 4 KB, past what lossless WebP
manages. Palette PNG also keeps the alpha channel and needs no <picture> fallback.

logo.png stays where it is. The Organization markup and the link-preview cards point at
it and both want the large one.

    python3 scripts/build_logo.py
"""
import os
import sys

from PIL import Image

WIDTH = 400
COLOURS = 64


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src_path = os.path.join(root, 'assets', 'img', 'logo.png')
    out_path = os.path.join(root, 'assets', 'img', 'logo-400.png')

    src = Image.open(src_path).convert('RGBA')
    height = round(src.height * WIDTH / src.width)
    small = src.resize((WIDTH, height), Image.LANCZOS)
    # .quantize() returns a palette image; converting it back to RGBA would throw the
    # palette away again and with it the whole saving.
    small.quantize(colors=COLOURS, method=Image.FASTOCTREE).save(out_path, optimize=True)

    print('%s  %dx%d  %.1f KB  (from %dx%d, %.1f KB)'
          % (os.path.relpath(out_path, root), WIDTH, height,
             os.path.getsize(out_path) / 1024, src.width, src.height,
             os.path.getsize(src_path) / 1024))
    print('header.site draws it at 123x30, footer at 107x26 -- keep WIDTH at least 3x that.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
