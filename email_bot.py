import logging
import requests
import random
import string
import os
import json
import re
from datetime import datetime
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters, ConversationHandler

# ========== KEEP-ALIVE WEB SERVER ==========
keep_alive_app = Flask(__name__)

@keep_alive_app.route('/')
def home():
    return "Bot is alive! Port is open."

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    keep_alive_app.run(host='0.0.0.0', port=port)

def start_keep_alive():
    t = Thread(target=run_flask)
    t.start()
# ===========================================

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8602213173:AAFaUOiaqdNWwQsAswjW3ba_7NQ5ocJ6U8M"
ACCOUNTS_FILE = "email_accounts.json"

# Conversation states
ASKING_RECIPIENT = 1
ASKING_SUBJECT = 2
ASKING_BODY = 3

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
    except:
        pass

user_data = load_accounts()

class GuerrillaMailAPI:
    """Guerrilla Mail API - Primary Provider"""
    
    BASE_URL = "https://api.guerrillamail.com/ajax.php"
    
    @staticmethod
    def create_account():
        """Create a new Guerrilla Mail account"""
        try:
            params = {
                'f': 'get_email_address',
                'ip': '127.0.0.1',
                'agent': 'telegram_temp_mail_bot'
            }
            r = requests.get(GuerrillaMailAPI.BASE_URL, params=params, timeout=10)
            if r.status_code == 200:
                data = r.json()
                email = data.get('email_addr')
                sid_token = data.get('sid_token')
                
                if email and sid_token:
                    # Also set the email address
                    params2 = {
                        'f': 'set_email_user',
                        'sid_token': sid_token,
                        'email_user': email.split('@')[0]
                    }
                    requests.get(GuerrillaMailAPI.BASE_URL, params=params2, timeout=10)
                    
                    return {
                        "email": email,
                        "password": "no_password_required",
                        "token": sid_token,
                        "domain": email.split('@')[1],
                        "service": "guerrillamail",
                        "created": datetime.now().strftime("%Y-%m-%d %H:%M")
                    }
        except Exception as e:
            logger.error(f"GuerrillaMail create error: {e}")
        return None
    
    @staticmethod
    def get_messages(sid_token):
        """Get inbox messages"""
        try:
            params = {
                'f': 'get_email_list',
                'offset': 0,
                'sid_token': sid_token
            }
            r = requests.get(GuerrillaMailAPI.BASE_URL, params=params, timeout=10)
            if r.status_code == 200:
                data = r.json()
                messages = []
                for m in data.get('list', []):
                    messages.append({
                        'id': m.get('mail_id'),
                        'from': m.get('mail_from', 'Unknown'),
                        'subject': m.get('mail_subject', 'No subject'),
                        'date': m.get('mail_date', ''),
                        'read': m.get('mail_read', 0)
                    })
                return messages
        except Exception as e:
            logger.error(f"Get messages error: {e}")
        return []
    
    @staticmethod
    def get_message(sid_token, msg_id):
        """Get specific message content"""
        try:
            params = {
                'f': 'fetch_email',
                'email_id': msg_id,
                'sid_token': sid_token
            }
            r = requests.get(GuerrillaMailAPI.BASE_URL, params=params, timeout=10)
            if r.status_code == 200:
                msg = r.json()
                return {
                    'from': msg.get('mail_from', 'Unknown'),
                    'subject': msg.get('mail_subject', 'No subject'),
                    'text': msg.get('mail_body', 'No content'),
                    'html': msg.get('mail_html', ''),
                    'date': msg.get('mail_date', '')
                }
        except Exception as e:
            logger.error(f"Get message error: {e}")
        return None
    
    @staticmethod
    def send_email(sid_token, to_addr, subject, body):
        """Send email from Guerrilla Mail account"""
        try:
            # First get the current email address
            params = {
                'f': 'get_email_address',
                'sid_token': sid_token
            }
            r = requests.get(GuerrillaMailAPI.BASE_URL, params=params, timeout=10)
            if r.status_code != 200:
                return False
            
            from_email = r.json().get('email_addr')
            
            # Compose and send
            params = {
                'f': 'send_email',
                'sid_token': sid_token,
                'to': to_addr,
                'subject': subject,
                'body': body
            }
            r = requests.post(GuerrillaMailAPI.BASE_URL, data=params, timeout=15)
            if r.status_code == 200:
                result = r.json()
                return result.get('status') == 'success'
        except Exception as e:
            logger.error(f"Send email error: {e}")
        return False


def get_user_data(user_id):
    user_id = str(user_id)
    if user_id not in user_data:
        user_data[user_id] = {"accounts": {}, "active": None}
    return user_data[user_id]

