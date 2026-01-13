"""
WHOOP Commands for Telegram Bot
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from .module import get_whoop_client

logger = logging.getLogger(__name__)


async def whoop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /whoop - Show all WHOOP metrics (Recovery, Sleep, Strain, Stress)
    """
    user_id = update.effective_user.id
    
    # Get WHOOP client
    whoop = get_whoop_client(user_id)
    
    if not whoop:
        await update.message.reply_text(
            "❌ WHOOP не подключён\n\n"
            "Для подключения:\n"
            "1. Зарегистрируй приложение на https://developer.whoop.com/dashboard\n"
            "2. Получи OAuth токен\n"
            "3. Добавь токен в настройки бота"
        )
        return
    
    # Fetch all data
    await update.message.reply_text("⏳ Загружаю данные из WHOOP...")
    
    recovery = whoop.get_latest_recovery()
    sleep = whoop.get_latest_sleep()
    cycle = whoop.get_today_cycle()
    
    # Format messages
    recovery_msg = whoop.format_recovery_message(recovery)
    sleep_msg = whoop.format_sleep_message(sleep)
    strain_msg = whoop.format_strain_message(cycle)
    stress_msg = whoop.calculate_stress_level(recovery)
    
    # Combine into one message
    full_message = f"""🏋️ **WHOOP Metrics**

{recovery_msg}

---

{sleep_msg}

---

{strain_msg}

---

😰 **Уровень стресса:** {stress_msg}
"""
    
    await update.message.reply_text(full_message, parse_mode='Markdown')


async def recovery_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /recovery - Show only Recovery metrics
    """
    user_id = update.effective_user.id
    
    whoop = get_whoop_client(user_id)
    
    if not whoop:
        await update.message.reply_text(
            "❌ WHOOP не подключён. Используй /whoop для инструкций."
        )
        return
    
    await update.message.reply_text("⏳ Загружаю Recovery...")
    
    recovery = whoop.get_latest_recovery()
    message = whoop.format_recovery_message(recovery)
    
    await update.message.reply_text(message, parse_mode='Markdown')


async def sleep_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /sleep - Show only Sleep metrics with analysis
    """
    user_id = update.effective_user.id
    
    whoop = get_whoop_client(user_id)
    
    if not whoop:
        await update.message.reply_text(
            "❌ WHOOP не подключён. Используй /whoop для инструкций."
        )
        return
    
    await update.message.reply_text("⏳ Загружаю данные о сне...")
    
    sleep = whoop.get_latest_sleep()
    recovery = whoop.get_latest_recovery()
    
    message = whoop.format_sleep_message(sleep)
    
    # Add recovery context if available
    if recovery and recovery.get("score"):
        recovery_score = recovery["score"].get("recovery_score", 0)
        message += f"\n\n💪 Recovery после сна: {recovery_score}%"
    
    await update.message.reply_text(message, parse_mode='Markdown')


async def strain_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /strain - Show today's Strain metrics
    """
    user_id = update.effective_user.id
    
    whoop = get_whoop_client(user_id)
    
    if not whoop:
        await update.message.reply_text(
            "❌ WHOOP не подключён. Используй /whoop для инструкций."
        )
        return
    
    await update.message.reply_text("⏳ Загружаю данные о нагрузке...")
    
    cycle = whoop.get_today_cycle()
    message = whoop.format_strain_message(cycle)
    
    await update.message.reply_text(message, parse_mode='Markdown')
