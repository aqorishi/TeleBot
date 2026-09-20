"""
monitoring.py

Complete Bybit WebSocket + REST manager that:
- connects to private WS (order, position) and public WS (tickers),
- fetches initial positions & orders via REST,
- watches price vs TPs you set with set_symbol_tps(symbol, [tp1, tp2, ...]),
- when price crosses TP_i -> moves stopLoss accordingly (TP1 -> entry, TP2 -> TP1, ...),
- when price crosses last TP -> creates a Trailing Stop order automatically,
- when stopLoss is moved to entry (or beyond) cancels non-reduce orders for that symbol.

Usage:
- put this file next to your bot runner (or in a package),
- set API_KEY / API_SECRET (env or pass explicitly),
- create BybitRest and BybitWSManager instances from your main and call manager.start(watch_symbols)

NOTE: Test on testnet before using on real account. Improve retry/backoff and logging for production.
"""

import asyncio
import aiohttp
import websockets
import hmac
import hashlib
import time
import json
import logging
from typing import Dict, Any, List, Optional

# ---------------------------
# CONFIG / Defaults
# ---------------------------
REST_HOST = "https://apidemo.bybit.com"            # change to testnet: https://api-testnet.bybit.com
WS_PRIVATE_URL = "wss://stream.bybit.com/v5/private"
WS_PUBLIC_URL = "wss://stream.bybit.com/v5/public"
DEFAULT_TRAILING = "0.2"   # default trailing callback (e.g. percent or price depending on pair)
CATEGORY_DEFAULT = "linear"

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("monitoring")

# ---------------------------
# Helpers: sign request (Bybit v5)
# ---------------------------

def current_timestamp_ms() -> str:
    return str(int(time.time() * 1000))


def sign_v5(secret: str, timestamp: str, method: str, path: str, body: str = "") -> str:
    msg = timestamp + method.upper() + path + body
    return hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()

