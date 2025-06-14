import os
import logging
from fastapi import FastAPI, Request, HTTPException
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
import aiohttp
from bs4 import BeautifulSoup
import re
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL environment variable is required")

ANIMESALT_BASE = "https://animesalt.cc"

telegram_app = None
fastapi_app = FastAPI()

async def search_animesalt(query: str):
    """Scrape animesalt.cc for series matching the query."""
    url = f"{ANIMESALT_BASE}/?s={query.replace(' ', '+')}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.error(f"Failed to fetch search page: {resp.status}")
                    return []
                html = await resp.text()
        soup = BeautifulSoup(html, "html.parser")
        ul = soup.find("ul", class_="post-lst")
        if not ul:
            return []
        results = []
        for li in ul.find_all("li", recursive=False):
            a = li.find("a", href=True)
            if not a:
                continue
            # Try to get title from img alt first
            img = a.find("img", alt=True)
            title = img["alt"] if img and img.has_attr("alt") else None
            
            # If no img alt, try to get from title attribute
            if not title:
                title = a.get("title")
            
            # If still no title, try to get from text content
            if not title:
                title = a.text.strip()
            
            # If all else fails, use the URL as a fallback
            if not title:
                title = a["href"].split("/")[-2].replace("-", " ").title()
            
            url = a["href"]
            results.append({"title": title, "url": url})
        return results
    except Exception as e:
        logger.error(f"Error scraping animesalt.cc: {e}")
        return []

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    try:
        help_text = (
            "🎬 *Anime Bot Help*\n\n"
            "*Available Commands:*\n"
            "• /start - Start the bot\n"
            "• /help - Show this help message\n"
            "• /anime <name> - Search for an anime\n\n"
            "*How to use:*\n"
            "1. Use /anime followed by the anime name\n"
            "2. Select from the search results\n\n"
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
    if not context.args:
        await update.message.reply_text("❗ Usage: /anime <name>\nExample: /anime naruto")
        return
    query = " ".join(context.args)
    msg = await update.message.reply_text("🔍 Searching for anime...")
    results = await search_animesalt(query)
    if not results:
        await msg.edit_text("❌ No series found. Please check the name and try again.")
        return
    keyboard = []
    for r in results:
        parsed = urlparse(r["url"])
        path = parsed.path  # e.g., /series/demon-slayer/
        keyboard.append([InlineKeyboardButton(r["title"], callback_data=f"series:{path}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await msg.edit_text("🎬 *Select a series:*", reply_markup=reply_markup, parse_mode='Markdown')

async def scrape_series_details(series_url: str):
    """Scrape the series page for overview, details, and available seasons."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(series_url) as resp:
                if resp.status != 200:
                    logger.error(f"Failed to fetch series page: {resp.status}")
                    return None
                html = await resp.text()
        soup = BeautifulSoup(html, "html.parser")
        # Overview
        overview = None
        overview_div = soup.find("div", id="overview-text")
        if overview_div:
            p = overview_div.find("p")
            if p:
                overview = p.get_text(strip=True)
        # Details block
        details_div = soup.find("div", style=re.compile(r"flex-wrap: wrap"))
        details = []
        if details_div:
            for child in details_div.find_all("div", recursive=False):
                text = child.get_text(" ", strip=True)
                if text:
                    details.append(text)
        # Seasons
        seasons = []
        season_header = soup.find("div", class_="choose-season")
        if season_header:
            ul = season_header.find("ul", class_="aa-cnt")
            if ul:
                for li in ul.find_all("li"):
                    a = li.find("a", attrs={"data-season": True, "data-post": True})
                    if a:
                        season_num = a["data-season"]
                        season_label = a.text.strip()
                        post_id = a["data-post"]
                        seasons.append({"season": season_num, "label": season_label, "post_id": post_id})
        return {"overview": overview, "details": details, "seasons": seasons}
    except Exception as e:
        logger.error(f"Error scraping series details: {e}")
        return None

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split(":")
    action = data[0]
    if action == "series":
        series_path = data[1]
        series_url = ANIMESALT_BASE + series_path
        details = await scrape_series_details(series_url)
        if not details:
            await query.edit_message_text("❌ Failed to fetch series details.")
            return
        overview_text = f"*Overview:*\n{details['overview']}\n\n" if details["overview"] else ""
        # Filter out 'min' and join with proper spacing
        filtered_details = [d for d in details["details"] if d.strip().lower() != "min"]
        details_text = " • ".join(filtered_details) if filtered_details else "No details found."
        if details["seasons"]:
            keyboard = [[InlineKeyboardButton(s["label"], callback_data=f"season:{series_path}:{s['season']}:{s['post_id']}")] for s in details["seasons"]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"🎬 *Series Details*\n\n{overview_text}{details_text}\n\n*Choose a season:*",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(f"🎬 *Series Details*\n\n{overview_text}{details_text}\n\nNo seasons found.", parse_mode='Markdown')

async def initialize_telegram_app():
    global telegram_app
    try:
        telegram_app = Application.builder().token(BOT_TOKEN).build()
        telegram_app.add_handler(CommandHandler("start", start))
        telegram_app.add_handler(CommandHandler("help", help_command))
        telegram_app.add_handler(CommandHandler("anime", anime))
        telegram_app.add_handler(CallbackQueryHandler(button_callback))
        await telegram_app.initialize()
        await telegram_app.start()
        webhook_info = await telegram_app.bot.get_webhook_info()
        if webhook_info.url != WEBHOOK_URL:
            await telegram_app.bot.set_webhook(WEBHOOK_URL)
            logger.info(f"Webhook set to: {WEBHOOK_URL}")
        else:
            logger.info("Webhook already set correctly")
        bot_info = await telegram_app.bot.get_me()
        logger.info(f"Bot initialized successfully: @{bot_info.username}")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize Telegram app: {e}")
        return False

@fastapi_app.get("/")
async def root():
    if telegram_app and telegram_app.running:
        bot_info = await telegram_app.bot.get_me()
        return {
            "status": "Bot is running!",
            "bot_username": f"@{bot_info.username}",
            "webhook_url": WEBHOOK_URL
        }
    else:
        return {"status": "Bot is starting up..."}

@fastapi_app.on_event("startup")
async def on_startup():
    await initialize_telegram_app()

@fastapi_app.post("/")
async def telegram_webhook(request: Request):
    global telegram_app
    if not telegram_app or not telegram_app.running:
        logger.error("Telegram app not initialized")
        raise HTTPException(status_code=500, detail="Bot not initialized")
    
    json_data = await request.json()
    update = Update.de_json(json_data, telegram_app.bot)
    if update:
        await telegram_app.process_update(update)
        logger.info("Update processed successfully")
    else:
        logger.warning("Failed to create Update object from JSON")
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:fastapi_app",
        host="0.0.0.0",
        port=10000,
        log_level="info"
    )