def get_active(user_id):
    data = get_user_data(user_id)
    active = data.get("active")
    if active and active in data.get("accounts", {}):
        return active, data["accounts"][active]
    return None, None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    active_email, active_info = get_active(user_id)
    total = len(data.get("accounts", {}))
    
    keyboard = [
        [InlineKeyboardButton("➕ Create Email", callback_data='create')],
    ]
    if total > 0:
        keyboard.append([
            InlineKeyboardButton("📨 Inbox", callback_data='inbox'),
            InlineKeyboardButton("📤 Send Email", callback_data='send')
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
            f"🔧 *Provider:* {active_info.get('service', 'N/A')}\n"
            f"📊 *Your Accounts:* {total}\n"
            f"👥 *Total Users:* {len(user_data)}\n\n"
            f"✅ Send & Receive emails\n"
            f"✅ Works with social media\n\n"
            f"/create - New email\n"
            f"/inbox - Check messages\n"
            f"/send - Send email"
        )
    else:
        text = (
            f"📧 *Temp Mail Bot*\n\n"
            f"Create free temp emails!\n"
            f"Send & Receive messages\n\n"
            f"/create to get started!"
        )
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def create_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔄 Creating your email...")
    
    user_id = update.effective_user.id
    account = GuerrillaMailAPI.create_account()
    
    if account:
        data = get_user_data(user_id)
        data["accounts"][account["email"]] = account
        data["active"] = account["email"]
        save_accounts(user_data)
        
        await msg.edit_text(
            f"✅ *Email Created!*\n\n"
            f"📧 *Email:* `{account['email']}`\n"
            f"🔧 *Provider:* Guerrilla Mail\n"
            f"🌐 *Domain:* {account['domain']}\n"
            f"📅 *Created:* {account['created']}\n\n"
            f"✅ Send & Receive emails\n"
            f"✅ Works on most platforms\n\n"
            f"/inbox - Check messages\n"
            f"/send - Send email",
            parse_mode='Markdown'
        )
    else:
        await msg.edit_text(
            "❌ *Failed to create email*\n"
            "Please try again in a few seconds.",
            parse_mode='Markdown'
        )

async def inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    active_email, active_info = get_active(user_id)
    
    if not active_email:
        await update.message.reply_text("❌ No active account! Use /create first.")
        return
    
    msg = await update.message.reply_text("🔍 Checking inbox...")
    messages = GuerrillaMailAPI.get_messages(active_info['token'])
    
    if messages:
        text = f"📨 *Inbox - {active_email}*\n📊 Messages: {len(messages)}\n\n"
        keyboard = []
        for i, m in enumerate(messages[:10], 1):
            from_addr = m.get('from', 'Unknown')
            subject = m.get('subject', 'No subject')
            unread = "🔵" if m.get('read') == 0 else "⚪"
            text += f"{i}. {unread} From: `{from_addr[:40]}`\n   Subject: {str(subject)[:50]}\n\n"
            keyboard.append([InlineKeyboardButton(f"📖 View #{i}", callback_data=f'msg_{m["id"]}')])
        keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data='inbox')])
        keyboard.append([InlineKeyboardButton("🏠 Menu", callback_data='start')])
    else:
        text = f"📭 *Inbox Empty*\n{active_email}\n\n💡 Wait 2-5 min then refresh"
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data='inbox')],
            [InlineKeyboardButton("🏠 Menu", callback_data='start')]
        ]
    
    await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def view_message(update: Update, context: ContextTypes.DEFAULT_TYPE, msg_id: str):
    _, active_info = get_active(update.effective_user.id)
    msg = await update.message.reply_text("📖 Loading message...")
    message = GuerrillaMailAPI.get_message(active_info['token'], msg_id)
    
    if message:
        body = str(message.get('text', 'No content'))[:1500]
        text = (
            f"📧 *Message*\n\n"
            f"*From:* `{message.get('from', 'Unknown')}`\n"
            f"*Subject:* {message.get('subject', 'No subject')}\n"
            f"*Date:* {message.get('date', 'Unknown')}\n\n"
            f"{body}"
        )
        keyboard = [
            [InlineKeyboardButton("🔙 Inbox", callback_data='inbox')],
            [InlineKeyboardButton("🏠 Menu", callback_data='start')]
        ]
        await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await msg.edit_text("❌ Failed to load message")

async def send_email_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    active_email, _ = get_active(user_id)
    
    if not active_email:
        await update.message.reply_text("❌ No active account! Use /create first.")
        return ConversationHandler.END
    
    await update.message.reply_text(
        f"📤 *Send Email*\n"
        f"From: `{active_email}`\n\n"
        f"Enter recipient email address:",
        parse_mode='Markdown'
    )
    return ASKING_RECIPIENT

async def process_recipient(update: Update, context: ContextTypes.DEFAULT_TYPE):
    recipient = update.message.text.strip()
    
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', recipient):
        await update.message.reply_text("❌ Invalid email! Please enter a valid email:")
        return ASKING_RECIPIENT
    
    context.user_data['recipient'] = recipient
    await update.message.reply_text("📝 Enter subject:")
    return ASKING_SUBJECT

async def process_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subject = update.message.text.strip()
    if not subject:
        await update.message.reply_text("❌ Subject cannot be empty! Enter subject:")
        return ASKING_SUBJECT
    
    context.user_data['subject'] = subject
    await update.message.reply_text("📄 Enter message body:")
    return ASKING_BODY

