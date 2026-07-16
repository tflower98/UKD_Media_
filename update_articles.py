#!/usr/bin/env python3
"""
Nightly updater for UK Defence Media Map.

Fetches articles from NewsAPI and generates index.html.
This script is the ONLY thing that should ever write index.html.
Never hand-edit index.html directly — it will be overwritten on the
next run, and a hand-edited copy is likely to be broken anyway (it
needs real JSON substituted into it, not a static template).
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "journalists.json"
INDEX_FILE = Path(__file__).parent / "index.html"
MAX_ARTICLES = 5
MOVE_FLAG_THRESHOLD = 2
REQUEST_DELAY_SECONDS = 1

NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "")

SYNDICATION_DOMAINS = {
    "news.google.com", "yahoo.com", "uk.yahoo.com", "ca.yahoo.com",
    "msn.com", "aol.com", "aol.co.uk", "inkl.com", "headtopics.com",
}


def newsapi_url(query: str, page: int = 1) -> str:
    params = {
        "q": query,
        "sortBy": "publishedAt",
        "language": "en",
        "pageSize": MAX_ARTICLES,
        "page": page,
        "apiKey": NEWSAPI_KEY,
    }
    return "https://newsapi.org/v2/everything?" + urllib.parse.urlencode(params)


def default_query(journalist: dict) -> str:
    name = journalist["name"]
    return f'"{name}" (defence OR defense OR military)'


def fetch_articles(url: str) -> list:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if data.get("status") != "ok":
            print(f"[warn] NewsAPI error: {data.get('message', 'unknown')}", file=sys.stderr)
            return []

        articles = []
        for article in data.get("articles", []):
            articles.append({
                "title": (article.get("title") or "").strip(),
                "link": (article.get("url") or "").strip(),
                "published": (article.get("publishedAt") or "").strip(),
                "source_name": (article.get("source") or {}).get("name", "Unknown"),
                "source_domain": domain_of(article.get("url", "")),
            })
        return articles
    except Exception as exc:
        print(f"[error] Failed to fetch from NewsAPI: {exc}", file=sys.stderr)
        return []


def domain_of(url: str) -> str:
    m = re.match(r"https?://(?:www\.)?([^/]+)", url or "")
    return m.group(1).lower() if m else ""


def is_home(domain: str, home_domains: list) -> bool:
    return any(domain == h or domain.endswith("." + h) for h in home_domains)


def check_for_move(journalist: dict, articles: list):
    home = [d.lower() for d in journalist.get("outlet_domains", [])]
    if not home:
        return None

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
            "detail": f"Last {MOVE_FLAG_THRESHOLD} bylines all from {dom}, expected one of {home}. Review manually.",
            "raised": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        }
    return None


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>UK Defence Media Map</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f5f5; color: #333; line-height: 1.6; }
.header { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: white; padding: 2rem; text-align: center; border-bottom: 3px solid #0f3460; }
.header h1 { font-size: 2rem; margin-bottom: 0.5rem; }
.header p { font-size: 0.95rem; opacity: 0.9; }
.container { max-width: 1400px; margin: 0 auto; padding: 2rem 1rem; }
.controls { display: flex; gap: 1rem; margin-bottom: 2rem; flex-wrap: wrap; align-items: center; }
.search-box { flex: 1; min-width: 250px; }
.search-box input { width: 100%; padding: 0.75rem 1rem; border: 1px solid #ddd; border-radius: 6px; font-size: 1rem; }
.search-box input:focus { outline: none; border-color: #0f3460; box-shadow: 0 0 0 3px rgba(15,52,96,0.1); }
.beat-filters { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.beat-btn { padding: 0.5rem 1rem; border: 2px solid #ddd; background: white; border-radius: 20px; cursor: pointer; font-size: 0.9rem; transition: all 0.2s; }
.beat-btn:hover { border-color: #0f3460; color: #0f3460; }
.beat-btn.active { background: #0f3460; color: white; border-color: #0f3460; }
.outlet-section { margin-bottom: 2.5rem; }
.outlet-heading { font-size: 1.3rem; font-weight: 600; color: #1a1a2e; margin-bottom: 1rem; padding-bottom: 0.5rem; border-bottom: 2px solid #0f3460; }
.journalists-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1.5rem; }
.journalist-card { background: white; border-radius: 8px; padding: 1.5rem; cursor: pointer; border: 1px solid #e0e0e0; transition: all 0.2s; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
.journalist-card:hover { box-shadow: 0 6px 12px rgba(0,0,0,0.1); transform: translateY(-2px); border-color: #0f3460; }
.card-header { display: flex; justify-content: space-between; align-items: start; margin-bottom: 0.75rem; }
.journalist-name { font-size: 1.1rem; font-weight: 600; color: #1a1a2e; }
.priority-badge { display: inline-block; padding: 0.25rem 0.6rem; border-radius: 3px; font-size: 0.8rem; font-weight: 600; }
.priority-1 { background: #e8f4f8; color: #0f3460; }
.priority-2 { background: #f0f4f8; color: #333; }
.priority-3 { background: #f5f5f5; color: #666; }
.journalist-role { font-size: 0.9rem; color: #666; margin-bottom: 0.5rem; }
.beats { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.75rem; }
.beat-tag { display: inline-block; background: #f0f4f8; color: #0f3460; padding: 0.3rem 0.6rem; border-radius: 3px; font-size: 0.8rem; }
.article-count { font-size: 0.85rem; color: #666; }
.flag-indicator { display: inline-block; background: #fff3cd; color: #856404; padding: 0.3rem 0.6rem; border-radius: 3px; font-size: 0.8rem; font-weight: 600; margin-top: 0.5rem; }
.modal { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 1000; overflow-y: auto; padding: 2rem 1rem; }
.modal.show { display: flex; align-items: center; justify-content: center; }
.modal-content { background: white; border-radius: 12px; max-width: 700px; width: 100%; max-height: 85vh; overflow-y: auto; padding: 2rem; position: relative; }
.modal-close { position: absolute; top: 1rem; right: 1rem; background: none; border: none; font-size: 1.5rem; cursor: pointer; color: #666; }
.modal-close:hover { color: #000; }
.modal-header { margin-bottom: 1.5rem; padding-right: 2rem; }
.modal-name { font-size: 1.5rem; font-weight: 700; color: #1a1a2e; margin-bottom: 0.5rem; }
.modal-role { color: #666; font-size: 1rem; margin-bottom: 0.5rem; }
.modal-outlet { font-size: 0.95rem; color: #0f3460; font-weight: 600; }
.modal-section { margin-bottom: 1.5rem; }
.modal-section h3 { font-size: 1rem; font-weight: 600; color: #1a1a2e; margin-bottom: 0.75rem; border-bottom: 1px solid #e0e0e0; padding-bottom: 0.5rem; }
.beats-list { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.beat-tag-modal { background: #f0f4f8; color: #0f3460; padding: 0.4rem 0.8rem; border-radius: 4px; font-size: 0.9rem; }
.meta-info { display: flex; gap: 1rem; flex-wrap: wrap; font-size: 0.9rem; }
.meta-item { display: flex; align-items: center; gap: 0.5rem; }
.confidence-tag { background: #f0f4f8; color: #0f3460; padding: 0.3rem 0.6rem; border-radius: 3px; font-size: 0.85rem; }
.articles-section { margin-bottom: 1.5rem; }
.articles-list { list-style: none; }
.article-item { margin-bottom: 0.75rem; padding-bottom: 0.75rem; border-bottom: 1px solid #f0f0f0; }
.article-item:last-child { border-bottom: none; }
.article-title { font-weight: 600; color: #0f3460; margin-bottom: 0.3rem; }
.article-title a { text-decoration: none; color: #0f3460; }
.article-title a:hover { text-decoration: underline; }
.article-source { font-size: 0.85rem; color: #666; margin-bottom: 0.2rem; }
.article-date { font-size: 0.8rem; color: #999; }
.no-articles { color: #999; font-style: italic; font-size: 0.9rem; }
.notes { background: #f9f9f9; padding: 1rem; border-radius: 6px; border-left: 3px solid #0f3460; font-size: 0.95rem; line-height: 1.5; }
.contact-info { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.contact-btn { display: inline-block; padding: 0.5rem 0.8rem; background: #0f3460; color: white; text-decoration: none; border-radius: 4px; font-size: 0.9rem; transition: background 0.2s; }
.contact-btn:hover { background: #1a1a2e; }
.flag-section { background: #fff3cd; padding: 1rem; border-radius: 6px; border-left: 3px solid #ffc107; margin-top: 1rem; }
.flag-section h4 { color: #856404; margin-bottom: 0.5rem; font-size: 0.95rem; }
.flag-detail { color: #856404; font-size: 0.9rem; }
.no-results { text-align: center; padding: 3rem 1rem; color: #999; }
@media (max-width: 768px) {
  .journalists-grid { grid-template-columns: 1fr; }
  .header h1 { font-size: 1.5rem; }
  .controls { flex-direction: column; align-items: stretch; }
  .modal-content { max-height: 95vh; padding: 1.5rem; }
}
</style>
</head>
<body>
<div class="header">
  <h1>UK Defence Media Map</h1>
  <p>Curated journalists covering UK defence. Articles updated nightly.</p>
</div>
<div class="container">
  <div class="controls">
    <div class="search-box"><input type="text" id="searchInput" placeholder="Search journalist or outlet..."></div>
    <div class="beat-filters" id="beatFilters"></div>
  </div>
  <div id="outletSections"></div>
</div>
<div id="modal" class="modal">
  <div class="modal-content">
    <button class="modal-close" onclick="closeModal()">&times;</button>
    <div id="modalBody"></div>
  </div>
</div>
<script>
const allJournalists = __DATA_PLACEHOLDER__;
let activeBeats = new Set();
let searchTerm = '';

function initPage() { renderBeats(); renderOutlets(); setupSearch(); }

function renderBeats() {
  const beatsSet = new Set();
  allJournalists.forEach(j => {
    if (j.status !== 'vacant-slot' && j.name !== 'TBC') j.beats.forEach(b => beatsSet.add(b));
  });
  const container = document.getElementById('beatFilters');
  container.innerHTML = '';
  Array.from(beatsSet).sort().forEach(beat => {
    const btn = document.createElement('button');
    btn.className = 'beat-btn';
    btn.textContent = beat;
    btn.onclick = () => toggleBeat(beat, btn);
    container.appendChild(btn);
  });
}

function toggleBeat(beat, btn) {
  if (activeBeats.has(beat)) { activeBeats.delete(beat); btn.classList.remove('active'); }
  else { activeBeats.add(beat); btn.classList.add('active'); }
  renderOutlets();
}

function setupSearch() {
  document.getElementById('searchInput').addEventListener('input', e => {
    searchTerm = e.target.value.toLowerCase();
    renderOutlets();
  });
}

function shouldShowJournalist(j) {
  if (j.status === 'vacant-slot' || j.name === 'TBC') return false;
  const matchesSearch = !searchTerm || j.name.toLowerCase().includes(searchTerm) ||
    j.outlet.toLowerCase().includes(searchTerm) || (j.notes && j.notes.toLowerCase().includes(searchTerm));
  if (!matchesSearch) return false;
  if (activeBeats.size === 0) return true;
  return j.beats.some(b => activeBeats.has(b));
}

function renderOutlets() {
  const byOutlet = {};
  allJournalists.forEach(j => {
    if (shouldShowJournalist(j)) {
      if (!byOutlet[j.outlet]) byOutlet[j.outlet] = [];
      byOutlet[j.outlet].push(j);
    }
  });
  const sortedOutlets = Object.keys(byOutlet).sort();
  let html = '';
  if (sortedOutlets.length === 0) {
    html = '<div class="no-results"><h2>No journalists found</h2></div>';
  } else {
    sortedOutlets.forEach(outlet => {
      html += '<div class="outlet-section"><h2 class="outlet-heading">' + escapeHtml(outlet) + '</h2><div class="journalists-grid">';
      byOutlet[outlet].sort((a, b) => (a.priority - b.priority) || a.name.localeCompare(b.name)).forEach(j => { html += renderCard(j); });
      html += '</div></div>';
    });
  }
  document.getElementById('outletSections').innerHTML = html;
  document.querySelectorAll('.journalist-card').forEach(card => {
    card.addEventListener('click', e => { if (!e.target.closest('a')) openModal(card.dataset.id); });
  });
}

function renderCard(j) {
  const articles = j.articles || [];
  const flags = j.flags || [];
  let html = '<div class="journalist-card" data-id="' + j.id + '"><div class="card-header"><div><div class="journalist-name">' +
    escapeHtml(j.name) + '</div><div class="journalist-role">' + escapeHtml(j.role) + '</div></div><span class="priority-badge priority-' +
    j.priority + '">P' + j.priority + '</span></div><div class="beats">';
  j.beats.forEach(b => { html += '<span class="beat-tag">' + escapeHtml(b) + '</span>'; });
  html += '</div><div class="article-count">' + articles.length + ' article' + (articles.length !== 1 ? 's' : '') + '</div>';
  if (flags.length > 0) html += '<div class="flag-indicator">\u26a0\ufe0f Possible move</div>';
  html += '</div>';
  return html;
}

function openModal(id) {
  const j = allJournalists.find(x => x.id === id);
  if (!j) return;
  const articles = j.articles || [];

  let html = '<div class="modal-header"><div class="modal-name">' + escapeHtml(j.name) + '</div><div class="modal-role">' +
    escapeHtml(j.role) + '</div><div class="modal-outlet">' + escapeHtml(j.outlet) + '</div></div>';

  html += '<div class="modal-section"><h3>Coverage areas</h3><div class="beats-list">';
  j.beats.forEach(b => { html += '<span class="beat-tag-modal">' + escapeHtml(b) + '</span>'; });
  html += '</div></div>';

  html += '<div class="modal-section"><h3>Details</h3><div class="meta-info"><div class="meta-item"><strong>Priority:</strong> <span class="confidence-tag">' +
    j.priority + '</span></div><div class="meta-item"><strong>Confidence:</strong> <span class="confidence-tag">' + escapeHtml(j.confidence) +
    '</span></div><div class="meta-item"><strong>Verified:</strong> ' + escapeHtml(j.last_verified || 'Not yet') + '</div></div></div>';

  if (j.notes) html += '<div class="modal-section"><h3>Coverage notes</h3><div class="notes">' + escapeHtml(j.notes) + '</div></div>';

  if (articles.length > 0) {
    html += '<div class="articles-section"><h3>Recent articles (' + articles.length + ')</h3><ul class="articles-list">';
    articles.forEach(a => {
      html += '<li class="article-item"><div class="article-title"><a href="' + escapeHtml(a.link) + '" target="_blank">' +
        escapeHtml(a.title) + '</a></div><div class="article-source">' + escapeHtml(a.source_name || 'Unknown') +
        '</div><div class="article-date">' + formatDate(a.published) + '</div></li>';
    });
    html += '</ul></div>';
  } else {
    html += '<div class="articles-section"><p class="no-articles">No recent articles found.</p></div>';
  }

  if (j.flags && j.flags.length > 0) {
    html += '<div class="flag-section"><h4>\u26a0\ufe0f Job move alert</h4>';
    j.flags.forEach(f => {
      if (f.type === 'possible-move') html += '<div class="flag-detail">' + escapeHtml(f.detail) + '</div>';
    });
    html += '</div>';
  }

  if (j.x_handle) {
    html += '<div class="modal-section"><h3>Contact</h3><div class="contact-info"><a href="https://x.com/' +
      escapeHtml(j.x_handle) + '" target="_blank" class="contact-btn">@' + escapeHtml(j.x_handle) + '</a></div></div>';
  }

  document.getElementById('modalBody').innerHTML = html;
  document.getElementById('modal').classList.add('show');
}

function closeModal() { document.getElementById('modal').classList.remove('show'); }

function formatDate(dateStr) {
  if (!dateStr) return '';
  try { return new Date(dateStr).toLocaleDateString('en-GB', { year: 'numeric', month: 'short', day: 'numeric' }); }
  catch (e) { return dateStr; }
}

function escapeHtml(text) {
  if (!text) return '';
  const map = {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'};
  return text.replace(/[&<>"']/g, m => map[m]);
}

document.getElementById('modal').addEventListener('click', e => { if (e.target.id === 'modal') closeModal(); });
window.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
initPage();
</script>
</body>
</html>
"""


