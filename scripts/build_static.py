"""Pre-render the site as real HTML, one file per page per language.

Why this exists
---------------
Everything on this site is drawn by JavaScript from JSON. That is fine for a person
with a browser and useless for a search engine: the HTML a crawler downloads is an
empty <div>. Google will execute JavaScript, eventually and unreliably. Yandex --
which handles a large share of Russian-language search in Moldova -- largely will not,
and neither will most link previews.

So the content is written out as static HTML at build time: headings, prices, sizes,
descriptions, internal links, structured data. The JavaScript then attaches to the page
that is already there rather than replacing it.

URLs
----
    /                       /ru/                  /en/            home
    /c/<category>/          /ru/c/<category>/     ...             category
    /g/<group>/             ...                                   group
    /p/<handle>/            ...                                   product
    /about/ /delivery/ /partners/ /returns/ /warranty/ /contact/   company

Every page declares hreflang alternates for the other two languages, so Google serves
the Romanian page to a Romanian searcher and the Russian page to a Russian one instead
of picking one and treating the others as duplicates.

    python3 scripts/build_static.py
"""
import html
import json
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, 'data')
SITE = 'https://stefsotra.md'          # change if the new site gets its own domain

LANGS = ['ro', 'ru', 'en']
PREFIX = {'ro': '', 'ru': '/ru', 'en': '/en'}

# Search terms people in Moldova actually type, per language. These go in the meta
# description and the page intro -- not stuffed into hidden text, which earns a penalty
# rather than a ranking.
# Russian inflects: "Молдова" standing alone in a title, "в Молдове" inside a sentence.
# Using one form for both produced titles that read as broken Russian.
GEO = {'ro': 'Moldova', 'ru': 'Молдова', 'en': 'Moldova'}
GEO_IN = {'ro': 'Moldova', 'ru': 'Молдове', 'en': 'Moldova'}
CITY = {'ro': 'Chișinău', 'ru': 'Кишинёве', 'en': 'Chișinău'}
CURRENCY = 'lei'

STR = {l: json.load(open(os.path.join(ROOT, 'i18n', l + '.json'), encoding='utf-8'))
       for l in LANGS}
CAT = json.load(open(os.path.join(DATA, 'products.json'), encoding='utf-8'))
PAGES = json.load(open(os.path.join(DATA, 'pages.json'), encoding='utf-8'))
REVIEWS = json.load(open(os.path.join(DATA, 'reviews.json'), encoding='utf-8'))
CONTACT = PAGES['_contact']

BY_HANDLE = {p['handle']: p for p in CAT['products']}
CAT_OF = {}
for g in CAT['groups']:
    for c in g['categories']:
        CAT_OF[c['key']] = g['key']


def t(lang, key, **vars):
    s = STR[lang].get(key, key)
    for k, v in vars.items():
        s = s.replace('{' + k + '}', str(v))
    return s


def cat_label(lang, key):
    return STR[lang].get('cat.' + key, key.replace('-', ' '))


def group_label(lang, key):
    return STR[lang].get('grp.' + key, key)


def e(s):
    return html.escape(str(s if s is not None else ''), quote=True)


def money(n, lang=None, unit=None):
    if not n:
        return t(lang or 'ro', 'prod.onRequest')
    """Whole Moldovan lei, spaced thousands. `lang` is accepted and ignored: the currency
    label is written the same way in all three languages. `unit` appends /m for the
    products that are cut from a roll -- see UNIT_BY_CATEGORY in build_catalogue.py."""
    out = '{:,}'.format(int(round(n))).replace(',', ' ') + ' ' + CURRENCY
    if unit == 'm':
        out += t(lang or 'ro', 'unit.m')
    return out


def strip_tags(s, limit=None):
    s = re.sub(r'<[^>]+>', ' ', s or '')
    s = html.unescape(s)
    s = re.sub(r'\s+', ' ', s).strip()
    if limit and len(s) > limit:
        s = s[:limit].rsplit(' ', 1)[0] + '…'
    return s


def dim_label(d):
    if d.get('default'):
        return ''          # Shopify's "Default Title" placeholder: not a size
    bits = []
    if d.get('id_mm') is not None and d.get('id2_mm') is not None:
        bits.append('Ø%g → %g mm' % (d['id_mm'], d['id2_mm']))
    elif d.get('id_mm') is not None:
        bits.append('Ø%g mm' % d['id_mm'])
    if d.get('clamp_min') is not None:
        bits.append('%g–%g mm' % (d['clamp_min'], d['clamp_max']))
    if d.get('dn') is not None:
        bits.append('DN%s' % d['dn'])
    for k in ('thread', 'material', 'designation'):
        if d.get(k):
            bits.append(d[k])
    if d.get('oe'):
        bits.append('OE ' + d['oe'])
    if d.get('group'):
        bits.insert(0, d['group'])
    if not bits and d.get('raw') and not d.get('default'):
        bits.append(d['raw'])
    return ' · '.join(bits)


def range_label(p):
    ids = [v['dims']['id_mm'] for v in p['variants'] if v['dims'].get('id_mm') is not None]
    out = []
    if ids:
        lo, hi = min(ids), max(ids)
        out.append('Ø%g mm' % lo if lo == hi else 'Ø%g–%g mm' % (lo, hi))
    if p['attrs'].get('angle'):
        out.append('%s°' % p['attrs']['angle'])
    if len(p['variants']) > 1:
        out.append('%d×' % len(p['variants']))
    return ' · '.join(out)


# ---------------------------------------------------------------- page shell

def head(lang, title, desc, path, image=None, jsonld=None, noindex=False):
    """<head> for one page, including the hreflang set and structured data."""
    alts = ''.join(
        '<link rel="alternate" hreflang="%s" href="%s%s%s">' % (l, SITE, PREFIX[l], path)
        for l in LANGS)
    alts += '<link rel="alternate" hreflang="x-default" href="%s%s">' % (SITE, path)
    canonical = SITE + PREFIX[lang] + path
    # 1.91:1 preview card. A square product photo was being cropped through the middle
    # by every chat app; these are drawn by scripts/build_og.py.
    img = image or (SITE + '/assets/img/og-default.png')
    blocks = ''.join(
        '<script type="application/ld+json">%s</script>' %
        json.dumps(b, ensure_ascii=False, separators=(',', ':'))
        for b in (jsonld or []))

    return (
        '<!doctype html>\n<html lang="%s">\n<head>\n' % lang +
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<title>%s</title>\n' % e(title) +
        '<meta name="description" content="%s">\n' % e(desc) +
        ('<meta name="robots" content="noindex,follow">\n' if noindex else
         '<meta name="robots" content="index,follow,max-image-preview:large">\n') +
        '<link rel="canonical" href="%s">\n' % e(canonical) +
        alts + '\n'
        '<meta property="og:type" content="website">\n'
        '<meta property="og:site_name" content="Stefsotra">\n'
        '<meta property="og:title" content="%s">\n' % e(title) +
        '<meta property="og:description" content="%s">\n' % e(desc) +
        '<meta property="og:url" content="%s">\n' % e(canonical) +
        '<meta property="og:image" content="%s">\n' % e(img) +
        '<meta property="og:image:width" content="1200">\n'
        '<meta property="og:image:height" content="630">\n'
        '<meta property="og:image:alt" content="%s">\n' % e(title) +
        '<meta property="og:locale" content="%s">\n' % {'ro': 'ro_MD', 'ru': 'ru_MD', 'en': 'en_US'}[lang] +
        '<meta name="twitter:card" content="summary_large_image">\n'
        '<meta name="theme-color" content="#bf2c2c">\n'
        '<link rel="icon" href="/favicon.ico" sizes="32x32">\n'
        '<link rel="icon" href="/assets/img/favicon.svg" type="image/svg+xml">\n'
        '<link rel="apple-touch-icon" href="/assets/img/apple-touch-icon.png">\n'
        '<link rel="manifest" href="/site.webmanifest">\n'
        '<link rel="preconnect" href="https://cdn.shopify.com" crossorigin>\n'
        '<link rel="stylesheet" href="/assets/css/app.css">\n' +
        blocks +
        '\n</head>\n<body>\n')


