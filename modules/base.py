"""
Базовый класс для всех модулей бота
"""
import logging
from abc import ABC, abstractmethod
from functools import wraps
from typing import List, Optional
from telegram import Update
from telegram.ext import Application, BaseHandler, ContextTypes

from config.settings import ALLOWED_USER_ID

logger = logging.getLogger(__name__)


def owner_only(func):
    """Декоратор для ограничения доступа только для владельца"""
    @wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id != ALLOWED_USER_ID:
            logger.warning(f"Попытка доступа от неавторизованного пользователя: {user_id}")
            if update.message:
                await update.message.reply_text(
                    "⛔ Этот бот приватный и доступен только владельцу."
                )
            elif update.callback_query:
                await update.callback_query.answer(
                    "⛔ Доступ запрещён", show_alert=True
                )
            return
        return await func(self, update, context, *args, **kwargs)
    return wrapper


class BaseModule(ABC):
    """
    Абстрактный базовый класс для модулей бота.
    Все модули должны наследоваться от этого класса.
    """
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.enabled = True
        self._app: Optional[Application] = None
    
    @property
    def app(self) -> Application:
        if self._app is None:
            raise RuntimeError(f"Module {self.name} not registered with application")
        return self._app
    
    def register(self, app: Application) -> None:
        """Регистрирует модуль в приложении"""
        self._app = app
        for handler in self.get_handlers():
            app.add_handler(handler)
        self.on_register()
    
    @abstractmethod
    def get_handlers(self) -> List[BaseHandler]:
        """Возвращает список обработчиков команд для модуля"""
        pass
    
    def on_register(self) -> None:
        """Вызывается после регистрации модуля"""
        pass
    
    async def on_startup(self) -> None:
        """Вызывается при запуске бота"""
        pass
    
    async def on_shutdown(self) -> None:
        """Вызывается при остановке бота"""
        pass
    
    def enable(self) -> None:
        """Включает модуль"""
        self.enabled = True
    
    def disable(self) -> None:
        """Выключает модуль"""
        self.enabled = False
    
    def __repr__(self) -> str:
        status = "enabled" if self.enabled else "disabled"
        return f"<Module {self.name} ({status})>"
