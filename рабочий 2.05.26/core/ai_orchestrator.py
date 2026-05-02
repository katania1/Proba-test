import json
import re
import os

class AIOrchestrator:
    def __init__(self):
        self.system_prompt = """Ты — VibeCoder AI, профессиональный ассистент разработчика.
ОТВЕЧАЙ СТРОГО В ФОРМАТЕ JSON. Никакого текста до или после JSON.
Формат ответа:
{
    "thoughts": "Твои мысли, логика, пояснения для пользователя (на русском). Для коммитов пиши лог сюда.",
    "request_files": ["путь/к/существующему_файлу.py", ...],
    "create_files": ["новая_папка/", "путь/к/новому_файлу.py"],
    "updates": [
        {
            "file_path": "путь/к/файлу.py",
            "action": "modify",
            "changes": [
                {
                    "search": "ТОЧНЫЙ кусок старого кода для замены (с отступами и переносами строк)",
                    "replace": "Новый код"
                }
            ]
        }
    ]
}
ПРАВИЛА:
1. Используй ТОЛЬКО относительные пути с прямыми слешами (/).
2. Если нужно создать папку, добавь слеш в конец пути (например, "styles/").
3. Если нужно прочитать файлы, которых нет в контексте, добавь их в request_files.
4. Если нужно создать новые пустые файлы или структуру папок для проекта, добавь их пути в create_files.
5. Изменения существующего или нового кода передавай в updates через точные блоки search/replace.
"""

    def format_request(self, user_prompt, project_path, current_file_path=None, file_content=""):
        context = f"[ПРОЕКТ: {project_path}]\n"
        if current_file_path:
            rel_path = os.path.relpath(current_file_path, project_path).replace('\\', '/')
            context += f"[ТЕКУЩИЙ ФАЙЛ: {rel_path}]\n\n```\n{file_content}\n```\n\n"
        return f"{self.system_prompt}\n\n{context}ЗАДАЧА ПОЛЬЗОВАТЕЛЯ:\n{user_prompt}"

    def parse_and_validate_response(self, text):
        try:
            json_str = text
            match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
            if match:
                json_str = match.group(1)
            else:
                start = text.find('{')
                end = text.rfind('}')
                if start != -1 and end != -1:
                    json_str = text[start:end+1]

            data = json.loads(json_str)
            
            if "thoughts" not in data:
                return {"status": "error", "error_message": "Отсутствует обязательное поле 'thoughts'"}
            
            return {"status": "success", "data": data}
            
        except json.JSONDecodeError as e:
            return {"status": "error", "error_message": f"Невалидный JSON: {str(e)}"}
        except Exception as e:
            return {"status": "error", "error_message": f"Системная ошибка парсинга: {str(e)}"}