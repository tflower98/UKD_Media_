#!/usr/bin/env python3
"""
Nightly updater for the UK defence media map.

For each journalist in data/journalists.json:
  1. Queries Google News RSS for recent articles under their byline.
  2. Stores the latest articles (title, source, link, date) on the record.
  3. Compares article sources against the journalist's declared outlet_domains.
     If the two most recent articles both come from a non-home domain, adds a
     possible-move flag for human review. It never rewrites the outlet itself.

Run locally:  python update_articles.py
Run in CI:    see .github/workflows/nightly.yml

Stdlib only. No API keys.
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "journalists.json"
MAX_ARTICLES = 5
LOOKBACK = "30d"
MOVE_FLAG_THRESHOLD = 2  # consecutive off-domain articles before flagging
REQUEST_DELAY_SECONDS = 2  # be polite to Google News

# Aggregator/syndication domains that should never trigger a move flag.
SYNDICATION_DOMAINS = {
    "news.google.com", "yahoo.com", "uk.yahoo.com", "ca.yahoo.com",
    "msn.com", "aol.com", "aol.co.uk", "inkl.com", "headtopics.com",
}


def gnews_url(query: str) -> str:
    q = urllib.parse.quote(f"{query} when:{LOOKBACK}")
    return (
        f"https://news.google.com/rss/search?q={q}"
        f"&hl=en-GB&gl=GB&ceid=GB:en"
    )


def default_query(journalist: dict) -> str:
    # Quoted byline plus a defence anchor keeps out namesakes reasonably well.
    name = journalist["name"]
    return f'"{name}" defence OR defense OR military'


def fetch_feed(url: str) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    root = ET.fromstring(raw)
    items = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        source_el = item.find("source")
        source_name = source_el.text.strip() if source_el is not None and source_el.text else ""
        source_url = source_el.get("url", "") if source_el is not None else ""
        items.append({
            "title": title,
            "link": link,
            "published": pub,
            "source_name": source_name,
            "source_domain": domain_of(source_url or link),
        })
    return items


def domain_of(url: str) -> str:
    m = re.match(r"https?://(?:www\.)?([^/]+)", url or "")
    return m.group(1).lower() if m else ""


def is_home(domain: str, home_domains: list[str]) -> bool:
    return any(domain == h or domain.endswith("." + h) for h in home_domains)


def check_for_move(journalist: dict, articles: list[dict]) -> dict | None:
    """Flag if the newest N articles are all from one non-home, non-syndication domain."""
    home = [d.lower() for d in journalist.get("outlet_domains", [])]
    if not home:
        return None  # vacant slots and pseudonymous outlets: nothing to compare

    considered = [
        a for a in articles
        if a["source_domain"] and a["source_domain"] not in SYNDICATION_DOMAINS
    ][:MOVE_FLAG_THRESHOLD]

    if len(considered) < MOVE_FLAG_THRESHOLD:
        return None
    if any(is_home(a["source_domain"], home) for a in considered):
        return None

    foreign = {a["source_domain"] for a in considered}
    if len(foreign) == 1:
        dom = foreign.pop()
        return {
            "type": "possible-move",
            "detail": (
                f"Last {MOVE_FLAG_THRESHOLD} bylines all from {dom}, "
                f"expected one of {home}. Review manually; could be a guest "
                f"column, freelance piece, or a genuine move."
            ),
            "raised": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        }
    return None


def main() -> int:
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    updated = 0

    for j in data["journalists"]:
        if j.get("status") == "vacant-slot" or j.get("name") == "TBC":
            continue

        query = j.get("gnews_query") or default_query(j)
        try:
            articles = fetch_feed(gnews_url(query))[:MAX_ARTICLES]
        except Exception as exc:  # noqa: BLE001 - log and carry on
            print(f"[warn] {j['id']}: fetch failed: {exc}", file=sys.stderr)
            time.sleep(REQUEST_DELAY_SECONDS)
            continue

        j["articles"] = articles

        # Only keep unresolved flags a human hasn't cleared, plus any new one.
        existing = [f for f in j.get("flags", []) if f.get("type") != "possible-move"]
        move = check_for_move(j, articles)
        if move:
            existing.append(move)
            print(f"[flag] {j['id']}: {move['detail']}")
        j["flags"] = existing

        updated += 1
        time.sleep(REQUEST_DELAY_SECONDS)

    data["meta"]["last_script_run"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    DATA_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Updated {updated} journalist records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
