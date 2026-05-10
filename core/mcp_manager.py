import os
import json
import sqlite3
import urllib.request
import urllib.parse
import re
import subprocess
import collections

class ExternalMCPClient:
    """
    Полноценный клиент Model Context Protocol.
    Общается с внешними серверами (Node.js/Python) через stdio по спецификации JSON-RPC 2.0.
    """
    def __init__(self, command, env=None):
        self.process = subprocess.Popen(
            command,
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            bufsize=1
        )
        self.req_id = 1
        
        self.send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "VibeCoder", "version": "1.0"}
        })
        self.send_notification("notifications/initialized")

    def send_request(self, method, params=None):
        req = {"jsonrpc": "2.0", "id": self.req_id, "method": method}
        if params: req["params"] = params
        
        self.process.stdin.write(json.dumps(req) + "\n")
        self.process.stdin.flush()
        
        while True:
            line = self.process.stdout.readline()
            if not line:
                raise Exception(f"MCP сервер разорвал соединение. Ошибка: {self.process.stderr.read()}")
            
            try:
                resp = json.loads(line)
                if "id" in resp and resp["id"] == self.req_id:
                    self.req_id += 1
                    return resp
            except json.JSONDecodeError:
                continue

    def send_notification(self, method, params=None):
        req = {"jsonrpc": "2.0", "method": method}
        if params: req["params"] = params
        self.process.stdin.write(json.dumps(req) + "\n")
        self.process.stdin.flush()

    def get_tools(self):
        resp = self.send_request("tools/list")
        return resp.get("result", {}).get("tools", [])

    def call_tool(self, name, args):
        resp = self.send_request("tools/call", {
            "name": name,
            "arguments": args
        })
        return resp.get("result", {})


