import os
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

OANDA_API_KEY = os.getenv("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
OANDA_ENV = os.getenv("OANDA_ENV", "practice")

BASE_URL = "https://api-fxpractice.oanda.com" if OANDA_ENV == "practice" else "https://api-fxtrade.oanda.com"

HEADERS = {
    "Authorization": f"Bearer {OANDA_API_KEY}",
    "Content-Type": "application/json"
}

def place_order(symbol, action, sl, tp):
    units = 100 if action == "buy" else -100

    url = f"{BASE_URL}/v3/accounts/{OANDA_ACCOUNT_ID}/orders"

    data = {
        "order": {
            "instrument": symbol.replace("OANDA:", "").replace("/", "_"),
            "units": str(units),
            "type": "MARKET",
            "positionFill": "DEFAULT",
            "stopLossOnFill": {"price": str(sl)},
            "takeProfitOnFill": {"price": str(tp)}
        }
    }

    r = requests.post(url, headers=HEADERS, json=data)
    return r.status_code, r.text


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data"}), 400

    action = data.get("action")
    symbol = data.get("symbol")
    sl = data.get("sl")
    tp = data.get("tp")
    score = float(data.get("score", 0))

    # 🔥 SNIPER FILTER
    if score < 80:
        return jsonify({"status": "skipped", "reason": "low score"})

    status, response = place_order(symbol, action, sl, tp)

    return jsonify({
        "status": "executed",
        "oanda_status": status,
        "response": response
    })


@app.route("/")
def home():
    return "Bot is running 🚀"


if __name__ == "__main__":
    app.run(port=8000)