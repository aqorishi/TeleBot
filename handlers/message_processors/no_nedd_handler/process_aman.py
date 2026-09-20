import re, os, uuid, sys
from dotenv import load_dotenv
from copy import deepcopy
from datetime import datetime, timezone
from utils.logger import adminReport
from sources.config import PFW_Premium, signal_template, PERSIANWATCHER


# # --- Load ENV ---
# load_dotenv()
# # --- Load ENV ---
# try:
#     load_dotenv()
#     AQ_BYBIT_API_KEY = os.getenv("AQ_BYBIT_API_KEY")
#     AQ_BYBIT_API_SECRET = os.getenv("AQ_BYBIT_API_SECRET")
# except Exception as e:
#     adminReport("Aman, API key or secret not loaded. Check your .env file.")
#     sys.exit(1)
    
# # Opera Browser Bybit Client (Demo)
# BYBIT = {
#     "api_key": AQ_BYBIT_API_KEY,
#     "api_secret": AQ_BYBIT_API_SECRET,
# }

decimal_places = 4  # تعداد اعشار موردنظر
format_num = lambda x: round(float(x), decimal_places)


def aman_clean_text(text: str) -> str:
    # 1. Replace numbering like "1. " with a comma
    text = re.sub(r"^\d+\.\s+", ",", text, flags=re.MULTILINE)

    # 2. Remove "$"
    text = text.replace("$", " ")

    # 3. Normalize numbers (remove commas inside numbers like 117,300 -> 117300)
    text = re.sub(r"(\d+),(\d+)", r"\1\2", text)

    # 4. Remove emojis
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002700-\U000027BF"
        "\U0001F900-\U0001F9FF"
        "\U00002600-\U000026FF"
        "]+",
        flags=re.UNICODE,
    )
    text = emoji_pattern.sub("", text)

    # 5. Remove spaces (but keep line breaks)
    text = re.sub(r"[ \t]+", "", text)

    # 6. Remove empty lines
    text = re.sub(r"\n+", "\n", text).strip()

    # 7. Remove "Disclaimer" and everything after
    text = re.split(r"Disclaimer", text, maxsplit=1)[0].strip()

    return text


def get_aman_signal(caption: str) -> dict | None:
    if not caption:
        return None

    # Normalize caption
    caption = caption.replace("\xa0", " ").strip()

    # # Check if it's a signal (must contain both TRADE and Disclaimer)
    # if not (re.search(r"TRADE", caption, re.IGNORECASE) and re.search(r"Disclaimer", caption, re.IGNORECASE)):
    #     return None  
    
    caption = aman_clean_text(caption)

    # Start from template
    signal = deepcopy(signal_template)
    signal["id"] = str(uuid.uuid4())
    # signal["keys"] = BYBIT
    signal["timestamp"] = datetime.now(timezone.utc).isoformat()
    signal["source"] = "Aman Crypto"
    signal["destination"] = PERSIANWATCHER
    signal["margin_mode"] = "isolated"
    signal["status"] = "new"

    # Extra (non-standard fields will be stored here)
    signal["extra"] = {}

    # --- 1. Pair / Symbol ---
    pair_match = re.search(r'TRADE\s*[-–]\s*([\w\s/]+)', caption, re.IGNORECASE)
    if pair_match:
        pair_raw = pair_match.group(1).strip()
        symbol = re.sub(r'[\s/]', '', pair_raw.upper())
        signal["symbol"] = symbol

    # --- 2. Position Type (Buy / Sell) ---
    type_match = re.search(r'Type\s*[-–:]\s*(LONG|SHORT|BUY|SELL)', caption, re.IGNORECASE)
    if type_match:
        side_raw = type_match.group(1).upper()
        if side_raw in ["LONG", "BUY"]:
            signal["side"] = "Buy"
        elif side_raw in ["SHORT", "SELL"]:
            signal["side"] = "Sell"

    # --- 3. Exchanges (non-standard, stored in extra) ---
    ex_match = re.search(r'TRADE\s*[-–]\s*[\w\s/]+\s*\(([^)]+)\)', caption, re.IGNORECASE)
    if ex_match:
        exchanges = [e.strip().upper() for e in re.split(r'[&|/,]', ex_match.group(1))]
        signal["extra"]["exchanges"] = exchanges

    # --- 4. Mode / Margin Mode ---
    mode_match = re.search(r'Mode\s*[-–]\s*(\w+)', caption, re.IGNORECASE)
    if mode_match:
        signal["margin_mode"] = mode_match.group(1).lower()

    # --- 5. Leverage ---
    leverage_match = re.search(r'Leverage\s*[-–]?\s*([^\n(]+)', caption, re.IGNORECASE)
    if leverage_match:
        leverage_caption = leverage_match.group(1)
        leverage_numbers = re.findall(r'(\d+(?:\.\d+)?)X?', leverage_caption)
        if leverage_numbers:
            signal["leverage"] = int(float(leverage_numbers[0]))

    # --- 6. Entry Zone ---
    zone_match = re.search(
        r'(buy|long|short|sell)\s*zone\s*[-–:]?\s*(\d+(?:\.\d+)?)\s*(?:to|-)\s*(\d+(?:\.\d+)?)',
        caption, re.IGNORECASE
    )
    if zone_match:
        z1 = str(format_num(zone_match.group(2)))
        z2 = str(format_num(zone_match.group(3)))
        signal["entry"] = [z1, z2]

    # --- 7. Targets ---
    target_section = re.search(r'(Target)[^\n]*\n([\s\S]*?)(?:Stop\s*loss|$)', caption, re.IGNORECASE)
    if target_section:
        targets = []
        mid_term_target = None
        for line in target_section.group(2).splitlines():
            clean_line = line.strip()
            if not clean_line:
                continue
            num_match = re.findall(r'(\d+(?:\.\d+)?)', clean_line)
            for nm in num_match:
                price = str(format_num(nm))
                targets.append(price)
                if "mid-term" in clean_line.lower() or "mid term" in clean_line.lower():
                    mid_term_target = price
        if targets:
            signal["takeProfits"] = targets
        if mid_term_target is not None:
            signal["extra"]["mid_term_target"] = mid_term_target

    # --- 8. Stop Loss ---
    sl_match = re.search(r'Stop\s*loss\s*(\d+(?:\.\d+)?)', caption, re.IGNORECASE)
    if sl_match:
        signal["stopLoss"] = str(format_num(sl_match.group(1)))

    return signal


