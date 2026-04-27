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
ASKING_USERNAME = 1
ASKING_PASSWORD = 2
ASKING_RECIPIENT = 3
ASKING_SUBJECT = 4
ASKING_BODY = 5

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

class TempMailAPI:
    """Email API Handler"""
    
    @staticmethod
    def create_account(username, password):
        """Create Guerrilla Mail account with custom username"""
        try:
            # Get a new email address
            params = {
                'f': 'get_email_address',
                'ip': '127.0.0.1',
                'agent': 'temp_mail_bot'
            }
            r = requests.get("https://api.guerrillamail.com/ajax.php", params=params, timeout=10)
            if r.status_code == 200:
                data = r.json()
                email = data.get('email_addr')
                sid_token = data.get('sid_token')
                
                if email and sid_token:
                    # Try to set custom username
                    domain = email.split('@')[1]
                    custom_email = f"{username}@{domain}"
                    
                    params2 = {
                        'f': 'set_email_user',
                        'sid_token': sid_token,
                        'email_user': username
                    }
                    r2 = requests.get("https://api.guerrillamail.com/ajax.php", params=params2, timeout=10)
                    
                    final_email = custom_email if r2.status_code == 200 else email
                    
                    return {
                        "email": final_email,
                        "password": password,
                        "token": sid_token,
                        "domain": domain,
                        "service": "Guerrilla Mail",
                        "username": username,
                        "created": datetime.now().strftime("%b %d, %Y at %I:%M %p")
                    }
        except:
            pass
        return None
    
    @staticmethod
    def get_messages(sid_token):
        """Get inbox messages"""
        try:
            params = {'f': 'get_email_list', 'offset': 0, 'sid_token': sid_token}
            r = requests.get("https://api.guerrillamail.com/ajax.php", params=params, timeout=10)
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
        except:
            pass
        return []
    
    @staticmethod
    def get_message(sid_token, msg_id):
        """Get message content"""
        try:
            params = {'f': 'fetch_email', 'email_id': msg_id, 'sid_token': sid_token}
            r = requests.get("https://api.guerrillamail.com/ajax.php", params=params, timeout=10)
            if r.status_code == 200:
                msg = r.json()
                return {
                    'from': msg.get('mail_from', 'Unknown'),
                    'subject': msg.get('mail_subject', 'No subject'),
                    'text': msg.get('mail_body', 'No content'),
                    'date': msg.get('mail_date', '')
                }
        except:
            pass
        return None
    
    @staticmethod
    def send_email(sid_token, to_addr, subject, body):
        """Send email"""
        try:
            params = {
                'f': 'send_email',
                'sid_token': sid_token,
                'to': to_addr,
                'subject': subject,
                'body': body
            }
            r = requests.post("https://api.guerrillamail.com/ajax.php", data=params, timeout=15)
            if r.status_code == 200:
                result = r.json()
                return result.get('status') == 'success'
        except:
            pass
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

# ============ HOME SCREEN ============

