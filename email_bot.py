import logging
import requests
import random
import string
import os
import json
from datetime import datetime
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

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
    @staticmethod
    def create_account():
        account = TempMailAPI._try_mailtm()
        if account: return account
        account = TempMailAPI._try_mailgw()
        if account: return account
        account = TempMailAPI._try_tempmail_lol()
        if account: return account
        return None
    
    @staticmethod
    def _try_mailtm():
        try:
            r = requests.get("https://api.mail.tm/domains", timeout=10)
            if r.status_code != 200: return None
            domains = r.json().get('hydra:member', [])
            if not domains: return None
            domain = random.choice(domains)['domain']
            username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
            email = f"{username}@{domain}"
            password = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
            r = requests.post("https://api.mail.tm/accounts", json={"address": email, "password": password}, headers={"Content-Type": "application/json"}, timeout=10)
            if r.status_code not in [200, 201]: return None
            r = requests.post("https://api.mail.tm/token", json={"address": email, "password": password}, headers={"Content-Type": "application/json"}, timeout=10)
            if r.status_code != 200: return None
            return {"email": email, "password": password, "token": r.json()['token'], "domain": domain, "service": "mail.tm", "created": datetime.now().strftime("%Y-%m-%d %H:%M")}
        except:
            return None
    
    @staticmethod
    def _try_mailgw():
        try:
            r = requests.get("https://api.mail.gw/domains", timeout=10)
            if r.status_code != 200: return None
            domains = r.json().get('hydra:member', [])
            if not domains: return None
            domain = random.choice(domains)['domain']
            username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
            email = f"{username}@{domain}"
            password = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
            r = requests.post("https://api.mail.gw/accounts", json={"address": email, "password": password}, headers={"Content-Type": "application/json"}, timeout=10)
            if r.status_code not in [200, 201]: return None
            r = requests.post("https://api.mail.gw/token", json={"address": email, "password": password}, headers={"Content-Type": "application/json"}, timeout=10)
            if r.status_code != 200: return None
            return {"email": email, "password": password, "token": r.json()['token'], "domain": domain, "service": "mail.gw", "created": datetime.now().strftime("%Y-%m-%d %H:%M")}
        except:
            return None
    
    @staticmethod
    def _try_tempmail_lol():
        try:
            r = requests.get("https://api.tempmail.lol/v2/inbox/create", timeout=10)
            if r.status_code == 200:
                data = r.json()
                return {"email": data['address'], "password": "no_password", "token": data['token'], "domain": data['address'].split('@')[1], "service": "tempmail.lol", "created": datetime.now().strftime("%Y-%m-%d %H:%M")}
        except:
            pass
        return None
    
    @staticmethod
    def get_messages(account):
        service = account.get('service', 'mail.tm')
        if service == 'tempmail.lol':
            try:
                r = requests.get(f"https://api.tempmail.lol/v2/inbox?token={account['token']}", timeout=10)
                if r.status_code == 200:
                    return [{'id': e.get('id'), 'from': {'address': e.get('from', 'Unknown')}, 'subject': e.get('subject', 'No subject')} for e in r.json().get('emails', [])]
            except:
                pass
            return []
        base = "https://api.mail.gw" if service == 'mail.gw' else "https://api.mail.tm"
        try:
            headers = {"Authorization": f"Bearer {account['token']}"}
            r = requests.get(f"{base}/messages", headers=headers, timeout=10)
            if r.status_code == 200: return r.json().get('hydra:member', [])
        except:
            pass
        return []
    
    @staticmethod
    def get_message(account, msg_id):
        service = account.get('service', 'mail.tm')
        if service == 'tempmail.lol':
            try:
                r = requests.get(f"https://api.tempmail.lol/v2/inbox?token={account['token']}&id={msg_id}", timeout=10)
                if r.status_code == 200:
                    emails = r.json().get('emails', [])
                    if emails:
                        e = emails[0]
                        return {'from': {'address': e.get('from', 'Unknown')}, 'subject': e.get('subject', 'No subject'), 'text': e.get('body', 'No content')}
            except:
                pass
            return None
        base = "https://api.mail.gw" if service == 'mail.gw' else "https://api.mail.tm"
        try:
            headers = {"Authorization": f"Bearer {account['token']}"}
            r = requests.get(f"{base}/messages/{msg_id}", headers=headers, timeout=10)
            if r.status_code == 200: return r.json()
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
    active = data.get("active")
    if active and active in data.get("accounts", {}):
        return active, data["accounts"][active]
    return None, None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    active_email, active_info = get_active(user_id)
    total = len(data.get("accounts", {}))
    keyboard = [[InlineKeyboardButton("➕ Create Email", callback_data='create')]]
    if total > 0:
        keyboard.append([InlineKeyboardButton("📨 Inbox", callback_data='inbox'), InlineKeyboardButton("📋 My Emails", callback_data='myemails')])
    if total > 1:
        keyboard.append([InlineKeyboardButton("🔄 Switch", callback_data='switch')])
    if total > 0:
        keyboard.append([InlineKeyboardButton("🗑 Delete", callback_data='delete')])
    keyboard.append([InlineKeyboardButton("❓ Help", callback_data='help')])
    if active_email:
        text = f"📧 *Active:* `{active_email}`\n🔑 *Pass:* `{active_info['password']}`\n📊 *Accounts:* {total}"
    else:
        text = f"📧 *Temp Mail Bot*\n/create to get started!"
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def create_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔄 Creating...")
    user_id = update.effective_user.id
    account = TempMailAPI.create_account()
    if account:
        data = get_user_data(user_id)
        data["accounts"][account["email"]] = account
        data["active"] = account["email"]
        save_accounts(user_data)
        await msg.edit_text(f"✅ *Created!*\n📧 `{account['email']}`\n🔑 `{account['password']}`", parse_mode='Markdown')
    else:
        await msg.edit_text("❌ Failed! Try again.")

