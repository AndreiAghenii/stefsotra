/* Hydration for the pre-rendered pages.

   The HTML that arrives from the server is already complete -- headings, prices, sizes,
   links, structured data. This file does not redraw any of it. It attaches the things
   that need a browser: the basket, the size picker, the menus, the assistant.

   That ordering matters for more than tidiness. Redrawing would mean the visitor sees
   the page twice, and it would mean the catalogue JSON (about 400 KB) had to be fetched
   before anything was usable. Here nothing but the 12 KB translation file is needed to
   make a page interactive, and the catalogue is fetched only on the pages that genuinely
   need it -- the basket, and the assistant once it is opened. */
(function () {
  'use strict';
  var S = window.S;
  if (!S || document.getElementById('root')) return;   // JS-rendered page: not ours

  var path = location.pathname;
  var m = path.match(/^\/(ru|en)(\/|$)/);
  S.lang = m ? m[1] : 'ro';
  S.prerendered = true;

  fetch('/i18n/' + S.lang + '.json')
    .then(function (r) { return r.json(); })
    .then(function (d) {
      S.strings = d;
      S.chrome(currentFile());
      wireProduct();
      wireForms();
    })
    .catch(function () {
      // Even with no translations the page is readable and the links work; only the
      // interactive extras are lost, so fail quietly rather than blanking the content.
      S.strings = {};
      S.chrome(currentFile());
      wireProduct();
      wireForms();
    });

  function currentFile() {
    return path.replace(/^\/(ru|en)/, '') || '/';
  }

  /* ------------------------------------------------------------------ product */

  function wireProduct() {
    var P = window.__PRODUCT;
    var unit = P && P.unit;
    var sel = document.getElementById('variant');
    var add = document.querySelector('[data-add]');
    if (!P || !sel || !add) return;

    var chosen = null;
    var info = document.getElementById('selInfo');

    // Hose is priced per metre, so the button has to show the total for the length
    // chosen, not the price of one metre. Everything else is bought by the piece and
    // has no length control at all.
    var rng = document.getElementById('metres');
    var num = document.getElementById('metresN');
    function metres() {
      return unit === 'm' ? Math.max(1, Number(num && num.value) || 1) : 1;
    }

    function pick(i) {
      chosen = i;
      if (i == null) {
        add.disabled = true;
        add.textContent = S.t('prod.choose');
        if (info) info.textContent = '';
        return;
      }
      var v = P.variants[i];
      var m = metres();
      add.disabled = false;
      add.textContent = S.t('prod.add') + ' — ' + S.money(v.price * m) +
        (m > 1 ? '  (' + m + ' m × ' + S.money(v.price, unit) + ')' : '');
      if (info) info.textContent = v.sku ? S.t('prod.sku') + ' ' + v.sku : '';
    }

    if (rng && num) {
      var sync = function (val, from) {
        val = Math.max(1, Math.min(9999, Math.round(Number(val) || 1)));
        num.value = val;
        // the slider stops at 100; a longer run is typed and the slider parks at its end
        rng.value = Math.min(val, Number(rng.max));
        if (chosen != null) pick(chosen);
      };
      rng.addEventListener('input', function () { sync(rng.value); });
      num.addEventListener('input', function () { sync(num.value); });
      document.querySelectorAll('.lenquick .size-chip').forEach(function (b) {
        b.addEventListener('click', function () {
          sync(b.dataset.m);
          document.querySelectorAll('.lenquick .size-chip').forEach(function (x) {
            x.removeAttribute('aria-pressed');
          });
          b.setAttribute('aria-pressed', 'true');
        });
      });
    }

    sel.addEventListener('change', function (e) {
      pick(e.target.value === '' ? null : Number(e.target.value));
    });
    add.addEventListener('click', function () {
      if (chosen == null) { sel.focus(); return; }
      S.cart.add(P.handle, P.variants[chosen].title, metres());
      add.textContent = S.t('prod.added') + ' ✓';
      add.classList.add('added');
      setTimeout(function () { add.classList.remove('added'); pick(chosen); }, 1500);
    });

    if (P.variants.length === 1) { sel.value = '0'; pick(0); }
    else { add.disabled = true; pick(null); }

    document.querySelectorAll('.thumbs button').forEach(function (b) {
      b.addEventListener('click', function () {
        document.getElementById('mainImg').src = P.images[Number(b.dataset.i)];
        document.querySelectorAll('.thumbs button').forEach(function (x) {
          x.setAttribute('aria-pressed', x === b);
        });
      });
    });
  }

  /* -------------------------------------------------------------------- forms */

  function wireForms() {
    var stars = document.querySelectorAll('.starpick button');
    var rval = document.getElementById('rval');
    if (stars.length && rval) {
      var paint = function (n) {
        stars.forEach(function (b, i) { b.classList.toggle('on', i < n); });
        rval.value = n;
      };
      stars.forEach(function (b) {
        b.addEventListener('click', function () { paint(Number(b.dataset.r)); });
      });
      paint(5);
    }

    // Netlify accepts a urlencoded POST to any path on the site, which is what lets a
    // static page take a submission without a backend.
    [['rf', 'rok', 'Recenzie Stefsotra'], ['cf', 'ok', 'Mesaj de pe stefsotra.md']]
      .forEach(function (spec) {
        var f = document.getElementById(spec[0]);
        var ok = document.getElementById(spec[1]);
        if (!f || !ok) return;
        f.addEventListener('submit', function (e) {
          e.preventDefault();
          fetch('/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams(new FormData(f)).toString()
          }).then(function (r) {
            if (!r.ok) throw new Error(r.status);
            f.hidden = true; ok.hidden = false;
          }).catch(function () {
            // Netlify unreachable or not configured: hand it to the mail client so the
            // message still reaches the shop rather than vanishing.
            var lines = [];
            new FormData(f).forEach(function (v, k) {
              if (k !== 'form-name' && k !== 'company' && v) lines.push(k + ': ' + v);
            });
            location.href = S.mailto(spec[2], lines.join('\n'));
            f.hidden = true; ok.hidden = false;
          });
        });
      });
  }
})();
