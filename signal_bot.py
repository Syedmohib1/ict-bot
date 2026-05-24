#!/usr/bin/env python
from flask import Flask
import ccxt
import pandas as pd
import time
import requests
import threading
import os
from datetime import datetime

app = Flask(__name__)

TELEGRAM_TOKEN = "8209138895:AAEsDG_TmbWS7sz3Xt5g3tZ3pF6bBZf4fgE"
TELEGRAM_CHAT  = "5329321896"

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

def send_telegram(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception as e:
        print(f"Telegram error: {e}")

def get_candles(exchange, symbol, timeframe="15m", limit=200):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(bars, columns=["time","open","high","low","close","volume"])
        df["time"] = pd.to_datetime(df["time"], unit="ms")
        return df
    except Exception as e:
        print(f"Error {symbol}: {e}")
        return None

def get_candles_1h(exchange, symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe="1h", limit=100)
        df = pd.DataFrame(bars, columns=["time","open","high","low","close","volume"])
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
    # Higher timeframe bias — 1H chart se trend dekho
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
    # 15M candles
    df = get_candles(exchange, symbol)
    if df is None or len(df) < 100:
        return

    # 1H bias
    df_1h = get_candles_1h(exchange, symbol)
    htf_bias = get_htf_bias(df_1h)

    # RSI
    df["rsi"] = calc_rsi(df)
    rsi = df["rsi"].iloc[-1]
    rsi_prev = df["rsi"].iloc[-2]

    # RSI Divergence check
    price_higher = df["close"].iloc[-1] > df["close"].iloc[-5]
    rsi_lower    = df["rsi"].iloc[-1] < df["rsi"].iloc[-5]
    bear_div     = price_higher and rsi_lower  # Bearish divergence

    price_lower  = df["close"].iloc[-1] < df["close"].iloc[-5]
    rsi_higher   = df["rsi"].iloc[-1] > df["rsi"].iloc[-5]
    bull_div     = price_lower and rsi_higher  # Bullish divergence

    # Volume analysis
    vol_ma    = df["volume"].rolling(20).mean().iloc[-1]
    vol_ratio = df["volume"].iloc[-1] / vol_ma
    high_vol  = vol_ratio > 1.8  # Strict — 1.8x average

    # Fibonacci levels (last 100 candles)
    swing_high = df["high"].rolling(100).max().iloc[-1]
    swing_low  = df["low"].rolling(100).min().iloc[-1]
    fib_382    = swing_high - (swing_high - swing_low) * 0.382
    fib_500    = swing_high - (swing_high - swing_low) * 0.500
    fib_618    = swing_high - (swing_high - swing_low) * 0.618
    fib_705    = swing_high - (swing_high - swing_low) * 0.705
    close      = df["close"].iloc[-1]

    near_fib_buy  = (fib_618 * 0.998 <= close <= fib_705 * 1.002)
    near_fib_sell = (fib_382 * 0.998 <= close <= fib_500 * 1.002)

    # Order Block — strict
    bull_ob = (df["close"].iloc[-3] < df["open"].iloc[-3] and
               df["close"].iloc[-2] < df["open"].iloc[-2] and
               df["close"].iloc[-1] > df["open"].iloc[-1] and
               df["close"].iloc[-1] > df["high"].iloc[-3])

    bear_ob = (df["close"].iloc[-3] > df["open"].iloc[-3] and
               df["close"].iloc[-2] > df["open"].iloc[-2] and
               df["close"].iloc[-1] < df["open"].iloc[-1] and
               df["close"].iloc[-1] < df["low"].iloc[-3])

    # FVG
    bull_fvg = df["low"].iloc[-1] > df["high"].iloc[-3]
    bear_fvg = df["high"].iloc[-1] < df["low"].iloc[-3]

    # BOS — last 30 candles
    prev_high = df["high"].iloc[-30:-1].max()
    prev_low  = df["low"].iloc[-30:-1].min()
    bull_bos  = close > prev_high
    bear_bos  = close < prev_low

    # Engulfing candle
    bull_engulf = (df["close"].iloc[-1] > df["open"].iloc[-2] and
                   df["open"].iloc[-1] < df["close"].iloc[-2] and
                   df["close"].iloc[-1] > df["open"].iloc[-1])
    bear_engulf = (df["close"].iloc[-1] < df["open"].iloc[-2] and
                   df["open"].iloc[-1] > df["close"].iloc[-2] and
                   df["close"].iloc[-1] < df["open"].iloc[-1])

    # ATR — wide SL/TP for 1:2.5 RR
    atr       = (df["high"] - df["low"]).rolling(14).mean().iloc[-1]
    sl_long   = round(close - atr * 2.0, 5)
    tp1_long  = round(close + atr * 2.5, 5)
    tp2_long  = round(close + atr * 4.5, 5)
    sl_short  = round(close + atr * 2.0, 5)
    tp1_short = round(close - atr * 2.5, 5)
    tp2_short = round(close - atr * 4.5, 5)

    rr = "1:2.5"

    # ── LONG CONDITIONS — minimum 4 confirmations ──
    long_score = 0
    long_reasons = []

    if htf_bias == "BULLISH":
        long_score += 2
        long_reasons.append("✅ HTF 1H Bullish bias")
    if bull_bos:
        long_score += 2
        long_reasons.append("✅ BOS confirmed")
    if bull_fvg:
        long_score += 1
        long_reasons.append("✅ FVG present")
    if bull_ob:
        long_score += 2
        long_reasons.append("✅ Bullish OB")
    if near_fib_buy:
        long_score += 2
        long_reasons.append("✅ Fib 0.618-0.705 zone")
    if rsi < 35:
        long_score += 2
        long_reasons.append(f"✅ RSI Oversold: {rsi:.1f}")
    elif rsi < 45:
        long_score += 1
        long_reasons.append(f"✅ RSI Discount: {rsi:.1f}")
    if bull_div:
        long_score += 2
        long_reasons.append("✅ Bullish RSI Divergence")
    if high_vol:
        long_score += 1
        long_reasons.append(f"✅ High Volume: {vol_ratio:.1f}x")
    if bull_engulf:
        long_score += 1
        long_reasons.append("✅ Bullish Engulfing")

    # ── SHORT CONDITIONS — minimum 4 confirmations ──
    short_score = 0
    short_reasons = []

    if htf_bias == "BEARISH":
        short_score += 2
        short_reasons.append("✅ HTF 1H Bearish bias")
    if bear_bos:
        short_score += 2
        short_reasons.append("✅ BOS confirmed")
    if bear_fvg:
        short_score += 1
        short_reasons.append("✅ FVG present")
    if bear_ob:
        short_score += 2
        short_reasons.append("✅ Bearish OB")
    if near_fib_sell:
        short_score += 2
        short_reasons.append("✅ Fib 0.382-0.5 zone")
    if rsi > 65:
        short_score += 2
        short_reasons.append(f"✅ RSI Overbought: {rsi:.1f}")
    elif rsi > 55:
        short_score += 1
        short_reasons.append(f"✅ RSI Premium: {rsi:.1f}")
    if bear_div:
        short_score += 2
        short_reasons.append("✅ Bearish RSI Divergence")
    if high_vol:
        short_score += 1
        short_reasons.append(f"✅ High Volume: {vol_ratio:.1f}x")
    if bear_engulf:
        short_score += 1
        short_reasons.append("✅ Bearish Engulfing")

    # Confidence level
    def get_confidence(score):
        if score >= 10: return "🔥 HIGH"
        elif score >= 7: return "⚡ MEDIUM"
        else: return "⚠️ LOW"

    # Signal bhejo — minimum score 7
    if long_score >= 7 and not bear_bos:
        confidence = get_confidence(long_score)
        msg = (
            f"🟢 *{symbol} — LONG*\n"
            f"📊 {exchange_name} | 15M + 1H\n\n"
            f"📍 Entry: `{round(close,5)}`\n"
            f"🛡 SL: `{sl_long}`\n"
            f"🎯 TP1: `{tp1_long}`\n"
            f"🎯 TP2: `{tp2_long}`\n"
            f"⚖️ R:R: `{rr}`\n\n"
            f"{confidence} | Score: {long_score}/14\n\n"
            f"📌 *ICT Confirmations:*\n" + "\n".join(long_reasons) + "\n\n"
            f"⏰ {datetime.now().strftime('%H:%M | %d %b %Y')}"
        )
        send_telegram(msg)
        print(f"✅ LONG: {symbol} | Score: {long_score} | {exchange_name}")

    elif short_score >= 7 and not bull_bos:
        confidence = get_confidence(short_score)
        msg = (
            f"🔴 *{symbol} — SHORT*\n"
            f"📊 {exchange_name} | 15M + 1H\n\n"
            f"📍 Entry: `{round(close,5)}`\n"
            f"🛡 SL: `{sl_short}`\n"
            f"🎯 TP1: `{tp1_short}`\n"
            f"🎯 TP2: `{tp2_short}`\n"
            f"⚖️ R:R: `{rr}`\n\n"
            f"{confidence} | Score: {short_score}/14\n\n"
            f"📌 *ICT Confirmations:*\n" + "\n".join(short_reasons) + "\n\n"
            f"⏰ {datetime.now().strftime('%H:%M | %d %b %Y')}"
        )
        send_telegram(msg)
        print(f"✅ SHORT: {symbol} | Score: {short_score} | {exchange_name}")
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
        "📊 5 Exchanges: MEXC, Bitget, KuCoin, OKX, Gate.io\n"
        "⏱ Timeframe: 15M + 1H HTF\n"
        "🎯 Min 4 ICT confirmations\n"
        "⚖️ R:R 1:2.5\n\n"
        "Signals aane ka wait karo 📡"
    )
    while True:
        print(f"\n⏱ Scan: {datetime.now().strftime('%H:%M:%S')}")
        for exchange_name, exchange in exchanges.items():
            for symbol in CRYPTO_SYMBOLS.get(exchange_name, []):
                try:
                    analyze(exchange, symbol, exchange_name)
                    time.sleep(1)
                except Exception as e:
                    print(f"Error {symbol}: {e}")
        okx = exchanges["okx"]
        for name, pair in FOREX_PAIRS.items():
            try:
                df = get_candles(okx, pair)
                if df is not None:
                    analyze(okx, pair, f"OKX | {name}")
                time.sleep(1)
            except Exception as e:
                print(f"Forex error {name}: {e}")
        print("✅ Scan complete — 5 min baad...")
        time.sleep(300)

@app.route("/")
def home():
    return "ICT Signal Bot chal raha hai ✅"

bot_thread = threading.Thread(target=run_bot)
bot_thread.daemon = True
bot_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
