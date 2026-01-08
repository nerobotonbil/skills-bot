"""
Reminders module - morning and evening notifications
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


class ReminderService:
    """
    Reminder service.
    
    Schedule:
    - 09:00 — morning reminder (gratitude)
    - 20:00 — evening task (smart recommendation based on progress)
    - 21:00 — evening reminder (summary + gratitude)
    """
    
    def __init__(self):
        self._app: Optional[Application] = None
        self._chat_id: Optional[int] = None
    
    def setup(self, app: Application) -> None:
        """Sets up the reminder service"""
        self._app = app
        
        # Parse time
        morning_hour, morning_minute = scheduler.parse_time(MORNING_REMINDER_TIME)
        task_hour, task_minute = scheduler.parse_time(EVENING_TASK_TIME)
        evening_hour, evening_minute = scheduler.parse_time(EVENING_REMINDER_TIME)
        
        # Morning reminder (09:00)
        scheduler.add_daily_job(
            "morning_reminder",
            self.send_morning_reminder,
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
        
        # Evening reminder (21:00) — summary + gratitude
        scheduler.add_daily_job(
            "evening_reminder",
            self.send_evening_reminder,
            hour=evening_hour,
            minute=evening_minute
        )
        
        logger.info(
            f"Reminders scheduled: morning at {MORNING_REMINDER_TIME}, "
            f"task at {EVENING_TASK_TIME}, evening at {EVENING_REMINDER_TIME}"
        )
    
    def set_chat_id(self, chat_id: int) -> None:
        """Sets chat ID for sending reminders"""
        self._chat_id = chat_id
        logger.info(f"Reminder chat ID set to {chat_id}")
    
    async def send_morning_reminder(self) -> None:
        """Sends morning reminder (09:00)"""
        if not self._app or not self._chat_id:
            logger.warning("Cannot send morning reminder: app or chat_id not set")
            return
        
        try:
            # Update skills data
            skills = await notion_module.refresh_skills_cache()
            
            # Generate message
            message = learning_module.get_morning_message(skills)
            
            await self._app.bot.send_message(
                chat_id=self._chat_id,
                text=message,
                parse_mode='Markdown'
            )
            
            # Wait for gratitude
            gratitude_module.set_waiting_for_gratitude(self._chat_id, "morning")
            
            logger.info("Morning reminder sent")
            
        except Exception as e:
            logger.error(f"Failed to send morning reminder: {e}")
    
    async def send_evening_task(self) -> None:
        """
        Sends evening task (20:00).
        Syncs with Notion and sends smart recommendation.
        """
        if not self._app or not self._chat_id:
            logger.warning("Cannot send evening task: app or chat_id not set")
            return
        
        try:
            # Sync with Notion — get current data
            skills = await notion_module.refresh_skills_cache()
            
            # Generate smart recommendation based on progress analysis
            message = learning_module.generate_evening_task_message(skills)
            
            await self._app.bot.send_message(
                chat_id=self._chat_id,
                text=message,
                parse_mode='Markdown'
            )
            
            logger.info("Evening task sent")
            
        except Exception as e:
            logger.error(f"Failed to send evening task: {e}")
    
    async def send_evening_reminder(self) -> None:
        """Sends evening reminder (21:00)"""
        if not self._app or not self._chat_id:
            logger.warning("Cannot send evening reminder: app or chat_id not set")
            return
        
        try:
            # Generate message with summary
            message = learning_module.get_evening_message()
            
            await self._app.bot.send_message(
                chat_id=self._chat_id,
                text=message,
                parse_mode='Markdown'
            )
            
            # Wait for gratitude
            gratitude_module.set_waiting_for_gratitude(self._chat_id, "evening")
            
            logger.info("Evening reminder sent")
            
        except Exception as e:
            logger.error(f"Failed to send evening reminder: {e}")
    
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
