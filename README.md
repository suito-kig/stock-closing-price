# 株価指数 自動投稿ボット (GitHub Actions版)

日経平均株価・TOPIX・NYダウ・NASDAQ総合指数の終値を、毎日決まった時刻に
GitHub Actionsから**Discord Webhook**へ自動投稿する仕組みです。

常駐プロセスやサーバーは不要で、GitHub Actionsの`schedule`(cron)機能で
1日1回スクリプトが実行され、投稿が終わったらそのまま終了します。

---

## 1. Discordで Webhook を作成する

Bot作成は不要です。投稿したいテキストチャンネルの設定からWebhookを作るだけです。

1. Discordで投稿したいチャンネルを開く
2. チャンネル名の右側の歯車アイコン(チャンネルの編集)→「連携サービス」→「ウェブフック」
3. 「新しいウェブフック」を作成(名前・アイコンは任意)
4. 「ウェブフックURLをコピー」でURLを取得
   - このURLは**トークン同様に秘密情報**です。GitHubのコードに直接書かないでください。

## 2. GitHubリポジトリを準備する

1. このフォルダの中身(`post_indices.py`, `requirements.txt`, `.github/workflows/post-indices.yml`)を
   GitHubリポジトリにアップロード(新規リポジトリを作ってpushでOK)
2. リポジトリの「Settings」→「Secrets and variables」→「Actions」を開く
3. 「New repository secret」で以下を登録
   - Name: `DISCORD_WEBHOOK_URL`
   - Secret: 手順1でコピーしたWebhook URL

## 3. 投稿時刻を設定する

`.github/workflows/post-indices.yml` 内のcron設定で投稿時刻を指定します。
**GitHub Actionsのcronは必ずUTC(世界標準時)**で書く必要があるので、日本時間から-9時間して指定してください。

```yaml
on:
  schedule:
    - cron: "0 23 * * *"   # UTC 23:00 = JST 8:00(翌日)
```

投稿タイミングの目安:
- NYダウ・NASDAQ: 米国市場の終値は日本時間の早朝(サマータイム中は6:00頃、非サマータイム中は7:00頃)に確定
- 日経平均・TOPIX: 日本市場の終値は15:00 JSTに確定

デフォルト設定(8:00 JST)だと「前日のNYダウ/NASDAQ」+「前営業日の日経平均/TOPIX」が揃った状態で投稿されます。
日本市場の当日終値も含めたい場合は市場が閉まった後(例: 16:00 JST → cronは `0 7 * * *`)に変更してください。
その場合NYダウ/NASDAQは前日分のままになります。

> **注意:** GitHub Actionsの`schedule`は指定時刻ちょうどに実行される保証はなく、
> 混雑状況によって数分〜数十分遅れることがあります。正確な時刻厳守が必要な用途には向きません。

## 4. 動作確認

設定後、GitHubリポジトリの「Actions」タブ →「Post Daily Indices to Discord」→
「Run workflow」から手動実行できます(`workflow_dispatch`を有効にしてあります)。
成功すればすぐにDiscordチャンネルに投稿されるので、Secretの設定ミスなどをその場で確認できます。

## 5. 注意点

- **プライベートリポジトリの場合**、GitHub Actionsの無料枠(月2,000分など)を消費します。
  1日1回・数十秒の実行なので通常は問題になりません。パブリックリポジトリなら無料枠は無制限です。
- リポジトリに**90日間コミットがない**と、GitHubが自動的にscheduled workflowを無効化します。
  その場合はActionsタブから再度有効化してください。
- Yahoo Financeは無料データのため、まれに取得エラーや数分程度の遅延が発生する場合があります。
  取得に失敗した指数はメッセージ内に「データ取得に失敗しました」と表示され、他の指数は投稿されます。

## ファイル構成

| ファイル | 内容 |
|---|---|
| `post_indices.py` | 指数の終値を取得しWebhookに1回だけ投稿するスクリプト |
| `requirements.txt` | 依存パッケージ |
| `.github/workflows/post-indices.yml` | 毎日自動実行するGitHub Actionsのワークフロー定義 |

## 使用しているデータソース

Yahoo Finance の株価データを `yfinance` ライブラリ経由で取得しています。
ティッカーシンボル:
- 日経平均株価: `^N225`
- TOPIX: `^TOPX`(取得失敗時は連動ETFの `1306.T` を自動使用)
- NYダウ: `^DJI`
- NASDAQ総合指数: `^IXIC`
