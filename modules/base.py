"""
Базовый класс для всех модулей бота
"""
from abc import ABC, abstractmethod
from typing import List, Optional
from telegram import Update
from telegram.ext import Application, BaseHandler


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
