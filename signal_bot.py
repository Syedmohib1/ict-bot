#!/usr/bin/env python
from flask import Flask
import ccxt
import pandas as pd
import time
import requests
import threading
import os
from datetime import datetime
import xml.etree.ElementTree as ET
import pytz

app = Flask(__name__)

PKT = pytz.timezone("Asia/Karachi")

TELEGRAM_TOKEN  = "8209138895:AAEsDG_TmbWS7sz3Xt5g3tZ3pF6bBZf4fgE"
TELEGRAM_CHAT   = "5329321896"
last_news_title = ""
NEWS_ZONE       = False

CRYPTO_SYMBOLS = {
    "mexc":   ["BTC/USDT", "ETH/USDT", "XRP/USDT", "SOL/USDT"],
    "bitget": ["BTC/USDT", "ETH/USDT", "XRP/USDT", "SOL/USDT"],
    "kucoin": ["BTC/USDT", "ETH/USDT", "XRP/USDT", "SOL/USDT"],
    "okx":    ["BTC/USDT", "ETH/USDT", "XRP/USDT", "SOL/USDT"],
    "gateio": ["BTC/USDT", "ETH/USDT", "XRP/USDT", "SOL/USDT"],
}

FOREX_PAIRS = {
    "EUR/USD": "EUR/USDT",
    "GBP/USD": "GBP/USDT",
    "XAU/USD": "XAU/USDT",
}

# News keywords — bullish ya bearish
BULLISH_NEWS = [
    "rate cut", "dovish", "stimulus", "gold rally",
    "dollar falls", "ceasefire", "peace", "recovery",
    "gdp growth", "jobs growth", "trump tariff removed"
]
BEARISH_NEWS = [
    "rate hike", "hawkish", "inflation surge", "war",
    "crisis", "sanctions", "nfp miss", "recession",
    "dollar rises", "fed hike", "tariff", "conflict",
    "cpi hot", "fomc hike"
]
GOLD_BULLISH = ["war", "crisis", "conflict", "sanctions", "inflation", "safe haven"]
GOLD_BEARISH = ["rate hike", "hawkish", "dollar rises", "fed hike", "strong dollar"]

def pkt_time():
    return datetime.now(PKT).strftime('%H:%M | %d %b %Y') + " PKT"

