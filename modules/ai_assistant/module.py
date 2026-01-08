"""
Модуль AI-ассистента на базе OpenAI GPT
Обрабатывает текстовые и голосовые сообщения, помогает управлять ботом
"""
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from telegram import Update
from telegram.ext import MessageHandler, ContextTypes, BaseHandler, filters

from modules.base import BaseModule
from config.settings import OPENAI_API_KEY, TIMEZONE

logger = logging.getLogger(__name__)


class AIAssistantModule(BaseModule):
    """
    AI-ассистент для управления ботом через естественный язык.
    Понимает голосовые и текстовые сообщения.
    """
    
    def __init__(self):
        super().__init__(
            name="ai_assistant",
            description="AI-ассистент для управления ботом через естественный язык"
        )
        self._client = None
        self._conversation_history: Dict[int, List[Dict]] = {}
        
        # Системный промпт для AI
        self._system_prompt = """Ты - персональный AI-ассистент в Telegram-боте для обучения и саморазвития.

Твои возможности:
1. Помогать пользователю отслеживать прогресс по навыкам
2. Записывать благодарности в дневник
3. Отвечать на вопросы об обучении
4. Мотивировать и поддерживать

Контекст бота:
- Пользователь изучает 50 навыков, отслеживает прогресс в Notion
- Типы контента: лекции, практика, видео, фильмы, VC лекции
- Есть утренние (9:00) и вечерние (21:00) напоминания
- Часовой пояс: Тбилиси (GMT+4)

Команды бота (можешь подсказывать):
- /today - цель на сегодня
- /progress - прогресс по навыкам
- /gratitude - записать благодарность
- /sync - синхронизация с Notion

Стиль общения:
- Дружелюбный, но не навязчивый
- Краткий и по делу
- Используй эмодзи умеренно
- Отвечай на русском языке

Если пользователь говорит что-то связанное с благодарностью - предложи записать через /gratitude.
Если спрашивает о прогрессе - предложи /progress.
Если хочет что-то отметить как выполненное - объясни как это сделать в Notion или через бота."""

    def get_handlers(self) -> List[BaseHandler]:
        """Возвращает обработчики для текстовых сообщений"""
        return [
            # Обрабатываем текстовые сообщения, которые не являются командами
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self.handle_text_message
            ),
        ]
    
    async def startup(self) -> None:
        """Инициализация при запуске"""
        if OPENAI_API_KEY:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=OPENAI_API_KEY)
                logger.info("AI Assistant initialized with OpenAI")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
        else:
            logger.warning("OPENAI_API_KEY not set, AI Assistant disabled")
    
    async def handle_text_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Обрабатывает текстовое сообщение через AI"""
        if not self._client:
            await update.message.reply_text(
                "❌ AI-ассистент не настроен. Проверьте OPENAI_API_KEY."
            )
            return
        
        user_id = update.effective_user.id
        user_message = update.message.text
        
        # Получаем или создаём историю разговора
        if user_id not in self._conversation_history:
            self._conversation_history[user_id] = []
        
        history = self._conversation_history[user_id]
        
        # Добавляем сообщение пользователя
        history.append({"role": "user", "content": user_message})
        
        # Ограничиваем историю последними 10 сообщениями
        if len(history) > 20:
            history = history[-20:]
            self._conversation_history[user_id] = history
        
        try:
            # Отправляем "печатает..."
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action="typing"
            )
            
            # Получаем ответ от AI
            response = await self._get_ai_response(history)
            
            if response:
                # Добавляем ответ в историю
                history.append({"role": "assistant", "content": response})
                
                # Отправляем ответ
                await update.message.reply_text(response)
            else:
                await update.message.reply_text(
                    "🤔 Не удалось получить ответ. Попробуй ещё раз."
                )
                
        except Exception as e:
            logger.error(f"Error in AI response: {e}")
            await update.message.reply_text(
                f"❌ Ошибка AI: {str(e)}"
            )
    
    async def process_voice_text(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        transcribed_text: str
    ) -> None:
        """
        Обрабатывает транскрибированный текст из голосового сообщения.
        Вызывается из voice модуля.
        """
        if not self._client:
            await update.message.reply_text(
                f"📝 Распознанный текст:\n\n{transcribed_text}\n\n"
                "❌ AI-ассистент не настроен для обработки."
            )
            return
        
        user_id = update.effective_user.id
        
        # Получаем или создаём историю разговора
        if user_id not in self._conversation_history:
            self._conversation_history[user_id] = []
        
        history = self._conversation_history[user_id]
        
        # Добавляем контекст что это голосовое сообщение
        voice_context = f"[Голосовое сообщение]: {transcribed_text}"
        history.append({"role": "user", "content": voice_context})
        
        # Ограничиваем историю
        if len(history) > 20:
            history = history[-20:]
            self._conversation_history[user_id] = history
        
        try:
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action="typing"
            )
            
            response = await self._get_ai_response(history)
            
            if response:
                history.append({"role": "assistant", "content": response})
                
                # Показываем распознанный текст и ответ AI
                await update.message.reply_text(
                    f"🎤 *Распознано:*\n_{transcribed_text}_\n\n"
                    f"🤖 *Ответ:*\n{response}",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    f"📝 Распознанный текст:\n\n{transcribed_text}"
                )
                
        except Exception as e:
            logger.error(f"Error processing voice with AI: {e}")
            await update.message.reply_text(
                f"📝 Распознанный текст:\n\n{transcribed_text}\n\n"
                f"❌ Ошибка AI: {str(e)}"
            )
    
    async def _get_ai_response(self, history: List[Dict]) -> Optional[str]:
        """Получает ответ от OpenAI API"""
        try:
            messages = [
                {"role": "system", "content": self._system_prompt}
            ] + history
            
            response = self._client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                max_tokens=500,
                temperature=0.7
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return None
    
    def clear_history(self, user_id: int) -> None:
        """Очищает историю разговора для пользователя"""
        if user_id in self._conversation_history:
            self._conversation_history[user_id] = []


# Экземпляр модуля
ai_assistant_module = AIAssistantModule()
