import os
import json
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.constants import ParseMode

# === JSON o‘quvchi/yozuvchi funksiyalar ===
def load_json(file):
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# === Fayllarni yaratish ===
for file in ["data.json", "stats.json", "codes.json", "channels.json"]:
    if not os.path.exists(file):
        save_json(file, {})

data = load_json("data.json")
stats = load_json("stats.json")
channels_data = load_json("channels.json")
CHANNEL_IDS = channels_data.get("channels", [])

# === Versiya va .env yuklash ===
VERSION = "1.0.0"
load_dotenv()

TOKEN = os.getenv("TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip()
# ADMINS ro'yxati olib tashlandi

# === Obuna tekshirish funksiyasi ===
async def is_subscribed(user_id, context):
    for ch in CHANNEL_IDS:
        try:
            member = await context.bot.get_chat_member(ch, user_id)
            if member.status in ["left", "kicked"]:
                return False, ch
        except Exception as e:
            print(f"Kanal tekshiruvida xato: {e}")
            return False, ch
    return True, None

# === Kanal boshqaruvi ===
async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Foydalanish: /addchannel @kanal")
    
    channel = context.args[0].strip()
    if not channel.startswith("@"):
        channel = f"@{channel}"

    if channel in CHANNEL_IDS:
        return await update.message.reply_text(f"❌ {channel} allaqachon mavjud.")

    try:
        chat = await context.bot.get_chat(channel)
        if chat.type not in ["channel", "supergroup"]:
            return await update.message.reply_text("❌ Faqat kanal yoki superguruh qo'shish mumkin.")
        
        bot_member = await context.bot.get_chat_member(channel, context.bot.id)
        if bot_member.status != "administrator":
            return await update.message.reply_text("❌ Bot admin emas.")
        
        CHANNEL_IDS.append(channel)
        save_json("channels.json", {"channels": CHANNEL_IDS})
        await update.message.reply_text(f"✅ {channel} qo'shildi.")
    except Exception as e:
        await update.message.reply_text(f"❌ Xato: {str(e)}")

async def remove_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Foydalanish: /removechannel @kanal")
    
    channel = context.args[0].strip()
    if not channel.startswith("@"):
        channel = f"@{channel}"
    if channel not in CHANNEL_IDS:
        return await update.message.reply_text(f"❌ {channel} topilmadi.")
    
    CHANNEL_IDS.remove(channel)
    save_json("channels.json", {"channels": CHANNEL_IDS})
    await update.message.reply_text(f"✅ {channel} o'chirildi.")

async def list_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not CHANNEL_IDS:
        return await update.message.reply_text("❌ Kanal yo'q.")
    await update.message.reply_text("📢 Kanallar ro'yxati:\n" + "\n".join(CHANNEL_IDS))

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
            [InlineKeyboardButton("📢 Obuna bo‘lish", url=f"https://t.me/{username}")],
            [InlineKeyboardButton("✅ Obuna bo‘ldim", callback_data="check_sub")]
        ]
        await update.message.reply_text(
            "📌 Botdan foydalanish uchun kanalga obuna bo‘ling:",
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

# === Obuna qayta tekshiruv ===
async def check_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sub, ch = await is_subscribed(query.from_user.id, context)

    if sub:
        await query.edit_message_text("✅ Obuna tasdiqlandi. Endi kodni yuboring.")
    else:
        try:
            chat = await context.bot.get_chat(ch)
            username = chat.username or ch.lstrip("@")
        except:
            username = ch.lstrip("@")
        await query.answer("❌ Siz hali ham obuna emassiz.", show_alert=True)
        await query.edit_message_text(f"❗ Obuna topilmadi: @{username}")

# === Kodni qabul qilish ===
async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    if "manhwa" in data and code in data["manhwa"]:
        item = data["manhwa"][code]
        title = f"{item['title']}\n📁 Turi: PDF\n📚 Boblar:"
        parts = item.get("parts", {})
        btns = [[InlineKeyboardButton(f"📖 {name}", callback_data=f"get|manhwa|{code}|{name}")] for name in parts]
        await update.message.reply_text(title, reply_markup=InlineKeyboardMarkup(btns))
    else:
        await update.message.reply_text("❌ Bunday kod topilmadi yoki noto‘g‘ri.")

# === Qism yuborish ===
async def send_part(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, category, code, part_name = query.data.split("|")
    item = data.get(category, {}).get(code)

    if not item or part_name not in item["parts"]:
        await query.edit_message_text("❌ Qism topilmadi.")
        return

    file_id = item["parts"][part_name]
    if category == "manhwa":
        await context.bot.send_document(query.from_user.id, file_id)
    else:
        await context.bot.send_video(query.from_user.id, file_id)

# === Barcha qismlarni yuborish ===
async def getall_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, cat, mid = query.data.split("|")
    item = data.get(cat, {}).get(mid)
    if not item:
        await query.edit_message_text("❌ Ma'lumot topilmadi.")
        return

    for name, file_id in item.get("parts", {}).items():
        if cat == "manhwa":
            await context.bot.send_document(query.from_user.id, file_id)
        else:
            await context.bot.send_video(query.from_user.id, file_id)

# === Fayl yuklash statuslari ===
pending_uploads = {}
awaiting_parts = {}
pending_publish = {}

# === /addname komandasi ===
async def addname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Foydalanish: /addname <id> <nom>")
        return
    mid, name = context.args[0], " ".join(context.args[1:])
    category = "manhwa" if mid in data.get("manhwa", {}) else "anime" if mid in data.get("anime", {}) else None

    if category:
        data[category][mid]["title"] = name
        save_json("data.json", data)
        awaiting_parts[update.effective_user.id] = {"id": mid, "cat": category}
        await update.message.reply_text(f"📎 {name} nomi yangilandi.\n📤 Endi qismlarni yuboring...")
    else:
        pending_uploads[update.effective_user.id] = {"id": mid, "name": name}
        await update.message.reply_text("📎 Iltimos, PDF yoki video yuboring...")

# === /addpart komandasi ===
async def addpart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("Foydalanish: /addpart <id>")
        return
    mid = context.args[0]
    for cat in ["manhwa", "anime"]:
        if mid in data.get(cat, {}):
            awaiting_parts[update.effective_user.id] = {"id": mid, "cat": cat}
            await update.message.reply_text("📤 Qismlarni yuboring...")
            return
    await update.message.reply_text("❌ ID topilmadi.")

# === Media router ===
async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in pending_uploads:
        await handle_media_upload(update, context)
    elif uid in awaiting_parts:
        await part_handler(update, context)
    elif uid in pending_publish:
        await handle_publish_media(update, context)
    else:
        await update.message.reply_text("❌ Sizdan hech qanday kutish yo‘q.")

# === Media saqlash (yangi) ===
async def handle_media_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    info = pending_uploads.pop(uid)
    mid, name = info["id"], info["name"]

    if update.message.document:
        file_id = update.message.document.file_id
    elif update.message.video:
        file_id = update.message.video.file_id
    elif update.message.photo:
        file_id = update.message.photo[-1].file_id
    else:
        await update.message.reply_text("❌ Fayl formati noto‘g‘ri.")
        return

    if "manhwa" not in data:
        data["manhwa"] = {}
    if mid not in data["manhwa"]:
        data["manhwa"][mid] = {"title": name, "parts": {}}
    else:
        data["manhwa"][mid]["title"] = name

    part_name = "1"
    data["manhwa"][mid]["parts"][part_name] = file_id
    save_json("data.json", data)
    await update.message.reply_text(f"✅ {name} uchun fayl qabul qilindi.")

# === Qism qo‘shish uchun media qabul qilish ===
async def part_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    info = awaiting_parts.get(uid)
    if not info:
        await update.message.reply_text("❌ Qism qo‘shish uchun ID topilmadi.")
        return

    mid = info["id"]
    cat = info["cat"]
    if cat not in data:
        data[cat] = {}

    if mid not in data[cat]:
        data[cat][mid] = {"title": "", "parts": {}}

    if update.message.document:
        file_id = update.message.document.file_id
    elif update.message.video:
        file_id = update.message.video.file_id
    elif update.message.photo:
        file_id = update.message.photo[-1].file_id
    else:
        await update.message.reply_text("❌ Fayl formati noto‘g‘ri.")
        return

    part_num = len(data[cat][mid]["parts"]) + 1
    part_name = str(part_num)
    data[cat][mid]["parts"][part_name] = file_id
    save_json("data.json", data)
    await update.message.reply_text(f"✅ {cat} {mid} uchun {part_name}-qism qabul qilindi.")

# === /publish komandasi (placeholder) ===
async def publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛠️ Bu funksiya hali ishlab chiqilmoqda.")

# === Main funksiyasi ===
def main():
    app = Application.builder().token(TOKEN).build()

    # Komandalar
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addchannel", add_channel))
    app.add_handler(CommandHandler("removechannel", remove_channel))
    app.add_handler(CommandHandler("listchannels", list_channels))
    app.add_handler(CommandHandler("addname", addname))
    app.add_handler(CommandHandler("addpart", addpart))
    app.add_handler(CommandHandler("publish", publish))

    # CallbackQuery handlerlar
    app.add_handler(CallbackQueryHandler(check_sub, pattern="check_sub"))
    app.add_handler(CallbackQueryHandler(send_part, pattern=r"get\|"))
    app.add_handler(CallbackQueryHandler(getall_handler, pattern=r"getall\|"))

    # Media va matn handlerlari
    media_filter = filters.Document.ALL | filters.VIDEO | filters.PHOTO
    app.add_handler(MessageHandler(media_filter, media_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code))

    print("✅ Bot ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()
