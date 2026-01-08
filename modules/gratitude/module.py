"""
Gratitude journal module
"""
import logging
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
from modules.notion.client import notion_client
from modules.voice.module import voice_module
from config.settings import NOTION_API_TOKEN

logger = logging.getLogger(__name__)

# Conversation states
WAITING_GRATITUDE = 1
WAITING_VOICE = 2


class GratitudeModule(BaseModule):
    """
    Gratitude journal module.
    Allows recording gratitude in the morning and evening,
    supports voice messages.
    """
    
    def __init__(self):
        super().__init__(
            name="gratitude",
            description="Gratitude journal with voice message support"
        )
        self._gratitude_db_id: Optional[str] = None
        self._waiting_for_gratitude: Dict[int, str] = {}  # chat_id -> time_of_day
    
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
    
    async def on_startup(self) -> None:
        """Initialization on startup"""
        # Check/create gratitude database
        await self._ensure_gratitude_database()
        
        # Set callback for voice messages
        voice_module.set_transcription_callback(self.handle_voice_gratitude)
    
    async def _ensure_gratitude_database(self) -> None:
        """Checks for gratitude database, creates if needed"""
        # For now using simple in-memory/file storage
        # In the future can create database in Notion
        logger.info("Gratitude module initialized")
    
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
            # Just show recognized text
            await update.message.reply_text(
                f"📝 Recognized text:\n\n{text}"
            )
            return
        
        time_of_day = self._waiting_for_gratitude.pop(chat_id)
        
        # Summarize text if needed
        summary = voice_module.summarize_text(text, max_length=500)
        
        await self._save_gratitude(update, context, summary, time_of_day, original=text)
    
    async def _save_gratitude(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        text: str,
        time_of_day: str,
        original: Optional[str] = None
    ) -> None:
        """Saves gratitude entry"""
        today = date.today().isoformat()
        
        # Save to bot context
        if 'gratitude_entries' not in context.bot_data:
            context.bot_data['gratitude_entries'] = []
        
        entry = {
            "date": today,
            "time_of_day": time_of_day,
            "text": text,
            "original_text": original,
            "timestamp": datetime.now().isoformat()
        }
        context.bot_data['gratitude_entries'].append(entry)
        
        # Try to save to Notion
        saved_to_notion = await self._save_to_notion(entry)
        
        # Format response
        emoji = "🌅" if time_of_day == "morning" else "🌙"
        response = f"{emoji} **Gratitude saved!**\n\n"
        response += f"_{text}_\n\n"
        
        if original and original != text:
            response += f"📝 Full text saved\n"
        
        if saved_to_notion:
            response += "✅ Synced to Notion"
        else:
            response += "💾 Saved locally"
        
        await update.message.reply_text(response, parse_mode='Markdown')
    
    async def _save_to_notion(self, entry: Dict) -> bool:
        """Saves entry to Notion"""
        if not self._gratitude_db_id:
            # No database yet - save only locally
            return False
        
        try:
            properties = {
                "Date": {
                    "date": {"start": entry["date"]}
                },
                "Time": {
                    "select": {"name": entry["time_of_day"].capitalize()}
                },
                "Gratitude": {
                    "title": [{"text": {"content": entry["text"][:100]}}]
                }
            }
            
            children = []
            if entry.get("original_text"):
                children.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": entry["original_text"]}}]
                    }
                })
            
            await notion_client.create_page(
                self._gratitude_db_id,
                properties,
                children if children else None
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to save to Notion: {e}")
            return False
    
    async def review_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Command /review - review gratitude entries"""
        entries = context.bot_data.get('gratitude_entries', [])
        
        if not entries:
            await update.message.reply_text(
                "📔 Journal is empty.\n"
                "Use /gratitude to make your first entry!"
            )
            return
        
        # Show last 5 entries
        recent = entries[-5:]
        
        message = "📔 **Recent Gratitude Entries**\n\n"
        
        for entry in reversed(recent):
            emoji = "🌅" if entry["time_of_day"] == "morning" else "🌙"
            message += f"{emoji} **{entry['date']}**\n"
            message += f"_{entry['text'][:100]}{'...' if len(entry['text']) > 100 else ''}_\n\n"
        
        message += f"Total entries: {len(entries)}"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
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
