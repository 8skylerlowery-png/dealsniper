#!/usr/bin/env python3
"""
General-purpose price watcher.

Give it a list of product page URLs plus a CSS selector pointing at the
price on each page (config/products.json). On each run it:
  1. Fetches the page
  2. Pulls the text at your selector, parses it as a price
  3. Compares to the last price it saw (data/prices.json)
  4. Reports a drop (or hitting your target price) via GitHub Issue and
     optional Discord webhook

Honest limits, read before relying on this:
  - Sites with heavy bot-detection (Amazon, and increasingly Walmart)
    may block requests from shared IP ranges like GitHub Actions runners,
    or serve a CAPTCHA page instead of the real page. This works best on
    sites without aggressive anti-bot protection.
  - Sites that render prices with JavaScript (rather than plain HTML)
    won't work with this approach — this script only sees the raw HTML
    a server returns, not what a browser renders after running JS. A
    headless-browser tool like Playwright can handle that, but it's a
    heavier, separate setup.
  - Selectors break when a site redesigns its page. If a product stops
    reporting, the selector is the first thing to check.
"""

import json
import os
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
PRODUCTS_FILE = ROOT / "config" / "products.json"
PRICES_FILE = ROOT / "data" / "prices.json"

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

PRICE_RE = re.compile(r"[\d,]+\.?\d*")


def load_products():
    if not PRODUCTS_FILE.exists():
        return []
    return json.loads(PRODUCTS_FILE.read_text(encoding="utf-8"))


def load_prices():
    if not PRICES_FILE.exists():
        return {}
    try:
        return json.loads(PRICES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_prices(prices):
    PRICES_FILE.parent.mkdir(parents=True, exist_ok=True)
    PRICES_FILE.write_text(json.dumps(prices, indent=2), encoding="utf-8")


def parse_price(text):
    if not text:
        return None
    match = PRICE_RE.search(text.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group().replace(",", ""))
    except ValueError:
        return None


def fetch_price(product):
    try:
        resp = requests.get(product["url"], headers=HEADERS, timeout=20)
    except requests.RequestException as e:
        print(f"[warn] Could not fetch {product['name']}: {e}")
        return None

    if resp.status_code != 200:
        print(f"[warn] {product['name']}: got HTTP {resp.status_code} (site may be blocking automated requests)")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    el = soup.select_one(product["selector"])
    if not el:
        print(f"[warn] {product['name']}: selector '{product['selector']}' matched nothing. "
              f"The page may render prices via JavaScript, or the selector needs updating.")
        return None

    price = parse_price(el.get_text())
    if price is None:
        print(f"[warn] {product['name']}: found the element but couldn't parse a price from '{el.get_text().strip()}'")
    return price


def check_products():
    products = load_products()
    prices = load_prices()
    alerts = []

    for product in products:
        key = product["url"]
        current = fetch_price(product)
        if current is None:
            continue

        prior = prices.get(key, {}).get("last_price")
        target = product.get("target_price")

        should_alert = False
        reason = ""
        if prior is not None and current < prior:
            should_alert = True
            reason = f"dropped from ${prior:.2f} to ${current:.2f}"
        elif target is not None and current <= target:
            should_alert = True
            reason = f"hit your target of ${target:.2f} (now ${current:.2f})"

        prices[key] = {
            "name": product["name"],
            "url": product["url"],
            "last_price": current,
        }

        if should_alert:
            alerts.append({"name": product["name"], "url": product["url"], "reason": reason})

    save_prices(prices)
    return alerts


def post_github_issue(alerts):
    if not (GITHUB_TOKEN and GITHUB_REPOSITORY):
        print("[info] Skipping GitHub issue (no token/repo in env).")
        return

    lines = [f"**{len(alerts)}** price change(s) worth a look:\n"]
    for a in alerts:
        lines.append(f"### {a['name']}")
        lines.append(a["reason"])
        lines.append(f"[View product]({a['url']})")
        lines.append("")

    resp = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPOSITORY}/issues",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        },
        json={"title": f"💰 {len(alerts)} price change(s)", "body": "\n".join(lines), "labels": ["price-alert"]},
        timeout=30,
    )
    if resp.status_code >= 300:
        print(f"[warn] GitHub issue creation failed: {resp.status_code} {resp.text}")
    else:
        print(f"[info] Opened issue: {resp.json().get('html_url')}")


def post_discord(alerts):
    if not DISCORD_WEBHOOK_URL:
        return

    lines = [f"**{len(alerts)} price change(s):**"]
    for a in alerts[:10]:
        lines.append(f"• **{a['name']}** — {a['reason']} — {a['url']}")

    resp = requests.post(DISCORD_WEBHOOK_URL, json={"content": "\n".join(lines)}, timeout=30)
    if resp.status_code >= 300:
        print(f"[warn] Discord post failed: {resp.status_code} {resp.text}")


def main():
    alerts = check_products()
    print(f"[info] {len(alerts)} price alert(s) this run.")
    if not alerts:
        return
    post_github_issue(alerts)
    post_discord(alerts)


if __name__ == "__main__":
    main()
