#!/usr/bin/env python3
"""
Trading Bot CLI — entry point.

Usage examples:
  # Market BUY
  python cli.py place --symbol BTCUSDT --side BUY --type MARKET --qty 0.01

  # Limit SELL
  python cli.py place --symbol ETHUSDT --side SELL --type LIMIT --qty 0.1 --price 3500

  # Stop-Market BUY (bonus order type)
  python cli.py place --symbol BTCUSDT --side BUY --type STOP_MARKET --qty 0.01 --stop-price 65000

  # Account info
  python cli.py account

  # Open orders
  python cli.py open-orders --symbol BTCUSDT
"""

from __future__ import annotations

import os
import sys
import argparse
import textwrap
from decimal import Decimal
from typing import Optional

# Ensure the project root is on the path when running as a script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.logging_config import setup_logging, get_logger
from bot.client import BinanceFuturesClient, BinanceAPIError, BinanceAuthError, BinanceNetworkError
from bot.validators import validate_all, validate_symbol
from bot.orders import place_order, OrderResult

# ── Colour helpers (graceful degradation on Windows) ────────────────────────
try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    _COLOURS = True
except ImportError:
    _COLOURS = False

    class _NoColour:
        def __getattr__(self, _): return ""

    Fore = Style = _NoColour()


def green(text: str) -> str:
    return f"{Fore.GREEN}{text}{Style.RESET_ALL}" if _COLOURS else text

def red(text: str) -> str:
    return f"{Fore.RED}{text}{Style.RESET_ALL}" if _COLOURS else text

def yellow(text: str) -> str:
    return f"{Fore.YELLOW}{text}{Style.RESET_ALL}" if _COLOURS else text

def cyan(text: str) -> str:
    return f"{Fore.CYAN}{text}{Style.RESET_ALL}" if _COLOURS else text

def bold(text: str) -> str:
    return f"{Style.BRIGHT}{text}{Style.RESET_ALL}" if _COLOURS else text


# ── Output helpers ───────────────────────────────────────────────────────────

DIVIDER = "─" * 60


def _print_order_request(symbol, side, order_type, qty, price=None, stop_price=None):
    """Print a formatted order request summary."""
    print()
    print(bold("  ORDER REQUEST SUMMARY"))
    print(f"  {DIVIDER}")
    print(f"  Symbol     : {cyan(symbol)}")
    print(f"  Side       : {green(side) if side == 'BUY' else red(side)}")
    print(f"  Type       : {yellow(order_type)}")
    print(f"  Quantity   : {qty}")
    if price:
        print(f"  Price      : {price}")
    if stop_price:
        print(f"  Stop Price : {stop_price}")
    print(f"  {DIVIDER}")


def _print_order_result(result: OrderResult):
    """Print a formatted order response."""
    status_fmt = green(result.status) if result.is_filled() else yellow(result.status)

    print()
    print(bold("  ORDER RESPONSE"))
    print(f"  {DIVIDER}")
    print(f"  Order ID        : {bold(str(result.order_id))}")
    print(f"  Client Order ID : {result.client_order_id}")
    print(f"  Symbol          : {result.symbol}")
    print(f"  Side            : {green(result.side) if result.side == 'BUY' else red(result.side)}")
    print(f"  Type            : {result.order_type}")
    print(f"  Status          : {status_fmt}")
    print(f"  Original Qty    : {result.orig_qty}")
    print(f"  Executed Qty    : {result.executed_qty}")
    if result.avg_price and result.avg_price != "0":
        print(f"  Avg Fill Price  : {result.avg_price}")
    if result.price and result.price != "0":
        print(f"  Limit Price     : {result.price}")
    if result.time_in_force:
        print(f"  Time in Force   : {result.time_in_force}")
    print(f"  {DIVIDER}")
    print()

    if result.is_filled():
        print(green("  ✓ Order FILLED successfully!"))
    elif result.is_open():
        print(yellow(f"  ⏳ Order is {result.status} — awaiting fill."))
    else:
        print(yellow(f"  ℹ Order status: {result.status}"))
    print()


def _print_error(message: str):
    print()
    print(red(f"  ✗ ERROR: {message}"))
    print()


# ── Client factory ───────────────────────────────────────────────────────────

