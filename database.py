# main.py

import os
import logging
import random
import string
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters,
    CallbackContext, ConversationHandler, CallbackQueryHandler
)

# Local imports
import database as db
import mail_gw as mail

# --- Basic Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Environment Variables ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("No BOT_TOKEN found in environment variables")
    
# --- Conversation States ---
GET_CUSTOM_USERNAME = 0

# --- Helper Functions ---
def generate_random_string(length=10):
    """Generate a random string of letters and digits."""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

# --- Command Handlers ---
def start(update: Update, context: CallbackContext) -> None:
    """Sends a welcome message and command list."""
    user = update.effective_user
    welcome_text = (
        f"👋 *Welcome to TempMail Bot, {user.first_name}!*
        \nThis bot helps you create temporary, disposable email addresses.
        \nPerfect for sign-ups, verifications, and protecting your privacy."
    )
    help_command(update, context, welcome_text)

def help_command(update: Update, context: CallbackContext, header: str = "📧 *Available Commands*") -> None:
    """Displays the help message with all commands."""
    commands_text = (
        f"{header}\n\n"
        "*/new* - Create a new random temporary email.\n"
        "*/custom* - Choose a custom username for your email.\n"
        "*/list* - Show all your active email addresses.\n"
        "*/inbox* - Check the inbox of one of your emails.\n"
        "*/delete* - Delete one of your temporary emails.\n"
        "*/stats* - View bot usage statistics.\n"
        "*/help* - Show this help message again."
    )
    update.message.reply_text(commands_text, parse_mode=ParseMode.MARKDOWN)

