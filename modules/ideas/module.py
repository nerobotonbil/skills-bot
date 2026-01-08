"""
Ideas recording module for Notion
"""
import logging
import os
import httpx
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes, BaseHandler, MessageHandler, filters

from modules.base import BaseModule

logger = logging.getLogger(__name__)


class IdeasModule(BaseModule):
    """
    Module for recording ideas to Notion.
    Works through AI assistant, which determines intent to save an idea.
    """
    
    def __init__(self):
        super().__init__(
            name="ideas",
            description="Recording ideas and notes to Notion"
        )
        self.notion_token = os.getenv("NOTION_API_TOKEN")
        # Use database_id, not data_source_id
        self.database_id = "2e28db7c936780b28d66e45ab2e6f7e6"
        self.notion_api_url = "https://api.notion.com/v1/pages"
        
        # Log initialization status
        if self.notion_token:
            logger.info(f"Ideas module initialized with token: {self.notion_token[:10]}...")
        else:
            logger.warning("Ideas module: NOTION_API_TOKEN not set!")
        
    def get_handlers(self):
        """This module has no direct handlers - works through AI"""
        return []
    
    async def save_idea(self, idea_text: str, user_id: int = None) -> dict:
        """
        Saves idea to Notion.
        
        Args:
            idea_text: Idea text (already processed by AI)
            user_id: Telegram user ID
            
        Returns:
            dict with result: {"success": bool, "message": str, "url": str}
        """
        # Re-read token in case it was set later
        token = os.getenv("NOTION_API_TOKEN")
        if not token:
            logger.error("NOTION_API_TOKEN not set in environment")
            return {
                "success": False,
                "message": "Notion not configured (no token)",
                "url": None
            }
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        # Format data for page creation
        data = {
            "parent": {
                "database_id": self.database_id
            },
            "properties": {
                "Idea": {
                    "title": [
                        {
                            "text": {
                                "content": idea_text[:2000]  # Notion limit
                            }
                        }
                    ]
                }
            }
        }
        
        logger.info(f"Saving idea to Notion: {idea_text[:50]}...")
        logger.info(f"Database ID: {self.database_id}")
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.notion_api_url,
                    headers=headers,
                    json=data,
                    timeout=30.0
                )
                
                logger.info(f"Notion API response: {response.status_code}")
                
                if response.status_code == 200:
                    result = response.json()
                    page_url = result.get("url", "")
                    logger.info(f"Idea saved successfully: {page_url}")
                    return {
                        "success": True,
                        "message": "Idea saved to Notion",
                        "url": page_url
                    }
                else:
                    error_text = response.text
                    logger.error(f"Notion API error: {response.status_code} - {error_text}")
                    
                    # Try alternative database_id format
                    if response.status_code == 404:
                        return await self._try_alternative_save(token, idea_text, headers)
                    
                    return {
                        "success": False,
                        "message": f"Notion API error: {response.status_code}",
                        "url": None
                    }
                    
        except Exception as e:
            logger.error(f"Error saving idea to Notion: {e}")
            return {
                "success": False,
                "message": f"Error: {str(e)}",
                "url": None
            }
    
    async def _try_alternative_save(self, token: str, idea_text: str, headers: dict) -> dict:
        """Tries alternative database_id format with dashes"""
        # Try with dashes
        alt_database_id = "2e28db7c-9367-80b2-8d66-e45ab2e6f7e6"
        
        data = {
            "parent": {
                "database_id": alt_database_id
            },
            "properties": {
                "Idea": {
                    "title": [
                        {
                            "text": {
                                "content": idea_text[:2000]
                            }
                        }
                    ]
                }
            }
        }
        
        logger.info(f"Trying alternative database ID: {alt_database_id}")
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.notion_api_url,
                    headers=headers,
                    json=data,
                    timeout=30.0
                )
                
                logger.info(f"Alternative Notion API response: {response.status_code}")
                
                if response.status_code == 200:
                    result = response.json()
                    page_url = result.get("url", "")
                    # Update database_id to working one
                    self.database_id = alt_database_id
                    logger.info(f"Idea saved with alternative ID: {page_url}")
                    return {
                        "success": True,
                        "message": "Idea saved to Notion",
                        "url": page_url
                    }
                else:
                    error_text = response.text
                    logger.error(f"Alternative also failed: {response.status_code} - {error_text}")
                    return {
                        "success": False,
                        "message": f"Notion API error: {response.status_code}",
                        "url": None
                    }
        except Exception as e:
            logger.error(f"Error in alternative save: {e}")
            return {
                "success": False,
                "message": f"Error: {str(e)}",
                "url": None
            }


# Global module instance
ideas_module = IdeasModule()
