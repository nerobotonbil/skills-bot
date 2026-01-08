#!/usr/bin/env python3
"""
Learning Bot - Telegram бот для обучения и саморазвития

Модули:
- Notion: интеграция с Notion для хранения данных
- Learning: планирование обучения и отслеживание прогресса
- Gratitude: дневник благодарности
- Voice: обработка голосовых сообщений
- AI Assistant: AI помощник для естественного общения
- Productivity: серии, чередование, глубокая практика

Запуск:
    python main.py
"""
import sys
import logging
from pathlib import Path

# Add root directory to path
sys.path.insert(0, str(Path(__file__).parent))

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config.settings import TELEGRAM_BOT_TOKEN, LOG_LEVEL, DATA_DIR, ALLOWED_USER_ID
from core.module_manager import module_manager
from core.scheduler import scheduler

# Import modules
from modules.notion.module import notion_module
from modules.learning.module import learning_module
from modules.gratitude.module import gratitude_module
from modules.voice.module import voice_module
from modules.ai_assistant.module import ai_assistant_module
from modules.ideas.module import ideas_module
from modules.productivity.module import productivity_module
from modules.reminders import reminder_service

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, LOG_LEVEL),
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(DATA_DIR / "bot.log")
    ]
)
logger = logging.getLogger(__name__)


def owner_only(func):
    """Декоратор для ограничения доступа только для владельца"""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id != ALLOWED_USER_ID:
            logger.warning(f"Попытка доступа от неавторизованного пользователя: {user_id}")
            await update.message.reply_text(
                "⛔ Этот бот приватный и доступен только владельцу."
            )
            return
        return await func(update, context)
    return wrapper


@owner_only
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    # Сохраняем chat_id для напоминаний
    context.bot_data['user_chat_id'] = chat_id
    reminder_service.set_chat_id(chat_id)
    
    welcome_message = f"""
🎯 Привет, {user.first_name}!

Я твой персональный AI-ассистент для обучения и саморазвития.

**Что я умею:**
📚 Планировать ежедневное обучение (лекции, видео, практика)
🔥 Отслеживать серии практики (как в Duolingo)
🧠 Создавать блоки глубокой практики
🙏 Вести дневник благодарности
🎤 Принимать голосовые сообщения
🤖 Отвечать на вопросы через AI

**Основные команды:**
/today — Цель на сегодня
/progress — Прогресс по навыкам
/skills — Все 50 навыков

**🔥 Продуктивность:**
/streak — Твоя серия практики
/deepblock — Блок глубокой практики (45 мин)
/interleave — Чередующаяся практика
/freeze — Использовать заморозку серии

**🙏 Благодарность:**
/gratitude — Записать благодарность
/review — Недельный обзор с AI

**⚙️ Система:**
/sync — Синхронизация с Notion
/help — Справка по командам

**Напоминания (время Тбилиси):**
🌅 09:00 — Утренняя благодарность
⚡ 18:00 — Защита серии
🧠 20:00 — Блок глубокой практики
🌙 23:00 — Вечерняя благодарность
📊 Пятница 19:00 — Недельный обзор

**AI-ассистент:**
Просто напиши мне или отправь голосовое — я пойму и помогу!

Готов начать? Напиши /today чтобы увидеть план на сегодня!
"""
    await update.message.reply_text(welcome_message, parse_mode='Markdown')


@owner_only
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help"""
    help_text = """
📖 **Справка по командам**

**📚 Обучение:**
/today — Цель и задачи на сегодня
/progress — Прогресс по всем навыкам
/skills — Список всех 50 навыков
/recommend — Получить рекомендацию
/sync — Синхронизация с Notion

**🔥 Продуктивность:**
/streak — Твоя серия практики
/deepblock — Блок глубокой практики (45 мин)
/interleave — Чередующаяся практика (микс навыков)
/freeze — Использовать заморозку серии

**🙏 Дневник благодарности:**
/gratitude — Записать благодарность
/review — Недельный обзор с AI-анализом

**⚙️ Система:**
/modules — Список активных модулей
/help — Эта справка

