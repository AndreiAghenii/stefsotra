/* The AI layer: a query understander used by search.html, and a chat assistant.

   Both talk to /.netlify/functions/assistant, which holds the API key server-side --
   a key shipped in a static page would be public the moment the site went live.

   Everything degrades. If the function is missing (running locally, or the key is not
   configured yet) search still works through the rule-based parser below, and the chat
   panel says plainly that it is not switched on rather than failing silently. */
(function () {
  'use strict';

  var S = window.S;
  var ENDPOINT = '/.netlify/functions/assistant';
  var available = null;          // null = untested, true/false once we know

  function call(payload) {
    return fetch(ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(function (r) {
      if (r.status === 404 || r.status === 501) { available = false; return null; }
      if (!r.ok) throw new Error('assistant ' + r.status);
      available = true;
      return r.json();
    });
  }

  /* ================================================================= parsing
     The rule-based parser. It is not AI and is not described as such in the UI --
     it is a keyword and number reader that covers the way people actually type
     these queries in all three languages. It is the fallback, and on a query like
     "furtun silicon 38 90" it is also simply the right tool. */

  var WORDS = {
    'silicone-hose':   ['silicon', 'силикон', 'silicone'],
    'camlock':         ['camlock', 'камлок', 'кэмлок'],
    'storz':           ['storz', 'шторц', 'сторц'],
    'guillemin':       ['guillemin', 'гиймен', 'гийемен'],
    'bauer':           ['bauer', 'бауэр'],
    'tw-coupling':     ['tw', 'вб', 'мб'],
    'clamp':           ['colier', 'coliere', 'хомут', 'хомуты', 'clamp'],
    'gasket':          ['garnitur', 'прокладк', 'gasket'],
    'valve':           ['robinet', 'кран', 'клапан', 'valve', 'supap'],
    'pvc-hose':        ['pvc', 'пвх'],
    'sheet-material':  ['placa', 'plăci', 'foaie', 'лист', 'sheet', 'текстолит', 'паронит'],
    'plastic-stock':   ['bara', 'bară', 'стержень', 'капролон', 'капралон', 'rod'],
    'rubber-profile':  ['snur', 'șnur', 'шнур', 'cord', 'profil'],
    'hose-fitting':    ['adaptor', 'racord', 'адаптер', 'головка', 'fitting', 'adapter'],
    'agri':            ['grebl', 'грабл', 'matura', 'метла', 'irigare', 'полив']
  };

  // Generic words name a whole group, not one category. "furtun" must not resolve to
  // industrial-hose, or it would hide every silicone and PVC hose in the shop.
  var GROUP_WORDS = {
    'hoses':     ['furtun', 'шланг', 'рукав', 'hose'],
    'couplings': ['cuplaj', 'cuplaje', 'соединен', 'муфта', 'coupling', 'fiting'],
    'sealing':   ['etans', 'уплотнен', 'sealing'],
    'materials': ['material', 'материал']
  };
  // Vehicle and brand names are deliberately NOT category keywords. "kamaz" describes a
  // product whose category is silicone-hose, so treating it as a category would filter
  // the very product being asked for; it works far better as a title term.

  var MATERIALS = {
    'silicone':      ['silicon', 'силикон', 'silicone'],
    'aluminium':     ['aluminiu', 'алюмин', 'aluminium', 'aluminum', ' al '],
    'polypropylene': ['polipropilen', 'полипропилен', 'пластик', 'plastic', ' pp ']
  };

  var ANGLE_HINT = ['grad', 'град', 'deg', '°', 'cot', 'колено', 'elbow', 'unghi', 'угол'];

  // Product titles in the catalogue are English. These are the words customers actually
  // type in Romanian and Russian for the things the shop stocks, mapped onto the English
  // word that appears in the title, so a Russian query can still match.
  var SYNONYM = {
    'пищев': 'food', 'alimentar': 'food',
    'воздуш': 'air', 'aer': 'air',
    'водян': 'water', 'вода': 'water', 'apa': 'water', 'apă': 'water',
    'топлив': 'fuel', 'combustibil': 'fuel', 'бензин': 'fuel',
    'масл': 'oil', 'ulei': 'oil',
    'кислород': 'oxygen', 'oxigen': 'oxygen',
    'канализ': 'sewage', 'фекал': 'sewage',
    'вентиляц': 'ventilation', 'ventilat': 'ventilation',
    'цемент': 'cement', 'штукатур': 'plastering', 'tencui': 'plastering',
    'пожарн': 'fire', 'incendiu': 'fire', 'pompieri': 'fire',
    'всасыв': 'suction', 'aspira': 'suction',
    'давлен': 'pressure', 'presiune': 'pressure',
    'армиров': 'braided', 'напорн': 'pressure'
  };

  function translate(text) {
    var out = String(text || '');
    Object.keys(SYNONYM).forEach(function (k) {
      if (out.toLowerCase().indexOf(k) >= 0) out += ' ' + SYNONYM[k];
    });
    return out;
  }

  S.parseQuery = function (raw) {
    var q = ' ' + String(raw || '').toLowerCase().replace(/[,;]/g, ' ') + ' ';
    var out = { raw: raw, cat: '', grp: '', dia: 0, ang: '', mat: '', text: '' };

    // Category and material keywords are recorded and then removed from the query, so
    // they cannot come back as free text and filter out the very products they selected.
    var rest = ' ' + String(raw || '').toLowerCase() + ' ';
    function claim(map, field) {
      Object.keys(map).some(function (key) {
        return map[key].some(function (w) {
          if (q.indexOf(w) >= 0) {
            out[field] = key;
            rest = rest.split(w).join(' ');
            return true;
          }
        });
      });
    }
    claim(WORDS, 'cat');
    if (!out.cat) claim(GROUP_WORDS, 'grp');   // a category always beats its group
    else Object.keys(GROUP_WORDS).forEach(function (g) {
      GROUP_WORDS[g].forEach(function (w) { rest = rest.split(w).join(' '); });
    });
    claim(MATERIALS, 'mat');

    // Numbers. A number written with a degree marker is an angle; one written with mm
    // is a diameter. Bare numbers are diameters, except 45/90/135/180 when the query
    // also mentions an angle in words -- "cot 90" is an elbow, not a 90 mm bore.
    var angled = ANGLE_HINT.some(function (w) { return q.indexOf(w) >= 0; });
    var nums = [];
    q.replace(/(\d+(?:[.,]\d+)?)\s*(°|mm|мм|grade|градус|deg)?/g, function (_, n, unit) {
      nums.push({ n: parseFloat(n.replace(',', '.')), unit: (unit || '').trim() });
      return _;
    });
    nums.forEach(function (x) {
      var isAngleUnit = /°|grad|градус|deg/.test(x.unit);
      var couldBeAngle = [45, 90, 135, 180].indexOf(x.n) >= 0;
      if (!out.ang && (isAngleUnit || (couldBeAngle && angled && out.dia))) out.ang = String(x.n);
      else if (!out.dia && !isAngleUnit) out.dia = x.n;
      else if (!out.ang && couldBeAngle && angled) out.ang = String(x.n);
    });
    // "cot 90" on its own: the single number is the angle, not a bore
    if (angled && out.dia && !out.ang && [45, 90, 135, 180].indexOf(out.dia) >= 0) {
      out.ang = String(out.dia); out.dia = 0;
    }

    // whatever is left over is free text, matched against titles and SKUs
    out.text = translate(rest)
      .replace(/\d+(?:[.,]\d+)?\s*(°|mm|мм|grade|градус|deg)?/g, ' ')
      .replace(/[-–*/]/g, ' ')
      .replace(/\s+/g, ' ').trim();
    return out;
  };

  /* Ask the model to read the query instead, when it is available. It returns the same
     shape as parseQuery, so search.html does not care which one answered. */
  S.smartParse = function (text) {
    var local = S.parseQuery(text);
    if (available === false) return Promise.resolve({ q: local, by: 'rules' });
    return call({ mode: 'parse', query: text, lang: S.lang })
      .then(function (d) {
        if (!d || !d.filters) return { q: local, by: 'rules' };
        var f = d.filters;
        return {
          q: {
            raw: text,
            cat: f.category || '',
            grp: f.group || '',
            dia: Number(f.diameter_mm) || 0,
            ang: f.angle ? String(f.angle) : '',
            mat: f.material || '',
            text: f.keywords || ''
          },
          by: 'ai'
        };
      })
      .catch(function () { return { q: local, by: 'rules' }; });
  };

  /* ================================================================== search
     Shared by search.html and the catalogue, so both rank the same way. */

  S.searchProducts = function (q) {
    var structured = !!(q.cat || q.grp || q.ang || q.mat || q.dia > 0);
    var terms = (q.text || '').toLowerCase().split(/\s+/)
                  .filter(function (t) { return t.length > 2; });

    var list = S.catalogue.products.filter(function (p) {
      if (q.cat && p.category !== q.cat) return false;
      if (q.grp && p.group !== q.grp) return false;
      if (q.ang && String(p.attrs.angle || '') !== q.ang) return false;
      if (q.mat) {
        var ok = p.attrs.material === q.mat ||
          p.variants.some(function (v) { return v.dims.material === q.mat; });
        if (!ok) return false;
      }
      if (q.dia > 0) {
        var hit = p.variants.some(function (v) {
          var d = v.dims;
          if (d.id_min != null) return q.dia >= d.id_min - 3 && q.dia <= d.id_max + 3;
          if (d.clamp_min != null) return q.dia >= d.clamp_min && q.dia <= d.clamp_max;
          return false;
        });
        if (!hit) return false;
      }
      // Leftover words rank results when the query already has a size or a category.
      // As a hard filter they would empty the page whenever someone types a Romanian
      // or Russian word that does not appear in an English product title.
      p._score = terms.length ? terms.filter(function (t) { return hay(p).indexOf(t) >= 0; }).length : 0;
      if (terms.length && !structured && !p._score) return false;
      return true;
    });

    function hay(p) {
      if (!p._hay) {
        p._hay = (p.title + ' ' + p.category + ' ' + p.tags.join(' ') + ' ' +
          p.variants.map(function (v) { return v.title + ' ' + v.sku; }).join(' ')).toLowerCase();
      }
      return p._hay;
    }
    // word matches first, then closest diameter -- a 38 mm query must not lead with 41 mm
    function dist(p) {
      if (!(q.dia > 0)) return 0;
      return Math.min.apply(null, p.variants.map(function (v) {
        var d = v.dims;
        if (d.id_min != null) return Math.min(Math.abs(q.dia - d.id_min), Math.abs(q.dia - d.id_max));
        if (d.clamp_min != null) return 0;
        return 999;
      }).concat([999]));
    }
    return list.sort(function (a, b) {
      return (b._score - a._score) || (dist(a) - dist(b));
    });
  };

  /* ================================================================== chat */

  var history = [];
  var busy = false;

  var A = S.assistant = {
    mount: function () {
      if (document.getElementById('aiPanel')) return;
      document.body.insertAdjacentHTML('beforeend',
        '<button type="button" class="ai-fab" data-ai-open aria-label="' + S.esc(S.t('ai.open')) + '">✦</button>' +
        '<section class="ai-panel" id="aiPanel" hidden aria-label="' + S.esc(S.t('ai.title')) + '">' +
          '<header><strong>' + S.esc(S.t('ai.title')) + '</strong>' +
            '<button type="button" class="linkish" id="aiClear">' + S.esc(S.t('ai.clear')) + '</button>' +
            '<button type="button" class="ai-x" id="aiClose" aria-label="' + S.esc(S.t('nav.close')) + '">✕</button>' +
          '</header>' +
          '<div class="ai-log" id="aiLog"></div>' +
          '<form class="ai-form" id="aiForm">' +
            '<input type="text" id="aiInput" autocomplete="off" placeholder="' + S.esc(S.t('ai.ph')) + '">' +
            '<button class="btn" type="submit">' + S.esc(S.t('ai.send')) + '</button>' +
          '</form>' +
          '<p class="ai-note small">' + S.esc(S.t('ai.note')) + '</p>' +
        '</section>');

      document.querySelectorAll('[data-ai-open]').forEach(function (b) {
        b.addEventListener('click', function () { A.open(); });
      });
      document.getElementById('aiClose').addEventListener('click', function () { A.open(false); });
      document.getElementById('aiClear').addEventListener('click', function () {
        history = []; A.reset();
      });
      document.getElementById('aiForm').addEventListener('submit', function (e) {
        e.preventDefault();
        var el = document.getElementById('aiInput');
        var text = el.value.trim();
        if (!text || busy) return;
        el.value = '';
        A.send(text);
      });
      A.reset();
    },

    open: function (v) {
      var p = document.getElementById('aiPanel');
      p.hidden = (v === false);
      if (p.hidden) return;
      document.getElementById('aiInput').focus();
      // The product cards in a reply are drawn from our own catalogue. Fetching it here
      // rather than on page load keeps 400 KB off every visit that never opens the chat.
      if (S.ensureCatalogue) S.ensureCatalogue();
    },

    reset: function () {
      document.getElementById('aiLog').innerHTML =
        '<div class="ai-msg bot">' + S.esc(S.t('ai.intro')) + '</div>';
    },

    say: function (cls, html) {
      var log = document.getElementById('aiLog');
      log.insertAdjacentHTML('beforeend', '<div class="ai-msg ' + cls + '">' + html + '</div>');
      log.scrollTop = log.scrollHeight;
      return log.lastElementChild;
    },

    send: function (text) {
      busy = true;
      A.say('me', S.esc(text));
      var wait = A.say('bot pending', S.esc(S.t('ai.thinking')));
      history.push({ role: 'user', content: text });

      call({ mode: 'chat', messages: history, lang: S.lang })
        .then(function (d) {
          if (!d) {                                   // function not deployed / no key
            wait.className = 'ai-msg bot';
            wait.innerHTML = S.esc(S.t('ai.off')) +
              ' <a href="search.html?q=' + encodeURIComponent(text) + '">' +
              S.esc(S.t('srch.h1')) + ' →</a>';
            history.pop();
            return;
          }
          history.push({ role: 'assistant', content: d.reply || '' });
          wait.className = 'ai-msg bot';
          wait.innerHTML = fmt(d.reply || '') + cards(d.handles || []);
        })
        .catch(function () {
          wait.className = 'ai-msg bot';
          wait.textContent = S.t('ai.error');
          history.pop();
        })
        .then(function () { busy = false; });
    }
  };

  // The reply is plain text; only paragraph breaks and **bold** are honoured, and the
  // text is escaped first so a model reply can never inject markup into the page.
  function fmt(t) {
    return S.esc(t)
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\n{2,}/g, '</p><p>')
      .replace(/\n/g, '<br>')
      .replace(/^/, '<p>').replace(/$/, '</p>');
  }

  // Products the model referred to are rendered from our own catalogue data, never
  // from what it wrote -- so a hallucinated price cannot reach the customer.
  function cards(handles) {
    if (!S.catalogue) return '';
    var found = handles.map(function (h) { return S.byHandle(h); }).filter(Boolean);
    if (!found.length) return '';
    return '<div class="ai-cards"><span class="small muted">' + S.esc(S.t('ai.suggest')) + '</span>' +
      found.slice(0, 4).map(function (p) {
        var img = S.img(p);
        return '<a class="ai-card" href="product.html?h=' + encodeURIComponent(p.handle) + '">' +
          (img ? '<img src="' + S.esc(img) + '" alt="">' : '<span class="ai-card-ph"></span>') +
          '<span><b>' + S.esc(p.title) + '</b>' +
          '<i>' + S.esc(S.rangeLabel(p)) + ' · ' + S.money(p.price_min) + '</i></span></a>';
      }).join('') + '</div>';
  }
})();
