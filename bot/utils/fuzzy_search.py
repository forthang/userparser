"""
Fuzzy search для поиска групп по названию
"""
from typing import List, Optional, Tuple
from difflib import SequenceMatcher


def normalize_text(text: str) -> str:
    """Нормализует текст для сравнения"""
    # Приводим к нижнему регистру
    text = text.lower()
    # Убираем лишние пробелы
    text = ' '.join(text.split())
    # Заменяем ё на е
    text = text.replace('ё', 'е')
    return text


def calculate_similarity(s1: str, s2: str) -> float:
    """Вычисляет схожесть двух строк (0.0 - 1.0)"""
    s1 = normalize_text(s1)
    s2 = normalize_text(s2)
    return SequenceMatcher(None, s1, s2).ratio()


def find_best_match(
    search_query: str,
    items: List,
    get_name_func,
    threshold: float = 0.4
) -> Tuple[Optional[any], float]:
    """
    Находит наиболее похожий элемент в списке.

    Args:
        search_query: Строка для поиска
        items: Список элементов
        get_name_func: Функция для получения имени из элемента
        threshold: Минимальный порог схожести (0.0 - 1.0)

    Returns:
        Tuple[найденный_элемент_или_None, score]
    """
    search_normalized = normalize_text(search_query)

    best_match = None
    best_score = 0.0

    for item in items:
        name = get_name_func(item)
        name_normalized = normalize_text(name)

        # Проверяем точное вхождение
        if search_normalized in name_normalized:
            score = 0.9 + (len(search_normalized) / len(name_normalized)) * 0.1
            if score > best_score:
                best_score = score
                best_match = item
            continue

        # Проверяем вхождение поисковой строки в имя (partial match)
        words_search = search_normalized.split()
        words_name = name_normalized.split()

        # Проверяем совпадение отдельных слов
        matching_words = 0
        for word in words_search:
            for name_word in words_name:
                if word in name_word or name_word in word:
                    matching_words += 1
                    break

        if matching_words > 0:
            word_score = matching_words / max(len(words_search), 1)
            # Комбинируем с similarity
            seq_score = calculate_similarity(search_normalized, name_normalized)
            score = word_score * 0.6 + seq_score * 0.4

            if score > best_score:
                best_score = score
                best_match = item
            continue

        # Fuzzy match через SequenceMatcher
        score = calculate_similarity(search_normalized, name_normalized)
        if score > best_score:
            best_score = score
            best_match = item

    if best_score >= threshold:
        return best_match, best_score

    return None, 0.0


def find_matches(
    search_query: str,
    items: List,
    get_name_func,
    threshold: float = 0.4,
    max_results: int = 5
) -> List[Tuple[any, float]]:
    """
    Находит все элементы, похожие на поисковый запрос.

    Returns:
        Список кортежей (элемент, score) отсортированный по score
    """
    search_normalized = normalize_text(search_query)
    results = []

    for item in items:
        name = get_name_func(item)
        name_normalized = normalize_text(name)

        # Проверяем точное вхождение
        if search_normalized in name_normalized:
            score = 0.9 + (len(search_normalized) / len(name_normalized)) * 0.1
            results.append((item, score))
            continue

        # Проверяем совпадение слов
        words_search = search_normalized.split()
        words_name = name_normalized.split()

        matching_words = 0
        for word in words_search:
            for name_word in words_name:
                if word in name_word or name_word in word:
                    matching_words += 1
                    break

        if matching_words > 0:
            word_score = matching_words / max(len(words_search), 1)
            seq_score = calculate_similarity(search_normalized, name_normalized)
            score = word_score * 0.6 + seq_score * 0.4

            if score >= threshold:
                results.append((item, score))
            continue

        # Fuzzy match
        score = calculate_similarity(search_normalized, name_normalized)
        if score >= threshold:
            results.append((item, score))

    # Сортируем по score и возвращаем топ-N
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:max_results]
