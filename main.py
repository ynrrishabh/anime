import os
import requests
import asyncio
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Load from environment
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g., "https://your-app-name.onrender.com"

# Validate environment variables
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL environment variable is required")

fastapi_app = FastAPI()

# Telegram command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎬 Send /anime <name> to watch an anime!")

async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Usage: /anime <name>")
        return
    
    query = " ".join(context.args)
    search_url = f"https://consumet-api-0kir.onrender.com/anime/gogoanime/{query}"
    
    # Send "searching..." message
    searching_msg = await update.message.reply_text("🔍 Searching for anime...")
    
    try:
        # Search for anime
        res = requests.get(search_url, timeout=10).json()
        
        if not res or len(res) == 0:
            await searching_msg.edit_text("❌ No anime found with that name.")
            return
            
        anime_id = res[0]["id"]
        title = res[0]["title"]
        
        # Update message
        await searching_msg.edit_text("📺 Found anime! Getting episode info...")
        
        # Fetch episode info
        ep_data = requests.get(
            f"https://consumet-api-0kir.onrender.com/anime/gogoanime/info/{anime_id}", 
            timeout=10
        ).json()
        
        if not ep_data.get("episodes") or len(ep_data["episodes"]) == 0:
            await searching_msg.edit_text("❌ No episodes found for this anime.")
            return
            
        first_ep_id = ep_data["episodes"][0]["id"]
        
        # Update message
        await searching_msg.edit_text("🎮 Getting stream link...")
        
        # Get stream source
        stream_data = requests.get(
            f"https://consumet-api-0kir.onrender.com/anime/gogoanime/watch/{first_ep_id}",
            timeout=10
        ).json()
        
        if not stream_data.get("sources") or len(stream_data["sources"]) == 0:
            await searching_msg.edit_text("❌ No stream source found for this episode.")
            return
            
        video_url = stream_data["sources"][0]["url"]
        player_url = f"https://animep.onrender.com/watch?src={video_url}"
        
        await searching_msg.edit_text(f"▶️ {title} - Episode 1\n🔗 {player_url}")
        
    except requests.exceptions.Timeout:
        await searching_msg.edit_text("❌ Request timeout. Please try again later.")
        print("Request timeout occurred")
    except requests.exceptions.RequestException as e:
        await searching_msg.edit_text("❌ Network error occurred. Please try again later.")
        print("Network error:", e)
    except KeyError as e:
        await searching_msg.edit_text("❌ Unexpected response format from API.")
        print("KeyError:", e)
    except Exception as e:
        await searching_msg.edit_text("❌ An error occurred. Please try again later.")
        print("Unexpected error:", e)

# Telegram app setup
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("anime", anime))

# FastAPI endpoints
@fastapi_app.get("/")
def root():
    return {"status": "Bot is running!", "webhook_url": WEBHOOK_URL}

@fastapi_app.post("/")
async def telegram_webhook(request: Request):
    """Handle incoming webhook updates from Telegram"""
    try:
        # Get the JSON data from the request
        json_data = await request.json()
        
        # Create Update object from the JSON data
        update = Update.de_json(json_data, app.bot)
        
        # Process the update
        await app.process_update(update)
        
        return {"status": "ok"}
    except Exception as e:
        print(f"Error processing webhook: {e}")
        return {"status": "error", "message": str(e)}

# Health check endpoint (useful for monitoring)
@fastapi_app.get("/health")
def health_check():
    return {"status": "healthy", "bot_username": app.bot.username if hasattr(app.bot, 'username') else "unknown"}

# Main async function
async def setup_bot():
    """Initialize and start the bot"""
    try:
        # Initialize the application
        await app.initialize()
        await app.start()
        
        # Set the webhook
        webhook_set = await app.bot.set_webhook(WEBHOOK_URL)
        
        if webhook_set:
            print(f"✅ Bot started successfully!")
            print(f"🔗 Webhook URL: {WEBHOOK_URL}")
            print(f"🤖 Bot username: @{app.bot.username}")
        else:
            print("❌ Failed to set webhook")
            
    except Exception as e:
        print(f"❌ Error setting up bot: {e}")
        raise

# Start everything
if __name__ == "__main__":
    # Create event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Setup bot in the background
    loop.create_task(setup_bot())
    
    # Start FastAPI server
    import uvicorn
    print("🚀 Starting FastAPI server...")
    uvicorn.run(fastapi_app, host="0.0.0.0", port=10000)