def header_html(lang, current=''):
    """The navigation, written out rather than injected, so a crawler can follow it."""
    px = PREFIX[lang]
    mega = ''
    for g in CAT['groups']:
        items = ''.join(
            '<li><a href="%s/c/%s/">%s<span>%d</span></a></li>' %
            (px, c['key'], e(cat_label(lang, c['key'])), c['count'])
            for c in g['categories'])
        mega += ('<div class="mega-col"><a class="mega-h" href="%s/g/%s/">%s</a><ul>%s</ul></div>'
                 % (px, g['key'], e(group_label(lang, g['key'])), items))
    total = sum(len(p['variants']) for p in CAT['products'])
    mega += ('<div class="mega-col mega-cta"><a class="mega-h" href="%s/catalog.html">%s</a>'
             '<p class="small muted">%s</p>'
             '<a class="btn ghost small-btn" href="%s/vehicle.html">%s</a></div>'
             % (px, e(t(lang, 'nav.catalog')), e(t(lang, 'nav.allIn', n=CAT['count'])),
                px, e(t(lang, 'nav.vehicle'))))

    links = ''.join(
        '<a href="%s%s"%s>%s</a>' % (px, url, ' aria-current="page"' if url == current else '',
                                     e(t(lang, key)))
        for url, key in [('/vehicle.html', 'nav.vehicle')])

    langs = ''.join(
        '<a href="%s%s" data-lang="%s" aria-pressed="%s">%s</a>'
        % (SITE if False else PREFIX[l], '{PATH}', l, 'true' if l == lang else 'false', l)
        for l in LANGS)

    return (
        '<header class="site"><div class="wrap bar">'
        '<a class="logo" href="%s/"><img src="/assets/img/logo.png" alt="STEFSOTRA" width="1620" height="395"></a>'
        '<nav class="main" id="mainnav">'
        '<button type="button" class="menu-trigger" id="prodBtn" aria-expanded="false">%s<i></i></button>'
        '%s</nav>'
        '<form class="hsearch" action="%s/search.html" method="get" role="search">'
        '<input type="search" name="q" aria-label="%s" placeholder="%s">'
        '<button type="submit" aria-label="%s">⌕</button></form>'
        '<div class="bar-end">'
        '<button type="button" class="iconbtn" data-ai-open title="%s"><span aria-hidden="true">✦</span>'
        '<span class="lbl">%s</span></button>'
        '<a class="iconbtn cartlink" href="%s/cart.html"><span aria-hidden="true">🛒</span>'
        '<span class="lbl">%s</span><span class="badge" data-cart-badge style="display:none">0</span></a>'
        '<div class="langs">%s</div>'
        '<button class="menu-btn" type="button" aria-label="%s">☰</button>'
        '</div></div>'
        '<div class="mega" id="mega" hidden><div class="wrap mega-in">%s</div></div>'
        '</header>\n'
        % (px, e(t(lang, 'nav.products')), links, px,
           e(t(lang, 'nav.search')), e(t(lang, 'srch.ph')), e(t(lang, 'srch.go')),
           e(t(lang, 'ai.open')), e(t(lang, 'nav.assistant')),
           px, e(t(lang, 'nav.cart')), langs, e(t(lang, 'nav.menu')), mega))


def footer_html(lang, path):
    px = PREFIX[lang]
    cols = [
        ('nav.products', [('/catalog.html', 'nav.catalog'), ('/vehicle.html', 'nav.vehicle'),
                          ('/search.html', 'srch.h1')]),
        ('foot.company', [('/about/', 'nav.about'), ('/partners/', 'nav.partners'),
                          ('/contact/', 'nav.contact')]),
        ('foot.help', [('/delivery/', 'nav.delivery'), ('/returns/', 'nav.returns'),
                       ('/warranty/', 'nav.warranty')]),
    ]
    colhtml = ''.join(
        '<div><h3>%s</h3><ul>%s</ul></div>' %
        (e(t(lang, title)), ''.join('<li><a href="%s%s">%s</a></li>' % (px, u, e(t(lang, k)))
                                    for u, k in links))
        for title, links in cols)

    # Every group linked from the footer of every page: a small, honest internal link
    # graph that lets a crawler reach all 17 categories from anywhere on the site.
    catlinks = ' · '.join(
        '<a href="%s/c/%s/">%s</a>' % (px, c['key'], e(cat_label(lang, c['key'])))
        for g in CAT['groups'] for c in g['categories'])

    c = CONTACT
    return (
        '<footer class="site"><div class="wrap foot">'
        '<div class="foot-brand"><img src="/assets/img/logo.png" alt="STEFSOTRA" class="foot-logo" '
        'width="1620" height="395">'
        '<p class="small">%s</p>'
        '<p class="small"><a href="tel:%s">%s</a></p>'
        '<p class="small"><a href="mailto:%s">%s</a></p>%s</div>%s</div>'
        '<div class="wrap foot-cats small">%s</div>'
        '<div class="wrap foot-legal small"><span>© 2026 STEFSOTRA · '
        '<a href="https://stefsotra.md">stefsotra.md</a></span>'
        '<span class="madeby"><a href="https://aggento.com" target="_blank" '
        'rel="noopener">%s</a></span></div>'
        '</footer>\n'
        % (e(t(lang, 'site.tagline')), e(c['phone_href']), e(c['phone']),
           e(c['email']), e(c['email']),
           ('<p class="small"><a href="%s" target="_blank" rel="noopener">%s</a></p>'
            % (e(c.get('maps', '')), e(c['address']))) if c.get('address') else '',
           colhtml, catlinks, e(t(lang, 'foot.by'))))


def page(lang, path, title, desc, body, image=None, jsonld=None, noindex=False,
         current='', scripts=''):
    doc = (head(lang, title, desc, path, image, jsonld, noindex) +
           header_html(lang, current).replace('{PATH}', path) +
           '<main>' + body + '</main>' +
           footer_html(lang, path) +
           '<script>window.__CONTACT=%s;</script>' % json.dumps(
               {k: CONTACT.get(k, '') for k in
                ('email', 'phone', 'phone_href', 'address', 'maps')},
               ensure_ascii=False, separators=(',', ':')) +
           '<script src="/assets/js/app.js"></script>'
           '<script src="/assets/js/assistant.js"></script>'
           '<script src="/assets/js/static.js"></script>' + scripts +
           '\n</body>\n</html>\n')
    out = os.path.join(ROOT, (PREFIX[lang] + path).lstrip('/'), 'index.html')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(doc)
    return SITE + PREFIX[lang] + path


# ---------------------------------------------------------------- structured data

def org_ld():
    d = {
        '@context': 'https://schema.org', '@type': 'Organization',
        'name': 'Stefsotra', 'url': SITE, 'logo': SITE + '/assets/img/logo.png',
        'telephone': CONTACT['phone'], 'email': CONTACT['email'],
        'areaServed': {'@type': 'Country', 'name': 'Moldova'},
    }
    if CONTACT.get('address'):
        d['address'] = {
            '@type': 'PostalAddress',
            'streetAddress': CONTACT.get('street', CONTACT['address']),
            'postalCode': CONTACT.get('postal_code', ''),
            'addressLocality': CONTACT.get('locality', 'Chișinău'),
            'addressCountry': CONTACT.get('country', 'MD'),
        }
        d['hasMap'] = CONTACT.get('maps', '')
    return d


