# Setup guide — GitHub + Netlify (free)

Time needed: ~20 minutes, plus the first pipeline run (30–60 min for Nifty 500; ~5–10 min for Nifty 50).

## Why the data lives on GitHub, not inside Netlify
On Netlify's credit-based Free plan you get **300 credits per month** and **each production deploy costs 15 credits** (about 20 deploys a month). Redeploying the site every day would run out before month-end. So:

- Netlify hosts the **website** and redeploys only when you change code.
- GitHub Actions writes fresh **data** to a branch called `data` in your repo.
- The website reads that data straight from `raw.githubusercontent.com`. This costs **no Netlify credits**.

This needs a **public** repository (raw GitHub URLs of private repos need a login). The data is only market prices, headlines and links, and no secrets. If you must keep the repo private, see "Option: private repository" at the end.

---

## Step 1 — Put the project on GitHub
1. Create a free account at github.com.
2. Click **New repository** and name it e.g. `market-intelligence`. Set it to **Public** and leave it empty (no README).
3. Upload the project:
   - **Easiest:** on the empty repo page click **uploading an existing file**. Drag in all files and folders from the unzipped project, including the hidden `.github` folder, then **Commit**.
     *Tip:* if your file browser hides `.github`, use the git commands below instead.
   - **With git:**
     ```bash
     cd market-intelligence
     git init && git add -A && git commit -m "Initial import"
     git branch -M main
     git remote add origin https://github.com/<you>/market-intelligence.git
     git push -u origin main
     ```

## Step 2 — Allow the workflow to publish data
Repository → **Settings → Actions → General**:
- *Actions permissions*: **Allow all actions**.
- *Workflow permissions*: **Read and write permissions** → Save.

## Step 3 — Run the pipeline once
Repository → **Actions** → **Daily market pipeline** → **Run workflow**.
- For a fast first test, type `nifty50` in *universe*. Later runs use `nifty500` from `config/settings.json`.
- When it finishes (green tick), a new branch **`data`** appears with `status.json`, `scanner.json`, `stocks/…`.
- Open the run log if it fails. Data-source failures do not stop the run; they are listed on the site's **System status** page.

After this, it runs by itself (times in IST, Mon–Fri):
- **19:15** — full end-of-day run
- **09:45, 11:45, 13:45, 15:45** — news and alerts refresh

GitHub's scheduler can start runs a few minutes late.

## Step 4 — Point the website at your data
Edit `site/js/config.js` on GitHub (pencil icon) and change one line:
```js
dataBase: "https://raw.githubusercontent.com/<you>/market-intelligence/data/",
```
Commit.

## Step 5 — Connect Netlify
1. Log in at netlify.com → **Add new project → Import an existing project → GitHub** → choose your repo.
2. Build settings are read from `netlify.toml`: publish directory `site`, no build command. Click **Deploy**.
3. **Important (saves credits):** Project configuration → **Build & deploy → Branches and deploy contexts** → set *Branch deploys* to **None**, so Netlify does not build the `data` branch.
4. Open your `*.netlify.app` URL. The top bar shows two badges:
   - **"End-of-day / delayed data"** — the date of the analysis data.
   - **"Delayed live quotes"** (during market hours) or **"Market closed"** — from the live-quotes function, which Netlify deploys automatically from `netlify/functions/`. You don't need to set anything up.

### Live quotes: cost and limits
- Each page view makes one quote request per minute while the market is open and the tab is visible. Results are cached at Netlify's edge for 30 seconds, so several people or tabs share one upstream call.
- Rough usage for personal use (one person, a few hours a day): a few thousand function calls a month, i.e. a few credits out of the free 300. Check **Usage & billing** in Netlify after the first week.
- To turn live quotes off, set `liveQuotes.enabled: false` in `site/js/config.js`. To refresh less often, raise `refreshSeconds` (e.g. 120).

## Step 6 (optional) — Telegram alerts
1. In Telegram, chat with **@BotFather** → `/newbot` → copy the **token**.
2. Send any message to your bot. Then open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser and copy `"chat":{"id": …}`.
3. GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
4. Thresholds are in `config/settings.json` → `alerts`.

## Updating
- Change settings or code → commit to `main`. Netlify redeploys the site (1 deploy = 15 credits); the data keeps updating on its own.
- Each January, add the year's NSE trading holidays to `config/holidays.json`.
- To retrain models immediately: Actions → Run workflow → `force_retrain = true` (otherwise they retrain weekly).

## Troubleshooting
| Symptom | Cause / fix |
|---|---|
| Site shows "no data has been generated yet" | `config.js` still says `./data/`, the repo is private, or the workflow hasn't run. Open the `dataBase` URL + `status.json` in a browser to test. |
| Status page: many price failures | Yahoo sometimes throttles cloud IPs. The next run retries, and the cache keeps earlier data. Reduce the universe if it persists. |
| Status page: NSE / Nifty list "failed: HTTP 403" | These sites often block cloud servers. The pipeline falls back to the last saved list, or to the bundled fallback list (flagged on the page). |
| All stocks "Insufficient evidence" | The models did not pass validation. That is the honest outcome, not a bug. See **Model performance** for the reasons. |
| Workflow error "Permission denied to github-actions" | Step 2 was not done (needs Read and write permissions). |
| Charts blank | The browser blocked `cdn.plot.ly` (ad-blocker or corporate network). |
| Badge says "Live quotes unavailable" | Yahoo is throttling Netlify's servers, or the function isn't deployed (check Netlify → Logs → Functions → `quotes`). Prices fall back to end-of-day; it retries on the next page load. |

## Option: private repository
Keep `dataBase: "./data/"`, set repository **variable** `DEPLOY_TO_NETLIFY=true`, and add secrets `NETLIFY_AUTH_TOKEN` (Netlify → User settings → Applications → Personal access token) and `NETLIFY_SITE_ID` (Project configuration → General).

The evening run will then deploy the site together with the data. Weekday deploys (~22/month × 15 = ~330 credits) exceed the 300-credit Free plan. To stay within it, reduce the schedule, e.g. change the evening cron to `45 13 * * 1,3,5` (3 days a week), or use a paid plan.
