import ccxt
import pandas as pd
import time
import requests
import json
from datetime import datetime

TELEGRAM_TOKEN = "8209138895:AAEsDG_TmbWS7sz3Xt5g3tZ3pF6bBZf4fgE"
TELEGRAM_CHAT  = "5329321896"

# ── Symbols ──────────────────────────────────────
CRYPTO_SYMBOLS = {
    "binance": ["BTC/USDT", "ETH/USDT", "XRP/USDT"],
    "bybit":   ["BTC/USDT", "ETH/USDT"],
    "bitget":  ["BTC/USDT", "ETH/USDT"],
    "mexc":    ["BTC/USDT", "ETH/USDT"],
}

FOREX_SYMBOLS = [
    "EUR/USD", "GBP/USD", "XAU/USD",
    "GBP/JPY", "NAS100", "US30"
]

# ── Telegram ─────────────────────────────────────
def send_telegram(msg):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "Markdown"},
        timeout=10
    )

# ── Candles fetch karo ───────────────────────────
def get_candles(exchange, symbol, timeframe="15m", limit=100):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(bars, columns=["time", "open", "high", "low", "close", "volume"])
        df["time"] = pd.to_datetime(df["time"], unit="ms")
        return df
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return None

# ── RSI calculate karo ───────────────────────────
def calc_rsi(df, period=14):
    delta = df["close"].diff()
    gain  = delta.where(delta > 0, 0).rolling(period).mean()
    loss  = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs    = gain / loss
    return 100 - (100 / (1 + rs))

# ── ICT Analysis ─────────────────────────────────
def analyze(df, symbol, exchange_name):
    if df is None or len(df) < 50:
        return

    # RSI
    df["rsi"] = calc_rsi(df)
    rsi = df["rsi"].iloc[-1]

    # Volume
    vol_ma   = df["volume"].rolling(20).mean().iloc[-1]
    high_vol = df["volume"].iloc[-1] > vol_ma * 1.5

    # Fibonacci
    swing_high = df["high"].rolling(50).max().iloc[-1]
    swing_low  = df["low"].rolling(50).min().iloc[-1]
    fib_618    = swing_high - (swing_high - swing_low) * 0.618
    fib_705    = swing_high - (swing_high - swing_low) * 0.705
    close      = df["close"].iloc[-1]
    near_fib   = abs(close - fib_618) / close < 0.003 or abs(close - fib_705) / close < 0.003

    # Order Block
    bull_ob = (df["close"].iloc[-2] < df["open"].iloc[-2] and
               df["close"].iloc[-1] > df["open"].iloc[-1] and
               df["close"].iloc[-1] > df["high"].iloc[-2])
    bear_ob = (df["close"].iloc[-2] > df["open"].iloc[-2] and
               df["close"].iloc[-1] < df["open"].iloc[-1] and
               df["close"].iloc[-1] < df["low"].iloc[-2])

    # FVG
    bull_fvg = df["low"].iloc[-1] > df["high"].iloc[-3]
    bear_fvg = df["high"].iloc[-1] < df["low"].iloc[-3]

    # BOS
    prev_high = df["high"].iloc[-20:-1].max()
    prev_low  = df["low"].iloc[-20:-1].min()
    bull_bos  = close > prev_high
    bear_bos  = close < prev_low

    # ATR
    atr      = (df["high"] - df["low"]).rolling(14).mean().iloc[-1]
    sl_long  = round(close - atr * 1.5, 5)
    tp1_long = round(close + atr * 2.0, 5)
    tp2_long = round(close + atr * 3.5, 5)
    sl_short  = round(close + atr * 1.5, 5)
    tp1_short = round(close - atr * 2.0, 5)
    tp2_short = round(close - atr * 3.5, 5)

    # LONG Signal
    if bull_bos and bull_fvg and rsi < 40 and high_vol:
        reasons = []
        if bull_ob:  reasons.append("✅ Bullish OB")
        if bull_fvg: reasons.append("✅ FVG present")
        if bull_bos: reasons.append("✅ BOS confirmed")
        if near_fib: reasons.append("✅ Fib 0.618/0.705")
        reasons.append(f"✅ RSI: {rsi:.1f}")
        reasons.append(f"✅ High Volume")

        msg = (
            f"🟢 *{symbol} — LONG*\n"
            f"📊 Exchange: {exchange_name}\n\n"
            f"📍 Entry: `{round(close, 5)}`\n"
            f"🛡 SL:    `{sl_long}`\n"
            f"🎯 TP1:   `{tp1_long}`\n"
            f"🎯 TP2:   `{tp2_long}`\n\n"
            f"📌 *ICT Reasons:*\n" + "\n".join(reasons) + "\n\n"
            f"⏰ {datetime.now().strftime('%H:%M | %d %b %Y')}"
        )
        send_telegram(msg)
        print(f"LONG signal sent: {symbol}")

    # SHORT Signal
    elif bear_bos and bear_fvg and rsi > 60 and high_vol:
        reasons = []
        if bear_ob:  reasons.append("✅ Bearish OB")
        if bear_fvg: reasons.append("✅ FVG present")
        if bear_bos: reasons.append("✅ BOS confirmed")
        if near_fib: reasons.append("✅ Fib 0.618/0.705")
        reasons.append(f"✅ RSI: {rsi:.1f}")
        reasons.append(f"✅ High Volume")

        msg = (
            f"🔴 *{symbol} — SHORT*\n"
            f"📊 Exchange: {exchange_name}\n\n"
            f"📍 Entry: `{round(close, 5)}`\n"
            f"🛡 SL:    `{sl_short}`\n"
            f"🎯 TP1:   `{tp1_short}`\n"
            f"🎯 TP2:   `{tp2_short}`\n\n"
            f"📌 *ICT Reasons:*\n" + "\n".join(reasons) + "\n\n"
            f"⏰ {datetime.now().strftime('%H:%M | %d %b %Y')}"
        )
        send_telegram(msg)
        print(f"SHORT signal sent: {symbol}")

    else:
        print(f"No signal: {symbol} | RSI: {rsi:.1f} | BOS: {bull_bos}/{bear_bos}")

# ── Main Loop ────────────────────────────────────
def run():
    exchanges = {
        "binance": ccxt.binance(),
        "bybit":   ccxt.bybit(),
        "bitget":  ccxt.bitget(),
        "mexc":    ccxt.mexc(),
    }

    print("🚀 ICT Signal Bot chal raha hai...")
    send_telegram("🚀 *ICT Signal Bot Start Ho Gaya!*\nForex + Crypto monitor ho raha hai 📊")

    while True:
        print(f"\n⏱ Scan: {datetime.now().strftime('%H:%M:%S')}")

        # Crypto scan
        for exchange_name, exchange in exchanges.items():
            for symbol in CRYPTO_SYMBOLS.get(exchange_name, []):
                df = get_candles(exchange, symbol)
                analyze(df, symbol, exchange_name)
                time.sleep(1)

        # Forex scan (Binance pe available pairs)
        forex_pairs = {
            "EUR/USD": "EURUSDT",
            "GBP/USD": "GBPUSDT",
            "XAU/USD": "XAUUSDT",
        }
        for name, pair in forex_pairs.items():
            try:
                df = get_candles(exchanges["binance"], pair)
                analyze(df, name, "Binance Forex")
                time.sleep(1)
            except:
                pass

        print("✅ Scan complete — 5 min baad dobara...")
        time.sleep(300)  # 5 minute

if __name__ == "__main__":
    run()