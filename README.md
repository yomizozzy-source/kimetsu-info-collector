# kimetsu-info-collector

アニメ「鬼滅の刃」の公式ニュース、グッズ、ガチャ、イベント、動画、X の情報を毎朝自動で集めて、
スマホで見やすい1ページにまとめるツールです。

- **毎朝 7 時（JST）ごろ**に GitHub Actions が自動で収集し、GitHub Pages のページを更新します
- 前日から増えた記事には **NEW** が付き、「新着(24h)」タブでまとめて確認できます
- 必要なら **Discord / Slack に新着を通知**できます
- 同じ話題を扱う別メディアの記事はタイトルで重複判定して1件にまとめます
- 一部のサイトが取得に失敗しても、ほかのソースは通常どおり収集します（失敗したソースはページ上部に表示されます）

## 収集しているソース

| タブ | 内容 |
|---|---|
| 公式 | アニメ公式サイト NEWS、公式発表（解禁・決定）を報じるニュース |
| ニュース | Google ニュース「鬼滅の刃」「無限城編」 |
| グッズ | Google ニュース（グッズ／予約／発売／フィギュア／一番くじ／コラボ） |
| ガチャ | カプセルトイのみ。Google ニュース（ガチャガチャ／ガシャポン／カプセルトイ。ゲームのガチャ記事は除外）＋ X のガチャガチャ関連ポストへのリンク |
| イベント | Google ニュース（イベント／展／舞台挨拶／上映／入場者特典） |
| 動画 | YouTube チャンネルの RSS（`sources.yaml` でチャンネル ID を設定すると有効） |
| X | 公式アカウント・最新ポスト検索へのリンク（下記参照） |

対象は [`sources.yaml`](sources.yaml) を編集すれば自由に追加・削除できます。

### X（旧 Twitter）について

X の API は有料のため、既定では公式アカウントと「最新」検索へのリンクを並べています。
ガチャ情報は「ガチャ」タブの先頭に、X のガチャガチャ（カプセルトイ）の最新ポスト・話題のポスト（いいね100以上）・
バンダイ ガシャポン公式の鬼滅ポストへのリンクを置いています。
リンクは `sources.yaml` の `x_links` に `category` を付けると好きなタブに表示できます。
RSSHub などで X の RSS を用意できる場合は、`sources.yaml` の例のとおり `type: rss`、
`category: x` で追加すると記事として取り込めます。

## セットアップ（初回のみ）

1. **GitHub Pages を有効にする**
   リポジトリの Settings → Pages → Build and deployment → Source を **GitHub Actions** にします。
2. **（任意）通知を設定する**
   Settings → Secrets and variables → Actions → New repository secret で以下を登録します。
   - `DISCORD_WEBHOOK_URL`: Discord のチャンネル設定 → 連携サービス → ウェブフック で作成した URL
   - `SLACK_WEBHOOK_URL`: Slack の Incoming Webhook URL
3. **動作確認**
   Actions タブ → 「鬼滅の刃 朝チェック」→ Run workflow で手動実行します。
   完了すると `https://<ユーザー名>.github.io/kimetsu-info-collector/` でページが見られます。

> 定期実行はデフォルトブランチ（main）にあるワークフローだけが動きます。
> 初回実行は既存記事がすべて「新着」になるため、通知は送らずページだけ作ります。

ページをスマホのホーム画面に追加しておくと、毎朝ワンタップで確認できます。

## ローカルで動かす

```bash
pip install -r requirements.txt
python -m collector --no-notify   # public/index.html が生成されます
python -m unittest discover -s tests
```

## 構成

```
collector/
  fetchers.py  # RSS / Atom / HTML ページから記事を取得
  main.py      # 収集 → 重複除去 → 既読管理 → 出力
  render.py    # スマホ向け HTML の生成
  notify.py    # Discord / Slack 通知
data/items.json  # 過去30日分の取得済み記事（NEW 判定用。Actions が自動コミット）
sources.yaml     # 収集元の設定
.github/workflows/daily.yml  # 毎朝の自動実行
```