def generate_html(data: dict) -> str:
    journalists_json = json.dumps(data.get("journalists", []), ensure_ascii=False)
    return HTML_TEMPLATE.replace("__DATA_PLACEHOLDER__", journalists_json)


def main() -> int:
    if not NEWSAPI_KEY:
        print("[error] NEWSAPI_KEY not set. Add it to GitHub Secrets.", file=sys.stderr)
        return 1

    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    updated = 0

    for j in data["journalists"]:
        if j.get("status") == "vacant-slot" or j.get("name") == "TBC":
            continue

        query = j.get("gnews_query") or default_query(j)
        try:
            articles = fetch_articles(newsapi_url(query))[:MAX_ARTICLES]
        except Exception as exc:
            print(f"[warn] {j['id']}: fetch failed: {exc}", file=sys.stderr)
            time.sleep(REQUEST_DELAY_SECONDS)
            continue

        j["articles"] = articles

        existing = [f for f in j.get("flags", []) if f.get("type") != "possible-move"]
        move = check_for_move(j, articles)
        if move:
            existing.append(move)
            print(f"[flag] {j['id']}: {move['detail']}")
        j["flags"] = existing

        updated += 1
        time.sleep(REQUEST_DELAY_SECONDS)

    data.setdefault("meta", {})["last_script_run"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Updated {updated} journalist records.")

    try:
        INDEX_FILE.write_text(generate_html(data), encoding="utf-8")
        print(f"Generated {INDEX_FILE.name}")
    except Exception as exc:
        print(f"[error] Failed to generate HTML: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
