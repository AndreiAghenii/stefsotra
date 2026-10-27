"""The authored translations, kept outside the generated catalogue.

The problem this solves
-----------------------
data/products.json is rebuilt from the Shopify feed every time build_catalogue.py runs,
and that rebuild was total: it never read the file it was replacing. Everything in there
that the feed does not provide -- the 390 titles translate_titles.py had written
(title_ro, title_ru, title_en), the descriptions translate_descriptions.py writes
(body_ro, body_ru), and the img_sig image signatures -- was destroyed by any routine
refresh for new stock or a price change. Nothing would fail; the Romanian and Russian
pages would just quietly start showing English names again.

The translations therefore live here instead, keyed by product handle, and
build_catalogue.py merges them back into the catalogue it builds.

Provenance
----------
Each translation records a hash of the exact English text it was made from. If Shopify
later changes that text, the stored translation is NOT merged: a confident Romanian
sentence describing the previous revision of a spec is worse than the English, because
somebody orders a part from it. Those are reported as stale so they can be redone, and
until then the page falls back to the source text.
"""
import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), 'data')
PATH = os.path.join(DATA, 'translations.json')

# The fields the Shopify feed does not provide, by the source field they translate.
KINDS = {'title': 'title', 'body': 'body_html'}
LANGS = {'title': ('ro', 'ru', 'en'), 'body': ('ro', 'ru')}


def src_hash(text):
    return hashlib.sha1((text or '').encode('utf-8')).hexdigest()


def load():
    if not os.path.exists(PATH):
        return {}
    with open(PATH, encoding='utf-8') as f:
        return json.load(f)


def save(store):
    with open(PATH, 'w', encoding='utf-8') as f:
        json.dump(store, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write('\n')


def record(store, handle, kind, lang, source_text, translation):
    """Store one translation against the source it was made from."""
    assert kind in KINDS, kind
    entry = store.setdefault(handle, {})
    slot = entry.setdefault(kind, {})
    slot[lang] = translation
    entry[kind + '_src'] = src_hash(source_text)


def merge_into(products, store=None):
    """Put the stored translations back on the freshly built products.

    Returns (carried, stale, missing): how many fields were restored, how many were
    skipped because the English has changed since, and how many handles in the store no
    longer exist in the catalogue.
    """
    store = load() if store is None else store
    carried = stale = 0
    handles = {p['handle'] for p in products}
    for p in products:
        entry = store.get(p['handle'])
        if not entry:
            continue
        for kind, src_field in KINDS.items():
            slot = entry.get(kind)
            if not slot:
                continue
            if entry.get(kind + '_src') != src_hash(p.get(src_field)):
                stale += len([l for l in LANGS[kind] if slot.get(l)])
                continue
            for lang in LANGS[kind]:
                if slot.get(lang):
                    p['%s_%s' % (kind, lang)] = slot[lang]
                    carried += 1
    return carried, stale, len(set(store) - handles)


def stale_report(products, store=None):
    """The handles whose English text has changed since it was translated."""
    store = load() if store is None else store
    out = []
    for p in products:
        entry = store.get(p['handle'])
        if not entry:
            continue
        for kind, src_field in KINDS.items():
            if entry.get(kind) and entry.get(kind + '_src') != src_hash(p.get(src_field)):
                out.append((p['handle'], kind))
    return out
