"""Turn the live Shopify catalogue into structured JSON for the static site.

The whole site keys off dimensions, so the real work here is parsing variant option
values into numbers. Stefsotra's variants are dimensional but stored as free text:
"38", "38mm AL", "16-13", "8-14", '1/2"', "A9065010482". Each shape means something
different, and getting it wrong silently would produce a search that returns the
wrong parts -- so anything unrecognised is flagged `unparsed` rather than guessed at.

    python3 scripts/build_catalogue.py            # fetch live
    python3 scripts/build_catalogue.py --offline  # reuse data/_raw.json
"""
import json, os, re, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, 'data')
RAW = os.path.join(DATA, '_raw.json')
SRC = 'https://stefsotra.com/products.json?limit=250'

# The Shopify feed quotes USD, but Stefsotra sells in Moldovan lei and the supplier
# sheets are in lei. The rate below is not a currency conversion -- it is the empirical
# ratio between the feed price and the price on the supplier sheets, measured over 72
# variants across three silicone families (range 15.112-15.150, spread 0.25%). Prices
# are shown as whole lei because 169 of the 199 sheet prices are whole lei.
#
# If Shopify's base prices or its Markets uplift change, re-derive rather than nudge:
#   sheet_price_in_lei / feed_price_in_usd, taken over a family with known sheet prices.
MDL_PER_FEED_USD = 15.1254


def to_mdl(usd):
    return round(float(usd) * MDL_PER_FEED_USD)


# ---------------------------------------------------------------- dimension parsing

MATERIAL = {'AL': 'aluminium', 'PP': 'polypropylene'}


def parse_variant(value, option_name=''):
    """Structured dimensions from a variant option value.

    Returns a dict. Always includes `raw`. Sets `unparsed: True` when the shape is
    not recognised, so the UI can fall back to showing the literal text instead of
    silently filtering the part out of dimensional searches.
    """
    v = (value or '').strip()
    d = {'raw': v}
    if not v or v.lower() in ('default title', 'заголовок'):
        d['default'] = True
        return d

    # OE part number: letters+digits, or digit groups with spaces -- e.g. A9065010482,
    # "9 065 012 482", 5490-1303450. Checked first; it would otherwise look like a size.
    if re.fullmatch(r'[A-Za-z]{0,4}[\d][\d\s\-/.]{6,}[\dA-Za-z]', v) or 'OE' in option_name:
        d['oe'] = re.sub(r'\s+', '', v)
        return d

    # material suffix: "38mm AL", "75mm Al", "100mm PP"
    m = re.fullmatch(r'(\d+(?:[.,]\d+)?)\s*mm\s*(AL|PP)', v, re.I)
    if m:
        d['id_mm'] = float(m.group(1).replace(',', '.'))
        d['material'] = MATERIAL[m.group(2).upper()]
        return d

    # clamp range: "8-14", "110-130". Distinguished from a reducer by option name and
    # by the second number being LARGER -- a reducer always steps down.
    m = re.fullmatch(r'(\d+)\s*[-–]\s*(\d+)', v)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if b > a:
            d['clamp_min'], d['clamp_max'] = a, b
        else:
            d['id_mm'], d['id2_mm'] = float(a), float(b)
        return d

    # reducer with * or / separator: "16*13", "38 / 50", "89*63.5"
    m = re.fullmatch(r'(\d+(?:[.,]\d+)?)\s*[*/xX]\s*(\d+(?:[.,]\d+)?)', v)
    if m:
        a = float(m.group(1).replace(',', '.'))
        b = float(m.group(2).replace(',', '.'))
        d['id_mm'], d['id2_mm'] = (a, b) if a >= b else (b, a)
        return d

    # BSP / imperial thread: 1/2", 3/4", 1"
    m = re.fullmatch(r'(\d+(?:\s*\d*/\d+)?)\s*["”]', v)
    if m:
        d['thread'] = m.group(0)
        return d

    # plain millimetre size: "38", "63.5", "Diameter 20"
    m = re.fullmatch(r'(?:diameter\s*)?(\d+(?:[.,]\d+)?)\s*(?:mm)?', v, re.I)
    if m:
        d['id_mm'] = float(m.group(1).replace(',', '.'))
        return d

    # DN size: "DN40", "DN50 / 50 mm"
    m = re.match(r'DN\s*(\d+)', v, re.I)
    if m:
        d['dn'] = int(m.group(1))
        return d

    # belt / seal designations: "L-800мм", "1.2 - 95*120 - 1"
    if re.match(r'L\s*[-–]\s*\d+', v, re.I) or re.search(r'\d+\*\d+', v):
        d['designation'] = v
        return d

    # reducer stated in mm: "50-32 mm", "20-30 mm", "75-50 mm (E)".
    # Order is meaningful here -- A50-75 and A75-50 are different parts -- so it is
    # preserved rather than sorted, and min/max are derived separately for searching.
    m = re.match(r'(\d+)\s*[-–]\s*(\d+)\s*mm', v, re.I)
    if m:
        d['id_mm'], d['id2_mm'] = float(m.group(1)), float(m.group(2))
        note = re.search(r'\(([^)]+)\)', v)
        if note:
            d['note'] = note.group(1)
        return d

    # size with the imperial equivalent alongside: '50 mm (2")', '65 mm (2,5")'
    m = re.match(r'(\d+)\s*mm\s*\(([^)]+)\)', v, re.I)
    if m:
        d['id_mm'] = float(m.group(1))
        d['thread'] = m.group(2)
        return d

    # a label in front of the size: "Suction / 38", "MB 50 mm", "VK 100 mm"
    m = re.match(r'([A-Za-zА-Яа-я][\w\s]*?)\s*[/ ]\s*(\d+(?:[.,]\d+)?)\s*(?:mm)?$', v)
    if m:
        d['group'] = m.group(1).strip()
        d['id_mm'] = float(m.group(2).replace(',', '.'))
        return d

    # size followed by a material word: "50 пластик" (plastic), "75 пластик"
    m = re.match(r'(\d+(?:[.,]\d+)?)\s*(?:mm)?\s+([A-Za-zА-Яа-я]+)$', v)
    if m:
        d['id_mm'] = float(m.group(1).replace(',', '.'))
        word = m.group(2).lower()
        d['material'] = 'polypropylene' if word.startswith('пласт') else word
        return d

    d['unparsed'] = True
    return d


