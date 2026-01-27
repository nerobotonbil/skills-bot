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


# Файл для сохранения chat_id
CHAT_ID_FILE = "/tmp/bot_chat_id.json"


class ReminderService:
    """
    Сервис напоминаний.
    
    Расписание:
    - 20:00 — вечерняя задача (1 навык)
    - 23:00 — вечерняя благодарность
    - 1-е число месяца 19:00 — месячный обзор с AI
    """
    
    def __init__(self):
        self._app: Optional[Application] = None
        # Try to load chat_id from environment first, then from file
        self._chat_id: Optional[int] = self._load_chat_id_from_env() or self._load_chat_id()
    
    def _load_chat_id_from_env(self) -> Optional[int]:
        """Loads chat_id from environment variable (Railway)"""
        try:
            chat_id_str = os.getenv("TELEGRAM_CHAT_ID")
            if chat_id_str:
                chat_id = int(chat_id_str)
                logger.info(f"Chat ID loaded from environment: {chat_id}")
                return chat_id
        except Exception as e:
            logger.warning(f"Error loading chat_id from environment: {e}")
        return None
    
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
        task_hour, task_minute = scheduler.parse_time(EVENING_TASK_TIME)
        evening_hour, evening_minute = scheduler.parse_time(EVENING_REMINDER_TIME)
        monthly_hour, monthly_minute = scheduler.parse_time(MONTHLY_REVIEW_TIME)
        
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
        
        # Воскресное напоминание (15:00) - дополнительные задачи
        scheduler.add_weekly_job(
            "sunday_afternoon_reminder",
            self.send_sunday_afternoon_reminder,
            day_of_week=6,  # Sunday
            hour=15,
            minute=0
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
            f"Напоминания настроены: "
            f"задача в {EVENING_TASK_TIME}, вечерняя благодарность в {EVENING_REMINDER_TIME}, "
            f"воскресенье в 15:00, "
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
        Отправляет утренний план дня с анализом WHOOP (08:00).
        Включает: энергию, стресс, рекомендации задач, время сна.
        """
        if not self._app or not self._chat_id:
            logger.warning("Не могу отправить утренний план: app или chat_id не установлены")
            return
        
        try:
            # Simple morning gratitude prompt
            message = (
                "🌅 **Доброе утро!**\n\n"
                "🙏 **За что ты благодарен этим утром?**\n\n"
                "_Просто ответь на это сообщение_"
            )
            
            await self._app.bot.send_message(
                chat_id=self._chat_id,
                text=message,
                parse_mode='Markdown'
            )
            
            gratitude_module.set_waiting_for_gratitude(self._chat_id, "morning")
            logger.info("Утреннее напоминание отправлено")
            
        except Exception as e:
            logger.error(f"Ошибка отправки утреннего плана: {e}", exc_info=True)
            # Fallback to simple message
            try:
                await self._app.bot.send_message(
                    chat_id=self._chat_id,
                    text="🌅 Доброе утро! За что ты благодарен сегодня?",
                    parse_mode='Markdown'
                )
                gratitude_module.set_waiting_for_gratitude(self._chat_id, "morning")
            except Exception as e2:
                logger.error(f"Ошибка отправки fallback сообщения: {e2}")
    
    
    async def send_evening_task(self) -> None:
        """
        Отправляет вечернюю задачу (20:00).
        Один случайный навык для изучения + WHOOP рекомендации.
        """
        if not self._app or not self._chat_id:
            logger.warning("Не могу отправить вечернюю задачу: app или chat_id не установлены")
            return
        
        try:
            skills = await notion_module.refresh_skills_cache()
            base_message = learning_module.generate_single_task_message(skills)
            
            # Enhance with WHOOP recommendation if available
            try:
                from modules.whoop_integration import get_evening_task_with_whoop
                message = get_evening_task_with_whoop(base_message)
            except Exception as whoop_error:
                logger.warning(f"WHOOP integration failed: {whoop_error}")
                message = base_message
            
            await self._app.bot.send_message(
                chat_id=self._chat_id,
                text=message,
                parse_mode='Markdown'
            )
            
            logger.info("Вечерняя задача отправлена (1 навык + WHOOP)")
            
        except Exception as e:
            logger.error(f"Ошибка отправки вечерней задачи: {e}")
    
    async def send_evening_gratitude(self) -> None:
        """
        Отправляет вечернюю благодарность (23:00).
        Просто напоминание, без перехода в режим ожидания.
        """
        if not self._app or not self._chat_id:
            logger.warning("Не могу отправить вечернюю благодарность: app или chat_id не установлены")
            return
        
        try:
            message = (
                "🌙 Добрый вечер!\n\n"
                "Время подвести итоги дня.\n"
                "За что ты благодарен сегодня?\n"
                "Что хорошего произошло?\n\n"
                "Используй /gratitude чтобы записать. 🙏"
            )
            
            await self._app.bot.send_message(
                chat_id=self._chat_id,
                text=message
            )
            
            # НЕ устанавливаем waiting state - пользователь сам вызовет /gratitude
            logger.info("Вечернее напоминание отправлено (без waiting state)")
            
        except Exception as e:
            logger.error(f"Ошибка отправки вечернего напоминания: {e}")
    
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
    
    async def send_sunday_afternoon_reminder(self) -> None:
        """
        Отправляет воскресное напоминание в 15:00.
        Второй раунд задач для выходного дня.
        """
        if not self._app or not self._chat_id:
            logger.warning("Не могу отправить воскресное напоминание")
            return
        
        try:
            from modules.whoop_integration import get_whoop_client
            from modules.task_recommender import get_task_recommender
            from modules.notion.module import notion_module
            import random
            
            whoop_client = get_whoop_client()
            recommender = get_task_recommender()
            
            message_parts = ["🌞 **Воскресный бонус!**\n"]
            message_parts.append("Вторая половина дня - отличное время для дополнительных задач!\n")
            
            if whoop_client and whoop_client.available:
                whoop_data = whoop_client.get_comprehensive_health_data()
                if whoop_data.get("available"):
                    energy_data = recommender.calculate_energy_level(whoop_data)
                    task_rec = recommender.recommend_task_difficulty(energy_data)
                    weekend_boost = recommender.get_weekend_boost_factor()
                    boosted_tasks = int(task_rec['max_tasks'] * weekend_boost)
                    
                    message_parts.append(f"\n💪 **Энергия**: {energy_data.get('energy_level', 'unknown').upper()}")
                    message_parts.append(f"\n📋 **Рекомендации**:")
                    message_parts.append(f"• Дополнительных задач: **{boosted_tasks}**")
                    message_parts.append(f"• Сложность: **{task_rec['recommended_difficulty']}**")
            
            # Get random skills
            try:
                skills = await notion_module.refresh_skills_cache()
                if skills:
                    sample_skills = random.sample(skills, min(3, len(skills)))
                    message_parts.append("\n\n🎯 **Навыки для прокачки**:")
                    for skill in sample_skills:
                        message_parts.append(f"• {skill.get('name', 'Unknown')}")
            except Exception as e:
                logger.warning(f"Could not fetch skills: {e}")
            
            message_parts.append("\n\n🚀 Используй выходной максимально!")
            
            await self._app.bot.send_message(
                chat_id=self._chat_id,
                text="\n".join(message_parts),
                parse_mode='Markdown'
            )
            logger.info("Воскресное напоминание отправлено")
            
        except Exception as e:
            logger.error(f"Ошибка воскресного напоминания: {e}")


# Глобальный экземпляр сервиса
reminder_service = ReminderService()
