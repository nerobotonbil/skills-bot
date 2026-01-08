"""
Notion integration module
"""
import logging
from typing import List, Optional
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes, BaseHandler

from modules.base import BaseModule
from modules.notion.client import notion_client

logger = logging.getLogger(__name__)


class NotionModule(BaseModule):
    """
    Module for Notion integration.
    Provides data synchronization and basic commands.
    """
    
    def __init__(self):
        super().__init__(
            name="notion",
            description="Notion integration for data storage"
        )
        self.client = notion_client
        self._all_skills_cache: List[dict] = []  # All skills
        self._active_skills_cache: List[dict] = []  # Only active
        self._cache_updated = None
    
    def get_handlers(self) -> List[BaseHandler]:
        """Returns command handlers"""
        return [
            CommandHandler("sync", self.sync_command),
        ]
    
    async def on_startup(self) -> None:
        """Loads data on startup"""
        await self.refresh_skills_cache()
    
    async def on_shutdown(self) -> None:
        """Closes client on shutdown"""
        await self.client.close()
    
    async def refresh_skills_cache(self) -> List[dict]:
        """Refreshes skills cache"""
        try:
            # Load all skills
            self._all_skills_cache = await self.client.get_all_skills()
            
            # Filter only active (with progress > 0)
            self._active_skills_cache = self.client.filter_active_skills(
                self._all_skills_cache
            )
            
            # Calculate priorities for active skills
            self._active_skills_cache = self.client.calculate_skill_priorities(
                self._active_skills_cache
            )
            
            from datetime import datetime
            self._cache_updated = datetime.now()
            
            logger.info(
                f"Skills cache refreshed: {len(self._all_skills_cache)} total, "
                f"{len(self._active_skills_cache)} active"
            )
            
            return self._active_skills_cache
            
        except Exception as e:
            logger.error(f"Failed to refresh skills cache: {e}")
            return self._active_skills_cache
    
    def get_skills(self) -> List[dict]:
        """Returns cached ACTIVE skills"""
        return self._active_skills_cache
    
    def get_all_skills(self) -> List[dict]:
        """Returns ALL skills (including inactive)"""
        return self._all_skills_cache
    
    def get_active_skills_count(self) -> int:
        """Returns number of active skills"""
        return len(self._active_skills_cache)
    
    def get_total_skills_count(self) -> int:
        """Returns total number of skills"""
        return len(self._all_skills_cache)
    
    def get_skill_by_name(self, name: str) -> Optional[dict]:
        """Finds skill by name among active"""
        for skill in self._active_skills_cache:
            if skill["name"].lower() == name.lower():
                return skill
        return None
    
    async def sync_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Command /sync - sync with Notion"""
        await update.message.reply_text("🔄 Syncing with Notion...")
        
        try:
            skills = await self.refresh_skills_cache()
            
            # Format list of active skills
            active_names = [s["name"] for s in skills]
            active_list = "\n".join([f"• {name}" for name in active_names]) if active_names else "No active skills"
            
            await update.message.reply_text(
                f"✅ Sync complete!\n\n"
                f"Total skills: {self.get_total_skills_count()}\n"
                f"Active (learning): {self.get_active_skills_count()}\n\n"
                f"📚 **Active skills:**\n{active_list}",
                parse_mode='Markdown'
            )
        except Exception as e:
            await update.message.reply_text(
                f"❌ Sync error: {str(e)}"
            )


# Module instance
notion_module = NotionModule()
