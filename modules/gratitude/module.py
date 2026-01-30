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

from modules.base import BaseModule, owner_only
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
        self._ai_assistant = None  # Ссылка на AI-ассистент
        logger.info(f"Gratitude module initialized with DB: {self._gratitude_db_id}")
    
    def set_ai_assistant(self, ai_assistant):
        """Устанавливает ссылку на AI-ассистент для передачи не-благодарностей"""
        self._ai_assistant = ai_assistant
        logger.info("AI assistant connected to Gratitude module")
    
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
            CommandHandler("weekly_gratitude", self.weekly_recap_command),
            CallbackQueryHandler(self.handle_time_selection, pattern="^gratitude_"),
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self.handle_text_gratitude
            ),
        ]
    
    @owner_only
    async def gratitude_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Command /gratitude - write gratitude entry"""
        keyboard = [
            [
                InlineKeyboardButton("🌅 Утро", callback_data="gratitude_morning"),
                InlineKeyboardButton("🌙 Вечер", callback_data="gratitude_evening"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🙏 **Дневник благодарности**\n\n"
            "Выбери тип записи:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    @owner_only
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
                "🌅 **Утренняя благодарность**\n\n"
                "За что ты благодарен этим утром?\n\n"
                "_Напиши сообщение или отправь голосовое_"
            )
        else:
            prompt = (
                "🌙 **Вечерняя благодарность**\n\n"
                "За что ты благодарен сегодня?\n\n"
                "_Напиши сообщение или отправь голосовое_"
            )
        
        await query.edit_message_text(prompt, parse_mode='Markdown')
    
    def _is_gratitude_message(self, text: str) -> bool:
        """
        Проверяет, является ли сообщение благодарностью или это заметка/задача/вопрос.
        Использует простые эвристики для быстрой проверки.
        """
        text_lower = text.lower().strip()
        
        # Ключевые слова заметок/задач (НЕ благодарность)
        task_keywords = [
            # Русские
            "запиши", "записать", "сохрани", "добавь", "напомни",
            "купить", "сделать", "позвонить", "написать", "отправить",
            "заметк", "задач", "туду", "todo", "идея:", "заметка:",
            "нужно ", "надо ", "следует ",
            # Английские
            "save", "note", "remind", "buy", "call", "send", "write down",
            "task", "idea:", "note:", "need to", "have to", "should"
        ]
        
        # Ключевые слова благодарности
        gratitude_keywords = [
            # Русские
            "благодар", "спасибо", "рад", "счастлив", "хорошо",
            "приятно", "ценю", "люблю", "нравится", "вдохновл",
            "поддержк", "помощь", "семь", "друз", "здоровь",
            # Английские
            "grateful", "thankful", "appreciate", "blessed", "happy",
            "glad", "love", "enjoy", "wonderful", "amazing"
        ]
        
        # Проверяем на ключевые слова задач (приоритет)
        for keyword in task_keywords:
            if keyword in text_lower:
                return False
        
        # Проверяем на URL (скорее всего заметка)
        if "http://" in text_lower or "https://" in text_lower or "www." in text_lower:
            return False
        
        # Проверяем на ключевые слова благодарности
        for keyword in gratitude_keywords:
            if keyword in text_lower:
                return True
        
        # Если нет явных признаков, считаем благодарностью
        # (так как пользователь в режиме ожидания благодарности)
        return True

    async def handle_text_gratitude(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handler for text gratitude"""
        chat_id = update.effective_chat.id
        
        if chat_id not in self._waiting_for_gratitude:
            return
        
        text = update.message.text
        
        # Пользователь в режиме ожидания благодарности - сохраняем всё как благодарность
        time_of_day = self._waiting_for_gratitude.pop(chat_id)
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
        
        # Пользователь в режиме ожидания благодарности - сохраняем всё как благодарность
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
        # If it's between 00:00 and 03:00, treat as previous day's evening
        now = datetime.now()
        if 0 <= now.hour < 3:
            entry_date = (date.today() - timedelta(days=1)).isoformat()
            # Force evening for late night entries
            if time_of_day == "morning":
                time_of_day = "evening"
        else:
            entry_date = date.today().isoformat()
        
        entry = {
            "date": entry_date,
            "time_of_day": time_of_day,
            "text": text,
            "original_text": original,
            "timestamp": datetime.now().isoformat()
        }
        
        saved_to_notion = await self._save_to_notion(entry)
        
        emoji = "🌅" if time_of_day == "morning" else "🌙"
        response = f"{emoji} **Благодарность сохранена!**\n\n"
        response += f"_{text}_\n\n"
        
        if saved_to_notion:
            response += "✅ Синхронизировано с Notion"
        else:
            response += "⚠️ Не удалось синхронизировать с Notion"
        
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
    
    @owner_only
    async def weekly_recap_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Command /weekly_gratitude - AI-powered weekly gratitude recap in Russian"""
        await update.message.reply_text("🔄 Анализирую твои записи благодарности за неделю...")
        
        # Get entries from last 7 days (Monday to Sunday)
        entries = await self._get_week_entries()
        
        if not entries:
            await update.message.reply_text(
                "📊 **Недельный рекап**\n\n"
                "Нет записей за последние 7 дней.\n"
                "Начни записывать благодарности, чтобы увидеть анализ!\n\n"
                "Используй /gratitude чтобы начать 🙏",
                parse_mode='Markdown'
            )
            return
        
        # Get weekly metrics from all databases
        metrics = await self._get_weekly_metrics()
        
        # Get AI analysis in Russian
        analysis = await self._analyze_week_patterns_russian(entries)
        
        # Format and send response
        message = await self._format_weekly_recap_russian(entries, analysis, metrics)
        
        await update.message.reply_text(message)
    
    @owner_only
    async def review_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Command /review - AI-powered monthly gratitude insights"""
        await update.message.reply_text("🔄 Анализирую твои записи благодарности за месяц...")
        
        # Get entries from last 30 days
        entries = await self._get_month_entries()
        
        if not entries or len(entries) < 3:
            await update.message.reply_text(
                "📊 **Месячный обзор**\n\n"
                "Недостаточно записей для анализа.\n"
                "Продолжай писать благодарности, и я покажу паттерны!\n\n"
                f"Записей за месяц: {len(entries) if entries else 0}\n"
                "Минимум нужно: 3",
                parse_mode='Markdown'
            )
            return
        
        # Get AI analysis
        analysis = await self._analyze_patterns(entries)
        
        # Get skill progress for recommendations
        skills_progress = await self._get_skills_progress()
        
        # Format and send response
        message = await self._format_monthly_review(entries, analysis, skills_progress)
        
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
    
    async def _analyze_week_patterns_russian(self, entries: List[Dict]) -> Dict:
        """Uses AI to analyze weekly gratitude patterns with life area categorization"""
        try:
            client = self._get_openai_client()
            
            # Combine all entries into text
            entries_text = "\n".join([
                f"- {e['date']} ({e['time']}): {e['text']}" 
                for e in entries
            ])
            
            prompt = f"""Проанализируй эти записи благодарности за неделю и категоризируй их по областям жизни.

ЗАПИСИ:
{entries_text}

Ответь в JSON формате:
{{
    "categories": {{
        "business": {{
            "count": 0,  // Количество записей
            "examples": ["пример1", "пример2"],  // 2-3 ключевых момента БЕЗ ДАТ
            "insight": "Краткий инсайт (1 предложение, максимум 15 слов)"
        }},
        "knowledge": {{
            "count": 0,
            "examples": [],
            "insight": ""
        }},
        "relationships": {{
            "count": 0,
            "examples": [],
            "insight": ""
        }},
        "health": {{
            "count": 0,
            "examples": [],
            "insight": ""
        }},
        "personal": {{
            "count": 0,
            "examples": [],
            "insight": ""
        }}
    }},
    "key_insights": [
        "Инсайт 1 - самое важное открытие (1 предложение)",
        "Инсайт 2 - второе по важности (1 предложение)",
        "Инсайт 3 - третье (1 предложение)"
    ],
    "recommendations": [
        "Краткая рекомендация 1 (максимум 10 слов)",
        "Краткая рекомендация 2 (максимум 10 слов)",
        "Краткая рекомендация 3 (максимум 10 слов)"
    ],
    "strengths": [
        "Сильная сторона 1 - что хорошо получается",
        "Сильная сторона 2"
    ],
    "growth_areas": [
        "Зона роста 1 - что можно улучшить",
        "Зона роста 2"
    ]
}}

КАТЕГОРИИ:
- business: работа, проекты, достижения, встречи, карьера, бизнес
- knowledge: обучение, инсайты, книги, курсы, навыки, развитие
- relationships: семья, друзья, партнёр, общение, люди
- health: спорт, питание, сон, энергия, самочувствие
- personal: хобби, развлечения, отдых, эмоции, личное время

ВАЖНО:
- Примеры БЕЗ ДАТ - только суть события
- Инсайты по категориям - МАКСИМУМ 15 слов, 1 предложение
- Рекомендации - МАКСИМУМ 10 слов каждая
- Сильные стороны - 2 категории где больше всего записей
- Зоны роста - 2 категории где меньше всего записей

Пиши на русском, будь конкретным и лаконичным."""

            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": "Ты мудрый коуч, который анализирует дневники благодарности и даёт глубокие инсайты на русском языке. Ты умеешь видеть паттерны и давать конкретные рекомендации."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1500
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
                "categories": {
                    "business": {"count": 0, "examples": [], "insight": ""},
                    "knowledge": {"count": 0, "examples": [], "insight": ""},
                    "relationships": {"count": 0, "examples": [], "insight": ""},
                    "health": {"count": 0, "examples": [], "insight": ""},
                    "personal": {"count": 0, "examples": [], "insight": ""}
                },
                "key_insights": ["Продолжай записывать благодарности каждый день"],
                "recommendations": ["Продолжай в том же духе!"],
                "strengths": [],
                "growth_areas": []
            }
    
    async def _format_weekly_recap_russian(self, entries: List[Dict], analysis: Dict, metrics: Dict[str, int] = None) -> str:
        """Formats weekly recap message in Russian with categorized structure"""
        from datetime import datetime, date, timedelta
        
        # Calculate date range
        today = date.today()
        week_ago = today - timedelta(days=7)
        
        # Count days with entries
        days_count = {}
        for entry in entries:
            if entry.get('date'):
                day_name = datetime.fromisoformat(entry['date']).strftime('%A')
                days_count[day_name] = days_count.get(day_name, 0) + 1
        
        # Start with header
        message = f"📊 Недельный рекап ({week_ago.strftime('%d.%m')} - {today.strftime('%d.%m')})\n\n"
        
        # Activity metrics
        message += "📈 Активность:\n"
        if metrics:
            activity_items = []
            if metrics.get('gratitudes', 0) > 0:
                activity_items.append(f"Записей: {metrics['gratitudes']}")
            if metrics.get('contacts', 0) > 0:
                activity_items.append(f"Знакомств: {metrics['contacts']}")
            if metrics.get('ideas', 0) > 0:
                activity_items.append(f"Идей: {metrics['ideas']}")
            message += f"  • {' | '.join(activity_items)}\n"
        else:
            message += f"  • Записей: {len(entries)}\n"
        
        message += f"  • Дней с записями: {len(days_count)} из 7\n\n"
        
        # Categories section
        categories = analysis.get('categories', {})
        category_icons = {
            'business': '🏢',
            'knowledge': '💡',
            'relationships': '❤️',
            'health': '💪',
            'personal': '🎯'
        }
        category_names = {
            'business': 'Бизнес',
            'knowledge': 'Знания',
            'relationships': 'Отношения',
            'health': 'Здоровье',
            'personal': 'Личное'
        }
        
        message += "🎯 По областям:\n\n"
        
        for cat_key, cat_data in categories.items():
            if cat_data.get('count', 0) > 0:
                icon = category_icons.get(cat_key, '🔸')
                name = category_names.get(cat_key, cat_key)
                count = cat_data['count']
                
                message += f"{icon} {name} ({count} записей)\n"
                
                # Add examples (max 2)
                examples = cat_data.get('examples', [])
                if examples:
                    for example in examples[:2]:  # Max 2 examples
                        message += f"  • {example}\n"
                
                # Add insight
                insight = cat_data.get('insight', '')
                if insight:
                    message += f"  → {insight}\n"
                
                message += "\n"
        
        # Strengths and growth areas
        strengths = analysis.get('strengths', [])
        growth_areas = analysis.get('growth_areas', [])
        
        if strengths or growth_areas:
            message += "📊 Анализ:\n\n"
            
            if strengths:
                message += "✅ Сильные стороны:\n"
                for strength in strengths[:2]:  # Max 2
                    message += f"  • {strength}\n"
                message += "\n"
            
            if growth_areas:
                message += "⚠️ Зоны роста:\n"
                for area in growth_areas[:2]:  # Max 2
                    message += f"  • {area}\n"
                message += "\n"
        
        # Key insights section
        key_insights = analysis.get('key_insights', [])
        if key_insights:
            message += "💡 Главные инсайты недели:\n"
            for i, insight in enumerate(key_insights[:3], 1):  # Max 3 insights
                message += f"{i}. {insight}\n"
            message += "\n"
        
        # Recommendations section
        recommendations = analysis.get('recommendations', [])
        if recommendations:
            message += "🚀 Рекомендации:\n"
            for rec in recommendations[:3]:  # Max 3 recommendations
                message += f"  • {rec}\n"
            message += "\n"
        
        message += "Используй /gratitude чтобы продолжить 🙏"
        
        return message
    
    async def _get_weekly_metrics(self) -> Dict[str, int]:
        """Fetch weekly metrics from all Notion databases"""
        from datetime import date, timedelta
        
        token = os.getenv("NOTION_API_TOKEN")
        if not token:
            return {}
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        week_ago = (date.today() - timedelta(days=7)).isoformat()
        
        metrics = {
            "contacts": 0,
            "ideas": 0,
            "gratitudes": 0
        }
        
        try:
            async with httpx.AsyncClient() as client:
                # Count contacts (networking)
                contacts_db_id = "28b8db7c936780b9a5c1facea087a15a"
                try:
                    response = await client.post(
                        f"https://api.notion.com/v1/databases/{contacts_db_id}/query",
                        headers=headers,
                        json={
                            "filter": {
                                "property": "Date",
                                "date": {"on_or_after": week_ago}
                            }
                        },
                        timeout=30.0
                    )
                    if response.status_code == 200:
                        metrics["contacts"] = len(response.json().get("results", []))
                except Exception as e:
                    logger.warning(f"Failed to fetch contacts: {e}")
                
                # Count ideas
                ideas_db_id = "2e28db7c936780b28d66e45ab2e6f7e6"
                try:
                    response = await client.post(
                        f"https://api.notion.com/v1/databases/{ideas_db_id}/query",
                        headers=headers,
                        json={
                            "filter": {
                                "property": "Created",
                                "date": {"on_or_after": week_ago}
                            }
                        },
                        timeout=30.0
                    )
                    if response.status_code == 200:
                        metrics["ideas"] = len(response.json().get("results", []))
                except Exception as e:
                    logger.warning(f"Failed to fetch ideas: {e}")
                
                # Gratitudes already counted from entries
                metrics["gratitudes"] = len(await self._get_week_entries())
                
        except Exception as e:
            logger.error(f"Failed to fetch weekly metrics: {e}")
        
        return metrics
    
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
        
        message = f"📊 **Недельный обзор благодарности**\n"
        message += f"_{week_ago.strftime('%d.%m')} - {today.strftime('%d.%m')}_\n\n"
        
        # Entry stats
        morning_count = len([e for e in entries if e.get('time') == 'Morning'])
        evening_count = len([e for e in entries if e.get('time') == 'Evening'])
        message += f"📝 Записей: {len(entries)} ({morning_count} утро, {evening_count} вечер)\n\n"
        
        # Themes
        themes = analysis.get("themes", [])
        if themes:
            message += "🔥 **Главные темы:**\n"
            for theme in themes[:3]:
                message += f"• {theme}\n"
            message += "\n"
        
        # Positive patterns
        positive = analysis.get("positive_patterns", "")
        if positive:
            message += f"✨ **Что делает тебя счастливым:**\n_{positive}_\n\n"
        
        # Challenges and skill recommendations
        challenges = analysis.get("challenges", [])
        recommended = analysis.get("recommended_skills", [])
        
        if challenges:
            message += "⚡ **Обнаруженные вызовы:**\n"
            for ch in challenges[:2]:
                message += f"• {ch}\n"
            message += "\n"
        
        if recommended:
            message += "💡 **Рекомендации по навыкам:**\n"
            for rec in recommended[:2]:
                skill_name = rec.get("skill", "")
                reason = rec.get("reason", "")
                
                # Check if already learning
                progress = skills_progress.get(skill_name, 0)
                if progress > 0:
                    message += f"📚 **{skill_name}** ({progress:.0f}%)\n"
                    message += f"_Ты уже изучаешь это! Продолжай._\n\n"
                else:
                    message += f"📚 **{skill_name}** (не начат)\n"
                    message += f"_{reason}_\n\n"
        
        # AI insight
        insight = analysis.get("insight", "")
        if insight:
            message += f"🎯 **Инсайт:**\n_{insight}_\n\n"
        
        # Streak encouragement
        if len(entries) >= 14:
            message += "🏆 Невероятно! Ты писал благодарность каждый день на этой неделе!\n"
        elif len(entries) >= 7:
            message += "👏 Отличная последовательность! Продолжай!\n"
        
        return message
    
    async def _get_month_entries(self) -> List[Dict]:
        """Gets entries from last 30 days from Notion"""
        token = os.getenv("NOTION_API_TOKEN")
        
        if not token or not self._gratitude_db_id:
            return []
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        month_ago = (date.today() - timedelta(days=30)).isoformat()
        
        data = {
            "filter": {
                "property": "Date",
                "date": {
                    "on_or_after": month_ago
                }
            },
            "sorts": [{"property": "Date", "direction": "descending"}],
            "page_size": 100
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
                        
                        if text:
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
            logger.error(f"Failed to get month entries from Notion: {e}")
            return []
    
    async def _format_monthly_review(
        self, 
        entries: List[Dict], 
        analysis: Dict,
        skills_progress: Dict[str, float]
    ) -> str:
        """Formats the monthly review message"""
        today = date.today()
        month_ago = today - timedelta(days=30)
        
        message = f"📊 **Месячный обзор благодарности**\n"
        message += f"_{month_ago.strftime('%d.%m')} - {today.strftime('%d.%m')}_\n\n"
        
        # Entry stats
        morning_count = len([e for e in entries if e.get('time') == 'Morning'])
        evening_count = len([e for e in entries if e.get('time') == 'Evening'])
        message += f"📝 Записей за месяц: {len(entries)} ({morning_count} утро, {evening_count} вечер)\n\n"
        
        # Themes
        themes = analysis.get("themes", [])
        if themes:
            message += "🔥 **Главные темы месяца:**\n"
            for theme in themes[:5]:
                message += f"• {theme}\n"
            message += "\n"
        
        # Positive patterns
        positive = analysis.get("positive_patterns", "")
        if positive:
            message += f"✨ **Что делает тебя счастливым:**\n_{positive}_\n\n"
        
        # Challenges and skill recommendations
        challenges = analysis.get("challenges", [])
        recommended = analysis.get("recommended_skills", [])
        
        if challenges:
            message += "⚡ **Вызовы месяца:**\n"
            for ch in challenges[:3]:
                message += f"• {ch}\n"
            message += "\n"
        
        if recommended:
            message += "💡 **Рекомендации по навыкам:**\n"
            for rec in recommended[:3]:
                skill_name = rec.get("skill", "")
                reason = rec.get("reason", "")
                
                progress = skills_progress.get(skill_name, 0)
                if progress > 0:
                    message += f"📚 **{skill_name}** ({progress:.0f}%)\n"
                    message += f"_Ты уже изучаешь это! Продолжай._\n\n"
                else:
                    message += f"📚 **{skill_name}** (не начат)\n"
                    message += f"_{reason}_\n\n"
        
        # AI insight
        insight = analysis.get("insight", "")
        if insight:
            message += f"🎯 **Инсайт месяца:**\n_{insight}_\n\n"
        
        # Monthly encouragement
        if len(entries) >= 50:
            message += "🏆 Потрясающе! Более 50 записей за месяц!\n"
        elif len(entries) >= 30:
            message += "👏 Отличная последовательность! Ты писал каждый день!\n"
        elif len(entries) >= 15:
            message += "💪 Хороший прогресс! Попробуй писать чаще.\n"
        
        return message
    
    async def send_monthly_review(self, bot, chat_id: int) -> None:
        """Sends monthly review (called by scheduler on 1st of each month)"""
        entries = await self._get_month_entries()
        
        if not entries or len(entries) < 3:
            await bot.send_message(
                chat_id=chat_id,
                text="📊 **Месячный обзор благодарности**\n\n"
                     "Недостаточно записей благодарности за этот месяц для анализа.\n"
                     "Постарайся написать хотя бы несколько записей в следующем месяце!\n\n"
                     "Используй /gratitude чтобы начать 🙏",
                parse_mode='Markdown'
            )
            return
        
        analysis = await self._analyze_patterns(entries)
        skills_progress = await self._get_skills_progress()
        message = await self._format_monthly_review(entries, analysis, skills_progress)
        
        await bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode='Markdown'
        )
    
    async def send_weekly_review(self, bot, chat_id: int) -> None:
        """Sends weekly review (called by scheduler on Fridays)"""
        entries = await self._get_week_entries()
        
        if not entries or len(entries) < 2:
            await bot.send_message(
                chat_id=chat_id,
                text="📊 **Пятничный недельный обзор**\n\n"
                     "Недостаточно записей благодарности на этой неделе для анализа.\n"
                     "Постарайся написать хотя бы 2 записи на следующей неделе!\n\n"
                     "Используй /gratitude чтобы начать 🙏",
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
    
    def is_waiting_for_gratitude(self, chat_id: int) -> bool:
        """Checks if chat is waiting for gratitude input"""
        return chat_id in self._waiting_for_gratitude


# Module instance
gratitude_module = GratitudeModule()
