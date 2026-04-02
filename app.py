import os
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

OANDA_API_KEY = os.getenv("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
OANDA_ENV = os.getenv("OANDA_ENV", "practice").lower()

BASE_URL = (
    "https://api-fxpractice.oanda.com"
    if OANDA_ENV == "practice"
    else "https://api-fxtrade.oanda.com"
)

HEADERS = {
    "Authorization": f"Bearer {OANDA_API_KEY}",
    "Content-Type": "application/json"
}

SYMBOL_MAP = {
    "EURUSD": "EUR_USD",
    "GBPUSD": "GBP_USD",
    "USDJPY": "USD_JPY",
    "AUDUSD": "AUD_USD",
    "USDCAD": "USD_CAD",
    "USDCHF": "USD_CHF",
    "NZDUSD": "NZD_USD",
    "XAUUSD": "XAU_USD",
    "XAGUSD": "XAG_USD",
    "EURJPY": "EUR_JPY",
    "GBPJPY": "GBP_JPY"
}


def get_oanda_instrument(tv_symbol: str) -> str:
    clean = str(tv_symbol).replace("OANDA:", "").replace("/", "").upper().strip()
    return SYMBOL_MAP.get(clean, clean)


def place_order(symbol, action, sl, tp):
    instrument = get_oanda_instrument(symbol)

    if action == "buy":
        units = "100"
    elif action == "sell":
        units = "-100"
    else:
        return 400, f"Invalid action: {action}"

    url = f"{BASE_URL}/v3/accounts/{OANDA_ACCOUNT_ID}/orders"

    payload = {
        "order": {
            "instrument": instrument,
            "units": units,
            "type": "MARKET",
            "timeInForce": "FOK",
            "positionFill": "DEFAULT",
            "stopLossOnFill": {
                "price": str(sl)
            },
            "takeProfitOnFill": {
                "price": str(tp)
            }
        }
    }

    print("Sending order to OANDA:")
    print(payload)

    try:
        response = requests.post(url, headers=HEADERS, json=payload, timeout=20)
        print("Raw OANDA response code:", response.status_code)
        print("Raw OANDA response text:", response.text)
        return response.status_code, response.text
    except Exception as e:
        print("OANDA request exception:", str(e))
        return 500, str(e)


@app.route("/", methods=["GET"])
def home():
    return "Bot is running 🚀", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True, silent=True)

        if not data:
            print("No JSON data received")
            return jsonify({"ok": False, "error": "No JSON data received"}), 400

        print("Webhook data received:", data)

        action = str(data.get("action", "")).lower().strip()
        symbol = str(data.get("symbol", "")).upper().strip()
        sl = data.get("sl")
        tp = data.get("tp")

        try:
            score = float(data.get("score", 0))
        except Exception:
            score = 0

        # Test-friendly filter
        if score < 1:
            print("Skipped trade: low score", score)
            return jsonify({
                "ok": True,
                "status": "skipped",
                "reason": "low score",
                "score": score
            }), 200

        if not action or not symbol or sl is None or tp is None:
            print("Missing required fields")
            return jsonify({
                "ok": False,
                "error": "Missing required fields",
                "received": data
            }), 400

        status, response_text = place_order(symbol, action, sl, tp)

        return jsonify({
            "ok": status in [200, 201],
            "status": "executed" if status in [200, 201] else "failed",
            "oanda_status": status,
            "oanda_response": response_text
        }), 200

    except Exception as e:
        print("Webhook exception:", str(e))
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
