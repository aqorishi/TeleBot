import asyncio
import aiohttp
import time
import asyncio
import hmac, hashlib
from utils.logger import adminReport
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from utils.bybit import get_bybit_server_time_ms


REST_HOST = "https://api-demo.bybit.com"
# WS_PUBLIC_URL = "wss://stream.bybit.com/v5/public/linear"
# CATEGORY_DEFAULT = "linear"
# REFRESH_INTERVAL = 10 # seconds


async def do_monitoring(api_key, api_secret):
    # فانکشن اصلی مانیتورینگ
    await adminReport("Monitoring task running...(internal is 30s)")

async def do_checking():
    # مثال فانکشن دوم
    await adminReport("Checking task running...(internal is 60s)")
    

async def sign_request(session, api_secret: str, api_key: str, mode: str) -> dict:
    """Add signature to request params"""
    params = {
            "api_key": api_key,
            "category": "linear",
            "settleCoin" : "USDT",
            "timestamp": await get_bybit_server_time_ms(session=session)
            }

    # 1) Add timestamp
    # params["api_key"] = api_key
    # params["timestamp"] = await get_bybit_server_time_ms(session=session)

    # 2) Build query string
    qs = "&".join([f"{k}={v}" for k, v in sorted(params.items())])

    # 3) Create signature
    signature = hmac.new(
        api_secret.encode("utf-8"),
        qs.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    # 4) Add sign to params
    params["sign"] = signature
    return params

    
# ========== Helpers ==========
async def fetch_positions_and_orders(session, api_key, api_secret):
    await adminReport("Fetching positions and orders...")
    try:
        # Sign request & fetch positions
        signed_params = await sign_request(session, api_secret, api_key, mode = "positions")
        async with session.get(f"{REST_HOST}/v5/position/list", params=signed_params) as resp:
            positions = await resp.json()

        # Sign request & fetch orders
        signed_params = await sign_request(session, api_secret, api_key, mode = "orders")
        async with session.get(f"{REST_HOST}/v5/order/realtime", params=signed_params) as resp:
            orders = await resp.json()

        # Check for errors in response
        if positions.get("retCode") != 0:
            print(f"Error in API response: Positions: {positions}")
        else:
            # print(f"Fetched positions: {positions}")
            for pos in positions["result"]["list"]:
                print("Symbol:", pos["symbol"])
                print("Side:", pos["side"])
                print("Size:", pos["size"])
                print("Entry Price:", pos["avgPrice"])
                print("Mark Price:", pos["markPrice"])
                print("Unrealised PnL:", pos["unrealisedPnl"])
                print("Stop Loss:", pos["stopLoss"])
                print("-" * 40)

            
        if orders.get("retCode") != 0:
            print(f"Error in API response: Orders: {orders}")
        else:
            # print(f"Fetched orders: {orders}")
            for order in orders["result"]["list"]:
                print("Order ID:", order["orderId"])
                print("Symbol:", order["symbol"])
                print("Side:", order["side"])
                print("Order Type:", order["orderType"])
                print("Price:", order["price"])
                print("Quantity:", order["qty"])
                print("Status:", order["orderStatus"])
                print("-" * 40)


        
        return positions, orders
    except Exception as e:
        await adminReport(f"Error fetching positions/orders: {e}")
        return None, None


# async def sign_request(session, api_secret: str, api_key: str, extra_params: dict = None) -> dict:
#     """Add signature to request params"""
#     params = {
#         "api_key": api_key,
#         "timestamp": await get_bybit_server_time_ms(session=session)
#     }

#     # اضافه کردن پارامترهای اضافی مثل category, settleCoin, symbol ...
#     if extra_params:
#         params.update(extra_params)

#     # Build query string مرتب شده بر اساس کلیدها
#     qs = "&".join([f"{k}={v}" for k, v in sorted(params.items())])

#     # Create signature
#     signature = hmac.new(
#         api_secret.encode("utf-8"),
#         qs.encode("utf-8"),
#         hashlib.sha256
#     ).hexdigest()

#     # Add sign to params
#     params["sign"] = signature
#     return params


# async def fetch_positions_and_orders(session, api_key, api_secret):
#     await adminReport("📡 Fetching positions and orders...")
#     try:
#         # ---------- Positions ----------
#         pos_params = {"api_key": api_key,"category": "linear", "settleCoin": "USDT", "timestamp": await get_bybit_server_time_ms(session=session)}
#         signed_params = await sign_request(session, api_secret, api_key, extra_params=pos_params)

#         async with session.get(f"{REST_HOST}/v5/position/list", params=signed_params) as resp:
#             positions = await resp.json()

#         # ---------- Orders ----------
#         order_params = {"api_key": api_key,"category": "linear", "timestamp": await get_bybit_server_time_ms(session=session)}
#         signed_params = await sign_request(session, api_secret, api_key, extra_params=order_params)

#         async with session.get(f"{REST_HOST}/v5/order/realtime", params=signed_params) as resp:
#             orders = await resp.json()

#         # ---------- Validate response ----------
#         if positions.get("retCode") != 0:
#             await adminReport(f"❌ Error in API response: Positions: {positions}")
#         elif orders.get("retCode") != 0:
#             await adminReport(f"❌ Error in API response: Orders: {orders}")
#         else:
#             print(f"\n\n🔴 Fetched positions: {positions}")
#             print(f"\n\n🔴 Fetched orders: {orders}")
        
#         return positions, orders

#     except Exception as e:
#         await adminReport(f"⚠️ Error fetching positions/orders: {e}")
#         return None, None



async def start_monitoring(session, api_key, api_secret):
    scheduler = AsyncIOScheduler()

    # session = aiohttp.ClientSession()

    scheduler.add_job(
        fetch_positions_and_orders,
        "interval",
        minutes=5,
        id="fetch_positions_and_orders_job",
        args=[session, api_key, api_secret]
    )

    # scheduler.add_job(
    #     do_checking,
    #     "interval",
    #     minutes=1,
    #     id="checking_job"
    # )

    scheduler.start()
    await adminReport("⏰ Scheduler started inside start_monitoring...")

    try:
        await asyncio.Event().wait()
    finally:
        await session.close()

 