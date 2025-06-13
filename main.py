import os, requests, asyncio
from fastapi import FastAPI
import uvicorn

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 10000))

# === FastAPI app just to bind the port ===
fastapi_app = FastAPI()

@fastapi_app.get("/")
def root():
    return {"status": "Bot is running!"}

# === Telegram Bot ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎬 Send /anime <name> to watch an anime!")

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

# === Main startup ===
async def start_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("anime", anime))

    await app.initialize()
    await app.bot.set_webhook(url=WEBHOOK_URL)
    await app.start()
    print("✅ Webhook set and bot started!")

# Start both FastAPI + Telegram bot
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(start_bot())
    uvicorn.run(fastapi_app, host="0.0.0.0", port=PORT)
