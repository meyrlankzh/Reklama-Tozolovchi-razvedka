import sqlite3
import re
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes
from telegram.ext import filters
from telegram.constants import ChatAction
from datetime import datetime

# Log konfiguratsiyasi
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# TOKEN sizning so'rovingizdagi kabi qoldirildi
TOKEN = "8591662739:AAHxRMnUsrCp8iQNibpWQ0y6enbwLBUVSng"

# Ma'lumotlar bazasini qayta yaratish
def init_database():
    conn = sqlite3.connect("chat_data.db", check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute("DROP TABLE IF EXISTS messages")
    cursor.execute("DROP TABLE IF EXISTS users")
    cursor.execute("DROP TABLE IF EXISTS chats")
    cursor.execute("DROP TABLE IF EXISTS bot_settings")
    
    cursor.execute('''CREATE TABLE messages (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id TEXT NOT NULL,
                      username TEXT,
                      first_name TEXT,
                      last_name TEXT,
                      message TEXT,
                      chat_id TEXT NOT NULL,
                      chat_title TEXT,
                      message_id TEXT,
                      timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                  )''')
    
    cursor.execute('''CREATE TABLE users (
                      user_id TEXT PRIMARY KEY,
                      username TEXT,
                      first_name TEXT,
                      last_name TEXT,
                      last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
                  )''')
    
    cursor.execute('''CREATE TABLE chats (
                      chat_id TEXT PRIMARY KEY,
                      chat_title TEXT,
                      chat_type TEXT,
                      last_activity DATETIME DEFAULT CURRENT_TIMESTAMP
                  )''')
    
    cursor.execute('''CREATE TABLE bot_settings (
                      setting_key TEXT PRIMARY KEY,
                      setting_value TEXT
                  )''')
    
    cursor.execute('''INSERT OR IGNORE INTO bot_settings (setting_key, setting_value) 
                      VALUES ('invisible_mode', 'true')''')
    
    conn.commit()
    conn.close()
    print("✅ Ma'lumotlar bazasi qayta yaratildi")

# Bazani ishga tushirish
init_database()

# Yangi ulanish
conn = sqlite3.connect("chat_data.db", check_same_thread=False)
cursor = conn.cursor()

# Kuchaytirilgan Reklama filtri
def is_spam(text):
    if not text:
        return False
    
    patterns = [
        r"http[s]?://",  # linklar
        r"t\.me/",       # telegram linklar
        r"@[\w_]+",      # username lar
        r"joinchat",     # guruhga qo'shilish
        r"канал", r"каналы", r"групп", r"канале",  # ruscha reklama
        r"kanal", r"guruh", r"gruppa",             # o'zbekcha reklama
        r"подпишись", r"подписаться",              # obuna bo'lish
        r"obuna", r"obunа", r"obunа bo'ling",      # obuna
        r"купить", r"продать", r"sotaman", r"sotib olaman",  # savdo
        r"bit\.ly", r"t\.ly", r"shorturl",         # qisqa linklar
        r"партнерк", r"hamkor", r"hamkorlik",      # hamkorlik
        r"заработ", r"daromad", r"pul ishlash",    # daromad
        r"крипто", r"crypto", "bitcoin",          # kripto
        r"бесплатно", r"bepul", r"tekinga",        # bepul
        r"бонус", r"bonus", r"promo",              # bonus
        r"реклам", r"reklama", r"reklamа"          # reklama so'zlari
    ]
    
    text_lower = text.lower()
    return any(re.search(pattern, text_lower, re.IGNORECASE) for pattern in patterns)

# Botning invisible mode ni tekshirish
def is_invisible_mode():
    cursor.execute("SELECT setting_value FROM bot_settings WHERE setting_key = 'invisible_mode'")
    result = cursor.fetchone()
    return result and result[0] == 'true'

# Foydalanuvchi ma'lumotlarini yangilash
def update_user_info(user, chat_id=None, chat_title=None):
    try:
        cursor.execute('''INSERT OR REPLACE INTO users 
                          (user_id, username, first_name, last_name, last_seen) 
                          VALUES (?, ?, ?, ?, datetime('now'))''',
                      (str(user.id), user.username or '', user.first_name or '', 
                       user.last_name or ''))
        
        if chat_id and chat_title:
            cursor.execute('''INSERT OR REPLACE INTO chats 
                              (chat_id, chat_title, chat_type, last_activity) 
                              VALUES (?, ?, ?, datetime('now'))''',
                          (str(chat_id), chat_title, "group"))
        conn.commit()
    except Exception as e:
        logger.error(f"Foydalanuvchi ma'lumotlarini saqlashda xato: {e}")

# YANGI: Reklamani o'chirish va ogohlantirish
async def handle_spam_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.message
        if not message:
            return
            
        user = message.from_user
        chat = message.chat
        
        # Bot o'zining xabarlarini tekshirmaslik
        if user.id == context.bot.id:
            return
        
        # 1. Matnni aniqlash
        text = message.text or message.caption or ""
        
        # 2. Media turlari uchun maxsus matn yaratish
        if not text:
            if message.photo:
                text = "[PHOTO]"
            elif message.video:
                text = "[VIDEO]"
            elif message.video_note:
                text = "[VIDEO_NOTE - KRUJKA]"
            elif message.document:
                text = f"[FILE: {message.document.file_name}]"
            elif message.voice:
                text = "[VOICE_MESSAGE]"
            elif message.location:
                text = "[LOCATION]"
            # Qo'shimcha turlar uchun (sticker, contact, va boshqalar)
            elif message.sticker:
                text = "[STICKER]"
            elif message.contact:
                text = "[CONTACT]"
            elif message.animation:
                text = "[GIF/ANIMATION]"
            elif message.poll:
                text = "[POLL]"
            # Boshqa noma'lum turdagi xabarlar
            else:
                text = "[OTHER_MEDIA_TYPE]"
        
        # Reklama tekshirish
        if is_spam(text):
            try:
                # Xabarni o'chirish
                await message.delete()
                logger.info(f"Reklama o'chirildi: {user.first_name} - {text[:50]}")
                
                # Foydalanuvchini ogohlantirish (faqat visible mode da)
                if not is_invisible_mode():
                    warning_msg = await context.bot.send_message(
                        chat_id=chat.id, 
                        text=f"⚠️ {user.first_name}, reklama yubormang!"
                    )
                    
                    # 10 soniyadan keyin ogohlantirish xabarini o'chirish
                    await asyncio.sleep(10)
                    try:
                        await warning_msg.delete()
                    except:
                        pass
                
                # Reklama xabarini bazaga saqlash
                update_user_info(user, chat.id, chat.title)
                cursor.execute('''INSERT INTO messages 
                                  (user_id, username, first_name, last_name, message, 
                                   chat_id, chat_title, message_id) 
                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                              (str(user.id), user.username or '', user.first_name or '', 
                               user.last_name or '', f"[REKLAMA] {text}", str(chat.id), chat.title, str(message.message_id)))
                conn.commit()
                
            except Exception as e:
                logger.error(f"Reklamani o'chirishda xato: {e}")
            return
        
        # Oddiy xabarlarni saqlash (matn yoki media tasvirlari)
        update_user_info(user, chat.id, chat.title)
        cursor.execute('''INSERT INTO messages 
                          (user_id, username, first_name, last_name, message, 
                           chat_id, chat_title, message_id) 
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                      (str(user.id), user.username or '', user.first_name or '', 
                       user.last_name or '', text, str(chat.id), chat.title, str(message.message_id)))
        conn.commit()
        
    except Exception as e:
        logger.error(f"Xabarni qayta ishlashda xato: {e}")

# Guruhdagi eski xabarlarni skaner qilish
async def scan_chat_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if str(user.id) not in ["6420024593"]:
        await update.message.reply_text("🚫 Bu buyruq faqat adminlar uchun!")
        return
    
    chat = update.effective_chat
    if chat.type == 'private':
        await update.message.reply_text("❌ Bu buyruq faqat guruhlarda ishlaydi!")
        return
    
    try:
        await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)
        message = await update.message.reply_text("🔍 Guruh xabarlari skanerlanmoqda...")
        
        saved_count = 0
        max_messages = 2000
        
        async for telegram_message in context.bot.get_chat_history(chat.id, limit=max_messages):
            try:
                if telegram_message.from_user and telegram_message.from_user.id == context.bot.id:
                    continue
                
                user = telegram_message.from_user
                if not user:
                    continue
                
                # Skanerlashda ham matnni aniqlash logikasi
                text = telegram_message.text or telegram_message.caption or ""
                
                if not text:
                    if telegram_message.photo:
                        text = "[PHOTO]"
                    elif telegram_message.video:
                        text = "[VIDEO]"
                    elif telegram_message.video_note:
                        text = "[VIDEO_NOTE - KRUJKA]"
                    elif telegram_message.document:
                        text = f"[FILE: {telegram_message.document.file_name}]"
                    elif telegram_message.voice:
                        text = "[VOICE_MESSAGE]"
                    elif telegram_message.location:
                        text = "[LOCATION]"
                    elif telegram_message.sticker:
                        text = "[STICKER]"
                    elif telegram_message.contact:
                        text = "[CONTACT]"
                    elif telegram_message.animation:
                        text = "[GIF/ANIMATION]"
                    elif telegram_message.poll:
                        text = "[POLL]"
                    else:
                        text = "[OTHER_MEDIA_TYPE]"

                # Matn yoki o'rnini bosuvchi matn bo'lsa saqlash
                if text.strip():
                    update_user_info(user, chat.id, chat.title)
                    
                    cursor.execute('''INSERT OR IGNORE INTO messages 
                                      (user_id, username, first_name, last_name, message, 
                                       chat_id, chat_title, message_id) 
                                      VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                                  (str(user.id), user.username or '', user.first_name or '', 
                                   user.last_name or '', text, str(chat.id), chat.title, 
                                   str(telegram_message.message_id)))
                    conn.commit()
                    
                    saved_count += 1
                    
                    if saved_count % 200 == 0:
                        await message.edit_text(f"🔍 {saved_count} ta xabar saqlandi...")
                
            except Exception as e:
                continue
        
        await message.edit_text(f"✅ {saved_count} ta xabar saqlandi!")
        
    except Exception as e:
        logger.error(f"Xabarlarni skaner qilishda xato: {e}")
        await update.message.reply_text("❌ Xatolik yuz berdi")

# Bot guruhga qo'shilganda - AVTOMATIK SKANER
async def handle_bot_added(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.new_chat_members:
        for member in update.message.new_chat_members:
            if member.id == context.bot.id:
                chat = update.effective_chat
                logger.info(f"Bot {chat.title} guruhiga qo'shildi")
                
                # Invisible mode da qo'shilish xabarini o'chirish
                if is_invisible_mode():
                    try:
                        await update.message.delete()
                    except Exception as e:
                        logger.error(f"Qo'shilish xabarini o'chirishda xato: {e}")
                
                # AVTOMATIK SKANER - 500 ta xabar
                try:
                    saved_count = 0
                    async for telegram_message in context.bot.get_chat_history(chat.id, limit=500):
                        try:
                            if telegram_message.from_user and telegram_message.from_user.id == context.bot.id:
                                continue
                            
                            user = telegram_message.from_user
                            if not user:
                                continue
                                
                            # Skanerlashda ham matnni aniqlash logikasi
                            text = telegram_message.text or telegram_message.caption or ""
                            
                            if not text:
                                if telegram_message.photo:
                                    text = "[PHOTO]"
                                elif telegram_message.video:
                                    text = "[VIDEO]"
                                elif telegram_message.video_note:
                                    text = "[VIDEO_NOTE - KRUJKA]"
                                elif telegram_message.document:
                                    text = f"[FILE: {telegram_message.document.file_name}]"
                                elif telegram_message.voice:
                                    text = "[VOICE_MESSAGE]"
                                elif telegram_message.location:
                                    text = "[LOCATION]"
                                elif telegram_message.sticker:
                                    text = "[STICKER]"
                                elif telegram_message.contact:
                                    text = "[CONTACT]"
                                elif telegram_message.animation:
                                    text = "[GIF/ANIMATION]"
                                elif telegram_message.poll:
                                    text = "[POLL]"
                                else:
                                    text = "[OTHER_MEDIA_TYPE]"
                            
                            if text.strip():
                                update_user_info(user, chat.id, chat.title)
                                
                                cursor.execute('''INSERT OR IGNORE INTO messages 
                                                  (user_id, username, first_name, last_name, message, 
                                                   chat_id, chat_title, message_id) 
                                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                                              (str(user.id), user.username or '', user.first_name or '', 
                                               user.last_name or '', text, str(chat.id), chat.title, 
                                               str(telegram_message.message_id)))
                                conn.commit()
                                saved_count += 1
                                
                        except Exception as e:
                            continue
                    
                    logger.info(f"Avtomatik skaner: {saved_count} ta xabar saqlandi")
                    
                except Exception as e:
                    logger.error(f"Avtomatik skanerda xato: {e}")

