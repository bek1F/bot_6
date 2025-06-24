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

    # Agar deep-link bilan kelingan bo‘lsa (start parametri)
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

    # Oddiy /start
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
        category, label = "manhwa", "📕 Manhwa"
    elif update.message.video:
        file_id = update.message.video.file_id
        category, label = "anime", "🎬 Anime"
    else:
        await update.message.reply_text("❌ Faqat PDF yoki video yuboring.")
        return

    data.setdefault(category, {})[mid] = {
        "title": name,
        "cover": file_id,
        "parts": {},
        "type": category
    }
    save_json("data.json", data)
    await update.message.reply_text(f"{label} nomi qo‘shildi: {name}")

# === Part saqlash ===
async def part_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    info = awaiting_parts.get(uid)
    if not info:
        await update.message.reply_text("❌ Kutilmagan holat.")
        return
    mid, cat = info["id"], info["cat"]
    file = update.message.document or update.message.video or (update.message.photo[-1] if update.message.photo else None)

    if not file:
        await update.message.reply_text("❌ Noto‘g‘ri fayl.")
        return

    parts = data[cat][mid]["parts"]
    index = len(parts) + 1
    name = f"Bob {index}" if cat == "manhwa" else f"Qism {index}"
    parts[name] = file.file_id
    save_json("data.json", data)
    await update.message.reply_text(f"✅ {name} saqlandi.")

# === /publish komandasi ===
async def publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("Foydalanish: /publish <id>")
        return
    mid = context.args[0]
    for cat in ["manhwa", "anime"]:
        if mid in data.get(cat, {}):
            pending_publish[update.effective_user.id] = {"id": mid, "cat": cat}
            await update.message.reply_text("📤 Iltimos, rasm yoki video yuboring (post uchun).")
            return
    await update.message.reply_text("❌ ID topilmadi.")
    
# === Media qabul qilish: publish uchun ===
async def handle_publish_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    info = pending_publish.pop(uid)
    mid, cat = info["id"], info["cat"]

    # Media faylni aniqlash va turi
    media = None
    media_type = None

    if update.message.video:
        media = update.message.video.file_id
        media_type = "video"
    elif update.message.photo:
        media = update.message.photo[-1].file_id
        media_type = "photo"
    else:
        await update.message.reply_text("❌ Iltimos, faqat rasm yoki video yuboring.")
        return

    # Foydalanuvchi yozgan caption
    user_caption = update.message.caption or ""

    # Yuklab olish tugmasi
    deep_link = f"https://t.me/{BOT_USERNAME}?start={cat}_{mid}"
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("📥 Yuklab olish", url=deep_link)]])

    # Har bir kanalga yuborish
    for ch in CHANNEL_IDS:
        try:
            if media_type == "photo":
                await context.bot.send_photo(
                    chat_id=ch,
                    photo=media,
                    caption=user_caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=btn
                )
            elif media_type == "video":
                await context.bot.send_video(
                    chat_id=ch,
                    video=media,
                    caption=user_caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=btn
                )
        except Exception as e:
            print(f"Xatolik: {e}")

    await update.message.reply_text("✅ Post yuborildi.")


    # Media faylni aniqlash
    media = update.message.photo[-1].file_id if update.message.photo else \
            update.message.video.file_id if update.message.video else None

    if not media:
        await update.message.reply_text("❌ Iltimos, faqat rasm yoki video yuboring.")
        return

    # Foydalanuvchi yozgan caption
    user_caption = update.message.caption or ""

    # Yuklab olish tugmasi
    deep_link = f"https://t.me/{BOT_USERNAME}?start={cat}_{mid}"
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("📥 Yuklab olish", url=deep_link)]])

    # Har bir kanalga yuborish
    for ch in CHANNEL_IDS:
        try:
            if cat == "manhwa":
                await context.bot.send_photo(
                    chat_id=ch,
                    photo=media,
                    caption=user_caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=btn
                )
            else:
                await context.bot.send_video(
                    chat_id=ch,
                    video=media,
                    caption=user_caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=btn
                )
        except Exception as e:
            print(f"Xatolik: {e}")

    await update.message.reply_text("✅ Post yuborildi.")


# === Botni ishga tushirish ===
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addname", addname))
    app.add_handler(CommandHandler("addpart", addpart))
    app.add_handler(CommandHandler("publish", publish))

    app.add_handler(CallbackQueryHandler(check_sub, pattern="check_sub"))
    app.add_handler(CallbackQueryHandler(send_part, pattern=r"get\|"))
    app.add_handler(CallbackQueryHandler(getall_handler, pattern=r"getall\|"))

    media_filter = filters.Document.ALL | filters.VIDEO | filters.PHOTO
    app.add_handler(MessageHandler(media_filter, media_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code))

    print("✅ Bot ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()
