import os
import requests
import asyncio
import logging
import urllib.parse
from fastapi import FastAPI, Request, HTTPException
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
import aiohttp
from typing import Optional, Dict, List

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load from environment
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# API URLs
JIKAN_API_BASE = "https://api.jikan.moe/v4"
ZORO_API_BASE = "https://consumet-api-0kir.onrender.com/anime/zoro"

# Validate environment variables
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL environment variable is required")

# Global variables
telegram_app = None
fastapi_app = FastAPI()

async def search_anime_jikan(query: str) -> Optional[List[Dict]]:
    """Search anime using Jikan API"""
    try:
        async with aiohttp.ClientSession() as session:
            # Add delay to respect rate limits
            await asyncio.sleep(1)
            async with session.get(
                f"{JIKAN_API_BASE}/anime",
                params={
                    "q": query,
                    "sfw": "true",  # Convert boolean to string
                    "limit": 5  # Limit results to 5
                }
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("data"):
                        return data["data"]
                    logger.error("No data found in Jikan API response")
                    return None
                logger.error(f"Jikan API error: {response.status}")
                return None
    except Exception as e:
        logger.error(f"Error searching Jikan API: {e}")
        return None

async def get_anime_details_jikan(anime_id: int) -> Optional[Dict]:
    """Get detailed anime information from Jikan API"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{JIKAN_API_BASE}/anime/{anime_id}/full") as response:
                if response.status == 200:
                    return await response.json()
                return None
    except Exception as e:
        logger.error(f"Error getting anime details from Jikan: {e}")
        return None

async def search_zoro(query: str) -> Optional[Dict]:
    """Search anime on Zoro"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{ZORO_API_BASE}/{query}") as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Zoro search response: {data}")
                    return data
                logger.error(f"Zoro search failed with status: {response.status}")
                return None
    except Exception as e:
        logger.error(f"Error searching Zoro: {e}")
        return None