async def process_body(update: Update, context: ContextTypes.DEFAULT_TYPE):
    body = update.message.text.strip()
    if not body:
        await update.message.reply_text("❌ Message cannot be empty! Enter message:")
        return ASKING_BODY
    
    user_id = update.effective_user.id
    _, active_info = get_active(user_id)
    
    msg = await update.message.reply_text("📤 Sending email...")
    
    success = GuerrillaMailAPI.send_email(
        active_info['token'],
        context.user_data['recipient'],
        context.user_data['subject'],
        body
    )
    
    if success:
        await msg.edit_text(
            f"✅ *Email Sent!*\n\n"
            f"📧 From: `{active_info['email']}`\n"
            f"📨 To: `{context.user_data['recipient']}`\n"
            f"📝 Subject: {context.user_data['subject']}\n\n"
            f"📄 Message:\n{body[:200]}{'...' if len(body) > 200 else ''}",
            parse_mode='Markdown'
        )
    else:
        await msg.edit_text("❌ Failed to send email. Please try again.")
    
    return ConversationHandler.END

async def myemails(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    active_email, _ = get_active(user_id)
    
    if not data.get("accounts"):
        await update.message.reply_text("📭 No accounts!")
        return
    
    text = "📋 *Your Emails*\n\n"
    for i, (email, info) in enumerate(data["accounts"].items(), 1):
        marker = "✅" if email == active_email else "📧"
        text += f"{i}. {marker} `{email}`\n   🔧 {info.get('service', 'N/A')}\n   📅 {info.get('created', 'N/A')}\n\n"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Switch", callback_data='switch')],
        [InlineKeyboardButton("🏠 Menu", callback_data='start')]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def switch_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    active_email, _ = get_active(user_id)
    
    if len(data.get("accounts", {})) < 2:
        await update.message.reply_text("❌ Need 2+ accounts!")
        return
    
    keyboard = []
    for email in data["accounts"]:
        prefix = "✅ " if email == active_email else "📧 "
        keyboard.append([InlineKeyboardButton(f"{prefix}{email}", callback_data=f'sw_{email}')])
    keyboard.append([InlineKeyboardButton("🔙 Cancel", callback_data='start')])
    await update.message.reply_text("🔄 Select:", reply_markup=InlineKeyboardMarkup(keyboard))

async def delete_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    active_email, _ = get_active(user_id)
    
    if not data.get("accounts"):
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
        "📧 *Temp Mail Bot*\n\n"
        "/start - Main menu\n"
        "/create - Create new email\n"
        "/inbox - Check messages\n"
        "/send - Send email\n"
        "/myemails - View accounts\n"
        "/switch - Change account\n"
        "/delete - Remove account\n"
        "/help - This message\n\n"
        "✅ Guerrilla Mail Provider\n"
        "✅ Send & Receive emails",
        parse_mode='Markdown'
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == 'create':
        await create_email(update, context)
    elif data == 'inbox':
        await inbox(update, context)
    elif data == 'send':
        await send_email_start(update, context)
    elif data == 'myemails':
        await myemails(update, context)
    elif data == 'switch':
        await switch_account(update, context)
    elif data == 'delete':
        await delete_account(update, context)
    elif data == 'help':
        await help_command(update, context)
    elif data == 'start':
        await start(update, context)
    elif data.startswith('sw_'):
        email = data[3:]
        user_id = query.from_user.id
        data_acc = get_user_data(user_id)
        if email in data_acc.get("accounts", {}):
            data_acc["active"] = email
            save_accounts(user_data)
            await query.message.reply_text(f"✅ Switched to `{email}`", parse_mode='Markdown')
    elif data.startswith('del_'):
        email = data[4:]
        user_id = query.from_user.id
        data_acc = get_user_data(user_id)
        if email in data_acc.get("accounts", {}):
            del data_acc["accounts"][email]
            if data_acc.get("active") == email:
                accounts = data_acc.get("accounts", {})
                data_acc["active"] = next(iter(accounts)) if accounts else None
            save_accounts(user_data)
            await query.message.reply_text("🗑 Deleted", parse_mode='Markdown')
    elif data.startswith('msg_'):
        await view_message(update, context, data[4:])

def main():
    start_keep_alive()
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Conversation handler for sending emails
    send_conv = ConversationHandler(
        entry_points=[
            CommandHandler('send', send_email_start),
            CallbackQueryHandler(button_handler, pattern='^send$')
        ],
        states={
            ASKING_RECIPIENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_recipient)],
            ASKING_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_subject)],
            ASKING_BODY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_body)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('create', create_email))
    app.add_handler(CommandHandler('inbox', inbox))
    app.add_handler(CommandHandler('myemails', myemails))
    app.add_handler(CommandHandler('switch', switch_account))
    app.add_handler(CommandHandler('delete', delete_account))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(send_conv)
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("🤖 Bot is running with Guerrilla Mail!")
    print("✅ Send & Receive emails enabled")
    app.run_polling()

if __name__ == '__main__':
    main()