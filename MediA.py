import os
import asyncio
import re
import sqlite3
import random
import time
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, FSInputFile, ReplyKeyboardRemove, InputMediaDocument
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatAction

TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = 8597653867

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

db_lock = asyncio.Lock()

def init_db():
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
    conn.close()

init_db()

user_queues = {}
user_state = {}
last_used_reaction = None

async def get_sub_link():
    async with db_lock:
        conn = sqlite3.connect("SAve.db")
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM config WHERE key='sub_link'")
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

async def set_sub_link(val):
    async with db_lock:
        conn = sqlite3.connect("SAve.db")
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('sub_link', ?)", (val,))
        conn.commit()
        conn.close()

def is_emoji_message(msg):
    if not msg:
        return False
    text = msg.text or ""
    clean_text = text.strip()
    if not clean_text or len(clean_text) > 4:
        return False
    emoji_pattern = re.compile(r'^[\U00010000-\U0010ffff\u200d\u2600-\u27bf]+$')
    return bool(emoji_pattern.match(clean_text))

def extract_url(text):
    if not text:
        return None
    pattern = r'(https?://[^\s]+)'
    match = re.search(pattern, text)
    return match.group(0) if match else None

async def send_animated_text(message: types.Message, text: str, reply_markup=None):
    words = text.split(" ")
    current_text = ""
    msg = None
    
    for i in range(0, len(words), 2):
        chunk = " ".join(words[i:i+2])
        current_text = f"{current_text} {chunk}".strip() if current_text else chunk
            
        if msg is None:
            msg = await message.bot.send_message(
                chat_id=message.chat.id, 
                text=current_text, 
                reply_to_message_id=message.message_id
            )
        else:
            try:
                if i + 2 >= len(words):
                    await msg.edit_text(current_text, reply_markup=reply_markup)
                else:
                    await msg.edit_text(current_text)
            except:
                pass
        await asyncio.sleep(0.3)
    return msg

async def handle_reactions(message: types.Message, bot_msg: types.Message = None):
    global last_used_reaction
    if message and is_emoji_message(message):
        return
    await asyncio.sleep(3)
    
    reactions_pool = ["😡", "🥰", "🤣", "😭", "😘"]
    available_reactions = [r for r in reactions_pool if r != last_used_reaction]
    if not available_reactions:
        available_reactions = reactions_pool

    r1 = random.choice(available_reactions)
    last_used_reaction = r1
    
    remaining_reactions = [r for r in reactions_pool if r != r1]
    r2 = random.choice(remaining_reactions)
    
    if message:
        try:
            await message.react([types.ReactionTypeEmoji(emoji=r1)])
        except:
            pass
    if bot_msg:
        try:
            await bot_msg.react([types.ReactionTypeEmoji(emoji=r2)])
        except:
            pass

async def react_with_banana(message: types.Message):
    if message and is_emoji_message(message):
        return
    await asyncio.sleep(1)
    try:
        await message.react([types.ReactionTypeEmoji(emoji="🍌")])
    except:
        pass

async def check_sub(user_id):
    link = await get_sub_link()
    if not link:
        return True
    try:
        chat_member = await bot.get_chat_member(chat_id=link, user_id=user_id)
        if chat_member.status in ["member", "administrator", "creator"]:
            return True
    except:
        pass
    return False

async def format_sub_url(link):
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

