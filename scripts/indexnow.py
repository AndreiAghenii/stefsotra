"""Tell Bing and Yandex which pages changed, through IndexNow.

Why this exists
---------------
Google is not the only engine that matters here. Yahoo's results are served from Bing,
and Yandex carries real weight for Russian-language search in Moldova. Both support
IndexNow: you host a key file and POST the URLs that changed, and they fetch them
instead of waiting for a crawl. Seznam and Naver use the same endpoint. Google does not
participate, and the old "ping the sitemap" endpoints were withdrawn in 2023, so for
Google the sitemap plus a crawl is still the route.

Be clear about what this does: it speeds up *indexing*, not ranking. A page that gets
crawled tomorrow instead of in three weeks starts earning whatever it was going to earn
sooner. It does not make a page rank better than it deserves.

Setup, once
-----------
    python3 scripts/indexnow.py --new-key      # writes the key into data/indexnow.json
    python3 scripts/build_static.py            # publishes <key>.txt at the site root
    git commit && push                         # the key file has to be live first

Then, after any deploy that changed pages:

    python3 scripts/indexnow.py                # submit what lastmod says changed
    python3 scripts/indexnow.py --all          # submit every indexable URL
    python3 scripts/indexnow.py --dry-run      # print the payload, send nothing

The key file must already be reachable at https://www.stefsotra.md/<key>.txt or the
engines reject the submission, so always deploy before submitting.
"""
import json
import os
import re
import secrets
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, 'data')
KEYFILE = os.path.join(DATA, 'indexnow.json')
ENDPOINT = 'https://api.indexnow.org/indexnow'
# One host per submission, and the engines cap a batch at 10 000 URLs.
BATCH = 10000


def site():
    """The canonical host, read from the builder so there is one source of truth."""
    src = open(os.path.join(HERE, 'build_static.py'), encoding='utf-8').read()
    m = re.search(r"^SITE = '([^']+)'", src, re.M)
    if not m:
        raise SystemExit('could not read SITE from build_static.py')
    return m.group(1)


def load_key():
    if not os.path.exists(KEYFILE):
        return None
    with open(KEYFILE, encoding='utf-8') as f:
        return (json.load(f).get('key') or '').strip() or None


def new_key():
    # IndexNow wants 8-128 characters, a-z A-Z 0-9 and dashes only.
    key = secrets.token_hex(16)
    with open(KEYFILE, 'w', encoding='utf-8') as f:
        json.dump({'key': key,
                   '_note': 'Published at /<key>.txt by build_static.py. Changing this '
                            'key means the old key file stops matching, so only change '
                            'it deliberately.'}, f, indent=1)
        f.write('\n')
    print('key written to %s' % KEYFILE)
    print('  %s' % key)
    print('Now run build_static.py, then commit and deploy so %s/%s.txt is live.'
          % (site(), key))
    return key


def sitemap_urls():
    path = os.path.join(ROOT, 'sitemap.xml')
    if not os.path.exists(path):
        raise SystemExit('no sitemap.xml -- run scripts/build_static.py first')
    with open(path, encoding='utf-8') as f:
        return re.findall(r'<loc>([^<]+)</loc>', f.read())


def changed_urls():
    """URLs whose lastmod is the newest date in the store.

    data/lastmod.json holds {url: {d: date, h: hash}} and build_static.py only moves a
    date when that page's HTML actually changed, so the newest date is the set of pages
    the last build touched.
    """
    path = os.path.join(DATA, 'lastmod.json')
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        store = json.load(f)
    if not store:
        return []
    newest = max(v.get('d', '') for v in store.values())
    changed = {u for u, v in store.items() if v.get('d') == newest}
    # lastmod tracks every page that is written, including the noindex ones (the basket,
    # the search page, 404). There is no point asking an engine to index a page that
    # tells it not to, so the set is narrowed to what the sitemap actually offers.
    indexable = set(sitemap_urls())
    return sorted(changed & indexable), newest


def submit(host, key, urls, dry_run=False):
    payload = {'host': host, 'key': key,
               'keyLocation': 'https://%s/%s.txt' % (host, key),
               'urlList': urls}
    body = json.dumps(payload).encode('utf-8')
    if dry_run:
        print(json.dumps({**payload, 'urlList': urls[:5] +
                          (['... %d more' % (len(urls) - 5)] if len(urls) > 5 else [])},
                         indent=1, ensure_ascii=False))
        return None
    req = urllib.request.Request(ENDPOINT, data=body,
                                 headers={'Content-Type': 'application/json; charset=utf-8'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status
    except urllib.error.HTTPError as err:
        # 403 means the key file is not reachable; 422 means the URLs do not match host.
        print('rejected: HTTP %s %s' % (err.code, err.reason))
        print(err.read().decode('utf-8', 'replace')[:300])
        return err.code
    except urllib.error.URLError as err:
        print('could not reach %s: %s' % (ENDPOINT, err.reason))
        return None


def main():
    if '--new-key' in sys.argv:
        new_key()
        return
    key = load_key()
    if not key:
        raise SystemExit('no key yet -- run: python3 scripts/indexnow.py --new-key')
    base = site()
    host = re.sub(r'^https?://', '', base).strip('/')

    if '--all' in sys.argv:
        urls, label = sitemap_urls(), 'every indexable URL'
    else:
        urls, newest = changed_urls()
        label = 'changed on %s' % newest
        if not urls:
            print('nothing to submit')
            return

    # Anything not on the canonical host would be refused for the whole batch.
    off = [u for u in urls if not u.startswith(base)]
    if off:
        raise SystemExit('%d URL(s) are not on %s, e.g. %s' % (len(off), base, off[0]))

    print('%d URL(s) to submit (%s) for %s' % (len(urls), label, host))
    dry = '--dry-run' in sys.argv
    for i in range(0, len(urls), BATCH):
        chunk = urls[i:i + BATCH]
        status = submit(host, key, chunk, dry_run=dry)
        if dry:
            continue
        if status in (200, 202):
            print('  submitted %d URL(s) -- accepted (%s)' % (len(chunk), status))
        else:
            print('  %d URL(s) NOT accepted' % len(chunk))
            raise SystemExit(1)
    if dry:
        print('\n(dry run -- nothing sent)')


if __name__ == '__main__':
    main()
