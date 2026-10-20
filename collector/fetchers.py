"""各種ソースから記事を取得して Item のリストに変換する。"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (compatible; kimetsu-info-collector/1.0; "
    "+https://github.com/yomizozzy-source/kimetsu-info-collector)"
)
TIMEOUT = 20
DEFAULT_MAX_ITEMS = 15

ATOM_NS = "{http://www.w3.org/2005/Atom}"
DATE_RE = re.compile(r"(20\d{2})[./年-]\s*(\d{1,2})[./月-]\s*(\d{1,2})")


@dataclass
class Item:
    title: str
    url: str
    source: str
    category: str
    published: str | None = None  # ISO 8601 (UTC)
    first_seen: str | None = None
    id: str = field(default="")

    def __post_init__(self) -> None:
        if not self.id:
            self.id = hashlib.sha1(self.url.encode("utf-8")).hexdigest()[:16]


def http_get(url: str) -> bytes:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.content


def _to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _parse_date(text: str | None) -> str | None:
    if not text:
        return None
    text = text.strip()
    try:
        return _to_iso(parsedate_to_datetime(text))  # RSS: RFC 822
    except (TypeError, ValueError):
        pass
    try:
        return _to_iso(datetime.fromisoformat(text.replace("Z", "+00:00")))  # Atom
    except ValueError:
        return _find_date(text)


def _find_date(text: str) -> str | None:
    """本文中の「2025.10.20」「2025年10月20日」などから日付を拾う。"""
    m = DATE_RE.search(text)
    if not m:
        return None
    y, mo, d = map(int, m.groups())
    try:
        return _to_iso(datetime(y, mo, d))
    except ValueError:
        return None


def parse_feed(xml: bytes, source: str, category: str) -> list[Item]:
    """RSS 2.0 / Atom をパースする。"""
    root = ET.fromstring(xml)
    items: list[Item] = []
    for node in root.iter("item"):
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        if title and link:
            items.append(Item(title, link, source, category, _parse_date(node.findtext("pubDate"))))
    for node in root.iter(f"{ATOM_NS}entry"):
        title = (node.findtext(f"{ATOM_NS}title") or "").strip()
        link_el = node.find(f"{ATOM_NS}link[@rel='alternate']")
        if link_el is None:
            link_el = node.find(f"{ATOM_NS}link")
        link = link_el.get("href", "").strip() if link_el is not None else ""
        date = node.findtext(f"{ATOM_NS}published") or node.findtext(f"{ATOM_NS}updated")
        if title and link:
            items.append(Item(title, link, source, category, _parse_date(date)))
    return items


def parse_html_links(html: bytes, base_url: str, link_pattern: str, source: str, category: str) -> list[Item]:
    """ページ内から link_pattern を含むリンクを記事として抜き出す。"""
    soup = BeautifulSoup(html, "html.parser")
    base_path = urlparse(base_url).path.rstrip("/")
    pattern = re.compile(link_pattern)
    items: list[Item] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        url = urljoin(base_url, a["href"]).split("#")[0]
        path = urlparse(url).path.rstrip("/")
        # 一覧ページ自身やページ送りは除外
        if not pattern.search(url) or path == base_path or re.search(r"/page/\d+$", path):
            continue
        if url in seen:
            continue
        text = " ".join(a.get_text(" ", strip=True).split())
        if len(text) < 4:
            continue
        # 日付はリンク内テキスト、なければ親要素のテキストから探す
        date = _find_date(text)
        if date is None and a.parent is not None:
            date = _find_date(a.parent.get_text(" ", strip=True))
        title = DATE_RE.sub("", text).strip(" .-|/") or text
        seen.add(url)
        items.append(Item(title, url, source, category, date))
    return items


def google_news_url(query: str) -> str:
    return f"https://news.google.com/rss/search?q={quote(query)}&hl=ja&gl=JP&ceid=JP:ja"


def fetch_source(src: dict) -> list[Item]:
    name, category, kind = src["name"], src["category"], src["type"]
    if kind == "google_news":
        items = parse_feed(http_get(google_news_url(src["query"])), name, category)
    elif kind == "rss":
        items = parse_feed(http_get(src["url"]), name, category)
    elif kind == "html_links":
        items = parse_html_links(http_get(src["url"]), src["url"], src["link_pattern"], name, category)
    else:
        raise ValueError(f"unknown source type: {kind}")

    keywords = src.get("keywords")
    if keywords:
        items = [it for it in items if any(k in it.title for k in keywords)]
    return items[: src.get("max_items", DEFAULT_MAX_ITEMS)]