**🤖 AI-ассистент:**
Просто напиши текст или отправь голосовое сообщение!

**⏰ Расписание напоминаний (Тбилиси):**
🌅 09:00 — Утренняя благодарность
⚡ 18:00 — Защита серии (loss aversion)
🧠 20:00 — Блок глубокой практики
🌙 23:00 — Вечерняя благодарность
📊 Пятница 19:00 — Недельный обзор
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')


@owner_only
async def modules_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает список модулей"""
    modules = module_manager.get_all_modules()
    
    if not modules:
        await update.message.reply_text("Модули не загружены")
        return
    
    # Русские названия модулей
    module_names_ru = {
        "notion": "Notion интеграция",
        "learning": "Планирование обучения",
        "gratitude": "Дневник благодарности",
        "voice": "Голосовые сообщения",
        "ai_assistant": "AI-ассистент",
        "ideas": "Банк идей",
        "productivity": "Продуктивность"
    }
    
    module_desc_ru = {
        "notion": "Синхронизация данных с Notion",
        "learning": "Умные рекомендации по обучению",
        "gratitude": "Ведение дневника благодарности",
        "voice": "Распознавание голосовых сообщений",
        "ai_assistant": "Естественное общение с AI",
        "ideas": "Сохранение и управление идеями",
        "productivity": "Серии, чередование, глубокая практика"
    }
    
    text = "📦 **Модули бота:**\n\n"
    for module in modules:
        status = "✅" if module.enabled else "❌"
        name = module_names_ru.get(module.name, module.name)
        desc = module_desc_ru.get(module.name, module.description)
        text += f"{status} **{name}**\n   {desc}\n\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')


async def post_init(application: Application) -> None:
    """Выполняется после инициализации приложения"""
    from telegram import BotCommand
    
    # Устанавливаем команды бота (на русском)
    commands = [
        BotCommand("start", "Запустить бота"),
        BotCommand("today", "Цель на сегодня"),
        BotCommand("progress", "Прогресс по навыкам"),
        BotCommand("skills", "Все 50 навыков"),
        BotCommand("streak", "Серия практики"),
        BotCommand("deepblock", "Блок глубокой практики"),
        BotCommand("interleave", "Чередующаяся практика"),
        BotCommand("freeze", "Заморозка серии"),
        BotCommand("gratitude", "Записать благодарность"),
        BotCommand("review", "Недельный обзор"),
        BotCommand("sync", "Синхронизация с Notion"),
        BotCommand("help", "Справка по командам"),
    ]
    await application.bot.set_my_commands(commands)
    
    # Запускаем все модули
    await module_manager.startup_all()
    
    # Подключаем голосовой модуль к AI-ассистенту
    voice_module.set_ai_assistant(ai_assistant_module)
    
    # Подключаем AI-ассистент к модулю идей
    ai_assistant_module.set_ideas_module(ideas_module)
    
    # Настраиваем сервис напоминаний
    reminder_service.setup(application)
    
    # Запускаем планировщик
    scheduler.start()
    
    logger.info("Бот успешно инициализирован с AI-ассистентом")


async def shutdown(application: Application) -> None:
    """Выполняется при остановке бота"""
    await module_manager.shutdown_all()
    scheduler.stop()
    logger.info("Бот остановлен")


def main() -> None:
    """Главная функция запуска бота"""
    # Создаём директорию для данных
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # Регистрируем модули
    module_manager.register_module(notion_module)
    module_manager.register_module(learning_module)
    module_manager.register_module(gratitude_module)
    module_manager.register_module(voice_module)
    module_manager.register_module(ai_assistant_module)
    module_manager.register_module(ideas_module)
    module_manager.register_module(productivity_module)
    
    logger.info(f"Зарегистрировано {len(module_manager)} модулей")
    
    # Создаём приложение
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(shutdown)
        .build()
    )
    
    # Регистрируем базовые обработчики
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("modules", modules_command))
    
    # Регистрируем модули в приложении
    module_manager.set_application(application)
    
    # Запускаем бота
    logger.info("Запуск бота...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
