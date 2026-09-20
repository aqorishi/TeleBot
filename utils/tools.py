import logging, math, json, jdatetime, textwrap
from aiogram.exceptions import TelegramBadRequest
from utils.logger import adminReport
from sources.config import CAPTION_HEADER, FOOTER_LINK, line, openai_api_key
from sources.config import PERSIANDIGITS, MONTHSMAP, DAYSMAP
from openai import OpenAI
from datetime import datetime

ai_client = OpenAI(api_key=openai_api_key)

# --- Setup logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



def formatPersianParagraph(text, width=42):

    text = " ".join(text.split())

    lines = textwrap.wrap(
        text, width=width, break_long_words=False, break_on_hyphens=False
    )

    return "\n".join(lines)


def formatShamsiDate(date: jdatetime.date) -> str:
    weekday_en = date.strftime("%A")
    weekday_fa = DAYSMAP.get(weekday_en, weekday_en)

    day_num = str(date.day).zfill(2).translate(PERSIANDIGITS)
    month_fa = MONTHSMAP[date.month]
    year_fa = str(date.year).translate(PERSIANDIGITS)

    return f"{weekday_fa} {day_num} {month_fa} {year_fa}"


def gregorianToJalali(dateString: str) -> str:
    dt = datetime.strptime(dateString, "%B %d, %Y")
    jdt = jdatetime.date.fromgregorian(date=dt.date())

    weekday = DAYSMAP[dt.strftime("%A")]
    day = str(jdt.day).translate(PERSIANDIGITS)
    # day = f"{jdt.day:02d}".translate(PERSIANDIGITS)
    month = MONTHSMAP[jdt.month]
    year = str(jdt.year).translate(PERSIANDIGITS)

    return f"{weekday} {day} {month} {year}"


async def _aio_get(session, server: str, params: dict = None, headers: dict = None):
    try:
        async with session.get(
            server, params=params, headers=headers, timeout=20
        ) as resp:
            text = await resp.text()
            try:
                return json.loads(text)
            except Exception:
                await adminReport(f"⚠️ Non-JSON response from {server}: {text}")
                return None
    except Exception as e:
        await adminReport(f"❌ HTTP GET failed {server}: {e}")
        return None


async def get_current_price(signal) -> float:
    """Get current last price for symbol (async)."""
    session = signal.get("session")
    symbol = signal.get("symbol")

    baseURL = signal.get("exchangeURL")
    endPoint = "/v5/market/tickers"
    url = baseURL + endPoint

    params = {"category": "linear", "symbol": symbol.upper()}

    res = await _aio_get(session, url, params=params)

    try:
        return float(res["result"]["list"][0]["lastPrice"])
    except Exception as e:
        await adminReport(f"❌ Error fetching price for {symbol}: {e}")
        return 0.0


async def signalReport(signal: dict):
    parts = []

    parts.append(f"{CAPTION_HEADER}\n{doRTL(line)}\n")

    # Headers and Pair
    parts.append("🚀 *PREMIUM SIGNAL ALERT* 🚀")
    # parts.append(f"📍 Source: *{signal.get('source', 'Unknown')}*")
    parts.append("")
    parts.append(f"📍 Pair: `{signal.get('symbol', '-')}`")

    # Side and Image
    side_icon = ""
    # image_path = "/home/botuser/bot/sources/images/neutral.jpg"
    image_path = ""
    if "side" in signal:
        if signal["side"] == "Buy":
            side_icon = "📈"
            image_path = "/opt/tradebot/sources/images/buy.jpg"
        elif signal["side"] == "Sell":
            side_icon = "📉"
            image_path = "/opt/tradebot/sources/images/sell.jpg"
        parts.append(f"{side_icon} Side: *{signal['side']}*")

    # Leverage
    if "leverage" in signal:
        lev = str(signal["leverage"])
        parts.append(f"⚡ Leverage: *{lev}x*")
    parts.append("")

    # Entry
    if "entry" in signal:
        entries = (
            signal["entry"] if isinstance(signal["entry"], list) else [signal["entry"]]
        )
        parts.append("🎯 Entry: " + " - ".join([f"`{e}`" for e in entries]))
    parts.append("")

    # Targets (takeProfits)
    if "takeProfits" in signal:
        targets = (
            signal["takeProfits"]
            if isinstance(signal["takeProfits"], list)
            else [signal["takeProfits"]]
        )
        target_str = "\n".join([f"🎯 TP{i+1}: `{t}`" for i, t in enumerate(targets)])
        parts.append(target_str)
    parts.append("")

    # Stop loss
    if "stopLoss" in signal:
        parts.append(f"⛔ Stop Loss: `{signal['stopLoss']}`")

    # Adding footer
    parts.append("")
    footer = FOOTER_LINK
    parts.append(footer)

    # Final caption
    caption = "\n".join(parts)

    return caption, image_path


