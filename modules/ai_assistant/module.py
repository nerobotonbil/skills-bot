"""
AI Assistant module based on OpenAI GPT
Processes text and voice messages, helps manage the bot
"""
import logging
import os
import json
import re
from typing import List, Optional, Dict, Any
from datetime import datetime

from telegram import Update
from telegram.ext import MessageHandler, ContextTypes, BaseHandler, filters

from modules.base import BaseModule

logger = logging.getLogger(__name__)

# Keywords that indicate user wants to save an idea
IDEA_KEYWORDS = [
    # English
    "save idea", "save note", "save thought", "write down", "note this",
    "remember this", "keep the idea", "need to save", "put in notes",
    "i have an idea", "idea:", "note:", "write it down", "save this",
    "add to notes", "record this", "jot down",
    # Russian
    "запиши", "сохрани", "идея:", "заметка:", "запомни",
    "записать", "сохранить идею", "добавь в заметки"
]


def detect_idea_intent(text: str) -> bool:
    """
    Detects if user wants to save an idea.
    Returns True if idea keywords found.
    """
    text_lower = text.lower()
    for keyword in IDEA_KEYWORDS:
        if keyword in text_lower:
            return True
    return False


def extract_idea_text(text: str) -> str:
    """
    Extracts the actual idea from the message.
    Removes trigger phrases and cleans up.
    """
    # Remove common prefixes
    prefixes_to_remove = [
        r"^\[voice message\]:?\s*",
        r"^save idea[,:]?\s*",
        r"^save note[,:]?\s*",
        r"^write down[,:]?\s*",
        r"^note this[,:]?\s*",
        r"^remember this[,:]?\s*",
        r"^i have an idea[,:]?\s*",
        r"^idea[,:]?\s*",
        r"^note[,:]?\s*",
        r"^запиши[,:]?\s*",
        r"^сохрани[,:]?\s*",
    ]
    
    result = text
    for pattern in prefixes_to_remove:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)
    
    return result.strip()


