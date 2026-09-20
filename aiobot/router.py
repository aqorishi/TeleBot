from aiobot.core import dp, router
from aiobot import commands  # commands فقط router و dp رو استفاده می‌کنه

# اینجا دستورات و routerها attach میشن
dp.include_router(router)


# # from aiogram import Bot, Dispatcher, Router
# from aiogram import Dispatcher, Router
# from aiogram.client.default import DefaultBotProperties
# from aiogram.enums import ParseMode
# from aiogram.fsm.storage.memory import MemoryStorage
# from sources.config import BOT_TOKEN
# from aiobot import commands

# bot = Bot(
#     token=BOT_TOKEN,
#     default=DefaultBotProperties(parse_mode=ParseMode.HTML)
# )

# dp = Dispatcher(storage=MemoryStorage())

# router = Router()  # 👈 این خط رو اضافه کن تا بتونی ایمپورتش کنی



# from sources.config import BOT_TOKEN
# from aiogram import Bot, Dispatcher, Router
# from aiogram.client.default import DefaultBotProperties

# # setup Bot with default properties
# bot = Bot(
#     token=BOT_TOKEN,
#     default=DefaultBotProperties(parse_mode="HTML"), timeout=30,
# )

# # Dispatcher and Router are defined but not connected yet
# dp = Dispatcher()
# router = Router()