async def normalize_signal_to_current_price_maxlen(signal: dict) -> dict:
    """
    Normalize all entry, stopLoss, and takeProfits values:
    - Scale to the same order-of-magnitude as current_price
    - Ensure all numbers have the same total length (integer + decimal) as the largest number
    - Maintain the maximum decimal places found in original data or current_price
    """
    # Collect original numbers
    entry_strs = signal.get("entry", [])
    stop_str = signal.get("stopLoss")
    tp_strs = signal.get("takeProfits", [])

    currentPrice = await get_current_price(signal)

    original_strs = list(entry_strs) + ([stop_str] if stop_str else []) + list(tp_strs)

    # Convert to float
    values = []
    for s in original_strs:
        try:
            values.append(float(s))
        except:
            values.append(0.0)

    # Determine target exponent based on current_price
    target_exp = math.floor(math.log10(abs(currentPrice))) if currentPrice != 0 else 0

    # Scale each value to target exponent
    scaled = []
    for v in values:
        if v == 0:
            scaled.append(0.0)
        else:
            exp_v = math.floor(math.log10(abs(v)))
            factor = 10 ** (target_exp - exp_v)
            scaled.append(v * factor)

    # Determine max decimals from original strings and current_price
    dec_lengths = []
    total_lengths = []
    for s, v in zip(original_strs, scaled):
        # decimal length
        if isinstance(s, str) and "." in s:
            dec_len = len(s.split(".")[1])
        else:
            dec_len = 0
        dec_lengths.append(dec_len)
        # total length (integer + decimal, ignoring sign)
        total_len = len(str(int(v))) + dec_len
        total_lengths.append(total_len)

    # include current_price
    s_cp = str(currentPrice)
    if "." in s_cp:
        dec_lengths.append(len(s_cp.split(".")[1]))
    else:
        dec_lengths.append(0)
    total_lengths.append(len(str(int(currentPrice))) + dec_lengths[-1])

    max_decimals = max(dec_lengths)
    max_total_len = max(total_lengths)

    # Adjust each number to match max total length by scaling
    fmt_values = []
    for v in scaled:
        # compute integer length
        int_len = len(str(int(v)))
        # number of zeros to prepend in integer part
        prepend_zeros = (
            max_total_len - int_len - max_decimals - 1
        )  # minus 1 for decimal point
        int_part = "0" * max(prepend_zeros, 0) + str(int(v))
        # format decimals
        dec_part = f"{v - int(v):.{max_decimals}f}"[1:]  # get decimal with dot
        fmt_values.append(int_part + dec_part)

    # Reassign to signal
    idx = 0
    signal["entry"] = [fmt_values[idx + i] for i in range(len(entry_strs))]
    idx += len(entry_strs)

    if stop_str:
        signal["stopLoss"] = fmt_values[idx]
        idx += 1

    signal["takeProfits"] = [fmt_values[idx + i] for i in range(len(tp_strs))]
    return signal


async def isValidSignal(signal: dict) -> tuple[dict, bool]:
    # First attempt
    if await validation(signal):
        return signal, True
    else:
        await adminReport(
            f"⚠️ Raw signal failed validation, trying normalization: {signal}"
        )

    # Normalize & retry
    normalized_signal = await normalize_signal_to_current_price_maxlen(signal)
    if await validation(normalized_signal):
        return normalized_signal, True

    # Final failure
    await adminReport(
        f"❌ Signal failed validation even after normalization: {normalized_signal}"
    )
    return signal, False


