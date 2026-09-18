# quiz_flow.py
# -*- coding: utf-8 -*-

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

NL = chr(10)


# ==================================================
# قوائم الاختبار المتتالية
# ==================================================

def quiz_source_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("من ملزمة PDF", callback_data="qs_source_pdf")],
        [InlineKeyboardButton("اختبار سريع (بدون ملف)", callback_data="qs_source_quick")],
        [InlineKeyboardButton("رجوع للقائمة", callback_data="back_main")],
    ])


def quiz_type_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("اختيار من متعدد", callback_data="qs_type_mcq")],
        [InlineKeyboardButton("صح وخطأ", callback_data="qs_type_tf")],
        [InlineKeyboardButton("مخلوط", callback_data="qs_type_mixed")],
        [InlineKeyboardButton("رجوع", callback_data="quiz")],
    ])


def quiz_count_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("5 أسئلة", callback_data="qs_count_5"),
            InlineKeyboardButton("7 أسئلة", callback_data="qs_count_7"),
        ],
        [
            InlineKeyboardButton("10 أسئلة", callback_data="qs_count_10"),
        ],
        [InlineKeyboardButton("رجوع", callback_data="quiz")],
    ])

def quiz_difficulty_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("سهل", callback_data="qs_diff_easy"),
            InlineKeyboardButton("متوسط", callback_data="qs_diff_medium"),
        ],
        [
            InlineKeyboardButton("صعب", callback_data="qs_diff_hard"),
        ],
        [InlineKeyboardButton("رجوع", callback_data="quiz")],
    ])


def quiz_final_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("ابدأ الاختبار", callback_data="qs_start")],
        [InlineKeyboardButton("إعادة الإعداد", callback_data="quiz")],
        [InlineKeyboardButton("رجوع للقائمة", callback_data="back_main")],
    ])


# ==================================================
# نصوص الخطوات
# ==================================================

def quiz_intro_text():
    return "اختبر نفسك" + NL + NL + "اختر طريقة الاختبار:"


def quiz_type_text(source):
    source_name = "من ملزمة PDF" if source == "pdf" else "اختبار سريع"
    return "اختبر نفسك - " + source_name + NL + NL + "اختر نوع الأسئلة:"


def quiz_count_text(source, q_type):
    type_names = {
        "mcq": "اختيار من متعدد",
        "tf": "صح وخطأ",
        "mixed": "مخلوط",
    }
    return (
        "اختبر نفسك" + NL
        + "المصدر: " + str(source) + NL
        + "النوع: " + type_names.get(q_type, q_type) + NL + NL
        + "كم سؤالا تريد؟"
    )


def quiz_difficulty_text(settings):
    return (
        "اختبر نفسك" + NL + NL
        + "المصدر: " + ("ملف PDF" if settings.get("source") == "pdf" else "سريع") + NL
        + "النوع: " + str(settings.get("type")) + NL
        + "العدد: " + str(settings.get("count")) + NL + NL
        + "اختر مستوى الصعوبة:"
    )


def quiz_confirm_text(settings):
    source = "من ملزمة PDF" if settings.get("source") == "pdf" else "اختبار سريع"
    type_names = {
        "mcq": "اختيار من متعدد",
        "tf": "صح وخطأ",
        "mixed": "مخلوط",
    }
    diff_names = {
        "easy": "سهل",
        "medium": "متوسط",
        "hard": "صعب",
    }
    return (
        "ملخص الإعدادات" + NL + NL
        + "المصدر: " + source + NL
        + "النوع: " + type_names.get(settings.get("type"), str(settings.get("type"))) + NL
        + "العدد: " + str(settings.get("count")) + " أسئلة" + NL
        + "الصعوبة: " + diff_names.get(settings.get("difficulty"), str(settings.get("difficulty"))) + NL + NL
        + "هل أنت جاهز؟"
    )


