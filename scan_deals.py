#!/usr/bin/env python3
"""
Free 24/7 deal scanner.

Runs on a GitHub Actions schedule (see .github/workflows/deal-scanner.yml).
Reads free public RSS feeds from deal aggregator sites, filters entries
against your keyword list, and reports anything new by:
  1. Opening a GitHub Issue in this repo (GitHub emails you automatically
     if you have notifications on).
  2. Posting to a Discord webhook, if you've set the DISCORD_WEBHOOK_URL
     secret (optional).

No paid APIs are used. Cost is $0 as long as you stay within GitHub's
free Actions minutes (2,000 min/month on free personal accounts, and
public repos get unlimited minutes).
"""

import json
import os
import re
from pathlib import Path

import feedparser
import requests

ROOT = Path(__file__).parent
KEYWORDS_FILE = ROOT / "config" / "keywords.txt"
SEEN_FILE = ROOT / "data" / "seen.json"

# Free public RSS feeds. Add or remove as you like — most deal sites
# publish one. If a feed URL goes stale, swap it for a current one from
# the site (look for an RSS/XML icon or check their /rss page).
FEEDS = [
    ("Slickdeals - Frontpage", "https://slickdeals.net/newsearch.php?rss=1&mode=frontpage"),
    ("DealNews - All Deals", "https://www.dealnews.com/rss.xml"),
    ("Woot", "https://www.woot.com/feed"),

    # More Slickdeals category feeds — confirmed current as of their own
    # staff forum posts, separate from the frontpage feed above.
    ("Slickdeals - Hot Deals", "https://slickdeals.net/newsearch.php?searchin=first&forumchoice%5B%5D=9&rss=1"),
    ("Slickdeals - Popular Deals", "https://slickdeals.net/newsearch.php?mode=popdeals&searcharea=deals&searchin=first&rss=1"),
    ("Slickdeals - Freebies", "https://slickdeals.net/newsearch.php?searchin=first&forumchoice%5B%5D=4&rss=1"),
    ("Slickdeals - Coupons", "https://slickdeals.net/newsearch.php?searchin=first&forumchoice%5B%5D=10&rss=1"),

    # DealNews category feeds — pre-narrowed to categories you actually care about.
    ("DealNews - Computers", "https://www.dealnews.com/c39/Computers/?rss=1"),
    ("DealNews - Electronics", "https://www.dealnews.com/c142/Electronics/?rss=1"),
    ("DealNews - Gaming & Toys", "https://www.dealnews.com/c186/Gaming-Toys/?rss=1"),

    # Slickdeals keyword-specific search feeds — pre-filtered before your
    # keyword list even runs. Add/remove one per thing you're hunting.
    ("Slickdeals - search: nvidia", "https://slickdeals.net/newsearch.php?rss=1&isUserSearch=1&q=nvidia&searcharea=deals&searchin=first"),
    ("Slickdeals - search: android phone", "https://slickdeals.net/newsearch.php?rss=1&isUserSearch=1&q=android+phone&searcharea=deals&searchin=first"),
    ("Slickdeals - search: monster energy", "https://slickdeals.net/newsearch.php?rss=1&isUserSearch=1&q=monster+energy&searcharea=deals&searchin=first"),
    ("Slickdeals - search: restaurant deal", "https://slickdeals.net/newsearch.php?rss=1&isUserSearch=1&q=restaurant+deal&searcharea=deals&searchin=first"),
    ("Slickdeals - search: fast food", "https://slickdeals.net/newsearch.php?rss=1&isUserSearch=1&q=fast+food&searcharea=deals&searchin=first"),
    ("Slickdeals - search: grocery", "https://slickdeals.net/newsearch.php?rss=1&isUserSearch=1&q=grocery&searcharea=deals&searchin=first"),

    # UNVERIFIED: this Brad's Deals feed address is several years old and
    # I couldn't fully confirm it's still live. It's safe to include —
    # if it's dead, the script just logs a warning and moves on — but
    # don't be surprised if this one never produces results.
    ("Brad's Deals - Blog (unverified)", "http://feeds.feedburner.com/BradsDealsBlog"),
]

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY")  # e.g. "yourname/deal-bot"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")


def load_keywords():
    if not KEYWORDS_FILE.exists():
        return []
    lines = KEYWORDS_FILE.read_text(encoding="utf-8").splitlines()
    return [
        line.strip().lower()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]


def load_seen():
    if not SEEN_FILE.exists():
        return set()
    try:
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return set()


def save_seen(seen_ids):
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Cap memory size so the file doesn't grow forever
    trimmed = list(seen_ids)[-5000:]
    SEEN_FILE.write_text(json.dumps(trimmed, indent=2), encoding="utf-8")


def entry_id(entry):
    return entry.get("id") or entry.get("link") or entry.get("title", "")


def strip_html(text):
    return re.sub(r"<[^>]+>", " ", text or "").strip()


def matches_keywords(entry, keywords):
    if not keywords:
        return True  # no filter set = report everything
    haystack = (entry.get("title", "") + " " + strip_html(entry.get("summary", ""))).lower()
    return any(kw in haystack for kw in keywords)


def fetch_new_deals():
    keywords = load_keywords()
    seen = load_seen()
    new_deals = []

    for source_name, url in FEEDS:
        try:
            parsed = feedparser.parse(url)
        except Exception as e:
            print(f"[warn] Could not fetch {source_name}: {e}")
            continue

        for entry in parsed.entries:
            eid = entry_id(entry)
            if not eid or eid in seen:
                continue
            if not matches_keywords(entry, keywords):
                continue

            new_deals.append(
                {
                    "id": eid,
                    "source": source_name,
                    "title": entry.get("title", "Untitled deal"),
                    "link": entry.get("link", ""),
                    "summary": strip_html(entry.get("summary", ""))[:300],
                }
            )
            seen.add(eid)

    save_seen(seen)
    return new_deals


def post_github_issue(deals):
    if not (GITHUB_TOKEN and GITHUB_REPOSITORY):
        print("[info] Skipping GitHub issue (no token/repo in env).")
        return

    lines = [f"Found **{len(deals)}** new deal(s) matching your keywords.\n"]
    for d in deals:
        lines.append(f"### {d['title']}")
        lines.append(f"*Source: {d['source']}*")
        if d["summary"]:
            lines.append(d["summary"])
        if d["link"]:
            lines.append(f"[View deal]({d['link']})")
        lines.append("")

    body = "\n".join(lines)
    title = f"🔥 {len(deals)} new deal(s) found"

    resp = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPOSITORY}/issues",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        },
        json={"title": title, "body": body, "labels": ["deal-alert"]},
        timeout=30,
    )
    if resp.status_code >= 300:
        print(f"[warn] GitHub issue creation failed: {resp.status_code} {resp.text}")
    else:
        print(f"[info] Opened issue: {resp.json().get('html_url')}")


def post_discord(deals):
    if not DISCORD_WEBHOOK_URL:
        return  # optional, silently skip if not configured

    lines = [f"**{len(deals)} new deal(s) found:**"]
    for d in deals[:10]:  # Discord messages have a length limit
        lines.append(f"• **{d['title']}** ({d['source']}) — {d['link']}")

    resp = requests.post(DISCORD_WEBHOOK_URL, json={"content": "\n".join(lines)}, timeout=30)
    if resp.status_code >= 300:
        print(f"[warn] Discord post failed: {resp.status_code} {resp.text}")


def main():
    deals = fetch_new_deals()
    print(f"[info] Found {len(deals)} new matching deal(s).")

    if not deals:
        return

    post_github_issue(deals)
    post_discord(deals)


if __name__ == "__main__":
    main()
