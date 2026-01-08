"""
AI Assistant module based on OpenAI GPT
Processes text and voice messages, helps manage the bot
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
    AI assistant for managing the bot through natural language.
    Understands voice and text messages.
    Can save ideas to Notion.
    """
    
    def __init__(self):
        super().__init__(
            name="ai_assistant",
            description="AI assistant for managing the bot through natural language"
        )
        self._client = None
        self._conversation_history: Dict[int, List[Dict]] = {}
        self._ideas_module = None
        
        # System prompt for AI
        self._system_prompt = """You are a personal AI assistant in a Telegram bot for learning and self-development.

Your capabilities:
1. Help user track progress on skills
2. Record gratitude entries in journal
3. Answer questions about learning
4. Motivate and support
5. SAVE IDEAS to Notion - this is a very important feature!

Bot context:
- User is learning 50 skills, tracking progress in Notion
- Content types: lectures, practice, videos, films, VC lectures
- There are morning (9:00 AM) and evening (9:00 PM) reminders
- Timezone: Tbilisi (GMT+4)

IMPORTANT - Saving ideas:
When user asks to save an idea, note, thought, or says something like:
- "save idea..."
- "save note..."
- "remember this..."
- "idea:..."
- "note:..."
- "want to write down..."
- "need to save..."
- "save thought..."

You MUST return JSON in format:
{"action": "save_idea", "idea": "full text of the idea"}

Rules for processing ideas - VERY IMPORTANT:
1. DON'T shorten text too much! Keep ALL information and ALL details
2. Only fix grammar and remove filler words (like, um, you know)
3. If message contains multiple ideas - save ALL ideas
4. Structure text for readability, but DON'T DELETE content
5. Idea should be complete and understandable when read later

Example:
User: "save idea, I was thinking it would be cool to make an app that helps people find interesting places in the city like google maps but only for local secret spots and also you can add reviews from locals"
Response: {"action": "save_idea", "idea": "App idea: helps people find interesting places in the city, like Google Maps, but only for local secret spots. Additional: add reviews from local residents."}

Example 2 (multiple ideas):
User: "save note - want to improve communication system with people, think about what software to make for this, and also idea about landing penguins on Mars"
Response: {"action": "save_idea", "idea": "1. Improve communication system with people - think about what software can be developed for this. 2. Idea about landing penguins on Mars (think through the concept)."}

Main rule: BETTER TO SAVE MORE INFORMATION than lose important details!

Bot commands (you can suggest):
- /today - today's goal
- /progress - skills progress
- /gratitude - record gratitude
- /sync - sync with Notion

Communication style:
- Friendly but not pushy
- Brief and to the point
- Use emojis moderately
- Respond in English

If user says something related to gratitude - suggest recording via /gratitude.
If asking about progress - suggest /progress.
If wants to save an idea - MUST return JSON with action: save_idea."""

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
    
    async def _process_ai_response(self, response: str, update: Update) -> str:
        """
        Processes AI response and executes actions if needed.
        Returns text to send to user.
        """
        # Check if response contains JSON with action
        try:
            # Try to find JSON in response
            if '{"action"' in response:
                # Extract JSON
                start = response.find('{"action"')
                end = response.find('}', start) + 1
                json_str = response[start:end]
                
                data = json.loads(json_str)
                
                if data.get("action") == "save_idea" and data.get("idea"):
                    idea_text = data["idea"]
                    
                    # Save idea to Notion
                    if self._ideas_module:
                        result = await self._ideas_module.save_idea(
                            idea_text,
                            user_id=update.effective_user.id
                        )
                        
                        if result["success"]:
                            return f"✅ Idea saved to Notion!\n\n📝 {idea_text}"
                        else:
                            return f"❌ Failed to save: {result['message']}\n\nIdea: {idea_text}"
                    else:
                        return f"❌ Ideas module not connected.\n\nIdea: {idea_text}"
        except json.JSONDecodeError:
            pass
        except Exception as e:
            logger.error(f"Error processing AI action: {e}")
        
        # If no action - return response as is
        # Remove JSON from response if present
        if '{"action"' in response:
            response = response[:response.find('{"action"')].strip()
        
        return response if response else "✅ Done!"

    async def handle_text_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handles text message through AI"""
        # Try to initialize if not initialized yet
        if not self._client:
            self._init_client()
        
        if not self._client:
            await update.message.reply_text(
                "❌ AI assistant not configured. Check OPENAI_API_KEY."
            )
            return
        
        user_id = update.effective_user.id
        user_message = update.message.text
        
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
                # Process response (possibly with action)
                final_response = await self._process_ai_response(response, update)
                
                # Add response to history
                history.append({"role": "assistant", "content": final_response})
                
                # Send response
                await update.message.reply_text(final_response)
            else:
                await update.message.reply_text(
                    "🤔 Couldn't get a response. Try again."
                )
                
        except Exception as e:
            logger.error(f"Error in AI response: {e}")
            await update.message.reply_text(
                f"❌ AI Error: {str(e)}"
            )
    
    async def process_voice_text(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        transcribed_text: str
    ) -> None:
        """
        Processes transcribed text from voice message.
        Called from voice module.
        """
        # Try to initialize if not initialized yet
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
        
        # Add context that this is a voice message
        voice_context = f"[Voice message]: {transcribed_text}"
        history.append({"role": "user", "content": voice_context})
        
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
                # Process response (possibly with action)
                final_response = await self._process_ai_response(response, update)
                
                history.append({"role": "assistant", "content": final_response})
                
                # Show recognized text and AI response
                await update.message.reply_text(
                    f"🎤 *Recognized:*\n_{transcribed_text}_\n\n"
                    f"🤖 *Response:*\n{final_response}",
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
        """Clears conversation history for user"""
        if user_id in self._conversation_history:
            self._conversation_history[user_id] = []


# Module instance
ai_assistant_module = AIAssistantModule()
