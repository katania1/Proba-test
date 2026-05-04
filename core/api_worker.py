import json
from PyQt6.QtCore import QThread, pyqtSignal

class APIWorker(QThread):
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    log_signal = pyqtSignal(str)

    def __init__(self, provider, prompt, system_prompt="", mcp_manager=None):
        super().__init__()
        self.provider = provider
        self.prompt = prompt
        self.system_prompt = system_prompt
        self.mcp_manager = mcp_manager

    def _extract_first_json(self, text):
        """Надежный парсер: вытаскивает первый валидный JSON из любого текста"""
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

    def run(self):
        try:
            current_sys_prompt = self.system_prompt
            
            if self.mcp_manager:
                tools_schema = self.mcp_manager.get_tools_schema()
                tools_instruction = (
                    "\n\n--- ДОСТУПНЫЕ ИНСТРУМЕНТЫ (MCP) ---\n"
                    "У тебя есть доступ к внешним инструментам (Context7, Поиск, БД).\n"
                    "АБСОЛЮТНЫЙ ПРИОРИТЕТ: Если тебе нужно вызвать инструмент, "
                    "ВЕРНИ ТОЛЬКО ОДИН JSON в формате:\n"
                    '{"tool": "имя_инструмента", "args": {"ключ": "значение"}}\n'
                    "Ты можешь вызывать инструменты ПО ОЧЕРЕДИ несколько раз, пока не соберешь всю нужную информацию.\n"
                    "Список инструментов:\n" + json.dumps(tools_schema, ensure_ascii=False, indent=2)
                )
                current_sys_prompt = tools_instruction + "\n\n" + current_sys_prompt

            current_prompt = self.prompt
            max_steps = 5 # ИИ может сделать до 5 вызовов инструментов подряд
            
            for step in range(max_steps):
                result = self.provider.generate(current_prompt, current_sys_prompt)
                
                if self.mcp_manager:
                    marker = '`' * 3
                    clean_result = result.replace(f'{marker}json', '').replace(marker, '').strip()
                    command = self._extract_first_json(clean_result)
                    
                    # Проверяем, что это именно запрос инструмента, а не финальный ответ Оркестратора
                    if command and isinstance(command, dict) and "tool" in command and "updates" not in command:
                        tool_name = command.get("tool")
                        args = command.get("args", {})
                        
                        self.log_signal.emit(f"⚙️ ИИ использует: {tool_name} (Шаг {step+1}/{max_steps})...")
                        tool_result = self.mcp_manager.execute_tool(tool_name, args)
                        
                        current_prompt = (
                            f"Результат выполнения '{tool_name}':\n"
                            f"-------------------\n{tool_result}\n-------------------\n\n"
                            f"Если нужна еще информация - вызови следующий инструмент.\n"
                            f"Если информации достаточно, дай финальный ответ СТРОГО в формате Оркестратора."
                        )
                        
                        self.log_signal.emit(f"🧠 ИИ анализирует результаты ({tool_name})...")
                        continue # Идем на следующий круг цикла (отправляем ИИ результаты)
                
                # Если ИИ не вызвал инструмент или выдал финальный JSON с кодом — завершаем работу
                self.finished_signal.emit(result)
                return 

            # Если ИИ застрял и сделал 5 вызовов подряд
            self.error_signal.emit("API Error: Превышен лимит шагов Агента (зацикливание).")

        except Exception as e:
            self.error_signal.emit(f"API Error: {str(e)}")