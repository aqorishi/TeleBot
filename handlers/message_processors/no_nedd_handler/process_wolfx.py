import re
from utils.logger import adminReport


def get_wolf_signal(caption: str) -> dict:
    if not caption:
        return None

    # نرمال‌سازی متن
    caption = caption.replace("\xa0", " ").strip()

    # # چک کردن اینکه متن سیگنال هست یا نه
    # if not (re.search(r"Enter", caption, re.IGNORECASE) and re.search(r"SL", caption, re.IGNORECASE)):
    #     return None  # اگر سیگنال نبود    
    
    result = {
        'signal': 'WolfX Trade Signal'
    }

    # --- Pair ---
    pair_match = re.search(r"([A-Z]{3,5})/([A-Z]{3,5})", caption, re.IGNORECASE)
    if pair_match:
        result["pair"] = pair_match.group(1).upper() + pair_match.group(2).upper()

    # --- Side (Buy/Sell) ---
    # حالت اول: کنار جفت ارز آمده (BTC/USDT 📈 BUY)
    side_match = re.search(r"(?:BUY|SELL|LONG|SHORT)", caption.split("\n")[0], re.IGNORECASE)
    # حالت دوم: خط جداگانه (📉SELL)
    if not side_match:
        side_match = re.search(r"(?:BUY|SELL|LONG|SHORT)", caption, re.IGNORECASE)

    if side_match:
        side_raw = side_match.group(0).upper()
        if side_raw in ["BUY", "LONG"]:
            result["side"] = "Buy"
        elif side_raw in ["SELL", "SHORT"]:
            result["side"] = "Sell"

    # --- Entry ---
    entry_match = re.search(r"Enter (above|below):?\s*([\d.]+)", caption, re.IGNORECASE)
    if entry_match:
        result["entry"] = [str(entry_match.group(2))]

    # --- Targets ---
    targets = re.findall(r"TP\d?\s*([\d.]+)", caption, re.IGNORECASE)
    if targets:
        result["targets"] = [str(tp) for tp in targets]

    # --- Stop Loss ---
    sl_match = re.search(r"SL\s*([\d.]+)", caption)
    if sl_match:
        result["stop_loss"] = str(sl_match.group(1))

    # --- Leverage ---
    lev_match = re.search(r"Leverage\s*(\d+)[xX]", caption)
    if lev_match:
        result["leverage"] = [str(lev_match.group(1))]

    return result


async def handle(caption: str):
    
    # Check if it's a signal (must contain both Enter and SL)
    if not (re.search(r"Enter", caption, re.IGNORECASE) and re.search(r"SL", caption, re.IGNORECASE)):
        return None

    signal = get_wolf_signal(caption)
    if signal:
        await adminReport(f"🔍 WolfX Signal Extracted.")
        # await place_bybit_order(signal)
        return signal
    else:
        return None
    