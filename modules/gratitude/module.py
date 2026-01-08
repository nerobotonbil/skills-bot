"""
Gratitude journal module with Notion integration and AI-powered weekly insights
"""
import logging
import os
import httpx
import json
from typing import List, Dict, Optional, Tuple
from datetime import datetime, date, timedelta
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
from openai import OpenAI

from modules.base import BaseModule
from config.settings import (
    NOTION_GRATITUDE_DATABASE_ID, 
    SKILL_CATEGORIES,
    CATEGORY_EMOJI
)

logger = logging.getLogger(__name__)

# Conversation states
WAITING_GRATITUDE = 1
WAITING_VOICE = 2

# All 50 skills with descriptions for AI matching
SKILL_DESCRIPTIONS = {
    "Active Listening": "Understanding others, empathy, paying attention in conversations, meetings",
    "Writing Clarity": "Clear writing, documentation, emails, reports",
    "Storytelling": "Presenting ideas, pitching, engaging audience",
    "Question Formulation": "Asking right questions, interviews, discovery",
    "Body Language Reading": "Understanding non-verbal cues, reading people",
    "Deception Detection": "Spotting lies, verifying information",
    "Negotiation": "Deals, agreements, getting better terms",
    "Public Speaking": "Presentations, speeches, addressing groups",
    "Persuasion": "Convincing others, influence, sales",
    "Conflict Resolution": "Handling disagreements, mediation, team conflicts",
    "Metacognition": "Self-awareness, thinking about thinking, learning how to learn",
    "Mental Simulation der": "Scenario planning, predicting outcomes",
    "Research Skills": "Finding information, analysis, due diligence",
    "Curiosity Cultivation": "Staying curious, exploring new areas",
    "Observation": "Noticing details, awareness, attention",
    "Visualization": "Mental imagery, planning, goal setting",
    "Reading Comprehension": "Understanding complex texts, learning from books",
    "Numerical Literacy": "Numbers, statistics, data interpretation",
    "Financial Literacy": "Money management, investments, budgeting",
    "Digital Literacy": "Technology, tools, digital workflows",
    "Critical Thinking": "Evaluating arguments, logic, reasoning",
    "Problem Solving": "Finding solutions, troubleshooting, fixing issues",
    "Adaptability": "Handling change, flexibility, pivoting",
    "Behavioral Change": "Building habits, changing behaviors",
    "Intuition Development": "Gut feelings, pattern recognition from experience",
    "Stress Management": "Handling pressure, staying calm, burnout prevention",
    "Emotional Regulation": "Managing emotions, staying composed",
    "Resilience": "Bouncing back, handling setbacks, persistence",
    "Time Management": "Productivity, prioritization, scheduling",
    "Decision Making": "Making choices, evaluating options",
    "Risk Assessment": "Evaluating risks, uncertainty, probability",
    "Leadership": "Leading teams, inspiring others, taking charge",
    "Team Building": "Creating effective teams, collaboration",
    "Delegation": "Assigning tasks, trusting others, letting go",
    "Motivation": "Inspiring self and others, maintaining drive",
    "Coaching": "Developing others, mentoring, teaching",
    "Feedback": "Giving and receiving feedback, improvement",
    "Strategic Thinking": "Long-term planning, big picture, strategy",
    "Vision Setting": "Creating vision, goals, direction",
    "Creativity": "Generating ideas, innovation, thinking differently",
    "Innovation": "Implementing new ideas, disruption",
    "Design Thinking": "User-centered problem solving, prototyping",
    "Brainstorming": "Idea generation, group creativity",
    "Lateral Thinking": "Unconventional approaches, thinking outside the box",
    "Pattern Recognition": "Seeing patterns, connecting dots"
}


