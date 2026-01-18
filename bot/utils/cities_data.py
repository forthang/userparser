from typing import List, Dict

MOSCOW_SUBURBS = [
    "Королёв", "Королев", "Мытищи", "Химки", "Долгопрудный", "Долгопрудная",
    "Лобня", "Балашиха", "Реутов", "Люберцы", "Котельники", "Дзержинский",
    "Видное", "Домодедово", "Одинцово", "Красногорск", "Истра",
    "Солнечногорск", "Клин", "Дмитров", "Сергиев Посад", "Пушкино",
    "Щёлково", "Щелково", "Ногинск", "Электросталь", "Железнодорожный",
    "Подольск", "Чехов", "Серпухов", "Коломна", "Раменское", "Жуковский",
    "Троицк", "Зеленоград", "Внуково", "Шереметьево", "Домодедово",
    "Барвиха", "Рублёвка", "Рублевка", "Горки", "Наро-Фоминск",
]

SPB_SUBURBS = [
    "Пушкин", "Павловск", "Петергоф", "Кронштадт", "Колпино",
    "Сестрорецк", "Зеленогорск", "Ломоносов", "Гатчина", "Всеволожск",
    "Мурино", "Кудрово", "Шушары", "Пулково", "Девяткино",
]

CITIES_DATA: Dict[str, Dict] = {
    "москва": {
        "variations": [
            "москва", "москве", "москву", "москвы", "московский", "московская",
            "мск", "moscow", "msk",
        ],
        "suburbs": MOSCOW_SUBURBS,
    },
    "санкт-петербург": {
        "variations": [
            "санкт-петербург", "санкт петербург", "петербург", "питер", "спб",
            "петербурге", "питере", "ленинград", "saint petersburg", "spb",
        ],
        "suburbs": SPB_SUBURBS,
    },
    "екатеринбург": {
        "variations": [
            "екатеринбург", "екатеринбурге", "екб", "екат",
            "yekaterinburg", "ekb",
        ],
        "suburbs": ["Верхняя Пышма", "Берёзовский", "Арамиль", "Среднеуральск"],
    },
    "новосибирск": {
        "variations": [
            "новосибирск", "новосибирске", "новосиб", "нск",
            "novosibirsk", "nsk",
        ],
        "suburbs": ["Бердск", "Академгородок", "Кольцово", "Обь"],
    },
    "казань": {
        "variations": [
            "казань", "казани", "kazan", "kzn",
        ],
        "suburbs": ["Иннополис", "Зеленодольск", "Высокая Гора"],
    },
    "нижний новгород": {
        "variations": [
            "нижний новгород", "нижнем новгороде", "нижний", "ннов",
            "nizhny novgorod", "nn",
        ],
        "suburbs": ["Бор", "Кстово", "Дзержинск"],
    },
    "челябинск": {
        "variations": [
            "челябинск", "челябинске", "челяб", "чел",
            "chelyabinsk", "chel",
        ],
        "suburbs": ["Копейск", "Миасс", "Златоуст"],
    },
    "самара": {
        "variations": [
            "самара", "самаре", "samara",
        ],
        "suburbs": ["Тольятти", "Новокуйбышевск", "Чапаевск"],
    },
    "ростов-на-дону": {
        "variations": [
            "ростов-на-дону", "ростов на дону", "ростов", "ростове",
            "рнд", "rostov",
        ],
        "suburbs": ["Батайск", "Аксай", "Таганрог", "Азов"],
    },
    "уфа": {
        "variations": [
            "уфа", "уфе", "ufa",
        ],
        "suburbs": ["Дёма", "Затон", "Шакша"],
    },
    "красноярск": {
        "variations": [
            "красноярск", "красноярске", "крск",
            "krasnoyarsk", "krsk",
        ],
        "suburbs": ["Дивногорск", "Сосновоборск", "Железногорск"],
    },
    "воронеж": {
        "variations": [
            "воронеж", "воронеже", "врн",
            "voronezh", "vrn",
        ],
        "suburbs": ["Нововоронеж", "Семилуки", "Рамонь"],
    },
    "пермь": {
        "variations": [
            "пермь", "перми", "perm",
        ],
        "suburbs": ["Краснокамск", "Добрянка"],
    },
    "волгоград": {
        "variations": [
            "волгоград", "волгограде", "влг",
            "volgograd", "vlg",
        ],
        "suburbs": ["Волжский", "Краснослободск"],
    },
    "краснодар": {
        "variations": [
            "краснодар", "краснодаре", "крд",
            "krasnodar", "krd",
        ],
        "suburbs": ["Анапа", "Геленджик", "Новороссийск", "Сочи", "Адлер"],
    },
    "сочи": {
        "variations": [
            "сочи", "sochi",
        ],
        "suburbs": ["Адлер", "Хоста", "Лазаревское", "Красная Поляна", "Дагомыс"],
    },
    "минск": {
        "variations": [
            "минск", "минске", "minsk", "мінск",
        ],
        "suburbs": ["Заславль", "Логойск", "Смолевичи", "Дзержинск"],
    },
}


def get_city_variations(city_name: str) -> List[str]:
    city_lower = city_name.lower().strip()

    if city_lower in CITIES_DATA:
        data = CITIES_DATA[city_lower]
        variations = list(data["variations"])
        variations.extend([s.lower() for s in data.get("suburbs", [])])
        return variations

    for key, data in CITIES_DATA.items():
        if city_lower in [v.lower() for v in data["variations"]]:
            variations = list(data["variations"])
            variations.extend([s.lower() for s in data.get("suburbs", [])])
            return variations

    return generate_variations(city_name)


def generate_variations(city_name: str) -> List[str]:
    base = city_name.lower().strip()
    variations = [base]

    if base.endswith("а"):
        variations.append(base[:-1] + "е")
        variations.append(base[:-1] + "у")
        variations.append(base[:-1] + "ы")
    elif base.endswith("ь"):
        variations.append(base[:-1] + "и")
        variations.append(base[:-1] + "ью")
    elif base.endswith("й"):
        variations.append(base[:-1] + "я")
        variations.append(base[:-1] + "ю")
        variations.append(base[:-1] + "ем")
    elif base.endswith("о"):
        variations.append(base[:-1] + "а")
        variations.append(base[:-1] + "е")
        variations.append(base[:-1] + "ом")
    else:
        variations.append(base + "а")
        variations.append(base + "е")
        variations.append(base + "ом")

    return list(set(variations))


def search_city_in_text(text: str, city_variations: List[str]) -> bool:
    text_lower = text.lower()

    for variation in city_variations:
        if variation.lower() in text_lower:
            return True

    return False
