"""新着を Discord / Slack に通知する（環境変数に Webhook URL があるときだけ）。"""

from __future__ import annotations

import os
import sys

import requests

from .fetchers import Item
from .render import CATEGORY_LABEL

MAX_LINES = 20


def build_message(new_items: list[Item], errors: list[str], page_url: str | None) -> str:
    lines = [f"🗡️ 鬼滅の刃 朝チェック：新着 {len(new_items)} 件"]
    for it in new_items[:MAX_LINES]:
        lines.append(f"・[{CATEGORY_LABEL.get(it.category, it.category)}] {it.title}\n  {it.url}")
    if len(new_items) > MAX_LINES:
        lines.append(f"…ほか {len(new_items) - MAX_LINES} 件")
    if errors:
        lines.append(f"⚠️ 取得失敗: {', '.join(errors)}")
    if page_url:
        lines.append(f"一覧: {page_url}")
    return "\n".join(lines)


def notify(new_items: list[Item], errors: list[str]) -> None:
    discord = os.environ.get("DISCORD_WEBHOOK_URL")
    slack = os.environ.get("SLACK_WEBHOOK_URL")
    if not (discord or slack):
        return
    if not new_items and not errors:
        return
    text = build_message(new_items, errors, os.environ.get("PAGE_URL"))
    try:
        if discord:
            # Discord は 1 メッセージ 2000 文字まで
            requests.post(discord, json={"content": text[:1990]}, timeout=20).raise_for_status()
        if slack:
            requests.post(slack, json={"text": text}, timeout=20).raise_for_status()
    except requests.RequestException as e:
        print(f"[notify] 送信失敗: {e}", file=sys.stderr)
