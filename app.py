import os
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# ====================
# OANDA CONFIG
# ====================
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

# ====================
# SETTINGS
# ====================
BASE_UNITS = int(os.getenv("BASE_UNITS", "1000"))

# Pine sends RSI as "score"
# Buy RSI min in Pine is 40, sell RSI max is 60
# Keep Python permissive so Pine stays the main brain
MIN_SCORE = float(os.getenv("MIN_SCORE", "0"))

# ====================
# SYMBOL / PRECISION
# ====================
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


def get_oanda_instrument(tv_symbol: str) -> str:
    clean = str(tv_symbol).replace("OANDA:", "").replace("/", "").upper().strip()
    return SYMBOL_MAP.get(clean, clean)


def format_price(instrument: str, price: float) -> str:
    decimals = INSTRUMENT_PRECISION.get(instrument, 5)
    return f"{float(price):.{decimals}f}"


# ====================
# OPEN TRADE CHECK
# ====================
def has_open_trade() -> bool:
    url = f"{BASE_URL}/v3/accounts/{OANDA_ACCOUNT_ID}/openTrades"
    r = requests.get(url, headers=HEADERS, timeout=15)

    if r.status_code != 200:
        print("Error checking open trades:", r.status_code, r.text)
        return False

    trades = r.json().get("trades", [])
    print("Open trades count:", len(trades))
    return len(trades) > 0


# ====================
# ORDER PLACEMENT
# ====================
def place_order(symbol: str, action: str, sl: float, tp: float):
    instrument = get_oanda_instrument(symbol)

    # one trade at a time
    if has_open_trade():
        print("Skipped: open trade already exists")
        return 200, "Skipped: open trade exists"

    if action == "buy":
        units = BASE_UNITS
    elif action == "sell":
        units = -BASE_UNITS
    else:
        return 400, f"Invalid action: {action}"

    sl_price = format_price(instrument, sl)
    tp_price = format_price(instrument, tp)

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

    url = f"{BASE_URL}/v3/accounts/{OANDA_ACCOUNT_ID}/orders"
    r = requests.post(url, headers=HEADERS, json=payload, timeout=20)

    print("OANDA status:", r.status_code)
    print("OANDA response:", r.text)

    return r.status_code, r.text


# ====================
# ROUTES
# ====================
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
    time_value = data.get("time")
    score = float(data.get("score", 0))
    sl = data.get("sl")
    tp = data.get("tp")

    if not action or not symbol or price is None or sl is None or tp is None:
        return jsonify({
            "status": "error",
            "message": "Missing action, symbol, price, sl, or tp"
        }), 400

    if action not in ["buy", "sell"]:
        return jsonify({
            "status": "error",
            "message": f"Invalid action: {action}"
        }), 400

    try:
        sl = float(sl)
        tp = float(tp)
        price = float(price)
    except ValueError:
        return jsonify({
            "status": "error",
            "message": "Invalid numeric value in price/sl/tp"
        }), 400

    # score is RSI in this Pine script
    if score < MIN_SCORE:
        print(f"Skipped: score {score} < MIN_SCORE {MIN_SCORE}")
        return jsonify({
            "status": "skipped",
            "message": "Low score"
        }), 200

    print(
        f"Parsed signal -> action={action}, symbol={symbol}, "
        f"price={price}, score={score}, sl={sl}, tp={tp}, time={time_value}"
    )

    status, response = place_order(symbol, action, sl, tp)

    return jsonify({
        "status": status,
        "response": response
    }), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
