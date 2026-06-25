import os
import re
import asyncio
import collections
from pyrogram import Client, filters
from pyrogram.enums import ChatAction
import yt_dlp

try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except ImportError:
    pass

TOKEN = "8500103986:AAGps22KpNo_xx4Il3tNJ6sEPDyKtKaK0Wg"
DEVELOPER_ID = 8597653867

app = Client("media_bot", bot_token=TOKEN)

user_queues = collections.defaultdict(list)
user_processing = collections.defaultdict(bool)
user_msg_counter = collections.defaultdict(lambda: 0)
last_reported_percent = collections.defaultdict(lambda: -10)

class DownloadProgressLogger:
    def __init__(self, user_id, chat_id, message_id):
        self.user_id = user_id
        self.chat_id = chat_id
        self.message_id = message_id

    def hook(self, d):
        if d.get('status') == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            if total > 0:
                percent = int((downloaded / total) * 100)
                if percent >= last_reported_percent[self.user_id] + 10 or percent == 100:
                    last_reported_percent[self.user_id] = percent
                    loop = asyncio.get_event_loop()
                    if percent < 100:
                        text_update = f"تم استلام الرابط والبدأ بتنزيل الميديا\nمولاي {percent}%"
                        loop.create_task(self._safe_edit(text_update))
                    else:
                        loop.create_task(self._safe_delete())

    async def _safe_edit(self, text):
        try:
            await app.edit_message_text(chat_id=self.chat_id, message_id=self.message_id, text=text)
        except:
            pass

    async def _safe_delete(self):
        try:
            await app.delete_message(chat_id=self.chat_id, message_id=self.message_id)
        except:
            pass

def filter_title(text):
    if not text:
        return "Unknown"
    cleaned = re.sub(r'[\#\*\?\\/\|:\<\>"\']', '', text)
    cleaned = re.sub(r'[̀-ͯ҃-҉᷀-᷿⃐-⃿︠-︯]', '', cleaned)
    return cleaned.strip()

def get_developer_keyboard():
    return [
        [
            {
                "text": "تواصل مع المطور",
                "url": f"tg://user?id={DEVELOPER_ID}"
            }
        ]
    ]

def extract_media_info(url):
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'skip_download': True,
        'quiet': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)

def download_media_sync(url, logger_instance):
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'quiet': True,
        'progress_hooks': [logger_instance.hook],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=True)

async def send_processed_files(chat_id, reply_msg_id, files):
    for chunk_idx in range(0, len(files), 8):
        group = files[chunk_idx:chunk_idx+8]
        if len(group) > 1:
            await app.send_media_group(chat_id=chat_id, media=group, reply_to_message_id=reply_msg_id)
        else:
            await app.send_document(chat_id=chat_id, document=group[0], reply_to_message_id=reply_msg_id)

async def process_queue(user_id, chat_id):
    if user_processing[user_id] or not user_queues[user_id]:
        return

    user_processing[user_id] = True
    url, reply_msg_id = user_queues[user_id].pop(0)

    try:
        info = await asyncio.to_thread(extract_media_info, url)
        filesize = info.get('filesize') or info.get('filesize_approx') or 0
        if filesize > 456 * 1024 * 1024:
            raise Exception
    except:
        await app.send_message(chat_id=chat_id, text="الرابط مو مدعوم او الموقع مو\nمدعوم", reply_to_message_id=reply_msg_id)
        await app.send_message(chat_id=chat_id, text="👈🏻👉🏻")
        user_processing[user_id] = False
        if user_queues[user_id]:
            asyncio.create_task(process_queue(user_id, chat_id))
        return

    await app.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    status_msg = await app.send_message(chat_id=chat_id, text="تم استلام الرابط والبدأ بتنزيل الميديا\nمولاي 0%", reply_to_message_id=reply_msg_id)
    await app.send_message(chat_id=chat_id, text="⏳")

    last_reported_percent[user_id] = -10
    os.makedirs('downloads', exist_ok=True)
    
    logger_instance = DownloadProgressLogger(user_id, chat_id, status_msg.id)

    try:
        downloaded_info = await asyncio.to_thread(download_media_sync, url, logger_instance)
        
        try:
            await app.delete_message(chat_id=chat_id, message_ids=status_msg.id)
        except:
            pass

        entries = downloaded_info.get('entries', [downloaded_info])
        clean_files = []
        uploader_name = filter_title(downloaded_info.get('uploader') or downloaded_info.get('uploader_id') or 'Channel')
        
        with yt_dlp.YoutubeDL({'outtmpl': 'downloads/%(id)s.%(ext)s'}) as ydl_temp:
            for entry in entries:
                if not entry:
                    continue
                
                try:
                    filename_expected = ydl_temp.prepare_filename(entry)
                    media_id = os.path.splitext(os.path.basename(filename_expected))[0]
                except:
                    media_id = entry.get('id', 'UnknownID')
                
                matched_file = None
                for p in os.listdir('downloads'):
                    if p.startswith(media_id):
                        matched_file = os.path.join('downloads', p)
                        break
                
                if matched_file and os.path.exists(matched_file):
                    ext = os.path.splitext(matched_file)[1]
                    new_path = f"downloads/{uploader_name}_{media_id}{ext}"
                    os.rename(matched_file, new_path)
                    clean_files.append(new_path)

        if clean_files:
            await app.send_message(chat_id=chat_id, text="العملية صارت بدون مشاكل\nتفضل مولاي", reply_to_message_id=reply_msg_id)
            await app.send_message(chat_id=chat_id, text="🍓")
            await send_processed_files(chat_id, reply_msg_id, clean_files)
        else:
            raise Exception
            
    except:
        await app.send_message(chat_id=chat_id, text="الرابط مو مدعوم او الموقع مو\nمدعوم", reply_to_message_id=reply_msg_id)
        await app.send_message(chat_id=chat_id, text="👈🏻👉🏻")
    finally:
        if os.path.exists('downloads'):
            for f in os.listdir('downloads'):
                try:
                    os.remove(os.path.join('downloads', f))
                except:
                    pass
        user_processing[user_id] = False
        if user_queues[user_id]:
            asyncio.create_task(process_queue(user_id, chat_id))

@app.on_message(filters.all)
async def message_handler(client, message):
    user_id = message.from_user.id if message.from_user else message.chat.id
    chat_id = message.chat.id
    text = message.text or message.caption or ""
    url_match = re.search(r'https?://[^\s]+', text)

    if url_match:
        if len(user_queues[user_id]) < 8:
            user_queues[user_id].append((url_match.group(0), message.id))
            if not user_processing[user_id]:
                asyncio.create_task(process_queue(user_id, chat_id))
    else:
        user_msg_counter[user_id] += 1
        count = user_msg_counter[user_id]

        reply_text = "اهلين دز رابط الميديا التريدها عزيزي\nيلا اوف" if count % 2 != 0 else "مو ناوي تستعملني مثل البوتات لو شنو\nترى اضوج"
        emoji_text = "🫦" if count % 2 != 0 else "😡"

        await app.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        await app.send_message(chat_id=chat_id, text=reply_text, reply_to_message_id=message.id)
        await app.send_message(chat_id=chat_id, text=emoji_text)

if __name__ == '__main__':
    app.run()
