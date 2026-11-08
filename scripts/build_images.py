"""Resized WebP copies of the product photographs.

The problem
-----------
Every photograph on the site is served at its original size, which for most is
1200x1200, and the markup asks for it everywhere: a catalogue tile roughly 300 px wide,
a 62 px gallery thumbnail and a group card 92 px tall all load the same file. A category
page is a dozen of those, the catalogue is 130, and the largest single photograph is
439 KB. On a phone that is the slowest thing on the page by a wide margin.

Every container the photographs sit in is square with `object-fit: contain`
(.tile .ph, .gallery .main, .thumbs, .gcard img), so a smaller copy loses nothing
visually -- it is scaled into the same box either way.

What this writes
----------------
For each assets/products/<name>.jpg, two WebP copies beside it:

    <name>-400.webp     for tiles, thumbnails and group cards
    <name>-800.webp     for the main product photograph, and for tiles on a 2x screen

build_static.py emits these as a <picture> with the original JPEG still in the <img>, so
a browser without WebP support keeps working and nothing breaks if a variant is missing.

    python3 scripts/build_images.py            # only what is missing or out of date
    python3 scripts/build_images.py --force    # rebuild every variant
    python3 scripts/build_images.py --check    # report, write nothing

Run it after adding photographs (scripts/add_photos.py), then build_static.py.
"""
import glob
import json
import os
import sys

try:
    from PIL import Image
except ImportError:                                     # pragma: no cover
    raise SystemExit('Pillow is needed: python3 -m pip install pillow')

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, 'assets', 'products')
WIDTHS = (400, 800)
QUALITY = 80
# build_static.py reads this instead of opening the images, so the site can be built
# without Pillow installed. It holds each variant's true pixel width, which srcset needs:
# a variant is never upscaled, so the "800" copy of a 577 px original is still 577 px and
# claiming 800w would make a wide screen fetch a blurry file.
MANIFEST = os.path.join(ROOT, 'data', 'images.json')


def variant_path(jpg, w):
    return '%s-%d.webp' % (os.path.splitext(jpg)[0], w)


def stale(jpg, out):
    """A variant is stale if it is missing or older than its source."""
    if not os.path.exists(out):
        return True
    return os.path.getmtime(out) < os.path.getmtime(jpg)


def build_one(jpg, force=False):
    made = []
    im = None
    for w in WIDTHS:
        out = variant_path(jpg, w)
        if not force and not stale(jpg, out):
            continue
        if im is None:
            im = Image.open(jpg)
            im.load()
        # Never upscale: a 577 px original stays 577 px wide in its "800" slot, which is
        # correct -- srcset describes what a candidate IS, and claiming 800w for an
        # upscaled 577 would have the browser pick a blurry file on a wide screen.
        if im.width <= w and im.height <= w:
            copy = im.copy()
        else:
            copy = im.copy()
            copy.thumbnail((w, w), Image.LANCZOS)
        copy.convert('RGB').save(out, 'WEBP', quality=QUALITY, method=6)
        made.append((out, copy.width, copy.height, os.path.getsize(out)))
    return made


def main():
    force = '--force' in sys.argv
    check = '--check' in sys.argv
    jpgs = sorted(glob.glob(os.path.join(SRC, '*.jpg')))
    if not jpgs:
        raise SystemExit('no photographs in %s' % SRC)

    todo = [j for j in jpgs
            if force or any(stale(j, variant_path(j, w)) for w in WIDTHS)]
    print('%d photograph(s), %d needing variants' % (len(jpgs), len(todo)))
    if check:
        print('manifest %s' % ('present' if os.path.exists(MANIFEST) else 'MISSING'))
        for j in todo[:20]:
            print('   stale: %s' % os.path.basename(j))
        if len(todo) > 20:
            print('   ... and %d more' % (len(todo) - 20))
        return

    orig_total = new_total = 0
    for i, jpg in enumerate(todo, 1):
        made = build_one(jpg, force=force)
        if not made:
            continue
        orig_total += os.path.getsize(jpg)
        new_total += min(sz for _, _, _, sz in made)
        if i % 50 == 0 or i == len(todo):
            print('   %d/%d' % (i, len(todo)))

    # The manifest is rewritten from what is on disk, so a removed photograph drops out.
    manifest = {}
    for j in jpgs:
        rel = '/assets/products/' + os.path.basename(j)
        entries = []
        for w in WIDTHS:
            v = variant_path(j, w)
            if not os.path.exists(v):
                continue
            iw, ih = Image.open(v).size
            entries.append({'src': '/assets/products/' + os.path.basename(v),
                            'w': iw, 'h': ih})
        # Two candidates of the same width are one candidate: a small original yields an
        # identical 400 and 800 copy, and srcset must not list a width twice.
        seen, uniq = set(), []
        for en in entries:
            if en['w'] in seen:
                continue
            seen.add(en['w'])
            uniq.append(en)
        if uniq:
            manifest[rel] = uniq
    with open(MANIFEST, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    print('manifest: %s (%d photograph(s))' % (MANIFEST, len(manifest)))

    kept = sum(os.path.getsize(variant_path(j, w)) for j in jpgs for w in WIDTHS
               if os.path.exists(variant_path(j, w)))
    jpg_total = sum(os.path.getsize(j) for j in jpgs)
    print('originals        : %.1f MB' % (jpg_total / 1e6))
    print('webp variants    : %.1f MB (both widths, all photographs)' % (kept / 1e6))
    if orig_total:
        print('a thumbnail now costs %.0f%% of what it did'
              % (100.0 * new_total / orig_total))
    print('\nNow run: python3 scripts/build_static.py')


if __name__ == '__main__':
    main()
