#!/usr/bin/env python3
"""
Learning Bot - Telegram бот для обучения и саморазвития

Модули:
- Notion: интеграция с Notion для хранения данных
- Learning: планирование обучения и отслеживание прогресса
- Gratitude: дневник благодарности
- Voice: обработка голосовых сообщений

Запуск:
    python main.py
"""
import sys
import logging
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config.settings import TELEGRAM_BOT_TOKEN, LOG_LEVEL, DATA_DIR
from core.module_manager import module_manager
from core.scheduler import scheduler

# Импортируем модули
from modules.notion.module import notion_module
from modules.learning.module import learning_module
from modules.gratitude.module import gratitude_module
from modules.voice.module import voice_module
from modules.reminders import reminder_service

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, LOG_LEVEL),
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(DATA_DIR / "bot.log")
    ]
)
logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    # Сохраняем chat_id для напоминаний
    context.bot_data['user_chat_id'] = chat_id
    reminder_service.set_chat_id(chat_id)
    
    welcome_message = f"""
🎯 Привет, {user.first_name}!

Я твой персональный помощник для обучения и саморазвития.

**Что я умею:**
📚 Планировать ежедневное обучение (лекции, видео, практика)
🙏 Вести дневник благодарности
🎤 Принимать голосовые сообщения

**Команды:**
/today - Цель на сегодня
/progress - Твой прогресс по навыкам
/gratitude - Записать благодарность
/review - Обзор записей благодарности
/sync - Синхронизация с Notion
/help - Справка по командам

**Напоминания:**
🌅 Утром в 9:00 - цель на день + благодарность
🌙 Вечером в 21:00 - итоги + благодарность

Готов начать? Напиши /today чтобы увидеть план на сегодня!
"""
    await update.message.reply_text(welcome_message, parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help"""
    help_text = """
📖 **Справка по командам**

**Обучение:**
/today - Цель и задачи на сегодня
/week - План на неделю
/progress - Прогресс по всем навыкам
/sync - Синхронизация с Notion

**Дневник благодарности:**
/gratitude - Записать благодарность
/review - Обзор записей

**Голосовые сообщения:**
Просто отправь голосовое сообщение, и я его обработаю!

**Модули:**
/modules - Список активных модулей

**Как работают напоминания:**
Каждое утро в 9:00 я пришлю тебе цель на день и попрошу записать благодарность.
Каждый вечер в 21:00 - итоги дня и вечернюю благодарность.

Ты можешь отвечать текстом или голосовым сообщением!
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def modules_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает список модулей"""
    modules = module_manager.get_all_modules()
    
    if not modules:
        await update.message.reply_text("Модули не загружены")
        return
    
    text = "📦 **Модули бота:**\n\n"
    for module in modules:
        status = "✅" if module.enabled else "❌"
        text += f"{status} **{module.name}**\n   {module.description}\n\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')


async def post_init(application: Application) -> None:
    """Выполняется после инициализации приложения"""
    from telegram import BotCommand
    
    # Устанавливаем команды бота
    commands = [
        BotCommand("start", "Начать работу с ботом"),
        BotCommand("today", "Цель на сегодня"),
        BotCommand("progress", "Прогресс по навыкам"),
        BotCommand("gratitude", "Записать благодарность"),
        BotCommand("review", "Обзор записей благодарности"),
        BotCommand("sync", "Синхронизация с Notion"),
        BotCommand("help", "Справка по командам"),
        BotCommand("modules", "Список модулей"),
    ]
    await application.bot.set_my_commands(commands)
    
    # Запускаем все модули
    await module_manager.startup_all()
    
    # Настраиваем сервис напоминаний
    reminder_service.setup(application)
    
    # Запускаем планировщик
    scheduler.start()
    
    logger.info("Bot initialized successfully")


async def shutdown(application: Application) -> None:
    """Выполняется при остановке бота"""
    await module_manager.shutdown_all()
    scheduler.stop()
    logger.info("Bot shutdown complete")


def main() -> None:
    """Главная функция запуска бота"""
    # Создаём директорию для данных
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # Регистрируем модули
    module_manager.register_module(notion_module)
    module_manager.register_module(learning_module)
    module_manager.register_module(gratitude_module)
    module_manager.register_module(voice_module)
    
    logger.info(f"Registered {len(module_manager)} modules")
    
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
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