# ---------------------------------------------------------------- product attributes

ANGLE_RE = re.compile(r'(45|90|135|180)\s*°')
LENGTH_RE = re.compile(r'\bL\s*(\d{3,4})\s*(?:mm)?', re.I)


def product_attrs(title, tags, body):
    a = {}
    m = ANGLE_RE.search(title)
    if m:
        a['angle'] = int(m.group(1))
    elif re.search(r'U-Shaped|180', title, re.I):
        a['angle'] = 180
    m = LENGTH_RE.search(title)
    if m:
        a['length_mm'] = int(m.group(1))
    t = title.lower()
    if 'silicone' in t:
        a['material'] = 'silicone'
    elif 'camlock' in t or 'aluminum' in t or 'aluminium' in t:
        a['material'] = 'aluminium'
    if 'reducer' in t or 'transition' in t or 'reducing' in t:
        a['reducer'] = True

    # specification facts worth surfacing, pulled only when the description states them
    spec = {}
    txt = re.sub(r'<[^>]+>', ' ', body or '')
    m = re.search(r'[-–−]\s*(\d{2,3})\s*°?[CС].{0,12}?\+?\s*(\d{2,3})\s*°?[CС]', txt)
    if m:
        spec['temperature'] = f"-{m.group(1)}°C … +{m.group(2)}°C"
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*MPa', txt, re.I)
    if m:
        spec['max_pressure'] = m.group(0)
    m = re.search(r'wall thickness of (\d+)\s*mm', txt, re.I)
    if m:
        spec['wall_mm'] = int(m.group(1))
    for std in ('DIN 14301', 'DIN 28450', 'NF E 29-573', 'UL 94', 'EPDM', 'NBR', 'PA6'):
        if std.lower() in txt.lower():
            spec.setdefault('standards', []).append(std)
    return a, spec


# Categories, most specific first -- the first rule that matches wins. Fittings are
# tested before hoses because "Hose Head" and "Coupling Head" both contain "hose" but
# belong with the couplings. Several titles are Cyrillic only, so the keywords are too.
def has(t, *words):
    return any(w in t for w in words)


