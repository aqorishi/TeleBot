from aiogram import F, types, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiobot.router import router
from fsm.states import APIRegistration
from database.models import User, UserAPI
from fsm.states import APIInputState
from aiogram.filters import Command
from aiobot.core import router, bot


@router.message(APIRegistration.entering_customer_id)
async def customer_id_entered(message: types.Message, state: FSMContext):
    await state.update_data(customer_id=message.text.strip())
    await message.answer("🔑 لطفاً API Key خود را وارد کنید:")
    await state.set_state(APIRegistration.entering_api_key)

@router.message(APIRegistration.entering_api_key)
async def api_key_entered(message: types.Message, state: FSMContext):
    await state.update_data(api_key=message.text.strip())
    await message.answer("🔐 لطفاً API Secret خود را وارد کنید:")
    await state.set_state(APIRegistration.entering_api_secret)

@router.message(APIRegistration.entering_api_secret)
async def api_secret_entered(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_telegram_id = message.from_user.id
    user = await User.get_or_none(telegram_id=user_telegram_id)

    if not user:
        await message.answer("❌ ابتدا با دستور /start ثبت‌نام کنید.")
        await state.clear()
        return

    await UserAPI.update_or_create(
        defaults={
            "exchange": data["exchange"],
            "customer_id": data["customer_id"],
            "api_key": data["api_key"],
            "api_secret": message.text.strip()
        },
        user=user
    )

    await message.answer("✅ اطلاعات API شما با موفقیت ذخیره شد.")
    await state.clear()













# router = Router()

# @router.message(F.text == "/set_api")
# async def set_api_command(message: types.Message, state: FSMContext):
#     await message.answer("🧭 لطفاً صرافی مورد نظر را انتخاب کنید:\n👉 bybit یا bitunix")
#     await state.set_state(APIInputState.waiting_for_exchange)


# @router.message(APIInputState.waiting_for_exchange)
# async def process_exchange(message: types.Message, state: FSMContext):
#     exchange = message.text.lower()
#     if exchange not in ["bybit", "bitunix"]:
#         await message.answer("❌ فقط یکی از گزینه‌های bybit یا bitunix را وارد کنید.")
#         return

#     await state.update_data(exchange=exchange)
#     await message.answer("🛠 حالا لطفاً API Key خود را وارد کنید:")
#     await state.set_state(APIInputState.waiting_for_api_key)


# @router.message(APIInputState.waiting_for_api_key)
# async def process_api_key(message: types.Message, state: FSMContext):
#     await state.update_data(api_key=message.text)
#     await message.answer("🔐 لطفاً API Secret خود را وارد کنید:")
#     await state.set_state(APIInputState.waiting_for_api_secret)


# @router.message(APIInputState.waiting_for_api_secret)
# async def process_api_secret(message: types.Message, state: FSMContext):
#     user_id = message.from_user.id
#     data = await state.get_data()

#     # ذخیره در دیتابیس
#     user = await User.get_or_none(telegram_id=user_id)
#     if not user:
#         await message.answer("❗ ابتدا با دستور /start ثبت‌نام کنید.")
#         return

#     await UserAPI.update_or_create(
#         defaults={
#             "api_key": data["api_key"],
#             "api_secret": message.text,
#         },
#         user=user,
#         exchange=data["exchange"],
#     )

#     await message.answer("✅ اطلاعات API شما با موفقیت ذخیره شد.")
#     await state.clear()


# @router.message(F.text == "/add_api")
# async def start_api_registration(message: Message, state: FSMContext):
#     keyboard = ReplyKeyboardMarkup(
#         keyboard=[
#             [KeyboardButton(text="Bybit")],
#             [KeyboardButton(text="Bitunix")]
#         ],
#         resize_keyboard=True
#     )
#     await message.answer("📌 لطفاً صرافی موردنظر را انتخاب کنید:", reply_markup=keyboard)
#     await state.set_state(APIRegistration.choosing_exchange)


# @router.message(APIRegistration.choosing_exchange)
# async def exchange_chosen(message: Message, state: FSMContext):
#     exchange = message.text.strip().lower()
#     if exchange not in ["bybit", "bitunix"]:
#         await message.answer("❌ فقط یکی از گزینه‌های Bybit یا Bitunix را انتخاب کنید.")
#         return

#     await state.update_data(exchange=exchange)
#     await message.answer("🔑 لطفاً API Key خود را وارد کنید:", reply_markup=ReplyKeyboardRemove())
#     await state.set_state(APIRegistration.entering_api_key)


# @router.message(APIRegistration.entering_api_key)
# async def api_key_entered(message: Message, state: FSMContext):
#     await state.update_data(api_key=message.text.strip())
#     await message.answer("🔐 لطفاً API Secret خود را وارد کنید:")
#     await state.set_state(APIRegistration.entering_api_secret)



# @router.message(APIRegistration.entering_api_secret)
# async def api_secret_entered(message: Message, state: FSMContext):
#     data = await state.get_data()
#     user_telegram_id = message.from_user.id

#     user = await User.get_or_none(telegram_id=user_telegram_id)
#     if not user:
#         await message.answer("❌ ابتدا با دستور /start ثبت‌نام کنید.")
#         await state.clear()
#         return

#     # حذف API قبلی اگر وجود داشته باشد
#     existing_api = await UserAPI.get_or_none(user=user)
#     if existing_api:
#         await existing_api.delete()

#     # ایجاد API جدید
#     await UserAPI.create(
#         user=user,
#         exchange=data["exchange"],
#         api_key=data["api_key"],
#         api_secret=message.text.strip()
#     )

#     await message.answer("✅ اطلاعات API شما با موفقیت ذخیره شد.")
#     await state.clear()


# @router.message(F.text == "/my_api")
# async def show_user_api(message: types.Message):
#     user_telegram_id = message.from_user.id
#     user = await User.get_or_none(telegram_id=user_telegram_id).prefetch_related("api_credentials")

#     if not user:
#         await message.answer("❌ ابتدا با دستور /start ثبت‌نام کنید.")
#         return

#     if not hasattr(user, "api_credentials") or user.api_credentials is None:
#         await message.answer("ℹ️ شما هنوز اطلاعات API ثبت نکرده‌اید.")
#         return

#     api = user.api_credentials
#     await message.answer(
#         f"🔐 اطلاعات API شما:\n"
#         f"📊 صرافی: <b>{api.exchange}</b>\n"
#         f"🔑 API Key: <code>{api.api_key}</code>\n"
#         f"📅 ثبت شده در: {api.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
#         parse_mode="HTML"
#     )


# @router.message(F.text == "/delete_api")
# async def delete_user_api(message: types.Message):
#     user_telegram_id = message.from_user.id
#     user = await User.get_or_none(telegram_id=user_telegram_id).prefetch_related("api_credentials")

#     if not user or not hasattr(user, "api_credentials") or user.api_credentials is None:
#         await message.answer("❌ اطلاعات API برای حذف وجود ندارد.")
#         return

#     await user.api_credentials.delete()
#     await message.answer("🗑️ اطلاعات API شما با موفقیت حذف شد.")
