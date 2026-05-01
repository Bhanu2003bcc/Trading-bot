# Binance Futures Testnet Trading Bot

A clean, production-structured Python CLI for placing orders on the
**Binance USDT-M Futures Testnet**.

---

## Features

| Capability | Detail |
|---|---|
| **Order types** | MARKET, LIMIT, STOP_MARKET (bonus) |
| **Sides** | BUY and SELL |
| **CLI** | `argparse`-based, with full `--help` on every sub-command |
| **Validation** | All inputs validated before any API call is made |
| **Logging** | Rotating file log (`logs/trading_bot.log`) + console warnings |
| **Error handling** | Typed exceptions for API errors, auth failures, network issues |
| **Output** | Colour-coded request summary + parsed response table |

---

## Project Structure

```
trading_bot/
├── bot/
│   ├── __init__.py          # Package exports
│   ├── client.py            # Binance REST client (signing, requests, error mapping)
│   ├── orders.py            # Order placement logic + OrderResult dataclass
│   ├── validators.py        # Input validation (raises ValueError with clear messages)
│   └── logging_config.py   # Rotating file + console logging setup
├── tests/
│   └── test_bot.py          # Unit tests (validators, formatters, mocked client)
├── logs/                    # Created automatically on first run
├── cli.py                   # CLI entry point (argparse sub-commands)
├── requirements.txt
└── README.md
```

---

## Setup

### 1. Register a Testnet Account

1. Visit <https://testnet.binancefuture.com> and sign up.
2. Generate API credentials under **API Management**.
3. Note your **API Key** and **Secret Key**.

### 2. Install Dependencies

```bash
# Python 3.8+ required
pip install -r requirements.txt
```

Core dependency is only `requests`. `colorama` is optional (adds terminal colours).

### 3. Set Credentials

**Option A — Environment variables (recommended)**

```bash
export BINANCE_API_KEY="your_api_key_here"
export BINANCE_API_SECRET="your_api_secret_here"
```

**Option B — CLI flags**

```bash
python cli.py --api-key YOUR_KEY --api-secret YOUR_SECRET place ...
```

---

## Usage

### Place a Market Order

```bash
# BUY 0.01 BTC at market price
python cli.py place --symbol BTCUSDT --side BUY --type MARKET --qty 0.01

# SELL 0.5 ETH at market price
python cli.py place --symbol ETHUSDT --side SELL --type MARKET --qty 0.5
```

### Place a Limit Order

```bash
# BUY 0.01 BTC with a limit at $60,000
python cli.py place --symbol BTCUSDT --side BUY --type LIMIT --qty 0.01 --price 60000

# SELL 0.1 ETH with a limit at $3,500, IOC fill
python cli.py place --symbol ETHUSDT --side SELL --type LIMIT --qty 0.1 --price 3500 --tif IOC
```

### Place a Stop-Market Order *(Bonus)*

```bash
# Trigger a market BUY when BTC reaches $65,000
python cli.py place --symbol BTCUSDT --side BUY --type STOP_MARKET --qty 0.01 --stop-price 65000

# Protect a long: trigger a market SELL if BTC drops to $58,000
python cli.py place --symbol BTCUSDT --side SELL --type STOP_MARKET --qty 0.01 --stop-price 58000
```

### View Account Info

```bash
python cli.py account
```

### List Open Orders

```bash
python cli.py open-orders
python cli.py open-orders --symbol BTCUSDT
```

### Full help

```bash
python cli.py --help
python cli.py place --help
```

---

## Sample Output

```
  ORDER REQUEST SUMMARY
  ────────────────────────────────────────────────────────────
  Symbol     : BTCUSDT
  Side       : BUY
  Type       : MARKET
  Quantity   : 0.01
  ────────────────────────────────────────────────────────────

  ORDER RESPONSE
  ────────────────────────────────────────────────────────────
  Order ID        : 3847291038
  Client Order ID : web_abc123
  Symbol          : BTCUSDT
  Side            : BUY
  Type            : MARKET
  Status          : FILLED
  Original Qty    : 0.01
  Executed Qty    : 0.01
  Avg Fill Price  : 64387.50
  ────────────────────────────────────────────────────────────

  ✓ Order FILLED successfully!
```

---

## Logging

Every API request and response is logged to `logs/trading_bot.log` (rotates at 5 MB, keeps 3 backups).

```
2025-05-01 14:32:01 | INFO     | bot.client           | → POST /fapi/v1/order  params={...}
2025-05-01 14:32:01 | INFO     | bot.client           | ← HTTP 200  body={...}
2025-05-01 14:32:01 | INFO     | bot.orders           | Order placed  orderId=3847291038  status=FILLED
```

Console output is limited to **WARNING** and above to keep CLI output clean.
Adjust with `--log-level DEBUG` for full verbosity.

---

## Running Tests

```bash
# Requires pytest
pip install pytest pytest-mock
pytest tests/ -v
```

Tests cover:
- All validator functions (happy path + every error branch)
- Decimal formatting
- `OrderResult` parsing
- `place_order()` with a mocked client (success + both error types)

---

## Design Decisions

| Decision | Rationale |
|---|---|
| `requests` only (no `python-binance`) | Fewer dependencies; full visibility into signing logic |
| Typed exceptions (`BinanceAPIError`, `BinanceAuthError`, `BinanceNetworkError`) | CLI can catch the right exception and show the right message |
| `Decimal` for all monetary values | Avoids floating-point precision bugs |
| Separate `client.py` / `orders.py` / `validators.py` | Each layer has one responsibility and is independently testable |
| Console handler at WARNING only | Keeps CLI output clean; file captures full debug trail |

---

## Environment Variables

| Variable | Description |
|---|---|
| `BINANCE_API_KEY` | Your testnet API key |
| `BINANCE_API_SECRET` | Your testnet API secret |