def crumbs_ld(lang, items):
    return {'@context': 'https://schema.org', '@type': 'BreadcrumbList',
            'itemListElement': [
                {'@type': 'ListItem', 'position': i + 1, 'name': name,
                 'item': SITE + PREFIX[lang] + url}
                for i, (name, url) in enumerate(items)]}


def product_ld(lang, p):
    prices = [v['price'] for v in p['variants'] if v['price']]
    d = {
        '@context': 'https://schema.org', '@type': 'Product',
        'name': p.get('title_' + lang) or p['title'],
        'alternateName': p['title'],
        'description': strip_tags(summary(lang, p), 300),
        'category': cat_label(lang, p['category']),
        'brand': {'@type': 'Brand', 'name': p['vendor'] or 'Stefsotra'},
        'url': SITE + PREFIX[lang] + '/p/%s/' % p['handle'],
    }
    if p['images']:
        d['image'] = p['images'][:4]
    skus = [v['sku'] for v in p['variants'] if v.get('sku')]
    if skus:
        d['sku'] = skus[0]
    # No aggregateRating: there are no reviews yet, and inventing one is both against
    # Google's structured-data policy and against consumer law here.
    if not prices:
        # No price yet: say nothing rather than publish a zero, which Google would show
        # as free and which would be a false offer.
        return d
    d['offers'] = {
        '@type': 'AggregateOffer', 'priceCurrency': 'MDL',
        'unitText': 'metre' if p.get('unit') == 'm' else 'piece',
        'lowPrice': min(prices), 'highPrice': max(prices),
        'offerCount': len(p['variants']),
        'availability': 'https://schema.org/InStock' if any(v['available'] for v in p['variants'])
                        else 'https://schema.org/PreOrder',
        'seller': {'@type': 'Organization', 'name': 'Stefsotra'},
    }
    return d


def faq_ld(faq):
    return {'@context': 'https://schema.org', '@type': 'FAQPage',
            'mainEntity': [{'@type': 'Question', 'name': x['q'],
                            'acceptedAnswer': {'@type': 'Answer', 'text': x['a']}}
                           for x in faq]}


# ---------------------------------------------------------------- shared blocks

PLACEHOLDER_ART = {'hoses': '<path d="M14 34c0-9 7-16 16-16h20c9 0 16 7 16 16v12c0 9-7 16-16 16H30c-9 0-16-7-16-16z"/><path d="M14 40h56M22 24v32M58 24v32"/>', 'couplings': '<circle cx="40" cy="40" r="22"/><circle cx="40" cy="40" r="12"/><path d="M18 40h-8M70 40h-8M40 18v-8M40 70v-8"/>', 'sealing': '<circle cx="40" cy="40" r="24"/><circle cx="40" cy="40" r="17"/><path d="M40 16v8M31 17l3 8M49 17l-3 8"/>', 'materials': '<path d="M12 30h44v28H12z"/><path d="M20 22h44v28"/><path d="M28 14h44v28"/>', 'vehicle': '<ellipse cx="40" cy="40" rx="26" ry="16"/><ellipse cx="40" cy="40" rx="18" ry="9"/><path d="M14 40h52"/>', 'other': '<rect x="16" y="20" width="48" height="40" rx="4"/><path d="M16 34h48"/>'}


def placeholder(lang, prod):
    """Drawn stand-in for a product we have no photograph of.

    A blank grey box reads as a broken image. An outline of the right kind of part,
    with the product's own name under it, reads as what it is: a real product we have
    not photographed yet. It is never another product's photo -- borrowing one is how
    the original catalogue ended up with 41 images showing the wrong item.
    """
    # the category is more specific than the group, so it wins where we have art for it
    art = (PLACEHOLDER_ART.get(prod['category'])
           or PLACEHOLDER_ART.get('tw' if prod['category'] == 'tw-coupling' else '')
           or PLACEHOLDER_ART.get(prod['group'], PLACEHOLDER_ART['other']))
    return ('<div class="ph none"><svg class="phart" viewBox="0 0 80 80" aria-hidden="true" '
            'fill="none" stroke="currentColor" stroke-width="2.5" stroke-linejoin="round" '
            'stroke-linecap="round">%s</svg><span class="phname">%s</span>'
            '<span class="phnote">%s</span></div>'
            % (art, e(prod['title']), e(t(lang, 'ph.none'))))


def desc_html(lang, p):
    """Description in the page's language. Falls back to the original whenever a
    translation is absent or was held back by the verifier in
    translate_descriptions.py -- an English description beats a wrong number."""
    return p.get('body_' + lang) or p['body_html']


def summary(lang, p):
    """A description in the page's language, assembled from verified data.

    The prose descriptions came from Shopify in English (and Russian for the camlocks),
    and translating 145,000 characters of them needs a model -- see
    translate_descriptions.py. Until that has been run the page would show Romanian
    headings above English text.

    This fills the gap without a translation risk: every sentence is built from a field
    that is already checked -- the parsed dimensions, the angle, the wall thickness, the
    temperature range read out of the source text, the price. Nothing here is invented
    and nothing is machine-translated, so it is correct in every language from the start.
    """
    out = []
    n = len(p['variants'])
    out.append(t(lang, 'sum.is' if n > 1 else 'sum.is1', name=name(lang, p), n=n))

    ids = [v['dims']['id_mm'] for v in p['variants'] if v['dims'].get('id_mm') is not None]
    if ids:
        d = ('%g mm' % min(ids)) if min(ids) == max(ids) else ('%g–%g mm' % (min(ids), max(ids)))
        out.append(t(lang, 'sum.dia', d=d))
    clamps = [v['dims'] for v in p['variants'] if v['dims'].get('clamp_min') is not None]
    if clamps:
        lo = min(c['clamp_min'] for c in clamps)
        hi = max(c['clamp_max'] for c in clamps)
        out.append(t(lang, 'sum.clamp', d='%g–%g mm' % (lo, hi)))

    if p['attrs'].get('angle'):
        out.append(t(lang, 'sum.angle', a=p['attrs']['angle']))
    mat = p['attrs'].get('material')
    if mat:
        out.append(t(lang, 'sum.material', m=STR[lang].get('mat.' + mat, mat)))
    if p['spec'].get('wall_mm'):
        out.append(t(lang, 'sum.wall', w=p['spec']['wall_mm']))
    if p['spec'].get('temperature'):
        out.append(t(lang, 'sum.temp', t=p['spec']['temperature']))
    if p['spec'].get('max_pressure'):
        out.append(t(lang, 'sum.press', p=p['spec']['max_pressure']))
    if p['spec'].get('standards'):
        out.append(t(lang, 'sum.std', s=', '.join(p['spec']['standards'])))

    out.append(t(lang, 'sum.price', p=money(p['price_min'], lang, p['unit'])))
    if p['group'] == 'hoses':
        out.append(t(lang, 'sum.cut'))
    out.append(t(lang, 'sum.deliver'))
    return ' '.join(out)


def name(lang, p):
    """The product's name in the page's language, falling back to the English original."""
    return p.get('title_' + lang) or p['title']


