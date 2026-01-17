"""
Contacts module for managing networking contacts
Automatically extracts contact information from voice messages using AI
"""
import logging
import json
import os
import httpx
from typing import List, Optional, Dict, Any
from datetime import datetime

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    BaseHandler,
)

from modules.base import BaseModule

logger = logging.getLogger(__name__)

# Notion database configuration
CONTACTS_DATABASE_ID = "28b8db7c936780b9a5c1facea087a15a"
CONTACTS_DATA_SOURCE_ID = "28b8db7c-9367-817e-91b5-000bbc2b2534"


class ContactsModule(BaseModule):
    """
    Module for managing networking contacts in Notion.
    Automatically extracts contact information from voice messages using AI.
    """
    
    def __init__(self):
        super().__init__(
            name="contacts",
            description="Manage networking contacts in Notion via voice messages"
        )
        # Store last saved contact data for advice generation
        self.last_contact_data = {}
    
    def get_handlers(self) -> List[BaseHandler]:
        """Returns command handlers"""
        return [
            CommandHandler("contacts", self.list_contacts),
        ]
    
    async def process_contact_voice(
        self,
        transcribed_text: str,
        chat_id: int,
        context: ContextTypes.DEFAULT_TYPE
    ) -> bool:
        """
        Process voice message to extract contact information using AI.
        Returns True if contact was successfully saved.
        """
        try:
            # Use OpenAI to extract structured contact information
            contact_data = await self._extract_contact_info(transcribed_text)
            
            if not contact_data or not contact_data.get("name"):
                logger.warning("Could not extract contact information from voice message")
                return False
            
            # Save to Notion
            success = await self._save_contact_to_notion(contact_data)
            
            if success:
                # Store contact data for potential advice request
                self.last_contact_data[chat_id] = contact_data
                
                # Send confirmation to user
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"✅ *Контакт сохранён в Notion!*\n\n"
                         f"👤 Имя: {contact_data['name']}\n"
                         f"💡 Ценность: {contact_data.get('value', 'не указано')[:50]}...\n\n"
                         f"💬 Хочешь получить совет по работе с этим контактом? Отправь голосовое сообщение с вопросом!",
                    parse_mode="Markdown"
                )
                return True
            else:
                # Get detailed error from last save attempt
                error_detail = getattr(self, '_last_error', 'Unknown error')
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Ошибка при сохранении контакта в Notion\n\n"
                         f"Детали: {error_detail}"
                )
                return False
                
        except Exception as e:
            logger.error(f"Error processing contact voice: {e}")
            return False
    
    async def _extract_contact_info(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Use OpenAI to extract structured contact information from text.
        """
        try:
            from openai import AsyncOpenAI
            
            # Use original OpenAI API (not custom base_url)
            client = AsyncOpenAI(
                api_key=os.getenv("OPENAI_API_KEY"),
                base_url="https://api.openai.com/v1"
            )
            
            # Get current date for AI prompt
            current_date = datetime.now().strftime("%Y-%m-%d")
            
            system_prompt = f"""Ты помощник для извлечения информации о контактах из текста.
Текущая дата: {current_date}

Извлеки следующую информацию о человеке:
- name: имя человека (обязательно)
- value: чем этот человек интересен, ценность знакомства
- nationality: национальность (Egyptian 🇪🇬, Israeli 🇮🇱, India 🇮🇳, Russian 🇷🇺, 🇬🇪 Georgian или другая)
- date: дата встречи (формат YYYY-MM-DD. ВАЖНО: Если сказано 'сегодня' или 'today' - используй {current_date}. Если не указана явно - используй {current_date}. Если указано 'вчера' или 'yesterday' - вычти 1 день от текущей даты. Если указано конкретное количество дней назад - вычти это количество от {current_date})
- contact_type: насколько теплый контакт (🟩 Fresh Contact или 🟧Middle Contact)
- followup: дата последнего фоловапа (формат YYYY-MM-DD, если не было - null)
- warm_word: теплые слова, что запомнил из диалога
- industry: индустрия работы человека (точно как упомянуто в тексте, например: lawyer, crypto, spirituality, tech, finance и т.д. Записывай ТОЧНО то слово, которое использовал пользователь)

Верни JSON с этими полями. Если какое-то поле не найдено, не включай его в ответ (кроме name - оно обязательно).
Отвечай ТОЛЬКО валидным JSON, без дополнительного текста."""

            response = await client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                temperature=0.3,
                max_tokens=500
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Remove markdown code blocks if present
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.startswith("```"):
                result_text = result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            
            result_text = result_text.strip()
            
            # Parse JSON
            contact_data = json.loads(result_text)
            
            # Set default date if not provided
            if "date" not in contact_data:
                contact_data["date"] = datetime.now().strftime("%Y-%m-%d")
            
            # Set default contact type if not provided
            if "contact_type" not in contact_data:
                contact_data["contact_type"] = "🟩 Fresh Contact"
            
            logger.info(f"Extracted contact info: {contact_data}")
            return contact_data
            
        except Exception as e:
            logger.error(f"Error extracting contact info: {e}")
            return None
    
    async def _save_contact_to_notion(self, data: Dict[str, Any]) -> bool:
        """Save contact to Notion database"""
        try:
            import asyncio
            
            token = os.getenv("NOTION_API_TOKEN")
            
            if not token:
                logger.error("NOTION_API_TOKEN not configured")
                return False
            
            # Add small delay to avoid rate limiting (3 requests per second max)
            await asyncio.sleep(0.4)
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28"
            }
            
            # Prepare properties for Notion API
            properties = {
                "Name": {
                    "title": [{"text": {"content": data["name"]}}]
                }
            }
            
            # Add optional fields
            if data.get("value"):
                properties["What's value? "] = {
                    "rich_text": [{"text": {"content": data["value"]}}]
                }
            
            if data.get("nationality"):
                # Handle both string and list
                nationalities = data["nationality"] if isinstance(data["nationality"], list) else [data["nationality"]]
                properties["Nationality "] = {
                    "multi_select": [{"name": nat} for nat in nationalities]
                }
            
            if data.get("date"):
                properties["Date"] = {
                    "date": {"start": data["date"]}
                }
            
            if data.get("contact_type"):
                properties["type contact"] = {
                    "select": {"name": data["contact_type"]}
                }
            
            if data.get("warm_word"):
                properties["Warm Word "] = {
                    "rich_text": [{"text": {"content": data["warm_word"]}}]
                }
            
            if data.get("industry"):
                # Handle both string and list, split by commas if needed
                if isinstance(data["industry"], list):
                    industries = data["industry"]
                else:
                    # Split by comma and strip whitespace
                    industries = [ind.strip() for ind in data["industry"].split(',')]
                properties["indastry"] = {
                    "multi_select": [{"name": ind} for ind in industries if ind]
                }
            
            # Add followup if exists
            if data.get("followup"):
                properties["Last follow up"] = {
                    "date": {"start": data["followup"]}
                }
            
            # Create page in Notion
            notion_data = {
                "parent": {"database_id": CONTACTS_DATABASE_ID},
                "properties": properties
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.notion.com/v1/pages",
                    headers=headers,
                    json=notion_data,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    logger.info(f"Contact saved to Notion: {data['name']}")
                    return True
                elif response.status_code == 429:
                    # Rate limit exceeded, wait and retry once
                    logger.warning(f"Rate limit exceeded, waiting 1 second and retrying...")
                    await asyncio.sleep(1.0)
                    
                    # Retry request
                    response = await client.post(
                        "https://api.notion.com/v1/pages",
                        headers=headers,
                        json=notion_data,
                        timeout=30.0
                    )
                    
                    if response.status_code == 200:
                        logger.info(f"Contact saved to Notion after retry: {data['name']}")
                        return True
                    else:
                        logger.error(f"Failed to save contact after retry: {response.status_code} - {response.text}")
                        return False
                else:
                    error_msg = f"Status {response.status_code}: {response.text[:200]}"
                    logger.error(f"Failed to save contact to Notion: {response.status_code} - {response.text}")
                    logger.error(f"Request data: {json.dumps(notion_data, indent=2)}")
                    self._last_error = error_msg
                    return False
            
        except Exception as e:
            logger.error(f"Error saving contact to Notion: {e}")
            return False
    
    async def list_contacts(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """List recent contacts"""
        await update.message.reply_text(
            "📋 *Твои контакты в Notion:*\n\n"
            f"[Открыть базу данных](https://www.notion.so/{CONTACTS_DATABASE_ID})",
            parse_mode="Markdown"
        )
    
    async def generate_advice(
        self,
        transcribed_text: str,
        chat_id: int,
        context: ContextTypes.DEFAULT_TYPE
    ) -> bool:
        """
        Generate personalized advice for working with the last saved contact.
        """
        try:
            # Check if there's a recent contact
            if chat_id not in self.last_contact_data:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ Нет недавно сохранённого контакта. Сначала сохрани контакт, а потом запроси совет!"
                )
                return False
            
            contact_data = self.last_contact_data[chat_id]
            
            # Generate advice using AI
            from openai import AsyncOpenAI
            
            client = AsyncOpenAI(
                api_key=os.getenv("OPENAI_API_KEY"),
                base_url="https://api.openai.com/v1"
            )
            
            system_prompt = f"""Ты эксперт по нетворкингу и построению деловых отношений.

Информация о контакте:
- Имя: {contact_data.get('name', 'не указано')}
- Ценность: {contact_data.get('value', 'не указано')}
- Национальность: {contact_data.get('nationality', 'не указано')}
- Индустрия: {contact_data.get('industry', 'не указано')}
- Тип контакта: {contact_data.get('contact_type', 'не указано')}
- Теплые слова: {contact_data.get('warm_word', 'не указано')}

Пользователь просит совет по работе с этим контактом. Дай персонализированный, практичный совет на основе всей информации о контакте и запроса пользователя.

Отвечай на русском языке, кратко и по делу (2-4 предложения)."""
            
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": transcribed_text}
                ],
                temperature=0.7,
                max_tokens=500
            )
            
            advice = response.choices[0].message.content.strip()
            
            # Send advice to user
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"💡 *Совет по работе с {contact_data['name']}:*\n\n{advice}\n\n"
                     f"✅ Совет сохранён в Notion!",
                parse_mode="Markdown"
            )
            
            # Update Notion with advice
            await self._update_contact_advice(contact_data['name'], advice)
            
            # Clear last contact data
            del self.last_contact_data[chat_id]
            
            return True
            
        except Exception as e:
            logger.error(f"Error generating advice: {e}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ Ошибка при генерации совета: {str(e)}"
            )
            return False
    
    async def _update_contact_advice(self, contact_name: str, advice: str) -> bool:
        """
        Update the Advise field for a contact in Notion.
        """
        try:
            notion_token = os.getenv("NOTION_API_TOKEN")
            if not notion_token:
                logger.error("NOTION_API_TOKEN not found")
                return False
            
            headers = {
                "Authorization": f"Bearer {notion_token}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28"
            }
            
            # First, search for the contact by name
            async with httpx.AsyncClient() as client:
                # Query database for contact
                search_response = await client.post(
                    f"https://api.notion.com/v1/databases/{CONTACTS_DATABASE_ID}/query",
                    headers=headers,
                    json={
                        "filter": {
                            "property": "Name",
                            "title": {
                                "equals": contact_name
                            }
                        },
                        "page_size": 1
                    },
                    timeout=30.0
                )
                
                if search_response.status_code != 200:
                    logger.error(f"Failed to search contact: {search_response.text}")
                    return False
                
                results = search_response.json().get("results", [])
                if not results:
                    logger.error(f"Contact {contact_name} not found in Notion")
                    return False
                
                page_id = results[0]["id"]
                
                # Update the page with advice
                update_response = await client.patch(
                    f"https://api.notion.com/v1/pages/{page_id}",
                    headers=headers,
                    json={
                        "properties": {
                            "Advise": {
                                "rich_text": [{"text": {"content": advice}}]
                            }
                        }
                    },
                    timeout=30.0
                )
                
                if update_response.status_code == 200:
                    logger.info(f"Advice updated for contact: {contact_name}")
                    return True
                else:
                    logger.error(f"Failed to update advice: {update_response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error updating contact advice: {e}")
            return False
    
    def is_advice_request(self, text: str) -> bool:
        """
        Check if the text is a request for advice about a contact.
        """
        keywords = [
            # Russian
            "совет", "как работать", "как общаться", "как поддерживать",
            "что делать", "как действовать", "стратегия", "подход",
            "как с ним", "как с ней", "направление", "рекомендация",
            # English
            "advice", "how to work", "how to communicate", "how to maintain",
            "what to do", "how to approach", "strategy", "recommendation",
            "how should i", "what should i"
        ]
        
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in keywords)
    
    def is_contact_related(self, text: str) -> bool:
        """
        Check if the text is related to adding a contact.
        """
        keywords = [
            # Russian
            "познакомился", "познакомилась", "встретил", "встретила",
            "новый человек", "новый контакт", "нетворкинг",
            "контакт", "знакомство", "встреча с",
            "новое знакомство", "новое знакомство это",
            "запиши контакт", "добавь контакт", "сохрани контакт",
            # English
            "met someone", "met a", "i met", "new contact", "networking",
            "new acquaintance", "new acquaintance but",
            "met her", "met him", "met this", "wonderful girl", "wonderful guy",
            "interesting person", "interesting guy", "interesting girl",
            "would like to meet", "want to meet again", "meet her again", "meet him again",
            "talked to", "talked with", "had a conversation", "spoke with",
            "save contact", "add contact", "record contact"
        ]
        
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in keywords)


# Module instance
contacts_module = ContactsModule()
