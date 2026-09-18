# bot.py
# -*- coding: utf-8 -*-

import socket

# اجبار Python على استخدام IPv4 فقط
_original_getaddrinfo = socket.getaddrinfo

def _force_ipv4(*args, **kwargs):
    responses = _original_getaddrinfo(*args, **kwargs)
    ipv4_only = [r for r in responses if r[0] == socket.AF_INET]
    return ipv4_only if ipv4_only else responses

socket.getaddrinfo = _force_ipv4
print("✅ تم تفعيل IPv4 فقط")


import os
import tempfile
import logging

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from google import genai

import database
import quiz
import quiz_flow
import llm_router
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN غير موجود في .env")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY غير موجود في .env")

client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-3.6-flash"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

NL = chr(10)

DEVELOPER_NAME = "جبران محمد"
DEVELOPER_USERNAME = "G_ubran"
DEVELOPER_URL = "https://t.me/G_ubran"


# ==================== القائمة الرئيسية ====================
def main_menu_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("📚 مساعدة دراسية", callback_data="study"),
            InlineKeyboardButton("📝 اختبر نفسك", callback_data="quiz"),
        ],
        [
            InlineKeyboardButton("🌐 ترجمة نصوص", callback_data="translate"),
            InlineKeyboardButton("🖼 توليد صور", callback_data="image"),
        ],
        [
            InlineKeyboardButton("🧠 حل مسائل رياضية", callback_data="math"),
            InlineKeyboardButton("ℹ️ عن البوت", callback_data="about"),
        ],
        [
            InlineKeyboardButton("📊 إحصائياتي", callback_data="my_stats"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


# ==================== الأوامر ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "صديقي"
    text = (
        "مرحباً " + name + "! 👋" + NL + NL
        + "أنا *بوتك الدراسي الذكي* 🤖" + NL
        + "اسألني أي شيء مباشرة، أو اختر من القائمة:" + NL + NL
        + "💾 *ملاحظة:* أتذكر محادثاتنا حتى بعد إغلاقي!"
    )
    await update.message.reply_text(
        text, parse_mode="Markdown", reply_markup=main_menu_keyboard()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *كيف تستخدمني:*" + NL + NL
        + "• أرسل أي سؤال وسأجيبك مباشرة." + NL
        + "• /start لعرض القائمة الرئيسية." + NL
        + "• /reset لمسح ذاكرة محادثتنا." + NL
        + "• /history لعرض سجل محادثاتك." + NL
        + "• /stats لعرض إحصائياتك." + NL
        + "• /help لعرض هذه الرسالة." + NL + NL
        + "💡 *نصيحة:* كلما كان سؤالك أوضح، كانت الإجابة أدق."
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    database.clear_user_messages(user_id)
    await update.message.reply_text("🧹 تم مسح كل محادثاتنا من قاعدة البيانات.")


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    messages = database.get_all_messages(user_id)

    if not messages:
        await update.message.reply_text("📭 لا يوجد سجل محادثات بعد.")
        return

    text = "📜 *سجل محادثاتك:*" + NL + NL
    for role, msg, ts in messages[-20:]:
        prefix = "👤" if role == "user" else "🤖"
        short_msg = msg if len(msg) < 100 else msg[:100] + "..."
        text += prefix + " " + short_msg + NL + NL

    await update.message.reply_text(text, parse_mode="Markdown")
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    stats = database.get_user_stats(user_id)

    if stats["quizzes_count"] == 0:
        await update.message.reply_text(
            "📊 لا توجد إحصائيات بعد." + NL
            + "ابدأ اختباراً من القائمة الرئيسية."
        )
        return

    text = (
        "📊 *إحصائياتك:*" + NL + NL
        + "📝 عدد الاختبارات: " + str(stats["quizzes_count"]) + NL
        + "🎯 مجموع نقاطك: " + str(stats["total_score"]) + " من " + str(stats["total_possible"]) + NL
        + "📈 متوسط النسبة: " + str(stats["avg_percent"]) + "%"
    )

    last = database.get_last_results(user_id, limit=5)
    if last:
        text += NL + NL + "🕒 *آخر النتائج:*" + NL
        for topic, score, total, ts in last:
            text += "• " + str(topic) + ": " + str(score) + "/" + str(total) + NL

    await update.message.reply_text(text, parse_mode="Markdown")


# ==================== معالج الأزرار ====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # -------- القائمة الرئيسية --------
    if data == "study":
        await query.edit_message_text(
            "📚 *المساعدة الدراسية*" + NL + NL
            + "أرسل لي أي سؤال دراسي وسأساعدك في شرحه وحله.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_main")
            ]])
        )
        return

    elif data == "quiz":
        context.user_data["quiz_settings"] = {}
        await query.edit_message_text(
            quiz_flow.quiz_intro_text(),
            parse_mode="Markdown",
            reply_markup=quiz_flow.quiz_source_keyboard()
        )
        return

    elif data == "translate":
        keyboard = [
            [
                InlineKeyboardButton("🇸🇦 عربي", callback_data="tr_ar"),
                InlineKeyboardButton("🇬🇧 إنجليزي", callback_data="tr_en"),
            ],
            [
                InlineKeyboardButton("🇫🇷 فرنسي", callback_data="tr_fr"),
                InlineKeyboardButton("🇪🇸 إسباني", callback_data="tr_es"),
            ],
            [
                InlineKeyboardButton("🇩🇪 ألماني", callback_data="tr_de"),
                InlineKeyboardButton("🇹🇷 تركي", callback_data="tr_tr"),
            ],
            [
                InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_main"),
            ],
        ]
        await query.edit_message_text(
            "🌐 *الترجمة*" + NL + NL + "اختر اللغة التي تريد الترجمة إليها:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    elif data == "image":
        await query.edit_message_text(
            "🖼 *توليد الصور*" + NL + NL + "قريباً! 🚧",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_main")
            ]])
        )
        return

    elif data == "math":
        await query.edit_message_text(
            "🧠 *الرياضيات*" + NL + NL
            + "أرسل لي أي مسألة رياضية وسأحلها خطوة بخطوة.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_main")
            ]])
        )
        return

    elif data == "about":
        about_text = (
            "ℹ️ عن البوت" + NL + NL
            + "🤖 تم تطوير هذا البوت بواسطة: " + DEVELOPER_NAME + NL + NL
            + "📖 بوت يخدم الطلاب في أشياء كثيرة:" + NL
            + "• مساعدة دراسية ذكية" + NL
            + "• اختبارات تفاعلية من ملفات PDF" + NL
            + "• ترجمة نصوص" + NL
            + "• حل مسائل رياضية" + NL + NL
            + "📩 إذا واجهت أي خطأ أو لديك اقتراح:" + NL
            + "تواصل معي: @" + DEVELOPER_USERNAME + NL + NL
            + "🔖 الإصدار: 2.0"
        )
        await query.edit_message_text(
            about_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 تواصل مع المطور", url=DEVELOPER_URL)],
                [InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_main")],
            ])
        )
        return

    elif data == "my_stats":
        user_id = update.effective_user.id
        stats = database.get_user_stats(user_id)
        if stats["quizzes_count"] == 0:
            await query.edit_message_text(
                "📊 لا توجد إحصائيات بعد." + NL
                + "ابدأ اختباراً من القائمة الرئيسية.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_main")
                ]])
            )
        else:
            text = (
                "📊 *إحصائياتك:*" + NL + NL
                + "📝 عدد الاختبارات: " + str(stats["quizzes_count"]) + NL
                + "🎯 مجموع نقاطك: " + str(stats["total_score"]) + " من " + str(stats["total_possible"]) + NL
                + "📈 متوسط النسبة: " + str(stats["avg_percent"]) + "%"
            )
            await query.edit_message_text(
                text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_main")
                ]])
            )
        return

    elif data.startswith("tr_"):
        lang_code = data[3:]
        lang_names = {
            "ar": "العربية",
            "en": "الإنجليزية",
            "fr": "الفرنسية",
            "es": "الإسبانية",
            "de": "الألمانية",
            "tr": "التركية",
        }
        context.user_data["mode"] = "translate"
        context.user_data["target_lang"] = lang_code
        context.user_data["target_lang_name"] = lang_names.get(lang_code, "العربية")
        await query.edit_message_text(
            "✅ تم اختيار: *" + lang_names.get(lang_code, "") + "*" + NL + NL
            + "الآن أرسل لي النص الذي تريد ترجمته." + NL + NL
            + "أو اضغط *إلغاء* للخروج.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ إلغاء الترجمة", callback_data="cancel_mode"),
                InlineKeyboardButton("🔙 رجوع", callback_data="translate"),
            ]])
        )
        return

    elif data == "cancel_mode":
        context.user_data["mode"] = None
        await query.edit_message_text(
            "✅ تم إلغاء الوضع الحالي." + NL + NL
            + "🏠 *القائمة الرئيسية:*",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard()
        )
        return

    elif data == "back_main":
        await query.edit_message_text(
            "🏠 *القائمة الرئيسية:*",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard()
        )
        return

    # -------- إعدادات الاختبار --------
    elif data.startswith("qs_source_"):
        source = data.replace("qs_source_", "")
        context.user_data.setdefault("quiz_settings", {})["source"] = source
        await query.edit_message_text(
            quiz_flow.quiz_type_text(source),
            parse_mode="Markdown",
            reply_markup=quiz_flow.quiz_type_keyboard()
        )
        return

    elif data.startswith("qs_type_"):
        q_type = data.replace("qs_type_", "")
        settings = context.user_data.get("quiz_settings", {})
        settings["type"] = q_type
        context.user_data["quiz_settings"] = settings
        await query.edit_message_text(
            quiz_flow.quiz_count_text(settings.get("source"), q_type),
            parse_mode="Markdown",
            reply_markup=quiz_flow.quiz_count_keyboard()
        )
        return
    elif data.startswith("qs_count_"):
        count = int(data.replace("qs_count_", ""))
        settings = context.user_data.get("quiz_settings", {})
        settings["count"] = count
        context.user_data["quiz_settings"] = settings
        await query.edit_message_text(
            quiz_flow.quiz_difficulty_text(settings),
            parse_mode="Markdown",
            reply_markup=quiz_flow.quiz_difficulty_keyboard()
        )
        return

    elif data.startswith("qs_diff_"):
        diff = data.replace("qs_diff_", "")
        settings = context.user_data.get("quiz_settings", {})
        settings["difficulty"] = diff
        context.user_data["quiz_settings"] = settings
        await query.edit_message_text(
            quiz_flow.quiz_confirm_text(settings),
            parse_mode="Markdown",
            reply_markup=quiz_flow.quiz_final_keyboard()
        )
        return

    elif data == "qs_start":
        settings = context.user_data.get("quiz_settings", {})
        if settings.get("source") == "pdf":
            context.user_data["mode"] = "waiting_pdf"
            await query.edit_message_text(
                "📄 *ممتاز!*" + NL + NL
                + "أرسل لي الآن ملف PDF الذي تريد الاختبار منه." + NL + NL
                + "⚠️ الملفات المحمية بكلمة مرور قد لا تعمل.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ إلغاء", callback_data="cancel_mode")
                ]])
            )
        else:
            context.user_data["mode"] = "quiz_quick_topic"
            await query.edit_message_text(
                "📚 *اختبار سريع*" + NL + NL
                + "أرسل لي موضوع الاختبار (مثل: الفيزياء، الرياضيات، التاريخ).",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ إلغاء", callback_data="cancel_mode")
                ]])
            )
        return

    # -------- الاختبار التفاعلي --------
    elif data.startswith("q_ans_"):
        await handle_quiz_answer(update, context, data)
        return

    elif data == "q_next":
        await show_next_question(update, context)
        return

    elif data == "q_finish":
        await show_quiz_results(update, context)
        return

    elif data == "q_quit":
        await query.edit_message_text(
            "🛑 تم إنهاء الاختبار." + NL + NL + "🏠 *القائمة الرئيسية:*",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard()
        )
        context.user_data.pop("current_quiz", None)
        return

    else:
        await query.edit_message_text(
            "خيار غير معروف.",
            reply_markup=main_menu_keyboard()
        )
        return


