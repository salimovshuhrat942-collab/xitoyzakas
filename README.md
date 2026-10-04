# Xitoyshop — Telegram do'kon (bot + Mini App + admin panel)

## Railway'ga joylash (24/7)
1. Bu papkani GitHub'ga yuklang (token yozilgan fayl YUKLANMASIN).
2. railway.app → New Project → Deploy from GitHub repo.
3. Shu loyihada: New → Database → PostgreSQL. `DATABASE_URL` avtomatik ulanadi.
4. Service → Variables:
   - BOT_TOKEN = BotFather'dan olingan YANGI token
   - OWNER_ID = 8007670371
   - CHANNEL = @xitoyshopuz_rasmi
   - WEBAPP_URL = (keyingi qadamdan keyin)
5. Service → Settings → Networking → Generate Domain. Chiqqan https manzilni WEBAPP_URL ga yozing. Redeploy.
6. Botni kanalga ADMIN qiling (xabar joylash + "Adminlarni qo'shish" huquqi bilan).

## Foydalanish
- Bot /start → "Xitoyshop" tugmasi → Mini App.
- Siz (OWNER_ID) ilovada "Boshqaruv" tugmasini ko'rasiz: buyurtmalar, mahsulotlar, sotuvchilar, statistika.
- Mahsulotda "Kanalga joylash" → kanalda "Buyurtma berish" tugmali post chiqadi → bot zayavka oladi.
- Yangi buyurtma sizga va sotuvchiga botda keladi, holatni shu yerdan o'zgartirasiz.
