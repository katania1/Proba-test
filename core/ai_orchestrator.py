import json
import re
import html
import markdown
from pygments.formatters import HtmlFormatter

class AIOrchestrator:
    def __init__(self):
        # Хранилище для кодовых блоков (чтобы не перегружать ссылки длинным текстом)
        self.code_blocks_memory = {}
        self.code_block_counter = 0
        
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
            
            if "thoughts" not in data and "updates" not in data and "create_files" not in data:
                dump = json.dumps(data, ensure_ascii=False, indent=2)
                data["thoughts"] = f"⚠️ **Внимание: ИИ выдал нестандартный JSON:**\n{marker}json\n{dump}\n{marker}"
            
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

    def extract_first_json(self, text):
        start = text.find('{')
        if start == -1: return None
        braces = 0
        for i in range(start, len(text)):
            if text[i] == '{': braces += 1
            elif text[i] == '}':
                braces -= 1
                if braces == 0:
                    try: return json.loads(text[start:i+1])
                    except: return None
        return None

    def extract_thoughts_robustly(self, raw_text):
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
                if match: return match.group(1).replace('\\n', '\n').replace('\\"', '"')
        marker = '`' * 3
        return raw_text.replace(f'{marker}json', '').replace(marker, '').strip()

    def markdown_to_html(self, text):
        """Рендерит Markdown текст и блоки кода в красивый HTML для чата через библиотеки"""
        
        custom_css = """
        <style>
            p { margin-top: 0px; margin-bottom: 12px; line-height: 1.4; }
            h1, h2, h3, h4 { color: #569cd6; margin-top: 15px; margin-bottom: 10px; font-weight: bold; }
            ul, ol { margin-top: 0px; margin-bottom: 12px; margin-left: 20px; }
            li { margin-bottom: 6px; }
            code { background-color: #2d2d2d; color: #ce9178; font-family: Consolas, monospace; padding: 2px 4px; border-radius: 3px; }
            pre { background-color: #1e1e1e; padding: 12px; border: 1px solid #3c3c3c; margin: 10px 0; font-family: Consolas, monospace; font-size: 13px; border-radius: 5px; white-space: pre-wrap; }
            pre code { background-color: transparent; padding: 0; color: inherit; }
        </style>
        """

        html_content = markdown.markdown(
            text,
            extensions=[
                'fenced_code', 
                'codehilite',  
                'tables',      
                'sane_lists',  
                'nl2br'        
            ],
            extension_configs={
                'codehilite': {
                    'noclasses': True,
                    'pygments_style': 'monokai',
                    'nobackground': True
                }
            }
        )

        # Функция вставки кнопки копирования
        def inject_copy_button(match):
            pre_open = match.group(1)   # <pre ...>
            inner_html = match.group(2) # код с тегами подсветки
            pre_close = match.group(3)  # </pre>
            
            raw_code = re.sub(r'<[^>]+>', '', inner_html)
            raw_code = html.unescape(raw_code)
            
            self.code_block_counter += 1
            block_id = f"block_{self.code_block_counter}"
            self.code_blocks_memory[block_id] = raw_code
            
            btn_html = f"""
            <div style="text-align: right; margin-bottom: -14px; margin-right: 10px; position: relative; z-index: 1;">
                <a href="copycode://{block_id}" style="color: #a6a6a6; background-color: #2d2d2d; padding: 4px 10px; text-decoration: none; font-size: 11px; font-weight: bold; border-radius: 4px; border: 1px solid #444;">📋 Копировать</a>
            </div>
            """
            return btn_html + pre_open + inner_html + pre_close

        html_content = re.sub(r'(<pre[^>]*>)(.*?)(</pre>)', inject_copy_button, html_content, flags=re.DOTALL)

        # ИСПРАВЛЕНИЕ: Удален жесткий font-size, чтобы работал зум чата
        return f"{custom_css}<div style='color: #d4d4d4; font-family: \"Segoe UI\", Arial, sans-serif;'>{html_content}</div>"