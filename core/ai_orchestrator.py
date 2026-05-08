import json
import re
import html

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
            "ФОРМАТ JSON ОТВЕТА:\n"
            "{\n"
            "  \"thoughts\": \"Твои мысли о том, как решить задачу (в Markdown)\",\n"
            "  \"request_files\": [\"путь/к/файлу1.py\"], \n"
            "  \"create_files\": [\"новый_файл.py\", \"новая_папка/\"],\n"
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
        req = self.system_prompt + "\n\n=== ТЕКУЩИЙ СТАТУС ПРОЕКТА ===\n"
        req += f"Путь проекта: {project_path}\n"
        if current_file_path:
            req += f"Активный файл в редакторе: {current_file_path}\n"
        req += "==============================\n\n"
        req += f"ЗАДАЧА ПОЛЬЗОВАТЕЛЯ:\n{user_prompt}\n"
        return req

    def parse_and_validate_response(self, raw_text):
        marker = '`' * 3
        clean_text = raw_text.replace(f'{marker}json', '').replace(marker, '').strip()
        
        start = clean_text.find('{')
        end = clean_text.rfind('}')
        
        if start == -1 or end == -1:
            return {"status": "error", "error_message": "Ответ не содержит JSON-объекта. ИИ ответил обычным текстом."}
            
        json_str = clean_text[start:end+1]
        
        try:
            data = json.loads(json_str)
            
            if not isinstance(data, dict):
                return {"status": "error", "error_message": "Корневой элемент JSON должен быть объектом (dict)."}
            
            if "thoughts" not in data:
                data["thoughts"] = ""
                
            for key in ["request_files", "create_files", "updates"]:
                if key not in data or not isinstance(data[key], list):
                    data[key] = []
                    
            return {"status": "success", "data": data}
            
        except json.JSONDecodeError as e:
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

    # ==========================================
    # УТИЛИТЫ ПАРСИНГА И РЕНДЕРИНГА (Перенесено из AIController)
    # ==========================================
    def extract_first_json(self, text):
        """Пытается извлечь первый валидный JSON из грязного текста"""
        start = text.find('{')
        if start == -1: return None
        
        braces = 0
        for i in range(start, len(text)):
            if text[i] == '{': braces += 1
            elif text[i] == '}':
                braces -= 1
                if braces == 0:
                    try:
                        return json.loads(text[start:i+1])
                    except:
                        return None
        return None

    def extract_thoughts_robustly(self, raw_text):
        """Надежно извлекает поле 'thoughts' (или весь текст, если это не JSON)"""
        result = self.parse_and_validate_response(raw_text)
        if result["status"] == "success":
            return result["data"].get("thoughts", "")

        start_idx = raw_text.find('{')
        end_idx = raw_text.rfind('}') + 1
        if start_idx != -1 and end_idx != -1:
            json_str = raw_text[start_idx:end_idx]
            try:
                data = json.loads(json_str)
                return data.get("thoughts", "")
            except Exception:
                match = re.search(r'"thoughts"\s*:\s*"(.*?)"\s*,\s*"(?:request_files|create_files|updates)"', json_str, re.DOTALL)
                if match:
                    return match.group(1).replace('\\n', '\n').replace('\\"', '"')
        
        marker = '`' * 3
        return raw_text.replace(f'{marker}json', '').replace(marker, '').strip()

    def markdown_to_html(self, text):
        """Рендерит Markdown текст и блоки кода в красивый HTML для чата"""
        text = html.escape(text)
        text = f"<div style='color: #d4d4d4; line-height: 1.5;'>{text}</div>"

        def code_replacer(match):
            lang = match.group(1).strip()
            lang = lang.split('\n')[0].strip()
            code = match.group(2).strip('\n') 
            header = f"<div style='background-color: #2d2d2d; color: #858585; padding: 4px 10px; font-size: 11px; font-weight: bold; border-top-left-radius: 5px; border-top-right-radius: 5px;'>{lang.upper() if lang else 'CODE'}</div>"
            body = f"<pre style='margin: 0; padding: 10px; color: #d4d4d4; font-family: Consolas, monospace; font-size: 13px; white-space: pre-wrap;'>{code}</pre>"
            return f"</div><div style='background-color: #1e1e1e; border: 1px solid #3c3c3c; border-radius: 5px; margin: 10px 0;'>{header}{body}</div><div style='color: #d4d4d4; line-height: 1.5;'>"

        text = re.sub(r'`{3}(.*?)\n(.*?)`{3}', code_replacer, text, flags=re.DOTALL)
        text = re.sub(r'`(.*?)`', r"<code style='background-color: #3c3c3c; color: #ce9178; padding: 2px 5px; border-radius: 4px; font-family: Consolas, monospace;'>\1</code>", text)
        text = re.sub(r'\*\*(.*?)\*\*', r"<b style='color: #ffffff;'>\1</b>", text)

        parts = re.split(r'(<pre.*?</pre>)', text, flags=re.DOTALL)
        for i in range(len(parts)):
            if not parts[i].startswith('<pre'):
                parts[i] = parts[i].replace('\n', '<br>')

        return "".join(parts)