# Bot guruhdan chiqarilganda
async def handle_bot_removed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.left_chat_member:
        if update.message.left_chat_member.id == context.bot.id:
            chat = update.effective_chat
            logger.info(f"Bot {chat.title} guruhidan chiqarildi")
            
            if is_invisible_mode():
                try:
                    await update.message.delete()
                except Exception as e:
                    logger.error(f"Chiqarilish xabarini o'chirishda xato: {e}")

# Start komandasi - faqat shaxsiy chatda
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    
    if chat.type != 'private':
        if is_invisible_mode():
            try:
                await update.message.delete()
            except:
                pass
        return
    
    update_user_info(user)
    
    welcome_text = f"""
🤖 Assalomu alaykum {user.first_name}!

Bu bot guruhlarni monitoring qilish va foydalanuvchi qidirish uchun mo'ljallangan.

📊 **Admin Buyruqlari:**
/search [username] - Foydalanuvchi qidirish (Endi @username ham ishlaydi)
/scan - Guruh xabarlarini skaner qilish (2000 ta)
/chats - Guruhlar ro'yxati
/stats - Statistika
/mode - Bot rejimini o'zgartirish

🔧 **Rejimlar:**
- 🕵️ Invisible: Bot sezilmas ishlaydi
- 👁️ Visible: Bot normal ishlaydi

⚠️ Bot faqat adminlar uchun.
    """
    await update.message.reply_text(welcome_text)