# ==================== منطق الاختبار التفاعلي ====================
async def handle_quiz_answer(update, context, data):
    query = update.callback_query

    try:
        parts = data.split("_")
        index = int(parts[2])
        choice = parts[3]
    except (IndexError, ValueError) as e:
        await query.edit_message_text("⚠️ خطأ في بيانات الزر. ابدأ الاختبار من جديد.")
        return

    quiz_state = context.user_data.get("current_quiz")
    if not quiz_state:
        await query.edit_message_text(
            "انتهت صلاحية الاختبار. ابدأ من جديد.",
            reply_markup=main_menu_keyboard()
        )
        return

    questions = quiz_state.get("questions", [])
    if not questions or index >= len(questions):
        await query.edit_message_text("⚠️ سؤال غير صالح.")
        return

    question = questions[index]
    total = len(questions)
    is_last = (index == total - 1)

    try:
        feedback_text, is_correct = quiz_flow.build_feedback_text(
            question, choice, index + 1, total, is_last
        )
        feedback_kb = quiz_flow.build_feedback_keyboard(is_last)
    except Exception as e:
        logger.error("خطأ في بناء التصحيح: " + type(e).__name__ + ": " + str(e))
        await query.edit_message_text(
            "⚠️ تعذّر عرض التصحيح. ننتقل للسؤال التالي." + NL,
            reply_markup=quiz_flow.build_feedback_keyboard(is_last)
        )
        # نعتبره خطأً
        quiz_state["answers"].append({
            "index": index,
            "choice": choice,
            "correct": False,
        })
        return

    if is_correct:
        quiz_state["score"] = quiz_state.get("score", 0) + 1

    quiz_state.setdefault("answers", []).append({
        "index": index,
        "choice": choice,
        "correct": is_correct,
    })

    try:
        await query.edit_message_text(feedback_text, reply_markup=feedback_kb)
    except Exception as e:
        logger.error("فشل عرض التصحيح: " + str(e))
