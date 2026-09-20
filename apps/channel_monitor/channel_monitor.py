import asyncio, logging, re
import os, tempfile
from collections import defaultdict
from openai import OpenAI
from telethon import events
from aiogram.types import FSInputFile
from telethon.tl.types import (
    MessageMediaPhoto,
    MessageMediaDocument,
    MessageEntityTextUrl,
)
from sources.config import (
    CAPTION_HEADER,
    FOOTER_LINK,
    line,
    SOURCE_CHANNELS,
    PERSIANFINANCIALWATCHER,
    PERSIANWATCHER,
    BINANCEKILLERS,
    BINANCEKILLERS_VIP,
    PFW_Premium,
    ln,
)
from handlers.message_processors import get_processor
from utils.bale import baleSendPost
from utils.logger import adminReport
from utils.tools import doRTL, signalReport, translate, gregorianToJalali
from utils.broadcaster import send_everywhere
from handlers.message_processors.process_binancekillers import splitMarketAnalysisReport

# --- Setup logging ---
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# Buffer to collect grouped media messages (albums)
album_buffer = defaultdict(list)
album_timeout = 5  # seconds


def setup_channel_monitor(client):
    @client.on(events.NewMessage(chats=list(SOURCE_CHANNELS.values())))
    async def handler(event):
        chat_id = event.chat_id
        processor = get_processor(str(chat_id))
        message = event.message
        caption = message.message or ""

        source_name = next(
            (k for k, v in SOURCE_CHANNELS.items() if str(v) == str(chat_id)), "Unknown"
        )

        if not processor:
            await adminReport(
                f"Channel Monitor : {ln()}\n❗️ No processor found for chat_id: {chat_id}"
            )
            return

        # 🔒 Custom logic for Signal channels, Process and skip forwarding [ALWAYS_WIN, AMAN, BINANCEKILLERS_VIP, FED_RUSSIAN_VIP, WOLFX, PFW_Premium]
        if chat_id in [BINANCEKILLERS_VIP, PFW_Premium]:
            handler = processor.get("handler")
            if not handler:
                await adminReport(
                    f"Channel Monitor : {ln()}\n❗️ No handler defined for this processor."
                )
                return
            try:
                if hasattr(event, "message") and caption:
                    handlerResponse = await handler(caption)

                    if handlerResponse is not None:
                        signal = handlerResponse
                        destination = signal.get("destination")
                        if destination is not None:
                            caption, image_path = await signalReport(signal)

                            await client.send_file(
                                entity=destination,
                                file=image_path,
                                caption=caption,
                                parse_mode="md",
                            )

                            await baleSendPost(caption, [image_path])
                    else:
                        await adminReport(f"Channel Monitor : {ln()}\n⚠️ Arrived message from {handler} is not a signal.")

            except Exception as e:
                await adminReport(
                    f"Channel Monitor : {ln()}\n❗️ Error in Signal Extract handler: {e}"
                )
            return

        # 1️⃣ Handle grouped messages (albums)
        if event.grouped_id:
            # await adminReport(
            #     f"Channel Monitor : {ln()}\n   ***   Detected media message from {source_name} in Handle grouped messages\n"
            # )            
            group_id = event.grouped_id
            album_buffer[group_id].append(event)

            # Wait for a short period to allow all messages in the group to arrive
            await asyncio.sleep(album_timeout)

            # Check if the group_id is still in the buffer (it might have been processed already)
            if group_id not in album_buffer:
                return  # Group already processed

            media_group = sorted(album_buffer[group_id], key=lambda x: x.id)
            album_buffer.pop(group_id, None)

            if not media_group:
                await adminReport(
                    f"Channel Monitor : {ln()}\n⚠️ Empty album group {group_id}"
                )
                return

            group_caption = media_group[0].message.message or ""
            handler_result = (
                await processor["handler"](group_caption) if group_caption else ""
            )
            new_caption = (
                handler_result.get("caption", "")
                if isinstance(handler_result, dict)
                else handler_result
            )
            destinationChannel = (
                handler_result.get("destination", PERSIANWATCHER)
                if isinstance(handler_result, dict)
                else PERSIANWATCHER
            )
            files = [
                msg.media
                for msg in media_group
                if isinstance(msg.media, (MessageMediaPhoto, MessageMediaDocument))
            ]

            if files:
                try:
                    if new_caption and destinationChannel:
                        await send_everywhere(
                            telethon_client=client,
                            destination=destinationChannel,
                            caption=new_caption,
                            media=files,
                        )
                    else:
                        await adminReport(
                            f"Channel Monitor : {ln()}\n⚠️ No valid caption or destination for album from {source_name}"
                        )
                except Exception as e:
                    await adminReport(
                        f"Channel Monitor : {ln()}\n❗️ Error while sending album: {e}"
                    )
            else:
                await adminReport(
                    f"Channel Monitor : {ln()}\n⚠️ No valid media in album from {source_name}"
                )

        # 2️⃣ Handle single media messages
        elif event.media:
            # await adminReport(
            #     f"Channel Monitor : {ln()}\n   ***   Detected media message from {source_name} in Handle single media messages\n"
            # )
            sendingFlag = True
            if chat_id == BINANCEKILLERS and "VIP MARKET UPDATE" in caption:
                sendingFlag = False

            handlerResult = await processor["handler"](caption) if caption else ""
            new_caption = (
                handlerResult.get("caption", "")
                if isinstance(handlerResult, dict)
                else handlerResult
            )
            destinationChannel = (
                handlerResult.get("destination", PERSIANWATCHER)
                if isinstance(handlerResult, dict)
                else PERSIANWATCHER
            )

            if isinstance(event.media, (MessageMediaPhoto, MessageMediaDocument)) and new_caption and destinationChannel:
                try:
                    # must change if channel becomes premium/start
                    if (
                        chat_id == BINANCEKILLERS or chat_id == PFW_Premium
                    ) and re.search(r"MARKET ANALYSIS:?", caption, re.IGNORECASE):
                        splitedCaption = splitMarketAnalysisReport(new_caption)

                        reportDate = gregorianToJalali(splitedCaption.get("DATE", ""))
                        marketAnalysis = splitedCaption.get("MARKET ANALYSIS", "")

                        topGainers = splitedCaption.get(
                            "TOP GAINERS (BINANCE FUTURES)", []
                        )
                        highestVolume = splitedCaption.get(
                            "HIGHEST VOLUME (FUTURES)", []
                        )
                        # اطمینان از تعداد کافی آیتم‌ها
                        topGainers = (topGainers + [{}] * 3)[:3]
                        highestVolume = (highestVolume + [{}] * 2)[:2]

                        dailyOutlook = splitedCaption.get("DAILY OUTLOOK", "")

                        firstMarketAnalysis = (
                            f"{CAPTION_HEADER}\n"
                            f"{doRTL(line)}\n\n"
                            f"{doRTL(reportDate)}\n\n"
                            f"تحلیل بازار:\n\n"
                            f"{marketAnalysis}\n\n"
                            f"👉 👉 ادامه در پست بعدی 👇 👇\n\n"
                            f"{FOOTER_LINK}"
                        )

                        # -------------------------------
                        # ساخت متن بیشترین سودها
                        # -------------------------------
                        gainersText = ""
                        for item in topGainers:
                            symbol = item.get("symbol", "N/A")
                            description = await translate(item.get("description", ""))

                            gainersText += (
                                f"{symbol}:\n"
                                f"{description}\n\n"
                            )

                        # -------------------------------
                        # ساخت متن بیشترین حجم
                        # -------------------------------
                        volumeText = ""
                        for item in highestVolume:
                            symbol = item.get("symbol", "N/A")
                            description = await translate(item.get("description", ""))

                            volumeText += (
                                f"{symbol}:\n"
                                f"{description}\n\n"
                            )

                        restMarketAnalysis = (
                            f"{CAPTION_HEADER}\n"
                            f"{doRTL(line)}\n\n"

                            f"بیشترین سودها (فیوچرز بایننس):\n\n"
                            f"{gainersText}"

                            f"{line}\n\n"

                            f"بیشترین حجم (فیوچرز):\n\n"
                            f"{volumeText}"

                            f"{line}\n\n"

                            f"چشم‌انداز روزانه:\n\n"
                            f"{await translate(dailyOutlook)}\n\n"

                            f"{FOOTER_LINK}"
                        )
                        # topGainer1, topGainer2, topGainer3 = topGainers[:3]
                        # highestVolume1, highestVolume2 = highestVolume[:2]

                        # dailyOutlook = splitedCaption.get("DAILY OUTLOOK", "")

                        # firstMarketAnalysis = (
                        #     f"{CAPTION_HEADER}\n"
                        #     f"{doRTL(line)}\n\n"
                        #     f"{doRTL(reportDate)}\n\n"
                        #     f"تحلیل بازار:\n\n"
                        #     f"{marketAnalysis}\n\n"
                        #     f"👉 👉 ادامه در پست بعدی 👇 👇\n\n"
                        #     f"{FOOTER_LINK}"
                        # )

                        # restMarketAnalysis = (
                        #     f"{CAPTION_HEADER}\n"
                        #     f"{doRTL(line)}\n\n"
                        #     f"بیشترین سودها (فیوچرز بایننس):\n\n"
                        #     f"{topGainer1["symbol"]}:\n"
                        #     f"{await translate(topGainer1['description'])}\n\n"
                        #     f"{topGainer2["symbol"]}:\n"
                        #     f"{await translate(topGainer2['description'])}\n\n"
                        #     f"{topGainer3["symbol"]}:\n"
                        #     f"{await translate(topGainer3['description'])}\n\n"
                        #     f"{line}\n\n"
                        #     f"بیشترین حجم (فیوچرز):\n\n"
                        #     f"{highestVolume1["symbol"]}:\n"
                        #     f"{await translate(highestVolume1['description'])}\n\n"
                        #     f"{highestVolume2["symbol"]}:\n"
                        #     f"{await translate(highestVolume2['description'])}\n\n"
                        #     f"{line}\n\n"
                        #     f"چشم‌انداز روزانه:\n\n"
                        #     f"{await translate(dailyOutlook)}\n\n"
                        #     f"{FOOTER_LINK}"
                        # )

                        await client.send_file(
                            destinationChannel,
                            file=event.media,
                            caption=firstMarketAnalysis[:1020],
                            parse_mode="html",
                            force_document=False,
                        )

                        await client.send_message(
                            destinationChannel,
                            restMarketAnalysis[:4096],
                            parse_mode="html",
                        )

                        # Send to Bale
                        baleMarketAnalysis = (
                            f"{CAPTION_HEADER}\n"
                            f"{doRTL(line)}\n\n"
                            f"{doRTL(reportDate)}\n\n"

                            f"تحلیل بازار:\n\n"
                            f"{marketAnalysis}\n\n"

                            f"بیشترین سودها (فیوچرز بایننس):\n\n"
                            f"{gainersText}"

                            f"{line}\n\n"

                            f"بیشترین حجم (فیوچرز):\n\n"
                            f"{volumeText}"

                            f"{line}\n\n"

                            f"چشم‌انداز روزانه:\n\n"
                            f"{await translate(dailyOutlook)}\n\n"

                            f"{FOOTER_LINK}"
                        )
                        # baleMarketAnalysis = (
                        #     f"{CAPTION_HEADER}\n"
                        #     f"{doRTL(line)}\n\n"
                        #     f"{doRTL(reportDate)}\n\n"
                        #     f"تحلیل بازار:\n\n"
                        #     f"{marketAnalysis}\n\n"
                        #     f"بیشترین سودها (فیوچرز بایننس):\n\n"
                        #     f"{topGainer1["symbol"]}:\n"
                        #     f"{await translate(topGainer1['description'])}\n\n"
                        #     f"{topGainer2["symbol"]}:\n"
                        #     f"{await translate(topGainer2['description'])}\n\n"
                        #     f"{topGainer3["symbol"]}:\n"
                        #     f"{await translate(topGainer3['description'])}\n\n"
                        #     f"{line}\n\n"
                        #     f"بیشترین حجم (فیوچرز):\n\n"
                        #     f"{highestVolume1["symbol"]}:\n"
                        #     f"{await translate(highestVolume1['description'])}\n\n"
                        #     f"{highestVolume2["symbol"]}:\n"
                        #     f"{await translate(highestVolume2['description'])}\n\n"
                        #     f"{line}\n\n"
                        #     f"چشم‌انداز روزانه:\n\n"
                        #     f"{await translate(dailyOutlook)}\n\n"
                        #     f"{FOOTER_LINK}"
                        # )
                        fd, path = tempfile.mkstemp(suffix=".jpg")
                        os.close(fd)

                        photo_path = await client.download_media(event.message, file=path)

                        await baleSendPost(baleMarketAnalysis, [photo_path])
                    # must change if channel becomes premium/end
                    else:
                        if sendingFlag:
                            await send_everywhere(
                                telethon_client=client,
                                destination=destinationChannel,
                                caption=new_caption,
                                media=[event.media],
                            )
                        else:
                            await client.send_file(
                                destinationChannel,
                                file=event.media,
                                caption=f"{new_caption}"[:1020],
                                parse_mode="html",
                                force_document=False,
                            )
                except Exception as e:
                    await adminReport(
                        f"Channel Monitor : {ln()}\n❗️ Error while sending media: {e}"
                    )
            # else:
                # try:
                #     if chat_id == BINANCEKILLERS:
                #         adminReport(f"Channel Monitor : {ln()}\n   ***   Detected media message from BINANCEKILLERS in Handle single media messages\n")
                #     await client.send_message(
                #         destinationChannel,
                #         f"{new_caption}"[:4096],
                #         parse_mode='html'
                #     )
                # except Exception as e:
                #     # logger.error(f"❗️ Error while sending fallback message: {e}")
                #     await adminReport(f"Channel Monitor : {ln()}\n❗️ Error while sending Handle single media messages:\n {e}")

        # 3️⃣ Handle plain text messages
        elif caption:
            # await adminReport(
            #     f"Channel Monitor : {ln()}\n   ***   Detected media message from {source_name} in Handle plain text messages\n"
            # )            
            try:
                handler_result = await processor["handler"](caption) if caption else ""
                new_caption = (
                    handler_result.get("caption", "")
                    if isinstance(handler_result, dict)
                    else handler_result
                )
                destinationChannel = (
                    handler_result.get("destination", PERSIANWATCHER)
                    if isinstance(handler_result, dict)
                    else PERSIANWATCHER
                )
                if new_caption and destinationChannel:
                    await send_everywhere(
                        telethon_client=client,
                        destination=destinationChannel,
                        caption=new_caption,
                    )
                else:
                    await adminReport(
                        f"Channel Monitor : {ln()}\n⚠️ No valid caption or destination for text message from {source_name}"
                    )

            except Exception as e:
                await adminReport(
                    f"Channel Monitor : {ln()}\n❗️ Error while sending text: {e}"
                )
                
                
# await client.send_message(
#     destinationChannel,
#     f"{new_caption}"[:4096],
#     parse_mode="html"
# )                
