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
from modules.contacts.module import contacts_module
from modules.reminders import reminder_service
from modules.logging_handler import telegram_handler, get_recent_logs

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, LOG_LEVEL),
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(DATA_DIR / "bot.log"),
        telegram_handler  # Send errors to Telegram
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
    
    # Настраиваем Telegram logging handler
    telegram_handler.set_bot(context.bot, chat_id)
    logger.info("Telegram logging handler configured for user")
    
    welcome_message = """🎯 **Привет, Andrew!**

Я AI-ассистент для обучения и саморазвития.

**Что я умею:**
✅ Планирую задачи на день
✅ Отслеживаю серии практики
✅ Веду дневник благодарности
✅ Учитываю твоё здоровье (WHOOP)
✅ Отвечаю на вопросы голосом

**📌 Главные команды:**

/today - план на сегодня
/streak - твоя серия практики
/gratitude - записать благодарность

**🔧 Дополнительно:**

/progress - прогресс по навыкам
/freeze - заморозить серию
/contact - добавить контакт
/help - полный список команд

**⏰ Напоминания:**
09:00 - утренняя благодарность
20:00 - задача на вечер + WHOOP
23:00 - вечерняя благодарность

**💬 Как пользоваться:**
Отправь голосовое или текст - я отвечу!

Начни с /today 🚀
"""""
    await update.message.reply_text(welcome_message, parse_mode='Markdown')


@owner_only
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help"""
    help_text = """📚 **Полный список команд**

**🎯 Обучение:**
/today - план на сегодня
/progress - прогресс по навыкам
/skills - список 50 навыков

**🔥 Серия практики:**
/streak - твоя серия
/freeze - заморозить серию

**🙏 Благодарность:**
/gratitude - записать
/weekly_gratitude - недельный рекап
/review - месячный обзор

**👥 Контакты:**
/contact - добавить
/contacts - список

**🔧 Система:**
/sync - синхронизация с Notion
/logs - последние логи

**⏰ Напоминания:**
09:00 - утренняя благодарность
20:00 - задача на вечер + WHOOP
23:00 - вечерняя благодарность

**💬 AI-ассистент:**
Отправь голосовое или текст - я отвечу!
Учитываю WHOOP данные для вопросов о здоровье.
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')


@owner_only
async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает chat_id пользователя для настройки Railway"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    message = (
        f"🆔 **Твои ID:**\n\n"
        f"Chat ID: `{chat_id}`\n"
        f"User ID: `{user_id}`\n\n"
        f"**Для настройки напоминаний в Railway:**\n"
        f"Добавь переменную окружения:\n"
        f"• Имя: `TELEGRAM_CHAT_ID`\n"
        f"• Значение: `{chat_id}`"
    )
    
    await update.message.reply_text(message, parse_mode='Markdown')


@owner_only
async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает последние логи"""
    try:
        count = 10
        # Проверяем, есть ли аргумент (количество логов)
        if context.args and len(context.args) > 0:
            try:
                count = int(context.args[0])
                count = min(count, 50)  # Максимум 50
            except ValueError:
                pass
        
        logs_text = get_recent_logs(count)
        await update.message.reply_text(logs_text, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка получения логов: {e}")


@owner_only
async def modules_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает список модулей и их статус"""
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


@owner_only
async def init_streak_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Инициализирует стрик с 3-дневной историей"""
    await update.message.reply_text("🔄 Инициализирую стрик с 3-дневной историей...")
    
    try:
        import subprocess
        import sys
        
        # Run init_streak.py script
        result = subprocess.run(
            [sys.executable, "init_streak.py"],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            # Success
            await update.message.reply_text(
                f"✅ **Стрик успешно инициализирован!**\n\n"
                f"Текущий стрик: **3 дня**\n\n"
                f"Теперь система будет правильно отслеживать твой ежедневный прогресс.",
                parse_mode='Markdown'
            )
            logger.info("Streak initialized successfully")
        else:
            # Error
            error_msg = result.stderr or result.stdout or "Unknown error"
            await update.message.reply_text(
                f"❌ Ошибка инициализации стрика:\n\n```\n{error_msg[:500]}\n```",
                parse_mode='Markdown'
            )
            logger.error(f"Streak initialization failed: {error_msg}")
    
    except Exception as e:
        await update.message.reply_text(
            f"❌ Ошибка: {str(e)}",
            parse_mode='Markdown'
        )
        logger.error(f"Error in init_streak_command: {e}")


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
        BotCommand("freeze", "Заморозка серии"),
        BotCommand("gratitude", "Записать благодарность"),
        BotCommand("weekly_gratitude", "Недельный рекап"),
        BotCommand("review", "Месячный обзор"),
        BotCommand("contact", "Добавить контакт"),
        BotCommand("contacts", "Список контактов"),
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
    
    # Подключаем модуль благодарности к AI-ассистенту (для передачи не-благодарностей)
    gratitude_module.set_ai_assistant(ai_assistant_module)
    
    # Подключаем AI-ассистент к модулю благодарности (для голосовых сообщений)
    ai_assistant_module.set_gratitude_module(gratitude_module)
    
    # Подключаем AI-ассистент к модулю контактов (для голосовых сообщений)
    ai_assistant_module.set_contacts_module(contacts_module)
    
    # Настраиваем сервис напоминаний
    reminder_service.setup(application)
    
    # Telegram logging handler будет настроен при /start
    
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
    # ВАЖНО: ai_assistant должен быть ПОСЛЕДНИМ, чтобы обрабатывать
    # все сообщения, которые не обработали другие модули
    module_manager.register_module(notion_module)
    module_manager.register_module(learning_module)
    module_manager.register_module(gratitude_module)
    module_manager.register_module(voice_module)
    module_manager.register_module(ideas_module)
    module_manager.register_module(productivity_module)
    module_manager.register_module(contacts_module)
    module_manager.register_module(ai_assistant_module)  # ПОСЛЕДНИМ!
    
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
    application.add_handler(CommandHandler("myid", myid_command))
    application.add_handler(CommandHandler("logs", logs_command))
    application.add_handler(CommandHandler("modules", modules_command))
    application.add_handler(CommandHandler("init_streak", init_streak_command))
    
    # Регистрируем модули в приложении
    module_manager.set_application(application)
    
    # Запускаем бота
    logger.info("Запуск бота...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
