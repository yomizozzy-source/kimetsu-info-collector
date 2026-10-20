"""エントリポイント: 収集 → 既読管理 → HTML 生成 → 通知。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from .fetchers import Item, fetch_source
from .notify import notify
from .render import render

ROOT = Path(__file__).resolve().parent.parent
KEEP_DAYS = 30


def normalize_title(title: str) -> str:
    # Google ニュースの「タイトル - 媒体名」の媒体名部分や記号を除いて比較する
    title = re.sub(r"\s+-\s+[^-]+$", "", title)
    return re.sub(r"[\s「」『』【】()（）!！?？・、。:：]", "", title).lower()


def dedupe(items: list[Item]) -> list[Item]:
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    out: list[Item] = []
    for it in items:
        key = normalize_title(it.title)
        if it.url in seen_urls or key in seen_titles:
            continue
        seen_urls.add(it.url)
        seen_titles.add(key)
        out.append(it)
    return out


def merge_state(state: dict[str, dict], fetched: list[Item], now: datetime) -> tuple[list[Item], list[Item]]:
    """state に新着を追加し、(保持する全件, 今回の新着) を返す。"""
    now_iso = now.isoformat(timespec="seconds")
    known_titles = {normalize_title(v["title"]) for v in state.values()}
    new_items: list[Item] = []
    for it in fetched:
        if it.id in state or normalize_title(it.title) in known_titles:
            continue
        it.first_seen = now_iso
        state[it.id] = asdict(it)
        known_titles.add(normalize_title(it.title))
        new_items.append(it)

    cutoff = (now - timedelta(days=KEEP_DAYS)).isoformat(timespec="seconds")
    for key in [k for k, v in state.items() if (v.get("first_seen") or "") < cutoff]:
        del state[key]

    all_items = [Item(**v) for v in state.values()]
    all_items.sort(key=lambda i: (i.first_seen or "", i.published or ""), reverse=True)
    return all_items, new_items


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="鬼滅の刃の最新情報を収集する")
    ap.add_argument("--config", default=ROOT / "sources.yaml", type=Path)
    ap.add_argument("--state", default=ROOT / "data" / "items.json", type=Path)
    ap.add_argument("--out", default=ROOT / "public" / "index.html", type=Path)
    ap.add_argument("--no-notify", action="store_true", help="通知を送らない")
    args = ap.parse_args(argv)

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)

    fetched: list[Item] = []
    errors: list[str] = []
    for src in config.get("sources", []):
        if src.get("enabled", True) is False:
            continue
        try:
            got = fetch_source(src)
            print(f"[ok]   {src['name']}: {len(got)} 件")
            fetched.extend(got)
        except Exception as e:  # 1つのソースの失敗で全体を止めない
            print(f"[fail] {src['name']}: {e}", file=sys.stderr)
            errors.append(f"{src['name']}: {type(e).__name__}")

    state: dict[str, dict] = {}
    if args.state.exists():
        state = json.loads(args.state.read_text(encoding="utf-8"))
    is_first_run = not state
    all_items, new_items = merge_state(state, dedupe(fetched), now)

    args.state.parent.mkdir(parents=True, exist_ok=True)
    args.state.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")

    # ページ上の NEW は「直近24時間に初めて見つけた記事」（手動で再実行しても消えない）
    recent = (now - timedelta(hours=24)).isoformat(timespec="seconds")
    recent_ids = {i.id for i in all_items if (i.first_seen or "") >= recent}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        render(all_items, recent_ids, config.get("x_links", []), now, errors),
        encoding="utf-8",
    )
    print(f"新着 {len(new_items)} 件 / 保持 {len(all_items)} 件 → {args.out}")

    # 初回は過去記事が全部「新着」になるので通知しない
    if not args.no_notify and not is_first_run:
        notify(new_items, errors)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