async def inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    active_email, active_info = get_active(user_id)
    if not active_email:
        await update.message.reply_text("❌ No active account!")
        return
    msg = await update.message.reply_text("🔍 Checking...")
    messages = TempMailAPI.get_messages(active_info)
    if messages:
        text = f"📨 *Inbox*\n📊 {len(messages)} messages\n\n"
        keyboard = []
        for i, m in enumerate(messages[:10], 1):
            from_addr = m.get('from', {}).get('address', 'Unknown') if isinstance(m.get('from'), dict) else m.get('from', 'Unknown')
            subject = m.get('subject', 'No subject')
            text += f"{i}. `{from_addr}`\n   {str(subject)[:50]}\n\n"
            keyboard.append([InlineKeyboardButton(f"📖 View #{i}", callback_data=f'msg_{m["id"]}')])
        keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data='inbox')])
        keyboard.append([InlineKeyboardButton("🏠 Menu", callback_data='start')])
    else:
        text = f"📭 *Empty*\n{active_email}"
        keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data='inbox')], [InlineKeyboardButton("🏠 Menu", callback_data='start')]]
    await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def view_message(update: Update, context: ContextTypes.DEFAULT_TYPE, msg_id: str):
    _, active_info = get_active(update.effective_user.id)
    msg = await update.message.reply_text("📖 Loading...")
    message = TempMailAPI.get_message(active_info, msg_id)
    if message:
        from_addr = message.get('from', {}).get('address', 'Unknown') if isinstance(message.get('from'), dict) else message.get('from', 'Unknown')
        body = str(message.get('text', 'No content'))[:1500]
        text = f"📧 *Message*\n*From:* `{from_addr}`\n*Subject:* {message.get('subject', 'No subject')}\n\n{body}"
        keyboard = [[InlineKeyboardButton("🔙 Inbox", callback_data='inbox')], [InlineKeyboardButton("🏠 Menu", callback_data='start')]]
        await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await msg.edit_text("❌ Failed")

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
        text += f"{i}. {marker} `{email}`\n   🔑 `{info['password']}`\n\n"
    keyboard = [[InlineKeyboardButton("🔄 Switch", callback_data='switch')], [InlineKeyboardButton("🏠 Menu", callback_data='start')]]
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
    await update.message.reply_text("📧 *Commands*\n/create /inbox /myemails /switch /delete /help", parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == 'create': await create_email(update, context)
    elif data == 'inbox': await inbox(update, context)
    elif data == 'myemails': await myemails(update, context)
    elif data == 'switch': await switch_account(update, context)
    elif data == 'delete': await delete_account(update, context)
    elif data == 'help': await help_command(update, context)
    elif data == 'start': await start(update, context)
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
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('create', create_email))
    app.add_handler(CommandHandler('inbox', inbox))
    app.add_handler(CommandHandler('myemails', myemails))
    app.add_handler(CommandHandler('switch', switch_account))
    app.add_handler(CommandHandler('delete', delete_account))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("🤖 Bot is running with port open!")
    app.run_polling()

if __name__ == '__main__':
    main()