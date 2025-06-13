import os
import logging
import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# Logging
logging.basicConfig(level=logging.INFO)

# Your bot token from environment variable
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Your hosted Consumet API
API_BASE = "https://consumet-api-0kir.onrender.com/anime/gogoanime"

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Send /anime <name> to search for anime.\nExample: /anime naruto")

# /anime command
async def anime_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Usage: /anime <anime name>")
        return

    query = " ".join(context.args)
    search_url = f"{API_BASE}/{query}"

    try:
        response = requests.get(search_url).json()
        if not response:
            await update.message.reply_text("❌ No anime found.")
            return

        keyboard = [
            [InlineKeyboardButton(anime['title'], callback_data=anime['id'])]
            for anime in response[:10]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("🎬 Select an anime:", reply_markup=reply_markup)

    except Exception as e:
        logging.error(e)
        await update.message.reply_text("❌ Error fetching anime.")

# Handle episode list after user clicks anime
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    anime_id = query.data
    info_url = f"{API_BASE}/info/{anime_id}"

    try:
        response = requests.get(info_url).json()
        episodes = response.get("episodes", [])[:10]

        if not episodes:
            await query.edit_message_text("❌ No episodes found.")
            return

        msg = f"🎥 *{response['title']}* - Episodes:\n\n"
        for ep in episodes:
            ep_url = f"https://animep.onrender.com/stream/{ep['id']}"
            msg += f"▶️ [{ep['number']}]({ep_url})\n"

        await query.edit_message_text(msg, parse_mode="Markdown", disable_web_page_preview=True)

    except Exception as e:
        logging.error(e)
        await query.edit_message_text("❌ Error loading episodes.")

# Set up the bot
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("anime", anime_search))
app.add_handler(CallbackQueryHandler(button_handler))

# Run bot
if __name__ == "__main__":
    app.run_polling()
