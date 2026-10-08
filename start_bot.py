import os
import sys
import time
import logging
from dotenv import load_dotenv

# Safe writer for stdout/stderr when running headless or piped
class SafeWriter:
    def __init__(self, filename):
        self.filename = filename
        self._file = None

    def write(self, s):
        try:
            if not self._file or self._file.closed:
                self._file = open(self.filename, "a", encoding="utf-8")
            self._file.write(s)
            self._file.flush()
        except Exception:
            pass

    def flush(self):
        try:
            if self._file and not self._file.closed:
                self._file.flush()
        except Exception:
            pass

class SafeStreamHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            super().emit(record)
        except Exception:
            pass

    def flush(self):
        try:
            super().flush()
        except Exception:
            pass

class SafeFileHandler(logging.FileHandler):
    def emit(self, record):
        try:
            super().emit(record)
        except Exception:
            pass

    def flush(self):
        try:
            super().flush()
        except Exception:
            pass

is_headless = "pythonw" in sys.executable.lower() or sys.stdout is None

if sys.stdout is None:
    sys.stdout = SafeWriter("bot_service.log")
if sys.stderr is None:
    sys.stderr = SafeWriter("bot_service.log")

if not is_headless and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()

# Setup logging
log_handlers = [SafeFileHandler("bot_service.log", encoding="utf-8")]
if not is_headless:
    log_handlers.append(SafeStreamHandler(sys.stdout))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=log_handlers
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
