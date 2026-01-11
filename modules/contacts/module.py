"""
Contacts module for managing networking contacts
"""
import logging
import json
from typing import List, Optional, Dict, Any
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    BaseHandler,
    filters,
    ConversationHandler
)

from modules.base import BaseModule

logger = logging.getLogger(__name__)

# Conversation states
(
    WAITING_NAME,
    WAITING_VALUE,
    WAITING_NATIONALITY,
    WAITING_DATE,
    WAITING_CONTACT_TYPE,
    WAITING_FOLLOWUP,
    WAITING_WARM_WORD,
    WAITING_INDUSTRY
) = range(8)

# Notion database configuration
CONTACTS_DATABASE_ID = "28b8db7c936780b9a5c1facea087a15a"
CONTACTS_DATA_SOURCE_ID = "28b8db7c-9367-817e-91b5-000bbc2b2534"


class ContactsModule(BaseModule):
    """
    Module for managing networking contacts in Notion.
    Allows adding new contacts with all relevant information.
    """
    
    def __init__(self):
        super().__init__(
            name="contacts",
            description="Manage networking contacts in Notion"
        )
        self._temp_contact_data: Dict[int, Dict[str, Any]] = {}
    
    def get_handlers(self) -> List[BaseHandler]:
        """Returns command handlers"""
        
        # Conversation handler for adding contacts
        add_contact_handler = ConversationHandler(
            entry_points=[
                CommandHandler("add_contact", self.start_add_contact),
                CommandHandler("contact", self.start_add_contact)
            ],
            states={
                WAITING_NAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_name)
                ],
                WAITING_VALUE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_value)
                ],
                WAITING_NATIONALITY: [
                    CallbackQueryHandler(self.receive_nationality, pattern="^nat_"),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.skip_nationality)
                ],
                WAITING_DATE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_date)
                ],
                WAITING_CONTACT_TYPE: [
                    CallbackQueryHandler(self.receive_contact_type, pattern="^type_")
                ],
                WAITING_FOLLOWUP: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_followup)
                ],
                WAITING_WARM_WORD: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_warm_word)
                ],
                WAITING_INDUSTRY: [
                    CallbackQueryHandler(self.receive_industry, pattern="^ind_"),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.skip_industry)
                ]
            },
            fallbacks=[
                CommandHandler("cancel", self.cancel_add_contact)
            ]
        )
        
        return [
            add_contact_handler,
            CommandHandler("contacts", self.list_contacts),
        ]
    
    async def start_add_contact(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Start adding a new contact"""
        chat_id = update.effective_chat.id
        
        # Initialize temp storage
        self._temp_contact_data[chat_id] = {}
        
        await update.message.reply_text(
            "👤 *Добавление нового контакта*\n\n"
            "Введи *имя* контакта:\n\n"
            "_Отправь /cancel чтобы отменить_",
            parse_mode="Markdown"
        )
        
        return WAITING_NAME
    
    async def receive_name(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Receive contact name"""
        chat_id = update.effective_chat.id
        name = update.message.text.strip()
        
        self._temp_contact_data[chat_id]["name"] = name
        
        await update.message.reply_text(
            f"✅ Имя: *{name}*\n\n"
            "Теперь напиши, *чем этот человек тебя заинтересовал*:",
            parse_mode="Markdown"
        )
        
        return WAITING_VALUE
    
    async def receive_value(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Receive what's valuable about this contact"""
        chat_id = update.effective_chat.id
        value = update.message.text.strip()
        
        self._temp_contact_data[chat_id]["value"] = value
        
        # Show nationality options
        keyboard = [
            [
                InlineKeyboardButton("🇪🇬 Egyptian", callback_data="nat_Egyptian 🇪🇬"),
                InlineKeyboardButton("🇮🇱 Israeli", callback_data="nat_Israeli 🇮🇱")
            ],
            [
                InlineKeyboardButton("🇮🇳 India", callback_data="nat_India 🇮🇳"),
                InlineKeyboardButton("🇷🇺 Russian", callback_data="nat_Russian 🇷🇺")
            ],
            [
                InlineKeyboardButton("🇬🇪 Georgian", callback_data="nat_🇬🇪 Georgian")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "✅ Ценность записана\n\n"
            "Выбери *национальность* (или напиши свою):",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
        return WAITING_NATIONALITY
    
    async def receive_nationality(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Receive nationality selection"""
        query = update.callback_query
        await query.answer()
        
        chat_id = update.effective_chat.id
        nationality = query.data.replace("nat_", "")
        
        self._temp_contact_data[chat_id]["nationality"] = [nationality]
        
        await query.edit_message_text(
            f"✅ Национальность: {nationality}\n\n"
            "Введи *дату встречи* (например, 2026-01-10 или просто напиши 'сегодня'):",
            parse_mode="Markdown"
        )
        
        return WAITING_DATE
    
    async def skip_nationality(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Skip nationality or enter custom"""
        chat_id = update.effective_chat.id
        nationality = update.message.text.strip()
        
        if nationality.lower() in ["skip", "пропустить", "-"]:
            self._temp_contact_data[chat_id]["nationality"] = []
        else:
            self._temp_contact_data[chat_id]["nationality"] = [nationality]
        
        await update.message.reply_text(
            "✅ Национальность записана\n\n"
            "Введи *дату встречи* (например, 2026-01-10 или просто напиши 'сегодня'):",
            parse_mode="Markdown"
        )
        
        return WAITING_DATE
    
    async def receive_date(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Receive meeting date"""
        chat_id = update.effective_chat.id
        date_text = update.message.text.strip()
        
        # Parse date
        if date_text.lower() in ["сегодня", "today"]:
            date = datetime.now().strftime("%Y-%m-%d")
        else:
            # Try to parse as ISO date
            try:
                datetime.strptime(date_text, "%Y-%m-%d")
                date = date_text
            except ValueError:
                await update.message.reply_text(
                    "❌ Неверный формат даты. Используй формат YYYY-MM-DD (например, 2026-01-10) или напиши 'сегодня'"
                )
                return WAITING_DATE
        
        self._temp_contact_data[chat_id]["date"] = date
        
        # Show contact type options
        keyboard = [
            [
                InlineKeyboardButton("🟩 Fresh Contact", callback_data="type_🟩 Fresh Contact")
            ],
            [
                InlineKeyboardButton("🟧 Middle Contact", callback_data="type_🟧Middle Contact")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ Дата: {date}\n\n"
            "Выбери *насколько теплый контакт*:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
        return WAITING_CONTACT_TYPE
    
    async def receive_contact_type(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Receive contact type"""
        query = update.callback_query
        await query.answer()
        
        chat_id = update.effective_chat.id
        contact_type = query.data.replace("type_", "")
        
        self._temp_contact_data[chat_id]["contact_type"] = contact_type
        
        await query.edit_message_text(
            f"✅ Тип контакта: {contact_type}\n\n"
            "Введи *дату последнего фоловапа* (или напиши 'нет' если еще не было):",
            parse_mode="Markdown"
        )
        
        return WAITING_FOLLOWUP
    
    async def receive_followup(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Receive last followup date"""
        chat_id = update.effective_chat.id
        followup_text = update.message.text.strip()
        
        if followup_text.lower() in ["нет", "no", "none", "-"]:
            self._temp_contact_data[chat_id]["followup"] = None
        else:
            # Parse date
            if followup_text.lower() in ["сегодня", "today"]:
                followup = datetime.now().strftime("%Y-%m-%d")
            else:
                try:
                    datetime.strptime(followup_text, "%Y-%m-%d")
                    followup = followup_text
                except ValueError:
                    await update.message.reply_text(
                        "❌ Неверный формат даты. Используй формат YYYY-MM-DD или напиши 'нет'"
                    )
                    return WAITING_FOLLOWUP
            
            self._temp_contact_data[chat_id]["followup"] = followup
        
        await update.message.reply_text(
            "✅ Фоловап записан\n\n"
            "Напиши *теплые слова* — что ты запомнил из диалога:",
            parse_mode="Markdown"
        )
        
        return WAITING_WARM_WORD
    
    async def receive_warm_word(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Receive warm words"""
        chat_id = update.effective_chat.id
        warm_word = update.message.text.strip()
        
        self._temp_contact_data[chat_id]["warm_word"] = warm_word
        
        # Show industry options
        keyboard = [
            [
                InlineKeyboardButton("💰 Crypto", callback_data="ind_crypto"),
                InlineKeyboardButton("🧘 Spirituality", callback_data="ind_spirituality")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "✅ Теплые слова записаны\n\n"
            "Выбери *индустрию* (или напиши свою):",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
        return WAITING_INDUSTRY
    
    async def receive_industry(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Receive industry selection"""
        query = update.callback_query
        await query.answer()
        
        chat_id = update.effective_chat.id
        industry = query.data.replace("ind_", "")
        
        self._temp_contact_data[chat_id]["industry"] = [industry]
        
        # Save to Notion
        await query.edit_message_text(
            f"✅ Индустрия: {industry}\n\n"
            "💾 Сохраняю контакт в Notion..."
        )
        
        success = await self._save_contact_to_notion(chat_id)
        
        if success:
            await query.message.reply_text(
                "✅ *Контакт успешно сохранён в Notion!*\n\n"
                f"Имя: {self._temp_contact_data[chat_id]['name']}",
                parse_mode="Markdown"
            )
        else:
            await query.message.reply_text(
                "❌ Ошибка при сохранении контакта. Попробуй еще раз."
            )
        
        # Clear temp data
        del self._temp_contact_data[chat_id]
        
        return ConversationHandler.END
    
    async def skip_industry(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Skip industry or enter custom"""
        chat_id = update.effective_chat.id
        industry_text = update.message.text.strip()
        
        if industry_text.lower() in ["skip", "пропустить", "-"]:
            self._temp_contact_data[chat_id]["industry"] = []
        else:
            self._temp_contact_data[chat_id]["industry"] = [industry_text]
        
        # Save to Notion
        await update.message.reply_text("💾 Сохраняю контакт в Notion...")
        
        success = await self._save_contact_to_notion(chat_id)
        
        if success:
            await update.message.reply_text(
                "✅ *Контакт успешно сохранён в Notion!*\n\n"
                f"Имя: {self._temp_contact_data[chat_id]['name']}",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "❌ Ошибка при сохранении контакта. Попробуй еще раз."
            )
        
        # Clear temp data
        del self._temp_contact_data[chat_id]
        
        return ConversationHandler.END
    
    async def _save_contact_to_notion(self, chat_id: int) -> bool:
        """Save contact to Notion database"""
        import os
        import httpx
        
        try:
            data = self._temp_contact_data[chat_id]
            token = os.getenv("NOTION_API_TOKEN")
            
            if not token:
                logger.error("NOTION_API_TOKEN not configured")
                return False
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28"
            }
            
            # Prepare properties for Notion API
            properties = {
                "Name": {
                    "title": [{"text": {"content": data["name"]}}]
                },
                "What's value? ": {
                    "rich_text": [{"text": {"content": data.get("value", "")}}]
                },
                "Nationality ": {
                    "multi_select": [{"name": nat} for nat in data.get("nationality", [])]
                },
                "Date": {
                    "date": {"start": data.get("date", "")}
                },
                "type contact": {
                    "select": {"name": data.get("contact_type", "🟩 Fresh Contact")}
                },
                "Warm Word ": {
                    "rich_text": [{"text": {"content": data.get("warm_word", "")}}]
                },
                "indastry": {
                    "multi_select": [{"name": ind} for ind in data.get("industry", [])]
                }
            }
            
            # Add followup if exists
            if data.get("followup"):
                properties["Last follow up"] = {
                    "date": {"start": data["followup"]}
                }
            
            # Create page in Notion
            notion_data = {
                "parent": {"database_id": CONTACTS_DATABASE_ID},
                "properties": properties
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.notion.com/v1/pages",
                    headers=headers,
                    json=notion_data,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    logger.info(f"Contact saved to Notion: {data['name']}")
                    return True
                else:
                    logger.error(f"Failed to save contact to Notion: {response.status_code} - {response.text}")
                    return False
            
        except Exception as e:
            logger.error(f"Error saving contact to Notion: {e}")
            return False
    
    async def cancel_add_contact(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Cancel adding contact"""
        chat_id = update.effective_chat.id
        
        if chat_id in self._temp_contact_data:
            del self._temp_contact_data[chat_id]
        
        await update.message.reply_text(
            "❌ Добавление контакта отменено."
        )
        
        return ConversationHandler.END
    
    async def list_contacts(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """List recent contacts"""
        await update.message.reply_text(
            "📋 *Твои контакты в Notion:*\n\n"
            f"[Открыть базу данных](https://www.notion.so/{CONTACTS_DATABASE_ID})",
            parse_mode="Markdown"
        )


# Module instance
contacts_module = ContactsModule()
