import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
print("مفتاح Gemini:", API_KEY[:10] + "..." if API_KEY else "غير موجود")

client = genai.Client(api_key=API_KEY)

try:
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="قل مرحبا فقط",
    )
    print("✅ نجح الاتصال!")
    print("الرد:", response.text)
except Exception as e:
    print("❌ فشل الاتصال:")
    print(type(e).__name__, ":", e)