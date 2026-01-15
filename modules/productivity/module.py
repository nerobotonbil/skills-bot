"""
Productivity Module - Evidence-Based Productivity Enhancements

Features:
1. Streak Tracking with Loss Aversion Notifications
2. Interleaving System for Skill Practice
3. Smart Scheduler with Deep Practice Blocks

Based on research from:
- Duolingo (streak psychology)
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

# File for storing streak and productivity data
PRODUCTIVITY_FILE = "/tmp/productivity_data.json"

# Streak freeze settings
MAX_STREAK_FREEZES = 2
STREAK_FREEZE_RESET_DAY = 1  # Monday (0=Monday in Python weekday)


class ProductivityModule(BaseModule):
    """
    Productivity module with three core features:
    
    1. STREAK SYSTEM (Dopamine Drive)
       - Tracks daily practice streaks
       - Loss aversion notifications
       - Streak freezes for flexibility
       - Milestone celebrations
    
    2. INTERLEAVING (Deep Practice)
       - Mixes practice from different skill categories
       - Prevents blocked practice
       - Strengthens neural connections
    
    3. SMART SCHEDULER (Deep Practice Blocks)
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
            "streak": {
                "current": 0,
                "longest": 0,
                "last_practice_date": None,
                "freezes_available": MAX_STREAK_FREEZES,
                "freezes_used_this_week": 0,
                "freeze_reset_date": None
            },
            "practice_history": [],  # List of {date, skills_practiced, duration_mins}
            "milestones_achieved": [],  # List of milestone days achieved
            "last_interleaved_skills": [],  # Last skills used in interleaving
            "deep_practice_sessions": [],  # History of deep practice blocks
            "daily_snapshots": {}  # Daily snapshots of skill values for progress tracking
        }
    
    def _save_data(self):
        """Saves productivity data to file"""
        try:
            with open(PRODUCTIVITY_FILE, 'w') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving productivity data: {e}")
    
    async def init_streak_with_history(self, days: int = 3) -> Dict[str, any]:
        """
        Initialize streak with N-day history by creating snapshots
        Returns dict with success status and message
        """
        try:
            from config.settings import NOTION_SKILLS_DATABASE_ID
            import httpx
            
            token = os.getenv("NOTION_API_TOKEN")
            if not token:
                return {"success": False, "message": "NOTION_API_TOKEN not configured"}
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28"
            }
            
            # Get current skills from Notion
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.notion.com/v1/databases/{NOTION_SKILLS_DATABASE_ID}/query",
                    headers=headers,
                    json={},
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    return {"success": False, "message": f"Failed to query Notion: {response.status_code}"}
                
                data = response.json()
                pages = data.get("results", [])
                
                # Build current skill values
                current_skills = {}
                for page in pages:
                    props = page.get("properties", {})
                    
                    # Get skill name
                    skill_name_prop = props.get("Skill", {})
                    skill_name = None
                    if skill_name_prop.get("type") == "title":
                        title_list = skill_name_prop.get("title", [])
                        if title_list:
                            skill_name = title_list[0].get("plain_text", "Unknown")
                    
                    if not skill_name:
                        continue
                    
                    # Get current values
                    current_values = {}
                    for content_type in ["Lectures", "Practice hours", "Videos", "Films ", "VC Lectures"]:
                        if content_type in props:
                            value = props[content_type].get("number", 0) or 0
                            current_values[content_type] = value
                    
                    current_skills[skill_name] = current_values
                
                if not current_skills:
                    return {"success": False, "message": "No skills found in Notion"}
                
                # Create snapshots for last N days
                if "daily_snapshots" not in self.data:
                    self.data["daily_snapshots"] = {}
                
                today = date.today()
                
                for days_ago in range(days, 0, -1):
                    snapshot_date = (today - timedelta(days=days_ago)).isoformat()
                    
                    # Create snapshot with values slightly lower than current
                    # to simulate progress over the days
                    snapshot = {}
                    for skill_name, values in current_skills.items():
                        snapshot_values = {}
                        for content_type, current_val in values.items():
                            # Reduce by days_ago to simulate progress
                            snapshot_val = max(0, current_val - days_ago)
                            snapshot_values[content_type] = snapshot_val
                        snapshot[skill_name] = snapshot_values
                    
                    self.data["daily_snapshots"][snapshot_date] = snapshot
                    logger.info(f"Created snapshot for {snapshot_date}")
                
                # Set streak to N days
                self.data["streak"]["current"] = days
                self.data["streak"]["longest"] = max(self.data["streak"].get("longest", 0), days)
                self.data["streak"]["last_practice_date"] = (today - timedelta(days=1)).isoformat()
                
                # Add practice history
                for days_ago in range(days, 0, -1):
                    practice_date = (today - timedelta(days=days_ago)).isoformat()
                    self.data["practice_history"].append({
                        "date": practice_date,
                        "skills_practiced": ["Memory Enhancement", "Research Skills"],
                        "duration_mins": 60
                    })
                
                # Save data
                self._save_data()
                
                return {
                    "success": True,
                    "message": f"Streak initialized with {days}-day history",
                    "current_streak": self.data["streak"]["current"],
                    "longest_streak": self.data["streak"]["longest"],
                    "snapshots_created": len(self.data["daily_snapshots"])
                }
        
        except Exception as e:
            logger.error(f"Error initializing streak: {e}")
            return {"success": False, "message": f"Error: {str(e)}"}
    
    def get_handlers(self) -> List[BaseHandler]:
        """Returns command handlers for this module"""
        handlers = [
            CommandHandler("streak", self.streak_command),
            CommandHandler("freeze", self.freeze_command),
            CommandHandler("init_streak", self.init_streak_command),
            CallbackQueryHandler(self.handle_practice_complete, pattern="^practice_done_"),
            CallbackQueryHandler(self.handle_freeze_confirm, pattern="^freeze_"),
        ]
        return handlers
    
    # ==================== STREAK SYSTEM ====================
    
    async def _check_notion_progress_today(self) -> bool:
        """Check if there's any progress in Notion today (without updating streak)"""
        try:
            from config.settings import NOTION_SKILLS_DATABASE_ID
            import httpx
            
            token = os.getenv("NOTION_API_TOKEN")
            if not token:
                logger.error("NOTION_API_TOKEN not configured")
                return False
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28"
            }
            
            # Query all skills from Notion
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.notion.com/v1/databases/{NOTION_SKILLS_DATABASE_ID}/query",
                    headers=headers,
                    json={},
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to query Notion: {response.status_code}")
                    return False
                
                data = response.json()
                pages = data.get("results", [])
                
                # Check if any skill has progress > 0
                for page in pages:
                    props = page.get("properties", {})
                    
                    # Check all content types for progress
                    for content_type in ["Lectures", "Practice hours", "Videos", "Films ", "VC Lectures"]:
                        if content_type in props:
                            value = props[content_type].get("number", 0)
                            if value and value > 0:
                                return True
                
                return False
                
        except Exception as e:
            logger.error(f"Error checking Notion progress: {e}")
            return False
    
    async def check_notion_progress_and_update_streak(self) -> bool:
        """Check Notion for any progress today and update streak if found"""
        try:
            from config.settings import NOTION_SKILLS_DATABASE_ID
            import httpx
            
            token = os.getenv("NOTION_API_TOKEN")
            if not token:
                logger.error("NOTION_API_TOKEN not configured")
                return False
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28"
            }
            
            # Query all skills from Notion
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.notion.com/v1/databases/{NOTION_SKILLS_DATABASE_ID}/query",
                    headers=headers,
                    json={},
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to query Notion: {response.status_code}")
                    return False
                
                data = response.json()
                pages = data.get("results", [])
                
                # Get yesterday's snapshot
                yesterday = (date.today() - timedelta(days=1)).isoformat()
                yesterday_snapshot = self.data.get("daily_snapshots", {}).get(yesterday, {})
                
                # Build current snapshot and compare with yesterday
                today_snapshot = {}
                has_progress = False
                
                for page in pages:
                    props = page.get("properties", {})
                    
                    # Get skill name
                    skill_name_prop = props.get("Skill", {})
                    skill_name = None
                    if skill_name_prop.get("type") == "title":
                        title_list = skill_name_prop.get("title", [])
                        if title_list:
                            skill_name = title_list[0].get("plain_text", "Unknown")
                    
                    if not skill_name:
                        continue
                    
                    # Get current values for all content types
                    current_values = {}
                    for content_type in ["Lectures", "Practice hours", "Videos", "Films ", "VC Lectures"]:
                        if content_type in props:
                            value = props[content_type].get("number", 0) or 0
                            current_values[content_type] = value
                    
                    today_snapshot[skill_name] = current_values
                    
                    # Compare with yesterday's values
                    if skill_name in yesterday_snapshot:
                        yesterday_values = yesterday_snapshot[skill_name]
                        for content_type, current_val in current_values.items():
                            yesterday_val = yesterday_values.get(content_type, 0)
                            if current_val > yesterday_val:
                                logger.info(f"Progress detected: {skill_name} - {content_type}: {yesterday_val} -> {current_val}")
                                has_progress = True
                                break
                    else:
                        # New skill added today - check if it has any progress
                        if any(v > 0 for v in current_values.values()):
                            logger.info(f"New skill with progress: {skill_name}")
                            has_progress = True
                    
                    if has_progress:
                        break
                
                # Save today's snapshot for tomorrow's comparison
                if "daily_snapshots" not in self.data:
                    self.data["daily_snapshots"] = {}
                
                today = date.today().isoformat()
                self.data["daily_snapshots"][today] = today_snapshot
                
                # Keep only last 7 days of snapshots
                cutoff = (date.today() - timedelta(days=7)).isoformat()
                self.data["daily_snapshots"] = {
                    d: s for d, s in self.data["daily_snapshots"].items()
                    if d >= cutoff
                }
                
                self._save_data()
                
                # If there's progress, update streak
                if has_progress:
                    last_practice = self.data["streak"]["last_practice_date"]
                    
                    # Only update if not already updated today
                    if last_practice != today:
                        self.record_practice(skill_name="Daily Practice", duration_mins=0)
                        logger.info("Streak updated based on Notion progress")
                        return True
                
                return False
                
        except Exception as e:
            logger.error(f"Error checking Notion progress: {e}")
            return False
    
    def get_streak_info(self) -> Dict:
        """Returns current streak information"""
        self._check_streak_status()
        return {
            "current": self.data["streak"]["current"],
            "longest": self.data["streak"]["longest"],
            "freezes_available": self.data["streak"]["freezes_available"],
            "last_practice": self.data["streak"]["last_practice_date"]
        }
    
    def _check_streak_status(self):
        """Checks and updates streak status based on current date"""
        today = date.today().isoformat()
        last_practice = self.data["streak"]["last_practice_date"]
        
        # Reset freezes on Monday
        self._check_freeze_reset()
        
        if not last_practice:
            return
        
        last_date = date.fromisoformat(last_practice)
        days_since = (date.today() - last_date).days
        
        if days_since > 1:
            # Streak broken (missed more than 1 day)
            # Check if we can use a freeze
            if days_since == 2 and self.data["streak"]["freezes_available"] > 0:
                # Auto-use freeze for yesterday
                self.data["streak"]["freezes_available"] -= 1
                self.data["streak"]["freezes_used_this_week"] += 1
                logger.info("Auto-used streak freeze")
            else:
                # Streak is broken
                self.data["streak"]["current"] = 0
                logger.info(f"Streak broken after {days_since} days of inactivity")
        
        self._save_data()
    
    def _check_freeze_reset(self):
        """Resets freeze count on Monday"""
        today = date.today()
        reset_date = self.data["streak"].get("freeze_reset_date")
        
        if reset_date:
            last_reset = date.fromisoformat(reset_date)
            # If it's a new week (Monday or later in a new week)
            if today.weekday() == 0 and (today - last_reset).days >= 7:
                self.data["streak"]["freezes_available"] = MAX_STREAK_FREEZES
                self.data["streak"]["freezes_used_this_week"] = 0
                self.data["streak"]["freeze_reset_date"] = today.isoformat()
                self._save_data()
        else:
            # Initialize reset date
            self.data["streak"]["freeze_reset_date"] = today.isoformat()
            self._save_data()
    
    def record_practice(self, skill_name: str, duration_mins: int = 15) -> Dict:
        """
        Records a practice session and updates streak.
        
        Returns:
            Dict with streak info and any milestones achieved
        """
        today = date.today().isoformat()
        last_practice = self.data["streak"]["last_practice_date"]
        
        result = {
            "streak_extended": False,
            "new_milestone": None,
            "current_streak": 0,
            "message": ""
        }
        
        # Check if already practiced today
        if last_practice == today:
            # Just add to practice history
            self.data["practice_history"].append({
                "date": today,
                "skill": skill_name,
                "duration_mins": duration_mins,
                "timestamp": datetime.now().isoformat()
            })
            self._save_data()
            result["current_streak"] = self.data["streak"]["current"]
            result["message"] = f"✅ Added {duration_mins} mins of {skill_name} practice!"
            return result
        
        # New day - extend streak
        if last_practice:
            last_date = date.fromisoformat(last_practice)
            days_since = (date.today() - last_date).days
            
            if days_since == 1:
                # Consecutive day - extend streak
                self.data["streak"]["current"] += 1
                result["streak_extended"] = True
            elif days_since == 0:
                # Same day (shouldn't happen but handle it)
                pass
            else:
                # Streak was broken, start new
                self.data["streak"]["current"] = 1
                result["streak_extended"] = True
        else:
            # First practice ever
            self.data["streak"]["current"] = 1
            result["streak_extended"] = True
        
        # Update last practice date
        self.data["streak"]["last_practice_date"] = today
        
        # Check for new longest streak
        if self.data["streak"]["current"] > self.data["streak"]["longest"]:
            self.data["streak"]["longest"] = self.data["streak"]["current"]
        
        # Check for milestones
        milestone = self._check_milestone(self.data["streak"]["current"])
        if milestone:
            result["new_milestone"] = milestone
            self.data["milestones_achieved"].append({
                "days": milestone,
                "date": today
            })
        
        # Add to practice history
        self.data["practice_history"].append({
            "date": today,
            "skill": skill_name,
            "duration_mins": duration_mins,
            "timestamp": datetime.now().isoformat()
        })
        
        # Keep only last 30 days of history
        cutoff = (date.today() - timedelta(days=30)).isoformat()
        self.data["practice_history"] = [
            p for p in self.data["practice_history"]
            if p["date"] >= cutoff
        ]
        
        self._save_data()
        
        result["current_streak"] = self.data["streak"]["current"]
        result["message"] = self._generate_streak_message(result)
        
        return result
    
    def _check_milestone(self, streak_days: int) -> Optional[int]:
        """Checks if current streak is a milestone"""
        milestones = [7, 14, 21, 30, 50, 100, 150, 200, 365]
        
        if streak_days in milestones:
            # Check if not already achieved
            achieved = [m["days"] for m in self.data["milestones_achieved"]]
            if streak_days not in achieved:
                return streak_days
        
        return None
    
    def _generate_streak_message(self, result: Dict) -> str:
        """Generates motivating streak message"""
        streak = result["current_streak"]
        
        if result["new_milestone"]:
            # Milestone celebration
            milestone_messages = {
                7: "🎉 **НЕВЕРОЯТНО! 7-ДНЕВНАЯ СЕРИЯ!**\n\nТы в 3.6 раза ближе к мастерству!",
                14: "🔥 **ДВЕ НЕДЕЛИ ПОДРЯД!**\n\nТы строишь настоящие нейронные связи!",
                21: "⭐ **21 ДЕНЬ! ПРИВЫЧКА СФОРМИРОВАНА!**\n\nЭто теперь часть тебя!",
                30: "🏆 **МЕСЯЦ! ЧЕМПИОН!**\n\nТы в топ-5% всех учеников!",
                50: "💎 **50 ДНЕЙ СОВЕРШЕНСТВА!**\n\nТы становишься экспертом!",
                100: "👑 **100 ДНЕЙ! ЛЕГЕНДА!**\n\nТы достиг того, о чём другие только мечтают!",
                150: "🌟 **150 ДНЕЙ! НЕУДЕРЖИМ!**\n\nТы перепрограммируешь свой мозг!",
                200: "🚀 **200 ДНЕЙ! ТРАНСЦЕНДЕНТНОСТЬ!**\n\nТы освоил саму последовательность!",
                365: "🎊 **ГОД! БЕССМЕРТНАЯ СЕРИЯ!**\n\nТы в 0.1% лучших!"
            }
            return milestone_messages.get(result["new_milestone"], f"🎉 Веха {result['new_milestone']} дней!")
        
        if streak <= 3:
            # Ранняя серия - празднуем рост
            return f"🔥 **{streak}-дневная серия!**\n\nТы набираешь обороты! Продолжай!"
        elif streak <= 10:
            return f"🔥 **{streak}-дневная серия!**\n\nТы в ударе! Не ломай цепочку!"
        else:
            return f"🔥 **{streak}-дневная серия!**\n\nНевероятная последовательность! Ты неудержим!"
    
    def generate_loss_aversion_reminder(self) -> Optional[str]:
        """
        Generates a loss aversion notification if streak is at risk.
        Called by the reminder service.
        """
        self._check_streak_status()
        
        streak = self.data["streak"]["current"]
        last_practice = self.data["streak"]["last_practice_date"]
        
        if not last_practice or streak == 0:
            return None
        
        last_date = date.fromisoformat(last_practice)
        today = date.today()
        
        # If practiced today, no reminder needed
        if last_date == today:
            return None
        
        # If yesterday was the last practice, streak is at risk
        if (today - last_date).days == 1:
            freezes = self.data["streak"]["freezes_available"]
            
            if streak >= 30:
                urgency = "🚨"
                message = (
                    f"{urgency} **ВНИМАНИЕ! Твоя {streak}-дневная серия под угрозой!**\n\n"
                    f"Ты так долго строил эту серию — не дай ей исчезнуть!\n\n"
                    f"⏰ Выполни хотя бы одно упражнение сегодня, чтобы сохранить прогресс.\n\n"
                )
            elif streak >= 14:
                urgency = "⚠️"
                message = (
                    f"{urgency} **Твоя {streak}-дневная серия под угрозой!**\n\n"
                    f"Две недели работы могут пропасть!\n\n"
                    f"⏰ Выполни одно упражнение, чтобы сохранить серию.\n\n"
                )
            elif streak >= 7:
                urgency = "⚡"
                message = (
                    f"{urgency} **{streak}-дневная серия ждёт тебя!**\n\n"
                    f"Не ломай цепочку! Ты уже в 3.6 раза ближе к мастерству.\n\n"
                )
            else:
                message = (
                    f"🔥 **Продолжи свою {streak}-дневную серию!**\n\n"
                    f"Каждый день приближает тебя к цели.\n\n"
                )
            
            if freezes > 0:
                message += f"❄️ У тебя есть {freezes} заморозки серии на случай форс-мажора."
            else:
                message += "❄️ Заморозки закончились — только практика спасёт серию!"
            
            return message
        
        return None
    
    async def init_streak_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Initialize streak with 3-day history"""
        await update.message.reply_text("🔄 Инициализирую стрик с 3-дневной историей...")
        
        result = await self.init_streak_with_history(days=3)
        
        if result["success"]:
            await update.message.reply_text(
                f"✅ **Стрик успешно инициализирован!**\n\n"
                f"Текущий стрик: **{result['current_streak']} дня**\n"
                f"Лучший стрик: **{result['longest_streak']} дней**\n"
                f"Снимков создано: **{result['snapshots_created']}**\n\n"
                f"Теперь система будет правильно отслеживать твой ежедневный прогресс.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"❌ Ошибка: {result['message']}",
                parse_mode='Markdown'
            )
    
    async def streak_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /streak command - shows streak info"""
        # Check Notion for today's progress and update streak if needed
        await self.check_notion_progress_and_update_streak()
        
        info = self.get_streak_info()
        
        # Create progress bar
        streak = info["current"]
        next_milestone = self._get_next_milestone(streak)
        progress = (streak / next_milestone * 100) if next_milestone else 100
        bar_filled = int(progress / 10)
        bar_empty = 10 - bar_filled
        progress_bar = "█" * bar_filled + "░" * bar_empty
        
        message = (
            f"🔥 **Твоя серия практики**\n\n"
            f"**Текущая серия:** {streak} дней\n"
            f"**Лучшая серия:** {info['longest']} дней\n\n"
            f"**До следующей вехи ({next_milestone} дней):**\n"
            f"[{progress_bar}] {progress:.0f}%\n\n"
            f"❄️ **Заморозки:** {info['freezes_available']}/{MAX_STREAK_FREEZES}\n\n"
        )
        
        if streak == 0:
            message += "💪 Начни практику сегодня, чтобы запустить серию!"
        elif streak < 7:
            message += f"📈 Ещё {7 - streak} дней до первой вехи!"
        else:
            message += "🌟 Отличная работа! Продолжай в том же духе!"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    def _get_next_milestone(self, current: int) -> int:
        """Returns the next milestone after current streak"""
        milestones = [7, 14, 21, 30, 50, 100, 150, 200, 365]
        for m in milestones:
            if m > current:
                return m
        return 365
    
    async def freeze_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /freeze command - use a streak freeze"""
        info = self.get_streak_info()
        
        if info["freezes_available"] <= 0:
            await update.message.reply_text(
                "❄️ **Заморозки закончились!**\n\n"
                "Новые заморозки появятся в понедельник.\n"
                "А пока — только практика спасёт серию! 💪",
                parse_mode='Markdown'
            )
            return
        
        keyboard = [
            [
                InlineKeyboardButton("❄️ Использовать заморозку", callback_data="freeze_confirm"),
                InlineKeyboardButton("❌ Отмена", callback_data="freeze_cancel")
            ]
        ]
        
        await update.message.reply_text(
            f"❄️ **Использовать заморозку серии?**\n\n"
            f"Это защитит твою {info['current']}-дневную серию на сегодня.\n\n"
            f"Осталось заморозок: {info['freezes_available']}/{MAX_STREAK_FREEZES}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    async def handle_freeze_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles freeze confirmation"""
        query = update.callback_query
        await query.answer()
        
        action = query.data.split("_")[1]
        
        if action == "confirm":
            if self.data["streak"]["freezes_available"] > 0:
                self.data["streak"]["freezes_available"] -= 1
                self.data["streak"]["freezes_used_this_week"] += 1
                self.data["streak"]["last_practice_date"] = date.today().isoformat()
                self._save_data()
                
                await query.edit_message_text(
                    f"❄️ **Заморозка активирована!**\n\n"
                    f"Твоя {self.data['streak']['current']}-дневная серия защищена на сегодня.\n"
                    f"Осталось заморозок: {self.data['streak']['freezes_available']}/{MAX_STREAK_FREEZES}",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text(
                    "❄️ Заморозки закончились!",
                    parse_mode='Markdown'
                )
        else:
            await query.edit_message_text(
                "👍 Отменено. Продолжай практику!",
                parse_mode='Markdown'
            )
    
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
                total_time += item["duration_mins"]
            
            message += f"⏱ **Общее время:** {total_time} минут\n\n"
            message += "_Совет: Делай короткие перерывы между навыками!_"
            
            # Add completion button
            keyboard = [[
                InlineKeyboardButton(
                    "✅ Завершил практику", 
                    callback_data=f"practice_done_{interleaved[0]['skill']['name']}"
                )
            ]]
            
            await update.message.reply_text(
                message, 
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error in interleave command: {e}")
            await update.message.reply_text(
                "❌ Ошибка при генерации практики. Попробуй позже.",
                parse_mode='Markdown'
            )
    
    # ==================== SMART SCHEDULER (DEEP PRACTICE BLOCKS) ====================
    
    def generate_deep_practice_block(self, skills: List[Dict]) -> Dict:
        """
        Generates a structured deep practice block.
        
        Based on:
        - Ultradian rhythms (90-minute focus cycles)
        - Interleaving (mixing skills)
        - Spaced repetition (reviewing older skills)
        
        Returns:
            Dict with practice block structure
        """
        if not skills:
            return {}
        
        # Get incomplete skills
        incomplete = [s for s in skills if self._calculate_overall_progress(s) < 100]
        if not incomplete:
            return {"completed": True}
        
        # Structure: 45-minute block with 3 segments
        # Segment 1: Main focus skill (20 mins)
        # Segment 2: Related skill (15 mins)  
        # Segment 3: Review of older skill (10 mins)
        
        # Find skill with lowest progress for main focus
        main_skill = min(incomplete, key=lambda s: self._calculate_overall_progress(s))
        main_category = self._get_skill_category(main_skill["name"])
        
        # Find related skill from same category
        same_category = [s for s in incomplete 
                        if s["name"] != main_skill["name"] 
                        and self._get_skill_category(s["name"]) == main_category]
        
        related_skill = random.choice(same_category) if same_category else None
        
        # Find review skill from different category (something practiced before)
        other_category = [s for s in incomplete 
                         if self._get_skill_category(s["name"]) != main_category]
        review_skill = random.choice(other_category) if other_category else None
        
        # Build the block
        block = {
            "total_duration": 45,
            "segments": []
        }
        
        # Segment 1: Main focus
        main_content, main_progress = self._find_weakest_content(main_skill)
        block["segments"].append({
            "order": 1,
            "skill": main_skill["name"],
            "category": main_category,
            "content_type": main_content,
            "duration_mins": 20,
            "focus": "deep",
            "instruction": f"Глубокое погружение в {CONTENT_NAMES_RU.get(main_content, main_content)}"
        })
        
        # Segment 2: Related skill
        if related_skill:
            rel_content, rel_progress = self._find_weakest_content(related_skill)
            block["segments"].append({
                "order": 2,
                "skill": related_skill["name"],
                "category": main_category,
                "content_type": rel_content,
                "duration_mins": 15,
                "focus": "practice",
                "instruction": f"Практика: {CONTENT_NAMES_RU.get(rel_content, rel_content)}"
            })
        
        # Segment 3: Review
        if review_skill:
            rev_content, rev_progress = self._find_weakest_content(review_skill)
            rev_category = self._get_skill_category(review_skill["name"])
            block["segments"].append({
                "order": 3,
                "skill": review_skill["name"],
                "category": rev_category,
                "content_type": rev_content,
                "duration_mins": 10,
                "focus": "review",
                "instruction": f"Повторение: {CONTENT_NAMES_RU.get(rev_content, rev_content)}"
            })
        
        # Recalculate total duration
        block["total_duration"] = sum(s["duration_mins"] for s in block["segments"])
        
        return block
    
    def _get_skill_category(self, skill_name: str) -> str:
        """Returns the category for a skill"""
        for category, skills in SKILL_CATEGORIES.items():
            if skill_name in skills:
                return category
        return "Other"
    
    async def deep_block_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /deepblock command - generates a deep practice block"""
        try:
            skills = await notion_module.refresh_skills_cache()
            block = self.generate_deep_practice_block(skills)
            
            if block.get("completed"):
                await update.message.reply_text(
                    "✅ Все навыки завершены! Ты молодец!",
                    parse_mode='Markdown'
                )
                return
            
            if not block.get("segments"):
                await update.message.reply_text(
                    "❌ Не удалось создать блок практики.",
                    parse_mode='Markdown'
                )
                return
            
            message = (
                "🧠 **Блок глубокой практики**\n\n"
                "_Структурированная сессия для максимального усвоения навыков._\n\n"
            )
            
            for segment in block["segments"]:
                emoji = CATEGORY_EMOJI.get(segment["category"], "📚")
                content_emoji = CONTENT_EMOJI.get(segment["content_type"], "📖")
                
                focus_label = {
                    "deep": "🎯 Глубокий фокус",
                    "practice": "💪 Практика",
                    "review": "🔄 Повторение"
                }.get(segment["focus"], "📖")
                
                message += (
                    f"**{segment['order']}. {segment['skill']}** {emoji}\n"
                    f"   {focus_label} — {segment['duration_mins']} мин\n"
                    f"   {content_emoji} {segment['instruction']}\n\n"
                )
            
            message += (
                f"⏱ **Общее время:** {block['total_duration']} минут\n\n"
                "💡 _Совет: Убери все отвлечения. Телефон в режим «Не беспокоить»._\n\n"
                "🍅 _Используй таймер Помодоро для каждого сегмента!_"
            )
            
            # Add completion button
            first_skill = block["segments"][0]["skill"]
            keyboard = [[
                InlineKeyboardButton(
                    "✅ Блок завершён", 
                    callback_data=f"practice_done_{first_skill}"
                )
            ]]
            
            await update.message.reply_text(
                message,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error in deep block command: {e}")
            await update.message.reply_text(
                "❌ Ошибка при создании блока. Попробуй позже.",
                parse_mode='Markdown'
            )
    
    async def handle_practice_complete(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles practice completion callback"""
        query = update.callback_query
        await query.answer()
        
        # Extract skill name from callback data
        skill_name = query.data.replace("practice_done_", "")
        
        # Record practice and update streak
        result = self.record_practice(skill_name, duration_mins=30)
        
        message = (
            f"{result['message']}\n\n"
            f"🔥 Текущая серия: **{result['current_streak']} дней**"
        )
        
        if result.get("new_milestone"):
            message = result["message"]  # Milestone message is already complete
        
        await query.edit_message_text(message, parse_mode='Markdown')


# Global module instance
productivity_module = ProductivityModule()