# How each category is sold. Hose is cut from a roll and priced by the metre; a moulded
# silicone elbow, a coupling or a clamp is one item. Nothing in the Shopify data records
# this -- exactly one description of 114 mentions a metre -- so it is a rule stated here
# rather than something derived, and it is the first place to correct if a category is
# actually sold the other way.
#
# Silicone hoses are deliberately PIECES: they are moulded fittings of a fixed length
# (L102, L1000), not cut lengths.
UNIT_BY_CATEGORY = {
    'industrial-hose': 'm',
    'pvc-hose':        'm',
    'rubber-profile':  'm',
    'plastic-stock':   'm',
}
UNIT_OVERRIDE = {
    'pvc-curtains': 'pc',        # sold as a made-up curtain, not off the roll
}


CATEGORY_RULES = [
    # --- couplings and fittings
    ('camlock',        lambda t: has(t, 'camlock')),
    ('storz',          lambda t: has(t, 'storz')),
    ('guillemin',      lambda t: has(t, 'guillemin')),
    ('bauer',          lambda t: has(t, 'bauer')),
    ('tw-coupling',    lambda t: has(t, 'vb coupling', 'mb coupling', 'mk coupling',
                                     'vk coupling')),
    ('hose-fitting',   lambda t: has(t, 'head', 'adapter', 'nut', 'nipple', 'coupling')),
    ('valve',          lambda t: has(t, 'valve')),
    # --- clamps and sealing
    ('clamp',          lambda t: has(t, 'clamp', 'хомут')),
    ('gasket',         lambda t: has(t, 'gasket', 'seal', 'прокладк')),
    ('rubber-profile', lambda t: has(t, 'cord', 'шнур', 'sponge', 'profile', 'губчат')),
    # --- hoses
    ('silicone-hose',  lambda t: has(t, 'silicone') and not has(t, 'sheet', 'лист')),
    ('pvc-hose',       lambda t: has(t, 'pvc', 'lay flat', 'layflat')),
    ('industrial-hose', lambda t: has(t, 'hose', 'duct', 'шланг', 'рукав')),
    # --- stock material
    ('sheet-material', lambda t: has(t, 'sheet', 'plate', 'flooring', 'paronite',
                                     'лист', 'текстолит', 'паронит')),
    ('plastic-stock',  lambda t: has(t, 'caprolon', 'polyurethane', 'nylon', 'tube pa',
                                     'капралон', 'капролон', 'полиурет', 'полуретан',
                                     'стержн')),
    # --- vehicles, agriculture
    ('vehicle-part',   lambda t: has(t, 'sprinter', 'kamaz', 'tire', 'liner', 'canopy',
                                     'compressor', 'belt', 'mercedes')),
    ('agri',           lambda t: has(t, 'rake', 'broom', 'sprinkler', 'fregat')),
]

# Second level of the menu. A flat list of 15 categories is as unusable as one bucket
# of 114 products, so the navigation groups them the way a customer thinks about them.
GROUPS = {
    'hoses':     ['silicone-hose', 'industrial-hose', 'pvc-hose'],
    'couplings': ['camlock', 'storz', 'guillemin', 'bauer', 'tw-coupling',
                  'hose-fitting', 'valve'],
    'sealing':   ['clamp', 'gasket', 'rubber-profile'],
    'materials': ['sheet-material', 'plastic-stock'],
    'vehicle':   ['vehicle-part', 'agri'],
}
CAT_GROUP = {c: g for g, cs in GROUPS.items() for c in cs}


def categorise(title, tags):
    t = title.lower()
    for name, rule in CATEGORY_RULES:
        if rule(t):
            return name
    return 'other'


# ---------------------------------------------------------------- build

