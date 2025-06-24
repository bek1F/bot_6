import os
import json
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.constants import ParseMode

# === JSON o'quvchi/yozuvchi funksiyalar ===
def load_json(file):
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# === Fayllarni yaratish ===
for file in ["data.json", "stats.json", "codes.json"]:
    if not os.path.exists(file):
        save_json(file, {})

data = load_json("data.json")
stats = load_json("stats.json")

# === Versiya va .env yuklash ===
VERSION = "1.0.0"
load_dotenv()

TOKEN = os.getenv("TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip()
CHANNEL_IDS = [ch if ch.startswith("@") else f"@{ch.strip()}" for ch in os.getenv("CHANNEL_IDS", "").split(",") if ch.strip()]
ADMINS = [int(admin_id) for admin_id in os.getenv("ADMINS", "").split(",") if admin_id.strip()]

# === Obuna tekshirish ===
async def is_subscribed(user_id, context):
    for ch in CHANNEL_IDS:
        try:
            member = await context.bot.get_chat_member(ch, user_id)
            if member.status in ["left", "kicked"]:
                return False, ch
        except Exception:
            return False, ch
    return True, None

# === Kanal boshqaruv funksiyalari ===
async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMINS:
        await update.message.reply_text("❌ Sizda bunday huquq yo'q.")
        return
    
    if not context.args:
        await update.message.reply_text("Foydalanish: /addchannel @kanal_nomi")
        return
    
    channel = context.args[0].strip()
    if not channel.startswith("@"):
        channel = f"@{channel}"
    
    if channel in CHANNEL_IDS:
        await update.message.reply_text(f"❌ {channel} kanali allaqachon qo'shilgan.")
        return
    
    try:
        chat = await context.bot.get_chat(channel)
        if chat.type not in ["channel", "supergroup"]:
            await update.message.reply_text("❌ Faqat kanal yoki superguruh qo'shish mumkin.")
            return
        
        bot_member = await context.bot.get_chat_member(channel, context.bot.id)
        if not bot_member.status == "administrator":
            await update.message.reply_text("❌ Bot kanalda admin emas. Iltimos, avval botni admin qiling.")
            return
        
        CHANNEL_IDS.append(channel)
        os.environ["CHANNEL_IDS"] = ",".join([ch.lstrip("@") for ch in CHANNEL_IDS])
        await update.message.reply_text(f"✅ {channel} kanali muvaffaqiyatli qo'shildi.")
    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik: {str(e)}")

async def remove_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMINS:
        await update.message.reply_text("❌ Sizda bunday huquq yo'q.")
        return
    
    if not context.args:
        await update.message.reply_text("Foydalanish: /removechannel @kanal_nomi")
        return
    
    channel = context.args[0].strip()
    if not channel.startswith("@"):
        channel = f"@{channel}"
    
    if channel not in CHANNEL_IDS:
        await update.message.reply_text(f"❌ {channel} kanali topilmadi.")
        return
    
    CHANNEL_IDS.remove(channel)
    os.environ["CHANNEL_IDS"] = ",".join([ch.lstrip("@") for ch in CHANNEL_IDS])
    await update.message.reply_text(f"✅ {channel} kanali muvaffaqiyatli o'chirildi.")

async def list_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMINS:
        await update.message.reply_text("❌ Sizda bunday huquq yo'q.")
        return
    
    if not CHANNEL_IDS:
        await update.message.reply_text("❌ Hozircha kanallar qo'shilmagan.")
        return
    
    message = "📢 Bot obuna kanallari:\n\n" + "\n".join(CHANNEL_IDS)
    await update.message.reply_text(message)

# === /start komandasi ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    stats[str(user.id)] = {"name": user.first_name}
    save_json("stats.json", stats)

    sub, ch = await is_subscribed(user.id, context)
    if not sub:
        try:
            chat = await context.bot.get_chat(ch)
            username = chat.username or ch.lstrip("@")
        except:
            username = ch.lstrip("@")
        btn = [
            [InlineKeyboardButton("📢 Obuna bo'lish", url=f"https://t.me/{username}")],
            [InlineKeyboardButton("✅ Obuna bo'ldim", callback_data="check_sub")]
        ]
        await update.message.reply_text(
            "📌 Botdan foydalanish uchun kanalga obuna bo'ling:",
            reply_markup=InlineKeyboardMarkup(btn)
        )
        return

    if context.args:
        param = context.args[0]
        if "_" in param:
            category, mid = param.split("_", 1)
            item = data.get(category, {}).get(mid)
            if item:
                type_text = "PDF" if category == "manhwa" else "Video"
                title = (
                    f"<b>📌 Nomi:</b> {item['title']}\n"
                    f"<b>📁 Turi:</b> {type_text}\n"
                    f"<b>📚 Qismlar:</b>"
                )
                parts = item.get("parts", {})
                btns = [[InlineKeyboardButton(f"📖 {name}", callback_data=f"get|{category}|{mid}|{name}")]
                        for name in parts]
                if parts:
                    btns.append([InlineKeyboardButton("📥 Hammasini yuklash", callback_data=f"getall|{category}|{mid}")])
                await update.message.reply_text(title, reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)
                return

    await update.message.reply_text("✅ Obuna tasdiqlandi. Endi kodni yuboring.")

# ... (qolgan funksiyalar o'zgarmagan holda qoldi) ...

# === Botni ishga tushirish ===
def main():
    app = Application.builder().token(TOKEN).build()

    # Komandalar
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addname", addname))
    app.add_handler(CommandHandler("addpart", addpart))
    app.add_handler(CommandHandler("publish", publish))
    app.add_handler(CommandHandler("addchannel", add_channel))
    app.add_handler(CommandHandler("removechannel", remove_channel))
    app.add_handler(CommandHandler("listchannels", list_channels))

    # Callback handlerlar
    app.add_handler(CallbackQueryHandler(check_sub, pattern="check_sub"))
    app.add_handler(CallbackQueryHandler(send_part, pattern=r"get\|"))
    app.add_handler(CallbackQueryHandler(getall_handler, pattern=r"getall\|"))

    # Message handlerlar
    media_filter = filters.Document.ALL | filters.VIDEO | filters.PHOTO
    app.add_handler(MessageHandler(media_filter, media_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code))

    print("✅ Bot ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()
