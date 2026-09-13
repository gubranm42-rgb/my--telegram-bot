import os
import logging
from collections import defaultdict
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

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN غير موجود في .env")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY غير موجود في .env")

client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-2.0-flash"   # ⬅️ غيّر هذا إلى النموذج الذي نجح معك

user_memory = defaultdict(list)
MAX_MEMORY = 10

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main_menu_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("📚 مساعدة دراسية", callback_data="study"),
            InlineKeyboardButton("📝 اختبار نفسك", callback_data="quiz"),
        ],
        [
            InlineKeyboardButton("🌐 ترجمة نصوص", callback_data="translate"),
            InlineKeyboardButton("🖼️ توليد صور", callback_data="image"),
        ],
        [
            InlineKeyboardButton("🧠 حل مسائل رياضية", callback_data="math"),
            InlineKeyboardButton("ℹ️ عن البوت", callback_data="about"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "صديقي"
    text = (
        f"مرحباً {name}! 👋\n\n"
        "أنا *بوتك الدراسي الذكي* 🤖\n"
        "اسألني أي شيء مباشرة، أو اختر من القائمة:"
    )
    await update.message.reply_text(
        text, parse_mode="Markdown", reply_markup=main_menu_keyboard()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *كيف تستخدمني:*\n\n"
        "• أرسل أي سؤال وسأجيبك مباشرة.\n"
        "• /start لعرض القائمة الرئيسية.\n"
        "• /reset لمسح ذاكرة محادثتنا.\n"
        "• /help لعرض هذه الرسالة.\n\n"
        "💡 *نصيحة:* كلما كان سؤالك أوضح، كانت الإجابة أدق."
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_memory[user_id].clear()
    await update.message.reply_text("🧹 تم مسح ذاكرة المحادثة بنجاح.")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "study":
        msg = "📚 *المساعدة الدراسية*\n\nأرسل لي أي سؤال دراسي وسأساعدك في شرحه وحله."
    elif data == "quiz":
        msg = "📝 *اختبار نفسك*\n\nقريباً! 🚧\nسأطرح عليك أسئلة اختيار من متعدد وصح/خطأ."
    elif data == "translate":
        msg = "🌐 *الترجمة*\n\nقريباً! 🚧\nأرسل لي أي نص وسأترجمه."
    elif data == "image":
        msg = "🖼️ *توليد الصور*\n\nقريباً! 🚧\nستتمكن من وصف صورة وسأولّدها لك."
    elif data == "math":
        msg = "🧠 *الرياضيات*\n\nأرسل لي أي مسألة رياضية وسأحلها خطوة بخطوة."
    elif data == "about":
        msg = (
            "ℹ️ *عن البوت*\n\n"
            "بوت دراسي ذكي يعمل بتقنية Gemini من Google.\n"
            "يهدف لمساعدة الطلاب في دراستهم.\n\n"
            "👨‍💻 *الإصدار:* 1.0"
        )
    else:
        msg = "خيار غير معروف."

    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=main_menu_keyboard())


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text.strip()
    # فحص: هل المستخدم يريد البدء؟
    if user_message.lower() in ["start", "بدء", "ابدأ", "البدء", "بداية", "هلا", "مرحبا", "السلام عليكم"]:
        name = update.effective_user.first_name or "صديقي"
        text = (
            f"مرحباً {name}! 👋\n\n"
            "أنا *بوتك الدراسي الذكي* 🤖\n"
            "اسألني أي شيء مباشرة، أو اختر من القائمة:"
        )
        await update.message.reply_text(
            text, parse_mode="Markdown", reply_markup=main_menu_keyboard()
        )
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    user_memory[user_id].append({"role": "user", "text": user_message})
    if len(user_memory[user_id]) > MAX_MEMORY:
        user_memory[user_id].pop(0)

    history_text = ""
    for entry in user_memory[user_id]:
        prefix = "المستخدم" if entry["role"] == "user" else "البوت"
        history_text += f"{prefix}: {entry['text']}\n"

    prompt = (
        "أنت مساعد دراسي ذكي ودود. أجب بالعربية بشكل واضح ومختصر.\n"
        "استخدم التنسيق الجميل عند الحاجة (نقاط، عناوين).\n\n"
        f"سجل المحادثة:\n{history_text}\n"
        "الرد:"
    )

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )
        reply = response.text
    except Exception as e:
        logger.error(f"خطأ من Gemini: {e}")
        reply = "عذراً، حدث خطأ أثناء معالجة سؤالك. حاول مرة أخرى."

    user_memory[user_id].append({"role": "bot", "text": reply})

    await update.message.reply_text(reply)


def main():
    print("🚀 البوت يعمل الآن... اذهب إلى تيليجرام وأرسل /start")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    app.run_polling()


if __name__ == "__main__":
    main()