def main():
    offline = '--offline' in sys.argv
    if offline and os.path.exists(RAW):
        raw = json.load(open(RAW, encoding='utf-8'))
    else:
        req = urllib.request.Request(SRC, headers={'User-Agent': 'Mozilla/5.0'})
        raw = json.loads(urllib.request.urlopen(req, timeout=60).read().decode('utf-8'))
        os.makedirs(DATA, exist_ok=True)
        json.dump(raw, open(RAW, 'w', encoding='utf-8'), ensure_ascii=False)

    products, stats = [], {'variants': 0, 'unparsed': 0, 'no_image': 0}
    for p in raw['products']:
        attrs, spec = product_attrs(p['title'], p['tags'], p.get('body_html'))
        variants = []
        for v in p['variants']:
            dims = parse_variant(v['title'], (p['options'][0]['name'] if p['options'] else ''))
            # derived span, so a reducer is findable from either end regardless of the
            # order its name states
            if 'id_mm' in dims:
                ends = [dims['id_mm']] + ([dims['id2_mm']] if 'id2_mm' in dims else [])
                dims['id_min'], dims['id_max'] = min(ends), max(ends)
            if dims.get('unparsed'):
                stats['unparsed'] += 1
            variants.append({
                'id': v['id'], 'title': v['title'], 'sku': v.get('sku') or '',
                'price': to_mdl(v['price']), 'price_usd': float(v['price']),
                'available': bool(v['available']),
                'dims': dims,
            })
            stats['variants'] += 1
        imgs = [i['src'].split('?')[0] for i in p['images']]
        if not imgs:
            stats['no_image'] += 1
        prices = [v['price'] for v in variants]   # already lei
        cat = categorise(p['title'], p['tags'])
        products.append({
            'handle': p['handle'], 'title': p['title'],
            'category': cat, 'group': CAT_GROUP.get(cat, 'other'),
            'unit': UNIT_OVERRIDE.get(p['handle'], UNIT_BY_CATEGORY.get(cat, 'pc')),
            'vendor': p['vendor'], 'tags': p['tags'],
            'body_html': p.get('body_html') or '',
            'option_name': p['options'][0]['name'] if p['options'] else '',
            'attrs': attrs, 'spec': spec, 'images': imgs,
            'price_min': min(prices) if prices else 0,
            'price_max': max(prices) if prices else 0,
            'variants': variants,
        })

    import collections
    cats = collections.Counter(p['category'] for p in products)
    # Only advertise groups and categories that actually hold stock, so the menu can
    # never show a heading that leads to an empty page.
    groups = [{'key': g, 'categories': [{'key': c, 'count': cats[c]} for c in cs if cats[c]],
               'count': sum(cats[c] for c in cs)}
              for g, cs in GROUPS.items() if sum(cats[c] for c in cs)]

    out = {'currency': 'MDL', 'rate_note': f'MDL = feed USD x {MDL_PER_FEED_USD}',
           'count': len(products),
           'groups': groups, 'products': products}
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, 'products.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))

    # Compact index for the assistant. The full catalogue is ~380 KB, far too much to
    # put in a prompt on every question; this is one line per product with the facts
    # needed to recommend it, and comes to a few KB.
    lines = []
    for p in products:
        ids = sorted({v['dims'][k] for v in p['variants']
                      for k in ('id_min', 'id_max') if v['dims'].get(k) is not None})
        bits = [p['handle'], p['title'], p['category']]
        if ids:
            bits.append(f"{ids[0]:g}-{ids[-1]:g}mm" if len(ids) > 1 else f"{ids[0]:g}mm")
        if p['attrs'].get('angle'):
            bits.append(f"{p['attrs']['angle']}deg")
        if p['attrs'].get('material'):
            bits.append(p['attrs']['material'])
        bits.append(f"{p['price_min']:.0f}-{p['price_max']:.0f} MDL"
                    if p['price_min'] != p['price_max'] else f"{p['price_min']:.0f} MDL")
        bits.append(f"{len(p['variants'])} sizes")
        lines.append(' | '.join(str(b) for b in bits))
    idx = os.path.join(DATA, 'index.txt')
    with open(idx, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    size = os.path.getsize(os.path.join(DATA, 'products.json')) / 1024
    print(f"products {len(products)}  variants {stats['variants']}  ({size:.0f} KB)")
    print(f"unparsed variant values : {stats['unparsed']}")
    print(f"products without image  : {stats['no_image']}")
    print(f"assistant index         : {os.path.getsize(idx)/1024:.1f} KB")
    print("categories:", dict(cats.most_common()))
    for g in groups:
        print(f"  {g['key']:<10} {g['count']:>3}  " +
              ', '.join(f"{c['key']}({c['count']})" for c in g['categories']))
    per_m = [p for p in products if p['unit'] == 'm']
    print(f"\npriced per metre        : {len(per_m)} products "
          f"({', '.join(sorted({p['category'] for p in per_m}))})")
    print(f"priced per piece        : {len(products) - len(per_m)} products")
    if cats.get('other'):
        print(f"\nWARNING: {cats['other']} products still uncategorised:")
        for p in products:
            if p['category'] == 'other':
                print('   ', p['title'][:70])
    ids = sum(1 for p in products for v in p['variants'] if 'id_mm' in v['dims'])
    print(f"variants with a usable inner diameter: {ids}")


if __name__ == '__main__':
    main()
