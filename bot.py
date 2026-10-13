import asyncio
import json
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    WebAppInfo,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import BOT_TOKEN, ADMIN_CHAT_ID, WEBAPP_URL
from products import PRODUCTS, SELLERS

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def order_number() -> str:
    # Masalan: #241013-0847  (sana + soat:minut)
    return "#" + datetime.now().strftime("%y%m%d-%H%M")


@dp.message(CommandStart())
async def start_handler(message: Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛍️ Xitoyshop — Do'konni ochish",
                    web_app=WebAppInfo(url=WEBAPP_URL),
                )
            ]
        ]
    )
    await message.answer(
        "Xitoyshopga xush kelibsiz!\n\n"
        "Bo'limlardan birini tanlab, kerakli mahsulotni savatga qo'shing "
        "va buyurtma bering — operatorimiz tez orada siz bilan bog'lanadi.",
        reply_markup=kb,
    )


@dp.message(F.web_app_data)
async def webapp_data_handler(message: Message):
    try:
        data = json.loads(message.web_app_data.data)
    except (ValueError, AttributeError):
        await message.answer("Buyurtmani o'qib bo'lmadi, qaytadan urinib ko'ring.")
        return

    if data.get("type") != "order":
        return

    items = data.get("items", [])
    name = data.get("name", "—")
    phone = data.get("phone", "—")
    address = data.get("address", "—")
    total = data.get("total", 0)
    num = order_number()

    # --- buyurtma tarkibini o'qiladigan matnga aylantirish ---
    lines = []
    sellers_involved = set()
    for item in items:
        pid = item.get("id")
        qty = item.get("qty", 1)
        product = PRODUCTS.get(pid)
        if not product:
            lines.append(f"• Noma'lum mahsulot (id {pid}) × {qty}")
            continue
        sellers_involved.add(product["seller"])
        line_total = product["price"] * qty
        lines.append(f"• {product['name']} × {qty} — {line_total:,.0f}".replace(",", " ") + " so'm")

    seller_names = ", ".join(SELLERS.get(s, s) for s in sellers_involved) or "—"
    items_text = "\n".join(lines) if lines else "—"
    total_text = f"{total:,.0f}".replace(",", " ") + " so'm"

    user = message.from_user
    username_part = f"@{user.username}" if user.username else f"id:{user.id}"

    admin_text = (
        f"🆕 Yangi buyurtma {num}\n\n"
        f"👤 Mijoz: {name}\n"
        f"📞 Tel: {phone}\n"
        f"📍 Manzil: {address}\n"
        f"💬 Telegram: {username_part}\n"
        f"🏬 Bo'lim(lar): {seller_names}\n\n"
        f"{items_text}\n\n"
        f"💰 Jami: {total_text}"
    )

    if ADMIN_CHAT_ID:
        try:
            await bot.send_message(ADMIN_CHAT_ID, admin_text)
        except Exception:
            logging.exception("Adminga buyurtmani yuborishda xato")

    await message.answer(
        f"Buyurtmangiz qabul qilindi! Raqami: {num}\n\n"
        f"Jami: {total_text}\n\n"
        f"Operatorimiz tez orada {phone} raqamiga qo'ng'iroq qiladi."
    )


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