async def show_next_question(update, context):
    query = update.callback_query
    quiz_state = context.user_data.get("current_quiz")

    if not quiz_state:
        await query.edit_message_text("انتهت صلاحية الاختبار.")
        return

    quiz_state["current_index"] = quiz_state.get("current_index", 0) + 1
    index = quiz_state["current_index"]
    questions = quiz_state.get("questions", [])
    total = len(questions)

    if index >= total:
        await show_quiz_results(update, context)
        return

    question = questions[index]

    try:
        text = quiz_flow.build_question_text(question, index + 1, total)
        kb = quiz_flow.build_question_keyboard(question, index)
    except Exception as e:
        logger.error("فشل بناء السؤال: " + type(e).__name__ + ": " + str(e))
        # نتخطى هذا السؤال
        quiz_state["current_index"] += 1
        await show_next_question(update, context)
        return

    try:
        await query.edit_message_text(text, reply_markup=kb)
    except Exception as e:
        logger.error("فشل عرض السؤال: " + str(e))
async def show_quiz_results(update, context):
    query = update.callback_query
    quiz_state = context.user_data.get("current_quiz")

    if not quiz_state:
        await query.edit_message_text("انتهت صلاحية الاختبار.")
        return

    score = quiz_state["score"]
    total = len(quiz_state["questions"])
    user_id = update.effective_user.id
    topic = quiz_state.get("topic", "اختبار")

    try:
        database.save_quiz_result(user_id, topic, score, total)
    except Exception as e:
        logger.error("خطا في حفظ النتيجة: " + str(e))

    text = quiz_flow.build_results_text(score, total)
    kb = quiz_flow.build_results_keyboard()

    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    context.user_data.pop("current_quiz", None)


