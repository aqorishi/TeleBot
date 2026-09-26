import ccxt, re, talib, time, datetime, json, asyncio
import pandas as pd
from aiobot.core import bot
from datetime import datetime, timedelta
from sources.config import FOOTER_LINK, line, ANALYZER_REPORTER
from utils.tools import doRTL
from utils.logger import adminReport
from utils.bale import baleSendPost
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from utils.broadcaster import send_everywhere


INTERVAL_HOURS = 1 #4
PRE_MINUTES = 15 #3

reportChannel = ANALYZER_REPORTER  # Channel ID for reports
eor = "\n\u200b\n"  # End of report marker

exchange = ccxt.binance()

# === Image Paths === #
INDICATOR_IMAGES = {
    "rsi": "./sources/images/rsi-indicator.jpg",
    "divergence": "./sources/images/divergence.jpg",
    "macd": "./sources/images/macd-indicator.jpg",
    "bollinger": "./sources/images/bb_indicator.png",
}


# === Load Trading Pairs === #
# async def load_trading_pairs(filename="./sources/pairs/pairs.json"):
#     try:
#         with open(filename, "r") as file:
#             data = json.load(file)
#             return data.get("pairs", [])
#     except Exception as e:
#         await adminReport(f"(Analyzer-32): Error loading trading pairs: {e}")
#         return []


# === Load Active Binance USDT Trading Pairs ===
async def load_trading_pairs():
    try:
        markets = exchange.load_markets()

        pairs = [
            symbol
            for symbol, market in markets.items()
            if market.get("active") is True
            and market.get("spot") is True
            and market.get("quote") == "USDT"
        ]

        pairs.sort()

        await adminReport(
            f"📊 Loaded {len(pairs)} active Binance USDT spot pairs."
        )

        return pairs

    except Exception as e:
        await adminReport(
            f"(Analyzer-32): Error loading Binance trading pairs: {e}"
        )
        return []


