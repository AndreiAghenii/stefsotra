/* Server side of the three forms: the order basket, the contact message and the product
 * review.
 *
 * They were written against Netlify Forms, which catches a urlencoded POST to any path on
 * the site and files it for you. Vercel does not do that, so every submission has been
 * falling through to the mail-client fallback in the page -- which works, but only for a
 * customer who has a mail client set up and presses send in it. This is the path that does
 * not depend on either.
 *
 * No dependencies on purpose: this repo has no package.json and no npm install step, so
 * delivery goes over fetch to whatever is configured.
 *
 *   RESEND_API_KEY + FORM_TO   email each submission (https://resend.com, free tier)
 *   FORM_WEBHOOK_URL           POST the JSON somewhere -- a sheet, Zapier, your own box
 *
 * Set either in Vercel -> Project Settings -> Environment Variables. With neither set this
 * answers 501 and the page falls back to the mail client, exactly as it does today, so
 * nothing gets worse while it is unconfigured and nothing is ever silently swallowed.
 */

// What each form must carry to be worth delivering, and what to title it.
const FORMS = {
  'quote-request': { need: ['name', 'phone'], subject: 'Comandă nouă — stefsotra.md' },
  'contact': { need: ['name', 'message'], subject: 'Mesaj de pe stefsotra.md' },
  'product-review': { need: ['name', 'text'], subject: 'Recenzie produs — stefsotra.md' },
};

// Both spellings the pages use. A filled honeypot is a bot: answer 200 so it learns
// nothing, and drop the submission.
const HONEYPOTS = ['company', 'bot-field'];

const MAX_FIELD = 5000;

function send(res, code, body) {
  res.status(code).setHeader('Content-Type', 'application/json; charset=utf-8');
  res.end(JSON.stringify(body));
}

function fields(req) {
  const b = req.body;
  if (!b) return {};
  if (typeof b !== 'string') return b;
  // A raw string means the runtime did not recognise the content type. Do not assume
  // which of the two it is: URLSearchParams happily turns a JSON document into one
  // nonsense key, and the order would then be refused as an unknown form.
  const t = b.trim();
  if (t.startsWith('{')) {
    try { return JSON.parse(t); } catch (e) { /* fall through to urlencoded */ }
  }
  return Object.fromEntries(new URLSearchParams(b));
}

function text(form, data) {
  const skip = new Set(['form-name', ...HONEYPOTS]);
  return Object.entries(data)
    .filter(([k, v]) => !skip.has(k) && String(v).trim())
    .map(([k, v]) => `${k}: ${String(v).slice(0, MAX_FIELD)}`)
    .join('\n');
}

async function deliver(subject, body) {
  const to = process.env.FORM_TO;
  if (process.env.RESEND_API_KEY && to) {
    const r = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${process.env.RESEND_API_KEY}`,
        'Content-Type': 'application/json',
      },
      // from must be a domain verified with Resend; FORM_FROM overrides it.
      body: JSON.stringify({
        from: process.env.FORM_FROM || 'Stefsotra <onboarding@resend.dev>',
        to: to.split(',').map((s) => s.trim()).filter(Boolean),
        subject,
        text: body,
      }),
    });
    if (!r.ok) throw new Error(`resend ${r.status}: ${(await r.text()).slice(0, 200)}`);
    return 'email';
  }
  if (process.env.FORM_WEBHOOK_URL) {
    const r = await fetch(process.env.FORM_WEBHOOK_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subject, body }),
    });
    if (!r.ok) throw new Error(`webhook ${r.status}`);
    return 'webhook';
  }
  return null;                                    // nothing configured
}

module.exports = async (req, res) => {
  if (req.method !== 'POST') return send(res, 405, { error: 'POST only' });

  const data = fields(req);
  const name = data['form-name'];
  const spec = FORMS[name];
  if (!spec) return send(res, 400, { error: 'unknown form' });

  if (HONEYPOTS.some((h) => String(data[h] || '').trim())) {
    return send(res, 200, { ok: true });         // a bot; say nothing useful
  }

  const missing = spec.need.filter((k) => !String(data[k] || '').trim());
  if (missing.length) return send(res, 422, { error: 'missing', fields: missing });

  let via;
  try {
    via = await deliver(spec.subject, text(name, data));
  } catch (err) {
    // Delivery is configured but broke. Say so plainly: the page falls back to the mail
    // client on any non-2xx, so the customer still gets their order out.
    console.error('form delivery failed', err);
    return send(res, 502, { error: 'delivery failed' });
  }

  if (!via) {
    return send(res, 501, {
      error: 'not configured',
      hint: 'set RESEND_API_KEY and FORM_TO, or FORM_WEBHOOK_URL',
    });
  }
  return send(res, 200, { ok: true, via });
};
