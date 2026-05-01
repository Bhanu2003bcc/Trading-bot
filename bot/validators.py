"""
Input validation helpers for the trading bot CLI.
All validation raises ValueError with a human-readable message.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional


VALID_SIDES = {"BUY", "SELL"}
VALID_ORDER_TYPES = {"MARKET", "LIMIT", "STOP_MARKET"}

# Conservative sanity-check limits (not exchange limits)
MIN_QUANTITY = Decimal("0.001")
MAX_QUANTITY = Decimal("1_000_000")
MAX_PRICE = Decimal("10_000_000")


def validate_symbol(symbol: str) -> str:
    """
    Normalise and validate a trading symbol.

    Rules:
      - Non-empty string
      - Uppercased
      - Only alphanumeric characters
    """
    if not symbol or not symbol.strip():
        raise ValueError("Symbol cannot be empty.")
    cleaned = symbol.strip().upper()
    if not cleaned.isalnum():
        raise ValueError(
            f"Symbol '{cleaned}' contains invalid characters. "
            "Use alphanumeric only (e.g. BTCUSDT)."
        )
    return cleaned


def validate_side(side: str) -> str:
    """Validate order side. Must be BUY or SELL (case-insensitive)."""
    normalised = side.strip().upper()
    if normalised not in VALID_SIDES:
        raise ValueError(
            f"Invalid side '{side}'. Must be one of: {', '.join(sorted(VALID_SIDES))}."
        )
    return normalised


def validate_order_type(order_type: str) -> str:
    """Validate order type. Must be MARKET, LIMIT, or STOP_MARKET."""
    normalised = order_type.strip().upper()
    if normalised not in VALID_ORDER_TYPES:
        raise ValueError(
            f"Invalid order type '{order_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_ORDER_TYPES))}."
        )
    return normalised


def validate_quantity(quantity: str | float) -> Decimal:
    """
    Parse and validate order quantity.

    Must be a positive number within [MIN_QUANTITY, MAX_QUANTITY].
    """
    try:
        qty = Decimal(str(quantity))
    except InvalidOperation:
        raise ValueError(f"Quantity '{quantity}' is not a valid number.")

    if qty <= 0:
        raise ValueError(f"Quantity must be positive, got {qty}.")
    if qty < MIN_QUANTITY:
        raise ValueError(f"Quantity {qty} is below minimum allowed ({MIN_QUANTITY}).")
    if qty > MAX_QUANTITY:
        raise ValueError(f"Quantity {qty} exceeds maximum allowed ({MAX_QUANTITY}).")
    return qty


def validate_price(price: Optional[str | float], order_type: str) -> Optional[Decimal]:
    """
    Parse and validate a limit price.

    - Required for LIMIT and STOP_MARKET orders.
    - Must be positive and within bounds.
    - Should be None / omitted for MARKET orders.
    """
    if order_type in {"LIMIT", "STOP_MARKET"}:
        if price is None:
            raise ValueError(f"Price is required for {order_type} orders.")
        try:
            p = Decimal(str(price))
        except InvalidOperation:
            raise ValueError(f"Price '{price}' is not a valid number.")
        if p <= 0:
            raise ValueError(f"Price must be positive, got {p}.")
        if p > MAX_PRICE:
            raise ValueError(f"Price {p} exceeds maximum sanity limit ({MAX_PRICE}).")
        return p

    # MARKET order — price should not be provided
    if price is not None:
        raise ValueError("Price should not be specified for MARKET orders.")
    return None


def validate_stop_price(stop_price: Optional[str | float], order_type: str) -> Optional[Decimal]:
    """Validate stop price for STOP_MARKET orders."""
    if order_type == "STOP_MARKET":
        if stop_price is None:
            raise ValueError("--stop-price is required for STOP_MARKET orders.")
        try:
            sp = Decimal(str(stop_price))
        except InvalidOperation:
            raise ValueError(f"Stop price '{stop_price}' is not a valid number.")
        if sp <= 0:
            raise ValueError(f"Stop price must be positive, got {sp}.")
        return sp
    return None


def validate_all(
    symbol: str,
    side: str,
    order_type: str,
    quantity: str | float,
    price: Optional[str | float] = None,
    stop_price: Optional[str | float] = None,
) -> dict:
    """
    Run all validations and return a clean params dict.

    Raises ValueError on the first validation failure encountered.
    """
    return {
        "symbol": validate_symbol(symbol),
        "side": validate_side(side),
        "order_type": validate_order_type(order_type),
        "quantity": validate_quantity(quantity),
        "price": validate_price(price, order_type.strip().upper()),
        "stop_price": validate_stop_price(stop_price, order_type.strip().upper()),
    }
