"""Open Graph preview images -- the card that appears when a link is pasted into
WhatsApp, Telegram, Viber, Messenger or Facebook.

The problem
-----------
The pages were pointing og:image at a product photograph: 1200x1200, product floating
on white. Every preview surface expects roughly 1.91:1, so a square image is either
letterboxed or cropped through the middle, and a lone hose on a white field says nothing
about who is sending it. Shared links are how a trade shop actually spreads, so this is
worth doing properly.

What this makes
---------------
    assets/img/og-default.png    1200x630, for the home, category and company pages
    assets/og/<handle>.png       1200x630 per product: photo, name, price, contact

Both are drawn here rather than hand-made so they stay correct when prices or names
change -- rerun after build_catalogue.py.

    python3 scripts/build_og.py
"""
import json
import os
import re
import shutil
import urllib.request

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, 'data')
OUT = os.path.join(ROOT, 'assets', 'og')
CACHE = os.path.join(DATA, '_img_cache')

W, H = 1200, 630
RED = (191, 44, 44)
INK = (22, 25, 29)
INK2 = (84, 93, 103)
LINE = (228, 232, 236)
BG2 = (247, 249, 250)

FONTS = ['/System/Library/Fonts/Supplemental/Arial Bold.ttf',
         '/System/Library/Fonts/Supplemental/Helvetica.ttc',
         '/Library/Fonts/Arial Bold.ttf']
SERIF = ['/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf',
         '/System/Library/Fonts/Supplemental/Georgia Bold.ttf']


def font(paths, size):
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def wrap(draw, text, f, width, max_lines=3):
    words, lines, cur = text.split(), [], ''
    for w in words:
        trial = (cur + ' ' + w).strip()
        if draw.textlength(trial, font=f) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
            if len(lines) == max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and draw.textlength(lines[-1], font=f) > width - 30:
        while lines[-1] and draw.textlength(lines[-1] + '…', font=f) > width:
            lines[-1] = lines[-1][:-1]
        lines[-1] += '…'
    return lines


def logo_strip(im, x, y, h=34):
    """The wordmark, scaled to a given height."""
    lg = Image.open(os.path.join(ROOT, 'assets', 'img', 'logo.png')).convert('RGBA')
    w = int(lg.width * h / lg.height)
    im.alpha_composite(lg.resize((w, h), Image.LANCZOS), (x, y))
    return w


def fetch(url):
    """Product photos live on Shopify's CDN; cache them so a rebuild is not 114 downloads."""
    os.makedirs(CACHE, exist_ok=True)
    name = re.sub(r'[^A-Za-z0-9._-]', '_', url.split('/')[-1])[:120]
    path = os.path.join(CACHE, name)
    if not os.path.exists(path):
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=45) as r, open(path, 'wb') as f:
            shutil.copyfileobj(r, f)
    return Image.open(path).convert('RGBA')


def money(n):
    return '{:,}'.format(int(round(n))).replace(',', ' ') + ' lei'


