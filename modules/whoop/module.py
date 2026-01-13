"""
WHOOP API Integration Module
Fetches health metrics: Recovery, Sleep, Strain
"""

import os
import requests
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class WhoopAPI:
    """WHOOP API client for fetching health metrics"""
    
    BASE_URL = "https://api.prod.whoop.com/developer"
    
    def __init__(self, access_token: str):
        """
        Initialize WHOOP API client
        
        Args:
            access_token: OAuth access token for the user
        """
        self.access_token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
    
    def get_latest_recovery(self) -> Optional[Dict[str, Any]]:
        """
        Get the latest recovery data
        
        Returns:
            Dict with recovery data or None if error
        """
        try:
            url = f"{self.BASE_URL}/v2/recovery"
            params = {"limit": 1}
            
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            if data.get("records"):
                return data["records"][0]
            return None
            
        except Exception as e:
            logger.error(f"Error fetching recovery data: {e}")
            return None
    
    def get_latest_sleep(self) -> Optional[Dict[str, Any]]:
        """
        Get the latest sleep data
        
        Returns:
            Dict with sleep data or None if error
        """
        try:
            url = f"{self.BASE_URL}/v2/activity/sleep"
            params = {"limit": 1}
            
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            if data.get("records"):
                return data["records"][0]
            return None
            
        except Exception as e:
            logger.error(f"Error fetching sleep data: {e}")
            return None
    
    def get_today_cycle(self) -> Optional[Dict[str, Any]]:
        """
        Get today's cycle (strain) data
        
        Returns:
            Dict with cycle data or None if error
        """
        try:
            url = f"{self.BASE_URL}/v2/cycle"
            
            # Get cycles from today
            now = datetime.utcnow()
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            
            params = {
                "limit": 1,
                "start": start.isoformat() + "Z"
            }
            
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            if data.get("records"):
                return data["records"][0]
            return None
            
        except Exception as e:
            logger.error(f"Error fetching cycle data: {e}")
            return None
    
    def format_recovery_message(self, recovery: Dict[str, Any]) -> str:
        """Format recovery data into readable message"""
        if not recovery or not recovery.get("score"):
            return "❌ Нет данных о восстановлении"
        
        score_data = recovery["score"]
        recovery_score = score_data.get("recovery_score", 0)
        rhr = score_data.get("resting_heart_rate", 0)
        hrv = score_data.get("hrv_rmssd_milli", 0)
        spo2 = score_data.get("spo2_percentage", 0)
        
        # Determine emoji based on recovery score
        if recovery_score >= 67:
            emoji = "🟢"
            status = "Отличное восстановление"
        elif recovery_score >= 34:
            emoji = "🟡"
            status = "Среднее восстановление"
        else:
            emoji = "🔴"
            status = "Низкое восстановление"
        
        message = f"""💪 **Recovery Score: {recovery_score}%** {emoji}

**Статус:** {status}

📊 **Метрики:**
• Пульс в покое: {rhr} bpm
• HRV: {hrv:.1f} ms
• SpO2: {spo2:.1f}%

"""
        
        # Add recommendation
        if recovery_score >= 67:
            message += "✅ Организм готов к нагрузкам! Можно делать интенсивную практику."
        elif recovery_score >= 34:
            message += "⚠️ Умеренное восстановление. Лёгкая практика или теория."
        else:
            message += "🛑 Низкое восстановление. Сегодня лучше отдохнуть или только лекции."
        
        return message
    
    def format_sleep_message(self, sleep: Dict[str, Any]) -> str:
        """Format sleep data into readable message"""
        if not sleep:
            return "❌ Нет данных о сне"
        
        # Parse sleep times
        start = datetime.fromisoformat(sleep["start"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(sleep["end"].replace("Z", "+00:00"))
        duration_hours = (end - start).total_seconds() / 3600
        
        score_data = sleep.get("score", {})
        performance = score_data.get("sleep_performance_percentage", 0)
        efficiency = score_data.get("sleep_efficiency_percentage", 0)
        respiratory_rate = score_data.get("respiratory_rate", 0)
        
        # Determine emoji
        if performance >= 85:
            emoji = "😴✨"
        elif performance >= 70:
            emoji = "😴"
        else:
            emoji = "😵"
        
        message = f"""💤 **Последний сон** {emoji}

**Длительность:** {duration_hours:.1f} часов
**Performance:** {performance}%
**Efficiency:** {efficiency:.1f}%
**Частота дыхания:** {respiratory_rate:.1f} вдохов/мин

"""
        
        # Add analysis
        if duration_hours < 6:
            message += "⚠️ Мало спал! Организму нужно больше отдыха."
        elif duration_hours > 10:
            message += "💭 Долгий сон - возможно, организм восстанавливался после стресса."
        else:
            message += "✅ Нормальная длительность сна."
        
        return message
    
    def format_strain_message(self, cycle: Dict[str, Any]) -> str:
        """Format strain/cycle data into readable message"""
        if not cycle or not cycle.get("score"):
            return "❌ Нет данных о нагрузке за сегодня"
        
        score_data = cycle["score"]
        strain = score_data.get("strain", 0)
        avg_hr = score_data.get("average_heart_rate", 0)
        max_hr = score_data.get("max_heart_rate", 0)
        
        # Determine emoji based on strain
        if strain >= 14:
            emoji = "🔥🔥"
            level = "Очень высокая"
        elif strain >= 10:
            emoji = "🔥"
            level = "Высокая"
        elif strain >= 7:
            emoji = "💪"
            level = "Средняя"
        else:
            emoji = "🌱"
            level = "Низкая"
        
        message = f"""⚡ **Strain Score: {strain:.1f}** {emoji}

**Уровень нагрузки:** {level}

📊 **Метрики:**
• Средний пульс: {avg_hr} bpm
• Макс пульс: {max_hr} bpm
"""
        
        return message
    
    def calculate_stress_level(self, recovery: Dict[str, Any]) -> str:
        """
        Calculate stress level based on HRV and RHR
        WHOOP doesn't provide direct stress metric, so we infer it
        """
        if not recovery or not recovery.get("score"):
            return "Нет данных"
        
        score_data = recovery["score"]
        recovery_score = score_data.get("recovery_score", 50)
        hrv = score_data.get("hrv_rmssd_milli", 50)
        
        # Low recovery + low HRV = high stress
        if recovery_score < 34 and hrv < 30:
            return "🔴 Высокий стресс"
        elif recovery_score < 67 and hrv < 50:
            return "🟡 Умеренный стресс"
        else:
            return "🟢 Низкий стресс"


def get_whoop_client(user_id: int) -> Optional[WhoopAPI]:
    """
    Get WHOOP API client for user
    
    Args:
        user_id: Telegram user ID
    
    Returns:
        WhoopAPI instance or None if not configured
    """
    # TODO: Load access token from database
    # For now, check environment variable
    access_token = os.getenv("WHOOP_ACCESS_TOKEN")
    
    if not access_token:
        logger.warning(f"No WHOOP access token found for user {user_id}")
        return None
    
    return WhoopAPI(access_token)
