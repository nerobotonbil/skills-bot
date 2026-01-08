"""
Модуль планирования обучения с умными рекомендациями
"""
import logging
from typing import List, Dict, Optional, Tuple
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    BaseHandler
)

from modules.base import BaseModule
from modules.notion.module import notion_module
from config.settings import MAX_VALUES, CONTENT_EMOJI, CONTENT_NAMES_RU

logger = logging.getLogger(__name__)


class LearningModule(BaseModule):
    """
    Модуль планирования обучения с умными рекомендациями.
    
    Логика:
    1. Пользователь обновляет прогресс в Notion вручную
    2. Бот синхронизируется с Notion и анализирует прогресс
    3. Бот вычисляет, какой тип контента отстаёт больше всего
    4. В 20:00 отправляет уведомление с конкретной рекомендацией
    """
    
    def __init__(self):
        super().__init__(
            name="learning",
            description="Умные рекомендации для обучения на основе анализа прогресса"
        )
    
    def get_handlers(self) -> List[BaseHandler]:
        """Возвращает обработчики команд"""
        return [
            CommandHandler("today", self.today_command),
            CommandHandler("progress", self.progress_command),
            CommandHandler("skills", self.skills_command),
            CommandHandler("recommend", self.recommend_command),
            CallbackQueryHandler(self.handle_skill_selection, pattern="^skill_"),
        ]
    
    def _calculate_content_progress(self, skill: Dict) -> Dict[str, float]:
        """
        Рассчитывает прогресс по каждому типу контента в процентах.
        
        Returns:
            Словарь {тип_контента: процент_выполнения}
        """
        return {
            "Lectures": skill["lectures"] / MAX_VALUES["Lectures"] * 100,
            "Practice hours": skill["practice_hours"] / MAX_VALUES["Practice hours"] * 100,
            "Video's": skill["videos"] / MAX_VALUES["Video's"] * 100,
            "Films ": skill["films"] / MAX_VALUES["Films "] * 100,
            "VC Lectures": skill["vc_lectures"] / MAX_VALUES["VC Lectures"] * 100,
        }
    
    def _find_weakest_content_type(self, skill: Dict) -> Tuple[str, float]:
        """
        Находит тип контента с наименьшим прогрессом.
        
        Returns:
            Кортеж (тип_контента, процент_выполнения)
        """
        progress = self._calculate_content_progress(skill)
        
        # Фильтруем только незавершённые типы (< 100%)
        incomplete = {k: v for k, v in progress.items() if v < 100}
        
        if not incomplete:
            return None, 100.0
        
        # Находим минимальный прогресс
        weakest = min(incomplete.items(), key=lambda x: x[1])
        return weakest
    
    def _generate_recommendation(self, skill: Dict) -> Optional[Dict]:
        """
        Генерирует рекомендацию для навыка.
        
        Returns:
            Словарь с рекомендацией или None если навык завершён
        """
        weakest_type, progress = self._find_weakest_content_type(skill)
        
        if weakest_type is None:
            return None
        
        # Получаем текущее и максимальное значение
        field_map = {
            "Lectures": skill["lectures"],
            "Practice hours": skill["practice_hours"],
            "Video's": skill["videos"],
            "Films ": skill["films"],
            "VC Lectures": skill["vc_lectures"],
        }
        
        current = field_map[weakest_type]
        maximum = MAX_VALUES[weakest_type]
        emoji = CONTENT_EMOJI[weakest_type]
        name_ru = CONTENT_NAMES_RU[weakest_type]
        
        return {
            "skill_name": skill["name"],
            "content_type": weakest_type,
            "content_name_ru": name_ru,
            "emoji": emoji,
            "current": current,
            "maximum": maximum,
            "progress_pct": progress,
        }
    
    def _generate_smart_task(self, skills: List[Dict]) -> Optional[Dict]:
        """
        Генерирует умную задачу на основе анализа всех активных навыков.
        Выбирает навык и тип контента с наименьшим прогрессом.
        
        Returns:
            Словарь с задачей или None
        """
        if not skills:
            return None
        
        # Собираем рекомендации для всех навыков
        recommendations = []
        for skill in skills:
            rec = self._generate_recommendation(skill)
            if rec:
                recommendations.append(rec)
        
        if not recommendations:
            return None
        
        # Выбираем рекомендацию с наименьшим прогрессом
        best_rec = min(recommendations, key=lambda x: x["progress_pct"])
        return best_rec
    
    def _is_skill_completed(self, skill: Dict) -> bool:
        """Проверяет, завершён ли навык полностью"""
        return (
            skill["lectures"] >= MAX_VALUES["Lectures"] and
            skill["practice_hours"] >= MAX_VALUES["Practice hours"] and
            skill["videos"] >= MAX_VALUES["Video's"] and
            skill["films"] >= MAX_VALUES["Films "] and
            skill["vc_lectures"] >= MAX_VALUES["VC Lectures"]
        )
    
    def _get_incomplete_skills(self, skills: List[Dict]) -> List[Dict]:
        """Возвращает только незавершённые навыки"""
        return [s for s in skills if not self._is_skill_completed(s)]
    
    def _progress_bar(self, current: float, maximum: float, length: int = 10) -> str:
        """Генерирует прогресс-бар"""
        if maximum <= 0:
            return "░" * length
        filled = int(min(current / maximum, 1.0) * length)
        return "█" * filled + "░" * (length - filled)
    
    def _format_skill_progress(self, skill: Dict) -> str:
        """Форматирует прогресс по одному навыку"""
        lines = []
        lines.append(f"📚 **{skill['name']}**\n")
        
        # Рассчитываем общий прогресс
        total_current = (
            skill["lectures"] + 
            skill["practice_hours"] + 
            skill["videos"] + 
            skill["films"] + 
            skill["vc_lectures"]
        )
        total_max = (
            MAX_VALUES["Lectures"] + 
            MAX_VALUES["Practice hours"] + 
            MAX_VALUES["Video's"] + 
            MAX_VALUES["Films "] + 
            MAX_VALUES["VC Lectures"]
        )
        overall_pct = (total_current / total_max * 100) if total_max > 0 else 0
        lines.append(f"Общий прогресс: {overall_pct:.0f}%\n\n")
        
        # Прогресс-бары для каждого типа контента
        progress_items = [
            ("Lectures", skill["lectures"], "📖 Лекции"),
            ("Practice hours", skill["practice_hours"], "💪 Практика"),
            ("Video's", skill["videos"], "🎬 Видео"),
            ("Films ", skill["films"], "🎥 Фильмы"),
            ("VC Lectures", skill["vc_lectures"], "💼 VC Лекции"),
        ]
        
        for key, current, label in progress_items:
            maximum = MAX_VALUES[key]
            bar = self._progress_bar(current, maximum, 8)
            
            # Отмечаем отстающий тип контента
            weakest, _ = self._find_weakest_content_type(skill)
            marker = " ⚠️" if key == weakest else ""
            
            if key == "Practice hours":
                lines.append(f"{bar} {label}: {current:.1f}/{maximum} ч{marker}\n")
            else:
                lines.append(f"{bar} {label}: {int(current)}/{maximum}{marker}\n")
        
        return "".join(lines)
    
    async def today_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Команда /today - показывает рекомендацию на сегодня"""
        # Синхронизируемся с Notion
        await notion_module.refresh_skills_cache()
        skills = notion_module.get_skills()
        
        if not skills:
            await update.message.reply_text(
                "📚 У тебя пока нет активных навыков.\n\n"
                "Чтобы начать:\n"
                "1. Открой Notion\n"
                "2. Заполни первый прогресс-бар для навыка\n"
                "3. Используй /sync для синхронизации"
            )
            return
        
        incomplete = self._get_incomplete_skills(skills)
        
        if not incomplete:
            await update.message.reply_text(
                "🎉 Поздравляю! Все активные навыки полностью изучены!"
            )
            return
        
        # Генерируем умную рекомендацию
        task = self._generate_smart_task(incomplete)
        
        if not task:
            await update.message.reply_text("✅ На сегодня всё готово!")
            return
        
        # Формируем сообщение
        text = f"🎯 **Рекомендация на сегодня**\n\n"
        text += f"Навык: **{task['skill_name']}**\n\n"
        text += f"{task['emoji']} Посмотри **{task['content_name_ru']}**\n"
        text += f"Прогресс: {task['current']:.0f}/{task['maximum']} ({task['progress_pct']:.0f}%)\n\n"
        text += f"_Этот тип контента отстаёт больше всего._\n\n"
        text += f"После выполнения обнови прогресс в Notion и нажми /sync"
        
        await update.message.reply_text(text, parse_mode='Markdown')
    
    async def recommend_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Команда /recommend - то же что /today"""
        await self.today_command(update, context)
    
    async def skills_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Команда /skills - показывает список навыков с кнопками"""
        await self._show_skills_menu(update, context)
    
    async def _show_skills_menu(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        edit_message: bool = False
    ) -> None:
        """Показывает меню с кнопками навыков"""
        skills = notion_module.get_skills()
        
        if not skills:
            text = (
                "📚 У тебя пока нет активных навыков.\n\n"
                "Чтобы начать:\n"
                "1. Открой Notion\n"
                "2. Заполни первый прогресс-бар для навыка\n"
                "3. Используй /sync для синхронизации"
            )
            if edit_message and update.callback_query:
                await update.callback_query.edit_message_text(text)
            else:
                await update.message.reply_text(text)
            return
        
        incomplete = self._get_incomplete_skills(skills)
        
        if not incomplete:
            text = "🎉 Поздравляю! Все активные навыки полностью изучены!"
            if edit_message and update.callback_query:
                await update.callback_query.edit_message_text(text)
            else:
                await update.message.reply_text(text)
            return
        
        # Формируем сообщение
        text = "📚 **Активные навыки**\n\n"
        text += f"Изучается: {len(incomplete)} навыков\n"
        text += "Выбери навык для просмотра прогресса:"
        
        # Создаём кнопки
        keyboard = []
        for skill in incomplete:
            # Рассчитываем общий прогресс
            total_current = (
                skill["lectures"] + 
                skill["practice_hours"] + 
                skill["videos"] + 
                skill["films"] + 
                skill["vc_lectures"]
            )
            total_max = (
                MAX_VALUES["Lectures"] + 
                MAX_VALUES["Practice hours"] + 
                MAX_VALUES["Video's"] + 
                MAX_VALUES["Films "] + 
                MAX_VALUES["VC Lectures"]
            )
            pct = int(total_current / total_max * 100) if total_max > 0 else 0
            
            short_name = skill["name"][:22] + "..." if len(skill["name"]) > 25 else skill["name"]
            
            keyboard.append([
                InlineKeyboardButton(
                    f"📚 {short_name} ({pct}%)",
                    callback_data=f"skill_{skill['id'][:20]}"
                )
            ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if edit_message and update.callback_query:
            await update.callback_query.edit_message_text(
                text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
    
    async def handle_skill_selection(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Обработчик выбора навыка — показывает прогресс"""
        query = update.callback_query
        await query.answer()
        
        skill_id_prefix = query.data.replace("skill_", "")
        
        skills = notion_module.get_skills()
        skill = None
        for s in skills:
            if s["id"].startswith(skill_id_prefix):
                skill = s
                break
        
        if not skill:
            await query.edit_message_text("❌ Навык не найден. Используй /sync")
            return
        
        # Формируем сообщение с прогрессом
        text = self._format_skill_progress(skill)
        
        # Добавляем рекомендацию
        rec = self._generate_recommendation(skill)
        if rec:
            text += f"\n💡 **Рекомендация:** посмотри {rec['content_name_ru']}"
        
        # Кнопка назад
        keyboard = [[InlineKeyboardButton("⬅️ Назад к навыкам", callback_data="skill_back")]]
        
        # Специальная обработка кнопки "назад"
        if skill_id_prefix == "back":
            await self._show_skills_menu(update, context, edit_message=True)
            return
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def progress_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Команда /progress - показывает прогресс по всем навыкам"""
        skills = notion_module.get_skills()
        
        if not skills:
            await update.message.reply_text(
                "📚 У тебя пока нет активных навыков.\n"
                "Начни изучать навык в Notion, затем используй /sync"
            )
            return
        
        text = f"📊 **Прогресс по навыкам**\n"
        text += f"Активных: {len(skills)}\n\n"
        
        for skill in skills:
            text += self._format_skill_progress(skill)
            text += "\n"
        
        await update.message.reply_text(text, parse_mode='Markdown')
    
    def generate_evening_task_message(self, skills: List[Dict]) -> str:
        """
        Генерирует вечернее сообщение с задачей на основе анализа прогресса.
        Вызывается в 20:00.
        """
        if not skills:
            return (
                "🌆 **Добрый вечер!**\n\n"
                "У тебя пока нет активных навыков.\n"
                "Начни изучать что-то новое в Notion!"
            )
        
        incomplete = self._get_incomplete_skills(skills)
        
        if not incomplete:
            return (
                "🌆 **Добрый вечер!**\n\n"
                "🎉 Все активные навыки изучены!\n"
                "Время начать новый навык."
            )
        
        # Генерируем умную рекомендацию
        task = self._generate_smart_task(incomplete)
        
        if not task:
            return "🌆 **Добрый вечер!**\n\n✅ На сегодня всё готово!"
        
        message = f"🌆 **Добрый вечер!**\n\n"
        message += f"🎯 **Задача на сегодня:**\n\n"
        message += f"Навык: **{task['skill_name']}**\n"
        message += f"{task['emoji']} Посмотри **{task['content_name_ru']}**\n\n"
        message += f"Прогресс: {task['current']:.0f}/{task['maximum']} ({task['progress_pct']:.0f}%)\n\n"
        message += f"_Этот тип контента отстаёт больше всего — "
        message += f"поэтому рекомендую именно его._\n\n"
        message += f"После выполнения обнови прогресс в Notion 📝"
        
        return message
    
    def get_morning_message(self, skills: List[Dict]) -> str:
        """Генерирует утреннее сообщение"""
        message = "🌅 **Доброе утро!**\n\n"
        
        if not skills:
            message += "Начни изучать новый навык сегодня!\n"
        else:
            incomplete = self._get_incomplete_skills(skills)
            if incomplete:
                message += f"У тебя {len(incomplete)} активных навыков.\n"
                message += "Вечером в 20:00 пришлю рекомендацию.\n"
            else:
                message += "Все навыки изучены! Время начать новый.\n"
        
        message += "\n💭 За что ты благодарен этому утру?"
        return message
    
    def get_evening_message(self) -> str:
        """Генерирует вечернее сообщение с итогами (21:00)"""
        message = "🌙 **Подводим итоги дня**\n\n"
        message += "Посмотри свой прогресс: /progress\n"
        message += "\n💭 За что ты благодарен этому дню?"
        return message


# Экземпляр модуля
learning_module = LearningModule()
