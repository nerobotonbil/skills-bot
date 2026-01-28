"""
Learning Progress tracking module with interactive checklist buttons
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
    Learning progress tracking with interactive checklist buttons
    """
    
    def __init__(self):
        super().__init__(
            name="learning_progress",
            description="Interactive learning progress tracker with checklist"
        )
        self._db_id = LEARNING_PROGRESS_DATABASE_ID
        self._current_course_name = "Доп. курсы"  # Default course name
        logger.info(f"Learning Progress module initialized with DB: {self._db_id}")
    
    def get_handlers(self) -> List[BaseHandler]:
        """Returns command handlers"""
        return [
            CommandHandler("today", self.today_command),
            CommandHandler("set_course", self.set_course_command),
            CallbackQueryHandler(self.handle_checklist_toggle, pattern="^lp_toggle_"),
            CallbackQueryHandler(self.handle_save, pattern="^lp_save$"),
        ]
    
    @owner_only
    async def set_course_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Command /set_course - set custom course name"""
        if context.args:
            course_name = " ".join(context.args)
            self._current_course_name = course_name
            message = f"✅ Установлен курс: {course_name}"
        else:
            self._current_course_name = "Доп. курсы"
            message = "✅ Сброшено на: Доп. курсы"
        
        await update.message.reply_text(message)
    
    @owner_only
    async def today_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Command /today - show interactive checklist for learning progress"""
        # Initialize state: nothing selected
        keyboard = self._build_keyboard(main_selected=False, additional_selected=False)
        
        await update.message.reply_text(
            "📚 Что сегодня изучил?\n\nВыбери нужные пункты:",
            reply_markup=keyboard
        )
    
    def _build_keyboard(self, main_selected: bool, additional_selected: bool) -> InlineKeyboardMarkup:
        """Build keyboard with current selection state"""
        main_icon = "☑️" if main_selected else "⬜️"
        additional_icon = "☑️" if additional_selected else "⬜️"
        
        keyboard = [
            [
                InlineKeyboardButton(
                    f"{main_icon} 50 скиллов", 
                    callback_data="lp_toggle_main"
                ),
            ],
            [
                InlineKeyboardButton(
                    f"{additional_icon} {self._current_course_name}", 
                    callback_data="lp_toggle_additional"
                ),
            ],
            [
                InlineKeyboardButton("💾 Сохранить", callback_data="lp_save"),
            ]
        ]
        
        return InlineKeyboardMarkup(keyboard)
    
    @owner_only
    async def handle_checklist_toggle(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle toggle button clicks"""
        query = update.callback_query
        await query.answer()
        
        # Parse current state from message text or callback data
        # We'll store state in callback_data by encoding it
        toggle_type = query.data.replace("lp_toggle_", "")
        
        # Get current state from keyboard buttons
        current_keyboard = query.message.reply_markup.inline_keyboard
        main_selected = "☑️" in current_keyboard[0][0].text
        additional_selected = "☑️" in current_keyboard[1][0].text
        
        # Toggle the clicked item
        if toggle_type == "main":
            main_selected = not main_selected
        elif toggle_type == "additional":
            additional_selected = not additional_selected
        
        # Update keyboard
        new_keyboard = self._build_keyboard(main_selected, additional_selected)
        
        await query.edit_message_reply_markup(reply_markup=new_keyboard)
    
    @owner_only
    async def handle_save(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle save button click"""
        query = update.callback_query
        await query.answer("Сохраняю...")
        
        # Get current state from keyboard
        current_keyboard = query.message.reply_markup.inline_keyboard
        main_selected = "☑️" in current_keyboard[0][0].text
        additional_selected = "☑️" in current_keyboard[1][0].text
        
        # Save to Notion
        saved = await self._save_progress(main_selected, additional_selected, self._current_course_name)
        
        # Build result message
        if not main_selected and not additional_selected:
            message = "📝 Записал: ничего не изучал сегодня"
        else:
            parts = []
            if main_selected:
                parts.append("50 скиллов")
            if additional_selected:
                parts.append(self._current_course_name)
            message = f"✅ Отметил: {', '.join(parts)}"
        
        if saved:
            message += "\n✅ Синхронизировано с Notion"
            
            # Get weekly stats
            stats = await self._get_weekly_stats()
            if stats:
                message += f"\n\n📊 За последние 7 дней:\n"
                message += f"• 50 скиллов: {stats['main_count']}/7\n"
                message += f"• {self._current_course_name}: {stats['additional_count']}/7"
                
                # Smart reminder if additional courses are neglected
                if stats['additional_count'] == 0 and stats['main_count'] >= 3:
                    message += f"\n\n⚠️ Не забывай про {self._current_course_name}!"
        else:
            message += "\n⚠️ Не удалось синхронизировать с Notion"
        
        # Remove keyboard and show final message
        await query.edit_message_text(message)
    
    async def _save_progress(
        self,
        main_skills: bool,
        additional_courses: bool,
        course_name: str = "Доп. курсы"
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
                },
                "Course Name": {
                    "rich_text": [{"text": {"content": course_name}}]
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
                    logger.info(f"Progress saved: main={main_skills}, additional={additional_courses}, course={course_name}")
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
                f"• {self._current_course_name}: {stats['additional_count']} дней\n\n"
                f"Не забывай про {self._current_course_name}! "
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