async def validation(signal: dict) -> bool:
    try:
        symbol = signal.get("symbol")
        if symbol is None or symbol.strip() == "":
            return False

        side = signal.get("side")
        entry = signal.get("entry")
        targets = signal.get("takeProfits", [])
        stop_loss = signal.get("stopLoss")

        # -------- 1. Side check --------
        if side not in {"Buy", "Sell"}:
            await adminReport(f"❌ Invalid side in signal: {side}")
            return False

        # -------- 2. Entry normalization --------
        entry_floats: list[float] = []
        if isinstance(entry, list):
            try:
                entry_floats = sorted(float(e) for e in entry)
            except Exception:
                await adminReport(f"❌ Invalid entry values: {entry}")
                return False
        elif entry is not None:
            try:
                entry_floats = [float(entry)]
            except Exception:
                await adminReport(f"❌ Invalid single entry: {entry}")
                return False

        entry_low = entry_floats[0] if entry_floats else None
        entry_high = entry_floats[-1] if entry_floats else None

        # -------- 3. Targets normalization --------
        try:
            target_floats = [float(t) for t in targets]
        except Exception:
            await adminReport(f"❌ Invalid target values: {targets}")
            return False

        if not target_floats:
            await adminReport("❌ No take profit targets provided")
            return False

        # -------- 4. Stop loss normalization --------
        try:
            stop_loss_f = float(stop_loss)
        except Exception:
            await adminReport(f"❌ Invalid stop loss: {stop_loss}")
            return False

        # -------- 5. Validation logic --------
        if side == "Buy":
            if entry_high is not None:
                if min(target_floats) <= entry_high:
                    await adminReport(
                        f"❌ Buy TP error: minTP={min(target_floats)} <= entryHigh={entry_high}"
                    )
                    return False
                if any(
                    target_floats[i] >= target_floats[i + 1]
                    for i in range(len(target_floats) - 1)
                ):
                    await adminReport("❌ Buy TP list must be strictly ascending")
                    return False
                if stop_loss_f >= entry_low:
                    await adminReport(
                        f"❌ Buy SL error: stopLoss={stop_loss_f} >= entryLow={entry_low}"
                    )
                    return False

        elif side == "Sell":
            if entry_low is not None:
                if max(target_floats) >= entry_low:
                    await adminReport(
                        f"❌ Sell TP error: maxTP={max(target_floats)} >= entryLow={entry_low}"
                    )
                    return False
                if any(
                    target_floats[i] <= target_floats[i + 1]
                    for i in range(len(target_floats) - 1)
                ):
                    await adminReport("❌ Sell TP list must be strictly descending")
                    return False
                if stop_loss_f <= entry_high:
                    await adminReport(
                        f"❌ Sell SL error: stopLoss={stop_loss_f} <= entryHigh={entry_high}"
                    )
                    return False

        return True

    except Exception as e:
        await adminReport(f"❌ Exception in isValidSignal: {e}")
        return False


async def translate(text: str) -> str:
    response = ai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a translator to Persian. "
                    "Translate all text to Persian, "
                    "but keep any emojis or flags unchanged."
                ),
            },
            {"role": "user", "content": text},
        ],
    )
    return response.choices[0].message.content


# Change direction to RTL


def doRTL(text: str) -> str:
    RTLMARK = "\u200f"  # Unicode Right-To-Left mark
    return RTLMARK + text


def extract_text_and_media(event):
    """
    متن و مدیا را از پیام تلگرام جدا می‌کند.
    خروجی: caption (str), media (object or list)
    """
    if event.grouped_id:
        # آلبوم
        return event.message.message or "", event
    elif event.media:
        return event.message.message or "", event.media
    else:
        return event.message.message or "", None


async def send_modified_message(bot, destination, media, caption):
    """
    ارسال پیام نهایی شامل کپشن و مدیا
    """
    if isinstance(media, list):
        # آلبوم (چند عکس یا ویدیو)
        files = [msg.media for msg in media]
        await bot.send_file(destination, files, caption=caption, force_document=False)
    elif media:
        await bot.send_file(
            destination, file=media, caption=caption, force_document=False
        )
    else:
        await bot.send_message(destination, caption)


async def check_membership(bot, channel_username: str, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=channel_username, user_id=user_id)
        return member.status not in ["left", "kicked"]
    except Exception as e:
        await adminReport(f"❌ Membership check failed: {e}")
        return False


async def is_user_member(bot, user_id: int, chat_id: str) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        return member.status in ("member", "creator", "administrator")
    except TelegramBadRequest:
        return False
