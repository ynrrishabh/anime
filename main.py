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
        
        # Search for anime (using URL encoding for better compatibility)
        import urllib.parse
        encoded_query = urllib.parse.quote(query)
        search_url = f"https://consumet-api-0kir.onrender.com/anime/gogoanime/{encoded_query}"
        
        # Search for anime (trying multiple endpoint formats)
        import urllib.parse
        encoded_query = urllib.parse.quote(query)
        
        # Try different API endpoint formats
        endpoints_to_try = [
            f"https://consumet-api-0kir.onrender.com/anime/gogoanime/{encoded_query}",
            f"https://consumet-api-0kir.onrender.com/anime/gogoanime?query={encoded_query}",
            f"https://consumet-api-0kir.onrender.com/anime/gogoanime/search?query={encoded_query}",
        ]
        
        anime_list = None
        working_url = None
        
        for search_url in endpoints_to_try:
            try:
                response = requests.get(search_url, timeout=15)
                logger.info(f"Trying URL: {search_url}")
                logger.info(f"API Response Status: {response.status_code}")
                logger.info(f"API Response Content: {response.text[:500]}...")
                
                if response.status_code != 200:
                    continue
                    
                res = response.json()
                logger.info(f"Parsed JSON structure: {type(res)} - {list(res.keys()) if isinstance(res, dict) else f'Length: {len(res) if isinstance(res, list) else 'Not list/dict'}'}")
                
                # Check if this response contains anime data
                if isinstance(res, dict) and ('intro' in res and 'routes' in res):
                    # This is the documentation response, try next endpoint
                    logger.info("Got documentation response, trying next endpoint...")
                    continue
                
                # Handle different response formats
                if isinstance(res, dict):
                    # If it's a dict, check for results key
                    if 'results' in res:
                        anime_list = res['results']
                        working_url = search_url
                        break
                    elif 'data' in res:
                        anime_list = res['data']
                        working_url = search_url
                        break
                elif isinstance(res, list) and len(res) > 0:
                    # Check if first item looks like anime data
                    if isinstance(res[0], dict) and 'id' in res[0] and 'title' in res[0]:
                        anime_list = res
                        working_url = search_url
                        break
                        
            except Exception as e:
                logger.error(f"Error with endpoint {search_url}: {e}")
                continue
        
        if not anime_list:
            await searching_msg.edit_text("❌ All API endpoints failed or returned no results. The API might be down.")
            return
        
        if len(anime_list) == 0:
            await searching_msg.edit_text("❌ No anime found with that name.")
            return
            
        logger.info(f"Successfully got anime list from: {working_url}")
        anime_id = anime_list[0]["id"]
        title = anime_list[0]["title"]
            
            # Update message
            await searching_msg.edit_text("📺 Found anime! Getting episode info...")
            
            # Fetch episode info
            ep_response = requests.get(
                f"https://consumet-api-0kir.onrender.com/anime/gogoanime/info/{anime_id}", 
                timeout=15
            )
            logger.info(f"Episode API Response Status: {ep_response.status_code}")
            logger.info(f"Episode API Response: {ep_response.text[:300]}...")
            
            ep_data = ep_response.json()
            
            # Handle different episode data formats
            episodes = None
            if isinstance(ep_data, dict):
                if 'episodes' in ep_data:
                    episodes = ep_data['episodes']
                elif 'data' in ep_data and isinstance(ep_data['data'], dict) and 'episodes' in ep_data['data']:
                    episodes = ep_data['data']['episodes']
                elif 'episodesList' in ep_data:
                    episodes = ep_data['episodesList']
            
            if not episodes or len(episodes) == 0:
                await searching_msg.edit_text("❌ No episodes found for this anime.")
                return
                
            first_ep_id = episodes[0]["id"]
            
            # Update message
            await searching_msg.edit_text("🎮 Getting stream link...")
            
            # Get stream source
            stream_response = requests.get(
                f"https://consumet-api-0kir.onrender.com/anime/gogoanime/watch/{first_ep_id}",
                timeout=15
            )
            logger.info(f"Stream API Response Status: {stream_response.status_code}")
            logger.info(f"Stream API Response: {stream_response.text[:300]}...")
            
            stream_data = stream_response.json()
            
            # Handle different stream data formats
            sources = None
            if isinstance(stream_data, dict):
                if 'sources' in stream_data:
                    sources = stream_data['sources']
                elif 'data' in stream_data and isinstance(stream_data['data'], dict) and 'sources' in stream_data['data']:
                    sources = stream_data['data']['sources']
                elif 'streamingLinks' in stream_data:
                    sources = stream_data['streamingLinks']
            
            if not sources or len(sources) == 0:
                await searching_msg.edit_text("❌ No stream source found for this episode.")
                return
                
            video_url = sources[0]["url"]
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
