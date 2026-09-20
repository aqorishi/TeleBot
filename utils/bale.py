import os
import json
import io
import aiohttp

from utils.logger import adminReport
from sources.config import baleToken, baleChatID

token = baleToken
chatID = baleChatID


async def post_request(url, *, data=None, json_data=None, form=None):

    async with aiohttp.ClientSession() as session:

        async with session.post(url, data=form or data, json=json_data) as response:

            return response.status, await response.text()


async def send_text(caption):

    baseURL = f"https://tapi.bale.ai/bot{token}"

    url = f"{baseURL}/sendMessage"

    payload = {"chat_id": chatID, "text": caption}

    status, text = await post_request(url, json_data=payload)

    await adminReport(f"Bale text status: {status}")

    return status, text


async def baleSendPost(caption: str, media: list):

    baseURL = f"https://tapi.bale.ai/bot{token}"

    try:
        if "@PersianFinancialWatcher" in caption:
            caption = caption.replace(
                "@PersianFinancialWatcher",
                f"Bale: @PersianFinancialWatcher\nTelegram: [@](https://t.me/PersianFinancialWatcher)[PersianFinancialWatcher](https://t.me/PersianFinancialWatcher)",
            )

        #
        # TEXT
        #

        if not media:

            return await send_text(caption)

        #
        # SINGLE FILE
        #

        if len(media) == 1:

            file_path = media[0]

            form = aiohttp.FormData()

            form.add_field("chat_id", str(chatID))

            form.add_field("caption", caption)

            form.add_field("photo", open(file_path, "rb"))

            async with aiohttp.ClientSession() as session:

                async with session.post(f"{baseURL}/sendPhoto", data=form) as response:

                    await adminReport(f"Bale single media: {response.status}")

                    return response.status

        #
        # ALBUM
        #

        media_list = []

        form = aiohttp.FormData()

        form.add_field("chat_id", str(chatID))

        for i, path in enumerate(media):

            key = f"file{i}"

            form.add_field(key, open(path, "rb"))

            item = {"type": "photo", "media": f"attach://{key}"}

            if i == 0:
                item["caption"] = caption

            media_list.append(item)

        form.add_field("media", json.dumps(media_list))

        async with aiohttp.ClientSession() as session:

            async with session.post(f"{baseURL}/sendMediaGroup", data=form) as response:

                await adminReport(f"Bale album status: {response.status}")

                return response.status

    except Exception as e:

        await adminReport(f"Bale Error: {e}")

        return None
