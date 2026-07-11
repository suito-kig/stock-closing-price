# 株価指数 自動投稿ボット (GitHub Actions版)

日経平均株価・TOPIX・NYダウ・NASDAQ総合指数の終値を、GitHub Actionsから
**Discord Webhook**へ自動投稿する仕組みです。常駐プロセスやサーバーは不要です。

日本市場と米国市場は終値が確定するタイミングが大きく異なるため、
**投稿を2本のワークフローに分けています。**

| ワークフロー | 投稿内容 | 投稿時刻(JST) | 実行曜日 |
|---|---|---|---|
| `post-jp-indices.yml` | 日経平均株価 | 15:35 | 月〜金(JST) |
| `post-us-indices.yml` | NYダウ・NASDAQ総合指数 | 6:05 | 火〜土(JST。米国市場が月〜金にクローズした翌朝に投稿されるため) |

どちらも同じ `post_indices.py` を `--group jp` / `--group us` で呼び分けているだけなので、
リポジトリを分ける必要はありません。1つのリポジトリの中に2つのワークフローがある状態で問題ありません。

---

## 1. Discordで Webhook を作成する

Bot作成は不要です。投稿したいテキストチャンネルの設定からWebhookを作るだけです。

1. Discordで投稿したいチャンネルを開く
2. チャンネル名の右側の歯車アイコン(チャンネルの編集)→「連携サービス」→「ウェブフック」
3. 「新しいウェブフック」を作成(名前・アイコンは任意)
4. 「ウェブフックURLをコピー」でURLを取得
   - このURLは**トークン同様に秘密情報**です。GitHubのコードに直接書かないでください。
   - 日本市場用・米国市場用でWebhookを分ける必要はありません。同じURLを両方のワークフローで使えます。

## 2. GitHubリポジトリを準備する

1. このフォルダの中身(`post_indices.py`, `requirements.txt`, `.github/workflows/*.yml`)を
   GitHubリポジトリにアップロード
2. リポジトリの「Settings」→「Secrets and variables」→「Actions」を開く
3. 「New repository secret」で以下を登録
   - Name: `DISCORD_WEBHOOK_URL`
   - Secret: 手順1でコピーしたWebhook URL

> **パブリックリポジトリについて:** Secretsの値はActionsのログにも表示されず、
> フォークされたリポジトリからは参照できない仕組みになっているので、パブリックリポジトリのままで問題ありません。
> また、パブリックリポジトリはGitHub Actionsの実行時間が無料枠無制限なので、
> ワークフローを2本に分けてもコスト面の心配は不要です。

## 3. 投稿時刻を調整したい場合

`.github/workflows/post-jp-indices.yml` と `post-us-indices.yml` 内のcron設定を書き換えます。
**GitHub Actionsのcronは必ずUTC(世界標準時)**で書く必要があるので、日本時間から-9時間して指定してください。

```yaml
# 日本市場用 (15:35 JST = 06:35 UTC)
- cron: "35 6 * * *"

# 米国市場用 (6:05 JST = 前日21:05 UTC)
- cron: "5 21 * * *"
```

> **注意:** GitHub Actionsの`schedule`は指定時刻ちょうどに実行される保証はなく、
> 混雑状況によって数分〜数十分遅れることがあります。正確な時刻厳守が必要な用途には向きません。

## 4. 動作確認

設定後、GitHubリポジトリの「Actions」タブから各ワークフローを選び、
「Run workflow」で手動実行できます(`workflow_dispatch`を有効にしてあります)。
成功すればすぐにDiscordチャンネルに投稿されるので、Secretの設定ミスなどをその場で確認できます。

ローカルで試す場合:
```bash
export DISCORD_WEBHOOK_URL="取得したWebhook URL"
pip install -r requirements.txt
python post_indices.py --group jp   # 日経平均・TOPIXのみ
python post_indices.py --group us   # NYダウ・NASDAQのみ
python post_indices.py --group all  # 全部まとめて(手動テスト用)
```

## 5. 注意点

- **土日は実行されません。** 各ワークフローのcronに曜日指定(月〜金)を入れてあります。
- **祝日で市場が休みの日は自動でスキップされます。** 完全な祝日カレンダーを持っているわけではなく、
  「その日の取引データがまだ存在しない(前営業日のままの日付)場合は投稿しない」という簡易的な判定です。
  これにより、祝日に前営業日と同じ値を重複投稿してしまうことを防いでいます。
  (`post_indices.py` の `get_expected_trading_date` / `main()` 内のロジック)
- リポジトリに**90日間コミットがない**と、GitHubが自動的にscheduled workflowを無効化します。
  その場合はActionsタブから再度有効化してください。
- Yahoo Financeは無料データのため、まれに取得エラーや数分程度の遅延が発生する場合があります。
  取得に失敗した指数はメッセージ内に「データ取得に失敗しました」と表示され、他の指数は投稿されます。

## ファイル構成

| ファイル | 内容 |
|---|---|
| `post_indices.py` | 指数の終値を取得しWebhookに投稿するスクリプト(`--group jp/us/all`で切り替え) |
| `requirements.txt` | 依存パッケージ |
| `.github/workflows/post-jp-indices.yml` | 日経平均・TOPIXを15:35 JSTに投稿するワークフロー |
| `.github/workflows/post-us-indices.yml` | NYダウ・NASDAQを6:05 JSTに投稿するワークフロー |

## 使用しているデータソース

Yahoo Finance の株価データを `yfinance` ライブラリ経由で取得しています。
ティッカーシンボル:
- 日経平均株価: `^N225`
- NYダウ: `^DJI`
- NASDAQ総合指数: `^IXIC`

> **TOPIXについて:** Yahoo Finance経由では信頼できる値が安定して取得できなかったため
> (連動ETFの株式分割で価格スケールがずれる問題が発生したため)、現在は投稿対象から外しています。
> 別のデータソースが見つかり次第、対応を検討してください。

各指数には「妥当な値の範囲」を設定してあり、範囲外の値が返ってきた場合は
取得失敗として扱います(連動ETFが株式分割された場合などに、価格スケールがずれた
誤った値をそのまま投稿してしまうのを防ぐためです)。
