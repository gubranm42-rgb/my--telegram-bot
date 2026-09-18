import os
from dotenv import load_dotenv
from google import genai
import quiz

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=API_KEY)

# نص طويل للاختبار
with open("test.pdf", "rb") as f:
    pass

text = quiz.extract_text_from_pdf("test.pdf")
print(f"طول النص: {len(text)} حرفاً")

print("🧠 جاري توليد 10 أسئلة...")
questions = quiz.generate_quiz_from_text(
    client=client,
MODEL_NAME = "gemini-3.6-flash",
    text=text,
    num_questions=10,
    question_type="mixed",
    difficulty="medium",
)

print(f"✅ تم توليد: {len(questions)} سؤالاً")