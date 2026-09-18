# quiz.py
# -*- coding: utf-8 -*-

import os
import json
import time
import logging
import concurrent.futures

from pypdf import PdfReader
from google.genai import types

logger = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 10000
TIMEOUT_SECONDS = 180
MAX_ATTEMPTS = 2
RETRY_DELAY = 5


# ==================== استخراج النص من PDF ====================
def extract_text_from_pdf(pdf_path):
    try:
        reader = PdfReader(pdf_path)
        parts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
        full = chr(10).join(parts).strip()
        logger.info("تم استخراج " + str(len(full)) + " حرفا من PDF")
        return full
    except Exception as e:
        logger.error("خطا في قراءة PDF: " + type(e).__name__ + ": " + str(e))
        return ""


# ==================== تنظيف رد JSON بدون regex ====================
def clean_json_response(raw):
    if not raw:
        return ""

    text = raw.strip()

    # حذف علامات الباكتيك (ثلاث مرات) التي قد تحيط بالـ JSON
    tick = chr(96)          # الرمز: 
    triple = tick + tick + tick

    # ازالة الفتح ``json في البداية
    if text.startswith(triple + "json"):
        text = text[len(triple) + 4:].strip()
    elif text.startswith(triple):
        text = text[len(triple):].strip()

    # ازالة الاغلاق ` في النهاية
    if text.endswith(triple):
        text = text[:-len(triple)].strip()

    # احيانا يكون json متبوعا بنص، فنبحث عن اول { واخر }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]

    return text.strip()


# ==================== بناء البرومبت ====================
def build_quiz_prompt(text, num_questions, question_type, difficulty,
                     lang_instruction=None, is_english=False):

    type_rule = {
        "mcq": "كل الأسئلة من نوع اختيار من متعدد (4 خيارات).",
        "tf": "كل الأسئلة من نوع صح أو خطأ.",
        "mixed": "اخلط بين اختيار من متعدد وصح/خطأ.",
    }.get(question_type, "مزيج من النوعين.")

    diff_rule = {
        "easy": "أسئلة مباشرة تتطلب تذكّر معلومة من النص.",
        "medium": "أسئلة تتطلب فهماً وتطبيقاً، وليس مجرد حفظ.",
        "hard": "أسئلة تحليلية واستنتاجية تتطلب تفكيراً عميقاً.",
    }.get(difficulty, "أسئلة متوسطة.")

    json_example = (
        "{" + chr(10)
        + '  "questions": [' + chr(10)
        + "    {" + chr(10)
        + '      "type": "mcq",' + chr(10)
        + '      "question": "QUESTION_TEXT",' + chr(10)
        + '      "options": ["option1", "option2", "option3", "option4"],' + chr(10)
        + '      "correct": 0,' + chr(10)
        + '      "explanation": "EXPLANATION_TEXT"' + chr(10)
        + "    }," + chr(10)
        + "    {" + chr(10)
        + '      "type": "tf",' + chr(10)
        + '      "question": "QUESTION_TEXT",' + chr(10)
        + '      "correct": true,' + chr(10)
        + '      "explanation": "EXPLANATION_TEXT"' + chr(10)
        + "    }" + chr(10)
        + "  ]" + chr(10)
        + "}"
    )

    # قواعد اللغة
    if is_english:
        lang_block = (
            "═══ LANGUAGE RULE (MUST FOLLOW) ═══" + chr(10)
            + "The source text is in ENGLISH." + chr(10)
            + "You MUST generate ALL questions, options, and explanations in ENGLISH." + chr(10)
            + "Then add an Arabic translation of the question between parentheses." + chr(10)
            + "Format: 'English question text (الترجمة العربية)'" + chr(10)
            + "Example:" + chr(10)
            + "  question: 'What is the capital of France? (ما هي عاصمة فرنسا؟)'" + chr(10)
            + "  options: ['Paris (باريس)', 'London (لندن)', 'Rome (روما)', 'Berlin (برلين)']" + chr(10)
            + "  explanation: 'Paris is the capital. (باريس هي العاصمة.)'" + chr(10)
            + "DO NOT write the question ONLY in Arabic." + chr(10)
            + "DO NOT write the question ONLY in English without the Arabic translation." + chr(10) + chr(10)
        )
    else:
        lang_block = (
            "لغة الأسئلة: العربية." + chr(10)
            + "اكتب جميع الأسئلة والخيارات والشرح بالعربية." + chr(10) + chr(10)
        )

    prompt = (
        "You are an expert teacher. Read the text carefully, then create "
        + str(num_questions) + " high-quality educational questions." + chr(10) + chr(10)

        + lang_block

        + "QUALITY RULES:" + chr(10)
        + "1. NO superficial questions (no author name, no year, no page number)." + chr(10)
        + "2. Questions must be: conceptual, applied, analytical, or inferential." + chr(10)
        + "3. Wrong options (distractors) must be logical and convincing." + chr(10)
        + "4. Correct answers must be from the text." + chr(10)
        + "5. Explanation must justify the answer, not just repeat it." + chr(10) + chr(10)

        + "Question type: " + type_rule + chr(10)
        + "Difficulty: " + diff_rule + chr(10) + chr(10)

        + "Return JSON ONLY, with this exact schema:" + chr(10)
        + json_example + chr(10) + chr(10)

        + "JSON rules:" + chr(10)
        + '- "type": "mcq" or "tf".' + chr(10)
        + '- "correct": integer 0-3 for mcq, true/false for tf.' + chr(10)
        + '- "options": exactly 4 for mcq.' + chr(10)
        + "- No extra fields." + chr(10) + chr(10)

        + "Text:" + chr(10)
        + text + chr(10) + chr(10)
        + "JSON:"
    )
    return prompt
