import os
import asyncio
import re
import sqlite3
import random
import time
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, FSInputFile, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
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

def is_emoji_message(msg):
    if not msg:
        return False
    text = msg.text or ""
    clean_text = text.strip()
    if not clean_text:
        return False
    if len(clean_text) > 4:
        return False
    emoji_pattern = re.compile(r'^[\U00010000-\U0010ffff\u200d\u2600-\u27bf]+$')
    return bool(emoji_pattern.match(clean_text))

async def send_animated_text(message: types.Message, text, reply_markup=None):
    words = text.split(" ")
    if not words:
        return None
        
    current_text = words[0]
    msg = await bot.send_message(
        chat_id=message.chat.id, 
        text=current_text, 
        reply_to_message_id=message.message_id
    )
    await asyncio.sleep(0.3)
    
    idx = 1
    alternate = True
    
    while idx < len(words):
        if alternate:
            chunk_words = words[idx:idx+2]
            idx += 2
        else:
            chunk_words = words[idx:idx+1]
            idx += 1
            
        if chunk_words:
            chunk = " ".join(chunk_words)
            current_text += " " + chunk
            try:
                await msg.edit_text(current_text)
            except:
                pass
            await asyncio.sleep(0.3)
            
        alternate = not alternate
        
    if reply_markup and isinstance(reply_markup, InlineKeyboardBuilder):
        reply_markup = reply_markup.as_markup()
        
    try:
        await msg.edit_text(text, reply_markup=reply_markup)
    except:
        pass
        
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
    if link.startswith("http") or link.startswith("t.me"):
        if link.startswith("t.me"):
            return f"https://{link}"
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
    
    if message and not is_emoji_message(message):
        try:
            await message.react([types.ReactionTypeEmoji(emoji=r1)])
        except:
            pass
            
    if bot_msg and bot_msg.video:
        try:
            await bot_msg.react([types.ReactionTypeEmoji(emoji=r2)])
        except:
            pass
    elif bot_msg and not is_emoji_message(bot_msg):
        try:
            await bot_msg.react([types.ReactionTypeEmoji(emoji=r2)])
        except:
            pass

async def delayed_banana_reaction(message):
    await asyncio.sleep(1)
    if message and not is_emoji_message(message):
        try:
            await message.react([types.ReactionTypeEmoji(emoji="🍌")])
        except:
            pass

async def progress_updater(user_id, message_id, queue):
    last_reported = -1
    while True:
        try:
            percent = await asyncio.wait_for(queue.get(), timeout=1.0)
            if percent == -1:
                break
            if percent != last_reported:
                last_reported = percent
                try:
                    await bot.edit_message_text(
                        chat_id=user_id,
                        message_id=message_id,
                        text=f"دانفذ طلبك عزيزي انتظر بليز\nترن ترن {percent}%"
                    )
                except:
                    pass
            queue.task_done()
        except asyncio.TimeoutError:
            continue
        except:
            break

