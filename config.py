import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://example.com/xitoyshop-market.html")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN .env faylida ko'rsatilmagan")
