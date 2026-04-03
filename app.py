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

BASE_UNITS = 1000  # adjust if needed

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

def get_oanda_instrument(tv_symbol):
    clean = str(tv_symbol).replace("OANDA:", "").replace("/", "").upper()
    return SYMBOL_MAP.get(clean, clean)

def format_price(instrument, price):
    decimals = INSTRUMENT_PRECISION.get(instrument, 5)
    return f"{float(price):.{decimals}f}"

# 🔒 CHECK OPEN TRADES
def has_open_trade():
    url = f"{BASE_URL}/v3/accounts/{OANDA_ACCOUNT_ID}/openTrades"
    r = requests.get(url, headers=HEADERS)

    if r.status_code != 200:
        print("Error checking trades:", r.text)
        return False

    trades = r.json().get("trades", [])
    print("Open trades count:", len(trades))

    return len(trades) > 0

def place_order(symbol, action, sl, tp, current_price):
    instrument = get_oanda_instrument(symbol)

    # 🔒 BLOCK IF TRADE EXISTS
    if has_open_trade():
        print("Trade skipped: already have open trade")
        return 200, "Skipped: open trade exists"

    units = BASE_UNITS if action == "buy" else -BASE_UNITS

    sl_val = float(sl)
    tp_val = float(tp)
    price = float(current_price)

    MIN_DISTANCE = 0.0010  # 10 pips safety

    if action == "buy":
        if sl_val >= price:
            sl_val = price - MIN_DISTANCE
        if tp_val <= price:
            tp_val = price + MIN_DISTANCE

        if (price - sl_val) < MIN_DISTANCE:
            sl_val = price - MIN_DISTANCE
        if (tp_val - price) < MIN_DISTANCE:
            tp_val = price + MIN_DISTANCE

    elif action == "sell":
        if sl_val <= price:
            sl_val = price + MIN_DISTANCE
        if tp_val >= price:
            tp_val = price - MIN_DISTANCE

        if (sl_val - price) < MIN_DISTANCE:
            sl_val = price + MIN_DISTANCE
        if (price - tp_val) < MIN_DISTANCE:
            tp_val = price - MIN_DISTANCE

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
            "stopLossOnFill": {"price": sl_price},
            "takeProfitOnFill": {"price": tp_price}
        }
    }

    print("Sending order:", payload)

    r = requests.post(url, headers=HEADERS, json=payload)

    print("OANDA status:", r.status_code)
    print("OANDA response:", r.text)

    return r.status_code, r.text


@app.route("/", methods=["GET"])
def home():
    return "Bot is running 🚀", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    print("Webhook:", data)

    action = str(data.get("action", "")).lower()
    symbol = str(data.get("symbol", "")).upper()
    sl = data.get("sl")
    tp = data.get("tp")
    price = data.get("price")
    score = float(data.get("score", 0))

    if score < 1:
        print("Skipped low score")
        return jsonify({"status": "skipped"}), 200

    status, response = place_order(symbol, action, sl, tp, price)

    return jsonify({
        "status": status,
        "response": response
    })
