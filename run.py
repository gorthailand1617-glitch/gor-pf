import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

from api.scheduler import start_scheduler

if __name__ == "__main__":
    # Start background scheduler
    scheduler = start_scheduler()
    
    # Start interactive Telegram bot polling
    try:
        from telegram_bot.webhook import start_telegram_polling
        start_telegram_polling()
    except Exception as e:
        print(f"Notice: Telegram polling not started: {e}")
    
    # Get port configuration
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger_msg = f"Starting GPF-SmartInvestor-AI API server on {host}:{port}..."
    print(logger_msg)
    
    try:
        # Launch FastAPI
        reload_flag = os.getenv("RELOAD", "false").lower() == "true"
        uvicorn.run(
            "api.main:app", 
            host=host, 
            port=port, 
            reload=reload_flag
        )
    finally:
        # Shutdown scheduler when app exits
        scheduler.shutdown()
        print("Scheduler shut down successfully.")