def tile(lang, p):
    px = PREFIX[lang]
    img = p['images'][0] if p['images'] else None
    one = len(p['variants']) == 1
    sizes = '' if one else (
        '<select class="tile-size" aria-label="%s"><option value="">%s</option>%s</select>'
        % (e(t(lang, 'prod.variants')), e(t(lang, 'prod.choose')),
           ''.join('<option value="%s">%s</option>'
                   % (e(v['title']),
                      e(('%s — %s' % (dim_label(v['dims']), money(v['price'], lang, p['unit'])))
                        if dim_label(v['dims']) else money(v['price'], lang, p['unit'])))
                   for v in p['variants'])))
    price = (money(p['price_min'], lang, p['unit']) if p['price_min'] == p['price_max']
             else '<small>%s</small> %s' % (e(t(lang, 'cat.from')), money(p['price_min'], lang, p['unit'])))
    return (
        '<article class="tile" data-h="%s"><a class="tile-link" href="%s/p/%s/">'
        '%s<div class="meta"><div class="name">%s</div><div class="dims">%s</div>'
        '<div class="price">%s</div></div></a>'
        '<div class="tile-add">%s<button type="button" class="btn tile-btn"%s>%s</button></div></article>'
        % (e(p['handle']), px, e(p['handle']),
           ('<div class="ph"><img loading="lazy" src="%s" alt="%s" width="1200" height="1200"></div>'
            % (e(img), e(name(lang, p)))) if img else
           placeholder(lang, p),
           e(name(lang, p)), e(range_label(p)), price, sizes,
           (' data-v="%s"' % e(p['variants'][0]['title'])) if one else '',
           e(t(lang, 'prod.add'))))


def crumb_html(lang, items):
    px = PREFIX[lang]
    parts = []
    for i, (name, url) in enumerate(items):
        last = i == len(items) - 1
        parts.append(e(name) if last else '<a href="%s%s">%s</a>' % (px, url, e(name)))
    return '<p class="small crumb">' + ' › '.join(parts) + '</p>'


# ---------------------------------------------------------------- the pages

def build_home(lang):
    px = PREFIX[lang]
    variants = sum(len(p['variants']) for p in CAT['products'])
    title = {
        'ro': 'Furtunuri industriale, cuplaje și cauciuc tehnic în Moldova | Stefsotra',
        'ru': 'Промышленные шланги, соединения и резинотехнические изделия в Молдове | Stefsotra',
        'en': 'Industrial hoses, couplings and technical rubber in Moldova | Stefsotra',
    }[lang]
    desc = {
        'ro': 'Furtun din silicon și PVC, cuplaje Camlock, Storz, Guillemin și Bauer, coliere '
              'și materiale tehnice. %d produse în %d dimensiuni, prețuri în lei. Livrare în '
              'Chișinău și în toată Moldova.' % (CAT['count'], variants),
        'ru': 'Силиконовые и ПВХ шланги, соединения Camlock, Storz, Guillemin и Bauer, хомуты '
              'и технические материалы. %d товаров в %d размерах, цены в леях. Доставка по '
              'Кишинёву и Молдове.' % (CAT['count'], variants),
        'en': 'Silicone and PVC hose, Camlock, Storz, Guillemin and Bauer couplings, clamps and '
              'technical materials. %d products in %d sizes, priced in lei. Delivery in Chișinău '
              'and across Moldova.' % (CAT['count'], variants),
    }[lang]

    # Four products that look different from each other. Filtering only by category put
    # the KAMAZ and the Sprinter hose side by side, and they share one photograph -- see
    # scripts/image_signatures.py. Pick on the picture, not on the product record.
    picks, seen_sig, seen_cat = [], [], set()
    for p in CAT['products']:
        if not p['images'] or p['category'] not in ('silicone-hose', 'camlock', 'storz',
                                                    'industrial-hose', 'pvc-hose', 'clamp'):
            continue
        sig = p.get('img_sig')
        if sig and any(bin(int(sig, 16) ^ int(s2, 16)).count('1') <= 6 for s2 in seen_sig):
            continue
        if p['category'] in seen_cat:
            continue
        picks.append(p)
        seen_cat.add(p['category'])
        if sig:
            seen_sig.append(sig)
        if len(picks) == 4:
            break
    art = ''.join(
        '<a class="hero-tile t%d" href="%s/p/%s/" title="%s"><img src="%s" alt="%s" '
        'width="1200" height="1200"%s></a>'
        % (i, px, e(p['handle']), e(p['title']), e(p['images'][0]), e(p['title']),
           '' if i == 0 else ' loading="lazy"')
        for i, p in enumerate(picks))

    gcards = ''
    for g in CAT['groups']:
        img = next((p['images'][0] for p in CAT['products']
                    if p['group'] == g['key'] and p['images']), None)
        gcards += (
            '<a class="gcard" href="%s/g/%s/">%s<span class="gcard-t">%s<i>%s</i></span>'
            '<span class="gcard-list small muted">%s</span></a>'
            % (px, g['key'],
               ('<img loading="lazy" src="%s" alt="" width="1200" height="1200">' % e(img))
               if img else '<span class="gcard-ph"></span>',
               e(group_label(lang, g['key'])), e(t(lang, 'cat.results', n=g['count'])),
               ' · '.join(e(cat_label(lang, c['key'])) for c in g['categories'][:4])))

    featured = sorted([p for p in CAT['products'] if p['images']],
                      key=lambda p: -len(p['variants']))[:8]

    body = (
        '<section class="hero"><div class="wrap hero-in"><div class="hero-copy">'
        '<p class="kicker">%s</p><h1>%s</h1><p class="lead">%s</p>'
        '<div class="hero-btns"><a class="btn" href="%s/catalog.html">%s</a>'
        '<a class="btn ghost" href="%s/vehicle.html">%s</a></div>'
        '<form class="hero-search" action="%s/search.html" method="get" role="search">'
        '<input type="search" name="q" placeholder="%s" aria-label="%s">'
        '<button class="btn" type="submit">%s</button></form>'
        '</div><div class="hero-art">%s</div></div></section>'
        % (e(t(lang, 'home.kicker')), e(t(lang, 'home.heroH1')),
           e(t(lang, 'home.heroSub', n=CAT['count'], v=variants)),
           px, e(t(lang, 'home.heroCta')), px, e(t(lang, 'home.heroAlt')),
           px, e(t(lang, 'srch.ph')), e(t(lang, 'srch.go')), e(t(lang, 'srch.go')), art) +

        '<div class="trust"><div class="wrap trust-in">%s</div></div>'
        % ''.join('<div><span aria-hidden="true">✓</span>%s</div>' % e(t(lang, k))
                  for k in ('home.trust1', 'home.trust2', 'home.trust3', 'home.trust4')) +

        '<div class="wrap">'
        '<section class="home-sec"><div class="sec-head"><h2>%s</h2>'
        '<a class="small" href="%s/catalog.html">%s →</a></div><div class="cards">%s</div></section>'
        % (e(t(lang, 'home.cats')), px, e(t(lang, 'home.seeAll')), gcards) +

        '<section class="home-sec"><div class="sec-head"><h2>%s</h2>'
        '<a class="small" href="%s/catalog.html">%s →</a></div><div class="grid">%s</div></section>'
        % (e(t(lang, 'home.popular')), px, e(t(lang, 'home.seeAll')),
           ''.join(tile(lang, p) for p in featured)) +

        '<section class="home-sec ask"><div><h2>%s</h2><p class="muted">%s</p></div>'
        '<button class="btn" type="button" data-ai-open>%s ✦</button></section>'
        % (e(t(lang, 'home.askH')), e(t(lang, 'home.askP')), e(t(lang, 'nav.assistant'))) +
        '</div>')

    site_ld = {'@context': 'https://schema.org', '@type': 'WebSite', 'url': SITE,
               'name': 'Stefsotra', 'inLanguage': lang,
               'potentialAction': {'@type': 'SearchAction',
                                   'target': SITE + PREFIX[lang] + '/search.html?q={search_term_string}',
                                   'query-input': 'required name=search_term_string'}}
    return page(lang, '/', title, desc, body,
                jsonld=[org_ld(), site_ld])


