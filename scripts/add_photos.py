"""Drop photos in a folder, run this, they are live.

Photography is the biggest remaining gap in the catalogue: 6 products have none, 58 have
exactly one, and 13 groups share a picture. This removes every step between having a
photograph and having it on the site, whether it came from a manufacturer's press pack,
a supplier, or a phone on a windowsill.

    1. put the files in photos_in/
    2. name each one after the product handle:
           tw-coupling-mk-brass.jpg          -> first photo
           tw-coupling-mk-brass-2.jpg        -> second photo
           tw-coupling-mk-brass-3.jpg        -> third, and so on
       the handle is the last part of the product's address:
           stefsotra.md/p/tw-coupling-mk-brass/
    3. python3 scripts/add_photos.py --write
    4. python3 scripts/build_static.py

Each photo is trimmed to the object, squared, centred on white and written out at
1200x1200, which is what the tiles, the product gallery and the link-preview cards all
expect. The original is never modified.

Where the photos may come from
------------------------------
Your own camera; a manufacturer's or supplier's press pack, which resellers are normally
given for the asking; a stock library you have licensed. Not another shop's website:
those photographs are their property, and republishing them here would be infringement
whoever asked for it.

    python3 scripts/add_photos.py            # report what it would do
    python3 scripts/add_photos.py --write    # do it
"""
import json
import os
import re
import sys

from PIL import Image, ImageChops, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, 'data')
IN = os.path.join(ROOT, 'photos_in')
OUT = os.path.join(ROOT, 'assets', 'products')
MAP = os.path.join(DATA, 'extra_images.json')

SIZE = 1200
PAD = 0.06          # breathing room around the object, as a share of the square
EXT = ('.jpg', '.jpeg', '.png', '.webp', '.heic', '.tif', '.tiff', '.bmp')


def backdrop(im):
    """The colour of the corners, which is the backdrop unless the object fills the frame."""
    w, h = im.size
    k = max(2, min(w, h) // 40)
    px = []
    for box in ((0, 0, k, k), (w - k, 0, w, k), (0, h - k, k, h), (w - k, h - k, w, h)):
        px += list(im.crop(box).getdata())
    r = sum(p[0] for p in px) // len(px)
    g = sum(p[1] for p in px) // len(px)
    b = sum(p[2] for p in px) // len(px)
    return (r, g, b)


def trim(im, tol=26):
    """Crop away a flat backdrop. Tolerant, because studio white is rarely 255,255,255."""
    bg = Image.new('RGB', im.size, backdrop(im))
    diff = ImageChops.difference(im, bg).convert('L').point(lambda v: 255 if v > tol else 0)
    box = diff.getbbox()
    if not box:
        return im
    # never crop to almost nothing: that means the photo is one flat colour
    if (box[2] - box[0]) < im.width * .08 or (box[3] - box[1]) < im.height * .08:
        return im
    return im.crop(box)


def square(im):
    im = trim(im.convert('RGB'))
    inner = int(SIZE * (1 - PAD * 2))
    # scale to fit, up OR down. thumbnail() only ever shrinks, which left a 300 px
    # source sitting at 300 px in the middle of a 1200 px canvas -- the object filled
    # under a quarter of the frame.
    k = min(inner / im.width, inner / im.height)
    im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
    im = im.filter(ImageFilter.UnsharpMask(radius=1.4, percent=55, threshold=3))
    out = Image.new('RGB', (SIZE, SIZE), (255, 255, 255))
    out.paste(im, ((SIZE - im.width) // 2, (SIZE - im.height) // 2))
    return out


def parse(fname):
    """`tw-coupling-mk-brass-2.jpg` -> ('tw-coupling-mk-brass', 2)"""
    stem = os.path.splitext(fname)[0]
    m = re.match(r'^(.*?)-(\d+)$', stem)
    return (m.group(1), int(m.group(2))) if m else (stem, 1)


def main():
    write = '--write' in sys.argv
    os.makedirs(IN, exist_ok=True)

    cat = json.load(open(os.path.join(DATA, 'products.json'), encoding='utf-8'))
    handles = {p['handle'] for p in cat['products']}
    titles = {p['handle']: p['title'] for p in cat['products']}

    files = sorted(f for f in os.listdir(IN) if f.lower().endswith(EXT))
    if not files:
        print(f'No photos in {IN}\n')
        print(__doc__.split('Where the photos may come from')[0].strip())
        missing = [p for p in cat['products'] if not p['images']]
        if missing:
            print(f'\n{len(missing)} products have no photograph at all. Their handles:')
            for p in missing:
                print(f'   {p["handle"]:<34} {titles[p["handle"]][:44]}')
        return

    good, unknown = {}, []
    for f in files:
        handle, n = parse(f)
        (good.setdefault(handle, []) if handle in handles else unknown).append((n, f))

    print(f'{len(files)} file(s) in photos_in/')
    if unknown:
        print(f'\n{len(unknown)} named after a product that does not exist -- check the spelling:')
        for _, f in unknown[:10]:
            print(f'   {f}')

    if not good:
        return
    print(f'\n{len(good)} product(s) matched:')
    os.makedirs(OUT, exist_ok=True)
    mapping = json.load(open(MAP, encoding='utf-8')) if os.path.exists(MAP) else {}

    for handle, items in sorted(good.items()):
        paths = []
        for n, f in sorted(items):
            dst_rel = f'/assets/products/{handle}-{n}.jpg'
            if write:
                im = Image.open(os.path.join(IN, f))
                if getattr(im, 'n_frames', 1) > 1:
                    im.seek(0)
                square(im).save(os.path.join(OUT, f'{handle}-{n}.jpg'),
                                quality=88, optimize=True, progressive=True)
            paths.append(dst_rel)
        mapping[handle] = paths
        had = len([p for p in cat['products'] if p['handle'] == handle][0]['images'])
        # the source resolution is worth stating: anything under about 700 px has to be
        # enlarged to fill the frame and will look soft next to a proper photograph
        src = Image.open(os.path.join(IN, sorted(items)[0][1]))
        warn = '  LOW RES' if min(src.size) < 700 else ''
        print(f'   {handle:<32} {len(paths)} photo(s)  src {src.width}x{src.height}{warn}'
              f'{"  replaces " + str(had) if had else ""}   {titles[handle][:28]}')

    if write:
        json.dump(mapping, open(MAP, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(f'\nwritten to {MAP}')
        print('now run:  python3 scripts/build_catalogue.py --offline'
              '  &&  python3 scripts/build_static.py')
    else:
        print('\n(dry run -- pass --write to convert and register them)')


if __name__ == '__main__':
    main()
