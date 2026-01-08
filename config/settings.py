"""
Конфигурация бота
"""
import os
from pathlib import Path

# Базовые пути
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

# Токены из переменных окружения (ОБЯЗАТЕЛЬНО настроить на сервере!)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
NOTION_API_TOKEN = os.getenv("NOTION_API_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Notion Database IDs
NOTION_SKILLS_DATABASE_ID = os.getenv("NOTION_SKILLS_DATABASE_ID", "efc48aa99cde4bcb8fab8e3b0ef625c0")
NOTION_SKILLS_DATA_SOURCE = os.getenv("NOTION_SKILLS_DATA_SOURCE", "collection://1f4e8789-6dd5-400f-b538-ce1c1bcc6487")

# Notion Gratitude Journal (будет создана автоматически)
NOTION_GRATITUDE_DATABASE_ID = os.getenv("NOTION_GRATITUDE_DATABASE_ID", None)

# Максимальные значения для прогресс-баров
MAX_VALUES = {
    "Lectures": 10,        # Лекции (теория)
    "Practice hours": 20,  # Практика (часы)
    "Videos": 5,          # Видео-истории (FBI, доктора и т.д.)
    "Films ": 3,           # Фильмы (с пробелом в конце как в Notion)
    "VC Lectures": 5       # VC лекции (советы от венчурных капиталистов)
}

# Описания типов контента
CONTENT_DESCRIPTIONS = {
    "Lectures": "📖 Лекции - теоретические материалы",
    "Practice hours": "💪 Практика - применение навыка на практике",
    "Videos": "🎬 Видео - истории от профессионалов (FBI, доктора и др.)",
    "Films ": "🎥 Фильмы - художественные фильмы по теме",
    "VC Lectures": "💼 VC Лекции - советы от венчурных капиталистов"
}

# Эмодзи для типов контента
CONTENT_EMOJI = {
    "Lectures": "📖",
    "Practice hours": "💪",
    "Videos": "🎬",
    "Films ": "🎥",
    "VC Lectures": "💼"
}

# Русские названия типов контента
CONTENT_NAMES_RU = {
    "Lectures": "лекцию",
    "Practice hours": "практику (1 час)",
    "Videos": "видео",
    "Films ": "фильм",
    "VC Lectures": "VC лекцию"
}

# Часовой пояс - Тбилиси (GMT+4)
TIMEZONE = os.getenv("TIMEZONE", "Asia/Tbilisi")

# Вечернее уведомление в 20:00 - психологически правильное время после работы
EVENING_TASK_TIME = "20:00"

# Утреннее напоминание (благодарность)
MORNING_REMINDER_TIME = "09:00"

# Вечернее напоминание (итоги + благодарность)
EVENING_REMINDER_TIME = "21:00"

# Настройки голосовых сообщений
VOICE_TRANSCRIPTION_METHOD = "openai"

# База данных SQLite
SQLITE_DB_PATH = DATA_DIR / "bot.db"

# Логирование
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = DATA_DIR / "bot.log"
