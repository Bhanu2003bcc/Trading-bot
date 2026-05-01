"""
Order placement logic — sits between the CLI and the raw API client.

Responsibilities:
  - Convert validated Decimal inputs to exchange-compatible strings
  - Call client.new_order()
  - Parse and return a clean OrderResult dataclass
  - Re-raise client exceptions with context-enriched messages
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .client import BinanceFuturesClient, BinanceAPIError, BinanceNetworkError
from .logging_config import get_logger

logger = get_logger("bot.orders")


@dataclass
class OrderResult:
    """Parsed, human-friendly representation of an exchange order response."""

    order_id: int
    client_order_id: str
    symbol: str
    side: str
    order_type: str
    status: str
    orig_qty: str
    executed_qty: str
    avg_price: str
    price: str                        # limit price if any
    time_in_force: str
    raw: dict = field(repr=False)     # full raw exchange response

    @classmethod
    def from_response(cls, data: dict) -> "OrderResult":
        return cls(
            order_id=data.get("orderId", 0),
            client_order_id=data.get("clientOrderId", ""),
            symbol=data.get("symbol", ""),
            side=data.get("side", ""),
            order_type=data.get("type", ""),
            status=data.get("status", ""),
            orig_qty=data.get("origQty", "0"),
            executed_qty=data.get("executedQty", "0"),
            avg_price=data.get("avgPrice", "0"),
            price=data.get("price", "0"),
            time_in_force=data.get("timeInForce", ""),
            raw=data,
        )

    def is_filled(self) -> bool:
        return self.status == "FILLED"

    def is_open(self) -> bool:
        return self.status in {"NEW", "PARTIALLY_FILLED"}


def _format_decimal(value: Decimal) -> str:
    """
    Convert Decimal to a string without scientific notation,
    stripping unnecessary trailing zeros.
    """
    formatted = f"{value:f}"
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return formatted


def place_order(
    client: BinanceFuturesClient,
    symbol: str,
    side: str,
    order_type: str,
    quantity: Decimal,
    price: Optional[Decimal] = None,
    stop_price: Optional[Decimal] = None,
    time_in_force: str = "GTC",
    reduce_only: bool = False,
) -> OrderResult:
    """
    High-level order placement.

    Args:
        client:         Authenticated BinanceFuturesClient instance
        symbol:         E.g. "BTCUSDT"
        side:           "BUY" or "SELL"
        order_type:     "MARKET", "LIMIT", or "STOP_MARKET"
        quantity:       Validated Decimal quantity
        price:          Validated Decimal price (LIMIT only)
        stop_price:     Validated Decimal stop price (STOP_MARKET only)
        time_in_force:  "GTC", "IOC", or "FOK"
        reduce_only:    Reduce-only flag

    Returns:
        OrderResult dataclass

    Raises:
        BinanceAPIError, BinanceNetworkError — propagated from the client layer
    """
    qty_str = _format_decimal(quantity)
    price_str = _format_decimal(price) if price is not None else None
    stop_price_str = _format_decimal(stop_price) if stop_price is not None else None

    logger.info(
        "Placing order  symbol=%s side=%s type=%s qty=%s price=%s stop=%s",
        symbol, side, order_type, qty_str, price_str, stop_price_str,
    )

    try:
        response = client.new_order(
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=qty_str,
            price=price_str,
            stop_price=stop_price_str,
            time_in_force=time_in_force,
            reduce_only=reduce_only,
        )
    except BinanceAPIError as exc:
        logger.error(
            "Order placement failed  code=%s  msg=%s  symbol=%s side=%s type=%s",
            exc.code, exc.message, symbol, side, order_type,
        )
        raise
    except BinanceNetworkError as exc:
        logger.error("Network failure during order placement: %s", exc)
        raise

    result = OrderResult.from_response(response)
    logger.info(
        "Order placed successfully  orderId=%s  status=%s  executedQty=%s  avgPrice=%s",
        result.order_id, result.status, result.executed_qty, result.avg_price,
    )
    return result
