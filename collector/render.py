"""収集結果を1枚の静的 HTML にする（スマホで朝チェックしやすい表示）。"""

from __future__ import annotations

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from .fetchers import Item

JST = ZoneInfo("Asia/Tokyo")
CATEGORIES = [
    ("official", "公式"),
    ("news", "ニュース"),
    ("goods", "グッズ"),
    ("event", "イベント"),
    ("video", "動画"),
    ("x", "X"),
]
CATEGORY_LABEL = dict(CATEGORIES)


def _safe_url(url: str) -> str:
    return escape(url) if url.startswith(("http://", "https://")) else "#"


def _fmt(iso: str | None) -> str:
    if not iso:
        return ""
    return datetime.fromisoformat(iso).astimezone(JST).strftime("%m/%d %H:%M")


def _item_html(it: Item, is_new: bool) -> str:
    badge = '<span class="new">NEW</span>' if is_new else ""
    date = _fmt(it.published or it.first_seen)
    return (
        f'<li class="item" data-cat="{escape(it.category)}" data-new="{int(is_new)}">'
        f'<a href="{_safe_url(it.url)}" target="_blank" rel="noopener noreferrer">{badge}{escape(it.title)}</a>'
        f'<div class="meta"><span class="cat">{escape(CATEGORY_LABEL.get(it.category, it.category))}</span>'
        f"{escape(it.source)}<span class=\"date\">{date}</span></div></li>"
    )


def render(items: list[Item], new_ids: set[str], x_links: list[dict], now: datetime, errors: list[str]) -> str:
    counts = {key: sum(1 for i in items if i.category == key) for key, _ in CATEGORIES}
    tabs = [f'<button class="tab active" data-filter="new">新着(24h) {len(new_ids)}</button>',
            f'<button class="tab" data-filter="all">すべて {len(items)}</button>']
    for key, label in CATEGORIES:
        n = counts[key] + (len(x_links) if key == "x" else 0)
        tabs.append(f'<button class="tab" data-filter="{key}">{label} {n}</button>')

    x_html = "".join(
        f'<li class="item" data-cat="x" data-new="0"><a href="{_safe_url(l["url"])}" target="_blank" '
        f'rel="noopener noreferrer">𝕏 {escape(l["label"])}</a><div class="meta"><span class="cat">X</span>リンク</div></li>'
        for l in x_links
    )
    items_html = "".join(_item_html(it, it.id in new_ids) for it in items)
    err_html = (
        f'<p class="errors">取得に失敗したソース: {escape(", ".join(errors))}</p>' if errors else ""
    )
    updated = now.astimezone(JST).strftime("%Y/%m/%d %H:%M")

    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>鬼滅の刃 朝チェック</title>
<style>
:root {{ --bg:#faf7f2; --fg:#1d1d1f; --sub:#6b6b70; --card:#fff; --line:#e7e2da; --accent:#c8102e; --green:#1f7a5a; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#121214; --fg:#ececf0; --sub:#9a9aa2; --card:#1c1c20; --line:#2c2c32; --accent:#ff5a6e; --green:#4cc39a; }}
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg);
  font-family:-apple-system,BlinkMacSystemFont,"Hiragino Sans","Noto Sans JP",sans-serif; }}
header {{ padding:20px 16px 8px; max-width:760px; margin:0 auto; }}
h1 {{ font-size:1.3rem; margin:0; }}
h1 small {{ display:block; font-size:.8rem; color:var(--sub); font-weight:normal; margin-top:4px; }}
nav {{ position:sticky; top:0; background:var(--bg); padding:8px 16px; display:flex; gap:6px;
  overflow-x:auto; max-width:760px; margin:0 auto; border-bottom:1px solid var(--line); }}
.tab {{ flex:none; border:1px solid var(--line); background:var(--card); color:var(--fg);
  border-radius:999px; padding:6px 12px; font-size:.85rem; cursor:pointer; }}
.tab.active {{ background:var(--accent); border-color:var(--accent); color:#fff; }}
main {{ max-width:760px; margin:0 auto; padding:8px 16px 40px; }}
ul {{ list-style:none; padding:0; margin:0; }}
.item {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px; margin:8px 0; }}
.item a {{ color:var(--fg); text-decoration:none; font-weight:600; line-height:1.45; }}
.item a:hover {{ text-decoration:underline; }}
.meta {{ color:var(--sub); font-size:.75rem; margin-top:6px; display:flex; gap:8px; flex-wrap:wrap; }}
.cat {{ color:var(--green); font-weight:600; }}
.date {{ margin-left:auto; }}
.new {{ background:var(--accent); color:#fff; font-size:.65rem; border-radius:4px; padding:1px 5px;
  margin-right:6px; vertical-align:2px; }}
.empty {{ color:var(--sub); text-align:center; padding:32px 0; }}
.errors {{ color:var(--sub); font-size:.75rem; }}
</style>
</head>
<body>
<header><h1>鬼滅の刃 朝チェック<small>最終更新 {updated}（毎朝7時ごろ自動更新）</small></h1></header>
<nav>{"".join(tabs)}</nav>
<main>
{err_html}
<ul id="list">{items_html}{x_html}</ul>
<p class="empty" id="empty" hidden>この分類の記事はまだありません</p>
</main>
<script>
const tabs = document.querySelectorAll('.tab');
const items = document.querySelectorAll('.item');
function apply(f) {{
  let shown = 0;
  items.forEach(el => {{
    const ok = f === 'all' || (f === 'new' ? el.dataset.new === '1' : el.dataset.cat === f);
    el.hidden = !ok; if (ok) shown++;
  }});
  document.getElementById('empty').hidden = shown > 0;
  tabs.forEach(t => t.classList.toggle('active', t.dataset.filter === f));
}}
tabs.forEach(t => t.addEventListener('click', () => apply(t.dataset.filter)));
apply('new');
</script>
</body>
</html>
"""
