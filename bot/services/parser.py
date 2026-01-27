import re
import logging
from typing import List, Optional, Tuple
from bot.database.models import Keyword, City
from bot.utils.cities_data import search_city_in_text

logger = logging.getLogger(__name__)


class MessageParser:
    """Парсер сообщений для поиска ключевых слов и городов"""

    def __init__(
        self,
        keywords: List[Keyword],
        cities: List[City],
    ):
        self.original_keywords = [kw.word for kw in keywords]
        self.keywords = [kw.word.lower() for kw in keywords]
        self.cities = cities

    def _find_keyword_match(self, text_lower: str) -> Optional[str]:
        """
        Поиск ключевого слова в тексте.
        Ищет совпадение слова с учётом кириллицы и пунктуации.
        "курск" найдёт: "Курск", "Курск.", "Курск!", "(Курск)", "г.Курск" и т.д.
        """
        # Нормализуем текст - убираем лишние пробелы
        text_normalized = ' ' + text_lower + ' '

        for i, keyword in enumerate(self.keywords):
            # Паттерн для кириллицы: слово может быть окружено:
            # - пробелами, началом/концом строки
            # - знаками препинания: . , ! ? : ; - ( ) " ' и т.д.
            # - цифрами или латиницей (но не другой кириллицей)

            # Используем негативный lookbehind/lookahead для кириллицы
            # [^а-яёa-z0-9] - не буква и не цифра перед/после слова
            pattern = rf'(?<![а-яёa-z0-9]){re.escape(keyword)}(?![а-яёa-z0-9])'
            if re.search(pattern, text_normalized):
                return self.original_keywords[i]

        return None

    def check_message(self, text: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """Проверяет сообщение на наличие ключевых слов и городов"""
        if not text:
            return False, None, None

        text_lower = text.lower()

        found_keyword = self._find_keyword_match(text_lower)

        if not found_keyword:
            return False, None, None

        if not self.cities:
            return True, found_keyword, None

        found_city = None
        for city in self.cities:
            variations = city.variations or []
            if search_city_in_text(text, variations):
                found_city = city.city_name
                break

        if found_city:
            return True, found_keyword, found_city

        return False, None, None

    def format_notification(
        self,
        message_text: str,
        group_name: str,
        keyword: Optional[str] = None,
        city: Optional[str] = None,
    ) -> str:
        """Форматирует уведомление о найденном заказе"""
        notification = f"🔔 <b>Новый заказ!</b>\n\n"
        notification += f"📍 Группа: {group_name}\n"

        if keyword:
            notification += f"🔤 Ключевое слово: {keyword}\n"

        if city:
            notification += f"🏙 Город: {city}\n"

        notification += f"\n📝 <b>Текст сообщения:</b>\n"

        if len(message_text) > 500:
            notification += message_text[:500] + "..."
        else:
            notification += message_text

        return notification


def is_order_message(
    text: str,
    keywords: List[str],
    city_variations: List[str] = None,
) -> bool:
    """Проверяет, является ли сообщение заказом"""
    if not text:
        return False

    text_lower = ' ' + text.lower() + ' '

    keyword_found = False
    for keyword in keywords:
        keyword_lower = keyword.lower()
        # Паттерн для кириллицы с учётом пунктуации
        pattern = rf'(?<![а-яёa-z0-9]){re.escape(keyword_lower)}(?![а-яёa-z0-9])'
        if re.search(pattern, text_lower):
            keyword_found = True
            break

    if not keyword_found:
        return False

    if city_variations:
        return search_city_in_text(text, city_variations)

    return True
