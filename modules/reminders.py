"""
Модуль напоминаний - утренняя/вечерняя благодарность, месячный обзор, защита серии
"""
import logging
import json
import os
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

# Время месячного обзора (1-е число каждого месяца)
MONTHLY_REVIEW_TIME = "19:00"
MONTHLY_REVIEW_DAY = 1  # 1-е число месяца

# Время напоминания о серии (днём, до вечерней задачи)
STREAK_REMINDER_TIME = "18:00"

# Файл для сохранения chat_id
CHAT_ID_FILE = "/tmp/bot_chat_id.json"


class ReminderService:
    """
    Сервис напоминаний.
    
    Расписание:
    - 09:00 — утренняя благодарность
    - 18:00 — защита серии (loss aversion)
    - 20:00 — вечерняя задача (1 навык)
    - 23:00 — вечерняя благодарность
    - 1-е число месяца 19:00 — месячный обзор с AI
    """
    
    def __init__(self):
        self._app: Optional[Application] = None
        self._chat_id: Optional[int] = self._load_chat_id()
    
    def _load_chat_id(self) -> Optional[int]:
        """Загружает chat_id из файла"""
        try:
            if os.path.exists(CHAT_ID_FILE):
                with open(CHAT_ID_FILE, 'r') as f:
                    data = json.load(f)
                    chat_id = data.get("chat_id")
                    if chat_id:
                        logger.info(f"Chat ID загружен из файла: {chat_id}")
                        return chat_id
        except Exception as e:
            logger.error(f"Ошибка загрузки chat_id: {e}")
        return None
    
    def _save_chat_id(self, chat_id: int) -> None:
        """Сохраняет chat_id в файл"""
        try:
            with open(CHAT_ID_FILE, 'w') as f:
                json.dump({"chat_id": chat_id}, f)
            logger.info(f"Chat ID сохранён в файл: {chat_id}")
        except Exception as e:
            logger.error(f"Ошибка сохранения chat_id: {e}")
    
    def setup(self, app: Application) -> None:
        """Настраивает сервис напоминаний"""
        self._app = app
        
        # Парсим время
        morning_hour, morning_minute = scheduler.parse_time(MORNING_REMINDER_TIME)
        streak_hour, streak_minute = scheduler.parse_time(STREAK_REMINDER_TIME)
        task_hour, task_minute = scheduler.parse_time(EVENING_TASK_TIME)
        evening_hour, evening_minute = scheduler.parse_time(EVENING_REMINDER_TIME)
        monthly_hour, monthly_minute = scheduler.parse_time(MONTHLY_REVIEW_TIME)
        
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
        
        # Вечерняя задача (20:00) — 1 навык
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
        
        # Месячный обзор (1-е число каждого месяца в 19:00)
        scheduler.add_monthly_job(
            "monthly_review",
            self.send_monthly_review,
            day=MONTHLY_REVIEW_DAY,
            hour=monthly_hour,
            minute=monthly_minute
        )
        
        logger.info(
            f"Напоминания настроены: утро в {MORNING_REMINDER_TIME}, "
            f"серия в {STREAK_REMINDER_TIME}, "
            f"задача в {EVENING_TASK_TIME}, вечер в {EVENING_REMINDER_TIME}, "
            f"месячный обзор {MONTHLY_REVIEW_DAY}-го числа в {MONTHLY_REVIEW_TIME}"
        )
        
        if self._chat_id:
            logger.info(f"Chat ID уже загружен: {self._chat_id}")
        else:
            logger.warning("Chat ID не установлен. Напоминания не будут отправляться до первого /start")
    
    def set_chat_id(self, chat_id: int) -> None:
        """Устанавливает и сохраняет chat ID для отправки напоминаний"""
        self._chat_id = chat_id
        self._save_chat_id(chat_id)
        logger.info(f"Chat ID для напоминаний установлен и сохранён: {chat_id}")
    
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
        Сначала синхронизирует данные с Notion, затем отправляет напоминание.
        Использует психологию неприятия потерь для мотивации.
        Отправляется только если серия под угрозой.
        """
        if not self._app or not self._chat_id:
            logger.warning("Не могу отправить напоминание о серии: app или chat_id не установлены")
            return
        
        try:
            # Синхронизация с Notion перед проверкой серии
            logger.info("Запускаю синхронизацию с Notion перед проверкой серии...")
            await notion_module.refresh_skills_cache()
            logger.info("Синхронизация завершена")
            
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
        Один случайный навык для изучения.
        """
        if not self._app or not self._chat_id:
            logger.warning("Не могу отправить вечернюю задачу: app или chat_id не установлены")
            return
        
        try:
            skills = await notion_module.refresh_skills_cache()
            message = learning_module.generate_single_task_message(skills)
            
            await self._app.bot.send_message(
                chat_id=self._chat_id,
                text=message,
                parse_mode='Markdown'
            )
            
            logger.info("Вечерняя задача отправлена (1 навык)")
            
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
    
    async def send_monthly_review(self) -> None:
        """
        Отправляет месячный обзор с AI-анализом (1-е число месяца в 19:00).
        Анализирует паттерны за месяц, определяет вызовы, рекомендует навыки.
        """
        if not self._app or not self._chat_id:
            logger.warning("Не могу отправить месячный обзор: app или chat_id не установлены")
            return
        
        try:
            logger.info("Отправляю месячный обзор...")
            
            # Используем функцию месячного обзора из модуля благодарности
            await gratitude_module.send_monthly_review(
                self._app.bot, 
                self._chat_id
            )
            
            logger.info("Месячный обзор успешно отправлен")
            
        except Exception as e:
            logger.error(f"Ошибка отправки месячного обзора: {e}")
    
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
