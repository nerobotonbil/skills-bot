"""
Модуль напоминаний - утренние и вечерние уведомления
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
    Сервис напоминаний.
    
    Расписание:
    - 09:00 — утреннее напоминание (благодарность)
    - 20:00 — вечерняя задача (умная рекомендация на основе прогресса)
    - 21:00 — вечернее напоминание (итоги + благодарность)
    """
    
    def __init__(self):
        self._app: Optional[Application] = None
        self._chat_id: Optional[int] = None
    
    def setup(self, app: Application) -> None:
        """Настраивает сервис напоминаний"""
        self._app = app
        
        # Парсим время
        morning_hour, morning_minute = scheduler.parse_time(MORNING_REMINDER_TIME)
        task_hour, task_minute = scheduler.parse_time(EVENING_TASK_TIME)
        evening_hour, evening_minute = scheduler.parse_time(EVENING_REMINDER_TIME)
        
        # Утреннее напоминание (09:00)
        scheduler.add_daily_job(
            "morning_reminder",
            self.send_morning_reminder,
            hour=morning_hour,
            minute=morning_minute
        )
        
        # Вечерняя задача (20:00) — умная рекомендация
        scheduler.add_daily_job(
            "evening_task",
            self.send_evening_task,
            hour=task_hour,
            minute=task_minute
        )
        
        # Вечернее напоминание (21:00) — итоги + благодарность
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
        """Устанавливает ID чата для отправки напоминаний"""
        self._chat_id = chat_id
        logger.info(f"Reminder chat ID set to {chat_id}")
    
    async def send_morning_reminder(self) -> None:
        """Отправляет утреннее напоминание (09:00)"""
        if not self._app or not self._chat_id:
            logger.warning("Cannot send morning reminder: app or chat_id not set")
            return
        
        try:
            # Обновляем данные о навыках
            skills = await notion_module.refresh_skills_cache()
            
            # Генерируем сообщение
            message = learning_module.get_morning_message(skills)
            
            await self._app.bot.send_message(
                chat_id=self._chat_id,
                text=message,
                parse_mode='Markdown'
            )
            
            # Ожидаем благодарность
            gratitude_module.set_waiting_for_gratitude(self._chat_id, "morning")
            
            logger.info("Morning reminder sent")
            
        except Exception as e:
            logger.error(f"Failed to send morning reminder: {e}")
    
    async def send_evening_task(self) -> None:
        """
        Отправляет вечернюю задачу (20:00).
        Синхронизируется с Notion и отправляет умную рекомендацию.
        """
        if not self._app or not self._chat_id:
            logger.warning("Cannot send evening task: app or chat_id not set")
            return
        
        try:
            # Синхронизируемся с Notion — получаем актуальные данные
            skills = await notion_module.refresh_skills_cache()
            
            # Генерируем умную рекомендацию на основе анализа прогресса
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
        """Отправляет вечернее напоминание (21:00)"""
        if not self._app or not self._chat_id:
            logger.warning("Cannot send evening reminder: app or chat_id not set")
            return
        
        try:
            # Генерируем сообщение с итогами
            message = learning_module.get_evening_message()
            
            await self._app.bot.send_message(
                chat_id=self._chat_id,
                text=message,
                parse_mode='Markdown'
            )
            
            # Ожидаем благодарность
            gratitude_module.set_waiting_for_gratitude(self._chat_id, "evening")
            
            logger.info("Evening reminder sent")
            
        except Exception as e:
            logger.error(f"Failed to send evening reminder: {e}")
    
    async def send_custom_reminder(self, message: str) -> None:
        """Отправляет произвольное напоминание"""
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


# Глобальный экземпляр сервиса
reminder_service = ReminderService()
