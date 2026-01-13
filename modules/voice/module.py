"""
Voice message processing module
"""
import logging
import os
import tempfile
from typing import List, Optional
from pathlib import Path

from telegram import Update, Voice
from telegram.ext import MessageHandler, ContextTypes, BaseHandler, filters

from modules.base import BaseModule
from config.settings import OPENAI_API_KEY, DATA_DIR

logger = logging.getLogger(__name__)


class VoiceModule(BaseModule):
    """
    Module for processing voice messages.
    Converts voice to text using OpenAI Whisper.
    After transcription, passes text to AI assistant for processing.
    """
    
    def __init__(self):
        super().__init__(
            name="voice",
            description="Voice message processing and text conversion"
        )
        self._voice_dir = DATA_DIR / "voice"
        self._voice_dir.mkdir(parents=True, exist_ok=True)
        
        # Reference to AI assistant module (set on startup)
        self._ai_assistant = None
        
        # Track last transcription error for debugging
        self._last_transcription_error = None
    
    def get_handlers(self) -> List[BaseHandler]:
        """Returns handlers"""
        return [
            MessageHandler(filters.VOICE, self.handle_voice_message),
        ]
    
    def set_ai_assistant(self, ai_assistant):
        """
        Sets reference to AI assistant for processing transcribed text.
        """
        self._ai_assistant = ai_assistant
        logger.info("Voice module connected to AI Assistant")
    
    async def handle_voice_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handles voice message"""
        voice = update.message.voice
        
        await update.message.reply_text("🎤 Processing voice message...")
        
        try:
            # Download voice message
            voice_file = await context.bot.get_file(voice.file_id)
            
            # Create temporary file for saving
            with tempfile.NamedTemporaryFile(
                suffix=".ogg",
                dir=self._voice_dir,
                delete=False
            ) as tmp_file:
                voice_path = tmp_file.name
            
            # Download file
            await voice_file.download_to_drive(voice_path)
            logger.info(f"Voice file downloaded: {voice_path}")
            
            # Transcribe
            text = await self.transcribe_audio(voice_path)
            
            # Delete temporary file
            try:
                os.unlink(voice_path)
            except:
                pass
            
            if text:
                # If AI assistant exists, pass text for processing
                if self._ai_assistant:
                    await self._ai_assistant.process_voice_text(update, context, text)
                else:
                    # Otherwise just show text
                    await update.message.reply_text(
                        f"📝 Recognized text:\n\n{text}"
                    )
            else:
                # Get detailed error info
                error_details = self._last_transcription_error or "Unknown error"
                await update.message.reply_text(
                    f"❌ Couldn't recognize speech.\n\nError details:\n{error_details}\n\nTry again or check /logs"
                )
                
        except Exception as e:
            logger.error(f"Error processing voice message: {e}")
            await update.message.reply_text(
                f"❌ Processing error: {str(e)}"
            )
    
    async def transcribe_audio(self, file_path: str) -> Optional[str]:
        """
        Transcribes audio file to text.
        Uses OpenAI Whisper API.
        """
        self._last_transcription_error = None
        
        if OPENAI_API_KEY:
            text = await self._transcribe_openai(file_path)
            if text:
                return text
            else:
                self._last_transcription_error = "OpenAI Whisper API failed. Check OPENAI_API_KEY or API status."
        else:
            self._last_transcription_error = "OPENAI_API_KEY not set."
        
        # Fallback to local tool
        text = await self._transcribe_local(file_path)
        if text:
            return text
        else:
            if self._last_transcription_error:
                self._last_transcription_error += " Local transcription also failed."
            else:
                self._last_transcription_error = "Local transcription failed. manus-speech-to-text error."
        
        return None
    
    async def _transcribe_local(self, file_path: str) -> Optional[str]:
        """Transcribes using local tool"""
        import subprocess
        
        try:
            result = subprocess.run(
                ["manus-speech-to-text", file_path],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                text = result.stdout.strip()
                logger.info(f"Local transcription successful: {len(text)} chars")
                return text
            else:
                logger.warning(f"Local transcription failed: {result.stderr}")
                return None
                
        except FileNotFoundError:
            logger.warning("manus-speech-to-text not found")
            self._last_transcription_error = "manus-speech-to-text tool not found"
            return None
        except subprocess.TimeoutExpired:
            logger.warning("Local transcription timed out")
            self._last_transcription_error = "Local transcription timed out (>60s)"
            return None
        except Exception as e:
            logger.error(f"Local transcription error: {e}")
            self._last_transcription_error = f"Local transcription error: {str(e)}"
            return None
    
    async def _transcribe_openai(self, file_path: str) -> Optional[str]:
        """Transcribes using OpenAI Whisper API"""
        try:
            from openai import OpenAI
            
            client = OpenAI(api_key=OPENAI_API_KEY)
            
            with open(file_path, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="en"  # English language
                )
            
            text = transcript.text.strip()
            logger.info(f"OpenAI transcription successful: {len(text)} chars")
            return text
            
        except ImportError:
            logger.warning("OpenAI package not installed")
            self._last_transcription_error = "OpenAI package not installed"
            return None
        except Exception as e:
            logger.error(f"OpenAI transcription error: {e}")
            self._last_transcription_error = f"OpenAI API error: {str(e)}"
            return None
    
    def summarize_text(self, text: str, max_length: int = 200) -> str:
        """
        Shortens text to specified length.
        Simple implementation - cuts by sentences.
        """
        if len(text) <= max_length:
            return text
        
        # Split into sentences
        sentences = text.replace("!", ".").replace("?", ".").split(".")
        
        result = []
        current_length = 0
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            
            if current_length + len(sentence) + 2 <= max_length:
                result.append(sentence)
                current_length += len(sentence) + 2
            else:
                break
        
        if result:
            return ". ".join(result) + "."
        else:
            return text[:max_length] + "..."


# Module instance
voice_module = VoiceModule()
