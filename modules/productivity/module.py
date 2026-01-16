"""
Productivity Module - Simplified Version (Streak functionality removed)

Features:
1. Interleaving System for Skill Practice
2. Smart Scheduler with Deep Practice Blocks

Based on research from:
- Bjork & Bjork (desirable difficulties, interleaving)
- Cal Newport (deep work)
"""
import logging
import json
import os
import random
from typing import List, Dict, Optional, Tuple
from datetime import date, datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    BaseHandler
)

from modules.base import BaseModule
from modules.notion.module import notion_module
from config.settings import MAX_VALUES, CONTENT_EMOJI, CONTENT_NAMES_EN, SKILL_CATEGORIES, CATEGORY_EMOJI

# Русские названия типов контента
CONTENT_NAMES_RU = {
    "Lectures": "лекция",
    "Practice hours": "практика (1 час)",
    "Videos": "видео",
    "Films ": "фильм",
    "VC Lectures": "VC лекция"
}

logger = logging.getLogger(__name__)

# File for storing productivity data
PRODUCTIVITY_FILE = "/tmp/productivity_data.json"


class ProductivityModule(BaseModule):
    """
    Productivity module with two core features:
    
    1. INTERLEAVING (Deep Practice)
       - Mixes practice from different skill categories
       - Prevents blocked practice
       - Strengthens neural connections
    
    2. SMART SCHEDULER (Deep Practice Blocks)
       - Creates structured practice sessions
       - Combines multiple skills in one block
       - Uses spaced repetition principles
    """
    
    def __init__(self):
        super().__init__(
            name="productivity",
            description="Evidence-based productivity enhancements"
        )
        self.data = self._load_data()
    
    def _load_data(self) -> Dict:
        """Loads productivity data from file"""
        try:
            if os.path.exists(PRODUCTIVITY_FILE):
                with open(PRODUCTIVITY_FILE, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading productivity data: {e}")
        
        return {
            "last_interleaved_skills": [],  # Last skills used in interleaving
            "deep_practice_sessions": [],  # History of deep practice blocks
            "daily_snapshots": {}  # Daily snapshots of skill values
        }
    
    def _save_data(self):
        """Saves productivity data to file"""
        try:
            with open(PRODUCTIVITY_FILE, 'w') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving productivity data: {e}")
    
    def get_handlers(self) -> List[BaseHandler]:
        """Returns command handlers for this module"""
        handlers = [
            CommandHandler("interleave", self.interleave_command),
            CommandHandler("deep", self.deep_practice_command),
            CallbackQueryHandler(self.handle_practice_complete, pattern="^practice_done_"),
        ]
        return handlers
    
    # ==================== INTERLEAVING SYSTEM ====================
    
    def generate_interleaved_practice(self, skills: List[Dict], num_skills: int = 3) -> List[Dict]:
        """
        Generates an interleaved practice session mixing different skill categories.
        
        Instead of practicing one skill repeatedly (blocked practice),
        this mixes skills from different categories to strengthen neural connections.
        
        Args:
            skills: List of all skills from Notion
            num_skills: Number of different skills to include
        
        Returns:
            List of skill recommendations with practice suggestions
        """
        if not skills:
            return []
        
        # Group skills by category
        skills_by_category = {}
        for skill in skills:
            for category, skill_names in SKILL_CATEGORIES.items():
                if skill["name"] in skill_names:
                    if category not in skills_by_category:
                        skills_by_category[category] = []
                    skills_by_category[category].append(skill)
                    break
        
        # Filter to incomplete skills only
        incomplete_by_category = {}
        for category, cat_skills in skills_by_category.items():
            incomplete = [s for s in cat_skills if self._calculate_overall_progress(s) < 100]
            if incomplete:
                incomplete_by_category[category] = incomplete
        
        if not incomplete_by_category:
            return []
        
        # Select skills from different categories
        selected = []
        categories = list(incomplete_by_category.keys())
        random.shuffle(categories)
        
        # Avoid recently used skills
        recent_skills = self.data.get("last_interleaved_skills", [])
        
        for category in categories[:num_skills]:
            cat_skills = incomplete_by_category[category]
            # Prefer skills not used recently
            available = [s for s in cat_skills if s["name"] not in recent_skills]
            if not available:
                available = cat_skills
            
            skill = random.choice(available)
            
            # Find weakest content type for this skill
            content_type, progress = self._find_weakest_content(skill)
            
            selected.append({
                "skill": skill,
                "category": category,
                "content_type": content_type,
                "progress": progress,
                "duration_mins": random.choice([10, 15, 20])  # Varied durations
            })
        
        # Update last used skills
        self.data["last_interleaved_skills"] = [s["skill"]["name"] for s in selected]
        self._save_data()
        
        return selected
    
    def _calculate_overall_progress(self, skill: Dict) -> float:
        """Calculates overall skill progress"""
        total_current = (
            skill.get("lectures", 0) + 
            skill.get("practice_hours", 0) + 
            skill.get("videos", 0) + 
            skill.get("films", 0) + 
            skill.get("vc_lectures", 0)
        )
        total_max = sum(MAX_VALUES.values())
        return (total_current / total_max * 100) if total_max > 0 else 0
    
    def _find_weakest_content(self, skill: Dict) -> Tuple[str, float]:
        """Finds the weakest content type for a skill"""
        progress = {
            "Lectures": skill.get("lectures", 0) / MAX_VALUES["Lectures"] * 100,
            "Practice hours": skill.get("practice_hours", 0) / MAX_VALUES["Practice hours"] * 100,
            "Videos": skill.get("videos", 0) / MAX_VALUES["Videos"] * 100,
            "Films ": skill.get("films", 0) / MAX_VALUES["Films "] * 100,
            "VC Lectures": skill.get("vc_lectures", 0) / MAX_VALUES["VC Lectures"] * 100,
        }
        
        incomplete = {k: v for k, v in progress.items() if v < 100}
        if not incomplete:
            return "Practice hours", 100.0
        
        weakest = min(incomplete.items(), key=lambda x: x[1])
        return weakest
    
    async def interleave_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /interleave command - generates interleaved practice"""
        try:
            skills = await notion_module.refresh_skills_cache()
            interleaved = self.generate_interleaved_practice(skills, num_skills=3)
            
            if not interleaved:
                await update.message.reply_text(
                    "✅ Все навыки завершены! Поздравляю!",
                    parse_mode='Markdown'
                )
                return
            
            message = (
                "🔀 **Чередующаяся практика (Interleaving)**\n\n"
                "_Смешивание разных навыков укрепляет нейронные связи "
                "и улучшает долгосрочное запоминание._\n\n"
                "**Сегодняшний микс:**\n\n"
            )
            
            total_time = 0
            for i, item in enumerate(interleaved, 1):
                emoji = CATEGORY_EMOJI.get(item["category"], "📚")
                content_emoji = CONTENT_EMOJI.get(item["content_type"], "📖")
                
                content_name = CONTENT_NAMES_RU.get(item['content_type'], item['content_type'])
                message += (
                    f"**{i}. {item['skill']['name']}** {emoji}\n"
                    f"   {content_emoji} {content_name} — {item['duration_mins']} мин\n"
                    f"   Прогресс: {item['progress']:.0f}%\n\n"
                )
                total_time += item['duration_mins']
            
            message += f"\n⏱ **Общее время:** {total_time} минут\n\n"
            message += "_Переключайся между навыками каждые 10-20 минут для лучшего усвоения!_"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in interleave command: {e}")
            await update.message.reply_text(
                "❌ Ошибка при генерации практики. Попробуй позже.",
                parse_mode='Markdown'
            )
    
    # ==================== DEEP PRACTICE SCHEDULER ====================
    
    def generate_deep_practice_block(self, skills: List[Dict], duration_mins: int = 90) -> Dict:
        """
        Generates a deep practice block combining multiple skills.
        
        Based on Cal Newport's "Deep Work" principles:
        - Focused, uninterrupted practice
        - Multiple skills in one session
        - Clear structure and goals
        
        Args:
            skills: List of all skills from Notion
            duration_mins: Total duration for the practice block (default 90 mins)
        
        Returns:
            Dict with practice block structure
        """
        if not skills:
            return {}
        
        # Get interleaved skills
        interleaved = self.generate_interleaved_practice(skills, num_skills=3)
        
        if not interleaved:
            return {}
        
        # Distribute time across skills
        time_per_skill = duration_mins // len(interleaved)
        
        # Build practice block
        block = {
            "duration_mins": duration_mins,
            "skills": [],
            "start_time": None,  # To be set by user
            "completed": False
        }
        
        for item in interleaved:
            block["skills"].append({
                "name": item["skill"]["name"],
                "category": item["category"],
                "content_type": item["content_type"],
                "duration_mins": time_per_skill,
                "progress_before": item["progress"]
            })
        
        return block
    
    async def deep_practice_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /deep command - generates deep practice block"""
        try:
            skills = await notion_module.refresh_skills_cache()
            
            # Get duration from args or use default
            duration = 90
            if context.args and context.args[0].isdigit():
                duration = int(context.args[0])
                duration = max(30, min(180, duration))  # Limit between 30-180 mins
            
            block = self.generate_deep_practice_block(skills, duration_mins=duration)
            
            if not block:
                await update.message.reply_text(
                    "✅ Все навыки завершены! Поздравляю!",
                    parse_mode='Markdown'
                )
                return
            
            message = (
                f"🎯 **Блок глубокой практики ({duration} минут)**\n\n"
                "_Сфокусированная практика без отвлечений для максимального прогресса._\n\n"
                "**План сессии:**\n\n"
            )
            
            for i, skill_block in enumerate(block["skills"], 1):
                emoji = CATEGORY_EMOJI.get(skill_block["category"], "📚")
                content_emoji = CONTENT_EMOJI.get(skill_block["content_type"], "📖")
                content_name = CONTENT_NAMES_RU.get(skill_block['content_type'], skill_block['content_type'])
                
                message += (
                    f"**{i}. {skill_block['name']}** {emoji}\n"
                    f"   {content_emoji} {content_name}\n"
                    f"   ⏱ {skill_block['duration_mins']} минут\n"
                    f"   📊 Текущий прогресс: {skill_block['progress_before']:.0f}%\n\n"
                )
            
            message += (
                "\n💡 **Советы для глубокой практики:**\n"
                "• Отключи уведомления\n"
                "• Найди тихое место\n"
                "• Делай короткие перерывы между навыками\n"
                "• Фокусируйся на качестве, а не количестве\n\n"
                "_Начинай, когда будешь готов!_"
            )
            
            # Save block to history
            block["created_at"] = datetime.now().isoformat()
            self.data["deep_practice_sessions"].append(block)
            self._save_data()
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in deep practice command: {e}")
            await update.message.reply_text(
                "❌ Ошибка при создании блока практики. Попробуй позже.",
                parse_mode='Markdown'
            )
    
    async def handle_practice_complete(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handler for practice completion callback"""
        await query.answer()
        
        skill_name = query.data.replace("practice_done_", "")
        
        message = f"✅ Отлично! Практика **{skill_name}** завершена.\n\nПродолжай в том же духе!"
        
        await query.edit_message_text(
            message,
            parse_mode='Markdown'
        )


# Create module instance
productivity_module = ProductivityModule()
