// Run: node --test tests/js/   (no network; Yahoo responses are mocked)
import test from "node:test";
import assert from "node:assert/strict";
import { handle, toYahoo, parseChart } from "../../netlify/functions/quotes.mjs";

const chart = (price, prev, ts = 1795000000) => ({
  chart: { result: [{ meta: { regularMarketPrice: price, chartPreviousClose: prev, regularMarketTime: ts, currency: "INR",
    exchangeName: "NSI", regularMarketDayHigh: price + 5, regularMarketDayLow: price - 5, regularMarketVolume: 12345 },
    timestamp: [ts - 120, ts - 60, ts], indicators: { quote: [{ close: [prev, null, price] }] } }], error: null },
});

function mockFetch(map) {
  const calls = [];
  const f = async (url) => {
    calls.push(url);
    const t = decodeURIComponent(url.split("/chart/")[1].split("?")[0]);
    const v = map[t];
    if (v === undefined) return { ok: false, status: 404, json: async () => ({}) };
    if (v === 429) return { ok: false, status: 429, json: async () => ({}) };
    return { ok: true, status: 200, json: async () => v };
  };
  f.calls = calls;
  return f;
}

test("symbol mapping and validation", () => {
  assert.equal(toYahoo("reliance"), "RELIANCE.NS");
  assert.equal(toYahoo("M&M"), "M&M.NS");
  assert.equal(toYahoo("BAJAJ-AUTO"), "BAJAJ-AUTO.NS");
  assert.equal(toYahoo("^NSEI"), "^NSEI");
  assert.equal(toYahoo("500325.BO"), "500325.BO");
  assert.equal(toYahoo("../etc/passwd"), null);
  assert.equal(toYahoo("A B"), null);
  assert.equal(toYahoo("<script>"), null);
});

test("parseChart computes change and keeps Yahoo's timestamp", () => {
  const q = parseChart(chart(110, 100, 1795000000));
  assert.equal(q.price, 110);
  assert.ok(Math.abs(q.change_pct - 10) < 1e-9);
  assert.equal(q.market_time, new Date(1795000000 * 1000).toISOString());
  assert.throws(() => parseChart({ chart: { result: null, error: { description: "No data found" } } }), /No data found/);
});

test("batch quotes: partial failures are reported, never invented", async () => {
  const f = mockFetch({ "RELIANCE.NS": chart(1300, 1290), "^NSEI": chart(24000, 24100), "TCS.NS": 429 });
  const res = await handle(new Request("https://x/api/quotes?symbols=RELIANCE,^NSEI,TCS,BAD SYM,NOPE"), f);
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.deepEqual(Object.keys(body.quotes).sort(), ["RELIANCE", "^NSEI"]);
  assert.equal(body.errors.TCS, "HTTP 429");
  assert.equal(body.errors["BAD SYM"], "invalid symbol");
  assert.equal(body.errors.NOPE, "HTTP 404");
  assert.match(body.data_type, /Delayed/);
  assert.equal(res.headers.get("Netlify-Vary"), "query");
  assert.ok(!f.calls.some((u) => u.includes("BAD")));
});

test("all failures -> 502 so the page falls back to end-of-day data", async () => {
  const res = await handle(new Request("https://x/api/quotes?symbols=A,B"), mockFetch({}));
  assert.equal(res.status, 502);
});

test("limits: empty and oversized requests are rejected", async () => {
  assert.equal((await handle(new Request("https://x/api/quotes"), mockFetch({}))).status, 400);
  const many = Array.from({ length: 61 }, (_, i) => "S" + i).join(",");
  assert.equal((await handle(new Request("https://x/api/quotes?symbols=" + many), mockFetch({}))).status, 400);
});

test("intraday series drops null points", async () => {
  const res = await handle(new Request("https://x/api/quotes?intraday=RELIANCE"), mockFetch({ "RELIANCE.NS": chart(1300, 1290) }));
  const body = await res.json();
  assert.equal(body.points.length, 2);
  assert.equal(body.quote.price, 1300);
  assert.ok(!("timestamps" in body.quote));
});
