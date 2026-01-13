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
        """Get latest recovery data for TODAY"""
        if not self.available:
            return None
        
        try:
            # Get TODAY's date range (from midnight to now)
            now = datetime.now()
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now
            
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
    
    def get_latest_sleep(self) -> Optional[Dict[str, Any]]:
        """Get latest sleep data for TODAY"""
        if not self.available:
            return None
        
        try:
            # Get sleep from last 36 hours (to catch last night's sleep)
            end = datetime.now()
            start = end - timedelta(hours=36)
            
            response = requests.get(
                f"{WHOOP_API_BASE}/v1/activity/sleep",
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
            logger.error(f"Error fetching sleep: {e}")
            return None
    
    def get_latest_cycle(self) -> Optional[Dict[str, Any]]:
        """Get latest physiological cycle (Strain data) for TODAY"""
        if not self.available:
            return None
        
        try:
            # Get TODAY's cycle (from midnight to now)
            now = datetime.now()
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now
            
            response = requests.get(
                f"{WHOOP_API_BASE}/v1/cycle",
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
            logger.error(f"Error fetching cycle: {e}")
            return None
    
    def get_comprehensive_health_data(self) -> Dict[str, Any]:
        """Get all health data for AI assistant context"""
        if not self.available:
            logger.warning("WHOOP API not available")
            return {"available": False}
        
        try:
            logger.warning("🔄 Fetching WHOOP recovery data...")
            recovery = self.get_latest_recovery()
            logger.warning(f"Recovery data received: {recovery is not None}")
            
            logger.warning("🔄 Fetching WHOOP sleep data...")
            sleep = self.get_latest_sleep()
            logger.warning(f"Sleep data received: {sleep is not None}")
            
            logger.warning("🔄 Fetching WHOOP cycle data...")
            cycle = self.get_latest_cycle()
            logger.warning(f"Cycle data received: {cycle is not None}")
            
            result = {
                "available": True,
                "timestamp": datetime.now().isoformat(),
                "recovery": None,
                "sleep": None,
                "strain": None
            }
            
            # Parse recovery data
            if recovery and "score" in recovery:
                score = recovery["score"]
                result["recovery"] = {
                    "score": score.get("recovery_score"),
                    "resting_heart_rate": score.get("resting_heart_rate"),
                    "hrv_rmssd": score.get("hrv_rmssd_milli"),
                    "spo2": score.get("spo2_percentage"),
                    "skin_temp_celsius": score.get("skin_temp_celsius"),
                    "user_calibrating": score.get("user_calibrating", False)
                }
            
            # Parse sleep data
            if sleep:
                result["sleep"] = {
                    "performance_percentage": sleep.get("score", {}).get("stage_summary", {}).get("total_in_bed_time_milli"),
                    "total_sleep_time_hours": sleep.get("score", {}).get("stage_summary", {}).get("total_sleep_time_milli", 0) / 3600000,
                    "sleep_efficiency": sleep.get("score", {}).get("sleep_efficiency_percentage"),
                    "respiratory_rate": sleep.get("score", {}).get("respiratory_rate"),
                    "stages": sleep.get("score", {}).get("stage_summary")
                }
            
            # Parse cycle/strain data  
            if cycle and "score" in cycle:
                score = cycle["score"]
                result["strain"] = {
                    "day_strain": score.get("strain"),
                    "kilojoules": score.get("kilojoule"),
                    "average_heart_rate": score.get("average_heart_rate"),
                    "max_heart_rate": score.get("max_heart_rate")
                }
            
            # Check if we have ANY data
            has_data = any([result["recovery"], result["sleep"], result["strain"]])
            logger.warning(f"✅ Comprehensive data compiled: recovery={result['recovery'] is not None}, sleep={result['sleep'] is not None}, strain={result['strain'] is not None}")
            
            if not has_data:
                logger.warning("❌ No WHOOP data available for today - all metrics are None")
                return {"available": False, "reason": "No data for today"}
            
            return result
        
        except Exception as e:
            logger.error(f"Error getting comprehensive health data: {e}")
            return {"available": False, "error": str(e)}


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
        logger.warning("⚠️ WHOOP_ACCESS_TOKEN not set in environment variables - WHOOP integration disabled")
        return None
    
    try:
        client = WhoopClient(WHOOP_ACCESS_TOKEN)
        if client.available:
            logger.warning("✅ WHOOP integration enabled and API available")
            return client
        else:
            logger.warning("❌ WHOOP token set but API unavailable - check token validity")
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
