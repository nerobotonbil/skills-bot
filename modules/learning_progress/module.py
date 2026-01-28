"""
Learning Progress tracking module with dual-track system (50 skills + additional courses)
"""
import logging
import os
import httpx
from typing import List, Dict, Optional
from datetime import datetime, date, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    BaseHandler
)

from modules.base import BaseModule, owner_only
from config.settings import LEARNING_PROGRESS_DATABASE_ID

logger = logging.getLogger(__name__)


class LearningProgressModule(BaseModule):
    """
    Learning progress tracking with two tracks: Main Skills (50 skills) and Additional Courses
    """
    
    def __init__(self):
        super().__init__(
            name="learning_progress",
            description="Dual-track learning progress tracker"
        )
        self._db_id = LEARNING_PROGRESS_DATABASE_ID
        logger.info(f"Learning Progress module initialized with DB: {self._db_id}")
    
    def get_handlers(self) -> List[BaseHandler]:
        """Returns command handlers"""
        return [
            CommandHandler("today", self.today_command),
            CallbackQueryHandler(self.handle_progress_selection, pattern="^progress_"),
        ]
    
    @owner_only
    async def today_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Command /today - mark today's learning progress"""
        keyboard = [
            [
                InlineKeyboardButton("✅ 50 скиллов", callback_data="progress_main"),
                InlineKeyboardButton("✅ Доп. курсы", callback_data="progress_additional"),
            ],
            [
                InlineKeyboardButton("✅ Оба", callback_data="progress_both"),
                InlineKeyboardButton("❌ Ничего", callback_data="progress_none"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📚 Что сегодня изучил?",
            reply_markup=reply_markup
        )
    
    @owner_only
    async def handle_progress_selection(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handler for progress selection buttons"""
        query = update.callback_query
        await query.answer()
        
        selection = query.data.replace("progress_", "")
        
        main_skills = False
        additional_courses = False
        
        if selection == "main":
            main_skills = True
            message = "✅ Отметил: 50 скиллов"
        elif selection == "additional":
            additional_courses = True
            message = "✅ Отметил: Доп. курсы"
        elif selection == "both":
            main_skills = True
            additional_courses = True
            message = "✅ Отметил: Оба трека"
        else:  # none
            message = "📝 Записал: ничего не изучал сегодня"
        
        # Save to Notion
        saved = await self._save_progress(main_skills, additional_courses)
        
        if saved:
            message += "\n✅ Синхронизировано с Notion"
            
            # Get weekly stats
            stats = await self._get_weekly_stats()
            if stats:
                message += f"\n\n📊 За последние 7 дней:\n"
                message += f"• 50 скиллов: {stats['main_count']}/7\n"
                message += f"• Доп. курсы: {stats['additional_count']}/7"
                
                # Smart reminder if additional courses are neglected
                if stats['additional_count'] == 0 and stats['main_count'] >= 3:
                    message += "\n\n⚠️ Не забывай про дополнительные курсы!"
        else:
            message += "\n⚠️ Не удалось синхронизировать с Notion"
        
        await query.edit_message_text(message)
    
    async def _save_progress(
        self,
        main_skills: bool,
        additional_courses: bool
    ) -> bool:
        """Saves progress entry to Notion"""
        token = os.getenv("NOTION_API_TOKEN")
        
        if not token or not self._db_id:
            logger.warning("Notion token or database ID not configured")
            return False
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        today = date.today().isoformat()
        
        data = {
            "parent": {"database_id": self._db_id},
            "properties": {
                "Name": {
                    "title": [{"text": {"content": f"Progress {today}"}}]
                },
                "Date": {
                    "date": {"start": today}
                },
                "Main Skills": {
                    "checkbox": main_skills
                },
                "Additional Courses": {
                    "checkbox": additional_courses
                }
            }
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.notion.com/v1/pages",
                    headers=headers,
                    json=data,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    logger.info(f"Progress saved: main={main_skills}, additional={additional_courses}")
                    return True
                else:
                    logger.error(f"Notion API error: {response.status_code} - {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to save progress: {e}")
            return False
    
    async def _get_weekly_stats(self) -> Optional[Dict]:
        """Gets weekly statistics for both tracks"""
        token = os.getenv("NOTION_API_TOKEN")
        
        if not token or not self._db_id:
            return None
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        # Get entries from last 7 days
        seven_days_ago = (date.today() - timedelta(days=7)).isoformat()
        
        filter_data = {
            "filter": {
                "property": "Date",
                "date": {
                    "on_or_after": seven_days_ago
                }
            }
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.notion.com/v1/databases/{self._db_id}/query",
                    headers=headers,
                    json=filter_data,
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to query Notion: {response.status_code}")
                    return None
                
                results = response.json().get("results", [])
                
                main_count = 0
                additional_count = 0
                
                for entry in results:
                    props = entry.get("properties", {})
                    
                    if props.get("Main Skills", {}).get("checkbox", False):
                        main_count += 1
                    
                    if props.get("Additional Courses", {}).get("checkbox", False):
                        additional_count += 1
                
                return {
                    "main_count": main_count,
                    "additional_count": additional_count,
                    "total_entries": len(results)
                }
                
        except Exception as e:
            logger.error(f"Failed to get weekly stats: {e}")
            return None
    
    async def check_and_send_reminder(self, app, chat_id: int) -> None:
        """
        Checks if additional courses are being neglected and sends reminder if needed.
        Called by reminder service.
        """
        stats = await self._get_weekly_stats()
        
        if not stats:
            return
        
        # If user studied main skills 5+ days but additional courses 0-1 days
        if stats['main_count'] >= 5 and stats['additional_count'] <= 1:
            message = (
                "⚠️ Напоминание о балансе обучения\n\n"
                f"За последние 7 дней:\n"
                f"• 50 скиллов: {stats['main_count']} дней\n"
                f"• Доп. курсы: {stats['additional_count']} дней\n\n"
                "Не забывай про дополнительные курсы! "
                "Они помогут применить знания на практике.\n\n"
                "Используй /today чтобы отметить прогресс."
            )
            
            try:
                await app.bot.send_message(
                    chat_id=chat_id,
                    text=message
                )
                logger.info("Sent balance reminder for additional courses")
            except Exception as e:
                logger.error(f"Failed to send balance reminder: {e}")


# Module instance
learning_progress_module = LearningProgressModule()