# Foydalanuvchi qidirish
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if update.effective_chat.type != 'private':
        if is_invisible_mode():
            try:
                await update.message.delete()
            except:
                pass
        return
    
    if str(user.id) not in ["6420024593"]:
        await update.message.reply_text("🚫 Bu buyruq faqat adminlar uchun!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Iltimos, qidirish uchun kalit so'z kiriting:\n/search [username yoki ism]")
        return
    
    search_term = ' '.join(context.args)
    
    # YANGI: @ belgisi bilan boshlansa, uni olib tashlash
    if search_term.startswith('@'):
        search_term = search_term[1:]

    try:
        # Eslatma: SQL so'rovi allaqachon barcha xabarlarni va guruhlarni qidiradi (u.user_id = m.user_id JOIN tufayli).
        cursor.execute('''SELECT DISTINCT u.user_id, u.username, u.first_name, u.last_name, 
                                 COUNT(m.id) as message_count
                          FROM users u
                          LEFT JOIN messages m ON u.user_id = m.user_id
                          WHERE u.username LIKE ? OR u.first_name LIKE ? OR u.last_name LIKE ? OR m.message LIKE ?
                          GROUP BY u.user_id
                          ORDER BY message_count DESC LIMIT 20''',
                      (f'%{search_term}%', f'%{search_term}%', f'%{search_term}%', f'%{search_term}%'))
        
        users = cursor.fetchall()
        
        if not users:
            await update.message.reply_text(f"❌ '{search_term}' bo'yicha foydalanuvchi topilmadi")
            return
        
        response = f"🔍 **{search_term}** - {len(users)} ta foydalanuvchi:\n\n"
        
        for i, (user_id, username, first_name, last_name, msg_count) in enumerate(users, 1):
            user_name = f"{first_name or ''} {last_name or ''}".strip() or username or f"ID:{user_id}"
            
            # Foydalanuvchi xabarlarini olish (barcha guruhlardan)
            cursor.execute('''SELECT chat_title, message, timestamp, chat_id, message_id
                              FROM messages 
                              WHERE user_id = ? 
                              ORDER BY timestamp DESC''', (user_id,))
            user_messages = cursor.fetchall()
            
            response += f"{i}. **{user_name}** ({'@' + username if username else 'ID:' + user_id}) - {msg_count} xabar\n"
            
            # Har bir xabar uchun link
            for j, (chat_title, message, timestamp, chat_id, tg_message_id) in enumerate(user_messages, 1):
                # Sana va vaqtni formatlash
                if timestamp:
                    try:
                        # O'zbekcha format: DD.MM.YYYY HH:MM
                        dt_obj = datetime.strptime(timestamp[:16], '%Y-%m-%d %H:%M')
                        full_datetime = dt_obj.strftime('%d.%m.%Y %H:%M')
                    except:
                        full_datetime = timestamp[:16]
                else:
                    full_datetime = "Noma'lum vaqt"
                
                # Xabar uzunligini qisqartirish (uzun bo'lsa)
                short_msg = message
                if len(short_msg) > 50:
                    short_msg = short_msg[:50] + "..."
                
                # LINK YARATISH
                if tg_message_id and chat_id:
                    try:
                        chat_id_clean = str(chat_id).replace('-100', '')
                        # message_link - Xabarga to'g'ridan-to'g'ri havola (Telegram linki)
                        message_link = f"https://t.me/c/{chat_id_clean}/{tg_message_id}"
                        # Qo'shimcha: Xabar qaysi guruhdan ekanligini ko'rsatish
                        response += f"   - {full_datetime} ({chat_title}): [{short_msg}]({message_link})\n"
                    except:
                        response += f"   - {full_datetime} ({chat_title}): {short_msg}\n"
                else:
                    response += f"   - {full_datetime} ({chat_title}): {short_msg}\n"
            
            response += "\n"
        
        await update.message.reply_text(response, parse_mode='Markdown', disable_web_page_preview=True)
    
    except Exception as e:
        logger.error(f"Qidirishda xato: {e}")
        await update.message.reply_text("❌ Qidirishda xatolik yuz berdi")

