import os, requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("8019727601:AAG78lFk_UT5mAi2Mi2Y9E9XiHD-KkRBJx4")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎬 Send /anime <name> to watch an anime!")

async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Usage: /anime naruto")
        return

    query = " ".join(context.args)
    search_url = f"https://api.consumet.org/anime/gogoanime/{query}"
    
    try:
        res = requests.get(search_url).json()
        anime_id = res[0]["id"]
        title = res[0]["title"]
        
        # Get episode info
        ep_data = requests.get(f"https://api.consumet.org/anime/gogoanime/info/{anime_id}").json()
        first_ep_id = ep_data["episodes"][0]["id"]
        
        # Get stream link
        stream_data = requests.get(f"https://api.consumet.org/anime/gogoanime/watch/{first_ep_id}").json()
        video_link = stream_data["sources"][0]["url"]
        
        player_url = f"https://animep.onrender.com/watch?src={video_link}"
        await update.message.reply_text(f"▶️ {title} - Episode 1\n🔗 {player_url}")
    
    except Exception as e:
        await update.message.reply_text("❌ Anime not found or API error.")
        print(f"Error: {e}")

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("anime", anime))

if __name__ == "__main__":
    app.run_polling()