def get_aman_signal_scalp(caption: str) -> dict | None:
    if not caption:
        return None

    caption = caption.replace("\xa0", " ").strip()
    caption = aman_clean_text(caption)

    # ===== پایه سیگنال از قالب استاندارد =====
    signal = deepcopy(signal_template)
    signal["id"] = str(uuid.uuid4())
    # signal["keys"] = BYBIT
    signal["timestamp"] = datetime.now(timezone.utc).isoformat()
    signal["source"] = "Aman Crypto Scalp"
    signal["destination"] = PERSIANWATCHER
    signal["status"] = "new"
    signal["extra"] = {}

    # --- 1. Pair Extraction ---
    first_line = caption.strip().splitlines()[0]
    
    pattern = r'^[^\w\s]?\s*([A-Z0-9]+.*?)\s*SCALP'
    m = re.search(pattern, first_line, flags=re.IGNORECASE)
    symbol = m.group(1).strip().split()[0].upper() if m else None
    signal["symbol"] = f"{symbol}USDT"

    # m = re.search(r'📣\s*(.*?)\s*SCALP', caption, flags=re.IGNORECASE)
    # signal["symbol"] = f"{m.group(1).strip().upper()}USDT" if m else None
    
    # --- 2. Type (LONG / SHORT / BUY / SELL) ---
    type_match = re.search(r'Type\s*[-–:]\s*(LONG|SHORT|BUY|SELL)', caption, re.IGNORECASE)
    if type_match:
        side_raw = type_match.group(1).upper()
        if side_raw in ["LONG", "BUY"]:
            signal["side"] = "Buy"
        elif side_raw in ["SHORT", "SELL"]:
            signal["side"] = "Sell"

    # --- 3. Leverage (اختیاری) ---
    leverage_match = re.search(r'Leverage\s*[-–]?\s*([\d.]+)', caption, re.IGNORECASE)
    if leverage_match:
        signal["leverage"] = int(float(leverage_match.group(1)))

    # --- 4. Entry Zone / Entry Price ---
    # پشتیبانی از: Entry price - $185 - 186
    entry_match = re.search(
        r'Entry\s*price\s*[-–:]?\s*\$?\s*(\d+(?:\.\d+)?)(?:\s*[-to]+\s*\$?\s*(\d+(?:\.\d+)?))?',
        caption,
        re.IGNORECASE
    )
    if entry_match:
        entries = []
        if entry_match.group(1):
            entries.append(str(format_num(entry_match.group(1))))
        if entry_match.group(2):
            entries.append(str(format_num(entry_match.group(2))))
        signal["entry"] = entries

    # --- 5. Targets ---
    target_section = re.search(
        r'Target\s*[-–:]?\s*([\s\S]*?)(?:Stop\s*Loss|SL|Disclaimer|$)',
        caption,
        re.IGNORECASE
    )
    if target_section:
        raw_targets = target_section.group(1)
        targets = re.findall(r'(\d+(?:\.\d+)?)', raw_targets)
        # if nums:
        #     signal["takeProfits"] = [str(format_num(n)) for n in nums]
        if targets:
            # تبدیل به float برای مرتب‌سازی عددی
            tps = [float(n) for n in targets]

            # مرتب‌سازی بر اساس جهت معامله
            if signal.get("side").lower() == "buy":
                tps = sorted(tps)          # صعودی برای خرید
            else:
                tps = sorted(tps, reverse=True)  # نزولی برای فروش

            # تبدیل نهایی به رشته فرمت‌شده
            signal["takeProfits"] = [str(format_num(tp)) for tp in tps]


    # --- 6. Stop Loss ---
    sl_match = re.search(
        r'(?:Stop\s*Loss|SL)[^\d]*(\d+(?:\.\d+)?)',
        caption,
        re.IGNORECASE
    )
    if sl_match:
        signal["stopLoss"] = str(format_num(sl_match.group(1)))

    # --- 7. Margin Mode (اختیاری) ---
    mode_match = re.search(r'Mode\s*[-–]\s*(\w+)', caption, re.IGNORECASE)
    if mode_match:
        signal["margin_mode"] = mode_match.group(1).lower()

    return signal


async def handle(caption: str):
    
    # Check if it's a signal (must contain both TRADE and Disclaimer)
    if re.search(r"TRADE", caption, re.IGNORECASE) and re.search(r"Disclaimer", caption, re.IGNORECASE) and re.search(r"Leverage", caption, re.IGNORECASE) and not (re.search(r"SCALP", caption, re.IGNORECASE)):
        signal = get_aman_signal(caption)
    elif re.search(r"SCALP TRADE", caption, re.IGNORECASE) and re.search(r"Disclaimer", caption, re.IGNORECASE):
        await adminReport("🕵️‍♂️ Detected Aman SCALP TRADE signal.")
        signal = get_aman_signal_scalp(caption)
    else:
        return None
    
    if signal:
        await adminReport(f"🔍 Aman Signal Extracted.")
        # await place_bybit_order(signal)
        return signal
    else:
        return None