# ==================================================
# عرض الأسئلة التفاعلية
# ==================================================
def build_question_text(question, index, total):
    """يبني نص السؤال الحالي."""
    header = "السؤال " + str(index) + " من " + str(total)
    q_text = str(question.get("question", ""))
    return header + NL + NL + q_text


def build_question_keyboard(question, index):
    qtype = str(question.get("type", "mcq")).lower()

    if qtype == "mcq":
        options = question.get("options", [])
        if not isinstance(options, list) or len(options) < 2:
            # سؤال تالف — نعرضه كصح/خطأ
            qtype = "tf"
        else:
            buttons = []
            for i, opt in enumerate(options):
                label = str(i + 1) + ". " + str(opt)
                if len(label) > 60:
                    label = label[:57] + "..."
                buttons.append([
                    InlineKeyboardButton(
                        label,
                        callback_data="q_ans_" + str(index) + "_" + str(i)
                    )
                ])
            buttons.append([
                InlineKeyboardButton("إنهاء الاختبار", callback_data="q_quit")
            ])
            return InlineKeyboardMarkup(buttons)

    # tf
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ صح", callback_data="q_ans_" + str(index) + "_true")],
        [InlineKeyboardButton("❌ خطأ", callback_data="q_ans_" + str(index) + "_false")],
        [InlineKeyboardButton("إنهاء الاختبار", callback_data="q_quit")],
    ])
def build_feedback_text(question, user_answer, index, total, is_last):
    qtype = str(question.get("type", "mcq")).lower()
    correct_raw = question.get("correct")
    explanation = str(question.get("explanation", "لا يوجد شرح."))
    options = question.get("options", [])

    is_correct = False
    correct_text = ""

    # معرفة النوع الحقيقي
    if qtype == "mcq" and isinstance(options, list) and len(options) >= 2:
        try:
            correct_idx = int(correct_raw) if correct_raw is not None else 0
            user_idx = int(user_answer)
            is_correct = (user_idx == correct_idx)
            if 0 <= correct_idx < len(options):
                correct_text = str(options[correct_idx])
            else:
                correct_text = "غير محدد"
        except (ValueError, TypeError):
            is_correct = False
            correct_text = "غير محدد"
    else:
        # tf
        correct_bool = bool(correct_raw)
        if isinstance(correct_raw, str):
            correct_bool = correct_raw.lower() in ("true", "صح", "1", "yes")
        user_bool = (str(user_answer).lower() == "true")
        is_correct = (user_bool == correct_bool)
        correct_text = "✅ صح" if correct_bool else "❌ خطأ"

    status_line = "✅ إجابة صحيحة!" if is_correct else "❌ إجابة خاطئة"
    header = "السؤال " + str(index) + " من " + str(total) + NL + NL

    text = (
        header
        + status_line + NL + NL
        + "الإجابة الصحيحة: " + correct_text + NL + NL
        + "💡 " + explanation
    )
    return text, is_correct

def build_feedback_keyboard(is_last):
    """أزرار شاشة التصحيح."""
    if is_last:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("عرض النتيجة النهائية", callback_data="q_finish")],
        ])
    else:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("السؤال التالي", callback_data="q_next")],
        ])


def build_results_text(score, total):
    """يبني شاشة النتيجة النهائية."""
    percent = round((score / total) * 100, 1) if total > 0 else 0

    if percent >= 90:
        emoji = "ممتاز جدا! 🌟"
    elif percent >= 75:
        emoji = "جيد جدا! 👏"
    elif percent >= 60:
        emoji = "جيد 👍"
    elif percent >= 50:
        emoji = "مقبول 🙂"
    else:
        emoji = "يحتاج مراجعة 📚"

    return (
        "النتيجة النهائية" + NL + NL
        + "أجبت بشكل صحيح على: " + str(score) + " من " + str(total) + NL
        + "النسبة: " + str(percent) + "%" + NL + NL
        + emoji
    )


def build_results_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("اختبار جديد", callback_data="quiz")],
        [InlineKeyboardButton("القائمة الرئيسية", callback_data="back_main")],
    ])