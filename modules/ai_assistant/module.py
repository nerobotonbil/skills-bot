"""
Модуль AI-ассистента на базе OpenAI GPT
Обрабатывает текстовые и голосовые сообщения, помогает управлять ботом
"""
import logging
import os
import json
from typing import List, Optional, Dict, Any
from datetime import datetime

from telegram import Update
from telegram.ext import MessageHandler, ContextTypes, BaseHandler, filters

from modules.base import BaseModule

logger = logging.getLogger(__name__)


class AIAssistantModule(BaseModule):
    """
    AI-ассистент для управления ботом через естественный язык.
    Понимает голосовые и текстовые сообщения.
    Может записывать идеи в Notion.
    """
    
    def __init__(self):
        super().__init__(
            name="ai_assistant",
            description="AI-ассистент для управления ботом через естественный язык"
        )
        self._client = None
        self._conversation_history: Dict[int, List[Dict]] = {}
        self._ideas_module = None
        
        # Системный промпт для AI
        self._system_prompt = """Ты - персональный AI-ассистент в Telegram-боте для обучения и саморазвития.

Твои возможности:
1. Помогать пользователю отслеживать прогресс по навыкам
2. Записывать благодарности в дневник
3. Отвечать на вопросы об обучении
4. Мотивировать и поддерживать
5. ЗАПИСЫВАТЬ ИДЕИ в Notion - это очень важная функция!

Контекст бота:
- Пользователь изучает 50 навыков, отслеживает прогресс в Notion
- Типы контента: лекции, практика, видео, фильмы, VC лекции
- Есть утренние (9:00) и вечерние (21:00) напоминания
- Часовой пояс: Тбилиси (GMT+4)

ВАЖНО - Запись идей:
Когда пользователь просит записать идею, заметку, мысль, или говорит что-то вроде:
- "запиши идею..."
- "сохрани заметку..."
- "запомни это..."
- "идея:..."
- "заметка:..."
- "хочу записать..."
- "надо записать..."
- "сохрани мысль..."

Ты должен ОБЯЗАТЕЛЬНО вернуть JSON в формате:
{"action": "save_idea", "idea": "полный текст идеи"}

Правила обработки идей - ОЧЕНЬ ВАЖНО:
1. НЕ СОКРАЩАЙ текст сильно! Сохраняй ВСЮ информацию и ВСЕ детали
2. Только исправь грамматику и убери слова-паразиты (типа, ну, короче, вот)
3. Если в сообщении несколько идей - сохрани ВСЕ идеи
4. Структурируй текст для читаемости, но НЕ УДАЛЯЙ содержание
5. Идея должна быть полной и понятной при прочтении позже

Пример:
Пользователь: "запиши идею, я тут подумал что было бы круто сделать приложение которое помогает людям находить интересные места в городе типа как гугл карты но только для локальных секретных мест и ещё можно добавить отзывы от местных"
Ответ: {"action": "save_idea", "idea": "Идея приложения: помогает людям находить интересные места в городе, как Google Maps, но только для локальных секретных мест. Дополнительно: добавить отзывы от местных жителей."}

Пример 2 (несколько идей):
Пользователь: "запиши заметку - хочу улучшить систему общения с людьми, подумать какой софт для этого сделать, и ещё идея про высадку пингвинов на Марс"
Ответ: {"action": "save_idea", "idea": "1. Улучшить систему общения с людьми - продумать какой софт можно для этого разработать. 2. Идея про высадку пингвинов на Марс (обдумать концепцию)."}

Главное правило: ЛУЧШЕ СОХРАНИТЬ БОЛЬШЕ ИНФОРМАЦИИ, чем потерять важные детали!

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
Если хочет записать идею - ОБЯЗАТЕЛЬНО верни JSON с action: save_idea."""

        # Инициализируем клиент сразу
        self._init_client()

    def _init_client(self):
        """Инициализация OpenAI клиента"""
        api_key = os.getenv("OPENAI_API_KEY", "")
        if api_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=api_key)
                logger.info("AI Assistant initialized with OpenAI")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
                self._client = None
        else:
            logger.warning("OPENAI_API_KEY not set, AI Assistant disabled")
            self._client = None

    def set_ideas_module(self, ideas_module):
        """Устанавливает модуль идей для записи в Notion"""
        self._ideas_module = ideas_module
        logger.info("Ideas module connected to AI Assistant")

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
        """Инициализация при запуске - повторная попытка если не удалось раньше"""
        if not self._client:
            self._init_client()
    
    async def _process_ai_response(self, response: str, update: Update) -> str:
        """
        Обрабатывает ответ AI и выполняет действия если нужно.
        Возвращает текст для отправки пользователю.
        """
        # Проверяем, содержит ли ответ JSON с действием
        try:
            # Пробуем найти JSON в ответе
            if '{"action"' in response:
                # Извлекаем JSON
                start = response.find('{"action"')
                end = response.find('}', start) + 1
                json_str = response[start:end]
                
                data = json.loads(json_str)
                
                if data.get("action") == "save_idea" and data.get("idea"):
                    idea_text = data["idea"]
                    
                    # Сохраняем идею в Notion
                    if self._ideas_module:
                        result = await self._ideas_module.save_idea(
                            idea_text,
                            user_id=update.effective_user.id
                        )
                        
                        if result["success"]:
                            return f"✅ Идея сохранена в Notion!\n\n📝 {idea_text}"
                        else:
                            return f"❌ Не удалось сохранить: {result['message']}\n\nИдея: {idea_text}"
                    else:
                        return f"❌ Модуль идей не подключен.\n\nИдея: {idea_text}"
        except json.JSONDecodeError:
            pass
        except Exception as e:
            logger.error(f"Error processing AI action: {e}")
        
        # Если нет действия - возвращаем ответ как есть
        # Убираем JSON из ответа если он там есть
        if '{"action"' in response:
            response = response[:response.find('{"action"')].strip()
        
        return response if response else "✅ Готово!"

    async def handle_text_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Обрабатывает текстовое сообщение через AI"""
        # Пробуем инициализировать если ещё не инициализирован
        if not self._client:
            self._init_client()
        
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
                # Обрабатываем ответ (возможно с действием)
                final_response = await self._process_ai_response(response, update)
                
                # Добавляем ответ в историю
                history.append({"role": "assistant", "content": final_response})
                
                # Отправляем ответ
                await update.message.reply_text(final_response)
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
        # Пробуем инициализировать если ещё не инициализирован
        if not self._client:
            self._init_client()
        
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
                # Обрабатываем ответ (возможно с действием)
                final_response = await self._process_ai_response(response, update)
                
                history.append({"role": "assistant", "content": final_response})
                
                # Показываем распознанный текст и ответ AI
                await update.message.reply_text(
                    f"🎤 *Распознано:*\n_{transcribed_text}_\n\n"
                    f"🤖 *Ответ:*\n{final_response}",
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