def _build_client(args) -> BinanceFuturesClient:
    """
    Build the API client from CLI flags or environment variables.
    Priority: CLI flags > environment variables.
    """
    api_key = getattr(args, "api_key", None) or os.environ.get("BINANCE_API_KEY", "")
    api_secret = getattr(args, "api_secret", None) or os.environ.get("BINANCE_API_SECRET", "")

    if not api_key or not api_secret:
        _print_error(
            "API credentials not found.\n"
            "  Set --api-key / --api-secret flags, or export:\n"
            "    BINANCE_API_KEY=<key>\n"
            "    BINANCE_API_SECRET=<secret>"
        )
        sys.exit(1)

    return BinanceFuturesClient(api_key=api_key, api_secret=api_secret)


# ── Sub-command handlers ─────────────────────────────────────────────────────

def cmd_place(args):
    """Handle the 'place' sub-command."""
    logger = get_logger("cli.place")

    # ── Validate inputs ──────────────────────────────────────────────────────
    try:
        params = validate_all(
            symbol=args.symbol,
            side=args.side,
            order_type=args.type,
            quantity=args.qty,
            price=args.price,
            stop_price=args.stop_price,
        )
    except ValueError as exc:
        _print_error(str(exc))
        logger.warning("Validation failed: %s", exc)
        sys.exit(1)

    # ── Print request summary ────────────────────────────────────────────────
    _print_order_request(
        symbol=params["symbol"],
        side=params["side"],
        order_type=params["order_type"],
        qty=params["quantity"],
        price=params.get("price"),
        stop_price=params.get("stop_price"),
    )

    # ── Build client and place order ─────────────────────────────────────────
    client = _build_client(args)

    try:
        result = place_order(
            client=client,
            symbol=params["symbol"],
            side=params["side"],
            order_type=params["order_type"],
            quantity=params["quantity"],
            price=params.get("price"),
            stop_price=params.get("stop_price"),
            time_in_force=args.tif or "GTC",
            reduce_only=args.reduce_only,
        )
    except BinanceAuthError as exc:
        _print_error(f"Authentication failed — check your API key/secret.\n  Detail: {exc}")
        sys.exit(1)
    except BinanceAPIError as exc:
        _print_error(f"Exchange rejected the order.\n  Code: {exc.code}  Message: {exc.message}")
        sys.exit(1)
    except BinanceNetworkError as exc:
        _print_error(f"Network error — is the testnet reachable?\n  Detail: {exc}")
        sys.exit(1)

    _print_order_result(result)


def cmd_account(args):
    """Handle the 'account' sub-command."""
    client = _build_client(args)
    try:
        data = client.get_account()
    except (BinanceAPIError, BinanceNetworkError) as exc:
        _print_error(str(exc))
        sys.exit(1)

    print()
    print(bold("  ACCOUNT INFO"))
    print(f"  {DIVIDER}")
    total_wb = data.get("totalWalletBalance", "N/A")
    avail_bal = data.get("availableBalance", "N/A")
    total_pnl = data.get("totalUnrealizedProfit", "N/A")
    print(f"  Total Wallet Balance    : {cyan(total_wb)} USDT")
    print(f"  Available Balance       : {cyan(avail_bal)} USDT")
    print(f"  Unrealised PnL          : {total_pnl} USDT")

    positions = [p for p in data.get("positions", []) if float(p.get("positionAmt", 0)) != 0]
    if positions:
        print(f"\n  {bold('Open Positions')}")
        for pos in positions:
            print(
                f"    {pos['symbol']:12s}  amt={pos['positionAmt']:>12s}"
                f"  entry={pos.get('entryPrice','?'):>12s}"
                f"  pnl={pos.get('unrealizedProfit','?')}"
            )
    print(f"  {DIVIDER}")
    print()


