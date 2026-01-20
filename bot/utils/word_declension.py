"""
Генерация склонений русских слов для улучшения поиска
"""
from typing import List, Set


def generate_word_variations(word: str) -> List[str]:
    """
    Генерирует различные формы слова (склонения, окончания и т.д.)
    """
    word = word.lower().strip()
    variations: Set[str] = {word}

    # Если это фраза - генерируем вариации для каждого слова
    if ' ' in word:
        variations.update(_generate_phrase_variations(word))
    else:
        variations.update(_generate_single_word_variations(word))

    return list(variations)


def _generate_phrase_variations(phrase: str) -> Set[str]:
    """Генерирует вариации для фразы"""
    variations: Set[str] = {phrase}
    words = phrase.split()

    # Базовая фраза и фраза без пробелов (слитно)
    variations.add(phrase)

    # Генерируем вариации для каждого слова в фразе
    word_variations_list = []
    for word in words:
        word_vars = _generate_single_word_variations(word)
        word_vars.add(word)
        word_variations_list.append(list(word_vars))

    # Комбинируем (но ограничиваем количество)
    if len(word_variations_list) == 2:
        for v1 in word_variations_list[0][:3]:
            for v2 in word_variations_list[1][:3]:
                variations.add(f"{v1} {v2}")
    elif len(word_variations_list) == 3:
        for v1 in word_variations_list[0][:2]:
            for v2 in word_variations_list[1][:2]:
                for v3 in word_variations_list[2][:2]:
                    variations.add(f"{v1} {v2} {v3}")

    return variations


def _generate_single_word_variations(word: str) -> Set[str]:
    """Генерирует вариации для одного слова"""
    variations: Set[str] = {word}

    if len(word) < 3:
        return variations

    # Существительные женского рода на -а/-я
    if word.endswith('а'):
        base = word[:-1]
        variations.update([
            base + 'а',   # И.п.
            base + 'ы',   # Р.п.
            base + 'е',   # Д.п., П.п.
            base + 'у',   # В.п.
            base + 'ой',  # Т.п.
            base + 'ою',  # Т.п. (поэт.)
            base + 'ам',  # Д.п. мн.
            base + 'ами', # Т.п. мн.
            base + 'ах',  # П.п. мн.
        ])
    elif word.endswith('я'):
        base = word[:-1]
        variations.update([
            base + 'я',
            base + 'и',
            base + 'е',
            base + 'ю',
            base + 'ей',
            base + 'ям',
            base + 'ями',
            base + 'ях',
        ])

    # Существительные мужского рода (твёрдая основа)
    elif word.endswith(('к', 'г', 'х', 'ж', 'ш', 'щ', 'ч', 'ц')):
        variations.update([
            word + 'а',
            word + 'у',
            word + 'ом',
            word + 'е',
            word + 'и',
            word + 'ов',
            word + 'ам',
            word + 'ами',
            word + 'ах',
        ])
    elif word[-1] not in 'аеёиоуыэюя':  # согласная
        variations.update([
            word + 'а',
            word + 'у',
            word + 'ом',
            word + 'е',
            word + 'ы',
            word + 'ов',
            word + 'ам',
            word + 'ами',
            word + 'ах',
        ])

    # Существительные на -ь (м.р. и ж.р.)
    if word.endswith('ь'):
        base = word[:-1]
        variations.update([
            base + 'ь',
            base + 'я',
            base + 'ю',
            base + 'ем',
            base + 'ём',
            base + 'е',
            base + 'и',
            base + 'ей',
            base + 'ям',
            base + 'ями',
            base + 'ях',
        ])

    # Существительные на -й
    if word.endswith('й'):
        base = word[:-1]
        variations.update([
            base + 'й',
            base + 'я',
            base + 'ю',
            base + 'ем',
            base + 'е',
            base + 'и',
            base + 'ев',
            base + 'ям',
            base + 'ями',
            base + 'ях',
        ])

    # Существительные среднего рода на -о/-е
    if word.endswith('о'):
        base = word[:-1]
        variations.update([
            base + 'о',
            base + 'а',
            base + 'у',
            base + 'ом',
            base + 'е',
        ])
    elif word.endswith('е') and len(word) > 3:
        base = word[:-1]
        variations.update([
            base + 'е',
            base + 'я',
            base + 'ю',
            base + 'ем',
            base + 'и',
        ])

    # Глаголы (базовые формы)
    if word.endswith('ть'):
        base = word[:-2]
        variations.update([
            base + 'ть',
            base + 'ю',
            base + 'у',
            base + 'ешь',
            base + 'ёшь',
            base + 'ет',
            base + 'ёт',
            base + 'ем',
            base + 'ём',
            base + 'ете',
            base + 'ёте',
            base + 'ют',
            base + 'ут',
            base + 'л',
            base + 'ла',
            base + 'ло',
            base + 'ли',
            base + 'й',
            base + 'йте',
        ])

    # Прилагательные
    if word.endswith(('ый', 'ий', 'ой')):
        base = word[:-2]
        variations.update([
            base + 'ый',
            base + 'ий',
            base + 'ой',
            base + 'ая',
            base + 'яя',
            base + 'ое',
            base + 'ее',
            base + 'ые',
            base + 'ие',
            base + 'ого',
            base + 'его',
            base + 'ому',
            base + 'ему',
            base + 'ым',
            base + 'им',
            base + 'ом',
            base + 'ем',
            base + 'ую',
            base + 'юю',
        ])

    return variations


def generate_keywords_with_variations(keywords: List[str]) -> List[str]:
    """
    Для списка ключевых слов генерирует все вариации.
    Возвращает уникальный список всех слов и их вариаций.
    """
    all_variations: Set[str] = set()

    for keyword in keywords:
        all_variations.update(generate_word_variations(keyword))

    return list(all_variations)
