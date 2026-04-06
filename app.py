import os
import json
import logging
from typing import Optional, Literal, Dict, Any

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field
import uvicorn

# ==========================================
# LOGGING
# ==========================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tv-webhook-bot")

# ==========================================
# ENV
# ==========================================
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "changeme")
PORT = int(os.getenv("PORT", "10000"))
BROKER_NAME = os.getenv("BROKER_NAME", "paper")
DEFAULT_QTY = int(os.getenv("DEFAULT_QTY", "1"))
ALLOW_LONGS = os.getenv("ALLOW_LONGS", "true").lower() == "true"
ALLOW_SHORTS = os.getenv("ALLOW_SHORTS", "true").lower() == "true"

# Tradovate / generic placeholders
TRADOVATE_USERNAME = os.getenv("TRADOVATE_USERNAME", "")
TRADOVATE_PASSWORD = os.getenv("TRADOVATE_PASSWORD", "")
TRADOVATE_CID = os.getenv("TRADOVATE_CID", "")
TRADOVATE_SECRET = os.getenv("TRADOVATE_SECRET", "")
TRADOVATE_ACCOUNT_ID = os.getenv("TRADOVATE_ACCOUNT_ID", "")
TRADOVATE_CONTRACT_ID = os.getenv("TRADOVATE_CONTRACT_ID", "")

# ==========================================
# APP
# ==========================================
app = FastAPI(title="TradingView Webhook Bot", version="2.0.0")

# ==========================================
# DATA MODELS
# ==========================================
class TVSignal(BaseModel):
    symbol: str
    action: Literal[
        "IMPULSE_BUY",
        "IMPULSE_SELL",
        "REVERSAL_BUY",
        "REVERSAL_SELL",
        "NO_TRADE"
    ]
    side: Literal["BUY", "SELL", "NONE"]
    price: float
    entry: float
    stop_loss: float = Field(alias="stop_loss")
    take_profit: float = Field(alias="take_profit")
    timeframe: str
    timestamp: str

class OrderResult(BaseModel):
    ok: bool
    broker: str
    detail: Dict[str, Any]

# ==========================================
# HEALTH
# ==========================================
@app.get("/")
def root():
    return {
        "ok": True,
        "service": "TradingView Webhook Bot",
        "broker": BROKER_NAME
    }

@app.get("/health")
def health():
    return {"ok": True}

# ==========================================
# HELPERS
# ==========================================
def verify_secret(x_webhook_secret: Optional[str]) -> None:
    if x_webhook_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

def side_allowed(side: str) -> bool:
    if side == "BUY" and not ALLOW_LONGS:
        return False
    if side == "SELL" and not ALLOW_SHORTS:
        return False
    return True

def normalize_qty(symbol: str, side: str) -> int:
    return DEFAULT_QTY

def build_order_payload(signal: TVSignal) -> Dict[str, Any]:
    qty = normalize_qty(signal.symbol, signal.side)
    return {
        "symbol": signal.symbol,
        "side": signal.side,
        "qty": qty,
        "entry": signal.entry,
        "stop_loss": signal.stop_loss,
        "take_profit": signal.take_profit,
        "signal_action": signal.action,
        "timeframe": signal.timeframe,
        "tv_timestamp": signal.timestamp
    }

# ==========================================
# NO TRADE HEARTBEAT HANDLER
# ==========================================
def handle_no_trade(signal: TVSignal) -> OrderResult:
    detail = {
        "message": "Heartbeat received: no trade this bar",
        "symbol": signal.symbol,
        "action": signal.action,
        "timeframe": signal.timeframe,
        "price": signal.price,
        "timestamp": signal.timestamp
    }
    logger.info("NO_TRADE HEARTBEAT: %s", json.dumps(detail))
    return OrderResult(
        ok=True,
        broker=BROKER_NAME,
        detail=detail
    )

# ==========================================
# PAPER BROKER
# ==========================================
def place_paper_order(signal: TVSignal) -> OrderResult:
    order = build_order_payload(signal)
    logger.info("PAPER ORDER: %s", json.dumps(order))
    return OrderResult(
        ok=True,
        broker="paper",
        detail={
            "message": "Paper order accepted",
            "order": order
        }
    )

# ==========================================
# TRADOVATE ADAPTER PLACEHOLDER
# Replace this section with your real API code
# ==========================================
def place_tradovate_order(signal: TVSignal) -> OrderResult:
    if not TRADOVATE_ACCOUNT_ID:
        return OrderResult(
            ok=False,
            broker="tradovate",
            detail={"message": "Missing TRADOVATE_ACCOUNT_ID env var"}
        )

    order = build_order_payload(signal)

    logger.info("TRADOVATE ORDER REQUEST: %s", json.dumps(order))

    simulated_response = {
        "message": "Tradovate adapter scaffold reached",
        "account_id": TRADOVATE_ACCOUNT_ID,
        "contract_id": TRADOVATE_CONTRACT_ID,
        "order": order
    }

    return OrderResult(
        ok=True,
        broker="tradovate",
        detail=simulated_response
    )

# ==========================================
# EXECUTOR
# ==========================================
def execute_trade(signal: TVSignal) -> OrderResult:
    if signal.action == "NO_TRADE" or signal.side == "NONE":
        return handle_no_trade(signal)

    if not side_allowed(signal.side):
        return OrderResult(
            ok=False,
            broker=BROKER_NAME,
            detail={"message": f"{signal.side} trades are disabled"}
        )

    if BROKER_NAME == "paper":
        return place_paper_order(signal)

    if BROKER_NAME == "tradovate":
        return place_tradovate_order(signal)

    return OrderResult(
        ok=False,
        broker=BROKER_NAME,
        detail={"message": f"Unsupported broker: {BROKER_NAME}"}
    )

# ==========================================
# WEBHOOK
# ==========================================
@app.post("/webhook")
async def webhook(
    request: Request,
    x_webhook_secret: Optional[str] = Header(default=None)
):
    verify_secret(x_webhook_secret)

    try:
        raw = await request.json()
    except Exception as exc:
        logger.exception("Invalid JSON")
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")

    try:
        signal = TVSignal(**raw)
    except Exception as exc:
        logger.exception("Payload validation failed")
        raise HTTPException(status_code=422, detail=f"Payload validation failed: {exc}")

    logger.info("SIGNAL RECEIVED: %s", signal.model_dump_json())

    result = execute_trade(signal)

    if not result.ok:
        logger.warning("REQUEST REJECTED: %s", result.model_dump_json())
        raise HTTPException(status_code=400, detail=result.detail)

    logger.info("REQUEST ACCEPTED: %s", result.model_dump_json())
    return result.model_dump()

# ==========================================
# MAIN
# ==========================================
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
