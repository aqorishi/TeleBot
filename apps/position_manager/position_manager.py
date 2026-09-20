import asyncio, json, aiohttp, hmac, hashlib, ccxt, os
import time, shutil
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from utils.logger import adminReport
from utils.bybit import (
    getBybitServerTimeMS, getPosition, getOpenOrders,
    signRequest, getCurrentPrice, placeSignalOrder,
    generateRatioList, splitQtyByWeights,
)
from json import JSONDecodeError
from sources.config import BYBIT, ln, signal_template

tradesLogFile = Path("./logs/trades.json")
fileLock = asyncio.Lock()
fetchIntervalMinutes = 1

# ============================================================
# تنظیمات قابل تنظیم
# ============================================================
SCALE_IN_TRIGGER_RATIO = 0.80  # 80% فاصله تا TP اول → تبدیل ورودی دوم به مارکت

exchange = ccxt.bybit()


# exchange = ccxt.bybit(
#     {
#         # "apiKey": BYBIT["api_key"],
#         # "secret": BYBIT["api_secret"],
#         "enableRateLimit": True,
#     }
# )


# ============================================================
# توابع کمکی موجود (بدون تغییر)
# ============================================================

async def cancel_order(
    session, symbol: str, order_id: str, api_key: str, api_secret: str, server
):
    """Cancel a single active order on Bybit (REST v5)."""
    endpoint = "/v5/order/cancel"
    url = server + endpoint

    timestamp = await getBybitServerTimeMS(session, server)
    recv_window = "5000"

    # Auto-detect category (spot vs linear)
    category = "linear" if "USDT" in symbol else "spot"
    body = {"category": category, "symbol": symbol, "orderId": order_id}

    param_str = str(timestamp) + api_key + recv_window + json.dumps(body)
    signature = hmac.new(
        api_secret.encode(), param_str.encode(), hashlib.sha256
    ).hexdigest()

    headers = {
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-TIMESTAMP": str(timestamp),
        "X-BAPI-RECV-WINDOW": recv_window,
        "X-BAPI-SIGN": signature,
        "Content-Type": "application/json",
    }

    try:
        async with session.post(url, headers=headers, json=body, timeout=10) as resp:
            data = await resp.json()
            if data.get("retCode") == 0:
                await adminReport(
                    f"position manager:{ln()}\n✅ Order {order_id} on {symbol} canceled successfully."
                )
                return True
            await adminReport(f"position manager:{ln()}\n⚠️ Failed to cancel {order_id} on {symbol}: {data}")
            return False
    except Exception as e:
        await adminReport(f"position manager:{ln()}\n❌ Exception while canceling {order_id} on {symbol}: {e}")
        return False


async def save_signals(signals: dict):
    """Safely saves updated signals to file using atomic write."""
    tmp_path = tradesLogFile + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(signals, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, tradesLogFile)


