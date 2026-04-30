import os
import json
import ast
import re

class AIOrchestrator:
    def __init__(self):
        # Объединенный жесткий свод правил
        self.system_prompt = """Ты — элитный AI-архитектор и разработчик.
Мы работаем над сложным проектом. Твоя задача — писать и редактировать код.

Для успешной работы ты ОБЯЗАН соблюдать следующие жесткие правила:

1. СТРОГИЙ ФОРМАТ: Ты отвечаешь ТОЛЬКО в формате JSON. Никакого текста до или после JSON. Никаких маркдаун-блоков (```json).
2. АБСОЛЮТНАЯ ПОЛНОТА КОДА: Отключи любые алгоритмы суммаризации и экономии токенов. Выдавай код измененного файла от первой до последней строчки.
3. ЗАПРЕТ НА ЗАГЛУШКИ: КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать комментарии вида `# ... остальной код без изменений ...`, `// код`, `pass` вместо реального кода.
4. НИКАКОЙ САМОДЕЯТЕЛЬНОСТИ: Любая оптимизация, рефакторинг или удаление старых функций происходят СТРОГО по запросу. Твоя задача — внедрить фичу, не сломав остальную логику.

Формат твоего ответа должен быть строго таким:
{
  "thoughts": "Краткое объяснение на русском, что ты сделал и почему",
  "updates": [
    {
      "file_path": "путь/к/файлу.py",
      "code": "ЗДЕСЬ ПОЛНЫЙ НОВЫЙ КОД ФАЙЛА"
    }
  ]
}
"""

    def build_project_bible(self, root_path):
        """Собирает дерево проекта для передачи контекста ИИ"""
        ignore_dirs = {'.git', 'venv', '__pycache__', '.vibe_backups', '.idea'}
        tree_str = "Структура проекта:\n"
        
        for dirpath, dirnames, filenames in os.walk(root_path):
            dirnames[:] = [d for d in dirnames if d not in ignore_dirs]
            
            level = dirpath.replace(root_path, '').count(os.sep)
            indent = ' ' * 4 * level
            folder_name = os.path.basename(dirpath)
            if folder_name:
                tree_str += f"{indent}📁 {folder_name}/\n"
            
            sub_indent = ' ' * 4 * (level + 1)
            for f in filenames:
                if not f.endswith(('.pyc', '.bak')):
                    tree_str += f"{sub_indent}📄 {f}\n"
                    
        return tree_str

    def format_request(self, user_prompt, project_path, current_file_path=None, file_content=""):
        """Упаковывает запрос пользователя, контекст и правила в один мощный промпт"""
        bible = self.build_project_bible(project_path)
        
        full_prompt = f"{self.system_prompt}\n\n=== КОНТЕКСТ ПРОЕКТА ===\n{bible}\n"
        
        if current_file_path and file_content:
            rel_path = os.path.relpath(current_file_path, project_path)
            full_prompt += f"\n=== ТЕКУЩИЙ ОТКРЫТЫЙ ФАЙЛ ({rel_path}) ===\n"
            full_prompt += f"{file_content}\n"
            
        full_prompt += f"\n=== ЗАДАЧА ОТ ПОЛЬЗОВАТЕЛЯ ===\n{user_prompt}"
        
        return full_prompt

    def parse_and_validate_response(self, raw_text):
        """
        Берет грязный ответ от чата, вытаскивает JSON и проверяет код на ошибки.
        Возвращает словарь: {'status': 'success'/'error', 'data': dict, 'error_message': str}
        """
        json_match = re.search(r'\{.*\}', raw_text.strip(), re.DOTALL)
        if not json_match:
            return {"status": "error", "error_message": "ИИ не вернул JSON или формат сломан."}
            
        json_str = json_match.group(0)
        
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            return {"status": "error", "error_message": f"Ошибка парсинга JSON: {str(e)}"}
            
        if "updates" in data:
            for update in data["updates"]:
                code = update.get("code", "")
                file_path = update.get("file_path", "")
                
                lazy_patterns = [r'#\s*\.\.\.', r'#\s*здесь.*код', r'#\s*остальной.*код']
                for pattern in lazy_patterns:
                    if re.search(pattern, code, re.IGNORECASE):
                        return {
                            "status": "error", 
                            "error_message": "ИИ поленился и прислал обрезанный код. Нужна регенерация."
                        }
                
                if file_path.endswith('.py'):
                    try:
                        ast.parse(code)
                    except SyntaxError as e:
                        return {
                            "status": "error", 
                            "error_message": f"ИИ прислал синтаксически сломанный код. SyntaxError: {e.msg} в строке {e.lineno}"
                        }
                        
        return {"status": "success", "data": data}