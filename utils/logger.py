import logging, html, os
from datetime import datetime
from aiogram import Bot
import asyncio
from sources.config import ADMIN_TOKEN, PFW_REPORTER

bot = Bot(token=ADMIN_TOKEN)  # فقط یکبار ساخته می‌شود

# def setup_logger():
#     if not os.path.exists("logs"):
#         os.makedirs("logs")

#     log_filename = datetime.now().strftime("logs/bot_%Y-%m-%d.log")

#     logger = logging.getLogger("bot_logger")
#     logger.setLevel(logging.INFO)

#     console_handler = logging.StreamHandler()
#     console_format = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
#     console_handler.setFormatter(console_format)

#     file_handler = logging.FileHandler(log_filename, encoding="utf-8")
#     file_format = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
#     file_handler.setFormatter(file_format)

#     logger.addHandler(console_handler)
#     logger.addHandler(file_handler)

#     return logger

async def adminReport(message: str):
    try:
        message = html.escape(message)  # امن‌سازی کاراکترهای HTML مثل < > &
        await bot.send_message(chat_id=PFW_REPORTER, text=f"📣 <b>System Report</b>:\n{message}", parse_mode="HTML")
    except Exception as e:
        logger = logging.getLogger("bot_logger")
        logger.error(f"Failed to send message to admin: {e}")

