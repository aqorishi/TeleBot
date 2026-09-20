import os
import tempfile
import asyncio
import traceback
from utils.logger import adminReport
from utils.bale import baleSendPost


def taskExceptionHandler(task: asyncio.Task):

    try:
        task.result()

    except asyncio.CancelledError:
        pass

    except Exception:

        task_name = task.get_name() if hasattr(task, "get_name") else "Unknown"

        asyncio.create_task(
            adminReport(
                f"Background Task '{task_name}' Error:\n\n"
                f"{traceback.format_exc()}"
            )
        )


async def send_everywhere(*, telethon_client, destination, caption="", media=None):
    """
    Send to Telegram + Bale
    """

    media = media or []
    temp_files = []

    try:

        # TELEGRAM #

        if media:

            await telethon_client.send_file(
                entity=destination,
                file=media,
                caption=caption[:1020],
                parse_mode="html",
                force_document=False,
            )

        else:

            await telethon_client.send_message(
                entity=destination,
                message=caption[:4096],
                parse_mode="html",
            )

        # BALE #

        if media:

            for item in media:

                fd, path = tempfile.mkstemp()
                os.close(fd)

                downloaded = await telethon_client.download_media(
                    item,
                    file=path,
                )

                # همیشه چیزی برای cleanup داشته باش
                temp_files.append(downloaded or path)

        baleTask = asyncio.create_task(
            baleSendPost(
                caption=caption,
                media=temp_files,
            ),
            name="baleSendPost",
        )

        baleTask.add_done_callback(taskExceptionHandler)

    except Exception as e:

        await adminReport(f"Broadcaster Error: {e}")

    finally:

        async def cleanup(files):

            await asyncio.sleep(30)

            for file in files:

                try:
                    if os.path.exists(file):
                        os.remove(file)
                except Exception:
                    pass

        if temp_files:

            cleanupTask = asyncio.create_task(
                cleanup(temp_files),
                name="cleanupTempFiles",
            )

            cleanupTask.add_done_callback(taskExceptionHandler)


# async def send_everywhere(*, telethon_client, destination, caption="", media=None):
#     """
#     Send to Telegram + Bale
#     """

#     media = media or []
#     temp_files = []

#     try:

#         #
#         # TELEGRAM
#         #

#         if media:

#             await telethon_client.send_file(
#                 entity=destination,
#                 file=media,
#                 caption=caption[:1020],
#                 parse_mode="html",
#                 force_document=False,
#             )

#         else:

#             await telethon_client.send_message(
#                 entity=destination, message=caption[:4096], parse_mode="html"
#             )

#         #
#         # BALE
#         #

#         if media:

#             for item in media:

#                 fd, path = tempfile.mkstemp()

#                 os.close(fd)

#                 downloaded = await telethon_client.download_media(item, file=path)

#                 if downloaded:
#                     temp_files.append(downloaded)

#         asyncio.create_task(baleSendPost(caption=caption, media=temp_files))

#     except Exception as e:

#         await adminReport(f"Broadcaster Error: {e}")

#     finally:

#         async def cleanup(files):

#             await asyncio.sleep(30)

#             for file in files:

#                 try:
#                     if os.path.exists(file):
#                         os.remove(file)
#                 except:
#                     pass

#         if temp_files:
#             asyncio.create_task(cleanup(temp_files))