def build_category(lang, key, count):
    px = PREFIX[lang]
    prods = [p for p in CAT['products'] if p['category'] == key]
    label = cat_label(lang, key)
    priced = [p['price_min'] for p in prods if p['price_min'] > 0]
    lo = min(priced) if priced else 0
    sizes = sum(len(p['variants']) for p in prods)
    grp = CAT_OF.get(key, '')

    title = {
        'ro': '%s Chișinău — %d produse, de la %s | Stefsotra' % (label, len(prods), money(lo, lang)),
        'ru': '%s Кишинёв — %d товаров, от %s | Stefsotra' % (label, len(prods), money(lo, lang)),
        'en': '%s in Chișinău — %d products from %s | Stefsotra' % (label, len(prods), money(lo, lang)),
    }[lang]
    desc = {
        'ro': '%s pe stoc la Stefsotra: %d produse, %d dimensiuni, preț de la %s. Livrare în %s '
              'și în toată Moldova, tăiere la dimensiune fără cost.'
              % (label, len(prods), sizes, money(lo, lang), CITY[lang]),
        'ru': '%s в наличии в Stefsotra: %d товаров, %d размеров, цена от %s. Доставка по %s '
              'и всей Молдове, резка по размеру бесплатно.'
              % (label, len(prods), sizes, money(lo, lang), CITY[lang]),
        'en': '%s in stock at Stefsotra: %d products, %d sizes, from %s. Delivery in %s and '
              'across Moldova, cut to size free of charge.'
              % (label, len(prods), sizes, money(lo, lang), CITY[lang]),
    }[lang]

    siblings = [c['key'] for c in next(g for g in CAT['groups'] if g['key'] == grp)['categories']]
    related = ''.join(
        '<a class="chip%s" href="%s/c/%s/">%s</a>' % (' on' if k == key else '', px, k,
                                                      e(cat_label(lang, k)))
        for k in siblings)

    body = ('<div class="pagehead"><div class="wrap">%s<h1>%s</h1><p class="lead">%s</p></div></div>'
            '<div class="wrap"><nav class="chips sibs">%s</nav>'
            '<p class="muted small">%s</p><div class="grid">%s</div>'
            '<p style="margin-top:26px"><a class="btn ghost" href="%s/catalog.html">%s</a></p></div>'
            % (crumb_html(lang, [(t(lang, 'nav.home'), '/'),
                                 (group_label(lang, grp), '/g/%s/' % grp), (label, '')]),
               e(label), e(desc.split('.')[0] + '.'), related,
               e(t(lang, 'cat.results', n=len(prods))),
               ''.join(tile(lang, p) for p in prods), px, e(t(lang, 'cat.all'))))

    lst = {'@context': 'https://schema.org', '@type': 'ItemList',
           'name': label, 'numberOfItems': len(prods),
           'itemListElement': [{'@type': 'ListItem', 'position': i + 1, 'name': p['title'],
                                'url': SITE + PREFIX[lang] + '/p/%s/' % p['handle']}
                               for i, p in enumerate(prods)]}
    crumb = crumbs_ld(lang, [(t(lang, 'nav.home'), '/'),
                             (group_label(lang, grp), '/g/%s/' % grp),
                             (label, '/c/%s/' % key)])
    return page(lang, '/c/%s/' % key, title, desc, body,
                jsonld=[lst, crumb])


def build_group(lang, g):
    px = PREFIX[lang]
    prods = [p for p in CAT['products'] if p['group'] == g['key']]
    label = group_label(lang, g['key'])
    lo = min(p['price_min'] for p in prods)
    sizes = sum(len(p['variants']) for p in prods)
    priced = [p['price_min'] for p in prods if p['price_min'] > 0]
    lo = min(priced) if priced else 0
    title = {
        'ro': '%s Chișinău — %d produse, de la %s | Stefsotra',
        'ru': '%s Кишинёв — %d товаров, от %s | Stefsotra',
        'en': '%s in Chișinău — %d products from %s | Stefsotra',
    }[lang] % (label, len(prods), money(lo, lang))
    desc = {
        'ro': '%s la Stefsotra Chișinău: %d produse în %d dimensiuni, preț de la %s. %s. '
              'Tăiem la dimensiune fără cost, livrare în Chișinău și în toată Moldova.',
        'ru': '%s в Stefsotra, Кишинёв: %d товаров в %d размерах, цена от %s. %s. '
              'Режем по размеру бесплатно, доставка по Кишинёву и всей Молдове.',
        'en': '%s at Stefsotra in Chișinău: %d products in %d sizes, from %s. %s. '
              'Cut to size free of charge, delivery in Chișinău and across Moldova.',
    }[lang] % (label, len(prods), sizes, money(lo, lang),
               ', '.join(cat_label(lang, c['key']) for c in g['categories']))

    cards = ''.join(
        '<a class="gcard" href="%s/c/%s/">%s<span class="gcard-t">%s<i>%s</i></span></a>'
        % (px, c['key'],
           ('<img loading="lazy" src="%s" alt="" width="1200" height="1200">'
            % e(next((p['images'][0] for p in CAT['products']
                      if p['category'] == c['key'] and p['images']), '')))
           if any(p['images'] for p in CAT['products'] if p['category'] == c['key'])
           else '<span class="gcard-ph"></span>',
           e(cat_label(lang, c['key'])), e(t(lang, 'cat.results', n=c['count'])))
        for c in g['categories'])

    # Every product in the group, not a sample of eight. Sixty-four couplings in one
    # undifferentiated wall would be worse than a sample, so they are laid out under
    # their category with a jump list at the top.
    sections = ''
    for c in g['categories']:
        in_cat = [p for p in prods if p['category'] == c['key']]
        if not in_cat:
            continue
        sections += ('<section class="home-sec" id="c-%s">'
                     '<div class="sec-head"><h2>%s</h2>'
                     '<a class="small" href="%s/c/%s/">%s →</a></div>'
                     '<p class="muted small">%s</p><div class="grid">%s</div></section>'
                     % (c['key'], e(cat_label(lang, c['key'])), px, c['key'],
                        e(t(lang, 'nav.allIn', n=c['count'])),
                        e(t(lang, 'cat.results', n=len(in_cat))),
                        ''.join(tile(lang, p) for p in in_cat)))

    jump = '<nav class="chips sibs">' + ''.join(
        '<a class="chip" href="#c-%s">%s <span>%d</span></a>' % (c['key'], e(cat_label(lang, c['key'])), c['count'])
        for c in g['categories'] if any(p['category'] == c['key'] for p in prods)) + '</nav>'

    body = ('<div class="pagehead"><div class="wrap">%s<h1>%s</h1><p class="lead">%s</p></div></div>'
            '<div class="wrap">%s<p class="muted small">%s</p><div class="cards">%s</div>%s</div>'
            % (crumb_html(lang, [(t(lang, 'nav.home'), '/'), (label, '')]),
               e(label), e(desc), jump, e(t(lang, 'cat.results', n=len(prods))), cards, sections))
    return page(lang, '/g/%s/' % g['key'], title, desc, body,
                jsonld=[crumbs_ld(lang, [(t(lang, 'nav.home'), '/'), (label, '/g/%s/' % g['key'])])])


