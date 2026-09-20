from aiogram import Router
from handlers.inline_commands import router as inline_commands_router

callback_router = Router()
callback_router.include_router(inline_commands_router)
