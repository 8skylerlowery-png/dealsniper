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

    # UNVERIFIED: this Brad's Deals feed address is several years old and
    # I couldn't fully confirm it's still live. It's safe to include —
    # if it's dead, the script just logs a warning and moves on — but
    # don't be surprised if this one never produces results.
    ("Brad's Deals - Blog (unverified)", "http://feeds.feedburner.com/BradsDealsBlog"),
]