async def get_streaming_links_zoro(anime_id: str) -> Optional[Dict]:
    """Get streaming links from Zoro API"""
    try:
        # First get the anime details from Jikan to get the title
        anime_details = await get_anime_details_jikan(int(anime_id))
        if not anime_details:
            return None
            
        title = anime_details['data']['title']
        logger.info(f"Searching Zoro for title: {title}")
        
        # Search for the anime on Zoro
        search_results = await search_zoro(title)
        if not search_results or not search_results.get("results"):
            logger.error(f"No results found on Zoro for: {title}")
            return None
            
        # Get the first result's ID
        first_result = search_results["results"][0]
        episode_id = first_result.get("id")
        if not episode_id:
            logger.error("No episode ID found in search results")
            return None
            
        logger.info(f"Found episode ID: {episode_id}")
        
        # Get streaming links using vidcloud server
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{ZORO_API_BASE}/watch",
                params={
                    "episodeId": episode_id,
                    "server": "vidcloud"
                }
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Got streaming data: {data}")
                    return data
                logger.error(f"Failed to get streaming links with status: {response.status}")
                return None
    except Exception as e:
        logger.error(f"Error getting streaming links from Zoro: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    try:
        welcome_text = (
            "🎬 Welcome to the Anime Bot!\n\n"
            "Commands:\n"
            "/anime <name> - Search for an anime\n"
            "/help - Show this help message\n\n"
            "Example: /anime naruto"
        )
        await update.message.reply_text(welcome_text)
        logger.info(f"Start command sent to user {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error in start command: {e}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    try:
        help_text = (
            "🎬 *Anime Bot Help*\n\n"
            "*Available Commands:*\n"
            "• /start - Start the bot\n"
            "• /help - Show this help message\n"
            "• /anime <name> - Search for an anime\n\n"
            "*How to use:*\n"
            "1. Use /anime followed by the anime name\n"
            "2. Select from the search results\n"
            "3. Click 'Watch' to get the streaming link\n"
            "4. Click 'More Info' for detailed information\n\n"
            "*Example:*\n"
            "/anime naruto\n"
            "/anime one piece\n"
            "/anime demon slayer"
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')
        logger.info(f"Help command sent to user {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error in help command: {e}")

async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /anime command"""
    try:
        if not context.args:
            await update.message.reply_text(
                "❗ Usage: /anime <name>\nExample: /anime naruto",
                parse_mode='Markdown'
            )
            return
        
        query = " ".join(context.args)
        logger.info(f"Anime search request: {query}")
        
        # Send "searching..." message
        searching_msg = await update.message.reply_text("🔍 Searching for anime...")
        
        # Search using Jikan API
        anime_list = await search_anime_jikan(query)
        
        if not anime_list or len(anime_list) == 0:
            await searching_msg.edit_text(
                "❌ No anime found. Please try:\n"
                "• Check the spelling\n"
                "• Use English titles\n"
                "• Try alternative names\n"
                "Example: /anime naruto shippuden"
            )
            return
        
        # Create message with search results
        results_text = "🎬 *Search Results:*\n\n"
        keyboard = []
        
        for idx, anime in enumerate(anime_list[:5], 1):
            title = anime["title"]
            year = anime.get("year", "N/A")
            score = anime.get("score", "N/A")
            results_text += f"{idx}. *{title}* ({year}) - ⭐ {score}\n"
            keyboard.append([InlineKeyboardButton(f"Select {title[:20]}...", callback_data=f"select_{anime['mal_id']}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await searching_msg.edit_text(results_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in anime command handler: {e}")
        await searching_msg.edit_text("❌ An error occurred. Please try again later.")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    try:
        action, anime_id = query.data.split('_')
        
        if action == "select":
            # Get detailed information
            details = await get_anime_details_jikan(int(anime_id))
            
            if not details:
                await query.edit_message_text(
                    "❌ Error getting anime details. Please try again.",
                    parse_mode='Markdown'
                )
                return
            
            info_text = (
                f"🎬 *{details['data']['title']}*\n\n"
                f"📝 *Synopsis:*\n{details['data']['synopsis'][:300]}...\n\n"
                f"⭐ *Score:* {details['data']['score']}\n"
                f"📊 *Status:* {details['data']['status']}\n"
                f"🎭 *Genres:* {', '.join(genre['name'] for genre in details['data']['genres'])}\n\n"
                f"Would you like to watch this anime?"
            )
            
            keyboard = [
                [
                    InlineKeyboardButton("▶️ Watch", callback_data=f"watch_{anime_id}"),
                    InlineKeyboardButton("ℹ️ More Info", callback_data=f"info_{anime_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(info_text, reply_markup=reply_markup, parse_mode='Markdown')
            
        elif action == "watch":
            # Show loading message
            await query.edit_message_text("🔍 Searching for streaming links...", parse_mode='Markdown')
            
            # Try to get streaming links from Zoro
            stream_data = await get_streaming_links_zoro(anime_id)
            
            if not stream_data or not stream_data.get("sources"):
                await query.edit_message_text(
                    "❌ Sorry, streaming is not available at the moment. Please try again later.",
                    parse_mode='Markdown'
                )
                return
            
            # Get the first available source
            sources = stream_data["sources"]
            if not sources:
                await query.edit_message_text(
                    "❌ No streaming sources found. Please try again later.",
                    parse_mode='Markdown'
                )
                return
                
            video_url = sources[0]["url"]
            player_url = f"https://animep.onrender.com/watch?src={urllib.parse.quote(video_url)}"
            
            await query.edit_message_text(
                f"▶️ Click the link below to watch:\n{player_url}",
                parse_mode='Markdown'
            )
            
        elif action == "info":
            # Get more detailed information
            details = await get_anime_details_jikan(int(anime_id))
            
            if not details:
                await query.edit_message_text(
                    "❌ Error getting anime details. Please try again.",
                    parse_mode='Markdown'
                )
                return
            
            info_text = (
                f"🎬 *{details['data']['title']}*\n\n"
                f"📝 *Full Synopsis:*\n{details['data']['synopsis']}\n\n"
                f"⭐ *Score:* {details['data']['score']}\n"
                f"📊 *Status:* {details['data']['status']}\n"
                f"🎭 *Genres:* {', '.join(genre['name'] for genre in details['data']['genres'])}\n"
                f"📅 *Aired:* {details['data']['aired']['string']}\n"
                f"📺 *Episodes:* {details['data']['episodes']}\n"
                f"⏱️ *Duration:* {details['data']['duration']}\n"
                f"📌 *Rating:* {details['data']['rating']}\n"
            )
            
            keyboard = [[InlineKeyboardButton("▶️ Watch", callback_data=f"watch_{anime_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(info_text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error in button callback: {e}")
        await query.edit_message_text(
            "❌ An error occurred. Please try again.",
            parse_mode='Markdown'
        )

async def initialize_telegram_app():
    """Initialize the Telegram application"""
    global telegram_app
    
    try:
        # Create application
        telegram_app = Application.builder().token(BOT_TOKEN).build()
        
        # Add handlers
        telegram_app.add_handler(CommandHandler("start", start))
        telegram_app.add_handler(CommandHandler("help", help_command))
        telegram_app.add_handler(CommandHandler("anime", anime))
        telegram_app.add_handler(CallbackQueryHandler(button_callback))
        
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
