"""
Клиент для работы с Notion API
"""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import httpx

from config.settings import (
    NOTION_API_TOKEN,
    NOTION_SKILLS_DATABASE_ID,
    MAX_VALUES
)

logger = logging.getLogger(__name__)

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


class NotionClient:
    """
    Клиент для работы с Notion API.
    Обеспечивает чтение и запись данных в базы данных Notion.
    """
    
    def __init__(self, token: str = NOTION_API_TOKEN):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_VERSION
        }
        self._client = httpx.AsyncClient(headers=self.headers, timeout=30.0)
    
    async def close(self):
        """Закрывает HTTP клиент"""
        await self._client.aclose()
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        json: Optional[Dict] = None
    ) -> Dict:
        """Выполняет запрос к Notion API"""
        url = f"{NOTION_API_BASE}{endpoint}"
        
        try:
            response = await self._client.request(method, url, json=json)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Notion API error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Request error: {e}")
            raise
    
    async def get_database(self, database_id: str) -> Dict:
        """Получает информацию о базе данных"""
        return await self._request("GET", f"/databases/{database_id}")
    
    async def query_database(
        self,
        database_id: str,
        filter: Optional[Dict] = None,
        sorts: Optional[List[Dict]] = None,
        page_size: int = 100
    ) -> List[Dict]:
        """
        Запрашивает записи из базы данных.
        
        Args:
            database_id: ID базы данных
            filter: Фильтр для запроса
            sorts: Сортировка
            page_size: Количество записей на странице
            
        Returns:
            Список записей
        """
        body = {"page_size": page_size}
        if filter:
            body["filter"] = filter
        if sorts:
            body["sorts"] = sorts
        
        results = []
        has_more = True
        start_cursor = None
        
        while has_more:
            if start_cursor:
                body["start_cursor"] = start_cursor
            
            response = await self._request(
                "POST",
                f"/databases/{database_id}/query",
                json=body
            )
            
            results.extend(response.get("results", []))
            has_more = response.get("has_more", False)
            start_cursor = response.get("next_cursor")
        
        return results
    
    async def get_page(self, page_id: str) -> Dict:
        """Получает страницу по ID"""
        return await self._request("GET", f"/pages/{page_id}")
    
    async def create_page(
        self,
        parent_database_id: str,
        properties: Dict[str, Any],
        children: Optional[List[Dict]] = None
    ) -> Dict:
        """
        Создаёт новую страницу в базе данных.
        
        Args:
            parent_database_id: ID родительской базы данных
            properties: Свойства страницы
            children: Содержимое страницы (блоки)
            
        Returns:
            Созданная страница
        """
        body = {
            "parent": {"database_id": parent_database_id},
            "properties": properties
        }
        
        if children:
            body["children"] = children
        
        return await self._request("POST", "/pages", json=body)
    
    async def update_page(
        self,
        page_id: str,
        properties: Dict[str, Any]
    ) -> Dict:
        """
        Обновляет свойства страницы.
        
        Args:
            page_id: ID страницы
            properties: Новые свойства
            
        Returns:
            Обновлённая страница
        """
        return await self._request(
            "PATCH",
            f"/pages/{page_id}",
            json={"properties": properties}
        )
    
    async def create_database(
        self,
        parent_page_id: str,
        title: str,
        properties: Dict[str, Dict]
    ) -> Dict:
        """
        Создаёт новую базу данных.
        
        Args:
            parent_page_id: ID родительской страницы
            title: Название базы данных
            properties: Схема свойств
            
        Returns:
            Созданная база данных
        """
        body = {
            "parent": {"page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": title}}],
            "properties": properties
        }
        
        return await self._request("POST", "/databases", json=body)
    
    # === Методы для работы с навыками ===
    
    async def get_all_skills(self) -> List[Dict]:
        """
        Получает все навыки из базы данных.
        
        Returns:
            Список навыков с их прогрессом
        """
        pages = await self.query_database(NOTION_SKILLS_DATABASE_ID)
        
        skills = []
        for page in pages:
            skill = self._parse_skill_page(page)
            if skill:
                skills.append(skill)
        
        return skills
    
    def _parse_skill_page(self, page: Dict) -> Optional[Dict]:
        """Парсит страницу навыка в удобный формат"""
        try:
            props = page.get("properties", {})
            
            # Получаем название навыка
            skill_prop = props.get("Skill", {})
            title_list = skill_prop.get("title", [])
            skill_name = title_list[0]["plain_text"] if title_list else "Unknown"
            
            # Получаем числовые значения
            def get_number(prop_name: str) -> float:
                prop = props.get(prop_name, {})
                value = prop.get("number") or 0.0
                if prop_name == "Video's":
                    logger.info(f"Skill {skill_name}: Video's raw prop = {prop}, value = {value}")
                return value
            
            return {
                "id": page["id"],
                "url": page["url"],
                "name": skill_name,
                "lectures": get_number("Lectures"),
                "videos": get_number("Video's"),
                "practice_hours": get_number("Practice hours"),
                "films": get_number("Films "),
                "vc_lectures": get_number("VC Lectures"),
                "last_edited": page.get("last_edited_time", "")
            }
        except Exception as e:
            logger.error(f"Error parsing skill page: {e}")
            return None
    
    async def update_skill_progress(
        self,
        page_id: str,
        field: str,
        value: float
    ) -> Dict:
        """
        Обновляет прогресс по навыку.
        
        Args:
            page_id: ID страницы навыка
            field: Поле для обновления (Lectures, Video's, Practice hours, etc.)
            value: Новое значение
        """
        properties = {
            field: {"number": value}
        }
        return await self.update_page(page_id, properties)
    
    def is_skill_active(self, skill: Dict) -> bool:
        """
        Проверяет, является ли навык активным.
        Навык считается активным, если хотя бы один прогресс-бар > 0.
        
        Args:
            skill: Словарь с данными навыка
            
        Returns:
            True если навык активный
        """
        return (
            skill["lectures"] > 0 or
            skill["videos"] > 0 or
            skill["practice_hours"] > 0 or
            skill["films"] > 0 or
            skill["vc_lectures"] > 0
        )
    
    def filter_active_skills(self, skills: List[Dict]) -> List[Dict]:
        """
        Фильтрует только активные навыки (с прогрессом > 0).
        
        Args:
            skills: Список всех навыков
            
        Returns:
            Список только активных навыков
        """
        active = [s for s in skills if self.is_skill_active(s)]
        logger.info(f"Active skills: {len(active)} out of {len(skills)}")
        return active
    
    def calculate_skill_priorities(self, skills: List[Dict]) -> List[Dict]:
        """
        Рассчитывает приоритеты для каждого навыка.
        Чем меньше прогресс — тем выше приоритет.
        
        Returns:
            Список навыков с приоритетами, отсортированный по приоритету
        """
        for skill in skills:
            # Рассчитываем прогресс по каждому типу контента
            lectures_progress = skill["lectures"] / MAX_VALUES["Lectures"]
            videos_progress = skill["videos"] / MAX_VALUES["Video's"]
            practice_progress = skill["practice_hours"] / MAX_VALUES["Practice hours"]
            
            # Общий прогресс (среднее)
            total_progress = (lectures_progress + videos_progress + practice_progress) / 3
            
            # Приоритеты по типам (чем меньше прогресс — тем выше приоритет)
            skill["priorities"] = {
                "lectures": 1 - lectures_progress,
                "videos": 1 - videos_progress,
                "practice": 1 - practice_progress,
                "total": 1 - total_progress
            }
            
            skill["progress"] = {
                "lectures": lectures_progress,
                "videos": videos_progress,
                "practice": practice_progress,
                "total": total_progress
            }
        
        # Сортируем по общему приоритету (от высокого к низкому)
        skills.sort(key=lambda x: x["priorities"]["total"], reverse=True)
        
        return skills


# Глобальный экземпляр клиента
notion_client = NotionClient()
