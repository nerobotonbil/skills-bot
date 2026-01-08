"""
Модуль записи идей в Notion
"""
import logging
import os
import httpx
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes, BaseHandler, MessageHandler, filters

from modules.base import BaseModule

logger = logging.getLogger(__name__)


class IdeasModule(BaseModule):
    """
    Модуль для записи идей в Notion.
    Работает через AI-ассистента, который определяет намерение записать идею.
    """
    
    def __init__(self):
        super().__init__(
            name="ideas",
            description="Запись идей и заметок в Notion"
        )
        self.notion_token = os.getenv("NOTION_TOKEN")
        self.database_id = "2e28db7c-9367-80cf-b223-000b195b9453"  # Data Source ID
        self.notion_api_url = "https://api.notion.com/v1/pages"
        
    def get_handlers(self):
        """Этот модуль не имеет прямых обработчиков - работает через AI"""
        return []
    
    async def save_idea(self, idea_text: str, user_id: int = None) -> dict:
        """
        Сохраняет идею в Notion.
        
        Args:
            idea_text: Текст идеи (уже обработанный AI)
            user_id: ID пользователя Telegram
            
        Returns:
            dict с результатом: {"success": bool, "message": str, "url": str}
        """
        if not self.notion_token:
            logger.error("NOTION_TOKEN not set")
            return {
                "success": False,
                "message": "Notion не настроен",
                "url": None
            }
        
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        # Формируем данные для создания страницы
        data = {
            "parent": {
                "database_id": self.database_id
            },
            "properties": {
                "Idea": {
                    "title": [
                        {
                            "text": {
                                "content": idea_text[:2000]  # Notion limit
                            }
                        }
                    ]
                }
            }
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.notion_api_url,
                    headers=headers,
                    json=data,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    page_url = result.get("url", "")
                    logger.info(f"Idea saved to Notion: {idea_text[:50]}...")
                    return {
                        "success": True,
                        "message": "Идея сохранена в Notion",
                        "url": page_url
                    }
                else:
                    logger.error(f"Notion API error: {response.status_code} - {response.text}")
                    return {
                        "success": False,
                        "message": f"Ошибка Notion API: {response.status_code}",
                        "url": None
                    }
                    
        except Exception as e:
            logger.error(f"Error saving idea to Notion: {e}")
            return {
                "success": False,
                "message": f"Ошибка: {str(e)}",
                "url": None
            }


# Глобальный экземпляр модуля
ideas_module = IdeasModule()
