# Stefsotra — custom storefront

A separate site from the Shopify store. Nothing here touches `stefsotra.md`; it reads the
same product catalogue and presents it with real technical detail, a vehicle finder and a
quotation basket instead of a checkout.

Vanilla HTML, CSS and JavaScript. No framework, no npm install. There is one build step:
a Python script that writes the site out as static HTML.

## Run it locally

```
cd stefsotra-web
python3 -m http.server 8787
```

Open <http://localhost:8787>. It must be served over HTTP, not opened as files.

## How the site is put together

Two kinds of page, on purpose.

**Pre-rendered pages** — home, every category, every group, every product, and the company
pages, in three languages. These are complete HTML: headings, prices, every size, internal
links, structured data. A crawler that runs no JavaScript still reads about 400–2,800 words
per page. JavaScript then attaches the basket and the assistant to the page that is already
there; it does not redraw anything, and it does not download the 395 KB catalogue.

**Interactive pages** — `catalog.html` (filters), `search.html`, `vehicle.html`, `cart.html`.
These need to react to input, so they are drawn in the browser and do fetch the catalogue.

```
/                       /ru/                /en/              home
/c/<category>/          17 categories                         category listing
/g/<group>/             5 groups                              group landing
/p/<handle>/            114 products                          product
/about/ /delivery/ /partners/ /returns/ /warranty/ /contact/   company
/catalog.html /search.html /vehicle.html /cart.html            tools
```

429 pre-rendered pages in total.

## Building

```
python3 scripts/build_catalogue.py --offline   # data/products.json from the cached feed
python3 scripts/build_catalogue.py             # ...or refetch from the live store
python3 scripts/build_vehicles.py              # vehicle tree (slow, ~10 min)
python3 scripts/build_static.py                # THE SITE — run this after any of the above
```

`build_static.py` deletes and rewrites `/p`, `/c`, `/g`, `/ru`, `/en` and the company page
folders, so a withdrawn product cannot survive as a live URL. **Run it after editing
`data/pages.json`, `data/reviews.json` or any `i18n/*.json`** — those files feed the
pre-rendered HTML, and editing them alone changes nothing that a visitor sees.

`build_catalogue.py` fails loudly: it prints any product it could not categorise and counts
variant sizes it could not parse. Both should be zero.

## SEO

What is in place:

- **Real HTML for crawlers.** This is the one that matters. Everything below is wasted if
  the page is an empty `<div>`, which is what it was before this build step existed.
- **A separate URL per language** with a full `hreflang` set (ro / ru / en / x-default) on
  all 429 pages and in the sitemap, so Google serves the Russian page to a Russian searcher
  instead of picking one and treating the rest as duplicates.
- **Structured data**: Organization, WebSite with SearchAction, Product with AggregateOffer
  in MDL, ItemList on category pages, BreadcrumbList everywhere, FAQPage on delivery,
  returns and warranty.
- **Titles and descriptions** written per page from real figures — product count, size
  count, lowest price, city — rather than one template repeated 400 times.
- **Every size in the HTML.** People search "furtun silicon 38 mm", so all 957 variant
  sizes are written out as text, not left inside a `<select>`.
- Canonical tags, Open Graph and Twitter cards, `sitemap.xml`, `robots.txt`, a 404 page,
  301 redirects from the old Shopify `/pages/...` and `/products/...` addresses, image
  `width`/`height` to stop layout shift, and about 107 KB of page weight before images.

What this cannot do, and it is worth being straight about it: ranking first for "rubber
products in Moldova" is not something a website alone decides. The technical side is now as
good as it reasonably gets. The rest is off-page and needs you:

1. **Google Business Profile** — free, and for local trade searches it usually outranks
   everything else on the page. It needs the street address.
2. **The address.** `data/pages.json` → `_contact.address` is still empty because nothing
   on stefsotra.md publishes one. Consistent name/address/phone across the site, Google,
   and directories is a large part of local ranking.
3. **Search Console and Yandex Webmaster** — submit `sitemap.xml` to both. Yandex is a
   significant share of Russian-language search here.
4. **Which domain.** `SITE` at the top of `build_static.py` says `https://stefsotra.md`. If
   this site goes live somewhere else, change it and rebuild, or every canonical tag will
   point at the old store.
5. **Links from real Moldovan sites** — suppliers, trade directories, customers. This is
   the slowest part and the one competitors cannot copy.
6. **Descriptions in Romanian and Russian.** See below.

## Prices

Whole Moldovan lei, in all three languages. The Shopify feed quotes USD, so the build
converts using `MDL_PER_FEED_USD` in `scripts/build_catalogue.py`. That number is not a
currency rate — it is the measured ratio between the feed price and the supplier sheet
price, checked over 72 variants across three silicone families (spread 0.25%). If Shopify's
prices change, re-derive it the same way rather than adjusting it by feel.

## Deploying

Drop the folder on Netlify. `netlify.toml` is already set up. Three things then work that
cannot work locally:

**Orders, messages and reviews.** The basket, the contact form and the review form post to
Netlify Forms. Each submission is emailed and kept in Netlify → Forms. No backend, no
payment: a customer sends a request, you contact them about fulfilment.

**The AI assistant.** Set `ANTHROPIC_API_KEY` in Site settings → Environment variables.
Until you do, the endpoint returns 501 and the site says plainly that the assistant is not
switched on. Search keeps working regardless — it also has a rule-based reader that handles
sizes, angles, materials and product words in Romanian, Russian and English.

The key stays server-side in `netlify/functions/assistant.js`. The assistant is given
`data/index.txt` and told to recommend only what is in it, and the products it names are
rendered from our own catalogue rather than from its text, so it cannot show an invented
price.

## Before this goes live

- **Street address** — see above. One line in `data/pages.json`, then rebuild.
- **Reviews.** `data/reviews.json` ships empty on purpose. Star ratings here show real
  customer reviews and nothing else: publishing invented ones is illegal in the EU under
  the Omnibus Directive and prohibited under Moldovan consumer-protection law, and Google's
  structured-data policy treats fake review markup as spam. The form is live; read
  submissions in Netlify → Forms → `product-review`, paste the ones you want to publish
  into that file, and rebuild.
- **Product descriptions** are still whatever Shopify holds — mostly English, the camlock
  copy Russian. The interface is fully translated; the descriptions are not. This is the
  biggest remaining SEO gap: a Romanian description on a Romanian page ranks for Romanian
  searches, and machine-translating 114 technical specifications would produce
  confident-sounding wrong numbers, so it is worth doing by hand.
- **Photography.** Six products have no image; see `../import/PHOTOS_NEEDED.csv`.
- **Policy wording** in `data/pages.json` is translated from the Russian on the current
  site. Have someone confirm it before relying on it.

## Testing

Checked in a headless browser, twice over: once with JavaScript disabled, to see what a
crawler sees, and once normally. All 21 sampled pages pass both — no JavaScript errors, no
untranslated keys on screen, no dollar price anywhere, one header and one footer per page,
no horizontal overflow at 360 px. The interaction path — pick a size, add from a product
page and from a category tile, check the basket total, switch language, sort and filter the
catalogue, run the vehicle finder — passes end to end.
