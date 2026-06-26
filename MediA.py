import os
import asyncio
import re
import sqlite3
import random
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatAction

TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = 8597653867

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

conn = sqlite3.connect("SAve.db")
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS queue (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    text TEXT,
    status TEXT
)
""")
conn.commit()

user_queues = {}
user_state = {}

def get_sub_link():
    cursor.execute("SELECT value FROM config WHERE key='sub_link'")
    row = cursor.fetchone()
    return row[0] if row else None

def set_sub_link(val):
    cursor.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('sub_link', ?)", (val,))
    conn.commit()

async def send_animated_text(message: types.Message, text, reply_markup=None):
    words = text.split(" ")
    current_text = ""
    msg = None
    
    for i in range(0, len(words), 2):
        chunk = " ".join(words[i:i+2])
        if current_text:
            current_text += " " + chunk
        else:
            current_text = chunk
            
        if msg is None:
            msg = await bot.send_message(
                chat_id=message.chat.id, 
                text=current_text, 
                reply_markup=reply_markup,
                reply_to_message_id=message.message_id
            )
        else:
            try:
                await msg.edit_text(current_text, reply_markup=reply_markup)
            except:
                pass
        await asyncio.sleep(0.3)
    return msg

async def check_sub(user_id):
    link = get_sub_link()
    if not link:
        return True
    try:
        chat_member = await bot.get_chat_member(chat_id=link, user_id=user_id)
        if chat_member.status in ["member", "administrator", "creator"]:
            return True
    except:
        pass
    return False

def format_sub_url(link):
    if not link:
        return f"tg://user?id={ADMIN_ID}"
    if link.startswith("@"):
        return f"https://t.me/{link[1:]}"
    if link.startswith("-100"):
        return f"https://t.me/c/{link[4:]}/1"
    if link.startswith("http"):
        return link
    return f"https://t.me/{link}"

def extract_url(text):
    pattern = r'(https?://[^\s]+)'
    match = re.search(pattern, text)
    return match.group(0) if match else None

async def handle_reactions(message, bot_msg=None):
    await asyncio.sleep(3)
    reactions = ["🥰", "😡", "😭", "🤣"]
    r1 = random.choice(reactions)
    r2 = random.choice([r for r in reactions if r != r1])
    try:
        await message.react([types.ReactionTypeEmoji(emoji=r1)])
    except:
        pass
    if bot_msg:
        try:
            await bot_msg.react([types.ReactionTypeEmoji(emoji=r2)])
        except:
            pass

async def process_tg_link(url, message):
    try:
        await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_DOCUMENT)
        msg_text = "عيرك ثكيل هواي وكسي مايكدر \nيشيله مولاي"
        msg1 = await bot.send_message(chat_id=message.chat.id, text=msg_text, reply_to_message_id=message.message_id)
        msg2 = await bot.send_message(chat_id=message.chat.id, text="🐈‍⬛", reply_to_message_id=message.message_id)
        asyncio.create_task(handle_reactions(message, msg1))
    except:
        pass

async def download_and_send(user_id, url, message):
    if "t.me/" in url or "telegram.me/" in url:
        await process_tg_link(url, message)
        return

    try:
        await message.react([types.ReactionTypeEmoji(emoji="🍌")])
    except:
        pass

    status_msg = await bot.send_message(user_id, "دانفذ طلبك عزيزي انتظر بليز", reply_to_message_id=message.message_id)
    await bot.send_chat_action(chat_id=user_id, action=ChatAction.UPLOAD_VIDEO)
    
    last_update_time = 0
    def ytdl_hook(d):
        nonlocal last_update_time
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded = d.get('downloaded_bytes', 0)
            if total > 0:
                percent = int(downloaded / total * 100)
                import time
                now = time.time()
                if now - last_update_time > 2.0 or percent == 100:
                    last_update_time = now
                    asyncio.create_task(status_msg.edit_text(f"ترن ترن {percent}%"))

    ydl_opts = {
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'progress_hooks': [ytdl_hook],
        'quiet': True,
    }

    loop = asyncio.get_event_loop()
    try:
        import yt_dlp
        info = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=True))
        filename = yt_dlp.YoutubeDL(ydl_opts).prepare_filename(info)
        
        try:
            await status_msg.delete()
        except:
            pass
            
        video_file = FSInputFile(filename)
        v_msg = await bot.send_video(
            chat_id=user_id, 
            video=video_file, 
            caption="طلبك تنفذ بدون مشاكل يبعدكسي\nاوف بستك",
            reply_to_message_id=message.message_id
        )
        m_msg = await bot.send_message(user_id, "🫦", reply_to_message_id=message.message_id)
        asyncio.create_task(handle_reactions(message, v_msg))
        
        if os.path.exists(filename):
            os.remove(filename)
            
    except Exception as e:
        try:
            f_msg = await status_msg.edit_text("فشل تحميل الرابط، تأكد منه مجدداً مّولاي ❌")
            asyncio.create_task(handle_reactions(message, f_msg))
        except:
            pass

async def worker(user_id):
    while user_queues.get(user_id) and len(user_queues[user_id]) > 0:
        url, msg = user_queues[user_id][0]
        try:
            await asyncio.wait_for(download_and_send(user_id, url, msg), timeout=360.0)
        except asyncio.TimeoutError:
            t_msg = await bot.send_message(user_id, "انتهى مؤقت انتظار اكتمال العملية\nوتعتبر فاشلة", reply_to_message_id=msg.message_id)
            await bot.send_message(user_id, "🍌", reply_to_message_id=msg.message_id)
            asyncio.create_task(handle_reactions(msg, t_msg))
        finally:
            if user_id in user_queues and len(user_queues[user_id]) > 0:
                user_queues[user_id].pop(0)

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    if message.forward_date:
        return
        
    user_id = message.from_user.id
    if not await check_sub(user_id):
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="اشترك بالقناة", url=format_sub_url(get_sub_link()), style="success"))
        s_msg = await bot.send_message(chat_id=message.chat.id, text="يفرض على الكل الاشتراك بالقناة\nليعمل البوت", reply_markup=kb.as_markup(), reply_to_message_id=message.message_id)
        asyncio.create_task(handle_reactions(message, s_msg))
        return

    state = user_state.get(user_id, 0)
    if state == 0:
        b_msg = await send_animated_text(message, "اهلين دز رابط الميديا التريدها عزيزي\nاوف يلا")
        await bot.send_message(user_id, "🏀", reply_to_message_id=message.message_id)
        user_state[user_id] = 1
        asyncio.create_task(handle_reactions(message, b_msg))
    else:
        b_msg = await send_animated_text(message, "مو ناوي تستعملني مثل البوتات ؟!\nترى اضوج منك")
        await bot.send_message(user_id, "🐈‍⬛", reply_to_message_id=message.message_id)
        user_state[user_id] = 0
        asyncio.create_task(handle_reactions(message, b_msg))

@dp.message()
async def handle_all_messages(message: types.Message):
    if message.forward_date:
        return

    user_id = message.from_user.id
    text = message.text or ""

    if user_id == ADMIN_ID and text == "ادت":
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="تعيين رابط", callback_data="set_link_btn", style="danger"))
        a_msg = await send_animated_text(message, "عين رابط الاشتراك الفرضي", reply_markup=kb.as_markup())
        asyncio.create_task(handle_reactions(message, a_msg))
        return

    if user_id == ADMIN_ID and user_state.get(f"waiting_link_{user_id}"):
        user_state.pop(f"waiting_link_{user_id}")
        if not (text.startswith("@") or text.startswith("-100") or text.startswith("http") or text.isdigit()):
            m1 = await send_animated_text(message, "اهو ليش تمضرط وياي مو راح اضوج\nلاتعيدها مولاي")
            await bot.send_message(chat_id=message.chat.id, text="💕", reply_to_message_id=message.message_id)
            asyncio.create_task(handle_reactions(message, m1))
            return
        
        set_sub_link(text)
        m2 = await send_animated_text(message, "تم تعيين رابط زر الاشتراك الفرضي\nصار مولاي")
        await bot.send_message(chat_id=message.chat.id, text="🌷", reply_to_message_id=message.message_id)
        asyncio.create_task(handle_reactions(message, m2))
        return

    url = extract_url(text)
    if not url:
        if not await check_sub(user_id):
            kb = InlineKeyboardBuilder()
            kb.row(InlineKeyboardButton(text="اشترك بالقناة", url=format_sub_url(get_sub_link()), style="success"))
            s_msg = await bot.send_message(chat_id=message.chat.id, text="يفرض على الكل الاشتراك بالقناة\nليعمل البوت", reply_markup=kb.as_markup(), reply_to_message_id=message.message_id)
            asyncio.create_task(handle_reactions(message, s_msg))
            return
            
        state = user_state.get(user_id, 0)
        if state == 0:
            kb = InlineKeyboardBuilder()
            kb.row(InlineKeyboardButton(text="تواصل مع المطور", url=f"tg://user?id={ADMIN_ID}", style="primary"))
            b_msg = await send_animated_text(message, "اهلين دز رابط الميديا التريدها عزيزي\nاوف يلا", reply_markup=kb.as_markup())
            await bot.send_message(user_id, "🏀", reply_to_message_id=message.message_id)
            user_state[user_id] = 1
            asyncio.create_task(handle_reactions(message, b_msg))
        else:
            kb = InlineKeyboardBuilder()
            kb.row(InlineKeyboardButton(text="تواصل مع المطور", url=f"tg://user?id={ADMIN_ID}", style="primary"))
            b_msg = await send_animated_text(message, "مو ناوي تستعملني مثل البوتات ؟!\nترى اضوج منك", reply_markup=kb.as_markup())
            await bot.send_message(user_id, "🐈‍⬛", reply_to_message_id=message.message_id)
            user_state[user_id] = 0
            asyncio.create_task(handle_reactions(message, b_msg))
        return

    if not await check_sub(user_id):
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="اشترك بالقناة", url=format_sub_url(get_sub_link()), style="success"))
        s_msg = await bot.send_message(chat_id=message.chat.id, text="يفرض على الكل الاشتراك بالقناة\nليعمل البوت", reply_markup=kb.as_markup(), reply_to_message_id=message.message_id)
        asyncio.create_task(handle_reactions(message, s_msg))
        return

    if user_id not in user_queues:
        user_queues[user_id] = []

    if len(user_queues[user_id]) >= 8:
        return

    user_queues[user_id].append((url, message))

    if len(user_queues[user_id]) == 1:
        asyncio.create_task(worker(user_id))

@dp.callback_query()
async def handle_callbacks(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id != ADMIN_ID:
        return

    if callback.data == "set_link_btn":
        user_state[f"waiting_link_{user_id}"] = True
        w_msg = await send_animated_text(callback.message, "ارسل يوزر / رابط / ايدي\nالقناة او الكروب")
        asyncio.create_task(handle_reactions(callback.message, w_msg))
        await callback.answer()

async def main():
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    await bot.send_message(chat_id=ADMIN_ID, text="البوت اشتغل مولاي")
    await bot.send_message(chat_id=ADMIN_ID, text="🧨")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
