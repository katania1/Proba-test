import json
import os

class AIOrchestrator:
    def __init__(self):
        # НОВЫЙ УЛЬТИМАТИВНЫЙ ПРОМПТ С ПОДДЕРЖКОЙ SMART DIFF И ЗАПРОСА ФАЙЛОВ
        self.system_prompt = """
ТЫ — ПРОФЕССИОНАЛЬНЫЙ SENIOR-РАЗРАБОТЧИК. ТВОЯ ЗАДАЧА — ПИСАТЬ ИДЕАЛЬНЫЙ, РАБОЧИЙ КОД БЕЗ ОШИБОК И ГАЛЛЮЦИНАЦИЙ.
ОТВЕЧАЙ СТРОГО В ФОРМАТЕ JSON. ЛЮБОЙ ТЕКСТ ВНЕ JSON (ИЗВИНЕНИЯ, ПОЯСНЕНИЯ, ПРИВЕТСТВИЯ) — СТРОГО ЗАПРЕЩЕН И ПРИВЕДЕТ К ФАТАЛЬНОМУ СБОЮ СИСТЕМЫ.

ТЫ РАБОТАЕШЬ В РЕЖИМЕ "SMART DIFF" (ЧАСТИЧНЫЕ ОБНОВЛЕНИЯ).
Никогда не присылай весь файл целиком, если нужно изменить только часть! Присылай только блоки SEARCH (что найти) и REPLACE (на что заменить).

ПРАВИЛА ДЛЯ БЛОКОВ JSON:
1. "request_files": массив строк. Если для решения задачи тебе НУЖЕН КОД других файлов из структуры проекта (которых нет в текущем контексте), напиши их имена здесь (например, ["main.py", "core/utils.py"]). Если файлы не нужны, оставь массив пустым [].
2. "updates": массив обновлений кода.
   - "file_path": путь к файлу.
   - "action": "modify" (изменить) или "create" (создать новый).
   - "changes": список блоков изменений (только для "modify"!).
      - "search": ТОЧНЫЙ кусок существующего кода для замены (минимум 2-4 строки для уникальности).
      - "replace": НОВЫЙ кусок кода на замену.
   - "code": полный код (используй ТОЛЬКО если "action" == "create").

ИДЕАЛЬНАЯ СТРУКТУРА JSON-ОТВЕТА (ЕСЛИ НУЖЕН КОНТЕКСТ):
{
  "thoughts": "Чтобы добавить эту функцию, мне нужно посмотреть, как устроена база данных в db.py.",
  "request_files": ["core/db.py"],
  "updates": []
}

ИДЕАЛЬНАЯ СТРУКТУРА JSON-ОТВЕТА (ЕСЛИ КОНТЕКСТА ХВАТАЕТ):
{
  "thoughts": "Я вижу, что нужно добавить кнопку.",
  "request_files": [],
  "updates": [
    {
      "file_path": "core/ui_main.py",
      "action": "modify",
      "changes": [
        {
          "search": "old_code()",
          "replace": "new_code()"
        }
      ]
    }
  ]
}
"""

    def get_project_structure(self, project_path):
        structure = []
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in ['.vibe_backups', 'venv', '__pycache__', '.git', '.vibecoder']]
            level = root.replace(project_path, '').count(os.sep)
            indent = ' ' * 4 * level
            structure.append(f"{indent}{os.path.basename(root)}/")
            subindent = ' ' * 4 * (level + 1)
            for f in files:
                structure.append(f"{subindent}{f}")
        return '\n'.join(structure)

    def format_request(self, user_prompt, project_path, current_file_path=None, file_content=None):
        structure = self.get_project_structure(project_path)
        
        full_prompt = f"{self.system_prompt}\n\n"
        full_prompt += f"=== ТЕКУЩАЯ СТРУКТУРА ПРОЕКТА ===\n{structure}\n\n"
        
        if current_file_path and file_content:
            full_prompt += f"=== АКТИВНЫЙ ФАЙЛ ({os.path.basename(current_file_path)}) ===\n{file_content}\n\n"
            
        full_prompt += f"=== ЗАДАЧА ОТ ПОЛЬЗОВАТЕЛЯ ===\n{user_prompt}"
        return full_prompt

    def parse_and_validate_response(self, raw_text):
        cleaned_text = raw_text.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.startswith("```"):
            cleaned_text = cleaned_text[3:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]
            
        cleaned_text = cleaned_text.strip()

        try:
            data = json.loads(cleaned_text)
            return {"status": "ok", "data": data}
        except json.JSONDecodeError as e:
            return {"status": "error", "error_message": f"Ошибка парсинга JSON: {e}\nСырой текст:\n{cleaned_text[:200]}..."}