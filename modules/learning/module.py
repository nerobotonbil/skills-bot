"""
Модуль планирования обучения с умными рекомендациями
Логика 50/50: половина рекомендаций на отстающее, половина на последовательное продвижение
"""
import logging
import json
import os
import random
from typing import List, Dict, Optional, Tuple
from datetime import date, datetime
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

# Файл для хранения истории задач
HISTORY_FILE = "/tmp/task_history.json"


class LearningModule(BaseModule):
    """
    Модуль планирования обучения с умными рекомендациями.
    
    Логика 50/50:
    - 50% рекомендаций: то, что отстаёт больше всего
    - 50% рекомендаций: последовательное продвижение (разнообразие)
    
    История:
    - Запоминает последние 7 дней выполненных задач
    - Не повторяет одни и те же задачи подряд
    """
    
    def __init__(self):
        super().__init__(
            name="learning",
            description="Умные рекомендации для обучения на основе анализа прогресса"
        )
        self.history = self._load_history()
    
    def _load_history(self) -> Dict:
        """Загружает историю задач из файла"""
        try:
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading history: {e}")
        return {"tasks": [], "last_recommendation": None}
    
    def _save_history(self):
        """Сохраняет историю задач в файл"""
        try:
            # Оставляем только последние 7 дней
            cutoff = datetime.now().timestamp() - (7 * 24 * 60 * 60)
            self.history["tasks"] = [
                t for t in self.history["tasks"] 
                if t.get("timestamp", 0) > cutoff
            ]
            with open(HISTORY_FILE, 'w') as f:
                json.dump(self.history, f)
        except Exception as e:
            logger.error(f"Error saving history: {e}")
    
    def _add_to_history(self, skill_name: str, content_type: str):
        """Добавляет задачу в историю"""
        self.history["tasks"].append({
            "skill": skill_name,
            "content_type": content_type,
            "timestamp": datetime.now().timestamp(),
            "date": date.today().isoformat()
        })
        self.history["last_recommendation"] = {
            "skill": skill_name,
            "content_type": content_type
        }
        self._save_history()
    
    def _was_recommended_recently(self, skill_name: str, content_type: str) -> bool:
        """Проверяет, рекомендовали ли эту задачу недавно (последние 2 дня)"""
        cutoff = datetime.now().timestamp() - (2 * 24 * 60 * 60)
        for task in self.history["tasks"]:
            if (task.get("skill") == skill_name and 
                task.get("content_type") == content_type and
                task.get("timestamp", 0) > cutoff):
                return True
        return False
    
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
        """
        return {
            "Lectures": skill["lectures"] / MAX_VALUES["Lectures"] * 100,
            "Practice hours": skill["practice_hours"] / MAX_VALUES["Practice hours"] * 100,
            "Video's": skill["videos"] / MAX_VALUES["Video's"] * 100,
            "Films ": skill["films"] / MAX_VALUES["Films "] * 100,
            "VC Lectures": skill["vc_lectures"] / MAX_VALUES["VC Lectures"] * 100,
        }
    
    def _find_weakest_content_type(self, skill: Dict) -> Tuple[str, float]:
        """Находит тип контента с наименьшим прогрессом."""
        progress = self._calculate_content_progress(skill)
        incomplete = {k: v for k, v in progress.items() if v < 100}
        
        if not incomplete:
            return None, 100.0
        
        weakest = min(incomplete.items(), key=lambda x: x[1])
        return weakest
    
    def _find_next_sequential_content(self, skill: Dict) -> Optional[Tuple[str, float]]:
        """
        Находит следующий тип контента для последовательного изучения.
        Приоритет: Лекции -> Видео -> VC Лекции -> Фильмы -> Практика
        """
        progress = self._calculate_content_progress(skill)
        
        # Порядок для последовательного изучения
        sequence = ["Lectures", "Video's", "VC Lectures", "Films ", "Practice hours"]
        
        for content_type in sequence:
            if progress.get(content_type, 100) < 100:
                # Проверяем, не рекомендовали ли недавно
                if not self._was_recommended_recently(skill["name"], content_type):
                    return content_type, progress[content_type]
        
        # Если всё недавно рекомендовали, возвращаем первый незавершённый
        for content_type in sequence:
            if progress.get(content_type, 100) < 100:
                return content_type, progress[content_type]
        
        return None, 100.0
    
    def _generate_recommendation(self, skill: Dict, mode: str = "weakest") -> Optional[Dict]:
        """
        Генерирует рекомендацию для навыка.
        
        Args:
            skill: Данные навыка
            mode: "weakest" - отстающее, "sequential" - последовательное
        """
        if mode == "sequential":
            content_type, progress = self._find_next_sequential_content(skill)
        else:
            content_type, progress = self._find_weakest_content_type(skill)
        
        if content_type is None:
            return None
        
        field_map = {
            "Lectures": skill["lectures"],
            "Practice hours": skill["practice_hours"],
            "Video's": skill["videos"],
            "Films ": skill["films"],
            "VC Lectures": skill["vc_lectures"],
        }
        
        current = field_map[content_type]
        maximum = MAX_VALUES[content_type]
        emoji = CONTENT_EMOJI[content_type]
        name_ru = CONTENT_NAMES_RU[content_type]
        
        return {
            "skill_name": skill["name"],
            "content_type": content_type,
            "content_name_ru": name_ru,
            "emoji": emoji,
            "current": current,
            "maximum": maximum,
            "progress_pct": progress,
            "mode": mode,
        }
    
    def _generate_smart_task(self, skills: List[Dict]) -> Optional[Dict]:
        """
        Генерирует умную задачу с логикой 50/50.
        50% - отстающее, 50% - последовательное продвижение.
        """
        if not skills:
            return None
        
        # Определяем режим: 50/50
        use_sequential = random.random() < 0.5
        mode = "sequential" if use_sequential else "weakest"
        
        # Собираем рекомендации для всех навыков
        recommendations = []
        for skill in skills:
            rec = self._generate_recommendation(skill, mode)
            if rec:
                # Проверяем, не рекомендовали ли недавно
                if not self._was_recommended_recently(rec["skill_name"], rec["content_type"]):
                    recommendations.append(rec)
        
        # Если все недавно рекомендовали, пробуем другой режим
        if not recommendations:
            alt_mode = "weakest" if use_sequential else "sequential"
            for skill in skills:
                rec = self._generate_recommendation(skill, alt_mode)
                if rec:
                    recommendations.append(rec)
        
        if not recommendations:
            # Возвращаем любую незавершённую задачу
            for skill in skills:
                rec = self._generate_recommendation(skill, "weakest")
                if rec:
                    return rec
            return None
        
        # Выбираем случайную рекомендацию для разнообразия
        if mode == "sequential":
            # Для последовательного - случайный выбор из навыков
            best_rec = random.choice(recommendations)
        else:
            # Для отстающего - выбираем с минимальным прогрессом
            best_rec = min(recommendations, key=lambda x: x["progress_pct"])
        
        # Добавляем в историю
        self._add_to_history(best_rec["skill_name"], best_rec["content_type"])
        
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
        """Генерирует красивый прогресс-бар с эмодзи"""
        if maximum <= 0:
            return "⬜" * length
        ratio = min(current / maximum, 1.0)
        filled = int(ratio * length)
        # Используем эмодзи которые хорошо отображаются в Telegram
        return "🟩" * filled + "⬜" * (length - filled)
    
    def _format_skill_progress(self, skill: Dict) -> str:
        """Форматирует прогресс по одному навыку - красивый формат"""
        lines = []
        lines.append(f"📚 *{skill['name']}*\n")
        
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
        lines.append(f"Общий прогресс: *{overall_pct:.0f}%*\n\n")
        
        # Находим отстающий тип контента
        weakest, _ = self._find_weakest_content_type(skill)
        
        # Прогресс для каждого типа контента
        progress_items = [
            ("Lectures", skill["lectures"], "📖", "Лекции"),
            ("Practice hours", skill["practice_hours"], "💪", "Практика"),
            ("Video's", skill["videos"], "🎬", "Видео"),
            ("Films ", skill["films"], "🎥", "Фильмы"),
            ("VC Lectures", skill["vc_lectures"], "🎤", "VC Лекции"),
        ]
        
        for key, current, emoji, label in progress_items:
            maximum = MAX_VALUES[key]
            bar = self._progress_bar(current, maximum, 8)
            
            # Отмечаем отстающий тип контента
            marker = " ⚠️" if key == weakest else ""
            
            if key == "Practice hours":
                value_str = f"{current:.1f}/{maximum}ч"
            else:
                value_str = f"{int(current)}/{maximum}"
            
            lines.append(f"{emoji} {label}: {value_str}{marker}\n")
            lines.append(f"    {bar}\n")
        
        return "".join(lines)
    
    async def today_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Команда /today - показывает рекомендацию на сегодня"""
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
        
        task = self._generate_smart_task(incomplete)
        
        if not task:
            await update.message.reply_text("✅ На сегодня всё готово!")
            return
        
        # Формируем сообщение с прогресс-баром
        bar = self._progress_bar(task['current'], task['maximum'], 10)
        
        # Определяем тип рекомендации
        if task.get('mode') == 'sequential':
            reason = "_Следующий шаг в изучении навыка._"
        else:
            reason = "_Этот тип контента отстаёт больше всего._"
        
        text = f"🎯 **Рекомендация на сегодня**\n\n"
        text += f"Навык: **{task['skill_name']}**\n\n"
        text += f"{task['emoji']} {task['content_name_ru']}:\n"
        text += f"{bar} {task['current']:.0f}/{task['maximum']}\n\n"
        text += f"{reason}\n\n"
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
        
        text = "📚 **Активные навыки**\n\n"
        text += f"Изучается: {len(incomplete)} навыков\n"
        text += "Выбери навык для просмотра прогресса:"
        
        keyboard = []
        for skill in incomplete:
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
        
        # Специальная обработка кнопки "назад"
        if skill_id_prefix == "back":
            await self._show_skills_menu(update, context, edit_message=True)
            return
        
        skills = notion_module.get_skills()
        skill = None
        for s in skills:
            if s["id"].startswith(skill_id_prefix):
                skill = s
                break
        
        if not skill:
            await query.edit_message_text("❌ Навык не найден. Используй /sync")
            return
        
        text = self._format_skill_progress(skill)
        
        rec = self._generate_recommendation(skill)
        if rec:
            text += f"\n💡 **Рекомендация:** посмотри {rec['content_name_ru']}"
        
        keyboard = [[InlineKeyboardButton("⬅️ Назад к навыкам", callback_data="skill_back")]]
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
        """Генерирует вечернее сообщение с задачей (20:00)"""
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
        
        task = self._generate_smart_task(incomplete)
        
        if not task:
            return "🌆 **Добрый вечер!**\n\n✅ На сегодня всё готово!"
        
        bar = self._progress_bar(task['current'], task['maximum'], 10)
        
        if task.get('mode') == 'sequential':
            reason = "Следующий шаг в изучении"
        else:
            reason = "Этот тип контента отстаёт"
        
        message = f"🌆 **Добрый вечер!**\n\n"
        message += f"🎯 **Задача на сегодня:**\n\n"
        message += f"Навык: **{task['skill_name']}**\n"
        message += f"{task['emoji']} {task['content_name_ru']}:\n"
        message += f"{bar} {task['current']:.0f}/{task['maximum']}\n\n"
        message += f"_{reason}_\n\n"
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