async def download_and_get_files(user_id, url, message):
    status_msg = await send_animated_text(message, "دانفذ طلبك عزيزي انتظر بليز\nترن ترن 0%")
    await bot.send_message(chat_id=user_id, text="🍔")
    try:
        await bot.send_chat_action(chat_id=user_id, action=ChatAction.UPLOAD_DOCUMENT)
    except:
        pass
    
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
        'outtmpl': 'downloads/%%(id)s_%%(title)s.%%(ext)s',
        'progress_hooks': [ytdl_hook],
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'ignoreerrors': True,
        'http_headers': {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9,ar;q=0.8',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1'
        },
        'extractor_args': {
            'youtube': {'player_client': ['android', 'web']},
            'tiktok': {'app_version': ['all']}
        }
    }

    try:
        import yt_dlp
        ydl = yt_dlp.YoutubeDL(ydl_opts)
        info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
        
        await progress_queue.put(-1)
        await update_task
        
        try:
            await bot.delete_message(chat_id=user_id, message_id=status_msg.message_id)
        except:
            pass

        if not info:
            raise Exception("Extract failed")
            
        downloaded_files = []
        
        if 'entries' in info:
            for entry in info['entries']:
                if entry:
                    filename = ydl.prepare_filename(entry)
                    if os.path.exists(filename):
                        downloaded_files.append(filename)
                    else:
                        basename, _ = os.path.splitext(filename)
                        for ext in ['mp4', 'mkv', 'webm', 'png', 'jpg', 'jpeg', 'webp']:
                            possible = f"{basename}.{ext}"
                            if os.path.exists(possible):
                                downloaded_files.append(possible)
                                break
        else:
            filename = ydl.prepare_filename(info)
            if os.path.exists(filename):
                downloaded_files.append(filename)
            else:
                basename, _ = os.path.splitext(filename)
                for ext in ['mp4', 'mkv', 'webm', 'png', 'jpg', 'jpeg', 'webp']:
                    possible = f"{basename}.{ext}"
                    if os.path.exists(possible):
                        downloaded_files.append(possible)
                        break

        if not downloaded_files:
            raise Exception("No files found")
            
        return downloaded_files
            
    except Exception as e:
        await progress_queue.put(-1)
        await update_task
        try:
            await bot.delete_message(chat_id=user_id, message_id=status_msg.message_id)
        except:
            pass
            
        f_msg = await send_animated_text(message, "هوف الرابط مو مدعوم او الموقع مو\nمدعوم")
        cat_msg = await send_animated_text(message, "🐈‍⬛")
        asyncio.create_task(handle_reactions(None, f_msg))
        asyncio.create_task(handle_reactions(None, cat_msg))
        return []

