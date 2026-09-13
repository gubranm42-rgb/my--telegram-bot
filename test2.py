import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=API_KEY)

# اختبار بنفس البرومبت الذي يستخدمه البوت
prompt = (
    "أنت مساعد دراسي ذكي ودود. أجب بالعربية بشكل واضح ومختصر.\n"
    "استخدم التنسيق الجميل عند الحاجة (نقاط، عناوين).\n\n"
    "سجل المحادثة:\nالمستخدم: اشرح لي الجاذبية\n"
    "الرد:"
)

try:
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    print("✅ نجح!")
    print("الرد:", response.text)
except Exception as e:
    print("❌ فشل!")
    print(type(e).name)
    print(str(e))