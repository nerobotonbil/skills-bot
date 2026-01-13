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
        
        # Напоминание о стрике (23:00) - если прогресса нет
        scheduler.add_daily_job(
            "streak_reminder_23",
            self.send_streak_reminder_23,
            hour=23,
            minute=0
        )
        
        # Финальная проверка стрика (03:00) - окончательное обновление
        scheduler.add_daily_job(
            "auto_streak_update",
            self.auto_update_streak,
            hour=3,
            minute=0
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
            f"Напоминания настроены: утро в {MORNING_REMINDER_TIME}, "
            f"серия в {STREAK_REMINDER_TIME}, "
            f"задача в {EVENING_TASK_TIME}, вечер в {EVENING_REMINDER_TIME}, "
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
            # Get WHOOP data
            from modules.whoop_integration import get_whoop_client
            from modules.task_recommender import get_task_recommender
            from datetime import datetime
            
            whoop_client = get_whoop_client()
            recommender = get_task_recommender()
            
            message_parts = ["🌅 **Доброе утро! План на день**\n"]
            
            if whoop_client and whoop_client.available:
                # Get comprehensive WHOOP data
                whoop_data = whoop_client.get_comprehensive_health_data()
                
                if whoop_data.get("available"):
                    # Calculate energy level
                    energy_data = recommender.calculate_energy_level(whoop_data)
                    
                    recovery = whoop_data.get("recovery", {})
                    sleep = whoop_data.get("sleep", {})
                    strain = whoop_data.get("strain", {})
                    workouts = whoop_data.get("workouts", [])
                    
                    # Recovery section
                    message_parts.append("\n📊 **Твоё восстановление:**")
                    if recovery:
                        rec_score = recovery.get("score")
                        hrv = recovery.get("hrv_rmssd")
                        rhr = recovery.get("resting_heart_rate")
                        
                        if rec_score:
                            emoji = "🟢" if rec_score >= 67 else "🟡" if rec_score >= 34 else "🔴"
                            message_parts.append(f"{emoji} Recovery: **{rec_score}%**")
                        if hrv:
                            message_parts.append(f"💓 HRV: {hrv}ms")
                        if rhr:
                            message_parts.append(f"❤️ RHR: {rhr} bpm")
                    
                    # Sleep section
                    if sleep:
                        message_parts.append("\n😴 **Твой сон:**")
                        total_sleep = sleep.get("total_sleep_hours")
                        deep_sleep = sleep.get("deep_sleep_hours")
                        rem_sleep = sleep.get("rem_sleep_hours")
                        sleep_perf = sleep.get("performance_percentage")
                        
                        if total_sleep:
                            message_parts.append(f"⏱ Всего: {total_sleep}ч")
                        if deep_sleep:
                            message_parts.append(f"🌊 Глубокий: {deep_sleep}ч")
                        if rem_sleep:
                            message_parts.append(f"💭 REM: {rem_sleep}ч")
                        if sleep_perf:
                            emoji = "✅" if sleep_perf >= 85 else "⚠️" if sleep_perf >= 70 else "❌"
                            message_parts.append(f"{emoji} Качество: {sleep_perf}%")
                    
                    # Stress indicator
                    stress = energy_data.get("stress_indicator")
                    if stress is not None:
                        message_parts.append("\n🧠 **Уровень стресса:**")
                        if stress < 30:
                            message_parts.append(f"🟢 Низкий ({stress}/100) - отлично!")
                        elif stress < 60:
                            message_parts.append(f"🟡 Средний ({stress}/100) - нормально")
                        else:
                            message_parts.append(f"🔴 Высокий ({stress}/100) - нужен отдых!")
                    
                    # Energy level and task recommendations
                    message_parts.append("\n⚡ **Твоя энергия:**")
                    energy_level = energy_data.get("energy_level")
                    if energy_level == "high":
                        message_parts.append("🟢 **ВЫСОКАЯ** - отличный день для сложных задач!")
                    elif energy_level == "medium":
                        message_parts.append("🟡 **СРЕДНЯЯ** - фокусируйся на рутине")
                    else:
                        message_parts.append("🔴 **НИЗКАЯ** - береги силы, делай простые задачи")
                    
                    # Task recommendations
                    task_rec = recommender.recommend_task_difficulty(energy_data)
                    message_parts.append("\n📋 **Рекомендации на сегодня:**")
                    message_parts.append(f"• Максимум задач: **{task_rec['max_tasks']}**")
                    message_parts.append(f"• Сложность: **{task_rec['recommended_difficulty']}**")
                    message_parts.append(f"• Фокус: {task_rec['focus_duration_hours']}ч")
                    message_parts.append(f"• Перерывы каждые {task_rec['break_frequency_minutes']}мин")
                    
                    message_parts.append(f"\n💡 {task_rec['advice']}")
                    
                    # Weekend boost
                    weekend_factor = recommender.get_weekend_boost_factor()
                    if weekend_factor > 1.0:
                        message_parts.append("\n🎉 **Выходной!** Можешь сделать x1.5 больше задач!")
                    
                    # Sleep recommendation
                    sleep_rec = recommender.recommend_sleep_time(whoop_data, target_wake_time="08:00")
                    message_parts.append("\n🌙 **Когда лечь спать:**")
                    message_parts.append(f"⏰ Рекомендуемое время: **{sleep_rec['recommended_bedtime']}**")
                    message_parts.append(f"💤 Нужно сна: {sleep_rec['sleep_need_hours']}ч")
                    if sleep_rec['sleep_debt_hours'] > 0:
                        message_parts.append(f"⚠️ Долг сна: {sleep_rec['sleep_debt_hours']}ч")
                    message_parts.append(f"\n{sleep_rec['advice']}")
                    
                    # Workouts summary
                    if workouts:
                        message_parts.append("\n🏃 **Вчерашние тренировки:**")
                        for workout in workouts[:3]:  # Show max 3
                            sport = workout.get("sport_name", "Unknown")
                            w_strain = workout.get("strain")
                            message_parts.append(f"• {sport}: Strain {w_strain:.1f}" if w_strain else f"• {sport}")
                
                else:
                    message_parts.append("\n⚠️ Нет данных WHOOP за сегодня")
            
            else:
                message_parts.append("\n⚠️ WHOOP не подключен")
            
            # Gratitude prompt
            message_parts.append("\n\n🙏 **За что ты благодарен этим утром?**")
            message_parts.append("_Просто ответь на это сообщение_")
            
            message = "\n".join(message_parts)
            
            await self._app.bot.send_message(
                chat_id=self._chat_id,
                text=message,
                parse_mode='Markdown'
            )
            
            gratitude_module.set_waiting_for_gratitude(self._chat_id, "morning")
            logger.info("Утренний план с WHOOP анализом отправлен")
            
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
    
    async def send_streak_reminder_23(self) -> None:
        """
        Отправляет напоминание в 23:00, если прогресса нет.
        Не сбрасывает стрик - даёт время до 03:00.
        """
        if not self._app or not self._chat_id:
            logger.warning("Не могу отправить напоминание: app или chat_id не установлены")
            return
        
        try:
            from modules.productivity.module import productivity_module
            
            # Проверяем Notion на наличие прогресса
            has_progress = await productivity_module._check_notion_progress_today()
            
            if not has_progress:
                info = productivity_module.get_streak_info()
                if info['current'] > 0:
                    await self._app.bot.send_message(
                        chat_id=self._chat_id,
                        text=f"⚠️ **Напоминание о стрике**\n\nСегодня пока нет прогресса в Notion.\nТекущая серия: **{info['current']} дней**\n\nУ тебя есть время до 03:00, чтобы добавить прогресс или использовать /freeze для заморозки.",
                        parse_mode='Markdown'
                    )
                    logger.info("Отправлено напоминание о стрике в 23:00")
            else:
                logger.info("Прогресс есть, напоминание не требуется")
                
        except Exception as e:
            logger.error(f"Ошибка отправки напоминания о стрике: {e}")
    
    async def auto_update_streak(self) -> None:
        """
        Автоматически обновляет стрик каждый день в 03:00.
        Проверяет Notion на наличие прогресса за предыдущий день и обновляет стрик.
        Если прогресса нет - стрик может сброситься (или использоваться заморозка).
        """
        if not self._app or not self._chat_id:
            logger.warning("Не могу обновить стрик: app или chat_id не установлены")
            return
        
        try:
            from modules.productivity.module import productivity_module
            
            # Проверяем Notion и обновляем стрик
            updated = await productivity_module.check_notion_progress_and_update_streak()
            
            if updated:
                logger.info("Стрик автоматически обновлён на основе прогресса в Notion")
                
                # Отправляем подтверждение
                info = productivity_module.get_streak_info()
                await self._app.bot.send_message(
                    chat_id=self._chat_id,
                    text=f"🔥 **Стрик обновлён!**\n\nТекущая серия: **{info['current']} дней**\n\nОтличная работа! 🎉",
                    parse_mode='Markdown'
                )
            else:
                logger.info("Прогресса сегодня нет, стрик не обновлён")
                
                # Отправляем напоминание
                info = productivity_module.get_streak_info()
                if info['current'] > 0:
                    await self._app.bot.send_message(
                        chat_id=self._chat_id,
                        text=f"⚠️ **Стрик не обновлён**\n\nСегодня не было прогресса в Notion.\nТекущая серия: **{info['current']} дней**\n\nЕсли ты практиковался, обнови данные в Notion или используй /freeze для заморозки.",
                        parse_mode='Markdown'
                    )
                
        except Exception as e:
            logger.error(f"Ошибка автоматического обновления стрика: {e}")
    
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
