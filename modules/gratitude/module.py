"""
Модуль дневника благодарности
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

# Состояния разговора
WAITING_GRATITUDE = 1
WAITING_VOICE = 2


class GratitudeModule(BaseModule):
    """
    Модуль дневника благодарности.
    Позволяет записывать благодарности утром и вечером,
    поддерживает голосовые сообщения.
    """
    
    def __init__(self):
        super().__init__(
            name="gratitude",
            description="Дневник благодарности с поддержкой голосовых сообщений"
        )
        self._gratitude_db_id: Optional[str] = None
        self._waiting_for_gratitude: Dict[int, str] = {}  # chat_id -> time_of_day
    
    def get_handlers(self) -> List[BaseHandler]:
        """Возвращает обработчики команд"""
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
        """Инициализация при запуске"""
        # Проверяем/создаём базу данных для благодарностей
        await self._ensure_gratitude_database()
        
        # Устанавливаем callback для голосовых сообщений
        voice_module.set_transcription_callback(self.handle_voice_gratitude)
    
    async def _ensure_gratitude_database(self) -> None:
        """Проверяет наличие базы данных благодарностей, создаёт если нужно"""
        # Пока используем простое хранение в памяти/файле
        # В будущем можно создать базу в Notion
        logger.info("Gratitude module initialized")
    
    async def gratitude_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Команда /gratitude - записать благодарность"""
        keyboard = [
            [
                InlineKeyboardButton("🌅 Утренняя", callback_data="gratitude_morning"),
                InlineKeyboardButton("🌙 Вечерняя", callback_data="gratitude_evening"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🙏 **Дневник благодарности**\n\n"
            "Выбери тип записи:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def handle_time_selection(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Обработчик выбора времени суток"""
        query = update.callback_query
        await query.answer()
        
        time_of_day = query.data.replace("gratitude_", "")
        chat_id = update.effective_chat.id
        
        # Запоминаем, что ждём благодарность от этого пользователя
        self._waiting_for_gratitude[chat_id] = time_of_day
        
        if time_of_day == "morning":
            prompt = (
                "🌅 **Утренняя благодарность**\n\n"
                "За что ты благодарен этому утру?\n"
                "Что хорошего ждёт тебя сегодня?\n\n"
                "_Напиши текстом или отправь голосовое сообщение_"
            )
        else:
            prompt = (
                "🌙 **Вечерняя благодарность**\n\n"
                "За что ты благодарен этому дню?\n"
                "Что хорошего произошло сегодня?\n\n"
                "_Напиши текстом или отправь голосовое сообщение_"
            )
        
        await query.edit_message_text(prompt, parse_mode='Markdown')
    
    async def handle_text_gratitude(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Обработчик текстовой благодарности"""
        chat_id = update.effective_chat.id
        
        # Проверяем, ждём ли мы благодарность от этого пользователя
        if chat_id not in self._waiting_for_gratitude:
            return  # Не наше сообщение
        
        time_of_day = self._waiting_for_gratitude.pop(chat_id)
        text = update.message.text
        
        await self._save_gratitude(update, context, text, time_of_day)
    
    async def handle_voice_gratitude(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        text: str
    ) -> None:
        """Обработчик голосовой благодарности (callback от voice модуля)"""
        chat_id = update.effective_chat.id
        
        # Проверяем, ждём ли мы благодарность
        if chat_id not in self._waiting_for_gratitude:
            # Просто показываем распознанный текст
            await update.message.reply_text(
                f"📝 Распознанный текст:\n\n{text}"
            )
            return
        
        time_of_day = self._waiting_for_gratitude.pop(chat_id)
        
        # Сокращаем текст если нужно
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
        """Сохраняет благодарность"""
        today = date.today().isoformat()
        
        # Сохраняем в контекст бота
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
        
        # Пытаемся сохранить в Notion
        saved_to_notion = await self._save_to_notion(entry)
        
        # Формируем ответ
        emoji = "🌅" if time_of_day == "morning" else "🌙"
        response = f"{emoji} **Благодарность записана!**\n\n"
        response += f"_{text}_\n\n"
        
        if original and original != text:
            response += f"📝 Полный текст сохранён\n"
        
        if saved_to_notion:
            response += "✅ Синхронизировано с Notion"
        else:
            response += "💾 Сохранено локально"
        
        await update.message.reply_text(response, parse_mode='Markdown')
    
    async def _save_to_notion(self, entry: Dict) -> bool:
        """Сохраняет запись в Notion"""
        if not self._gratitude_db_id:
            # Пока нет базы данных - сохраняем только локально
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
        """Команда /review - обзор записей благодарности"""
        entries = context.bot_data.get('gratitude_entries', [])
        
        if not entries:
            await update.message.reply_text(
                "📔 Дневник пока пуст.\n"
                "Используй /gratitude чтобы сделать первую запись!"
            )
            return
        
        # Показываем последние 5 записей
        recent = entries[-5:]
        
        message = "📔 **Последние записи благодарности**\n\n"
        
        for entry in reversed(recent):
            emoji = "🌅" if entry["time_of_day"] == "morning" else "🌙"
            message += f"{emoji} **{entry['date']}**\n"
            message += f"_{entry['text'][:100]}{'...' if len(entry['text']) > 100 else ''}_\n\n"
        
        message += f"Всего записей: {len(entries)}"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    def get_morning_prompt(self) -> str:
        """Возвращает утренний промпт для благодарности"""
        return (
            "🌅 **Доброе утро!**\n\n"
            "Начни день с благодарности.\n"
            "За что ты благодарен этому утру?\n\n"
            "_Напиши текстом или отправь голосовое сообщение_"
        )
    
    def get_evening_prompt(self) -> str:
        """Возвращает вечерний промпт для благодарности"""
        return (
            "🌙 **Добрый вечер!**\n\n"
            "Время подвести итоги дня.\n"
            "За что ты благодарен этому дню?\n\n"
            "_Напиши текстом или отправь голосовое сообщение_"
        )
    
    def set_waiting_for_gratitude(self, chat_id: int, time_of_day: str) -> None:
        """Устанавливает ожидание благодарности для чата"""
        self._waiting_for_gratitude[chat_id] = time_of_day


# Экземпляр модуля
gratitude_module = GratitudeModule()
