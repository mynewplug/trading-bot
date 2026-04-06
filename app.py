import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Literal, Dict, Any, Set

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError


# =========================================================
# LOGGING
# =========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("icc-webhook")


# =========================================================
# APP
# =========================================================
app = FastAPI(title="ICC TradingView Webhook Bot")


# =========================================================
# ENV / CONFIG
# =========================================================
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()
ENABLE_LIVE_TRADING = os.getenv("ENABLE_LIVE_TRADING", "false").lower() == "true"
ALLOW_FORMING_SIGNALS = os.getenv("ALLOW_FORMING_SIGNALS", "false").lower() == "true"
MAX_RISK_PER_TRADE = float(os.getenv("MAX_RISK_PER_TRADE", "0.0"))  # optional
PORT = int(os.getenv("PORT", "8000"))

# Optional broker env vars for future use
BROKER_NAME = os.getenv("BROKER_NAME", "").strip()   # e.g. OANDA
BROKER_API_KEY = os.getenv("BROKER_API_KEY", "").strip()
BROKER_ACCOUNT_ID = os.getenv("BROKER_ACCOUNT_ID", "").strip()
BROKER_ENV = os.getenv("BROKER_ENV", "practice").strip()


# =========================================================
# MEMORY / SIMPLE DUPLICATE PROTECTION
# =========================================================
processed_keys: Set[str] = set()


# =========================================================
# MODELS
# =========================================================
AllowedAction = Literal[
    "ICC_BUY",
    "ICC_SELL",
    "ICC_BUY_FORMING",
    "ICC_SELL_FORMING",
    "NO_TRADE"
]

AllowedSide = Literal["BUY", "SELL", "NONE"]


class WebhookPayload(BaseModel):
    symbol: str = Field(..., min_length=1)
    action: AllowedAction
    side: AllowedSide
    price: float
    entry: float
    stop_loss: float
    take_profit: float
    timeframe: str
    timestamp: str
    secret: Optional[str] = None

    def dedupe_key(self) -> str:
        return f"{self.symbol}|{self.timeframe}|{self.timestamp}|{self.action}"


# =========================================================
# HELPERS
# =========================================================
def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception as exc:
        raise ValueError(f"Could not convert to float: {value}") from exc


def validate_trade_levels(payload: WebhookPayload) -> None:
    """
    Validate only real trade signals.
    NO_TRADE and FORMING signals do not require full trade validation.
    """
    if payload.action == "NO_TRADE":
        return

    if payload.action in {"ICC_BUY_FORMING", "ICC_SELL_FORMING"}:
        return

    if payload.side == "BUY":
        if not (payload.stop_loss < payload.entry < payload.take_profit):
            raise ValueError(
                f"Invalid BUY levels. Expected stop_loss < entry < take_profit, "
                f"got stop_loss={payload.stop_loss}, entry={payload.entry}, take_profit={payload.take_profit}"
            )

    elif payload.side == "SELL":
        if not (payload.take_profit < payload.entry < payload.stop_loss):
            raise ValueError(
                f"Invalid SELL levels. Expected take_profit < entry < stop_loss, "
                f"got take_profit={payload.take_profit}, entry={payload.entry}, stop_loss={payload.stop_loss}"
            )


def should_trade(payload: WebhookPayload) -> bool:
    if payload.action in {"ICC_BUY", "ICC_SELL"}:
        return True

    if payload.action in {"ICC_BUY_FORMING", "ICC_SELL_FORMING"}:
        return ALLOW_FORMING_SIGNALS

    return False


def log_payload(payload: WebhookPayload) -> None:
    logger.info(
        "Webhook received | symbol=%s action=%s side=%s timeframe=%s entry=%s sl=%s tp=%s ts=%s",
        payload.symbol,
        payload.action,
        payload.side,
        payload.timeframe,
        payload.entry,
        payload.stop_loss,
        payload.take_profit,
        payload.timestamp,
    )


