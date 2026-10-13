# Xitoyshop bot

## O'rnatish
1. `pip install -r requirements.txt`
2. `.env.example` ni `.env` qilib nusxalang va to'ldiring:
   - `BOT_TOKEN` — BotFather dan olingan token
   - `ADMIN_CHAT_ID` — buyurtmalar tushadigan guruh/kanal ID (o'zingizning shaxsiy chat ID'ingiz ham bo'lishi mumkin)
   - `WEBAPP_URL` — `xitoyshop-market.html` joylashgan HTTPS manzil (Netlify'da statik sifatida joylashtiring)
3. `python bot.py`

## Muhim
- `products.py` dagi `PRODUCTS` va `SELLERS` ro'yxati `xitoyshop-market.html` ichidagi
  bir xil nomli ro'yxatlar bilan **har doim bir xil** bo'lishi kerak. Mini App'ga
  yangi mahsulot/sotuvchi qo'shganingizda, shu faylga ham xuddi shu yozuvni qo'shing.
- Bot hozircha onlayn to'lovsiz — faqat buyurtmani qabul qilib, admin guruhiga
  yuboradi va operator mijozga qo'ng'iroq qiladi (loyihangizdagi rejaga mos).
- Railway yoki Render'da doimiy ishlashi uchun: repo'ni yuklang, `BOT_TOKEN` va
  `ADMIN_CHAT_ID` ni Environment Variables bo'limiga qo'shing, start buyrug'i
  sifatida `python bot.py` ni ko'rsating.
