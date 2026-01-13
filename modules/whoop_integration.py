"""
WHOOP Integration Module (Optional)
Provides health-based recommendations without breaking bot if unavailable
"""

import os
import logging
import requests
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# WHOOP API configuration
WHOOP_API_BASE = "https://api.prod.whoop.com/developer"
WHOOP_ACCESS_TOKEN = os.getenv("WHOOP_ACCESS_TOKEN")


class WhoopClient:
    """Client for WHOOP API with safe error handling"""
    
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        self.available = self._check_availability()
    
    def _check_availability(self) -> bool:
        """Check if WHOOP API is available"""
        try:
            response = requests.get(
                f"{WHOOP_API_BASE}/v1/user/profile/basic",
                headers=self.headers,
                timeout=5
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"WHOOP API not available: {e}")
            return False
    
    def get_latest_recovery(self) -> Optional[Dict[str, Any]]:
        """Get latest recovery data"""
        if not self.available:
            return None
        
        try:
            # Get today's date range
            end = datetime.now()
            start = end - timedelta(days=1)
            
            response = requests.get(
                f"{WHOOP_API_BASE}/v1/recovery",
                headers=self.headers,
                params={
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "limit": 1
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                records = data.get("records", [])
                return records[0] if records else None
            
            return None
        
        except Exception as e:
            logger.error(f"Error fetching recovery: {e}")
            return None
    
    def get_recovery_score(self) -> Optional[int]:
        """Get just the recovery score (0-100)"""
        recovery = self.get_latest_recovery()
        if recovery and "score" in recovery:
            return recovery["score"].get("recovery_score")
        return None


def get_whoop_recommendation(recovery_score: Optional[int]) -> str:
    """
    Generate task recommendation based on WHOOP recovery score
    
    Args:
        recovery_score: Recovery percentage (0-100) or None if unavailable
    
    Returns:
        Recommendation text to append to evening message
    """
    if recovery_score is None:
        return ""
    
    # Green zone (67-100%) - High performance
    if recovery_score >= 67:
        return (
            "\n\n🟢 **WHOOP Recovery: {}%**\n"
            "Отличное восстановление! Организм готов к нагрузкам.\n"
            "✅ Можешь делать интенсивную практику или сложные задачи."
        ).format(recovery_score)
    
    # Yellow zone (34-66%) - Moderate performance
    elif recovery_score >= 34:
        return (
            "\n\n🟡 **WHOOP Recovery: {}%**\n"
            "Среднее восстановление. Умеренная активность рекомендована.\n"
            "✅ Лучше выбрать лёгкую практику или просмотр лекций."
        ).format(recovery_score)
    
    # Red zone (0-33%) - Low performance
    else:
        return (
            "\n\n🔴 **WHOOP Recovery: {}%**\n"
            "Низкое восстановление. Организму нужен отдых.\n"
            "✅ Сегодня лучше ограничиться просмотром лекций.\n"
            "💡 Используй /freeze если не успеешь сделать практику."
        ).format(recovery_score)


def get_whoop_client() -> Optional[WhoopClient]:
    """
    Get WHOOP client instance if token is available
    
    Returns:
        WhoopClient instance or None if token not set
    """
    if not WHOOP_ACCESS_TOKEN:
        logger.debug("WHOOP_ACCESS_TOKEN not set, WHOOP integration disabled")
        return None
    
    try:
        client = WhoopClient(WHOOP_ACCESS_TOKEN)
        if client.available:
            logger.info("WHOOP integration enabled")
            return client
        else:
            logger.warning("WHOOP token set but API unavailable")
            return None
    except Exception as e:
        logger.error(f"Error initializing WHOOP client: {e}")
        return None


# Global client instance (initialized once)
_whoop_client = None


def get_evening_task_with_whoop(base_message: str) -> str:
    """
    Enhance evening task message with WHOOP recommendation
    
    Args:
        base_message: Base evening task message
    
    Returns:
        Enhanced message with WHOOP data if available
    """
    global _whoop_client
    
    # Initialize client on first use
    if _whoop_client is None:
        _whoop_client = get_whoop_client()
    
    # If WHOOP not available, return base message
    if _whoop_client is None:
        return base_message
    
    # Get recovery score
    try:
        recovery_score = _whoop_client.get_recovery_score()
        whoop_rec = get_whoop_recommendation(recovery_score)
        
        if whoop_rec:
            return base_message + whoop_rec
    
    except Exception as e:
        logger.error(f"Error getting WHOOP recommendation: {e}")
    
    return base_message
