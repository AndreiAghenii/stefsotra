"""Fingerprint every product's main photograph, so the site never shows the same
picture twice side by side.

Two products in the hero were showing what looked like one product photographed twice.
Their image URLs were different, so de-duplicating on the URL found nothing: the same
photograph had simply been uploaded under two filenames. This is the same fault the
original catalogue audit found, where a large share of images had been borrowed from a
different product.

So the picture itself is fingerprinted. Each main image is reduced to 8x8 greyscale and
turned into a 64-bit average hash; two images whose hashes differ by a few bits are the
same photograph regardless of filename, size or re-compression. The signature is stored
on the product as `img_sig`, and the page builders use it to pick a visually distinct
set.

    python3 scripts/image_signatures.py           # report the duplicate groups
    python3 scripts/image_signatures.py --write    # store img_sig in products.json
"""
import json
import os
import re
import shutil
import sys
import urllib.request

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, 'data')
CACHE = os.path.join(DATA, '_img_cache')


def fetch(url):
    os.makedirs(CACHE, exist_ok=True)
    name = re.sub(r'[^A-Za-z0-9._-]', '_', url.split('/')[-1])[:120]
    path = os.path.join(CACHE, name)
    if not os.path.exists(path):
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=45) as r, open(path, 'wb') as f:
            shutil.copyfileobj(r, f)
    return path


def ahash(path):
    """64-bit average hash: 8x8 greyscale, each pixel a bit for above/below the mean."""
    im = Image.open(path).convert('L').resize((8, 8), Image.LANCZOS)
    px = list(im.getdata())
    avg = sum(px) / len(px)
    bits = ''.join('1' if p > avg else '0' for p in px)
    return '%016x' % int(bits, 2)


def distance(a, b):
    return bin(int(a, 16) ^ int(b, 16)).count('1')


def main():
    write = '--write' in sys.argv
    path = os.path.join(DATA, 'products.json')
    cat = json.load(open(path, encoding='utf-8'))

    sigs, failed = {}, []
    todo = [p for p in cat['products'] if p['images']]
    for i, p in enumerate(todo, 1):
        try:
            sigs[p['handle']] = ahash(fetch(p['images'][0]))
        except Exception as e:
            failed.append((p['handle'], str(e)[:50]))
        if i % 30 == 0:
            print(f'  {i}/{len(todo)}')

    for p in cat['products']:
        if p['handle'] in sigs:
            p['img_sig'] = sigs[p['handle']]

    # group products whose photographs are the same to within a few bits
    groups, seen = [], set()
    items = list(sigs.items())
    for h, s in items:
        if h in seen:
            continue
        same = [h2 for h2, s2 in items if h2 != h and distance(s, s2) <= 4]
        if same:
            g = [h] + same
            seen.update(g)
            groups.append(g)

    by = {p['handle']: p for p in cat['products']}
    print(f'\n{len(sigs)} images fingerprinted, {len(failed)} could not be read')
    if groups:
        print(f'\n{len(groups)} group(s) of products sharing the same photograph:')
        for g in groups:
            print('  ' + ' | '.join(by[h]['title'][:34] for h in g))
    else:
        print('\nno two products share a photograph')
    if failed:
        print('\nunreadable:', ', '.join(h for h, _ in failed[:8]))

    if write:
        json.dump(cat, open(path, 'w', encoding='utf-8'),
                  ensure_ascii=False, separators=(',', ':'))
        print(f'\nimg_sig written to {path}')
    else:
        print('\n(dry run -- pass --write to save)')


if __name__ == '__main__':
    main()
