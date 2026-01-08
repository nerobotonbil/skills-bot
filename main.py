#!/usr/bin/env python3
"""
Learning Bot - Telegram bot for learning and self-development

Modules:
- Notion: integration with Notion for data storage
- Learning: learning planning and progress tracking
- Gratitude: gratitude journal
- Voice: voice message processing
- AI Assistant: AI helper for natural language control

Run:
    python main.py
"""
import sys
import logging
from pathlib import Path

# Add root directory to path
sys.path.insert(0, str(Path(__file__).parent))

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config.settings import TELEGRAM_BOT_TOKEN, LOG_LEVEL, DATA_DIR
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


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for /start command"""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    # Save chat_id for reminders
    context.bot_data['user_chat_id'] = chat_id
    reminder_service.set_chat_id(chat_id)
    
    welcome_message = f"""
🎯 Hey, {user.first_name}!

I'm your personal AI assistant for learning and self-development.

**What I can do:**
📚 Plan daily learning (lectures, videos, practice)
🙏 Keep a gratitude journal
🎤 Accept voice messages
🤖 Answer questions via AI

**Commands:**
/today - Today's goal
/progress - Your skill progress
/gratitude - Write gratitude entry
/review - Review gratitude entries
/sync - Sync with Notion
/help - Help with commands

**Reminders (Tbilisi time):**
🌅 Morning at 9:00 AM - daily goal + gratitude
🌙 Evening at 9:00 PM - summary + gratitude

**AI Assistant:**
Just text me or send a voice message - I'll understand and help!

Ready to start? Type /today to see today's plan!
"""
    await update.message.reply_text(welcome_message, parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for /help command"""
    help_text = """
📖 **Command Reference**

**Learning:**
/today - Today's goal and tasks
/progress - Progress on all skills
/sync - Sync with Notion

**🔥 Productivity (NEW!):**
/streak - Your practice streak
/deepblock - Deep practice block (45 min)
/interleave - Interleaved skill practice
/freeze - Use streak freeze

**Gratitude Journal:**
/gratitude - Write gratitude entry
/review - Review entries

**AI Assistant:**
Just text or send voice - I'll understand!

**Modules:**
/modules - List of active modules

**Reminders (Tbilisi time):**
🌅 09:00 — Morning gratitude
⚡ 18:00 — Streak reminder
🧠 20:00 — Deep practice block
🌙 23:00 — Evening gratitude
📊 Friday 19:00 — Weekly review
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def modules_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows list of modules"""
    modules = module_manager.get_all_modules()
    
    if not modules:
        await update.message.reply_text("No modules loaded")
        return
    
    text = "📦 **Bot Modules:**\n\n"
    for module in modules:
        status = "✅" if module.enabled else "❌"
        text += f"{status} **{module.name}**\n   {module.description}\n\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')


async def post_init(application: Application) -> None:
    """Executed after application initialization"""
    from telegram import BotCommand
    
    # Set bot commands
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("today", "Today's goal"),
        BotCommand("progress", "Skill progress"),
        BotCommand("streak", "Your practice streak"),
        BotCommand("deepblock", "Deep practice block"),
        BotCommand("interleave", "Interleaved practice"),
        BotCommand("gratitude", "Write gratitude entry"),
        BotCommand("review", "Review gratitude entries"),
        BotCommand("sync", "Sync with Notion"),
        BotCommand("help", "Command reference"),
        BotCommand("modules", "List of modules"),
    ]
    await application.bot.set_my_commands(commands)
    
    # Start all modules
    await module_manager.startup_all()
    
    # Connect voice module to AI assistant
    voice_module.set_ai_assistant(ai_assistant_module)
    
    # Connect AI assistant to ideas module
    ai_assistant_module.set_ideas_module(ideas_module)
    
    # Setup reminder service
    reminder_service.setup(application)
    
    # Start scheduler
    scheduler.start()
    
    logger.info("Bot initialized successfully with AI Assistant")


async def shutdown(application: Application) -> None:
    """Executed on bot shutdown"""
    await module_manager.shutdown_all()
    scheduler.stop()
    logger.info("Bot shutdown complete")


def main() -> None:
    """Main function to start the bot"""
    # Create data directory
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # Register modules
    module_manager.register_module(notion_module)
    module_manager.register_module(learning_module)
    module_manager.register_module(gratitude_module)
    module_manager.register_module(voice_module)
    module_manager.register_module(ai_assistant_module)
    module_manager.register_module(ideas_module)
    module_manager.register_module(productivity_module)
    
    logger.info(f"Registered {len(module_manager)} modules")
    
    # Create application
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(shutdown)
        .build()
    )
    
    # Register base handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("modules", modules_command))
    
    # Register modules in application
    module_manager.set_application(application)
    
    # Start bot
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
