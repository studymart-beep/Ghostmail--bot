import logging
import requests
import random
import string
import re
import json
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters, ConversationHandler

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token
BOT_TOKEN = "8602213173:AAFaUOiaqdNWwQsAswjW3ba_7NQ5ocJ6U8M"

# File to save accounts
ACCOUNTS_FILE = "email_accounts.json"

# Conversation states
ASKING_USERNAME = 1

def load_accounts():
    """Load accounts from file"""
    try:
        if os.path.exists(ACCOUNTS_FILE):
            with open(ACCOUNTS_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {}

def save_accounts(data):
    """Save accounts to file"""
    try:
        with open(ACCOUNTS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Save error: {e}")

# Global storage
user_data = load_accounts()

class TempMailAPI:
    """Handle temp mail operations"""
    
    BASE_URL = "https://api.mail.tm"
    
    @staticmethod
    def create_account():
        """Create a new temp email account"""
        try:
            # Get available domains
            resp = requests.get(f"{TempMailAPI.BASE_URL}/domains", timeout=10)
            if resp.status_code != 200:
                return None
            
            domains = resp.json().get('hydra:member', [])
            if not domains:
                return None
            
            domain = random.choice(domains)['domain']
            username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
            email = f"{username}@{domain}"
            password = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
            
            # Create account
            account_data = {"address": email, "password": password}
            resp = requests.post(
                f"{TempMailAPI.BASE_URL}/accounts",
                json=account_data,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if resp.status_code not in [200, 201]:
                return None
            
            # Get token
            resp = requests.post(
                f"{TempMailAPI.BASE_URL}/token",
                json=account_data,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if resp.status_code != 200:
                return None
            
            token = resp.json().get('token')
            
            return {
                "email": email,
                "password": password,
                "token": token,
                "domain": domain,
                "created": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
            
        except Exception as e:
            logger.error(f"Create account error: {e}")
            return None
    
    @staticmethod
    def get_messages(token):
        """Get inbox messages"""
        try:
            headers = {"Authorization": f"Bearer {token}"}
            resp = requests.get(
                f"{TempMailAPI.BASE_URL}/messages",
                headers=headers,
                timeout=10
            )
            
            if resp.status_code == 200:
                return resp.json().get('hydra:member', [])
            return []
            
        except Exception as e:
            logger.error(f"Get messages error: {e}")
            return []
    
    @staticmethod
    def get_message(token, msg_id):
        """Get specific message"""
        try:
            headers = {"Authorization": f"Bearer {token}"}
            resp = requests.get(
                f"{TempMailAPI.BASE_URL}/messages/{msg_id}",
                headers=headers,
                timeout=10
            )
            
            if resp.status_code == 200:
                return resp.json()
            return None
            
        except Exception as e:
            logger.error(f"Get message error: {e}")
            return None
    
    @staticmethod
    def refresh_token(email, password):
        """Refresh expired token"""
        try:
            resp = requests.post(
                f"{TempMailAPI.BASE_URL}/token",
                json={"address": email, "password": password},
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if resp.status_code == 200:
                return resp.json().get('token')
            return None
            
        except Exception as e:
            logger.error(f"Refresh token error: {e}")
            return None


def get_user_data(user_id):
    """Get or create user data"""
    user_id = str(user_id)
    if user_id not in user_data:
        user_data[user_id] = {"accounts": {}, "active": None}
    return user_data[user_id]


def get_active(user_id):
    """Get active account for user"""
    data = get_user_data(user_id)
    active = data.get("active")
    if active and active in data.get("accounts", {}):
        return active, data["accounts"][active]
    return None, None


# ============ BOT COMMANDS ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command - show main menu"""
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    active_email, active_info = get_active(user_id)
    total = len(data.get("accounts", {}))
    total_users = len(user_data)

    keyboard = [
        [InlineKeyboardButton("➕ Create Email", callback_data='create')],
    ]
    
    if total > 0:
        keyboard.append([
            InlineKeyboardButton("📨 Check Inbox", callback_data='inbox'),
            InlineKeyboardButton("📋 My Emails", callback_data='myemails')
        ])
    
    if total > 1:
        keyboard.append([InlineKeyboardButton("🔄 Switch Account", callback_data='switch')])
    
    if total > 0:
        keyboard.append([InlineKeyboardButton("🗑 Delete Account", callback_data='delete')])
    
    keyboard.append([InlineKeyboardButton("❓ Help", callback_data='help')])

    if active_email:
        text = (
            f"📧 *Temp Mail Bot*\n\n"
            f"📧 *Active:* `{active_email}`\n"
            f"🔑 *Password:* `{active_info['password']}`\n"
            f"📊 *Your Accounts:* {total}\n"
            f"👥 *Total Users:* {total_users}\n\n"
            f"✅ Works with social media\n"
            f"✅ Facebook, TikTok, Instagram\n\n"
            f"/inbox - Check messages\n"
            f"/create - New email"
        )
    else:
        text = (
            f"📧 *Temp Mail Bot*\n\n"
            f"Create free temp emails!\n"
            f"👥 {total_users} users\n\n"
            f"/create to get started!"
        )

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def create_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create new email account"""
    msg = await update.message.reply_text("🔄 Creating your email...")
    
    user_id = update.effective_user.id
    account = TempMailAPI.create_account()
    
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
            f"📅 *Created:* {account['created']}\n\n"
            f"✅ Works on most platforms\n"
            f"✅ Facebook, TikTok, Instagram\n\n"
            f"/inbox - Check messages",
            parse_mode='Markdown'
        )
    else:
        await msg.edit_text(
            "❌ *Failed to create email*\n"
            "Please try again with /create",
            parse_mode='Markdown'
        )


async def inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check inbox for active account"""
    user_id = update.effective_user.id
    active_email, active_info = get_active(user_id)
    
    if not active_email:
        await update.message.reply_text("❌ No active account! Use /create first.")
        return
    
    msg = await update.message.reply_text("🔍 Checking inbox...")
    
    # Try to refresh token
    new_token = TempMailAPI.refresh_token(active_email, active_info['password'])
    if new_token:
        active_info['token'] = new_token
    
    messages = TempMailAPI.get_messages(active_info['token'])
    
    if messages:
        text = f"📨 *Inbox - {active_email}*\n📊 Messages: {len(messages)}\n\n"
        keyboard = []
        
        for i, m in enumerate(messages[:10], 1):
            from_addr = m.get('from', {}).get('address', 'Unknown')
            subject = m.get('subject', 'No subject')
            text += f"{i}. From: `{from_addr}`\n   Subject: {subject[:50]}\n\n"
            keyboard.append([
                InlineKeyboardButton(f"📖 View #{i}", callback_data=f'msg_{m["id"]}')
            ])
        
        keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data='inbox')])
        keyboard.append([InlineKeyboardButton("🏠 Menu", callback_data='start')])
    else:
        text = (
            f"📭 *Inbox Empty*\n"
            f"Email: `{active_email}`\n\n"
            f"💡 Wait 2-5 min for codes\n"
            f"Click 🔄 Refresh to check again"
        )
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data='inbox')],
            [InlineKeyboardButton("🏠 Menu", callback_data='start')]
        ]
    
    await msg.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def view_message(update: Update, context: ContextTypes.DEFAULT_TYPE, msg_id: str):
    """View a specific message"""
    user_id = update.effective_user.id
    _, active_info = get_active(user_id)
    
    msg = await update.message.reply_text("📖 Loading message...")
    
    message = TempMailAPI.get_message(active_info['token'], msg_id)
    
    if message:
        from_addr = message.get('from', {}).get('address', 'Unknown')
        subject = message.get('subject', 'No subject')
        body = message.get('text', message.get('html', 'No content'))
        
        if len(str(body)) > 1500:
            body = str(body)[:1500] + "..."
        
        text = (
            f"📧 *Message*\n\n"
            f"*From:* `{from_addr}`\n"
            f"*Subject:* {subject}\n\n"
            f"{body}"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔙 Inbox", callback_data='inbox')],
            [InlineKeyboardButton("🏠 Menu", callback_data='start')]
        ]
        
        await msg.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        await msg.edit_text("❌ Failed to load message")


