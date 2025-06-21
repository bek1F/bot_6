import os
import json
import asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# === Versiya ===
VERSION = "1.0.0"

# === Yuklamalar ===
load_dotenv()
TOKEN = os.getenv("TOKEN")
CHANNEL_IDS = [ch.strip() for ch in os.getenv("CHANNEL_IDS", "").split(",") if ch.strip()]
BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip()

# === JSON funksiyalar ===
def load_json(file):
    if not os.path.exists(file):
        return {}
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"⚠️ Xatolik: '{file}' bo‘sh yoki noto‘g‘ri formatda. Bo‘sh obyekt bilan yuklandi.")
        return {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# === Fayllarni boshlash ===
for file in ["data.json", "stats.json", "admins.json", "codes.json"]:
    if not os.path.exists(file): save_json(file, {})

data = load_json("data.json")
stats = load_json("stats.json")
admins = load_json("admins.json")
codes = load_json("codes.json")

# === Obuna tekshirish ===
async def is_subscribed(user_id, context):
    for ch in CHANNEL_IDS:
        try:
            member = await context.bot.get_chat_member(ch, user_id)
            if member.status in ["left", "kicked"]:
                return False, ch
        except:
            return False, ch
    return True, None

# === /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if "users" not in stats:
        stats["users"] = {}
    if str(user.id) not in stats["users"]:
        stats["users"][str(user.id)] = {"name": user.first_name}
        save_json("stats.json", stats)

    sub, ch = await is_subscribed(user.id, context)
    if not sub and ch:
        try:
            chat = await context.bot.get_chat(ch)
            btn = [
                [InlineKeyboardButton("📢 Obuna bo‘lish", url=f"https://t.me/{chat.username}")],
                [InlineKeyboardButton("✅ Obuna bo‘ldim", callback_data="check_sub")]
            ]
            return await update.message.reply_text(
                "📌 Botdan foydalanish uchun kanalga obuna bo‘ling:",
                reply_markup=InlineKeyboardMarkup(btn)
            )
        except:
            return await update.message.reply_text("❌ Kanalga kira olmadim. Iltimos, .env dagi CHANNEL_IDS ni tekshiring.")
    await update.message.reply_text("✅ Obuna tasdiqlandi. Endi kodni yuboring.")

# === Obuna qayta tekshirish ===
async def check_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sub, ch = await is_subscribed(query.from_user.id, context)
    if sub:
        await query.edit_message_text("✅ Obuna tasdiqlandi. Endi kodni yuboring.")
    else:
        try:
            ch_name = (await context.bot.get_chat(ch)).username
            await query.answer("❌ Siz hali ham obuna emassiz.", show_alert=True)
            await query.edit_message_text(f"❗ Obuna topilmadi: @{ch_name}")
        except:
            await query.edit_message_text("❌ Obuna kanali topilmadi.")

# === Kodni qabul qilish ===
async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    if code not in data:
        return await update.message.reply_text("❌ Bunday kod topilmadi yoki noto‘g‘ri.")
    item = data[code]
    type_label = "📖 PDF (kitob)" if item["type"] == "pdf" else "🎬 Video"
    title = f"📚 {item['name']}\nTuri: {type_label}\nQismlar:"
    btns = [[InlineKeyboardButton(f"{'📖 Bob' if item['type']=='pdf' else '🎞 Qism'} {i+1}", callback_data=f"get|{code}|{i}")]
            for i in range(len(item.get("parts", [])))]
    await update.message.reply_text(title, reply_markup=InlineKeyboardMarkup(btns))

# === Qism yuborish ===
async def send_part(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, code, idx = update.callback_query.data.split("|")
    idx = int(idx)
    item = data.get(code)
    if not item:
        return await update.callback_query.message.reply_text("❌ Ma'lumot topilmadi.")
    part = item['parts'][idx]
    if item['type'] == "pdf":
        await context.bot.send_document(update.effective_user.id, part['file_id'])
    else:
        await context.bot.send_video(update.effective_user.id, part['file_id'])
    await update.callback_query.answer()

# === Admin tekshir ===
def is_admin(uid):
    return str(uid) in admins

# === /addname <id> <name>
async def addname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Faqat adminlar kirita oladi
    if not is_admin(update.effective_user.id):
        return

    # Kamida 2 ta argument kerak: id va nom
    if len(context.args) < 2:
        return await update.message.reply_text("Foydalanish: /addname <id> <nomi>")

    # Id va nomni ajratish
    cid = context.args[0]
    name = " ".join(context.args[1:])

    # Admin sessionga vaqtincha saqlanadi
    context.user_data['add_id'] = cid
    context.user_data['add_name'] = name

    # Foydalanuvchiga javob
    await update.message.reply_text("✅ Nomi saqlandi. Endi video yoki PDF yuboring.")

# === Fayl qabul qilish ===
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'add_id' not in context.user_data: return
    file = update.message.document or update.message.video
    if not file: return await update.message.reply_text("Faqat PDF yoki video yuboring.")
    cid = context.user_data['add_id']
    name = context.user_data['add_name']
    ftype = "pdf" if update.message.document else "video"
    data[cid] = {"name": name, "type": ftype, "file_id": file.file_id, "parts": []}
    save_json("data.json", data)
    context.user_data.clear()
    await update.message.reply_text("Fayl saqlandi. Endi qismlarni /addpart <id> bilan yuklang.")

# === /addpart <id>
async def addpart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if len(context.args) != 1: return await update.message.reply_text("Foydalanish: /addpart <id>")
    context.user_data['add_part_id'] = context.args[0]
    await update.message.reply_text("📥 Endi PDF yoki video fayl yuboring.")

# === Qismni qabul qilish ===
async def handle_part(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = context.user_data.get('add_part_id')
    if not cid or cid not in data: return
    file = update.message.document or update.message.video
    if not file: return
    item = data[cid]
    parts = item.get("parts", [])
    idx = len(parts) + 1
    label = f"Bob {idx}" if item['type'] == "pdf" else f"Qism {idx}"
    parts.append({"file_id": file.file_id, "name": label})
    item['parts'] = parts
    save_json("data.json", data)
    await update.message.reply_text(f"✅ {label} qo‘shildi.\n✅ Qism joylandi.")

# === /publish <id>
async def publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if len(context.args) != 1: return await update.message.reply_text("Foydalanish: /publish <id>")
    cid = context.args[0]
    item = data.get(cid)
    if not item: return await update.message.reply_text("❌ Topilmadi.")
    caption = f"📄 {item['name']}\n📁 Turi: {item['type'].upper()}"
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("O‘qish", url=f"https://t.me/{BOT_USERNAME}?start={cid}")]])
    for ch in CHANNEL_IDS:
        try:
            await context.bot.send_document(chat_id=ch, document=item['file_id'], caption=caption, reply_markup=btn)
        except:
            continue
    await update.message.reply_text("✅ Kanallarga yuborildi.")

