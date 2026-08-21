# Deal Bot — free 24/7 deal scanner on GitHub Actions

Watches free deal-site RSS feeds around the clock and notifies you the
moment something matches your keywords. Runs entirely on GitHub's free
Actions minutes — no server, no paid API, no machine of yours needs to
stay powered on.

## What it does

Every 6 hours (configurable), GitHub spins up a temporary free runner that:
1. Reads RSS feeds from Slickdeals, DealNews, and Woot
2. Filters entries against your keyword list
3. Skips anything it's already shown you
4. Opens a GitHub Issue with any new matches (GitHub emails you automatically)
5. Optionally posts to a Discord webhook too

## Setup (10 minutes, no coding required)

1. **Create a new GitHub repository.** Go to github.com → New repository →
   name it anything (e.g. `deal-bot`) → keep it **public** (public repos get
   unlimited free Actions minutes; private repos get 2,000 free min/month,
   which is still plenty for this).

2. **Upload these files**, keeping the folder structure exactly as-is:
   ```
   deal-bot/
   ├── .github/workflows/deal-scanner.yml
   ├── config/keywords.txt
   ├── data/seen.json
   ├── requirements.txt
   ├── scan_deals.py
   └── README.md
   ```
   Easiest way: on your new repo's page, click "Add file" → "Upload files,"
   drag the whole folder in, and commit.

3. **Edit `config/keywords.txt`** to whatever you want to track — one term
   per line (e.g. `walmart`, `airpods`, `laptop`). This is the only file
   you'll normally need to touch.

4. **Enable Actions** if prompted (Settings → Actions → General → allow
   workflows to run). It's on by default for most new repos.

5. **Turn on notifications for the repo** so GitHub actually emails you:
   click "Watch" on the repo (top right) → "All Activity," or at minimum
   "Custom" → Issues.

6. **(Optional) Add a Discord webhook** for instant pings: in Discord,
   go to a channel → Settings → Integrations → Webhooks → New Webhook →
   copy the URL. Then in your GitHub repo: Settings → Secrets and
   variables → Actions → New repository secret → name it
   `DISCORD_WEBHOOK_URL` → paste the URL.

7. **Test it manually** before waiting for the schedule: go to the
   Actions tab → "Deal Scanner" workflow → "Run workflow." Check the logs
   and, if matches were found, check the Issues tab.

That's it — it now runs unattended, forever, for $0.

## Tuning it

- **Change frequency:** edit the `cron` line in
  `.github/workflows/deal-scanner.yml`. `0 */6 * * *` = every 6 hours.
  `0 */2 * * *` = every 2 hours. (Times are UTC.)
- **Add more feeds:** edit the `FEEDS` list near the top of
  `scan_deals.py`. Most deal sites publish an RSS feed — look for an RSS
  icon or check `sitename.com/rss`.
- **Feeds go stale sometimes:** if a feed URL stops working, the workflow
  logs a warning but keeps running the others — it won't crash the whole
  job.

## Price watcher (optional add-on)

In addition to the RSS-based deal scanner, this repo includes
`price_watch.py` — a general-purpose price tracker for specific product
pages you choose, not just what aggregator sites happen to publish.

### How to use it

1. **Find the CSS selector for the price** on a product page:
   - Open the product page in Chrome or Firefox
   - Right-click directly on the price → "Inspect"
   - In the dev tools panel that opens, right-click the highlighted HTML
     element → Copy → "Copy selector"
   - That's your `selector` value

2. **Edit `config/products.json`**, one entry per product:
   ```json
   [
     {
       "name": "Sony WH-1000XM5 Headphones",
       "url": "https://example-store.com/product/12345",
       "selector": ".price-now",
       "target_price": 250
     }
   ]
   ```
   - `target_price` is optional — set it if you want an alert as soon as
     the price hits that number, even if it's the first time it drops.
   - Leave `target_price` as `null` to only get alerted on any price drop.

3. Commit the file. The next scheduled run (or a manual "Run workflow")
   will pick it up automatically — no other changes needed, it's already
   wired into the same workflow as the deal scanner.

### Read this before pointing it at Amazon or Walmart specifically

- Both sites actively detect and block automated requests, including
  from shared IP ranges like GitHub's — you may get blocked, served a
  CAPTCHA page, or an incomplete page instead of real data. Success is
  not guaranteed and may be inconsistent over time.
- Both render some prices via JavaScript after the page loads, which
  this script can't see (it only reads the raw HTML the server sends,
  not what a browser draws after running JS). If the selector matches
  nothing, this is usually why.
- Smaller retailers without heavy bot-protection tend to work more
  reliably with this approach.
- If you need something that reliably handles JS-heavy, bot-protected
  sites, that requires a headless browser tool like Playwright — a
  meaningfully heavier setup than this script, and still not guaranteed
  against determined anti-bot systems.
- Scraping large retailers' sites typically violates their Terms of
  Service. Light personal use (checking a handful of products every few
  hours) is unlikely to draw attention, but this isn't legal advice, and
  you're responsible for how you use this.

## Honest limitations


- RSS feeds only cover what those sites choose to publish — it won't see
  a retailer's own site directly (e.g. it can't watch Walmart.com itself
  without a scraper, which is a bigger, more fragile project).
- Free GitHub accounts get 2,000 Actions minutes/month on private repos;
  each run of this script takes well under a minute, so even hourly runs
  use a small fraction of that. Public repos don't have this limit at all.
- This is keyword matching on RSS text, not the AI-powered filtering the
  in-chat version does — it won't understand nuance like "genuinely good
  deal" vs. "mentions a discount," just literal text matches.
