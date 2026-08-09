/* Server side of the AI assistant.
 *
 * It exists for one reason: the Anthropic API key must not be in the page. Everything
 * the browser sends comes through here, the key is read from the environment, and the
 * reply goes back as plain JSON.
 *
 * Set ANTHROPIC_API_KEY in Netlify (Site settings -> Environment variables). Without
 * it this returns 501 and the front end quietly falls back to rule-based search, so
 * the site is never broken by a missing key.
 */
const fs = require('fs');
const path = require('path');

const MODEL = 'claude-sonnet-5';
const MAX_TURNS = 12;          // keep the prompt small; this is a shop, not a therapist

// One line per product: handle | title | category | size range | angle | material | price.
// Loaded once per container, not per request.
let CATALOGUE = null;
function catalogue() {
  if (CATALOGUE !== null) return CATALOGUE;
  for (const p of ['data/index.txt', '../data/index.txt', '../../data/index.txt']) {
    try {
      CATALOGUE = fs.readFileSync(path.join(__dirname, p), 'utf8');
      return CATALOGUE;
    } catch (e) { /* try the next location */ }
  }
  CATALOGUE = '';
  return CATALOGUE;
}

const LANG_NAME = { ro: 'Romanian', ru: 'Russian', en: 'English' };

const CHAT_SYSTEM = (lang) => `
You are the sales assistant for Stefsotra, a Moldovan supplier of industrial hoses,
couplings and technical rubber goods, trading since the 1990s.

Answer in ${LANG_NAME[lang] || 'Romanian'}. Be brief and practical — customers are
tradespeople, farmers and mechanics, not engineers. Two or three short paragraphs at most.

The full catalogue is below, one product per line:
handle | title | category | size range | angle | material | price in Moldovan lei | variant count

RULES
- Recommend only products that appear in the catalogue below. Never invent a product,
  a size or a price.
- Prices are in Moldovan lei (MDL) and are the price per unit. Quote them as e.g. "91 lei".
- These hoses are chosen by measured size. If the customer names a vehicle but not a
  size, ask them to measure the inside diameter of the end of the old hose — we only
  hold exact vehicle fitment for Mercedes Sprinter and KAMAZ/MAZ.
- If nothing in the catalogue fits, say so and suggest they call +373 (22) 55-39-54.
- Orders on this site are requests for a quotation. There is no online payment.
- Never promise stock, a delivery date or a discount.

When you name products, finish your reply with a final line in exactly this form,
listing their handles, and nothing after it:
[[handles: handle-one, handle-two]]
Omit that line entirely if you are not recommending anything specific.

CATALOGUE
${catalogue()}
`.trim();

const PARSE_SYSTEM = `
You convert a shopper's search query into filters for an industrial hose catalogue.
Reply with JSON only, no prose, no code fence:

{"category": "", "group": "", "diameter_mm": 0, "angle": 0, "material": "", "keywords": ""}

category must be one of, or empty:
silicone-hose industrial-hose pvc-hose camlock storz guillemin bauer tw-coupling
hose-fitting valve clamp gasket rubber-profile sheet-material plastic-stock
vehicle-part agri

group is the wider family and must be one of, or empty:
hoses couplings sealing materials vehicle
Set group and leave category empty when the shopper names a family rather than a type
-- "a hose", "un furtun", "шланг" is group=hoses, not category=industrial-hose, because
silicone and PVC hoses are hoses too. Never set both.

material must be one of, or empty: silicone aluminium polypropylene

diameter_mm is the inside diameter in millimetres, 0 if not stated.
angle is 45, 90, 135 or 180, 0 if not stated. A number written with "grade", "градусов"
or "°" is an angle; a bare number is normally a diameter.
keywords holds any remaining meaningful words, or "".

Queries arrive in Romanian, Russian or English.
`.trim();

async function anthropic(key, body) {
  const r = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-api-key': key,
      'anthropic-version': '2023-06-01'
    },
    body: JSON.stringify(body)
  });
  if (!r.ok) throw new Error(`anthropic ${r.status}: ${(await r.text()).slice(0, 300)}`);
  const d = await r.json();
  return (d.content || []).filter(c => c.type === 'text').map(c => c.text).join('').trim();
}

const json = (code, obj) => ({
  statusCode: code,
  headers: { 'content-type': 'application/json', 'cache-control': 'no-store' },
  body: JSON.stringify(obj)
});

exports.handler = async (event) => {
  if (event.httpMethod !== 'POST') return json(405, { error: 'POST only' });

  const key = process.env.ANTHROPIC_API_KEY;
  if (!key) return json(501, { error: 'ANTHROPIC_API_KEY is not configured' });

  let req;
  try { req = JSON.parse(event.body || '{}'); }
  catch (e) { return json(400, { error: 'bad JSON' }); }

  const lang = ['ro', 'ru', 'en'].includes(req.lang) ? req.lang : 'ro';

  try {
    if (req.mode === 'parse') {
      const q = String(req.query || '').slice(0, 300);
      if (!q) return json(400, { error: 'empty query' });
      const text = await anthropic(key, {
        model: MODEL,
        max_tokens: 200,
        system: PARSE_SYSTEM,
        messages: [{ role: 'user', content: q }]
      });
      let filters;
      try { filters = JSON.parse(text.replace(/^```(?:json)?|```$/g, '').trim()); }
      catch (e) { return json(200, { filters: null }); }
      return json(200, { filters });
    }

    // ---- chat
    const msgs = (Array.isArray(req.messages) ? req.messages : [])
      .filter(m => m && (m.role === 'user' || m.role === 'assistant') && m.content)
      .slice(-MAX_TURNS)
      .map(m => ({ role: m.role, content: String(m.content).slice(0, 2000) }));
    if (!msgs.length) return json(400, { error: 'no messages' });

    let text = await anthropic(key, {
      model: MODEL,
      max_tokens: 700,
      system: CHAT_SYSTEM(lang),
      messages: msgs
    });

    // pull the handle list off the end and hand it back separately, so the browser
    // renders those products from its own data rather than from the model's prose
    let handles = [];
    text = text.replace(/\[\[handles:\s*([^\]]*)\]\]\s*$/i, (_, list) => {
      handles = list.split(',').map(s => s.trim()).filter(Boolean);
      return '';
    }).trim();

    return json(200, { reply: text, handles });
  } catch (err) {
    console.error(err);
    return json(502, { error: 'upstream failed' });
  }
};
