"""
Bot Configuration
"""
import os
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

# Tokens from environment variables (MUST be configured on server!)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
NOTION_API_TOKEN = os.getenv("NOTION_API_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Notion Database IDs
NOTION_SKILLS_DATABASE_ID = os.getenv("NOTION_SKILLS_DATABASE_ID", "efc48aa99cde4bcb8fab8e3b0ef625c0")
NOTION_SKILLS_DATA_SOURCE = os.getenv("NOTION_SKILLS_DATA_SOURCE", "collection://1f4e8789-6dd5-400f-b538-ce1c1bcc6487")

# Notion Gratitude Journal (will be created automatically)
NOTION_GRATITUDE_DATABASE_ID = os.getenv("NOTION_GRATITUDE_DATABASE_ID", None)

# Maximum values for progress bars
MAX_VALUES = {
    "Lectures": 10,        # Lectures (theory)
    "Practice hours": 20,  # Practice (hours)
    "Videos": 5,           # Video stories (FBI, doctors, etc.)
    "Films ": 3,           # Films (with trailing space as in Notion)
    "VC Lectures": 5       # VC lectures (venture capitalist advice)
}

# Content type descriptions
CONTENT_DESCRIPTIONS = {
    "Lectures": "📖 Lectures - theoretical materials",
    "Practice hours": "💪 Practice - applying the skill in practice",
    "Videos": "🎬 Videos - stories from professionals (FBI, doctors, etc.)",
    "Films ": "🎥 Films - feature films on the topic",
    "VC Lectures": "💼 VC Lectures - advice from venture capitalists"
}

# Emoji for content types
CONTENT_EMOJI = {
    "Lectures": "📖",
    "Practice hours": "💪",
    "Videos": "🎬",
    "Films ": "🎥",
    "VC Lectures": "💼"
}

# English names for content types (for recommendations)
CONTENT_NAMES_EN = {
    "Lectures": "lecture",
    "Practice hours": "practice (1 hour)",
    "Videos": "video",
    "Films ": "film",
    "VC Lectures": "VC lecture"
}

# Keep Russian names for backward compatibility
CONTENT_NAMES_RU = CONTENT_NAMES_EN

# Timezone - Tbilisi (GMT+4)
TIMEZONE = os.getenv("TIMEZONE", "Asia/Tbilisi")

# Evening notification at 20:00 - psychologically right time after work
EVENING_TASK_TIME = "20:00"

# Morning reminder (gratitude)
MORNING_REMINDER_TIME = "09:00"

# Evening reminder (summary + gratitude)
EVENING_REMINDER_TIME = "21:00"

# Voice message settings
VOICE_TRANSCRIPTION_METHOD = "openai"

# SQLite database
SQLITE_DB_PATH = DATA_DIR / "bot.db"

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = DATA_DIR / "bot.log"
