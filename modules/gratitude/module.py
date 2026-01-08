"""
Gratitude journal module with Notion integration
"""
import logging
import os
import httpx
from typing import List, Dict, Optional
from datetime import datetime, date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    ContextTypes,
    BaseHandler,
    filters
)

from modules.base import BaseModule
from config.settings import NOTION_GRATITUDE_DATABASE_ID

logger = logging.getLogger(__name__)

# Conversation states
WAITING_GRATITUDE = 1
WAITING_VOICE = 2


class GratitudeModule(BaseModule):
    """
    Gratitude journal module with Notion integration.
    Allows recording gratitude in the morning and evening,
    supports voice messages.
    """
    
    def __init__(self):
        super().__init__(
            name="gratitude",
            description="Gratitude journal with Notion sync"
        )
        self._gratitude_db_id = NOTION_GRATITUDE_DATABASE_ID
        self._waiting_for_gratitude: Dict[int, str] = {}  # chat_id -> time_of_day
        logger.info(f"Gratitude module initialized with DB: {self._gratitude_db_id}")
    
    def get_handlers(self) -> List[BaseHandler]:
        """Returns command handlers"""
        return [
            CommandHandler("gratitude", self.gratitude_command),
            CommandHandler("review", self.review_command),
            CallbackQueryHandler(self.handle_time_selection, pattern="^gratitude_"),
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self.handle_text_gratitude
            ),
        ]
    
    async def gratitude_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Command /gratitude - write gratitude entry"""
        keyboard = [
            [
                InlineKeyboardButton("🌅 Morning", callback_data="gratitude_morning"),
                InlineKeyboardButton("🌙 Evening", callback_data="gratitude_evening"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🙏 **Gratitude Journal**\n\n"
            "Choose entry type:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def handle_time_selection(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handler for time of day selection"""
        query = update.callback_query
        await query.answer()
        
        time_of_day = query.data.replace("gratitude_", "")
        chat_id = update.effective_chat.id
        
        # Remember that we're waiting for gratitude from this user
        self._waiting_for_gratitude[chat_id] = time_of_day
        
        if time_of_day == "morning":
            prompt = (
                "🌅 **Morning Gratitude**\n\n"
                "What are you grateful for this morning?\n"
                "What good awaits you today?\n\n"
                "_Type your message or send a voice note_"
            )
        else:
            prompt = (
                "🌙 **Evening Gratitude**\n\n"
                "What are you grateful for today?\n"
                "What good happened today?\n\n"
                "_Type your message or send a voice note_"
            )
        
        await query.edit_message_text(prompt, parse_mode='Markdown')
    
    async def handle_text_gratitude(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handler for text gratitude"""
        chat_id = update.effective_chat.id
        
        # Check if we're waiting for gratitude from this user
        if chat_id not in self._waiting_for_gratitude:
            return  # Not our message
        
        time_of_day = self._waiting_for_gratitude.pop(chat_id)
        text = update.message.text
        
        await self._save_gratitude(update, context, text, time_of_day)
    
    async def handle_voice_gratitude(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        text: str
    ) -> None:
        """Handler for voice gratitude (callback from voice module)"""
        chat_id = update.effective_chat.id
        
        # Check if we're waiting for gratitude
        if chat_id not in self._waiting_for_gratitude:
            return
        
        time_of_day = self._waiting_for_gratitude.pop(chat_id)
        
        await self._save_gratitude(update, context, text, time_of_day, original=text)
    
    async def _save_gratitude(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        text: str,
        time_of_day: str,
        original: Optional[str] = None
    ) -> None:
        """Saves gratitude entry to Notion"""
        today = date.today().isoformat()
        
        entry = {
            "date": today,
            "time_of_day": time_of_day,
            "text": text,
            "original_text": original,
            "timestamp": datetime.now().isoformat()
        }
        
        # Save to Notion
        saved_to_notion = await self._save_to_notion(entry)
        
        # Format response
        emoji = "🌅" if time_of_day == "morning" else "🌙"
        response = f"{emoji} **Gratitude saved!**\n\n"
        response += f"_{text}_\n\n"
        
        if saved_to_notion:
            response += "✅ Synced to Notion"
        else:
            response += "⚠️ Couldn't sync to Notion"
        
        await update.message.reply_text(response, parse_mode='Markdown')
    
    async def _save_to_notion(self, entry: Dict) -> bool:
        """Saves entry to Notion database"""
        token = os.getenv("NOTION_API_TOKEN")
        
        if not token or not self._gratitude_db_id:
            logger.warning("Notion token or database ID not configured")
            return False
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        # Map time_of_day to Select options
        time_label = "Morning" if entry["time_of_day"] == "morning" else "Evening"
        
        data = {
            "parent": {
                "database_id": self._gratitude_db_id
            },
            "properties": {
                "Gratitude": {
                    "title": [
                        {
                            "text": {
                                "content": entry["text"][:2000]
                            }
                        }
                    ]
                },
                "Date": {
                    "date": {
                        "start": entry["date"]
                    }
                },
                "Select": {
                    "select": {
                        "name": time_label
                    }
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
                    logger.info(f"Gratitude saved to Notion: {entry['text'][:50]}...")
                    return True
                else:
                    logger.error(f"Notion API error: {response.status_code} - {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to save to Notion: {e}")
            return False
    
    async def review_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Command /review - review gratitude entries from Notion"""
        entries = await self._get_recent_entries()
        
        if not entries:
            await update.message.reply_text(
                "📔 Journal is empty.\n"
                "Use /gratitude to make your first entry!"
            )
            return
        
        message = "📔 **Recent Gratitude Entries**\n\n"
        
        for entry in entries[:5]:
            emoji = "🌅" if entry.get("time") == "Morning" else "🌙"
            message += f"{emoji} **{entry['date']}**\n"
            text = entry.get('text', '')
            message += f"_{text[:100]}{'...' if len(text) > 100 else ''}_\n\n"
        
        message += f"Total entries: {len(entries)}"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def _get_recent_entries(self) -> List[Dict]:
        """Gets recent entries from Notion"""
        token = os.getenv("NOTION_API_TOKEN")
        
        if not token or not self._gratitude_db_id:
            return []
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        data = {
            "sorts": [
                {
                    "property": "Date",
                    "direction": "descending"
                }
            ],
            "page_size": 10
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.notion.com/v1/databases/{self._gratitude_db_id}/query",
                    headers=headers,
                    json=data,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    results = response.json().get("results", [])
                    entries = []
                    
                    for page in results:
                        props = page.get("properties", {})
                        
                        # Get title
                        title_prop = props.get("Gratitude", {})
                        title_arr = title_prop.get("title", [])
                        text = title_arr[0].get("plain_text", "") if title_arr else ""
                        
                        # Get date
                        date_prop = props.get("Date", {})
                        date_obj = date_prop.get("date", {})
                        date_str = date_obj.get("start", "") if date_obj else ""
                        
                        # Get time of day
                        select_prop = props.get("Select", {})
                        select_obj = select_prop.get("select", {})
                        time_str = select_obj.get("name", "") if select_obj else ""
                        
                        entries.append({
                            "text": text,
                            "date": date_str,
                            "time": time_str
                        })
                    
                    return entries
                else:
                    logger.error(f"Notion query error: {response.status_code}")
                    return []
                    
        except Exception as e:
            logger.error(f"Failed to get entries from Notion: {e}")
            return []
    
    def get_morning_prompt(self) -> str:
        """Returns morning prompt for gratitude"""
        return (
            "🌅 **Good morning!**\n\n"
            "Start your day with gratitude.\n"
            "What are you grateful for this morning?\n\n"
            "_Type your message or send a voice note_"
        )
    
    def get_evening_prompt(self) -> str:
        """Returns evening prompt for gratitude"""
        return (
            "🌙 **Good evening!**\n\n"
            "Time to reflect on the day.\n"
            "What are you grateful for today?\n\n"
            "_Type your message or send a voice note_"
        )
    
    def set_waiting_for_gratitude(self, chat_id: int, time_of_day: str) -> None:
        """Sets gratitude waiting state for chat"""
        self._waiting_for_gratitude[chat_id] = time_of_day


# Module instance
gratitude_module = GratitudeModule()
