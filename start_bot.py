import os
import sys
import time
import logging
from dotenv import load_dotenv

# Ensure stdout handles UTF-8 on Windows or redirect to file if headless
if sys.stdout is None:
    sys.stdout = open("bot_service.log", "a", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open("bot_service.log", "a", encoding="utf-8")

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot_service.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("TelegramBotService")

from telegram_bot.webhook import TelegramWebhookHandler, start_telegram_polling
from api.scheduler import start_scheduler

def main():
    logger.info("==================================================")
    logger.info("   Gor.PF Telegram Interactive Bot & Scheduler")
    logger.info("==================================================")
    
    handler = TelegramWebhookHandler()
    if not handler.bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not found in .env!")
        return

    # Start automated daily report & alerts scheduler
    scheduler = None
    try:
        scheduler = start_scheduler()
        logger.info("Daily Scheduler active: 18:30 ICT Daily Summary & hourly checks.")
    except Exception as e:
        logger.warning(f"Could not initialize APScheduler: {e}")

    logger.info("Starting Telegram Bot listener in background thread...")
    thread = start_telegram_polling(handler)
    logger.info("Bot is now ONLINE and actively listening for messages from @Gor_Gpf_bot!")
    
    # Keep the main process alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Bot service stopped by user.")
    finally:
        if scheduler:
            scheduler.shutdown()
            logger.info("Scheduler shut down successfully.")

if __name__ == "__main__":
    main()
