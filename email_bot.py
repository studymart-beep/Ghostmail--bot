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

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

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
    except:
        pass

user_data = load_accounts()

# ============ MULTIPLE EMAIL PROVIDERS ============

def create_mailtm(username):
    """mail.tm - multiple domain attempts"""
    try:
        r = requests.get("https://api.mail.tm/domains", timeout=10)
        if r.status_code != 200:
            return None
        domains = r.json().get('hydra:member', [])
        if not domains:
            return None
        
        # Try each domain until one works
        for domain_obj in domains:
            domain = domain_obj['domain']
            email = f"{username}@{domain}"
            password = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
            
            r = requests.post(
                "https://api.mail.tm/accounts",
                json={"address": email, "password": password},
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            if r.status_code in [200, 201]:
                r = requests.post(
                    "https://api.mail.tm/token",
                    json={"address": email, "password": password},
                    headers={"Content-Type": "application/json"},
                    timeout=10
                )
                if r.status_code == 200:
                    return {
                        "email": email,
                        "password": password,
                        "token": r.json()['token'],
                        "domain": domain,
                        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "service": "mailtm"
                    }
        return None
    except Exception as e:
        logger.error(f"Mail.tm error: {e}")
        return None

def create_tempmail_lol(username):
    """tempmail.lol - better domains"""
    try:
        r = requests.get("https://api.tempmail.lol/v2/inbox/create", timeout=10)
        if r.status_code == 200:
            data = r.json()
            return {
                "email": data['address'],
                "password": "no_password",
                "token": data['token'],
                "domain": data['address'].split('@')[1],
                "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "service": "tempmail_lol"
            }
    except:
        pass
    return None

def create_mail_gw(username):
    """mail.gw - reliable domains"""
    try:
        r = requests.get("https://api.mail.gw/domains", timeout=10)
        if r.status_code != 200:
            return None
        domains = r.json().get('hydra:member', [])
        if not domains:
            return None
        
        domain = domains[0]['domain']
        email = f"{username}@{domain}"
        password = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
        
        r = requests.post(
            "https://api.mail.gw/accounts",
            json={"address": email, "password": password},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        if r.status_code in [200, 201]:
            r = requests.post(
                "https://api.mail.gw/token",
                json={"address": email, "password": password},
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            if r.status_code == 200:
                return {
                    "email": email,
                    "password": password,
                    "token": r.json()['token'],
                    "domain": domain,
                    "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "service": "mailgw"
                }
        return None
    except:
        pass
    return None

def create_best_email(username):
    """Try all providers until one works"""
    # Try tempmail.lol first (best domains)
    account = create_tempmail_lol(username)
    if account:
        logger.info(f"Created with tempmail.lol: {account['email']}")
        return account
    
    # Try mail.gw second
    account = create_mail_gw(username)
    if account:
        logger.info(f"Created with mail.gw: {account['email']}")
        return account
    
    # Try mail.tm last
    account = create_mailtm(username)
    if account:
        logger.info(f"Created with mail.tm: {account['email']}")
        return account
    
    return None

def get_messages(account):
    """Get messages based on service"""
    service = account.get('service')
    
    if service == 'mailtm' or service == 'mailgw':
        try:
            headers = {"Authorization": f"Bearer {account['token']}"}
            base = "https://api.mail.tm" if service == 'mailtm' else "https://api.mail.gw"
            r = requests.get(f"{base}/messages", headers=headers, timeout=10)
            if r.status_code == 200:
                return r.json().get('hydra:member', [])
        except:
            pass
    
    elif service == 'tempmail_lol':
        try:
            r = requests.get(
                f"https://api.tempmail.lol/v2/inbox?token={account['token']}",
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                return data.get('emails', [])
        except:
            pass
    
    return []

def get_message_detail(account, msg_id):
    """Get message detail"""
    service = account.get('service')
    
    if service == 'mailtm' or service == 'mailgw':
        try:
            headers = {"Authorization": f"Bearer {account['token']}"}
            base = "https://api.mail.tm" if service == 'mailtm' else "https://api.mail.gw"
            r = requests.get(f"{base}/messages/{msg_id}", headers=headers, timeout=10)
            if r.status_code == 200:
                return r.json()
        except:
            pass
    
    elif service == 'tempmail_lol':
        try:
            r = requests.get(
                f"https://api.tempmail.lol/v2/inbox?token={account['token']}&id={msg_id}",
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                if data.get('emails'):
                    msg = data['emails'][0]
                    return {
                        "from": {"address": msg.get('from', 'Unknown')},
                        "subject": msg.get('subject', 'No subject'),
                        "text": msg.get('body', msg.get('html', 'No content')),
                        "html": msg.get('html', '')
                    }
        except:
            pass
    
    return None

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
            InlineKeyboardButton("📋 My Emails", callback_data='myemails')
        ])
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
            f"✅ Works: TikTok, FB, IG, Snapchat\n"
            f"✅ Multiple providers for better success\n\n"
            f"/inbox - Check messages\n"
            f"/create - New email"
        )
    else:
        text = (
            f"📧 *Temp Mail Bot*\n\n"
            f"Welcome! No accounts yet.\n"
            f"/create to start!\n\n"
            f"✅ Multiple email providers\n"
            f"✅ Auto-selects best domain"
        )

    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def create_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "➕ *Create New Email*\n\n"
        "Enter username (3-30 chars):\n"
        "Example: `john2024`\n\n"
        "🔄 Trying multiple providers...\n"
        "Or /cancel",
        parse_mode='Markdown'
    )
    return ASKING_USERNAME

async def process_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip().lower()
    if not re.match(r'^[a-zA-Z0-9._-]{3,30}$', username):
        await update.message.reply_text("❌ Invalid! Try again:")
        return ASKING_USERNAME

    msg = await update.message.reply_text("🔄 Trying multiple email providers...")
    user_id = update.effective_user.id
    account = create_best_email(username)

    if account:
        data = get_user_data(user_id)
        data["accounts"][account["email"]] = account
        data["active"] = account["email"]
        save_accounts(user_data)

        await msg.edit_text(
            f"✅ *Email Created!*\n\n"
            f"📧 *Email:* `{account['email']}`\n"
            f"🔑 *Password:* `{account['password']}`\n"
            f"🌐 *Domain:* {account['domain']}\n"
            f"🔧 *Provider:* {account['service']}\n\n"
            f"✅ Works with social media\n"
            f"📌 Use /inbox to check messages",
            parse_mode='Markdown'
        )
    else:
        await msg.edit_text("❌ All providers failed! Try a different username.")
    return ConversationHandler.END

async def inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    active_email, active_info = get_active(user_id)

    if not active_email:
        msg = "❌ No active account! /create first."
        if update.message:
            await update.message.reply_text(msg)
        else:
            await update.callback_query.message.reply_text(msg)
        return

    if update.message:
        status_msg = await update.message.reply_text("🔍 Fetching inbox...")
    else:
        status_msg = await update.callback_query.message.reply_text("🔍 Fetching inbox...")

    messages = get_messages(active_info)

    if messages:
        text = f"📨 *Inbox - {active_email}*\n📊 Messages: {len(messages)}\n\n"
        keyboard = []
        for i, m in enumerate(messages[:10], 1):
            from_addr = m.get('from', {})
            if isinstance(from_addr, dict):
                from_addr = from_addr.get('address', 'Unknown')
            subject = m.get('subject', 'No subject')
            msg_id = m.get('id', str(i))
            
            text += f"{i}. From: `{from_addr}`\n   Subject: {str(subject)[:50]}\n\n"
            keyboard.append([InlineKeyboardButton(f"📖 View #{i}", callback_data=f'msg_{msg_id}')])
        
        keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data='inbox')])
        keyboard.append([InlineKeyboardButton("🏠 Menu", callback_data='start')])
    else:
        text = (
            f"📭 *Inbox Empty*\n"
            f"Email: `{active_email}`\n\n"
            f"💡 Click 🔄 Refresh\n"
            f"Wait 2-5 min for social media codes"
        )
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh Now", callback_data='inbox')],
            [InlineKeyboardButton("🏠 Menu", callback_data='start')]
        ]

    await status_msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def view_message(update: Update, context: ContextTypes.DEFAULT_TYPE, msg_id: str):
    user_id = update.effective_user.id
    _, active_info = get_active(user_id)
    msg = await update.message.reply_text("📖 Loading...")
    message = get_message_detail(active_info, msg_id)

    if message:
        from_addr = message.get('from', {})
        if isinstance(from_addr, dict):
            from_addr = from_addr.get('address', 'Unknown')
        subject = message.get('subject', 'No subject')
        body = str(message.get('text') or message.get('html') or 'No content')[:1500]

        text = f"📧 *Message*\n*From:* `{from_addr}`\n*Subject:* {subject}\n\n{body}"
        keyboard = [
            [InlineKeyboardButton("🔙 Inbox", callback_data='inbox')],
            [InlineKeyboardButton("🏠 Menu", callback_data='start')]
        ]
        await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await msg.edit_text("❌ Failed to load")

