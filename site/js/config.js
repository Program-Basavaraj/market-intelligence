/*
 * Where the dashboard reads its data from.
 *
 * Recommended (saves Netlify credits): the GitHub Action pushes data to a `data` branch of your
 * PUBLIC repository and the site reads it straight from GitHub, so Netlify never redeploys:
 *   dataBase: "https://raw.githubusercontent.com/<your-github-user>/<your-repo>/data/"
 *
 * Alternative: keep "./data/" and let the Action deploy to Netlify each day
 * (each production deploy costs Netlify credits — see docs/SETUP.md).
 */
window.MI_CONFIG = {
  dataBase: "https://github.com/Program-Basavaraj/market-intelligence/blob/data/",
  learnUrl: "./learn.json",
  // Delayed quotes via the Netlify Function in netlify/functions/quotes.mjs (works only on Netlify or `netlify dev`).
  // Refreshes every refreshSeconds while the NSE market is open (09:15–15:30 IST) and the tab is visible.
  liveQuotes: { enabled: true, endpoint: "/api/quotes", refreshSeconds: 60 }
};
