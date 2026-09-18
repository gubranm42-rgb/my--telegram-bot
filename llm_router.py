# llm_router.py
# -*- coding: utf-8 -*-
"""
طبقة تبديل تلقائي بين Gemini و Groq.
- يحاول Gemini اولا.
- اذا فشل (حصة منتهية، خطأ سيرفر، timeout)، ينتقل الى Groq.
- يعيد نص الرد دائما، او None اذا فشل الاثنان.
"""

import os
import time
import logging

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# نموذج Groq الذي نجح عندك
GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_MODEL_LARGE = "openai/gpt-oss-120b"
# ---- تهيئة عملاء Gemini ----
_gemini_client = None
_gemini_model = "gemini-3.6-flash"

if GEMINI_API_KEY:
    try:
        from google import genai
        _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        print("[llm_router] Gemini جاهز")
    except Exception as e:
        print("[llm_router] فشل تهيئة Gemini: " + str(e))
else:
    print("[llm_router] لا يوجد مفتاح Gemini")


# ---- تهيئة عميل Groq ----
_groq_client = None

if GROQ_API_KEY:
    try:
        from groq import Groq
        _groq_client = Groq(api_key=GROQ_API_KEY)
        print("[llm_router] Groq جاهز")
    except Exception as e:
        print("[llm_router] فشل تهيئة Groq: " + str(e))
else:
    print("[llm_router] لا يوجد مفتاح Groq")


def _is_retryable_error(err_msg):
    """هل الخطأ مؤقت (يستحق الانتقال لمزود اخر)؟"""
    err = err_msg.lower()
    retryable_keywords = [
        "429", "resource_exhausted", "quota",
        "503", "unavailable", "servererror",
        "500", "internal", "timeout", "deadline",
        "overloaded", "rate limit",
    ]
    for kw in retryable_keywords:
        if kw in err:
            return True
    return False


def _try_gemini(prompt, temperature=0.7):
    """محاولة استخدام Gemini. يعيد النص او يرفع استثناء."""
    if not _gemini_client:
        raise RuntimeError("Gemini غير مهيأ")

    from google.genai import types

    chat = _gemini_client.chats.create(model=_gemini_model)
    cfg = types.GenerateContentConfig(
        automatic_function_calling=types.AutomaticFunctionCallingConfig(
            disable=True
        ),
        temperature=temperature,
    )
    response = chat.send_message(prompt, config=cfg)
    if not response or not response.text:
        raise RuntimeError("Gemini رجع ردا فارغا")
    return response.text


def _try_groq(prompt, temperature=0.7):
    """محاولة استخدام Groq. يعيد النص او يرفع استثناء."""
    if not _groq_client:
        raise RuntimeError("Groq غير مهيأ")

    response = _groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=4096,
    )
    text = response.choices[0].message.content
    if not text:
        raise RuntimeError("Groq رجع ردا فارغا")
    return text


def generate(prompt, temperature=0.7, prefer=None):
    """
    الدالة الموحدة.
    - prompt: النص المطلوب.
    - temperature: درجة الابداع.
    - prefer: "gemini" او "groq" او None (يعني Gemini اولا).

    يعيد: نص الرد، او None اذا فشل الاثنان.
    """
    providers_order = ["gemini", "groq"]
    if prefer == "groq":
        providers_order = ["groq", "gemini"]

    last_error = ""

    for provider in providers_order:
        for attempt in range(2):
            try:
                if provider == "gemini":
                    text = _try_gemini(prompt, temperature=temperature)
                else:
                    text = _try_groq(prompt, temperature=temperature)

                logger.info("نجح " + provider + " في المحاولة " + str(attempt + 1))
                return text

            except Exception as e:
                err_msg = str(e)
                last_error = provider + ": " + type(e).__name__ + " - " + err_msg[:200]
                logger.warning("فشل " + provider + " (محاولة " + str(attempt + 1) + "): " + last_error)

                if _is_retryable_error(err_msg) and attempt == 0:
                    time.sleep(3)
                    continue
                else:
                    break
                logger.error("فشل جميع المزودين. اخر خطأ: " + last_error)
    return None


def get_status():
    """يعيد حالة المزودين."""
    return {
        "gemini": _gemini_client is not None,
        "groq": _groq_client is not None,
    }