# ==================== الاستدعاء المحمي بـ Timeout ====================
def _call_gemini_with_timeout(client, model_name, prompt, timeout=TIMEOUT_SECONDS):
    """يستدعي Gemini مع timeout + retry داخلي عند 503 و 429."""

    def _single_call():
        chat = client.chats.create(model=model_name)
        cfg = types.GenerateContentConfig(
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
            temperature=0.7,
        )
        response = chat.send_message(prompt, config=cfg)
        return response.text if response else ""
def generate_quiz_from_text(client, model_name, text, num_questions=5,
                             question_type="mixed", difficulty="medium"):

    if not text or not text.strip():
        print("النص فارغ")
        return []

    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH]
        print("تم تقليص النص الى " + str(MAX_TEXT_LENGTH))

    # كشف اللغة
    sample = text[:3000]
    arabic_chars = sum(1 for c in sample if '\u0600' <= c <= '\u06FF')
    english_chars = sum(1 for c in sample if c.isascii() and c.isalpha())

    is_english = english_chars > arabic_chars
    print("العربية: " + str(arabic_chars) + " | الإنجليزية: " + str(english_chars))
    print("لغة النص: " + ("إنجليزية" if is_english else "عربية"))

    prompt = build_quiz_prompt(
        text, num_questions, question_type, difficulty,
        is_english=is_english
    )

    print("طول الطلب: " + str(len(prompt)) + " حرف")

    import llm_router
    raw_response = llm_router.generate(prompt, temperature=0.7, prefer="groq")

    if not raw_response:
        print("فشل توليد الاسئلة")
        return []

    print("تم استقبال الرد: " + str(len(raw_response)) + " حرف")

    cleaned = clean_json_response(raw_response)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print("خطا JSON: " + str(e))
        print("الرد الخام (اول 500 حرف):")
        print(cleaned[:500])
        return []

    questions = data.get("questions", [])
    if not isinstance(questions, list):
        return []

    valid = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        if not q.get("question"):
            continue

        qtype = q.get("type", "mcq")

        if qtype == "mcq":
            opts = q.get("options", [])
            correct = q.get("correct", -1)
            if (isinstance(opts, list)
                    and len(opts) >= 2
                    and isinstance(correct, int)
                    and 0 <= correct < len(opts)):
                valid.append(q)
        elif qtype == "tf":
            if isinstance(q.get("correct"), bool):
                valid.append(q)

    print("تم توليد " + str(len(valid)) + " سؤال صالح")
    return valid
# ==================== الدالة الرئيسية ====================