# === Fetch OHLCV Data === #
async def analyzer_fetch_ohlcv(pair, timeframe="4h", limit=200):
    try:
        data = exchange.fetch_ohlcv(pair, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(
            data, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        await adminReport(
            f"(Analyzer-54):Error fetching data for {pair} on {timeframe}: {e}"
        )
        return pd.DataFrame()


# === Indicator Calculations === #
def calculate_rsi(df, period=14):
    if df.empty:
        return None
    df["rsi"] = talib.RSI(df["close"], timeperiod=period)
    return df


def calculate_macd(df, fastperiod=12, slowperiod=26, signalperiod=9):
    if df.empty:
        return None
    macd, signal, hist = talib.MACD(
        df["close"],
        fastperiod=fastperiod,
        slowperiod=slowperiod,
        signalperiod=signalperiod,
    )
    df["macd"] = macd
    df["signal"] = signal
    df["hist"] = hist
    return df


def calculate_bollinger_bands(df, period=20, std_dev=2):
    if df.empty:
        return None
    upper, middle, lower = talib.BBANDS(
        df["close"], timeperiod=period, nbdevup=std_dev, nbdevdn=std_dev
    )
    df["bb_upper"] = upper
    df["bb_middle"] = middle
    df["bb_lower"] = lower
    return df


def split_report_parts(text: str):
    # Split the full report into atomic parts that must stay together (e.g. a full 📈...📉 section)
    return re.findall(r"(📈.*?\u200B|📉.*?\u200B)", text, flags=re.DOTALL)


def group_report_parts(parts, max_length, header_length, footer_length):
    grouped = []
    current = []
    current_len = 0
    limit = max_length - header_length - footer_length

    for part in parts:
        part = part.strip()
        part_len = len(part) + 2  # plus newlines
        if current_len + part_len > limit:
            if current:
                grouped.append(current)
                current = []
                current_len = 0
        current.append(part)
        current_len += part_len

    if current:
        grouped.append(current)

    return grouped


def translate_numbers_to_persian(s: str) -> str:
    return s.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


async def send_telegram_message(client, message, image_path=None):
    HEADER_BASE = "✅ ناظر مالی پارسی"
    FOOTER = f"\n\n{FOOTER_LINK}"
    MAX_CAPTION = 1024

    try:
        report_parts = split_report_parts(message)
        header_sample = f"{HEADER_BASE}\n{doRTL(line)}\n\n"
        grouped_chunks = group_report_parts(
            report_parts, MAX_CAPTION, len(header_sample), len(FOOTER)
        )

        total = len(grouped_chunks)

        for idx, chunk_parts in enumerate(grouped_chunks, start=1):
            body = "\n\n".join(chunk_parts).strip()
            part_num = translate_numbers_to_persian(str(idx))
            total_num = translate_numbers_to_persian(str(total))
            header = (
                f"{HEADER_BASE} (بخش {part_num} از {total_num})\n{doRTL(line)}\n\n"
            )
            caption = f"{header}{body}{FOOTER}"

            await client.send_file(
                reportChannel,
                image_path,
                caption=caption[:MAX_CAPTION],
                parse_mode="html",
            )

            # await baleSendPost(caption, [image_path])

    except Exception as e:
        await adminReport(f"(Analyzer-140):❌ Error sending message: {e}")


# === Analysis Functions === #
def check_rsi_alerts(pair, df_4h, df_1d):
    df_4h = calculate_rsi(df_4h)
    df_1d = calculate_rsi(df_1d)
    message = ""
    if df_4h is not None and df_1d is not None:
        rsi_4h = df_4h["rsi"].iloc[-1]
        rsi_1d = df_1d["rsi"].iloc[-1]
        if rsi_4h >= 70 and rsi_1d >= 70:
            message += f"📈 {pair} is OVERBOUGHT\n  → RSI 4H: {rsi_4h:.2f}, RSI 1D: {rsi_1d:.2f}{eor}"
        elif rsi_4h <= 30 and rsi_1d <= 30:
            message += f"📉 {pair} is OVERSOLD\n  → RSI 4H: {rsi_4h:.2f}, RSI 1D: {rsi_1d:.2f}{eor}"
    return message


def check_macd_crossover(pair, df):
    df = calculate_macd(df)
    message = ""
    if df is not None and len(df) >= 2:
        current_macd = df["macd"].iloc[-1]
        current_signal = df["signal"].iloc[-1]
        previous_macd = df["macd"].iloc[-2]
        previous_signal = df["signal"].iloc[-2]
        if previous_macd < previous_signal and current_macd > current_signal:
            message += f"📈 {pair} (4H) MACD BULLISH Crossover.{eor}"
        elif previous_macd > previous_signal and current_macd < current_signal:
            message += f"📉 {pair} (4H) MACD BEARISH Crossover.{eor}"
    return message


def check_bollinger_bands_alert(pair, df):
    df = calculate_bollinger_bands(df)
    message = ""
    if df is not None and not df.empty:
        last_close = df["close"].iloc[-1]
        upper_band = df["bb_upper"].iloc[-1]
        lower_band = df["bb_lower"].iloc[-1]
        if last_close > upper_band:
            message += f"📈 {pair} in TimeFrame 4H \nPrice broke ABOVE Bollinger Upper Band: {last_close:.2f} > {upper_band:.2f}{eor}"
        elif last_close < lower_band:
            message += f"📉 {pair} in TimeFrame 4H \nPrice broke BELOW Bollinger Lower Band: {last_close:.2f} < {lower_band:.2f}{eor}"
    return message


def find_pivots(df, left=5, right=5):
    df["pivot_low"] = df["close"].where(
        df["close"] == df["close"].rolling(left + right + 1, center=True).min()
    )
    df["pivot_high"] = df["close"].where(
        df["close"] == df["close"].rolling(left + right + 1, center=True).max()
    )
    df["pivot_rsi_low"] = df["rsi"].where(
        df["rsi"] == df["rsi"].rolling(left + right + 1, center=True).min()
    )
    df["pivot_rsi_high"] = df["rsi"].where(
        df["rsi"] == df["rsi"].rolling(left + right + 1, center=True).max()
    )
    return df


def detect_divergence(pair, df):
    df = calculate_rsi(df)
    if df is None or len(df) < 20:
        return ""

    df = find_pivots(df)
    pivots = df[["timestamp", "close", "rsi", "pivot_low", "pivot_high"]].dropna(
        how="all"
    )
    message = ""
    found_divergence = False

    three_days_ago = datetime.now() - timedelta(days=2)
    # three_days_ago = datetime.now(ZoneInfo("Asia/Tehran")) - timedelta(days=2)


    last_two_lows = pivots[pivots["pivot_low"].notna()].tail(2)
    if len(last_two_lows) >= 2:
        last_date = last_two_lows.iloc[-1]["timestamp"]
        if last_date >= three_days_ago:
            if (
                last_two_lows.iloc[-1]["close"] < last_two_lows.iloc[-2]["close"]
                and last_two_lows.iloc[-1]["rsi"] > last_two_lows.iloc[-2]["rsi"]
            ):
                message += (
                    f"📈 Bullish Divergence for {pair} in 4H TimeFrame\n"
                    f"⏰ {last_two_lows.iloc[-2]['timestamp']} → {last_two_lows.iloc[-1]['timestamp']}\n"
                    f"💲 Price: {last_two_lows.iloc[-2]['close']:.2f} → {last_two_lows.iloc[-1]['close']:.2f}\n"
                    f"📊 RSI: {last_two_lows.iloc[-2]['rsi']:.2f} → {last_two_lows.iloc[-1]['rsi']:.2f}{eor}"
                )
                found_divergence = True

    last_two_highs = pivots[pivots["pivot_high"].notna()].tail(2)
    if len(last_two_highs) >= 2:
        last_date = last_two_highs.iloc[-1]["timestamp"]
        if last_date >= three_days_ago:
            if (
                last_two_highs.iloc[-1]["close"] > last_two_highs.iloc[-2]["close"]
                and last_two_highs.iloc[-1]["rsi"] < last_two_highs.iloc[-2]["rsi"]
            ):
                message += (
                    f"📉 Bearish Divergence for {pair} in 4H TimeFrame\n"
                    f"⏰ {last_two_highs.iloc[-2]['timestamp']} → {last_two_highs.iloc[-1]['timestamp']}\n"
                    f"💲 Price: {last_two_highs.iloc[-2]['close']:.2f} → {last_two_highs.iloc[-1]['close']:.2f}\n"
                    f"📊 RSI: {last_two_highs.iloc[-2]['rsi']:.2f} → {last_two_highs.iloc[-1]['rsi']:.2f}{eor}"
                )
                found_divergence = True

    return message if found_divergence else ""


# === Split run_analysis_cycle into two steps ===
async def prepare_analysis_reports():
    start_time = time.time()

    divergence_reports = ""
    rsi_reports = ""
    macd_reports = ""
    bollinger_reports = ""
    
    TRADING_PAIRS = await load_trading_pairs()
    
    for pair in TRADING_PAIRS:
        df_4h = await analyzer_fetch_ohlcv(pair=pair, timeframe="4h", limit=200)
        df_1d = await analyzer_fetch_ohlcv(pair=pair, timeframe="1d", limit=200)

        divergence_reports += detect_divergence(pair, df_4h)
        rsi_reports += check_rsi_alerts(pair, df_4h, df_1d)
        macd_reports += check_macd_crossover(pair, df_4h)
        bollinger_reports += check_bollinger_bands_alert(pair, df_4h)

    elapsed_time = time.time() - start_time
    await adminReport(f"✅ Analysis prepared in {int(elapsed_time)} seconds.")

    return {
        "divergence": divergence_reports,
        "rsi": rsi_reports,
        "macd": macd_reports,
        "bollinger": bollinger_reports,
    }


async def send_analysis_reports(client, reports):
    if reports["divergence"]:
        await send_telegram_message(
            client,
            f"{reports['divergence']}\n\n{FOOTER_LINK}",
            INDICATOR_IMAGES["divergence"],
        )
    if reports["rsi"]:
        await send_telegram_message(
            client, f"{reports['rsi']}\n\n{FOOTER_LINK}", INDICATOR_IMAGES["rsi"]
        )
    if reports["macd"]:
        await send_telegram_message(
            client, f"{reports['macd']}\n{FOOTER_LINK}", INDICATOR_IMAGES["macd"]
        )
    if reports["bollinger"]:
        await send_telegram_message(
            client,
            f"{reports['bollinger']}\n\n{FOOTER_LINK}",
            INDICATOR_IMAGES["bollinger"],
        )


# interval and pre-notify (can be arguments or config)
async def start_analyzer_loop(client):
    tehran_tz = ZoneInfo("Asia/Tehran")
    await adminReport("📊 Analyzer loop started.")

    while True:
        now = datetime.now(tehran_tz)

        #_+_+_+_+_+_+_+_+
        # # --- compute next_run robustly ---
        # # round down to hour (00 minutes) as base
        # base = now.replace(minute=0, second=0, microsecond=0)
        # # hours to add until next multiple of INTERVAL_HOURS
        # hours_to_add = INTERVAL_HOURS - (now.hour % INTERVAL_HOURS)
        # if hours_to_add == 0:
        #     hours_to_add = INTERVAL_HOURS
        # next_run = base + timedelta(hours=hours_to_add)

        # # Ensure next_run is strictly in the future (covers edge-cases / DST)
        # while next_run <= now:
        #     next_run += timedelta(hours=INTERVAL_HOURS)

        # prepare_time = next_run - timedelta(minutes=PRE_MINUTES)

        # --- Schedule next run every day at 08:00 Tehran time ---
        next_run = now.replace(
            hour=8,
            minute=0,
            second=0,
            microsecond=0,
        )

        # If today's 08:00 has already passed, schedule for tomorrow
        if next_run <= now:
            next_run += timedelta(days=1)

        prepare_time = next_run - timedelta(minutes=PRE_MINUTES)



        # --- wait until prepare time (if still in future) ---
        wait_prepare = (prepare_time - now).total_seconds()
        if wait_prepare > 0:
            # sleep until prepare_time
            await asyncio.sleep(wait_prepare)
            # prepare step (3 minutes before)
            await adminReport(
                f"⏳ Preparing analysis reports at {prepare_time.strftime('%Y-%m-%d %H:%M:%S')} (Tehran)"
            )
            reports = await prepare_analysis_reports()
        else:
            # we're already past prepare_time
            # if still before next_run -> prepare immediately
            now_after = datetime.now(tehran_tz)
            if now_after < next_run:
                await adminReport(
                    f"⏳ Preparing analysis reports (late) at {now_after.strftime('%Y-%m-%d %H:%M:%S')}"
                )
                reports = await prepare_analysis_reports()
            else:
                # already past next_run as well (race or slow) -> jump to compute next cycle
                # continue to top to compute a new next_run
                await adminReport(
                    "⚠️ Skipped prepare because we're already past the scheduled run; recalculating next run."
                )
                continue

        # --- wait remaining time until exact next_run (if any) ---
        now2 = datetime.now(tehran_tz)
        wait_run = (next_run - now2).total_seconds()
        if wait_run > 0:
            await asyncio.sleep(wait_run)

        # --- send prepared reports exactly at next_run ---
        time_formatted = datetime.now(tehran_tz).strftime("%Y-%m-%d %H:%M:%S")
        await adminReport(f"🚀 Sending analysis reports at {time_formatted} (Tehran)")
        await send_analysis_reports(client, reports)

        # loop will repeat and compute the next next_run correctly