def build_product(lang, p):
    px = PREFIX[lang]
    label = cat_label(lang, p['category'])
    rng = range_label(p)
    price = (money(p['price_min'], lang, p['unit']) if p['price_min'] == p['price_max']
             else '%s %s – %s' % (t(lang, 'cat.from'), money(p['price_min'], lang, p['unit']),
                                 money(p['price_max'], lang, p['unit'])))

    nm = name(lang, p)
    title = '%s — %s | Stefsotra %s' % (nm, rng or label, GEO[lang])
    if len(title) > 68:
        title = '%s | Stefsotra %s' % (nm, GEO[lang])
    body_txt = strip_tags(summary(lang, p), 90)
    desc = {
        'ro': '%s. %s. Preț de la %s, %d dimensiuni pe stoc. %sLivrare în %s și în toată Moldova.',
        'ru': '%s. %s. Цена от %s, %d размеров в наличии. %sДоставка по %s и всей Молдове.',
        'en': '%s. %s. From %s, %d sizes in stock. %sDelivery in %s and across Moldova.',
    }[lang] % (nm, rng or label, money(p['price_min'], lang, p['unit']), len(p['variants']),
               body_txt + '. ' if body_txt else '', CITY[lang])

    imgs = p['images']
    gallery = (
        '<div class="main"><img id="mainImg" src="%s" alt="%s" width="1200" height="1200"></div>'
        % (e(imgs[0]), e(p['title'])) +
        ('<div class="thumbs">%s</div>' % ''.join(
            '<button type="button" data-i="%d" aria-pressed="%s"><img src="%s" alt="" '
            'loading="lazy" width="1200" height="1200"></button>'
            % (i, 'true' if i == 0 else 'false', e(u)) for i, u in enumerate(imgs))
         if len(imgs) > 1 else '')
    ) if imgs else ('<div class="main ph none">%s</div>'
                    % placeholder(lang, p).replace('<div class="ph none">', '').replace('</div>', ''))

    rows = []
    ids = [v['dims']['id_mm'] for v in p['variants'] if v['dims'].get('id_mm') is not None]
    if ids:
        rows.append((t(lang, 'cat.diameter'),
                     '%g mm' % min(ids) if min(ids) == max(ids) else '%g–%g mm' % (min(ids), max(ids))))
    rows.append((t(lang, 'prod.category'), label))
    for key, val in (('prod.material', p['attrs'].get('material')),
                     ('prod.angle', '%s°' % p['attrs']['angle'] if p['attrs'].get('angle') else None),
                     ('prod.length', '%s mm' % p['attrs']['length_mm'] if p['attrs'].get('length_mm') else None),
                     ('prod.wall', '%s mm' % p['spec']['wall_mm'] if p['spec'].get('wall_mm') else None),
                     ('prod.temp', p['spec'].get('temperature')),
                     ('prod.pressure', p['spec'].get('max_pressure')),
                     ('prod.standards', ', '.join(p['spec']['standards']) if p['spec'].get('standards') else None)):
        if val:
            rows.append((t(lang, key), val))
    spec = '<table class="spec">%s</table>' % ''.join(
        '<tr><th>%s</th><td>%s</td></tr>' % (e(k), e(v)) for k, v in rows)

    one = len(p['variants']) == 1
    unnamed = one and p['variants'][0]['dims'].get('default')
    def vlabel(v):
        lbl = dim_label(v['dims'])
        if lbl:
            return '%s — %s' % (lbl, money(v['price'], lang, p['unit']))
        return money(v['price'], lang, p['unit'])

    opts = ('' if one else '<option value="">%s</option>' % e(t(lang, 'prod.choose'))) + ''.join(
        '<option value="%d">%s</option>' % (i, e(vlabel(v)))
        for i, v in enumerate(p['variants']))

    # A plain list of every size, in the HTML. This is what makes "Ø38 mm silicone hose"
    # findable at all -- the sizes are the search terms, and inside a <select> alone they
    # carry much less weight.
    sizetable = '' if unnamed else '<details class="sizelist"%s><summary>%s (%d)</summary><ul>%s</ul></details>' % (
        ' open' if len(p['variants']) <= 12 else '',
        e(t(lang, 'prod.variants')), len(p['variants']),
        ''.join('<li><span>%s</span><b>%s</b>%s</li>'
                % (e(dim_label(v['dims'])), e(money(v['price'], lang, p['unit'])),
                   ('<i>%s %s</i>' % (e(t(lang, 'prod.sku')), e(v['sku']))) if v.get('sku') else '')
                for v in p['variants']))

    related = [x for x in CAT['products']
               if x['handle'] != p['handle'] and x['category'] == p['category']][:5]

    body = (
        '<div class="wrap">' +
        crumb_html(lang, [(t(lang, 'nav.home'), '/'),
                          (group_label(lang, p['group']), '/g/%s/' % p['group']),
                          (label, '/c/%s/' % p['category']), (nm, '')]) +
        '<div class="pdp"><div class="gallery">%s</div><div>' % gallery +
        '<h1>%s</h1>%s<p class="price big">%s</p>%s'
        % (e(nm), ('<p class="altname small muted">%s</p>' % e(p['title'])) if nm != p['title'] else '',
           e(price),
           ('<p class="small muted perm">%s</p>' % e(t(lang, 'unit.perM'))) if p['unit'] == 'm' else '') +
        ('<div class="field" style="margin-top:20px"><label for="variant">%s</label>'
         '<select id="variant">%s</select></div>' % (e(t(lang, 'prod.variants')), opts)
         if not unnamed else
         '<select id="variant" hidden>%s</select>' % opts) +
        '<p class="muted small" id="selInfo" style="margin:-6px 0 12px"></p>' +
        # Hose is cut from a roll, so the thing a customer actually chooses is a length.
        # A slider with a number beside it: the slider is quick on a phone, the box is
        # exact, and the running total updates as either moves.
        ('<div class="lenpick"><label for="metres">%s</label>'
         '<div class="lenrow">'
         '<input type="range" id="metres" min="1" max="100" step="1" value="1">'
         '<div class="lennum"><input type="number" id="metresN" min="1" max="9999" step="1" value="1">'
         '<span>m</span></div></div>'
         '<p class="chips lenquick">%s</p>'
         '<p class="small muted">%s</p></div>'
         % (e(t(lang, 'prod.metres')),
            ''.join('<button type="button" class="size-chip" data-m="%d">%d m</button>' % (m, m)
                    for m in (5, 10, 20, 50, 100)),
            e(t(lang, 'prod.cutNote'))) if p['unit'] == 'm' else '') +
        '<button class="btn" id="add" style="width:100%%" data-add>%s</button>'
        '<ul class="reassure">%s</ul>' % (
            e(t(lang, 'prod.choose')),
            ''.join('<li>%s</li>' % e(t(lang, k))
                    for k in ('prod.noPay', 'prod.cut'))) +
        '<h2 style="margin-top:26px">%s</h2>%s</div></div>' % (e(t(lang, 'prod.spec')), spec) +
        sizetable +
        ('<div class="desc"><h2>%s</h2><p class="summary">%s</p></div>'
         % (e(t(lang, 'prod.summary')), e(summary(lang, p)))) +
        # The manufacturer's own copy is long, and until it has been translated it is in
        # another language than the rest of the page. It stays in the HTML so search
        # engines still read it, but it is folded away behind a summary so the page
        # leads with the specification a customer came for.
        ('<details class="desc orig"><summary>%s</summary>%s%s</details>'
         % (e(t(lang, 'prod.origDesc')),
            ('<p class="small muted">%s</p>' % e(t(lang, 'prod.origNote')))
            if not p.get('body_' + lang) else '',
            desc_html(lang, p)) if p['body_html'] else '') +
        review_block(lang, p) +
        ('<section style="margin-top:40px"><h2>%s</h2><div class="grid">%s</div></section>'
         % (e(t(lang, 'prod.related')), ''.join(tile(lang, x) for x in related)) if related else '') +
        '</div>')

    embed = ('<script>window.__PRODUCT=%s;</script>'
             % json.dumps({'handle': p['handle'], 'unit': p['unit'],
                           'variants': [{'title': v['title'], 'price': v['price'],
                                         'sku': v.get('sku', '')} for v in p['variants']],
                           'images': p['images']}, ensure_ascii=False, separators=(',', ':')))

    return page(lang, '/p/%s/' % p['handle'], title, desc, body,
                image=SITE + '/assets/og/%s.png' % p['handle'],
                jsonld=[product_ld(lang, p),
                        crumbs_ld(lang, [(t(lang, 'nav.home'), '/'),
                                         (label, '/c/%s/' % p['category']),
                                         (p['title'], '/p/%s/' % p['handle'])])],
                scripts=embed)


