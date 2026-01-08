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
        self.notion_token = os.getenv("NOTION_API_TOKEN")
        # Используем database_id, а не data_source_id
        self.database_id = "2e28db7c936780b28d66e45ab2e6f7e6"
        self.notion_api_url = "https://api.notion.com/v1/pages"
        
        # Логируем статус инициализации
        if self.notion_token:
            logger.info(f"Ideas module initialized with token: {self.notion_token[:10]}...")
        else:
            logger.warning("Ideas module: NOTION_API_TOKEN not set!")
        
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
        # Перечитываем токен на случай, если он был установлен позже
        token = os.getenv("NOTION_API_TOKEN")
        if not token:
            logger.error("NOTION_API_TOKEN not set in environment")
            return {
                "success": False,
                "message": "Notion не настроен (нет токена)",
                "url": None
            }
        
        headers = {
            "Authorization": f"Bearer {token}",
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
        
        logger.info(f"Saving idea to Notion: {idea_text[:50]}...")
        logger.info(f"Database ID: {self.database_id}")
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.notion_api_url,
                    headers=headers,
                    json=data,
                    timeout=30.0
                )
                
                logger.info(f"Notion API response: {response.status_code}")
                
                if response.status_code == 200:
                    result = response.json()
                    page_url = result.get("url", "")
                    logger.info(f"Idea saved successfully: {page_url}")
                    return {
                        "success": True,
                        "message": "Идея сохранена в Notion",
                        "url": page_url
                    }
                else:
                    error_text = response.text
                    logger.error(f"Notion API error: {response.status_code} - {error_text}")
                    
                    # Пробуем альтернативный формат database_id
                    if response.status_code == 404:
                        return await self._try_alternative_save(token, idea_text, headers)
                    
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
    
    async def _try_alternative_save(self, token: str, idea_text: str, headers: dict) -> dict:
        """Пробует альтернативный формат database_id с дефисами"""
        # Пробуем с дефисами
        alt_database_id = "2e28db7c-9367-80b2-8d66-e45ab2e6f7e6"
        
        data = {
            "parent": {
                "database_id": alt_database_id
            },
            "properties": {
                "Idea": {
                    "title": [
                        {
                            "text": {
                                "content": idea_text[:2000]
                            }
                        }
                    ]
                }
            }
        }
        
        logger.info(f"Trying alternative database ID: {alt_database_id}")
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.notion_api_url,
                    headers=headers,
                    json=data,
                    timeout=30.0
                )
                
                logger.info(f"Alternative Notion API response: {response.status_code}")
                
                if response.status_code == 200:
                    result = response.json()
                    page_url = result.get("url", "")
                    # Обновляем database_id на рабочий
                    self.database_id = alt_database_id
                    logger.info(f"Idea saved with alternative ID: {page_url}")
                    return {
                        "success": True,
                        "message": "Идея сохранена в Notion",
                        "url": page_url
                    }
                else:
                    error_text = response.text
                    logger.error(f"Alternative also failed: {response.status_code} - {error_text}")
                    return {
                        "success": False,
                        "message": f"Ошибка Notion API: {response.status_code}",
                        "url": None
                    }
        except Exception as e:
            logger.error(f"Error in alternative save: {e}")
            return {
                "success": False,
                "message": f"Ошибка: {str(e)}",
                "url": None
            }


# Глобальный экземпляр модуля
ideas_module = IdeasModule()
