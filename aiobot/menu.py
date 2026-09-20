from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def main_menu():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 اشتراک طلایی ( بزودی )", callback_data="plan_gold")],
        [InlineKeyboardButton(text="💰 اشتراک نقره‌ای ( 5 دلار درماه )", callback_data="plan_silver")],
        [InlineKeyboardButton(text="🟢 اشتراک برنزی ( جهت آزمایش _ رایگان )", callback_data="plan_bronze")]
    ])
    return keyboard

