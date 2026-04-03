import os
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

#====================
# OANDA CONFIG
#====================
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

#====================
# SETTINGS
#====================
BASE_UNITS = 1000
MIN_SCORE = 0   # allow all signals from Pine

#====================
# SYMBOL MAP
#====================
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

#====================
# CHECK OPEN TRADES
#====================
def has_open_trade():
    url = f"{BASE_URL}/v3/accounts/{OANDA_ACCOUNT_ID}/openTrades"
    r = requests.get(url, headers=HEADERS)

    if r.status_code != 200:
        print("Error checking trades:", r.text)
        return False

    trades = r.json().get("trades", [])
    return len(trades) > 0

#====================
# PLACE ORDER
#====================
def place_order(symbol, action, sl, tp):

    instrument = get_oanda_instrument(symbol)

    # 🔒 ONLY ONE TRADE AT A TIME
    if has_open_trade():
        print("Skipped: trade already open")
        return 200, "Skipped: open trade exists"

    units = BASE_UNITS if action == "buy" else -BASE_UNITS

    sl_price = format_price(instrument, sl)
    tp_price = format_price(instrument, tp)

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

    url = f"{BASE_URL}/v3/accounts/{OANDA_ACCOUNT_ID}/orders"
    r = requests.post(url, headers=HEADERS, json=payload)

    print("OANDA status:", r.status_code)
    print("OANDA response:", r.text)

    return r.status_code, r.text

#====================
# ROUTES
#====================
@app.route("/", methods=["GET"])
def home():
    return "Bot is running 🚀", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    print("Webhook received:", data)

    action = str(data.get("action", "")).lower()
    symbol = str(data.get("symbol", "")).upper()
    sl = float(data.get("sl"))
    tp = float(data.get("tp"))
    score = float(data.get("score", 0))

    # Optional score filter
    if score < MIN_SCORE:
        print("Skipped: low score")
        return jsonify({"status": "skipped"}), 200

    status, response = place_order(symbol, action, sl, tp)

    return jsonify({
        "status": status,
        "response": response
    })
