import os, sys
from dotenv import load_dotenv
import inspect

def ln():
    return inspect.currentframe().f_back.f_lineno

# --- Load ENV ---
load_dotenv()
try:
    API_KEY = os.getenv("MQ_BYBIT_API_KEY")
    API_SECRET = os.getenv("MQ_BYBIT_API_SECRET")
except Exception as e:
    print(" ❌ API key or secret not loaded. Check your .env file.")
    sys.exit(1)

# API Keys for OpenAI
openai_api_key = os.getenv("openai_api_key")

#Telegram Bot and API Config
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")

#Bale Bot and API Config
baleToken = os.getenv("BALE_TOKEN")
baleChatID = os.getenv("BALE_CHAT_ID")


# Session paths
SESSION_DIR = os.getenv("SESSION_DIR", "bot/sessions")
BOT_SESSION = os.path.join(SESSION_DIR, "bot")
ANALYZER_SESSION = os.path.join(SESSION_DIR, "analyzer")

# Trading Parameters
LEVERAGE = int(os.getenv("LEVERAGE", 5))  # Default leverage if not set in .env
QTY = int(os.getenv("QTY", 1000))  # Default quantity if not set in .env
trade_percent = "0.02"  # Percentage of balance to use per trade

# --------------- Instant Parameters ---------------
LOG_DIR = "/home/botuser/bot/logs"
FOOTER_LINK = '@PersianFinancialWatcher'
line = '➖' * 15 # Line separator for messages
CAPTION_HEADER = f'{("✅  ناظر مالی پارسی")}'
CAPTION_HEADER_BASE = "✅  ناظر مالی پارسی"


# --------------- Telegram Channel IDs for monitoring ---------------
ADMIN = -1002061989413
ALWAYS_WIN = -1001288549616
AMAN = -1001744711450 
BINANCEKILLERS = -1001220789766
BINANCEKILLERS_VIP = -1001556597544
FEAR_AND_GREED = -1002250488311
FED_RUSSIAN_VIP = -1001701261905
PERSIANWATCHER = -1002676558853 # Channel
# PERSIANWATCHER = -1004254150486 # Group
PERSIANFINANCIALWATCHER = -1002569014258
PFW_Robot = -4669780859
PFW_Premium = -1002174598690
WATCHER_GURU = -1001556054753
WOLFX = -1001394941879


ANALYZER_REPORTER = PERSIANFINANCIALWATCHER
PFW_REPORTER = ADMIN

# Source channels to monitor, can be specified by their numeric ID or username with @
SOURCE_CHANNELS = {
    "binancekillers": BINANCEKILLERS,
    "binancekillers_VIP": BINANCEKILLERS_VIP,
    "fearandgreed": FEAR_AND_GREED,
    "guru": WATCHER_GURU,
    "pfw": PFW_Robot,
    "PFW_Premium": PFW_Premium,
}
# SOURCE_CHANNELS = {
#     "alwayswin": ALWAYS_WIN,
#     "aman": AMAN,
#     "binancekillers": BINANCEKILLERS,
#     "binancekillers_VIP": BINANCEKILLERS_VIP,
#     "fearandgreed": FEAR_AND_GREED,
#     "fed_russian_vip": FED_RUSSIAN_VIP,
#     "guru": WATCHER_GURU,
#     "pfw": PFW_Robot,
#     "PFW_Premium": PFW_Premium,
#     "wolfx": WOLFX,
# }

BYBIT = {
    "api_key": API_KEY,
    "api_secret": API_SECRET,
}

bybit_main = "https://api.bybit.com"
bybit_demo = "https://api-demo.bybit.com"
bybit_testnet = "https://api-testnet.bybit.com"

demo = True  # Set to False for real trading

exchangeURL = bybit_demo if demo else bybit_main

# --------------- Signal Template ---------------
signal_template = {
    "id": None,                     # Unique ID for the signal (optional: uuid4)
    "variant": None,                # main / alt1 / alt2 ...
    "index": None,                  # Original index of entry in input signal
    "session":None,                 # Exchange Session
    "keys": BYBIT,                  # API keys for exchange session
    "exchangeURL": exchangeURL,     # Exchange server URL
    "demo": bool,                   # Real or Demo
    "timestamp": None,              # Signal generation time
    "source": "",                   # Signal source: Aman, BK, Fed, etc.
    "destination": "",              # Destination to send the signal
    "status": "new",                # new, placed, filled, closed, cancelled

    # Trade info
    "category": "linear",           # linear / inverse / spot
    "symbol": None,                 # e.g., "BTCUSDT"
    "side": None,                   # Buy / Sell
    "orderType": "Limit",           # Market / Limit
    "leverage": LEVERAGE,           # Leverage
    "margin_mode": "isolated",      # Margin Mode: cross / isolated
    "qtyPercent": trade_percent,    # % of balance to use
    "qty": None,                    # Final calculated base qty
    "entry": [],                    # Entry prices
    "execPrice": "",                # Actual executed price
    "minQty": "",                   # Minimum order quantity
    "maxQty": "",                   # maximum order quantity
    "step": "",                     # Quantity step size
    "maxTrailing": "",              # Maximum trailing stop distance

    # Risk management
    "stopLoss": None,               # SL price
    "takeProfits": [],              # List of TP prices
    "riskReward": None,             # Optional R:R ratio
    "reduceOnly": False,            # Optional reduce only flag
    "closeOnTrigger": False ,       # Optional close on trigger flag
    "trailingStop": None,           # Optional trailing stop price

    # Execution result
    "order_id": None,               # Main order id after placement
    "order_timestamp": None,        # Time of order placement
    "extra_orders": [],             # TP/SL order ids if placed separately
    "error": None,                  # Error message if failed
}

# Days mapping
DAYSMAP = {
    "Saturday": "شنبه",
    "Sunday": "یکشنبه",
    "Monday": "دوشنبه",
    "Tuesday": "سه‌شنبه",
    "Wednesday": "چهارشنبه",
    "Thursday": "پنجشنبه",
    "Friday": "جمعه",
}

# Months mapping
MONTHSMAP = {
    1: "فروردین",
    2: "اردیبهشت",
    3: "خرداد",
    4: "تیر",
    5: "مرداد",
    6: "شهریور",
    7: "مهر",
    8: "آبان",
    9: "آذر",
    10: "دی",
    11: "بهمن",
    12: "اسفند",
}

# Persian digits mapping
PERSIANDIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
