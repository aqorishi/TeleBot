from aiogram import Bot, Router, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from sources.config import BOT_TOKEN

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

router = Router()
dp = Dispatcher(storage=MemoryStorage())