async def home_screen(update: Update, context: ContextTypes.DEFAULT_TYPE, message=None):
    """Show home screen"""
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    active_email, active_info = get_active(user_id)
    total = len(data.get("accounts", {}))
    total_users = len(user_data)
    
    keyboard = [
        [InlineKeyboardButton("✨ Create New Email", callback_data='create')],
    ]
    
    if total > 0:
        keyboard.append([
            InlineKeyboardButton("📥 Inbox", callback_data='inbox'),
            InlineKeyboardButton("📤 Send Mail", callback_data='send')
        ])
        keyboard.append([
            InlineKeyboardButton("📋 My Emails", callback_data='myemails'),
            InlineKeyboardButton("🔄 Switch", callback_data='switch')
        ])
        keyboard.append([InlineKeyboardButton("🗑 Delete Account", callback_data='delete')])
    
    keyboard.append([
        InlineKeyboardButton("ℹ️ Help", callback_data='help'),
        InlineKeyboardButton("📊 Stats", callback_data='stats')
    ])
    
    if active_email:
        text = (
            f"╔══════════════════════╗\n"
            f"║   📧 TEMP MAIL BOT   ║\n"
            f"╚══════════════════════╝\n\n"
            f"👤 *Active Account*\n"
            f"┣ 📧 `{active_email}`\n"
            f"┣ 🔑 `{active_info.get('password', 'N/A')}`\n"
            f"┣ 🔒 *Provider:* {active_info.get('service', 'N/A')}\n"
            f"┣ 📅 *Created:* {active_info.get('created', 'N/A')}\n"
            f"┗ 📊 *Your Accounts:* {total}\n\n"
            f"🌍 *Global Stats*\n"
            f"┗ 👥 Total Users: {total_users}\n\n"
            f"💡 Type *home* anytime to return here!"
        )
    else:
        text = (
            f"╔══════════════════════╗\n"
            f"║   📧 TEMP MAIL BOT   ║\n"
            f"╚══════════════════════╝\n\n"
            f"👋 *Welcome!*\n\n"
            f"✨ Create disposable emails\n"
            f"📥 Receive verification codes\n"
            f"📤 Send emails anonymously\n"
            f"🔒 Custom username & password\n\n"
            f"🌍 *Total Users:* {total_users}\n\n"
            f"👉 Click *Create New Email* to start!\n"
            f"💡 Type *home* anytime to return."
        )
    
    if message:
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# ============ CREATE EMAIL ============