async def load_signals_from_file():
    """Load active signal list from file (return empty list if missing or corrupted)."""
    async with fileLock:
        if not tradesLogFile.exists():
            tradesLogFile.parent.mkdir(parents=True, exist_ok=True)
            tradesLogFile.write_text("[]", encoding="utf-8")
            return []
        try:
            with open(tradesLogFile, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []


async def fetch_active_orders(session, api_key: str, api_secret: str, server):
    """
    Fetch all active orders from Bybit (demo or real account).
    Returns: dict
    """
    try:
        endpoint = "/v5/order/realtime"
        url = server + endpoint

        params = {"category": "linear", "settleCoin": "USDT"}

        # --- Create signature ---
        timestamp = await getBybitServerTimeMS(session, server)
        recv_window = "5000"
        query_string = "category=linear&settleCoin=USDT"

        # ✅ Convert timestamp to string before concatenation
        prehash = str(timestamp) + api_key + recv_window + query_string
        signature = hmac.new(
            bytes(api_secret, "utf-8"), prehash.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        headers = {
            "X-BAPI-API-KEY": api_key,
            "X-BAPI-TIMESTAMP": str(timestamp),
            "X-BAPI-RECV-WINDOW": recv_window,
            "X-BAPI-SIGN": signature,
        }

        async with session.get(url, params=params, headers=headers) as resp:
            data = await resp.json()
            if data.get("retCode") != 0:
                await adminReport(f"position manager:{ln()}\n⚠️ Bybit returned error: {data}")
                return {"result": {"list": []}}

            orders = data.get("result", {}).get("list", [])
            return data

    except Exception as e:
        await adminReport(f"position manager:{ln()}\n⚠️ Error fetching active orders: {e}")
        return {"result": {"list": []}}


async def update_stop_loss(
    session,
    symbol: str,
    new_sl: float,
    api_key: str,
    api_secret: str,
    server: str,
    order_id: str = None,
):
    """Update stop loss for an open position (Bybit v5)."""
    try:
        url = server + "/v5/position/trading-stop"

        timestamp = await getBybitServerTimeMS(session=session, server=server)
        recv_window = "5000"

        payload = {
            "category": "linear",
            "symbol": symbol,
            "stopLoss": str(new_sl),
        }

        # --- Combine with auth params for signing ---
        sign_params = {
            "api_key": api_key,
            "timestamp": timestamp,
            "recv_window": recv_window,
            **payload,
        }

        signature = signRequest(sign_params, api_secret)

        headers = {"Content-Type": "application/json"}
        payload.update(
            {
                "api_key": api_key,
                "timestamp": timestamp,
                "recv_window": recv_window,
                "sign": signature,
            }
        )

        async with session.post(url, json=payload, headers=headers) as resp:
            data = await resp.json()

            if data.get("retCode") == 0:
                await adminReport(f"position manager:{ln()}\n✅ Stop loss updated for {symbol} → {new_sl}")
                return True
            else:
                await adminReport(f"position manager:{ln()}\n⚠️ Failed to update SL for {symbol}: {data}")
                return False

    except Exception as e:
        await adminReport(f"position manager:{ln()}\n⚠️ Error updating stop loss for {symbol}: {e}")
        return False


async def fetch_ohlcv(pair, timeframe="1m", limit=1):
    """
    Fetch OHLCV data for a given symbol and timeframe.
    Returns a pandas DataFrame with columns: timestamp, open, high, low, close, volume.
    """
    try:
        data = exchange.fetch_ohlcv(pair, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(
            data, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        await adminReport(
            f"position manager:{ln()}\n⚠️ Error fetching data for {pair} on {timeframe}: {e}"
        )
        return pd.DataFrame()


def atomic_save_json(path: str, data):
    """
    Save JSON atomically: write to temp file then replace.
    """
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as tf:
        json.dump(data, tf, ensure_ascii=False, indent=2)
        tf.flush()
        os.fsync(tf.fileno())
    os.replace(tmp_path, path)  # atomic on most OSes


async def loadSignalsSafe(path: str, createIfMissing: bool = False):
    """
    Safely load the signals JSON file.
    Returns: dict (signals) or None on fatal error.
    Side-effects: if file is corrupted, creates a timestamped backup and returns None.
    """
    if not os.path.exists(path):
        if createIfMissing:
            try:
                atomic_save_json(path, {})  # create empty file
            except Exception as e:
                await adminReport(f"⚠️ Couldn't create {path}: {e}")
                return None
            return {}
        await adminReport(f"⚠️ No {path} found.")
        return None

    # quick sanity: check filesize
    try:
        size = os.path.getsize(path)
    except Exception as e:
        await adminReport(f"⚠️ Could not stat {path}: {e}")
        return None

    if size == 0:
        # backup and treat as empty
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        backup = f"{path}.bak.empty.{timestamp}"
        try:
            shutil.copy2(path, backup)
            await adminReport(f"⚠️ {path} is empty. Backed up to {backup}.")
            atomic_save_json(path, {})
            return {}
        except Exception as e:
            await adminReport(f"⚠️ Error handling empty {path}: {e}")
            return None

    # read contents safely
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        await adminReport(f"⚠️ Couldn't read {path}: {e}")
        return None

    if not text.strip():
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        backup = f"{path}.bak.blank.{timestamp}"
        try:
            shutil.copy2(path, backup)
            await adminReport(
                f"⚠️ {path} contains only whitespace. Backed up to {backup}. Reinitializing."
            )
            atomic_save_json(path, {})
            return {}
        except Exception as e:
            await adminReport(f"⚠️ Error handling blank {path}: {e}")
            return None

    try:
        signals = json.loads(text)
        if not isinstance(signals, dict):
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            backup = f"{path}.bak.notdict.{timestamp}"
            shutil.copy2(path, backup)
            await adminReport(
                f"⚠️ {path} JSON root is not an object. Backed up to {backup}."
            )
            return None
        return signals
    except JSONDecodeError as je:
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        backup = f"{path}.bak.corrupt.{timestamp}"
        try:
            shutil.copy2(path, backup)
            await adminReport(
                f"⚠️ Corrupted JSON in {path}: {je}. Backed up to {backup}. Reinitializing to empty."
            )
            atomic_save_json(path, {})
            return {}
        except Exception as e:
            await adminReport(f"⚠️ Error backing up corrupted {path}: {e}")
            return None


# ============================================================
# توابع کمکی جدید (اضافه شده)
# ============================================================

async def refresh_position_from_api(
    session, symbol: str, api_key: str, api_secret: str, server
):
    """
    Fetch latest position info (avgPrice, size) from Bybit API safely.
    """
    url = server + "/v5/position/list"
    params = {
        "category": "linear",
        "symbol": symbol,
        "apiKey": api_key,
        "timestamp": await getBybitServerTimeMS(session, server),
    }
    params["sign"] = signRequest(params, api_secret)

    try:
        async with session.get(url, params=params, timeout=15) as resp:
            text = await resp.text()
            await adminReport(
                f"🔄 position manager:{ln()}\n Bybit response for {symbol}: {text}"
            )

            try:
                data = json.loads(text)
            except Exception:
                await adminReport(f"position manager:{ln()}\n⚠️ Non-JSON response from Bybit: {text}")
                return None

            if not isinstance(data, dict):
                await adminReport(f"position manager:{ln()}\n⚠️ Unexpected data type from Bybit: {type(data)}")
                return None

            # ✅ Safely check nested fields
            result = data.get("result", {})
            if (
                data.get("retCode") == 0
                and result
                and "list" in result
                and result["list"]
            ):
                pos = result["list"][0]
                avg_price = float(pos.get("avgPrice", 0))
                qty = float(pos.get("size", 0))
                return {"avgPrice": avg_price, "qty": qty}
            else:
                await adminReport(f"position manager:{ln()}\n⚠️ Could not fetch position info: {data}")
                return None

    except Exception as e:
        await adminReport(f"position manager:{ln()}\n❌ Error in refresh_position_from_api: {e}")
        return None


def _build_pm_signal(signal: dict, session, apiKey: str, apiSecret: str, server: str) -> dict:
    """
    ساخت یک signal dict سازگار با توابع getCurrentPrice و placeSignalOrder
    از داده‌های موجود در trades.json + پارامترهای ورودی.
    """
    return {
        "session": session,
        "symbol": signal.get("symbol"),
        "exchangeURL": server,
        "keys": {"api_key": apiKey, "api_secret": apiSecret},
        "category": signal.get("category", "linear"),
        "side": signal.get("side"),
        "leverage": signal.get("leverage", 1),
        "margin_mode": signal.get("marginMode", "isolated"),
        "minQty": signal.get("minQty", 0.001),
        "maxQty": signal.get("maxQty", 1000000),
        "step": signal.get("step", 0.001),
        "maxTrailing": signal.get("maxTrailing", 0.2),
    }


async def close_position(session, params):
    """
    Closes an open position on Bybit (or demo mode if enabled).
    Automatically determines the opposite side (Buy -> Sell, Sell -> Buy).
    ⚠️ باگ close_position اصلاح شد (قبلا server و symbol به عنوان key نوشته شده بود)
    """
    try:
        server = params.get("server")
        keys = params.get("keys")
        api_key = keys.get("api_key")
        api_secret = keys.get("api_secret")
        symbol = params.get("symbol")

        # Get current position to find size & side
        position_data = await getPosition(session, params)
        pos = position_data.get("position", position_data)
        side = pos.get("side", "").capitalize()
        size = float(pos.get("size", 0))

        if size == 0:
            await adminReport(f"position manager:{ln()}\nℹ️ No active position found for {symbol}. Nothing to close.")
            return False

        # Determine opposite side for closing
        close_side = "Sell" if side == "Buy" else "Buy"

        # Build close order payload
        order_payload = {
            "symbol": symbol,
            "side": close_side,
            "orderType": "Market",
            "reduceOnly": True,
            "qty": size,
            "category": "linear",
        }

        # --- Execute close order ---
        if "demo" in server:
            await adminReport(f"position manager:{ln()}\n🧪 [DEMO] Closing {symbol}: {side} position ({size}) via Market.")
            return True

        # Send the real close order
        timestamp = await getBybitServerTimeMS(session, server)
        recv_window = "5000"
        sign_params = {
            "api_key": api_key,
            "timestamp": timestamp,
            "recv_window": recv_window,
            **order_payload,
        }
        signature = signRequest(sign_params, api_secret)

        headers = {"Content-Type": "application/json"}
        order_payload.update({
            "api_key": api_key,
            "timestamp": timestamp,
            "recv_window": recv_window,
            "sign": signature,
        })

        res = await session.post(
            url=server + "/v5/order/create",
            headers=headers,
            json=order_payload,
        )
        data = await res.json()

        if data.get("retCode") == 0:
            await adminReport(f"position manager:{ln()}\n✅ {symbol} position closed successfully.")
            return True
        else:
            await adminReport(f"position manager:{ln()}\n⚠️ Failed to close {symbol}: {data}")
            return False

    except Exception as e:
        await adminReport(f"position manager:{ln()}\n⚠️ Error closing position for {symbol}: {e}")
        return False


async def syncTradeState(
    signal: dict, session, apiKey: str, apiSecret: str, server: str
) -> dict:
    """
    همگام‌سازی وضعیت واقعی بای‌بیت با trades.json (بدون هیچ منطق معامله‌ای)
    
    مراحل:
      1. دریافت پوزیشن و سفارش‌های باز از بای‌بیت
      2. بروزرسانی وضعیت هر entry (filled/cancelled/still open)
      3. بروزرسانی وضعیت پوزیشن (opened/qty/avgPrice)
      4. تعیین state کلی معامله
      5. ذخیره در trades.json
    
    Returns: signal (بروزرسانی شده)
    """
    symbol = signal.get("symbol")

    try:
        # === STEP 1: ساخت signal سازگار و دریافت داده از بای‌بیت ===
        pm_signal = _build_pm_signal(signal, session, apiKey, apiSecret, server)

        position = await getPosition(pm_signal)
        openOrders = await getOpenOrders(pm_signal)

        positionExists = position is not None and float(position.get("size", 0)) > 0
        positionQty = float(position.get("size", 0)) if position else 0.0
        positionAvgPrice = float(position.get("avgPrice", 0)) if position else None
        positionSide = position.get("side") if position else None

        activeOrderIds = {o.get("orderId") for o in openOrders}

        # === STEP 2: همگام‌سازی وضعیت entries ===
        entries = signal.get("entries", [])

        filledQty = 0.0
        openQty = 0.0
        cancelledCount = 0

        for entry in entries:
            orderId = entry.get("orderId")

            # هنوز در open orders هست → هنوز fill نشده
            if orderId and orderId in activeOrderIds:
                entry["filled"] = False
                entry["cancelled"] = False
                openQty += float(entry.get("qty", 0))

            # در open orders نیست ولی position داریم → filled
            elif positionExists and not entry.get("cancelled", False):
                entry["filled"] = True
                entry["cancelled"] = False
                entry["fillPrice"] = positionAvgPrice
                entry["fillQty"] = float(entry.get("qty", 0))
                filledQty += float(entry.get("qty", 0))

            # نه order هست نه position → cancelled
            elif not positionExists:
                if orderId and orderId not in activeOrderIds:
                    entry["cancelled"] = True
                    cancelledCount += 1

        # === STEP 3: تعیین state ===
        totalEntries = len(entries)
        openEntriesCount = sum(1 for e in entries if not e.get("filled") and not e.get("cancelled"))
        filledEntriesCount = sum(1 for e in entries if e.get("filled"))
        allCancelled = all(e.get("cancelled") for e in entries)

        if allCancelled and not positionExists:
            state = "closed"
        elif positionExists and openEntriesCount > 0:
            state = "partial_fill"
        elif positionExists and openEntriesCount == 0:
            state = "full_fill"
        elif not positionExists and openEntriesCount > 0:
            state = "waiting_entry"
        elif not positionExists and openEntriesCount == 0 and not allCancelled:
            state = "closed"
        else:
            state = signal.get("state", "unknown")

        # === STEP 4: بروزرسانی position snapshot ===
        signal["position"] = {
            "opened": positionExists,
            "qty": positionQty,
            "avgPrice": positionAvgPrice,
            "side": positionSide,
            "updatedAt": datetime.now(timezone.utc).isoformat()
        }

        # === STEP 5: بروزرسانی qty ها ===
        signal["filledQty"] = filledQty
        signal["openQty"] = openQty

        if positionExists:
            signal["entry"] = positionAvgPrice
            signal["qty"] = positionQty

        # === STEP 6: بروزرسانی state ===
        signal["state"] = state

        # === STEP 7: ذخیره ===
        signal["updatedAt"] = datetime.now(timezone.utc).isoformat()

        # await adminReport(
        #     f"🔄 {symbol} | state={state} | pos={positionQty} | "
        #     f"avgPrice={positionAvgPrice} | openEntries={openEntriesCount} | "
        #     f"filledEntries={filledEntriesCount}"
        # )

        return signal

    except Exception as e:
        await adminReport(f"position manager:{ln()}\n⚠️ syncTradeState error for {symbol}: {e}")
        return signal


async def _place_tp_order(
    signal: dict, session, apiKey: str, apiSecret: str, server: str,
    tp_index: int, tp_price: float, tp_qty: float
) -> str | None:
    """
    قرار دادن یک سفارش حد سود (Limit reduceOnly) روی بای‌بیت.
    
    Returns:
        order_id (str) یا None در صورت خطا
    """
    symbol = signal.get("symbol")
    side = signal.get("side")  # Buy یا Sell
    maxTrailing = signal.get("maxTrailing", 0.2)

    # تعیین جهت خروج (خلاف جهت ورود)
    close_side = "Sell" if side == "Buy" else "Buy"

    # تعداد کل TP ها
    tp_orders = signal.get("tpOrders", [])
    total_tp = len(tp_orders)
    is_last_tp = (tp_index == total_tp - 1)

    # ساخت signal برای placeSignalOrder
    pm_signal = {
        "session": session,
        "symbol": symbol,
        "exchangeURL": server,
        "keys": {"api_key": apiKey, "api_secret": apiSecret},
        "category": signal.get("category", "linear"),
        "side": close_side,
        "orderType": "Limit",
        "qty": str(tp_qty),
        "price": str(tp_price),
        "variant": f"TP{tp_index + 1}",
        "reduceOnly": True,
        "closeOnTrigger": is_last_tp,
        "trailingStop": maxTrailing if is_last_tp else None,
    }

    # اگر آخرین TP باشد، closeOnTrigger + trailingStop فعال شود
    # if is_last_tp:
    #     pm_signal["timeInForce"] = "GTE"

    if is_last_tp:
        pm_signal["timeInForce"] = "GTC"
        

    result = await placeSignalOrder(pm_signal)

    if result and result.get("response") == 0:
        await adminReport(
            f"position manager:{ln()}\n✅ TP{tp_index + 1} order placed for {symbol}: "
            f"price={tp_price}, qty={tp_qty}, orderId={result.get('order_id')}"
        )
        return result.get("order_id")
    else:
        await adminReport(
            f"position manager:{ln()}\n⚠️ Failed to place TP{tp_index + 1} for {symbol}: {result}"
        )
        return None


async def _place_market_order(
    signal: dict, session, apiKey: str, apiSecret: str, server: str,
    qty: float
) -> str | None:
    """
    ارسال سفارش مارکت برای افزایش حجم پوزیشن (scale-in).
    
    Returns:
        order_id (str) یا None در صورت خطا
    """
    symbol = signal.get("symbol")
    side = signal.get("side")  # همون جهت پوزیشن اصلی

    pm_signal = {
        "session": session,
        "symbol": symbol,
        "exchangeURL": server,
        "keys": {"api_key": apiKey, "api_secret": apiSecret},
        "category": signal.get("category", "linear"),
        "side": side,
        "orderType": "Market",
        "qty": str(qty),
        "variant": "scale_in",
        "reduceOnly": False,
    }

    result = await placeSignalOrder(pm_signal)

    if result and result.get("response") == 0:
        await adminReport(
            f"position manager:{ln()}\n✅ Market order placed for {symbol} (scale-in): "
            f"qty={qty}, orderId={result.get('order_id')}"
        )
        return result.get("order_id")
    else:
        await adminReport(
            f"position manager:{ln()}\n⚠️ Failed to place market order for {symbol}: {result}"
        )
        return None


async def _place_protection_orders(
    signal: dict, session, apiKey: str, apiSecret: str, server: str
):
    """
    قرار دادن SL و تمام TP های محاسبه شده روی بای‌بیت.
    فقط یکبار زمانی که اولین entry پر میشود صدا زده میشود.
    
    محاسبه TP qty ها:
      - از generateRatioList و splitQtyByWeights استفاده میکند
      - هر TP یک سفارش Limit reduceOnly جداگانه است
    """
    symbol = signal.get("symbol")
    tp_orders = signal.get("tpOrders", [])
    if not tp_orders:
        await adminReport(f"position manager:{ln()}\n⚠️ No TP orders defined for {symbol}")
        return

    # محاسبه مقدار پوزیشن فعلی
    positionQty = float(signal.get("qty", 0))
    if positionQty <= 0:
        await adminReport(f"position manager:{ln()}\n⚠️ Position qty is 0 for {symbol}, cannot place TP orders")
        return

    minQty = float(signal.get("minQty", 0.001))
    step = float(signal.get("step", 0.001))
    n = len(tp_orders)

    # محاسبه وزن‌ها و تقسیم qty
    weights = generateRatioList(n)
    tp_qtys = splitQtyByWeights(positionQty, weights, minQty, step)

    await adminReport(
        f"position manager:{ln()}\n⚖️ {symbol}: Split total qty={positionQty} into {tp_qtys}"
    )

    # قرار دادن SL
    slPrice = float(signal.get("SLNow", signal.get("SLPrice", 0)))
    if slPrice > 0:
        res = await update_stop_loss(
            session, symbol, slPrice, apiKey, apiSecret, server
        )
        if res:
            signal["slOrderId"] = "sl_set"
            await adminReport(f"position manager:{ln()}\n✅ SL set for {symbol} at {slPrice}")

    # قرار دادن هر TP
    for i, tp_order in enumerate(tp_orders):
        tp_price = float(tp_order.get("price", 0))
        tp_qty = tp_qtys[i] if i < len(tp_qtys) else 0

        if tp_qty <= 0 or tp_price <= 0:
            tp_order["placed"] = False
            continue

        order_id = await _place_tp_order(
            signal, session, apiKey, apiSecret, server,
            i, tp_price, tp_qty
        )

        if order_id:
            tp_order["placed"] = True
            tp_order["orderId"] = order_id
            tp_order["qty"] = tp_qty
        else:
            tp_order["placed"] = False


async def _update_tp_orders_after_fill(
    signal: dict, session, apiKey: str, apiSecret: str, server: str
):
    """
    وقتی entry دوم پر شد، تمام TP orders قبلی را کنسل کرده
    و با qty جدید پوزیشن دوباره محاسبه و قرار می‌دهد.
    """
    symbol = signal.get("symbol")

    # کنسل کردن TP orders قبلی
    tp_orders = signal.get("tpOrders", [])
    for tp_order in tp_orders:
        if tp_order.get("placed") and tp_order.get("orderId"):
            await cancel_order(
                session, symbol,
                tp_order["orderId"], apiKey, apiSecret, server
            )
            tp_order["placed"] = False
            tp_order["orderId"] = None
            tp_order["filled"] = False
            tp_order["qty"] = None

    # محاسبه و قرار دادن TP های جدید با qty جدید
    await _place_protection_orders(signal, session, apiKey, apiSecret, server)


async def processSignals(session, apiKey: str, apiSecret: str, server):
    """
    موتور اصلی مدیریت معاملات (مبتنی بر وضعیت واقعی بای‌بیت، بدون کندل)
    
    هر یک دقیقه یکبار اجرا میشود. برای هر ارز:
    
    1. syncTradeState: همگام‌سازی وضعیت سفارش‌ها و پوزیشن از بای‌بیت
    2. مدیریت state های مختلف معامله
    
    State های ممکن:
      - waiting_entry: سفارش‌ها ثبت شده ولی هیچکدام پر نشده
      - partial_fill: حداقل یک entry پر شده ولی هنوز entry باز داریم
      - full_fill: تمام entry های فعال پر شده
      - closed: معامله بسته شده
    """
    try:
        # --- Load signals file safely ---
        async with fileLock:
            signals = await loadSignalsSafe(tradesLogFile, createIfMissing=False)

        if signals is None or not signals:
            return

        # --- Iterate through all active signals ---
        for symbol in list(signals.keys()):
            signal = signals[symbol]

            try:
                # ============================================================
                # PHASE 1: SYNC with ByBit
                # ============================================================
                signal = await syncTradeState(signal, session, apiKey, apiSecret, server)

                state = signal.get("state", "unknown")

                # اگر معامله بسته شده، حذف کن
                if state == "closed":
                    await adminReport(f"position manager:{ln()}\n🗑️ {symbol}: Trade closed. Removing from list.")
                    del signals[symbol]
                    async with fileLock:
                        atomic_save_json(tradesLogFile, signals)
                    continue

                # دریافت قیمت فعلی
                pm_signal = _build_pm_signal(signal, session, apiKey, apiSecret, server)
                current_price = await getCurrentPrice(pm_signal)
                if not current_price or current_price <= 0:
                    await adminReport(f"position manager:{ln()}\n⚠️ Could not get price for {symbol}, skipping...")
                    continue

                # ============================================================
                # PHASE 2: مدیریت بر اساس state
                # ============================================================

                if state == "waiting_entry":
                    # فقط منتظریم — کاری نمیکنیم
                    # await adminReport(
                    #     f"position manager:{ln()}\n⏳ {symbol}: Waiting for entry fill. "
                    #     f"currentPrice={current_price}"
                    # )
                    continue

                elif state == "partial_fill":
                    # ========================================================
                    # حداقل یک entry پر شده — بررسی موارد زیر:
                    # ========================================================

                    entries = signal.get("entries", [])
                    filled_entries = [e for e in entries if e.get("filled")]
                    open_entries = [e for e in entries if not e.get("filled") and not e.get("cancelled")]
                    tp_orders = signal.get("tpOrders", [])
                    tpIndexHit = int(signal.get("tpIndexHit", 0))
                    positionQty = float(signal.get("qty", 0))
                    positionAvgPrice = float(signal.get("entry", 0))
                    slPrice = float(signal.get("SLNow", signal.get("SLPrice", 0)))

                    # --- 2-a: اگر اولین entry پر شد و هنوز SL/TP نگذاشتیم ---
                    if filled_entries and not signal.get("slOrderId"):
                        await adminReport(
                            f"position manager:{ln()}\n🎯 {symbol}: First entry filled! "
                            f"Placing protection orders (SL + TPs)..."
                        )
                        await _place_protection_orders(
                            signal, session, apiKey, apiSecret, server
                        )

                    # --- 2-b: بررسی SCALE-IN TRIGGER (شرط 3 - 80% فاصله تا TP اول) ---
                    if (
                        open_entries
                        and tp_orders
                        and tpIndexHit == 0  # هنوز هیچ TP ای هیت نشده
                    ):
                        # محاسبه فاصله بین entry اول و TP اول
                        main_entry_price = float(filled_entries[0].get("fillPrice", signal.get("entry", 0)))
                        first_tp_price = float(tp_orders[0].get("price", 0))

                        if main_entry_price > 0 and first_tp_price > 0:
                            distance = abs(first_tp_price - main_entry_price)
                            trigger_price = main_entry_price + (distance * SCALE_IN_TRIGGER_RATIO)

                            is_long = signal.get("side", "").lower() in ("buy", "long")
                            if not is_long:
                                trigger_price = main_entry_price - (distance * SCALE_IN_TRIGGER_RATIO)

                            # آیا قیمت به trigger رسیده؟
                            triggered = False
                            if is_long:
                                triggered = current_price >= trigger_price
                            else:
                                triggered = current_price <= trigger_price

                            if triggered:
                                await adminReport(
                                    f"position manager:{ln()}\n🚀 {symbol}: Scale-in triggered! "
                                    f"currentPrice={current_price} >= trigger={trigger_price} "
                                    f"({SCALE_IN_TRIGGER_RATIO * 100:.0f}% of TP1 distance)"
                                )

                                # کنسل کردن entry های باز
                                for open_entry in open_entries:
                                    if open_entry.get("orderId"):
                                        await cancel_order(
                                            session, symbol,
                                            open_entry["orderId"],
                                            apiKey, apiSecret, server
                                        )
                                        open_entry["cancelled"] = True
                                        await adminReport(
                                            f"position manager:{ln()}\n🗑️ {symbol}: Cancelled alt entry "
                                            f"price={open_entry.get('price')}, qty={open_entry.get('qty')}"
                                        )

                                # خرید مارکت با حجم ورودی دوم
                                total_alt_qty = sum(float(e.get("qty", 0)) for e in open_entries)
                                if total_alt_qty > 0:
                                    scale_order_id = await _place_market_order(
                                        signal, session, apiKey, apiSecret, server,
                                        total_alt_qty
                                    )

                                    if scale_order_id:
                                        # انتقال SL به entry اول (ریسک فری)
                                        new_sl = main_entry_price
                                        res = await update_stop_loss(
                                            session, symbol, new_sl,
                                            apiKey, apiSecret, server
                                        )
                                        if res:
                                            signal["SLNow"] = new_sl
                                            await adminReport(
                                                f"position manager:{ln()}\n🛡️ {symbol}: SL moved to "
                                                f"entry price ({new_sl}) → RISK FREE!"
                                            )

                                        # بروزرسانی وضعیت entries (همه cancelled یا filled)
                                        # open_entries الان cancelled شده‌اند
                                        signal["openQty"] = 0.0

                    # --- 2-c: بررسی اینکه آیا entry دوم به طور طبیعی پر شده ---
                    # syncTradeState قبلا این رو چک کرده، فقط باید واکنش نشون بدیم
                    newly_filled = [e for e in entries if e.get("filled") and not e.get("_processed")]
                    if newly_filled:
                        for e in newly_filled:
                            await adminReport(
                                f"position manager:{ln()}\n✅ {symbol}: Entry {e.get('variant')} "
                                f"filled at price={e.get('fillPrice')}, qty={e.get('qty')}"
                            )
                            e["_processed"] = True

                        # اگر entry جدیدی پر شد، TP ها رو با qty جدید بازمحاسبه کن
                        await _update_tp_orders_after_fill(
                            signal, session, apiKey, apiSecret, server
                        )

                    # --- 2-d: بررسی حد سود و حد ضرر ---
                    await _manage_tp_sl(
                        signal, session, apiKey, apiSecret, server,
                        current_price, signals
                    )

                    # ذخیره
                    async with fileLock:
                        atomic_save_json(tradesLogFile, signals)

                    continue

                elif state == "full_fill":
                    # ========================================================
                    # تمام entry ها پر شده — فقط مدیریت TP و SL
                    # ========================================================
                    await _manage_tp_sl(
                        signal, session, apiKey, apiSecret, server,
                        current_price, signals
                    )

                    # ذخیره
                    async with fileLock:
                        atomic_save_json(tradesLogFile, signals)

                    continue

                else:
                    await adminReport(
                        f"position manager:{ln()}\n⚠️ {symbol}: Unknown state '{state}', skipping..."
                    )
                    continue

            except Exception as e:
                await adminReport(f"position manager:{ln()}\n⚠️ Error processing {symbol}: {e}")
                # ذخیره وضعیت فعلی حتی در صورت خطا
                async with fileLock:
                    atomic_save_json(tradesLogFile, signals)
                continue

    except Exception as e:
        await adminReport(f"position manager:{ln()}\n⚠️ Global error in processSignals: {e}")


async def _manage_tp_sl(
    signal: dict, session, apiKey: str, apiSecret: str, server: str,
    current_price: float, signals: dict
):
    """
    مدیریت حد سود و حد ضرر یک پوزیشن باز.
    
    منطق:
      1. اگر SL هیت شد → حذف معامله
      2. اگر TP اول هیت شد:
         - SL رو به قیمت ورودی منتقل کن (ریسک فری)
         - entry های باز (如果有) را کنسل کن
         - کنسل کردن سفارش TP اول از بای‌بیت (reduceOnly خودش پر شده)
         - tpIndexHit را افزایش بده
      3. اگر TP های بعدی هیت شدند:
         - SL را به TP قبلی منتقل کن
         - کنسل کردن سفارش TP از بای‌بیت
         - tpIndexHit را افزایش بده
      4. اگر آخرین TP هیت شد:
         - کل پوزیشن رو ببند
         - حذف از trades.json
    
    نکته: تشخیص TP hit بر اساس:
      - وجود پوزیشن + تعداد TPs باز کمتر از قبل
      - یا مقایسه قیمت فعلی با TP (به عنوان fallback)
    """
    symbol = signal.get("symbol")
    tp_orders = signal.get("tpOrders", [])
    tpIndexHit = int(signal.get("tpIndexHit", 0))
    slNow = float(signal.get("SLNow", signal.get("SLPrice", 0)))
    positionQty = float(signal.get("qty", 0))
    is_long = signal.get("side", "").lower() in ("buy", "long")

    # ============================================================
    # STEP 1: بررسی حد ضرر
    # ============================================================
    # اگر پوزیشن نداریم یعنی SL زده شده یا معامله بسته شده
    if positionQty <= 0:
        await adminReport(
            f"position manager:{ln()}\n🛑 {symbol}: Position is 0. SL likely hit or position closed."
        )
        del signals[symbol]
        async with fileLock:
            atomic_save_json(tradesLogFile, signals)
        return

    # بررسی SL با قیمت فعلی (fallback)
    sl_hit = False
    if slNow > 0:
        if is_long and current_price <= slNow:
            sl_hit = True
        elif not is_long and current_price >= slNow:
            sl_hit = True

    if sl_hit:
        await adminReport(
            f"position manager:{ln()}\n🛑 {symbol}: StopLoss hit at {slNow}. "
            f"currentPrice={current_price}. Removing trade."
        )
        del signals[symbol]
        async with fileLock:
            atomic_save_json(tradesLogFile, signals)
        return

    # ============================================================
    # STEP 2: تشخیص اینکه آیا TP جدیدی هیت شده
    # ============================================================
    
    # روش اول: بررسی از طریق سفارش‌های باز بای‌بیت
    pm_signal = _build_pm_signal(signal, session, apiKey, apiSecret, server)
    open_orders = await getOpenOrders(pm_signal)
    active_tp_order_ids = set()
    
    for order in open_orders:
        order_id = order.get("orderId")
        # بررسی اینکه آیا این order یکی از TP orders ماست
        for tp_order in tp_orders:
            if tp_order.get("orderId") == order_id:
                active_tp_order_ids.add(order_id)

    # TP های که قبلاً placed بودند ولی الان نیستند → filled
    newly_hit_tps = []
    for i, tp_order in enumerate(tp_orders):
        if (
            tp_order.get("placed")
            and tp_order.get("orderId")
            and tp_order["orderId"] not in active_tp_order_ids
            and not tp_order.get("filled")
            and i >= tpIndexHit  # فقط TP های بعد از آخرین TP هیت شده
        ):
            newly_hit_tps.append(i)
            tp_order["filled"] = True

    # روش دوم (fallback): بررسی قیمت فعلی
    if not newly_hit_tps and tpIndexHit < len(tp_orders):
        target_tp_price = float(tp_orders[tpIndexHit].get("price", 0))
        if target_tp_price > 0:
            if is_long and current_price >= target_tp_price:
                newly_hit_tps = [tpIndexHit]
                tp_orders[tpIndexHit]["filled"] = True
            elif not is_long and current_price <= target_tp_price:
                newly_hit_tps = [tpIndexHit]
                tp_orders[tpIndexHit]["filled"] = True

    if not newly_hit_tps:
        # هیچ TP جدیدی هیت نشده
        return

    # ============================================================
    # STEP 3: پردازش TP های هیت شده
    # ============================================================
    
    # پردازش به ترتیب (اولین TP اول)
    for tp_idx in sorted(newly_hit_tps):
        tp_price = float(tp_orders[tp_idx].get("price", 0))
        await adminReport(
            f"position manager:{ln()}\n🎯 {symbol}: TP{tp_idx + 1} hit at {tp_price}!"
        )

        # --- بررسی اینکه آیا آخرین TP است ---
        if tp_idx == len(tp_orders) - 1:
            # آخرین TP → بستن کل پوزیشن
            keys = {"api_key": apiKey, "api_secret": apiSecret}
            params = {
                "server": server,
                "keys": keys,
                "symbol": symbol,
            }

            await close_position(session, params)
            await adminReport(
                f"position manager:{ln()}\n🏁 {symbol}: Final TP{tp_idx + 1} hit ({tp_price}). "
                f"Position closed."
            )
            del signals[symbol]
            async with fileLock:
                atomic_save_json(tradesLogFile, signals)
            return

        # --- TP اول هیت شد ---
        if tp_idx == 0:
            # SL را به قیمت ورودی منتقل کن (ریسک فری)
            entry_price = float(signal.get("entry", 0))
            if entry_price > 0:
                res = await update_stop_loss(
                    session, symbol, entry_price,
                    apiKey, apiSecret, server
                )
                if res:
                    signal["SLNow"] = entry_price
                    await adminReport(
                        f"position manager:{ln()}\n🛡️ {symbol}: SL moved to entry price "
                        f"({entry_price}) → RISK FREE after TP1!"
                    )

            # کنسل کردن entry های باز (اگر باقی مانده)
            entries = signal.get("entries", [])
            for entry in entries:
                if not entry.get("filled") and not entry.get("cancelled"):
                    if entry.get("orderId"):
                        await cancel_order(
                            session, symbol,
                            entry["orderId"], apiKey, apiSecret, server
                        )
                    entry["cancelled"] = True
                    await adminReport(
                        f"position manager:{ln()}\n🗑️ {symbol}: Cancelled remaining entry "
                        f"{entry.get('variant')} at {entry.get('price')}"
                    )
            signal["openQty"] = 0.0

            signal["tpIndexHit"] = tp_idx + 1
            continue

        # --- TP های میانی (از دوم تا یکی مانده به آخر) ---
        if 0 < tp_idx < len(tp_orders) - 1:
            # SL را به TP قبلی منتقل کن
            prev_tp_price = float(tp_orders[tp_idx - 1].get("price", 0))
            if prev_tp_price > 0:
                res = await update_stop_loss(
                    session, symbol, prev_tp_price,
                    apiKey, apiSecret, server
                )
                if res:
                    signal["SLNow"] = prev_tp_price
                    await adminReport(
                        f"position manager:{ln()}\n🔁 {symbol}: SL moved to "
                        f"TP{tp_idx} ({prev_tp_price})"
                    )

            signal["tpIndexHit"] = tp_idx + 1
            continue


# ============================================================
# Scheduler (بدون تغییر)
# ============================================================

async def startMonitoring(session=None, apiKey=None, apiSecret=None, server=None):
    """Start async scheduler to monitor and sync signals with Bybit."""

    async def monitorWrapper():
        """Read signals from file and process them."""
        await processSignals(session, apiKey, apiSecret, server)

    # --- Align with interval start ---
    bybitTimeMS = await getBybitServerTimeMS(session, server)

    nextIntervalTime = (
        (int(bybitTimeMS // (fetchIntervalMinutes * 60)) + 1)
        * fetchIntervalMinutes
        * 60
    )
    delayUntilNext = nextIntervalTime - bybitTimeMS

    await adminReport(
        f"🕒 Waiting {delayUntilNext:.2f}s until next check interval..."
    )

    await asyncio.sleep(delayUntilNext)

    await adminReport(
        "🚀 Initial signal check starting now..."
    )
    await monitorWrapper()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(monitorWrapper, "interval", minutes=fetchIntervalMinutes)
    scheduler.start()

    await adminReport(
        "⏰ Monitoring scheduler started — running every "
        f"{fetchIntervalMinutes} minute(s)."
    )
    await asyncio.Event().wait()


# ─────────────────────────────
if __name__ == "__main__":

    async def main():
        async with aiohttp.ClientSession() as session:
            await startMonitoring(session, "demo_key", "demo_secret")

    asyncio.run(main())