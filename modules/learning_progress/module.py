import sqlite3
import os
from datetime import date, datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes

class LearningProgressModule:
    def __init__(self):
        self.name = "learning_progress"
        self.db_path = os.getenv("SQLITE_DB_PATH", "/app/data/learning_progress.db")
        self._init_database()
        self.course_name = "Доп. курсы"  # Default course name
    
    def _init_database(self):
        """Initialize SQLite database"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                main_skills INTEGER DEFAULT 0,
                additional_courses INTEGER DEFAULT 0,
                course_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
    
    async def today_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show interactive checklist for today's progress"""
        keyboard = [
            [
                InlineKeyboardButton("⬜️ 50 скиллов", callback_data="toggle_main_0"),
                InlineKeyboardButton(f"⬜️ {self.course_name}", callback_data="toggle_additional_0")
            ],
            [InlineKeyboardButton("💾 Сохранить", callback_data="save_progress")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📚 Что сегодня изучил?",
            reply_markup=reply_markup
        )
    
    async def set_course_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set custom course name"""
        if not context.args:
            await update.message.reply_text(
                "❌ Укажи название курса\n"
                f"Текущее: {self.course_name}\n\n"
                "Пример: /set_course ABI мышление"
            )
            return
        
        self.course_name = " ".join(context.args)
        await update.message.reply_text(f"✅ Название курса изменено на: {self.course_name}")
    
    async def progress_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show progress history"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get last 10 entries
        cursor.execute('''
            SELECT date, main_skills, additional_courses, course_name, created_at
            FROM progress
            ORDER BY date DESC
            LIMIT 10
        ''')
        entries = cursor.fetchall()
        
        if not entries:
            await update.message.reply_text("📊 История пуста")
            conn.close()
            return
        
        # Get statistics
        cursor.execute('''
            SELECT 
                COUNT(*) as total_days,
                SUM(main_skills) as main_count,
                SUM(additional_courses) as additional_count
            FROM progress
        ''')
        stats = cursor.fetchone()
        conn.close()
        
        # Format message
        message = f"📊 **История обучения**\n\n"
        message += f"📈 Статистика:\n"
        message += f"• Всего дней: {stats[0]}\n"
        message += f"• 50 скиллов: {stats[1]} раз\n"
        message += f"• Доп. курсы: {stats[2]} раз\n\n"
        message += f"📅 Последние записи:\n"
        
        for entry in entries:
            date_str, main, additional, course, created = entry
            icons = []
            if main:
                icons.append("✅ 50 скиллов")
            if additional:
                icons.append(f"✅ {course or 'Доп. курсы'}")
            
            if icons:
                message += f"\n{date_str}: {', '.join(icons)}"
            else:
                message += f"\n{date_str}: ⬜️ Ничего"
        
        await update.message.reply_text(message, parse_mode="Markdown")
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button clicks"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data.startswith("toggle_"):
            # Toggle checkbox
            parts = data.split("_")
            field = parts[1]  # main or additional
            current_state = int(parts[2])  # 0 or 1
            new_state = 1 - current_state
            
            # Update keyboard
            keyboard = query.message.reply_markup.inline_keyboard
            for row in keyboard:
                for button in row:
                    if button.callback_data == data:
                        if field == "main":
                            icon = "☑️" if new_state else "⬜️"
                            button.text = f"{icon} 50 скиллов"
                            button.callback_data = f"toggle_main_{new_state}"
                        elif field == "additional":
                            icon = "☑️" if new_state else "⬜️"
                            button.text = f"{icon} {self.course_name}"
                            button.callback_data = f"toggle_additional_{new_state}"
            
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif data == "save_progress":
            # Extract states from keyboard
            keyboard = query.message.reply_markup.inline_keyboard
            main_skills = 0
            additional_courses = 0
            
            for row in keyboard:
                for button in row:
                    if "toggle_main" in button.callback_data:
                        main_skills = int(button.callback_data.split("_")[2])
                    elif "toggle_additional" in button.callback_data:
                        additional_courses = int(button.callback_data.split("_")[2])
            
            # Save to database
            today = date.today().isoformat()
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if entry for today already exists
            cursor.execute("SELECT id FROM progress WHERE date = ?", (today,))
            existing = cursor.fetchone()
            
            if existing:
                cursor.execute('''
                    UPDATE progress 
                    SET main_skills = ?, additional_courses = ?, course_name = ?
                    WHERE date = ?
                ''', (main_skills, additional_courses, self.course_name, today))
            else:
                cursor.execute('''
                    INSERT INTO progress (date, main_skills, additional_courses, course_name)
                    VALUES (?, ?, ?, ?)
                ''', (today, main_skills, additional_courses, self.course_name))
            
            conn.commit()
            conn.close()
            
            # Show result
            result = []
            if main_skills:
                result.append("✅ 50 скиллов")
            if additional_courses:
                result.append(f"✅ {self.course_name}")
            
            if result:
                message = f"✅ Отмечено: {', '.join(result)}"
            else:
                message = "⬜️ Ничего не отмечено"
            
            await query.edit_message_text(message)
    
    def get_handlers(self):
        """Return list of handlers"""
        return [
            CommandHandler("today", self.today_command),
            CommandHandler("set_course", self.set_course_command),
            CommandHandler("progress", self.progress_command),
            CallbackQueryHandler(self.button_callback, pattern="^(toggle_|save_progress)")
        ]

# Export module instance
module = LearningProgressModule()