async def worker(user_id):
    while user_queues.get(user_id) and len(user_queues[user_id]) > 0:
        url, msg = user_queues[user_id][0]
        
        try:
            files = await asyncio.wait_for(download_and_get_files(user_id, url, msg), timeout=360.0)
            
            if files:
                chunk_size = 8
                for i in range(0, len(files), chunk_size):
                    chunk = files[i:i + chunk_size]
                    media_group = [InputMediaDocument(media=FSInputFile(f)) for f in chunk]
                    await bot.send_media_group(chat_id=user_id, media=media_group, reply_to_message_id=msg.message_id)
                
                fin_msg = await send_animated_text(msg, "طلبك تنفذ بدون مشاكل يبعدكسي\nاوف بستك")
                await bot.send_message(chat_id=user_id, text="🫦")
                asyncio.create_task(handle_reactions(None, fin_msg))
                
                for f in files:
                    if os.path.exists(f):
                        os.remove(f)
                        
        except asyncio.TimeoutError:
            t_msg = await send_animated_text(msg, "انتهى مؤقت انتظار اكتمال العملية\nوتعتبر فاشلة")
            await bot.send_message(chat_id=user_id, text="🍌")
            asyncio.create_task(handle_reactions(None, t_msg))
        except Exception as e:
            pass
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
        sub_link = await get_sub_link()
        kb.row(InlineKeyboardButton(text="اشترك بالقناة", url=await format_sub_url(sub_link), style="success"))
        s_msg = await send_animated_text(message, "اشترك بالقناة لو ماراح يشتغل وياك البوت\nضروري عيني", reply_markup=kb.as_markup())
        await bot.send_message(chat_id=user_id, text="🍔")
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
        a_msg = await send_animated_text(message, "تريد تعين رابط الزر ارسل تعيين رابط\nتريد معاينة سريعة ارسل عرض الزر")
        await bot.send_message(chat_id=message.chat.id, text="🎮")
        asyncio.create_task(handle_reactions(message, a_msg))
        return

    if user_id == ADMIN_ID and text == "تعيين رابط":
        user_state[f"waiting_link_{user_id}"] = True
        w_msg = await send_animated_text(message, "ارسل يوزر / رابط القناة او الكروب\nيلا مولاي")
        asyncio.create_task(handle_reactions(message, w_msg))
        return

    if user_id == ADMIN_ID and text == "عرض الزر":
        kb = InlineKeyboardBuilder()
        sub_link = await get_sub_link()
        kb.row(InlineKeyboardButton(text="اشترك بالقناة", url=await format_sub_url(sub_link), style="success"))
        v_msg = await send_animated_text(message, "اشترك بالقناة لو ماراح يشتغل وياك البوت\nضروري عيني", reply_markup=kb.as_markup())
        await bot.send_message(chat_id=message.chat.id, text="🍔")
        asyncio.create_task(handle_reactions(message, v_msg))
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
        
        await set_sub_link(text)
        
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="اشترك بالقناة", url=await format_sub_url(text), style="success"))
        
        m2 = await send_animated_text(message, "تم تعيين زر الاشتراك الفرضي\nصار مولاي", reply_markup=kb.as_markup())
        await bot.send_message(chat_id=message.chat.id, text="🌷")
        asyncio.create_task(handle_reactions(message, m2))
        return

    url = extract_url(text)
    if not url:
        if not await check_sub(user_id):
            kb = InlineKeyboardBuilder()
            sub_link = await get_sub_link()
            kb.row(InlineKeyboardButton(text="اشترك بالقناة", url=await format_sub_url(sub_link), style="success"))
            s_msg = await send_animated_text(message, "اشترك بالقناة لو ماراح يشتغل وياك البوت\nضروري عيني", reply_markup=kb.as_markup())
            await bot.send_message(chat_id=user_id, text="🍔")
            asyncio.create_task(handle_reactions(message, s_msg))
            return
            
        state = user_state.get(user_id, 0)
        if state == 0:
            kb = InlineKeyboardBuilder()
            kb.row(InlineKeyboardButton(text="تواصل مع المطور", url=f"tg://user?id={ADMIN_ID}", style="primary"))
            b_msg = await send_animated_text(message, "اهلين دز رابط الميديا التريدها عزيزي\nاوف يلا", reply_markup=kb.as_markup())
            await bot.send_message(chat_id=user_id, text="🏀")
            user_state[user_id] = 1
            asyncio.create_task(handle_reactions(message, b_msg))
        else:
            kb = InlineKeyboardBuilder()
            kb.row(InlineKeyboardButton(text="تواصل مع المطور", url=f"tg://user?id={ADMIN_ID}", style="primary"))
            b_msg = await send_animated_text(message, "مو ناوي تستعملني مثل البوتات ؟!\nترى اضوج منك", reply_markup=kb.as_markup())
            await bot.send_message(chat_id=user_id, text="🐈‍⬛")
            user_state[user_id] = 0
            asyncio.create_task(handle_reactions(message, b_msg))
        return

    if not await check_sub(user_id):
        kb = InlineKeyboardBuilder()
        sub_link = await get_sub_link()
        kb.row(InlineKeyboardButton(text="اشترك بالقناة", url=await format_sub_url(sub_link), style="success"))
        s_msg = await send_animated_text(message, "اشترك بالقناة لو ماراح يشتغل وياك البوت\nضروري عيني", reply_markup=kb.as_markup())
        await bot.send_message(chat_id=user_id, text="🍔")
        asyncio.create_task(handle_reactions(message, s_msg))
        return

    asyncio.create_task(react_with_banana(message))

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
    
    try:
        init_msg = await bot.send_message(chat_id=ADMIN_ID, text="اشتغل البوت مرتلخ تاج راسي\nارضع عيرك ؟!")
        await bot.send_message(chat_id=ADMIN_ID, text="🧨")
        asyncio.create_task(handle_reactions(None, init_msg))
    except:
        pass
        
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
