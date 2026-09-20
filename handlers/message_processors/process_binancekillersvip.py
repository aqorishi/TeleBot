import re, os, uuid, sys
from dotenv import load_dotenv
from copy import deepcopy
from datetime import datetime, timezone
from utils.logger import adminReport
from sources.config import PERSIANFINANCIALWATCHER, signal_template, PERSIANWATCHER
from utils.bybit import placeBybitOrder



decimal_places = 4  # Number of decimal places for formatting numbers
format_num = lambda x: round(float(x), decimal_places)
telegramSignalDestination = PERSIANFINANCIALWATCHER  # Destination channel for signals


def getBinanceKillersSignal(caption: str) -> dict | None:
    if not caption:
        return None

    # Normalize text
    caption = caption.replace("\xa0", " ").strip()

    # Check if the text is a signal (must contain ENTRY, STOP LOSS, and COIN)
    caption = re.sub(r"\*\*", "", caption)
    caption = caption.replace(',', '')

    # Remove decorative lines
    lines = [line.strip() for line in caption.strip().splitlines() if line.strip() and '—' not in line and '➖' not in line]

    # Start with the template
    signal = deepcopy(signal_template)
    signal["id"] = str(uuid.uuid4())
    # signal["keys"] = BYBIT
    signal["timestamp"] = datetime.now(timezone.utc).isoformat()
    signal["source"] = "Binance Killers"
    signal["destination"] = telegramSignalDestination
    signal["status"] = "new"
    signal["margin_mode"] = "isolated"
    signal["extra"] = {}

    for line in lines:
        # --- 1. Symbol & Leverage ---
        if line.upper().startswith("COIN:"):
            coin_match = re.search(r"COIN:\s*\$?([A-Z]+)[/\\]([A-Z]+)", line, re.IGNORECASE)
            if coin_match:
                symbol = coin_match.group(1).upper() + coin_match.group(2).upper()
                signal["symbol"] = symbol

            lev_match = re.search(r"\(([\d–\-xX]+)\)", line)
            if lev_match:
                lev_caption = lev_match.group(1).lower().replace('x', '').replace('–', '-')
                try:
                    if '-' in lev_caption:
                        l1, l2 = map(int, lev_caption.split('-'))
                        signal["leverage"] = l1  # محدوده → فقط اولی رو بذاریم
                        signal["extra"]["leverage_range"] = [l1, l2]
                    else:
                        signal["leverage"] = int(lev_caption)
                except:
                    pass

        # --- 2. Direction ---
        elif line.upper().startswith("DIRECTION:"):
            direction_match = re.search(r"DIRECTION:\s*(LONG|SHORT)", line, re.IGNORECASE)
            if direction_match:
                side_raw = direction_match.group(1).upper()
                signal["side"] = "Buy" if side_raw == "LONG" else "Sell"

        # --- 3. Entry ---
        elif line.upper().startswith("ENTRY:"):
            entry_match = re.findall(r"\d+\.\d+|\d+", line)
            if entry_match:
                signal["entry"] = [str(format_num(e)) for e in entry_match]

        # --- 4. Targets ---
        elif line.upper().startswith("TARGETS:"):
            targets = re.findall(r"\d+\.\d+|\d+", line)
            
            if targets:
                tps = [float(n) for n in targets]

                if signal["side"].lower() == "buy":
                    tps = sorted(tps)
                else:
                    tps = sorted(tps, reverse=True)
                    
            signal["takeProfits"] = [str(format_num(t)) for t in targets]
            # if targets:
            #     signal["takeProfits"] = [str(format_num(t)) for t in targets]

        # --- 5. Stop Loss ---
        elif line.upper().startswith("STOP LOSS:"):
            sl_match = re.search(r"\d+\.\d+|\d+", line)
            if sl_match:
                signal["stopLoss"] = str(format_num(sl_match.group()))

    return signal


# --- Main Handler --- Google Chrome
async def handle(caption: str):
    
    # Check if it's a signal (must contain both ENTRY and STOP LOSS and COIN)
    if not (re.search(r"ENTRY", caption, re.IGNORECASE) and re.search(r"STOP LOSS", caption, re.IGNORECASE) and re.search(r"COIN", caption, re.IGNORECASE)):
        return None
    
    signal = getBinanceKillersSignal(caption)
    if signal:
        await adminReport(f"🔍 Binance Killers Signal Extracted.")
        await placeBybitOrder(signal)
        return signal
    else:
        return None
