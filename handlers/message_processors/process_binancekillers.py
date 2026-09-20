import re
from utils.tools import doRTL
from sources.config import (
    FOOTER_LINK,
    line,
    CAPTION_HEADER,
    PERSIANWATCHER,
    PERSIANFINANCIALWATCHER,
    PFW_Premium
)
from utils.logger import adminReport



def splitMarketAnalysisReport(text):
    """
    Split market report into structured sections.

    Returns:
    {
        "DATE": "...",

        "MARKET ANALYSIS": "...",

        "TOP GAINERS (BINANCE FUTURES)": [
            {
                "symbol": "...",
                "description": "..."
            }
        ],

        "HIGHEST VOLUME (FUTURES)": [
            {
                "symbol": "...",
                "description": "..."
            }
        ],

        "DAILY OUTLOOK": "..."
    }
    """

    text = text.strip()

    if not text:
        return {}

    lines = [line.rstrip() for line in text.splitlines()]

    result = {}

    # -------------------------
    # DATE
    # -------------------------
    result["DATE"] = lines[0].strip()

    current_section = None
    section_lines = []

    sections = {}

    # -------------------------
    # Extract sections
    # -------------------------
    for line in lines[1:]:

        stripped = line.strip()

        if not stripped:
            continue

        if re.fullmatch(r"[A-Z0-9 ():-]+", stripped):

            if current_section:
                sections[current_section] = section_lines

            current_section = stripped.rstrip(" :")
            section_lines = []

        else:

            if current_section:
                section_lines.append(stripped)

    if current_section:
        sections[current_section] = section_lines

    # -------------------------
    # MARKET ANALYSIS
    # -------------------------
    if "MARKET ANALYSIS" in sections:

        result["MARKET ANALYSIS"] = "\n".join(sections["MARKET ANALYSIS"]).strip()

    # -------------------------
    # DAILY OUTLOOK
    # -------------------------
    if "DAILY OUTLOOK" in sections:

        result["DAILY OUTLOOK"] = "\n".join(sections["DAILY OUTLOOK"]).strip()

    # -------------------------
    # TOP GAINERS
    # -------------------------
    if "TOP GAINERS (BINANCE FUTURES)" in sections:

        result["TOP GAINERS (BINANCE FUTURES)"] = []

        items = sections["TOP GAINERS (BINANCE FUTURES)"]

        current_symbol = None
        current_desc = []

        for line in items:

            if re.match(r"^[A-Z0-9]+\/USDT:", line):

                if current_symbol:

                    result["TOP GAINERS (BINANCE FUTURES)"].append(
                        {
                            "symbol": current_symbol,
                            "description": " ".join(current_desc).strip(),
                        }
                    )

                current_symbol = line
                current_desc = []

            else:

                current_desc.append(line)

        if current_symbol:

            result["TOP GAINERS (BINANCE FUTURES)"].append(
                {
                    "symbol": current_symbol,
                    "description": " ".join(current_desc).strip(),
                }
            )

    # -------------------------
    # HIGHEST VOLUME
    # -------------------------
    if "HIGHEST VOLUME (FUTURES)" in sections:

        result["HIGHEST VOLUME (FUTURES)"] = []

        items = sections["HIGHEST VOLUME (FUTURES)"]

        current_symbol = None
        current_desc = []

        for line in items:

            if re.match(r"^[A-Z0-9]+\/USDT:", line):

                if current_symbol:

                    result["HIGHEST VOLUME (FUTURES)"].append(
                        {
                            "symbol": current_symbol,
                            "description": " ".join(current_desc).strip(),
                        }
                    )

                current_symbol = line
                current_desc = []

            else:

                current_desc.append(line)

        if current_symbol:

            result["HIGHEST VOLUME (FUTURES)"].append(
                {
                    "symbol": current_symbol,
                    "description": " ".join(current_desc).strip(),
                }
            )

    return result


async def cleanMarketAnalysisReport(text):

    lines = []

    for line in text.splitlines():

        stripped = line.strip()

        # Remove lines starting with "🔸"
        if stripped.startswith("🔸"):
            continue

        # Remove lines containing "binance killers" (case-insensitive)
        if "binance killers" in stripped.lower():
            continue

        # Replace lines that are just "➖" with an empty line
        if stripped and set(stripped) == {"➖"}:
            lines.append("")
            continue

        lines.append(line)

    cleanedReport = "\n".join(lines)
    # splitedReport = split_report_sections(finalText)
    # cleanedReport["DATE"] = gregorianToJalali(cleanedReport["DATE"])

    return cleanedReport


