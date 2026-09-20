import jdatetime, datetime, re
from utils.tools import doRTL, formatShamsiDate
from sources.config import (
    CAPTION_HEADER,
    FOOTER_LINK,
    PERSIANFINANCIALWATCHER,
    line,
)
from utils.logger import adminReport


async def handle(caption: str) -> dict:
    await adminReport(f"✅ Processing FearAndGreed message...")

    if re.search(r"Fear And Greed Index?", caption, re.IGNORECASE):
        todayMiladi = datetime.date.today()
        todayShamsi = jdatetime.date.fromgregorian(date=todayMiladi)

        # 📅 Dates
        shamsiSTR = doRTL(formatShamsiDate(todayShamsi))
        miladiSTR = doRTL(todayMiladi.strftime("%A, %d %B %Y"))

        cleanedCaption = caption.strip()
        cleanedCaption = cleanedCaption.replace(
            "Fear And Greed Index",
            f"🟠 شاخص ترس و طمع کریپتو \n\n 📅 {shamsiSTR}\n 📅 {miladiSTR}",
        )

        cleanedCaption = f"{CAPTION_HEADER}\n{doRTL(line)}\n\n{doRTL(cleanedCaption)}\n\n{FOOTER_LINK}"
        destination = PERSIANFINANCIALWATCHER
    else:
        await adminReport(
            f"⚠️ Fear And Greed message does not match expected patterns."
        )
        destination = None
        cleanedCaption = None        

    return {
        "caption": cleanedCaption,
        "destination": destination,
    }
