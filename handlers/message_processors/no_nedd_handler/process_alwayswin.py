import re, os, uuid, sys
from dotenv import load_dotenv
from copy import deepcopy
from datetime import datetime, timezone
from utils.logger import adminReport
from sources.config import PFW_Premium, signal_template, PERSIANWATCHER


last_signal = deepcopy(signal_template)
# last_signal["timestamp"] = "1970-01-01T00:00:00+00:00"  # initial old timestamp
# last_signal["symbol"] = "symbol"  # initial empty symbol


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


def parse_iso_timestamp(val):
    """
    Accepts:
      - ISO string like "2025-10-19T12:34:56" or "2025-10-19T12:34:56Z" or with offset
      - a datetime object
      - an int/float epoch (seconds)
      - None -> returns None

    Returns: datetime (tz-aware UTC if possible) or None
    """
    if val is None:
        return None

    # already a datetime
    if isinstance(val, datetime):
        # normalize: remove microseconds for parity with original intent
        return val.replace(microsecond=0)

    # numeric epoch (seconds)
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(float(val), tz=timezone.utc).replace(microsecond=0)

    # assume string
    if isinstance(val, str):
        s = val.strip()
        # handle trailing Z (UTC)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            # fallback: try parsing common formats (very simple fallback)
            # try without timezone
            try:
                dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
            except Exception:
                # Last resort: return None or raise — here we return None
                return None
        # if naive datetime, make it UTC to be consistent (optional)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.replace(microsecond=0)

    # unknown type
    return None



def get_alwayswin_signal(caption: str) -> dict | None:
    if not caption:
        return None

    caption = caption.replace("\xa0", " ").strip()

    # # Check required keywords
    # if not (re.search(r"Entries?", caption, re.IGNORECASE) and re.search(r"(?:SL|STOP\s*LOSS)", caption, re.IGNORECASE)):
    #     return None

    # Start from template
    signal = deepcopy(signal_template)
    signal["id"] = str(uuid.uuid4())
    # signal["keys"] = BYBIT
    signal["timestamp"] = datetime.now(timezone.utc).isoformat()
    signal["source"] = "AlwaysWin"
    signal["destination"] = PERSIANWATCHER
    signal["margin_mode"] = "isolated"

    signal["status"] = "new"

    # Symbol + Side
    symbol_match = re.search(r"([A-Z]+\/USDT)\s+(LONG|SHORT)", caption, re.IGNORECASE)
    if symbol_match:
        signal["symbol"] = symbol_match.group(1).replace("/", "").upper()
        side_raw = symbol_match.group(2).upper()
        signal["side"] = "Buy" if side_raw == "LONG" else "Sell"

    # Leverage
    leverage_match = re.search(r"Leverage\s+(\d+)x?", caption, re.IGNORECASE)
    if leverage_match:
        signal["leverage"] = int(leverage_match.group(1))

    # Entries
    entry_match = re.findall(r"Entries?\s+([\d.]+)", caption, re.IGNORECASE)
    if entry_match:
        signal["entry"] = [str(format_num(e)) for e in entry_match]

    # Targets
    targets = re.findall(r"Target\s*\d*\s*([\d.]+)", caption, re.IGNORECASE)
    # if targets:
        # signal["takeProfits"] = [str(format_num(t)) for t in targets]
    if targets:
        tps = [float(n) for n in targets]

        if signal["side"].lower() == "buy":
            tps = sorted(tps)
        else:
            tps = sorted(tps, reverse=True)

        signal["takeProfits"] = [str(format_num(tp)) for tp in tps]


    # Stop loss
    sl_match = re.search(r"(?:SL|STOP\s*LOSS)[:\s]*([\d.]+)", caption, re.IGNORECASE)
    if sl_match:
        signal["stopLoss"] = str(format_num(sl_match.group(1)))

    return signal


async def handle(caption: str):
    global last_signal
    
    current_time = datetime.now(timezone.utc).isoformat()
    # await adminReport(f"🔔 Complete time is {current_time}")

    # Check if it's a signal (must contain both Entries and STOP LOSS)
    if not (re.search(r"Entries?", caption, re.IGNORECASE) and re.search(r"(?:SL|STOP\s*LOSS)", caption, re.IGNORECASE)):
        return None
    
    signal = get_alwayswin_signal(caption)
    if signal:
        symbol = signal.get("symbol", "unknown")

        # Change to datetime objects without microseconds for comparison
        current_signal_timestamp = parse_iso_timestamp(signal.get("timestamp"))
        last_signal_timestamp = parse_iso_timestamp(last_signal.get("timestamp"))
        
        # handle parsing failures
        if current_signal_timestamp is None:
            await adminReport(f"⚠️ Signal {symbol}: invalid or missing timestamp in current signal: {signal.get('timestamp')!r}")
            return None

        if last_signal_timestamp is None:
            await adminReport(f"⚠️ Signal {symbol}: invalid or missing timestamp in last signal: {last_signal.get('timestamp')!r}")
            return None

        await adminReport(f"🕵️‍♂️ {current_signal_timestamp=} \n {last_signal_timestamp=}")

        # Check for duplicate
        if  (signal["symbol"] == last_signal["symbol"]) and (current_signal_timestamp == last_signal_timestamp):
            await adminReport("⏩ Duplicate AlwaysWin signal detected, skipping...")
            return None
        
        await adminReport(f"🔍 AlwaysWin Signal Extracted.")
        # await place_bybit_order(signal)
        last_signal = signal
        return signal
    else:
        return None

        # current_signal_timestamp = datetime.fromisoformat(str(signal["timestamp"])).replace(microsecond=0)
        # last_signal_timestamp = datetime.fromisoformat(last_signal["timestamp"]).replace(microsecond=0)    