# Guruhlar ro'yxati
async def chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if update.effective_chat.type != 'private':
        if is_invisible_mode():
            try:
                await update.message.delete()
            except:
                pass
        return
    
    if str(user.id) not in ["6420024593"]:
        await update.message.reply_text("🚫 Bu buyruq faqat adminlar uchun!")
        return
    
    try:
        cursor.execute('''SELECT chat_id, chat_title, 
                                 COUNT(DISTINCT user_id) as active_users,
                                 COUNT(id) as total_messages,
                                 MAX(timestamp) as last_activity
                          FROM messages 
                          GROUP BY chat_id, chat_title
                          ORDER BY last_activity DESC LIMIT 20''')
        
        chats = cursor.fetchall()
        
        if not chats:
            await update.message.reply_text("❌ Hozircha guruhlar ma'lumoti yo'q")
            return
        
        response = "📊 **Guruhlar ro'yxati:**\n\n"
        
        for i, (chat_id, chat_title, active_users, total_msgs, last_activity) in enumerate(chats, 1):
            if last_activity:
                try:
                    date_obj = datetime.strptime(last_activity[:10], '%Y-%m-%d')
                    months_ru = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'нояб', 'дек']
                    month_name = months_ru[date_obj.month - 1]
                    formatted_date = f"{date_obj.day} {month_name}."
                except:
                    formatted_date = last_activity[:10]
            else:
                formatted_date = "Noma'lum"
            
            # Guruh linkini yaratish
            try:
                chat_id_clean = str(chat_id).replace('-100', '')
                chat_link = f"https://t.me/c/{chat_id_clean}"
                response += f"{formatted_date} [{chat_title}]({chat_link}) ({total_msgs})\n"
            except:
                response += f"{formatted_date} {chat_title} ({total_msgs})\n"
        
        await update.message.reply_text(response, parse_mode='Markdown', disable_web_page_preview=True)
    
    except Exception as e:
        logger.error(f"Chats da xato: {e}")
        await update.message.reply_text("❌ Guruhlar ro'yxatini olishda xatolik")

