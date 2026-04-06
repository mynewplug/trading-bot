import os
import json
import logging
from datetime import datetime, timezone

from flask import Flask, request, jsonify

app = Flask(__name__)

# =========================================================
# LOGGING
# =========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("icc-flask-webhook")

# =========================================================
# CONFIG
# =========================================================
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()
ENABLE_LIVE_TRADING = os.getenv("ENABLE_LIVE_TRADING", "false").lower() == "true"
ALLOW_FORMING_SIGNALS = os.getenv("ALLOW_FORMING_SIGNALS", "false").lower() == "true"
BROKER_NAME = os.getenv("BROKER_NAME", "").strip()

processed_keys = set()


# =========================================================
# HELPERS
# =========================================================
def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def validate_payload(data):
    required_fields = [
        "symbol",
        "action",
        "side",
        "price",
        "entry",
        "stop_loss",
        "take_profit",
        "timeframe",
        "timestamp",
    ]

    for field in required_fields:
        if field not in data:
            return f"Missing field: {field}"

    allowed_actions = {
        "ICC_BUY",
        "ICC_SELL",
        "ICC_BUY_FORMING",
        "ICC_SELL_FORMING",
        "NO_TRADE",
    }

    allowed_sides = {"BUY", "SELL", "NONE"}

    if data["action"] not in allowed_actions:
        return f"Invalid action: {data['action']}"

    if data["side"] not in allowed_sides:
        return f"Invalid side: {data['side']}"

    return None


def validate_trade_levels(data):
    action = data["action"]
    side = data["side"]

    if action == "NO_TRADE":
        return None

    if action in {"ICC_BUY_FORMING", "ICC_SELL_FORMING"}:
        return None

    entry = float(data["entry"])
    stop_loss = float(data["stop_loss"])
    take_profit = float(data["take_profit"])

    if side == "BUY":
        if not (stop_loss < entry < take_profit):
            return f"Invalid BUY levels: stop_loss={stop_loss}, entry={entry}, take_profit={take_profit}"

    elif side == "SELL":
        if not (take_profit < entry < stop_loss):
            return f"Invalid SELL levels: take_profit={take_profit}, entry={entry}, stop_loss={stop_loss}"

    return None


def dedupe_key(data):
    return f"{data['symbol']}|{data['timeframe']}|{data['timestamp']}|{data['action']}"


def place_trade_with_broker(data):
    """
    Placeholder broker logic.
    Replace later with OANDA / Tradovate / etc.
    """
    if not ENABLE_LIVE_TRADING:
        logger.info("LIVE TRADING DISABLED | Simulating trade.")
        return {
            "status": "simulated",
            "broker": BROKER_NAME or "none",
            "symbol": data["symbol"],
            "action": data["action"],
            "side": data["side"],
            "entry": data["entry"],
            "stop_loss": data["stop_loss"],
            "take_profit": data["take_profit"],
            "timestamp": utc_now_iso(),
        }

    logger.info("LIVE TRADING ENABLED but broker code not implemented.")
    return {
        "status": "live_placeholder",
        "broker": BROKER_NAME or "unknown",
        "symbol": data["symbol"],
        "action": data["action"],
        "side": data["side"],
        "entry": data["entry"],
        "stop_loss": data["stop_loss"],
        "take_profit": data["take_profit"],
        "timestamp": utc_now_iso(),
    }


# =========================================================
# ROUTES
# =========================================================
@app.route("/", methods=["GET"])
def root():
    return jsonify({
        "ok": True,
        "service": "icc-flask-webhook",
        "live_trading": ENABLE_LIVE_TRADING,
        "broker": BROKER_NAME or "none",
        "time": utc_now_iso(),
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "time": utc_now_iso(),
        "live_trading": ENABLE_LIVE_TRADING,
        "broker": BROKER_NAME or "none",
    })


@app.route("/version", methods=["GET"])
def version():
    return jsonify({
        "version": "icc-flask-v1"
    })


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True)

    if data is None:
        logger.error("Invalid or missing JSON body.")
        return jsonify({"ok": False, "error": "Invalid JSON"}), 400

    logger.info("Incoming webhook: %s", json.dumps(data))

    payload_error = validate_payload(data)
    if payload_error:
        logger.error("Payload validation failed: %s", payload_error)
        return jsonify({"ok": False, "error": payload_error}), 400

    if WEBHOOK_SECRET:
        if data.get("secret") != WEBHOOK_SECRET:
            logger.warning("Invalid webhook secret.")
            return jsonify({"ok": False, "error": "Invalid secret"}), 401

    key = dedupe_key(data)
    if key in processed_keys:
        logger.info("Duplicate webhook ignored: %s", key)
        return jsonify({
            "ok": True,
            "status": "duplicate_ignored",
            "action": data["action"],
            "symbol": data["symbol"],
        }), 200

    levels_error = validate_trade_levels(data)
    if levels_error:
        logger.error("Trade level validation failed: %s", levels_error)
        return jsonify({"ok": False, "error": levels_error}), 400

    # Accept heartbeat safely
    if data["action"] == "NO_TRADE":
        processed_keys.add(key)
        logger.info("NO_TRADE heartbeat accepted.")
        return jsonify({
            "ok": True,
            "status": "heartbeat_accepted",
            "action": data["action"],
            "symbol": data["symbol"],
            "side": data["side"],
        }), 200

    # Accept forming signal safely
    if data["action"] in {"ICC_BUY_FORMING", "ICC_SELL_FORMING"} and not ALLOW_FORMING_SIGNALS:
        processed_keys.add(key)
        logger.info("Forming signal logged but not traded.")
        return jsonify({
            "ok": True,
            "status": "forming_signal_logged",
            "action": data["action"],
            "symbol": data["symbol"],
            "side": data["side"],
        }), 200

    # Real trade execution
    broker_result = place_trade_with_broker(data)
    processed_keys.add(key)

    logger.info("Trade processed successfully.")

    return jsonify({
        "ok": True,
        "status": "trade_processed",
        "action": data["action"],
        "symbol": data["symbol"],
        "side": data["side"],
        "broker_result": broker_result,
    }), 200


# =========================================================
# LOCAL RUN
# =========================================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
