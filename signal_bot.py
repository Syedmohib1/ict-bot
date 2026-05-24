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

def get_candles(exchange, symbol, timeframe="15m", limit=100):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(bars, columns=["time","open","high","low","close","volume"])
        df["time"] = pd.to_datetime(df["time"], unit="ms")
        return df
    except Exception as e:
        print(f"Error {symbol}: {e}")
        return None

def calc_rsi(df, period=14):
    delta = df["close"].diff()
    gain  = delta.where(delta > 0, 0).rolling(period).mean()
    loss  = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs    = gain / loss
    return 100 - (100 / (1 + rs))

def analyze(df, symbol, exchange_name):
    if df is None or len(df) < 50:
        return
    df["rsi"] = calc_rsi(df)
    rsi        = df["rsi"].iloc[-1]
    vol_ma     = df["volume"].rolling(20).mean().iloc[-1]
    high_vol   = df["volume"].iloc[-1] > vol_ma * 1.5
    swing_high = df["high"].rolling(50).max().iloc[-1]
    swing_low  = df["low"].rolling(50).min().iloc[-1]
    fib_618    = swing_high - (swing_high - swing_low) * 0.618
    fib_705    = swing_high - (swing_high - swing_low) * 0.705
    close      = df["close"].iloc[-1]
    near_fib   = abs(close - fib_618)/close < 0.003 or abs(close - fib_705)/close < 0.003
    bull_ob    = (df["close"].iloc[-2] < df["open"].iloc[-2] and
                  df["close"].iloc[-1] > df["open"].iloc[-1] and
                  df["close"].iloc[-1] > df["high"].iloc[-2])
    bear_ob    = (df["close"].iloc[-2] > df["open"].iloc[-2] and
                  df["close"].iloc[-1] < df["open"].iloc[-1] and
                  df["close"].iloc[-1] < df["low"].iloc[-2])
    bull_fvg   = df["low"].iloc[-1] > df["high"].iloc[-3]
    bear_fvg   = df["high"].iloc[-1] < df["low"].iloc[-3]
    prev_high  = df["high"].iloc[-20:-1].max()
    prev_low   = df["low"].iloc[-20:-1].min()
    bull_bos   = close > prev_high
    bear_bos   = close < prev_low
    atr        = (df["high"] - df["low"]).rolling(14).mean().iloc[-1]
    sl_long    = round(close - atr * 1.5, 5)
    tp1_long   = round(close + atr * 2.0, 5)
    tp2_long   = round(close + atr * 3.5, 5)
    sl_short   = round(close + atr * 1.5, 5)
    tp1_short  = round(close - atr * 2.0, 5)
    tp2_short  = round(close - atr * 3.5, 5)

    if bull_bos and bull_fvg and rsi < 40 and high_vol:
        reasons = []
        if bull_ob:  reasons.append("✅ Bullish OB")
        if bull_fvg: reasons.append("✅ FVG present")
        if bull_bos: reasons.append("✅ BOS confirmed")
        if near_fib: reasons.append("✅ Fib 0.618/0.705")
        reasons.append(f"✅ RSI: {rsi:.1f}")
        reasons.append("✅ High Volume")
        msg = (
            f"🟢 *{symbol} — LONG*\n"
            f"📊 {exchange_name}\n\n"
            f"📍 Entry: `{round(close,5)}`\n"
            f"🛡 SL: `{sl_long}`\n"
            f"🎯 TP1: `{tp1_long}`\n"
            f"🎯 TP2: `{tp2_long}`\n\n"
            f"📌 *ICT Analysis:*\n" + "\n".join(reasons) + "\n\n"
            f"⏰ {datetime.now().strftime('%H:%M | %d %b %Y')}"
        )
        send_telegram(msg)
        print(f"✅ LONG: {symbol} | {exchange_name}")

    elif bear_bos and bear_fvg and rsi > 60 and high_vol:
        reasons = []
        if bear_ob:  reasons.append("✅ Bearish OB")
        if bear_fvg: reasons.append("✅ FVG present")
        if bear_bos: reasons.append("✅ BOS confirmed")
        if near_fib: reasons.append("✅ Fib 0.618/0.705")
        reasons.append(f"✅ RSI: {rsi:.1f}")
        reasons.append("✅ High Volume")
        msg = (
            f"🔴 *{symbol} — SHORT*\n"
            f"📊 {exchange_name}\n\n"
            f"📍 Entry: `{round(close,5)}`\n"
            f"🛡 SL: `{sl_short}`\n"
            f"🎯 TP1: `{tp1_short}`\n"
            f"🎯 TP2: `{tp2_short}`\n\n"
            f"📌 *ICT Analysis:*\n" + "\n".join(reasons) + "\n\n"
            f"⏰ {datetime.now().strftime('%H:%M | %d %b %Y')}"
        )
        send_telegram(msg)
        print(f"✅ SHORT: {symbol} | {exchange_name}")
    else:
        print(f"No signal: {symbol} | RSI: {rsi:.1f}")

def run_bot():
    exchanges = {
        "mexc":   ccxt.mexc(),
        "bitget": ccxt.bitget(),
        "kucoin": ccxt.kucoin(),
        "okx":    ccxt.okx(),
        "gateio": ccxt.gateio(),
    }
    print("🚀 ICT Signal Bot chal raha hai...")
    send_telegram("🚀 *ICT Signal Bot Start!*\n5 Exchanges monitor ho rahe hain\nBTC ETH XRP SOL + Forex 📊")
    while True:
        print(f"\n⏱ Scan: {datetime.now().strftime('%H:%M:%S')}")
        for exchange_name, exchange in exchanges.items():
            for symbol in CRYPTO_SYMBOLS.get(exchange_name, []):
                df = get_candles(exchange, symbol)
                analyze(df, symbol, exchange_name)
                time.sleep(1)
        okx = exchanges["okx"]
        for name, pair in FOREX_PAIRS.items():
            try:
                df = get_candles(okx, pair)
                analyze(df, name, "OKX Forex")
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
