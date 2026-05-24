from flask import Flask, request, jsonify
from groq import Groq
import requests, json
from datetime import datetime

app = Flask(__name__)

groq_client = Groq(api_key="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")

TELEGRAM_TOKEN = "8209138895:AAEsDG_TmbWS7sz3Xt5g3tZ3pF6bBZf4fgE"
TELEGRAM_CHAT  = "5329321896"

def get_ict_signal(data):
    prompt = f"""
Tu ek expert ICT trader hai. Yeh data analyze kar:

Symbol:  {data.get('symbol')}
Action:  {data.get('action')}
Price:   {data.get('close')}
RSI:     {data.get('rsi')}
BOS:     {data.get('bos')}
FVG:     {data.get('fvg')}
OB:      {data.get('ob')}
Fib 618: {data.get('fib618')}
SL:      {data.get('sl')}
TP:      {data.get('tp')}

Sirf JSON mein jawab do. Koi explanation nahi, koi markdown nahi, sirf JSON:
{{"confirmed":true,"direction":"LONG","entry":67000,"sl":66500,"tp1":68000,"tp2":69000,"rr":"1:3","confidence":"HIGH","reason":"ICT analysis yahan"}}

JSON ke bahar kuch bhi mat likho. Pehla character {{ hona chahiye.
"""
    resp = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "Tu sirf valid JSON return karta hai. Koi extra text nahi, koi markdown nahi, sirf JSON object."},
            {"role": "user", "content": prompt}
        ]
    )
    text = resp.choices[0].message.content.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    start = text.find('{')
    end   = text.rfind('}') + 1
    return json.loads(text[start:end])

def send_telegram(signal, raw):
    e  = "🟢" if signal["direction"] == "LONG" else "🔴"
    cf = {"HIGH": "🔥", "MEDIUM": "⚡", "LOW": "⚠️"}
    msg = (
        f"{e} *{raw.get('symbol')} — {signal['direction']}*\n\n"
        f"📍 Entry: `{signal['entry']}`\n"
        f"🛡 SL:    `{signal['sl']}`\n"
        f"🎯 TP1:   `{signal['tp1']}`\n"
        f"🎯 TP2:   `{signal['tp2']}`\n"
        f"⚖️ R:R:   `{signal['rr']}`\n\n"
        f"{cf.get(signal['confidence'], '⚡')} Confidence: {signal['confidence']}\n\n"
        f"📊 {signal['reason']}\n\n"
        f"⏰ {datetime.now().strftime('%H:%M | %d %b %Y')}"
    )
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "Markdown"},
        timeout=10
    )

@app.route("/")
def home():
    return "ICT Signal Bot chal raha hai ✅"

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "koi data nahi"}), 400
        print(f"Alert mila: {data}")
        signal = get_ict_signal(data)
        if signal.get("confirmed"):
            send_telegram(signal, data)
            return jsonify({"status": "signal bhej diya ✅", "signal": signal})
        else:
            return jsonify({"status": "signal confirm nahi hua"})
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)