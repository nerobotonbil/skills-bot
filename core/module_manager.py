"""
Менеджер модулей - управляет загрузкой и регистрацией модулей
"""
import logging
from typing import Dict, List, Optional, Type
from telegram.ext import Application

from modules.base import BaseModule

logger = logging.getLogger(__name__)


class ModuleManager:
    """
    Управляет модулями бота.
    Позволяет динамически загружать, включать и отключать модули.
    """
    
    def __init__(self):
        self._modules: Dict[str, BaseModule] = {}
        self._app: Optional[Application] = None
    
    def register_module(self, module: BaseModule) -> None:
        """Регистрирует модуль в менеджере"""
        if module.name in self._modules:
            logger.warning(f"Module {module.name} already registered, skipping")
            return
        
        self._modules[module.name] = module
        logger.info(f"Module {module.name} registered")
        
        # Если приложение уже установлено, регистрируем обработчики
        if self._app is not None:
            module.register(self._app)
    
    def set_application(self, app: Application) -> None:
        """Устанавливает приложение Telegram и регистрирует все модули"""
        self._app = app
        for module in self._modules.values():
            module.register(app)
    
    def get_module(self, name: str) -> Optional[BaseModule]:
        """Возвращает модуль по имени"""
        return self._modules.get(name)
    
    def get_all_modules(self) -> List[BaseModule]:
        """Возвращает список всех модулей"""
        return list(self._modules.values())
    
    def get_enabled_modules(self) -> List[BaseModule]:
        """Возвращает список включённых модулей"""
        return [m for m in self._modules.values() if m.enabled]
    
    def enable_module(self, name: str) -> bool:
        """Включает модуль"""
        module = self.get_module(name)
        if module:
            module.enable()
            logger.info(f"Module {name} enabled")
            return True
        return False
    
    def disable_module(self, name: str) -> bool:
        """Отключает модуль"""
        module = self.get_module(name)
        if module:
            module.disable()
            logger.info(f"Module {name} disabled")
            return True
        return False
    
    async def startup_all(self) -> None:
        """Вызывает on_startup для всех модулей"""
        for module in self._modules.values():
            try:
                await module.on_startup()
                logger.info(f"Module {module.name} started")
            except Exception as e:
                logger.error(f"Error starting module {module.name}: {e}")
    
    async def shutdown_all(self) -> None:
        """Вызывает on_shutdown для всех модулей"""
        for module in self._modules.values():
            try:
                await module.on_shutdown()
                logger.info(f"Module {module.name} stopped")
            except Exception as e:
                logger.error(f"Error stopping module {module.name}: {e}")
    
    def __len__(self) -> int:
        return len(self._modules)
    
    def __repr__(self) -> str:
        return f"<ModuleManager with {len(self)} modules>"


# Глобальный экземпляр менеджера модулей
module_manager = ModuleManager()
