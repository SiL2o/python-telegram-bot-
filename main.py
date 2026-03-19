import asyncio
import os
import json
from pyrogram import Client, filters, types, errors
from pyromod import listen
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

bot = Client("bot_manager", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

active_sessions = {}
post_data = {} 
DB_FILE = "sessions/sessions_db.json"

def save_db():
    data = {
        "accounts": {p: {"api_id": v["api_id"], "api_hash": v["api_hash"], "status": v["status"]} for p, v in active_sessions.items()},
        "groups": post_data
    }
    with open(DB_FILE, "w") as f: json.dump(data, f)

def load_db():
    global post_data
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                data = json.load(f)
                post_data = data.get("groups", {})
                return data.get("accounts", {})
        except: return {}
    return {}

main_keyboard = types.ReplyKeyboardMarkup(
    [[types.KeyboardButton("📱 اضف رقم"), types.KeyboardButton("🤖 زر اوتو مسج")],
     [types.KeyboardButton("📊 الاكاونتات المضافة"), types.KeyboardButton("🗑️ مسح كروب")]],
    resize_keyboard=True,
    is_persistent=True
)

async def start_media_catcher(user_client, phone, owner_id):
    @user_client.on_message(filters.private & ~filters.me & (filters.photo | filters.video | filters.voice))
    async def catcher(client, msg):
        if not active_sessions.get(phone, {}).get("status"): return
        is_timer = False
        if (msg.photo or msg.video) and msg.ttl_seconds: is_timer = True
        elif msg.voice: is_timer = True

        if is_timer:
            try:
                path = await msg.download()
                user = await client.get_users(msg.from_user.id)
                name = user.first_name if user.first_name else "اسم مفقود"
                if msg.voice:
                    await bot.send_voice(owner_id, path, caption=f"بصمة مؤقته من {name}")
                elif msg.photo:
                    await bot.send_photo(owner_id, path, caption=f"صورة مؤقته من {name}")
                elif msg.video:
                    await bot.send_video(owner_id, path, caption=f"فيديو مؤقت من {name}")
                if os.path.exists(path): os.remove(path)
            except: pass

@bot.on_message(filters.private & ~filters.regex("📱 اضف رقم|🤖 زر اوتو مسج|📊 الاكاونتات المضافة|🗑️ مسح كروب"))
async def start_cmd(client, message):
    await message.reply("اهلا وسهلا بالبوت المصمم\nبدون غلط", reply_markup=main_keyboard)

@bot.on_message(filters.text & filters.regex("📱 اضف رقم"))
async def add_session(client, message):
    try:
        p = await client.ask(message.chat.id, "دز الرقم مع مفتاح الدولة\nمثلا 966...")
        phone = p.text.strip().replace("+", "")
        id_m = await client.ask(message.chat.id, "دز الايبي ايدي\nمالتك")
        u_api_id = int(id_m.text)
        hash_m = await client.ask(message.chat.id, "دز الايبي هاش\nمالتك")
        u_api_hash = hash_m.text
        new_c = Client(f"sessions/{phone}", api_id=u_api_id, api_hash=u_api_hash)
        await new_c.connect()
        c_hash = await new_c.send_code(phone)
        code_m = await client.ask(message.chat.id, "دز الكود الوصلك\nهسة")
        try:
            await new_c.sign_in(phone, c_hash.phone_code_hash, code_m.text)
        except errors.SessionPasswordNeeded:
            pw = await client.ask(message.chat.id, "دز الباسورد 2FA\nمالتك")
            await new_c.check_password(pw.text)
        active_sessions[phone] = {"client": new_c, "status": True, "api_id": u_api_id, "api_hash": u_api_hash}
        save_db()
        asyncio.create_task(start_media_catcher(new_c, phone, message.chat.id))
        await message.reply("اشتغل بدون مشاكل\nبرافو عليك ✅..", reply_markup=main_keyboard)
    except:
        await message.reply("ماشتغل معلسف المعلومات\nغلط ❌..", reply_markup=main_keyboard)

@bot.on_message(filters.text & filters.regex("🤖 زر اوتو مسج"))
async def auto_msg_setup(client, message):
    grp_ask = await client.ask(message.chat.id, "اعزل كروب تريدة من ضمن\nطاقم كروباتك")
    msg_ask = await client.ask(message.chat.id, "دز مسج تريد يضل\nاوتو نشر")
    chat_id_val = grp_ask.text
    await message.reply("ماهو نوع الفاصل الزمني", reply_markup=types.InlineKeyboardMarkup([
        [types.InlineKeyboardButton("د", callback_data=f"tmin_{chat_id_val}_{msg_ask.text}"), 
         types.InlineKeyboardButton("س", callback_data=f"thrs_{chat_id_val}_{msg_ask.text}")]
    ]))

@bot.on_callback_query()
async def handle_calls(client, cb):
    if cb.data.startswith("tmin_") or cb.data.startswith("thrs_"):
        parts = cb.data.split("_")
        t_type, c_id, msg_text = parts[0], parts[1], parts[2]
        if t_type == "tmin":
            t = await client.ask(cb.message.chat.id, "دز كذا 00\nمثال صفرين: 54 دقيقة")
        else:
            t = await client.ask(cb.message.chat.id, "دز كذا 0:00 او كذا 00\nمثال صفرين: 12 مثال تلاث اصفار: 1:23")
        post_data[c_id] = {"msg": msg_text, "interval": t.text}
        save_db()
        await client.send_message(cb.message.chat.id, f"ممتاز اصبح الفاصل الزمني\n{t.text}")
    elif cb.data.startswith("tog_"):
        phone = cb.data.split("_")[1]
        active_sessions[phone]["status"] = not active_sessions[phone]["status"]
        save_db()
        btns = [[types.InlineKeyboardButton(f"{p} {'✅' if v['status'] else '❌'}", callback_data=f"tog_{p}")] for p, v in active_sessions.items()]
        btns.append([types.InlineKeyboardButton("🗑️ مسح رقم", callback_data="del_acc_start")])
        await cb.edit_message_reply_markup(types.InlineKeyboardMarkup(btns))
    elif cb.data == "del_acc_start":
        ask_p = await client.ask(cb.message.chat.id, "دز الرقم الراح\nينمسح")
        p_to_del = ask_p.text.strip().replace("+", "")
        if p_to_del in active_sessions:
            try: await active_sessions[p_to_del]["client"].stop()
            except: pass
            del active_sessions[p_to_del]
            save_db()
            await client.send_message(cb.message.chat.id, "تم مسح الرقم", reply_markup=main_keyboard)
    elif cb.data.startswith("prep_del_"):
        key = cb.data.split("_")[2]
        await cb.edit_message_reply_markup(types.InlineKeyboardMarkup([[types.InlineKeyboardButton("مسح", callback_data=f"conf_del_{key}")],[types.InlineKeyboardButton("عودة", callback_data="back_to_list")]]))
    elif cb.data.startswith("conf_del_"):
        key = cb.data.split("_")[2]
        if key in post_data: del post_data[key]
        save_db()
        await cb.message.delete()
    elif cb.data == "back_to_list":
        btns = [[types.InlineKeyboardButton(k, callback_data=f"prep_del_{k}")] for k in post_data.keys()]
        await cb.edit_message_reply_markup(types.InlineKeyboardMarkup(btns))

@bot.on_message(filters.text & filters.regex("📊 الاكاونتات المضافة"))
async def list_accs(client, message):
    if not active_sessions:
        return await message.reply("ماكو اكاونتات\nمضافة", reply_markup=main_keyboard)
    btns = [[types.InlineKeyboardButton(f"{p} {'✅' if v['status'] else '❌'}", callback_data=f"tog_{p}")] for p, v in active_sessions.items()]
    btns.append([types.InlineKeyboardButton("🗑️ مسح رقم", callback_data="del_acc_start")])
    await message.reply("الاكاونتات الشغالة", reply_markup=types.InlineKeyboardMarkup(btns))

@bot.on_message(filters.text & filters.regex("🗑️ مسح كروب"))
async def delete_group_list(client, message):
    if not post_data: return
    btns = [[types.InlineKeyboardButton(k, callback_data=f"prep_del_{k}")] for k in post_data.keys()]
    await message.reply(" ", reply_markup=types.InlineKeyboardMarkup(btns))

async def main():
    if not os.path.exists("sessions"): os.mkdir("sessions")
    await bot.start()
    db_accs = load_db()
    for p, v in db_accs.items():
        cli = Client(f"sessions/{p}", api_id=v["api_id"], api_hash=v["api_hash"])
        try:
            await cli.start()
            active_sessions[p] = {"client": cli, "status": v["status"], "api_id": v["api_id"], "api_hash": v["api_hash"]}
            asyncio.create_task(start_media_catcher(cli, p, bot.me.id))
        except: pass
    await asyncio.sleep(float('inf'))

if __name__ == "__main__":
    bot.run(main())
