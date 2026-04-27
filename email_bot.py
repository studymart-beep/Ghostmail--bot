import logging
import requests
import random
import string
import re
import json
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters, ConversationHandler
)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ✅ YOUR BOT TOKEN
BOT_TOKEN = "8602213173:AAFaUOiaqdNWwQsAswjW3ba_7NQ5ocJ6U8M"

ACCOUNTS_FILE = "email_accounts.json"

ASKING_USERNAME = 1
ASKING_RECIPIENT = 2
ASKING_SUBJECT = 3
ASKING_MESSAGE = 4

def load_accounts():
    try:
        if os.path.exists(ACCOUNTS_FILE):
            with open(ACCOUNTS_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {}

def save_accounts(data):
    try:
        with open(ACCOUNTS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Save error: {e}")

user_data = load_accounts()

class EmailAPI:
    BASE = "https://api.mail.tm"

    @staticmethod
    def create_account(username):
        try:
            r = requests.get(f"{EmailAPI.BASE}/domains", timeout=10)
            if r.status_code != 200:
                return None
            domains = r.json().get('hydra:member', [])
            if not domains:
                return None

            domain = domains[0]['domain']
            email = f"{username}@{domain}"
            password = ''.join(random.choices(string.ascii_letters + string.digits, k=16))

            r = requests.post(
                f"{EmailAPI.BASE}/accounts",
                json={"address": email, "password": password},
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            if r.status_code not in [200, 201]:
                return None

            r = requests.post(
                f"{EmailAPI.BASE}/token",
                json={"address": email, "password": password},
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            if r.status_code != 200:
                return None

            return {
                "email": email,
                "password": password,
                "token": r.json()['token'],
                "domain": domain,
                "created": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
        except Exception as e:
            logger.error(f"Create error: {e}")
            return None

    @staticmethod
    def refresh_token(email, password):
        try:
            r = requests.post(
                f"{EmailAPI.BASE}/token",
                json={"address": email, "password": password},
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            if r.status_code == 200:
                return r.json()['token']
        except:
            pass
        return None

    @staticmethod
    def get_messages(token):
        try:
            headers = {"Authorization": f"Bearer {token}"}
            r = requests.get(f"{EmailAPI.BASE}/messages", headers=headers, timeout=10)
            if r.status_code == 200:
                return r.json().get('hydra:member', [])
        except:
            pass
        return []

    @staticmethod
    def get_message(token, msg_id):
        try:
            headers = {"Authorization": f"Bearer {token}"}
            r = requests.get(f"{EmailAPI.BASE}/messages/{msg_id}", headers=headers, timeout=10)
            if r.status_code == 200:
                return r.json()
        except:
            pass
        return None

    @staticmethod
    def send_email(token, from_addr, to_addr, subject, body):
        try:
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            data = {
                "from": {"address": from_addr},
                "to": [{"address": to_addr}],
                "subject": subject,
                "text": body
            }
            r = requests.post(f"{EmailAPI.BASE}/messages", json=data, headers=headers, timeout=10)
            return r.status_code in [200, 201]
        except:
            return False

def get_user_data(user_id):
    user_id = str(user_id)
    if user_id not in user_data:
        user_data[user_id] = {"accounts": {}, "active": None}
    return user_data[user_id]

def get_active(user_id):
    data = get_user_data(user_id)
    active = data["active"]
    if active and active in data["accounts"]:
        return active, data["accounts"][active]
    return None, None

# ============ COMMANDS ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    active_email, active_info = get_active(user_id)
    total = len(data["accounts"])

    keyboard = [
        [InlineKeyboardButton("➕ Create Email", callback_data='create')],
    ]
    if total > 0:
        keyboard.append([
            InlineKeyboardButton("📨 Inbox", callback_data='inbox'),
            InlineKeyboardButton("📤 Send", callback_data='send')
        ])
        keyboard.append([InlineKeyboardButton("📋 My Emails", callback_data='myemails')])
    if total > 1:
        keyboard.append([InlineKeyboardButton("🔄 Switch", callback_data='switch')])
    if total > 0:
        keyboard.append([InlineKeyboardButton("🗑 Delete", callback_data='delete')])
    keyboard.append([InlineKeyboardButton("❓ Help", callback_data='help')])

    if active_email:
        text = (
            f"📧 *Temp Mail Bot*\n\n"
            f"📧 *Active:* `{active_email}`\n"
            f"🔑 *Password:* `{active_info['password']}`\n"
            f"📊 *Total Accounts:* {total}\n\n"
            f"✅ Works: TikTok, FB, IG, Telegram\n"
            f"✅ Receives: Codes, Links, Verifications\n\n"
            f"/create - New email\n"
            f"/inbox - Check messages\n"
            f"/myemails - View all accounts"
        )
    else:
        text = (
            f"📧 *Temp Mail Bot*\n\n"
            f"Welcome! Create your first email!\n\n"
            f"/create to start!"
        )

    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def create_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "➕ *Create New Email*\n\n"
        "Enter username (3-30 chars):\n"
        "Example: `john2024`\n\n"
        "Or /cancel to abort",
        parse_mode='Markdown'
    )
    return ASKING_USERNAME

async def process_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip().lower()
    if not re.match(r'^[a-zA-Z0-9._-]{3,30}$', username):
        await update.message.reply_text("❌ Invalid! Try again (3-30 chars, letters/numbers only):")
        return ASKING_USERNAME

    msg = await update.message.reply_text("🔄 Creating your email...")
    user_id = update.effective_user.id
    account = EmailAPI.create_account(username)

    if account:
        data = get_user_data(user_id)
        data["accounts"][account["email"]] = account
        data["active"] = account["email"]
        save_accounts(user_data)

        await msg.edit_text(
            f"✅ *Email Created!*\n\n"
            f"📧 *Email:* `{account['email']}`\n"
            f"🔑 *Password:* `{account['password']}`\n"
            f"🌐 *Domain:* {account['domain']}\n\n"
            f"✅ Can receive verification codes\n"
            f"✅ Works with social media\n\n"
            f"/inbox - Check messages",
            parse_mode='Markdown'
        )
    else:
        await msg.edit_text("❌ Failed! Try a different username with /create")
    return ConversationHandler.END

async def inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    active_email, active_info = get_active(user_id)

    if not active_email:
        await update.message.reply_text("❌ No active account! /create first.")
        return

    msg = await update.message.reply_text("🔍 Fetching inbox...")

    # Refresh token if needed
    new_token = EmailAPI.refresh_token(active_email, active_info['password'])
    if new_token:
        active_info['token'] = new_token

    messages = EmailAPI.get_messages(active_info['token'])

    if messages:
        text = f"📨 *Inbox - {active_email}*\n📊 *Messages:* {len(messages)}\n\n"
        keyboard = []
        for i, m in enumerate(messages[:10], 1):
            from_addr = m.get('from', {}).get('address', 'Unknown')
            subject = m.get('subject', 'No subject')
            text += f"{i}. From: `{from_addr}`\n   Subject: {subject[:50]}\n\n"
            keyboard.append([InlineKeyboardButton(f"📖 View #{i}", callback_data=f'msg_{m["id"]}')])
        keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data='inbox')])
        keyboard.append([InlineKeyboardButton("🏠 Menu", callback_data='start')])
    else:
        text = (
            f"📭 *Inbox Empty*\n"
            f"Email: `{active_email}`\n\n"
            f"💡 Click 🔄 Refresh if you just signed up!"
        )
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh Now", callback_data='inbox')],
            [InlineKeyboardButton("🏠 Menu", callback_data='start')]
        ]

    await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def view_message(update: Update, context: ContextTypes.DEFAULT_TYPE, msg_id: str):
    user_id = update.effective_user.id
    _, active_info = get_active(user_id)

    msg = await update.message.reply_text("📖 Loading message...")
    message = EmailAPI.get_message(active_info['token'], msg_id)

    if message:
        from_addr = message.get('from', {}).get('address', 'Unknown')
        subject = message.get('subject', 'No subject')
        body = (message.get('text') or message.get('html') or 'No content')
        if len(body) > 1500:
            body = body[:1500] + "..."

        text = f"📧 *Message*\n\n*From:* `{from_addr}`\n*Subject:* {subject}\n\n{body}"
        keyboard = [
            [InlineKeyboardButton("🔙 Inbox", callback_data='inbox')],
            [InlineKeyboardButton("🏠 Menu", callback_data='start')]
        ]
        await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await msg.edit_text("❌ Failed to load message")

async def myemails(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    active_email, _ = get_active(user_id)

    if not data["accounts"]:
        await update.message.reply_text("📭 No accounts! /create to make one.")
        return

    text = f"📋 *Your Emails*\n\n"
    for i, (email, info) in enumerate(data["accounts"].items(), 1):
        marker = "✅" if email == active_email else "📧"
        text += f"{i}. {marker} `{email}`\n   🔑 `{info['password']}`\n\n"

    keyboard = [
        [InlineKeyboardButton("🔄 Switch", callback_data='switch')],
        [InlineKeyboardButton("🏠 Menu", callback_data='start')]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def switch_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    active_email, _ = get_active(user_id)

    if len(data["accounts"]) < 2:
        await update.message.reply_text(f"❌ Need 2+ accounts! You have {len(data['accounts'])}.")
        return

    keyboard = []
    for email in data["accounts"]:
        prefix = "✅ " if email == active_email else "📧 "
        keyboard.append([InlineKeyboardButton(f"{prefix}{email}", callback_data=f'sw_{email}')])
    keyboard.append([InlineKeyboardButton("🔙 Cancel", callback_data='start')])

    await update.message.reply_text("🔄 Select account:", reply_markup=InlineKeyboardMarkup(keyboard))

async def send_email_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    active_email, _ = get_active(user_id)
    if not active_email:
        await update.message.reply_text("❌ No active account!")
        return ConversationHandler.END
    await update.message.reply_text(f"📤 *Send Email*\nFrom: `{active_email}`\n\nEnter recipient:", parse_mode='Markdown')
    return ASKING_RECIPIENT

async def process_recipient(update: Update, context: ContextTypes.DEFAULT_TYPE):
    recipient = update.message.text.strip()
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', recipient):
        await update.message.reply_text("❌ Invalid email! Try again:")
        return ASKING_RECIPIENT
    context.user_data['recipient'] = recipient
    await update.message.reply_text("📝 Subject:")
    return ASKING_SUBJECT

async def process_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['subject'] = update.message.text.strip()
    await update.message.reply_text("📄 Message:")
    return ASKING_MESSAGE

async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    active_email, active_info = get_active(user_id)
    msg = await update.message.reply_text("📤 Sending...")
    success = EmailAPI.send_email(
        active_info['token'], active_email,
        context.user_data['recipient'],
        context.user_data['subject'],
        update.message.text
    )
    if success:
        await msg.edit_text(f"✅ Sent to `{context.user_data['recipient']}`!", parse_mode='Markdown')
    else:
        await msg.edit_text("❌ Failed!")
    return ConversationHandler.END

async def delete_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    active_email, _ = get_active(user_id)
    if not data["accounts"]:
        await update.message.reply_text("❌ No accounts!")
        return
    keyboard = []
    for email in data["accounts"]:
        prefix = "✅" if email == active_email else "📧"
        keyboard.append([InlineKeyboardButton(f"🗑 {prefix} {email}", callback_data=f'del_{email}')])
    keyboard.append([InlineKeyboardButton("🔙 Cancel", callback_data='start')])
    await update.message.reply_text("⚠️ Delete which?", reply_markup=InlineKeyboardMarkup(keyboard))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📧 *Temp Mail Bot Help*\n\n"
        "/start - Menu\n/create - New email\n"
        "/inbox - Check messages\n/myemails - View all\n"
        "/switch - Change account\n/send - Send\n"
        "/delete - Remove\n\n"
        "💡 Click 🔄 Refresh!"
    , parse_mode='Markdown')

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'create':
        await query.message.reply_text("➕ Enter username:")
        return ASKING_USERNAME
    elif data == 'myemails':
        await myemails_button(query)
    elif data == 'switch':
        await switch_button(query)
    elif data == 'inbox':
        await inbox_button(query)
    elif data == 'send':
        await query.message.reply_text("📤 Enter recipient:")
        return ASKING_RECIPIENT
    elif data == 'delete':
        await delete_button(query)
    elif data == 'help':
        await help_button(query)
    elif data == 'start':
        await start_button(query)
    elif data.startswith('sw_'):
        email = data[3:]
        user_id = query.from_user.id
        data_acc = get_user_data(user_id)
        if email in data_acc["accounts"]:
            data_acc["active"] = email
            save_accounts(user_data)
            await query.message.reply_text(f"✅ Switched to `{email}`", parse_mode='Markdown')
    elif data.startswith('del_'):
        email = data[4:]
        user_id = query.from_user.id
        data_acc = get_user_data(user_id)
        if email in data_acc["accounts"]:
            del data_acc["accounts"][email]
            if data_acc["active"] == email:
                data_acc["active"] = next(iter(data_acc["accounts"])) if data_acc["accounts"] else None
            save_accounts(user_data)
            await query.message.reply_text(f"🗑 Deleted")
    elif data.startswith('msg_'):
        await view_message_button(query, data[4:])

async def myemails_button(query):
    user_id = query.from_user.id
    data = get_user_data(user_id)
    active_email, _ = get_active(user_id)
    if not data["accounts"]:
        await query.message.reply_text("📭 No accounts!")
        return
    text = f"📋 *Your Emails*\n\n"
    for i, (email, info) in enumerate(data["accounts"].items(), 1):
        marker = "✅" if email == active_email else "📧"
        text += f"{i}. {marker} `{email}`\n   🔑 `{info['password']}`\n\n"
    keyboard = [[InlineKeyboardButton("🔄 Switch", callback_data='switch')], [InlineKeyboardButton("🏠 Menu", callback_data='start')]]
    await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def switch_button(query):
    user_id = query.from_user.id
    data = get_user_data(user_id)
    active_email, _ = get_active(user_id)
    if len(data["accounts"]) < 2:
        await query.message.reply_text("❌ Need 2+ accounts!")
        return
    keyboard = []
    for email in data["accounts"]:
        prefix = "✅ " if email == active_email else "📧 "
        keyboard.append([InlineKeyboardButton(f"{prefix}{email}", callback_data=f'sw_{email}')])
    keyboard.append([InlineKeyboardButton("🔙 Cancel", callback_data='start')])
    await query.message.reply_text("🔄 Select:", reply_markup=InlineKeyboardMarkup(keyboard))

async def inbox_button(query):
    user_id = query.from_user.id
    active_email, active_info = get_active(user_id)
    if not active_email:
        await query.message.reply_text("❌ No active account!")
        return
    msg = await query.message.reply_text("🔍 Fetching inbox...")
    
    new_token = EmailAPI.refresh_token(active_email, active_info['password'])
    if new_token:
        active_info['token'] = new_token
    
    messages = EmailAPI.get_messages(active_info['token'])
    
    if messages:
        text = f"📨 *Inbox*\n📊 {len(messages)} messages\n\n"
        keyboard = []
        for i, m in enumerate(messages[:10], 1):
            from_addr = m.get('from', {}).get('address', 'Unknown')
            subject = m.get('subject', 'No subject')[:40]
            text += f"{i}. `{from_addr}`\n   {subject}\n\n"
            keyboard.append([InlineKeyboardButton(f"📖 View #{i}", callback_data=f'msg_{m["id"]}')])
        keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data='inbox')])
        keyboard.append([InlineKeyboardButton("🏠 Menu", callback_data='start')])
    else:
        text = "📭 Empty\n\n💡 Click 🔄 Refresh!"
        keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data='inbox')], [InlineKeyboardButton("🏠 Menu", callback_data='start')]]
    
    await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def view_message_button(query, msg_id):
    user_id = query.from_user.id
    _, active_info = get_active(user_id)
    msg = await query.message.reply_text("📖 Loading...")
    message = EmailAPI.get_message(active_info['token'], msg_id)
    if message:
        from_addr = message.get('from', {}).get('address', 'Unknown')
        subject = message.get('subject', 'No subject')
        body = (message.get('text') or message.get('html') or 'No content')
        if len(body) > 1500:
            body = body[:1500] + "..."
        text = f"📧 *Message*\n*From:* `{from_addr}`\n*Subject:* {subject}\n\n{body}"
        keyboard = [[InlineKeyboardButton("🔙 Inbox", callback_data='inbox')], [InlineKeyboardButton("🏠 Menu", callback_data='start')]]
        await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await msg.edit_text("❌ Failed")

