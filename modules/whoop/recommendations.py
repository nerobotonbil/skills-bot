"""
WHOOP-based Smart Recommendations
Adjusts learning recommendations based on health metrics
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class WhoopRecommendations:
    """Generate smart recommendations based on WHOOP data"""
    
    @staticmethod
    def get_activity_recommendation(recovery_score: int, strain: float = 0) -> Dict[str, Any]:
        """
        Get activity recommendation based on recovery score
        
        Args:
            recovery_score: Recovery percentage (0-100)
            strain: Current strain score (0-21)
        
        Returns:
            Dict with recommendation details
        """
        if recovery_score >= 67:
            # Green recovery - ready for intense activity
            return {
                "level": "high",
                "emoji": "🟢",
                "title": "Отличное восстановление!",
                "description": "Организм готов к нагрузкам",
                "activities": [
                    "Интенсивная практика",
                    "Глубокая работа (Deep Work)",
                    "Физические упражнения",
                    "Сложные задачи"
                ],
                "avoid": [],
                "energy_level": "Высокий"
            }
        
        elif recovery_score >= 34:
            # Yellow recovery - moderate activity
            return {
                "level": "medium",
                "emoji": "🟡",
                "title": "Среднее восстановление",
                "description": "Умеренная активность рекомендована",
                "activities": [
                    "Лёгкая практика",
                    "Просмотр лекций",
                    "Чтение материалов",
                    "Планирование"
                ],
                "avoid": [
                    "Интенсивные тренировки",
                    "Сложные задачи требующие концентрации"
                ],
                "energy_level": "Средний"
            }
        
        else:
            # Red recovery - rest needed
            return {
                "level": "low",
                "emoji": "🔴",
                "title": "Низкое восстановление",
                "description": "Организму нужен отдых",
                "activities": [
                    "Только просмотр лекций",
                    "Лёгкое чтение",
                    "Медитация",
                    "Отдых"
                ],
                "avoid": [
                    "Практика",
                    "Интенсивная работа",
                    "Физические нагрузки"
                ],
                "energy_level": "Низкий"
            }
    
    @staticmethod
    def get_learning_plan_adjustment(recovery: Dict[str, Any], sleep: Dict[str, Any] = None) -> str:
        """
        Generate learning plan adjustment message based on WHOOP data
        
        Args:
            recovery: Recovery data from WHOOP
            sleep: Sleep data from WHOOP (optional)
        
        Returns:
            Formatted message with recommendations
        """
        if not recovery or not recovery.get("score"):
            return ""
        
        score_data = recovery["score"]
        recovery_score = score_data.get("recovery_score", 50)
        hrv = score_data.get("hrv_rmssd_milli", 0)
        rhr = score_data.get("resting_heart_rate", 0)
        
        # Get recommendation
        rec = WhoopRecommendations.get_activity_recommendation(recovery_score)
        
        message = f"""
🏋️ **Рекомендации на основе WHOOP**

{rec['emoji']} **{rec['title']}**
{rec['description']}

💪 Recovery: {recovery_score}%
❤️ HRV: {hrv:.1f} ms
🫀 RHR: {rhr} bpm

**Рекомендуемые активности:**
"""
        
        for activity in rec['activities']:
            message += f"✅ {activity}\n"
        
        if rec['avoid']:
            message += "\n**Избегать:**\n"
            for avoid in rec['avoid']:
                message += f"❌ {avoid}\n"
        
        # Add sleep context if available
        if sleep and sleep.get("score"):
            sleep_perf = sleep["score"].get("sleep_performance_percentage", 0)
            
            # Parse sleep duration
            from datetime import datetime
            start = datetime.fromisoformat(sleep["start"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(sleep["end"].replace("Z", "+00:00"))
            duration_hours = (end - start).total_seconds() / 3600
            
            message += f"\n💤 **Сон:** {duration_hours:.1f}ч (Performance: {sleep_perf}%)\n"
            
            if duration_hours < 6:
                message += "⚠️ Недостаточный сон - снижена когнитивная функция\n"
            elif sleep_perf < 70:
                message += "⚠️ Низкое качество сна - возможна усталость\n"
        
        return message
    
    @staticmethod
    def should_skip_practice(recovery_score: int) -> bool:
        """
        Determine if practice should be skipped today
        
        Args:
            recovery_score: Recovery percentage (0-100)
        
        Returns:
            True if practice should be skipped
        """
        return recovery_score < 34
    
    @staticmethod
    def get_optimal_practice_time(recovery: Dict[str, Any], cycle: Dict[str, Any] = None) -> str:
        """
        Suggest optimal time for practice based on recovery and strain
        
        Args:
            recovery: Recovery data
            cycle: Cycle/strain data (optional)
        
        Returns:
            Time recommendation message
        """
        if not recovery or not recovery.get("score"):
            return "Нет данных для рекомендации"
        
        recovery_score = recovery["score"].get("recovery_score", 50)
        
        if recovery_score >= 67:
            return "🌅 Утро или день - пик энергии"
        elif recovery_score >= 34:
            return "🌤️ Утро предпочтительнее - энергия снизится к вечеру"
        else:
            return "🌙 Сегодня лучше отдохнуть"
    
    @staticmethod
    def format_recommendation_for_ai(recovery: Dict[str, Any], sleep: Dict[str, Any] = None) -> str:
        """
        Format WHOOP data as context for AI assistant
        
        This can be injected into AI prompts to make context-aware recommendations
        
        Args:
            recovery: Recovery data
            sleep: Sleep data (optional)
        
        Returns:
            Formatted context string for AI
        """
        if not recovery or not recovery.get("score"):
            return ""
        
        score_data = recovery["score"]
        recovery_score = score_data.get("recovery_score", 50)
        
        rec = WhoopRecommendations.get_activity_recommendation(recovery_score)
        
        context = f"""
User's current health status (WHOOP data):
- Recovery Score: {recovery_score}% ({rec['level']} level)
- Energy Level: {rec['energy_level']}
- Recommended activities: {', '.join(rec['activities'])}
- Should avoid: {', '.join(rec['avoid']) if rec['avoid'] else 'None'}
"""
        
        if sleep:
            from datetime import datetime
            start = datetime.fromisoformat(sleep["start"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(sleep["end"].replace("Z", "+00:00"))
            duration_hours = (end - start).total_seconds() / 3600
            sleep_perf = sleep.get("score", {}).get("sleep_performance_percentage", 0)
            
            context += f"- Last sleep: {duration_hours:.1f} hours (Performance: {sleep_perf}%)\n"
        
        context += "\nPlease adjust your recommendations based on this health data."
        
        return context
