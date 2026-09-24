import asyncio, aiohttp
import sources.config as config
from aiobot.core import bot, dp

# from database.db import init_db
from dotenv import load_dotenv
from utils.logger import adminReport
from apps.analyzer.analyzer import start_analyzer_loop
from apps.channel_monitor.channel_monitor import setup_channel_monitor
from apps.position_manager.position_manager import startMonitoring
from telethon import TelegramClient
from dispatcher.callback_router import callback_router

BOT_SESSION = config.BOT_SESSION
API_ID = config.API_ID
API_HASH = config.API_HASH
API_KEY = config.API_KEY
API_SECRET = config.API_SECRET
exchangeURL = config.exchangeURL

dp.include_router(callback_router)

# Telethon setup
client = TelegramClient(BOT_SESSION, API_ID, API_HASH)


async def main():
    # await init_db()
    await adminReport("✅ Bot started successfully.")
    await bot.delete_webhook(drop_pending_updates=True)

    await client.start()  # Telethon client
    setup_channel_monitor(client)
    await adminReport("📡 Telethon (monitor) started...")

    session = aiohttp.ClientSession()  # aiohttp session for Bybit API

    try:
        await asyncio.gather(
            dp.start_polling(bot),
            # start_analyzer_loop(client),
            startMonitoring(session, API_KEY, API_SECRET, exchangeURL),
        )
    finally:
        await bot.session.close()
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())