async def myemails(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all user's email accounts"""
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    active_email, _ = get_active(user_id)
    
    if not data.get("accounts"):
        await update.message.reply_text("📭 No accounts! Use /create to make one.")
        return
    
    text = f"📋 *Your Emails*\n\n"
    for i, (email, info) in enumerate(data["accounts"].items(), 1):
        marker = "✅" if email == active_email else "📧"
        text += f"{i}. {marker} `{email}`\n   🔑 `{info['password']}`\n   📅 {info['created']}\n\n"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Switch", callback_data='switch')],
        [InlineKeyboardButton("🏠 Menu", callback_data='start')]
    ]
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def switch_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch active account"""
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    active_email, _ = get_active(user_id)
    
    if len(data.get("accounts", {})) < 2:
        await update.message.reply_text(f"❌ Need 2+ accounts! You have {len(data.get('accounts', {}))}.")
        return
    
    keyboard = []
    for email in data["accounts"]:
        prefix = "✅ " if email == active_email else "📧 "
        keyboard.append([
            InlineKeyboardButton(f"{prefix}{email}", callback_data=f'sw_{email}')
        ])
    keyboard.append([InlineKeyboardButton("🔙 Cancel", callback_data='start')])
    
    await update.message.reply_text(
        "🔄 Select account:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def delete_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete an account"""
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    active_email, _ = get_active(user_id)
    
    if not data.get("accounts"):
        await update.message.reply_text("❌ No accounts to delete!")
        return
    
    keyboard = []
    for email in data["accounts"]:
        prefix = "✅" if email == active_email else "📧"
        keyboard.append([
            InlineKeyboardButton(f"🗑 {prefix} {email}", callback_data=f'del_{email}')
        ])
    keyboard.append([InlineKeyboardButton("🔙 Cancel", callback_data='start')])
    
    await update.message.reply_text(
        "⚠️ Select account to delete:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help"""
    await update.message.reply_text(
        "📧 *Temp Mail Bot Help*\n\n"
        "/start - Main menu\n"
        "/create - Create new email\n"
        "/inbox - Check messages\n"
        "/myemails - View your accounts\n"
        "/switch - Change account\n"
        "/delete - Remove account\n"
        "/help - Show this message\n\n"
        "✅ Works with social media\n"
        "💡 Click 🔄 Refresh in inbox!",
        parse_mode='Markdown'
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all button presses"""
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == 'create':
        await create_email(update, context)
    
    elif data == 'inbox':
        await inbox(update, context)
    
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
            await query.message.reply_text(f"🗑 Deleted `{email}`", parse_mode='Markdown')
    
    elif data.startswith('msg_'):
        msg_id = data[4:]
        await view_message(update, context, msg_id)


def main():
    """Start the bot"""
    # Create application
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Add command handlers
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('create', create_email))
    app.add_handler(CommandHandler('inbox', inbox))
    app.add_handler(CommandHandler('myemails', myemails))
    app.add_handler(CommandHandler('switch', switch_account))
    app.add_handler(CommandHandler('delete', delete_account))
    app.add_handler(CommandHandler('help', help_command))
    
    # Add button handler
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Start bot
    print("=" * 50)
    print("🤖 Temp Mail Bot is running!")
    print("Bot: @ghost_mailbot")
    print("=" * 50)
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()