def review_block(lang, p):
    rs = REVIEWS.get('products', {}).get(p['handle'], [])
    items = ''.join(
        '<article class="review"><span class="stars sm">%s</span><b>%s</b>'
        '<time class="small muted">%s</time><p>%s</p></article>'
        % (''.join('<i class="%s">★</i>' % ('on' if i <= r['rating'] else '') for i in range(1, 6)),
           e(r['name']), e(r.get('date', '')), e(r['text']))
        for r in rs)
    form = (
        '<details class="revform"><summary>%s</summary>'
        '<form name="product-review" method="POST" data-netlify="true" netlify-honeypot="company" id="rf">'
        '<input type="hidden" name="form-name" value="product-review">'
        '<input type="hidden" name="handle" value="%s">'
        '<p hidden><label>company <input name="company"></label></p>'
        '<div class="field"><label>%s</label><div class="starpick">%s'
        '<input type="hidden" name="rating" id="rval" value="5"></div></div>'
        '<div class="field"><label for="rname">%s</label>'
        '<input id="rname" name="name" type="text" required></div>'
        '<div class="field"><label for="rtext">%s</label>'
        '<textarea id="rtext" name="text" rows="4" required></textarea></div>'
        '<button class="btn" type="submit">%s</button></form>'
        '<p class="note ok" id="rok" hidden>%s</p></details>'
        % (e(t(lang, 'rev.write')), e(p['handle']), e(t(lang, 'rev.rating')),
           ''.join('<button type="button" data-r="%d" aria-label="%d">★</button>' % (i, i)
                   for i in range(1, 6)),
           e(t(lang, 'ct.name')), e(t(lang, 'rev.text')),
           e(t(lang, 'rev.submit')), e(t(lang, 'rev.pending'))))
    return ('<section id="reviews" class="reviews"><h2>%s</h2>%s%s</section>'
            % (e(t(lang, 'rev.h')),
               items or '<p class="muted">%s %s</p>' % (e(t(lang, 'rev.none')), e(t(lang, 'rev.first'))),
               form))


def build_content(lang, slug, url):
    d = PAGES[slug].get(lang) or PAGES[slug]['ro']
    px = PREFIX[lang]
    variants = sum(len(p['variants']) for p in CAT['products'])

    parts = []
    if d.get('lead'):
        parts.append('<p class="lead">%s</p>' % e(d['lead']))
    if d.get('stats'):
        parts.append('<div class="statrow">%s</div>' % ''.join(
            '<div class="stat"><b>%s</b><span>%s</span></div>' % (e(s['v']), e(s['l']))
            for s in d['stats']))
    parts += ['<p>%s</p>' % e(x) for x in d.get('body', [])]
    if d.get('cards'):
        if d.get('cardsTitle'):
            parts.append('<h2>%s</h2>' % e(d['cardsTitle']))
        parts.append('<div class="infocards">%s</div>' % ''.join(
            '<div class="infocard"><h3>%s</h3><p>%s</p></div>' % (e(x['t']), e(x['p']))
            for x in d['cards']))
    if d.get('steps'):
        if d.get('stepsTitle'):
            parts.append('<h2>%s</h2>' % e(d['stepsTitle']))
        parts.append('<ol class="flowsteps">%s</ol>' % ''.join(
            '<li><b></b><div><h3>%s</h3><p>%s</p></div></li>' % (e(x['t']), e(x['p']))
            for x in d['steps']))
    if d.get('list'):
        if d.get('listTitle'):
            parts.append('<h2>%s</h2>' % e(d['listTitle']))
        parts.append('<ul class="ticks">%s</ul>' % ''.join('<li>%s</li>' % e(x) for x in d['list']))
    if d.get('faq'):
        if d.get('faqTitle'):
            parts.append('<h2>%s</h2>' % e(d['faqTitle']))
        parts.append('<div class="faq">%s</div>' % ''.join(
            '<details><summary>%s</summary><p>%s</p></details>' % (e(x['q']), e(x['a']))
            for x in d['faq']))
    if d.get('cta'):
        parts.append('<p class="lead" style="margin-top:26px">%s <a href="%s/contact/">%s →</a></p>'
                     % (e(d['cta']), px, e(t(lang, 'nav.contact'))))

    others = [('/about/', 'nav.about'), ('/delivery/', 'nav.delivery'),
              ('/partners/', 'nav.partners'), ('/returns/', 'nav.returns'),
              ('/warranty/', 'nav.warranty'), ('/contact/', 'nav.contact')]
    side = (
        '<div class="sidecard"><h3>%s</h3><p class="small">%s</p>'
        '<a class="bigphone" href="tel:%s">%s</a><a class="small" href="mailto:%s">%s</a>'
        '<button type="button" class="btn ghost small-btn" data-ai-open>%s ✦</button></div>'
        '<div class="sidecard"><h3>%s</h3><ul class="sidelinks">%s</ul></div>'
        % (e(t(lang, 'pg.help')), e(t(lang, 'pg.helpText')),
           e(CONTACT['phone_href']), e(CONTACT['phone']), e(CONTACT['email']), e(CONTACT['email']),
           e(t(lang, 'nav.assistant')), e(t(lang, 'pg.more')),
           ''.join('<li><a href="%s%s">%s</a></li>' % (px, u, e(t(lang, k)))
                   for u, k in others if u != url)))

    body = (
        '<div class="pagehead"><div class="wrap">%s<h1>%s</h1></div></div>'
        '<div class="wrap pagebody"><article class="prose">%s</article>'
        '<aside class="pageside">%s</aside></div>'
        '<div class="wrap"><section class="home-sec ask"><div><h2>%s</h2>'
        '<p class="muted">%s</p></div><a class="btn" href="%s/catalog.html">%s</a></section></div>'
        % (crumb_html(lang, [(t(lang, 'nav.home'), '/'), (d['title'], '')]),
           e(d['title']), ''.join(parts), side,
           e(t(lang, 'pg.ctaH')), e(t(lang, 'pg.ctaP', n=CAT['count'], v=variants)),
           px, e(t(lang, 'nav.catalog'))))

    title = '%s | Stefsotra %s' % (d['title'], GEO[lang])
    desc = strip_tags(d.get('lead', '') + ' ' + (d.get('body') or [''])[0], 158)
    ld = [org_ld(), crumbs_ld(lang, [(t(lang, 'nav.home'), '/'), (d['title'], url)])]
    if d.get('faq'):
        ld.append(faq_ld(d['faq']))
    return page(lang, url, title, desc, body, jsonld=ld, current=url)


