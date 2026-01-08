"""
Планировщик задач для напоминаний
"""
import logging
from datetime import datetime, time
from typing import Callable, Optional
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config.settings import TIMEZONE

logger = logging.getLogger(__name__)


class TaskScheduler:
    """
    Планировщик задач для отправки напоминаний.
    Использует APScheduler для асинхронного планирования.
    """
    
    def __init__(self):
        self.timezone = pytz.timezone(TIMEZONE)
        self.scheduler = AsyncIOScheduler(timezone=self.timezone)
        self._started = False
    
    def start(self) -> None:
        """Запускает планировщик"""
        if not self._started:
            self.scheduler.start()
            self._started = True
            logger.info("Scheduler started")
    
    def stop(self) -> None:
        """Останавливает планировщик"""
        if self._started:
            self.scheduler.shutdown()
            self._started = False
            logger.info("Scheduler stopped")
    
    def add_daily_job(
        self,
        job_id: str,
        callback: Callable,
        hour: int,
        minute: int = 0,
        **kwargs
    ) -> None:
        """
        Добавляет ежедневную задачу.
        
        Args:
            job_id: Уникальный идентификатор задачи
            callback: Асинхронная функция для выполнения
            hour: Час выполнения (0-23)
            minute: Минута выполнения (0-59)
            **kwargs: Дополнительные аргументы для callback
        """
        trigger = CronTrigger(hour=hour, minute=minute, timezone=self.timezone)
        
        # Удаляем существующую задачу, если есть
        existing = self.scheduler.get_job(job_id)
        if existing:
            self.scheduler.remove_job(job_id)
        
        self.scheduler.add_job(
            callback,
            trigger=trigger,
            id=job_id,
            kwargs=kwargs,
            replace_existing=True
        )
        logger.info(f"Daily job '{job_id}' scheduled at {hour:02d}:{minute:02d}")
    
    def add_weekly_job(
        self,
        job_id: str,
        callback: Callable,
        day_of_week: int,
        hour: int,
        minute: int = 0,
        **kwargs
    ) -> None:
        """
        Adds a weekly job.
        
        Args:
            job_id: Unique job identifier
            callback: Async function to execute
            day_of_week: Day of week (0=Monday, 4=Friday, 6=Sunday)
            hour: Hour to execute (0-23)
            minute: Minute to execute (0-59)
            **kwargs: Additional arguments for callback
        """
        trigger = CronTrigger(
            day_of_week=day_of_week, 
            hour=hour, 
            minute=minute, 
            timezone=self.timezone
        )
        
        existing = self.scheduler.get_job(job_id)
        if existing:
            self.scheduler.remove_job(job_id)
        
        self.scheduler.add_job(
            callback,
            trigger=trigger,
            id=job_id,
            kwargs=kwargs,
            replace_existing=True
        )
        days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        logger.info(f"Weekly job '{job_id}' scheduled for {days[day_of_week]} at {hour:02d}:{minute:02d}")
    
    def add_interval_job(
        self,
        job_id: str,
        callback: Callable,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
        **kwargs
    ) -> None:
        """
        Добавляет периодическую задачу.
        
        Args:
            job_id: Уникальный идентификатор задачи
            callback: Асинхронная функция для выполнения
            hours: Интервал в часах
            minutes: Интервал в минутах
            seconds: Интервал в секундах
            **kwargs: Дополнительные аргументы для callback
        """
        # Удаляем существующую задачу, если есть
        existing = self.scheduler.get_job(job_id)
        if existing:
            self.scheduler.remove_job(job_id)
        
        self.scheduler.add_job(
            callback,
            'interval',
            id=job_id,
            hours=hours,
            minutes=minutes,
            seconds=seconds,
            kwargs=kwargs,
            replace_existing=True
        )
        logger.info(f"Interval job '{job_id}' scheduled every {hours}h {minutes}m {seconds}s")
    
    def remove_job(self, job_id: str) -> bool:
        """Удаляет задачу"""
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"Job '{job_id}' removed")
            return True
        except Exception as e:
            logger.warning(f"Failed to remove job '{job_id}': {e}")
            return False
    
    def get_jobs(self) -> list:
        """Возвращает список всех задач"""
        return self.scheduler.get_jobs()
    
    def parse_time(self, time_str: str) -> tuple:
        """
        Парсит строку времени в формате HH:MM.
        
        Returns:
            Tuple (hour, minute)
        """
        parts = time_str.split(":")
        return int(parts[0]), int(parts[1])


# Глобальный экземпляр планировщика
scheduler = TaskScheduler()
