import os, requests, asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# Load environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Example: https://your-bot.onrender.com
PORT = int(os.getenv("PORT", 10000))    # Default to 10000 if not set

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎬 Send /anime <name> to watch an anime!")

# /anime command
async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Usage: /anime naruto")
        return

    query = " ".join(context.args)
    search_url = f"https://consumet-api-0kir.onrender.com/anime/gogoanime/{query}"
    
    try:
        res = requests.get(search_url).json()
        anime_id = res[0]["id"]
        title = res[0]["title"]

        ep_data = requests.get(f"https://consumet-api-0kir.onrender.com/anime/gogoanime/info/{anime_id}").json()
        first_ep_id = ep_data["episodes"][0]["id"]

        stream_data = requests.get(f"https://consumet-api-0kir.onrender.com/anime/gogoanime/watch/{first_ep_id}").json()
        video_link = stream_data["sources"][0]["url"]

        player_url = f"https://animep.onrender.com/watch?src={video_link}"
        await update.message.reply_text(f"▶️ {title} - Episode 1\n🔗 {player_url}")

    except Exception as e:
        await update.message.reply_text("❌ Anime not found or API error.")
        print(f"Error: {e}")

# Start the bot with webhook
if __name__ == "__main__":
    async def main():
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("anime", anime))

        await app.initialize()
        await app.bot.set_webhook(url=WEBHOOK_URL)
        await app.start()
        await app.updater.start_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path="",
            webhook_url=WEBHOOK_URL
        )
        print(f"🚀 Bot running on port {PORT} with webhook set to {WEBHOOK_URL}")
        await app.updater.idle()

    asyncio.run(main())
