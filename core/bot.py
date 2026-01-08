"""
Основной класс Telegram бота
"""
import logging
from typing import Optional
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)

from config.settings import TELEGRAM_BOT_TOKEN, LOG_LEVEL
from core.module_manager import module_manager
from core.scheduler import scheduler

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, LOG_LEVEL)
)
logger = logging.getLogger(__name__)


class LearningBot:
    """
    Основной класс бота для обучения и саморазвития.
    """
    
    def __init__(self):
        self.app: Optional[Application] = None
        self.user_chat_id: Optional[int] = None  # ID чата пользователя для напоминаний
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /start"""
        user = update.effective_user
        self.user_chat_id = update.effective_chat.id
        
        # Сохраняем chat_id в контексте бота для напоминаний
        context.bot_data['user_chat_id'] = self.user_chat_id
        
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
/help - Справка по командам

Напоминания будут приходить:
🌅 Утром в 9:00 - цель на день + благодарность
🌙 Вечером в 21:00 - итоги + благодарность

Готов начать? Напиши /today чтобы увидеть план на сегодня!
"""
        await update.message.reply_text(welcome_message, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /help"""
        help_text = """
📖 **Справка по командам**

**Обучение:**
/today - Цель на сегодня
/week - План на неделю
/progress - Прогресс по всем навыкам
/done - Отметить задачу выполненной
/skip - Пропустить задачу

**Дневник благодарности:**
/gratitude - Записать благодарность
/review - Обзор записей

**Настройки:**
/settings - Настройки бота
/modules - Список модулей

**Голосовые сообщения:**
Просто отправь голосовое сообщение, и я его обработаю!
"""
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def modules_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    
    async def unknown_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик неизвестных команд"""
        await update.message.reply_text(
            "🤔 Не понимаю эту команду. Напиши /help для списка команд."
        )
    
    async def post_init(self, application: Application) -> None:
        """Выполняется после инициализации приложения"""
        # Устанавливаем команды бота
        commands = [
            BotCommand("start", "Начать работу с ботом"),
            BotCommand("today", "Цель на сегодня"),
            BotCommand("progress", "Прогресс по навыкам"),
            BotCommand("gratitude", "Записать благодарность"),
            BotCommand("help", "Справка по командам"),
            BotCommand("modules", "Список модулей"),
        ]
        await application.bot.set_my_commands(commands)
        
        # Запускаем все модули
        await module_manager.startup_all()
        
        # Запускаем планировщик
        scheduler.start()
        
        logger.info("Bot initialized successfully")
    
    async def shutdown(self, application: Application) -> None:
        """Выполняется при остановке бота"""
        await module_manager.shutdown_all()
        scheduler.stop()
        logger.info("Bot shutdown complete")
    
    def setup(self) -> Application:
        """Настраивает и возвращает приложение"""
        # Создаём приложение
        self.app = (
            Application.builder()
            .token(TELEGRAM_BOT_TOKEN)
            .post_init(self.post_init)
            .post_shutdown(self.shutdown)
            .build()
        )
        
        # Регистрируем базовые обработчики
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("modules", self.modules_command))
        
        # Регистрируем модули
        module_manager.set_application(self.app)
        
        # Обработчик неизвестных команд (должен быть последним)
        self.app.add_handler(MessageHandler(
            filters.COMMAND,
            self.unknown_command
        ))
        
        return self.app
    
    def run(self) -> None:
        """Запускает бота"""
        app = self.setup()
        logger.info("Starting bot...")
        app.run_polling(allowed_updates=Update.ALL_TYPES)


# Создаём экземпляр бота
bot = LearningBot()
