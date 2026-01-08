"""
Модуль обработки голосовых сообщений
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
    Модуль для обработки голосовых сообщений.
    Конвертирует голос в текст с помощью OpenAI Whisper или локального инструмента.
    """
    
    def __init__(self):
        super().__init__(
            name="voice",
            description="Обработка голосовых сообщений и конвертация в текст"
        )
        self._voice_dir = DATA_DIR / "voice"
        self._voice_dir.mkdir(parents=True, exist_ok=True)
        
        # Callback для обработки транскрибированного текста
        self._transcription_callback = None
    
    def get_handlers(self) -> List[BaseHandler]:
        """Возвращает обработчики"""
        return [
            MessageHandler(filters.VOICE, self.handle_voice_message),
        ]
    
    def set_transcription_callback(self, callback):
        """
        Устанавливает callback для обработки транскрибированного текста.
        Callback должен принимать (update, context, text).
        """
        self._transcription_callback = callback
    
    async def handle_voice_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Обрабатывает голосовое сообщение"""
        voice = update.message.voice
        
        await update.message.reply_text("🎤 Обрабатываю голосовое сообщение...")
        
        try:
            # Скачиваем голосовое сообщение
            voice_file = await context.bot.get_file(voice.file_id)
            
            # Создаём временный файл для сохранения
            with tempfile.NamedTemporaryFile(
                suffix=".ogg",
                dir=self._voice_dir,
                delete=False
            ) as tmp_file:
                voice_path = tmp_file.name
            
            # Скачиваем файл
            await voice_file.download_to_drive(voice_path)
            logger.info(f"Voice file downloaded: {voice_path}")
            
            # Транскрибируем
            text = await self.transcribe_audio(voice_path)
            
            # Удаляем временный файл
            try:
                os.unlink(voice_path)
            except:
                pass
            
            if text:
                # Если есть callback, вызываем его
                if self._transcription_callback:
                    await self._transcription_callback(update, context, text)
                else:
                    # Иначе просто показываем текст
                    await update.message.reply_text(
                        f"📝 Распознанный текст:\n\n{text}"
                    )
            else:
                await update.message.reply_text(
                    "❌ Не удалось распознать речь. Попробуй ещё раз."
                )
                
        except Exception as e:
            logger.error(f"Error processing voice message: {e}")
            await update.message.reply_text(
                f"❌ Ошибка обработки: {str(e)}"
            )
    
    async def transcribe_audio(self, file_path: str) -> Optional[str]:
        """
        Транскрибирует аудио файл в текст.
        Использует OpenAI Whisper API или локальный инструмент.
        """
        # Сначала пробуем локальный инструмент manus-speech-to-text
        text = await self._transcribe_local(file_path)
        if text:
            return text
        
        # Если не получилось, пробуем OpenAI API
        if OPENAI_API_KEY:
            text = await self._transcribe_openai(file_path)
            if text:
                return text
        
        return None
    
    async def _transcribe_local(self, file_path: str) -> Optional[str]:
        """Транскрибирует с помощью локального инструмента"""
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
            return None
        except subprocess.TimeoutExpired:
            logger.warning("Local transcription timed out")
            return None
        except Exception as e:
            logger.error(f"Local transcription error: {e}")
            return None
    
    async def _transcribe_openai(self, file_path: str) -> Optional[str]:
        """Транскрибирует с помощью OpenAI Whisper API"""
        try:
            from openai import OpenAI
            
            client = OpenAI()
            
            with open(file_path, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="ru"  # Русский язык
                )
            
            text = transcript.text.strip()
            logger.info(f"OpenAI transcription successful: {len(text)} chars")
            return text
            
        except ImportError:
            logger.warning("OpenAI package not installed")
            return None
        except Exception as e:
            logger.error(f"OpenAI transcription error: {e}")
            return None
    
    def summarize_text(self, text: str, max_length: int = 200) -> str:
        """
        Сокращает текст до указанной длины.
        Простая реализация - обрезает по предложениям.
        """
        if len(text) <= max_length:
            return text
        
        # Разбиваем на предложения
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


# Экземпляр модуля
voice_module = VoiceModule()