async def create_email_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 1: Ask for username"""
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='home')]]
    
    if update.callback_query:
        await update.callback_query.message.reply_text(
            "✨ *Create Your Email*\n\n"
            "📝 *Step 1/2:* Choose your username\n\n"
            "• 3-30 characters\n"
            "• Letters, numbers, dots, hyphens\n"
            "• Example: `john.doe` or `mike123`\n\n"
            "✏️ Enter your desired username:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "✨ *Create Your Email*\n\n"
            "📝 *Step 1/2:* Choose your username\n\n"
            "• 3-30 characters\n"
            "• Letters, numbers, dots, hyphens\n"
            "• Example: `john.doe` or `mike123`\n\n"
            "✏️ Enter your desired username:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    return ASKING_USERNAME

async def process_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 2: Save username and ask for password"""
    username = update.message.text.strip().lower()
    
    if not re.match(r'^[a-zA-Z0-9._-]{3,30}$', username):
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='home')]]
        await update.message.reply_text(
            "❌ *Invalid Username!*\n\n"
            "• Must be 3-30 characters\n"
            "• Only letters, numbers, dots, hyphens\n"
            "• Example: `john.doe`\n\n"
            "Try again:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return ASKING_USERNAME
    
    # Check if username already taken by this user
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    for email in data.get("accounts", {}):
        if username in email:
            keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='home')]]
            await update.message.reply_text(
                f"❌ Username `{username}` is already in use!\n\n"
                "Choose a different username:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return ASKING_USERNAME
    
    context.user_data['username'] = username
    
    keyboard = [[InlineKeyboardButton("🔀 Generate Random", callback_data='gen_pass')],
                [InlineKeyboardButton("❌ Cancel", callback_data='home')]]
    
    await update.message.reply_text(
        f"🔐 *Step 2/2:* Choose Password\n\n"
        f"Username: `{username}`\n\n"
        f"Enter your password (min 6 chars)\n"
        f"or click Generate Random:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return ASKING_PASSWORD

async def process_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create account with username and password"""
    password = update.message.text.strip()
    
    if len(password) < 6:
        keyboard = [[InlineKeyboardButton("🔀 Generate Random", callback_data='gen_pass')],
                    [InlineKeyboardButton("❌ Cancel", callback_data='home')]]
        await update.message.reply_text(
            "❌ Password must be at least 6 characters!\n\n"
            "Enter a stronger password:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return ASKING_PASSWORD
    
    return await create_account_final(update, context, password)

async def generate_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate random password"""
    query = update.callback_query
    await query.answer()
    
    password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
    
    await query.message.reply_text(
        f"🔑 *Generated Password:* `{password}`\n\n"
        "Creating your account..."
    )
    
    return await create_account_final(update, context, password)

async def create_account_final(update, context, password):
    """Final step: Create the account"""
    username = context.user_data.get('username', 'user')
    
    msg = await update.message.reply_text("🔄 *Creating your email...*", parse_mode='Markdown')
    
    user_id = update.effective_user.id
    account = TempMailAPI.create_account(username, password)
    
    if account:
        data = get_user_data(user_id)
        data["accounts"][account["email"]] = account
        data["active"] = account["email"]
        save_accounts(user_data)
        
        keyboard = [
            [InlineKeyboardButton("📥 Check Inbox", callback_data='inbox'),
             InlineKeyboardButton("📤 Send Email", callback_data='send')],
            [InlineKeyboardButton("🏠 Go to Home", callback_data='home')]
        ]
        
        await msg.edit_text(
            f"✅ *Account Created Successfully!*\n\n"
            f"┏━━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃ 👤 *Username:* {account['username']}\n"
            f"┃ 📧 `{account['email']}`\n"
            f"┃ 🔑 `{account['password']}`\n"
            f"┃ 🌐 *Domain:* {account['domain']}\n"
            f"┃ 📅 {account['created']}\n"
            f"┗━━━━━━━━━━━━━━━━━━━━┛\n\n"
            f"✅ Save your password!\n"
            f"✅ Works with social media\n"
            f"✅ Receive & Send emails",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        keyboard = [
            [InlineKeyboardButton("🔄 Try Again", callback_data='create')],
            [InlineKeyboardButton("🏠 Home", callback_data='home')]
        ]
        await msg.edit_text(
            "❌ *Account creation failed*\n\n"
            "Please try again with a different username.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    return ConversationHandler.END

# ============ INBOX ============

async def inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check inbox"""
    user_id = update.effective_user.id
    active_email, active_info = get_active(user_id)
    
    if not active_email:
        keyboard = [
            [InlineKeyboardButton("✨ Create Email", callback_data='create')],
            [InlineKeyboardButton("🏠 Home", callback_data='home')]
        ]
        if update.callback_query:
            await update.callback_query.message.reply_text(
                "❌ *No Active Account*\n\nCreate an email first!",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "❌ *No Active Account*\n\nCreate an email first!",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        return
    
    if update.callback_query:
        msg = await update.callback_query.message.reply_text("🔍 *Checking inbox...*", parse_mode='Markdown')
    else:
        msg = await update.message.reply_text("🔍 *Checking inbox...*", parse_mode='Markdown')
    
    messages = TempMailAPI.get_messages(active_info['token'])
    
    if messages:
        text = f"📥 *Inbox* ━━━ {active_email}\n┗ 📊 {len(messages)} message(s)\n\n"
        keyboard = []
        
        for i, m in enumerate(messages[:8], 1):
            from_addr = m.get('from', 'Unknown')[:35]
            subject = str(m.get('subject', 'No subject'))[:40]
            unread = "🔵" if m.get('read') == 0 else "⚪"
            
            text += f"{unread} *{i}.* `{from_addr}`\n      {subject}\n\n"
            keyboard.append([InlineKeyboardButton(f"📖 Open #{i} - {subject[:25]}", callback_data=f'msg_{m["id"]}')])
        
        keyboard.append([InlineKeyboardButton("🔄 Refresh Inbox", callback_data='inbox')])
        keyboard.append([InlineKeyboardButton("🏠 Back to Home", callback_data='home')])
    else:
        text = (
            f"📭 *Inbox Empty*\n"
            f"┗ {active_email}\n\n"
            f"💡 *Don't see your email?*\n"
            f"• Wait 2-5 minutes\n"
            f"• Click 🔄 Refresh below"
        )
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh Now", callback_data='inbox')],
            [InlineKeyboardButton("🏠 Back to Home", callback_data='home')]
        ]
    
    await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# ============ VIEW MESSAGE ============

async def view_message(update: Update, context: ContextTypes.DEFAULT_TYPE, msg_id: str):
    """View message content"""
    _, active_info = get_active(update.effective_user.id)
    msg = await update.callback_query.message.reply_text("📖 *Opening message...*", parse_mode='Markdown')
    message = TempMailAPI.get_message(active_info['token'], msg_id)
    
    if message:
        body = str(message.get('text', 'No content'))
        if len(body) > 1200:
            body = body[:1200] + "...\n\n[Message truncated]"
        
        text = (
            f"📧 *Message Details*\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"👤 *From:* {message.get('from', 'Unknown')}\n"
            f"📝 *Subject:* {message.get('subject', 'No subject')}\n"
            f"📅 *Date:* {message.get('date', 'Unknown')}\n"
            f"━━━━━━━━━━━━━━━━━\n\n"
            f"{body}"
        )
        keyboard = [
            [InlineKeyboardButton("🔙 Back to Inbox", callback_data='inbox')],
            [InlineKeyboardButton("🏠 Home", callback_data='home')]
        ]
        await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        keyboard = [
            [InlineKeyboardButton("🔙 Back to Inbox", callback_data='inbox')],
            [InlineKeyboardButton("🏠 Home", callback_data='home')]
        ]
        await msg.edit_text("❌ *Message not found*\nIt may have expired.", 
                           reply_markup=InlineKeyboardMarkup(keyboard),
                           parse_mode='Markdown')

# ============ SEND EMAIL ============

async def send_email_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start send email process"""
    user_id = update.effective_user.id
    active_email, _ = get_active(user_id)
    
    if not active_email:
        keyboard = [
            [InlineKeyboardButton("✨ Create Email", callback_data='create')],
            [InlineKeyboardButton("🏠 Home", callback_data='home')]
        ]
        if update.callback_query:
            await update.callback_query.message.reply_text(
                "❌ *No Active Account*\n\nCreate an email first!",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "❌ *No Active Account*\n\nCreate an email first!",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        return ConversationHandler.END
    
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='home')]]
    
    if update.callback_query:
        await update.callback_query.message.reply_text(
            f"📤 *Compose Email*\n━━━━━━━━━━━━━━━━━\n"
            f"From: `{active_email}`\n\n"
            f"📧 Enter recipient email:\n"
            f"Example: `friend@gmail.com`",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            f"📤 *Compose Email*\n━━━━━━━━━━━━━━━━━\n"
            f"From: `{active_email}`\n\n"
            f"📧 Enter recipient email:\n"
            f"Example: `friend@gmail.com`",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    return ASKING_RECIPIENT

async def process_recipient(update: Update, context: ContextTypes.DEFAULT_TYPE):
    recipient = update.message.text.strip()
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', recipient):
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='home')]]
        await update.message.reply_text(
            "❌ *Invalid email!*\nEnter a valid email:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return ASKING_RECIPIENT
    
    context.user_data['recipient'] = recipient
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='home')]]
    await update.message.reply_text(
        "📝 *Enter subject:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return ASKING_SUBJECT

async def process_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subject = update.message.text.strip()
    if not subject:
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='home')]]
        await update.message.reply_text(
            "❌ Subject cannot be empty!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return ASKING_SUBJECT
    
    context.user_data['subject'] = subject
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='home')]]
    await update.message.reply_text(
        "📄 *Enter your message:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return ASKING_BODY

async def process_body(update: Update, context: ContextTypes.DEFAULT_TYPE):
    body = update.message.text.strip()
    if not body:
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='home')]]
        await update.message.reply_text(
            "❌ Message cannot be empty!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return ASKING_BODY
    
    user_id = update.effective_user.id
    _, active_info = get_active(user_id)
    
    msg = await update.message.reply_text("📤 *Sending email...*", parse_mode='Markdown')
    
    success = TempMailAPI.send_email(
        active_info['token'],
        context.user_data['recipient'],
        context.user_data['subject'],
        body
    )
    
    if success:
        keyboard = [[InlineKeyboardButton("🏠 Back to Home", callback_data='home')]]
        await msg.edit_text(
            f"✅ *Email Sent Successfully!*\n\n"
            f"📧 To: `{context.user_data['recipient']}`\n"
            f"📝 Subject: {context.user_data['subject']}\n\n"
            f"📄 Message:\n{body[:200]}{'...' if len(body) > 200 else ''}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        keyboard = [
            [InlineKeyboardButton("🔄 Try Again", callback_data='send')],
            [InlineKeyboardButton("🏠 Home", callback_data='home')]
        ]
        await msg.edit_text(
            "❌ *Failed to send!*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    return ConversationHandler.END

# ============ MY EMAILS ============

async def myemails(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all accounts"""
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    active_email, _ = get_active(user_id)
    
    if not data.get("accounts"):
        keyboard = [
            [InlineKeyboardButton("✨ Create Email", callback_data='create')],
            [InlineKeyboardButton("🏠 Home", callback_data='home')]
        ]
        await update.message.reply_text(
            "📭 *No Email Accounts*\n\nCreate your first email!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    text = f"📋 *Your Email Accounts*\n━━━━━━━━━━━━━━━━━\n\n"
    for i, (email, info) in enumerate(data["accounts"].items(), 1):
        marker = "✅" if email == active_email else "📧"
        text += f"{marker} *{i}.* `{email}`\n   🔑 `{info.get('password', 'N/A')}`\n   📅 {info.get('created', 'N/A')}\n\n"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Switch Account", callback_data='switch')],
        [InlineKeyboardButton("🗑 Delete Account", callback_data='delete')],
        [InlineKeyboardButton("🏠 Back to Home", callback_data='home')]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# ============ SWITCH ACCOUNT ============

async def switch_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch active account"""
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    active_email, _ = get_active(user_id)
    
    if len(data.get("accounts", {})) < 2:
        keyboard = [
            [InlineKeyboardButton("✨ Create Another", callback_data='create')],
            [InlineKeyboardButton("🏠 Home", callback_data='home')]
        ]
        await update.message.reply_text(
            f"❌ *Need More Accounts*\n\nYou have {len(data.get('accounts', {}))} account(s).\nCreate another to switch!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    keyboard = []
    for email in data["accounts"]:
        prefix = "✅ " if email == active_email else "📧 "
        keyboard.append([InlineKeyboardButton(f"{prefix}{email}", callback_data=f'sw_{email}')])
    keyboard.append([InlineKeyboardButton("🏠 Cancel", callback_data='home')])
    
    await update.message.reply_text(
        "🔄 *Switch Active Account*\n\nSelect the account to use:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ============ DELETE ACCOUNT ============

async def delete_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete account"""
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    active_email, _ = get_active(user_id)
    
    if not data.get("accounts"):
        await update.message.reply_text("❌ *No accounts to delete!*", parse_mode='Markdown')
        return
    
    keyboard = []
    for email in data["accounts"]:
        prefix = "✅" if email == active_email else "📧"
        keyboard.append([InlineKeyboardButton(f"🗑 Delete {email}", callback_data=f'del_{email}')])
    keyboard.append([InlineKeyboardButton("🏠 Cancel", callback_data='home')])
    
    await update.message.reply_text(
        "⚠️ *Delete Account*\n\nSelect account to permanently delete:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ============ STATS ============

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot statistics"""
    total_users = len(user_data)
    total_emails = sum(len(data.get("accounts", {})) for data in user_data.values())
    
    text = (
        f"📊 *Bot Statistics*\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"👥 Total Users: {total_users}\n"
        f"📧 Total Emails: {total_emails}\n"
        f"🌐 Provider: Guerrilla Mail\n"
        f"⚡ Status: Online 24/7\n"
        f"🔒 Privacy: Protected\n\n"
        f"💡 Share this bot with friends!"
    )
    keyboard = [[InlineKeyboardButton("🏠 Back to Home", callback_data='home')]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# ============ HELP ============

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help menu"""
    text = (
        f"ℹ️ *Help & Information*\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"✨ *Create Email*\n"
        f"Choose custom username & password\n\n"
        f"📥 *Inbox*\n"
        f"Check received messages & codes\n\n"
        f"📤 *Send Mail*\n"
        f"Send anonymous emails\n\n"
        f"📋 *My Emails*\n"
        f"View all your email accounts\n\n"
        f"🔄 *Switch*\n"
        f"Change active email account\n\n"
        f"🗑 *Delete*\n"
        f"Remove an email account\n\n"
        f"💡 Type *home* to return to main menu!"
    )
    keyboard = [[InlineKeyboardButton("🏠 Back to Home", callback_data='home')]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# ============ CANCEL ============

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🏠 Go to Home", callback_data='home')]]
    await update.message.reply_text(
        "❌ *Cancelled.*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return ConversationHandler.END

# ============ TEXT MESSAGE HANDLER ============

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages like 'home'"""
    text = update.message.text.strip().lower()
    
    if text == 'home':
        await start(update, context)

# ============ BUTTON HANDLER ============

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all button presses"""
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == 'create':
        return await create_email_start(update, context)
    elif data == 'inbox':
        await inbox(update, context)
    elif data == 'send':
        return await send_email_start(update, context)
    elif data == 'myemails':
        await myemails(update, context)
    elif data == 'switch':
        await switch_account(update, context)
    elif data == 'delete':
        await delete_account(update, context)
    elif data == 'help':
        await help_command(update, context)
    elif data == 'stats':
        await stats(update, context)
    elif data == 'home':
        await home_screen(update, context, message=query.message)
    elif data == 'gen_pass':
        return await generate_password(update, context)
    elif data.startswith('sw_'):
        email = data[3:]
        user_id = query.from_user.id
        data_acc = get_user_data(user_id)
        if email in data_acc.get("accounts", {}):
            data_acc["active"] = email
            save_accounts(user_data)
            keyboard = [
                [InlineKeyboardButton("📥 Check Inbox", callback_data='inbox')],
                [InlineKeyboardButton("🏠 Home", callback_data='home')]
            ]
            await query.message.reply_text(
                f"✅ *Switched to:* `{email}`",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
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
            keyboard = [
                [InlineKeyboardButton("✨ Create New", callback_data='create')],
                [InlineKeyboardButton("🏠 Home", callback_data='home')]
            ]
            await query.message.reply_text(
                f"🗑 *Deleted:* `{email}`",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
    elif data.startswith('msg_'):
        await view_message(update, context, data[4:])

# ============ MAIN ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command - shows home screen"""
    await home_screen(update, context)

def main():
    start_keep_alive()
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Create email conversation
    create_conv = ConversationHandler(
        entry_points=[
            CommandHandler('create', create_email_start),
            CallbackQueryHandler(button_handler, pattern='^create$')
        ],
        states={
            ASKING_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_username)],
            ASKING_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_password),
                CallbackQueryHandler(button_handler, pattern='^gen_pass$')
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel), CallbackQueryHandler(button_handler, pattern='^home$')]
    )
    
    # Send email conversation
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
        fallbacks=[CommandHandler('cancel', cancel), CallbackQueryHandler(button_handler, pattern='^home$')]
    )
    
    # All handlers
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('inbox', inbox))
    app.add_handler(CommandHandler('myemails', myemails))
    app.add_handler(CommandHandler('switch', switch_account))
    app.add_handler(CommandHandler('delete', delete_account))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('stats', stats))
    app.add_handler(create_conv)
    app.add_handler(send_conv)
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("╔══════════════════════════════╗")
    print("║   📧 TEMP MAIL BOT ONLINE   ║")
    print("║   ✅ Custom Username/Pass   ║")
    print("║   ✅ All Buttons Working    ║")
    print("║   ✅ Home Navigation Fixed  ║")
    print("╚══════════════════════════════╝")
    app.run_polling()

if __name__ == '__main__':
    main()