def send_telegram(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception as e:
        print(f"Telegram error: {e}")

def send_news_signal(title, direction, pair, reason):
    if direction == "LONG":
        emoji = "🟢"
        sl_pips = "30 pips / $30"
        tp_pips = "90 pips / $90"
        rr = "1:3"
    else:
        emoji = "🔴"
        sl_pips = "30 pips / $30"
        tp_pips = "90 pips / $90"
        rr = "1:3"

    msg = (
        f"📰 *NEWS TRADE SIGNAL!*\n\n"
        f"{emoji} *{pair} — {direction}*\n\n"
        f"📌 *News:* {title}\n\n"
        f"📊 *Trade Setup:*\n"
        f"⚡ Entry: Market price pe enter karo\n"
        f"🛡 SL: {sl_pips}\n"
        f"🎯 TP: {tp_pips}\n"
        f"⚖️ R:R: `{rr}`\n\n"
        f"⚠️ *Reason:* {reason}\n\n"
        f"🔥 HIGH IMPACT — Fast move expected!\n"
        f"⏰ {pkt_time()}"
    )
    send_telegram(msg)
    print(f"📰 NEWS SIGNAL: {pair} {direction}")

def check_news():
    global last_news_title, NEWS_ZONE

    rss_feeds = [
        "https://feeds.reuters.com/reuters/businessNews",
        "https://feeds.bloomberg.com/markets/news.rss",
    ]

    all_keywords = BULLISH_NEWS + BEARISH_NEWS + GOLD_BULLISH + GOLD_BEARISH

    try:
        for feed_url in rss_feeds:
            try:
                resp = requests.get(
                    feed_url, timeout=8,
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                root = ET.fromstring(resp.content)
                for item in root.iter("item"):
                    title = item.find("title")
                    if title is not None and title.text:
                        t = title.text.lower()

                        # Sirf nayi news pe
                        if title.text == last_news_title:
                            return

                        for kw in all_keywords:
                            if kw in t:
                                last_news_title = title.text

                                # Gold signals
                                for gk in GOLD_BULLISH:
                                    if gk in t:
                                        send_news_signal(
                                            title.text, "LONG", "XAU/USD (Gold)",
                                            "War/Crisis/Inflation = Gold pumps 🚀"
                                        )
                                        return

                                for gk in GOLD_BEARISH:
                                    if gk in t:
                                        send_news_signal(
                                            title.text, "SHORT", "XAU/USD (Gold)",
                                            "Strong Dollar/Rate Hike = Gold dumps 📉"
                                        )
                                        return

                                # Forex signals
                                for bk in BULLISH_NEWS:
                                    if bk in t:
                                        send_news_signal(
                                            title.text, "LONG", "GBP/USD & EUR/USD",
                                            "Dollar weakness expected 📉"
                                        )
                                        return

                                for bk in BEARISH_NEWS:
                                    if bk in t:
                                        send_news_signal(
                                            title.text, "SHORT", "GBP/USD & EUR/USD",
                                            "Dollar strength expected 📈"
                                        )
                                        return
            except:
                continue
    except Exception as e:
        print(f"News error: {e}")

def news_monitor():
    while True:
        check_news()
        time.sleep(60)  # Har 1 min news check

def get_candles(exchange, symbol, timeframe="15m", limit=200):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df   = pd.DataFrame(bars, columns=["time","open","high","low","close","volume"])
        df["time"] = pd.to_datetime(df["time"], unit="ms")
        return df
    except:
        return None

def get_candles_1h(exchange, symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe="1h", limit=100)
        df   = pd.DataFrame(bars, columns=["time","open","high","low","close","volume"])
        df["time"] = pd.to_datetime(df["time"], unit="ms")
        return df
    except:
        return None

def calc_rsi(df, period=14):
    delta = df["close"].diff()
    gain  = delta.where(delta > 0, 0).rolling(period).mean()
    loss  = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs    = gain / loss
    return 100 - (100 / (1 + rs))

def get_htf_bias(df_1h):
    if df_1h is None or len(df_1h) < 50:
        return "NEUTRAL"
    ema_20 = df_1h["close"].ewm(span=20).mean().iloc[-1]
    ema_50 = df_1h["close"].ewm(span=50).mean().iloc[-1]
    close  = df_1h["close"].iloc[-1]
    if close > ema_20 > ema_50:
        return "BULLISH"
    elif close < ema_20 < ema_50:
        return "BEARISH"
    return "NEUTRAL"

def analyze(exchange, symbol, exchange_name):
    df = get_candles(exchange, symbol)
    if df is None or len(df) < 100:
        return

    df_1h    = get_candles_1h(exchange, symbol)
    htf_bias = get_htf_bias(df_1h)

    if htf_bias == "NEUTRAL":
        print(f"↔️ Neutral — skip {symbol}")
        return

    df["rsi"] = calc_rsi(df)
    rsi       = df["rsi"].iloc[-1]

    bull_div = (df["close"].iloc[-1] < df["close"].iloc[-5] and
                df["rsi"].iloc[-1]   > df["rsi"].iloc[-5])
    bear_div = (df["close"].iloc[-1] > df["close"].iloc[-5] and
                df["rsi"].iloc[-1]   < df["rsi"].iloc[-5])

    vol_ma    = df["volume"].rolling(20).mean().iloc[-1]
    vol_ratio = df["volume"].iloc[-1] / vol_ma
    high_vol  = vol_ratio > 2.0

    swing_high    = df["high"].rolling(100).max().iloc[-1]
    swing_low     = df["low"].rolling(100).min().iloc[-1]
    fib_618       = swing_high - (swing_high - swing_low) * 0.618
    fib_705       = swing_high - (swing_high - swing_low) * 0.705
    fib_382       = swing_high - (swing_high - swing_low) * 0.382
    fib_500       = swing_high - (swing_high - swing_low) * 0.500
    close         = df["close"].iloc[-1]
    near_fib_buy  = fib_618 * 0.997 <= close <= fib_705 * 1.003
    near_fib_sell = fib_382 * 0.997 <= close <= fib_500 * 1.003

    bull_ob = (df["close"].iloc[-3] < df["open"].iloc[-3] and
               df["close"].iloc[-2] < df["open"].iloc[-2] and
               df["close"].iloc[-1] > df["open"].iloc[-1] and
               df["close"].iloc[-1] > df["high"].iloc[-3])
    bear_ob = (df["close"].iloc[-3] > df["open"].iloc[-3] and
               df["close"].iloc[-2] > df["open"].iloc[-2] and
               df["close"].iloc[-1] < df["open"].iloc[-1] and
               df["close"].iloc[-1] < df["low"].iloc[-3])

    bull_fvg = df["low"].iloc[-1]  > df["high"].iloc[-3]
    bear_fvg = df["high"].iloc[-1] < df["low"].iloc[-3]

    prev_high = df["high"].iloc[-30:-1].max()
    prev_low  = df["low"].iloc[-30:-1].min()
    bull_bos  = close > prev_high
    bear_bos  = close < prev_low

    bull_engulf = (df["close"].iloc[-1] > df["open"].iloc[-2] and
                   df["open"].iloc[-1]  < df["close"].iloc[-2] and
                   df["close"].iloc[-1] > df["open"].iloc[-1])
    bear_engulf = (df["close"].iloc[-1] < df["open"].iloc[-2] and
                   df["open"].iloc[-1]  > df["close"].iloc[-2] and
                   df["close"].iloc[-1] < df["open"].iloc[-1])

    atr       = (df["high"] - df["low"]).rolling(14).mean().iloc[-1]
    sl_long   = round(close - atr * 2.0, 5)
    tp1_long  = round(close + atr * 2.5, 5)
    tp2_long  = round(close + atr * 4.5, 5)
    sl_short  = round(close + atr * 2.0, 5)
    tp1_short = round(close - atr * 2.5, 5)
    tp2_short = round(close - atr * 4.5, 5)

    long_score   = 0
    long_reasons = []
    if htf_bias == "BULLISH":
        long_score += 2; long_reasons.append("✅ HTF 1H Bullish")
    if bull_bos:
        long_score += 2; long_reasons.append("✅ BOS confirmed")
    if bull_ob:
        long_score += 2; long_reasons.append("✅ Bullish OB")
    if bull_fvg:
        long_score += 1; long_reasons.append("✅ FVG present")
    if near_fib_buy:
        long_score += 2; long_reasons.append("✅ Fib 0.618-0.705")
    if rsi < 35:
        long_score += 2; long_reasons.append(f"✅ RSI Oversold: {rsi:.1f}")
    elif rsi < 45:
        long_score += 1; long_reasons.append(f"✅ RSI Discount: {rsi:.1f}")
    if bull_div:
        long_score += 2; long_reasons.append("✅ Bullish Divergence")
    if high_vol:
        long_score += 1; long_reasons.append(f"✅ Volume: {vol_ratio:.1f}x")
    if bull_engulf:
        long_score += 1; long_reasons.append("✅ Bullish Engulfing")

    short_score   = 0
    short_reasons = []
    if htf_bias == "BEARISH":
        short_score += 2; short_reasons.append("✅ HTF 1H Bearish")
    if bear_bos:
        short_score += 2; short_reasons.append("✅ BOS confirmed")
    if bear_ob:
        short_score += 2; short_reasons.append("✅ Bearish OB")
    if bear_fvg:
        short_score += 1; short_reasons.append("✅ FVG present")
    if near_fib_sell:
        short_score += 2; short_reasons.append("✅ Fib 0.382-0.5")
    if rsi > 65:
        short_score += 2; short_reasons.append(f"✅ RSI Overbought: {rsi:.1f}")
    elif rsi > 55:
        short_score += 1; short_reasons.append(f"✅ RSI Premium: {rsi:.1f}")
    if bear_div:
        short_score += 2; short_reasons.append("✅ Bearish Divergence")
    if high_vol:
        short_score += 1; short_reasons.append(f"✅ Volume: {vol_ratio:.1f}x")
    if bear_engulf:
        short_score += 1; short_reasons.append("✅ Bearish Engulfing")

    def get_confidence(score):
        if score >= 10: return "🔥 HIGH"
        elif score >= 8: return "⚡ MEDIUM"
        else: return "⚠️ LOW"

    if long_score >= 10 and htf_bias == "BULLISH" and not bear_bos:
        msg = (
            f"🟢 *{symbol} — LONG*\n"
            f"📊 {exchange_name} | 15M+1H\n\n"
            f"📍 Entry: `{round(close,5)}`\n"
            f"🛡 SL: `{sl_long}`\n"
            f"🎯 TP1: `{tp1_long}`\n"
            f"🎯 TP2: `{tp2_long}`\n"
            f"⚖️ R:R: `1:2.5`\n\n"
            f"{get_confidence(long_score)} | Score: {long_score}/15\n\n"
            f"📌 *Confirmations:*\n" + "\n".join(long_reasons) + "\n\n"
            f"⏰ {pkt_time()}"
        )
        send_telegram(msg)
        print(f"🟢 LONG: {symbol} | {long_score}/15")

    elif short_score >= 10 and htf_bias == "BEARISH" and not bull_bos:
        msg = (
            f"🔴 *{symbol} — SHORT*\n"
            f"📊 {exchange_name} | 15M+1H\n\n"
            f"📍 Entry: `{round(close,5)}`\n"
            f"🛡 SL: `{sl_short}`\n"
            f"🎯 TP1: `{tp1_short}`\n"
            f"🎯 TP2: `{tp2_short}`\n"
            f"⚖️ R:R: `1:2.5`\n\n"
            f"{get_confidence(short_score)} | Score: {short_score}/15\n\n"
            f"📌 *Confirmations:*\n" + "\n".join(short_reasons) + "\n\n"
            f"⏰ {pkt_time()}"
        )
        send_telegram(msg)
        print(f"🔴 SHORT: {symbol} | {short_score}/15")
    else:
        print(f"No signal: {symbol} | L:{long_score} S:{short_score} | RSI:{rsi:.1f}")

def run_bot():
    exchanges = {
        "mexc":   ccxt.mexc(),
        "bitget": ccxt.bitget(),
        "kucoin": ccxt.kucoin(),
        "okx":    ccxt.okx(),
        "gateio": ccxt.gateio(),
    }
    print("🚀 ICT Signal Bot chal raha hai...")
    send_telegram(
        "🚀 *ICT Signal Bot Start!*\n\n"
        "📊 5 Exchanges\n"
        "⏱ Scan: har 12 seconds\n"
        "🎯 Score 10+ pe signal\n"
        "📰 News = Trade signal!\n"
        "⚖️ R:R 1:2.5 — 1:3\n"
        "🕐 Pakistan Time\n\n"
        "Signals ka wait karo 📡"
    )
    while True:
        print(f"\n⏱ Scan: {datetime.now(PKT).strftime('%H:%M:%S')} PKT")
        for exchange_name, exchange in exchanges.items():
            for symbol in CRYPTO_SYMBOLS.get(exchange_name, []):
                try:
                    analyze(exchange, symbol, exchange_name)
                    time.sleep(0.2)
                except Exception as e:
                    print(f"Error {symbol}: {e}")
                    time.sleep(0.2)
        okx = exchanges["okx"]
        for name, pair in FOREX_PAIRS.items():
            try:
                analyze(okx, pair, f"OKX|{name}")
                time.sleep(0.2)
            except Exception as e:
                print(f"Forex error {name}: {e}")
        print("✅ Scan complete — 12 sec baad...")
        time.sleep(12)

@app.route("/")
def home():
    return "ICT Signal Bot chal raha hai ✅"

news_thread = threading.Thread(target=news_monitor)
news_thread.daemon = True
news_thread.start()

bot_thread = threading.Thread(target=run_bot)
bot_thread.daemon = True
bot_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
