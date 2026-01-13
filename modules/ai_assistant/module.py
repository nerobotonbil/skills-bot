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
            description="AI assistant for natural conversation"
        )
        self._client = None
        self._conversation_history: Dict[int, List[Dict]] = {}
        self._ideas_module = None
        self._gratitude_module = None
        self._contacts_module = None
        
        # System prompt for AI
        self._system_prompt = """You are a helpful personal AI assistant in a Telegram bot for learning and self-development.

Your capabilities:
1. Help user track progress on skills
2. Record gratitude entries in journal
3. Answer questions about learning
4. Motivate and support
5. Analyze health data from WHOOP to give personalized recommendations

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
- CONCISE and DIRECT - like texting, not email
- Short sentences, get to the point fast
- No fluff or unnecessary words
- Use emojis sparingly
- Respond in English

WHEN WHOOP DATA IS AVAILABLE:
- Start with: "Based on your WHOOP data: [key metrics]"
- Show Recovery Score, HRV, Sleep hours if relevant
- Then give specific actionable advice
- Keep it SHORT - 3-4 sentences max

Example good response:
"Based on your WHOOP data: Recovery 45%, HRV 32ms, 6.5h sleep.

7 PM is a good point to pause. Take a 30-45 min break.

After that, light study session - 1 to 1.5 hours on something manageable.

For sleep: wind down around 10:30 PM, asleep by 11:00 PM."

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
    
    def set_gratitude_module(self, gratitude_module):
        """Set gratitude module reference for voice handling"""
        self._gratitude_module = gratitude_module
        logger.info("Gratitude module connected to AI assistant")
    
    def set_contacts_module(self, contacts_module):
        """Set contacts module reference for voice handling"""
        self._contacts_module = contacts_module
        logger.info("Contacts module connected to AI assistant")

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
        FIRST checks for gratitude waiting, then ideas, then processes with AI.
        """
        chat_id = update.effective_chat.id
        
        # FIRST: Check if gratitude module is waiting for input
        if self._gratitude_module and self._gratitude_module.is_waiting_for_gratitude(chat_id):
            logger.info(f"Gratitude waiting detected, forwarding voice text: {transcribed_text[:50]}...")
            await update.message.reply_text(
                f"🎤 **Recognized:**\n_{transcribed_text}_",
                parse_mode="Markdown"
            )
            await self._gratitude_module.handle_voice_gratitude(update, context, transcribed_text)
            return
        
        # SECOND: Check if this is an advice request for last saved contact
        if self._contacts_module and self._contacts_module.is_advice_request(transcribed_text):
            logger.info(f"Advice request detected in voice message: {transcribed_text[:50]}...")
            await update.message.reply_text(
                f"🎤 *Recognized:*\n_{transcribed_text}_\n\n💡 Generating advice...",
                parse_mode="Markdown"
            )
            await self._contacts_module.generate_advice(transcribed_text, chat_id, context)
            return
        
        # THIRD: Check if this is a contact to save
        if self._contacts_module and self._contacts_module.is_contact_related(transcribed_text):
            logger.info(f"Contact detected in voice message: {transcribed_text[:50]}...")
            await update.message.reply_text(
                f"🎤 *Recognized:*\n_{transcribed_text}_\n\n💾 Saving contact...",
                parse_mode="Markdown"
            )
            await self._contacts_module.process_contact_voice(transcribed_text, chat_id, context)
            return
        
        # FOURTH: Check if this is an idea to save
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
        """Gets response from OpenAI API with WHOOP health context"""
        try:
            # Get WHOOP health data if available
            whoop_context = self._get_whoop_context()
            
            # Build system prompt with WHOOP data
            system_prompt = self._system_prompt
            if whoop_context:
                system_prompt += "\n\n" + whoop_context
            
            messages = [
                {"role": "system", "content": system_prompt}
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
    
    def _get_whoop_context(self) -> str:
        """Get WHOOP health data as context for AI"""
        try:
            from modules.whoop_integration import get_whoop_client
            
            client = get_whoop_client()
            if not client:
                logger.info("WHOOP client not available (no token)")
                return ""
            
            logger.info("Fetching WHOOP health data...")
            health_data = client.get_comprehensive_health_data()
            logger.info(f"WHOOP data received: available={health_data.get('available')}, keys={list(health_data.keys())}")
            
            if not health_data.get("available"):
                logger.warning("WHOOP data not available")
                return ""
            
            # Format health data for AI context
            context = "\n=== USER HEALTH DATA (WHOOP) ===\n"
            
            # Recovery data
            if health_data.get("recovery"):
                rec = health_data["recovery"]
                context += f"\nRecovery Score: {rec.get('score')}% (0-100%)\n"
                context += f"Resting Heart Rate: {rec.get('resting_heart_rate')} bpm\n"
                context += f"HRV (Heart Rate Variability): {rec.get('hrv_rmssd'):.1f} ms\n"
                context += f"Blood Oxygen (SpO2): {rec.get('spo2'):.1f}%\n"
                context += f"Skin Temperature: {rec.get('skin_temp_celsius'):.1f}°C\n"
            
            # Sleep data
            if health_data.get("sleep"):
                sleep = health_data["sleep"]
                context += f"\nSleep Duration: {sleep.get('total_sleep_time_hours', 0):.1f} hours\n"
                context += f"Sleep Efficiency: {sleep.get('sleep_efficiency', 0):.1f}%\n"
                context += f"Respiratory Rate: {sleep.get('respiratory_rate', 0):.1f} breaths/min\n"
            
            # Strain data
            if health_data.get("strain"):
                strain = health_data["strain"]
                context += f"\nDay Strain: {strain.get('day_strain', 0):.1f} (0-21 scale)\n"
                context += f"Calories Burned: {strain.get('kilojoules', 0) * 0.239:.0f} kcal\n"
                context += f"Average Heart Rate: {strain.get('average_heart_rate')} bpm\n"
            
            context += "\n=== INSTRUCTIONS ===\n"
            context += "Use this health data to answer questions about:\n"
            context += "- Sleep quality and recommendations\n"
            context += "- Recovery and readiness for activity\n"
            context += "- When to sleep, work out, or rest\n"
            context += "- Why user feels tired or energized\n"
            context += "- Optimal times for learning/practice based on recovery\n"
            context += "\nInterpretation guidelines:\n"
            context += "- Recovery 67-100%: Excellent, ready for intense activity\n"
            context += "- Recovery 34-66%: Moderate, light activity recommended\n"
            context += "- Recovery 0-33%: Low, rest and recovery needed\n"
            context += "- HRV >50ms: Good, <30ms: Stressed/fatigued\n"
            context += "- Sleep efficiency >85%: Good, <75%: Poor\n"
            
            return context
        
        except Exception as e:
            logger.warning(f"Could not get WHOOP context: {e}")
            return ""
    
    def clear_history(self, user_id: int) -> None:
        """Clears conversation history for user"""
        if user_id in self._conversation_history:
            self._conversation_history[user_id] = []


# Module instance
ai_assistant_module = AIAssistantModule()
