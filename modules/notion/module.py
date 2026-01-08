"""
Модуль интеграции с Notion
"""
import logging
from typing import List, Optional
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes, BaseHandler

from modules.base import BaseModule
from modules.notion.client import notion_client

logger = logging.getLogger(__name__)


class NotionModule(BaseModule):
    """
    Модуль для интеграции с Notion.
    Обеспечивает синхронизацию данных и базовые команды.
    """
    
    def __init__(self):
        super().__init__(
            name="notion",
            description="Интеграция с Notion для хранения данных"
        )
        self.client = notion_client
        self._all_skills_cache: List[dict] = []  # Все навыки
        self._active_skills_cache: List[dict] = []  # Только активные
        self._cache_updated = None
    
    def get_handlers(self) -> List[BaseHandler]:
        """Возвращает обработчики команд"""
        return [
            CommandHandler("sync", self.sync_command),
        ]
    
    async def on_startup(self) -> None:
        """Загружает данные при запуске"""
        await self.refresh_skills_cache()
    
    async def on_shutdown(self) -> None:
        """Закрывает клиент при остановке"""
        await self.client.close()
    
    async def refresh_skills_cache(self) -> List[dict]:
        """Обновляет кэш навыков"""
        try:
            # Загружаем все навыки
            self._all_skills_cache = await self.client.get_all_skills()
            
            # Фильтруем только активные (с прогрессом > 0)
            self._active_skills_cache = self.client.filter_active_skills(
                self._all_skills_cache
            )
            
            # Рассчитываем приоритеты для активных навыков
            self._active_skills_cache = self.client.calculate_skill_priorities(
                self._active_skills_cache
            )
            
            from datetime import datetime
            self._cache_updated = datetime.now()
            
            logger.info(
                f"Skills cache refreshed: {len(self._all_skills_cache)} total, "
                f"{len(self._active_skills_cache)} active"
            )
            
            return self._active_skills_cache
            
        except Exception as e:
            logger.error(f"Failed to refresh skills cache: {e}")
            return self._active_skills_cache
    
    def get_skills(self) -> List[dict]:
        """Возвращает кэшированные АКТИВНЫЕ навыки"""
        return self._active_skills_cache
    
    def get_all_skills(self) -> List[dict]:
        """Возвращает ВСЕ навыки (включая неактивные)"""
        return self._all_skills_cache
    
    def get_active_skills_count(self) -> int:
        """Возвращает количество активных навыков"""
        return len(self._active_skills_cache)
    
    def get_total_skills_count(self) -> int:
        """Возвращает общее количество навыков"""
        return len(self._all_skills_cache)
    
    def get_skill_by_name(self, name: str) -> Optional[dict]:
        """Находит навык по имени среди активных"""
        for skill in self._active_skills_cache:
            if skill["name"].lower() == name.lower():
                return skill
        return None
    
    async def sync_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Команда /sync - синхронизация с Notion"""
        await update.message.reply_text("🔄 Синхронизация с Notion...")
        
        try:
            skills = await self.refresh_skills_cache()
            
            # Формируем список активных навыков
            active_names = [s["name"] for s in skills]
            active_list = "\n".join([f"• {name}" for name in active_names]) if active_names else "Нет активных навыков"
            
            await update.message.reply_text(
                f"✅ Синхронизация завершена!\n\n"
                f"Всего навыков: {self.get_total_skills_count()}\n"
                f"Активных (изучаются): {self.get_active_skills_count()}\n\n"
                f"📚 **Активные навыки:**\n{active_list}",
                parse_mode='Markdown'
            )
        except Exception as e:
            await update.message.reply_text(
                f"❌ Ошибка синхронизации: {str(e)}"
            )


# Экземпляр модуля
notion_module = NotionModule()
