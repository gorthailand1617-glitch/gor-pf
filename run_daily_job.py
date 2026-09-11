"""
Standalone Daily Market Sync & Alert Runner
Used by GitHub Actions, Cloud Scheduler, and Background Crons to run
the daily analysis and broadcast the daily market briefing to Telegram and LINE.
"""
import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("daily_job")

def main():
    logger.info("Starting Daily Market Sync & Broadcast Job...")
    try:
        from data_pipeline.gspread_client import GPFSpreadsheetClient
        from data_pipeline.pipeline import GPFPipeline
        from line_bot.notifier import LINEBotNotifier
        from telegram_bot.notifier import TelegramBotNotifier
        from api.scheduler import check_and_notify_profit_opportunity

        sheets = GPFSpreadsheetClient()
        pipeline = GPFPipeline(sheets_client=sheets)
        notifier = LINEBotNotifier()
        tg_notifier = TelegramBotNotifier()

        # Run pipeline update (persist to Google Sheets if connected)
        transitions = pipeline.run_daily_update(persist=sheets.is_connected())

        # 1. Always Broadcast Daily Market Summary
        if pipeline.latest_results:
            logger.info("Broadcasting Daily Market Summary to Telegram...")
            if tg_notifier.enabled:
                tg_notifier.send_daily_summary(pipeline.latest_results)

        # 2. Broadcast Transitions if any plan shifted signal
        if transitions:
            if sheets.is_connected() and notifier.enabled:
                subscribers = sheets.get_subscribers()
                if subscribers:
                    notifier.broadcast_transitions(transitions, subscribers)
            if tg_notifier.enabled:
                tg_notifier.send_transition_alert(transitions)

        # 3. Check and notify profit opportunities
        check_and_notify_profit_opportunity(sheets, pipeline, notifier, tg_notifier)

        logger.info("Daily market job completed successfully.")
    except Exception as e:
        logger.error(f"Error running daily market job: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