# === /add <code>
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1: return await update.message.reply_text("Foydalanish: /add <kod>")
    code = context.args[0]
    if code in codes:
        admins[str(update.effective_user.id)] = True
        del codes[code]
        save_json("admins.json", admins)
        save_json("codes.json", codes)
        await update.message.reply_text("✅ Siz admin bo‘ldingiz!")
    else:
        await update.message.reply_text("❌ Kod noto‘g‘ri yoki ishlatilgan.")

# === /addreklama <matn>
async def addreklama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args: return await update.message.reply_text("Foydalanish: /addreklama <matn>")
    text = " ".join(context.args)
    for uid in stats.get("users", {}):
        try:
            await context.bot.send_message(chat_id=uid, text=text)
        except:
            continue
    await update.message.reply_text("📣 Reklama yuborildi.")

# === Bot to‘xtaganda kanalga xabar ===
async def on_shutdown(app):
    for ch in CHANNEL_IDS:
        try:
            await app.bot.send_message(ch, "❌ Bot vaqtincha ishlamayapti. Yaqinda ishga tushadi.")
        except:
            continue

# === Botni ishga tushirish ===
async def main():
    print(f"✅ Bot ishga tushdi | Versiya: {VERSION}")
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addname", addname))
    app.add_handler(CommandHandler("addpart", addpart))
    app.add_handler(CommandHandler("publish", publish))
    app.add_handler(CommandHandler("add", add_admin))
    app.add_handler(CommandHandler("addreklama", addreklama))
    app.add_handler(CallbackQueryHandler(check_sub, pattern="check_sub"))
    app.add_handler(CallbackQueryHandler(send_part, pattern=r"get\|"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code))
    app.add_handler(MessageHandler((filters.Document.ALL | filters.VIDEO) & filters.ChatType.PRIVATE, handle_file))
    app.add_handler(MessageHandler((filters.Document.ALL | filters.VIDEO) & filters.ChatType.PRIVATE, handle_part))

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await on_shutdown(app)
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
