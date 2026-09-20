#!/usr/bin/env python3
"""Pull every product photograph onto this site and stop borrowing from Shopify.

The catalogue feed hands back image URLs on cdn.shopify.com. Serving those directly
means the whole catalogue goes to placeholders the day that store closes or its
subscription lapses -- not a theoretical risk for a shop that is being sold. This
downloads each one to assets/products/ and records it in data/extra_images.json,
which build_catalogue.py already prefers over whatever the feed says, so the local
copy survives every later rebuild.

    python3 scripts/mirror_images.py            # fetch what is missing
    python3 scripts/mirror_images.py --force    # re-fetch everything

Then rebuild, as usual:

    python3 scripts/build_catalogue.py --offline
    python3 scripts/build_static.py

Photographs are capped at 1200px on the long edge and re-encoded as progressive JPEG.
The tiles and the product gallery draw at 1200 square at most, so anything larger is
weight no visitor benefits from.
"""

import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, 'data')
PRODUCTS = os.path.join(DATA, 'products.json')
EXTRA_IMG = os.path.join(DATA, 'extra_images.json')
OUT_DIR = os.path.join(ROOT, 'assets', 'products')
OUT_URL = '/assets/products'

MAX_EDGE = 1200
QUALITY = 82
UA = 'Mozilla/5.0 (compatible; stefsotra-mirror/1.0)'


def fetch(url, tries=3):
    """Bytes for one image. Shopify rate-limits, so back off rather than give up."""
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            return urllib.request.urlopen(req, timeout=45).read()
        except (urllib.error.URLError, OSError) as exc:      # transient, usually
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError('%s -- %s' % (url, last))


def convert(raw):
    """Re-encode to a progressive JPEG no larger than MAX_EDGE on its long edge."""
    im = Image.open(io.BytesIO(raw))
    # Product shots are on white. Flattening onto white keeps a transparent PNG
    # looking the way it did on the old store instead of going black.
    if im.mode in ('RGBA', 'LA', 'P'):
        im = im.convert('RGBA')
        flat = Image.new('RGB', im.size, (255, 255, 255))
        flat.paste(im, mask=im.split()[-1])
        im = flat
    elif im.mode != 'RGB':
        im = im.convert('RGB')
    if max(im.size) > MAX_EDGE:
        im.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, 'JPEG', quality=QUALITY, optimize=True, progressive=True)
    return buf.getvalue(), im.size


def main():
    force = '--force' in sys.argv
    with open(PRODUCTS, encoding='utf-8') as f:
        products = json.load(f)['products']
    extra = {}
    if os.path.exists(EXTRA_IMG):
        with open(EXTRA_IMG, encoding='utf-8') as f:
            extra = json.load(f)
    os.makedirs(OUT_DIR, exist_ok=True)

    mirrored = skipped = already = 0
    failures = []
    total_bytes = 0

    for p in products:
        handle, urls = p['handle'], p.get('images') or []
        if not urls:
            continue
        local = []
        for i, url in enumerate(urls, 1):
            if not url.startswith('http'):
                local.append(url)                            # already ours
                already += 1
                continue
            # A Cyrillic handle would percent-encode into an unusable filename.
            stem = ''.join(c if (c.isalnum() and c.isascii()) or c in '-_' else '-'
                           for c in handle).strip('-')[:70] or 'product'
            name = '%s-%d.jpg' % (stem, i)
            path = os.path.join(OUT_DIR, name)
            if os.path.exists(path) and not force:
                local.append('%s/%s' % (OUT_URL, name))
                skipped += 1
                continue
            try:
                data, size = convert(fetch(url))
            except Exception as exc:                          # noqa: BLE001 -- report, continue
                failures.append((handle, url, str(exc)[:90]))
                continue
            with open(path, 'wb') as f:
                f.write(data)
            local.append('%s/%s' % (OUT_URL, name))
            mirrored += 1
            total_bytes += len(data)
            print('  %-52s %4d x %-4d %6.0f KB' % (name, size[0], size[1], len(data) / 1024))
        if local:
            extra[handle] = local

    with open(EXTRA_IMG, 'w', encoding='utf-8') as f:
        json.dump(extra, f, ensure_ascii=False, indent=1)
        f.write('\n')

    print('\n%d mirrored (%.1f MB), %d already local, %d on disk already'
          % (mirrored, total_bytes / 1e6, already, skipped))
    print('%d products now carry local photographs' % len(extra))
    if failures:
        print('\n%d FAILED -- these still point at Shopify:' % len(failures))
        for handle, url, err in failures:
            print('  %-40s %s' % (handle, err))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
