import asyncio
import os
import json
import re
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
    [[types.KeyboardButton("📱 اضف رقم"), types.KeyboardButton("🤖 اوتو مسج")],
     [types.KeyboardButton("📊 الاكاونتات المضافة"), types.KeyboardButton("📁 الكروبات المضافة")]],
    resize_keyboard=True,
    is_persistent=True
)

@bot.on_message(filters.private & ~filters.regex("📱 اضف رقم|🤖 اوتو مسج|📊 الاكاونتات المضافة|📁 الكروبات المضافة"))
async def start_cmd(client, message):
    await message.reply("اهلا وسهلا بالبوت المصمم\nبدون غلط", reply_markup=main_keyboard, quote=True)

@bot.on_message(filters.text & filters.regex("📱 اضف رقم"))
async def add_session(client, message):
    try:
        while True:
            p = await client.ask(message.chat.id, "دز الرقم مع مفتاح الدولة\nمثلا 966...", reply_to_message_id=message.id)
            phone = p.text.strip().replace("+", "").replace(" ", "")
            if phone.isdigit() and len(phone) > 8:
                break
            await message.reply("دز رقم عمري", quote=True)

        while True:
            id_m = await client.ask(message.chat.id, "دز الايبي ايدي\nمالتك", reply_to_message_id=p.id)
            if id_m.text.strip().isdigit():
                u_api_id = int(id_m.text.strip())
                break
            await message.reply("دز رقم عمري", quote=True)

        while True:
            hash_m = await client.ask(message.chat.id, "دز الايبي هاش\nمالتك", reply_to_message_id=id_m.id)
            u_api_hash = hash_m.text.strip()
            if len(u_api_hash) == 32 and re.match(r'^[a-fA-F0-9]+$', u_api_hash):
                break
            await message.reply("دز رقم عمري", quote=True)
        
        new_c = Client(f"sessions/{phone}", api_id=u_api_id, api_hash=u_api_hash,
                       device_model="PC 64bit", system_version="Windows 11", app_version="4.15.2 x64")
        
        await new_c.connect()
        c_hash = await new_c.send_code(phone)
        
        while True:
            code_m = await client.ask(message.chat.id, "دز الكود الوصلك\nهسة", reply_to_message_id=hash_m.id)
            clean_code = re.sub(r'\D', '', code_m.text)
            if clean_code and len(clean_code) >= 5:
                final_code = clean_code[:5]
                break
            await message.reply("دز رقم عمري", quote=True)
        
        try:
            await new_c.sign_in(phone, c_hash.phone_code_hash, final_code)
        except errors.SessionPasswordNeeded:
            pw = await client.ask(message.chat.id, "دز الباسورد 2FA\nمالتك", reply_to_message_id=code_m.id)
            await new_c.check_password(pw.text)
            
        active_sessions[phone] = {"client": new_c, "status": True, "api_id": u_api_id, "api_hash": u_api_hash}
        save_db()
        await message.reply("اشتغل بدون مشاكل\nبرافو عليك ✅..", reply_markup=main_keyboard, quote=True)
    except Exception:
        await message.reply("ماشتغل معلسف المعلومات\nغلط ❌..", reply_markup=main_keyboard, quote=True)

@bot.on_message(filters.text & filters.regex("🤖 اوتو مسج"))
async def auto_msg_setup(client, message):
    if not active_sessions:
        return await message.reply("ضيف رقم على الأقل علمود تكدر\nتستعمل البوت بالشكل الكامل", quote=True)
    grp_ask = await client.ask(message.chat.id, "اعزل كروب تريدة من ضمن\nطاقم كروباتك", reply_to_message_id=message.id)
    msg_ask = await client.ask(message.chat.id, "دز المسج تريد يضل\nاوتو نشر", reply_to_message_id=grp_ask.id)
    await message.reply("ماهو نوع الفاصل الزمني", reply_markup=types.InlineKeyboardMarkup([
        [types.InlineKeyboardButton("د", callback_data=f"tmin_{grp_ask.text}_{msg_ask.text}"), 
         types.InlineKeyboardButton("س", callback_data=f"thrs_{grp_ask.text}_{msg_ask.text}")]
    ]), quote=True)

@bot.on_message(filters.text & filters.regex("📊 الاكاونتات المضافة"))
async def list_accs(client, message):
    if not active_sessions:
        return await message.reply("ضيف رقم على الأقل علمود تكدر\nتستعمل البوت بالشكل الكامل", quote=True)
    btns = [[types.InlineKeyboardButton(f"{p} {'✅' if v['status'] else '❌'}", callback_data=f"tog_{p}")] for p, v in active_sessions.items()]
    btns.append([types.InlineKeyboardButton("🗑️ مسح رقم", callback_data="del_acc_start")])
    await message.reply("الاكاونتات الشغالة", reply_markup=types.InlineKeyboardMarkup(btns), quote=True)

