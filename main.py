import os
import requests
import asyncio
import logging
from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load from environment
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Validate environment variables
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL environment variable is required")

# Global variables
telegram_app = None
fastapi_app = FastAPI()

# Telegram command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    try:
        await update.message.reply_text("🎬 Send /anime <name> to watch an anime!")
        logger.info(f"Start command sent to user {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error in start command: {e}")

async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /anime command"""
    try:
        if not context.args:
            await update.message.reply_text("❗ Usage: /anime <name>")
            return
        
        query = " ".join(context.args)
        logger.info(f"Anime search request: {query}")
        
        # Send "searching..." message
        searching_msg = await update.message.reply_text("🔍 Searching for anime...")
        
        # Search for anime
        search_url = f"https://consumet-api-0kir.onrender.com/anime/gogoanime/{query}"
        
        try:
            res = requests.get(search_url, timeout=15).json()
            
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
                timeout=15
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
                timeout=15
            ).json()
            
            if not stream_data.get("sources") or len(stream_data["sources"]) == 0:
                await searching_msg.edit_text("❌ No stream source found for this episode.")
                return
                
            video_url = stream_data["sources"][0]["url"]
            player_url = f"https://animep.onrender.com/watch?src={video_url}"
            
            await searching_msg.edit_text(f"▶️ {title} - Episode 1\n🔗 {player_url}")
            logger.info(f"Successfully processed anime request: {title}")
            
        except requests.exceptions.Timeout:
            await searching_msg.edit_text("❌ Request timeout. Please try again later.")
            logger.error("API request timeout")
        except requests.exceptions.RequestException as e:
            await searching_msg.edit_text("❌ Network error occurred. Please try again later.")
            logger.error(f"Network error: {e}")
        except KeyError as e:
            await searching_msg.edit_text("❌ Unexpected response format from API.")
            logger.error(f"KeyError: {e}")
        except Exception as e:
            await searching_msg.edit_text("❌ An error occurred. Please try again later.")
            logger.error(f"Unexpected error in anime command: {e}")
            
    except Exception as e:
        logger.error(f"Error in anime command handler: {e}")

async def initialize_telegram_app():
    """Initialize the Telegram application"""
    global telegram_app
    
    try:
        # Create application
        telegram_app = Application.builder().token(BOT_TOKEN).build()
        
        # Add handlers
        telegram_app.add_handler(CommandHandler("start", start))
        telegram_app.add_handler(CommandHandler("anime", anime))
        
        # Initialize the application
        await telegram_app.initialize()
        await telegram_app.start()
        
        # Set webhook
        webhook_info = await telegram_app.bot.get_webhook_info()
        if webhook_info.url != WEBHOOK_URL:
            await telegram_app.bot.set_webhook(WEBHOOK_URL)
            logger.info(f"Webhook set to: {WEBHOOK_URL}")
        else:
            logger.info("Webhook already set correctly")
            
        # Get bot info
        bot_info = await telegram_app.bot.get_me()
        logger.info(f"Bot initialized successfully: @{bot_info.username}")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize Telegram app: {e}")
        return False

# FastAPI endpoints
@fastapi_app.get("/")
async def root():
    """Root endpoint for health checks"""
    if telegram_app and telegram_app.running:
        bot_info = await telegram_app.bot.get_me()
        return {
            "status": "Bot is running!",
            "bot_username": f"@{bot_info.username}",
            "webhook_url": WEBHOOK_URL
        }
    else:
        return {"status": "Bot is starting up..."}

@fastapi_app.post("/")
async def telegram_webhook(request: Request):
    """Handle incoming webhook updates from Telegram"""
    global telegram_app
    
    if not telegram_app or not telegram_app.running:
        logger.error("Telegram app not initialized")
        raise HTTPException(status_code=500, detail="Bot not initialized")
    
    try:
        # Get the JSON data from the request
        json_data = await request.json()
        logger.info(f"Received webhook update: {json_data.get('update_id', 'unknown')}")
        
        # Create Update object from the JSON data
        update = Update.de_json(json_data, telegram_app.bot)
        
        if update:
            # Process the update
            await telegram_app.process_update(update)
            logger.info("Update processed successfully")
        else:
            logger.warning("Failed to create Update object from JSON")
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return {"status": "error", "message": str(e)}

@fastapi_app.get("/health")
async def health_check():
    """Health check endpoint"""
    if telegram_app and telegram_app.running:
        return {"status": "healthy", "bot_running": True}
    else:
        return {"status": "unhealthy", "bot_running": False}

@fastapi_app.get("/webhook-info")
async def webhook_info():
    """Get current webhook information"""
    if telegram_app and telegram_app.running:
        try:
            webhook_info = await telegram_app.bot.get_webhook_info()
            return {
                "url": webhook_info.url,
                "has_custom_certificate": webhook_info.has_custom_certificate,
                "pending_update_count": webhook_info.pending_update_count,
                "last_error_date": webhook_info.last_error_date,
                "last_error_message": webhook_info.last_error_message,
                "max_connections": webhook_info.max_connections,
                "allowed_updates": webhook_info.allowed_updates
            }
        except Exception as e:
            return {"error": str(e)}
    else:
        return {"error": "Bot not initialized"}

# Startup event
@fastapi_app.on_event("startup")
async def startup_event():
    """Initialize the bot when FastAPI starts"""
    logger.info("FastAPI startup - initializing Telegram bot...")
    success = await initialize_telegram_app()
    if success:
        logger.info("✅ Telegram bot initialized successfully!")
    else:
        logger.error("❌ Failed to initialize Telegram bot!")

# Shutdown event
@fastapi_app.on_event("shutdown")
async def shutdown_event():
    """Clean shutdown of the bot"""
    global telegram_app
    if telegram_app:
        logger.info("Shutting down Telegram bot...")
        await telegram_app.stop()
        await telegram_app.shutdown()
        logger.info("Telegram bot shut down successfully")

# Main execution
if __name__ == "__main__":
    import uvicorn
    logger.info("🚀 Starting anime bot server...")
    uvicorn.run(
        fastapi_app, 
        host="0.0.0.0", 
        port=10000,
        log_level="info"
    )
