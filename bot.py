import asyncio
import hashlib
import hmac
import html
import io
import json
import logging
import os
import time
from urllib.parse import parse_qsl

import asyncpg
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, Message, MenuButtonWebApp, ReplyKeyboardMarkup,
    ReplyKeyboardRemove, WebAppInfo,
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.environ["OWNER_ID"])
CHANNEL = os.environ.get("CHANNEL", "@xitoyshopuz_rasmi")
DATABASE_URL = os.environ["DATABASE_URL"]
WEBAPP_URL = os.environ["WEBAPP_URL"].rstrip("/")
PORT = int(os.environ.get("PORT", "8080"))

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)
pool: asyncpg.Pool = None
BOT_USERNAME = ""

STATUS_UZ = {"new": "🆕 Yangi", "accepted": "✅ Qabul qilindi",
             "delivered": "🚚 Yetkazildi", "cancelled": "❌ Bekor qilindi"}
e = html.escape


# ───────────────────────── DB ─────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS sellers (
  tg_id BIGINT PRIMARY KEY, name TEXT NOT NULL, channel TEXT,
  created_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS products (
  id SERIAL PRIMARY KEY, seller_id BIGINT NOT NULL, title TEXT NOT NULL,
  description TEXT DEFAULT '', price BIGINT NOT NULL DEFAULT 0, photo TEXT,
  active BOOLEAN DEFAULT TRUE, created_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS orders (
  id SERIAL PRIMARY KEY, product_id INT, seller_id BIGINT NOT NULL,
  product_title TEXT, price BIGINT, qty INT DEFAULT 1,
  customer_id BIGINT, customer_name TEXT, username TEXT, phone TEXT,
  address TEXT, note TEXT, status TEXT DEFAULT 'new',
  created_at TIMESTAMPTZ DEFAULT now());
"""


async def init_db():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    async with pool.acquire() as c:
        await c.execute(SCHEMA)


async def get_role(uid: int) -> str:
    if uid == OWNER_ID:
        return "owner"
    row = await pool.fetchrow("SELECT 1 FROM sellers WHERE tg_id=$1", uid)
    return "seller" if row else "customer"


# ───────────────────────── Orders / notify ─────────────────────────
def status_kb(oid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Qabul", callback_data=f"st:{oid}:accepted"),
        InlineKeyboardButton(text="🚚 Yetkazildi", callback_data=f"st:{oid}:delivered"),
        InlineKeyboardButton(text="❌ Bekor", callback_data=f"st:{oid}:cancelled"),
    ]])


def order_text(o) -> str:
    total = (o["price"] or 0) * (o["qty"] or 1)
    uname = f" (@{e(o['username'])})" if o["username"] else ""
    return (
        f"🆕 <b>Buyurtma #{o['id']}</b>\n"
        f"📦 {e(o['product_title'])} × {o['qty']}\n"
        f"💰 {total:,} so'm\n"
        f"👤 {e(o['customer_name'] or '-')}{uname}\n"
        f"📞 {e(o['phone'] or '-')}\n"
        f"📍 {e(o['address'] or '-')}\n"
        f"💬 {e(o['note'] or '-')}\n"
        f"Holat: {STATUS_UZ[o['status']]}"
    )


async def create_order(product, qty, user, name, phone, address, note):
    row = await pool.fetchrow(
        """INSERT INTO orders (product_id, seller_id, product_title, price, qty,
           customer_id, customer_name, username, phone, address, note)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING *""",
        product["id"], product["seller_id"], product["title"], product["price"], qty,
        user.get("id"), name, user.get("username"), phone, address, note)
    for uid in {row["seller_id"], OWNER_ID}:
        try:
            await bot.send_message(uid, order_text(row), reply_markup=status_kb(row["id"]))
        except Exception as ex:
            logging.warning("notify %s failed: %s", uid, ex)
    return row


@router.callback_query(F.data.startswith("st:"))
async def on_status(cb: CallbackQuery):
    _, oid, status = cb.data.split(":")
    o = await pool.fetchrow("SELECT * FROM orders WHERE id=$1", int(oid))
    if not o:
        return await cb.answer("Topilmadi")
    if cb.from_user.id != OWNER_ID and cb.from_user.id != o["seller_id"]:
        return await cb.answer("Ruxsat yo'q", show_alert=True)
    o = await pool.fetchrow("UPDATE orders SET status=$2 WHERE id=$1 RETURNING *", int(oid), status)
    await cb.message.edit_text(order_text(o), reply_markup=status_kb(o["id"]))
    await cb.answer("Yangilandi")
    if o["customer_id"]:
        try:
            await bot.send_message(
                o["customer_id"],
                f"Buyurtma #{o['id']} ({e(o['product_title'])}): {STATUS_UZ[status]}")
        except Exception:
            pass


# ───────────────────────── Bot handlers ─────────────────────────
class Buy(StatesGroup):
    qty = State()
    phone = State()
    address = State()


def app_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🛍 Xitoyshop", web_app=WebAppInfo(url=WEBAPP_URL))]])


@router.message(CommandStart())
async def start(m: Message, command: CommandObject, state: FSMContext):
    await state.clear()
    arg = command.args or ""
    if arg.startswith("p_") and arg[2:].isdigit():
        p = await pool.fetchrow("SELECT * FROM products WHERE id=$1 AND active", int(arg[2:]))
        if p:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛒 Buyurtma berish", callback_data=f"buy:{p['id']}")],
                [InlineKeyboardButton(text="🛍 Barcha mahsulotlar", web_app=WebAppInfo(url=WEBAPP_URL))]])
            cap = f"<b>{e(p['title'])}</b>\n\n{e(p['description'] or '')}\n\n💰 <b>{p['price']:,} so'm</b>"
            if p["photo"]:
                return await m.answer_photo(p["photo"], caption=cap, reply_markup=kb)
            return await m.answer(cap, reply_markup=kb)
    role = await get_role(m.from_user.id)
    extra = "\n\nAdmin panel ham shu ilova ichida." if role != "customer" else ""
    await m.answer("Assalomu alaykum! Xitoydan keltirilgan tovarlar do'koniga xush kelibsiz.\n"
                   "Pastdagi tugmani bosing 👇" + extra, reply_markup=app_kb())


@router.callback_query(F.data.startswith("buy:"))
async def buy(cb: CallbackQuery, state: FSMContext):
    pid = int(cb.data.split(":")[1])
    await state.set_state(Buy.qty)
    await state.update_data(pid=pid)
    await cb.message.answer("Nechta kerak? Raqam yuboring (masalan: 1)")
    await cb.answer()


@router.message(Buy.qty)
async def b_qty(m: Message, state: FSMContext):
    if not (m.text or "").isdigit() or not 0 < int(m.text) < 1000:
        return await m.answer("Iltimos, faqat raqam yuboring.")
    await state.update_data(qty=int(m.text))
    await state.set_state(Buy.phone)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📞 Raqamni yuborish", request_contact=True)]],
                             resize_keyboard=True, one_time_keyboard=True)
    await m.answer("Telefon raqamingiz:", reply_markup=kb)


@router.message(Buy.phone)
async def b_phone(m: Message, state: FSMContext):
    phone = m.contact.phone_number if m.contact else (m.text or "").strip()
    if len(phone) < 7:
        return await m.answer("Telefon raqamini to'g'ri yuboring.")
    await state.update_data(phone=phone)
    await state.set_state(Buy.address)
    await m.answer("Manzilingiz (viloyat, shahar, ko'cha):", reply_markup=ReplyKeyboardRemove())


@router.message(Buy.address)
async def b_addr(m: Message, state: FSMContext):
    d = await state.get_data()
    await state.clear()
    p = await pool.fetchrow("SELECT * FROM products WHERE id=$1", d["pid"])
    if not p:
        return await m.answer("Mahsulot topilmadi.")
    name = m.from_user.full_name
    user = {"id": m.from_user.id, "username": m.from_user.username}
    o = await create_order(p, d["qty"], user, name, d["phone"], (m.text or "").strip(), "")
    await m.answer(f"✅ Buyurtma #{o['id']} qabul qilindi! Tez orada siz bilan bog'lanamiz.")


# ───────────────────────── Web API ─────────────────────────
class ApiError(Exception):
    def __init__(self, msg, code=400):
        self.msg, self.code = msg, code


def check_init(init_data: str):
    data = dict(parse_qsl(init_data, keep_blank_values=True))
    h = data.pop("hash", None)
    if not h:
        return None
    s = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(hmac.new(secret, s.encode(), hashlib.sha256).hexdigest(), h):
        return None
    if time.time() - int(data.get("auth_date", 0)) > 7 * 86400:
        return None
    return json.loads(data["user"])


@web.middleware
async def mw(req: web.Request, handler):
    try:
        if req.path.startswith("/api/"):
            user = check_init(req.headers.get("X-Init-Data", ""))
            if not user:
                raise ApiError("Telegram ichida oching", 401)
            req["user"] = user
            req["role"] = await get_role(user["id"])
        return await handler(req)
    except ApiError as ex:
        return web.json_response({"error": ex.msg}, status=ex.code)


def jr(data):
    return web.json_response(data, dumps=lambda x: json.dumps(x, default=str))


def need_admin(req):
    if req["role"] == "customer":
        raise ApiError("Ruxsat yo'q", 403)


def prod_dict(r):
    d = dict(r)
    d["photo"] = f"/photo/{r['photo']}" if r["photo"] else None
    return d


async def api_me(req):
    u = req["user"]
    return jr({"id": u["id"], "name": u.get("first_name", ""), "role": req["role"]})


async def api_products(req):
    if req.query.get("mine") and req["role"] != "customer":
        if req["role"] == "owner":
            rows = await pool.fetch("""SELECT p.*, COALESCE(s.name,'Bosh admin') AS seller_name
                FROM products p LEFT JOIN sellers s ON s.tg_id=p.seller_id ORDER BY p.id DESC""")
        else:
            rows = await pool.fetch("""SELECT p.*, 'Siz' AS seller_name FROM products p
                WHERE seller_id=$1 ORDER BY id DESC""", req["user"]["id"])
    else:
        rows = await pool.fetch("SELECT *, '' AS seller_name FROM products WHERE active ORDER BY id DESC")
    return jr([prod_dict(r) for r in rows])


async def photo_to_file_id(data: bytes, uid: int) -> str:
    for target in (uid, OWNER_ID):
        try:
            m = await bot.send_photo(target, BufferedInputFile(data, "p.jpg"), disable_notification=True)
            fid = m.photo[-1].file_id
            try:
                await bot.delete_message(target, m.message_id)
            except Exception:
                pass
            return fid
        except Exception:
            continue
    raise ApiError("Rasm yuklanmadi. Botga /start bosing.")


async def api_save_product(req):
    need_admin(req)
    uid = req["user"]["id"]
    f = await req.post()
    title = (f.get("title") or "").strip()
    if not title:
        raise ApiError("Nomini kiriting")
    try:
        price = int(f.get("price") or 0)
    except ValueError:
        raise ApiError("Narx noto'g'ri")
    desc = (f.get("description") or "").strip()
    active = f.get("active", "1") == "1"
    fid = None
    ph = f.get("photo")
    if ph is not None and hasattr(ph, "file") and ph.filename:
        fid = await photo_to_file_id(ph.file.read(), uid)
    pid = f.get("id")
    if pid:
        old = await pool.fetchrow("SELECT * FROM products WHERE id=$1", int(pid))
        if not old or (req["role"] != "owner" and old["seller_id"] != uid):
            raise ApiError("Ruxsat yo'q", 403)
        await pool.execute(
            "UPDATE products SET title=$2, description=$3, price=$4, active=$5, photo=COALESCE($6, photo) WHERE id=$1",
            int(pid), title, desc, price, active, fid)
    else:
        pid = await pool.fetchval(
            "INSERT INTO products (seller_id,title,description,price,photo,active) VALUES ($1,$2,$3,$4,$5,$6) RETURNING id",
            uid, title, desc, price, fid, active)
    return jr({"ok": True, "id": int(pid)})


async def own_product(req, pid):
    p = await pool.fetchrow("SELECT * FROM products WHERE id=$1", pid)
    if not p or (req["role"] != "owner" and p["seller_id"] != req["user"]["id"]):
        raise ApiError("Ruxsat yo'q", 403)
    return p


async def api_delete_product(req):
    need_admin(req)
    p = await own_product(req, int(req.match_info["id"]))
    await pool.execute("DELETE FROM products WHERE id=$1", p["id"])
    return jr({"ok": True})


async def api_post_product(req):
    need_admin(req)
    p = await own_product(req, int(req.match_info["id"]))
    s = await pool.fetchrow("SELECT channel FROM sellers WHERE tg_id=$1", p["seller_id"])
    chat = (s["channel"] if s and s["channel"] else CHANNEL)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="🛒 Buyurtma berish", url=f"https://t.me/{BOT_USERNAME}?start=p_{p['id']}")]])
    cap = f"<b>{e(p['title'])}</b>\n\n{e(p['description'] or '')}\n\n💰 <b>{p['price']:,} so'm</b>"
    try:
        if p["photo"]:
            await bot.send_photo(chat, p["photo"], caption=cap, reply_markup=kb)
        else:
            await bot.send_message(chat, cap, reply_markup=kb)
    except Exception as ex:
        raise ApiError(f"Kanalga joylanmadi: bot kanalda admin ekanini tekshiring ({ex})")
    return jr({"ok": True})


async def api_create_order(req):
    d = await req.json()
    items = d.get("items") or []
    name, phone = (d.get("name") or "").strip(), (d.get("phone") or "").strip()
    if not items or not name or len(phone) < 7:
        raise ApiError("Ism va telefonni to'ldiring")
    ids = []
    for it in items[:30]:
        p = await pool.fetchrow("SELECT * FROM products WHERE id=$1 AND active", int(it["id"]))
        if not p:
            continue
        qty = max(1, min(999, int(it.get("qty", 1))))
        o = await create_order(p, qty, req["user"], name, phone,
                               (d.get("address") or "").strip(), (d.get("note") or "").strip())
        ids.append(o["id"])
    if not ids:
        raise ApiError("Mahsulot topilmadi")
    return jr({"ok": True, "ids": ids})


async def api_orders(req):
    need_admin(req)
    if req["role"] == "owner":
        rows = await pool.fetch("""SELECT o.*, COALESCE(s.name,'Bosh admin') AS seller_name
            FROM orders o LEFT JOIN sellers s ON s.tg_id=o.seller_id ORDER BY o.id DESC LIMIT 300""")
    else:
        rows = await pool.fetch("SELECT *, 'Siz' AS seller_name FROM orders WHERE seller_id=$1 ORDER BY id DESC LIMIT 300",
                                req["user"]["id"])
    return jr([dict(r) for r in rows])


async def api_order_status(req):
    need_admin(req)
    oid = int(req.match_info["id"])
    status = (await req.json()).get("status")
    if status not in STATUS_UZ:
        raise ApiError("Noto'g'ri holat")
    o = await pool.fetchrow("SELECT * FROM orders WHERE id=$1", oid)
    if not o or (req["role"] != "owner" and o["seller_id"] != req["user"]["id"]):
        raise ApiError("Ruxsat yo'q", 403)
    await pool.execute("UPDATE orders SET status=$2 WHERE id=$1", oid, status)
    if o["customer_id"]:
        try:
            await bot.send_message(o["customer_id"],
                                   f"Buyurtma #{oid} ({e(o['product_title'])}): {STATUS_UZ[status]}")
        except Exception:
            pass
    return jr({"ok": True})


async def api_stats(req):
    need_admin(req)
    where, args = ("", []) if req["role"] == "owner" else ("WHERE seller_id=$1", [req["user"]["id"]])
    rows = await pool.fetch(f"SELECT status, COUNT(*) c, COALESCE(SUM(price*qty),0) s FROM orders {where} GROUP BY status", *args)
    return jr({r["status"]: {"count": r["c"], "sum": int(r["s"])} for r in rows})


def need_owner(req):
    if req["role"] != "owner":
        raise ApiError("Faqat bosh admin", 403)


async def api_sellers(req):
    need_owner(req)
    rows = await pool.fetch("SELECT * FROM sellers ORDER BY created_at DESC")
    return jr([dict(r) for r in rows])


async def api_add_seller(req):
    need_owner(req)
    d = await req.json()
    try:
        tg_id = int(str(d.get("tg_id", "")).strip())
    except ValueError:
        raise ApiError("Telegram ID raqam bo'lishi kerak")
    name = (d.get("name") or "").strip() or str(tg_id)
    channel = (d.get("channel") or "").strip() or None
    if channel and not channel.startswith("@"):
        channel = "@" + channel.replace("https://t.me/", "").lstrip("@")
    await pool.execute(
        """INSERT INTO sellers (tg_id,name,channel) VALUES ($1,$2,$3)
           ON CONFLICT (tg_id) DO UPDATE SET name=$2, channel=$3""", tg_id, name, channel)
    # Kanalda admin huquqi (bot kanalda "Adminlarni qo'shish" huquqiga ega bo'lsa)
    promoted = False
    for chat in {CHANNEL, channel} - {None}:
        try:
            await bot.promote_chat_member(chat, tg_id, can_post_messages=True,
                                          can_edit_messages=True, can_delete_messages=True)
            promoted = True
        except Exception as ex:
            logging.warning("promote failed in %s: %s", chat, ex)
    try:
        await bot.send_message(tg_id, "Siz Xitoyshop sotuvchisi qilib qo'shildingiz. /start bosing va ilovani oching.",
                               reply_markup=app_kb())
    except Exception:
        pass
    return jr({"ok": True, "channel_admin": promoted})


async def api_del_seller(req):
    need_owner(req)
    tg_id = int(req.match_info["id"])
    await pool.execute("DELETE FROM sellers WHERE tg_id=$1", tg_id)
    try:
        await bot.promote_chat_member(CHANNEL, tg_id, can_post_messages=False, can_edit_messages=False,
                                      can_delete_messages=False)
    except Exception:
        pass
    return jr({"ok": True})


async def photo(req):
    fid = req.match_info["fid"]
    try:
        f = await bot.get_file(fid)
        buf = io.BytesIO()
        await bot.download_file(f.file_path, buf)
    except Exception:
        raise web.HTTPNotFound()
    return web.Response(body=buf.getvalue(), content_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=86400"})


async def index(_):
    return web.FileResponse(os.path.join(os.path.dirname(__file__), "webapp", "index.html"))


async def health(_):
    return web.Response(text="ok")


def make_app():
    app = web.Application(middlewares=[mw], client_max_size=15 * 1024 * 1024)
    app.add_routes([
        web.get("/", index), web.get("/health", health), web.get("/photo/{fid}", photo),
        web.get("/api/me", api_me),
        web.get("/api/products", api_products),
        web.post("/api/products", api_save_product),
        web.delete("/api/products/{id}", api_delete_product),
        web.post("/api/products/{id}/post", api_post_product),
        web.post("/api/orders", api_create_order),
        web.get("/api/orders", api_orders),
        web.post("/api/orders/{id}/status", api_order_status),
        web.get("/api/stats", api_stats),
        web.get("/api/sellers", api_sellers),
        web.post("/api/sellers", api_add_seller),
        web.delete("/api/sellers/{id}", api_del_seller),
    ])
    return app


async def main():
    global BOT_USERNAME
    await init_db()
    BOT_USERNAME = (await bot.get_me()).username
    await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Xitoyshop", web_app=WebAppInfo(url=WEBAPP_URL)))
    runner = web.AppRunner(make_app())
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