# =========================================================
# BROKER EXECUTION PLACEHOLDER
# =========================================================
def place_trade_with_broker(payload: WebhookPayload) -> Dict[str, Any]:
    """
    Replace this function with your actual broker logic.
    Right now it only returns a simulated success response.

    If you later want OANDA, Tradovate, etc., I’ll rewrite this whole block.
    """
    if not ENABLE_LIVE_TRADING:
        logger.info("LIVE TRADING DISABLED | Simulating trade only.")
        return {
            "status": "simulated",
            "broker": BROKER_NAME or "none",
            "symbol": payload.symbol,
            "action": payload.action,
            "side": payload.side,
            "entry": payload.entry,
            "stop_loss": payload.stop_loss,
            "take_profit": payload.take_profit,
            "timestamp": utc_now_iso(),
        }

    # -------------------------------
    # PUT YOUR LIVE BROKER CODE HERE
    # -------------------------------
    #
    # Example structure:
    # if BROKER_NAME == "OANDA":
    #     return place_oanda_trade(payload)
    #
    # elif BROKER_NAME == "TRADOVATE":
    #     return place_tradovate_trade(payload)
    #
    # else:
    #     raise RuntimeError("Unsupported broker")
    #
    # For now, we simulate:
    logger.info("LIVE TRADING ENABLED but broker function not yet implemented.")
    return {
        "status": "live_placeholder",
        "broker": BROKER_NAME or "unknown",
        "symbol": payload.symbol,
        "action": payload.action,
        "side": payload.side,
        "entry": payload.entry,
        "stop_loss": payload.stop_loss,
        "take_profit": payload.take_profit,
        "timestamp": utc_now_iso(),
    }


# =========================================================
# ROUTES
# =========================================================
@app.get("/")
async def root() -> Dict[str, Any]:
    return {
        "ok": True,
        "service": "icc-webhook-bot",
        "live_trading": ENABLE_LIVE_TRADING,
        "broker": BROKER_NAME or "none",
        "time": utc_now_iso(),
    }


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "time": utc_now_iso(),
        "live_trading": ENABLE_LIVE_TRADING,
        "broker": BROKER_NAME or "none",
    }


@app.post("/webhook")
async def webhook(request: Request) -> JSONResponse:
    raw_body = await request.body()

    try:
        incoming = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        logger.error("Invalid JSON received: %s", raw_body)
        raise HTTPException(status_code=400, detail="Invalid JSON")

    try:
        payload = WebhookPayload(**incoming)
    except ValidationError as exc:
        logger.error("Payload validation error: %s | payload=%s", exc, incoming)
        raise HTTPException(status_code=400, detail=exc.errors())

    # Optional secret check
    if WEBHOOK_SECRET:
        if payload.secret != WEBHOOK_SECRET:
            logger.warning("Unauthorized webhook attempt for symbol=%s", payload.symbol)
            raise HTTPException(status_code=401, detail="Invalid secret")

    # Duplicate bar/action protection
    dedupe_key = payload.dedupe_key()
    if dedupe_key in processed_keys:
        logger.info("Duplicate webhook ignored | %s", dedupe_key)
        return JSONResponse(
            status_code=200,
            content={
                "ok": True,
                "status": "duplicate_ignored",
                "action": payload.action,
                "symbol": payload.symbol,
                "timestamp": payload.timestamp,
            },
        )

    log_payload(payload)

    # Validate only when needed
    try:
        validate_trade_levels(payload)
    except ValueError as exc:
        logger.error("Trade level validation failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))

    # Handle NO_TRADE heartbeat safely
    if payload.action == "NO_TRADE":
        processed_keys.add(dedupe_key)
        logger.info("Heartbeat accepted | symbol=%s timeframe=%s", payload.symbol, payload.timeframe)
        return JSONResponse(
            status_code=200,
            content={
                "ok": True,
                "status": "heartbeat_accepted",
                "action": payload.action,
                "symbol": payload.symbol,
                "side": payload.side,
                "timestamp": payload.timestamp,
            },
        )

    # Handle forming signals safely
    if payload.action in {"ICC_BUY_FORMING", "ICC_SELL_FORMING"} and not ALLOW_FORMING_SIGNALS:
        processed_keys.add(dedupe_key)
        logger.info("Forming signal accepted but not traded | action=%s", payload.action)
        return JSONResponse(
            status_code=200,
            content={
                "ok": True,
                "status": "forming_signal_logged",
                "action": payload.action,
                "symbol": payload.symbol,
                "side": payload.side,
                "timestamp": payload.timestamp,
            },
        )

    # Real trade signal
    if should_trade(payload):
        broker_result = place_trade_with_broker(payload)
        processed_keys.add(dedupe_key)

        logger.info("Trade processed | result=%s", broker_result)

        return JSONResponse(
            status_code=200,
            content={
                "ok": True,
                "status": "trade_processed",
                "action": payload.action,
                "symbol": payload.symbol,
                "side": payload.side,
                "broker_result": broker_result,
            },
        )

    processed_keys.add(dedupe_key)
    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "status": "accepted_no_execution",
            "action": payload.action,
            "symbol": payload.symbol,
            "side": payload.side,
        },
    )
