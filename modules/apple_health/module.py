"""
Apple Health Integration Module
Receives health data from iOS Shortcuts
"""

import logging
from datetime import datetime
from typing import Dict, Optional
import pytz
from config.settings import TIMEZONE

logger = logging.getLogger(__name__)


class AppleHealthModule:
    """Handles Apple Health data from iOS Shortcuts"""
    
    def __init__(self):
        self._latest_data: Dict = {}
        self._last_update: Optional[datetime] = None
    
    def store_health_data(self, data: Dict) -> str:
        """
        Store health data received from iOS Shortcuts
        
        Args:
            data: Dictionary with health metrics
                - sleep_score: int (0-100)
                - steps: int
                - heart_rate_avg: int (bpm)
                - heart_rate_resting: int (bpm)
                - calories: int
                - active_energy: int
                - exercise_minutes: int
                - date: str (YYYY-MM-DD)
        
        Returns:
            Confirmation message
        """
        try:
            tz = pytz.timezone(TIMEZONE)
            now = datetime.now(tz)
            
            self._latest_data = data
            self._last_update = now
            
            logger.info(f"✅ Apple Health data stored: {data}")
            
            # Format response message
            message_parts = ["📊 Данные Apple Health получены!\n"]
            
            if data.get("sleep_score"):
                score = data["sleep_score"]
                emoji = "🟢" if score >= 70 else "🟡" if score >= 50 else "🔴"
                message_parts.append(f"{emoji} Оценка сна: {score} баллов")
            
            if data.get("steps"):
                message_parts.append(f"🚶 Шаги: {data['steps']:,}")
            
            if data.get("heart_rate_resting"):
                message_parts.append(f"❤️ Пульс покоя: {data['heart_rate_resting']} bpm")
            
            if data.get("calories"):
                message_parts.append(f"🔥 Калории: {data['calories']} ккал")
            
            if data.get("exercise_minutes"):
                message_parts.append(f"💪 Упражнения: {data['exercise_minutes']} мин")
            
            message_parts.append(f"\n⏰ Обновлено: {now.strftime('%H:%M')}")
            
            return "\n".join(message_parts)
            
        except Exception as e:
            logger.error(f"Error storing Apple Health data: {e}", exc_info=True)
            return f"❌ Ошибка сохранения данных: {str(e)}"
    
    def get_latest_data(self) -> Optional[Dict]:
        """Get the latest stored health data"""
        return self._latest_data if self._latest_data else None
    
    def get_health_summary(self) -> str:
        """Get formatted summary of latest health data"""
        if not self._latest_data:
            return "❌ Нет данных Apple Health. Отправь данные через Shortcut!"
        
        data = self._latest_data
        message_parts = ["📊 Твоё здоровье (Apple Health)\n"]
        
        if data.get("sleep_score"):
            score = data["sleep_score"]
            emoji = "🟢" if score >= 70 else "🟡" if score >= 50 else "🔴"
            message_parts.append(f"{emoji} Оценка сна: {score}/100")
        
        if data.get("steps"):
            steps = data["steps"]
            goal = 10000
            progress = min(100, int(steps / goal * 100))
            message_parts.append(f"🚶 Шаги: {steps:,} ({progress}% от цели)")
        
        if data.get("heart_rate_resting"):
            message_parts.append(f"❤️ Пульс покоя: {data['heart_rate_resting']} bpm")
        
        if data.get("heart_rate_avg"):
            message_parts.append(f"💓 Средний пульс: {data['heart_rate_avg']} bpm")
        
        if data.get("calories"):
            message_parts.append(f"🔥 Калории: {data['calories']} ккал")
        
        if data.get("active_energy"):
            message_parts.append(f"⚡ Активные калории: {data['active_energy']} ккал")
        
        if data.get("exercise_minutes"):
            mins = data["exercise_minutes"]
            goal_mins = 30
            progress = min(100, int(mins / goal_mins * 100))
            message_parts.append(f"💪 Упражнения: {mins} мин ({progress}% от цели)")
        
        if self._last_update:
            message_parts.append(f"\n⏰ Обновлено: {self._last_update.strftime('%d.%m.%Y %H:%M')}")
        
        return "\n".join(message_parts)
    
    def get_health_context_for_ai(self) -> str:
        """Get health data formatted as context for AI assistant"""
        if not self._latest_data:
            return ""
        
        data = self._latest_data
        context_parts = ["\n=== APPLE HEALTH DATA ==="]
        
        if data.get("sleep_score"):
            context_parts.append(f"Sleep Score: {data['sleep_score']}/100")
        
        if data.get("steps"):
            context_parts.append(f"Steps Today: {data['steps']:,}")
        
        if data.get("heart_rate_resting"):
            context_parts.append(f"Resting Heart Rate: {data['heart_rate_resting']} bpm")
        
        if data.get("heart_rate_avg"):
            context_parts.append(f"Average Heart Rate: {data['heart_rate_avg']} bpm")
        
        if data.get("calories"):
            context_parts.append(f"Total Calories: {data['calories']} kcal")
        
        if data.get("exercise_minutes"):
            context_parts.append(f"Exercise Minutes: {data['exercise_minutes']} min")
        
        context_parts.append("\nUse this data to give personalized health and activity recommendations.")
        
        return "\n".join(context_parts)


# Module instance
apple_health_module = AppleHealthModule()
