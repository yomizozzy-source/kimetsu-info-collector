import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from collector import fetchers, main
from collector.fetchers import Item, parse_feed, parse_html_links
from collector.notify import build_message
from collector.render import render

FIX = Path(__file__).parent / "fixtures"


class ParseTest(unittest.TestCase):
    def test_rss(self):
        items = parse_feed((FIX / "google_news.xml").read_bytes(), "GN", "news")
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0].url, "https://news.example.com/a1")
        self.assertEqual(items[0].published, "2026-10-19T23:00:00+00:00")

    def test_atom(self):
        items = parse_feed((FIX / "youtube.xml").read_bytes(), "YT", "video")
        self.assertEqual([i.url for i in items],
                         ["https://www.youtube.com/watch?v=abc", "https://www.youtube.com/watch?v=def"])
        self.assertEqual(items[0].published, "2026-10-19T10:00:00+00:00")

    def test_html_links(self):
        url = "https://kimetsu.com/anime/news/"
        items = parse_html_links((FIX / "official_news.html").read_bytes(), url, "/anime/news/", "公式", "official")
        self.assertEqual([i.url for i in items],
                         ["https://kimetsu.com/anime/news/1234/", "https://kimetsu.com/anime/news/1233/"])
        self.assertEqual(items[0].title, "劇場版 来場者特典 第5弾 決定！")
        self.assertTrue(items[0].published.startswith("2026-10-19"))
        self.assertEqual(items[1].title, "コラボカフェ開催のお知らせ")

    def test_keywords_and_max_items(self):
        with mock.patch.object(fetchers, "http_get", return_value=(FIX / "youtube.xml").read_bytes()):
            items = fetchers.fetch_source({"name": "YT", "type": "rss", "category": "video",
                                           "url": "https://x", "keywords": ["鬼滅"]})
            self.assertEqual(len(items), 1)
            items = fetchers.fetch_source({"name": "YT", "type": "rss", "category": "video",
                                           "url": "https://x", "max_items": 1})
            self.assertEqual(len(items), 1)


class StateTest(unittest.TestCase):
    def test_dedupe_similar_titles(self):
        items = parse_feed((FIX / "google_news.xml").read_bytes(), "GN", "news")
        self.assertEqual(len(main.dedupe(items)), 2)

    def test_dedupe_prefers_specific_category(self):
        news = Item("鬼滅の刃 新作ガチャ登場", "https://e/1", "GN", "news")
        gacha = Item("鬼滅の刃 新作ガチャ登場", "https://e/1", "GNガチャ", "gacha")
        self.assertEqual([i.category for i in main.dedupe([news, gacha])], ["gacha"])

    def test_merge_marks_only_unseen_and_expires_old(self):
        now = datetime(2026, 10, 20, 22, 0, tzinfo=timezone.utc)
        old = Item("昔の記事", "https://e/old", "s", "news",
                   first_seen=(now - timedelta(days=40)).isoformat())
        known = Item("既知の記事", "https://e/known", "s", "news",
                     first_seen=(now - timedelta(days=1)).isoformat())
        state = {old.id: old.__dict__.copy(), known.id: known.__dict__.copy()}
        fetched = [Item("既知の記事", "https://e/known", "s", "news"),
                   Item("新しい記事", "https://e/new", "s", "goods")]
        all_items, new_items = main.merge_state(state, fetched, now)
        self.assertEqual([i.title for i in new_items], ["新しい記事"])
        self.assertNotIn(old.id, state)
        self.assertEqual(all_items[0].title, "新しい記事")


class EndToEndTest(unittest.TestCase):
    def test_run_twice(self):
        feeds = {
            "news.google.com": (FIX / "google_news.xml").read_bytes(),
            "kimetsu.com": (FIX / "official_news.html").read_bytes(),
        }

        def fake_get(url):
            for host, body in feeds.items():
                if host in url:
                    return body
            raise OSError("network down")

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            cfg = d / "sources.yaml"
            cfg.write_text(
                "sources:\n"
                "  - {name: GN, type: google_news, category: news, query: 鬼滅の刃}\n"
                "  - {name: 公式, type: html_links, category: official, url: 'https://kimetsu.com/anime/news/', link_pattern: /anime/news/}\n"
                "  - {name: 壊れたソース, type: rss, category: video, url: 'https://broken.example/feed'}\n"
                "x_links:\n  - {label: 公式X, url: 'https://x.com/kimetsu_off'}\n",
                encoding="utf-8")
            args = ["--config", str(cfg), "--state", str(d / "items.json"), "--out", str(d / "index.html")]
            with mock.patch.object(fetchers, "http_get", side_effect=fake_get), \
                 mock.patch.object(main, "notify") as notify:
                main.main(args)
                notify.assert_not_called()  # 初回は通知しない
                main.main(args)
                notify.assert_called_once()
                self.assertEqual(notify.call_args.args[0], [])  # 2回目は新着なし
                self.assertEqual(notify.call_args.args[1], ["壊れたソース: OSError"])

            state = json.loads((d / "items.json").read_text(encoding="utf-8"))
            self.assertEqual(len(state), 4)
            html = (d / "index.html").read_text(encoding="utf-8")
            self.assertIn("劇場版 来場者特典 第5弾 決定！", html)
            self.assertIn("https://x.com/kimetsu_off", html)
            self.assertIn("壊れたソース", html)


class RenderTest(unittest.TestCase):
    def test_escapes_and_blocks_js_urls(self):
        it = Item("<script>alert(1)</script>", "javascript:alert(1)", "s", "news")
        html = render([it], {it.id}, [], datetime.now(timezone.utc), [])
        self.assertNotIn("<script>alert", html)
        self.assertNotIn('href="javascript:', html)

    def test_x_links_go_to_their_tab(self):
        links = [{"label": "ガチャ検索", "url": "https://x.com/search?q=a", "category": "gacha"},
                 {"label": "公式X", "url": "https://x.com/kimetsu_off"}]
        html = render([], set(), links, datetime.now(timezone.utc), [])
        self.assertIn('data-cat="gacha" data-new="0"><a href="https://x.com/search?q=a"', html)
        self.assertIn('data-cat="x" data-new="0"><a href="https://x.com/kimetsu_off"', html)
        self.assertIn('data-filter="gacha">ガチャ 1<', html)
        self.assertIn('data-filter="x">X 1<', html)

    def test_message(self):
        items = [Item(f"記事{i}", f"https://e/{i}", "s", "goods") for i in range(25)]
        msg = build_message(items, [], "https://example.github.io/")
        self.assertIn("新着 25 件", msg)
        self.assertIn("[グッズ] 記事0", msg)
        self.assertIn("ほか 5 件", msg)


if __name__ == "__main__":
    unittest.main()
