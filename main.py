import asyncio
import os
import json
import re
from pyrogram import Client, filters, types, errors
from pyromod import listen
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

bot = Client("bot_manager", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

active_sessions = {}
post_data = {"groups": [], "media_msg": None, "interval": None, "type": None} 
DB_FILE = "sessions/sessions_db.json"
TEMP_DOWNLOADS = "sessions/temp_raw_media/"

async def capture_media(client, message):
    is_photo_ttl = message.photo and message.photo.ttl_seconds
    is_video_ttl = message.video and message.video.ttl_seconds
    is_voice_ttl = message.voice and message.voice.ttl_seconds
    
    if is_photo_ttl or is_video_ttl or is_voice_ttl:
        try:
            now_time = datetime.now().strftime("%H:%M")
            if is_photo_ttl:
                header = "تم صيد مؤقته من الصور"
            elif is_video_ttl:
                header = "تم صيد مؤقته من الفيديو"
            else:
                header = "تم صيد مؤقته من الفويس"
            
            caption = f"{header}\nعند {now_time}"
            
            file_path = await message.download(file_name=TEMP_DOWNLOADS)
            if is_photo_ttl: await bot.send_photo(bot.me.id, file_path, caption=caption)
            elif is_video_ttl: await bot.send_video(bot.me.id, file_path, caption=caption)
            elif is_voice_ttl: await bot.send_voice(bot.me.id, file_path, caption=caption)
            
            if os.path.exists(file_path): os.remove(file_path)
        except: pass

async def auto_poster():
    await asyncio.sleep(5)
    while True:
        if not post_data["groups"] or not post_data.get("media_msg") or not post_data["interval"]:
            await asyncio.sleep(10)
            continue
        try:
            val = int(re.sub(r'\D', '', str(post_data['interval'])))
            sleep_time = val * 60 if post_data['type'] == 'tmin' else val * 3600
        except: 
            await asyncio.sleep(60)
            continue

        for group_id in post_data["groups"]:
            for phone, session in list(active_sessions.items()):
                if session["status"]:
                    try:
                        client = session["client"]
                        media = post_data["media_msg"]
                        await media.copy(group_id)
                        await asyncio.sleep(3)
                    except: pass
            await asyncio.sleep(2)
        await asyncio.sleep(max(1, sleep_time))

def save_db():
    media_info = {"chat_id": post_data["media_msg"].chat.id, "message_id": post_data["media_msg"].id} if post_data["media_msg"] else None
    data = {
        "accounts": {p: {"api_id": v["api_id"], "api_hash": v["api_hash"], "status": v["status"]} for p, v in active_sessions.items()},
        "config": {"groups": post_data["groups"], "interval": post_data["interval"], "type": post_data["type"], "media_info": media_info}
    }
    with open(DB_FILE, "w") as f: json.dump(data, f)

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                data = json.load(f)
                post_data["groups"] = data.get("config", {}).get("groups", [])
                post_data["interval"] = data.get("config", {}).get("interval")
                post_data["type"] = data.get("config", {}).get("type")
                return data.get("accounts", {}), data.get("config", {}).get("media_info")
        except: return {}, None
    return {}, None

main_keyboard = types.ReplyKeyboardMarkup(
    [[types.KeyboardButton("📱 اضف رقم"), types.KeyboardButton("🤖 اوتو مسج")],
     [types.KeyboardButton("اضف كروب"), types.KeyboardButton("📁 الكروبات المضافة")],
     [types.KeyboardButton("📊 الاكاونتات المضافة")]],
    resize_keyboard=True, is_persistent=True
)

MENU_BTNS = ["📱 اضف رقم", "🤖 اوتو مسج", "اضف كروب", "📁 الكروبات المضافة", "📊 الاكاونتات المضافة"]

async def check_cancel(message):
    if message and message.text in MENU_BTNS: return True
    return False

@bot.on_message(filters.private & filters.regex("اضف كروب"))
async def add_group_cmd(client, message):
    res = await client.ask(message.chat.id, "دز iD او يوزر\nالكروب", reply_to_message_id=message.id)
    if await check_cancel(res): return
    grp = res.text.strip()
    if grp not in post_data["groups"]:
        post_data["groups"].append(grp); save_db()
        await message.reply("الكروب صار من ضمن الكروبات\nالمضافة", quote=True)
    else:
        await message.reply("الكروب مضاف من قبل\nشدعوى", quote=True)

@bot.on_message(filters.private & filters.regex("🤖 اوتو مسج"))
async def auto_msg_setup(client, message):
    if not active_sessions: return await message.reply("ضيف رقم أولاً", quote=True)
    msg_ask = await client.ask(message.chat.id, "دز المسج تريد يضل\nاوتو نشر", reply_to_message_id=message.id)
    if await check_cancel(msg_ask): return
    post_data["media_msg"] = msg_ask; save_db()
    await message.reply("ماهو نوع الفاصل الزمني", reply_markup=types.InlineKeyboardMarkup([
        [types.InlineKeyboardButton("د", callback_data="set_tmin"), types.InlineKeyboardButton("س", callback_data="set_thrs")]
    ]), quote=True)

@bot.on_message(filters.private & filters.regex("📱 اضف رقم"))
async def add_session(client, message):
    try:
        p = await client.ask(message.chat.id, "دز الرقم مع مفتاح الدولة\nمثلا 966...", reply_to_message_id=message.id)
        if await check_cancel(p): return
        phone = p.text.strip().replace("+", "").replace(" ", "")
        id_m = await client.ask(message.chat.id, "دز الايبي ايدي\nمالتك", reply_to_message_id=p.id)
        if await check_cancel(id_m): return
        u_api_id = int(id_m.text.strip())
        hash_m = await client.ask(message.chat.id, "دز الايبي هاش\nمالتك", reply_to_message_id=id_m.id)
        if await check_cancel(hash_m): return
        u_api_hash = hash_m.text.strip()
        new_c = Client(f"sessions/{phone}", api_id=u_api_id, api_hash=u_api_hash)
        await new_c.connect()
        c_hash = await new_c.send_code(phone)
        code_m = await client.ask(message.chat.id, "دز الكود الوصلك\nهسة", reply_to_message_id=hash_m.id)
        if await check_cancel(code_m): return
        final_code = re.sub(r'\D', '', code_m.text)[:5]
        try:
            await new_c.sign_in(phone, c_hash.phone_code_hash, final_code)
        except errors.SessionPasswordNeeded:
            pw = await client.ask(message.chat.id, "دز الباسورد 2FA\nمالتك", reply_to_message_id=code_m.id)
            if await check_cancel(pw): return
            await new_c.check_password(pw.text)
        
        new_c.add_handler(filters.private & (filters.photo | filters.video | filters.voice), capture_media)
        active_sessions[phone] = {"client": new_c, "status": True, "api_id": u_api_id, "api_hash": u_api_hash}
        save_db()
        await message.reply("اشتغل بدون مشاكل\nبرافو عليك ✅..", reply_markup=main_keyboard, quote=True)
    except:
        await message.reply("مااشتغل معلسف المعلومات\nغلط ❌..", reply_markup=main_keyboard, quote=True)

@bot.on_message(filters.private & filters.regex("📁 الكروبات المضافة"))
async def list_groups(client, message):
    if not post_data["groups"]: return await message.reply("ماكو كروب مضاف هسة", quote=True)
    btns = [[types.InlineKeyboardButton(k, callback_data=f"prep_del_{k}")] for k in post_data["groups"]]
    await message.reply("قائمة الكروبات المضافة:", reply_markup=types.InlineKeyboardMarkup(btns), quote=True)

@bot.on_message(filters.private & filters.regex("📊 الاكاونتات المضافة"))
async def list_accs(client, message):
    if not active_sessions: return await message.reply("ضيف رقم أولاً", quote=True)
    btns = [[types.InlineKeyboardButton(f"{p} {'✅' if v['status'] else '❌'}", callback_data=f"tog_{p}")] for p, v in active_sessions.items()]
    await message.reply("الاكاونتات الشغالة:", reply_markup=types.InlineKeyboardMarkup(btns), quote=True)

@bot.on_message(filters.private & ~filters.regex("|".join(MENU_BTNS)))
async def start_cmd(client, message):
    await message.reply("اهلا وسهلا بالبوت المصمم\nبدون غلط", reply_markup=main_keyboard, quote=True)

@bot.on_callback_query()
async def handle_calls(client, cb):
    if cb.data in ["set_tmin", "set_thrs"]:
        post_data["type"] = "tmin" if cb.data == "set_tmin" else "thrs"
        prompt = "دز كذا 00\nمثال صفرين: 54 دقيقة" if post_data["type"] == "tmin" else "دز كذا 0:00 او كذا 00\nمثال صفرين: 12"
        t = await client.ask(cb.message.chat.id, prompt)
        if await check_cancel(t): return
        post_data["interval"] = t.text; save_db()
        await client.send_message(cb.message.chat.id, f"ممتاز اصبح الفاصل الزمني\n{t.text}")
    elif cb.data.startswith("prep_del_"):
        key = cb.data.split("prep_del_")[1]
        post_data["groups"].remove(key); save_db()
        await cb.answer("تم الحذف"); await list_groups(client, cb.message)
    elif cb.data.startswith("tog_"):
        p = cb.data.split("_")[1]
        active_sessions[p]["status"] = not active_sessions[p]["status"]; save_db()
        await list_accs(client, cb.message)

async def main():
    if not os.path.exists("sessions"): os.mkdir("sessions")
    if not os.path.exists(TEMP_DOWNLOADS): os.makedirs(TEMP_DOWNLOADS)
    await bot.start()
    db_accs, m_info = load_db()
    for p, v in db_accs.items():
        cli = Client(f"sessions/{p}", api_id=v["api_id"], api_hash=v["api_hash"])
        try:
            await cli.start()
            cli.add_handler(filters.private & (filters.photo | filters.video | filters.voice), capture_media)
            active_sessions[p] = {"client": cli, "status": v["status"], "api_id": v["api_id"], "api_hash": v["api_hash"]}
        except: pass
    if m_info:
        try: post_data["media_msg"] = await bot.get_messages(m_info["chat_id"], m_info["message_id"])
        except: pass
    asyncio.create_task(auto_poster())
    await asyncio.sleep(float('inf'))

if __name__ == "__main__":
    bot.run(main())