async def download_and_send(user_id, url, message):
    asyncio.create_task(delayed_banana_reaction(message))

    status_msg = await send_animated_text(message, "دانفذ طلبك عزيزي انتظر بليز\nترن ترن 0%")
    await bot.send_message(chat_id=user_id, text="🍔")
    await bot.send_chat_action(chat_id=user_id, action=ChatAction.UPLOAD_VIDEO)
    
    progress_queue = asyncio.Queue()
    update_task = asyncio.create_task(progress_updater(user_id, status_msg.message_id, progress_queue))
    
    last_reported_milestone = 0
    loop = asyncio.get_event_loop()
    
    def ytdl_hook(d):
        nonlocal last_reported_milestone
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded = d.get('downloaded_bytes', 0)
            if total > 0:
                percent = int(downloaded / total * 100)
                if percent - last_reported_milestone >= 25 or percent == 100 or (last_reported_milestone == 0 and percent >= 25):
                    last_reported_milestone = (percent // 25) * 25
                    if percent == 100:
                        last_reported_milestone = 100
                    loop.call_soon_threadsafe(progress_queue.put_nowait, last_reported_milestone)

    ydl_opts = {
        'outtmpl': 'downloads/%%(id)s.%%(ext)s',
        'progress_hooks': [ytdl_hook],
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'extractor_args': {
            'youtube': {'player_client': ['android', 'web']},
            'tiktok': {'app_version': ['all']}
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9,ar;q=0.8',
            'Sec-Ch-Ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1'
        }
    }

    try:
        import yt_dlp
        ydl = yt_dlp.YoutubeDL(ydl_opts)
        info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
        
        await progress_queue.put(-1)
        await update_task
        
        if not info:
            raise Exception("Extract failed")
            
        filename = ydl.prepare_filename(info)
        
        if not os.path.exists(filename):
            basename, _ = os.path.splitext(filename)
            for ext in ['mp4', 'mkv', 'webm', '3gp', 'flv', 'avi']:
                possible_file = f"{basename}.{ext}"
                if os.path.exists(possible_file):
                    filename = possible_file
                    break

        if not os.path.exists(filename):
            raise Exception("File not found")

        try:
            await bot.delete_message(chat_id=user_id, message_id=status_msg.message_id)
        except:
            pass
            
        video_file = FSInputFile(filename)
        v_msg = await bot.send_video(
            chat_id=user_id, 
            video=video_file, 
            reply_to_message_id=message.message_id
        )
        
        await send_animated_text(message, "طلبك تنفذ بدون مشاكل يبعدكسي\nاوف بستك")
        await bot.send_message(chat_id=user_id, text="🫦")
        asyncio.create_task(handle_reactions(message, v_msg))
        
        if os.path.exists(filename):
            os.remove(filename)
            
    except Exception as e:
        await progress_queue.put(-1)
        await update_task
        
        try:
            await bot.delete_message(chat_id=user_id, message_id=status_msg.message_id)
        except:
            pass
            
        f_msg = await send_animated_text(message, "هوف الرابط مو مدعوم او الموقع مو\nمدعوم")
        await bot.send_message(chat_id=user_id, text="🐈‍⬛")
        asyncio.create_task(handle_reactions(message, f_msg))

async def worker(user_id):
    while user_queues.get(user_id) and len(user_queues[user_id]) > 0:
        url, msg = user_queues[user_id][0]
        try:
            await asyncio.wait_for(download_and_send(user_id, url, msg), timeout=360.0)
        except asyncio.TimeoutError:
            t_msg = await send_animated_text(msg, "انتهى مؤقت انتظار اكتمال العملية\nوتعتبر فاشلة")
            await bot.send_message(chat_id=user_id, text="🍌")
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
        s_msg = await send_animated_text(message, "يفرض على الكل الاشتراك بالقناة\nليعمل البوت", reply_markup=kb)
        asyncio.create_task(handle_reactions(message, s_msg))
        return

    state = user_state.get(user_id, 0)
    if state == 0:
        b_msg = await send_animated_text(message, "اهلين دز رابط الميديا التريدها عزيزي\nاوف يلا")
        await bot.send_message(chat_id=user_id, text="🏀")
        user_state[user_id] = 1
        asyncio.create_task(handle_reactions(message, b_msg))
    else:
        b_msg = await send_animated_text(message, "مو ناوي تستعملني مثل البوتات ؟!\nترى اضوج منك")
        await bot.send_message(chat_id=user_id, text="🐈‍⬛")
        user_state[user_id] = 0
        asyncio.create_task(handle_reactions(message, b_msg))

@dp.message()
async def handle_all_messages(message: types.Message):
    if message.forward_date:
        return

    user_id = message.from_user.id
    text = message.text or ""

    if user_id == ADMIN_ID and text == "ادت":
        await send_animated_text(message, "اضغط على زر تعيين رابط بالأسفل\nءمهمواح دادي")
        kb = ReplyKeyboardBuilder()
        kb.add(KeyboardButton(text="تعيين رابط"))
        reply_markup = ReplyKeyboardMarkup(keyboard=kb.export(), resize_keyboard=True, one_time_keyboard=True)
        await bot.send_message(chat_id=message.chat.id, text="لوحة التحكم:", reply_markup=reply_markup)
        return

    if user_id == ADMIN_ID and text == "تعيين رابط":
        user_state[f"waiting_link_{user_id}"] = True
        w_msg = await bot.send_message(chat_id=message.chat.id, text="ارسل يوزر / رابط القناة او الكروب\nيلا مولاي", reply_markup=ReplyKeyboardRemove())
        return

    if user_id == ADMIN_ID and user_state.get(f"waiting_link_{user_id}"):
        user_state.pop(f"waiting_link_{user_id}")
        
        check_text = text.lower()
        is_url = check_text.startswith("https://") or check_text.startswith("http://") or check_text.startswith("t.me")
        is_user = check_text.startswith("@")
        
        if not (is_url or is_user):
            m1 = await send_animated_text(message, "اهو ليش تمضرط وياي مو راح اضوج\nلاتعيدها مولاي")
            await bot.send_message(chat_id=message.chat.id, text="💕")
            asyncio.create_task(handle_reactions(message, m1))
            return
            
        target_chat = text
        if text.startswith("t.me/"):
            target_chat = "@" + text.split("t.me/")[1]
            
        try:
            await bot.get_chat(target_chat)
        except:
            msg_type = "الرابط" if is_url else "اليوزر"
            err_msg = await send_animated_text(
                message=message,
                text=f"هذا {msg_type} مو شغال وعاطل ماله اثر دادي\nههع ابوس زبك"
            )
            await bot.send_message(chat_id=message.chat.id, text="🍔")
            asyncio.create_task(handle_reactions(message, err_msg))
            return
        
        set_sub_link(text)
        
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="اشترك بالقناة", url=format_sub_url(text), style="success"))
        
        m2 = await send_animated_text(message, "تم تعيين زر الاشتراك الفرضي\nصار مولاي", reply_markup=kb)
        await bot.send_message(chat_id=message.chat.id, text="🌷")
        asyncio.create_task(handle_reactions(message, m2))
        return

    url = extract_url(text)
    if not url:
        if not await check_sub(user_id):
            kb = InlineKeyboardBuilder()
            kb.row(InlineKeyboardButton(text="اشترك بالقناة", url=format_sub_url(get_sub_link()), style="success"))
            s_msg = await send_animated_text(message, "يفرض على الكل الاشتراك بالقناة\nليعمل البوت", reply_markup=kb)
            asyncio.create_task(handle_reactions(message, s_msg))
            return
            
        state = user_state.get(user_id, 0)
        if state == 0:
            kb = InlineKeyboardBuilder()
            kb.row(InlineKeyboardButton(text="تواصل مع المطور", url=f"tg://user?id={ADMIN_ID}", style="primary"))
            b_msg = await send_animated_text(message, "اهلين دز رابط الميديا التريدها عزيزي\nاوف يلا", reply_markup=kb)
            await bot.send_message(chat_id=user_id, text="🏀")
            user_state[user_id] = 1
            asyncio.create_task(handle_reactions(message, b_msg))
        else:
            kb = InlineKeyboardBuilder()
            kb.row(InlineKeyboardButton(text="تواصل مع المطور", url=f"tg://user?id={ADMIN_ID}", style="primary"))
            b_msg = await send_animated_text(message, "مو ناوي تستعملني مثل البوتات ؟!\nترى اضوج منك", reply_markup=kb)
            await bot.send_message(chat_id=user_id, text="🐈‍⬛")
            user_state[user_id] = 0
            asyncio.create_task(handle_reactions(message, b_msg))
        return

    if not await check_sub(user_id):
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="اشترك بالقناة", url=format_sub_url(get_sub_link()), style="success"))
        s_msg = await send_animated_text(message, "يفرض على الكل الاشتراك بالقناة\nليعمل البوت", reply_markup=kb)
        asyncio.create_task(handle_reactions(message, s_msg))
        return

    if user_id not in user_queues:
        user_queues[user_id] = []

    if len(user_queues[user_id]) >= 8:
        return

    user_queues[user_id].append((url, message))

    if len(user_queues[user_id]) == 1:
        asyncio.create_task(worker(user_id))

async def main():
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    await bot.send_message(chat_id=ADMIN_ID, text="اشتغل البوت مرتلخ تاج راسي\nارضع عيرك ؟!")
    await bot.send_message(chat_id=ADMIN_ID, text="🧨")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
