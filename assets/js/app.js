/* Shared core: data loading, i18n, cart, formatting, header.
   No framework and no build step -- this has to stay editable by someone who is not
   a developer. Everything hangs off window.S. */
(function () {
  'use strict';

  var LANGS = ['ro', 'ru', 'en'];
  var LS_LANG = 'stefsotra.lang';
  var LS_CART = 'stefsotra.cart';

  var S = window.S = {
    lang: 'ro',
    t: {},
    catalogue: null,
    vehicles: null,
    fitment: null,
    pages: null
  };

  /* ------------------------------------------------------------------ i18n */

  // Language is decided by the URL: / is Romanian, /ru/ and /en/ are the others. Each
  // language therefore has its own indexable address, which is what lets Google serve
  // the Russian page to a Russian searcher instead of treating it as a duplicate.
  // localStorage only carries the preference across to the interactive pages, which
  // live at a single URL.
  //
  // Romanian is the default for everyone. The browser language is deliberately not
  // consulted: this is a Moldovan shop, and a visitor arriving with an English browser
  // should still land on the state language until they choose otherwise.
  S.detectLang = function () {
    var m = location.pathname.match(/^\/(ru|en)(\/|$)/);
    if (m) return m[1];
    var saved = localStorage.getItem(LS_LANG);
    return (saved && LANGS.indexOf(saved) >= 0) ? saved : 'ro';
  };

  // The same page in another language: strip any prefix, then add the new one.
  S.langUrl = function (lang) {
    var p = location.pathname.replace(/^\/(ru|en)(?=\/|$)/, '') || '/';
    return (lang === 'ro' ? '' : '/' + lang) + p + location.search;
  };

  // Every internal link goes through here so the language prefix is never dropped.
  S.url = function (path) {
    return (S.lang === 'ro' ? '' : '/' + S.lang) + path;
  };

  S.setLang = function (lang) {
    localStorage.setItem(LS_LANG, lang);
    var url = S.langUrl(lang);
    if (url === location.pathname + location.search) location.reload();
    else location.href = url;
  };

  // Translate. Missing keys return the key itself so gaps are visible rather than blank.
  S.t = function (key, vars) {
    var s = (S.strings && S.strings[key]) != null ? S.strings[key] : key;
    if (vars) Object.keys(vars).forEach(function (k) {
      s = s.replace('{' + k + '}', vars[k]);
    });
    return s;
  };

  S.applyStatic = function (root) {
    (root || document).querySelectorAll('[data-t]').forEach(function (el) {
      el.textContent = S.t(el.getAttribute('data-t'));
    });
    (root || document).querySelectorAll('[data-t-ph]').forEach(function (el) {
      el.setAttribute('placeholder', S.t(el.getAttribute('data-t-ph')));
    });
  };

  // Category and group names live in the i18n files under cat.* / grp.*, so a category
  // key that has no translation yet still renders as something readable.
  S.catLabel = function (key) {
    var s = S.t('cat.' + key);
    return s === 'cat.' + key ? key.replace(/-/g, ' ') : s;
  };
  S.groupLabel = function (key) {
    var s = S.t('grp.' + key);
    return s === 'grp.' + key ? key : s;
  };

  /* ------------------------------------------------------------------ data */

  function json(url) {
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error(url + ' -> ' + r.status);
      return r.json();
    });
  }

  // Loads only what a page asks for, so the vehicle tree isn't fetched on the cart page.
  S.load = function (what) {
    S.lang = S.detectLang();
    document.documentElement.lang = S.lang;
    var jobs = [json('/i18n/' + S.lang + '.json').then(function (d) { S.strings = d; })];
    // The JS-rendered pages build their menu from the catalogue's group index and their
    // footer from the contact block, so they need both whatever else they asked for. The
    // pre-rendered pages already have menu and footer in their HTML and skip this.
    if (!S.prerendered) ['catalogue', 'pages'].forEach(function (k) {
      if (what.indexOf(k) < 0) what = what.concat([k]);
    });
    if (what.indexOf('catalogue') >= 0)
      jobs.push(json('/data/products.json').then(function (d) { S.catalogue = d; }));
    if (what.indexOf('reviews') >= 0)
      jobs.push(json('/data/reviews.json').then(function (d) { S.reviews = d; })
                .catch(function () { S.reviews = { products: {} }; }));
    if (what.indexOf('vehicles') >= 0)
      jobs.push(json('/data/vehicles.json').then(function (d) { S.vehicles = d; }));
    if (what.indexOf('fitment') >= 0)
      jobs.push(json('/data/fitment.json').then(function (d) { S.fitment = d; }));
    if (what.indexOf('pages') >= 0)
      jobs.push(json('/data/pages.json').then(function (d) { S.pages = d; }));
    return Promise.all(jobs);
  };

  // Fetched once, only when something actually needs the full catalogue.
  var catPromise = null;
  S.ensureCatalogue = function () {
    if (S.catalogue) return Promise.resolve(S.catalogue);
    if (!catPromise) catPromise = json('/data/products.json').then(function (d) {
      S.catalogue = d; return d;
    });
    return catPromise;
  };

  // Where every request goes. The value comes from data/pages.json; the pre-rendered
  // pages carry it inline as window.__CONTACT because they never fetch that file. The
  // literal is only a last resort so a form can never lose its destination.
  S.contact = function () {
    return (window.__CONTACT) || S.pagesContact ||
           { email: 'stefsotra@mail.ru', phone: '+373 (22) 55-39-54', phone_href: '+37322553954' };
  };

  // A mailto with the whole request already written out. This is the fallback when
  // Netlify is unreachable, and a visible option in its own right -- some customers
  // would simply rather send an email.
  S.mailto = function (subject, body) {
    return 'mailto:' + S.contact().email +
      '?subject=' + encodeURIComponent(subject) +
      '&body=' + encodeURIComponent(body);
  };

  S.byHandle = function (handle) {
    if (!S.catalogue) return null;
    return S.catalogue.products.filter(function (p) { return p.handle === handle; })[0];
  };

  /* ------------------------------------------------------------------ cart
     Held in localStorage. This is a request for quotation, so there is no
     payment, no stock reservation and no server round-trip until submit. */

  S.cart = {
    read: function () {
      try { return JSON.parse(localStorage.getItem(LS_CART)) || []; }
      catch (e) { return []; }
    },
    write: function (items) {
      localStorage.setItem(LS_CART, JSON.stringify(items));
      S.cart.paint();
      window.dispatchEvent(new CustomEvent('cart:change'));
    },
    add: function (handle, variantTitle, qty) {
      var items = S.cart.read();
      var hit = items.filter(function (i) {
        return i.handle === handle && i.variant === variantTitle;
      })[0];
      if (hit) hit.qty += (qty || 1);
      else items.push({ handle: handle, variant: variantTitle, qty: qty || 1 });
      S.cart.write(items);
    },
    setQty: function (idx, qty) {
      var items = S.cart.read();
      if (!items[idx]) return;
      if (qty <= 0) items.splice(idx, 1); else items[idx].qty = qty;
      S.cart.write(items);
    },
    remove: function (idx) {
      var items = S.cart.read();
      items.splice(idx, 1);
      S.cart.write(items);
    },
    clear: function () { S.cart.write([]); },
    count: function () {
      return S.cart.read().reduce(function (n, i) { return n + i.qty; }, 0);
    },
    paint: function () {
      var n = S.cart.count();
      document.querySelectorAll('[data-cart-badge]').forEach(function (el) {
        el.textContent = n;
        el.style.display = n ? '' : 'none';
      });
    }
  };

  /* ------------------------------------------------------------------ format */

  // Prices are whole Moldovan lei -- see MDL_PER_FEED_USD in build_catalogue.py for
  // how they are derived. Thousands are spaced, which is the local convention, and the
  // currency label is the same in all three languages: these are Moldovan lei. `unit`
  // appends /m for the products cut from a roll -- see UNIT_BY_CATEGORY in
  // build_catalogue.py for which categories those are.
  S.money = function (n, unit) {
    // A product with no price says so. "0 lei" reads as free.
    if (!Number(n)) return S.t('prod.onRequest');
    return Math.round(Number(n)).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ') + ' lei' +
           (unit === 'm' ? S.t('unit.m') : '');
  };

  // Human-readable dimensions, e.g. "Ø38 mm · aluminium" or "50 → 32 mm".
  S.dimLabel = function (dims) {
    if (!dims || dims.default) return '';
    var bits = [];
    if (dims.id_mm != null && dims.id2_mm != null) bits.push('Ø' + dims.id_mm + ' → ' + dims.id2_mm + ' mm');
    else if (dims.id_mm != null) bits.push('Ø' + dims.id_mm + ' mm');
    if (dims.clamp_min != null) bits.push(dims.clamp_min + '–' + dims.clamp_max + ' mm');
    if (dims.dn != null) bits.push('DN' + dims.dn);
    if (dims.thread) bits.push(dims.thread);
    if (dims.oe) bits.push('OE ' + dims.oe);
    if (dims.material) bits.push(dims.material);
    if (dims.group) bits.unshift(dims.group);
    if (dims.designation) bits.push(dims.designation);
    if (!bits.length && dims.raw && !dims.default) bits.push(dims.raw);
    return bits.join(' · ');
  };

  // The range of sizes a product covers, for the catalogue tile.
  S.rangeLabel = function (p) {
    var ids = p.variants.map(function (v) { return v.dims.id_mm; })
                        .filter(function (x) { return x != null; });
    var out = [];
    if (ids.length) {
      var lo = Math.min.apply(null, ids), hi = Math.max.apply(null, ids);
      out.push(lo === hi ? 'Ø' + lo + ' mm' : 'Ø' + lo + '–' + hi + ' mm');
    }
    if (p.attrs.angle) out.push(p.attrs.angle + '°');
    if (p.variants.length > 1) out.push(p.variants.length + '×');
    return out.join(' · ');
  };

  // Drawn stand-in for a product with no photograph -- see placeholder() in
  // build_static.py for why this is never another product's picture.
  var PH_ART = {"hoses": "<path d=\"M14 34c0-9 7-16 16-16h20c9 0 16 7 16 16v12c0 9-7 16-16 16H30c-9 0-16-7-16-16z\"/><path d=\"M14 40h56M22 24v32M58 24v32\"/>", "couplings": "<circle cx=\"40\" cy=\"40\" r=\"22\"/><circle cx=\"40\" cy=\"40\" r=\"12\"/><path d=\"M18 40h-8M70 40h-8M40 18v-8M40 70v-8\"/>", "sealing": "<circle cx=\"40\" cy=\"40\" r=\"24\"/><circle cx=\"40\" cy=\"40\" r=\"17\"/><path d=\"M40 16v8M31 17l3 8M49 17l-3 8\"/>", "materials": "<path d=\"M12 30h44v28H12z\"/><path d=\"M20 22h44v28\"/><path d=\"M28 14h44v28\"/>", "vehicle": "<ellipse cx=\"40\" cy=\"40\" rx=\"26\" ry=\"16\"/><ellipse cx=\"40\" cy=\"40\" rx=\"18\" ry=\"9\"/><path d=\"M14 40h52\"/>", "other": "<rect x=\"16\" y=\"20\" width=\"48\" height=\"40\" rx=\"4\"/><path d=\"M16 34h48\"/>"};
  S.placeholder = function (p) {
    return '<div class="ph none">' +
      '<svg class="phart" viewBox="0 0 80 80" aria-hidden="true" fill="none" stroke="currentColor" ' +
      'stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round">' +
      (PH_ART[p.group] || PH_ART.other) + '</svg>' +
      '<span class="phname">' + S.esc(p.title) + '</span>' +
      '<span class="phnote">' + S.esc(S.t('ph.none')) + '</span></div>';
  };

  // Product name in the current language, falling back to the English original.
  S.name = function (p) {
    return p['title_' + S.lang] || p.title;
  };

  // Description likewise. A missing translation means the verifier in
  // translate_descriptions.py held it back, so the original is shown instead.
  S.body = function (p) {
    return p['body_' + S.lang] || p.body_html;
  };

  S.img = function (p) {
    return p.images && p.images.length ? p.images[0] : null;
  };

  S.esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };

  /* --------------------------------------------------------------- product tile
     One renderer for every grid on the site, so a change to the card shape lands
     everywhere at once. Each card carries its own add-to-request control: a single
     size is added straight away, several sizes open a picker on the card itself so
     the customer never has to leave the listing. */

  S.tile = function (p) {
    var img = S.img(p);
    var one = p.variants.length === 1;
    return '<article class="tile" data-h="' + S.esc(p.handle) + '">' +
      '<a class="tile-link" href="' + S.url('/p/' + encodeURIComponent(p.handle) + '/') + '">' +
        (img ? '<div class="ph"><img loading="lazy" src="' + S.esc(img) + '" alt="' + S.esc(S.name(p)) + '"></div>'
             : S.placeholder(p)) +
        '<div class="meta">' +
          '<div class="name">' + S.esc(S.name(p)) + '</div>' +
          '<div class="dims">' + S.esc(S.rangeLabel(p)) + '</div>' +
          '<div class="price">' +
            (p.price_min === p.price_max ? S.money(p.price_min, p.unit)
              : '<small>' + S.esc(S.t('cat.from')) + '</small> ' + S.money(p.price_min, p.unit)) +
          '</div>' +
        '</div>' +
      '</a>' +
      '<div class="tile-add">' +
        (one ? '' :
          '<select class="tile-size" aria-label="' + S.esc(S.t('prod.variants')) + '">' +
            '<option value="">' + S.esc(S.t('prod.choose')) + '</option>' +
            p.variants.map(function (v) {
              var lbl = S.dimLabel(v.dims);
              return '<option value="' + S.esc(v.title) + '">' +
                (lbl ? S.esc(lbl) + ' — ' : '') + S.money(v.price, p.unit) + '</option>';
            }).join('') +
          '</select>') +
        '<button type="button" class="btn tile-btn"' +
          (one ? ' data-v="' + S.esc(p.variants[0].title) + '"' : '') + '>' +
          S.esc(S.t('prod.add')) + '</button>' +
      '</div>' +
    '</article>';
  };

  // Delegated once per page: works for grids that are re-rendered on every filter change.
  S.wireTiles = function (root) {
    (root || document).addEventListener('click', function (e) {
      var btn = e.target.closest('.tile-btn');
      if (!btn) return;
      e.preventDefault();
      var card = btn.closest('.tile');
      var sel = card.querySelector('.tile-size');
      var variant = sel ? sel.value : btn.dataset.v;
      if (!variant) {                     // several sizes and none chosen yet
        sel.focus();
        sel.classList.add('needs');
        setTimeout(function () { sel.classList.remove('needs'); }, 1200);
        return;
      }
      S.cart.add(card.dataset.h, variant, 1);
      btn.textContent = S.t('prod.added') + ' ✓';
      btn.classList.add('added');
      setTimeout(function () {
        btn.textContent = S.t('prod.add');
        btn.classList.remove('added');
      }, 1500);
    });
  };

  /* ------------------------------------------------------------------ chrome */

  // Grouped menu. A flat list of 17 categories is no more usable than one bucket of
  // 114 products, so products hang under five groups and everything else -- vehicle
  // search, company pages -- sits beside it rather than inside it.
  function productsMenu() {
    var groups = (S.catalogue && S.catalogue.groups) || [];
    return '<div class="mega" id="mega" hidden><div class="wrap mega-in">' +
      groups.map(function (g) {
        return '<div class="mega-col">' +
          '<a class="mega-h" href="catalog.html?group=' + encodeURIComponent(g.key) + '">' +
            S.esc(S.groupLabel(g.key)) + '</a>' +
          '<ul>' + g.categories.map(function (c) {
            return '<li><a href="catalog.html?cat=' + encodeURIComponent(c.key) + '">' +
              S.esc(S.catLabel(c.key)) + '<span>' + c.count + '</span></a></li>';
          }).join('') + '</ul></div>';
      }).join('') +
      '<div class="mega-col mega-cta">' +
        '<a class="mega-h" href="' + S.url('/catalog.html') + '">' + S.esc(S.t('nav.catalog')) + '</a>' +
        '<p class="small muted">' + S.esc(S.t('nav.allIn', { n: S.catalogue ? S.catalogue.count : '' })) + '</p>' +
        '<a class="btn ghost small-btn" href="' + S.url('/vehicle.html') + '">' + S.esc(S.t('nav.vehicle')) + '</a>' +
      '</div>' +
    '</div></div>';
  }

  // The company pages sit in the footer, by request. The header carries only what a
  // shopper is here to do: find a product, find one for their vehicle, search, order.
  S.header = function (current) {

    var langs = LANGS.map(function (l) {
      return '<button type="button" data-lang="' + l + '" aria-pressed="' +
             (l === S.lang) + '">' + l + '</button>';
    }).join('');

    var onCat = current === '/catalog.html';
    return '<header class="site">' +
      '<div class="wrap bar">' +
        '<a class="logo" href="' + S.url('/') + '"><img src="/assets/img/logo-400.png" alt="STEFSOTRA" width="400" height="98"></a>' +
        '<nav class="main" id="mainnav">' +
          '<button type="button" class="menu-trigger" id="prodBtn" aria-expanded="false"' +
            (onCat ? ' aria-current="page"' : '') + '>' +
            S.esc(S.t('nav.products')) + '<i></i></button>' +
          '<a href="' + S.url('/vehicle.html') + '"' + (current === '/vehicle.html' ? ' aria-current="page"' : '') +
            '>' + S.esc(S.t('nav.vehicle')) + '</a>' +
        '</nav>' +
        '<form class="hsearch" action="' + S.url('/search.html') + '" method="get" role="search">' +
          '<input type="search" name="q" aria-label="' + S.esc(S.t('nav.search')) + '" placeholder="' +
            S.esc(S.t('srch.ph')) + '">' +
          '<button type="submit" aria-label="' + S.esc(S.t('srch.go')) + '">⌕</button>' +
        '</form>' +
        '<div class="bar-end">' +
          '<a class="iconbtn cartlink" href="' + S.url('/cart.html') + '"' + (current === '/cart.html' ? ' aria-current="page"' : '') + '>' +
            '<span aria-hidden="true">🛒</span><span class="lbl">' + S.esc(S.t('nav.cart')) + '</span>' +
            '<span class="badge" data-cart-badge style="display:none">0</span></a>' +
          '<div class="langs">' + langs + '</div>' +
          '<button class="menu-btn" type="button" aria-label="' + S.esc(S.t('nav.menu')) + '">☰</button>' +
        '</div>' +
      '</div>' +
      productsMenu() +
    '</header>';
  };

  S.footer = function () {
    var c = (S.pagesContact || {});
    var cols = [
      ['nav.products', [['/catalog.html', 'nav.catalog'], ['/vehicle.html', 'nav.vehicle'],
                        ['/search.html', 'srch.h1']]],
      ['foot.company', [['/about/', 'nav.about'], ['/partners/', 'nav.partners'],
                        ['/contact/', 'nav.contact']]],
      ['foot.help', [['/delivery/', 'nav.delivery'], ['/returns/', 'nav.returns'],
                     ['/warranty/', 'nav.warranty']]]
    ].map(function (col) {
      return '<div><h3>' + S.esc(S.t(col[0])) + '</h3><ul>' + col[1].map(function (l) {
        return '<li><a href="' + S.url(l[0]) + '">' + S.esc(S.t(l[1])) + '</a></li>';
      }).join('') + '</ul></div>';
    }).join('');

    return '<footer class="site"><div class="wrap foot">' +
      '<div class="foot-brand">' +
        '<img src="/assets/img/logo-400.png" alt="STEFSOTRA" class="foot-logo" width="400" height="98" loading="lazy" decoding="async">' +
        '<p class="small">' + S.esc(S.t('site.tagline')) + '</p>' +
        (c.phone ? '<p class="small"><a href="tel:' + S.esc(c.phone_href) + '">' + S.esc(c.phone) + '</a></p>' : '') +
        (c.email ? '<p class="small"><a href="mailto:' + S.esc(c.email) + '">' + S.esc(c.email) + '</a></p>' : '') +
        (c.address ? '<p class="small"><a href="' + S.esc(c.maps || '#') +
          '" target="_blank" rel="noopener">' + S.esc(c.address) + '</a></p>' : '') +
      '</div>' + cols +
    '</div><div class="wrap foot-legal small">' +
      '<span>© ' + new Date().getFullYear() + ' STEFSOTRA · ' +
      '<a href="https://stefsotra.md">stefsotra.md</a></span>' +
      '<span class="madeby"><a href="https://aggento.com" target="_blank" rel="noopener">' +
      S.esc(S.t('foot.by')) + '</a></span></div></footer>';
  };

  S.chrome = function (current) {
    if (S.pages && S.pages._contact) S.pagesContact = S.pages._contact;
    if (!document.querySelector('header.site')) {
      document.body.insertAdjacentHTML('afterbegin', S.header(current));
      document.body.insertAdjacentHTML('beforeend', S.footer());
    }

    document.querySelectorAll('[data-lang]').forEach(function (b) {
      b.addEventListener('click', function (e) {
        // On a pre-rendered page these are real links and must stay real links, so a
        // crawler can follow them; clicking one only needs to record the preference.
        if (b.tagName === 'A') { localStorage.setItem(LS_LANG, b.getAttribute('data-lang')); return; }
        e.preventDefault();
        S.setLang(b.getAttribute('data-lang'));
      });
    });

    buildDrawer();

    // Products mega-menu: hover on pointer devices, click everywhere (and on touch,
    // where hover would otherwise make it impossible to close).
    var btn = document.getElementById('prodBtn');
    var mega = document.getElementById('mega');
    if (btn && mega) {
      var open = function (v) {
        mega.hidden = !v;
        btn.setAttribute('aria-expanded', String(v));
      };
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        open(mega.hidden);
      });
      document.addEventListener('click', function (e) {
        if (!mega.hidden && !mega.contains(e.target)) open(false);
      });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') open(false);
      });
    }

    var q = document.querySelector('.hsearch input');
    if (q) q.value = new URLSearchParams(location.search).get('q') || '';

    S.cart.paint();
    S.wireTiles(document);
    if (S.assistant) S.assistant.mount();
  };

  /* ------------------------------------------------------- static content pages
     About, delivery, partners and the two policies all share one renderer; the
     copy lives in data/pages.json so it can be edited without touching HTML. */

  var PAGE_LINKS = [
    ['/about/', 'nav.about'], ['/delivery/', 'nav.delivery'],
    ['/partners/', 'nav.partners'], ['/returns/', 'nav.returns'],
    ['/warranty/', 'nav.warranty'], ['/contact/', 'nav.contact']
  ];

  // A heading and three paragraphs on a white page reads as an unfinished site, so a
  // content page gets the same furniture a product page has: a titled band, the copy,
  // whatever structured blocks it defines in pages.json, a help sidebar, and a way back
  // into the catalogue. Every block is optional -- a page renders whatever it has.
  S.renderPage = function (slug, currentFile) {
    var d = (S.pages[slug] || {})[S.lang] || (S.pages[slug] || {}).ro;
    if (!d) { location.replace(S.url('/')); return; }
    document.title = d.title + ' — Stefsotra';

    var c = S.pagesContact || {};
    var variants = S.catalogue
      ? S.catalogue.products.reduce(function (a, p) { return a + p.variants.length; }, 0) : 0;

    var body =
      (d.lead ? '<p class="lead">' + S.esc(d.lead) + '</p>' : '') +
      (d.stats ? '<div class="statrow">' + d.stats.map(function (s) {
        return '<div class="stat"><b>' + S.esc(s.v) + '</b><span>' + S.esc(s.l) + '</span></div>';
      }).join('') + '</div>' : '') +
      (d.body || []).map(function (p) { return '<p>' + S.esc(p) + '</p>'; }).join('') +

      (d.cards ? (d.cardsTitle ? '<h2>' + S.esc(d.cardsTitle) + '</h2>' : '') +
        '<div class="infocards">' + d.cards.map(function (x) {
          return '<div class="infocard"><h3>' + S.esc(x.t) + '</h3><p>' + S.esc(x.p) + '</p></div>';
        }).join('') + '</div>' : '') +

      (d.steps ? (d.stepsTitle ? '<h2>' + S.esc(d.stepsTitle) + '</h2>' : '') +
        '<ol class="flowsteps">' + d.steps.map(function (x) {
          return '<li><b></b><div><h3>' + S.esc(x.t) + '</h3><p>' + S.esc(x.p) + '</p></div></li>';
        }).join('') + '</ol>' : '') +

      (d.listTitle ? '<h2>' + S.esc(d.listTitle) + '</h2>' : '') +
      (d.list ? '<ul class="ticks">' + d.list.map(function (li) {
        return '<li>' + S.esc(li) + '</li>';
      }).join('') + '</ul>' : '') +

      (d.faq ? (d.faqTitle ? '<h2>' + S.esc(d.faqTitle) + '</h2>' : '') +
        '<div class="faq">' + d.faq.map(function (x) {
          return '<details><summary>' + S.esc(x.q) + '</summary><p>' + S.esc(x.a) + '</p></details>';
        }).join('') + '</div>' : '') +

      (d.cta ? '<p class="lead" style="margin-top:26px">' + S.esc(d.cta) +
        ' <a href="' + S.url('/contact/') + '">' + S.esc(S.t('nav.contact')) + ' →</a></p>' : '');

    var side =
      '<div class="sidecard">' +
        '<h3>' + S.esc(S.t('pg.help')) + '</h3>' +
        '<p class="small">' + S.esc(S.t('pg.helpText')) + '</p>' +
        (c.phone ? '<a class="bigphone" href="tel:' + S.esc(c.phone_href) + '">' + S.esc(c.phone) + '</a>' : '') +
        (c.email ? '<a class="small" href="mailto:' + S.esc(c.email) + '">' + S.esc(c.email) + '</a>' : '') +
        '<button type="button" class="btn ghost small-btn" data-ai-open>' +
          S.esc(S.t('nav.assistant')) + ' ✦</button>' +
      '</div>' +
      '<div class="sidecard"><h3>' + S.esc(S.t('pg.more')) + '</h3><ul class="sidelinks">' +
        PAGE_LINKS.filter(function (l) { return l[0] !== currentFile; }).map(function (l) {
          return '<li><a href="' + S.url(l[0]) + '">' + S.esc(S.t(l[1])) + '</a></li>';
        }).join('') + '</ul></div>';

    document.getElementById('root').innerHTML =
      '<div class="pagehead"><div class="wrap">' +
        '<p class="small crumb"><a href="' + S.url('/') + '">' + S.esc(S.t('nav.home')) + '</a> › ' +
          S.esc(d.title) + '</p>' +
        '<h1>' + S.esc(d.title) + '</h1>' +
      '</div></div>' +
      '<div class="wrap pagebody">' +
        '<article class="prose">' + body + '</article>' +
        '<aside class="pageside">' + side + '</aside>' +
      '</div>' +
      '<div class="wrap"><section class="home-sec ask">' +
        '<div><h2>' + S.esc(S.t('pg.ctaH')) + '</h2>' +
        '<p class="muted">' + S.esc(S.t('pg.ctaP', { n: S.catalogue ? S.catalogue.count : '', v: variants })) + '</p></div>' +
        '<a class="btn" href="' + S.url('/catalog.html') + '">' + S.esc(S.t('nav.catalog')) + '</a>' +
      '</section></div>';

    document.querySelectorAll('.pageside [data-ai-open]').forEach(function (b) {
      b.addEventListener('click', function () { if (S.assistant) S.assistant.open(); });
    });
  };

  /* --------------------------------------------------------------- mobile menu
     On a phone the old menu was the desktop bar stacked vertically: two items, one of
     which opened a mega-menu inside it. You could not reach a category without two
     taps into a panel that was never designed to be there.

     This is a proper drawer instead -- search, then the product groups as an accordion,
     then the vehicle finder, the company pages, the language switch and the phone
     number. It is built once here from the mega-menu already in the page, so the
     pre-rendered pages and the JavaScript pages get the same thing without a second
     implementation to keep in step. */

  function buildDrawer() {
    var btn = document.querySelector('.menu-btn');
    var mega = document.getElementById('mega');
    if (!btn || document.getElementById('drawer')) return;

    var groups = mega ? [].slice.call(mega.querySelectorAll('.mega-col')).filter(function (c) {
      return !c.classList.contains('mega-cta');
    }) : [];

    var acc = groups.map(function (col, i) {
      var head = col.querySelector('.mega-h');
      var items = [].slice.call(col.querySelectorAll('li a')).map(function (a) {
        return '<li><a href="' + a.getAttribute('href') + '">' + a.innerHTML + '</a></li>';
      }).join('');
      return '<details class="dgroup"' + (i === 0 ? ' open' : '') + '>' +
        '<summary>' + S.esc(head.textContent) + '</summary>' +
        '<ul>' + items + '<li class="all"><a href="' + head.getAttribute('href') + '">' +
        S.esc(S.t('home.seeAll')) + ' →</a></li></ul></details>';
    }).join('');

    var pages = [['/vehicle.html', 'nav.vehicle'], ['/about/', 'nav.about'],
                 ['/delivery/', 'nav.delivery'], ['/partners/', 'nav.partners'],
                 ['/returns/', 'nav.returns'], ['/warranty/', 'nav.warranty'],
                 ['/contact/', 'nav.contact']]
      .map(function (l) {
        return '<a href="' + S.url(l[0]) + '">' + S.esc(S.t(l[1])) + '</a>';
      }).join('');

    var langs = LANGS.map(function (l) {
      return '<a href="' + S.langUrl(l) + '" data-lang="' + l + '" aria-pressed="' +
             (l === S.lang) + '">' + l + '</a>';
    }).join('');

    var c = S.contact();

    document.body.insertAdjacentHTML('beforeend',
      '<div class="drawer-back" id="drawerBack" hidden></div>' +
      '<aside class="drawer" id="drawer" hidden aria-label="' + S.esc(S.t('nav.menu')) + '">' +
        '<header>' +
          '<a class="logo" href="' + S.url('/') + '"><img src="/assets/img/logo-400.png" alt="STEFSOTRA" width="400" height="98"></a>' +
          '<button type="button" class="ai-x" id="drawerClose" aria-label="' + S.esc(S.t('nav.close')) + '">✕</button>' +
        '</header>' +
        '<form class="drawer-search" action="' + S.url('/search.html') + '" method="get" role="search">' +
          '<input type="search" name="q" placeholder="' + S.esc(S.t('srch.ph')) + '" aria-label="' + S.esc(S.t('srch.go')) + '">' +
          '<button class="btn" type="submit">' + S.esc(S.t('srch.go')) + '</button>' +
        '</form>' +
        '<nav class="drawer-body">' +
          '<p class="dlabel">' + S.esc(S.t('nav.products')) + '</p>' + acc +
          '<p class="dlabel">' + S.esc(S.t('foot.company')) + '</p>' +
          '<div class="dlinks">' + pages + '</div>' +
        '</nav>' +
        '<footer>' +
          (c.address ? '<a class="draddr small" href="' + S.esc(c.maps || '#') +
            '" target="_blank" rel="noopener">' + S.esc(c.address) + '</a>' : '') +
          '<div class="drrow">' +
            '<a class="btn" href="tel:' + S.esc(c.phone_href) + '">' + S.esc(c.phone) + '</a>' +
            '<div class="langs">' + langs + '</div>' +
          '</div>' +
        '</footer>' +
      '</aside>');

    var drawer = document.getElementById('drawer');
    var back = document.getElementById('drawerBack');
    function open(v) {
      drawer.hidden = !v;
      back.hidden = !v;
      document.body.classList.toggle('noscroll', v);
      btn.setAttribute('aria-expanded', String(v));
      if (v) drawer.querySelector('input').focus();
    }
    btn.setAttribute('aria-expanded', 'false');
    btn.addEventListener('click', function () { open(drawer.hidden); });
    back.addEventListener('click', function () { open(false); });
    document.getElementById('drawerClose').addEventListener('click', function () { open(false); });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !drawer.hidden) open(false);
    });
    drawer.querySelectorAll('[data-lang]').forEach(function (a) {
      a.addEventListener('click', function () {
        localStorage.setItem(LS_LANG, a.getAttribute('data-lang'));
      });
    });
  }

  S.fail = function (err) {
    console.error(err);
    var m = document.querySelector('main') || document.body;
    m.innerHTML = '<div class="wrap"><div class="note warn"><strong>Data could not be loaded.</strong>' +
      '<br>If you opened this file directly, run a local server instead: ' +
      '<code>python3 -m http.server</code><br><span class="small">' + S.esc(err.message) +
      '</span></div></div>';
  };
})();
