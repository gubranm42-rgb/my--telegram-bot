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
def build_quiz_prompt(text, num_questions, question_type, difficulty, lang_instruction="الأسئلة بالعربية."):
    type_rule = {
        "mcq": "كل الأسئلة من نوع اختيار من متعدد (4 خيارات).",
        "tf": "كل الأسئلة من نوع صح أو خطأ.",
        "mixed": "اخلط بين اختيار من متعدد وصح/خطأ (نصف ونصف).",
    }.get(question_type, "مزيج من النوعين.")

    diff_rule = {
        "easy": "أسئلة مباشرة تتطلب تذكّر معلومة من النص.",
        "medium": "أسئلة تتطلب فهماً وتطبيقاً، وليس مجرد حفظ.",
        "hard": "أسئلة تحليلية واستنتاجية تتطلب تفكيراً عميقاً وربطاً بين الأفكار.",
    }.get(difficulty, "أسئلة متوسطة.")

    json_example = (
        "{" + chr(10)
        + '  "questions": [' + chr(10)
        + "    {" + chr(10)
        + '      "type": "mcq",' + chr(10)
        + '      "question": "نص السؤال",' + chr(10)
        + '      "options": ["خيار1", "خيار2", "خيار3", "خيار4"],' + chr(10)
        + '      "correct": 0,' + chr(10)
        + '      "explanation": "شرح مختصر"' + chr(10)
        + "    }," + chr(10)
        + "    {" + chr(10)
        + '      "type": "tf",' + chr(10)
        + '      "question": "نص السؤال",' + chr(10)
        + '      "correct": true,' + chr(10)
        + '      "explanation": "شرح مختصر"' + chr(10)
        + "    }" + chr(10)
        + "  ]" + chr(10)
        + "}"
    )

    prompt = (
        "أنت مدرّس خبير ومتخصص في إعداد الاختبارات. اقرأ النص التالي بعناية، ثم أنشئ "
        + str(num_questions) + " سؤالاً تعليمياً عالي الجودة منه." + chr(10) + chr(10)

        + "⚠️ قواعد صارمة للجودة:" + chr(10)
        + "1. ممنوع منعاً باتاً الأسئلة السطحية أو التافهة، مثل:" + chr(10)
        + "   - من هو المؤلف؟" + chr(10)
        + "   - في أي سنة؟" + chr(10)
        + "   - ما اسم الكتاب؟" + chr(10)
        + "   - ماذا قال في السطر الأول؟" + chr(10) + chr(10)

        + "2. يجب أن تكون الأسئلة من هذه الأنواع فقط:" + chr(10)
        + "   - أسئلة مفاهيم: تختبر فهم الطالب للفكرة وليس حفظه." + chr(10)
        + "   - أسئلة تطبيق: تعرض حالة جديدة وتطلب من الطالب تطبيق المفهوم." + chr(10)
        + "   - أسئلة تحليل: تطلب مقارنة، سبب، نتيجة، أو ربط بين فكرتين." + chr(10)
        + "   - أسئلة استنتاج: تطلب استنتاجاً غير مذكور حرفياً في النص." + chr(10) + chr(10)

        + "3. الخيارات الخاطئة (Distractors) يجب أن تكون:" + chr(10)
        + "   - منطقية ومقنعة (ليست سخيفة)." + chr(10)
        + "   - متشابهة في الطول والصياغة مع الإجابة الصحيحة." + chr(10)
        + "   - تعكس أخطاء شائعة عند الطلاب." + chr(10) + chr(10)

        + "4. الإجابات الصحيحة يجب أن تكون مذكورة أو مستنتجة من النص." + chr(10)
        + "5. الشرح يجب أن يوضح سبب صحة الإجابة، وليس فقط إعادة ذكرها." + chr(10) + chr(10)

        + "أمثلة على أسئلة جيدة مقابل سيئة:" + chr(10) + chr(10)

        + "❌ سؤال سطحي (ممنوع):" + chr(10)
        + "   السؤال: ما هو تعريف الطاقة؟" + chr(10)
        + "   (هذا سؤال حفظ مذكور حرفياً، لا يختبر الفهم)" + chr(10) + chr(10)

        + "✅ سؤال جيد (مطلوب):" + chr(10)
        + "   السؤال: إذا رفعنا درجة حرارة جسم بمقدار الضعف، فماذا يحدث لطاقته الحركية؟" + chr(10)
        + "   (هذا سؤال تطبيق يختبر فهم العلاقة)" + chr(10) + chr(10)

        + "❌ سؤال سطحي (ممنوع):" + chr(10)
        + "   السؤال: هل الشمس نجم؟" + chr(10)
        + "   (إجابته واضحة بدون قراءة النص)" + chr(10) + chr(10)

        + "✅ سؤال جيد (مطلوب):" + chr(10)
        + "   السؤال: ما الفرق الجوهري بين النجم والكوكب من حيث مصدر الطاقة؟" + chr(10)
        + "   (هذا سؤال تحليل يطلب مقارنة)" + chr(10) + chr(10)

        + "نوع الأسئلة المطلوبة: " + type_rule + chr(10)
        + "مستوى الصعوبة: " + diff_rule + chr(10) + chr(10)

        + "أعد JSON فقط، بدون أي نص قبله أو بعده، بهذه الصيغة:" + chr(10)
        + json_example + chr(10) + chr(10)

        + "قواعد JSON:" + chr(10)
        + '- "type": "mcq" أو "tf" فقط.' + chr(10)
        + '- في mcq: "correct" رقم من 0 إلى 3، و"options" بها 4 خيارات بالضبط.' + chr(10)
        + '- في tf: "correct" هي true أو false.' + chr(10)
        + '- "explanation": جملة أو جملتان توضحان السبب.' + chr(10)
        + "- لا تضع حقولاً إضافية." + chr(10) + chr(10)+ "النص المطلوب منه الأسئلة:" + chr(10)
        + text + chr(10) + chr(10)
        + "JSON:"
        + "لغة الأسئلة: " + lang_instruction + chr(10) + chr(10)
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
    """
    النسخة الجديدة: تستخدم llm_router الذي يبدل تلقائيا بين Gemini و Groq.
    الواجهة (الوسائط) نفسها القديمة للتوافق.
    """
    if not text or not text.strip():
        print("النص فارغ")
        return []

    if len(text) > MAX_TEXT_LENGTH:
        # أخذ عينة موزعة من كل الملف، وليس فقط البداية
        step = len(text) // 4
        quarter = MAX_TEXT_LENGTH // 4
        text = (
            text[:quarter]
            + chr(10) + text[step:step + quarter]
            + chr(10) + text[step*2:step*2 + quarter]
            + chr(10) + text[step*3:step*3 + quarter]
    )
    print("تم أخذ عينة موزعة: " + str(len(text)) + " حرف")
    # كشف لغة النص
    arabic_chars = sum(1 for c in text[:2000] if '\u0600' <= c <= '\u06FF')
    is_arabic = arabic_chars > 50

    if is_arabic:
        lang_instruction = "الأسئلة بالعربية."
    else:
        lang_instruction = (
            "الأسئلة باللغة الإنجليزية (كما هو النص). "
            + "وأضف لكل سؤال ترجمة عربية بين قوسين بعد السؤال."
        )
    prompt = build_quiz_prompt(text, num_questions, question_type, difficulty, lang_instruction)
    print("طول الطلب: " + str(len(prompt)) + " حرف")

    import llm_router

    raw_response = llm_router.generate(prompt, temperature=0.7, prefer="groq")
    if not raw_response:
        print("فشل توليد الاسئلة (Gemini و Groq فشلا)")
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
        print("البنية غير صحيحة")
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

    print("تم توليد " + str(len(valid)) + " سؤالا صالحا")
    return valid
    def _call_with_retry():
        last_err = None
        for i in range(3):
            try:
                return _single_call()
            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                is_retryable = (
                    "503" in err_str
                    or "unavailable" in err_str
                    or "429" in err_str
                    or "resource_exhausted" in err_str
                    or "servererror" in err_str
                )
                if is_retryable and i < 2:
                    print("محاولة " + str(i + 1) + " فشلت (خطأ مؤقت)، انتظار 5 ثوان...")
                    time.sleep(5)
                    continue
                else:
                    raise
        if last_err:
            raise last_err
        return ""

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(_call_with_retry)

    try:
        result = future.result(timeout=timeout)
        executor.shutdown(wait=False)
        return result
    except concurrent.futures.TimeoutError:
        print("انتهت المهلة " + str(timeout) + " ثانية - الغاء الطلب")
        executor.shutdown(wait=False)
        return None
    except Exception as e:
        print("فشل استدعاء Gemini: " + type(e).__name__ + ": " + str(e)[:200])
        executor.shutdown(wait=False)
        return None

# ==================== الدالة الرئيسية ====================
