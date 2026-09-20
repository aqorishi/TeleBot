import re, os, uuid, sys, unicodedata
from dotenv import load_dotenv
from copy import deepcopy
from datetime import datetime, timezone
from utils.logger import adminReport
from sources.config import PFW_Premium, signal_template, PERSIANWATCHER


# # --- Load ENV ---
# try:
#     load_dotenv()
#     MQ_BYBIT_API_KEY = os.getenv("MQ_BYBIT_API_KEY")
#     MQ_BYBIT_API_SECRET = os.getenv("MQ_BYBIT_API_SECRET")
# except Exception as e:
#     adminReport("AlwaysWin, API key or secret not loaded. Check your .env file.")
#     sys.exit(1)
    

# BYBIT = {
#     "api_key": MQ_BYBIT_API_KEY,
#     "api_secret": MQ_BYBIT_API_SECRET,
# }


decimal_places = 4  # Number of decimal places for formatting numbers
format_num = lambda x: round(float(x), decimal_places)


def get_fedrussian_signal(caption: str) -> dict | None:
    caption = unicodedata.normalize("NFKC", caption)
    caption = caption.replace('\u200e', '').replace('\u200f', '').replace('\xa0', ' ')
    
    if not caption:
        return None

    # # چک کردن اینکه متن سیگنال هست یا نه
    # if not (re.search(r"Entry", caption, re.IGNORECASE) and re.search(r"RISK", caption, re.IGNORECASE)):
    #     return None

    # شروع از قالب استاندارد
    signal = deepcopy(signal_template)
    signal["id"] = str(uuid.uuid4())
    # signal["keys"] = BYBIT
    signal["timestamp"] = datetime.now(timezone.utc).isoformat()
    signal["source"] = "Fed Russian"
    signal["destination"] = PERSIANWATCHER
    signal["status"] = "new"
    signal["margin_mode"] = "isolated"
    signal["extra"] = {}

    # --- 1. Pair ---
    pair_match = re.search(r"Pair:\s*(?:[*\s]*)\$?([A-Z]+)[*/\s]+([A-Z]+)", caption)
    if pair_match:
        signal["symbol"] = f"{pair_match.group(1).upper()}{pair_match.group(2).upper()}"

    # --- 2. Direction ---
    direction_match = re.search(r"Direction:\s*(LONG|SHORT)", caption, re.IGNORECASE)
    if direction_match:
        side_raw = direction_match.group(1).upper()
        signal["side"] = "Buy" if side_raw == "LONG" else "Sell"

    # --- 3. Leverage ---
    lev_match = re.search(r"Leverage\s*:\s*(\d+)[xX]", caption)
    if lev_match:
        signal["leverage"] = int(lev_match.group(1))

    # --- 4. Position Size (در extra ذخیره میشه) ---
    pos_match = re.search(r"Position Size:\s*([\d\.\-\s%]+)", caption)
    if pos_match:
        signal["extra"]["position_size"] = pos_match.group(1).strip()

    # --- 5. Trade Type (در extra ذخیره میشه) ---
    type_match = re.search(r"Trade Type:\s*(\w+)", caption)
    if type_match:
        signal["extra"]["trade_type"] = type_match.group(1).strip().upper()

    # --- 6. Entry ---
    entry_match = re.search(r"Entry:\s*([^\n]+)", caption)
    if entry_match:
        nums = re.findall(r"[\d.]+", entry_match.group(1))
        if nums:
            signal["entry"] = [str(format_num(e)) for e in nums]

    # --- 7. Stop Loss ---
    sl_match = re.search(r"(?:SL|STOP\s+LOSS)\s*:\s*([\d.]+)", caption, re.IGNORECASE)
    if sl_match:
        signal["stopLoss"] = str(format_num(sl_match.group(1)))

    # --- 8. Targets ---
    targets_match = re.search(r"(?:TARGETS|Targets)\s*:\s*([^\n]+)", caption, re.IGNORECASE)
    if targets_match:
        raw_targets = re.findall(r"[\d.]+", targets_match.group(1))
        if raw_targets:
            signal["takeProfits"] = [str(format_num(t)) for t in raw_targets]

    # --- 9. Risk (در extra ذخیره میشه) ---
    risk_match = re.search(r"RISK:\s*([^\n]+)", caption)
    if risk_match:
        signal["extra"]["risk"] = risk_match.group(1).strip()

    return signal


async def handle(caption: str):
    
    # Check if it's a signal (must contain both Entry and RISK)
    if not (re.search(r"Entry", caption, re.IGNORECASE) and re.search(r"RISK", caption, re.IGNORECASE)):
        return None
    
    signal = get_fedrussian_signal(caption)
    if signal:
        await adminReport(f"🔍 Fed_Russian Signal Extracted.")
        # await place_bybit_order(signal)
        return signal
    else:
        return None
    