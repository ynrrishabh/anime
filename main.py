import os
import asyncio
import requests
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Load tokens and URLs from environment
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g., "https://your-app-name.onrender.com"

# FastAPI app
fastapi_app = FastAPI()

# Initialize Telegram bot app
app = ApplicationBuilder().token(BOT_TOKEN).build()

# --- Command Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎬 Send /anime <name> to watch an anime!")

async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Usage: /anime <name>")
        return

    query = " ".join(context.args)
    search_url = f"https://consumet-api-0kir.onrender.com/anime/gogoanime/{query}"

    try:
        res = requests.get(search_url).json()
        anime_id = res[0]["id"]
        title = res[0]["title"]

        # Get episode info
        ep_data = requests.get(f"https://consumet-api-0kir.onrender.com/anime/gogoanime/info/{anime_id}").json()
        first_ep_id = ep_data["episodes"][0]["id"]

        # Get stream source
        stream_data = requests.get(f"https://consumet-api-0kir.onrender.com/anime/gogoanime/watch/{first_ep_id}").json()
        video_url = stream_data["sources"][0]["url"]

        player_url = f"https://animep.onrender.com/watch?src={video_url}"
        await update.message.reply_text(f"▶️ {title} - Episode 1\n🔗 {player_url}")

    except Exception as e:
        await update.message.reply_text("❌ Anime not found or error occurred.")
        print("Error:", e)

# Register handlers
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("anime", anime))

# --- FastAPI Routes ---

@fastapi_app.get("/")
def root():
    return {"status": "Bot is running!"}

@fastapi_app.post("/")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, app.bot)
    await app.update_queue.put(update)
    return {"status": "received"}

# --- Main App Runner ---

async def main():
    await app.initialize()
    await app.bot.set_webhook(WEBHOOK_URL)
    await app.start()
    print(f"✅ Bot is live with webhook set to: {WEBHOOK_URL}")

# Entry point
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(main())

    import uvicorn
    uvicorn.run(fastapi_app, host="0.0.0.0", port=10000)
