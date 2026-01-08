"""
Learning planning module with smart recommendations
50/50 Logic: half recommendations for lagging content, half for sequential progression
"""
import logging
import json
import os
import random
from typing import List, Dict, Optional, Tuple
from datetime import date, datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    BaseHandler
)

from modules.base import BaseModule
from modules.notion.module import notion_module
from config.settings import MAX_VALUES, CONTENT_EMOJI, CONTENT_NAMES_EN

logger = logging.getLogger(__name__)

# File for storing task history
HISTORY_FILE = "/tmp/task_history.json"


class LearningModule(BaseModule):
    """
    Learning planning module with smart recommendations.
    
    50/50 Logic:
    - 50% recommendations: what's lagging the most
    - 50% recommendations: sequential progression (variety)
    
    History:
    - Remembers last 7 days of completed tasks
    - Doesn't repeat the same tasks consecutively
    """
    
    def __init__(self):
        super().__init__(
            name="learning",
            description="Smart learning recommendations based on progress analysis"
        )
        self.history = self._load_history()
    
    def _load_history(self) -> Dict:
        """Loads task history from file"""
        try:
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading history: {e}")
        return {"tasks": [], "last_recommendation": None}
    
    def _save_history(self):
        """Saves task history to file"""
        try:
            # Keep only last 7 days
            cutoff = datetime.now().timestamp() - (7 * 24 * 60 * 60)
            self.history["tasks"] = [
                t for t in self.history["tasks"] 
                if t.get("timestamp", 0) > cutoff
            ]
            with open(HISTORY_FILE, 'w') as f:
                json.dump(self.history, f)
        except Exception as e:
            logger.error(f"Error saving history: {e}")
    
    def _add_to_history(self, skill_name: str, content_type: str):
        """Adds task to history"""
        self.history["tasks"].append({
            "skill": skill_name,
            "content_type": content_type,
            "timestamp": datetime.now().timestamp(),
            "date": date.today().isoformat()
        })
        self.history["last_recommendation"] = {
            "skill": skill_name,
            "content_type": content_type
        }
        self._save_history()
    
    def _was_recommended_recently(self, skill_name: str, content_type: str) -> bool:
        """Checks if this task was recommended recently (last 2 days)"""
        cutoff = datetime.now().timestamp() - (2 * 24 * 60 * 60)
        for task in self.history["tasks"]:
            if (task.get("skill") == skill_name and 
                task.get("content_type") == content_type and
                task.get("timestamp", 0) > cutoff):
                return True
        return False
    
    def get_handlers(self) -> List[BaseHandler]:
        """Returns command handlers"""
        return [
            CommandHandler("today", self.today_command),
            CommandHandler("progress", self.progress_command),
            CommandHandler("skills", self.skills_command),
            CommandHandler("recommend", self.recommend_command),
            CallbackQueryHandler(self.handle_skill_selection, pattern="^skill_"),
        ]
    
    def _calculate_content_progress(self, skill: Dict) -> Dict[str, float]:
        """
        Calculates progress for each content type in percentage.
        """
        return {
            "Lectures": skill["lectures"] / MAX_VALUES["Lectures"] * 100,
            "Practice hours": skill["practice_hours"] / MAX_VALUES["Practice hours"] * 100,
            "Videos": skill["videos"] / MAX_VALUES["Videos"] * 100,
            "Films ": skill["films"] / MAX_VALUES["Films "] * 100,
            "VC Lectures": skill["vc_lectures"] / MAX_VALUES["VC Lectures"] * 100,
        }
    
    def _calculate_overall_progress(self, skill: Dict) -> float:
        """Calculates overall skill progress in percentage"""
        total_current = (
            skill["lectures"] + 
            skill["practice_hours"] + 
            skill["videos"] + 
            skill["films"] + 
            skill["vc_lectures"]
        )
        total_max = (
            MAX_VALUES["Lectures"] + 
            MAX_VALUES["Practice hours"] + 
            MAX_VALUES["Videos"] + 
            MAX_VALUES["Films "] + 
            MAX_VALUES["VC Lectures"]
        )
        return (total_current / total_max * 100) if total_max > 0 else 0
    
    def _find_weakest_content_type(self, skill: Dict) -> Tuple[str, float]:
        """Finds content type with lowest progress."""
        progress = self._calculate_content_progress(skill)
        incomplete = {k: v for k, v in progress.items() if v < 100}
        
        if not incomplete:
            return None, 100.0
        
        weakest = min(incomplete.items(), key=lambda x: x[1])
        return weakest
    
    def _find_next_sequential_content(self, skill: Dict) -> Optional[Tuple[str, float]]:
        """
        Finds next content type for sequential learning.
        Priority: Lectures -> Videos -> VC Lectures -> Films -> Practice
        """
        progress = self._calculate_content_progress(skill)
        
        # Order for sequential learning
        sequence = ["Lectures", "Videos", "VC Lectures", "Films ", "Practice hours"]
        
        for content_type in sequence:
            if progress.get(content_type, 100) < 100:
                # Check if not recommended recently
                if not self._was_recommended_recently(skill["name"], content_type):
                    return content_type, progress[content_type]
        
        # If all were recommended recently, return first incomplete
        for content_type in sequence:
            if progress.get(content_type, 100) < 100:
                return content_type, progress[content_type]
        
        return None, 100.0
    
    def _generate_recommendation(self, skill: Dict, mode: str = "weakest") -> Optional[Dict]:
        """
        Generates recommendation for a skill.
        
        Args:
            skill: Skill data
            mode: "weakest" - lagging, "sequential" - sequential
        """
        if mode == "sequential":
            content_type, progress = self._find_next_sequential_content(skill)
        else:
            content_type, progress = self._find_weakest_content_type(skill)
        
        if content_type is None:
            return None
        
        field_map = {
            "Lectures": skill["lectures"],
            "Practice hours": skill["practice_hours"],
            "Videos": skill["videos"],
            "Films ": skill["films"],
            "VC Lectures": skill["vc_lectures"],
        }
        
        current = field_map[content_type]
        maximum = MAX_VALUES[content_type]
        emoji = CONTENT_EMOJI[content_type]
        name_en = CONTENT_NAMES_EN[content_type]
        
        return {
            "skill_name": skill["name"],
            "content_type": content_type,
            "content_name_en": name_en,
            "emoji": emoji,
            "current": current,
            "maximum": maximum,
            "progress_pct": progress,
            "mode": mode,
        }
    
    def _generate_smart_task(self, skills: List[Dict]) -> Optional[Dict]:
        """
        Generates smart task with 50/50 logic.
        50% - lagging, 50% - sequential progression.
        """
        if not skills:
            return None
        
        # Determine mode: 50/50
        use_sequential = random.random() < 0.5
        mode = "sequential" if use_sequential else "weakest"
        
        # Collect recommendations for all skills
        recommendations = []
        for skill in skills:
            rec = self._generate_recommendation(skill, mode)
            if rec:
                # Check if not recommended recently
                if not self._was_recommended_recently(rec["skill_name"], rec["content_type"]):
                    recommendations.append(rec)
        
        # If all were recommended recently, try other mode
        if not recommendations:
            alt_mode = "weakest" if use_sequential else "sequential"
            for skill in skills:
                rec = self._generate_recommendation(skill, alt_mode)
                if rec:
                    recommendations.append(rec)
        
        if not recommendations:
            # Return any incomplete task
            for skill in skills:
                rec = self._generate_recommendation(skill, "weakest")
                if rec:
                    return rec
            return None
        
        # Choose random recommendation for variety
        if mode == "sequential":
            # For sequential - random choice from skills
            best_rec = random.choice(recommendations)
        else:
            # For lagging - choose with minimum progress
            best_rec = min(recommendations, key=lambda x: x["progress_pct"])
        
        # Add to history
        self._add_to_history(best_rec["skill_name"], best_rec["content_type"])
        
        return best_rec
    
    def _is_skill_completed(self, skill: Dict) -> bool:
        """Checks if skill is fully completed"""
        return (
            skill["lectures"] >= MAX_VALUES["Lectures"] and
            skill["practice_hours"] >= MAX_VALUES["Practice hours"] and
            skill["videos"] >= MAX_VALUES["Videos"] and
            skill["films"] >= MAX_VALUES["Films "] and
            skill["vc_lectures"] >= MAX_VALUES["VC Lectures"]
        )
    
    def _get_incomplete_skills(self, skills: List[Dict]) -> List[Dict]:
        """Returns only incomplete skills"""
        return [s for s in skills if not self._is_skill_completed(s)]
    
    def _progress_bar(self, current: float, maximum: float, length: int = 10) -> str:
        """Generates beautiful progress bar with emoji"""
        if maximum <= 0:
            return "⬜" * length
        ratio = min(current / maximum, 1.0)
        filled = int(ratio * length)
        # Use emoji that display well in Telegram
        return "🟩" * filled + "⬜" * (length - filled)
    
    def _format_skill_progress(self, skill: Dict) -> str:
        """Formats progress for one skill - beautiful format"""
        lines = []
        lines.append(f"📚 *{skill['name']}*\n")
        
        # Calculate overall progress
        overall_pct = self._calculate_overall_progress(skill)
        lines.append(f"Overall progress: *{overall_pct:.0f}%*\n\n")
        
        # Find lagging content type
        weakest, _ = self._find_weakest_content_type(skill)
        
        # Progress for each content type
        progress_items = [
            ("Lectures", skill["lectures"], "📖", "Lectures"),
            ("Practice hours", skill["practice_hours"], "💪", "Practice"),
            ("Videos", skill["videos"], "🎬", "Videos"),
            ("Films ", skill["films"], "🎥", "Films"),
            ("VC Lectures", skill["vc_lectures"], "🎤", "VC Lectures"),
        ]
        
        for key, current, emoji, label in progress_items:
            maximum = MAX_VALUES[key]
            bar = self._progress_bar(current, maximum, 8)
            
            # Mark lagging content type
            marker = " ⚠️" if key == weakest else ""
            
            if key == "Practice hours":
                value_str = f"{current:.1f}/{maximum}h"
            else:
                value_str = f"{int(current)}/{maximum}"
            
            lines.append(f"{emoji} {label}: {value_str}{marker}\n")
            lines.append(f"    {bar}\n")
        
        return "".join(lines)
    
    async def today_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Command /today - shows today's recommendation"""
        # Auto-sync with Notion
        await notion_module.refresh_skills_cache()
        skills = notion_module.get_skills()
        
        if not skills:
            await update.message.reply_text(
                "📚 You don't have any active skills yet.\n\n"
                "To start:\n"
                "1. Open Notion\n"
                "2. Fill in the first progress bar for a skill\n"
                "3. Use /sync to synchronize"
            )
            return
        
        incomplete = self._get_incomplete_skills(skills)
        
        if not incomplete:
            await update.message.reply_text(
                "🎉 Congratulations! All active skills are fully learned!"
            )
            return
        
        task = self._generate_smart_task(incomplete)
        
        if not task:
            await update.message.reply_text("✅ All done for today!")
            return
        
        # Format message with progress bar
        bar = self._progress_bar(task['current'], task['maximum'], 10)
        
        # Determine recommendation type
        if task.get('mode') == 'sequential':
            reason = "_Next step in learning this skill._"
        else:
            reason = "_This content type is lagging the most._"
        
        text = f"🎯 **Today's Recommendation**\n\n"
        text += f"Skill: **{task['skill_name']}**\n\n"
        text += f"{task['emoji']} {task['content_name_en']}:\n"
        text += f"{bar} {task['current']:.0f}/{task['maximum']}\n\n"
        text += f"{reason}\n\n"
        text += f"After completing, update progress in Notion and tap /sync"
        
        await update.message.reply_text(text, parse_mode='Markdown')
    
    async def recommend_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Command /recommend - same as /today"""
        await self.today_command(update, context)
    
    async def skills_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Command /skills - shows list of skills with buttons"""
        # Auto-sync with Notion
        await notion_module.refresh_skills_cache()
        await self._show_skills_menu(update, context)
    
    async def _show_skills_menu(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        edit_message: bool = False
    ) -> None:
        """Shows menu with skill buttons"""
        skills = notion_module.get_skills()
        
        if not skills:
            text = (
                "📚 You don't have any active skills yet.\n\n"
                "To start:\n"
                "1. Open Notion\n"
                "2. Fill in the first progress bar for a skill\n"
                "3. Use /sync to synchronize"
            )
            if edit_message and update.callback_query:
                await update.callback_query.edit_message_text(text)
            else:
                await update.message.reply_text(text)
            return
        
        # Sort skills by progress (highest to lowest)
        sorted_skills = sorted(
            skills,
            key=lambda s: self._calculate_overall_progress(s),
            reverse=True
        )
        
        # Create buttons for each skill
        keyboard = []
        for skill in sorted_skills:
            progress = self._calculate_overall_progress(skill)
            btn_text = f"📚 {skill['name']} ({progress:.0f}%)"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"skill_{skill['id'][:8]}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = "📊 **Select a skill to view:**"
        
        if edit_message and update.callback_query:
            await update.callback_query.edit_message_text(
                text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
    
    async def handle_skill_selection(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handles skill selection from menu"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == "skill_back":
            await self._show_skills_menu(update, context, edit_message=True)
            return
        
        # Extract skill ID
        skill_id_prefix = data.replace("skill_", "")
        
        skills = notion_module.get_skills()
        skill = None
        for s in skills:
            if s["id"].startswith(skill_id_prefix):
                skill = s
                break
        
        if not skill:
            await query.edit_message_text("❌ Skill not found. Use /sync")
            return
        
        text = self._format_skill_progress(skill)
        
        rec = self._generate_recommendation(skill)
        if rec:
            text += f"\n💡 **Recommendation:** watch {rec['content_name_en']}"
        
        keyboard = [[InlineKeyboardButton("⬅️ Back to skills", callback_data="skill_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def progress_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Command /progress - shows progress for all skills"""
        # Auto-sync with Notion
        await notion_module.refresh_skills_cache()
        skills = notion_module.get_skills()
        
        if not skills:
            await update.message.reply_text(
                "📚 You don't have any active skills yet.\n"
                "Start learning a skill in Notion, then use /sync"
            )
            return
        
        # Sort skills by progress (highest to lowest)
        sorted_skills = sorted(
            skills,
            key=lambda s: self._calculate_overall_progress(s),
            reverse=True
        )
        
        text = f"📊 Skill Progress\n"
        text += f"Active: {len(skills)}\n\n"
        
        for skill in sorted_skills:
            text += self._format_skill_progress(skill)
            text += "\n"
        
        await update.message.reply_text(text, parse_mode='Markdown')
    
    def generate_evening_task_message(self, skills: List[Dict]) -> str:
        """Generates evening message with task (8:00 PM)"""
        if not skills:
            return (
                "🌆 **Good evening!**\n\n"
                "You don't have any active skills yet.\n"
                "Start learning something new in Notion!"
            )
        
        incomplete = self._get_incomplete_skills(skills)
        
        if not incomplete:
            return (
                "🌆 **Good evening!**\n\n"
                "🎉 All active skills are learned!\n"
                "Time to start a new skill."
            )
        
        task = self._generate_smart_task(incomplete)
        
        if not task:
            return "🌆 **Good evening!**\n\n✅ All done for today!"
        
        bar = self._progress_bar(task['current'], task['maximum'], 10)
        
        if task.get('mode') == 'sequential':
            reason = "Next step in learning"
        else:
            reason = "This content type is lagging"
        
        message = f"🌆 **Good evening!**\n\n"
        message += f"🎯 Evening task:\n\n"
        message += f"Skill: **{task['skill_name']}**\n"
        message += f"{task['emoji']} {task['content_name_en']}:\n"
        message += f"{bar} {task['current']:.0f}/{task['maximum']}\n\n"
        message += f"_{reason}_\n\n"
        message += f"After completing, update progress in Notion!"
        
        return message
    
    def generate_morning_message(self) -> str:
        """Generates morning message (9:00 AM)"""
        return (
            "🌅 **Good morning!**\n\n"
            "New day - new opportunities for growth!\n\n"
            "Use /today to get today's recommendation."
        )
    
    def generate_night_message(self, skills: List[Dict]) -> str:
        """Generates night message with summary (9:00 PM)"""
        if not skills:
            return (
                "🌙 **Good night!**\n\n"
                "Tomorrow start learning a new skill in Notion!"
            )
        
        # Calculate overall progress
        total_progress = sum(self._calculate_overall_progress(s) for s in skills) / len(skills)
        
        message = f"🌙 **Good night!**\n\n"
        message += f"📊 Average skill progress: *{total_progress:.0f}%*\n\n"
        
        # Show top 3 skills
        sorted_skills = sorted(
            skills,
            key=lambda s: self._calculate_overall_progress(s),
            reverse=True
        )[:3]
        
        message += "🏆 Top skills:\n"
        for i, skill in enumerate(sorted_skills, 1):
            progress = self._calculate_overall_progress(skill)
            message += f"{i}. {skill['name']} - {progress:.0f}%\n"
        
        message += "\nRest well and recharge! 💪"
        
        return message


# Module instance
learning_module = LearningModule()
