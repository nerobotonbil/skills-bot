"""
Reminders module - morning/evening gratitude and weekly review notifications
"""
import logging
from typing import Optional
from telegram.ext import Application

from core.scheduler import scheduler
from modules.notion.module import notion_module
from modules.learning.module import learning_module
from modules.gratitude.module import gratitude_module
from config.settings import (
    MORNING_REMINDER_TIME, 
    EVENING_REMINDER_TIME,
    EVENING_TASK_TIME
)

logger = logging.getLogger(__name__)

# Friday evening time for weekly review
FRIDAY_REVIEW_TIME = "19:00"


class ReminderService:
    """
    Reminder service.
    
    Schedule:
    - 09:00 — morning gratitude prompt
    - 20:00 — evening task (smart recommendation)
    - 23:00 — evening gratitude prompt
    - Friday 19:00 — weekly gratitude review with AI insights
    """
    
    def __init__(self):
        self._app: Optional[Application] = None
        self._chat_id: Optional[int] = None
    
    def setup(self, app: Application) -> None:
        """Sets up the reminder service"""
        self._app = app
        
        # Parse times
        morning_hour, morning_minute = scheduler.parse_time(MORNING_REMINDER_TIME)
        task_hour, task_minute = scheduler.parse_time(EVENING_TASK_TIME)
        evening_hour, evening_minute = scheduler.parse_time(EVENING_REMINDER_TIME)
        friday_hour, friday_minute = scheduler.parse_time(FRIDAY_REVIEW_TIME)
        
        # Morning gratitude (09:00)
        scheduler.add_daily_job(
            "morning_reminder",
            self.send_morning_gratitude,
            hour=morning_hour,
            minute=morning_minute
        )
        
        # Evening task (20:00) — smart recommendation
        scheduler.add_daily_job(
            "evening_task",
            self.send_evening_task,
            hour=task_hour,
            minute=task_minute
        )
        
        # Evening gratitude (23:00)
        scheduler.add_daily_job(
            "evening_reminder",
            self.send_evening_gratitude,
            hour=evening_hour,
            minute=evening_minute
        )
        
        # Friday weekly review (19:00)
        scheduler.add_weekly_job(
            "friday_review",
            self.send_weekly_review,
            day_of_week=4,  # Friday (0=Monday)
            hour=friday_hour,
            minute=friday_minute
        )
        
        logger.info(
            f"Reminders scheduled: morning at {MORNING_REMINDER_TIME}, "
            f"task at {EVENING_TASK_TIME}, evening at {EVENING_REMINDER_TIME}, "
            f"weekly review on Friday at {FRIDAY_REVIEW_TIME}"
        )
    
    def set_chat_id(self, chat_id: int) -> None:
        """Sets chat ID for sending reminders"""
        self._chat_id = chat_id
        logger.info(f"Reminder chat ID set to {chat_id}")
    
    async def send_morning_gratitude(self) -> None:
        """
        Sends morning gratitude prompt (09:00).
        """
        if not self._app or not self._chat_id:
            logger.warning("Cannot send morning gratitude: app or chat_id not set")
            return
        
        try:
            message = (
                "🌅 **Good morning!**\n\n"
                "What are you grateful for this morning?\n"
                "What good awaits you today?\n\n"
                "_Just reply to this message_"
            )
            
            await self._app.bot.send_message(
                chat_id=self._chat_id,
                text=message,
                parse_mode='Markdown'
            )
            
            gratitude_module.set_waiting_for_gratitude(self._chat_id, "morning")
            logger.info("Morning gratitude prompt sent")
            
        except Exception as e:
            logger.error(f"Failed to send morning gratitude: {e}")
    
    async def send_evening_task(self) -> None:
        """
        Sends evening task (20:00).
        """
        if not self._app or not self._chat_id:
            logger.warning("Cannot send evening task: app or chat_id not set")
            return
        
        try:
            skills = await notion_module.refresh_skills_cache()
            message = learning_module.generate_evening_task_message(skills)
            
            await self._app.bot.send_message(
                chat_id=self._chat_id,
                text=message,
                parse_mode='Markdown'
            )
            
            logger.info("Evening task sent")
            
        except Exception as e:
            logger.error(f"Failed to send evening task: {e}")
    
    async def send_evening_gratitude(self) -> None:
        """
        Sends evening gratitude prompt (23:00).
        """
        if not self._app or not self._chat_id:
            logger.warning("Cannot send evening gratitude: app or chat_id not set")
            return
        
        try:
            message = (
                "🌙 **Good evening!**\n\n"
                "Time to reflect on the day.\n"
                "What are you grateful for today?\n"
                "What good happened?\n\n"
                "_Just reply to this message_"
            )
            
            await self._app.bot.send_message(
                chat_id=self._chat_id,
                text=message,
                parse_mode='Markdown'
            )
            
            gratitude_module.set_waiting_for_gratitude(self._chat_id, "evening")
            logger.info("Evening gratitude prompt sent")
            
        except Exception as e:
            logger.error(f"Failed to send evening gratitude: {e}")
    
    async def send_weekly_review(self) -> None:
        """
        Sends weekly gratitude review with AI insights (Friday 19:00).
        Analyzes patterns, detects challenges, recommends skills.
        """
        if not self._app or not self._chat_id:
            logger.warning("Cannot send weekly review: app or chat_id not set")
            return
        
        try:
            logger.info("Sending Friday weekly review...")
            
            # Use gratitude module's weekly review function
            await gratitude_module.send_weekly_review(
                self._app.bot, 
                self._chat_id
            )
            
            logger.info("Weekly review sent successfully")
            
        except Exception as e:
            logger.error(f"Failed to send weekly review: {e}")
    
    async def send_custom_reminder(self, message: str) -> None:
        """Sends custom reminder"""
        if not self._app or not self._chat_id:
            return
        
        try:
            await self._app.bot.send_message(
                chat_id=self._chat_id,
                text=message,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to send custom reminder: {e}")


# Global service instance
reminder_service = ReminderService()