def build_contact(lang):
    px = PREFIX[lang]
    c = CONTACT
    addr = ('<a href="%s" target="_blank" rel="noopener">%s</a>'
            '<span class="maplink"><a href="%s" target="_blank" rel="noopener">%s</a></span>'
            % (e(c['maps']), e(c['address']), e(c['maps']), e(t(lang, 'ct.openMap')))) \
           if c.get('address') else '<span class="muted">%s</span>' % e(t(lang, 'ct.noAddr'))

    facts = ''.join(
        '<div class="fact"><span class="small muted">%s</span><div>%s</div></div>' % (e(k), v)
        for k, v in [
            (t(lang, 'ct.phone'), '<a href="tel:%s">%s</a>' % (e(c['phone_href']), e(c['phone']))),
            (t(lang, 'ct.email'), '<a href="mailto:%s">%s</a>' % (e(c['email']), e(c['email']))),
            (t(lang, 'ct.address'), addr),
        ] + ([(t(lang, 'ct.hours'), e(c['hours']))] if c.get('hours') else []))

    flow = '<ol class="flowsteps">%s</ol>' % ''.join(
        '<li><b></b><div><h3>%s</h3></div></li>' % e(t(lang, k))
        for k in ('flow.1', 'flow.2', 'flow.3', 'flow.4'))

    form = (
        '<form name="contact" method="POST" data-netlify="true" netlify-honeypot="company" id="cf">'
        '<input type="hidden" name="form-name" value="contact">'
        '<p hidden><label>company <input name="company"></label></p><div class="row">'
        '<div class="field"><label for="name">%s</label><input id="name" name="name" type="text" required></div>'
        '<div class="field"><label for="phone">%s</label><input id="phone" name="phone" type="tel" required></div>'
        '</div><div class="field"><label for="email">%s</label>'
        '<input id="email" name="email" type="email"></div>'
        '<div class="field"><label for="message">%s</label>'
        '<textarea id="message" name="message" rows="5" required></textarea></div>'
        '<button class="btn" type="submit">%s</button></form>'
        '<p class="note ok" id="ok" hidden>%s</p>'
        % (e(t(lang, 'ct.name')), e(t(lang, 'cart.phone')), e(t(lang, 'ct.email')),
           e(t(lang, 'ct.msg')), e(t(lang, 'ct.send')), e(t(lang, 'ct.sent'))))

    body = (
        '<div class="pagehead"><div class="wrap">%s<h1>%s</h1><p class="lead">%s</p></div></div>'
        '<div class="wrap"><div class="contact-grid">'
        '<div class="contact-facts">%s</div>'
        '<div class="contact-form"><h2>%s</h2>%s</div></div>'
        '<section class="home-sec"><h2>%s</h2>%s</section></div>'
        % (crumb_html(lang, [(t(lang, 'nav.home'), '/'), (t(lang, 'ct.h1'), '')]),
           e(t(lang, 'ct.h1')), e(t(lang, 'ct.lead')), facts,
           e(t(lang, 'ct.formH')), form, e(t(lang, 'flow.h')), flow))

    title = '%s — Stefsotra %s | %s' % (t(lang, 'ct.h1'), GEO[lang], CONTACT['phone'])
    desc = {'ro': 'Contactează Stefsotra: telefon %s, e-mail %s. Furnizor de furtunuri industriale '
                  'și cauciuc tehnic în Chișinău și în toată Moldova.',
            'ru': 'Свяжитесь с Stefsotra: телефон %s, эл. почта %s. Поставщик промышленных шлангов '
                  'и резинотехнических изделий в Кишинёве и по всей Молдове.',
            'en': 'Contact Stefsotra: phone %s, email %s. Supplier of industrial hoses and '
                  'technical rubber goods in Chișinău and across Moldova.'}[lang] \
           % (CONTACT['phone'], CONTACT['email'])
    return page(lang, '/contact/', title, desc, body,
                jsonld=[org_ld(), crumbs_ld(lang, [(t(lang, 'nav.home'), '/'),
                                                   (t(lang, 'ct.h1'), '/contact/')])],
                current='/contact/')


def build_404():
    lang = 'ro'
    body = ('<div class="wrap" style="padding:60px 20px;text-align:center">'
            '<h1>%s</h1><p class="lead" style="margin:0 auto 22px">%s</p>'
            '<a class="btn" href="/catalog.html">%s</a></div>'
            % (e(t(lang, 'nf.h')), e(t(lang, 'nf.p')), e(t(lang, 'nf.cta'))))
    doc = (head(lang, t(lang, 'nf.h') + ' | Stefsotra', t(lang, 'nf.p'), '/404', noindex=True) +
           header_html(lang).replace('{PATH}', '/') + '<main>' + body + '</main>' +
           footer_html(lang, '/') +
           '<script>window.__CONTACT=%s;</script>' % json.dumps(
               {k: CONTACT.get(k, '') for k in
                ('email', 'phone', 'phone_href', 'address', 'maps')},
               ensure_ascii=False, separators=(',', ':')) +
           '<script src="/assets/js/app.js"></script>'
           '<script src="/assets/js/assistant.js"></script>'
           '<script src="/assets/js/static.js"></script></body></html>')
    with open(os.path.join(ROOT, '404.html'), 'w', encoding='utf-8') as f:
        f.write(doc)


# ---------------------------------------------------------------- main

def main():
    # Wipe previously generated trees so a removed product cannot linger as a live URL.
    for d in ('p', 'c', 'g', 'ru', 'en', 'about', 'delivery', 'partners', 'returns',
              'warranty', 'contact'):
        shutil.rmtree(os.path.join(ROOT, d), ignore_errors=True)

    urls = []
    for lang in LANGS:
        urls.append((build_home(lang), lang, '/'))
        for g in CAT['groups']:
            urls.append((build_group(lang, g), lang, '/g/%s/' % g['key']))
            for c in g['categories']:
                urls.append((build_category(lang, c['key'], c['count']), lang, '/c/%s/' % c['key']))
        for p in CAT['products']:
            urls.append((build_product(lang, p), lang, '/p/%s/' % p['handle']))
        for slug, url in (('about', '/about/'), ('delivery', '/delivery/'),
                          ('partners', '/partners/'), ('returns', '/returns/'),
                          ('warranty', '/warranty/')):
            urls.append((build_content(lang, slug, url), lang, url))
        urls.append((build_contact(lang), lang, '/contact/'))
    build_404()

    # The interactive tools live at one address each, but the header on a Russian page
    # must link to a Russian tool page, so each gets a copy under the language prefix.
    for lang in ('ru', 'en'):
        for tool in ('catalog.html', 'search.html', 'vehicle.html', 'cart.html'):
            src = os.path.join(ROOT, tool)
            dst = os.path.join(ROOT, lang, tool)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)

    # sitemap, with the hreflang set repeated on every entry as Google requires
    by_path = {}
    for loc, lang, path in urls:
        by_path.setdefault(path, {})[lang] = loc
    entries = []
    for path, locs in by_path.items():
        prio = '1.0' if path == '/' else '0.9' if path.startswith('/c/') else \
               '0.8' if path.startswith('/p/') else '0.7'
        for lang, loc in locs.items():
            alts = ''.join('<xhtml:link rel="alternate" hreflang="%s" href="%s"/>' % (l, u)
                           for l, u in locs.items())
            alts += '<xhtml:link rel="alternate" hreflang="x-default" href="%s"/>' % locs['ro']
            entries.append('<url><loc>%s</loc>%s<changefreq>weekly</changefreq>'
                           '<priority>%s</priority></url>' % (loc, alts, prio))
    # the interactive tools, indexable but lower priority
    for tool in ('/catalog.html', '/vehicle.html', '/search.html'):
        entries.append('<url><loc>%s%s</loc><priority>0.6</priority></url>' % (SITE, tool))

    with open(os.path.join(ROOT, 'sitemap.xml'), 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
                'xmlns:xhtml="http://www.w3.org/1999/xhtml">\n' +
                '\n'.join(entries) + '\n</urlset>\n')

    with open(os.path.join(ROOT, 'robots.txt'), 'w', encoding='utf-8') as f:
        f.write('User-agent: *\nAllow: /\n'
                'Disallow: /cart.html\n'
                'Disallow: /*?q=\n\n'
                'Sitemap: %s/sitemap.xml\n' % SITE)

    print('%d pages, %d URLs in the sitemap' % (len(urls), len(entries)))
    print('  %d products x %d languages' % (CAT['count'], len(LANGS)))
    print('  %d categories, %d groups' % (sum(len(g['categories']) for g in CAT['groups']),
                                          len(CAT['groups'])))


if __name__ == '__main__':
    main()