class GratitudeModule(BaseModule):
    """
    Gratitude journal module with Notion integration and AI-powered insights.
    """
    
    def __init__(self):
        super().__init__(
            name="gratitude",
            description="Gratitude journal with AI insights"
        )
        self._gratitude_db_id = NOTION_GRATITUDE_DATABASE_ID
        self._waiting_for_gratitude: Dict[int, str] = {}
        self._openai_client = None
        logger.info(f"Gratitude module initialized with DB: {self._gratitude_db_id}")
    
    def _get_openai_client(self):
        """Lazy initialization of OpenAI client"""
        if self._openai_client is None:
            self._openai_client = OpenAI()
        return self._openai_client
    
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
        
        self._waiting_for_gratitude[chat_id] = time_of_day
        
        if time_of_day == "morning":
            prompt = (
                "🌅 **Morning Gratitude**\n\n"
                "What are you grateful for this morning?\n\n"
                "_Type your message or send a voice note_"
            )
        else:
            prompt = (
                "🌙 **Evening Gratitude**\n\n"
                "What are you grateful for today?\n\n"
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
        
        if chat_id not in self._waiting_for_gratitude:
            return
        
        time_of_day = self._waiting_for_gratitude.pop(chat_id)
        text = update.message.text
        
        await self._save_gratitude(update, context, text, time_of_day)
    
    async def handle_voice_gratitude(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        text: str
    ) -> None:
        """Handler for voice gratitude"""
        chat_id = update.effective_chat.id
        
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
        
        saved_to_notion = await self._save_to_notion(entry)
        
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
        
        time_label = "Morning" if entry["time_of_day"] == "morning" else "Evening"
        
        data = {
            "parent": {"database_id": self._gratitude_db_id},
            "properties": {
                "Gratitude": {
                    "title": [{"text": {"content": entry["text"][:2000]}}]
                },
                "Date": {
                    "date": {"start": entry["date"]}
                },
                "Select": {
                    "select": {"name": time_label}
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
        """Command /review - AI-powered weekly gratitude insights"""
        await update.message.reply_text("🔄 Analyzing your gratitude entries...")
        
        # Get entries from last 7 days
        entries = await self._get_week_entries()
        
        if not entries or len(entries) < 2:
            await update.message.reply_text(
                "📊 **Weekly Insights**\n\n"
                "Not enough entries for analysis yet.\n"
                "Keep writing gratitude daily, and I'll show you patterns!\n\n"
                f"Current entries this week: {len(entries) if entries else 0}\n"
                "Minimum needed: 2",
                parse_mode='Markdown'
            )
            return
        
        # Get AI analysis
        analysis = await self._analyze_patterns(entries)
        
        # Get skill progress for recommendations
        skills_progress = await self._get_skills_progress()
        
        # Format and send response
        message = await self._format_weekly_review(entries, analysis, skills_progress)
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def _get_week_entries(self) -> List[Dict]:
        """Gets entries from last 7 days from Notion"""
        token = os.getenv("NOTION_API_TOKEN")
        
        if not token or not self._gratitude_db_id:
            return []
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        week_ago = (date.today() - timedelta(days=7)).isoformat()
        
        data = {
            "filter": {
                "property": "Date",
                "date": {
                    "on_or_after": week_ago
                }
            },
            "sorts": [{"property": "Date", "direction": "descending"}],
            "page_size": 50
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
                        
                        title_arr = props.get("Gratitude", {}).get("title", [])
                        text = title_arr[0].get("plain_text", "") if title_arr else ""
                        
                        date_obj = props.get("Date", {}).get("date", {})
                        date_str = date_obj.get("start", "") if date_obj else ""
                        
                        select_obj = props.get("Select", {}).get("select", {})
                        time_str = select_obj.get("name", "") if select_obj else ""
                        
                        if text:  # Only add non-empty entries
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
    
    async def _analyze_patterns(self, entries: List[Dict]) -> Dict:
        """Uses AI to analyze gratitude patterns and detect challenges"""
        try:
            client = self._get_openai_client()
            
            # Combine all entries into text
            entries_text = "\n".join([
                f"- {e['date']} ({e['time']}): {e['text']}" 
                for e in entries
            ])
            
            # Create skill list for AI
            skills_list = "\n".join([
                f"- {skill}: {desc}" 
                for skill, desc in SKILL_DESCRIPTIONS.items()
            ])
            
            prompt = f"""Analyze these gratitude journal entries and identify patterns.

ENTRIES:
{entries_text}

AVAILABLE SKILLS TO RECOMMEND:
{skills_list}

Respond in JSON format:
{{
    "themes": ["theme1", "theme2", "theme3"],  // Top 3 recurring themes (work, family, health, etc.)
    "challenges": ["challenge1", "challenge2"],  // Challenges or frustrations mentioned (if any)
    "positive_patterns": "Brief description of what makes the person happy",
    "recommended_skills": [
        {{
            "skill": "Skill Name",
            "reason": "Why this skill would help based on the entries"
        }}
    ],
    "insight": "One personalized insight or observation (2-3 sentences)"
}}

Focus on actionable insights. If challenges are mentioned, recommend skills that address them.
If no challenges, recommend skills that enhance what's already working."""

            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": "You are an insightful life coach analyzing gratitude journals."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=800
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Parse JSON from response
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0]
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0]
            
            return json.loads(result_text)
            
        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
            return {
                "themes": ["gratitude", "daily life"],
                "challenges": [],
                "positive_patterns": "Regular gratitude practice",
                "recommended_skills": [],
                "insight": "Keep up the great work with your gratitude practice!"
            }
    
    async def _get_skills_progress(self) -> Dict[str, float]:
        """Gets current skill progress from Notion"""
        from config.settings import NOTION_SKILLS_DATABASE_ID, MAX_VALUES
        
        token = os.getenv("NOTION_API_TOKEN")
        if not token:
            return {}
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.notion.com/v1/databases/{NOTION_SKILLS_DATABASE_ID}/query",
                    headers=headers,
                    json={
                        "filter": {
                            "property": "Status",
                            "select": {"equals": "Изучаю"}
                        }
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    results = response.json().get("results", [])
                    progress = {}
                    
                    for page in results:
                        props = page.get("properties", {})
                        name_arr = props.get("Skill", {}).get("title", [])
                        name = name_arr[0].get("plain_text", "") if name_arr else ""
                        
                        if name:
                            total = 0
                            for key, max_val in MAX_VALUES.items():
                                val = props.get(key, {}).get("number", 0) or 0
                                total += (val / max_val) * 100
                            progress[name] = total / len(MAX_VALUES)
                    
                    return progress
                    
        except Exception as e:
            logger.error(f"Failed to get skills progress: {e}")
        
        return {}
    
    async def _format_weekly_review(
        self, 
        entries: List[Dict], 
        analysis: Dict,
        skills_progress: Dict[str, float]
    ) -> str:
        """Formats the weekly review message"""
        today = date.today()
        week_ago = today - timedelta(days=7)
        
        message = f"📊 **Weekly Gratitude Insights**\n"
        message += f"_{week_ago.strftime('%b %d')} - {today.strftime('%b %d')}_\n\n"
        
        # Entry stats
        morning_count = len([e for e in entries if e.get('time') == 'Morning'])
        evening_count = len([e for e in entries if e.get('time') == 'Evening'])
        message += f"📝 Entries: {len(entries)} ({morning_count} morning, {evening_count} evening)\n\n"
        
        # Themes
        themes = analysis.get("themes", [])
        if themes:
            message += "🔥 **Top Themes:**\n"
            for theme in themes[:3]:
                message += f"• {theme}\n"
            message += "\n"
        
        # Positive patterns
        positive = analysis.get("positive_patterns", "")
        if positive:
            message += f"✨ **What makes you happy:**\n_{positive}_\n\n"
        
        # Challenges and skill recommendations
        challenges = analysis.get("challenges", [])
        recommended = analysis.get("recommended_skills", [])
        
        if challenges:
            message += "⚡ **Challenges detected:**\n"
            for ch in challenges[:2]:
                message += f"• {ch}\n"
            message += "\n"
        
        if recommended:
            message += "💡 **Skill Recommendations:**\n"
            for rec in recommended[:2]:
                skill_name = rec.get("skill", "")
                reason = rec.get("reason", "")
                
                # Check if already learning
                progress = skills_progress.get(skill_name, 0)
                if progress > 0:
                    message += f"📚 **{skill_name}** ({progress:.0f}%)\n"
                    message += f"_You're already learning this! Keep going._\n\n"
                else:
                    message += f"📚 **{skill_name}** (not started)\n"
                    message += f"_{reason}_\n\n"
        
        # AI insight
        insight = analysis.get("insight", "")
        if insight:
            message += f"🎯 **Insight:**\n_{insight}_\n\n"
        
        # Streak encouragement
        if len(entries) >= 14:
            message += "🏆 Amazing! You wrote gratitude every day this week!\n"
        elif len(entries) >= 7:
            message += "👏 Great consistency! Keep it up!\n"
        
        return message
    
    async def send_weekly_review(self, bot, chat_id: int) -> None:
        """Sends weekly review (called by scheduler on Fridays)"""
        entries = await self._get_week_entries()
        
        if not entries or len(entries) < 2:
            await bot.send_message(
                chat_id=chat_id,
                text="📊 **Friday Weekly Review**\n\n"
                     "Not enough gratitude entries this week for insights.\n"
                     "Try to write at least 2 entries next week!\n\n"
                     "Use /gratitude to start now 🙏",
                parse_mode='Markdown'
            )
            return
        
        analysis = await self._analyze_patterns(entries)
        skills_progress = await self._get_skills_progress()
        message = await self._format_weekly_review(entries, analysis, skills_progress)
        
        await bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode='Markdown'
        )
    
    def get_morning_prompt(self) -> str:
        """Returns morning prompt for gratitude"""
        return (
            "🌅 **Good morning!**\n\n"
            "What are you grateful for this morning?\n\n"
            "_Just reply to this message_"
        )
    
    def get_evening_prompt(self) -> str:
        """Returns evening prompt for gratitude"""
        return (
            "🌙 **Good evening!**\n\n"
            "What are you grateful for today?\n\n"
            "_Just reply to this message_"
        )
    
    def set_waiting_for_gratitude(self, chat_id: int, time_of_day: str) -> None:
        """Sets gratitude waiting state for chat"""
        self._waiting_for_gratitude[chat_id] = time_of_day


# Module instance
gratitude_module = GratitudeModule()
