from aiogram import types
from aiogram.filters import Command
from aiobot.core import router, bot
from aiobot.menu import main_menu
from aiogram.types import FSInputFile
from utils.tools import check_membership, rtl_text
from sources.config import PERSIANFINANCIALWATCHER, line
from database.models import User

# 👤 مشترک‌سازی کد بررسی عضویت
async def ensure_membership(message: types.Message) -> bool:
    user_id = message.from_user.id
    is_member = await check_membership(bot, PERSIANFINANCIALWATCHER, user_id)
    if not is_member:
        image_path = "./sources/images/join.jpg"
        photo = FSInputFile(image_path)
        await message.answer_photo(
            photo=photo,
            caption=(
                "⚠️ <b>دسترسی محدود!</b>\n"
                f"❌ شما هنوز در کانال <a href='https://t.me/{PERSIANFINANCIALWATCHER}'>ناظر مالی پارسی</a> عضو نیستید.\n"
                "📢 لطفاً ابتدا عضو شوید و سپس دوباره /start را بزنید."
            ),
            parse_mode="HTML"
        )
        return False
    return True

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    if not await ensure_membership(message):
        return

    sender = message.from_user
    full_name = f"{sender.first_name or ''} {sender.last_name or ''}".strip()
    username = f"@{sender.username}" if sender.username else "ندارد"
    user_id = sender.id

    existing_user = await User.get_or_none(telegram_id=user_id)
    if not existing_user:
        await User.create(
            telegram_id=user_id,
            full_name=full_name,
            username=sender.username
        )

    photo = FSInputFile("./sources/images/welcome.jpg")
    await message.answer_photo(
        photo=photo,
        caption=(
            f"🔗 <b>اطلاعات اتصال شما:</b>\n"
            f"👤 نام کامل: <b>{full_name}</b>\n"
            f"👤 نام کاربری: <b>{username}</b>\n"
            f"👤 آیدی عددی: <code>{user_id}</code>\n\n"
            f"{rtl_text(line)}\n"
            f"🟢 <b>درود بر شما، {full_name} گرامی</b>\n"
            "📢 می‌توانید از خدمات رایگان ربات استفاده کنید.\n"
            "💰 خدمات با این علامت نیاز به اشتراک دارند."
        ),
        parse_mode="HTML",
        reply_markup=main_menu()
    )

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    if not await ensure_membership(message):
        return

    photo = FSInputFile("./sources/images/help.jpg")
    await message.answer_photo(
        photo=photo,
        caption=(
            "📚 <b>راهنمای استفاده از ربات:</b>\n"
            "1. /start — شروع\n"
            "2. /status — بررسی وضعیت ربات\n"
            "3. /help — راهنمای استفاده\n"
            "4. برای دسترسی بیشتر، از منو استفاده کنید."
        ),
        parse_mode="HTML",
        reply_markup=main_menu()
    )

@router.message(Command("status"))
async def cmd_status(message: types.Message):
    await message.answer("🟢 ربات فعال است.")

# 👇 هندلر عمومی برای سایر پیام‌های متنی
@router.message()
async def handle_unknown(message: types.Message):
    photo = FSInputFile("./sources/images/invalid.jpg")
    await message.answer_photo(
        photo=photo,
        caption="❓ دستور نامعتبر است. لطفاً از منوی زیر استفاده کنید.",
        parse_mode="HTML",
        reply_markup=main_menu()
    )












# from aiogram import types
# from aiobot.router import router, bot
# from aiobot.menu import main_menu
# from aiogram.types import FSInputFile
# from utils.tools import check_membership
# from sources.config import PERSIANFINANCIALWATCHER, line
# from utils.tools import rtl_text
# from database.models import User

# @router.message()
# async def handle_all(message: types.Message):
#     sender = message.from_user
#     full_name = f"{sender.first_name or ''} {sender.last_name or ''}".strip()
#     username = f"@{sender.username}" if sender.username else "ندارد"
#     user_id = sender.id
    
#     persian_link = '<a href="https://t.me/PersianFinancialWatcher">ناظر مالی پارسی</a>'
 
#     is_member = await check_membership(bot, PERSIANFINANCIALWATCHER, user_id)

#     if not is_member:
#         image_path = "./sources/images/join.jpg"
#         photo = FSInputFile(image_path)

#         await message.answer_photo(
#             photo=photo,
#             caption=(
#                 f"🔗 <b>اطلاعات اتصال شما:</b>\n"
#                 f"👤 نام کامل: <b>{full_name}</b>\n"
#                 f"👤 نام کاربری: <b>{username}</b>\n"
#                 f"👤 آیدی عددی: <code>{user_id}</code>\n\n"
#                 f"{rtl_text(line)}\n"                
#                 f"⚠️ <b>دسترسی محدود!</b>\n"
#                 f"❌ شما هنوز در کانال {persian_link} عضو نیستید.\n"
#                 "📢 لطفاً ابتدا عضو شوید.\n"
#                 "🕐 سپس دوباره /start را بزنید."
#             ),
#             parse_mode="HTML"
#         )
#         return

#     if message.text == "/start":
#         # بررسی ثبت در دیتابیس
#         existing_user = await User.get_or_none(telegram_id=user_id)
#         if not existing_user:
#             await User.create(
#                 telegram_id=user_id,
#                 full_name=full_name,
#                 username=sender.username
#             )

#         image_path = "./sources/images/welcome.jpg"
#         photo = FSInputFile(image_path)
#         await message.answer_photo(
#             photo=photo,
#             caption=(
#                 f"🔗 <b>اطلاعات اتصال شما:</b>\n"
#                 f"👤 نام کامل: <b>{full_name}</b>\n"
#                 f"👤 نام کاربری: <b>{username}</b>\n"
#                 f"👤 آیدی عددی: <code>{user_id}</code>\n\n"
#                 f"{rtl_text(line)}\n"
#                 f"🟢 <b> درود   {full_name}   گرامی</b>\n"
#                 f"📢 شما میتوانید از خدمات مجانی این ربات استفاده کنید.\n"
#                 f"📢  خدماتی که با علامت 💰 مشخص شده است نیاز به خرید اشتراک دارند.\n"
#                 f"."
#             ),
#             parse_mode="HTML", reply_markup=main_menu()
#         )
#     elif message.text == "/status":
#         await message.answer("🟢 ربات فعال است.")
#     elif message.text == "/help":
#         image_path = "./sources/images/help.jpg"
#         photo = FSInputFile(image_path)
        
#         await message.answer_photo(
#             photo=photo,
#             caption=(
#                 "📚 <b>راهنمای استفاده از ربات:</b>\n"
#                 "1. برای شروع، دستور /start را بزنید.\n"
#                 "2. برای مشاهده وضعیت ربات، دستور /status را بزنید.\n"
#                 "3. برای دریافت راهنمایی، دستور /help را بزنید.\n"
#                 "4. برای دسترسی به منوی اصلی، از دکمه‌های زیر استفاده کنید."
#             ),
#             parse_mode="HTML", reply_markup=main_menu()
#         )
#     else:
#         image_path = "./sources/images/invalid.jpg"
#         photo = FSInputFile(image_path)
        
#         await message.answer_photo(
#             photo=photo,
#             caption=("❓ دستور نامعتبر است. لطفاً از منوی زیر استفاده کنید."),
#             parse_mode="HTML", reply_markup=main_menu()
#         )
