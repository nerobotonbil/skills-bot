"""
Smart Recommendation Command with WHOOP Integration
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from .module import get_whoop_client
from .recommendations import WhoopRecommendations

logger = logging.getLogger(__name__)


async def recommend_with_whoop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /recommend - Get personalized learning recommendation based on WHOOP data
    """
    user_id = update.effective_user.id
    
    # Get WHOOP client
    whoop = get_whoop_client(user_id)
    
    if not whoop:
        # Fallback to regular recommendation without WHOOP
        await update.message.reply_text(
            "💡 **Рекомендация дня**\n\n"
            "WHOOP не подключён - даю общую рекомендацию:\n\n"
            "✅ Начни с одной лекции (20-30 мин)\n"
            "✅ Затем лёгкая практика (15 мин)\n"
            "✅ Запиши инсайты в Notion\n\n"
            "Подключи WHOOP для персонализированных рекомендаций: /whoop"
        )
        return
    
    await update.message.reply_text("⏳ Анализирую твоё состояние...")
    
    # Fetch WHOOP data
    recovery = whoop.get_latest_recovery()
    sleep = whoop.get_latest_sleep()
    cycle = whoop.get_today_cycle()
    
    if not recovery:
        await update.message.reply_text(
            "❌ Не удалось получить данные Recovery из WHOOP.\n"
            "Проверь подключение или попробуй позже."
        )
        return
    
    # Get recommendation
    message = WhoopRecommendations.get_learning_plan_adjustment(recovery, sleep)
    
    # Add optimal time suggestion
    optimal_time = WhoopRecommendations.get_optimal_practice_time(recovery, cycle)
    message += f"\n⏰ **Оптимальное время:** {optimal_time}\n"
    
    # Check if practice should be skipped
    recovery_score = recovery.get("score", {}).get("recovery_score", 50)
    if WhoopRecommendations.should_skip_practice(recovery_score):
        message += "\n🛑 **Рекомендация:** Сегодня пропусти практику, сосредоточься на теории или отдыхе."
        message += "\nИспользуй /freeze чтобы сохранить стрик."
    
    await update.message.reply_text(message, parse_mode='Markdown')
