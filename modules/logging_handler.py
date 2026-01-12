"""
Logging handler that sends error logs to Telegram
"""
import logging
import traceback
from datetime import datetime
from typing import Optional
from collections import deque

# Store recent logs in memory
recent_logs = deque(maxlen=50)


class TelegramLoggingHandler(logging.Handler):
    """
    Custom logging handler that sends error logs to Telegram.
    """
    
    def __init__(self, bot=None, chat_id=None):
        super().__init__()
        self.bot = bot
        self.chat_id = chat_id
        self.setLevel(logging.ERROR)  # Only send ERROR and above
    
    def set_bot(self, bot, chat_id):
        """Set bot and chat_id after initialization"""
        self.bot = bot
        self.chat_id = chat_id
    
    def emit(self, record):
        """Send log record to Telegram"""
        try:
            # Format log message
            log_entry = self.format(record)
            
            # Store in recent logs
            recent_logs.append({
                'timestamp': datetime.now().isoformat(),
                'level': record.levelname,
                'message': log_entry
            })
            
            # Send to Telegram if bot is available
            if self.bot and self.chat_id:
                # Format for Telegram
                message = f"🚨 **ERROR LOG**\n\n"
                message += f"**Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                message += f"**Module:** {record.name}\n"
                message += f"**Level:** {record.levelname}\n\n"
                message += f"**Message:**\n```\n{record.getMessage()}\n```\n"
                
                # Add traceback if available
                if record.exc_info:
                    tb = ''.join(traceback.format_exception(*record.exc_info))
                    # Truncate if too long
                    if len(tb) > 500:
                        tb = tb[:500] + "\n... (truncated)"
                    message += f"\n**Traceback:**\n```\n{tb}\n```"
                
                # Truncate message if too long for Telegram
                if len(message) > 4000:
                    message = message[:4000] + "\n... (truncated)"
                
                # Send asynchronously
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(
                            self.bot.send_message(
                                chat_id=self.chat_id,
                                text=message,
                                parse_mode='Markdown'
                            )
                        )
                    else:
                        loop.run_until_complete(
                            self.bot.send_message(
                                chat_id=self.chat_id,
                                text=message,
                                parse_mode='Markdown'
                            )
                        )
                except Exception as e:
                    # Avoid infinite loop - don't log this error
                    print(f"Failed to send log to Telegram: {e}")
                    
        except Exception as e:
            # Avoid infinite loop
            print(f"Error in TelegramLoggingHandler: {e}")


def get_recent_logs(count: int = 10) -> str:
    """Get recent logs as formatted string"""
    if not recent_logs:
        return "No recent logs available."
    
    logs = list(recent_logs)[-count:]
    
    message = f"📋 **Recent Logs ({len(logs)} entries)**\n\n"
    
    for log in logs:
        timestamp = log['timestamp'].split('T')[1].split('.')[0]  # Extract time
        level_emoji = {
            'ERROR': '🔴',
            'WARNING': '⚠️',
            'INFO': 'ℹ️',
            'DEBUG': '🔍'
        }.get(log['level'], '📝')
        
        message += f"{level_emoji} **{timestamp}** [{log['level']}]\n"
        msg = log['message']
        if len(msg) > 200:
            msg = msg[:200] + "..."
        message += f"```\n{msg}\n```\n\n"
    
    return message


# Global handler instance
telegram_handler = TelegramLoggingHandler()
