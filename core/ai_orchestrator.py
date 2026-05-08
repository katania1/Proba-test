import json
import re

class AIOrchestrator:
    def __init__(self):
        self.system_prompt = (
            "Ты — главный AI-разработчик и архитектор (VibeCoder).\n\n"
            "У ТЕБЯ ЕСТЬ ДВА РЕЖИМА РАБОТЫ:\n"
            "1. РЕЖИМ ЧАТА (Вопросы, теория, примеры кода): Если пользователь задает абстрактный вопрос, "
            "просит пояснить документацию или привести пример, и ТЕБЕ НЕ НУЖНО создавать/изменять файлы в его проекте, "
            "ОТВЕЧАЙ В ФОРМАТЕ MARKDOWN. Можешь использовать блоки кода ```.\n"
            "ДЕТЕКТОР БОЛТАЛКИ: Если запрос короткий и не содержит требований изменить код — это режим чата.\n\n"
            
            "2. РЕЖИМ КОДИНГА (Изменение или создание файлов проекта): Если задача требует написать функционал, "
            "исправить баг или внедрить фичу в существующие файлы, "
            "ТЫ ОБЯЗАН ОТВЕТИТЬ СТРОГО В ФОРМАТЕ JSON. ЭТО КРИТИЧЕСКИ ВАЖНО ДЛЯ АВТОМАТИКИ IDE!\n\n"
            
            "🚨 КРИТИЧЕСКИЕ ПРАВИЛА JSON-РЕЖИМА:\n"
            "- НИКАКОГО Markdown текста до или после JSON. Ответ должен начинаться с `{` и заканчиваться на `}`.\n"
            "- Внутри полей 'search' и 'replace' СТАРАЙСЯ ИСПОЛЬЗОВАТЬ ТОЛЬКО ОДИНАРНЫЕ КАВЫЧКИ ('). "
            "Если используешь двойные кавычки в коде — ОБЯЗАТЕЛЬНО тщательно экранируй их (\\\"). Иначе JSON-парсер сломается.\n"
            "- Используй поле 'search' для точного поиска куска кода (от 1 до 10 строк), который нужно заменить. "
            "Копируй код для 'search' СЛОВО В СЛОВО из предоставленных тебе файлов.\n"
            "- Поле 'replace' содержит новый код, который встанет вместо 'search'.\n"
            "- Не пиши комментарии вида '// остальной код без изменений'. Пиши полные рабочие блоки.\n\n"
            
            "ФОРМАТ JSON ОТВЕТА (Режим Кодинга):\n"
            "{\n"
            "  \"thoughts\": \"Твои мысли о том, как решить задачу (кратко, можно в Markdown)\",\n"
            "  \"request_files\": [\"путь/к/файлу1.py\", \"путь/к/файлу2.json\"], // Запроси файлы, если их нет в контексте\n"
            "  \"create_files\": [\"новый_файл.py\", \"новая_папка/\"], // Файлы/папки для создания с нуля\n"
            "  \"updates\": [\n"
            "    {\n"
            "      \"file_path\": \"существующий_файл.py\",\n"
            "      \"action\": \"modify\",\n"
            "      \"changes\": [\n"
            "        {\n"
            "          \"search\": \"def old_func():\\n    print('old')\",\n"
            "          \"replace\": \"def new_func():\\n    print('new')\"\n"
            "        }\n"
            "      ]\n"
            "    }\n"
            "  ]\n"
            "}"
        )

    def format_request(self, user_prompt, project_path, current_file_path=None, file_content=""):
        # Этот метод используется в основном для API, так как в браузере 
        # мы теперь отправляем правила и контекст отдельными файлами
        req = self.system_prompt + "\n\n=== ТЕКУЩИЙ СТАТУС ПРОЕКТА ===\n"
        req += f"Путь проекта: {project_path}\n"
        if current_file_path:
            req += f"Активный файл в редакторе: {current_file_path}\n"
        req += "==============================\n\n"
        req += f"ЗАДАЧА ПОЛЬЗОВАТЕЛЯ:\n{user_prompt}\n"
        return req

    def parse_and_validate_response(self, raw_text):
        """
        Умный парсер, который пытается вытащить JSON даже из грязного ответа (Markdown + JSON).
        """
        # Убираем возможные Markdown обертки
        marker = '`' * 3
        clean_text = raw_text.replace(f'{marker}json', '').replace(marker, '').strip()
        
        # Ищем границы JSON
        start = clean_text.find('{')
        end = clean_text.rfind('}')
        
        if start == -1 or end == -1:
            return {"status": "error", "error_message": "Ответ не содержит JSON-объекта. ИИ ответил обычным текстом."}
            
        json_str = clean_text[start:end+1]
        
        try:
            # Пытаемся распарсить
            data = json.loads(json_str)
            
            # Базовые проверки структуры
            if not isinstance(data, dict):
                return {"status": "error", "error_message": "Корневой элемент JSON должен быть объектом (dict)."}
            
            # Обеспечиваем наличие обязательных ключей, чтобы не падал интерфейс
            if "thoughts" not in data:
                data["thoughts"] = ""
                
            for key in ["request_files", "create_files", "updates"]:
                if key not in data or not isinstance(data[key], list):
                    data[key] = []
                    
            return {"status": "success", "data": data}
            
        except json.JSONDecodeError as e:
            # Последняя линия обороны: если JSON сломался окончательно, 
            # но внутри явно нет попытки изменить код (нет ключей updates/create_files),
            # мы прощаем ошибку и отдаем текст как обычную "болталку" (thoughts).
            if "\"updates\": [" not in raw_text and "\"create_files\": [" not in raw_text:
                return {
                    "status": "success", 
                    "data": {
                        "thoughts": raw_text.strip(), 
                        "request_files": [], 
                        "create_files": [], 
                        "updates": []
                    }
                }
            return {"status": "error", "error_message": f"Ошибка валидации формата (JSON сломан, проверьте кавычки): {str(e)}"}
        except Exception as e:
            return {"status": "error", "error_message": f"Неизвестная ошибка парсинга: {str(e)}"}