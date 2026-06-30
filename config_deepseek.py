# -----настройка генерации новостей----
AI_TASKS = {
    "rewrite": {
        "description": "Рерайт новостей",
        "temperature": 0.7,  # на сколько точно отвечает нейросеть 0-сухо и точно 1-максимально фантазирует(грубо говоря)
        "max_tokens": 2000,
    },
    "faq": {
        "description": "FAQ",
        "temperature": 0.6,
        "max_token": 1500,
    },  # сравнение оборудования
    "comparison": {
        "description": "сравнение моделей оборудования",
        "temperature": 0.5,
        "max_token": 2500,
    },
    "seo_description": {
        "description": "SEO описание по PDF",
        "temperature": 0.5,
        "max_token": 800,
    },
}


DEFAULT_NEWS_TASK = "comparison"
