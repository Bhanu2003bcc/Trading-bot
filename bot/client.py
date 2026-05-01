"""
Binance Futures Testnet REST client.

Handles:
  - HMAC-SHA256 request signing
  - Timestamping / recvWindow
  - HTTP error mapping to typed exceptions
  - Structured logging of every request/response
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any, Optional
from urllib.parse import urlencode

import requests

from .logging_config import get_logger

logger = get_logger("bot.client")

# ── Constants ────────────────────────────────────────────────────────────────
BASE_URL = "https://testnet.binancefuture.com"
RECV_WINDOW = 5_000          # ms – tight window to catch clock drift early
DEFAULT_TIMEOUT = 10         # seconds


# ── Custom exceptions ────────────────────────────────────────────────────────

class BinanceAPIError(Exception):
    """Raised when the Binance API returns a non-2xx status or error payload."""

    def __init__(self, code: int, message: str, http_status: int = 0):
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(f"[{code}] {message}")


class BinanceNetworkError(Exception):
    """Raised on network-level failures (timeout, connection refused, etc.)."""


class BinanceAuthError(BinanceAPIError):
    """Raised specifically for authentication / signature failures."""


# ── Client ───────────────────────────────────────────────────────────────────

class BinanceFuturesClient:
    """
    Thin wrapper around the Binance USDT-M Futures REST API.

    Usage:
        client = BinanceFuturesClient(api_key="...", api_secret="...")
        order = client.new_order(symbol="BTCUSDT", side="BUY", ...)
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        if not api_key or not api_secret:
            raise ValueError("api_key and api_secret must not be empty.")
        self._api_key = api_key
        self._api_secret = api_secret.encode()
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "X-MBX-APIKEY": self._api_key,
                "Content-Type": "application/x-www-form-urlencoded",
            }
        )
        logger.info("BinanceFuturesClient initialised. base_url=%s", self._base_url)

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _sign(self, params: dict) -> dict:
        """Append timestamp + recvWindow, then add HMAC-SHA256 signature."""
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = RECV_WINDOW
        query_string = urlencode(params)
        signature = hmac.new(
            self._api_secret,
            query_string.encode(),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = signature
        return params

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        signed: bool = True,
    ) -> Any:
        """
        Execute an HTTP request, sign if required, log everything,
        and translate HTTP / API errors into typed exceptions.
        """
        params = params or {}
        if signed:
            params = self._sign(params)

        url = f"{self._base_url}{endpoint}"
        log_params = {k: v for k, v in params.items() if k != "signature"}
        logger.info("→ %s %s  params=%s", method.upper(), endpoint, log_params)

        try:
            response = self._session.request(
                method,
                url,
                params=params if method.upper() == "GET" else None,
                data=params if method.upper() == "POST" else None,
                timeout=self._timeout,
            )
        except requests.exceptions.Timeout as exc:
            logger.error("Request timed out: %s %s", method, endpoint)
            raise BinanceNetworkError(f"Request timed out after {self._timeout}s.") from exc
        except requests.exceptions.ConnectionError as exc:
            logger.error("Connection error: %s", exc)
            raise BinanceNetworkError(f"Cannot connect to {self._base_url}.") from exc
        except requests.exceptions.RequestException as exc:
            logger.error("Unexpected network error: %s", exc)
            raise BinanceNetworkError(str(exc)) from exc

        logger.info(
            "← HTTP %s  url=%s  body=%s",
            response.status_code,
            response.url,
            response.text[:500],
        )

        # Parse JSON (Binance always returns JSON, even for errors)
        try:
            data = response.json()
        except ValueError:
            logger.error("Non-JSON response: %s", response.text[:200])
            response.raise_for_status()
            return response.text

        # Handle Binance application-level errors
        if isinstance(data, dict) and "code" in data and data["code"] != 200:
            code = data.get("code", -1)
            msg = data.get("msg", "Unknown error")
            logger.error("Binance API error  code=%s  msg=%s", code, msg)
            if code in (-2014, -2015, -1022):
                raise BinanceAuthError(code, msg, http_status=response.status_code)
            raise BinanceAPIError(code, msg, http_status=response.status_code)

        # Handle HTTP errors that didn't return a JSON error body
        if not response.ok:
            logger.error("HTTP error %s: %s", response.status_code, response.text[:200])
            raise BinanceAPIError(-1, response.text, http_status=response.status_code)

        return data

    # ── Public API methods ───────────────────────────────────────────────────

    def get_server_time(self) -> dict:
        """Check server time — useful for clock-skew debugging."""
        return self._request("GET", "/fapi/v1/time", signed=False)

    def get_exchange_info(self) -> dict:
        """Fetch exchange trading rules and symbol information."""
        return self._request("GET", "/fapi/v1/exchangeInfo", signed=False)

    def get_account(self) -> dict:
        """Fetch futures account details (balances, positions)."""
        return self._request("GET", "/fapi/v2/account")

    def new_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: str,
        price: Optional[str] = None,
        stop_price: Optional[str] = None,
        time_in_force: str = "GTC",
        reduce_only: bool = False,
    ) -> dict:
        """
        Place a new futures order.

        Args:
            symbol:        Trading pair, e.g. "BTCUSDT"
            side:          "BUY" or "SELL"
            order_type:    "MARKET", "LIMIT", or "STOP_MARKET"
            quantity:      Order quantity as a string (precision handled by caller)
            price:         Required for LIMIT orders
            stop_price:    Required for STOP_MARKET orders
            time_in_force: "GTC" (default), "IOC", "FOK" — ignored for MARKET
            reduce_only:   If True, the order only reduces an existing position

        Returns:
            Raw order response dict from the exchange.
        """
        params: dict = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": quantity,
        }

        if order_type == "LIMIT":
            if not price:
                raise ValueError("Price is required for LIMIT orders.")
            params["price"] = price
            params["timeInForce"] = time_in_force

        if order_type == "STOP_MARKET":
            if not stop_price:
                raise ValueError("stopPrice is required for STOP_MARKET orders.")
            params["stopPrice"] = stop_price

        if reduce_only:
            params["reduceOnly"] = "true"

        logger.info(
            "Placing order: symbol=%s side=%s type=%s qty=%s price=%s stopPrice=%s",
            symbol, side, order_type, quantity, price, stop_price,
        )
        return self._request("POST", "/fapi/v1/order", params=params)

    def get_open_orders(self, symbol: Optional[str] = None) -> list:
        """List open orders, optionally filtered by symbol."""
        params = {}
        if symbol:
            params["symbol"] = symbol
        return self._request("GET", "/fapi/v1/openOrders", params=params)

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        """Cancel a specific order by ID."""
        return self._request(
            "DELETE",
            "/fapi/v1/order",
            params={"symbol": symbol, "orderId": order_id},
        )
