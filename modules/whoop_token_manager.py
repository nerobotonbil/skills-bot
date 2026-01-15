"""
WHOOP Token Manager
Handles automatic token refresh using refresh_token
"""

import os
import logging
import requests
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import threading
import time

logger = logging.getLogger(__name__)

# WHOOP OAuth Configuration
TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
WHOOP_CLIENT_ID = os.getenv("WHOOP_CLIENT_ID")
WHOOP_CLIENT_SECRET = os.getenv("WHOOP_CLIENT_SECRET")
WHOOP_REFRESH_TOKEN = os.getenv("WHOOP_REFRESH_TOKEN")

# Token storage
_current_access_token = os.getenv("WHOOP_ACCESS_TOKEN")
_current_refresh_token = WHOOP_REFRESH_TOKEN
_token_expires_at = None
_token_lock = threading.Lock()


class WhoopTokenManager:
    """Manages WHOOP access token with automatic refresh"""
    
    def __init__(self):
        self.client_id = WHOOP_CLIENT_ID
        self.client_secret = WHOOP_CLIENT_SECRET
        self.refresh_token = WHOOP_REFRESH_TOKEN
        self.access_token = _current_access_token
        
        # Initialize expiration time
        # Assume current token expires in 1 hour if we don't know
        if self.access_token:
            self.expires_at = datetime.now() + timedelta(hours=1)
            logger.info(f"⏰ Token expiration initialized to: {self.expires_at.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            self.expires_at = None
        
        self.lock = threading.Lock()
        
        # Check if credentials are available
        if not all([self.client_id, self.client_secret, self.refresh_token]):
            logger.warning("⚠️ WHOOP token refresh credentials not fully configured")
            logger.warning(f"  Client ID: {'✓' if self.client_id else '✗'}")
            logger.warning(f"  Client Secret: {'✓' if self.client_secret else '✗'}")
            logger.warning(f"  Refresh Token: {'✓' if self.refresh_token else '✗'}")
    
    def get_access_token(self) -> Optional[str]:
        """
        Get current access token, refreshing if needed
        
        Returns:
            Current valid access token or None if unavailable
        """
        with self.lock:
            # If token is about to expire (within 5 minutes), refresh it
            if self.expires_at and datetime.now() >= self.expires_at - timedelta(minutes=5):
                logger.info("🔄 Access token expiring soon, refreshing...")
                self._refresh_token()
            
            return self.access_token
    
    def _refresh_token(self) -> bool:
        """
        Refresh the access token using refresh token
        
        Returns:
            True if refresh successful, False otherwise
        """
        if not all([self.client_id, self.client_secret, self.refresh_token]):
            logger.error("❌ Cannot refresh token: missing credentials")
            return False
        
        try:
            logger.info("🔄 Refreshing WHOOP access token...")
            
            token_data = {
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret
            }
            
            response = requests.post(TOKEN_URL, data=token_data, timeout=10)
            
            if response.status_code == 200:
                token_info = response.json()
                
                # Update tokens
                self.access_token = token_info.get('access_token')
                new_refresh_token = token_info.get('refresh_token')
                expires_in = token_info.get('expires_in', 3600)
                
                # Update refresh token if a new one was provided
                if new_refresh_token:
                    self.refresh_token = new_refresh_token
                    logger.info("🔄 Refresh token updated")
                
                # Calculate expiration time
                self.expires_at = datetime.now() + timedelta(seconds=expires_in)
                
                logger.info(f"✅ Access token refreshed successfully")
                logger.info(f"⏰ New token expires at: {self.expires_at.strftime('%Y-%m-%d %H:%M:%S')}")
                
                # Update global token
                global _current_access_token, _current_refresh_token
                _current_access_token = self.access_token
                _current_refresh_token = self.refresh_token
                
                return True
            else:
                logger.error(f"❌ Token refresh failed: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return False
        
        except Exception as e:
            logger.error(f"❌ Error refreshing token: {e}")
            return False
    
    def force_refresh(self) -> bool:
        """Force immediate token refresh"""
        with self.lock:
            return self._refresh_token()


# Global token manager instance
_token_manager = None


def get_token_manager() -> Optional[WhoopTokenManager]:
    """
    Get global token manager instance
    
    Returns:
        WhoopTokenManager instance or None if not configured
    """
    global _token_manager
    
    if _token_manager is None:
        _token_manager = WhoopTokenManager()
    
    return _token_manager


def get_current_access_token() -> Optional[str]:
    """
    Get current valid access token
    
    Returns:
        Current access token or None if unavailable
    """
    manager = get_token_manager()
    if manager:
        return manager.get_access_token()
    return _current_access_token
