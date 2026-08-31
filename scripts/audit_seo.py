#!/usr/bin/env python3
"""Reads the built site the way a crawler would and fails on anything that would cost a
ranking. Run it after scripts/build_static.py; it touches nothing and exits non-zero when
it finds a problem, so it can sit in front of a deploy.

What it checks, and why each one is here rather than in a list of general advice:

  * every page has a title, a description, a robots tag and a canonical, and that
    canonical is the page's own address -- the catalogue/search/vehicle/cart pages once
    shipped as byte-identical copies at /, /ru/ and /en/ with no canonical at all
  * no two indexable pages claim the same canonical
  * the hreflang set is four links and names the page itself, which is what Google needs
    before it will serve the Russian page to a Russian searcher
  * titles fit in 70 characters and descriptions in 165, measured after HTML unescaping,
    because that is what a result actually shows
  * exactly one h1 per page, counting the markup and not the scripts -- seven Camlock
    descriptions arrived from Shopify with an h1 of their own inside the manufacturer copy
  * every JSON-LD block parses
  * the header and footer are in the HTML, not assembled by JavaScript afterwards
  * the sitemap points only at files that exist, and every indexable page is in it
"""
import collections
import glob
import html
import json
import os
import re
import sys

SITE = 'https://stefsotra.md'
SKIP_DIRS = ('assets/', 'templates/', 'netlify/', 'photos_in/', 'node_modules/')
TITLE_MAX, DESC_MAX = 70, 165
DESC_MIN = 60


def find(s, pat):
    m = re.search(pat, s)
    return html.unescape(m.group(1)) if m else None


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root)
    files = [f for f in glob.glob('**/*.html', recursive=True)
             if not f.startswith(SKIP_DIRS) and f != '404.html']
    bad = collections.defaultdict(list)
    canons, indexable = {}, set()

    for f in files:
        s = open(f, encoding='utf-8').read()
        title = find(s, r'<title>(.*?)</title>')
        desc = find(s, r'<meta name="description" content="(.*?)">')
        canon = find(s, r'<link rel="canonical" href="(.*?)">')
        robots = find(s, r'<meta name="robots" content="(.*?)">')

        if not title:
            bad['no title'].append(f)
        elif len(title) > TITLE_MAX:
            bad['title over %d chars' % TITLE_MAX].append('%s (%d)' % (f, len(title)))
        if not desc:
            bad['no description'].append(f)
        elif not DESC_MIN <= len(desc) <= DESC_MAX:
            bad['description outside %d-%d' % (DESC_MIN, DESC_MAX)].append(
                '%s (%d)' % (f, len(desc)))
        if not robots:
            bad['no robots tag'].append(f)
        if not canon:
            bad['no canonical'].append(f)
        else:
            want = SITE + '/' + (f[:-len('index.html')] if f.endswith('index.html') else f)
            if canon.rstrip('/') != want.rstrip('/'):
                bad['canonical is not the page itself'].append('%s -> %s' % (f, canon))
            if canon in canons:
                bad['two pages share a canonical'].append('%s / %s' % (canons[canon], f))
            canons[canon] = f

        alts = re.findall(r'hreflang="[a-z-]+" href="([^"]+)"', s)
        if len(alts) != 4:
            bad['hreflang set is not 4 links'].append('%s (%d)' % (f, len(alts)))
        elif canon and canon not in alts:
            bad['hreflang set omits the page itself'].append(f)

        for blk in re.findall(r'<script type="application/ld\+json">(.*?)</script>', s, re.S):
            try:
                json.loads(blk)
            except ValueError as ex:
                bad['JSON-LD does not parse'].append('%s: %s' % (f, ex))

        # count headings in the markup only: the pages that draw themselves carry '<h1>'
        # inside a JavaScript string, and that is not a heading on the page.
        n = re.sub(r'<script.*?</script>', '', s, flags=re.S).count('<h1')
        if n != 1:
            bad['not exactly one h1'].append('%s (%d)' % (f, n))
        if '<header class="site"' not in s:
            bad['header is not in the HTML'].append(f)
        if '<footer class="site"' not in s:
            bad['footer is not in the HTML'].append(f)
        if robots and 'noindex' not in robots:
            indexable.add(f)

    sitemap = open('sitemap.xml', encoding='utf-8').read()
    locs = re.findall(r'<loc>(.*?)</loc>', sitemap)
    if len(locs) != len(set(locs)):
        bad['the same URL twice in the sitemap'].append('yes')
    listed = set()
    for u in locs:
        rel = u[len(SITE):].lstrip('/')
        path = rel if rel.endswith('.html') else os.path.join(rel, 'index.html')
        if not os.path.exists(path):
            bad['sitemap URL with no file behind it'].append(u)
        else:
            listed.add(path)
    for f in sorted(indexable - listed):
        bad['indexable page missing from the sitemap'].append(f)

    print('%d pages checked, %d in the sitemap' % (len(files), len(locs)))
    if not bad:
        print('no problems found')
        return 0
    for k in sorted(bad):
        v = bad[k]
        print('  %-42s %4d  %s' % (k, len(v), '; '.join(v[:3])[:140]))
    return 1


if __name__ == '__main__':
    sys.exit(main())
