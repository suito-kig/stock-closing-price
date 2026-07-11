"""
株価指数(日経平均・TOPIX・NYダウ・NASDAQ)の終値を取得し、
Discordの Webhook URL に1回だけ投稿して終了するスクリプト。

GitHub Actions の scheduled workflow から実行される想定。
(常駐は行わない = discord.py のBotログインは不要)

必要な環境変数:
  DISCORD_WEBHOOK_URL - Discordチャンネルに作成したWebhookのURL
"""

import os
import sys
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
# TOPIXが取得できない場合は 1306.T (TOPIX連動ETF) を自動でフォールバック
INDICES = [
    {"name": "日経平均株価", "ticker": "^N225", "fallback": None},
    {"name": "TOPIX", "ticker": "^TOPX", "fallback": "1306.T"},
    {"name": "NYダウ", "ticker": "^DJI", "fallback": None},
    {"name": "NASDAQ総合指数", "ticker": "^IXIC", "fallback": None},
]

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


def build_embed() -> dict:
    today_str = datetime.datetime.now(JST).strftime("%Y年%m月%d日")
    fields = []

    for index in INDICES:
        data = fetch_last_close(index["ticker"])
        if data is None and index["fallback"]:
            logger.info(
                "%s の取得に失敗したためフォールバック %s を使用します",
                index["ticker"], index["fallback"],
            )
            data = fetch_last_close(index["fallback"])

        if data is None:
            fields.append({
                "name": index["name"],
                "value": "データ取得に失敗しました",
                "inline": False,
            })
            continue

        change = data["change"]
        change_pct = data["change_pct"]
        if change is not None:
            arrow = "🔺" if change > 0 else ("🔻" if change < 0 else "➖")
            change_str = f"{arrow} {change:+,.2f} ({change_pct:+.2f}%)"
        else:
            change_str = "前日比データなし"

        value = f"**{data['close']:,.2f}**\n{change_str}\n({data['date']} 時点)"
        fields.append({"name": index["name"], "value": value, "inline": False})

    embed = {
        "title": f"📈 株価指数 終値速報 ({today_str})",
        "color": 0x2ecc71,
        "fields": fields,
        "footer": {"text": "データ提供: Yahoo Finance (yfinance) / GitHub Actions自動投稿"},
    }
    return embed


def main():
    embed = build_embed()
    payload = {"embeds": [embed]}
    resp = requests.post(WEBHOOK_URL, json=payload, timeout=30)

    if resp.status_code not in (200, 204):
        logger.error("Discordへの投稿に失敗しました: %s %s", resp.status_code, resp.text)
        sys.exit(1)

    logger.info("指数情報を投稿しました。")


if __name__ == "__main__":
    main()
