/* Market Intelligence — static dashboard (no build step, no framework).
 * Reads JSON produced by the Python pipeline. All text from data files is HTML-escaped. */
(() => {
  "use strict";
  const CFG = window.MI_CONFIG || { dataBase: "./data/", learnUrl: "./learn.json" };
  const BASE = CFG.dataBase.endsWith("/") ? CFG.dataBase : CFG.dataBase + "/";
  const $ = (s, el = document) => el.querySelector(s);
  const view = $("#view");
  const cache = new Map();

  // ------------------------------------------------------------------ utils
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const safeUrl = (u) => (/^https?:\/\//i.test(String(u || "")) ? esc(u) : "#");
  const isNum = (v) => typeof v === "number" && isFinite(v);
  const fmt = (v, d = 2) => (isNum(v) ? v.toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d }) : "—");
  const inr = (v, d = 2) => (isNum(v) ? "₹" + fmt(v, d) : "—");
  const cr = (v) => (isNum(v) ? "₹" + fmt(v / 1e7, 0) + " cr" : "—");
  const chg = (v, d = 2) => (isNum(v) ? `<span class="${v > 0 ? "up" : v < 0 ? "down" : ""}">${v > 0 ? "▲ +" : v < 0 ? "▼ " : ""}${fmt(v, d)}%</span>` : "—");
  const dt = (s) => { if (!s) return "—"; const d = new Date(s); return isNaN(d) ? esc(s) : d.toLocaleString(LOC(), { dateStyle: "medium", timeStyle: s.length > 10 ? "short" : undefined, timeZone: "Asia/Kolkata" }); };
  const day = (s) => (s ? new Date(s).toLocaleDateString(LOC(), { dateStyle: "medium", timeZone: "Asia/Kolkata" }) : "—");
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const stockLink = (file, sym) => `<a href="#/stock/${encodeURIComponent(file || sym)}">${esc(sym)}</a>`;
  const I18N = window.I18N || { lang: "en", t: (x) => x, locale: () => "en-IN", start() {}, set() {} };
  const LOC = () => I18N.locale();
  const T = (x) => I18N.t(x);
  // heading in the selected language only (CSS hides the other); bp() = same for longer authored HTML
  const bi = (en, kn) => `<span class="t-en">${esc(en)}</span><span class="t-kn kn">${esc(kn)}</span>`;
  const bp = (en, kn) => `<span class="t-en">${en}</span><span class="t-kn kn">${kn}</span>`;

  async function getJSON(name, { base = BASE, fresh = false } = {}) {
    const url = name.startsWith("http") || name.startsWith("./") ? name : base + name;
    if (!fresh && cache.has(url)) return cache.get(url);
    const p = fetch(url + (url.includes("?") ? "&" : "?") + "v=" + Math.floor(Date.now() / 300000), { cache: "no-cache" })
      .then((r) => { if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${url}`); return r.json(); });
    cache.set(url, p);
    p.catch(() => cache.delete(url));
    return p;
  }

  function labelPill(label) {
    const t = { bullish: "Bullish", bearish: "Bearish", neutral: "Neutral", insufficient: "Insufficient evidence" }[label] || label || "—";
    return `<span class="pill ${esc(label)}">${label === "bullish" ? "▲" : label === "bearish" ? "▼" : label === "neutral" ? "◆" : "○"} ${esc(t)}</span>`;
  }
  function probBar(p) {
    if (!p) return `<span class="muted">—</span>`;
    return `<div class="pbar" title="Bearish ${p.bearish}% · Neutral ${p.neutral}% · Bullish ${p.bullish}%">
      <span class="b" style="width:${p.bearish}%"></span><span class="n" style="width:${p.neutral}%"></span><span class="u" style="width:${p.bullish}%"></span></div>
      <div class="ptext">▼ ${fmt(p.bearish, 1)}% · ◆ ${fmt(p.neutral, 1)}% · ▲ ${fmt(p.bullish, 1)}%</div>`;
  }
  function sparkline(values, w = 160, h = 36) {
    if (!values || values.length < 2) return "";
    const lo = Math.min(...values), hi = Math.max(...values), r = hi - lo || 1;
    const pts = values.map((v, i) => `${((i / (values.length - 1)) * (w - 2) + 1).toFixed(1)},${(h - 2 - ((v - lo) / r) * (h - 4)).toFixed(1)}`).join(" ");
    const col = values[values.length - 1] >= values[0] ? "var(--up)" : "var(--down)";
    return `<svg width="100%" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" height="${h}" aria-hidden="true"><polyline fill="none" stroke="${col}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" points="${pts}"/></svg>`;
  }
  function sortableTable(el, rows, columns, { pageSize = 100, initialSort = null } = {}) {
    let sortKey = initialSort?.key, dir = initialSort?.dir || -1, limit = pageSize;
    const render = () => {
      const data = [...rows];
      if (sortKey) {
        const col = columns.find((c) => c.key === sortKey);
        const val = col.sort || ((r) => r[sortKey]);
        data.sort((a, b) => { const x = val(a), y = val(b); if (x == null) return 1; if (y == null) return -1; return (x > y ? 1 : x < y ? -1 : 0) * dir; });
      }
      el.innerHTML = `<div class="table-wrap"><table><thead><tr>${columns.map((c) => `<th class="${c.sortable === false ? "" : "sortable"} ${c.num ? "num" : ""}" data-k="${c.key}">${c.title}${sortKey === c.key ? (dir > 0 ? " ↑" : " ↓") : ""}</th>`).join("")}</tr></thead>
        <tbody>${data.slice(0, limit).map((r) => `<tr>${columns.map((c) => `<td class="${c.num ? "num" : ""} ${c.cls || ""}">${c.render ? c.render(r) : esc(r[c.key])}</td>`).join("")}</tr>`).join("") || `<tr><td colspan="${columns.length}" class="empty">No rows match these filters.</td></tr>`}</tbody></table></div>
        ${data.length > limit ? `<p class="muted">Showing ${limit} of ${data.length}. <button class="btn" data-more>Show more</button></p>` : `<p class="muted">${data.length} rows</p>`}`;
      el.querySelectorAll("th.sortable").forEach((th) => th.addEventListener("click", () => { const k = th.dataset.k; dir = sortKey === k ? -dir : -1; sortKey = k; render(); }));
      el.querySelector("[data-more]")?.addEventListener("click", () => { limit += pageSize; render(); liveTick(); });
      applyQuotes(el);
    };
    render();
  }

  // ------------------------------------------------------------------ plotting
  const plotReady = () => new Promise((res) => { const t = () => (window.Plotly ? res() : setTimeout(t, 60)); t(); });
  function baseLayout(extra = {}) {
    return Object.assign({
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      font: { family: "Inter, system-ui, sans-serif", size: 12, color: css("--text-secondary") },
      margin: { l: 56, r: 16, t: 10, b: 32 }, hovermode: "x unified", showlegend: true,
      legend: { orientation: "h", y: 1.08, x: 0, font: { color: css("--text-secondary") } },
      xaxis: { gridcolor: css("--border"), linecolor: css("--border"), zeroline: false, rangeslider: { visible: false }, type: "category", nticks: 8 },
      yaxis: { gridcolor: css("--border"), linecolor: css("--border"), zeroline: false, tickformat: ",.0f" },
      hoverlabel: { bgcolor: css("--surface-1"), bordercolor: css("--border"), font: { color: css("--text-primary") } },
    }, extra);
  }
  async function plot(el, traces, layout = {}) {
    await plotReady();
    window.Plotly.newPlot(el, traces, baseLayout(layout), { displaylogo: false, responsive: true, modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"] });
  }

  // ------------------------------------------------------------------ live (delayed) quotes
  // Elements marked data-live-price="SYM" / data-live-chg="SYM" are filled from the Netlify Function.
  // If the function is missing or Yahoo fails, the end-of-day values already on the page stay visible.
  const LIVE = Object.assign({ enabled: true, endpoint: "/api/quotes", refreshSeconds: 60, maxSymbols: 120 }, CFG.liveQuotes || {});
  const liveState = { quotes: {}, ok: null, at: null, error: null, failures: 0 };
  const liveHooks = [];
  let liveTimer = null;
  function marketOpenIST(now = new Date()) {
    const p = Object.fromEntries(new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false })
      .formatToParts(now).map((x) => [x.type, x.value]));
    const mins = Number(p.hour) * 60 + Number(p.minute);
    return !["Sat", "Sun"].includes(p.weekday) && mins >= 555 && mins <= 935;   // 09:15–15:35 IST
  }
  const timeIST = (iso) => (iso ? new Date(iso).toLocaleTimeString(LOC(), { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "Asia/Kolkata" }) + " IST" : "—");
  async function fetchQuotes(symbols) {
    const out = {};
    for (let i = 0; i < symbols.length; i += 60) {
      const chunk = symbols.slice(i, i + 60);
      const r = await fetch(`${LIVE.endpoint}?symbols=${encodeURIComponent(chunk.join(","))}`, { cache: "no-cache" });
      if (!r.ok && r.status !== 502) throw new Error(`quotes HTTP ${r.status}`);
      const body = await r.json();
      Object.assign(out, body.quotes || {});
      if (!Object.keys(body.quotes || {}).length) throw new Error("quote source returned no data");
    }
    return out;
  }
  function applyQuotes(root = document) {
    const Q = liveState.quotes;
    root.querySelectorAll("[data-live-price]").forEach((el) => {
      const q = Q[el.dataset.livePrice];
      if (!q) return;
      el.innerHTML = (el.dataset.fmt === "num" ? fmt(q.price) : inr(q.price)) + `<span class="live-tag" title="Delayed quote from Yahoo Finance at ${esc(timeIST(q.market_time))}">●</span>`;
    });
    root.querySelectorAll("[data-live-chg]").forEach((el) => {
      const q = Q[el.dataset.liveChg];
      if (q && isNum(q.change_pct)) el.innerHTML = chg(q.change_pct);
    });
    root.querySelectorAll("[data-live-time]").forEach((el) => {
      const q = Q[el.dataset.liveTime];
      if (q) el.textContent = `delayed quote · ${timeIST(q.market_time)}`;
    });
  }
  function liveBadge() {
    const b = $("#liveBadge");
    if (!LIVE.enabled) { b.hidden = true; return; }
    b.hidden = false;
    const open = marketOpenIST();
    if (liveState.ok) {
      const latest = Object.values(liveState.quotes).map((q) => q.market_time).filter(Boolean).sort().pop();
      b.className = "data-badge live";
      b.innerHTML = `<span class="dot"></span><span><strong>${open ? "Delayed live quotes" : "Market closed"}</strong> · last quote ${timeIST(latest)}${open ? ` · refresh ${LIVE.refreshSeconds}s` : ""}</span>`;
    } else if (liveState.ok === false) {
      b.className = "data-badge stale";
      b.innerHTML = `<span class="dot"></span><span>Live quotes unavailable — showing end-of-day prices</span>`;
      b.title = liveState.error || "";
    }
  }
  async function liveTick() {
    if (!LIVE.enabled || document.hidden || liveState.failures >= 3) return;
    const syms = [...new Set([...document.querySelectorAll("[data-live-price],[data-live-chg]")].map((e) => e.dataset.livePrice || e.dataset.liveChg))].slice(0, LIVE.maxSymbols);
    if (!syms.length && !liveHooks.length) return;
    try {
      if (syms.length) Object.assign(liveState.quotes, await fetchQuotes(syms));
      liveState.ok = true; liveState.failures = 0; liveState.at = new Date().toISOString();
      applyQuotes();
      liveBadge();
      liveHooks.forEach((h) => Promise.resolve().then(h).catch((err) => console.warn("live hook:", err.message)));
    } catch (e) {
      liveState.failures += 1; liveState.error = e.message;
      if (!Object.keys(liveState.quotes).length) liveState.ok = false;
    }
    liveBadge();
  }
  function startLive() {
    clearInterval(liveTimer);
    liveTick();
    liveTimer = setInterval(() => { if (marketOpenIST()) liveTick(); }, LIVE.refreshSeconds * 1000);
  }
  document.addEventListener("visibilitychange", () => { if (!document.hidden && marketOpenIST()) liveTick(); });

  // ------------------------------------------------------------------ navigation
  const NAV = [
    ["Overview", [["#/", "Market overview", "ಮಾರುಕಟ್ಟೆ ಅವಲೋಕನ"]]],
    ["Scanners", [["#/scanner", "Stock scanner", "ಷೇರು ಶೋಧಕ"], ["#/scanner/bullish", "Bullish", "ಏರುಮುಖ"], ["#/scanner/bearish", "Bearish", "ಇಳಿಮುಖ"],
      ["#/scanner/neutral", "Neutral", "ತಟಸ್ಥ"], ["#/scanner/smallcap", "Small-cap", "ಸಣ್ಣ ಕಂಪನಿ"], ["#/scanner/midcap", "Mid-cap", "ಮಧ್ಯಮ ಕಂಪನಿ"]]],
    ["News", [["#/news", "Market news", "ಮಾರುಕಟ್ಟೆ ಸುದ್ದಿ"], ["#/orders", "Order wins", "ಆರ್ಡರ್ ಗೆಲುವುಗಳು"], ["#/announcements", "Exchange filings", "ಅಧಿಕೃತ ಪ್ರಕಟಣೆಗಳು"]]],
    ["Analysis", [["#/swing", "Swing predictions", "ಸ್ವಿಂಗ್ ಮುನ್ಸೂಚನೆ"], ["#/intraday", "Intraday", "ದಿನದೊಳಗಿನ"], ["#/compare", "Compare stocks", "ಹೋಲಿಕೆ"],
      ["#/backtest", "Backtesting", "ಹಿಂಪರೀಕ್ಷೆ"], ["#/model", "Model performance", "ಮಾದರಿ ಕಾರ್ಯಕ್ಷಮತೆ"]]],
    ["More", [["#/learn", "Learning centre", "ಕಲಿಕಾ ಕೇಂದ್ರ"], ["#/alerts", "Alerts", "ಎಚ್ಚರಿಕೆಗಳು"], ["#/status", "System status", "ವ್ಯವಸ್ಥೆಯ ಸ್ಥಿತಿ"]]],
  ];
  function renderNav() {
    $("#nav").innerHTML = NAV.map(([g, items]) => `<div class="nav-group">${esc(g)}</div>` +
      items.map(([h, en, kn]) => `<a href="${h}" data-h="${h}">${bi(en, kn)}</a>`).join("")).join("");
  }
  function markNav() {
    const h = location.hash || "#/";
    document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.h === h || (a.dataset.h !== "#/" && h.startsWith(a.dataset.h) && !NAV.flatMap((g) => g[1]).some(([x]) => x !== a.dataset.h && x.startsWith(a.dataset.h) && h.startsWith(x)))));
  }

  // ------------------------------------------------------------------ status badge & setup screen
  let STATUS = null;
  async function loadStatus() {
    try {
      STATUS = await getJSON("status.json", { fresh: true });
      const b = $("#dataBadge");
      const stale = STATUS.market_date && (Date.now() - new Date(STATUS.market_date).getTime()) / 864e5 > 4;
      b.classList.toggle("stale", !!stale);
      b.innerHTML = `<span class="dot"></span><span><strong>Analysis: end-of-day</strong> · ${day(STATUS.market_date)}${stale ? " · ⚠ may be stale" : ""}</span>`;
      b.title = `Market date ${day(STATUS.market_date)} · pipeline updated ${dt(STATUS.run_finished)}`;
    } catch (e) {
      STATUS = null;
      $("#dataBadge").innerHTML = `<span class="dot"></span><span>No data yet</span>`;
    }
  }
  function setupScreen(err) {
    view.innerHTML = `<div class="page-head"><div><h1>${bi("Welcome — no data has been generated yet", "ಸ್ವಾಗತ — ಇನ್ನೂ ದತ್ತಾಂಶ ತಯಾರಾಗಿಲ್ಲ")}</h1>
      <p>${bp(`The website is deployed, but the daily data job has not produced data at <code>${esc(BASE)}</code> yet.`,
              `ವೆಬ್‌ಸೈಟ್ ಸಿದ್ಧವಾಗಿದೆ, ಆದರೆ ದೈನಂದಿನ ದತ್ತಾಂಶ ಕೆಲಸ ಇನ್ನೂ ಈ ವಿಳಾಸದಲ್ಲಿ ದತ್ತಾಂಶ ತಯಾರಿಸಿಲ್ಲ: <code>${esc(BASE)}</code>`)}</p></div></div>
      <div class="card"><h2>${bi("Finish setup", "ಸಿದ್ಧತೆ ಪೂರ್ಣಗೊಳಿಸಿ")}</h2>
      ${bp(`<ol class="clean">
        <li>Push this project to a <strong>public</strong> GitHub repository.</li>
        <li>In GitHub → <em>Actions</em>, enable workflows and run <strong>“Daily market pipeline”</strong> once (Run workflow).</li>
        <li>Edit <code>site/js/config.js</code> and set <code>dataBase</code> to <code>https://raw.githubusercontent.com/&lt;user&gt;/&lt;repo&gt;/data/</code>, then redeploy Netlify once.</li>
        <li>Optional: add <code>TELEGRAM_BOT_TOKEN</code> and <code>TELEGRAM_CHAT_ID</code> as GitHub Secrets for alerts.</li>
      </ol>
      <p class="muted">Full guide: <code>docs/SETUP.md</code> in the project. Technical detail: ${esc(err?.message || "")}</p>`,
      `<ol class="clean">
        <li>ಈ ಯೋಜನೆಯನ್ನು <strong>ಸಾರ್ವಜನಿಕ (public)</strong> GitHub repository ಗೆ ಹಾಕಿ.</li>
        <li>GitHub ನಲ್ಲಿ <em>Actions</em> ತೆರೆಯಿರಿ ಮತ್ತು <strong>“Daily market pipeline”</strong> ಅನ್ನು ಒಮ್ಮೆ ಓಡಿಸಿ (Run workflow).</li>
        <li><code>site/js/config.js</code> ನಲ್ಲಿ <code>dataBase</code> ಅನ್ನು <code>https://raw.githubusercontent.com/&lt;user&gt;/&lt;repo&gt;/data/</code> ಎಂದು ಬದಲಿಸಿ; ನಂತರ Netlify ಅನ್ನು ಒಮ್ಮೆ ಮರುನಿಯೋಜಿಸಿ.</li>
        <li>ಐಚ್ಛಿಕ: ಎಚ್ಚರಿಕೆಗಳಿಗಾಗಿ <code>TELEGRAM_BOT_TOKEN</code> ಮತ್ತು <code>TELEGRAM_CHAT_ID</code> ಅನ್ನು GitHub Secrets ಆಗಿ ಸೇರಿಸಿ.</li>
      </ol>
      <p class="muted">ಸಂಪೂರ್ಣ ಮಾರ್ಗದರ್ಶಿ: <code>docs/SETUP.md</code>. ತಾಂತ್ರಿಕ ವಿವರ: ${esc(err?.message || "")}</p>`)}</div>
      <div class="section"><a class="btn" href="#/learn">Meanwhile, open the Learning centre →</a></div>`;
  }

  // ------------------------------------------------------------------ pages
  async function pageOverview() {
    const [ov, sc, news] = await Promise.all([getJSON("overview.json"), getJSON("scanner.json"), getJSON("news.json").catch(() => ({ items: [] }))]);
    const idx = ov.indices.filter((i) => i.available);
    const count = (h, l) => sc.rows.filter((r) => r.horizons?.[h]?.label === l).length;
    const hs = Object.keys(sc.rows[0]?.horizons || {});
    const b = ov.breadth || {};
    const topNews = [...(news.items || [])].filter((n) => n.symbol).sort((a, b) => b.importance - a.importance).slice(0, 8);
    view.innerHTML = `
      <div class="page-head"><div><h1>${bi("Market overview", "ಮಾರುಕಟ್ಟೆ ಅವಲೋಕನ")}</h1>
      <p>${bp(`Indian equities, end-of-day as of <strong>${day(ov.market_date)}</strong>. Index values are delayed and for research only.`,
          `ಭಾರತೀಯ ಷೇರುಗಳು — <strong>${day(ov.market_date)}</strong> ರ ದಿನದ ಅಂತ್ಯದ ದತ್ತಾಂಶ. ಸೂಚ್ಯಂಕ ಮೌಲ್ಯಗಳು ತಡವಾದವು; ಸಂಶೋಧನೆಗಾಗಿ ಮಾತ್ರ.`)}</p></div></div>
      ${ov.market_context?.nifty_below_200dma ? `<div class="notice"><strong>Market context:</strong> Nifty 50 is below its 200-day average — a weaker backdrop for bullish setups.</div>` : ""}
      <div class="grid g4">${idx.slice(0, 8).map((i) => `<div class="card tile"><div class="label">${esc(i.name)}</div>
        <div class="value" data-live-price="${esc(i.ticker)}" data-fmt="num">${fmt(i.last)}</div><div class="sub"><span data-live-chg="${esc(i.ticker)}">${chg(i.chg_1d)}</span> 1D · ${chg(i.chg_20d)} 1M</div>${sparkline(i.spark)}
        <div class="muted" style="font-size:11px"><span data-live-time="${esc(i.ticker)}">close ${day(i.date)}</span> · 6-month trend</div></div>`).join("") || `<div class="card">Index data unavailable — see System status.</div>`}</div>
      <div class="grid g4 section">
        <div class="card tile"><div class="label">${bi("Advances / Declines", "ಏರಿಕೆ / ಇಳಿಕೆ")}</div><div class="value">${b.advances ?? "—"} / ${b.declines ?? "—"}</div><div class="sub muted">A/D ratio ${fmt(b.ad_ratio)}</div></div>
        <div class="card tile"><div class="label">Above 200-day average</div><div class="value">${fmt(b.pct_above_200dma, 1)}%</div><div class="sub muted">of tracked stocks</div></div>
        <div class="card tile"><div class="label">Breakouts / Breakdowns</div><div class="value">${b.breakouts ?? "—"} / ${b.breakdowns ?? "—"}</div><div class="sub muted">20-day range, volume ≥ 1.5×</div></div>
        <div class="card tile"><div class="label">Model signals (${hs.map((h) => h + "d").join(" / ")})</div>
          <div class="value" style="font-size:1.1rem">${hs.map((h) => `<span class="up">▲${count(h, "bullish")}</span> <span class="down">▼${count(h, "bearish")}</span>`).join(" · ") || "—"}</div>
          <div class="sub muted">${hs.length && hs.every((h) => sc.rows.every((r) => r.horizons[h].label === "insufficient")) ? "Models not validated — no recommendations" : "validated thresholds only"}</div></div>
      </div>
      <div class="grid g2 section">
        <div class="card"><h2>${bi("Sector performance", "ವಲಯವಾರು ಸಾಧನೆ")}</h2><div id="sectorChart" class="chart"></div><p class="muted">Average 20-day change of tracked stocks per sector (equal-weighted).</p></div>
        <div class="card"><h2>${bi("Important news", "ಪ್ರಮುಖ ಸುದ್ದಿ")}<a href="#/news" style="font-size:12px">All news →</a></h2>
          ${topNews.map(newsRow).join("") || `<p class="muted">No matched news yet.</p>`}</div>
      </div>
      <div class="grid g3 section">
        ${["gainers", "losers", "volume_spikes"].map((k) => `<div class="card"><h2>${{ gainers: "Top gainers", losers: "Top losers", volume_spikes: "Unusual volume" }[k]}</h2>
          <div class="table-wrap"><table><thead><tr><th>Symbol</th><th class="num">Price</th><th class="num">1D</th><th class="num">Rel. vol</th></tr></thead><tbody>
          ${(ov.movers?.[k] || []).map((r) => `<tr><td class="sym">${stockLink(r.file, r.symbol)}</td><td class="num" data-live-price="${esc(r.symbol)}">${inr(r.price)}</td><td class="num" data-live-chg="${esc(r.symbol)}">${chg(r.chg_1d)}</td><td class="num">${fmt(r.rel_vol, 1)}×</td></tr>`).join("") || `<tr><td colspan="4" class="muted">None</td></tr>`}
          </tbody></table></div></div>`).join("")}
      </div>`;
    const sec = (ov.sectors || []).slice().sort((a, b) => a.chg_20d - b.chg_20d);
    if (sec.length) {
      plot($("#sectorChart"), [{ type: "bar", orientation: "h", y: sec.map((s) => s.sector), x: sec.map((s) => s.chg_20d),
        marker: { color: sec.map((s) => (s.chg_20d >= 0 ? css("--up") : css("--down"))) }, hovertemplate: "%{y}: %{x:.2f}%<extra></extra>", showlegend: false }],
        { height: Math.max(260, sec.length * 22 + 40), margin: { l: 190, r: 16, t: 6, b: 30 }, hovermode: "closest", bargap: 0.35,
          xaxis: { gridcolor: css("--border"), ticksuffix: "%", zeroline: true, zerolinecolor: css("--text-muted") }, yaxis: { automargin: true, type: "category" } });
    }
  }

  function newsRow(n) {
    const oa = n.order_analysis || {};
    return `<div class="flag"><div style="min-width:0">
      <div class="notranslate"><a href="${safeUrl(n.url)}" target="_blank" rel="noopener noreferrer nofollow">${esc(n.headline)}</a></div>
      <div class="muted" style="font-size:12px;display:flex;gap:6px;flex-wrap:wrap;margin-top:3px">
        ${n.verified ? `<span class="pill verified">Exchange filing</span>` : `<span class="pill">Media report</span>`}
        <span class="pill cat">${esc(n.category_label)}</span>
        ${n.symbol ? stockLink(n.symbol.replace(/[^A-Za-z0-9_-]/g, "_"), n.symbol) : ""}
        <span>${esc(n.source)}${n.also_reported_by?.length ? " +" + n.also_reported_by.length : ""}</span><span>· ${dt(n.published)}</span>
        <span>· impact ${fmt(n.importance, 0)}/100</span><span>· sentiment ${n.sentiment > 0 ? "+" : ""}${fmt(n.sentiment)}</span>
        ${isNum(oa.order_size_ratio_pct) ? `<span>· order = <strong>${fmt(oa.order_size_ratio_pct, 1)}%</strong> of revenue (${esc(oa.materiality)})</span>` : ""}
        ${n.repeat_of ? `<span>· similar to an earlier item</span>` : ""}
      </div>
      <details style="font-size:12.5px;margin-top:3px"><summary class="muted">${bi("Explain", "ವಿವರಣೆ")}</summary><p>${bp(esc(n.explain_en), esc(n.explain_kn))}</p></details>
    </div></div>`;
  }

  async function pageScanner(preset) {
    const sc = await getJSON("scanner.json");
    const rows = sc.rows;
    const hs = Object.keys(rows[0]?.horizons || { 5: {} });
    const sectors = [...new Set(rows.map((r) => r.sector))].sort();
    const st = { q: "", sector: "", cap: preset === "smallcap" ? "Small" : preset === "midcap" ? "Mid" : "", exch: "", h: hs.includes("5") ? "5" : hs[0],
      label: ["bullish", "bearish", "neutral"].includes(preset) ? preset : "", minP: 0, liquidOnly: true, minVol: 0 };
    const title = { bullish: "Bullish scanner", bearish: "Bearish scanner", neutral: "Neutral stocks", smallcap: "Small-cap scanner", midcap: "Mid-cap scanner" }[preset] || "Stock scanner";
    view.innerHTML = `<div class="page-head"><div><h1>${esc(title)}</h1><p>${bp(`Every tracked stock with its separate technical score, fundamental label, news sentiment and the calibrated model probabilities for the chosen swing horizon.
      <strong>Labels only appear when the model passed out-of-sample validation and the probability crossed a validated threshold.</strong>`,
      `ಪ್ರತಿ ಷೇರಿನ ತಾಂತ್ರಿಕ ಅಂಕ, ಮೂಲಭೂತ ಮೌಲ್ಯಮಾಪನ, ಸುದ್ದಿ ಭಾವನೆ ಮತ್ತು ಆಯ್ಕೆ ಮಾಡಿದ ಅವಧಿಯ ಮಾದರಿ ಸಂಭವನೀಯತೆಗಳು — ಎಲ್ಲವೂ ಪ್ರತ್ಯೇಕವಾಗಿ.
      <strong>ಮಾದರಿ ಹೊರಗಿನ ಪರೀಕ್ಷೆಯಲ್ಲಿ ಉತ್ತೀರ್ಣವಾಗಿ, ಸಂಭವನೀಯತೆ ಪರಿಶೀಲಿತ ಮಿತಿಯನ್ನು ದಾಟಿದಾಗ ಮಾತ್ರ ಏರುಮುಖ/ಇಳಿಮುಖ ಎಂದು ತೋರಿಸಲಾಗುತ್ತದೆ.</strong>`)}</p></div></div>
      <div class="filters">
        <input type="search" id="fq" placeholder="Filter symbol / name">
        <label>Horizon <select id="fh">${hs.map((h) => `<option value="${h}" ${h === st.h ? "selected" : ""}>${h} trading days</option>`).join("")}</select></label>
        <label>Sector <select id="fs"><option value="">All</option>${sectors.map((s) => `<option>${esc(s)}</option>`).join("")}</select></label>
        <label>Size <select id="fc"><option value="">All</option>${["Large", "Mid", "Small", "Unclassified"].map((c) => `<option ${c === st.cap ? "selected" : ""}>${c}</option>`).join("")}</select></label>
        <label>Exchange <select id="fe"><option value="">NSE (all)</option><option value="BSE">Also on BSE</option></select></label>
        <label>Min. probability <input type="number" id="fp" min="0" max="100" step="5" value="0" style="width:70px">%</label>
        <label>Min. rel. volume <input type="number" id="fv" min="0" step="0.5" value="0" style="width:64px">×</label>
        <label><input type="checkbox" id="fl" checked> Liquid only</label>
      </div>
      <div class="tabs" id="ftabs">${["", "bullish", "bearish", "neutral", "insufficient"].map((l) => `<button data-l="${l}" class="${l === st.label ? "active" : ""}">${l ? l[0].toUpperCase() + l.slice(1) : "All"}</button>`).join("")}</div>
      <div id="tbl"></div>`;
    const draw = () => {
      const q = st.q.toLowerCase();
      const data = rows.filter((r) => (!q || r.symbol.toLowerCase().includes(q) || (r.name || "").toLowerCase().includes(q)) &&
        (!st.sector || r.sector === st.sector) && (!st.cap || r.cap === st.cap) && (!st.exch || (r.exchanges || "").includes(st.exch)) &&
        (!st.label || r.horizons[st.h]?.label === st.label) && (!st.liquidOnly || r.liquid) && (!st.minVol || (r.rel_vol || 0) >= st.minVol) &&
        (!st.minP || Math.max(r.horizons[st.h]?.p?.bullish || 0, r.horizons[st.h]?.p?.bearish || 0) >= st.minP));
      const H = (r) => r.horizons[st.h] || {};
      sortableTable($("#tbl"), data, [
        { key: "symbol", title: "Stock", cls: "sym", render: (r) => `${stockLink(r.file, r.symbol)}<span class="name notranslate">${esc(r.name)}</span>` },
        { key: "sector", title: "Sector", render: (r) => `<span class="secondary">${esc(r.sector)}</span><br><small>${esc(r.cap)}</small>` },
        { key: "price", title: "Price", num: true, render: (r) => `<span data-live-price="${esc(r.symbol)}">${inr(r.price)}</span><br><small>EOD ${day(r.date)}${r.stale ? " ⚠" : ""}</small>` },
        { key: "chg_1d", title: "1D", num: true, render: (r) => `<span data-live-chg="${esc(r.symbol)}">${chg(r.chg_1d)}</span>` },
        { key: "chg_20d", title: "1M", num: true, render: (r) => chg(r.chg_20d) },
        { key: "rel_vol", title: "Rel. vol", num: true, render: (r) => (isNum(r.rel_vol) ? fmt(r.rel_vol, 1) + "×" : "—") },
        { key: "rsi", title: "RSI", num: true, render: (r) => fmt(r.rsi, 0) },
        { key: "tech_score", title: "Tech score", num: true, render: (r) => fmt(r.tech_score, 0) },
        { key: "fund_label", title: "Fundamentals", render: (r) => esc(r.fund_label || "n/a") },
        { key: "news_sent", title: "News", num: true, render: (r) => (isNum(r.news_sent) ? (r.news_sent > 0 ? "+" : "") + fmt(r.news_sent) : "—") },
        { key: "label", title: `${st.h}-day assessment`, sort: (r) => ({ bullish: 3, neutral: 2, bearish: 1 }[H(r).label] || 0), render: (r) => labelPill(H(r).label) },
        { key: "prob", title: "Probabilities", sort: (r) => H(r).p?.bullish, sortable: true, render: (r) => probBar(H(r).p) },
      ], { initialSort: { key: "prob", dir: -1 } });
    };
    const bind = (id, key, conv = (v) => v) => $(id).addEventListener("input", (e) => { st[key] = conv(e.target.type === "checkbox" ? e.target.checked : e.target.value); draw(); });
    bind("#fq", "q"); bind("#fh", "h"); bind("#fs", "sector"); bind("#fc", "cap"); bind("#fe", "exch"); bind("#fp", "minP", Number); bind("#fv", "minVol", Number); bind("#fl", "liquidOnly");
    $("#ftabs").addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return; st.label = b.dataset.l; $("#ftabs").querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b)); draw(); });
    draw();
  }

  async function pageStock(file) {
    const s = await getJSON(`stocks/${file}.json`);
    const rec = s.recommendation, q = s.quality, ch = s.chart, f = s.fundamentals, qs = s.quant;
    const last = ch.close[ch.close.length - 1], prev = ch.close[ch.close.length - 2];
    const ind = s.indicators;
    view.innerHTML = `
      <div class="page-head"><div><h1 class="notranslate">${esc(s.name)} <span class="muted">${esc(s.symbol)}</span></h1>
        <p>NSE: <strong>${esc(s.symbol)}</strong> ${s.bse_code ? `· BSE: <strong>${esc(s.bse_code)}</strong>` : ""} · ISIN ${esc(s.isin || "—")} · ${esc(s.sector || "—")} · ${esc(s.cap_category || "")}-cap <small>(${esc(s.cap_source || "")})</small></p></div>
        <div style="text-align:right"><div style="font-size:1.6rem;font-weight:650" data-live-price="${esc(s.symbol)}">${inr(last)}</div>
        <div><span data-live-chg="${esc(s.symbol)}">${chg(((last / prev) - 1) * 100)}</span> · <span data-live-time="${esc(s.symbol)}">close of ${day(q.last_date)}</span></div>
        <div class="muted" style="font-size:12px">End-of-day close: ${inr(last)} (${day(q.last_date)})</div></div></div>
      <div class="notice ${q.stale ? "critical" : "info"}"><strong>${esc(q.data_type)}</strong> · source: ${esc(q.provider)} · fetched ${dt(q.fetched_at)}${q.stale ? " · ⚠ data is stale" : ""}${!q.liquid ? " · ⚠ low liquidity" : ""}
        ${q.issues?.length ? `<br>Data-quality notes: ${q.issues.map(esc).join("; ")}` : ""}</div>

      <div class="card" id="intradayCard" hidden><h2>${bi("Today (delayed, 1-minute)", "ಇಂದಿನ ಬೆಲೆ ಚಲನೆ (ತಡವಾದ)")}<span class="muted" style="font-size:12px" id="intradayMeta"></span></h2>
        <div id="intradayChart" class="chart" style="min-height:200px"></div>
        <p class="muted">Delayed quotes from Yahoo Finance (unofficial). For viewing only — the assessments below use end-of-day data.</p></div>
      <h2 class="section">${bi("Research assessment", "ಸಂಶೋಧನಾ ಮೌಲ್ಯಮಾಪನ")}</h2>
      <div class="grid g4">${rec.horizons.map(horizonCard).join("")}
        <div class="card"><h3>Intraday</h3>${labelPill("insufficient")}<p class="muted">${esc(rec.intraday.reasons[0])}</p></div></div>

      <div class="grid g3 section">
        <div class="card"><h3>Technical justification <span class="muted">(score ${fmt(rec.technical.score, 0)} / ±100)</span></h3><ul class="clean">${rec.technical_justification.map((x) => `<li>${esc(x)}</li>`).join("")}</ul><p class="muted">${esc(rec.technical.note)}</p></div>
        <div class="card"><h3>Fundamental justification</h3><ul class="clean">${rec.fundamental_justification.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
        <div class="card"><h3>News justification</h3><ul class="clean">${rec.news_justification.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
      </div>
      <div class="grid g2 section">
        <div class="card"><h3>Scenarios (not instructions)</h3>${rec.scenarios?.reference_price ? `<dl class="kv">
          <dt>Reference price</dt><dd>${inr(rec.scenarios.reference_price)}</dd><dt>Entry scenario</dt><dd>${esc(rec.scenarios.entry_scenario)}</dd>
          <dt>Stop-loss scenario</dt><dd>${inr(rec.scenarios.stop_loss_scenario)}</dd><dt>Target scenario</dt><dd>${inr(rec.scenarios.target_scenario)}</dd>
          <dt>Risk / reward</dt><dd>${fmt(rec.scenarios.risk_reward)}</dd><dt>Support</dt><dd>${rec.support.map((x) => `${inr(x.level)} (${x.touches}×)`).join(", ") || "—"}</dd>
          <dt>Resistance</dt><dd>${rec.resistance.map((x) => `${inr(x.level)} (${x.touches}×)`).join(", ") || "—"}</dd></dl><p class="muted">${esc(rec.scenarios.method)}</p>` : "<p class='muted'>Not enough data.</p>"}</div>
        <div class="card"><h3>${bi("Main reasons this could fail", "ವಿಫಲವಾಗಬಹುದಾದ ಮುಖ್ಯ ಕಾರಣಗಳು")}</h3><ul class="clean">${rec.failure_reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul><p class="muted">${esc(rec.disclaimer)}</p></div>
      </div>

      <div class="card section"><h2>${bi("Price chart", "ಬೆಲೆ ಚಾರ್ಟ್")}<span class="filters" style="margin:0" id="ovl">
        ${[["sma_20", "SMA 20"], ["sma_50", "SMA 50", 1], ["sma_200", "SMA 200", 1], ["ema_20", "EMA 20"], ["bb", "Bollinger"], ["vwap_20", "VWAP 20d"], ["supertrend", "Supertrend"], ["psar", "Parabolic SAR"], ["sr", "Support/Resistance", 1]]
          .map(([k, l, on]) => `<label><input type="checkbox" value="${k}" ${on ? "checked" : ""}>${l}</label>`).join("")}</span></h2>
        <div id="pc" class="chart tall"></div><div id="vc" class="chart" style="min-height:140px"></div></div>
      <div class="grid g2 section"><div class="card"><h3>RSI (14)</h3><div id="rc" class="chart"></div></div><div class="card"><h3>MACD (12, 26, 9)</h3><div id="mc" class="chart"></div></div></div>

      <div class="grid g2 section">
        <div class="card"><h2>${bi("Indicator readings", "ಸೂಚಕಗಳ ಮೌಲ್ಯಗಳು")}<a href="#/learn" style="font-size:12px">What do these mean? →</a></h2>${indicatorTable(ind, last)}</div>
        <div class="card"><h2>${bi("Price structure", "ಬೆಲೆ ರಚನೆ")}</h2><dl class="kv">
          <dt>Market structure</dt><dd>${esc(s.structure?.structure)}</dd>
          <dt>Pivot (classic)</dt><dd>P ${fmt(s.pivots.P)} · R1 ${fmt(s.pivots.R1)} · S1 ${fmt(s.pivots.S1)} · R2 ${fmt(s.pivots.R2)} · S2 ${fmt(s.pivots.S2)}</dd>
          <dt>Fibonacci (${esc(s.fibonacci.direction)} swing)</dt><dd>${Object.entries(s.fibonacci.retracement).map(([k, v]) => `${k}: ${fmt(v)}`).join(" · ")}</dd>
          <dt>Fib extensions</dt><dd>${Object.entries(s.fibonacci.extension).map(([k, v]) => `${k}: ${fmt(v)}`).join(" · ")}</dd>
          <dt>Beta / correlation (1y vs Nifty)</dt><dd>${fmt(s.beta_corr?.beta)} / ${fmt(s.beta_corr?.correlation)}</dd>
          <dt>Volatility regime</dt><dd>${esc(q.vol_regime)}</dd>
          <dt>Candles, last 5 sessions</dt><dd>${Object.entries(s.candlestick_patterns_last5 || {}).filter(([, v]) => v.length).map(([d, v]) => `${day(d)}: ${v.map((x) => esc(x.replace(/_/g, " "))).join(", ")}`).join("<br>") || "No standard pattern"}</dd>
        </dl></div>
      </div>

      <div class="card section"><h2>${bi("Fundamental analysis", "ಮೂಲಭೂತ ವಿಶ್ಲೇಷಣೆ")}</h2>${fundamentalsBlock(f)}</div>
      <div class="card section"><h2>${bi("Risk & return statistics", "ಅಪಾಯ ಮತ್ತು ಪ್ರತಿಫಲ ಅಂಕಿಅಂಶ")}</h2>${quantBlock(qs)}</div>
      <div class="card section"><h2>${bi("Related news", "ಸಂಬಂಧಿತ ಸುದ್ದಿ")}</h2>${(s.news || []).map(newsRow).join("") || "<p class='muted'>No matched news in the stored history.</p>"}</div>`;
    drawStockCharts(s);
    $("#ovl").addEventListener("change", () => drawStockCharts(s));
    liveHooks.push(() => drawIntraday(s.symbol, last));
  }

  async function drawIntraday(sym, eodClose) {
    if (!LIVE.enabled) return;
    const card = $("#intradayCard");
    if (!card) return;
    const r = await fetch(`${LIVE.endpoint}?intraday=${encodeURIComponent(sym)}`, { cache: "no-cache" });
    if (!r.ok) return;
    const d = await r.json();
    if (!d.points?.length) return;
    card.hidden = false;
    $("#intradayMeta").textContent = `last ${timeIST(d.quote.market_time)} · prev close ${fmt(d.quote.prev_close)}`;
    const x = d.points.map((p) => new Date(p[0]).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" }));
    const y = d.points.map((p) => p[1]);
    const up = y[y.length - 1] >= (d.quote.prev_close ?? y[0]);
    await plot($("#intradayChart"), [{ type: "scatter", mode: "lines", x, y, name: sym, line: { color: up ? css("--up") : css("--down"), width: 2 },
      hovertemplate: "%{x} IST: ₹%{y:,.2f}<extra></extra>" }], { height: 220, showlegend: false, margin: { l: 56, r: 16, t: 6, b: 30 },
      shapes: isNum(d.quote.prev_close) ? [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: d.quote.prev_close, y1: d.quote.prev_close, line: { color: css("--text-muted"), width: 1, dash: "dot" } }] : [],
      yaxis: { gridcolor: css("--border"), tickformat: ",.0f" } });
  }

  function horizonCard(h) {
    if (h.label === "insufficient") {
      return `<div class="card"><h3>${h.horizon_days}-day swing</h3>${labelPill("insufficient")}<p><strong>${esc(h.message)}</strong></p><ul class="clean muted">${h.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul></div>`;
    }
    const d = h.historical_return_distribution_pct || {};
    return `<div class="card"><h3>${h.horizon_days}-day swing</h3>${labelPill(h.label)} <span class="pill">confidence: ${esc(h.model_confidence)}</span>
      <div style="margin:10px 0">${probBar(h.probabilities)}</div>
      <p class="muted" style="font-size:12.5px">${esc(h.label_note)}. Thresholds: bullish ≥ ${h.thresholds_used.bullish ?? "n/a"}, bearish ≥ ${h.thresholds_used.bearish ?? "n/a"}. Model: ${esc(h.model)}.</p>
      <p style="font-size:12.5px">Past ${h.horizon_days}-day returns of this stock (not a forecast): 10th pct ${fmt(d[10])}%, median ${fmt(d[50])}%, 90th pct ${fmt(d[90])}%; positive ${fmt((h.historical_p_positive || 0) * 100, 0)}% of the time.</p></div>`;
  }

  function indicatorTable(i, price) {
    const rows = [
      ["RSI (14)", fmt(i.rsi_14, 1), "rsi"], ["MACD / signal / hist", `${fmt(i.macd)} / ${fmt(i.macd_signal)} / ${fmt(i.macd_hist)}`, "macd"],
      ["Stochastic %K / %D", `${fmt(i.stoch_k, 1)} / ${fmt(i.stoch_d, 1)}`, "stoch"], ["Stochastic RSI K / D", `${fmt(i.stochrsi_k, 1)} / ${fmt(i.stochrsi_d, 1)}`, "stochrsi"],
      ["ROC (12)", fmt(i.roc_12) + "%", "roc"], ["Momentum (10)", fmt(i.mom_10), "momentum"], ["CCI (20)", fmt(i.cci_20, 0), "cci"], ["Williams %R (14)", fmt(i.willr_14, 1), "willr"],
      ["SMA 20 / 50 / 200", `${fmt(i.sma_20)} / ${fmt(i.sma_50)} / ${fmt(i.sma_200)}`, "sma"], ["EMA 9 / 20 / 50", `${fmt(i.ema_9)} / ${fmt(i.ema_20)} / ${fmt(i.ema_50)}`, "ema"],
      ["WMA / DEMA / TEMA / HMA (20)", `${fmt(i.wma_20)} / ${fmt(i.dema_20)} / ${fmt(i.tema_20)} / ${fmt(i.hma_20)}`, "hma"],
      ["Bollinger upper / lower, %B", `${fmt(i.bb_upper)} / ${fmt(i.bb_lower)}, ${fmt(i.bb_pctb)}`, "bollinger"], ["ATR (14)", `${fmt(i.atr_14)} (${fmt((i.atr_14 / price) * 100, 1)}% of price)`, "atr"],
      ["Keltner upper / lower", `${fmt(i.kc_upper)} / ${fmt(i.kc_lower)}`, "keltner"], ["Donchian 20 high / low", `${fmt(i.dc_upper)} / ${fmt(i.dc_lower)}`, "donchian"],
      ["Std-dev (20) / Hist. vol", `${fmt(i.stddev_20)} / ${fmt(i.hv_20, 1)}%`, "hv"], ["VWAP 20-day (daily bars)", fmt(i.vwap_20), "vwap"],
      ["OBV / A-D line", `${fmt(i.obv, 0)} / ${fmt(i.ad_line, 0)}`, "obv"], ["CMF (20) / MFI (14)", `${fmt(i.cmf_20, 3)} / ${fmt(i.mfi_14, 1)}`, "cmf"],
      ["Volume ROC / Relative volume", `${fmt(i.vroc_14, 0)}% / ${fmt(i.rel_volume, 2)}×`, "relvol"], ["ADX / +DI / −DI", `${fmt(i.adx, 1)} / ${fmt(i.plus_di, 1)} / ${fmt(i.minus_di, 1)}`, "adx"],
      ["Parabolic SAR", fmt(i.psar), "psar"], ["Supertrend (10, 3)", `${fmt(i.supertrend)} (${i.supertrend_dir === 1 ? "buy mode" : i.supertrend_dir === -1 ? "sell mode" : "—"})`, "supertrend"],
      ["Ichimoku tenkan / kijun / span A / span B", `${fmt(i.ichi_tenkan)} / ${fmt(i.ichi_kijun)} / ${fmt(i.ichi_span_a)} / ${fmt(i.ichi_span_b)}`, "ichimoku"],
      ["Relative strength vs Nifty (63d)", isNum(i.rs_63) ? fmt(i.rs_63, 1) + " pp" : "—", "rs"], ["Gap today", fmt(i.gap_pct) + "%", "gap"],
      ["Breakout / breakdown today", `${i.breakout ? "Breakout" : "—"} / ${i.breakdown ? "Breakdown" : "—"}`, "breakout"],
    ];
    return `<div class="table-wrap"><table><tbody>${rows.map(([n, v, id]) => `<tr><td><a href="#/learn/${id}">${esc(n)}</a></td><td class="num">${v}</td></tr>`).join("")}</tbody></table></div>`;
  }

  function fundamentalsBlock(f) {
    if (!f?.available) return `<p class="muted">${esc(f?.reason || "Not available yet — fundamentals are refreshed gradually (about 80 companies per run).")}</p>`;
    const r = f.ratios, sc = f.scorecard;
    const names = { pe: "P/E", pb: "P/B", eps: "EPS (₹)", roe: "ROE %", roce: "ROCE %", roa: "ROA %", debt_to_equity: "Debt / Equity", current_ratio: "Current ratio", quick_ratio: "Quick ratio",
      interest_coverage: "Interest coverage ×", ebitda_margin: "EBITDA margin %", net_margin: "Net margin %", operating_margin: "Operating margin %", ocf_to_net_profit: "OCF / Net profit",
      ps: "Price / Sales", ev_ebitda: "EV / EBITDA", dividend_yield: "Dividend yield %", peg: "PEG", working_capital: "Working capital (₹)" };
    return `<p class="muted">${esc(f.data_status)} · latest period ${esc(f.latest_period)} · source ${esc(f.provider)} · fetched ${dt(f.fetched_at)}</p>
      <div class="grid g2"><div><h3>Scorecard: ${esc(sc.label)} ${sc.score != null ? `(${sc.passed}/${sc.evaluated} checks)` : ""}</h3>
        <div class="table-wrap"><table><tbody>${sc.checks.map((c) => `<tr><td>${esc(c.check)}</td><td>${c.result === "pass" ? "✔ pass" : c.result === "fail" ? "✖ fail" : "n/a"}</td><td class="num">${c.value != null ? fmt(c.value) : ""}</td></tr>`).join("")}</tbody></table></div>
        ${sc.note ? `<p class="muted">${esc(sc.note)}</p>` : ""}
        <h3 class="section">Red flags</h3>${f.red_flags.length ? f.red_flags.map((x) => `<div class="flag"><span class="icon">${x.severity === "high" ? "⛔" : "⚠️"}</span><div><strong>${esc(x.flag)}</strong><br><span class="muted">${esc(x.detail)}</span></div></div>`).join("") : "<p class='muted'>None detected from available data.</p>"}
        <p class="muted">${esc(f.governance_note)}</p></div>
      <div><h3>Ratios</h3><div class="table-wrap"><table><thead><tr><th>Ratio</th><th class="num">Value</th><th>Formula</th></tr></thead><tbody>
        ${Object.entries(names).map(([k, n]) => `<tr><td>${esc(n)}</td><td class="num">${k === "working_capital" ? cr(r[k]?.value) : fmt(r[k]?.value)}</td><td class="muted" style="font-size:12px">${esc(r[k]?.formula)}</td></tr>`).join("")}</tbody></table></div></div></div>
      <h3 class="section">Multi-year statements (₹ crore)</h3><div class="table-wrap"><table><thead><tr><th>Period</th>${["Revenue", "EBITDA", "Net profit", "Op. cash flow", "Free cash flow", "Total debt", "Equity", "Receivables", "Inventory"].map((x) => `<th class="num">${x}</th>`).join("")}</tr></thead>
        <tbody>${f.years.map((y) => `<tr><td>${esc(y.period)}</td>${["revenue", "ebitda", "net_income", "ocf", "fcf", "total_debt", "equity", "receivables", "inventory"].map((k) => `<td class="num">${isNum(y[k]) ? fmt(y[k] / 1e7, 0) : "—"}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  }

  function quantBlock(q) {
    if (!q?.available) return `<p class="muted">${esc(q?.reason || "n/a")}</p>`;
    return `<div class="grid g2"><dl class="kv">
      <dt>Annualised return (3y)</dt><dd>${fmt(q.annual_return_pct)}%</dd><dt>Annualised volatility</dt><dd>${fmt(q.annual_volatility_pct)}%</dd>
      <dt>Sharpe / Sortino</dt><dd>${fmt(q.sharpe)} / ${fmt(q.sortino)} <small>(risk-free ${fmt(q.risk_free_rate_pct, 1)}%)</small></dd>
      <dt>Max drawdown</dt><dd>${fmt(q.max_drawdown_pct)}% <small>(${day(q.peak_date)} → ${day(q.trough_date)})</small></dd><dt>Current drawdown</dt><dd>${fmt(q.current_drawdown_pct)}%</dd>
      <dt>1-day VaR 95% (hist / normal / Cornish-Fisher)</dt><dd>${fmt(q.var_1d.historical_var_pct)}% / ${fmt(q.var_1d.normal_var_pct)}% / ${fmt(q.var_1d.cornish_fisher_var_pct)}%</dd>
      <dt>1-day CVaR 95%</dt><dd>${fmt(q.var_1d.historical_cvar_pct)}%</dd><dt>Beta / correlation (1y)</dt><dd>${fmt(q.beta_1y)} / ${fmt(q.correlation_1y)}</dd>
      <dt>Normality (Jarque–Bera p)</dt><dd>${fmt(q.normality.jarque_bera_p, 4)} → ${q.normality.normal_assumption_ok ? "normal not rejected" : "fat tails: prefer historical VaR"}</dd>
      <dt>Mean daily return significant?</dt><dd>${q.mean_return_significance.significant_at_5pct ? "yes" : "no"} (p = ${fmt(q.mean_return_significance.p_value, 3)})</dd></dl>
      <div><div class="table-wrap"><table><thead><tr><th>Horizon</th><th class="num">Mean (95% CI)</th><th class="num">P(positive) (95% CI)</th><th class="num">10th / 90th pct</th><th class="num">n</th></tr></thead><tbody>
      ${q.horizons.filter((h) => h.available).map((h) => `<tr><td>${h.horizon_days} days</td><td class="num">${fmt(h.mean_return_pct)}% <small>(${fmt(h.mean_return_ci95_pct[0])} … ${fmt(h.mean_return_ci95_pct[1])})</small></td>
        <td class="num">${fmt(h.p_positive * 100, 0)}% <small>(${fmt(h.p_positive_ci95[0] * 100, 0)}–${fmt(h.p_positive_ci95[1] * 100, 0)})</small></td><td class="num">${fmt(h.quantiles_pct[10])}% / ${fmt(h.quantiles_pct[90])}%</td><td class="num">${h.n_independent}</td></tr>`).join("")}
      </tbody></table></div><p class="muted">Historical statistics of non-overlapping past periods — descriptive, not a forecast, and separate from model probabilities.</p></div></div>`;
  }

  function drawStockCharts(s) {
    const ch = s.chart, on = new Set([...document.querySelectorAll("#ovl input:checked")].map((x) => x.value));
    const x = ch.date;
    const line = (y, name, color, extra = {}) => ({ type: "scatter", mode: "lines", x, y, name, line: { color, width: 2 }, hovertemplate: `${name}: %{y:,.2f}<extra></extra>`, ...extra });
    const tr = [{ type: "candlestick", x, open: ch.open, high: ch.high, low: ch.low, close: ch.close, name: "Price",
      increasing: { line: { color: css("--up"), width: 1 }, fillcolor: css("--up") }, decreasing: { line: { color: css("--down"), width: 1 }, fillcolor: css("--down") } }];
    if (on.has("sma_20")) tr.push(line(ch.sma_20, "SMA 20", css("--series-4")));
    if (on.has("sma_50")) tr.push(line(ch.sma_50, "SMA 50", css("--series-2")));
    if (on.has("sma_200")) tr.push(line(ch.sma_200, "SMA 200", css("--series-7")));
    if (on.has("ema_20")) tr.push(line(ch.ema_20, "EMA 20", css("--series-3")));
    if (on.has("vwap_20")) tr.push(line(ch.vwap_20, "VWAP 20d", css("--text-secondary"), { line: { color: css("--text-secondary"), width: 2, dash: "dot" } }));
    if (on.has("bb")) { tr.push(line(ch.bb_upper, "BB upper", css("--text-muted"), { line: { color: css("--text-muted"), width: 1, dash: "dash" } })); tr.push(line(ch.bb_lower, "BB lower", css("--text-muted"), { line: { color: css("--text-muted"), width: 1, dash: "dash" } })); }
    if (on.has("supertrend")) tr.push(line(ch.supertrend, "Supertrend", css("--series-3"), { line: { color: css("--series-3"), width: 2, shape: "hv" } }));
    if (on.has("psar")) tr.push({ type: "scatter", mode: "markers", x, y: ch.psar, name: "Parabolic SAR", marker: { size: 4, color: css("--text-secondary") }, hovertemplate: "SAR: %{y:,.2f}<extra></extra>" });
    const shapes = [], ann = [];
    if (on.has("sr")) {
      const rec = s.recommendation;
      [...rec.support.map((z) => [z, "S"]), ...rec.resistance.map((z) => [z, "R"])].forEach(([z, t]) => {
        shapes.push({ type: "line", xref: "paper", x0: 0, x1: 1, y0: z.level, y1: z.level, line: { color: t === "S" ? css("--up") : css("--down"), width: 1, dash: "dot" } });
        ann.push({ xref: "paper", x: 1, xanchor: "right", y: z.level, yanchor: "bottom", text: `${t} ${fmt(z.level)}`, showarrow: false, font: { size: 11, color: css("--text-secondary") } });
      });
    }
    plot($("#pc"), tr, { height: 430, shapes, annotations: ann, yaxis: { gridcolor: css("--border"), tickformat: ",.0f", title: { text: "₹" } } });
    plot($("#vc"), [{ type: "bar", x, y: ch.volume, name: "Volume", marker: { color: ch.close.map((c, i) => (i && c < ch.close[i - 1] ? css("--down") : css("--up"))) }, hovertemplate: "Volume: %{y:,.0f}<extra></extra>" }],
      { height: 150, showlegend: false, margin: { l: 56, r: 16, t: 4, b: 28 }, yaxis: { gridcolor: css("--border"), tickformat: ".2s" }, bargap: 0.25 });
    plot($("#rc"), [line(ch.rsi_14, "RSI 14", css("--series-1"))], { height: 230, showlegend: false, yaxis: { range: [0, 100], gridcolor: css("--border"), tickvals: [0, 30, 50, 70, 100] },
      shapes: [30, 70].map((v) => ({ type: "line", xref: "paper", x0: 0, x1: 1, y0: v, y1: v, line: { color: css("--text-muted"), width: 1, dash: "dot" } })) });
    plot($("#mc"), [{ type: "bar", x, y: ch.macd_hist, name: "Histogram", marker: { color: ch.macd_hist.map((v) => (v >= 0 ? css("--up") : css("--down"))) }, opacity: 0.6, hovertemplate: "Hist: %{y:.2f}<extra></extra>" },
      line(ch.macd, "MACD", css("--series-1")), line(ch.macd_signal, "Signal", css("--series-2"))], { height: 230, yaxis: { gridcolor: css("--border"), tickformat: ".1f" } });
  }

  async function pageNews(mode) {
    const n = await getJSON("news.json");
    let items = n.items || [];
    if (mode === "orders") items = items.filter((x) => x.category === "order_win");
    if (mode === "announcements") items = items.filter((x) => x.verified);
    const sectors = [...new Set(items.map((x) => x.sector).filter(Boolean))].sort();
    const st = { q: "", cat: "", sent: "", sector: "", days: 7, matched: false, verified: false };
    const title = { orders: ["Order-win scanner", "ಆರ್ಡರ್ ಗೆಲುವು ಶೋಧಕ"], announcements: ["Corporate announcement scanner", "ಕಾರ್ಪೊರೇಟ್ ಪ್ರಕಟಣೆಗಳು"] }[mode] || ["Market news", "ಮಾರುಕಟ್ಟೆ ಸುದ್ದಿ"];
    view.innerHTML = `<div class="page-head"><div><h1>${bi(...title)}</h1><p>${bp(`${esc(n.note)} Items are classified automatically (rules + text similarity); check the original before acting.
      ${mode === "orders" ? "<br><strong>Order Size Ratio = order value ÷ annual revenue × 100.</strong> A large order is not automatically bullish — margins, execution time and funding matter." : ""}`,
      `ಶೀರ್ಷಿಕೆ ಮತ್ತು ಮೂಲ ಲಿಂಕ್ ಮಾತ್ರ ತೋರಿಸಲಾಗಿದೆ; ಪೂರ್ಣ ಸುದ್ದಿಗೆ ಮೂಲವನ್ನು ತೆರೆಯಿರಿ. ವರ್ಗೀಕರಣ ಸ್ವಯಂಚಾಲಿತ (ನಿಯಮಗಳು + ಪಠ್ಯ ಹೋಲಿಕೆ); ನಿರ್ಧಾರಕ್ಕೆ ಮೊದಲು ಮೂಲವನ್ನು ಪರಿಶೀಲಿಸಿ.
      ${mode === "orders" ? "<br><strong>ಆರ್ಡರ್ ಗಾತ್ರ ಅನುಪಾತ = ಆರ್ಡರ್ ಮೊತ್ತ ÷ ವಾರ್ಷಿಕ ಆದಾಯ × 100.</strong> ದೊಡ್ಡ ಆರ್ಡರ್ ಬಂದ ಮಾತ್ರಕ್ಕೆ ಏರುಮುಖ ಎಂದಲ್ಲ — ಲಾಭಾಂಶ, ಅನುಷ್ಠಾನ ಅವಧಿ ಮತ್ತು ಹಣಕಾಸು ಮುಖ್ಯ." : ""}`)}</p></div></div>
      <div class="filters"><input type="search" id="nq" placeholder="Search headline / symbol">
        ${mode ? "" : `<label>Category <select id="nc"><option value="">All</option>${Object.entries(n.categories || {}).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}<option value="other">Other</option></select></label>`}
        <label>Sentiment <select id="ns"><option value="">All</option><option value="pos">Positive</option><option value="neg">Negative</option><option value="neu">Neutral</option></select></label>
        <label>Sector <select id="nsec"><option value="">All</option>${sectors.map((s) => `<option>${esc(s)}</option>`).join("")}</select></label>
        <label>Last <select id="nd"><option value="1">1 day</option><option value="3">3 days</option><option value="7" selected>7 days</option><option value="30">30 days</option><option value="60">all stored</option></select></label>
        <label><input type="checkbox" id="nm"> Matched to a stock</label>${mode === "announcements" ? "" : `<label><input type="checkbox" id="nv"> Exchange filings only</label>`}</div>
      <div id="nlist"></div>`;
    const draw = () => {
      const cutoff = Date.now() - st.days * 864e5, q = st.q.toLowerCase();
      const data = items.filter((x) => new Date(x.published).getTime() >= cutoff && (!q || x.headline.toLowerCase().includes(q) || (x.symbol || "").toLowerCase().includes(q)) &&
        (!st.cat || x.category === st.cat) && (!st.sector || x.sector === st.sector) && (!st.matched || x.symbol) && (!st.verified || x.verified) &&
        (!st.sent || (st.sent === "pos" ? x.sentiment > 0.15 : st.sent === "neg" ? x.sentiment < -0.15 : Math.abs(x.sentiment) <= 0.15)));
      if (mode === "orders") {
        sortableTable($("#nlist"), data, [
          { key: "published", title: "Date", render: (r) => dt(r.published) },
          { key: "symbol", title: "Company", cls: "sym", render: (r) => (r.symbol ? stockLink(r.symbol.replace(/[^A-Za-z0-9_-]/g, "_"), r.symbol) : "<span class='muted'>unmatched</span>") },
          { key: "headline", title: "Headline", cls: "notranslate-cell", render: (r) => `<a class="notranslate" href="${safeUrl(r.url)}" target="_blank" rel="noopener noreferrer nofollow">${esc(r.headline)}</a><br><small>${esc(r.source)} ${r.verified ? "· ✔ filing" : "· media"}</small>` },
          { key: "ov", title: "Order (₹ cr)", num: true, sort: (r) => r.order_analysis?.order_value_cr, render: (r) => fmt(r.order_analysis?.order_value_cr, 0) },
          { key: "rev", title: "Revenue (₹ cr)", num: true, sort: (r) => r.order_analysis?.annual_revenue_cr, render: (r) => fmt(r.order_analysis?.annual_revenue_cr, 0) },
          { key: "osr", title: "Order size ratio", num: true, sort: (r) => r.order_analysis?.order_size_ratio_pct, render: (r) => (isNum(r.order_analysis?.order_size_ratio_pct) ? fmt(r.order_analysis.order_size_ratio_pct, 1) + "%" : "—") },
          { key: "mat", title: "Materiality", render: (r) => esc(r.order_analysis?.materiality || "—") + (r.order_analysis?.execution_months ? `<br><small>over ${fmt(r.order_analysis.execution_months, 0)} months</small>` : "") },
          { key: "repeat", title: "Note", sortable: false, render: (r) => (r.repeat_of ? "May be a repeat of an earlier disclosure" : "") },
        ], { initialSort: { key: "published", dir: -1 } });
      } else {
        $("#nlist").innerHTML = `<div class="card">${data.slice(0, 300).map(newsRow).join("") || "<p class='empty'>No news matches these filters.</p>"}</div><p class="muted">${data.length} items</p>`;
      }
    };
    const bind = (id, k, c = (v) => v) => $(id)?.addEventListener("input", (e) => { st[k] = c(e.target.type === "checkbox" ? e.target.checked : e.target.value); draw(); });
    bind("#nq", "q"); bind("#nc", "cat"); bind("#ns", "sent"); bind("#nsec", "sector"); bind("#nd", "days", Number); bind("#nm", "matched"); bind("#nv", "verified");
    draw();
  }

  async function pageModel() {
    const m = await getJSON("model.json");
    const hs = Object.keys(m.horizons || {});
    view.innerHTML = `<div class="page-head"><div><h1>${bi("Model performance", "ಮಾದರಿ ಕಾರ್ಯಕ್ಷಮತೆ")}</h1>
      <p>${bp(`All numbers are <strong>out-of-sample</strong> (expanding walk-forward, purge gap = horizon). A model is used only if it beats the base-rate forecast with a bootstrap-confirmed margin.
      Intraday: ${esc(m.intraday?.reason)}.`,
      `ಎಲ್ಲಾ ಸಂಖ್ಯೆಗಳು <strong>ತರಬೇತಿಗೆ ಬಳಸದ (out-of-sample)</strong> ದತ್ತಾಂಶದ ಮೇಲಿನವು (ಮುಂದೆ ಸಾಗುವ ಪರೀಕ್ಷೆ, ಅವಧಿಯಷ್ಟು ಅಂತರ). ಸರಳ ಮೂಲ ಆವರ್ತನದ ಮುನ್ಸೂಚನೆಗಿಂತ ಖಚಿತವಾಗಿ ಉತ್ತಮವಾದರೆ ಮಾತ್ರ ಮಾದರಿಯನ್ನು ಬಳಸಲಾಗುತ್ತದೆ.
      ದಿನದೊಳಗಿನ ಮಾದರಿ: ಅಧಿಕೃತ ನೇರ ದತ್ತಾಂಶ ಬೇಕು.`)}</p></div></div>
      ${hs.map((h) => { const r = m.horizons[h]; const best = r.metrics?.[r.selected_model] || {};
        return `<div class="card section"><h2>${h}-day swing model ${r.gate?.passed ? `<span class="pill verified">Validated — in use</span>` : `<span class="pill insufficient">Not validated — no recommendations</span>`}</h2>
        ${r.gate?.passed ? "" : `<div class="notice"><strong>Why not released:</strong> ${(r.gate?.reasons || []).map(esc).join("; ")}</div>`}
        <p class="muted">${esc(r.label_definition || "")}. ${esc(r.validation || "")}. Trained ${dt(r.trained_at)}${r.train_end ? `, data to ${day(r.train_end)}` : ""}.
          ${r.metrics?._oos_period ? `Out-of-sample period ${day(r.metrics._oos_period[0])} – ${day(r.metrics._oos_period[1])}, ${r.metrics._folds} folds.` : ""}</p>
        ${r.metrics && !r.metrics.error ? `<div class="table-wrap"><table><thead><tr><th>Model</th><th class="num">n</th><th class="num">Brier</th><th class="num">Brier (base rate)</th><th class="num">Brier skill</th><th class="num">Log loss</th><th class="num">Log loss (base)</th><th class="num">AUC bull / bear</th></tr></thead><tbody>
          ${Object.entries(r.metrics).filter(([k]) => !k.startsWith("_")).map(([k, v]) => `<tr><td>${esc(k.replace(/_/g, " "))}${k === r.selected_model ? " ★" : ""}</td><td class="num">${v.n}</td><td class="num">${fmt(v.brier, 4)}</td><td class="num">${fmt(v.brier_base_rate, 4)}</td>
          <td class="num">${fmt(v.brier_skill_score, 4)}</td><td class="num">${fmt(v.log_loss, 4)}</td><td class="num">${fmt(v.log_loss_base_rate, 4)}</td><td class="num">${fmt(v.roc_auc?.bullish, 3)} / ${fmt(v.roc_auc?.bearish, 3)}</td></tr>`).join("")}
          </tbody></table></div>
          <p class="muted">★ selected (lowest log loss). Bootstrap Brier skill, 5th percentile: <strong>${fmt(r.gate?.bootstrap?.lower_5pct, 4)}</strong> (median ${fmt(r.gate?.bootstrap?.median, 4)}, ${r.gate?.bootstrap?.n_dates ?? "—"} dates, ${r.gate?.bootstrap?.block_days ?? "—"}-day blocks). Must be &gt; 0.</p>
          <div class="grid g2"><div><h3>Calibration — bullish class</h3><div id="rel${h}" class="chart"></div><p class="muted">Points near the diagonal = well calibrated. Bins with fewer than 20 predictions are hidden.</p></div>
          <div><h3>Thresholds (chosen on 1st half, tested on 2nd half)</h3><div class="table-wrap"><table><thead><tr><th>Class</th><th class="num">Threshold</th><th class="num">Hold-out precision</th><th class="num">Base rate</th><th class="num">Lift</th><th class="num">Signals</th><th class="num">p-value</th><th>Valid?</th></tr></thead><tbody>
          ${Object.entries(r.thresholds || {}).map(([c, t]) => `<tr><td>${esc(c)}</td><td class="num">${t.threshold ?? "—"}</td><td class="num">${isNum(t.holdout_precision) ? fmt(t.holdout_precision * 100, 1) + "%" : "—"}</td><td class="num">${isNum(t.holdout_base_rate) ? fmt(t.holdout_base_rate * 100, 1) + "%" : "—"}</td>
            <td class="num">${fmt(t.holdout_lift, 2)}</td><td class="num">${t.holdout_signals ?? "—"}</td><td class="num">${fmt(t.p_value, 4)}</td><td>${t.validated ? "✔ yes" : "✖ no"}</td></tr>`).join("")}</tbody></table></div>
          <h3 class="section">Confusion matrix (${esc(r.selected_model)})</h3><div class="table-wrap"><table><thead><tr><th>actual ↓ / predicted →</th>${(best.confusion_matrix?.labels || []).map((l) => `<th class="num">${esc(l)}</th>`).join("")}</tr></thead>
          <tbody>${(best.confusion_matrix?.matrix || []).map((row, i) => `<tr><th>${esc(best.confusion_matrix.labels[i])}</th>${row.map((v) => `<td class="num">${v}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
          <h3 class="section">Per-class precision / recall / F1</h3><div class="table-wrap"><table><tbody>${Object.entries(best.per_class || {}).map(([c, v]) => `<tr><td>${esc(c)}</td><td class="num">P ${fmt(v.precision, 3)}</td><td class="num">R ${fmt(v.recall, 3)}</td><td class="num">F1 ${fmt(v.f1, 3)}</td><td class="num">n ${v.support}</td></tr>`).join("")}</tbody></table></div></div></div>
          <p class="muted">Features: ${(r.features || []).map(esc).join(", ")}${r.features_dropped_correlated?.length ? ` · dropped as highly correlated (|ρ| &gt; 0.9): ${r.features_dropped_correlated.map(esc).join(", ")}` : ""}</p>` : `<p class="muted">${esc(r.metrics?.error || "No metrics")}</p>`}</div>`; }).join("") || `<div class="card empty">No model reports yet.</div>`}`;
    for (const h of hs) {
      const best = m.horizons[h].metrics?.[m.horizons[h].selected_model];
      const rel = best?.reliability_bullish || [];
      const el = $(`#rel${h}`);
      if (el && rel.length) plot(el, [
        { type: "scatter", mode: "lines", x: [0, 1], y: [0, 1], name: T("Perfect calibration"), line: { color: css("--text-muted"), width: 1, dash: "dot" }, hoverinfo: "skip" },
        { type: "scatter", mode: "lines+markers", x: rel.map((b) => b.mean_predicted), y: rel.map((b) => b.observed), name: "Model", text: rel.map((b) => b.n),
          line: { color: css("--series-1"), width: 2 }, marker: { size: 8, color: css("--series-1"), line: { color: css("--surface-1"), width: 2 } }, hovertemplate: "predicted %{x:.2f} → observed %{y:.2f} (n=%{text})<extra></extra>" }],
        { height: 260, hovermode: "closest", xaxis: { range: [0, 1], title: { text: T("Predicted P(bullish)") }, gridcolor: css("--border"), type: "linear" }, yaxis: { range: [0, 1], title: { text: T("Observed frequency") }, gridcolor: css("--border"), tickformat: ".1f" } });
    }
  }

  async function pageBacktest() {
    const b = await getJSON("backtest.json");
    const hs = Object.keys(b.horizons || {});
    view.innerHTML = `<div class="page-head"><div><h1>${bi("Historical backtesting", "ಐತಿಹಾಸಿಕ ಹಿಂಪರೀಕ್ಷೆ")}</h1><p>${bp("Out-of-sample signals only. Buy at the next session's open, sell at the close after the horizon, equal weight, Indian delivery costs (STT, stamp duty, exchange, SEBI, GST, brokerage, slippage). Past results do not predict future results.",
  "ತರಬೇತಿಗೆ ಬಳಸದ ಅವಧಿಯ ಸಂಕೇತಗಳು ಮಾತ್ರ. ಮುಂದಿನ ದಿನದ ಆರಂಭ ಬೆಲೆಯಲ್ಲಿ ಖರೀದಿ, ಅವಧಿಯ ಕೊನೆಯ ಮುಕ್ತಾಯ ಬೆಲೆಯಲ್ಲಿ ಮಾರಾಟ, ಸಮಾನ ತೂಕ, ಭಾರತೀಯ ಡೆಲಿವರಿ ವೆಚ್ಚಗಳು (STT, ಮುದ್ರಾಂಕ ಶುಲ್ಕ, ವಿನಿಮಯ, SEBI, GST, ದಲ್ಲಾಳಿ, ಜಾರಿಕೆ). ಹಿಂದಿನ ಫಲಿತಾಂಶಗಳು ಭವಿಷ್ಯವನ್ನು ಖಚಿತಪಡಿಸುವುದಿಲ್ಲ.")}</p></div></div>
      ${hs.map((h) => { const r = b.horizons[h]; if (!r.available) return `<div class="card section"><h2>${h}-day</h2><p class="muted">${esc(r.reason)}</p></div>`;
        const S = r.strategy, B = r.benchmark_equal_weight_universe;
        return `<div class="card section"><h2>${h}-day swing · threshold ${r.threshold} · ${esc(r.model)}</h2>
        <div class="grid g4">${[["Strategy total return", fmt(S.total_return_pct) + "%"], ["Benchmark (all stocks)", fmt(B.total_return_pct) + "%"], ["Strategy max drawdown", fmt(S.max_drawdown_pct) + "%"], ["Strategy Sharpe", fmt(S.sharpe)],
          ["Trades", r.trades], ["Win rate (net)", fmt(r.win_rate_pct, 1) + "%"], ["Avg trade (net)", fmt(r.avg_trade_net_pct, 3) + "%"], ["Round-trip cost", fmt(r.round_trip_cost_pct, 3) + "%"]]
          .map(([l, v]) => `<div class="tile"><div class="label">${l}</div><div class="value" style="font-size:1.2rem">${v}</div></div>`).join("")}</div>
        <div id="eq${h}" class="chart"></div>
        <p class="muted">Exposure ${fmt(r.exposure_pct, 1)}% of periods. Bearish-signal check (avoid list): ${r.bearish_signal_check.signals} signals, average forward return ${fmt(r.bearish_signal_check.avg_forward_return_pct, 3)}% vs universe ${fmt(r.bearish_signal_check.universe_avg_forward_return_pct, 3)}%.
        <br>Known biases: ${r.biases.map(esc).join("; ")}.</p></div>`; }).join("") || `<div class="card empty">No backtests yet.</div>`}`;
    for (const h of hs) {
      const r = b.horizons[h];
      if (!r.available) continue;
      const x = r.equity_curve.map((p) => p.date);
      plot($(`#eq${h}`), [
        { type: "scatter", mode: "lines", x, y: r.equity_curve.map((p) => p.strategy), name: T("Strategy"), line: { color: css("--series-1"), width: 2 }, hovertemplate: "Strategy: %{y:.3f}<extra></extra>" },
        { type: "scatter", mode: "lines", x, y: r.equity_curve.map((p) => p.benchmark), name: T("All tracked stocks (equal weight)"), line: { color: css("--series-2"), width: 2 }, hovertemplate: "Benchmark: %{y:.3f}<extra></extra>" }],
        { height: 300, yaxis: { gridcolor: css("--border"), tickformat: ".2f", title: { text: T("Growth of ₹1") } } });
    }
  }

  async function pageCompare(param) {
    const sc = await getJSON("scanner.json");
    const pre = (param || "").split(",").filter(Boolean).slice(0, 3);
    view.innerHTML = `<div class="page-head"><div><h1>${bi("Compare stocks", "ಷೇರುಗಳ ಹೋಲಿಕೆ")}</h1><p>${bp("Pick up to three stocks. Prices are indexed to 100 at the start so they share one axis.", "ಮೂರು ಷೇರುಗಳವರೆಗೆ ಆಯ್ಕೆಮಾಡಿ. ಹೋಲಿಸಲು ಸುಲಭವಾಗುವಂತೆ ಬೆಲೆಗಳನ್ನು ಆರಂಭದಲ್ಲಿ 100 ಕ್ಕೆ ಸಮಗೊಳಿಸಲಾಗಿದೆ.")}</p></div></div>
      <div class="filters">${[0, 1, 2].map((i) => `<input list="symbolList" id="cmp${i}" placeholder="Symbol ${i + 1}" value="${esc(pre[i] || "")}" style="width:160px">`).join("")}<button class="btn primary" id="cmpGo">Compare</button></div><div id="cmpOut"></div>`;
    const go = async () => {
      const syms = [0, 1, 2].map((i) => $(`#cmp${i}`).value.trim().toUpperCase()).filter(Boolean);
      const rows = syms.map((s) => sc.rows.find((r) => r.symbol === s)).filter(Boolean);
      if (!rows.length) { $("#cmpOut").innerHTML = `<p class="muted">Enter valid NSE symbols.</p>`; return; }
      history.replaceState(null, "", `#/compare/${rows.map((r) => r.symbol).join(",")}`);
      const det = await Promise.all(rows.map((r) => getJSON(`stocks/${r.file}.json`)));
      const line = (label, f) => `<tr><td>${label}</td>${det.map((d) => `<td class="num">${f(d)}</td>`).join("")}</tr>`;
      $("#cmpOut").innerHTML = `<div class="card"><div id="cmpChart" class="chart"></div></div>
        <div class="table-wrap section"><table><thead><tr><th></th>${det.map((d) => `<th class="num">${stockLink(d.symbol.replace(/[^A-Za-z0-9_-]/g, "_"), d.symbol)}</th>`).join("")}</tr></thead><tbody>
        ${line("Price", (d) => inr(d.chart.close.at(-1)))}${line("Sector", (d) => esc(d.sector))}${line("Size", (d) => esc(d.cap_category))}
        ${line("RSI 14", (d) => fmt(d.indicators.rsi_14, 1))}${line("ADX", (d) => fmt(d.indicators.adx, 1))}${line("Technical score", (d) => fmt(d.recommendation.technical.score, 0))}
        ${line("Fundamental label", (d) => esc(d.fundamentals.scorecard?.label || "n/a"))}${line("ROE %", (d) => fmt(d.fundamentals.ratios?.roe?.value))}${line("Debt / equity", (d) => fmt(d.fundamentals.ratios?.debt_to_equity?.value))}
        ${line("P/E", (d) => fmt(d.fundamentals.ratios?.pe?.value))}${line("Volatility (ann.)", (d) => fmt(d.quant.annual_volatility_pct) + "%")}${line("Max drawdown (3y)", (d) => fmt(d.quant.max_drawdown_pct) + "%")}
        ${line("Beta", (d) => fmt(d.quant.beta_1y))}${line("Sharpe", (d) => fmt(d.quant.sharpe))}
        ${(det[0].recommendation.horizons || []).map((h, i) => line(`${h.horizon_days}-day assessment`, (d) => labelPill(d.recommendation.horizons[i]?.label) + (d.recommendation.horizons[i]?.probabilities ? `<br><small>▲ ${fmt(d.recommendation.horizons[i].probabilities.bullish, 1)}%</small>` : ""))).join("")}
        </tbody></table></div>`;
      const colors = [css("--series-1"), css("--series-2"), css("--series-3")];
      plot($("#cmpChart"), det.map((d, i) => { const c = d.chart.close, b = c.find((v) => v != null); return { type: "scatter", mode: "lines", x: d.chart.date, y: c.map((v) => (v == null ? null : (v / b) * 100)), name: d.symbol, line: { color: colors[i], width: 2 }, hovertemplate: `${d.symbol}: %{y:.1f}<extra></extra>` }; }),
        { height: 320, yaxis: { gridcolor: css("--border"), tickformat: ".0f", title: { text: T("Indexed (start = 100)") } } });
    };
    $("#cmpGo").addEventListener("click", go);
    if (pre.length) go();
  }

  async function pageSwing() {
    const m = await getJSON("model.json");
    const anyPass = Object.values(m.horizons || {}).some((r) => r.gate?.passed);
    view.innerHTML = `<div class="page-head"><div><h1>${bi("Swing prediction dashboard", "ಸ್ವಿಂಗ್ ಮುನ್ಸೂಚನೆ")}</h1><p>${bp("Separate calibrated models for 2, 5 and 10 trading days.", "2, 5 ಮತ್ತು 10 ವಹಿವಾಟು ದಿನಗಳಿಗೆ ಪ್ರತ್ಯೇಕ ಮಾದರಿಗಳು.")}</p></div></div>
      ${anyPass ? "" : `<div class="notice critical">${bp(`<strong>No swing model currently passes validation.</strong> Every stock therefore shows “Insufficient evidence — no recommendation”. This is the honest outcome when the data contains no reliable edge. See <a href="#/model">Model performance</a>.`,
  `<strong>ಯಾವುದೇ ಸ್ವಿಂಗ್ ಮಾದರಿ ಸದ್ಯ ಪರೀಕ್ಷೆಯಲ್ಲಿ ಉತ್ತೀರ್ಣವಾಗಿಲ್ಲ.</strong> ಆದ್ದರಿಂದ ಎಲ್ಲಾ ಷೇರುಗಳಿಗೆ “ಸಾಕಷ್ಟು ಆಧಾರವಿಲ್ಲ — ಶಿಫಾರಸು ಇಲ್ಲ” ಎಂದು ತೋರಿಸಲಾಗಿದೆ. ದತ್ತಾಂಶದಲ್ಲಿ ವಿಶ್ವಾಸಾರ್ಹ ಸಂಕೇತ ಇಲ್ಲದಿದ್ದಾಗ ಇದೇ ಪ್ರಾಮಾಣಿಕ ಫಲಿತಾಂಶ. <a href="#/model">ಮಾದರಿ ಕಾರ್ಯಕ್ಷಮತೆ</a> ನೋಡಿ.`)}</div>`}
      <div class="grid g3">${Object.entries(m.horizons || {}).map(([h, r]) => `<div class="card"><h2>${h} trading days</h2>${r.gate?.passed ? labelPill("bullish").replace("Bullish", "Validated") : labelPill("insufficient")}
        <p class="muted">Model: ${esc(r.selected_model || "—")} · Brier skill ${fmt(r.metrics?.[r.selected_model]?.brier_skill_score, 4)}</p>
        <a class="btn" href="#/scanner">Open scanner (choose ${h}-day horizon) →</a></div>`).join("")}</div>`;
    const sc = await getJSON("scanner.json");
    const div = document.createElement("div"); div.className = "section"; view.appendChild(div);
    const best = (h) => sc.rows.filter((r) => ["bullish", "bearish"].includes(r.horizons[h]?.label)).sort((a, b) => Math.max(b.horizons[h].p.bullish, b.horizons[h].p.bearish) - Math.max(a.horizons[h].p.bullish, a.horizons[h].p.bearish)).slice(0, 15);
    div.innerHTML = Object.keys(m.horizons || {}).map((h) => `<div class="card section"><h2>Strongest ${h}-day signals</h2>${best(h).length ? `<div class="table-wrap"><table><thead><tr><th>Stock</th><th>Assessment</th><th>Probabilities</th><th class="num">Price</th></tr></thead><tbody>
      ${best(h).map((r) => `<tr><td class="sym">${stockLink(r.file, r.symbol)}<span class="name">${esc(r.name)}</span></td><td>${labelPill(r.horizons[h].label)}</td><td>${probBar(r.horizons[h].p)}</td><td class="num">${inr(r.price)}</td></tr>`).join("")}</tbody></table></div>` : "<p class='muted'>No validated directional signals.</p>"}</div>`).join("");
  }

  function pageIntraday() {
    view.innerHTML = `<div class="page-head"><div><h1>${bi("Intraday prediction dashboard", "ದಿನದೊಳಗಿನ ಮುನ್ಸೂಚನೆ")}</h1></div></div>
      <div class="card">${labelPill("insufficient")}<p><strong>${T("Insufficient evidence — no recommendation.")}</strong></p>
      ${bp(`<p>Intraday horizons (5, 15, 30 minutes, 1 hour, end of day) need an <strong>authorised intraday data feed</strong>. This free, static deployment uses end-of-day data only, so no intraday model is trained and no intraday probability is shown.
      Showing intraday predictions from daily data would be misleading.</p>
      <h3>How to enable later</h3><ul class="clean"><li>Open a broker account that offers a free API for personal use (for example Angel One SmartAPI, Upstox, Fyers or Dhan).</li>
      <li>Implement <code>MarketDataProvider.intraday()</code> in <code>pipeline/providers/</code> for that broker (credentials in environment variables only).</li>
      <li>Run it on your own PC or server (Option B). Broker data is licensed for your personal use — do not publish it on a public website.</li></ul>`,
      `<p>ದಿನದೊಳಗಿನ ಅವಧಿಗಳ (5, 15, 30 ನಿಮಿಷ, 1 ಗಂಟೆ, ದಿನದ ಅಂತ್ಯ) ಮುನ್ಸೂಚನೆಗೆ <strong>ಅಧಿಕೃತ ನೇರ ದತ್ತಾಂಶ</strong> ಬೇಕು. ಈ ಉಚಿತ ವ್ಯವಸ್ಥೆ ದಿನದ ಅಂತ್ಯದ ದತ್ತಾಂಶವನ್ನು ಮಾತ್ರ ಬಳಸುವುದರಿಂದ ದಿನದೊಳಗಿನ ಮಾದರಿಯನ್ನು ತರಬೇತಿಗೊಳಿಸಿಲ್ಲ ಮತ್ತು ಸಂಭವನೀಯತೆ ತೋರಿಸುವುದಿಲ್ಲ.
      ದೈನಂದಿನ ದತ್ತಾಂಶದಿಂದ ದಿನದೊಳಗಿನ ಮುನ್ಸೂಚನೆ ತೋರಿಸಿದರೆ ಅದು ತಪ್ಪುದಾರಿಗೆಳೆಯುತ್ತದೆ.</p>
      <h3>ಮುಂದೆ ಸಕ್ರಿಯಗೊಳಿಸುವುದು ಹೇಗೆ</h3><ul class="clean"><li>ವೈಯಕ್ತಿಕ ಬಳಕೆಗೆ ಉಚಿತ API ನೀಡುವ ಬ್ರೋಕರ್ ಖಾತೆ ತೆರೆಯಿರಿ (ಉದಾ. Angel One SmartAPI, Upstox, Fyers ಅಥವಾ Dhan).</li>
      <li>ಆ ಬ್ರೋಕರ್‌ಗಾಗಿ <code>pipeline/providers/</code> ನಲ್ಲಿ <code>MarketDataProvider.intraday()</code> ಬರೆಯಿರಿ (ಗುಪ್ತ ಮಾಹಿತಿ environment variables ನಲ್ಲಿ ಮಾತ್ರ).</li>
      <li>ಅದನ್ನು ನಿಮ್ಮ ಸ್ವಂತ ಕಂಪ್ಯೂಟರ್ ಅಥವಾ ಸರ್ವರ್‌ನಲ್ಲಿ ಓಡಿಸಿ (ಆಯ್ಕೆ B). ಬ್ರೋಕರ್ ದತ್ತಾಂಶ ನಿಮ್ಮ ವೈಯಕ್ತಿಕ ಬಳಕೆಗೆ ಮಾತ್ರ — ಸಾರ್ವಜನಿಕ ವೆಬ್‌ಸೈಟ್‌ನಲ್ಲಿ ಪ್ರಕಟಿಸಬೇಡಿ.</li></ul>`)}</div>`;
  }

  async function pageAlerts() {
    const st = STATUS || {};
    const tg = st.steps?.telegram || {};
    const s = st.settings || {};
    view.innerHTML = `<div class="page-head"><div><h1>${bi("Alert configuration", "ಎಚ್ಚರಿಕೆ ಸಂರಚನೆ")}</h1><p>${bp("Telegram alerts are sent by the scheduled GitHub Action, not by this website. Duplicate alerts are suppressed for 10 days.", "Telegram ಎಚ್ಚರಿಕೆಗಳನ್ನು ಈ ವೆಬ್‌ಸೈಟ್ ಅಲ್ಲ, ನಿಗದಿತ GitHub Action ಕಳುಹಿಸುತ್ತದೆ. ಒಂದೇ ಎಚ್ಚರಿಕೆಯನ್ನು 10 ದಿನಗಳವರೆಗೆ ಮತ್ತೆ ಕಳುಹಿಸುವುದಿಲ್ಲ.")}</p></div></div>
      <div class="grid g2"><div class="card"><h2>Current status</h2><dl class="kv"><dt>Telegram configured</dt><dd>${tg.configured ? "✔ yes" : "✖ no"}</dd>
        <dt>Last run</dt><dd>${tg.candidates ?? 0} candidates, ${tg.new ?? 0} new, ${tg.sent ?? 0} sent, ${tg.failed ?? 0} failed</dd>${tg.note ? `<dt>Note</dt><dd>${esc(tg.note)}</dd>` : ""}
        ${(tg.errors || []).length ? `<dt>Errors</dt><dd>${tg.errors.map(esc).join("<br>")}</dd>` : ""}</dl></div>
      <div class="card"><h2>Thresholds in use</h2><dl class="kv">${Object.entries(s.alerts || {}).map(([k, v]) => `<dt>${esc(k.replace(/_/g, " "))}</dt><dd>${esc(v)}</dd>`).join("") || "<dt>—</dt><dd>Run the pipeline first</dd>"}</dl>
        <p class="muted">${bp(`Change them in <code>config/settings.json</code> → <code>"alerts"</code> and commit. Schedules are in <code>.github/workflows/daily-pipeline.yml</code>.`,
          `ಇವುಗಳನ್ನು <code>config/settings.json</code> → <code>"alerts"</code> ನಲ್ಲಿ ಬದಲಿಸಿ commit ಮಾಡಿ. ವೇಳಾಪಟ್ಟಿ <code>.github/workflows/daily-pipeline.yml</code> ನಲ್ಲಿದೆ.`)}</p></div></div>
      <div class="card section"><h2>Set up Telegram (5 minutes)</h2>${bp(`<ol class="clean">
        <li>In Telegram, open <strong>@BotFather</strong>, send <code>/newbot</code> and copy the bot token.</li>
        <li>Send any message to your new bot, then open <code>https://api.telegram.org/bot&lt;TOKEN&gt;/getUpdates</code> and copy <code>chat.id</code>.</li>
        <li>GitHub repository → Settings → Secrets and variables → Actions → add <code>TELEGRAM_BOT_TOKEN</code> and <code>TELEGRAM_CHAT_ID</code>.</li>
        <li>Run the workflow once. Alerts cover major order wins, important filings, negative events, strong validated signals, breakouts/breakdowns and unusual volume.</li></ol>
        <p class="muted">Never put the token in code or in <code>settings.json</code>. Alerts are research notes, never buy/sell instructions.</p>`,
        `<ol class="clean">
        <li>Telegram ನಲ್ಲಿ <strong>@BotFather</strong> ತೆರೆಯಿರಿ, <code>/newbot</code> ಕಳುಹಿಸಿ ಮತ್ತು bot token ನಕಲಿಸಿ.</li>
        <li>ನಿಮ್ಮ ಹೊಸ bot ಗೆ ಯಾವುದಾದರೂ ಸಂದೇಶ ಕಳುಹಿಸಿ, ನಂತರ <code>https://api.telegram.org/bot&lt;TOKEN&gt;/getUpdates</code> ತೆರೆದು <code>chat.id</code> ನಕಲಿಸಿ.</li>
        <li>GitHub repository → Settings → Secrets and variables → Actions → <code>TELEGRAM_BOT_TOKEN</code> ಮತ್ತು <code>TELEGRAM_CHAT_ID</code> ಸೇರಿಸಿ.</li>
        <li>Workflow ಅನ್ನು ಒಮ್ಮೆ ಓಡಿಸಿ. ದೊಡ್ಡ ಆರ್ಡರ್ ಗೆಲುವು, ಮುಖ್ಯ ಪ್ರಕಟಣೆಗಳು, ನಕಾರಾತ್ಮಕ ಘಟನೆಗಳು, ಬಲವಾದ ಪರಿಶೀಲಿತ ಸಂಕೇತಗಳು, ಬ್ರೇಕ್‌ಔಟ್/ಬ್ರೇಕ್‌ಡೌನ್ ಮತ್ತು ಅಸಾಮಾನ್ಯ ವಹಿವಾಟಿಗೆ ಎಚ್ಚರಿಕೆ ಬರುತ್ತದೆ.</li></ol>
        <p class="muted">Token ಅನ್ನು ಕೋಡ್‌ನಲ್ಲಿ ಅಥವಾ <code>settings.json</code> ನಲ್ಲಿ ಎಂದೂ ಇಡಬೇಡಿ. ಎಚ್ಚರಿಕೆಗಳು ಸಂಶೋಧನಾ ಟಿಪ್ಪಣಿಗಳು ಮಾತ್ರ; ಖರೀದಿ/ಮಾರಾಟದ ಸೂಚನೆಗಳಲ್ಲ.</p>`)}</div>`;
  }

  async function pageLearn(focus) {
    const L = await getJSON(CFG.learnUrl);
    view.innerHTML = `<div class="page-head"><div><h1>${bi("Learning centre", "ಕಲಿಕಾ ಕೇಂದ್ರ")}</h1><p>${bp(esc(L.note_en), esc(L.note_kn))}</p></div></div>
      <div class="filters"><input type="search" id="lq" placeholder="Search: RSI, ROE, VaR, ಬೆಂಬಲ…"><label>Topic <select id="lg"><option value="">All topics</option>${Object.entries(L.groups).map(([k, g]) => `<option value="${k}">${esc(I18N.lang === "kn" ? g.kn : g.en)}</option>`).join("")}</select></label>
        <label>Language <select id="ll"><option value="both">English + ಕನ್ನಡ</option><option value="en" ${I18N.lang === "en" ? "selected" : ""}>English</option><option value="kn" ${I18N.lang === "kn" ? "selected" : ""}>ಕನ್ನಡ</option></select></label></div><div id="lout"></div>`;
    const st = { q: "", g: "", lang: I18N.lang };
    const field = (label, en, kn) => {
      const showEn = st.lang !== "kn" && en, showKn = st.lang !== "en" && kn;
      return showEn || showKn ? `<div><h4>${label}</h4>${showEn ? `<p>${esc(en)}</p>` : ""}${showKn ? `<p class="kn">${esc(kn)}</p>` : ""}</div>` : "";
    };
    const draw = () => {
      const q = st.q.toLowerCase();
      const items = L.items.filter((i) => (!st.g || i.group === st.g) && (!q || JSON.stringify(i).toLowerCase().includes(q)));
      $("#lout").innerHTML = Object.entries(L.groups).map(([gk, g]) => {
        const its = items.filter((i) => i.group === gk);
        if (!its.length) return "";
        return `<h2 class="section">${bi(g.en, g.kn)}</h2>` + its.map((i) => `<details class="learn-item" id="learn-${esc(i.id)}" ${focus === i.id ? "open" : ""}>
          <summary class="notranslate">${bp(`<span><strong>${esc(i.en)}</strong> <span class="muted">${esc(i.full || "")}</span></span><span class="kn muted">${esc(i.kn)}</span>`,
            `<span><strong>${esc(i.kn)}</strong> <span class="muted">${esc(i.en)} · ${esc(i.full || "")}</span></span>`)}</summary>
          <div class="learn-body"><div class="full"><h4>Formula · ಸೂತ್ರ</h4><div class="formula">${esc(i.formula)}</div></div>
            ${field("What it measures · ಏನನ್ನು ಅಳೆಯುತ್ತದೆ", i.what, i.what_kn)}${field("How to use · ಹೇಗೆ ಬಳಸುವುದು", i.use, i.use_kn)}
            ${i.bull ? field("Bullish reading", i.bull) : ""}${i.bear ? field("Bearish reading", i.bear) : ""}${i.side ? field("Sideways market", i.side) : ""}
            ${i.limits ? field("Limitations · ಮಿತಿಗಳು", i.limits) : ""}${i.mistakes ? field("Common mistakes · ಸಾಮಾನ್ಯ ತಪ್ಪುಗಳು", i.mistakes) : ""}
            ${i.example ? `<div class="full"><h4>Example (hypothetical) · ಉದಾಹರಣೆ</h4><p>${esc(i.example)}</p></div>` : ""}</div></details>`).join("");
      }).join("") || `<p class="empty">Nothing found.</p>`;
      if (focus) document.getElementById("learn-" + focus)?.scrollIntoView({ block: "start" });
      focus = null;
    };
    $("#lq").addEventListener("input", (e) => { st.q = e.target.value; draw(); });
    $("#lg").addEventListener("input", (e) => { st.g = e.target.value; draw(); });
    $("#ll").addEventListener("input", (e) => { st.lang = e.target.value; draw(); });
    draw();
  }

  async function pageStatus() {
    const s = await getJSON("status.json", { fresh: true });
    const steps = s.steps || {};
    const kv = (o) => `<dl class="kv">${Object.entries(o || {}).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${typeof v === "object" && v !== null ? `<code>${esc(JSON.stringify(v))}</code>` : esc(v)}</dd>`).join("")}</dl>`;
    view.innerHTML = `<div class="page-head"><div><h1>${bi("System status", "ವ್ಯವಸ್ಥೆಯ ಸ್ಥಿತಿ")}</h1><p>${bp("Every data-source failure is listed here — nothing is hidden or filled in.", "ಪ್ರತಿಯೊಂದು ದತ್ತಾಂಶ ಮೂಲದ ವೈಫಲ್ಯವನ್ನು ಇಲ್ಲಿ ತೋರಿಸಲಾಗಿದೆ — ಏನನ್ನೂ ಮುಚ್ಚಿಡುವುದಿಲ್ಲ ಅಥವಾ ಕಲ್ಪಿಸುವುದಿಲ್ಲ.")}</p></div></div>
      <div class="grid g4">${[["State", s.state], ["Market date", day(s.market_date)], ["Run finished", dt(s.run_finished)], ["Duration", (s.duration_sec ?? "—") + " s"]].map(([l, v]) => `<div class="card tile"><div class="label">${l}</div><div class="value" style="font-size:1.1rem">${esc(v)}</div></div>`).join("")}</div>
      ${(s.warnings || []).length ? `<div class="notice section"><strong>Warnings</strong><ul class="clean">${s.warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul></div>` : ""}
      <div class="grid g2 section">
        <div class="card"><h2>Prices</h2>${kv(steps.prices)}</div>
        <div class="card"><h2>Instruments</h2>${kv({ master: steps.instruments?.master, universe: steps.instruments?.universe, selected: steps.instruments?.selected, mode: steps.instruments?.report?.mode })}
          <h3 class="section">Sources</h3>${kv(steps.instruments?.report?.sources)}${steps.instruments?.report?.changes ? `<h3>Changes since last run</h3>${kv(steps.instruments.report.changes)}` : ""}</div>
        <div class="card"><h2>News feeds</h2>${kv({ fetched: steps.news?.fetched, new: steps.news?.new, stored: steps.news?.stored })}<h3 class="section">Per feed</h3>${kv(steps.news?.feeds)}</div>
        <div class="card"><h2>Fundamentals, models & alerts</h2>${kv(steps.fundamentals)}<h3 class="section">Models</h3>${kv(steps.models)}<h3 class="section">Telegram</h3>${kv(steps.telegram)}</div>
      </div><p class="muted">Pipeline version ${esc(s.version)} · data location <code>${esc(BASE)}</code></p>`;
  }

  // ------------------------------------------------------------------ router
  const routes = [
    [/^#?\/?$/, () => pageOverview()], [/^#\/scanner(?:\/(\w+))?$/, (m) => pageScanner(m[1])], [/^#\/stock\/(.+)$/, (m) => pageStock(decodeURIComponent(m[1]))],
    [/^#\/news$/, () => pageNews()], [/^#\/orders$/, () => pageNews("orders")], [/^#\/announcements$/, () => pageNews("announcements")],
    [/^#\/model$/, () => pageModel()], [/^#\/backtest$/, () => pageBacktest()], [/^#\/compare(?:\/(.*))?$/, (m) => pageCompare(decodeURIComponent(m[1] || ""))],
    [/^#\/swing$/, () => pageSwing()], [/^#\/intraday$/, () => pageIntraday()], [/^#\/alerts$/, () => pageAlerts()],
    [/^#\/learn(?:\/(\w+))?$/, (m) => pageLearn(m[1])], [/^#\/status$/, () => pageStatus()],
  ];
  async function route() {
    const h = location.hash || "#/";
    clearInterval(liveTimer);
    liveHooks.length = 0;
    markNav();
    $("#sidebar").classList.remove("open");
    const r = routes.find(([re]) => re.test(h));
    view.innerHTML = `<div class="loader">Loading…</div>`;
    window.scrollTo(0, 0);
    const needsData = !/^#\/(learn|intraday)/.test(h);
    if (needsData && !STATUS) { setupScreen(new Error("status.json not found")); return; }
    try { await (r ? r[1](h.match(r[0])) : pageOverview()); startLive(); }
    catch (e) {
      console.error(e);
      if (/404/.test(e.message) && needsData) setupScreen(e);
      else view.innerHTML = `<div class="notice critical"><strong>Could not load this page.</strong> ${esc(e.message)}</div>`;
    }
  }

  async function init() {
    renderNav();
    const ls = $("#langSel");
    ls.value = I18N.lang;
    ls.addEventListener("change", async () => {
      I18N.set(ls.value);
      cache.clear();
      await loadStatus();
      liveBadge();
      route();
    });
    I18N.start();
    $("#menuBtn").addEventListener("click", () => $("#sidebar").classList.toggle("open"));
    $("#themeBtn").addEventListener("click", () => {
      const cur = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
      const next = cur === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem("mi-theme", next); } catch (e) { /* storage unavailable */ }
      route();
    });
    await loadStatus();
    if (STATUS) {
      getJSON("scanner.json").then((sc) => {
        $("#symbolList").innerHTML = sc.rows.map((r) => `<option value="${esc(r.symbol)}">${esc(r.name)}</option>`).join("");
        $("#globalSearch").addEventListener("change", (e) => {
          const v = e.target.value.trim().toUpperCase();
          const r = sc.rows.find((x) => x.symbol === v) || sc.rows.find((x) => (x.name || "").toUpperCase().includes(v));
          if (r) { location.hash = `#/stock/${r.file}`; e.target.value = ""; }
        });
      }).catch(() => {});
    }
    window.addEventListener("hashchange", route);
    route();
  }
  init();
})();
