"""
Unit tests for validators, order formatting, and client error handling.
Run with:  pytest tests/test_bot.py -v
"""

from __future__ import annotations

import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from bot.validators import (
    validate_symbol,
    validate_side,
    validate_order_type,
    validate_quantity,
    validate_price,
    validate_all,
)
from bot.orders import _format_decimal, place_order, OrderResult
from bot.client import BinanceAPIError, BinanceNetworkError


# ── Validator tests ──────────────────────────────────────────────────────────

class TestValidateSymbol:
    def test_valid(self):
        assert validate_symbol("btcusdt") == "BTCUSDT"
        assert validate_symbol("  ethusdt  ") == "ETHUSDT"

    def test_empty(self):
        with pytest.raises(ValueError, match="empty"):
            validate_symbol("")

    def test_invalid_chars(self):
        with pytest.raises(ValueError, match="invalid characters"):
            validate_symbol("BTC-USDT")


class TestValidateSide:
    def test_buy(self):
        assert validate_side("buy") == "BUY"
        assert validate_side("BUY") == "BUY"

    def test_sell(self):
        assert validate_side("sell") == "SELL"

    def test_invalid(self):
        with pytest.raises(ValueError, match="Invalid side"):
            validate_side("LONG")


class TestValidateOrderType:
    def test_valid_types(self):
        for t in ("MARKET", "LIMIT", "STOP_MARKET"):
            assert validate_order_type(t) == t

    def test_case_insensitive(self):
        assert validate_order_type("market") == "MARKET"

    def test_invalid(self):
        with pytest.raises(ValueError, match="Invalid order type"):
            validate_order_type("OCO")


class TestValidateQuantity:
    def test_valid(self):
        assert validate_quantity("0.01") == Decimal("0.01")
        assert validate_quantity(1) == Decimal("1")

    def test_zero(self):
        with pytest.raises(ValueError, match="positive"):
            validate_quantity(0)

    def test_negative(self):
        with pytest.raises(ValueError, match="positive"):
            validate_quantity(-1)

    def test_below_min(self):
        with pytest.raises(ValueError, match="minimum"):
            validate_quantity("0.0001")

    def test_non_numeric(self):
        with pytest.raises(ValueError, match="not a valid number"):
            validate_quantity("abc")


class TestValidatePrice:
    def test_limit_requires_price(self):
        with pytest.raises(ValueError, match="required"):
            validate_price(None, "LIMIT")

    def test_market_no_price(self):
        assert validate_price(None, "MARKET") is None

    def test_market_price_error(self):
        with pytest.raises(ValueError, match="should not be specified"):
            validate_price("50000", "MARKET")

    def test_valid_limit_price(self):
        assert validate_price("65000", "LIMIT") == Decimal("65000")

    def test_zero_price(self):
        with pytest.raises(ValueError, match="positive"):
            validate_price("0", "LIMIT")


class TestValidateAll:
    def test_valid_market_order(self):
        result = validate_all("BTCUSDT", "BUY", "MARKET", "0.01")
        assert result["symbol"] == "BTCUSDT"
        assert result["side"] == "BUY"
        assert result["order_type"] == "MARKET"
        assert result["quantity"] == Decimal("0.01")
        assert result["price"] is None

    def test_valid_limit_order(self):
        result = validate_all("ETHUSDT", "SELL", "LIMIT", "0.1", price="3500")
        assert result["price"] == Decimal("3500")

    def test_limit_missing_price(self):
        with pytest.raises(ValueError, match="required"):
            validate_all("BTCUSDT", "BUY", "LIMIT", "0.01")


# ── Decimal formatting tests ─────────────────────────────────────────────────

class TestFormatDecimal:
    def test_integer_value(self):
        assert _format_decimal(Decimal("100")) == "100"

    def test_decimal_value(self):
        assert _format_decimal(Decimal("0.01")) == "0.01"

    def test_trailing_zeros_stripped(self):
        assert _format_decimal(Decimal("1.10000")) == "1.1"


# ── OrderResult tests ────────────────────────────────────────────────────────

class TestOrderResult:
    FILLED_RESPONSE = {
        "orderId": 12345,
        "clientOrderId": "abc",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "MARKET",
        "status": "FILLED",
        "origQty": "0.01",
        "executedQty": "0.01",
        "avgPrice": "65000.0",
        "price": "0",
        "timeInForce": "GTC",
    }

    def test_from_response(self):
        r = OrderResult.from_response(self.FILLED_RESPONSE)
        assert r.order_id == 12345
        assert r.is_filled()
        assert not r.is_open()

    def test_open_status(self):
        data = {**self.FILLED_RESPONSE, "status": "NEW"}
        r = OrderResult.from_response(data)
        assert r.is_open()
        assert not r.is_filled()


# ── place_order integration (mocked client) ──────────────────────────────────

class TestPlaceOrder:
    def _make_client(self, response_data):
        client = MagicMock()
        client.new_order.return_value = response_data
        return client

    def test_market_order_success(self):
        fake_response = {
            "orderId": 999,
            "clientOrderId": "x",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "MARKET",
            "status": "FILLED",
            "origQty": "0.01",
            "executedQty": "0.01",
            "avgPrice": "64000",
            "price": "0",
            "timeInForce": "GTC",
        }
        client = self._make_client(fake_response)
        result = place_order(client, "BTCUSDT", "BUY", "MARKET", Decimal("0.01"))
        assert result.order_id == 999
        assert result.status == "FILLED"
        client.new_order.assert_called_once_with(
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
            quantity="0.01",
            price=None,
            stop_price=None,
            time_in_force="GTC",
            reduce_only=False,
        )

    def test_api_error_propagates(self):
        client = MagicMock()
        client.new_order.side_effect = BinanceAPIError(-1121, "Invalid symbol.")
        with pytest.raises(BinanceAPIError, match="Invalid symbol"):
            place_order(client, "INVALID", "BUY", "MARKET", Decimal("0.01"))

    def test_network_error_propagates(self):
        client = MagicMock()
        client.new_order.side_effect = BinanceNetworkError("Connection refused.")
        with pytest.raises(BinanceNetworkError):
            place_order(client, "BTCUSDT", "BUY", "MARKET", Decimal("0.01"))
