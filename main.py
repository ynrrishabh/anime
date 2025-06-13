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
ANILIST_API = "https://graphql.anilist.co"
GOGOANIME_API_BASE = "https://api.consumet.org/anime/gogoanime"

# GraphQL query for AniList
ANILIST_QUERY = """
query ($search: String) {
  Page(page: 1, perPage: 5) {
    media(search: $search, type: ANIME) {
      id
      title {
        romaji
        english
      }
      coverImage {
        large
      }
      description
      averageScore
      status
      genres
      episodes
      duration
      format
      startDate {
        year
        month
        day
      }
    }
  }
}
"""

# Validate environment variables
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL environment variable is required")

# Global variables
telegram_app = None
fastapi_app = FastAPI()

async def search_anime_anilist(query: str) -> Optional[List[Dict]]:
    """Search anime using AniList API"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                ANILIST_API,
                json={
                    "query": ANILIST_QUERY,
                    "variables": {"search": query}
                }
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("data", {}).get("Page", {}).get("media", [])
                logger.error(f"AniList API error: {response.status}")
                return None
    except Exception as e:
        logger.error(f"Error searching AniList API: {e}")
        return None

async def get_anime_details_anilist(anime_id: int) -> Optional[Dict]:
    """Get detailed anime information from AniList API"""
    try:
        query = """
        query ($id: Int) {
          Media(id: $id, type: ANIME) {
            id
            title {
              romaji
              english
            }
            description
            coverImage {
              large
            }
            bannerImage
            averageScore
            status
            genres
            episodes
            duration
            format
            startDate {
              year
              month
              day
            }
            endDate {
              year
              month
              day
            }
            studios {
              nodes {
                name
              }
            }
          }
        }
        """
        async with aiohttp.ClientSession() as session:
            async with session.post(
                ANILIST_API,
                json={
                    "query": query,
                    "variables": {"id": anime_id}
                }
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("data", {}).get("Media")
                return None
    except Exception as e:
        logger.error(f"Error getting anime details from AniList: {e}")
        return None

async def get_streaming_links_gogoanime(title: str) -> Optional[Dict]:
    """Get streaming links from Gogoanime API"""
    try:
        # Search for the anime on Gogoanime
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{GOGOANIME_API_BASE}/search",
                params={"query": title}
            ) as response:
                if response.status == 200:
                    search_data = await response.json()
                    if not search_data.get("results"):
                        logger.error(f"No results found on Gogoanime for: {title}")
                        return None
                    
                    # Get the first result's ID
                    gogo_id = search_data["results"][0]["id"]
                    logger.info(f"Found Gogoanime ID: {gogo_id}")
                    
                    # Get streaming links
                    async with session.get(f"{GOGOANIME_API_BASE}/watch/{gogo_id}") as watch_response:
                        if watch_response.status == 200:
                            return await watch_response.json()
                        logger.error(f"Failed to get streaming links with status: {watch_response.status}")
                        return None
                logger.error(f"Gogoanime search failed with status: {response.status}")
                return None
    except Exception as e:
        logger.error(f"Error getting streaming links from Gogoanime: {e}")
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
            "3. Click 'Watch' to get the video\n"
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
        
        # Search using AniList API
        anime_list = await search_anime_anilist(query)
        
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
            title = anime["title"]["english"] or anime["title"]["romaji"]
            score = anime.get("averageScore", "N/A")
            if score != "N/A":
                score = f"{score/10:.1f}"
            year = anime.get("startDate", {}).get("year", "N/A")
            results_text += f"{idx}. *{title}* ({year}) - ⭐ {score}\n"
            keyboard.append([InlineKeyboardButton(f"Select {title[:20]}...", callback_data=f"select_{anime['id']}")])
        
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
            details = await get_anime_details_anilist(int(anime_id))
            
            if not details:
                await query.edit_message_text(
                    "❌ Error getting anime details. Please try again.",
                    parse_mode='Markdown'
                )
                return
            
            title = details["title"]["english"] or details["title"]["romaji"]
            description = details.get("description", "No description available.")
            score = details.get("averageScore", "N/A")
            if score != "N/A":
                score = f"{score/10:.1f}"
            
            info_text = (
                f"🎬 *{title}*\n\n"
                f"📝 *Synopsis:*\n{description[:300]}...\n\n"
                f"⭐ *Score:* {score}\n"
                f"📊 *Status:* {details['status']}\n"
                f"🎭 *Genres:* {', '.join(details['genres'])}\n\n"
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
            
            # Get anime details to get the title
            details = await get_anime_details_anilist(int(anime_id))
            if not details:
                await query.edit_message_text(
                    "❌ Error getting anime details. Please try again.",
                    parse_mode='Markdown'
                )
                return
            
            title = details["title"]["english"] or details["title"]["romaji"]
            
            # Try to get streaming links from Gogoanime
            stream_data = await get_streaming_links_gogoanime(title)
            
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
            
            # Send video directly to Telegram
            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=video_url,
                caption=f"🎬 Here's your anime episode!\n\nClick the video to play directly in Telegram."
            )
            
            # Delete the previous message
            await query.message.delete()
            
        elif action == "info":
            # Get more detailed information
            details = await get_anime_details_anilist(int(anime_id))
            
            if not details:
                await query.edit_message_text(
                    "❌ Error getting anime details. Please try again.",
                    parse_mode='Markdown'
                )
                return
            
            title = details["title"]["english"] or details["title"]["romaji"]
            description = details.get("description", "No description available.")
            score = details.get("averageScore", "N/A")
            if score != "N/A":
                score = f"{score/10:.1f}"
            
            start_date = details.get("startDate", {})
            end_date = details.get("endDate", {})
            aired = f"{start_date.get('year', '?')}"
            if end_date.get("year"):
                aired += f" - {end_date.get('year')}"
            
            studios = [studio["name"] for studio in details.get("studios", {}).get("nodes", [])]
            
            info_text = (
                f"🎬 *{title}*\n\n"
                f"📝 *Full Synopsis:*\n{description}\n\n"
                f"⭐ *Score:* {score}\n"
                f"📊 *Status:* {details['status']}\n"
                f"🎭 *Genres:* {', '.join(details['genres'])}\n"
                f"📅 *Aired:* {aired}\n"
                f"📺 *Episodes:* {details.get('episodes', 'N/A')}\n"
                f"⏱️ *Duration:* {details.get('duration', 'N/A')} min\n"
                f"🎨 *Format:* {details.get('format', 'N/A')}\n"
                f"🎬 *Studios:* {', '.join(studios) if studios else 'N/A'}\n"
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