async def myemails(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    active_email, _ = get_active(user_id)
    if not data["accounts"]:
        await update.message.reply_text("📭 No accounts!")
        return
    text = f"📋 *Your Emails*\n\n"
    for i, (email, info) in enumerate(data["accounts"].items(), 1):
        marker = "✅" if email == active_email else "📧"
        text += f"{i}. {marker} `{email}`\n   🔑 `{info['password']}`\n\n"
    keyboard = [[InlineKeyboardButton("🔄 Switch", callback_data='switch')], [InlineKeyboardButton("🏠 Menu", callback_data='start')]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def switch_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    active_email, _ = get_active(user_id)
    if len(data["accounts"]) < 2:
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
        "📧 *Help*\n\n"
        "/create - New email\n"
        "/inbox - Check messages\n"
        "/myemails - View all\n"
        "/switch - Change account\n"
        "/delete - Remove\n\n"
        "✅ Multiple providers\n"
        "✅ Auto-selects best domain\n"
        "💡 Click 🔄 Refresh!",
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
        await query.message.reply_text("➕ Enter username:")
        return ASKING_USERNAME
    elif data == 'myemails':
        await myemails_button(query)
    elif data == 'switch':
        await switch_button(query)
    elif data == 'inbox':
        await inbox_button(query)
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
            await query.message.reply_text(f"🗑 Deleted", parse_mode='Markdown')
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
    msg = await query.message.reply_text("🔍 Fetching...")
    messages = get_messages(active_info)
    if messages:
        text = f"📨 *Inbox*\n📊 {len(messages)} messages\n\n"
        keyboard = []
        for i, m in enumerate(messages[:10], 1):
            from_addr = m.get('from', {})
            if isinstance(from_addr, dict):
                from_addr = from_addr.get('address', 'Unknown')
            subject = m.get('subject', 'No subject')
            msg_id = m.get('id', str(i))
            text += f"{i}. `{from_addr}`\n   {str(subject)[:40]}\n\n"
            keyboard.append([InlineKeyboardButton(f"📖 View #{i}", callback_data=f'msg_{msg_id}')])
        keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data='inbox')])
        keyboard.append([InlineKeyboardButton("🏠 Menu", callback_data='start')])
    else:
        text = "📭 Empty\n💡 Click 🔄 Refresh!"
        keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data='inbox')], [InlineKeyboardButton("🏠 Menu", callback_data='start')]]
    await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def view_message_button(query, msg_id):
    user_id = query.from_user.id
    _, active_info = get_active(user_id)
    msg = await query.message.reply_text("📖 Loading...")
    message = get_message_detail(active_info, msg_id)
    if message:
        from_addr = message.get('from', {})
        if isinstance(from_addr, dict):
            from_addr = from_addr.get('address', 'Unknown')
        subject = message.get('subject', 'No subject')
        body = str(message.get('text') or message.get('html') or 'No content')[:1500]
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
    await query.message.reply_text("📧 /create /inbox /myemails /switch /delete\n💡 Click 🔄 Refresh!", parse_mode='Markdown')

async def start_button(query):
    user_id = query.from_user.id
    data = get_user_data(user_id)
    active_email, active_info = get_active(user_id)
    total = len(data["accounts"])
    keyboard = [[InlineKeyboardButton("➕ Create", callback_data='create')]]
    if total > 0:
        keyboard.append([InlineKeyboardButton("📨 Inbox", callback_data='inbox'), InlineKeyboardButton("📋 My Emails", callback_data='myemails')])
    if total > 1:
        keyboard.append([InlineKeyboardButton("🔄 Switch", callback_data='switch')])
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
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('myemails', myemails))
    app.add_handler(CommandHandler('switch', switch_account))
    app.add_handler(CommandHandler('inbox', inbox))
    app.add_handler(CommandHandler('delete', delete_account))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(create_conv)
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("=" * 50)
    print("📧 Temp Mail Bot Running!")
    print("Bot: @ghost_mailbot")
    print("Providers: tempmail.lol, mail.gw, mail.tm")
    print("=" * 50)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()