def cmd_open_orders(args):
    """Handle the 'open-orders' sub-command."""
    client = _build_client(args)
    symbol = None
    if args.symbol:
        try:
            symbol = validate_symbol(args.symbol)
        except ValueError as exc:
            _print_error(str(exc))
            sys.exit(1)

    try:
        orders = client.get_open_orders(symbol=symbol)
    except (BinanceAPIError, BinanceNetworkError) as exc:
        _print_error(str(exc))
        sys.exit(1)

    print()
    print(bold(f"  OPEN ORDERS{' — ' + symbol if symbol else ''}"))
    print(f"  {DIVIDER}")
    if not orders:
        print("  No open orders.")
    else:
        for o in orders:
            side_fmt = green(o["side"]) if o["side"] == "BUY" else red(o["side"])
            print(
                f"  [{o['orderId']}]  {o['symbol']:12s}  {side_fmt}  "
                f"{o['type']:12s}  qty={o.get('origQty','?')}  "
                f"price={o.get('price','?')}  status={o.get('status','?')}"
            )
    print(f"  {DIVIDER}")
    print()


# ── Argument parser ──────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trading_bot",
        description=textwrap.dedent("""\
            Binance Futures Testnet Trading Bot
            ────────────────────────────────────
            Place market, limit, and stop-market orders on the
            Binance USDT-M Futures testnet.
        """),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # ── Global flags ─────────────────────────────────────────────────────────
    parser.add_argument(
        "--api-key",
        dest="api_key",
        metavar="KEY",
        help="Binance API key (or set BINANCE_API_KEY env var).",
    )
    parser.add_argument(
        "--api-secret",
        dest="api_secret",
        metavar="SECRET",
        help="Binance API secret (or set BINANCE_API_SECRET env var).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="File log level (default: INFO).",
    )

    sub = parser.add_subparsers(dest="command", title="commands")
    sub.required = True

    # ── place ────────────────────────────────────────────────────────────────
    place = sub.add_parser(
        "place",
        help="Place a new futures order.",
        description=textwrap.dedent("""\
            Place a MARKET, LIMIT, or STOP_MARKET order.

            Examples:
              Market BUY  0.01 BTC:
                python cli.py place --symbol BTCUSDT --side BUY --type MARKET --qty 0.01

              Limit SELL  0.1 ETH @ 3500:
                python cli.py place --symbol ETHUSDT --side SELL --type LIMIT --qty 0.1 --price 3500

              Stop-Market BUY (trigger @ 65000):
                python cli.py place --symbol BTCUSDT --side BUY --type STOP_MARKET --qty 0.01 --stop-price 65000
        """),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    place.add_argument("--symbol", required=True, help="Trading pair, e.g. BTCUSDT.")
    place.add_argument(
        "--side", required=True, choices=["BUY", "SELL"],
        type=str.upper, help="Order side: BUY or SELL."
    )
    place.add_argument(
        "--type", required=True,
        choices=["MARKET", "LIMIT", "STOP_MARKET"],
        type=str.upper,
        dest="type",
        help="Order type.",
    )
    place.add_argument("--qty", required=True, type=str, help="Order quantity.")
    place.add_argument(
        "--price", type=str, default=None,
        help="Limit price (required for LIMIT orders)."
    )
    place.add_argument(
        "--stop-price", dest="stop_price", type=str, default=None,
        help="Stop price (required for STOP_MARKET orders)."
    )
    place.add_argument(
        "--tif", default="GTC",
        choices=["GTC", "IOC", "FOK"],
        help="Time-in-force for LIMIT orders (default: GTC)."
    )
    place.add_argument(
        "--reduce-only", dest="reduce_only", action="store_true",
        help="Place a reduce-only order."
    )
    place.set_defaults(func=cmd_place)

    # ── account ───────────────────────────────────────────────────────────────
    acct = sub.add_parser("account", help="Show account balances and open positions.")
    acct.set_defaults(func=cmd_account)

    # ── open-orders ──────────────────────────────────────────────────────────
    oo = sub.add_parser("open-orders", help="List open orders.")
    oo.add_argument("--symbol", default=None, help="Filter by symbol (optional).")
    oo.set_defaults(func=cmd_open_orders)

    return parser


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = build_parser()
    args = parser.parse_args()

    setup_logging(log_level=args.log_level)
    logger = get_logger("cli")
    logger.info("CLI invoked with command=%s", args.command)

    try:
        args.func(args)
    except KeyboardInterrupt:
        print(yellow("\n  Interrupted by user."))
        sys.exit(0)


if __name__ == "__main__":
    main()
