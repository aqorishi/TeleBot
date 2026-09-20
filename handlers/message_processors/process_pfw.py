
from sources.config import PERSIANFINANCIALWATCHER
from utils.logger import adminReport


async def handle(caption: str) -> dict:
    await adminReport(f"✅ Processing PFW(Robot) message...")

    if caption:
        cleanedCaption = caption.strip()        
        destination = PERSIANFINANCIALWATCHER
    else:
        await adminReport(
            f"⚠️ PFW Robot message does not match expected patterns."
        )
        destination = None
        cleanedCaption = None          

    return {"caption": cleanedCaption, "destination": destination}