# ==================== معالج الرسائل النصية ====================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text.strip()
    mode = context.user_data.get("mode")

    # 1) وضع الترجمة
    # 1) وضع الترجمة
    if mode == "translate":
        target_lang = context.user_data.get("target_lang_name", "العربية")
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action=ChatAction.TYPING
        )

        prompt = (
            "Translate the following text into " + target_lang + ". "
            + "Return ONLY the translation, nothing else:" + NL + NL
            + user_message
        )

        reply = llm_router.generate(prompt, temperature=0.2)

        if not reply:
            reply = (
                "⚠️ تعذّرت الترجمة حالياً." + NL
                + "خدمة Gemini مشغولة أو الحصة منتهية، و Groq لم يستجب."
            )

        database.save_message(user_id, "user", user_message)
        database.save_message(user_id, "bot", reply)
        context.user_data["mode"] = None

        await update.message.reply_text(
            "🌐 الترجمة إلى " + target_lang + ":" + NL + NL + reply
        )
        return

    # 2) اختبار سريع
    if mode == "quiz_quick_topic":
        context.user_data["mode"] = None
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action=ChatAction.TYPING
        )
        msg = await update.message.reply_text("⏳ جاري توليد الأسئلة عن: " + user_message)

        settings = context.user_data.get("quiz_settings", {})
        num_q = settings.get("count", 5)
        q_type = settings.get("type", "mixed")
        diff = settings.get("difficulty", "medium")
        fake_text = (
            "الموضوع: " + user_message + NL
            + "ولد أسئلة متنوعة تغطي هذا الموضوع بعمق."
        )

        questions = quiz.generate_quiz_from_text(
            client=client,
            model_name=MODEL_NAME,
            text=fake_text,
            num_questions=num_q,
            question_type=q_type,
            difficulty=diff,
        )

        if not questions:
            await msg.edit_text("⚠️ فشل توليد الأسئلة. حاول مرة أخرى.")
            return

        await start_interactive_quiz(update, context, questions, user_message)
        return

    # 3) كلمات الترحيب
    if user_message.lower() in [
        "start", "بدء", "ابدأ", "البدء", "بداية",
        "هلا", "مرحبا", "السلام عليكم"
    ]:
        name = update.effective_user.first_name or "صديقي"
        text = (
            "مرحباً " + name + "! 👋" + NL + NL
            + "أنا *بوتك الدراسي الذكي* 🤖" + NL
            + "اسألني أي شيء مباشرة:"
        )
        await update.message.reply_text(
            text, parse_mode="Markdown", reply_markup=main_menu_keyboard()
        )
        return

    # 3.5) أسئلة عن المطور
    # 3.5) أسئلة عن المطور
    developer_keywords = [
    "من طورك", "من طور هذا البوت", "من مطورك", "من صانعك",
    "من صنعك", "من انشأك", "من انشا هذا البوت", "من مبرمجك",
    "من عمل هذا البوت", "who made you", "who created you",
    "who developed you", "من بناك", "من اسسك",
    "من هو مطورك", "من مبرمج هذا البوت", "من صاحب البوت",
    "من صاحبك", "من انت", "من انت؟", "من أنت", "من أنت؟",
    "من تكون", "من تكون؟", "من هو صاحبك", "من مالك",
    "من مؤسسك", "من باني هذا البوت", "من صانع هذا البوت",
    "تعرف جبران", "تعرف جبران محمد", "هل تعرف جبران",
    "جبران محمد", "جبران",
]
    if any(kw in user_message.lower() for kw in developer_keywords):
        reply = (
            "🤖 أنا بوت دراسي ذكي" + NL + NL
            + "تم تطويري بواسطة: " + DEVELOPER_NAME + NL + NL
            + "📚 أهدف لمساعدة الطلاب في:" + NL
            + "• المساعدة الدراسية" + NL
            + "• الاختبارات التفاعلية" + NL
            + "• الترجمة" + NL
            + "• حل المسائل الرياضية" + NL + NL
            + "📩 للتواصل مع المطور: @" + DEVELOPER_USERNAME
        )
        database.save_message(user_id, "user", user_message)
        database.save_message(user_id, "bot", reply)
        await update.message.reply_text(
            reply,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💬 تواصل مع المطور", url=DEVELOPER_URL)
            ]])
        )
        return
    # 4) الدردشة العادية
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )

    database.save_message(user_id, "user", user_message)
    history = database.get_recent_messages(user_id, limit=10)

    history_text = ""
    for entry in history:
        prefix = "المستخدم" if entry["role"] == "user" else "البوت"
        history_text += prefix + ": " + entry["text"] + NL

    prompt = (
        "أنت مساعد دراسي ذكي ودود. أجب بالعربية بشكل واضح ومختصر." + NL
        + "استخدم التنسيق الجميل عند الحاجة (نقاط، عناوين)." + NL + NL
        + "⚠️ قواعد مهمة جداً للرياضيات والرموز:" + NL
        + "- لا تستخدم رموز LaTeX إطلاقاً." + NL
        + "- استخدم الرموز الرياضية اليونيكود المباشرة." + NL
        + "- استخدم الرموز التعبيرية (Emojis) لتوضيح المعنى." + NL + NL
        + "أمثلة على الرموز الصحيحة:" + NL
        + "- الجذر التربيعي: √ (مثال: √-1 = i)" + NL
        + "- الأس: ² ³ ⁴ ⁵ (مثال: i² = -1)" + NL
        + "- الكسور: اكتبها بصيغة (1/2) أو (3/4)" + NL
        + "- الضرب: × (مثال: 3 × 5 = 15)" + NL
        + "- القسمة: ÷ (مثال: 10 ÷ 2 = 5)" + NL
        + "- باي: π (مثال: π ≈ 3.14)" + NL
        + "- ما لا نهاية: ∞" + NL
        + "- أكبر/أصغر: ≥ ≤ ≠ ≈" + NL
        + "- المجموع: Σ، التكامل: ∫" + NL
        + "- الزوايا: ° (مثال: 90°)" + NL + NL
        + "سجل المحادثة:" + NL + history_text + NL
        + "الرد:"
    )

    # استخدام llm_router (Gemini -> Groq تلقائياً)
    reply = llm_router.generate(prompt, temperature=0.7)

    if not reply:
        reply = "⚠️ تعذّر الحصول على رد من Gemini أو Groq. حاول لاحقاً."

    database.save_message(user_id, "bot", reply)
    await update.message.reply_text(reply)