class AIAssistantModule(BaseModule):
    """
    AI assistant for managing the bot through natural language.
    Understands voice and text messages.
    Can save ideas to Notion.
    
    Uses handler_group=1 to run AFTER all other modules,
    so it only handles messages that weren't processed elsewhere.
    """
    
    # Группа 1 - фоллбэк, выполняется после всех остальных модулей
    handler_group = 1
    
    def __init__(self):
        super().__init__(
            name="ai_assistant",
            description="AI assistant for managing the bot through natural language"
        )
        self._client = None
        self._conversation_history: Dict[int, List[Dict]] = {}
        self._ideas_module = None
        
        # System prompt for AI
        self._system_prompt = """You are a helpful personal AI assistant in a Telegram bot for learning and self-development.

Your capabilities:
1. Help user track progress on skills
2. Record gratitude entries in journal
3. Answer questions about learning
4. Motivate and support
5. Have friendly conversations

Bot context:
- User is learning 50 skills, tracking progress in Notion
- Content types: lectures, practice, videos, films, VC lectures
- There are morning (9:00 AM) and evening (11:00 PM) gratitude reminders
- Timezone: Tbilisi (GMT+4)

Bot commands (you can suggest):
- /today - today's learning tasks
- /progress - skills progress
- /gratitude - record gratitude
- /sync - sync with Notion

Communication style:
- Friendly and supportive
- Brief and to the point
- Use emojis moderately
- Respond in English

NOTE: Ideas are handled automatically by the system. Just be helpful and conversational."""

        # Initialize client immediately
        self._init_client()

    def _init_client(self):
        """Initialize OpenAI client"""
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
        """Sets ideas module for saving to Notion"""
        self._ideas_module = ideas_module
        logger.info("Ideas module connected to AI Assistant")

    def get_handlers(self) -> List[BaseHandler]:
        """Returns handlers for text messages"""
        return [
            # Handle text messages that are not commands
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self.handle_text_message
            ),
        ]
    
    async def startup(self) -> None:
        """Initialization on startup - retry if failed earlier"""
        if not self._client:
            self._init_client()
    
    async def _save_idea_directly(self, idea_text: str, update: Update) -> str:
        """
        Saves idea directly to Notion without AI processing.
        Returns response message.
        """
        if not self._ideas_module:
            return f"❌ Ideas module not connected.\n\nIdea: {idea_text}"
        
        # Clean up the idea text
        clean_idea = extract_idea_text(idea_text)
        
        if not clean_idea:
            return "❌ Could not extract idea from message. Please try again."
        
        result = await self._ideas_module.save_idea(
            clean_idea,
            user_id=update.effective_user.id
        )
        
        if result["success"]:
            return f"✅ Idea saved to Notion!\n\n📝 {clean_idea}"
        else:
            return f"❌ Failed to save: {result['message']}\n\nIdea: {clean_idea}"

    async def handle_text_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handles text message - checks for ideas first, then AI"""
        user_message = update.message.text
        
        # FIRST: Check if this is an idea to save
        if detect_idea_intent(user_message):
            logger.info(f"Idea detected in text message: {user_message[:50]}...")
            response = await self._save_idea_directly(user_message, update)
            await update.message.reply_text(response)
            return
        
        # Otherwise, process with AI
        if not self._client:
            self._init_client()
        
        if not self._client:
            await update.message.reply_text(
                "❌ AI assistant not configured. Check OPENAI_API_KEY."
            )
            return
        
        user_id = update.effective_user.id
        
        # Get or create conversation history
        if user_id not in self._conversation_history:
            self._conversation_history[user_id] = []
        
        history = self._conversation_history[user_id]
        
        # Add user message
        history.append({"role": "user", "content": user_message})
        
        # Limit history to last 10 messages
        if len(history) > 20:
            history = history[-20:]
            self._conversation_history[user_id] = history
        
        try:
            # Send "typing..."
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action="typing"
            )
            
            # Get AI response
            response = await self._get_ai_response(history)
            
            if response:
                # Add response to history
                history.append({"role": "assistant", "content": response})
                
                # Send response
                await update.message.reply_text(response)
            else:
                await update.message.reply_text(
                    "🤔 Couldn't get a response. Try again."
                )
                
        except Exception as e:
            logger.error(f"Error in AI response: {e}")
            await update.message.reply_text(
                f"❌ AI Error: {str(e)}"
            )
    
    async def handle_forwarded_voice(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        transcribed_text: str
    ) -> None:
        """
        Обрабатывает голосовое сообщение, переданное из другого модуля.
        Используется когда gratitude модуль определил, что это не благодарность.
        """
        await self.process_voice_text(update, context, transcribed_text)

    async def process_voice_text(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        transcribed_text: str
    ) -> None:
        """
        Processes transcribed text from voice message.
        Called from voice module.
        FIRST checks for ideas, then processes with AI.
        """
        # FIRST: Check if this is an idea to save
        if detect_idea_intent(transcribed_text):
            logger.info(f"Idea detected in voice message: {transcribed_text[:50]}...")
            response = await self._save_idea_directly(transcribed_text, update)
            await update.message.reply_text(
                f"🎤 *Recognized:*\n_{transcribed_text}_\n\n{response}",
                parse_mode="Markdown"
            )
            return
        
        # Otherwise, process with AI
        if not self._client:
            self._init_client()
        
        if not self._client:
            await update.message.reply_text(
                f"📝 Recognized text:\n\n{transcribed_text}\n\n"
                "❌ AI assistant not configured for processing."
            )
            return
        
        user_id = update.effective_user.id
        
        # Get or create conversation history
        if user_id not in self._conversation_history:
            self._conversation_history[user_id] = []
        
        history = self._conversation_history[user_id]
        
        # Add message to history (without [Voice message] prefix to avoid confusion)
        history.append({"role": "user", "content": transcribed_text})
        
        # Limit history
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
                
                # Show recognized text and AI response
                await update.message.reply_text(
                    f"🎤 *Recognized:*\n_{transcribed_text}_\n\n"
                    f"🤖 *Response:*\n{response}",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    f"📝 Recognized text:\n\n{transcribed_text}"
                )
                
        except Exception as e:
            logger.error(f"Error processing voice with AI: {e}")
            await update.message.reply_text(
                f"📝 Recognized text:\n\n{transcribed_text}\n\n"
                f"❌ AI Error: {str(e)}"
            )
    
    async def _get_ai_response(self, history: List[Dict]) -> Optional[str]:
        """Gets response from OpenAI API"""
        try:
            messages = [
                {"role": "system", "content": self._system_prompt}
            ] + history
            
            response = self._client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=messages,
                max_tokens=500,
                temperature=0.7
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return None
    
    def clear_history(self, user_id: int) -> None:
        """Clears conversation history for user"""
        if user_id in self._conversation_history:
            self._conversation_history[user_id] = []


# Module instance
ai_assistant_module = AIAssistantModule()
