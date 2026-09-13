import os
from dotenv import load_dotenv
from telegram import Bot
import asyncio

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
print("التوكن:", TOKEN[:10] + "..." if TOKEN else "غير موجود")

async def main():
    bot = Bot(token=TOKEN)
    try:
        me = await bot.get_me()
        print("✅ نجح الاتصال بـ Telegram!")
        print("اسم البوت:", me.first_name)
        print("المعرف:", me.username)
    except Exception as e:
        print("❌ فشل الاتصال:")
        print(type(e).name, ":", e)

asyncio.run(main())