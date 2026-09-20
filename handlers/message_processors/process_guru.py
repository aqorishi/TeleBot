import re
from utils.tools import translate, doRTL
from sources.config import FOOTER_LINK, line, CAPTION_HEADER, PERSIANFINANCIALWATCHER
from utils.logger import adminReport


async def handle(caption: str) -> dict:
    await adminReport(f"✅ Processing WatcherGuru message...")
    
    # if re.search(r"JUST IN:?", caption, re.IGNORECASE):
    if re.search(r"\b(JUST IN|BREAKING):?", caption, re.IGNORECASE):
        cleanedCaption = caption.strip()

        # Remove unwanted phrases
        cleanedCaption = cleanedCaption.replace("@WatcherGuru", "")
        
        if re.search(r"JUST IN:?", cleanedCaption, re.IGNORECASE):
            cleanedCaption = cleanedCaption.replace("JUST IN:", "")
        elif re.search(r"BREAKING:?", cleanedCaption, re.IGNORECASE):
            cleanedCaption = cleanedCaption.replace("BREAKING:", "")

        # Translate the cleaned text to Persian
        cleanedCaption = await translate(cleanedCaption)

        # Apply right-to-left formatting
        cleanedCaption = doRTL(cleanedCaption)

        # Construct the new caption with header, line separator, cleaned text, and footer link
        newCaption = (
            f"{CAPTION_HEADER}\n{doRTL(line)}\n\n{cleanedCaption}\n\n\n{FOOTER_LINK}"
        )
        
        destination = PERSIANFINANCIALWATCHER
    else:
        await adminReport(
            f"⚠️ WatcherGuru message does not match expected patterns."
        )
        destination = None
        newCaption = None        

    return {"caption": newCaption, "destination": destination}