class MCPManager:
    def __init__(self, project_path):
        self.project_path = project_path
        self.external_client = None
        self.external_tools = []
        
        self.status = "offline" 
        self.error_message = "MCP не инициализирован"
        
        # ВСТАВЬ СВОЙ КЛЮЧ ОТ CONTEXT7 СЮДА:
        self.context7_api_key = "ctx7sk-53f7a253-a33f-4b82-b243-6eae7aa3a016" 
        
        self._init_external_servers()

        self.internal_tools = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Поиск в интернете (DuckDuckGo). Используй для поиска общих статей и новостей.",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string", "description": "Поисковый запрос"}},
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "execute_sql",
                    "description": "Выполняет SQL-запрос (SELECT) к локальной SQLite базе данных проекта.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "db_filename": {"type": "string", "description": "Имя файла базы данных (например: database.db)"},
                            "query": {"type": "string", "description": "SQL запрос (только SELECT)"}
                        },
                        "required": ["db_filename", "query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "run_terminal_command",
                    "description": "Выполняет команду в системном терминале (например: pip install, git status). Работает в безопасном режиме (песочница).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string", "description": "Системная команда для выполнения в терминале"}
                        },
                        "required": ["command"]
                    }
                }
            },
            # --- НОВЫЙ ИНСТРУМЕНТ ФАЗЫ 34 ---
            {
                "type": "function",
                "function": {
                    "name": "analyze_log",
                    "description": "Интеллектуальный парсер текстовых файлов и логов. Читает гигантские файлы, не забивая оперативную память. Используй его для поиска ошибок (Traceback, Exception) в логах.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string", "description": "Относительный путь к файлу логов."},
                            "keyword": {"type": "string", "description": "Слово для поиска (например, 'ERROR'). Если пусто, вернутся просто последние строки файла."},
                            "tail_lines": {"type": "integer", "description": "Сколько последних строк вернуть, если keyword пуст (по умолчанию 50)."},
                            "context_lines": {"type": "integer", "description": "Сколько строк захватить до и после найденного слова (по умолчанию 5)."}
                        },
                        "required": ["file_path"]
                    }
                }
            }
        ]

    def _init_external_servers(self):
        if self.context7_api_key and self.context7_api_key != "ТВОЙ_КЛЮЧ_CONTEXT7":
            try:
                env = os.environ.copy()
                env["CONTEXT7_API_KEY"] = self.context7_api_key
                self.external_client = ExternalMCPClient("npx -y @upstash/context7-mcp", env=env)
                c7_tools = self.external_client.get_tools()
                
                for tool in c7_tools:
                    self.external_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool["name"],
                            "description": tool.get("description", ""),
                            "parameters": tool.get("inputSchema", {})
                        }
                    })
                self.status = "online"
                self.error_message = f"Context7 подключен (Доступно инструментов: {len(c7_tools)})"
            except Exception as e:
                self.status = "error"
                self.error_message = f"Ошибка Context7: {str(e)}"
                print(f"⚠️ {self.error_message}")
        else:
            self.status = "offline"
            self.error_message = "Ключ Context7 не задан. Внешние инструменты отключены."

    def get_tools_schema(self):
        return self.internal_tools + self.external_tools

    def execute_tool(self, tool_name, kwargs):
        try:
            if tool_name == "web_search":
                return self._tool_web_search(**kwargs)
            elif tool_name == "execute_sql":
                return self._tool_execute_sql(**kwargs)
            elif tool_name == "run_terminal_command":
                return self._tool_run_terminal_command(**kwargs)
            elif tool_name == "analyze_log":
                return self._tool_analyze_log(**kwargs)
            elif self.external_client:
                result = self.external_client.call_tool(tool_name, kwargs)
                content_blocks = result.get("content", [])
                if content_blocks and content_blocks[0].get("type") == "text":
                    return content_blocks[0].get("text")
                return str(result)
            else:
                return f"Инструмент '{tool_name}' не найден."
        except Exception as e:
            return f"Ошибка выполнения инструмента {tool_name}: {str(e)}"

    # ==========================================
    # РЕАЛИЗАЦИЯ ЛОКАЛЬНЫХ ИНСТРУМЕНТОВ
    # ==========================================

    def _tool_analyze_log(self, file_path, keyword=None, tail_lines=50, context_lines=5):
        """Интеллектуальный ленивый парсер логов (Фаза 34)"""
        abs_path = os.path.abspath(os.path.join(self.project_path, file_path))
        project_abs = os.path.abspath(self.project_path)
        
        # Защита от выхода за пределы проекта
        if not os.path.commonpath([project_abs]) == os.path.commonpath([project_abs, abs_path]):
            return "❌ Ошибка: доступ к файлам вне директории проекта запрещен."
            
        if not os.path.exists(abs_path):
            return f"❌ Ошибка: Файл '{file_path}' не найден."

        try:
            file_size_mb = os.path.getsize(abs_path) / (1024 * 1024)
            
            # Если ключевое слово не задано, отдаем просто "хвост" файла
            if not keyword:
                with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
                    tail = collections.deque(f, maxlen=tail_lines)
                return f"📄 Последние {len(tail)} строк файла {file_path} ({file_size_mb:.1f} MB):\n\n" + "".join(tail)

            # Если задан поиск с контекстом
            results = []
            with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
                before_buffer = collections.deque(maxlen=context_lines)
                lines_after_match = 0
                current_match_block = []
                
                for line_num, line in enumerate(f, 1):
                    # Если мы находимся в режиме записи строк ПОСЛЕ совпадения
                    if lines_after_match > 0:
                        current_match_block.append(f"{line_num}: {line.rstrip()}")
                        lines_after_match -= 1
                        
                        # Блок завершен
                        if lines_after_match == 0:
                            results.append("\n".join(current_match_block))
                            current_match_block = []
                            # Ограничиваем выдачу 5 совпадениями, чтобы не сжечь токены ИИ
                            if len(results) >= 5:
                                results.append("\n... [ПОКАЗАНЫ ПЕРВЫЕ 5 СОВПАДЕНИЙ, ОСТАЛЬНЫЕ ОБРЕЗАНЫ ДЛЯ ЭКОНОМИИ КОНТЕКСТА]")
                                break
                        continue
                        
                    # Если нашли совпадение
                    if keyword.lower() in line.lower():
                        current_match_block.append(f"--- Найден блок (строка {line_num}) ---")
                        for b_line_num, b_line in before_buffer:
                            current_match_block.append(f"{b_line_num}: {b_line.rstrip()}")
                        current_match_block.append(f">>{line_num}: {line.rstrip()}<<")
                        lines_after_match = context_lines
                    else:
                        before_buffer.append((line_num, line))
                        
                # На случай, если файл закончился до того, как блок контекста 'после' заполнился
                if current_match_block:
                     results.append("\n".join(current_match_block))
                     
            if not results:
                return f"Поиск завершен. Ключевое слово '{keyword}' не найдено в файле {file_path}."
                
            return f"🔍 Найдено '{keyword}' в {file_path}:\n\n" + "\n\n".join(results)
            
        except Exception as e:
            return f"❌ Системная ошибка при чтении лога: {str(e)}"

    def _tool_run_terminal_command(self, command):
        forbidden_keywords = [
            'rm ', 'del ', 'format ', 'shutdown', 'reboot', 'mkfs', 
            '>', '>>', 'chmod', 'chown', 'kill', 'taskkill', 'curl ', 'wget '
        ]
        
        cmd_lower = command.lower()
        for word in forbidden_keywords:
            if word in cmd_lower:
                return f"⛔ КОМАНДА ЗАБЛОКИРОВАНА (Сработала защита Песочницы): Использование конструкции '{word}' запрещено в целях безопасности."

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=15 
            )
            
            output = result.stdout.strip()
            error_output = result.stderr.strip()
            
            if result.returncode == 0:
                return f"✅ Успешно:\n{output}" if output else "✅ Команда выполнена успешно (без вывода)."
            else:
                return f"❌ Ошибка (Код {result.returncode}):\n{error_output}\n{output}"
                
        except subprocess.TimeoutExpired:
            return "⏳ ВРЕМЯ ОЖИДАНИЯ ВЫШЛО: Команда зависла или требует ручного ввода (таймаут 15 секунд). Процесс прерван."
        except Exception as e:
            return f"⚠️ Системная ошибка при выполнении: {str(e)}"

    def _tool_web_search(self, query):
        url = "https://lite.duckduckgo.com/lite/"
        data = urllib.parse.urlencode({'q': query}).encode('utf-8')
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode('utf-8')
            
            snippets = re.findall(r'class="[^"]*snippet[^"]*"[^>]*>(.*?)</td>', html, re.IGNORECASE | re.DOTALL)
            if not snippets: return "Поиск не дал результатов."
                
            clean_snippets = [re.sub(r'<[^>]+>', '', s).strip() for s in snippets[:4] if s]
            return f"Результаты веб-поиска по '{query}':\n" + "\n---\n".join(clean_snippets)
        except Exception as e:
            return f"Ошибка сети при поиске: {str(e)}"

    def _tool_execute_sql(self, db_filename, query):
        if not query.strip().upper().startswith("SELECT"):
            return "Разрешены только SELECT запросы."
            
        db_path = os.path.join(self.project_path, db_filename)
        if not os.path.exists(db_path):
            return f"Файл базы данных '{db_filename}' не найден."
            
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(query)
            column_names = [description[0] for description in cursor.description]
            rows = cursor.fetchmany(15)
            conn.close()
            
            if not rows: return "Таблица пуста или нет совпадений."
            return "\n".join([f"Колонки: {', '.join(column_names)}"] + [str(row) for row in rows])
        except Exception as e:
            return f"Ошибка SQL запроса: {str(e)}"