def transformCaption(caption: str) -> str:
    # 1- Replace VIP MARKET UPDATE: → Persian text
    caption = caption.replace("VIP MARKET UPDATE:", "🔥 بروزرسانی وضعیت بازار:")

    # 2- Convert coin after $ in the first line → COIN/USDT + add line break
    caption = re.sub(r"\$([A-Z]+)", r"\1/USDT\n", caption, count=1)

    # 3- Remove lines containing "➖" or "Binance Killers®"
    lines = caption.splitlines()
    lines = [
        line for line in lines if "➖" not in line and "Binance Killers" not in line
    ]

    # 4- Remove $ at the beginning of any paragraph
    result = []
    for line in lines:
        result.append(re.sub(r"^\$", "", line).strip())

    return "\n".join(result).strip()


async def handle(caption: str) -> dict:
    await adminReport(f"✅ Processing Binance Killer message...")

    if re.search(r"VIP MARKET UPDATE?", caption, re.IGNORECASE):
        await adminReport(f"🔴🔴🔴 Detected VIP MARKET UPDATE pattern. ✅")
        caption = caption.strip()
        caption = transformCaption(caption)
        caption = caption.replace("VIP MARKET UPDATE", "")
        destination = PERSIANWATCHER
        # destination = PFW_Premium
        cleanedCaption = (
            f"{CAPTION_HEADER}\n{doRTL(line)}\n\n{caption}\n\n\n\n{FOOTER_LINK}"
        )

    elif re.search(r"MARKET ANALYSIS:?", caption, re.IGNORECASE):
        if len(caption) > 1020:
            await adminReport(
                f"⚠️ Binance Killer MARKET ANALYSIS caption is too long ({len(caption)} characters), splitting into parts..."
            )

        cleanedCaption = await cleanMarketAnalysisReport(caption)
        destination = PERSIANFINANCIALWATCHER  # PERSIANWATCHER

    else:
        await adminReport(
            f"⚠️ Binance Killer message does not match expected patterns."
        )
        destination = None
        cleanedCaption = None

    return {"caption": cleanedCaption, "destination": destination}












# async def process_market_text(text: str) -> str:
#     lines = [l.rstrip() for l in text.splitlines()]
#     output = []

#     i = 0
#     n = len(lines)

#     # --- 1. تاریخ ---
#     jalali_date = gregorianToJalali(lines[i])
#     output.append(doRTL(jalali_date))
#     i += 1

#     # --- 2. خط چین ---
#     output.append(doRTL(lines[i]))
#     i += 1

#     # --- 3. MARKET ANALYSIS ---
#     if lines[i].strip().upper() == "MARKET ANALYSIS:":
#         output.append(doRTL("تحلیل بازار:"))
#         i += 1

#     # --- 4. خطوط اطلاعات بازار (بدون تغییر، LTR) ---
#     while i < n and not lines[i].startswith("🔸"):
#         output.append(lines[i])
#         i += 1

#     # --- 5. حذف خطوط VIP ---
#     while i < n and lines[i].startswith("🔸"):
#         i += 1

#     # --- 6. خط چین بعدی ---
#     if i < n and "➖" in lines[i]:
#         output.append(lines[i])
#         i += 1

#     # --- 7. TOP GAINERS ---
#     if i < n and lines[i].startswith("TOP GAINERS"):
#         output.append(lines[i])
#         i += 1

#         while i < n and lines[i] and not lines[i].startswith("HIGHEST VOLUME"):
#             if re.search(r"/USDT:\s*\+\d", lines[i]):
#                 output.append(lines[i])  # فقط زوج + درصد
#                 i += 1
#             else:
#                 i += 1  # توضیحات حذف می‌شود

#     # --- 8. HIGHEST VOLUME ---
#     if i < n and lines[i].startswith("HIGHEST VOLUME"):
#         output.append(lines[i])
#         i += 1

#         while i < n and lines[i] and not lines[i].startswith("DAILY OUTLOOK"):
#             if re.search(r"/USDT:\s*\$", lines[i]):
#                 output.append(lines[i])
#                 i += 1
#             else:
#                 i += 1

#     # --- 9. DAILY OUTLOOK ---
#     if i < n and lines[i].startswith("DAILY OUTLOOK"):
#         daily_text = "\n".join(lines[i:])
#         translated = await translate(daily_text)
#         output.append(doRTL(translated))

#     return "\n".join(output)
