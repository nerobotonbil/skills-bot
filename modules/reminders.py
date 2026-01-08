"""
Модуль напоминаний - утренняя/вечерняя благодарность, недельный обзор, защита серии
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

# Время пятничного обзора
FRIDAY_REVIEW_TIME = "19:00"

# Время напоминания о серии (днём, до вечерней задачи)
STREAK_REMINDER_TIME = "18:00"


class ReminderService:
    """
    Сервис напоминаний.
    
    Расписание:
    - 09:00 — утренняя благодарность
    - 18:00 — защита серии (loss aversion)
    - 20:00 — вечерняя задача
    - 23:00 — вечерняя благодарность
    - Пятница 19:00 — недельный обзор с AI
    """
    
    def __init__(self):
        self._app: Optional[Application] = None
        self._chat_id: Optional[int] = None
    
    def setup(self, app: Application) -> None:
        """Настраивает сервис напоминаний"""
        self._app = app
        
        # Парсим время
        morning_hour, morning_minute = scheduler.parse_time(MORNING_REMINDER_TIME)
        streak_hour, streak_minute = scheduler.parse_time(STREAK_REMINDER_TIME)
        task_hour, task_minute = scheduler.parse_time(EVENING_TASK_TIME)
        evening_hour, evening_minute = scheduler.parse_time(EVENING_REMINDER_TIME)
        friday_hour, friday_minute = scheduler.parse_time(FRIDAY_REVIEW_TIME)
        
        # Утренняя благодарность (09:00)
        scheduler.add_daily_job(
            "morning_reminder",
            self.send_morning_gratitude,
            hour=morning_hour,
            minute=morning_minute
        )
        
        # Напоминание о серии (18:00) — loss aversion
        scheduler.add_daily_job(
            "streak_reminder",
            self.send_streak_reminder,
            hour=streak_hour,
            minute=streak_minute
        )
        
        # Вечерняя задача (20:00) — блок глубокой практики
        scheduler.add_daily_job(
            "evening_task",
            self.send_evening_task,
            hour=task_hour,
            minute=task_minute
        )
        
        # Вечерняя благодарность (23:00)
        scheduler.add_daily_job(
            "evening_reminder",
            self.send_evening_gratitude,
            hour=evening_hour,
            minute=evening_minute
        )
        
        # Пятничный недельный обзор (19:00)
        scheduler.add_weekly_job(
            "friday_review",
            self.send_weekly_review,
            day_of_week=4,  # Пятница (0=Понедельник)
            hour=friday_hour,
            minute=friday_minute
        )
        
        logger.info(
            f"Напоминания настроены: утро в {MORNING_REMINDER_TIME}, "
            f"серия в {STREAK_REMINDER_TIME}, "
            f"задача в {EVENING_TASK_TIME}, вечер в {EVENING_REMINDER_TIME}, "
            f"недельный обзор в пятницу в {FRIDAY_REVIEW_TIME}"
        )
    
    def set_chat_id(self, chat_id: int) -> None:
        """Устанавливает chat ID для отправки напоминаний"""
        self._chat_id = chat_id
        logger.info(f"Chat ID для напоминаний установлен: {chat_id}")
    
    async def send_morning_gratitude(self) -> None:
        """
        Отправляет утреннюю благодарность (09:00).
        """
        if not self._app or not self._chat_id:
            logger.warning("Не могу отправить утреннюю благодарность: app или chat_id не установлены")
            return
        
        try:
            message = (
                "🌅 **Доброе утро!**\n\n"
                "За что ты благодарен этим утром?\n"
                "Что хорошего ждёт тебя сегодня?\n\n"
                "_Просто ответь на это сообщение_"
            )
            
            await self._app.bot.send_message(
                chat_id=self._chat_id,
                text=message,
                parse_mode='Markdown'
            )
            
            gratitude_module.set_waiting_for_gratitude(self._chat_id, "morning")
            logger.info("Утренняя благодарность отправлена")
            
        except Exception as e:
            logger.error(f"Ошибка отправки утренней благодарности: {e}")
    
    async def send_streak_reminder(self) -> None:
        """
        Отправляет напоминание о защите серии (18:00).
        Использует психологию неприятия потерь для мотивации.
        Отправляется только если серия под угрозой.
        """
        if not self._app or not self._chat_id:
            logger.warning("Не могу отправить напоминание о серии: app или chat_id не установлены")
            return
        
        try:
            # Импортируем здесь чтобы избежать циклических импортов
            from modules.productivity.module import productivity_module
            
            # Генерируем сообщение loss aversion (возвращает None если не нужно)
            message = productivity_module.generate_loss_aversion_reminder()
            
            if message:
                await self._app.bot.send_message(
                    chat_id=self._chat_id,
                    text=message,
                    parse_mode='Markdown'
                )
                logger.info("Напоминание о серии отправлено (loss aversion)")
            else:
                logger.info("Напоминание о серии пропущено (уже практиковался сегодня или нет серии)")
            
        except Exception as e:
            logger.error(f"Ошибка отправки напоминания о серии: {e}")
    
    async def send_evening_task(self) -> None:
        """
        Отправляет вечернюю задачу (20:00).
        Простая рекомендация на основе прогресса.
        """
        if not self._app or not self._chat_id:
            logger.warning("Не могу отправить вечернюю задачу: app или chat_id не установлены")
            return
        
        try:
            skills = await notion_module.refresh_skills_cache()
            message = learning_module.generate_evening_task_message(skills)
            
            await self._app.bot.send_message(
                chat_id=self._chat_id,
                text=message,
                parse_mode='Markdown'
            )
            
            logger.info("Вечерняя задача отправлена")
            
        except Exception as e:
            logger.error(f"Ошибка отправки вечерней задачи: {e}")
    
    async def send_evening_gratitude(self) -> None:
        """
        Отправляет вечернюю благодарность (23:00).
        """
        if not self._app or not self._chat_id:
            logger.warning("Не могу отправить вечернюю благодарность: app или chat_id не установлены")
            return
        
        try:
            message = (
                "🌙 **Добрый вечер!**\n\n"
                "Время подвести итоги дня.\n"
                "За что ты благодарен сегодня?\n"
                "Что хорошего произошло?\n\n"
                "_Просто ответь на это сообщение_"
            )
            
            await self._app.bot.send_message(
                chat_id=self._chat_id,
                text=message,
                parse_mode='Markdown'
            )
            
            gratitude_module.set_waiting_for_gratitude(self._chat_id, "evening")
            logger.info("Вечерняя благодарность отправлена")
            
        except Exception as e:
            logger.error(f"Ошибка отправки вечерней благодарности: {e}")
    
    async def send_weekly_review(self) -> None:
        """
        Отправляет недельный обзор с AI-анализом (Пятница 19:00).
        Анализирует паттерны, определяет вызовы, рекомендует навыки.
        """
        if not self._app or not self._chat_id:
            logger.warning("Не могу отправить недельный обзор: app или chat_id не установлены")
            return
        
        try:
            logger.info("Отправляю пятничный недельный обзор...")
            
            # Используем функцию недельного обзора из модуля благодарности
            await gratitude_module.send_weekly_review(
                self._app.bot, 
                self._chat_id
            )
            
            logger.info("Недельный обзор успешно отправлен")
            
        except Exception as e:
            logger.error(f"Ошибка отправки недельного обзора: {e}")
    
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
            logger.error(f"Ошибка отправки произвольного напоминания: {e}")


# Глобальный экземпляр сервиса
reminder_service = ReminderService()