# ==================== بدء الاختبار التفاعلي ====================
async def start_interactive_quiz(update, context, questions, topic):
    context.user_data["current_quiz"] = {
        "questions": questions,
        "current_index": 0,
        "score": 0,
        "answers": [],
        "topic": topic,
    }

    first_q = questions[0]
    text = quiz_flow.build_question_text(first_q, 1, len(questions))
    kb = quiz_flow.build_question_keyboard(first_q, 0)

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


# ==================== معالج ملفات PDF ====================
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if context.user_data.get("mode") != "waiting_pdf":
        await update.message.reply_text(
            "ℹ️ لإرسال ملف، استخدم القائمة: /start ← 📝 اختبر نفسك"
        )
        return

    document = update.message.document
    if not document:
        await update.message.reply_text("⚠️ لم أستقبل ملفاً.")
        return

    if not document.file_name.lower().endswith(".pdf"):
        await update.message.reply_text("⚠️ أرسل ملف PDF فقط.")
        return
    # حد أقصى لحجم الملف: 10 ميجابايت
    if document.file_size and document.file_size > 10 * 1024 * 1024:
        await update.message.reply_text(
            "⚠️ الملف كبير جداً (أكثر من 10 ميجابايت)." + NL
            + "💡 جرّب ملفاً أصغر."
        )
        return

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )
    msg = await update.message.reply_text("⏳ جاري استخراج النص...")

    tmp_path = None
    try:
        file = await context.bot.get_file(document.file_id)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp_path = tmp.name
        await file.download_to_drive(tmp_path)

        text = quiz.extract_text_from_pdf(tmp_path)

        # حماية اذا رجع None او فارغ
        if not text or not isinstance(text, str) or len(text) < 100:
            try:
                await msg.edit_text(
                    "⚠️ لم أستطع استخراج نص كافٍ من الملف." + NL
                    + "قد يكون محمياً بكلمة مرور أو صوراً."
                )
            except Exception:
                pass
            context.user_data["mode"] = None
            return

        settings = context.user_data.get("quiz_settings", {})
        num_q = settings.get("count", 5)
        q_type = settings.get("type", "mixed")
        diff = settings.get("difficulty", "hard")

        try:
            await msg.edit_text(
                "✅ تم استخراج " + str(len(text)) + " حرفاً." + NL
                + "🧠 جاري توليد " + str(num_q) + " سؤالاً... (قد يأخذ دقيقة)"
            )
        except Exception:
            pass

        questions = quiz.generate_quiz_from_text(
            client=client,
            model_name=MODEL_NAME,
            text=text,
            num_questions=num_q,
            question_type=q_type,
            difficulty=diff,
        )

        # حماية اذا رجع None
        if not questions or not isinstance(questions, list):
            try:
                await msg.edit_text(
                    "⚠️ فشل توليد الأسئلة (خدمة Gemini مشغولة)." + NL + NL
                    + "💡 جرّب:" + NL
                    + "• الانتظار دقيقة وإعادة المحاولة." + NL
                    + "• عدداً أقل من الأسئلة (5 أو 10)." + NL
                    + "• ملف PDF أصغر."
                )
            except Exception:
                pass
            context.user_data["mode"] = None
            return

        context.user_data["mode"] = None
        try:
            await msg.edit_text("✅ تم التوليد! نبدأ الاختبار...")
        except Exception:
            pass

        await start_interactive_quiz(update, context, questions, document.file_name)

    except Exception as e:
        logger.error("خطا في معالجة PDF: " + type(e).__name__ + ": " + str(e))
        try:
            await msg.edit_text(
                "⚠️ حدث خطأ أثناء المعالجة." + NL
                + "النوع: " + type(e).__name__ + NL + NL
                + "💡 جرّب مرة أخرى بعد قليل."
            )
        except Exception:
            pass
        context.user_data["mode"] = None

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
# ==================== التشغيل ====================
def main():
    database.init_db()
    print("🚀 البوت يعمل... اذهب إلى تيليجرام وأرسل /start")
    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.run_polling()


if __name__ == "__main__":
    main()