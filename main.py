import asyncio
import os
import json
from pyrogram import Client, filters, types, errors
from pyromod import listen
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID", "2040"))
API_HASH = os.getenv("API_HASH", "b18441a1ff607e10c989891a5462e627")

bot = Client("bot_manager", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

active_sessions = {}
DB_FILE = "sessions_db.json"
temp_post_data = {}

def save_db():
    data = {p: {"api_id": v["api_id"], "api_hash": v["api_hash"], "status": v["status"]} 
            for p, v in active_sessions.items()}
    with open(DB_FILE, "w") as f: json.dump(data, f)

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return json.load(f)
        except: return {}
    return {}

main_keyboard = types.ReplyKeyboardMarkup(
    [[types.KeyboardButton("📱 اضف رقم"), types.KeyboardButton("🤖 زر اوتو مسج")],
     [types.KeyboardButton("📊 الاكاونتات المضافة"), types.KeyboardButton("🗑️ مسح كروب")]],
    resize_keyboard=True
)

async def start_media_catcher(user_client, phone, owner_id):
    @user_client.on_message(filters.private & ~filters.me & (filters.photo | filters.video | filters.voice))
    async def catcher(client, msg):
        if not active_sessions.get(phone, {}).get("status"): return
        is_timer = False
        if (msg.photo or msg.video) and msg.ttl_seconds: is_timer = True
        elif msg.voice and getattr(msg.voice, "ttl_seconds", None): is_timer = True

        if is_timer:
            path = await msg.download()
            if msg.voice:
                sent = await bot.send_voice(owner_id, path)
            else:
                sent = await bot.send_document(owner_id, path)
            await sent.reply(f"الاسم: {msg.from_user.first_name}")
            if os.path.exists(path): os.remove(path)

@bot.on_message(filters.command("start"))
async def start_cmd(client, message):
    await message.reply("اهلا وسهلا بالبوت المصمم\nبدون غلط", reply_markup=main_keyboard)

@bot.on_message(filters.text & filters.regex("📱 اضف رقم"))
async def add_session(client, message):
    try:
        p = await client.ask(message.chat.id, "1\nدز الرقم مع مفتاح الدولة\nمثلا 966...")
        phone = p.text.strip().replace("+", "")
        id_m = await client.ask(message.chat.id, "2\nدز الايبي ايدي\nمالتك")
        u_api_id = int(id_m.text)
        hash_m = await client.ask(message.chat.id, "3\nدز الايبي هاش\nمالتك")
        u_api_hash = hash_m.text
        
        new_c = Client(f"sessions/{phone}", api_id=u_api_id, api_hash=u_api_hash)
        await new_c.connect()
        c_hash = await new_c.send_code(phone)
        code_m = await client.ask(message.chat.id, "4\nدز الكود الوصلك\nهسة")
        
        try:
            await new_c.sign_in(phone, c_hash.phone_code_hash, code_m.text)
        except errors.SessionPasswordNeeded:
            pw = await client.ask(message.chat.id, "5\nدز الباسورد 2FA\nمالتك")
            await new_c.check_password(pw.text)
            
        active_sessions[phone] = {"client": new_c, "status": True, "api_id": u_api_id, "api_hash": u_api_hash}
        save_db()
        asyncio.create_task(start_media_catcher(new_c, phone, message.chat.id))
        await message.reply("اشتغل بدون مشاكل\nبرافو عليك ✅..")
    except:
        await message.reply("ماشتغل معلسف المعلومات\nغلط ❌..")

@bot.on_message(filters.text & filters.regex("📊 الاكاونتات المضافة"))
async def list_accs(client, message):
    if not active_sessions:
        return await message.reply("ماكو اكاونتات\nمضافة")
    btns = [[types.InlineKeyboardButton(f"{p} {'✅' if v['status'] else '❌'}", callback_data=f"tog_{p}")] for p, v in active_sessions.items()]
    btns.append([types.InlineKeyboardButton("🗑️ مسح رقم", callback_data="del_acc_start")])
    await message.reply("الاكاونتات الشغالة", reply_markup=types.InlineKeyboardMarkup(btns))

@bot.on_message(filters.text & filters.regex("🤖 زر اوتو مسج"))
async def auto_msg_setup(client, message):
    grp_ask = await client.ask(message.chat.id, "اعزل كروب تريدة من ضمن\nطاقم كروباتك")
    msg_ask = await client.ask(message.chat.id, "دز مسج تريد يضل\nاوتو نشر")
    temp_post_data[message.chat.id] = {"chat_id": grp_ask.text, "msg": msg_ask.text}
    await message.reply("ماهو نوع الفاصل الزمني", reply_markup=types.InlineKeyboardMarkup([
        [types.InlineKeyboardButton("د", callback_data="time_min"), types.InlineKeyboardButton("س", callback_data="time_hrs")]
    ]))

@bot.on_message(filters.text & filters.regex("🗑️ مسح كروب"))
async def delete_group_list(client, message):
    if not temp_post_data: return
    btns = [[types.InlineKeyboardButton(v["chat_id"], callback_data=f"prep_del_{k}")] for k, v in temp_post_data.items()]
    await message.reply(" ", reply_markup=types.InlineKeyboardMarkup(btns))

@bot.on_callback_query()
async def handle_calls(client, cb):
    if cb.data.startswith("tog_"):
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
            await client.send_message(cb.message.chat.id, "تم مسح الرقم")

    elif cb.data.startswith("prep_del_"):
        key = int(cb.data.split("_")[2])
        await cb.edit_message_reply_markup(types.InlineKeyboardMarkup([
            [types.InlineKeyboardButton("مسح", callback_data=f"conf_del_{key}")],
            [types.InlineKeyboardButton("عودة", callback_data="back_to_list")]
        ]))

    elif cb.data.startswith("conf_del_"):
        key = int(cb.data.split("_")[2])
        if key in temp_post_data: del temp_post_data[key]
        await cb.message.delete()

    elif cb.data == "back_to_list":
        btns = [[types.InlineKeyboardButton(v["chat_id"], callback_data=f"prep_del_{k}")] for k, v in temp_post_data.items()]
        await cb.edit_message_reply_markup(types.InlineKeyboardMarkup(btns))

    elif cb.data == "time_min":
        t = await client.ask(cb.message.chat.id, "ادز كذا 45")
        await client.send_message(cb.message.chat.id, f"ممتاز اصبح الفاصل الزمني\n{t.text}")

    elif cb.data == "time_hrs":
        t = await client.ask(cb.message.chat.id, "ادز كذا 1:30 او 8 او 10 ساعات")
        await client.send_message(cb.message.chat.id, f"ممتاز اصبح الفاصل الزمني\n{t.text}")

async def main():
    await bot.start()
    db = load_db()
    for p, v in db.items():
        cli = Client(f"sessions/{p}", api_id=v["api_id"], api_hash=v["api_hash"])
        try:
            await cli.start()
            active_sessions[p] = {"client": cli, "status": v["status"], "api_id": v["api_id"], "api_hash": v["api_hash"]}
            asyncio.create_task(start_media_catcher(cli, p, bot.me.id))
        except: pass
    await asyncio.sleep(float('inf'))

if __name__ == "__main__":
    if not os.path.exists("sessions"): os.mkdir("sessions")
    bot.run(main())
