"""
Message utilities for Telegram bot
"""
from typing import List


# Telegram message length limit
TELEGRAM_MAX_LENGTH = 4096


def split_long_message(text: str, max_length: int = TELEGRAM_MAX_LENGTH) -> List[str]:
    """
    Split long message into chunks that fit Telegram's length limit.
    
    Args:
        text: The message text to split
        max_length: Maximum length per chunk (default: 4096 for Telegram)
    
    Returns:
        List of message chunks
    """
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    current_chunk = ""
    
    # Split by paragraphs first (double newline)
    paragraphs = text.split('\n\n')
    
    for paragraph in paragraphs:
        # If adding this paragraph would exceed limit
        if len(current_chunk) + len(paragraph) + 2 > max_length:
            # If current chunk is not empty, save it
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            
            # If paragraph itself is too long, split by sentences
            if len(paragraph) > max_length:
                sentences = paragraph.split('. ')
                for sentence in sentences:
                    sentence = sentence.strip()
                    if not sentence:
                        continue
                    
                    # Add period back if it was removed
                    if not sentence.endswith('.'):
                        sentence += '.'
                    
                    # If adding this sentence would exceed limit
                    if len(current_chunk) + len(sentence) + 1 > max_length:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                            current_chunk = ""
                        
                        # If sentence itself is too long, force split
                        if len(sentence) > max_length:
                            for i in range(0, len(sentence), max_length - 100):
                                chunks.append(sentence[i:i + max_length - 100])
                        else:
                            current_chunk = sentence
                    else:
                        if current_chunk:
                            current_chunk += " " + sentence
                        else:
                            current_chunk = sentence
            else:
                current_chunk = paragraph
        else:
            if current_chunk:
                current_chunk += "\n\n" + paragraph
            else:
                current_chunk = paragraph
    
    # Add remaining chunk
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks


async def send_long_message(update, text: str, **kwargs):
    """
    Send a potentially long message, splitting if necessary.
    
    Args:
        update: Telegram update object
        text: Message text to send
        **kwargs: Additional arguments for reply_text (e.g., parse_mode)
    """
    chunks = split_long_message(text)
    
    for i, chunk in enumerate(chunks):
        if i == 0:
            await update.message.reply_text(chunk, **kwargs)
        else:
            # For subsequent chunks, add a continuation indicator
            await update.message.reply_text(f"_(continued)_\n\n{chunk}", **kwargs)
