"""
Webhook server for receiving Apple Health data from iOS Shortcuts
Runs alongside the Telegram bot
"""

import logging
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
import uvicorn
import asyncio
from telegram import Bot

from config.settings import TELEGRAM_BOT_TOKEN, ALLOWED_USER_ID
from modules.apple_health.module import apple_health_module

logger = logging.getLogger(__name__)

app = FastAPI(title="Apple Health Webhook")


class HealthData(BaseModel):
    """Health data from iOS Shortcuts"""
    sleep_score: Optional[int] = None
    steps: Optional[int] = None
    heart_rate_avg: Optional[int] = None
    heart_rate_resting: Optional[int] = None
    calories: Optional[int] = None
    active_energy: Optional[int] = None
    exercise_minutes: Optional[int] = None
    date: Optional[str] = None
    secret: str  # Simple authentication


@app.post("/health")
async def receive_health_data(data: HealthData):
    """
    Endpoint for receiving Apple Health data from iOS Shortcuts
    
    Example request:
    POST /health
    {
        "sleep_score": 71,
        "steps": 2085,
        "heart_rate_resting": 65,
        "calories": 451,
        "exercise_minutes": 58,
        "date": "2026-01-23",
        "secret": "your_secret_key"
    }
    """
    try:
        # Simple authentication
        if data.secret != "apple_health_2026":
            raise HTTPException(status_code=401, detail="Invalid secret")
        
        # Store data
        health_dict = data.dict()
        del health_dict['secret']  # Remove secret from stored data
        
        message = apple_health_module.store_health_data(health_dict)
        
        # Send notification to Telegram
        try:
            bot = Bot(token=TELEGRAM_BOT_TOKEN)
            await bot.send_message(
                chat_id=ALLOWED_USER_ID,
                text=message
            )
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
        
        return {"status": "success", "message": "Health data received"}
        
    except Exception as e:
        logger.error(f"Error processing health data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "ok", "service": "Apple Health Webhook"}


def run_webhook_server(port: int = 8000):
    """Run the webhook server"""
    logger.info(f"Starting Apple Health webhook server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    run_webhook_server()