def default_card(cat, contact):
    """Home, category and company pages: the shop itself, not one arbitrary hose."""
    im = Image.new('RGBA', (W, H), (255, 255, 255, 255))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 8], fill=RED)

    logo_strip(im, 64, 58, 46)

    f_h1 = font(FONTS, 62)
    f_sub = font(FONTS, 30)
    f_small = font(FONTS, 26)

    for i, line in enumerate(['Furtunuri, cuplaje', 'și cauciuc tehnic']):
        d.text((64, 150 + i * 72), line, font=f_h1, fill=INK)

    variants = sum(len(p['variants']) for p in cat['products'])
    d.text((64, 312), f"{cat['count']} produse · {variants} dimensiuni · prețuri în lei",
           font=f_sub, fill=INK2)

    d.rectangle([64, 372, 64 + 5, 372 + 34], fill=RED)
    d.text((84, 372), 'Chișinău și toată Moldova', font=f_sub, fill=INK)

    d.line([64, H - 108, 660, H - 108], fill=LINE, width=2)
    d.text((64, H - 82), contact['phone'], font=f_small, fill=INK)
    d.text((64 + 260, H - 82), 'stefsotra.md', font=f_small, fill=RED)

    # a strip of real product photography on the right, which says more than a stock shot
    # Distinct photographs, not just distinct products: several products share one
    # picture (see scripts/image_signatures.py), and the first draft of this card showed
    # the same blue elbow twice.
    picks, sigs, cats = [], [], set()
    for p in cat['products']:
        if not p['images'] or p['category'] not in ('silicone-hose', 'camlock', 'storz',
                                                    'clamp', 'valve', 'guillemin', 'bauer'):
            continue
        sg = p.get('img_sig')
        if sg and any(bin(int(sg, 16) ^ int(o, 16)).count('1') <= 6 for o in sigs):
            continue
        if p['category'] in cats:
            continue
        picks.append(p); cats.add(p['category'])
        if sg:
            sigs.append(sg)
        if len(picks) == 4:
            break
    bx, by, bs, gap = 706, 96, 192, 18
    for i, p in enumerate(picks):
        try:
            src = fetch(p['images'][0])
        except Exception:
            continue
        cell = Image.new('RGBA', (bs, bs), BG2 + (255,))
        src.thumbnail((bs - 24, bs - 24), Image.LANCZOS)
        cell.alpha_composite(src, ((bs - src.width) // 2, (bs - src.height) // 2))
        box = Image.new('RGBA', (bs, bs), (0, 0, 0, 0))
        ImageDraw.Draw(box).rounded_rectangle([0, 0, bs - 1, bs - 1], 14, fill=BG2 + (255,),
                                              outline=LINE + (255,), width=2)
        box.alpha_composite(cell)
        x = bx + (i % 2) * (bs + gap)
        y = by + (i // 2) * (bs + gap) + (0 if i % 2 == 0 else 22)
        im.alpha_composite(box, (x, y))
    return im


def product_card(p, lang, contact):
    """Photo on the left, what it is and what it costs on the right."""
    im = Image.new('RGBA', (W, H), (255, 255, 255, 255))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 8], fill=RED)

    pane = 470
    d.rectangle([0, 8, pane, H], fill=BG2 + (255,))
    if p['images']:
        try:
            src = fetch(p['images'][0])
            src.thumbnail((pane - 90, H - 130), Image.LANCZOS)
            im.alpha_composite(src, ((pane - src.width) // 2, (H - src.height) // 2))
        except Exception:
            pass
    else:
        f = font(FONTS, 26)
        d.text((pane // 2, H // 2), 'STEFSOTRA', font=f, fill=INK2, anchor='mm')

    x = pane + 56
    width = W - x - 56
    logo_strip(im, x, 56, 34)

    name = p.get('title_' + lang) or p['title']
    f_name = font(FONTS, 46)
    lines = wrap(d, name, f_name, width, 3)
    y = 132
    for line in lines:
        d.text((x, y), line, font=f_name, fill=INK)
        y += 56

    ids = [v['dims']['id_mm'] for v in p['variants'] if v['dims'].get('id_mm') is not None]
    bits = []
    if ids:
        bits.append('Ø%g mm' % min(ids) if min(ids) == max(ids)
                    else 'Ø%g–%g mm' % (min(ids), max(ids)))
    if p['attrs'].get('angle'):
        bits.append('%s°' % p['attrs']['angle'])
    if len(p['variants']) > 1:
        bits.append('%d dimensiuni' % len(p['variants']))
    if bits:
        d.text((x, y + 8), ' · '.join(bits), font=font(FONTS, 28), fill=INK2)

    price = (money(p['price_min']) if p['price_min'] == p['price_max']
             else 'de la ' + money(p['price_min']))
    d.text((x, H - 190), price, font=font(FONTS, 54), fill=RED)

    d.line([x, H - 104, W - 56, H - 104], fill=LINE, width=2)
    d.text((x, H - 78), contact['phone'] + '  ·  stefsotra.md', font=font(FONTS, 25), fill=INK2)
    return im


def main():
    cat = json.load(open(os.path.join(DATA, 'products.json'), encoding='utf-8'))
    contact = json.load(open(os.path.join(DATA, 'pages.json'), encoding='utf-8'))['_contact']

    os.makedirs(OUT, exist_ok=True)
    default_card(cat, contact).convert('RGB').save(
        os.path.join(ROOT, 'assets', 'img', 'og-default.png'), quality=92)
    print('assets/img/og-default.png')

    made, failed = 0, []
    for i, p in enumerate(cat['products'], 1):
        try:
            product_card(p, 'ro', contact).convert('RGB').save(
                os.path.join(OUT, p['handle'] + '.png'), quality=88)
            made += 1
        except Exception as e:
            failed.append((p['handle'], str(e)[:60]))
        if i % 25 == 0:
            print(f'  {i}/{len(cat["products"])}')

    total = sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT))
    print(f'\n{made} product cards, {total/1024/1024:.1f} MB total')
    if failed:
        print(f'{len(failed)} failed:')
        for h, e in failed[:8]:
            print(f'   {h}: {e}')


if __name__ == '__main__':
    main()
