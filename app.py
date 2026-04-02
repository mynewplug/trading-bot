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

# ✅ SAFE SIZE FOR $33 ACCOUNT
BASE_UNITS = 100

# Instrument formatting
SYMBOL_MAP = {
    "EURUSD": "EUR_USD",
    "GBPUSD": "GBP_USD",
    "USDJPY": "USD_JPY",
    "AUDUSD": "AUD_USD",
    "USDCAD": "USD_CAD",
    "USDCHF": "USD_CHF",
    "NZDUSD": "NZD_USD",
    "XAUUSD": "XAU_USD",
    "XAGUSD": "XAG_USD"
}

# Price precision
INSTRUMENT_PRECISION = {
    "EUR_USD": 5,
    "GBP_USD": 5,
    "AUD_USD": 5,
    "NZD_USD": 5,
    "USD_CAD": 5,
    "USD_CHF": 5,
    "USD_JPY": 3,
    "XAU_USD": 2,
    "XAG_USD": 3,
}

def get_oanda_instrument(tv_symbol: str) -> str:
    clean = str(tv_symbol).replace("OANDA:", "").replace("/", "").upper().strip()
    return SYMBOL_MAP.get(clean, clean)

def format_price(instrument: str, price) -> str:
    decimals = INSTRUMENT_PRECISION.get(instrument, 5)
    return f"{float(price):.{decimals}f}"

def place_order(symbol, action, sl, tp, current_price):
    instrument = get_oanda_instrument(symbol)

    # ✅ Safe units
    units = BASE_UNITS if action == "buy" else -BASE_UNITS

    # ✅ Convert values
    sl_val = float(sl)
    tp_val = float(tp)
    price = float(current_price)

    # ✅ MIN DISTANCE (10 pips for EURUSD)
    MIN_DISTANCE = 0.0010

    # 🔥 FIX SL/TP LOGIC
    if action == "buy":
        # SL must be below price
        if sl_val >= price:
            sl_val = price - MIN_DISTANCE

        # TP must be above price
        if tp_val <= price:
            tp_val = price + MIN_DISTANCE

        # ensure distance
        if (price - sl_val) < MIN_DISTANCE:
            sl_val = price - MIN_DISTANCE

        if (tp_val - price) < MIN_DISTANCE:
            tp_val = price + MIN_DISTANCE

    elif action == "sell":
        # SL must be above price
        if sl_val <= price:
            sl_val = price + MIN_DISTANCE

        # TP must be below price
        if tp_val >= price:
            tp_val = price - MIN_DISTANCE

        # ensure distance
        if (sl_val - price) < MIN_DISTANCE:
            sl_val = price + MIN_DISTANCE

        if (price - tp_val) < MIN_DISTANCE:
            tp_val = price - MIN_DISTANCE

    # ✅ Format properly
    sl_price = format_price(instrument, sl_val)
    tp_price = format_price(instrument, tp_val)

    url = f"{BASE_URL}/v3/accounts/{OANDA_ACCOUNT_ID}/orders"

    payload = {
        "order": {
            "instrument": instrument,
            "units": str(units),
            "type": "MARKET",
            "timeInForce": "FOK",
            "positionFill": "DEFAULT",
            "stopLossOnFill": {
                "price": sl_price
            },
            "takeProfitOnFill": {
                "price": tp_price
            }
        }
    }

    print("Sending order to OANDA:")
    print(payload)

    try:
        response = requests.post(url, headers=HEADERS, json=payload, timeout=20)
        print("OANDA status:", response.status_code)
        print("OANDA response:", response.text)
        return response.status_code, response.text
    except Exception as e:
        print("OANDA error:", str(e))
        return 500, str(e)


@app.route("/", methods=["GET"])
def home():
    return "Bot is running 🚀", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True, silent=True)

        if not data:
            print("No data received")
            return jsonify({"error": "No data"}), 400

        print("Webhook data:", data)

        action = str(data.get("action", "")).lower()
        symbol = str(data.get("symbol", "")).upper()
        sl = data.get("sl")
        tp = data.get("tp")
        price = data.get("price")

        score = float(data.get("score", 0))

        # ✅ allow trades for testing
        if score < 1:
            print("Skipped: low score")
            return jsonify({"status": "skipped"}), 200

        if not action or not symbol or not sl or not tp or not price:
            print("Missing data")
            return jsonify({"error": "missing fields"}), 400

        status, response = place_order(symbol, action, sl, tp, price)

        return jsonify({
            "status": "executed" if status in [200, 201] else "failed",
            "oanda_status": status,
            "response": response
        }), 200

    except Exception as e:
        print("Webhook error:", str(e))
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