def new_email(update: Update, context: CallbackContext) -> None:
    """Generates a new random email address."""
    user_id = update.effective_user.id
    username = generate_random_string()
    password = generate_random_string(12)
    domain = mail.get_domains()

    if not domain:
        update.message.reply_text("❌ Could not fetch a domain from the mail provider. Please try again later.")
        return

    email_address = f"{username}@{domain}"
    account_info = mail.create_account(email_address, password)

    if account_info and 'id' in account_info:
        db.add_email(user_id, email_address, password, account_info['id'])
        update.message.reply_text(
            f"✅ *New temporary email created!* \n\n"
            f"📧 **Email:** `{email_address}`\n\n"
            f"You will be notified here of new messages. Use /inbox to check manually.",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        update.message.reply_text("❌ Failed to create the email account. The username might be taken or the service is down.")

def custom_email_start(update: Update, context: CallbackContext) -> int:
    """Starts the conversation to get a custom username."""
    update.message.reply_text("Please send me the custom username you want for your email (e.g., `my-cool-name`).\n\nSend /cancel to abort.")
    return GET_CUSTOM_USERNAME

def get_custom_username(update: Update, context: CallbackContext) -> int:
    """Processes the custom username and creates the email."""
    user_id = update.effective_user.id
    username = update.message.text.strip().lower()
    password = generate_random_string(12)
    domain = mail.get_domains()

    if not domain:
        update.message.reply_text("❌ Could not fetch a domain. Please try again later.")
        return ConversationHandler.END

    email_address = f"{username}@{domain}"
    account_info = mail.create_account(email_address, password)
    
    if account_info and 'id' in account_info:
        db.add_email(user_id, email_address, password, account_info['id'])
        update.message.reply_text(
            f"✅ *Custom temporary email created!* \n\n"
            f"📧 **Email:** `{email_address}`\n\n"
            f"Use /inbox to check for messages.",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        update.message.reply_text(f"❌ Failed to create `{email_address}`. The username is likely already taken or invalid. Please try another one.")
    
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext) -> int:
    """Cancels the current conversation."""
    update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

def list_emails(update: Update, context: CallbackContext) -> None:
    """Lists all active emails for the user."""
    user_id = update.effective_user.id
    emails = db.get_user_emails(user_id)
    if not emails:
        update.message.reply_text("You have no active temporary emails. Use /new or /custom to create one.")
        return

    message = "📄 *Your active email addresses:*\n\n"
    for email, _, _ in emails:
        message += f"📧 `{email}`\n"
    
    update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

def inbox_or_delete_prompt(update: Update, context: CallbackContext, action: str) -> None:
    """Generic function to prompt user to select an email for an action."""
    user_id = update.effective_user.id
    emails = db.get_user_emails(user_id)
    if not emails:
        update.message.reply_text("You have no active emails. Use /new or /custom first.")
        return

    keyboard = []
    for email, _, _ in emails:
        callback_data = f"{action}:{email}"
        keyboard.append([InlineKeyboardButton(email, callback_data=callback_data)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    prompt_text = "Please select an email to "
    if action == "inbox":
        prompt_text += "check its inbox:"
    elif action == "delete":
        prompt_text += "delete:"
        
    update.message.reply_text(prompt_text, reply_markup=reply_markup)

def inbox(update: Update, context: CallbackContext) -> None:
    """Prompts the user to select an email to view its inbox."""
    inbox_or_delete_prompt(update, context, "inbox")

def delete_email_prompt(update: Update, context: CallbackContext) -> None:
    """Prompts the user to select an email to delete."""
    inbox_or_delete_prompt(update, context, "delete")
    
def stats(update: Update, context: CallbackContext) -> None:
    """Shows bot statistics."""
    total_users, total_emails = db.get_stats()
    update.message.reply_text(
        f"📊 *Bot Statistics*\n\n"
        f"- *Active Users:* {total_users}\n"
        f"- *Total Active Emails:* {total_emails}",
        parse_mode=ParseMode.MARKDOWN
    )

def auto_cleanup_job(context: CallbackContext):
    """Job to periodically clean up old emails from the database."""
    logger.info("Running scheduled job: cleanup_old_emails")
    db.cleanup_old_emails()

def auto_check_new_mail_job(context: CallbackContext):
    """Job to periodically check for new emails for all users."""
    logger.info("Running scheduled job: check_new_emails")
    # This feature is complex to implement without spamming users.
    # A simple implementation:
    # 1. Get all emails from DB.
    # 2. For each email, get a token.
    # 3. Fetch messages.
    # 4. Compare with last known message list (stored in context.bot_data)
    # 5. If new message, send notification.
    # To avoid complexity in this example, we'll keep this disabled but show the structure.
    # Example:
    # all_emails = db.get_all_emails_for_checking()
    # for user_id, email, password in all_emails:
    #     token = mail.get_auth_token(email, password)
    #     messages = mail.get_messages(token)
    #     # ... logic to detect and send new mail notifications ...
    pass # Disabling for now


# --- CallbackQuery Handlers (for Inline Buttons) ---
def button_handler(update: Update, context: CallbackContext) -> None:
    """Parses the CallbackQuery and directs to the right function."""
    query = update.callback_query
    query.answer() # Acknowledge the button press
    
    data = query.data
    action, value = data.split(":", 1)

    if action == "delete":
        handle_delete_callback(query, context, value)
    elif action == "inbox":
        handle_inbox_callback(query, context, value)
    elif action == "view_msg":
        handle_view_message_callback(query, context, value)

def handle_delete_callback(query, context: CallbackContext, email_address: str):
    """Handles the deletion of an email after button press."""
    email_data = db.find_email(email_address)
    if not email_data:
        query.edit_message_text(text="❌ This email no longer exists.")
        return
    
    user_id, password, mail_gw_id = email_data
    token = mail.get_auth_token(email_address, password)
    
    if token:
        mail.delete_account_by_id(token, mail_gw_id) # API call
    
    db.delete_email(email_address) # DB call
    query.edit_message_text(text=f"✅ Successfully deleted `{email_address}`.", parse_mode=ParseMode.MARKDOWN)

def handle_inbox_callback(query, context: CallbackContext, email_address: str):
    """Shows the list of messages in the inbox."""
    email_data = db.find_email(email_address)
    if not email_data:
        query.edit_message_text(text="❌ This email no longer exists.")
        return
    
    _, password, _ = email_data
    token = mail.get_auth_token(email_address, password)

    if not token:
        query.edit_message_text(text="❌ Could not authenticate with the mail provider.")
        return

    messages = mail.get_messages(token)
    if not messages:
        query.edit_message_text(f"📥 Inbox for `{email_address}` is empty.", parse_mode=ParseMode.MARKDOWN)
        return

    message_list_text = f"📬 *Inbox for `{email_address}`:*\n\n"
    keyboard = []
    for msg in messages[:10]: # Show latest 10
        callback_data = f"view_msg:{msg['id']}|{email_address}"
        button_text = f"👤 {msg['from']['name']} | ር {msg['subject']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(message_list_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

def handle_view_message_callback(query, context: CallbackContext, value: str):
    """Displays the full content of a selected email."""
    message_id, email_address = value.split("|", 1)

    email_data = db.find_email(email_address)
    if not email_data:
        query.edit_message_text(text="❌ This email no longer exists.")
        return
        
    _, password, _ = email_data
    token = mail.get_auth_token(email_address, password)
    
    if not token:
        query.edit_message_text(text="❌ Could not authenticate.")
        return
    
    message_content = mail.get_message_by_id(token, message_id)
    if not message_content:
        query.edit_message_text(text="❌ Could not fetch message content.")
        return

    # Basic HTML tag stripping for clean display in Telegram
    content = message_content.get('text') or message_content.get('html', [''])[0]
    import re
    clean_content = re.sub('<[^<]+?>', '', content)

    full_message = (
        f"*From:* {message_content['from']['address']}\n"
        f"*To:* {', '.join([to['address'] for to in message_content['to']])}\n"
        f"*Subject:* {message_content['subject']}\n"
        f"*Date:* {message_content['createdAt']}\n\n"
        f"-----------------------------------------\n"
        f"{clean_content[:3000]}" # Truncate to avoid hitting Telegram limits
    )

    # Handle attachments
    attachments = message_content.get('attachments', [])
    keyboard = []
    if attachments:
        # Note: The mail.gw API doesn't provide direct download links.
        # This is a placeholder for how you would handle it.
        # For a real scenario, you'd need an API that gives a download URL.
        full_message += "\n\n*Attachments found (download not supported by API)*"

    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(full_message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)


# --- Main Application Logic ---
def main() -> None:
    """Start the bot."""
    # Initialize the database
    db.init_db()

    # Create the Updater and pass it your bot's token.
    updater = Updater(BOT_TOKEN)

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher
    
    # --- Job Queue for background tasks ---
    job_queue = updater.job_queue
    job_queue.run_repeating(auto_cleanup_job, interval=3600, first=10) # Run every hour
    # job_queue.run_repeating(auto_check_new_mail_job, interval=120, first=20) # Check every 2 mins

    # --- Conversation Handler for /custom command ---
    custom_email_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('custom', custom_email_start)],
        states={
            GET_CUSTOM_USERNAME: [MessageHandler(Filters.text & ~Filters.command, get_custom_username)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # --- Register all handlers ---
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("new", new_email))
    dispatcher.add_handler(custom_email_conv_handler)
    dispatcher.add_handler(CommandHandler("list", list_emails))
    dispatcher.add_handler(CommandHandler("inbox", inbox))
    dispatcher.add_handler(CommandHandler("delete", delete_email_prompt))
    dispatcher.add_handler(CommandHandler("stats", stats))
    dispatcher.add_handler(CallbackQueryHandler(button_handler))

    # Start the Bot using polling
    updater.start_polling()
    logger.info("Bot has started successfully.")

    # Block until you press Ctrl-C
    updater.idle()


# --- Render Deployment Web Server ---
# Render's web services need a port to bind to. We'll run a lightweight
# Flask app in a separate thread to satisfy this requirement.
app = Flask(__name__)

@app.route('/')
def index():
    return "Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

if __name__ == '__main__':
    # Run Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    
    # Run the bot in the main thread
    main()