# ---------------------------
# REST client (aiohttp)
# ---------------------------
class BybitRest:
    def __init__(self, api_key: str, api_secret: str, rest_host: str = REST_HOST, session: Optional[aiohttp.ClientSession] = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.host = rest_host
        self._session = session or aiohttp.ClientSession()

    async def _request(self, method: str, path: str, params: Dict[str, Any] = None, json_body: Dict[str, Any] = None):
        url = self.host + path
        ts = current_timestamp_ms()
        body_str = json.dumps(json_body) if json_body else ""
        signature = sign_v5(self.api_secret, ts, method, path, body_str)
        headers = {
            "Content-Type": "application/json",
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-SIGN": signature,
            "X-BAPI-RECV-WINDOW": "5000",
        }

        log.debug("REST %s %s %s %s", method, url, params or "", body_str or "")
        async with self._session.request(method, url, params=params, json=json_body, headers=headers, timeout=20) as resp:
            text = await resp.text()
            try:
                data = json.loads(text)
            except Exception:
                log.error("Non-JSON response: %s", text)
                raise
            if resp.status != 200:
                log.error("HTTP error %s %s", resp.status, data)
                raise Exception(f"HTTP {resp.status}: {data}")
            return data

    # convenience methods for endpoints we need
    async def get_positions(self, category: str = CATEGORY_DEFAULT):
        path = "/v5/position/list"
        params = {"category": category}
        return await self._request("GET", path, params=params)

    async def get_open_orders(self, category: str = CATEGORY_DEFAULT, symbol: Optional[str] = None):
        path = "/v5/order/realtime"
        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        return await self._request("GET", path, params=params)

    async def set_trading_stop(self, category: str, symbol: str, stopLoss: Optional[str] = None, takeProfit: Optional[str] = None):
        path = "/v5/position/trading-stop"
        body: Dict[str, Any] = {"category": category, "symbol": symbol}
        if stopLoss is not None:
            body["stopLoss"] = str(stopLoss)
        if takeProfit is not None:
            body["takeProfit"] = str(takeProfit)
        return await self._request("POST", path, json_body=body)

    async def cancel_order(self, category: str, symbol: str, order_id: str):
        path = "/v5/order/cancel"
        body = {"category": category, "symbol": symbol, "orderId": order_id}
        return await self._request("POST", path, json_body=body)

    async def cancel_all_orders(self, category: str, symbol: Optional[str] = None):
        path = "/v5/order/cancel-all"
        body = {"category": category}
        if symbol:
            body["symbol"] = symbol
        return await self._request("POST", path, json_body=body)

    async def place_order(self, order_payload: Dict[str, Any]):
        path = "/v5/order/create"
        # ensure category present
        if "category" not in order_payload:
            order_payload["category"] = CATEGORY_DEFAULT
        return await self._request("POST", path, json_body=order_payload)

    async def close(self):
        await self._session.close()

# ---------------------------
# WebSocket Manager
# ---------------------------
class BybitWSManager:
    def __init__(self, api_key: str, api_secret: str, rest: BybitRest, category: str = CATEGORY_DEFAULT, default_trailing: str = DEFAULT_TRAILING):
        self.api_key = api_key
        self.api_secret = api_secret
        self.rest = rest
        self.category = category
        self.default_trailing = default_trailing

        # state
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.orders: Dict[str, Dict[str, Any]] = {}
        self.tps: Dict[str, List[float]] = {}
        self.processed_tps: Dict[str, set] = {}
        self.trailing_orders: Dict[str, Any] = {}  # symbol -> order info

        # tasks
        self._ws_private_task: Optional[asyncio.Task] = None
        self._ws_public_task: Optional[asyncio.Task] = None

    # ---------------------------
    # Public control
    # ---------------------------
    async def start(self, watch_symbols: List[str]):
        # start private & public ws tasks
        if self._ws_private_task is None or self._ws_private_task.done():
            self._ws_private_task = asyncio.create_task(self._run_private_ws())
        if self._ws_public_task is None or self._ws_public_task.done():
            self._ws_public_task = asyncio.create_task(self._run_public_ws(watch_symbols))
        log.info("WS manager started: watching %s", watch_symbols)

    async def close(self):
        log.info("Closing WS manager")
        if self._ws_private_task:
            self._ws_private_task.cancel()
        if self._ws_public_task:
            self._ws_public_task.cancel()
        await self.rest.close()

    # ---------------------------
    # Internal WS loops
    # ---------------------------
    async def _auth_private(self, ws):
        expires = int(time.time() * 1000) + 5000
        sign = hmac.new(self.api_secret.encode(), f"GET/realtime{expires}".encode(), hashlib.sha256).hexdigest()
        auth = {"op": "auth", "args": [self.api_key, expires, sign]}
        await ws.send(json.dumps(auth))
        log.info("Private WS: auth sent")

    async def _subscribe_private(self, ws):
        sub = {"op": "subscribe", "args": ["order", "position"]}
        await ws.send(json.dumps(sub))
        log.info("Private WS: subscribe sent")

    async def _subscribe_public_ticker(self, ws, symbols: List[str]):
        # subscribe to tickers.SYMBOL for each symbol
        args = [f"tickers.{s}" for s in symbols]
        if not args:
            return
        sub = {"op": "subscribe", "args": args}
        await ws.send(json.dumps(sub))
        log.info("Public WS: subscribed to tickers: %s", symbols)

    async def _run_private_ws(self):
        while True:
            try:
                async with websockets.connect(WS_PRIVATE_URL) as ws:
                    await self._auth_private(ws)
                    await asyncio.sleep(0.1)
                    await self._subscribe_private(ws)

                    async for msg in ws:
                        if not msg:
                            continue
                        data = json.loads(msg)
                        await self._handle_private_msg(data)
            except asyncio.CancelledError:
                log.info("Private WS task cancelled")
                raise
            except Exception as e:
                log.exception("Private WS error, reconnecting in 3s: %s", e)
                await asyncio.sleep(3)

    async def _run_public_ws(self, symbols: List[str]):
        while True:
            try:
                async with websockets.connect(WS_PUBLIC_URL) as ws:
                    await self._subscribe_public_ticker(ws, symbols)
                    async for msg in ws:
                        if not msg:
                            continue
                        data = json.loads(msg)
                        await self._handle_public_msg(data)
            except asyncio.CancelledError:
                log.info("Public WS task cancelled")
                raise
            except Exception as e:
                log.exception("Public WS error, reconnecting in 3s: %s", e)
                await asyncio.sleep(3)

    # ---------------------------
    # Message handlers
    # ---------------------------
    async def _handle_private_msg(self, payload: Dict[str, Any]):
        topic = payload.get("topic") or payload.get("type")
        log.debug("Private WS payload: %s", payload)
        if not topic:
            return

        if topic == "position":
            data = payload.get("data") or {}
            # data may be {list: [...]}
            if isinstance(data, dict):
                for pos in data.get("list", []):
                    await self.handle_position_update(pos)
            elif isinstance(data, list):
                for pos in data:
                    await self.handle_position_update(pos)
        elif topic == "order":
            data = payload.get("data") or {}
            if isinstance(data, dict):
                for o in data.get("list", []):
                    await self.handle_order_update(o)
            elif isinstance(data, list):
                for o in data:
                    await self.handle_order_update(o)
        else:
            log.debug("Unhandled private topic: %s", topic)

    async def _handle_public_msg(self, payload: Dict[str, Any]):
        topic = payload.get("topic")
        if not topic:
            return
        if topic.startswith("tickers."):
            arr = payload.get("data") or []
            if isinstance(arr, list):
                for t in arr:
                    await self.handle_ticker_update(t)
            elif isinstance(arr, dict):
                await self.handle_ticker_update(arr)

    # ---------------------------
    # High-level handlers
    # ---------------------------
    async def handle_order_update(self, order: Dict[str, Any]):
        oid = order.get("orderId") or order.get("orderLinkId")
        log.info("Order update: %s %s %s", oid, order.get("symbol"), order.get("orderStatus") or order.get("status"))
        if not oid:
            return
        self.orders[oid] = order

        # If order is a trigger that fired for last TP, we might need to place trailing stop
        status = (order.get("orderStatus") or order.get("status") or order.get("state") or "").lower()
        # Check if this order had a triggerPrice and matches a last TP
        trigger_price = order.get("triggerPrice") or order.get("stopPrice") or order.get("trigger_price")
        symbol = order.get("symbol")
        if trigger_price and symbol and status in ("triggered", "filled", "finished"):
            try:
                tp_val = float(trigger_price)
            except Exception:
                tp_val = None
            if tp_val and symbol in self.tps:
                tps_sorted = sorted([float(x) for x in self.tps[symbol]])
                if tps_sorted and abs(tps_sorted[-1] - tp_val) < 1e-8:
                    # last TP trigger fired -> create trailing stop if not already
                    await self._create_trailing_if_not_exists(symbol)

        # Refresh positions if important state changed
        if status in ("filled", "cancelled", "triggered", "finished"):
            await asyncio.sleep(0.2)
            await self.refresh_positions()

    async def handle_position_update(self, pos: Dict[str, Any]):
        symbol = pos.get("symbol")
        if not symbol:
            return
        self.positions[symbol] = pos
        log.info("Position update: %s %s size=%s entry=%s sl=%s",
                 symbol, pos.get("side"), pos.get("size"), pos.get("avgPrice"), pos.get("stopLoss"))

        # If stopLoss moved to entry or beyond -> cancel related orders
        await self._maybe_cancel_orders_if_sl_at_entry(pos)

    async def handle_ticker_update(self, ticker: Dict[str, Any]):
        symbol = ticker.get("symbol")
        if not symbol:
            return
        try:
            price = float(ticker.get("lastPrice") or ticker.get("last_price") or ticker.get("last") or 0)
        except Exception:
            return
        if symbol in self.tps and self.tps[symbol]:
            await self._check_price_against_tps(symbol, price)

    # ---------------------------
    # Business logic
    # ---------------------------
    async def _check_price_against_tps(self, symbol: str, price: float):
        if symbol not in self.tps:
            return
        pos = self.positions.get(symbol)
        if not pos:
            return
        side = pos.get("side")
        entry = float(pos.get("avgPrice") or 0)
        remaining_size = float(pos.get("size") or 0)
        if remaining_size <= 0:
            return

        # sort TPs appropriately
        tps_sorted = sorted([float(x) for x in self.tps[symbol]])
        triggered = []
        if side == "Buy":
            triggered = [tp for tp in tps_sorted if price >= tp]
        else:  # Sell
            triggered = [tp for tp in tps_sorted if price <= tp]

        if not triggered:
            return

        highest_triggered = max(triggered) if side == "Buy" else min(triggered)
        idx = tps_sorted.index(highest_triggered)

        # If last TP -> create trailing stop (once)
        if idx == len(tps_sorted) - 1:
            # last TP reached
            already = self.processed_tps.get(symbol, set())
            if highest_triggered in already:
                return
            log.info("Last TP %s reached for %s -> creating trailing stop", highest_triggered, symbol)
            await self._create_trailing_if_not_exists(symbol, trailing=self.default_trailing)
            # mark as processed
            self.processed_tps.setdefault(symbol, set()).add(highest_triggered)
            return

        # Otherwise: move SL to previous safe level
        new_sl = None
        if idx == 0:
            new_sl = entry
        else:
            new_sl = tps_sorted[idx - 1]

        current_sl = float(pos.get("stopLoss") or 0) or 0
        if new_sl is not None and abs(current_sl - float(new_sl)) > 1e-8:
            log.info("Moving SL for %s from %s to %s (price=%s reached TP%s)", symbol, current_sl, new_sl, price, highest_triggered)
            try:
                await self.rest.set_trading_stop(self.category, symbol, stopLoss=str(new_sl))
                await asyncio.sleep(0.2)
                await self.refresh_positions()
            except Exception as e:
                log.exception("Failed to set trading stop: %s", e)

    async def _create_trailing_if_not_exists(self, symbol: str, trailing: Optional[str] = None):
        # If already created trailing for symbol, skip
        if symbol in self.trailing_orders:
            log.info("Trailing stop already exists for %s -> skip", symbol)
            return
        pos = self.positions.get(symbol)
        if not pos:
            log.warning("No position found for %s when creating trailing", symbol)
            return
        side = pos.get("side")
        remaining_size = float(pos.get("size") or 0)
        if remaining_size <= 0:
            log.warning("Zero size for %s -> skip trailing creation", symbol)
            return

        trailing_val = trailing or self.default_trailing
        payload = {
            "category": self.category,
            "symbol": symbol,
            "side": "Sell" if side == "Buy" else "Buy",
            "orderType": "Market",
            "qty": str(remaining_size),
            "reduceOnly": True,
            "closeOnTrigger": True,
            "trailingStop": str(trailing_val),
        }
        try:
            res = await self.rest.place_order(payload)
            log.info("Placed trailing stop for %s -> %s", symbol, res)
            # store trailing order info (best effort: try to extract orderId)
            rid = res.get("result", {}).get("orderId") or res.get("result", {}).get("orderId") if isinstance(res.get("result"), dict) else None
            self.trailing_orders[symbol] = {"payload": payload, "result": res, "order_id": rid}
            await asyncio.sleep(0.2)
            await self.refresh_positions()
        except Exception as e:
            log.exception("Failed to place trailing stop for %s: %s", symbol, e)

    async def _maybe_cancel_orders_if_sl_at_entry(self, pos: Dict[str, Any]):
        symbol = pos.get("symbol")
        if not symbol:
            return
        side = pos.get("side")
        entry = float(pos.get("avgPrice") or 0)
        sl = float(pos.get("stopLoss") or 0) or 0
        size = float(pos.get("size") or 0) or 0
        if size <= 0:
            return

        should_cancel = False
        if side == "Buy" and sl >= entry and sl > 0:
            should_cancel = True
        elif side == "Sell" and sl <= entry and sl > 0:
            should_cancel = True

        if should_cancel:
            log.info("SL for %s reached entry -> cancelling related open orders", symbol)
            try:
                res = await self.rest.get_open_orders(category=self.category, symbol=symbol)
                orders_list = res.get("result", {}).get("list") or res.get("result") or []
                for o in orders_list:
                    oid = o.get("orderId") or o.get("orderLinkId")
                    if not oid:
                        continue
                    o_symbol = o.get("symbol")
                    reduce_only = o.get("reduceOnly", False)
                    if o_symbol != symbol:
                        continue
                    # cancel orders that would open new positions (reduceOnly == False)
                    if not reduce_only:
                        log.info("Cancelling order %s for %s", oid, symbol)
                        try:
                            await self.rest.cancel_order(self.category, symbol, oid)
                        except Exception as e:
                            log.exception("Error cancelling order %s: %s", oid, e)
            except Exception as e:
                log.exception("Failed to fetch/cancel orders: %s", e)

    # ---------------------------
    # Utility: refresh positions (REST)
    # ---------------------------
    async def refresh_positions(self):
        try:
            resp = await self.rest.get_positions(category=self.category)
            result = resp.get("result", {})
            if isinstance(result, dict) and "list" in result:
                for pos in result["list"]:
                    self.positions[pos["symbol"]] = pos
            elif isinstance(result, list):
                for pos in result:
                    self.positions[pos["symbol"]] = pos
            elif isinstance(result, dict):
                for pos in result.get("list", []):
                    self.positions[pos["symbol"]] = pos
            log.info("Positions refreshed: %s", list(self.positions.keys()))
        except Exception as e:
            log.exception("Failed refresh positions: %s", e)

    # ---------------------------
    # External setter
    # ---------------------------
    def set_symbol_tps(self, symbol: str, tps: List[float]):
        self.tps[symbol] = [float(x) for x in tps]
        self.processed_tps[symbol] = set()
        log.info("Set TPs for %s -> %s", symbol, self.tps[symbol])

# ---------------------------
# If run as script for quick manual test
# ---------------------------
if __name__ == "__main__":
    import os

    API_KEY = os.environ.get("BYBIT_API_KEY")
    API_SECRET = os.environ.get("BYBIT_API_SECRET")
    if not API_KEY or not API_SECRET:
        print("Please set BYBIT_API_KEY and BYBIT_API_SECRET environment variables for a quick test")
        raise SystemExit(1)

    async def _demo():
        rest = BybitRest(API_KEY, API_SECRET)
        mgr = BybitWSManager(API_KEY, API_SECRET, rest)
        mgr.set_symbol_tps("ETHUSDT", [4000, 4050, 4100, 4150])
        await mgr.refresh_positions()
        await mgr.start(["ETHUSDT"])
        # run indefinitely
        while True:
            await asyncio.sleep(3600)

    try:
        asyncio.run(_demo())
    except KeyboardInterrupt:
        log.info("Stopped by user")