async def delete_button(query):
    user_id = query.from_user.id
    data = get_user_data(user_id)
    active_email, _ = get_active(user_id)
    if not data["accounts"]:
        await query.message.reply_text("❌ No accounts!")
        return
    keyboard = []
    for email in data["accounts"]:
        prefix = "✅" if email == active_email else "📧"
        keyboard.append([InlineKeyboardButton(f"🗑 {prefix} {email}", callback_data=f'del_{email}')])
    keyboard.append([InlineKeyboardButton("🔙 Cancel", callback_data='start')])
    await query.message.reply_text("⚠️ Delete which?", reply_markup=InlineKeyboardMarkup(keyboard))

async def help_button(query):
    await query.message.reply_text("📧 /start /create /inbox /myemails /switch /send /delete\n💡 Click 🔄 Refresh!", parse_mode='Markdown')

async def start_button(query):
    user_id = query.from_user.id
    data = get_user_data(user_id)
    active_email, active_info = get_active(user_id)
    total = len(data["accounts"])
    keyboard = [
        [InlineKeyboardButton("➕ Create", callback_data='create')],
        [InlineKeyboardButton("📋 My Emails", callback_data='myemails')],
    ]
    if total > 0:
        keyboard.append([InlineKeyboardButton("📨 Inbox", callback_data='inbox'), InlineKeyboardButton("📤 Send", callback_data='send')])
    if total > 1:
        keyboard.append([InlineKeyboardButton("🔄 Switch", callback_data='switch')])
    if total > 0:
        keyboard.append([InlineKeyboardButton("🗑 Delete", callback_data='delete')])
    if active_email:
        text = f"📧 `{active_email}`\n📊 {total} accounts"
    else:
        text = f"📊 {total} accounts"
    await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    create_conv = ConversationHandler(
        entry_points=[CommandHandler('create', create_account_start), CallbackQueryHandler(button_handler, pattern='^create$')],
        states={ASKING_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_username)]},
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    send_conv = ConversationHandler(
        entry_points=[CommandHandler('send', send_email_start), CallbackQueryHandler(button_handler, pattern='^send$')],
        states={
            ASKING_RECIPIENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_recipient)],
            ASKING_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_subject)],
            ASKING_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_message)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('myemails', myemails))
    app.add_handler(CommandHandler('switch', switch_account))
    app.add_handler(CommandHandler('inbox', inbox))
    app.add_handler(CommandHandler('delete', delete_account))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(create_conv)
    app.add_handler(send_conv)
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("=" * 50)
    print("📧 Temp Mail Bot is running!")
    print("Bot: @ghost_mailbot")
    print("=" * 50)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()