# Statistika
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if update.effective_chat.type != 'private':
        if is_invisible_mode():
            try:
                await update.message.delete()
            except:
                pass
        return
    
    if str(user.id) not in ["6420024593"]:
        await update.message.reply_text("🚫 Bu buyruq faqat adminlar uchun!")
        return
    
    try:
        cursor.execute("SELECT COUNT(*) FROM messages")
        total_messages = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM messages")
        total_users = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(DISTINCT chat_id) FROM messages")
        total_chats = cursor.fetchone()[0] or 0
        
        response = "📈 **Bot statistika:**\n\n"
        response += f"💬 **Xabarlar:** {total_messages}\n"
        response += f"👥 **Foydalanuvchilar:** {total_users}\n"
        response += f"📋 **Guruhlar:** {total_chats}\n"
        
        await update.message.reply_text(response)
    
    except Exception as e:
        logger.error(f"Stats da xato: {e}")
        await update.message.reply_text("❌ Statistika olishda xatolik")

# Bot rejimini o'zgartirish
async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    
    if chat.type != 'private':
        return
    
    if str(user.id) not in ["6420024593"]:
        await update.message.reply_text("🚫 Bu buyruq faqat adminlar uchun!")
        return
    
    current_mode = is_invisible_mode()
    
    if context.args:
        new_mode = context.args[0].lower()
        if new_mode in ['on', 'true', '1', 'invisible']:
            cursor.execute("UPDATE bot_settings SET setting_value = 'true' WHERE setting_key = 'invisible_mode'")
            mode_text = "🕵️ **Invisible mode** yoqildi"
        elif new_mode in ['off', 'false', '0', 'visible']:
            cursor.execute("UPDATE bot_settings SET setting_value = 'false' WHERE setting_key = 'invisible_mode'")
            mode_text = "👁️ **Visible mode** yoqildi"
        else:
            await update.message.reply_text("❌ Noto'g'ri rejim. /mode [on/off]")
            return
        conn.commit()
    else:
        mode_text = f"🔄 Joriy rejim: {'🕵️ Invisible' if current_mode else '👁️ Visible'}"
    
    response = f"{mode_text}\n\n"
    response += "**Invisible mode:** Bot guruhda hech qanday xabar yubormaydi\n"
    response += "**Visible mode:** Bot normal ishlaydi"
    
    await update.message.reply_text(response)

