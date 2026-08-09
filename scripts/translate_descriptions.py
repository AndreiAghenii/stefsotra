"""Romanian and Russian product descriptions, translated and then verified.

The problem
-----------
The 114 descriptions are 145,000 characters of real prose, not templates, so the
term-substitution trick used for the titles would produce broken grammar. They have to
be translated properly. But they are full of specifications -- "-50°C to +200°C",
"1.6 MPa", "5 mm wall", "DIN 14301" -- and a translation that quietly changes 1.6 to 16,
or drops a minus sign, is worse than leaving the text in English. A customer would buy
the wrong part on the strength of it.

The approach
------------
Translate with the model, then check the translation mechanically:

  * every number in the source must appear the same number of times in the translation
  * every unit and standard code (MPa, °C, mm, bar, DIN 14301, EPDM, NBR, PA6, DN40)
    must survive with the same count
  * the translation must not be suspiciously shorter or longer than the source

Anything that fails is NOT published. It is written to data/_translation_review.json for
a person to look at, and the site falls back to the original text for that product. So
the worst case is an English description, never a wrong number.

    export ANTHROPIC_API_KEY=sk-ant-...
    python3 scripts/translate_descriptions.py --check          # verify existing work
    python3 scripts/translate_descriptions.py --lang ro        # translate, dry run
    python3 scripts/translate_descriptions.py --lang ro --write
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, 'data')
MODEL = 'claude-sonnet-5'

LANG_NAME = {'ro': 'Romanian', 'ru': 'Russian'}

SYSTEM = """
You translate product descriptions for a Moldovan supplier of industrial hoses,
couplings and technical rubber goods, from English into {lang}.

These are specifications a tradesperson buys parts from. Accuracy outranks style.

ABSOLUTE RULES
- Reproduce every number exactly as written: 1.6 stays 1.6, -50 keeps its minus sign,
  102*102 keeps its form. Never round, never convert, never reorder.
- Keep every unit and standard exactly as written and in the same place: mm, MPa, bar,
  °C, DN40, DIN 14301, DIN 28450, NF E 29-573, EPDM, NBR, PA6, UL 94.
- Keep brand and type names in Latin script: Camlock, Storz, Guillemin, Bauer, KAMAZ,
  MAZ, Mercedes Sprinter, Stefsotra, and type letters such as Type A, Type DP.
- Keep the HTML tags and their order exactly. Translate only the text between them.
- Do not add, remove or soften any claim. If the source does not say it, it is not there.
- Do not add a preamble or a note. Output only the translated HTML.

Write the way a Moldovan trade catalogue writes: plain, direct, no marketing filler.
""".strip()

# What must survive translation untouched.
NUM = re.compile(r'-?\d+(?:[.,]\d+)?')
UNIT = re.compile(r'\b(?:mm|cm|m|MPa|bar|kg|g|DN\s*\d+|°\s*C|°|'
                  r'DIN\s*\d+|NF\s*E\s*[\d-]+|UL\s*94|EPDM|NBR|PA6|PVC|ABS)\b', re.I)


def signature(html):
    """The facts that must be identical before and after translation."""
    text = re.sub(r'<[^>]+>', ' ', html or '')
    nums = sorted(n.replace(',', '.') for n in NUM.findall(text))
    units = sorted(u.upper().replace(' ', '') for u in UNIT.findall(text))
    tags = re.findall(r'</?([a-zA-Z0-9]+)', html or '')
    return nums, units, tags


def verify(src, out):
    """Return a list of reasons the translation must not be published."""
    problems = []
    s_num, s_unit, s_tag = signature(src)
    o_num, o_unit, o_tag = signature(out)
    if s_num != o_num:
        missing = [n for n in s_num if n not in o_num]
        added = [n for n in o_num if n not in s_num]
        problems.append('numbers differ' +
                        (f' (missing {missing[:6]})' if missing else '') +
                        (f' (added {added[:6]})' if added else ''))
    if s_unit != o_unit:
        problems.append(f'units differ: {sorted(set(s_unit) ^ set(o_unit))[:6]}')
    if s_tag != o_tag:
        problems.append(f'HTML structure differs: {len(s_tag)} tags in, {len(o_tag)} out')
    s_len, o_len = len(re.sub(r'<[^>]+>', '', src)), len(re.sub(r'<[^>]+>', '', out))
    if s_len and not (0.55 <= o_len / s_len <= 1.9):
        problems.append(f'length {o_len} vs {s_len} — text likely dropped or padded')
    return problems


def call(key, system, text):
    body = json.dumps({
        'model': MODEL, 'max_tokens': 4000, 'system': system,
        'messages': [{'role': 'user', 'content': text}],
    }).encode('utf-8')
    req = urllib.request.Request(
        'https://api.anthropic.com/v1/messages', data=body,
        headers={'content-type': 'application/json', 'x-api-key': key,
                 'anthropic-version': '2023-06-01'})
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read().decode('utf-8'))
    return ''.join(c['text'] for c in d.get('content', []) if c.get('type') == 'text').strip()


def main():
    args = sys.argv[1:]
    lang = args[args.index('--lang') + 1] if '--lang' in args else None
    write = '--write' in args
    path = os.path.join(DATA, 'products.json')
    cat = json.load(open(path, encoding='utf-8'))

    if '--check' in args:
        bad = ok = missing = 0
        for p in cat['products']:
            for l in ('ro', 'ru'):
                t = p.get('body_' + l)
                if not t:
                    missing += 1
                    continue
                if verify(p['body_html'], t):
                    bad += 1
                else:
                    ok += 1
        print(f'verified {ok}, failed {bad}, not translated {missing}')
        return

    if lang not in LANG_NAME:
        print(__doc__)
        return

    key = os.environ.get('ANTHROPIC_API_KEY')
    if not key:
        print('ANTHROPIC_API_KEY is not set.\n'
              'This is the same key the assistant uses, so setting it once covers both.\n'
              '  export ANTHROPIC_API_KEY=sk-ant-...')
        return

    system = SYSTEM.format(lang=LANG_NAME[lang])
    todo = [p for p in cat['products'] if p['body_html'] and not p.get('body_' + lang)]
    print(f'{len(todo)} descriptions to translate into {LANG_NAME[lang]}\n')

    review, done, failed = [], 0, 0
    for i, p in enumerate(todo, 1):
        try:
            out = call(key, system, p['body_html'])
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            print(f'  [{i}/{len(todo)}] {p["handle"][:34]:<34} REQUEST FAILED: {e}')
            failed += 1
            time.sleep(3)
            continue

        problems = verify(p['body_html'], out)
        if problems:
            failed += 1
            review.append({'handle': p['handle'], 'lang': lang,
                           'problems': problems, 'source': p['body_html'], 'translation': out})
            print(f'  [{i}/{len(todo)}] {p["handle"][:34]:<34} HELD BACK: {"; ".join(problems)}')
        else:
            p['body_' + lang] = out
            done += 1
            print(f'  [{i}/{len(todo)}] {p["handle"][:34]:<34} ok')
        time.sleep(0.4)

    print(f'\n{done} verified and kept, {failed} held back for review')
    if review:
        rp = os.path.join(DATA, '_translation_review.json')
        json.dump(review, open(rp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(f'held-back translations written to {rp}')
        print('Those products keep their original description until someone checks them.')

    if write and done:
        json.dump(cat, open(path, 'w', encoding='utf-8'),
                  ensure_ascii=False, separators=(',', ':'))
        print(f'\nwritten to {path}')
        print('Now run: python3 scripts/build_static.py')
    elif done:
        print('\n(dry run — pass --write to save)')


if __name__ == '__main__':
    main()
