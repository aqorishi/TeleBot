from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    FSInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiobot.core import router as core_router  # اگر هنوز نیاز هست
from aiobot.menu import main_menu
from fsm.states import APIRegistration



router = Router()

@router.callback_query(lambda c: c.data.startswith("plan_"))
async def handle_plan_selection(callback: types.CallbackQuery):
    plan = callback.data.replace("plan_", "")
    if plan == "bronze":
        image = FSInputFile("sources/images/bybit_demo.jpg")
        link = "https://www.bybit.com/invite?ref=RNRXZG4"
        # link = "https://api-demo.bybit.com"
        guide_file = FSInputFile("/home/botuser/bot/sources/docs/bybit_guide.pdf")
    else:
        image = FSInputFile("sources/images/bitunix.jpg")
        link = "https://www.bitunix.com/register?inviteCode=cdx553"
        # link = "https://bitunix.com/referral/123456"  # لینک ریفرال واقعی‌ات
        guide_file = FSInputFile("/home/botuser/bot/sources/docs/bitunix_guide.pdf")

    # ارسال پیام راهنمایی
    await callback.message.answer_photo(
        photo=image,
        caption=(
            f"📌 <b>راهنمای ثبت‌ نام در صرافی {'Bybit دمو' if plan == 'bronze' else 'Bitunix'}:</b>\n"
            f"🔗 لینک ثبت‌نام:\n <a href='{link}'>{link}</a>\n\n"
            "1. ابتدا از لینک بالا وارد شوید.\n"
            "2. طبق فایل راهنما ثبت‌نام کنید.\n"
            "3. سپس گزینه زیر را انتخاب کنید."
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➡️ وارد کردن Customer ID", callback_data=f"step_customer_{plan}")],
            [InlineKeyboardButton(text="📄 دانلود فایل راهنما", callback_data=f"download_guide_{plan}")],
            [InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="back_main_menu")],
        ])
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("download_guide_"))
async def download_guide_file(callback: types.CallbackQuery):
    plan = callback.data.replace("download_guide_", "")
    path = f"/home/botuser/bot/sources/docs/{'bybit_guide.pdf' if plan == 'bronze' else 'bitunix_guide.pdf'}"
    file = FSInputFile(path)
    await callback.message.answer_document(file)
    await callback.answer("📎 فایل راهنما ارسال شد.")

@router.callback_query(lambda c: c.data == "back_main_menu")
async def go_back_main_menu(callback: types.CallbackQuery):
    image = FSInputFile("sources/images/bot.jpg")
    await callback.message.answer_photo(
        photo=image,
        caption="🔙 به منوی اصلی برگشتید.",
        reply_markup=main_menu()
    )
    await callback.answer()

    
@router.callback_query(lambda c: c.data.startswith("step_customer_"))
async def step_customer_id(callback: types.CallbackQuery, state: FSMContext):
    plan = callback.data.replace("step_customer_", "")
    exchange = "bybit" if plan == "bronze" else "bitunix"
    await state.update_data(exchange=exchange)
    await callback.message.answer("🧾 لطفاً Customer ID خود را وارد کنید:")
    await state.set_state(APIRegistration.entering_customer_id)
    await callback.answer()
    

# مرحله 1: گرفتن Customer ID *************************************
@router.message(APIRegistration.entering_customer_id)
async def get_customer_id(message: types.Message, state: FSMContext):
    customer_id = message.text.strip()
    await state.update_data(customer_id=customer_id)
    await message.answer("🛡 لطفاً API Key خود را وارد کنید:")
    await state.set_state(APIRegistration.entering_api_key)

# مرحله 2: گرفتن API Key
@router.message(APIRegistration.entering_api_key)
async def get_api_key(message: types.Message, state: FSMContext):
    api_key = message.text.strip()
    await state.update_data(api_key=api_key)
    await message.answer("🔐 لطفاً API Secret خود را وارد کنید:")
    await state.set_state(APIRegistration.entering_api_secret)

# مرحله 3: گرفتن API Secret و نمایش نهایی
@router.message(APIRegistration.entering_api_secret)
async def get_api_secret(message: types.Message, state: FSMContext):
    api_secret = message.text.strip()
    data = await state.get_data()

    await message.answer(
        "✅ اطلاعات شما ثبت شد:\n"
        f"📌 صرافی: {data.get('exchange')}\n"
        f"🧾 Customer ID: <code>{data.get('customer_id')}</code>\n"
        f"🔑 API Key: <code>{data.get('api_key')}</code>\n"
        f"🔐 API Secret: <code>{api_secret}</code>\n\n"
        "اگر اشتباهی رخ داده، مجدد از منوی اصلی اقدام کنید.",
        parse_mode="HTML",
        reply_markup=main_menu()
    )

    # (اختیاری) ذخیره اطلاعات در دیتابیس

    await state.clear()