# Xatolik handler
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Xato: {context.error}")

# Asosiy funksiya
def main():
    try:
        application = Application.builder().token(TOKEN).build()
        
        # Handlerlarni qo'shish
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("search", search_command))
        application.add_handler(CommandHandler("scan", scan_chat_history))
        application.add_handler(CommandHandler("chats", chats_command))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(CommandHandler("mode", mode_command))
        
        # Maxsus handlerlar
        application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_bot_added))
        application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, handle_bot_removed))
        
        # Barcha xabarlarni (matn, sarlavha, rasm, video, krujka, fayl, ovoz, joylashuv, stiker va boshqalar) qayta ishlash
        application.add_handler(MessageHandler(
            filters.ALL & 
            ~filters.COMMAND & 
            ~filters.StatusUpdate.ALL, 
            handle_spam_message
        ))
        
        application.add_error_handler(error_handler)
        
        print("🤖 Bot ishga tushdi...")
        print("✅ Ma'lumotlar bazasi qayta yaratildi")
        print("🚫 KUCHAYTIRILGAN REKLAMA FILTRI")
        print("🕵️ INVISIBLE MODE - MAXFIYLIK")
        print("🔍 AVTOMATIK SKANER - 500 ta xabar")
        print("➕ MEDIA XABARLAR QO'SHILDI")
        print("🔍 @username QIDIRUVI YOQILDI")

        application.run_polling()
        
    except Exception as e:
        logger.error(f"Botni ishga tushirishda xato: {e}")

if __name__ == "__main__":
    main()