"""
株価指数の終値を取得し、Discordの Webhook URL に1回だけ投稿して終了するスクリプト。

GitHub Actions の scheduled workflow から実行される想定。
(常駐は行わない = discord.py のBotログインは不要)

日本市場(日経平均・TOPIX)と米国市場(NYダウ・NASDAQ)は終値が確定する時刻が
大きく異なるため、--group 引数でどちらを投稿するか指定できるようにしている。

使い方:
  python post_indices.py --group jp   # 日経平均・TOPIXのみ投稿
  python post_indices.py --group us   # NYダウ・NASDAQのみ投稿
  python post_indices.py --group all  # 全部まとめて投稿(デフォルト)

必要な環境変数:
  DISCORD_WEBHOOK_URL - Discordチャンネルに作成したWebhookのURL

  :更新用行
"""

import os
import sys
import argparse
import datetime
import logging

import requests
import yfinance as yf

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("index-bot")

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

if not WEBHOOK_URL:
    logger.error("環境変数 DISCORD_WEBHOOK_URL が設定されていません。")
    sys.exit(1)

# 投稿する指数と Yahoo Finance のティッカーシンボル
# 各指数ごとに「ありえない値」を弾くための妥当範囲(min, max)も設定しておく。
# これにより、ETFの株式分割などでフォールバック先の価格スケールが急変した場合でも
# 誤った値をそのまま投稿してしまうことを防ぐ。
INDICES_JP = [
    {
        "name": "日経平均株価",
        "ticker": "^N225",
        "fallback": None,
        "valid_range": (5000, 150000),
    },
]
INDICES_US = [
    {
        "name": "NYダウ",
        "ticker": "^DJI",
        "fallback": None,
        "valid_range": (5000, 100000),
    },
    {
        "name": "NASDAQ総合指数",
        "ticker": "^IXIC",
        "fallback": None,
        "valid_range": (1000, 50000),
    },
]
INDICES_ALL = INDICES_JP + INDICES_US

GROUP_MAP = {
    "jp": (INDICES_JP, "日本市場 終値速報"),
    "us": (INDICES_US, "米国市場 終値速報"),
    "all": (INDICES_ALL, "株価指数 終値速報"),
}

JST = datetime.timezone(datetime.timedelta(hours=9))


def fetch_last_close(ticker: str):
    """指定ティッカーの直近の終値と前日比を取得する。取得失敗時は None を返す。"""
    try:
        hist = yf.Ticker(ticker).history(period="5d")
        if hist is None or len(hist) < 1:
            return None
        closes = hist["Close"].dropna()
        if len(closes) < 1:
            return None
        last_close = float(closes.iloc[-1])
        last_date = closes.index[-1].strftime("%Y-%m-%d")
        prev_close = float(closes.iloc[-2]) if len(closes) >= 2 else None
        change = None
        change_pct = None
        if prev_close is not None:
            change = last_close - prev_close
            change_pct = (change / prev_close) * 100
        return {
            "close": last_close,
            "date": last_date,
            "change": change,
            "change_pct": change_pct,
        }
    except Exception as e:
        logger.warning("価格取得に失敗しました (%s): %s", ticker, e)
        return None


def fetch_index_data(index: dict):
    """
    ticker → (失敗すれば) fallback の順に取得を試み、valid_range から外れた値は
    「取得失敗」として扱う(株式分割などでスケールがずれた値を誤投稿しないため)。
    """
    valid_range = index.get("valid_range")
    candidates = [index["ticker"]]
    if index.get("fallback"):
        candidates.append(index["fallback"])

    for ticker in candidates:
        data = fetch_last_close(ticker)
        if data is None:
            continue
        if valid_range and not (valid_range[0] <= data["close"] <= valid_range[1]):
            logger.warning(
                "%s の取得値 %.2f が妥当範囲 %s の外だったため無効とみなします",
                ticker, data["close"], valid_range,
            )
            continue
        return data

    return None


def build_embed(group: str) -> dict:
    indices, title_label = GROUP_MAP[group]
    today_str = datetime.datetime.now(JST).strftime("%Y年%m月%d日")
    fields = []

    for i, index in enumerate(indices):
        data = fetch_index_data(index)
        is_last = i == len(indices) - 1

        if data is None:
            value = "データ取得に失敗しました"
        else:
            change = data["change"]
            change_pct = data["change_pct"]
            if change is not None:
                arrow = "🔺" if change > 0 else ("🔻" if change < 0 else "➖")
                change_str = f"{arrow} {change:+,.2f} ({change_pct:+.2f}%)"
            else:
                change_str = "前日比データなし"
            value = f"**{data['close']:,.2f}**\n{change_str}\n({data['date']} 時点)"

        # 指数と指数の間に軽く余白を入れる(フィールドを分けると余白が大きくなりすぎるため
        # 同じフィールドの末尾に空行を1行追加するだけにする)
        if not is_last:
            value += "\n\u200b"

        fields.append({"name": index["name"], "value": value, "inline": False})

    embed = {
        "title": f"📈 {title_label} ({today_str})",
        "color": 0x2ecc71,
        "fields": fields,
    }
    return embed


def get_expected_trading_date(group: str):
    """
    このgroupの投稿が「新しい取引日のデータ」であるべき日付(YYYY-MM-DD)を返す。
    祝日等でこの日付のデータがまだ無い場合は、投稿をスキップして重複投稿を防ぐために使う。
    all(手動テスト用)の場合は None を返し、フレッシュさのチェックをスキップする。
    """
    if group == "jp":
        # 日本市場は15:35 JST(市場クローズ後)に実行される想定なので、JSTの「今日」が取引日のはず
        return datetime.datetime.now(JST).strftime("%Y-%m-%d")
    if group == "us":
        # 米国市場は21:05 UTC(米国市場クローズ直後)に実行される想定なので、UTCの「今日」が取引日のはず
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    return None


def parse_args():
    parser = argparse.ArgumentParser(description="株価指数の終値をDiscordに投稿する")
    parser.add_argument(
        "--group",
        choices=["jp", "us", "all"],
        default="all",
        help="投稿する指数グループ (jp: 日経平均/TOPIX, us: NYダウ/NASDAQ, all: 全部)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    expected_date = get_expected_trading_date(args.group)
    if expected_date:
        indices, _ = GROUP_MAP[args.group]
        anchor_data = fetch_index_data(indices[0])
        if anchor_data is None or anchor_data["date"] != expected_date:
            logger.info(
                "最新の取引日データがまだ無いため投稿をスキップします"
                "(祝日などで市場が休みの可能性があります。期待日=%s, 取得日=%s)",
                expected_date, anchor_data["date"] if anchor_data else None,
            )
            return

    embed = build_embed(args.group)
    payload = {"embeds": [embed]}
    resp = requests.post(WEBHOOK_URL, json=payload, timeout=30)

    if resp.status_code not in (200, 204):
        logger.error("Discordへの投稿に失敗しました: %s %s", resp.status_code, resp.text)
        sys.exit(1)

    logger.info("指数情報を投稿しました。(group=%s)", args.group)


if __name__ == "__main__":
    main()
