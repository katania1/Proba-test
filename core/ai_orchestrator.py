import json
import re

class AIOrchestrator:
    def __init__(self):
        self.system_prompt = (
            "Ты — главный AI-разработчик и архитектор (VibeCoder).\n\n"
            "У ТЕБЯ ЕСТЬ ДВА РЕЖИМА РАБОТЫ:\n"
            "1. РЕЖИМ ЧАТА (Вопросы, теория, примеры кода): Если пользователь задает абстрактный вопрос, "
            "просит пояснить документацию или привести пример, и ТЕБЕ НЕ НУЖНО создавать/изменять файлы в его проекте, "
            "ОТВЕЧАЙ В ФОРМАТЕ MARKDOWN (обязательно оборачивай примеры кода в тройные обратные кавычки ```язык ... ```). "
            "НЕ ИСПОЛЬЗУЙ JSON в этом режиме.\n\n"
            "2. РЕЖИМ КОДИНГА (Изменение проекта): Если задача требует создать, удалить или изменить файлы, "
            "ТЫ ОБЯЗАН ОТВЕТИТЬ СТРОГО В ФОРМАТЕ JSON.\n\n"
            "🚨 КРИТИЧЕСКОЕ ПРАВИЛО JSON: Внутри полей 'search' и 'replace' СТАРАЙСЯ ИСПОЛЬЗОВАТЬ ТОЛЬКО ОДИНАРНЫЕ КАВЫЧКИ ('). "
            "Если используешь двойные кавычки в коде — ОБЯЗАТЕЛЬНО экранируй их (\\\").\n\n"
            "Формат JSON (если нужны правки файлов):\n"
            "{\n"
            "  \"thoughts\": \"Твои мысли и план действий\",\n"
            "  \"request_files\": [\"путь/к/файлу.py\"],\n"
            "  \"create_files\": [\"путь/к/новому.py\"],\n"
            "  \"updates\": [\n"
            "    {\n"
            "      \"file_path\": \"путь/к/файлу.py\",\n"
            "      \"action\": \"modify\",\n"
            "      \"changes\": [\n"
            "        {\n"
            "          \"search\": \"Старый код\",\n"
            "          \"replace\": \"Новый код\"\n"
            "        }\n"
            "      ]\n"
            "    }\n"
            "  ]\n"
            "}"
        )

    def format_request(self, user_prompt, project_path, current_file_path=None, file_content=""):
        """Формирует финальный текстовый запрос к ИИ с добавлением контекста"""
        prompt = f"Проект находится в: {project_path}\n"
        
        if current_file_path and file_content:
            marker = '`' * 3
            prompt += f"\nСейчас открыт файл: {current_file_path}\nКод файла:\n{marker}\n{file_content}\n{marker}\n"
        
        prompt += f"\nЗАДАЧА ПОЛЬЗОВАТЕЛЯ:\n{user_prompt}"
        return prompt

    def parse_and_validate_response(self, raw_text):
        """Парсит ответ от ИИ: распознает обычный текст или валидирует JSON"""
        marker = '`' * 3
        clean_text = raw_text.replace(f'{marker}json', '').replace(marker, '').strip()
        
        # Проверяем, похоже ли это на JSON Оркестратора
        is_looks_like_json = "{" in clean_text and ("\"updates\"" in raw_text or "\"create_files\"" in raw_text or "\"request_files\"" in raw_text)
        
        # Если это явно не JSON для кода (а просто ответ-болталка или пример)
        if not is_looks_like_json:
            return {
                "status": "success", 
                "data": {
                    "thoughts": raw_text.strip(), # Отдаем весь текст пользователя как "мысли"
                    "request_files": [],
                    "create_files": [],
                    "updates": []
                }
            }
            
        # Если JSON есть, пытаемся вырезать его
        start = clean_text.find('{')
        braces = 0
        end = -1
        for i in range(start, len(clean_text)):
            if clean_text[i] == '{':
                braces += 1
            elif clean_text[i] == '}':
                braces -= 1
                if braces == 0:
                    end = i
                    break
                    
        if end == -1:
            # Если сломались скобки, но "updates" нет - возвращаем как текст
            if "\"updates\"" not in raw_text:
                return {
                    "status": "success", 
                    "data": {
                        "thoughts": raw_text.strip(), 
                        "request_files": [], 
                        "create_files": [], 
                        "updates": []
                    }
                }
            return {"status": "error", "error_message": "Некорректная структура JSON (не закрыты скобки)."}
            
        json_str = clean_text[start:end+1]
        
        try:
            data = json.loads(json_str)
            
            # Базовые проверки структуры
            if not isinstance(data, dict):
                return {"status": "error", "error_message": "Корневой элемент должен быть объектом (dict)."}
            
            # Обеспечиваем наличие обязательных ключей
            if "thoughts" not in data:
                data["thoughts"] = ""
                
            for key in ["request_files", "create_files", "updates"]:
                if key not in data or not isinstance(data[key], list):
                    data[key] = []
                    
            return {"status": "success", "data": data}
            
        except json.JSONDecodeError as e:
            # Последняя линия обороны: если JSON сломался, но файлов на изменение нет - отдаем текстом
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
            return {"status": "error", "error_message": str(e)}
        except Exception as e:
            return {"status": "error", "error_message": f"Неизвестная ошибка парсинга: {str(e)}"}