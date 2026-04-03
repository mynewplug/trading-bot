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

#====================================================
# SETTINGS
#====================================================
BASE_UNITS = 1000
MIN_SCORE = 60  # matches your Pine strategy directionally

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

# tighter scalp distances
SCALP_SL_DISTANCE = {
    "EUR_USD": 0.00030,  # 3 pips
    "GBP_USD": 0.00040,
    "AUD_USD": 0.00030,
    "NZD_USD": 0.00030,
    "USD_CAD": 0.00030,
    "USD_CHF": 0.00030,
    "USD_JPY": 0.030,
    "XAU_USD": 0.80,
    "XAG_USD": 0.06,
}

SCALP_TP_DISTANCE = {
    "EUR_USD": 0.00050,  # 5 pips
    "GBP_USD": 0.00060,
    "AUD_USD": 0.00050,
    "NZD_USD": 0.00050,
    "USD_CAD": 0.00050,
    "USD_CHF": 0.00050,
    "USD_JPY": 0.050,
    "XAU_USD": 1.20,
    "XAG_USD": 0.10,
}

#====================================================
# HELPERS
#====================================================
def get_oanda_instrument(tv_symbol: str) -> str:
    clean = str(tv_symbol).replace("OANDA:", "").replace("/", "").upper().strip()
    return SYMBOL_MAP.get(clean, clean)

def format_price(instrument: str, price: float) -> str:
    decimals = INSTRUMENT_PRECISION.get(instrument, 5)
    return f"{float(price):.{decimals}f}"

def has_open_trade() -> bool:
    url = f"{BASE_URL}/v3/accounts/{OANDA_ACCOUNT_ID}/openTrades"
    r = requests.get(url, headers=HEADERS, timeout=15)

    if r.status_code != 200:
        print("Error checking open trades:", r.status_code, r.text)
        return False

    trades = r.json().get("trades", [])
    print("Open trades count:", len(trades))
    return len(trades) > 0

def build_scalp_prices(instrument: str, action: str, current_price: float):
    price = float(current_price)

    sl_dist = SCALP_SL_DISTANCE.get(instrument, 0.00030)
    tp_dist = SCALP_TP_DISTANCE.get(instrument, 0.00050)

    if action == "buy":
        sl_price = price - sl_dist
        tp_price = price + tp_dist
    elif action == "sell":
        sl_price = price + sl_dist
        tp_price = price - tp_dist
    else:
        raise ValueError(f"Invalid action: {action}")

    return format_price(instrument, sl_price), format_price(instrument, tp_price)

def place_order(symbol: str, action: str, current_price: float):
    instrument = get_oanda_instrument(symbol)

    if has_open_trade():
        print("Trade skipped: already have open trade")
        return 200, "Skipped: open trade exists"

    units = BASE_UNITS if action == "buy" else -BASE_UNITS

    sl_price, tp_price = build_scalp_prices(instrument, action, current_price)

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

    print("Sending order payload:", payload)

    r = requests.post(url, headers=HEADERS, json=payload, timeout=20)

    print("OANDA status:", r.status_code)
    print("OANDA response:", r.text)

    return r.status_code, r.text

#====================================================
# ROUTES
#====================================================
@app.route("/", methods=["GET"])
def home():
    return "Bot is running 🚀", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True, silent=True)

    if not data:
        print("No JSON received")
        return jsonify({"status": "error", "message": "No JSON received"}), 400

    print("Webhook received:", data)

    action = str(data.get("action", "")).lower().strip()
    symbol = str(data.get("symbol", "")).upper().strip()
    price = data.get("price")
    score = float(data.get("score", 0))

    if not action or not symbol or price is None:
        print("Missing required fields")
        return jsonify({"status": "error", "message": "Missing action, symbol, or price"}), 400

    if action not in ["buy", "sell"]:
        print("Invalid action:", action)
        return jsonify({"status": "error", "message": f"Invalid action: {action}"}), 400

    if score < MIN_SCORE:
        print(f"Skipped low score: {score} < {MIN_SCORE}")
        return jsonify({"status": "skipped", "message": "Low score"}), 200

    status, response = place_order(symbol, action, float(price))

    return jsonify({
        "status": status,
        "response": response
    }), 200

#====================================================
# MAIN
#====================================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
