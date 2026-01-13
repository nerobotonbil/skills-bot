"""
Intelligent Task Recommendation System
Based on WHOOP recovery data and energy levels
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class TaskRecommender:
    """Recommends tasks based on energy levels and recovery data"""
    
    # Task difficulty levels
    DIFFICULTY_EASY = "easy"
    DIFFICULTY_MEDIUM = "medium"
    DIFFICULTY_HARD = "hard"
    
    # Energy level thresholds
    ENERGY_LOW = "low"          # Recovery < 33%
    ENERGY_MEDIUM = "medium"    # Recovery 33-66%
    ENERGY_HIGH = "high"        # Recovery > 66%
    
    def __init__(self):
        pass
    
    def calculate_energy_level(self, whoop_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate current energy level based on WHOOP data
        
        Returns dict with:
        - energy_level: "low", "medium", "high"
        - recovery_score: 0-100
        - strain: day strain value
        - sleep_quality: 0-100
        - stress_indicator: 0-100 (higher = more stress)
        """
        
        if not whoop_data or not whoop_data.get("available"):
            return {
                "energy_level": self.ENERGY_MEDIUM,
                "recovery_score": None,
                "strain": None,
                "sleep_quality": None,
                "stress_indicator": None,
                "reason": "No WHOOP data available"
            }
        
        recovery = whoop_data.get("recovery", {})
        sleep = whoop_data.get("sleep", {})
        strain = whoop_data.get("strain", {})
        
        # Get recovery score (primary indicator)
        recovery_score = recovery.get("score") if recovery else None
        
        # Get sleep quality
        sleep_performance = sleep.get("performance_percentage") if sleep else None
        
        # Get strain
        day_strain = strain.get("day_strain") if strain else None
        
        # Calculate stress indicator
        stress_indicator = self._calculate_stress(recovery, sleep, strain)
        
        # Determine energy level
        if recovery_score is None:
            energy_level = self.ENERGY_MEDIUM
        elif recovery_score >= 67:
            energy_level = self.ENERGY_HIGH
        elif recovery_score >= 34:
            energy_level = self.ENERGY_MEDIUM
        else:
            energy_level = self.ENERGY_LOW
        
        # Adjust for sleep quality
        if sleep_performance and sleep_performance < 70:
            # Poor sleep reduces energy level
            if energy_level == self.ENERGY_HIGH:
                energy_level = self.ENERGY_MEDIUM
            elif energy_level == self.ENERGY_MEDIUM:
                energy_level = self.ENERGY_LOW
        
        # Adjust for high strain
        if day_strain and day_strain > 15:
            # High strain without recovery
            if recovery_score and recovery_score < 50:
                if energy_level == self.ENERGY_MEDIUM:
                    energy_level = self.ENERGY_LOW
        
        return {
            "energy_level": energy_level,
            "recovery_score": recovery_score,
            "strain": day_strain,
            "sleep_quality": sleep_performance,
            "stress_indicator": stress_indicator,
            "hrv": recovery.get("hrv_rmssd") if recovery else None,
            "rhr": recovery.get("resting_heart_rate") if recovery else None
        }
    
    def _calculate_stress(self, recovery: Dict, sleep: Dict, strain: Dict) -> Optional[int]:
        """
        Calculate stress indicator (0-100, higher = more stress)
        Based on HRV, RHR, recovery, and strain/recovery balance
        """
        
        if not recovery:
            return None
        
        stress_score = 0
        factors = 0
        
        # Factor 1: Recovery score (inverted - low recovery = high stress)
        recovery_score = recovery.get("score")
        if recovery_score is not None:
            stress_score += (100 - recovery_score)
            factors += 1
        
        # Factor 2: HRV (low HRV = high stress)
        # Typical HRV range: 20-100ms, optimal: 50-100ms
        hrv = recovery.get("hrv_rmssd")
        if hrv is not None:
            if hrv < 30:
                stress_score += 80
            elif hrv < 50:
                stress_score += 50
            elif hrv < 70:
                stress_score += 30
            else:
                stress_score += 10
            factors += 1
        
        # Factor 3: RHR elevation (higher than normal = stress)
        # Typical RHR: 40-70 bpm, athlete: 40-60 bpm
        rhr = recovery.get("resting_heart_rate")
        if rhr is not None:
            if rhr > 70:
                stress_score += 70
            elif rhr > 65:
                stress_score += 50
            elif rhr > 60:
                stress_score += 30
            else:
                stress_score += 10
            factors += 1
        
        # Factor 4: Sleep quality (poor sleep = stress)
        if sleep:
            sleep_perf = sleep.get("performance_percentage")
            if sleep_perf is not None:
                stress_score += (100 - sleep_perf)
                factors += 1
        
        # Factor 5: Strain/Recovery balance
        if strain and recovery_score is not None:
            day_strain = strain.get("day_strain")
            if day_strain is not None:
                # High strain with low recovery = stress accumulation
                if day_strain > 15 and recovery_score < 50:
                    stress_score += 80
                elif day_strain > 12 and recovery_score < 60:
                    stress_score += 50
                elif day_strain > 10:
                    stress_score += 30
                else:
                    stress_score += 10
                factors += 1
        
        if factors == 0:
            return None
        
        return min(100, int(stress_score / factors))
    
    def recommend_task_difficulty(self, energy_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recommend task difficulty based on energy level
        
        Returns:
        - recommended_difficulty: "easy", "medium", "hard"
        - max_tasks: suggested number of tasks
        - focus_duration_hours: recommended focus time
        - break_frequency_minutes: how often to take breaks
        - task_types: list of recommended task types
        """
        
        energy_level = energy_data.get("energy_level", self.ENERGY_MEDIUM)
        recovery_score = energy_data.get("recovery_score")
        stress = energy_data.get("stress_indicator")
        
        if energy_level == self.ENERGY_HIGH:
            return {
                "recommended_difficulty": self.DIFFICULTY_HARD,
                "max_tasks": 5,
                "focus_duration_hours": 4,
                "break_frequency_minutes": 60,
                "task_types": [
                    "Complex problem solving",
                    "Learning new skills (courses, lectures)",
                    "Strategic planning",
                    "Creative work",
                    "Challenging projects"
                ],
                "advice": "Высокая энергия! Отличный день для сложных задач и обучения. Можешь браться за курсы и challenging проекты."
            }
        
        elif energy_level == self.ENERGY_MEDIUM:
            return {
                "recommended_difficulty": self.DIFFICULTY_MEDIUM,
                "max_tasks": 3,
                "focus_duration_hours": 3,
                "break_frequency_minutes": 45,
                "task_types": [
                    "Routine work",
                    "Meetings and communication",
                    "Light learning (videos, articles)",
                    "Planning and organizing",
                    "Moderate complexity tasks"
                ],
                "advice": "Средняя энергия. Фокусируйся на рутинных задачах и легком обучении. Избегай слишком сложных проектов."
            }
        
        else:  # LOW energy
            # Check if it's due to high stress
            if stress and stress > 70:
                return {
                    "recommended_difficulty": self.DIFFICULTY_EASY,
                    "max_tasks": 1,
                    "focus_duration_hours": 1,
                    "break_frequency_minutes": 30,
                    "task_types": [
                        "Rest and recovery",
                        "Light reading",
                        "Meditation",
                        "Easy administrative tasks",
                        "Planning for tomorrow"
                    ],
                    "advice": "⚠️ Высокий стресс и низкая энергия! Рекомендую отдых и восстановление. Сегодня лучше набраться сил для завтрашнего дня."
                }
            else:
                return {
                    "recommended_difficulty": self.DIFFICULTY_EASY,
                    "max_tasks": 2,
                    "focus_duration_hours": 2,
                    "break_frequency_minutes": 30,
                    "task_types": [
                        "Easy tasks",
                        "Administrative work",
                        "Light communication",
                        "Simple planning",
                        "Low-effort activities"
                    ],
                    "advice": "Низкая энергия. Делай только простые задачи. Сохрани силы для более важных дел завтра."
                }
    
    def recommend_sleep_time(self, whoop_data: Dict[str, Any], target_wake_time: str = "08:00") -> Dict[str, Any]:
        """
        Recommend optimal sleep time based on sleep need and recovery
        
        Args:
            whoop_data: WHOOP comprehensive data
            target_wake_time: Desired wake time in "HH:MM" format
        
        Returns:
            - recommended_bedtime: "HH:MM"
            - sleep_need_hours: total sleep needed
            - sleep_debt_hours: current sleep debt
            - advice: text recommendation
        """
        
        sleep = whoop_data.get("sleep", {})
        recovery = whoop_data.get("recovery", {})
        
        # Get sleep need
        baseline_need = sleep.get("baseline_need_hours", 8.0)
        debt_need = sleep.get("debt_need_hours", 0)
        strain_need = sleep.get("strain_need_hours", 0)
        
        total_need = baseline_need + debt_need + strain_need
        
        # Parse target wake time
        wake_hour, wake_min = map(int, target_wake_time.split(":"))
        
        # Calculate bedtime
        sleep_hours = int(total_need)
        sleep_minutes = int((total_need - sleep_hours) * 60)
        
        bedtime_hour = wake_hour - sleep_hours
        bedtime_min = wake_min - sleep_minutes
        
        # Handle negative minutes
        if bedtime_min < 0:
            bedtime_hour -= 1
            bedtime_min += 60
        
        # Handle negative hours (previous day)
        if bedtime_hour < 0:
            bedtime_hour += 24
        
        bedtime = f"{bedtime_hour:02d}:{bedtime_min:02d}"
        
        # Generate advice
        recovery_score = recovery.get("score") if recovery else None
        
        if debt_need > 1:
            advice = f"У тебя накопился долг сна {debt_need:.1f}ч. Ложись пораньше!"
        elif recovery_score and recovery_score < 50:
            advice = "Низкое восстановление. Сегодня важно хорошо выспаться."
        elif total_need > 9:
            advice = f"Тебе нужно {total_need:.1f}ч сна из-за высокой нагрузки."
        else:
            advice = f"Стандартная потребность во сне: {total_need:.1f}ч."
        
        return {
            "recommended_bedtime": bedtime,
            "target_wake_time": target_wake_time,
            "sleep_need_hours": round(total_need, 1),
            "baseline_need_hours": round(baseline_need, 1),
            "sleep_debt_hours": round(debt_need, 1),
            "strain_need_hours": round(strain_need, 1),
            "advice": advice
        }
    
    def get_weekend_boost_factor(self) -> float:
        """
        Get task multiplier for weekends
        User has more energy on weekends due to rest
        """
        now = datetime.now()
        if now.weekday() in [5, 6]:  # Saturday, Sunday
            return 1.5
        return 1.0


# Singleton instance
_recommender = None

def get_task_recommender() -> TaskRecommender:
    """Get singleton task recommender instance"""
    global _recommender
    if _recommender is None:
        _recommender = TaskRecommender()
    return _recommender