@bot.on_message(filters.text & filters.regex("📁 الكروبات المضافة"))
async def list_groups(client, message):
    if not active_sessions:
        return await message.reply("ضيف رقم على الأقل علمود تكدر\nتستعمل البوت بالشكل الكامل", quote=True)
    if not post_data: 
        return await message.reply("ماكو كروب مضاف هسة", quote=True)
    btns = [[types.InlineKeyboardButton(k, callback_data=f"prep_del_{k}")] for k in post_data.keys()]
    await message.reply("قائمة الكروبات المضافة:", reply_markup=types.InlineKeyboardMarkup(btns), quote=True)

@bot.on_callback_query()
async def handle_calls(client, cb):
    if cb.data.startswith("tmin_") or cb.data.startswith("thrs_"):
        parts = cb.data.split("_")
        while True:
            prompt = "دز كذا 00\nمثال صفرين: 54 دقيقة" if parts[0] == "tmin" else "دز كذا 0:00 او كذا 00\nمثال صفرين: 12 مثال تلاث اصفار: 1:23"
            t = await client.ask(cb.message.chat.id, prompt, reply_to_message_id=cb.message.id)
            clean_time = re.sub(r'\D', '', t.text)
            if clean_time:
                post_data[parts[1]] = {"msg": parts[2], "interval": t.text, "type": parts[0]}
                save_db()
                await client.send_message(cb.message.chat.id, f"ممتاز اصبح الفاصل الزمني\n{t.text}", reply_to_message_id=t.id)
                break
            await client.send_message(cb.message.chat.id, "دز رقم عمري", reply_to_message_id=t.id)

    elif cb.data.startswith("tog_"):
        phone = cb.data.split("_")[1]
        active_sessions[phone]["status"] = not active_sessions[phone]["status"]
        save_db()
        btns = [[types.InlineKeyboardButton(f"{p} {'✅' if v['status'] else '❌'}", callback_data=f"tog_{p}")] for p, v in active_sessions.items()]
        btns.append([types.InlineKeyboardButton("🗑️ مسح رقم", callback_data="del_acc_start")])
        await cb.edit_message_reply_markup(types.InlineKeyboardMarkup(btns))

    elif cb.data == "del_acc_start":
        ask_p = await client.ask(cb.message.chat.id, "دز الرقم الراح\nينمسح", reply_to_message_id=cb.message.id)
        p_to_del = ask_p.text.strip().replace("+", "")
        if p_to_del in active_sessions:
            del active_sessions[p_to_del]
            save_db()
            await client.send_message(cb.message.chat.id, "تم مسح الرقم", reply_markup=main_keyboard, reply_to_message_id=ask_p.id)

    elif cb.data.startswith("prep_del_"):
        key = cb.data.split("prep_del_")[1]
        await cb.edit_message_reply_markup(types.InlineKeyboardMarkup([
            [types.InlineKeyboardButton("مسح 🗑️", callback_data=f"conf_del_{key}")],
            [types.InlineKeyboardButton("🔙 عودة", callback_data="back_to_list")]
        ]))

    elif cb.data.startswith("conf_del_"):
        key = cb.data.split("conf_del_")[1]
        if key in post_data: 
            del post_data[key]
            save_db()
        if not post_data:
            await cb.edit_message_text("ماكو كروب مضاف هسة")
        else:
            btns = [[types.InlineKeyboardButton(k, callback_data=f"prep_del_{k}")] for k in post_data.keys()]
            await cb.edit_message_reply_markup(types.InlineKeyboardMarkup(btns))

    elif cb.data == "back_to_list":
        btns = [[types.InlineKeyboardButton(k, callback_data=f"prep_del_{k}")] for k in post_data.keys()]
        await cb.edit_message_reply_markup(types.InlineKeyboardMarkup(btns))

async def main():
    if not os.path.exists("sessions"): os.mkdir("sessions")
    await bot.start()
    db_accs = load_db()
    for p, v in db_accs.items():
        cli = Client(f"sessions/{p}", api_id=v["api_id"], api_hash=v["api_hash"], device_model="PC 64bit", system_version="Windows 11", app_version="4.15.2 x64")
        try:
            await cli.start()
            active_sessions[p] = {"client": cli, "status": v["status"], "api_id": v["api_id"], "api_hash": v["api_hash"]}
        except: pass
    await asyncio.sleep(float('inf'))


if __name__ == "__main__":
    bot.run(main())
