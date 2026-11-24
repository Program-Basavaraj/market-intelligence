/*
 * Netlify Function: delayed quotes and today's intraday line from Yahoo Finance's public chart endpoint.
 *
 *   GET /api/quotes?symbols=RELIANCE,TCS,^NSEI      -> latest delayed quote per symbol
 *   GET /api/quotes?intraday=RELIANCE               -> today's 1-minute closes for one symbol
 *
 * Honesty rules (also shown on the website):
 *   - Unofficial source. Quotes may be delayed (seconds to ~15 minutes) and may fail or be throttled.
 *   - Every quote carries Yahoo's own market timestamp; nothing is invented or carried forward silently.
 *   - Results are cached at Netlify's CDN for 30 s so many page views make few upstream calls.
 */

const YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/";
const UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36";
const MAX_SYMBOLS = 60;
const CONCURRENCY = 8;
const SYMBOL_RE = /^\^?[A-Z0-9&\-]{1,20}(\.(NS|BO))?$/;

/** NSE symbol -> Yahoo ticker. Indices (^NSEI) and explicit .NS/.BO tickers pass through. */
export function toYahoo(sym) {
  const s = String(sym || "").trim().toUpperCase();
  if (!SYMBOL_RE.test(s)) return null;
  if (s.startsWith("^") || s.endsWith(".NS") || s.endsWith(".BO")) return s;
  return s + ".NS";
}

export function parseChart(json) {
  const r = json?.chart?.result?.[0];
  if (!r || !r.meta) {
    const err = json?.chart?.error?.description || "no data";
    throw new Error(err);
  }
  const m = r.meta;
  const price = m.regularMarketPrice;
  const prev = m.chartPreviousClose ?? m.previousClose;
  if (typeof price !== "number") throw new Error("no price in response");
  return {
    price,
    prev_close: typeof prev === "number" ? prev : null,
    change_pct: typeof prev === "number" && prev ? ((price / prev) - 1) * 100 : null,
    day_high: m.regularMarketDayHigh ?? null,
    day_low: m.regularMarketDayLow ?? null,
    volume: m.regularMarketVolume ?? null,
    currency: m.currency || "INR",
    exchange: m.exchangeName || m.fullExchangeName || null,
    market_time: m.regularMarketTime ? new Date(m.regularMarketTime * 1000).toISOString() : null,
    timestamps: r.timestamp || [],
    closes: r.indicators?.quote?.[0]?.close || [],
  };
}

async function fetchChart(ticker, fetchImpl, { interval = "1d", range = "1d" } = {}) {
  const url = `${YAHOO}${encodeURIComponent(ticker)}?interval=${interval}&range=${range}&includePrePost=false`;
  const res = await fetchImpl(url, { headers: { "User-Agent": UA, Accept: "application/json" } });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return parseChart(await res.json());
}

async function pool(items, n, fn) {
  const out = new Array(items.length);
  let i = 0;
  const workers = Array.from({ length: Math.min(n, items.length) }, async () => {
    while (i < items.length) {
      const k = i++;
      out[k] = await fn(items[k]);
    }
  });
  await Promise.all(workers);
  return out;
}

function json(body, status = 200, cacheSeconds = 30) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "public, max-age=15",
      "Netlify-CDN-Cache-Control": `public, s-maxage=${cacheSeconds}, stale-while-revalidate=30`,
      "Netlify-Vary": "query",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

export async function handle(req, fetchImpl = fetch) {
  const url = new URL(req.url);
  const fetchedAt = new Date().toISOString();
  const base = { source: "Yahoo Finance (unofficial)", data_type: "Delayed quote — not guaranteed real-time", fetched_at: fetchedAt };

  const intraday = url.searchParams.get("intraday");
  if (intraday) {
    const t = toYahoo(intraday);
    if (!t) return json({ ...base, error: "invalid symbol" }, 400, 300);
    try {
      const c = await fetchChart(t, fetchImpl, { interval: "1m", range: "1d" });
      const points = c.timestamps.map((ts, i) => [new Date(ts * 1000).toISOString(), c.closes[i]]).filter((p) => typeof p[1] === "number");
      const { timestamps, closes, ...quote } = c;
      return json({ ...base, symbol: intraday.toUpperCase(), ticker: t, quote, points }, 200, 60);
    } catch (e) {
      return json({ ...base, symbol: intraday.toUpperCase(), error: String(e.message || e) }, 502, 20);
    }
  }

  const raw = (url.searchParams.get("symbols") || "").split(",").map((s) => s.trim()).filter(Boolean);
  if (!raw.length) return json({ ...base, error: "pass ?symbols=SYM1,SYM2" }, 400, 300);
  if (raw.length > MAX_SYMBOLS) return json({ ...base, error: `at most ${MAX_SYMBOLS} symbols per request` }, 400, 300);
  const pairs = raw.map((s) => [s.toUpperCase(), toYahoo(s)]);
  const quotes = {}, errors = {};
  await pool(pairs, CONCURRENCY, async ([sym, t]) => {
    if (!t) { errors[sym] = "invalid symbol"; return; }
    try {
      const { timestamps, closes, ...q } = await fetchChart(t, fetchImpl);
      quotes[sym] = q;
    } catch (e) {
      errors[sym] = String(e.message || e).slice(0, 120);
    }
  });
  const status = Object.keys(quotes).length ? 200 : 502;
  return json({ ...base, quotes, errors }, status, status === 200 ? 30 : 15);
}

export default async (req) => handle(req);

export const config = { path: "/api/quotes" };
