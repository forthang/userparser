import logging
from typing import List, Optional, Tuple
from bot.database.models import Keyword, City
from bot.utils.cities_data import search_city_in_text

logger = logging.getLogger(__name__)


class MessageParser:
    def __init__(
        self,
        keywords: List[Keyword],
        cities: List[City],
    ):
        self.keywords = [kw.word.lower() for kw in keywords]
        self.cities = cities

    def check_message(self, text: str) -> Tuple[bool, Optional[str], Optional[str]]:
        if not text:
            return False, None, None

        text_lower = text.lower()

        found_keyword = None
        for keyword in self.keywords:
            if keyword in text_lower:
                found_keyword = keyword
                break

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
    if not text:
        return False

    text_lower = text.lower()

    keyword_found = False
    for keyword in keywords:
        if keyword.lower() in text_lower:
            keyword_found = True
            break

    if not keyword_found:
        return False

    if city_variations:
        return search_city_in_text(text, city_variations)

    return True
